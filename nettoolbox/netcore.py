"""Shared building blocks for every probe: validation, DNS, guarded HTTP.

Nothing in here knows about Flask. The probes call these helpers, and the
worker on the root server runs exactly the same code as the add-on at home —
that is the whole point of keeping it separate from app.py.
"""

import ipaddress
import re
import socket
import time
from dataclasses import dataclass, field

import dns.exception
import dns.flags
import dns.rdatatype
import dns.resolver
import dns.reversename
import requests

# ── Errors ────────────────────────────────────────────────────────────────────


class ProbeError(Exception):
    """Anything the user can fix by typing something else."""

    def __init__(self, code: str, detail: str = ''):
        super().__init__(code)
        self.code = code
        self.detail = detail


# ── Context ───────────────────────────────────────────────────────────────────


@dataclass
class Context:
    """Everything a probe is allowed to know about its environment."""

    resolvers: list = field(default_factory=lambda: ['9.9.9.9', '1.1.1.1'])
    dns_timeout: float = 5.0
    http_timeout: float = 10.0
    allow_private: bool = False
    allow_port_check: bool = True
    # Der GPL-lizenzierte Zusatz-Datensatz wird nur benutzt, wenn der
    # Betreiber ihn in den Einstellungen angefordert hat (wapimport.py).
    tech_extra_rules: bool = False
    user_agent: str = 'NetToolbox'
    # Fürs Domain-Verfügbarkeits-Check (domaincheck.py) — eigenes
    # Cloudflare-Konto des Betreibers, aus den Einstellungen.
    cf_account_id: str = ''
    cf_api_token: str = ''


# ── Validation ────────────────────────────────────────────────────────────────

# A label may hold letters, digits and hyphens; underscores are illegal in host
# names but perfectly normal in the service labels DNS uses (_dmarc, _25._tcp),
# so they are allowed here and only rejected where a real host is required.
_LABEL = re.compile(r'^[A-Za-z0-9_](?:[A-Za-z0-9_-]{0,61}[A-Za-z0-9_])?$')
_SELECTOR = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$')

RR_TYPES = ('A', 'AAAA', 'MX', 'NS', 'TXT', 'CNAME', 'SOA', 'PTR', 'SRV',
            'CAA', 'DS', 'DNSKEY', 'TLSA', 'NAPTR', 'SPF')


def clean_domain(raw: str) -> str:
    """Normalise user input to a bare, punycode domain name.

    Accepts what people actually paste: a URL, a mail address, a trailing dot,
    upper case, umlauts.
    """
    value = (raw or '').strip().strip('.')
    if not value:
        raise ProbeError('empty_target')
    if '://' in value:
        value = value.split('://', 1)[1]
    if '@' in value:
        value = value.rsplit('@', 1)[1]
    value = value.split('/', 1)[0].split('?', 1)[0]
    if value.startswith('[') and ']' in value:          # [2001:db8::1]:443
        value = value[1:value.index(']')]
    elif value.count(':') == 1:                          # host:port
        value = value.split(':', 1)[0]
    value = value.strip('.').lower()
    if not value:
        raise ProbeError('empty_target')
    if len(value) > 253:
        raise ProbeError('target_too_long')
    try:
        value = value.encode('idna').decode('ascii')
    except UnicodeError:
        # Pure-ASCII names with an underscore fail encode('idna'); keep those.
        if any(ord(c) > 127 for c in value):
            raise ProbeError('bad_target')
    for label in value.split('.'):
        if not _LABEL.match(label):
            raise ProbeError('bad_target')
    return value


def clean_host_or_ip(raw: str) -> str:
    """A domain or a literal IP — used where either makes sense."""
    value = (raw or '').strip()
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return clean_domain(value)


def clean_ip(raw: str) -> str:
    try:
        return str(ipaddress.ip_address((raw or '').strip()))
    except ValueError:
        raise ProbeError('bad_ip')


def clean_selector(raw: str) -> str:
    value = (raw or '').strip().strip('.').lower()
    if not value or not _SELECTOR.match(value):
        raise ProbeError('bad_selector')
    return value


def clean_rrtype(raw: str) -> str:
    value = (raw or 'A').strip().upper()
    if value not in RR_TYPES:
        raise ProbeError('bad_rrtype')
    return value


# ── DNS ───────────────────────────────────────────────────────────────────────


def build_resolver(ctx: Context, servers=None) -> dns.resolver.Resolver:
    res = dns.resolver.Resolver(configure=not (servers or ctx.resolvers))
    picked = [s for s in (servers or ctx.resolvers) if s]
    if picked:
        res.nameservers = picked
    res.timeout = ctx.dns_timeout
    res.lifetime = ctx.dns_timeout * 2
    # Ask for the AD flag so DNSSEC state can be reported; without EDNS a
    # validating resolver may still answer, but never sets it.
    res.use_edns(0, dns.flags.DO, 1232)
    return res


@dataclass
class DnsAnswer:
    name: str
    rrtype: str
    records: list
    ttl: int = 0
    authenticated: bool = False
    ms: int = 0
    nameserver: str = ''


def _render(rdata) -> str:
    text = rdata.to_text()
    # dnspython escapes and quotes TXT chunk by chunk; the joined string is
    # what every checker actually works on.
    if rdata.rdtype == dns.rdatatype.TXT:
        return ''.join(part.decode('utf-8', 'replace') for part in rdata.strings)
    return text


def query(ctx: Context, name: str, rrtype: str, servers=None,
          raise_on_empty: bool = False) -> DnsAnswer:
    """One DNS question. An empty answer is a result, not an error."""
    res = build_resolver(ctx, servers)
    started = time.monotonic()
    try:
        answer = res.resolve(name, rrtype, raise_on_no_answer=False)
    except dns.resolver.NXDOMAIN:
        if raise_on_empty:
            raise ProbeError('nxdomain', name)
        return DnsAnswer(name, rrtype, [], nameserver=','.join(res.nameservers))
    except dns.resolver.NoNameservers:
        raise ProbeError('dns_refused', name)
    except dns.exception.Timeout:
        raise ProbeError('dns_timeout', name)
    except dns.exception.DNSException as e:
        raise ProbeError('dns_error', type(e).__name__)
    ms = int((time.monotonic() - started) * 1000)
    records = sorted(_render(r) for r in (answer.rrset or []))
    if raise_on_empty and not records:
        raise ProbeError('no_records', f'{name} {rrtype}')
    return DnsAnswer(
        name=name, rrtype=rrtype, records=records,
        ttl=int(answer.rrset.ttl) if answer.rrset is not None else 0,
        authenticated=bool(answer.response.flags & dns.flags.AD),
        ms=ms, nameserver=','.join(res.nameservers))


def txt_strings(ctx: Context, name: str) -> list:
    return query(ctx, name, 'TXT').records


def mx_hosts(ctx: Context, domain: str) -> list:
    """[(preference, host)] sorted by preference."""
    out = []
    for row in query(ctx, domain, 'MX').records:
        parts = row.split(None, 1)
        if len(parts) != 2:
            continue
        try:
            pref = int(parts[0])
        except ValueError:
            continue
        out.append((pref, parts[1].strip('.').lower()))
    return sorted(out)


def reverse_name(ip: str) -> str:
    return str(dns.reversename.from_address(ip))


# ── Address classification / SSRF guard ───────────────────────────────────────


def ip_is_public(value: str) -> bool:
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_multicast or addr.is_reserved or addr.is_unspecified)


def resolve_addresses(host: str) -> list:
    """Every address the host resolves to, via the system resolver.

    The guard has to judge what the HTTP client will really connect to, so it
    deliberately uses getaddrinfo and not the configured DNS servers.
    """
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ProbeError('host_unresolvable', host)
    return sorted({info[4][0] for info in infos})


def guard_target(ctx: Context, host: str) -> list:
    """Refuse targets in private space unless the operator allowed it.

    Without this the add-on is an open scanning proxy into the LAN for anyone
    who can reach its port.
    """
    try:
        addr = ipaddress.ip_address(host)
        addresses = [str(addr)]
    except ValueError:
        addresses = resolve_addresses(host)
    if ctx.allow_private:
        return addresses
    if not all(ip_is_public(a) for a in addresses):
        raise ProbeError('private_target', host)
    return addresses


# ── HTTP ──────────────────────────────────────────────────────────────────────


def _set_cookies(resp) -> list:
    """Jedes Set-Cookie einzeln.

    requests klebt gleichnamige Header mit Komma zusammen, und genau in einem
    Cookie-Wert (Expires=Wed, 01 Jan ...) steht selbst ein Komma -- ein Split
    darauf zerlegt die falsche Stelle. urllib3 hat die Einzelwerte noch, also
    werden sie dort geholt; nur wenn das je wegfaellt, bleibt der
    zusammengesetzte Header als Notloesung.
    """
    raw = getattr(resp, 'raw', None)
    headers = getattr(raw, 'headers', None)
    getlist = getattr(headers, 'getlist', None)
    if callable(getlist):
        return [str(value) for value in getlist('set-cookie')]
    single = resp.headers.get('set-cookie', '')
    return [single] if single else []


def http_get(ctx: Context, url: str, max_bytes: int = 128 * 1024,
             accept: str = '*/*') -> dict:
    """A guarded GET. Only http(s), only public targets, size-capped."""
    if not url.lower().startswith(('https://', 'http://')):
        raise ProbeError('bad_url', url)
    host = url.split('://', 1)[1].split('/', 1)[0].split(':', 1)[0]
    host = host.strip('[]')
    guard_target(ctx, clean_host_or_ip(host))
    try:
        with requests.get(url, timeout=ctx.http_timeout, stream=True,
                          allow_redirects=False,
                          headers={'User-Agent': ctx.user_agent,
                                   'Accept': accept}) as resp:
            body = b''
            for chunk in resp.iter_content(8192):
                body += chunk
                if len(body) > max_bytes:
                    body = body[:max_bytes]
                    break
            return {'status': resp.status_code,
                    'headers': {k.lower(): v for k, v in resp.headers.items()},
                    'cookies': _set_cookies(resp),
                    'body': body.decode('utf-8', 'replace'),
                    'bytes': len(body),
                    'url': url}
    except requests.exceptions.SSLError:
        raise ProbeError('tls_error', url)
    except requests.exceptions.Timeout:
        raise ProbeError('http_timeout', url)
    except requests.RequestException:
        raise ProbeError('http_error', url)
