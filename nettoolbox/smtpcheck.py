"""SMTP server probe: banner, EHLO capabilities, STARTTLS, and a safe,
non-delivering open-relay check.

Connects, reads the greeting, sends EHLO, and if the server offers STARTTLS
upgrades the connection -- reporting only the negotiated protocol and
cipher, not certificate trust. Unlike a browser-facing HTTPS site, a
self-signed certificate on port 25 opportunistic TLS is normal and not a
finding here; MTA-STS, checked separately (mailauth.py), is where trust
actually matters for mail delivery.

The relay probe sends MAIL FROM and RCPT TO an address on example.com (the
IANA-reserved documentation domain, RFC 2606) and reads the server's answer,
then always sends RSET and QUIT. DATA is never sent -- no matter what the
server answers, nothing is ever actually delivered. This is the same
non-destructive technique every "check my mail server" tool has always used.
"""

import ipaddress
import re
import smtplib
import socket
import ssl

from netcore import Context, ProbeError, clean_host_or_ip, guard_target, query, reverse_name

OK, INFO, WARN, FAIL = 'ok', 'info', 'warn', 'fail'
DEFAULT_PORT = 25
RELAY_TEST_SENDER = 'relay-probe@nettoolbox.invalid'
RELAY_TEST_RECIPIENT = 'relay-probe@example.com'

_HELO_NAME = 'nettoolbox.local'


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


def _parse_target(raw: str) -> tuple:
    raw = (raw or '').strip()
    if not raw:
        raise ProbeError('empty_target')
    host, _, port_part = raw.partition(':') if raw.count(':') == 1 else (raw, '', '')
    port = DEFAULT_PORT
    if port_part:
        try:
            port = int(port_part)
        except ValueError:
            raise ProbeError('bad_port', port_part)
        if not (1 <= port <= 65535):
            raise ProbeError('bad_port', port_part)
    return clean_host_or_ip(host or raw), port


def _text(value) -> str:
    return value.decode('utf-8', 'replace') if isinstance(value, bytes) else str(value)


def check_smtp(ctx: Context, target: str) -> dict:
    host, port = _parse_target(target)
    guard_target(ctx, host)

    findings = []
    result = {
        'host': host, 'port': port, 'banner': '', 'banner_host': '',
        'ehlo_ok': False, 'features': [], 'starttls_offered': False,
        'starttls_ok': False, 'tls_protocol': '', 'tls_cipher': '',
        'reverse_match': None, 'relay_open': None, 'findings': findings,
    }

    smtp = smtplib.SMTP(timeout=ctx.http_timeout)
    try:
        code, banner = smtp.connect(host, port)
    except socket.timeout:
        raise ProbeError('smtp_timeout', f'{host}:{port}')
    except (socket.gaierror, ConnectionRefusedError, OSError) as e:
        raise ProbeError('smtp_unreachable', f'{host}:{port}: {e}')
    # connect() alone leaves _host unset (only the constructor's own
    # connect() call fills it in) -- starttls() needs it for SNI, so it is
    # set by hand. Verified live against real servers, not assumed.
    smtp._host = host

    banner_text = _text(banner)
    result['banner'] = banner_text
    if code != 220:
        findings.append(_finding(FAIL, 'smtp_bad_banner', code=code))
        result['level'] = _worst(findings)
        smtp.close()
        return result
    findings.append(_finding(OK, 'smtp_connected'))

    m = re.match(r'^(\S+)', banner_text)
    if m:
        result['banner_host'] = m.group(1).rstrip('.')

    try:
        try:
            connected_ip = str(ipaddress.ip_address(host))
        except ValueError:
            addresses = query(ctx, host, 'A').records
            connected_ip = addresses[0] if addresses else None
        names = ([n.strip('.').lower() for n in query(ctx, reverse_name(connected_ip), 'PTR').records]
                 if connected_ip else [])
        if names and result['banner_host']:
            result['reverse_match'] = result['banner_host'].lower() in names
            if result['reverse_match']:
                findings.append(_finding(OK, 'smtp_banner_ptr_match'))
            else:
                findings.append(_finding(WARN, 'smtp_banner_ptr_mismatch',
                                         banner=result['banner_host'],
                                         ptr=', '.join(names)))
    except ProbeError:
        pass

    try:
        code, ehlo_resp = smtp.ehlo(_HELO_NAME)
    except smtplib.SMTPException as e:
        findings.append(_finding(FAIL, 'smtp_ehlo_failed', reason=str(e)))
        result['level'] = _worst(findings)
        try:
            smtp.close()
        except Exception:
            pass
        return result

    result['ehlo_ok'] = code == 250
    if result['ehlo_ok']:
        result['features'] = sorted(smtp.esmtp_features.keys())
        findings.append(_finding(OK, 'smtp_ehlo_ok'))
    else:
        findings.append(_finding(FAIL, 'smtp_ehlo_failed', reason=_text(ehlo_resp)))

    result['starttls_offered'] = 'starttls' in smtp.esmtp_features
    if result['starttls_offered']:
        try:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            code, _resp = smtp.starttls(context=context)
            result['starttls_ok'] = code == 220
            if result['starttls_ok']:
                sock = smtp.sock
                result['tls_protocol'] = sock.version() or ''
                cipher = sock.cipher()
                result['tls_cipher'] = cipher[0] if cipher else ''
                findings.append(_finding(OK, 'smtp_starttls_ok',
                                         protocol=result['tls_protocol']))
                smtp.ehlo(_HELO_NAME)  # RFC 3207: state resets, EHLO again
            else:
                findings.append(_finding(WARN, 'smtp_starttls_failed'))
        except (smtplib.SMTPException, ssl.SSLError, OSError) as e:
            findings.append(_finding(WARN, 'smtp_starttls_failed', reason=str(e)))
    else:
        findings.append(_finding(WARN, 'smtp_no_starttls'))

    try:
        code, _msg = smtp.mail(RELAY_TEST_SENDER)
        if code == 250:
            code2, _msg2 = smtp.rcpt(RELAY_TEST_RECIPIENT)
            result['relay_open'] = code2 == 250
            if result['relay_open']:
                findings.append(_finding(FAIL, 'smtp_open_relay'))
            else:
                findings.append(_finding(OK, 'smtp_relay_closed'))
        smtp.rset()
    except smtplib.SMTPException:
        pass  # best-effort: a failed probe here is not itself a finding

    try:
        smtp.quit()
    except smtplib.SMTPException:
        try:
            smtp.close()
        except Exception:
            pass

    result['level'] = _worst(findings)
    return result
