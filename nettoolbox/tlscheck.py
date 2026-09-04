"""TLS / certificate inspection.

Standard-library ssl module only. Once OpenSSL has verified a certificate,
SSLSocket.getpeercert() already hands back parsed subject/issuer/validity/SAN
fields — no X.509/ASN.1 parsing, no cryptography dependency needed.

With verify_mode=CERT_NONE, getpeercert() returns an empty dict — OpenSSL
only populates the parsed fields for a chain it accepted. The raw DER is
still available, so for an untrusted certificate it is parsed with the
cryptography package (already a dependency for the settings encryption) into
the same shape getpeercert() produces. That matters in practice: a reverse
proxy answering with its own default certificate, because no host is
configured for the name, looked like a bare "self-signed certificate" with no
further detail — with the fields parsed, its issuer and subject say plainly
whose certificate it is.
"""

import socket
import ssl
from datetime import datetime, timezone

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding

import tlsextra

_DER = Encoding.DER

from netcore import Context, ProbeError, clean_host_or_ip, guard_target

OK, INFO, WARN, FAIL = 'ok', 'info', 'warn', 'fail'

_WEAK_PROTOCOLS = {'TLSv1', 'TLSv1.1', 'SSLv3', 'SSLv2'}
EXPIRY_WARN_DAYS = 30
EXPIRY_URGENT_DAYS = 14
# Oeffentliche CAs stellen laengst nichts mehr ueber ein Jahr aus. Was
# jahrzehntelang gilt, ist selbst ausgestellt -- und meistens ein Platzhalter.
ABSURD_LIFETIME_DAYS = 3650


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
    # No explicit minimum_version pin here on purpose: this connects to
    # arbitrary user-specified targets to REPORT what protocol they
    # negotiate (_WEAK_PROTOCOLS above), which is the whole point of this
    # module. Pinning TLSv1_2 would make the handshake itself fail against a
    # TLSv1/1.1 server instead of connecting and flagging it as weak --
    # exactly the case this tool exists to surface. No NetToolbox secret
    # crosses this socket. (CodeQL py/insecure-protocol: intentional, not a
    # missed hardening step.)
    context = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=timeout) as sock:
        with context.wrap_socket(sock, server_hostname=host) as ssock:
            return (ssock.getpeercert(), ssock.version(), ssock.cipher(),
                    _peer_chain(ssock))


def _fetch_unverified(host: str, port: int, timeout: float):
    # Same rationale as _fetch_verified above -- also drops chain validation
    # so a self-signed/expired/wrong-host cert still yields a protocol and
    # cipher reading instead of aborting the handshake outright. The DER form
    # comes along because getpeercert() itself stays empty without
    # verification.
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, port), timeout=timeout) as sock:
        with context.wrap_socket(sock, server_hostname=host) as ssock:
            return (ssock.version(), ssock.cipher(),
                    ssock.getpeercert(binary_form=True), _peer_chain(ssock))


def _der_to_certdict(der: bytes) -> dict:
    """The DER certificate in the shape getpeercert() would have produced.

    Same keys, same value formats -- including OpenSSL's odd time strings --
    so everything downstream treats a verified and an unverified certificate
    exactly alike.
    """
    if not der:
        return {}
    try:
        cert = x509.load_der_x509_certificate(der)
    except Exception:  # noqa: BLE001 — ein unlesbares Zertifikat ist ein Befund
        return {}

    def name_pairs(name):
        out = []
        for attribute in name:
            label = _OID_NAMES.get(attribute.oid.dotted_string)
            if label:
                out.append(((label, str(attribute.value)),))
        return tuple(out)

    def stamp(value):
        return value.strftime('%b %e %H:%M:%S %Y GMT').replace('  ', ' ' * 2)

    try:
        names = cert.extensions.get_extension_for_class(
            x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
    except x509.ExtensionNotFound:
        names = []

    # cryptography deprecated the naive not_valid_after in favour of the
    # timezone-aware *_utc variants; both are handled so a version bump in
    # either direction cannot break this.
    not_before = getattr(cert, 'not_valid_before_utc', None) or cert.not_valid_before
    not_after = getattr(cert, 'not_valid_after_utc', None) or cert.not_valid_after
    return {
        'subject': name_pairs(cert.subject),
        'issuer': name_pairs(cert.issuer),
        'subjectAltName': tuple(('DNS', n) for n in names),
        'notBefore': stamp(not_before),
        'notAfter': stamp(not_after),
        'serialNumber': format(cert.serial_number, 'X'),
    }


# Nur die Felder, die die Oberflaeche zeigt -- getpeercert() benennt sie genau so.
_OID_NAMES = {
    '2.5.4.3': 'commonName',
    '2.5.4.10': 'organizationName',
    '2.5.4.11': 'organizationalUnitName',
    '2.5.4.6': 'countryName',
    '2.5.4.7': 'localityName',
    '2.5.4.8': 'stateOrProvinceName',
}


def _peer_chain(ssock) -> list:
    """Alle Zertifikate, die der Server geschickt hat, als DER.

    Erst Python 3.13 gibt die Kette heraus (get_verified_chain /
    get_unverified_chain). Auf älteren Fassungen bleibt die Liste leer und
    die Oberfläche sagt das auch -- das Urteil über eine unvollständige
    Kette hängt nicht daran, denn OpenSSL meldet den Fall ohnehin als
    "unable to get local issuer certificate".
    """
    for name in ('get_verified_chain', 'get_unverified_chain'):
        getter = getattr(ssock, name, None)
        if getter is None:
            continue
        try:
            return [c.public_bytes(_DER) if hasattr(c, 'public_bytes') else bytes(c)
                    for c in (getter() or [])]
        except Exception:  # noqa: BLE001 — eine fehlende Kette ist kein Fehler
            continue
    return []


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
        'not_before': '', 'not_after': '', 'days_left': None,
        'lifetime_days': None, 'serial': '',
        'self_signed': False, 'hostname_match': False,
        'details_verified': True, 'chain': [], 'chain_available': False,
        'caa': {}, 'findings': findings,
    }

    cert = None
    chain_der = []
    try:
        cert, proto, cipher, chain_der = _fetch_verified(host, port, ctx.http_timeout)
        result['trusted'] = True
        result['details_available'] = True
        result['hostname_match'] = True
        findings.append(_finding(OK, 'tls_trusted'))
    except ssl.SSLCertVerificationError as e:
        reason = getattr(e, 'verify_message', '') or str(e)
        result['verify_error'] = reason
        try:
            proto, cipher, der, chain_der = _fetch_unverified(host, port, ctx.http_timeout)
            cert = _der_to_certdict(der)
            result['details_available'] = bool(cert)
            # Ausdruecklich vermerkt: die Angaben stammen aus einem
            # Zertifikat, das die Pruefung nicht bestanden hat.
            result['details_verified'] = False
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
        if _name_str(subject) == _name_str(issuer) and not result['self_signed']:
            result['self_signed'] = True
            findings.append(_finding(WARN, 'tls_self_signed'))

        san = [v for k, v in cert.get('subjectAltName', ()) if k == 'DNS']
        result['san'] = san
        if san and not result['hostname_match']:
            result['hostname_match'] = _hostname_covered(host, san)
            if not result['hostname_match']:
                findings.append(_finding(WARN, 'tls_hostname_not_in_san', host=host))

        not_before_raw = cert.get('notBefore', '')
        not_after_raw = cert.get('notAfter', '')
        result['not_before'] = not_before_raw
        result['not_after'] = not_after_raw
        result['serial'] = str(cert.get('serialNumber', ''))
        try:
            expires = _parse_time(not_after_raw)
            remaining = expires - datetime.now(timezone.utc)
            days_left = remaining.days
            result['days_left'] = days_left

            # Fixed day thresholds are wrong for short-lived certificates —
            # some CAs now issue 6-7 day certs (e.g. Let's Encrypt's
            # short-lived profile) that are renewed automatically well
            # before expiry; "6 days left" there is the normal, healthy
            # state, not an emergency. Judged as a fraction of the
            # certificate's own lifetime instead, matching how CAs
            # themselves define a renewal window (commonly: renew once
            # about a third of the lifetime remains). Falls back to the
            # old fixed-day thresholds only if notBefore can't be parsed.
            lifetime_days = None
            try:
                issued = _parse_time(not_before_raw)
                lifetime_days = (expires - issued).days
            except (ValueError, TypeError):
                pass
            result['lifetime_days'] = lifetime_days

            # A hard floor under the fraction math below: for a genuinely
            # short-lived cert (lifetime under ~10 days), 1 full day left can
            # still be >=10% of its lifetime and only reach WARN there, even
            # though "renews or breaks within the next 24h" is urgent in
            # absolute terms regardless of the cert's own lifetime. Checked
            # in seconds, not the truncated days_left, so 23h59m still counts.
            under_24h = 0 <= remaining.total_seconds() < 86400

            if days_left < 0:
                findings.append(_finding(FAIL, 'tls_expired', days=abs(days_left)))
            elif days_left > ABSURD_LIFETIME_DAYS:
                # "Noch 364996 Tage gueltig" als gruener Haken zu melden waere
                # Unfug -- das ist kein gesundes Zertifikat, sondern ein
                # Hinweis darauf, dass hier gar keins eingerichtet wurde.
                findings.append(_finding(INFO, 'tls_absurd_lifetime',
                                         years=days_left // 365))
            elif lifetime_days and lifetime_days > 0:
                if lifetime_days <= 15:
                    findings.append(_finding(INFO, 'tls_short_lived',
                                             lifetime=lifetime_days))
                fraction_left = days_left / lifetime_days
                if under_24h or fraction_left < 0.10:
                    findings.append(_finding(FAIL, 'tls_expiring_urgent', days=days_left))
                elif fraction_left < 0.34:
                    findings.append(_finding(WARN, 'tls_expiring_soon', days=days_left))
                else:
                    findings.append(_finding(OK, 'tls_expiry_ok', days=days_left))
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

    result['chain'] = tlsextra.describe_chain(chain_der)
    result['chain_available'] = bool(chain_der)
    if chain_der:
        findings.extend(tlsextra.chain_findings(result['chain'],
                                                result['verify_error']))
    else:
        # Ohne die Kette bleibt der eine Fall, den OpenSSL selbst meldet.
        findings.extend(tlsextra.chain_findings([], result['verify_error']))

    # CAA nur bei echten Namen -- bei einer IP gibt es keine Zone dafuer.
    if result['issuer'] and not _is_ip(host):
        try:
            result['caa'] = tlsextra.check_caa(ctx, host, result['issuer'])
            findings.extend(result['caa'].get('findings', []))
        except ProbeError:
            pass

    if _looks_like_placeholder(result):
        findings.append(_finding(INFO, 'tls_default_certificate'))

    result['level'] = _worst(findings)
    return result


def _is_ip(value: str) -> bool:
    import ipaddress
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def _looks_like_placeholder(result: dict) -> bool:
    """Erkennt das Standardzertifikat eines Webservers oder Reverse-Proxys.

    Ist fuer einen Namen kein Host eingerichtet, antwortet der Proxy trotzdem
    -- mit einem selbst ausgestellten Platzhalter ohne passenden Namen und
    mit absurder Laufzeit (NPMplus: CN "*", gueltig bis 3026). Als blosser
    "self-signed"-Fehler ist das schwer zu deuten; benannt ist es eine
    Diagnose.
    """
    if not result['self_signed'] or result['hostname_match']:
        return False
    if (result.get('days_left') or 0) <= ABSURD_LIFETIME_DAYS:
        return False
    subject = (result.get('subject') or '').strip().lower()
    return not result.get('san') or subject in ('*', 'localhost', '')
