"""Domain availability via Cloudflare's Registrar API.

Answering "is this free to register" from here directly (WHOIS "no match"
text, RDAP) is not reliable across TLDs -- the wording varies per registry,
several rate-limit hard against repeated lookups of names that don't exist
yet, and there is no free public API that covers many TLDs at once. Cloudflare
Registrar's own domain-check endpoint answers "can this actually be
registered" (not just "is WHOIS empty") for up to 20 names per call, using
the operator's own Cloudflare account -- so this needs an Account ID and an
API token with Registrar read access, set in Settings, not a public probe.

Checking does not require an active Cloudflare Registrar subscription --
only *registering* through Cloudflare would. A domain answered
"not registrable" still might be perfectly available at another registrar;
`reason` says why Cloudflare specifically won't do it (unsupported TLD,
premium pricing, already taken, ...).
"""

import requests

from netcore import ProbeError

API_BASE = 'https://api.cloudflare.com/client/v4'
MAX_DOMAINS = 20  # Cloudflare's own per-request cap
REQUEST_TIMEOUT = 15.0


def check_availability(account_id: str, api_token: str, domains: list) -> list:
    if not account_id or not api_token:
        raise ProbeError('cloudflare_not_configured')
    if not domains:
        raise ProbeError('empty_target')
    if len(domains) > MAX_DOMAINS:
        raise ProbeError('too_many_values', 'domains')

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
