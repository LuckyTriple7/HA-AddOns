"""Domain availability via Cloudflare's Registrar API, with two direct
fallbacks for TLDs Cloudflare does not sell at all.

Answering "is this free to register" from here directly (WHOIS "no match"
text, RDAP) is not reliable across TLDs in general -- the wording varies per
registry, several rate-limit hard against repeated lookups of names that
don't exist yet, and there is no free public API that covers many TLDs at
once. Cloudflare Registrar's own domain-check endpoint answers "can this
actually be registered" (not just "is WHOIS empty") for up to 20 names per
call, using the operator's own Cloudflare account -- so this needs an
Account ID and an API token with Registrar read access, set in Settings.

Checking does not require an active Cloudflare Registrar subscription --
only *registering* through Cloudflare would. A domain answered
"not registrable" still might be perfectly available at another registrar;
`reason` says why Cloudflare specifically won't do it (unsupported TLD,
premium pricing, already taken, ...).

.de and .eu are the two exceptions worth naming: Cloudflare does not sell
either (verified live against its published TLD list), but both registries
answer the one question asked here cleanly enough to skip Cloudflare
entirely -- DENIC over its own RDAP server (not in IANA's bootstrap
registry, so the ordinary RDAP lookup in domaininfo.py falls back to plain
WHOIS for it; verified live: https://data.iana.org/rdap/dns.json has no
"de" entry), EURid over its own WHOIS format. Neither carries pricing, so
those rows never do either -- Cloudflare is the only source for that here,
and it doesn't sell these two.
"""

import socket

import requests

from netcore import ProbeError

API_BASE = 'https://api.cloudflare.com/client/v4'
MAX_DOMAINS = 20  # Cloudflare's own per-request cap
REQUEST_TIMEOUT = 15.0

DENIC_RDAP_URL = 'https://rdap.denic.de/domain/{}'
EURID_WHOIS_HOST = 'whois.eu'
EURID_WHOIS_PORT = 43


def _check_de_domain(name: str) -> dict:
    """DENIC's RDAP server answers with plain HTTP status: 200 means
    registered, 404 means free. No pricing this way."""
    try:
        resp = requests.head(DENIC_RDAP_URL.format(name), timeout=REQUEST_TIMEOUT,
                             allow_redirects=True)
    except requests.exceptions.RequestException:
        return {'name': name, 'registrable': False, 'reason': 'registry_check_failed'}
    if resp.status_code == 404:
        return {'name': name, 'registrable': True, 'tier': 'standard'}
    if resp.status_code == 200:
        return {'name': name, 'registrable': False, 'reason': 'domain_unavailable'}
    return {'name': name, 'registrable': False, 'reason': 'registry_check_failed'}


def _whois_query(host: str, port: int, query: str) -> str:
    with socket.create_connection((host, port), timeout=REQUEST_TIMEOUT) as sock:
        sock.sendall((query + '\r\n').encode('ascii', 'ignore'))
        chunks = []
        sock.settimeout(REQUEST_TIMEOUT)
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
    return b''.join(chunks).decode('utf-8', 'replace')


def _check_eu_domain(name: str) -> dict:
    """EURid's WHOIS (it runs no RDAP) marks a free name with its own
    'Status: AVAILABLE' line -- nothing else in the response carries it."""
    try:
        text = _whois_query(EURID_WHOIS_HOST, EURID_WHOIS_PORT, name)
    except OSError:
        return {'name': name, 'registrable': False, 'reason': 'registry_check_failed'}
    if 'Status: AVAILABLE' in text:
        return {'name': name, 'registrable': True, 'tier': 'standard'}
    if f'Domain: {name}' in text:
        return {'name': name, 'registrable': False, 'reason': 'domain_unavailable'}
    return {'name': name, 'registrable': False, 'reason': 'registry_check_failed'}


# TLD (lowercase, no dot) -> direct checker. Everything else goes to
# Cloudflare. Add an entry here only for a TLD verified live to answer
# cleanly enough for a plain yes/no -- not a general-purpose fallback for
# whatever else Cloudflare might be missing.
_DIRECT_REGISTRIES = {
    'de': _check_de_domain,
    'eu': _check_eu_domain,
}


def _check_cloudflare(account_id: str, api_token: str, domains: list) -> list:
    if not account_id or not api_token:
        raise ProbeError('cloudflare_not_configured')
    try:
        resp = requests.post(
            f'{API_BASE}/accounts/{account_id}/registrar/domain-check',
            headers={'Authorization': f'Bearer {api_token}',
                     'Content-Type': 'application/json'},
            json={'domains': domains}, timeout=REQUEST_TIMEOUT)
    except requests.exceptions.Timeout:
        raise ProbeError('cloudflare_timeout')
    except requests.exceptions.RequestException as e:
        raise ProbeError('cloudflare_unreachable', type(e).__name__)

    if resp.status_code in (401, 403):
        raise ProbeError('cloudflare_auth')
    try:
        data = resp.json()
    except ValueError:
        raise ProbeError('cloudflare_bad_response', str(resp.status_code))
    if not data.get('success'):
        detail = '; '.join(e.get('message', '') for e in (data.get('errors') or []))
        raise ProbeError('cloudflare_error', detail[:200])

    return (data.get('result') or {}).get('domains') or []


def check_availability(account_id: str, api_token: str, domains: list) -> list:
    """Order matches the input list regardless of which registry answered
    each one -- the caller never sees the split."""
    if not domains:
        raise ProbeError('empty_target')
    if len(domains) > MAX_DOMAINS:
        raise ProbeError('too_many_values', 'domains')

    rows_by_name = {}
    cloudflare_names = []
    for name in domains:
        tld = name.rsplit('.', 1)[-1].lower()
        checker = _DIRECT_REGISTRIES.get(tld)
        if checker:
            rows_by_name[name] = checker(name)
        else:
            cloudflare_names.append(name)

    # A Cloudflare account is only needed for the names that actually go
    # through Cloudflare -- an all-.de/.eu selection works without one.
    if cloudflare_names:
        for row in _check_cloudflare(account_id, api_token, cloudflare_names):
            rows_by_name[row['name']] = row

    return [rows_by_name[d] for d in domains]


def verify_token(api_token: str) -> bool:
    """Cloudflare's own token-verify endpoint -- no account ID needed, so it
    doubles as a lightweight "are these credentials even valid" test that
    does not touch the registrar product at all."""
    if not api_token:
        return False
    try:
        resp = requests.get(
            f'{API_BASE}/user/tokens/verify',
            headers={'Authorization': f'Bearer {api_token}'},
            timeout=REQUEST_TIMEOUT)
    except requests.exceptions.RequestException:
        return False
    if resp.status_code != 200:
        return False
    try:
        return bool(resp.json().get('success'))
    except ValueError:
        return False
