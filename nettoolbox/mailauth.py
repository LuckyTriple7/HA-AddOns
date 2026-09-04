"""Mail authentication checks: SPF, DKIM, DMARC, MTA-STS, TLS-RPT, BIMI.

Every check returns a plain dict with a `findings` list. A finding carries a
code, never a sentence — the web interface turns the code into German or
English text, so the checks stay free of language.
"""

import base64
import re

import mailprovider
from netcore import (Context, ProbeError, clean_domain, clean_selector,
                     http_get, mx_hosts, query, txt_strings)

OK, INFO, WARN, FAIL = 'ok', 'info', 'warn', 'fail'

# Selectors worth trying when the user does not know theirs. Cheap: one TXT
# question each, and a wrong guess simply answers nothing.
COMMON_SELECTORS = (
    'default', 'google', 'selector1', 'selector2', 's1', 's2', 'k1', 'k2',
    'mail', 'dkim', 'smtp', 'key1', 'mandrill', 'zoho', 'protonmail',
    'protonmail2', 'fm1', 'fm2', 'fm3', 'mimecast20200101', 'everlytickey1',
    'sig1', 'ctct1', 'pm', 'amazonses', 'hs1', 'hs2', 'mxvault',
)

SPF_LOOKUP_LIMIT = 10
SPF_VOID_LIMIT = 2


def _finding(level: str, code: str, **args) -> dict:
    return {'level': level, 'code': code, 'args': args}


def _worst(findings: list) -> str:
    """The overall pill only reflects real problems (FAIL/WARN); a purely
    informational finding (single MX, missing optional record, short-lived
    cert *type*) stays visible on its own line but never keeps the summary
    from going green. An actual near-expiry or similar risk is its own
    separate WARN/FAIL finding, unaffected by this."""
    for level in (FAIL, WARN):
        if any(f['level'] == level for f in findings):
            return level
    return OK


def _tags(record: str) -> dict:
    """Parse the `k=v; k=v` shape every mail policy record uses."""
    out = {}
    for part in record.split(';'):
        part = part.strip()
        if not part or '=' not in part:
            continue
        key, value = part.split('=', 1)
        key = key.strip().lower()
        if key and key not in out:
            out[key] = value.strip()
    return out


# ── SPF ───────────────────────────────────────────────────────────────────────

_SPF_LOOKUP_TERMS = ('include', 'a', 'mx', 'ptr', 'exists', 'redirect')
_SPF_QUALIFIERS = {'+': 'pass', '-': 'fail', '~': 'softfail', '?': 'neutral'}


def _spf_records(ctx: Context, domain: str) -> list:
    return [t for t in txt_strings(ctx, domain)
            if t.lower().startswith('v=spf1')]


def _spf_walk(ctx: Context, domain: str, record: str, seen: set,
              depth: int, state: dict) -> None:
    """Count the DNS lookups a resolving mail server would have to make.

    RFC 7208 caps this at ten; blowing the cap makes the whole record
    permerror, which is why it is a hard finding and not a hint.
    """
    if depth > SPF_LOOKUP_LIMIT:
        return
    for term in record.split()[1:]:
        if state['lookups'] > SPF_LOOKUP_LIMIT:
            return
        bare = term.lstrip('+-~?')
        name, _, arg = bare.partition(':')
        name = name.lower()
        if name.startswith('redirect='):
            name, arg = 'redirect', name.split('=', 1)[1]
        elif '=' in bare and not arg:
            key, _, value = bare.partition('=')
            if key.lower() == 'redirect':
                name, arg = 'redirect', value
            else:
                continue                                   # exp=, unknown mods
        if name not in _SPF_LOOKUP_TERMS:
            continue
        state['lookups'] += 1
        if name in ('a', 'mx') and not arg:
            arg = domain
        if name == 'ptr':
            state['findings'].append(_finding(WARN, 'spf_ptr'))
            continue
        if name not in ('include', 'redirect') or not arg:
            continue
        target = arg.strip().lower().strip('.')
        if '%' in target:                                   # macro — not expanded
            state['findings'].append(_finding(INFO, 'spf_macro', term=term))
            continue
        try:
            target = clean_domain(target)
        except ProbeError:
            state['findings'].append(_finding(WARN, 'spf_bad_term', term=term))
            continue
        if target in seen:
            state['findings'].append(_finding(FAIL, 'spf_loop', domain=target))
            continue
        seen.add(target)
        try:
            nested = _spf_records(ctx, target)
        except ProbeError:
            state['voids'] += 1
            state['findings'].append(_finding(WARN, 'spf_unresolved',
                                              domain=target))
            continue
        if not nested:
            state['voids'] += 1
            state['findings'].append(_finding(WARN, 'spf_void', domain=target))
            continue
        state['chain'].append({'domain': target, 'record': nested[0]})
        _spf_walk(ctx, target, nested[0], seen, depth + 1, state)


def check_spf(ctx: Context, domain: str) -> dict:
    domain = clean_domain(domain)
    records = _spf_records(ctx, domain)
    findings = []
    result = {'domain': domain, 'records': records, 'record': '',
              'chain': [], 'lookups': 0, 'all': '', 'findings': findings}
    if not records:
        findings.append(_finding(FAIL, 'spf_missing', domain=domain))
        result['level'] = _worst(findings)
        return result
    if len(records) > 1:
        # Two v=spf1 records are a permerror; no mail server picks a winner.
        findings.append(_finding(FAIL, 'spf_multiple', count=len(records)))
    record = records[0]
    result['record'] = record
    if len(record) > 450:
        findings.append(_finding(WARN, 'spf_long', length=len(record)))

    all_term = ''
    for term in record.split()[1:]:
        if term.lstrip('+-~?').lower() == 'all':
            all_term = term
    if not all_term:
        findings.append(_finding(WARN, 'spf_no_all'))
    else:
        qualifier = all_term[0] if all_term[0] in _SPF_QUALIFIERS else '+'
        result['all'] = _SPF_QUALIFIERS[qualifier]
        if qualifier == '+':
            findings.append(_finding(FAIL, 'spf_pass_all'))
        elif qualifier == '?':
            findings.append(_finding(WARN, 'spf_neutral_all'))
        elif qualifier == '~':
            findings.append(_finding(INFO, 'spf_softfail_all'))
        else:
            findings.append(_finding(OK, 'spf_fail_all'))

    state = {'lookups': 0, 'voids': 0, 'findings': findings, 'chain': []}
    _spf_walk(ctx, domain, record, {domain}, 1, state)
    result['lookups'] = state['lookups']
    result['chain'] = state['chain']
    if state['lookups'] > SPF_LOOKUP_LIMIT:
        findings.append(_finding(FAIL, 'spf_too_many_lookups',
                                 count=state['lookups'],
                                 limit=SPF_LOOKUP_LIMIT))
    elif state['lookups'] >= SPF_LOOKUP_LIMIT - 1:
        findings.append(_finding(WARN, 'spf_lookups_tight',
                                 count=state['lookups'],
                                 limit=SPF_LOOKUP_LIMIT))
    else:
        findings.append(_finding(OK, 'spf_lookups_ok', count=state['lookups'],
                                 limit=SPF_LOOKUP_LIMIT))
    if state['voids'] > SPF_VOID_LIMIT:
        findings.append(_finding(FAIL, 'spf_too_many_voids',
                                 count=state['voids'], limit=SPF_VOID_LIMIT))
    result['level'] = _worst(findings)
    return result


# ── DKIM ──────────────────────────────────────────────────────────────────────


def _der_length(data: bytes, i: int):
    first = data[i]
    i += 1
    if first < 0x80:
        return first, i
    count = first & 0x7F
    if count == 0 or count > 4 or i + count > len(data):
        raise ValueError('der')
    return int.from_bytes(data[i:i + count], 'big'), i + count


def _rsa_key_bits(der: bytes) -> int:
    """Modulus size of an RSA SubjectPublicKeyInfo, 0 if it is not one.

    Only the shape matters here, so a handful of lines beats pulling in a
    crypto library just to print a number.
    """
    try:
        i = 0
        if der[i] != 0x30:
            return 0
        _, i = _der_length(der, i + 1)
        if der[i] != 0x30:                                  # AlgorithmIdentifier
            return 0
        alg_len, i = _der_length(der, i + 1)
        i += alg_len
        if der[i] != 0x03:                                  # BIT STRING
            return 0
        _, i = _der_length(der, i + 1)
        i += 1                                              # unused-bits byte
        if der[i] != 0x30:                                  # RSAPublicKey
            return 0
        _, i = _der_length(der, i + 1)
        if der[i] != 0x02:                                  # INTEGER modulus
            return 0
        mod_len, i = _der_length(der, i + 1)
        modulus = der[i:i + mod_len].lstrip(b'\x00')
        return len(modulus) * 8
    except (IndexError, ValueError):
        return 0


def _dkim_one(ctx: Context, domain: str, selector: str) -> dict:
    name = f'{selector}._domainkey.{domain}'
    records = [t for t in txt_strings(ctx, name) if 'p=' in t or 'v=DKIM1' in t]
    out = {'selector': selector, 'name': name, 'record': '', 'found': False,
            'key_type': '', 'bits': 0, 'flags': '', 'findings': []}
    if not records:
        return out
    record = records[0]
    out['found'] = True
    out['record'] = record
    tags = _tags(record)
    key_type = (tags.get('k') or 'rsa').lower()
    out['key_type'] = key_type
    out['flags'] = tags.get('t', '')
    key = re.sub(r'\s+', '', tags.get('p', ''))
    if not key:
        # p= present but empty is the documented way to revoke a selector.
        out['findings'].append(_finding(WARN, 'dkim_revoked', selector=selector))
        return out
    try:
        raw = base64.b64decode(key + '=' * (-len(key) % 4), validate=True)
    except (ValueError, base64.binascii.Error):
        out['findings'].append(_finding(FAIL, 'dkim_bad_key', selector=selector))
        return out
    if key_type == 'ed25519':
        out['bits'] = len(raw) * 8
        if len(raw) != 32:
            out['findings'].append(_finding(FAIL, 'dkim_bad_key',
                                            selector=selector))
        else:
            out['findings'].append(_finding(OK, 'dkim_ok', selector=selector,
                                            bits=256, key_type='ed25519'))
        return out
    bits = _rsa_key_bits(raw)
    out['bits'] = bits
    if bits == 0:
        out['findings'].append(_finding(FAIL, 'dkim_bad_key', selector=selector))
    elif bits < 1024:
        out['findings'].append(_finding(FAIL, 'dkim_key_weak',
                                        selector=selector, bits=bits))
    elif bits < 2048:
        out['findings'].append(_finding(WARN, 'dkim_key_short',
                                        selector=selector, bits=bits))
    else:
        out['findings'].append(_finding(OK, 'dkim_ok', selector=selector,
                                        bits=bits, key_type=key_type))
    if 'y' in (out['flags'] or '').lower():
        out['findings'].append(_finding(WARN, 'dkim_testing', selector=selector))
    return out


def check_dkim(ctx: Context, domain: str, selectors=None) -> dict:
    domain = clean_domain(domain)
    wanted = [clean_selector(s) for s in (selectors or []) if str(s).strip()]
    guessed = not wanted
    if guessed:
        wanted = list(COMMON_SELECTORS)
    keys, findings = [], []
    for selector in wanted:
        try:
            entry = _dkim_one(ctx, domain, selector)
        except ProbeError:
            continue
        if entry['found']:
            keys.append(entry)
            findings.extend(entry['findings'])
        elif not guessed:
            findings.append(_finding(FAIL, 'dkim_missing', selector=selector))
    if not keys and guessed:
        # Not finding a guessed selector proves nothing — DKIM has no way to
        # enumerate selectors, so this stays a hint.
        findings.append(_finding(INFO, 'dkim_none_guessed',
                                 count=len(COMMON_SELECTORS)))
    return {'domain': domain, 'keys': keys, 'guessed': guessed,
            'tried': len(wanted), 'findings': findings,
            'level': _worst(findings)}


# ── DMARC ─────────────────────────────────────────────────────────────────────

_POLICIES = ('none', 'quarantine', 'reject')


def _report_uris(raw: str) -> list:
    out = []
    for part in (raw or '').split(','):
        part = part.strip()
        if part.lower().startswith('mailto:'):
            address = part[7:].split('!', 1)[0].strip()
            if '@' in address:
                out.append(address)
        elif part:
            out.append(part)
    return out


def check_dmarc(ctx: Context, domain: str) -> dict:
    domain = clean_domain(domain)
    name = f'_dmarc.{domain}'
    records = [t for t in txt_strings(ctx, name)
               if t.lower().replace(' ', '').startswith('v=dmarc1')]
    findings = []
    result = {'domain': domain, 'name': name, 'record': '', 'tags': {},
              'policy': '', 'subdomain_policy': '', 'pct': 100,
              'rua': [], 'ruf': [], 'findings': findings}
    if not records:
        findings.append(_finding(FAIL, 'dmarc_missing', domain=domain))
        result['level'] = _worst(findings)
        return result
    if len(records) > 1:
        findings.append(_finding(FAIL, 'dmarc_multiple', count=len(records)))
    record = records[0]
    result['record'] = record
    tags = _tags(record)
    result['tags'] = tags

    policy = (tags.get('p') or '').lower()
    result['policy'] = policy
    if policy not in _POLICIES:
        findings.append(_finding(FAIL, 'dmarc_no_policy'))
    elif policy == 'none':
        findings.append(_finding(WARN, 'dmarc_policy_none'))
    elif policy == 'quarantine':
        findings.append(_finding(INFO, 'dmarc_policy_quarantine'))
    else:
        findings.append(_finding(OK, 'dmarc_policy_reject'))

    sub = (tags.get('sp') or '').lower()
    result['subdomain_policy'] = sub
    if sub and sub not in _POLICIES:
        findings.append(_finding(WARN, 'dmarc_bad_sp', value=sub))
    elif sub == 'none' and policy in ('quarantine', 'reject'):
        findings.append(_finding(WARN, 'dmarc_sp_none'))

    try:
        pct = int(tags.get('pct', '100'))
    except ValueError:
        pct = 100
        findings.append(_finding(WARN, 'dmarc_bad_pct', value=tags.get('pct')))
    result['pct'] = pct
    if 0 <= pct < 100 and policy in ('quarantine', 'reject'):
        findings.append(_finding(WARN, 'dmarc_partial', pct=pct))

    result['rua'] = _report_uris(tags.get('rua', ''))
    result['ruf'] = _report_uris(tags.get('ruf', ''))
    if not result['rua']:
        findings.append(_finding(WARN, 'dmarc_no_rua'))
    else:
        findings.append(_finding(OK, 'dmarc_rua', count=len(result['rua'])))

    # A report address in a foreign domain only works if that domain says so.
    external = []
    for address in result['rua'] + result['ruf']:
        target = address.rsplit('@', 1)[-1].lower()
        if not target or target == domain or target.endswith('.' + domain):
            continue
        authz = f'{domain}._report._dmarc.{target}'
        try:
            allowed = any('v=dmarc1' in t.lower().replace(' ', '')
                          for t in txt_strings(ctx, authz))
        except ProbeError:
            allowed = False
        if not allowed:
            external.append(target)
    if external:
        findings.append(_finding(WARN, 'dmarc_external_unauthorised',
                                 domains=sorted(set(external))))
    result['level'] = _worst(findings)
    return result


# ── MTA-STS ───────────────────────────────────────────────────────────────────


def check_mta_sts(ctx: Context, domain: str) -> dict:
    domain = clean_domain(domain)
    name = f'_mta-sts.{domain}'
    records = [t for t in txt_strings(ctx, name)
               if t.lower().replace(' ', '').startswith('v=stsv1')]
    findings = []
    result = {'domain': domain, 'name': name, 'record': '', 'id': '',
              'policy_url': f'https://mta-sts.{domain}/.well-known/mta-sts.txt',
              'policy': '', 'mode': '', 'mx': [], 'max_age': 0,
              'findings': findings}
    if not records:
        findings.append(_finding(WARN, 'mtasts_missing', domain=domain))
        result['level'] = _worst(findings)
        return result
    if len(records) > 1:
        findings.append(_finding(FAIL, 'mtasts_multiple', count=len(records)))
    result['record'] = records[0]
    result['id'] = _tags(records[0]).get('id', '')
    if not result['id']:
        findings.append(_finding(FAIL, 'mtasts_no_id'))

    try:
        resp = http_get(ctx, result['policy_url'], accept='text/plain')
    except ProbeError as e:
        findings.append(_finding(FAIL, 'mtasts_policy_unreachable',
                                 reason=e.code))
        result['level'] = _worst(findings)
        return result
    if resp['status'] != 200:
        findings.append(_finding(FAIL, 'mtasts_policy_status',
                                 status=resp['status']))
        result['level'] = _worst(findings)
        return result
    if not resp['headers'].get('content-type', '').lower().startswith('text/plain'):
        findings.append(_finding(WARN, 'mtasts_policy_type',
                                 value=resp['headers'].get('content-type', '')))
    result['policy'] = resp['body']

    mode, mx_patterns, max_age = '', [], 0
    for line in resp['body'].splitlines():
        key, _, value = line.partition(':')
        key, value = key.strip().lower(), value.strip()
        if key == 'mode':
            mode = value.lower()
        elif key == 'mx':
            mx_patterns.append(value.lower())
        elif key == 'max_age':
            try:
                max_age = int(value)
            except ValueError:
                max_age = 0
    result['mode'], result['mx'], result['max_age'] = mode, mx_patterns, max_age

    if mode == 'enforce':
        findings.append(_finding(OK, 'mtasts_enforce'))
    elif mode == 'testing':
        findings.append(_finding(WARN, 'mtasts_testing'))
    elif mode == 'none':
        findings.append(_finding(WARN, 'mtasts_mode_none'))
    else:
        findings.append(_finding(FAIL, 'mtasts_bad_mode', value=mode))
    if max_age < 86400:
        findings.append(_finding(WARN, 'mtasts_max_age_short', value=max_age))
    if not mx_patterns:
        findings.append(_finding(FAIL, 'mtasts_no_mx'))
    else:
        # A policy that does not cover the live MX makes mail bounce, so the
        # real records are compared against the patterns.
        live = [host for _, host in mx_hosts(ctx, domain)]
        uncovered = [h for h in live if not _mx_covered(h, mx_patterns)]
        if uncovered:
            findings.append(_finding(FAIL, 'mtasts_mx_uncovered',
                                     hosts=uncovered))
        elif live:
            findings.append(_finding(OK, 'mtasts_mx_ok', count=len(live)))
    result['level'] = _worst(findings)
    return result


def _mx_covered(host: str, patterns: list) -> bool:
    host = host.strip('.').lower()
    for pattern in patterns:
        pattern = pattern.strip('.').lower()
        if pattern == host:
            return True
        # Only a single leading wildcard label is legal, and it matches exactly
        # one label — *.example.com covers mx.example.com, not a.mx.example.com.
        if pattern.startswith('*.') and host.endswith(pattern[1:]):
            head = host[:-len(pattern[1:])]
            if head and '.' not in head:
                return True
    return False


# ── TLS-RPT ───────────────────────────────────────────────────────────────────


def check_tls_rpt(ctx: Context, domain: str) -> dict:
    domain = clean_domain(domain)
    name = f'_smtp._tls.{domain}'
    records = [t for t in txt_strings(ctx, name)
               if t.lower().replace(' ', '').startswith('v=tlsrptv1')]
    findings = []
    result = {'domain': domain, 'name': name, 'record': '', 'rua': [],
              'findings': findings}
    if not records:
        findings.append(_finding(INFO, 'tlsrpt_missing', domain=domain))
        result['level'] = _worst(findings)
        return result
    result['record'] = records[0]
    result['rua'] = _report_uris(_tags(records[0]).get('rua', ''))
    if not result['rua']:
        findings.append(_finding(FAIL, 'tlsrpt_no_rua'))
    else:
        findings.append(_finding(OK, 'tlsrpt_ok', count=len(result['rua'])))
    result['level'] = _worst(findings)
    return result


# ── BIMI ──────────────────────────────────────────────────────────────────────


def check_bimi(ctx: Context, domain: str, selector: str = 'default') -> dict:
    domain = clean_domain(domain)
    selector = clean_selector(selector or 'default')
    name = f'{selector}._bimi.{domain}'
    records = [t for t in txt_strings(ctx, name)
               if t.lower().replace(' ', '').startswith('v=bimi1')]
    findings = []
    result = {'domain': domain, 'selector': selector, 'name': name,
              'record': '', 'logo': '', 'vmc': '', 'findings': findings}
    if not records:
        findings.append(_finding(INFO, 'bimi_missing', domain=domain))
        result['level'] = _worst(findings)
        return result
    result['record'] = records[0]
    tags = _tags(records[0])
    result['logo'] = tags.get('l', '')
    result['vmc'] = tags.get('a', '')
    if not result['logo']:
        findings.append(_finding(FAIL, 'bimi_no_logo'))
    else:
        try:
            resp = http_get(ctx, result['logo'], accept='image/svg+xml')
            if resp['status'] != 200:
                findings.append(_finding(FAIL, 'bimi_logo_status',
                                         status=resp['status']))
            elif 'svg' not in resp['headers'].get('content-type', '').lower():
                findings.append(_finding(WARN, 'bimi_logo_type',
                                         value=resp['headers'].get('content-type', '')))
            else:
                findings.append(_finding(OK, 'bimi_logo_ok'))
        except ProbeError as e:
            findings.append(_finding(FAIL, 'bimi_logo_unreachable',
                                     reason=e.code))
    if not result['vmc']:
        findings.append(_finding(INFO, 'bimi_no_vmc'))
    result['level'] = _worst(findings)
    return result


# ── Bundle ────────────────────────────────────────────────────────────────────


def check_mail_health(ctx: Context, domain: str, selectors=None) -> dict:
    """Everything a mail domain gets judged on, in one answer."""
    domain = clean_domain(domain)
    findings = []
    mx = [{'preference': pref, 'host': host}
          for pref, host in mx_hosts(ctx, domain)]
    if not mx:
        findings.append(_finding(FAIL, 'mx_missing', domain=domain))
    else:
        findings.append(_finding(OK, 'mx_found', count=len(mx)))
        if len(mx) == 1:
            findings.append(_finding(INFO, 'mx_single'))
    for entry in mx:
        addresses = []
        for rrtype in ('A', 'AAAA'):
            try:
                addresses.extend(query(ctx, entry['host'], rrtype).records)
            except ProbeError:
                pass
        entry['addresses'] = addresses
        if not addresses:
            findings.append(_finding(FAIL, 'mx_no_address', host=entry['host']))

    parts = {}
    for key, fn in (('spf', check_spf), ('dmarc', check_dmarc),
                    ('mta_sts', check_mta_sts), ('tls_rpt', check_tls_rpt),
                    ('bimi', check_bimi)):
        try:
            parts[key] = fn(ctx, domain)
        except ProbeError as e:
            parts[key] = {'level': FAIL, 'findings':
                          [_finding(FAIL, 'probe_failed', probe=key,
                                    reason=e.code)]}
        findings.extend(parts[key].get('findings', []))
    try:
        parts['dkim'] = check_dkim(ctx, domain, selectors)
    except ProbeError as e:
        parts['dkim'] = {'level': FAIL, 'findings':
                         [_finding(FAIL, 'probe_failed', probe='dkim',
                                   reason=e.code)]}
    findings.extend(parts['dkim'].get('findings', []))

    return {'domain': domain, 'mx': mx, 'parts': parts,
            'provider': mailprovider.detect_provider([e['host'] for e in mx]),
            'findings': findings, 'level': _worst(findings),
            'score': _score(findings)}


def _score(findings: list) -> int:
    """A blunt 0–100 number so a domain can be compared with itself over time.

    It is our own arithmetic, not anybody else's rating.
    """
    score = 100
    for f in findings:
        if f['level'] == FAIL:
            score -= 12
        elif f['level'] == WARN:
            score -= 4
    return max(0, min(100, score))
