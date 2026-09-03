"""Domain registration lookup: RDAP first, plain WHOIS as a fallback.

RDAP (RFC 9082/9083) is JSON and the target server is found the same way any
RDAP client finds it -- via IANA's own bootstrap registry. Not every registry
runs one: .de (DENIC) is the most visible holdout, still text-only WHOIS at
the time this was written (verified live, not assumed). For those, a minimal
WHOIS client follows the one-hop referral from whois.iana.org to the
registry's own server. DENIC's own policy withholds registrar and every date
field on port 43 for privacy reasons -- that isn't a bug here, it is reported
back to the user as exactly that.
"""

import re
import socket
import threading
import time
from datetime import datetime, timezone

from netcore import Context, ProbeError, clean_domain, guard_target, http_get

OK, INFO, WARN, FAIL = 'ok', 'info', 'warn', 'fail'

BOOTSTRAP_URL = 'https://data.iana.org/rdap/dns.json'
BOOTSTRAP_TTL = 24 * 3600
EXPIRY_WARN_DAYS = 30

_bootstrap_cache = {'data': None, 'ts': 0.0}
_bootstrap_lock = threading.Lock()


def _finding(level: str, code: str, **args) -> dict:
    return {'level': level, 'code': code, 'args': args}


def _worst(findings: list) -> str:
    for level in (FAIL, WARN, INFO, OK):
        if any(f['level'] == level for f in findings):
            return level
    return OK


# ── RDAP bootstrap ───────────────────────────────────────────────────────────


def _load_bootstrap(ctx: Context) -> dict:
    """TLD -> [RDAP base URLs], cached for a day.

    A slow or dead IANA fetch must not break every lookup -- falls back to
    the last good copy, or an empty map (meaning: no known RDAP server, go
    straight to WHOIS) rather than raising.
    """
    with _bootstrap_lock:
        if (_bootstrap_cache['data'] is not None
                and time.time() - _bootstrap_cache['ts'] < BOOTSTRAP_TTL):
            return _bootstrap_cache['data']
    try:
        resp = http_get(ctx, BOOTSTRAP_URL, max_bytes=2 * 1024 * 1024,
                        accept='application/json')
        import json
        services = json.loads(resp['body']).get('services', [])
    except (ProbeError, ValueError):
        return _bootstrap_cache['data'] or {}
    mapping = {}
    for entry in services:
        try:
            tlds, urls = entry[0], entry[1]
        except (IndexError, TypeError, KeyError):
            continue
        for tld in tlds:
            mapping[str(tld).lower()] = urls
    with _bootstrap_lock:
        _bootstrap_cache['data'] = mapping
        _bootstrap_cache['ts'] = time.time()
    return mapping


def _tld_of(domain: str) -> str:
    return domain.rsplit('.', 1)[-1].lower()


# ── RDAP lookup ───────────────────────────────────────────────────────────────


def _rdap_fetch(ctx: Context, domain: str, base_urls: list) -> dict:
    last_error = None
    for base in base_urls:
        url = base.rstrip('/') + '/domain/' + domain
        try:
            resp = http_get(ctx, url, accept='application/rdap+json')
        except ProbeError as e:
            last_error = e.code
            continue
        if resp['status'] == 404:
            return {}
        if resp['status'] != 200:
            last_error = f"http_{resp['status']}"
            continue
        try:
            import json
            return json.loads(resp['body'])
        except ValueError:
            last_error = 'bad_json'
            continue
    raise ProbeError('rdap_unreachable', last_error or '')


def _vcard_field(vcard: list, name: str) -> str:
    for entry in (vcard[1] if len(vcard) > 1 else []):
        if entry and entry[0] == name:
            value = entry[-1]
            return value if isinstance(value, str) else ''
    return ''


def _entity_name(entity: dict) -> str:
    vcard = entity.get('vcardArray')
    if vcard:
        name = _vcard_field(vcard, 'fn')
        if name:
            return name
    return entity.get('handle', '')


def _entities_by_role(entities: list, role: str) -> list:
    out = []
    for entity in entities or ():
        if role in (entity.get('roles') or ()):
            out.append(entity)
        out.extend(_entities_by_role(entity.get('entities') or (), role))
    return out


def _event_date(events: list, action: str) -> str:
    for event in events or ():
        if event.get('eventAction') == action:
            return event.get('eventDate', '')
    return ''


def _parse_rdap_result(domain: str, data: dict) -> dict:
    findings = []
    result = {
        'domain': domain, 'source': 'rdap', 'found': bool(data),
        'registrar': '', 'abuse_email': '', 'status': list(data.get('status') or ()),
        'nameservers': [ns.get('ldhName', '').lower().rstrip('.')
                        for ns in data.get('nameservers') or ()],
        'registered': '', 'expires': '', 'last_changed': '',
        'days_until_expiry': None, 'dnssec_signed': None,
        'raw': '', 'findings': findings,
    }
    if not data:
        findings.append(_finding(WARN, 'domain_not_found', domain=domain))
        result['level'] = _worst(findings)
        return result

    registrars = _entities_by_role(data.get('entities'), 'registrar')
    if registrars:
        result['registrar'] = _entity_name(registrars[0])
        abuse = _entities_by_role(registrars[0].get('entities'), 'abuse')
        if abuse:
            result['abuse_email'] = _vcard_field(abuse[0].get('vcardArray') or [], 'email')

    events = data.get('events') or ()
    result['registered'] = _event_date(events, 'registration')
    result['expires'] = _event_date(events, 'expiration')
    result['last_changed'] = _event_date(events, 'last changed')

    secure_dns = data.get('secureDNS') or {}
    if 'delegationSigned' in secure_dns:
        result['dnssec_signed'] = bool(secure_dns['delegationSigned'])

    _apply_common_findings(result, findings)
    result['level'] = _worst(findings)
    return result


def _apply_common_findings(result: dict, findings: list) -> None:
    status_lower = [s.lower() for s in result['status']]
    if any('hold' in s for s in status_lower):
        findings.append(_finding(FAIL, 'domain_on_hold',
                                 status=[s for s in result['status'] if 'hold' in s.lower()]))
    if any('pendingdelete' in s.replace(' ', '') or 'redemptionperiod' in s.replace(' ', '')
           for s in status_lower):
        findings.append(_finding(FAIL, 'domain_pending_delete'))

    if result['registered']:
        try:
            registered = datetime.fromisoformat(result['registered'].replace('Z', '+00:00'))
            age_days = (datetime.now(timezone.utc) - registered).days
            if age_days < 30:
                findings.append(_finding(INFO, 'domain_young', days=age_days))
        except ValueError:
            pass

    if result['expires']:
        try:
            expires = datetime.fromisoformat(result['expires'].replace('Z', '+00:00'))
            days_left = (expires - datetime.now(timezone.utc)).days
            result['days_until_expiry'] = days_left
            if days_left < 0:
                findings.append(_finding(FAIL, 'domain_expired', days=abs(days_left)))
            elif days_left < EXPIRY_WARN_DAYS:
                findings.append(_finding(WARN, 'domain_expiring_soon', days=days_left))
            else:
                findings.append(_finding(OK, 'domain_expiry_ok', days=days_left))
        except ValueError:
            pass

    if not result['registrar'] and result['source'] == 'rdap':
        findings.append(_finding(INFO, 'domain_registrar_redacted'))

    if not findings:
        findings.append(_finding(OK, 'domain_found'))


# ── Plain WHOIS fallback ────────────────────────────────────────────────────

_WHOIS_FIELD_PATTERNS = (
    ('registrar', re.compile(r'^Registrar:\s*(.+)$', re.I | re.M)),
    ('registered', re.compile(r'^(?:Creation Date|Created(?: On)?|'
                              r'Registered(?: On)?|Registration Date):\s*(.+)$', re.I | re.M)),
    ('expires', re.compile(r'^(?:Registry Expiry Date|Expir(?:y|ation) Date|'
                           r'Expires(?: On)?|paid-till):\s*(.+)$', re.I | re.M)),
    ('last_changed', re.compile(r'^(?:Updated Date|Changed|Last[- ]Modified):\s*(.+)$',
                                re.I | re.M)),
)
_WHOIS_STATUS_RE = re.compile(r'^(?:Domain )?Status:\s*(.+)$', re.I | re.M)
_WHOIS_NS_RE = re.compile(r'^N(?:ame)? ?[Ss]erver:\s*(\S+)', re.I | re.M)
_WHOIS_REFERRAL_RE = re.compile(r'^whois:\s*(\S+)', re.I | re.M)


def _whois_query(ctx: Context, server: str, query: str) -> str:
    guard_target(ctx, server)
    try:
        with socket.create_connection((server, 43), timeout=ctx.dns_timeout) as sock:
            sock.sendall((query + '\r\n').encode('ascii', 'ignore'))
            chunks = []
            sock.settimeout(ctx.http_timeout)
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
        text = b''.join(chunks).decode('utf-8', 'replace')
        return text.replace('\r\n', '\n').replace('\r', '\n')
    except socket.timeout:
        raise ProbeError('whois_timeout', server)
    except OSError as e:
        raise ProbeError('whois_unreachable', f'{server}: {e}')


def _whois_lookup(ctx: Context, domain: str) -> dict:
    iana_text = _whois_query(ctx, 'whois.iana.org', domain.rsplit('.', 1)[-1])
    referral = _WHOIS_REFERRAL_RE.search(iana_text)
    if not referral:
        raise ProbeError('whois_no_referral', domain)
    server = referral.group(1)
    # DENIC's plain "<domain>" query answers with a brief domain+status-only
    # form; the fuller (still privacy-limited) one needs this exact flag.
    # Verified live, not assumed -- other registries take a bare domain name.
    query = f'-T dn {domain}' if server.lower() == 'whois.denic.de' else domain
    text = _whois_query(ctx, server, query)

    findings = []
    result = {
        'domain': domain, 'source': 'whois', 'found': True,
        'whois_server': server, 'registrar': '', 'abuse_email': '',
        'status': _WHOIS_STATUS_RE.findall(text),
        'nameservers': sorted({m.lower().rstrip('.') for m in _WHOIS_NS_RE.findall(text)}),
        'registered': '', 'expires': '', 'last_changed': '',
        'days_until_expiry': None, 'dnssec_signed': None,
        'raw': text.strip()[:4000], 'findings': findings,
    }
    low = text.lower()
    if 'no entries found' in low or 'not found' in low or 'no match' in low:
        result['found'] = False
        findings.append(_finding(WARN, 'domain_not_found', domain=domain))
        result['level'] = _worst(findings)
        return result

    for key, pattern in _WHOIS_FIELD_PATTERNS:
        m = pattern.search(text)
        if m and not result[key]:
            result[key] = m.group(1).strip()

    if not result['registered'] and not result['expires']:
        findings.append(_finding(INFO, 'whois_fields_withheld', server=server))

    _apply_common_findings(result, findings)
    result['level'] = _worst(findings)
    return result


# ── Entry point ───────────────────────────────────────────────────────────────


def check_domain(ctx: Context, domain: str) -> dict:
    domain = clean_domain(domain)
    tld = _tld_of(domain)
    bootstrap = _load_bootstrap(ctx)
    base_urls = bootstrap.get(tld)

    if base_urls:
        try:
            data = _rdap_fetch(ctx, domain, base_urls)
            return _parse_rdap_result(domain, data)
        except ProbeError:
            pass  # fall through to WHOIS below

    return _whois_lookup(ctx, domain)
