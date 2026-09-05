"""WordPress hardening check: is it WordPress, is it current, and does it
leak the handful of things that make it an easy target.

Detection first, everything else only if that succeeds -- there is no point
asking a Drupal site for wp-config.php.bak. Every follow-up request is a
single GET against a well-known path with allow_redirects=False, same as the
rest of the HTTP checks; nothing here logs in, submits a form, or writes
anything.

Deliberately not covered: plugin/theme enumeration (would mean guessing
hundreds of paths -- noisy against someone else's server for a guess), and
comparing against a CVE database (needs a feed this add-on does not carry).
What is covered is what a single well-behaved GET each can answer for
certain.
"""

import re
import time
from urllib.parse import urlparse

import httpcheck
from netcore import Context, ProbeError, http_get

OK, INFO, WARN, FAIL = 'ok', 'info', 'warn', 'fail'

MAX_BYTES = 256 * 1024
WP_VERSION_CHECK_URL = 'https://api.wordpress.org/core/version-check/1.7/'

# Ordered roughly by how often each one turns out to actually be there.
_CONFIG_BACKUP_NAMES = (
    'wp-config.php.bak', 'wp-config.php~', 'wp-config.php.save',
    'wp-config.php.swp', 'wp-config.php.old', 'wp-config.bak',
    'wp-config.txt', 'wp-config.php.orig',
)

_GENERATOR_RE = re.compile(
    r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']WordPress ([\d.]+)',
    re.I)
_README_VERSION_RE = re.compile(r'[Vv]ersion\s+([\d.]+)')


def _finding(level: str, code: str, **args) -> dict:
    return {'level': level, 'code': code, 'args': args}


def _worst(findings: list) -> str:
    for level in (FAIL, WARN):
        if any(f['level'] == level for f in findings):
            return level
    return OK


def _score(findings: list) -> int:
    """Same idea as the other checks' scores. A config backup is a
    credentials leak and weighted like one; everything else here is a
    hardening recommendation, not a break-in already in progress."""
    score = 100
    for f in findings:
        if f['level'] == FAIL:
            score -= 30
        elif f['level'] == WARN:
            score -= 10
    return max(0, min(100, score))


def _fetch(ctx: Context, url: str, accept: str = '*/*') -> dict:
    try:
        return http_get(ctx, url, max_bytes=MAX_BYTES, accept=accept)
    except ProbeError:
        return {}


def _version_tuple(raw: str) -> tuple:
    try:
        return tuple(int(p) for p in raw.split('.'))
    except ValueError:
        return ()


def _latest_wp_version(ctx: Context) -> str:
    """The current stable release per wordpress.org's own update API -- the
    same endpoint a real WordPress install polls itself. A fixed, trusted
    public host, unrelated to the site being checked."""
    resp = _fetch(ctx, WP_VERSION_CHECK_URL, accept='application/json')
    if not resp or resp.get('status') != 200:
        return ''
    try:
        import json
        data = json.loads(resp.get('body') or '{}')
    except ValueError:
        return ''
    offers = data.get('offers') or []
    return str(offers[0].get('version', '')) if offers else ''


def _detect(ctx: Context, origin: str, home_body: str) -> dict:
    """Best signal first: the generator tag names an exact version. Absent
    that (many hardening guides say to strip it), wp-content/wp-includes
    paths in the markup are still a reliable "this is WordPress" signal even
    with no version attached. The REST index is the last resort for
    sites that hide both."""
    m = _GENERATOR_RE.search(home_body)
    if m:
        return {'found': True, 'version': m.group(1), 'source': 'meta'}
    if 'wp-content/' in home_body or 'wp-includes/' in home_body:
        return {'found': True, 'version': '', 'source': 'markup'}
    resp = _fetch(ctx, origin + '/wp-json/', accept='application/json')
    if resp and resp.get('status') == 200 and '"namespaces"' in (resp.get('body') or ''):
        return {'found': True, 'version': '', 'source': 'rest'}
    return {'found': False, 'version': '', 'source': ''}


def _check_readme(ctx: Context, origin: str, findings: list) -> str:
    """Also the fallback version source when the generator tag is gone and
    the site never got detected via markup either."""
    resp = _fetch(ctx, origin + '/readme.html', accept='text/html,*/*')
    if resp and resp.get('status') == 200 and 'wordpress' in (resp.get('body') or '').lower():
        findings.append(_finding(WARN, 'wp_readme_exposed'))
        m = _README_VERSION_RE.search(resp.get('body') or '')
        return m.group(1) if m else ''
    return ''


def _check_config_backups(ctx: Context, origin: str, findings: list) -> None:
    for name in _CONFIG_BACKUP_NAMES:
        resp = _fetch(ctx, origin + '/' + name, accept='*/*')
        if not resp or resp.get('status') != 200:
            continue
        body = resp.get('body') or ''
        if 'DB_NAME' in body or 'define(' in body or "define ('" in body:
            findings.append(_finding(FAIL, 'wp_config_backup_exposed', file=name))
            return
    findings.append(_finding(OK, 'wp_config_backup_clean'))


def _check_xmlrpc(ctx: Context, origin: str, findings: list) -> None:
    resp = _fetch(ctx, origin + '/xmlrpc.php', accept='text/xml,*/*')
    body = (resp.get('body') or '') if resp else ''
    if resp and resp.get('status') == 200 and (
            'XML-RPC server accepts POST requests only' in body or '<methodCall' in body
            or 'xmlrpc' in body.lower()):
        findings.append(_finding(WARN, 'wp_xmlrpc_enabled'))
    else:
        findings.append(_finding(OK, 'wp_xmlrpc_disabled'))


def _check_users(ctx: Context, origin: str, findings: list) -> None:
    resp = _fetch(ctx, origin + '/wp-json/wp/v2/users', accept='application/json')
    if resp and resp.get('status') == 200:
        try:
            import json
            users = json.loads(resp.get('body') or '[]')
        except ValueError:
            users = None
        if isinstance(users, list) and users:
            names = [str(u.get('slug') or u.get('name') or '')[:40] for u in users][:10]
            findings.append(_finding(WARN, 'wp_users_exposed', users=', '.join(n for n in names if n)))
            return
    findings.append(_finding(OK, 'wp_users_hidden'))


def _check_directory_listing(ctx: Context, origin: str, findings: list) -> None:
    resp = _fetch(ctx, origin + '/wp-content/uploads/', accept='text/html,*/*')
    body = (resp.get('body') or '') if resp else ''
    if resp and resp.get('status') == 200 and re.search(r'index of /', body, re.I):
        findings.append(_finding(WARN, 'wp_directory_listing'))
    else:
        findings.append(_finding(OK, 'wp_directory_listing_off'))


def check_wordpress(ctx: Context, target: str) -> dict:
    start_url = httpcheck.normalise_url(target)
    chain = httpcheck.follow_redirects(ctx, start_url)
    final_url = chain[-1]['url']
    parsed = urlparse(final_url)
    origin = f'{parsed.scheme}://{parsed.netloc}'

    started = time.monotonic()
    home = _fetch(ctx, final_url, accept='text/html,*/*')
    home_body = home.get('body') or ''

    findings = []
    detected = _detect(ctx, origin, home_body)
    if not detected['found']:
        findings.append(_finding(INFO, 'wp_not_detected'))
        # 'ok', not the finding's own 'info': for the vast majority of
        # targets that simply are not WordPress, this step has nothing to
        # say, and it must not drag the overall report badge down to "info"
        # on every single one of them.
        return {'origin': origin, 'detected': False, 'version': '', 'latest': '',
                'findings': findings, 'level': OK,
                'score': 100, 'ms': int((time.monotonic() - started) * 1000)}

    version = detected['version'] or _check_readme(ctx, origin, findings)
    latest = _latest_wp_version(ctx)
    if version and latest:
        if _version_tuple(version) < _version_tuple(latest):
            findings.append(_finding(WARN, 'wp_version_outdated', version=version, latest=latest))
        else:
            findings.append(_finding(OK, 'wp_version_current', version=version))
    elif version:
        findings.append(_finding(INFO, 'wp_version_unknown_latest', version=version))
    else:
        findings.append(_finding(INFO, 'wp_version_unknown'))

    _check_config_backups(ctx, origin, findings)
    _check_xmlrpc(ctx, origin, findings)
    _check_users(ctx, origin, findings)
    _check_directory_listing(ctx, origin, findings)

    return {'origin': origin, 'detected': True, 'version': version, 'latest': latest,
            'findings': findings, 'level': _worst(findings), 'score': _score(findings),
            'ms': int((time.monotonic() - started) * 1000)}
