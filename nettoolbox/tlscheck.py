"""TLS / certificate inspection.

Standard-library ssl module only. Once OpenSSL has verified a certificate,
SSLSocket.getpeercert() already hands back parsed subject/issuer/validity/SAN
fields — no X.509/ASN.1 parsing, no cryptography dependency needed.

The one real limitation: with verify_mode=CERT_NONE, getpeercert() returns an
empty dict — OpenSSL only populates the parsed fields for a chain it accepted.
So a broken chain (expired, self-signed, wrong host) still reports protocol,
cipher and the exact verification failure, but not the parsed certificate
fields themselves. Getting those too would need raw DER parsing or a
cryptography dependency, both skipped here — the failure reason is normally
the actionable part anyway.
"""

import socket
import ssl
from datetime import datetime, timezone

from netcore import Context, ProbeError, clean_host_or_ip, guard_target

OK, INFO, WARN, FAIL = 'ok', 'info', 'warn', 'fail'

_WEAK_PROTOCOLS = {'TLSv1', 'TLSv1.1', 'SSLv3', 'SSLv2'}
EXPIRY_WARN_DAYS = 30
EXPIRY_URGENT_DAYS = 14


def _finding(level: str, code: str, **args) -> dict:
    return {'level': level, 'code': code, 'args': args}


def _worst(findings: list) -> str:
    for level in (FAIL, WARN, INFO, OK):
        if any(f['level'] == level for f in findings):
            return level
    return OK


def _parse_target(raw: str) -> tuple:
    raw = (raw or '').strip()
    if not raw:
        raise ProbeError('empty_target')
    if raw.startswith('['):                              # [::1]:443
        host, _, rest = raw[1:].partition(']')
        port_part = rest[1:] if rest.startswith(':') else ''
    elif raw.count(':') == 1:                             # host:port
        host, port_part = raw.split(':', 1)
    else:
        host, port_part = raw, ''
    port = 443
    if port_part:
        try:
            port = int(port_part)
        except ValueError:
            raise ProbeError('bad_port', port_part)
        if not (1 <= port <= 65535):
            raise ProbeError('bad_port', port_part)
    return clean_host_or_ip(host), port


def _cn(pairs) -> str:
    for rdn in pairs:
        for key, value in rdn:
            if key == 'commonName':
                return value
    return ''


def _name_str(pairs) -> str:
    return ', '.join(f'{k}={v}' for rdn in pairs for k, v in rdn)


def _parse_time(raw: str) -> datetime:
    # OpenSSL's format via the ssl module, e.g. 'Jun  1 12:00:00 2027 GMT'.
    return datetime.strptime(raw, '%b %d %H:%M:%S %Y %Z').replace(tzinfo=timezone.utc)


def _hostname_covered(host: str, san: list) -> bool:
    host = host.lower()
    for pattern in san:
        pattern = pattern.lower()
        if pattern == host:
            return True
        if pattern.startswith('*.') and host.endswith(pattern[1:]):
            head = host[:-len(pattern[1:])]
            if head and '.' not in head:
                return True
    return False


def _fetch_verified(host: str, port: int, timeout: float):
    context = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=timeout) as sock:
        with context.wrap_socket(sock, server_hostname=host) as ssock:
            return ssock.getpeercert(), ssock.version(), ssock.cipher()


def _fetch_unverified(host: str, port: int, timeout: float):
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, port), timeout=timeout) as sock:
        with context.wrap_socket(sock, server_hostname=host) as ssock:
            return ssock.version(), ssock.cipher()


def _connection_error(e: Exception, where: str) -> ProbeError:
    if isinstance(e, socket.timeout):
        return ProbeError('tls_timeout', where)
    if isinstance(e, (socket.gaierror, ConnectionRefusedError, OSError)):
        return ProbeError('tls_unreachable', f'{where}: {e}')
    return ProbeError('tls_error', str(e))


def check_tls(ctx: Context, target: str) -> dict:
    host, port = _parse_target(target)
    guard_target(ctx, host)
    where = f'{host}:{port}'

    findings = []
    result = {
        'host': host, 'port': port, 'protocol': '', 'cipher': '',
        'cipher_bits': 0, 'trusted': False, 'details_available': False,
        'verify_error': '', 'subject': '', 'issuer': '', 'san': [],
        'not_before': '', 'not_after': '', 'days_left': None, 'serial': '',
        'self_signed': False, 'hostname_match': False, 'findings': findings,
    }

    cert = None
    try:
        cert, proto, cipher = _fetch_verified(host, port, ctx.http_timeout)
        result['trusted'] = True
        result['details_available'] = True
        result['hostname_match'] = True
        findings.append(_finding(OK, 'tls_trusted'))
    except ssl.SSLCertVerificationError as e:
        reason = getattr(e, 'verify_message', '') or str(e)
        result['verify_error'] = reason
        try:
            proto, cipher = _fetch_unverified(host, port, ctx.http_timeout)
        except ssl.SSLError as e2:
            raise ProbeError('tls_error', str(e2))
        except Exception as e2:
            raise _connection_error(e2, where)
        low = reason.lower()
        if 'hostname mismatch' in low or "doesn't match" in low:
            findings.append(_finding(FAIL, 'tls_hostname_mismatch', host=host))
        elif 'self signed' in low or 'self-signed' in low:
            result['self_signed'] = True
            findings.append(_finding(FAIL, 'tls_self_signed'))
        elif 'expired' in low:
            findings.append(_finding(FAIL, 'tls_expired_chain'))
        else:
            findings.append(_finding(FAIL, 'tls_untrusted', reason=reason))
    except ssl.SSLError as e:
        raise ProbeError('tls_error', str(e))
    except Exception as e:
        raise _connection_error(e, where)

    result['protocol'] = proto or ''
    if cipher:
        result['cipher'] = cipher[0]
        result['cipher_bits'] = cipher[2] if len(cipher) > 2 else 0

    if proto in _WEAK_PROTOCOLS:
        findings.append(_finding(FAIL, 'tls_weak_protocol', protocol=proto))
    elif proto == 'TLSv1.2':
        findings.append(_finding(INFO, 'tls_protocol_12'))
    elif proto == 'TLSv1.3':
        findings.append(_finding(OK, 'tls_protocol_13'))

    if cert:
        subject = cert.get('subject', ())
        issuer = cert.get('issuer', ())
        result['subject'] = _cn(subject) or _name_str(subject)
        result['issuer'] = _cn(issuer) or _name_str(issuer)
        if _name_str(subject) == _name_str(issuer):
            result['self_signed'] = True
            findings.append(_finding(WARN, 'tls_self_signed'))

        san = [v for k, v in cert.get('subjectAltName', ()) if k == 'DNS']
        result['san'] = san
        if san and not result['hostname_match']:
            result['hostname_match'] = _hostname_covered(host, san)
            if not result['hostname_match']:
                findings.append(_finding(WARN, 'tls_hostname_not_in_san', host=host))

        not_after_raw = cert.get('notAfter', '')
        result['not_before'] = cert.get('notBefore', '')
        result['not_after'] = not_after_raw
        result['serial'] = str(cert.get('serialNumber', ''))
        try:
            expires = _parse_time(not_after_raw)
            days_left = (expires - datetime.now(timezone.utc)).days
            result['days_left'] = days_left
            if days_left < 0:
                findings.append(_finding(FAIL, 'tls_expired', days=abs(days_left)))
            elif days_left < EXPIRY_URGENT_DAYS:
                findings.append(_finding(FAIL, 'tls_expiring_urgent', days=days_left))
            elif days_left < EXPIRY_WARN_DAYS:
                findings.append(_finding(WARN, 'tls_expiring_soon', days=days_left))
            else:
                findings.append(_finding(OK, 'tls_expiry_ok', days=days_left))
        except (ValueError, TypeError):
            findings.append(_finding(INFO, 'tls_expiry_unparsed'))
    else:
        findings.append(_finding(INFO, 'tls_details_unavailable'))

    result['level'] = _worst(findings)
    return result
