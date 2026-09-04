"""The probe registry.

Every tool the web interface offers is one entry in PROBES. A probe takes a
plain dict of parameters and returns a plain dict — no Flask, no globals — so
the same function runs locally in the add-on and remotely in the worker on the
root server.
"""

import blocklists
import domaininfo
import geoip
import httpcheck
import mailauth
import mailheader
import mailprovider
import netutils
import nettech
import portcheck
import quiccheck
import seocheck
import smtpcheck
import tlscheck
import tlsextra
from netcore import (Context, ProbeError, clean_domain, clean_host_or_ip,
                     clean_ip, clean_rrtype, ip_is_public, mx_hosts,
                     query, reverse_name, txt_strings)

# Resolvers used for the propagation view. Public, free, no registration, and
# spread over enough operators that a disagreement means something.
PUBLIC_RESOLVERS = (
    ('Quad9', '9.9.9.9'),
    ('Cloudflare', '1.1.1.1'),
    ('Google', '8.8.8.8'),
    ('OpenDNS', '208.67.222.222'),
    ('DNS.WATCH', '84.200.69.80'),
    ('Level3', '4.2.2.1'),
    ('AdGuard', '94.140.14.140'),
    ('CleanBrowsing', '185.228.168.9'),
)

COMMON_TYPES = ('A', 'AAAA', 'MX', 'NS', 'TXT', 'SOA', 'CAA')


def _str(params: dict, key: str, default: str = '') -> str:
    value = params.get(key, default)
    if value is None:
        return default
    if not isinstance(value, (str, int, float)):
        raise ProbeError('bad_param', key)
    return str(value).strip()


def _list(params: dict, key: str) -> list:
    value = params.get(key) or []
    if isinstance(value, str):
        value = [p for p in value.replace(',', ' ').split() if p]
    if not isinstance(value, list):
        raise ProbeError('bad_param', key)
    if len(value) > 20:
        raise ProbeError('too_many_values', key)
    return [str(v).strip() for v in value if str(v).strip()]


def _resolver_arg(ctx: Context, params: dict) -> list:
    """An explicit resolver may be given, but not one inside the LAN."""
    raw = _str(params, 'resolver')
    if not raw:
        return []
    server = clean_ip(raw)
    if not ctx.allow_private and not ip_is_public(server):
        raise ProbeError('private_target', server)
    return [server]


# ── DNS ───────────────────────────────────────────────────────────────────────


def p_dns(ctx: Context, params: dict) -> dict:
    name = clean_domain(_str(params, 'name'))
    rrtype = clean_rrtype(_str(params, 'type', 'A'))
    answer = query(ctx, name, rrtype, servers=_resolver_arg(ctx, params))
    return {'name': answer.name, 'type': answer.rrtype,
            'records': answer.records, 'ttl': answer.ttl,
            'dnssec': answer.authenticated, 'ms': answer.ms,
            'nameserver': answer.nameserver}


def p_dns_all(ctx: Context, params: dict) -> dict:
    name = clean_domain(_str(params, 'name'))
    servers = _resolver_arg(ctx, params)
    sets, errors = [], []
    for rrtype in COMMON_TYPES:
        try:
            answer = query(ctx, name, rrtype, servers=servers)
        except ProbeError as e:
            errors.append({'type': rrtype, 'code': e.code})
            continue
        sets.append({'type': rrtype, 'records': answer.records,
                     'ttl': answer.ttl, 'ms': answer.ms})
    return {'name': name, 'sets': sets, 'errors': errors}


def p_reverse(ctx: Context, params: dict) -> dict:
    """PTR plus the forward-confirmation mail servers actually care about."""
    ip = clean_ip(_str(params, 'ip'))
    ptr_name = reverse_name(ip)
    names = [n.strip('.') for n in query(ctx, ptr_name, 'PTR').records]
    hosts = []
    for host in names:
        addresses = []
        for rrtype in ('A', 'AAAA'):
            try:
                addresses.extend(query(ctx, host, rrtype).records)
            except ProbeError:
                pass
        hosts.append({'host': host, 'addresses': addresses,
                      'confirmed': ip in addresses})
    return {'ip': ip, 'ptr_name': ptr_name, 'hosts': hosts,
            'confirmed': any(h['confirmed'] for h in hosts),
            'public': ip_is_public(ip)}


def p_aaaa_guard(ctx: Context, params: dict) -> dict:
    """Warns if any of the given domains has grown an AAAA record.

    Built for a home server with no properly working IPv6 path: a stray AAAA
    (leftover from a router or DDNS client that briefly saw an IPv6 address)
    makes IPv6-preferring clients try that address first and fail, with
    nothing in the logs pointing at DNS. Several domains at once, since
    checking a dozen of them one-by-one would mean a dozen separate monitors.
    """
    domains = _list(params, 'domains')
    if not domains:
        raise ProbeError('empty_target')
    rows = []
    for raw in domains:
        # A typo'd domain must not abort the other eleven -- it's marked
        # errored on its own row instead of raising out of the whole probe.
        try:
            name = clean_domain(raw)
            records = query(ctx, name, 'AAAA').records
            rows.append({'domain': name, 'records': records, 'error': ''})
        except ProbeError as e:
            rows.append({'domain': raw.strip(), 'records': [], 'error': e.code})

    flagged = [r for r in rows if r['records']]
    errored = [r for r in rows if r['error']]
    if flagged:
        level = 'warn'
        summary = 'AAAA-Eintrag gefunden bei: ' + ', '.join(
            f"{r['domain']} ({', '.join(r['records'])})" for r in flagged)
    elif errored:
        level = 'warn'
        summary = 'DNS-Abfrage fehlgeschlagen bei: ' + ', '.join(r['domain'] for r in errored)
    else:
        level = 'ok'
        summary = f"Kein AAAA-Eintrag bei {len(rows)} Domain(s)"
    return {'domains': rows, 'flagged': [r['domain'] for r in flagged],
            'level': level, 'summary': summary}


def p_propagation(ctx: Context, params: dict) -> dict:
    """The same question to many resolvers — shows a rollout still in flight."""
    name = clean_domain(_str(params, 'name'))
    rrtype = clean_rrtype(_str(params, 'type', 'A'))
    rows, seen = [], {}
    for label, server in PUBLIC_RESOLVERS:
        row = {'label': label, 'server': server, 'records': [], 'ms': 0,
               'error': ''}
        try:
            answer = query(ctx, name, rrtype, servers=[server])
            row['records'] = answer.records
            row['ms'] = answer.ms
            row['ttl'] = answer.ttl
        except ProbeError as e:
            row['error'] = e.code
        rows.append(row)
        if not row['error']:
            seen.setdefault('|'.join(row['records']), []).append(label)
    return {'name': name, 'type': rrtype, 'rows': rows,
            'variants': [{'records': k.split('|') if k else [],
                          'resolvers': v} for k, v in seen.items()],
            'consistent': len(seen) <= 1}


def p_dnssec(ctx: Context, params: dict) -> dict:
    """Is the zone signed, and does a validating resolver accept the answer?"""
    name = clean_domain(_str(params, 'name'))
    ds = query(ctx, name, 'DS')
    dnskey = query(ctx, name, 'DNSKEY')
    probe = query(ctx, name, 'SOA')
    signed = bool(ds.records) and bool(dnskey.records)
    return {'name': name, 'ds': ds.records, 'dnskey_count': len(dnskey.records),
            'signed': signed, 'validated': probe.authenticated,
            'parent_ds': bool(ds.records)}


def p_txt(ctx: Context, params: dict) -> dict:
    name = clean_domain(_str(params, 'name'))
    return {'name': name, 'records': txt_strings(ctx, name)}


def p_soa(ctx: Context, params: dict) -> dict:
    """SOA at the zone plus the serial each authoritative server reports."""
    name = clean_domain(_str(params, 'name'))
    soa = query(ctx, name, 'SOA')
    nameservers = [n.strip('.') for n in query(ctx, name, 'NS').records]
    rows = []
    for host in nameservers:
        row = {'host': host, 'serial': 0, 'error': ''}
        try:
            addresses = query(ctx, host, 'A').records
            if not addresses:
                row['error'] = 'no_address'
            else:
                answer = query(ctx, name, 'SOA', servers=[addresses[0]])
                parts = answer.records[0].split() if answer.records else []
                row['serial'] = int(parts[2]) if len(parts) > 2 else 0
        except (ProbeError, ValueError, IndexError):
            row['error'] = row['error'] or 'unreachable'
        rows.append(row)
    serials = {r['serial'] for r in rows if not r['error']}
    return {'name': name, 'soa': soa.records, 'nameservers': rows,
            'in_sync': len(serials) <= 1}


# ── Mail ──────────────────────────────────────────────────────────────────────


def p_spf(ctx: Context, params: dict) -> dict:
    return mailauth.check_spf(ctx, _str(params, 'domain'))


def p_dkim(ctx: Context, params: dict) -> dict:
    return mailauth.check_dkim(ctx, _str(params, 'domain'),
                               _list(params, 'selectors'))


def p_dmarc(ctx: Context, params: dict) -> dict:
    return mailauth.check_dmarc(ctx, _str(params, 'domain'))


def p_mta_sts(ctx: Context, params: dict) -> dict:
    return mailauth.check_mta_sts(ctx, _str(params, 'domain'))


def p_tls_rpt(ctx: Context, params: dict) -> dict:
    return mailauth.check_tls_rpt(ctx, _str(params, 'domain'))


def p_bimi(ctx: Context, params: dict) -> dict:
    return mailauth.check_bimi(ctx, _str(params, 'domain'),
                               _str(params, 'selector', 'default'))


def p_mail_health(ctx: Context, params: dict) -> dict:
    return mailauth.check_mail_health(ctx, _str(params, 'domain'),
                                      _list(params, 'selectors'))


def p_mx(ctx: Context, params: dict) -> dict:
    domain = clean_domain(_str(params, 'domain'))
    rows = []
    for pref, host in mx_hosts(ctx, domain):
        entry = {'preference': pref, 'host': host, 'addresses': [],
                 'reverse': []}
        for rrtype in ('A', 'AAAA'):
            try:
                entry['addresses'].extend(query(ctx, host, rrtype).records)
            except ProbeError:
                pass
        for address in entry['addresses']:
            try:
                names = query(ctx, reverse_name(address), 'PTR').records
            except ProbeError:
                names = []
            entry['reverse'].append({'ip': address,
                                     'names': [n.strip('.') for n in names]})
        rows.append(entry)
    return {'domain': domain, 'mx': rows,
            'provider': mailprovider.detect_provider(
                [r['host'] for r in rows])}


def p_blacklist(ctx: Context, params: dict) -> dict:
    return blocklists.check_blacklist(ctx, _str(params, 'ip'))


def p_tls(ctx: Context, params: dict) -> dict:
    return tlscheck.check_tls(ctx, _str(params, 'target'))


def p_dane(ctx: Context, params: dict) -> dict:
    return tlsextra.check_dane(ctx, _str(params, 'domain'))


def p_whois(ctx: Context, params: dict) -> dict:
    return domaininfo.check_domain(ctx, _str(params, 'domain'))


def p_http(ctx: Context, params: dict) -> dict:
    return httpcheck.check_http(ctx, _str(params, 'target'))


def p_smtp(ctx: Context, params: dict) -> dict:
    return smtpcheck.check_smtp(ctx, _str(params, 'target'))


def p_quic(ctx: Context, params: dict) -> dict:
    return quiccheck.check_quic(ctx, _str(params, 'target'))


def p_mailheader(ctx: Context, params: dict) -> dict:
    """Reine Textauswertung -- die einzige Prüfung ohne Netzzugriff."""
    try:
        return mailheader.analyse(_str(params, 'text'))
    except ValueError as e:
        raise ProbeError(str(e) or 'bad_params')


def p_seo(ctx: Context, params: dict) -> dict:
    return seocheck.check_seo(ctx, _str(params, 'target'))


def p_tech(ctx: Context, params: dict) -> dict:
    return nettech.check_tech(ctx, _str(params, 'target'))


def _port_check_allowed(ctx: Context) -> None:
    """Der Portcheck lässt sich abschalten.

    Er ist harmlos gebaut (feste kurze Liste, ein Host, kein Bereich), aber
    wer das Add-on jemandem zugänglich macht, soll entscheiden können, ob
    von hier aus überhaupt Verbindungen zu fremden Diensten aufgebaut
    werden.
    """
    if not getattr(ctx, 'allow_port_check', True):
        raise ProbeError('port_check_disabled')


def p_ports(ctx: Context, params: dict) -> dict:
    _port_check_allowed(ctx)
    return portcheck.check_ports(ctx, _str(params, 'target'),
                                 family=_str(params, 'family'),
                                 ports=_str(params, 'ports'))


def p_dualstack(ctx: Context, params: dict) -> dict:
    _port_check_allowed(ctx)
    return portcheck.check_dualstack(ctx, _str(params, 'target'))


def p_ping(ctx: Context, params: dict) -> dict:
    count = params.get('count')
    if count is None:
        count = netutils.PING_COUNT
    try:
        count = int(count)
    except (TypeError, ValueError):
        raise ProbeError('bad_param', 'count')
    return netutils.check_ping(ctx, _str(params, 'target'), count=count,
                                family=_str(params, 'family'))


def p_ipinfo(ctx: Context, params: dict) -> dict:
    """An empty target is not an error here -- it means "which address does
    this instance itself come from", which is exactly what the button next to
    the field asks."""
    return geoip.check_ip(ctx, _str(params, 'ip'), lang=_str(params, 'lang', 'en'))


def p_traceroute(ctx: Context, params: dict) -> dict:
    return netutils.check_traceroute(ctx, _str(params, 'target'),
                                     family=_str(params, 'family'),
                                     icmp=bool(params.get('icmp')))


# ── Registry ──────────────────────────────────────────────────────────────────

PROBES = {
    'dns': p_dns,
    'dns_all': p_dns_all,
    'reverse': p_reverse,
    'aaaa_guard': p_aaaa_guard,
    'propagation': p_propagation,
    'dnssec': p_dnssec,
    'txt': p_txt,
    'soa': p_soa,
    'mx': p_mx,
    'blacklist': p_blacklist,
    'tls': p_tls,
    'dane': p_dane,
    'whois': p_whois,
    'http': p_http,
    'smtp': p_smtp,
    'quic': p_quic,
    'seo': p_seo,
    'tech': p_tech,
    'mailheader': p_mailheader,
    'ping': p_ping,
    'traceroute': p_traceroute,
    'ports': p_ports,
    'dualstack': p_dualstack,
    'ipinfo': p_ipinfo,
    'spf': p_spf,
    'dkim': p_dkim,
    'dmarc': p_dmarc,
    'mta_sts': p_mta_sts,
    'tls_rpt': p_tls_rpt,
    'bimi': p_bimi,
    'mail_health': p_mail_health,
}

# What the front end shows in the target field, per probe.
TARGET_KIND = {
    'dns': 'name', 'dns_all': 'name', 'propagation': 'name', 'dnssec': 'name',
    'txt': 'name', 'soa': 'name', 'reverse': 'ip', 'aaaa_guard': 'domains', 'mx': 'domain',
    'blacklist': 'ip', 'tls': 'target', 'dane': 'domain', 'whois': 'domain',
    'http': 'target', 'smtp': 'target', 'quic': 'target',
    'seo': 'target', 'tech': 'target', 'mailheader': 'text',
    'ping': 'ip', 'traceroute': 'ip', 'ipinfo': 'ip',
    'ports': 'target', 'dualstack': 'target',
    'spf': 'domain', 'dkim': 'domain', 'dmarc': 'domain',
    'mta_sts': 'domain', 'tls_rpt': 'domain', 'bimi': 'domain',
    'mail_health': 'domain',
}


def run(name: str, params: dict, ctx: Context) -> dict:
    fn = PROBES.get(name)
    if fn is None:
        raise ProbeError('unknown_probe', str(name)[:40])
    if not isinstance(params, dict):
        raise ProbeError('bad_params')
    return fn(ctx, params)


# Re-exported so app.py does not have to reach into two modules.
__all__ = ['PROBES', 'PUBLIC_RESOLVERS', 'TARGET_KIND', 'run', 'Context',
           'ProbeError', 'clean_host_or_ip']
