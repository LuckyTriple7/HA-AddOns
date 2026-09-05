"""Domain availability: Cloudflare's Registrar API first, with a generic
IANA-driven fallback for whatever it doesn't sell -- no per-TLD table.

Cloudflare's own domain-check endpoint answers "can this actually be
registered" (not just "is WHOIS empty") for up to 20 names per call, using
the operator's own Cloudflare account -- so it needs an Account ID and an
API token with Registrar read access, set in Settings. Checking does not
require an active Registrar subscription -- only *registering* through
Cloudflare would.

For a TLD Cloudflare answers `reason: extension_not_supported*` for -- or
for every TLD at all, if no Cloudflare account is configured -- the fallback
is the exact same pipeline the Whois tab already uses (domaininfo.py):
IANA's RDAP bootstrap registry first (hundreds of TLDs, RDAP's 404 meaning
"not found" is spec-standard, so this half is exact), the classic WHOIS
referral from whois.iana.org second. Both discovered live per TLD, nothing
about "which server serves .fr/.nl/.pl/..." is hardcoded here.

One named exception: DENIC (.de) runs a real RDAP server
(rdap.denic.de) but is not listed in IANA's bootstrap file (verified live
against https://data.iana.org/rdap/dns.json -- no "de" entry), so the
generic pipeline above would otherwise fall back to plain WHOIS for it.
Skipping straight to DENIC's RDAP is one documented patch for that one gap,
not a general-purpose table.

None of the fallback paths carry pricing -- only Cloudflare knows what it
would charge, and by definition it isn't selling whatever ends up here.

The WHOIS half stays best-effort by nature, not by oversight: domaininfo.py's
"is this registered" detection covers the phrasings verified live so far
("no entries found" / "not found" / "no match", plus a bare
"status: available" -- .eu and .it both use exactly that and nothing else,
confirmed live for both a registered and a free name each). A registry
whose wording matches none of those reports found=True by default, which
reads as "taken" here even when it might not be. Worse, some registries
don't answer at all: .ch (verified live) refuses automated WHOIS outright
("Requests of this client are not permitted"), and .es (verified live, from
two unrelated networks) never even completes the TCP handshake to
whois.nic.es -- both surface as registry_check_failed, an honest "could not
tell" rather than a guess either way. None of this needs fixing per TLD
before shipping; it is the honest cost of not paying
Cloudflare (or another registrar API) for every ccTLD in existence.
"""

import requests

from netcore import Context, ProbeError
import domaininfo

API_BASE = 'https://api.cloudflare.com/client/v4'
MAX_DOMAINS = 20  # Cloudflare's own per-request cap
REQUEST_TIMEOUT = 15.0

DENIC_RDAP_URL = 'https://rdap.denic.de/domain/{}'


def _check_de_domain(name: str) -> dict:
    """DENIC's RDAP server answers with plain HTTP status: 200 means
    registered, 404 means free."""
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


def _check_via_registry(ctx: Context, name: str) -> dict:
    """The generic fallback: same RDAP-bootstrap-then-WHOIS-referral chain
    the Whois tab runs (domaininfo.check_domain), read as a plain yes/no.
    'found' already means exactly "this name is registered" there -- an RDAP
    404 sets it False without ever touching WHOIS (see domaininfo._rdap_fetch),
    and a WHOIS "no entries found" sets it False too. Whatever fails outright
    (no referral, both paths timing out) is reported honestly as unknown
    rather than guessed either way."""
    if name.rsplit('.', 1)[-1].lower() == 'de':
        return _check_de_domain(name)
    try:
        result = domaininfo.check_domain(ctx, name)
    except ProbeError:
        return {'name': name, 'registrable': False, 'reason': 'registry_check_failed'}
    if result.get('found'):
        return {'name': name, 'registrable': False, 'reason': 'domain_unavailable'}
    return {'name': name, 'registrable': True, 'tier': 'standard'}


def _check_cloudflare(account_id: str, api_token: str, domains: list) -> list:
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


def check_availability(ctx: Context, account_id: str, api_token: str, domains: list) -> list:
    """Order matches the input list regardless of which source answered
    each one -- the caller never sees the split."""
    if not domains:
        raise ProbeError('empty_target')
    if len(domains) > MAX_DOMAINS:
        raise ProbeError('too_many_values', 'domains')

    rows_by_name = {}
    fallback_names = list(domains)

    if account_id and api_token:
        try:
            for row in _check_cloudflare(account_id, api_token, domains):
                rows_by_name[row['name']] = row
            # Only the ones Cloudflare itself declined for lack of TLD
            # support go on to the registry fallback -- everything else
            # (taken, premium, disallowed) is Cloudflare's own real answer.
            fallback_names = [name for name, row in rows_by_name.items()
                              if str(row.get('reason') or '').startswith('extension_not_supported')]
        except ProbeError:
            # Cloudflare itself unreachable or misconfigured: the registry
            # pipeline below still answers the actual question on its own,
            # just without Cloudflare's pricing/premium info. A broken
            # token belongs in the Settings connection test, not in every
            # single check failing outright.
            rows_by_name = {}
            fallback_names = list(domains)

    for name in fallback_names:
        rows_by_name[name] = _check_via_registry(ctx, name)

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
