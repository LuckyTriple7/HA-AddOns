"""IP geolocation and network ownership lookup (ip-api.com).

Free, no registration, no API key -- but that tier is plain HTTP only and
capped at roughly 45 requests per minute per source address, which is why
nothing here batches or polls. One lookup per button press.

The PTR name is resolved through the add-on's own configured resolvers
instead of ip-api's `reverse` field: that field makes their side do a
blocking rDNS lookup and noticeably slows the answer, while netcore.query()
already does exactly the same thing with the resolvers the operator picked.
"""

import ipaddress
import json

from netcore import (Context, ProbeError, clean_host_or_ip, http_get,
                     ip_is_public, query, reverse_name)

OK, INFO, WARN, FAIL = 'ok', 'info', 'warn', 'fail'

API_URL = 'http://ip-api.com/json/'

# Asked for explicitly so the answer stays small and stable; `status` and
# `message` are what ip-api uses to report a failed lookup.
API_FIELDS = ('status,message,continent,continentCode,country,countryCode,'
              'region,regionName,city,district,zip,lat,lon,timezone,offset,'
              'currency,isp,org,as,asname,mobile,proxy,hosting,query')

# The languages ip-api actually knows; anything else falls back to English.
API_LANGS = ('en', 'de', 'es', 'fr', 'ja', 'pt-BR', 'ru', 'zh-CN')


def _finding(level: str, code: str, **args) -> dict:
    return {'level': level, 'code': code, 'args': args}


def _worst(findings: list) -> str:
    """Informational notes (hosting, mobile network) stay on their own line
    but never colour the summary pill -- same rule as the other probes."""
    for level in (FAIL, WARN):
        if any(f['level'] == level for f in findings):
            return level
    return OK


def _split_as(value: str) -> tuple:
    """ip-api returns the AS as one string: "AS15169 Google LLC"."""
    value = (value or '').strip()
    if not value:
        return '', ''
    parts = value.split(None, 1)
    if parts[0].upper().startswith('AS'):
        return parts[0].upper(), (parts[1] if len(parts) > 1 else '')
    return '', value


def _ptr_names(ctx: Context, ip: str) -> list:
    try:
        return [n.strip('.') for n in query(ctx, reverse_name(ip), 'PTR').records]
    except ProbeError:
        return []


def _resolve_input(ctx: Context, raw: str) -> tuple:
    """(ip, resolved_from) -- a domain name is looked up first, A before AAAA.

    Deliberately not guard_target(): this probe never connects to the
    address, it only asks ip-api about it. A private address is reported as
    such below instead of being refused.
    """
    value = clean_host_or_ip(raw)
    try:
        return str(ipaddress.ip_address(value)), ''
    except ValueError:
        pass
    for rrtype in ('A', 'AAAA'):
        records = query(ctx, value, rrtype).records
        if records:
            return records[0], value
    raise ProbeError('host_unresolvable', value)


def check_ip(ctx: Context, target: str, lang: str = 'en') -> dict:
    """Geolocation, ISP and AS for one address.

    An empty target asks ip-api which address *this* instance comes from --
    the home connection's public IP, or the root server's when the probe
    runs on the worker.
    """
    raw = (target or '').strip()
    own = not raw
    resolved_from = ''
    ip = ''
    if not own:
        ip, resolved_from = _resolve_input(ctx, raw)
        if not ip_is_public(ip):
            # No point asking a geolocation service about 192.168.x.x, and no
            # reason to hand a private address to a third party either.
            return {'query': ip, 'input': raw, 'resolved_from': resolved_from,
                    'public': False, 'ptr': _ptr_names(ctx, ip), 'own': False,
                    'findings': [_finding(WARN, 'geoip_private', ip=ip)],
                    'level': WARN}

    lang = lang if lang in API_LANGS else 'en'
    url = f'{API_URL}{ip}?fields={API_FIELDS}&lang={lang}'
    response = http_get(ctx, url, accept='application/json')
    if response['status'] == 429:
        raise ProbeError('geoip_rate_limited', 'ip-api.com')
    if response['status'] != 200:
        raise ProbeError('geoip_error', str(response['status']))
    try:
        data = json.loads(response['body'])
    except ValueError:
        raise ProbeError('geoip_bad_response', 'ip-api.com')
    if not isinstance(data, dict):
        raise ProbeError('geoip_bad_response', 'ip-api.com')
    if data.get('status') != 'success':
        # "private range", "reserved range", "invalid query" -- all reported
        # by ip-api as a message string rather than an HTTP error.
        raise ProbeError('geoip_failed', str(data.get('message') or '')[:80])

    ip = str(data.get('query') or ip)
    asn, as_name = _split_as(str(data.get('as') or ''))
    result = {
        'query': ip,
        'input': raw,
        'resolved_from': resolved_from,
        'own': own,
        'public': True,
        'ptr': _ptr_names(ctx, ip),
        'continent': data.get('continent') or '',
        'continent_code': data.get('continentCode') or '',
        'country': data.get('country') or '',
        'country_code': data.get('countryCode') or '',
        'region': data.get('regionName') or '',
        'region_code': data.get('region') or '',
        'city': data.get('city') or '',
        'district': data.get('district') or '',
        'zip': data.get('zip') or '',
        'lat': data.get('lat'),
        'lon': data.get('lon'),
        'timezone': data.get('timezone') or '',
        'utc_offset': data.get('offset'),
        'currency': data.get('currency') or '',
        'isp': data.get('isp') or '',
        'org': data.get('org') or '',
        'asn': asn,
        'as_name': data.get('asname') or as_name,
        'mobile': bool(data.get('mobile')),
        'proxy': bool(data.get('proxy')),
        'hosting': bool(data.get('hosting')),
    }

    findings = []
    place = ', '.join(p for p in (result['city'], result['country']) if p)
    if own:
        findings.append(_finding(OK, 'geoip_own_ip', ip=ip, place=place or '?'))
    else:
        findings.append(_finding(OK, 'geoip_located', place=place or '?'))
    if result['hosting']:
        findings.append(_finding(INFO, 'geoip_hosting'))
    if result['mobile']:
        findings.append(_finding(INFO, 'geoip_mobile'))
    if result['proxy']:
        findings.append(_finding(WARN, 'geoip_proxy'))
    result['findings'] = findings
    result['level'] = _worst(findings)
    return result
