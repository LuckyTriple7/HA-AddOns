"""HTTP response inspection: redirect chain, security headers, HTTP/3 signal.

Every hop is fetched through netcore.http_get, so the same SSRF guard that
protects every other probe covers the whole redirect chain too -- a server
cannot redirect this add-on into a private network by pointing Location at
one, since each hop is re-validated on arrival, not just the first URL.

HTTP/3 support itself is not verified here -- that needs an actual QUIC
handshake over UDP (RFC 9000), which needs a QUIC/TLS-1.3 stack such as
aioquic. That pulls in the cryptography package, and Alpine + a very new
Python together make its wheel availability uncertain enough to not risk a
broken build over. What is checked instead, and reported as exactly that,
is whether the server *advertises* h3 via the Alt-Svc response header
(RFC 7838) -- the same signal most lightweight online checkers rely on.
"""

import re

from netcore import Context, ProbeError, http_get

OK, INFO, WARN, FAIL = 'ok', 'info', 'warn', 'fail'
MAX_REDIRECTS = 8
HEADER_FETCH_BYTES = 8192  # only headers/status/location matter here

_SECURITY_HEADERS = (
    'strict-transport-security', 'content-security-policy',
    'x-frame-options', 'x-content-type-options', 'referrer-policy',
    'permissions-policy',
)
# Missing these two is a real gap; the rest are best-practice hardening.
_REQUIRED_HEADERS = {'strict-transport-security', 'content-security-policy'}

_ALT_SVC_H3_RE = re.compile(r'(?:^|,)\s*h3(?:-\d+)?=', re.I)
_ABS_URL_RE = re.compile(r'^https?://', re.I)
_HOST_RE = re.compile(r'^(https?://[^/]+)', re.I)


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


def _normalise_url(raw: str) -> str:
    raw = (raw or '').strip()
    if not raw:
        raise ProbeError('empty_target')
    if not _ABS_URL_RE.match(raw):
        raw = 'https://' + raw
    return raw


def _follow(ctx: Context, url: str) -> list:
    chain = []
    seen = set()
    current = url
    for _ in range(MAX_REDIRECTS):
        if current in seen:
            raise ProbeError('redirect_loop', current)
        seen.add(current)
        resp = http_get(ctx, current, max_bytes=HEADER_FETCH_BYTES,
                        accept='text/html,*/*')
        chain.append({'url': current, 'status': resp['status'],
                      'headers': resp['headers']})
        if resp['status'] not in (301, 302, 303, 307, 308):
            return chain
        location = resp['headers'].get('location', '')
        if not location:
            return chain
        if location.startswith('/'):
            base = _HOST_RE.match(current)
            current = (base.group(1) if base else '') + location
        elif _ABS_URL_RE.match(location):
            current = location
        else:
            return chain
    raise ProbeError('too_many_redirects', url)


def check_http(ctx: Context, target: str) -> dict:
    start_url = _normalise_url(target)
    chain = _follow(ctx, start_url)
    final = chain[-1]
    headers = final['headers']
    findings = []

    final_is_https = final['url'].lower().startswith('https://')
    result = {
        'start_url': start_url, 'final_url': final['url'],
        'final_status': final['status'], 'chain': chain, 'https': final_is_https,
        'security_headers': {name: headers.get(name, '') for name in _SECURITY_HEADERS},
        'server': headers.get('server', ''), 'powered_by': headers.get('x-powered-by', ''),
        'http3_advertised': bool(_ALT_SVC_H3_RE.search(headers.get('alt-svc', ''))),
        'alt_svc': headers.get('alt-svc', ''), 'findings': findings,
    }

    if chain[0]['url'].lower().startswith('http://'):
        if final_is_https:
            findings.append(_finding(OK, 'http_redirects_to_https'))
        else:
            findings.append(_finding(FAIL, 'http_no_https_redirect'))

    for name in _SECURITY_HEADERS:
        code = 'header_' + name.replace('-', '_')
        if result['security_headers'][name]:
            findings.append(_finding(OK, code + '_present'))
        else:
            level = FAIL if name in _REQUIRED_HEADERS else WARN
            findings.append(_finding(level, code + '_missing'))

    if result['server']:
        findings.append(_finding(INFO, 'header_server_disclosed', value=result['server']))
    if result['powered_by']:
        findings.append(_finding(WARN, 'header_powered_by_disclosed',
                                 value=result['powered_by']))

    if result['http3_advertised']:
        findings.append(_finding(OK, 'http3_advertised'))
    else:
        findings.append(_finding(INFO, 'http3_not_advertised'))

    if len(chain) > 4:
        findings.append(_finding(WARN, 'http_long_redirect_chain', count=len(chain)))

    result['level'] = _worst(findings)
    result['score'] = _score(findings)
    return result


def _score(findings: list) -> int:
    score = 100
    for f in findings:
        if f['level'] == FAIL:
            score -= 15
        elif f['level'] == WARN:
            score -= 5
    return max(0, min(100, score))
