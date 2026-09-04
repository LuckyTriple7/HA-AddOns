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

import mailprovider
from netcore import (Context, ProbeError, clean_host_or_ip, guard_target,
                     mx_hosts, query, reverse_name)

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
    """(host, port, port_was_explicit)."""
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
    return clean_host_or_ip(host or raw), port, bool(port_part)


def _has_address(ctx: Context, host: str) -> bool:
    for rrtype in ('A', 'AAAA'):
        try:
            if query(ctx, host, rrtype).records:
                return True
        except ProbeError:
            pass
    return False


def _resolve_target(ctx: Context, host: str, explicit_port: bool) -> tuple:
    """Which host to actually connect to: (host, mx_domain, mx_candidates).

    Typing a bare domain is the normal case -- nobody knows their provider's
    MX host names by heart, and looking them up by hand first just to paste
    them back in was needless work. So a domain is followed to its MX record
    here, exactly the way a sending mail server would.

    An explicit port ("host:587") is left alone: submission ports live on the
    host itself, never on the MX record, so following MX there would connect
    somewhere the user did not ask for. An IP literal is left alone for the
    same reason.
    """
    if explicit_port:
        return host, '', []
    try:
        ipaddress.ip_address(host)
        return host, '', []
    except ValueError:
        pass
    try:
        records = mx_hosts(ctx, host)
    except ProbeError:
        records = []
    # RFC 7505: a single MX pointing at the root ("0 .") is a domain stating
    # outright that it accepts no mail. mx_hosts() renders that as an empty
    # host name, which would otherwise be handed to the resolver and come
    # back as a confusing "host unresolvable".
    usable = [(pref, h) for pref, h in records if h]
    if records and not usable:
        raise ProbeError('null_mx', host)
    if usable:
        return usable[0][1], host, [h for _pref, h in usable]
    # No MX -- but "mail.example.com" typed directly is a perfectly normal
    # input and has an address of its own.
    if _has_address(ctx, host):
        return host, '', []
    # Neither: this domain runs no mail server. That is a clean answer, not a
    # failed check, so it leaves as an error message instead of a red result.
    raise ProbeError('no_mail_host', host)


def _is_private(value: str) -> bool:
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return False
    return bool(addr.is_private or addr.is_loopback or addr.is_link_local)


def _text(value) -> str:
    return value.decode('utf-8', 'replace') if isinstance(value, bytes) else str(value)


def check_smtp(ctx: Context, target: str) -> dict:
    typed_host, port, explicit_port = _parse_target(target)
    host, mx_domain, mx_candidates = _resolve_target(ctx, typed_host, explicit_port)
    guard_target(ctx, host)

    findings = []
    if mx_domain:
        findings.append(_finding(INFO, 'smtp_via_mx', domain=mx_domain,
                                 host=host, count=len(mx_candidates)))
    result = {
        'host': host, 'port': port, 'input': typed_host,
        'mx_domain': mx_domain, 'mx_candidates': mx_candidates,
        'banner': '', 'banner_host': '',
        'ehlo_ok': False, 'features': [], 'starttls_offered': False,
        'starttls_ok': False, 'tls_protocol': '', 'tls_cipher': '',
        'reverse_match': None, 'relay_open': None,
        'source_ip': '', 'peer_ip': '', 'same_host': False,
        'software': mailprovider.detect_software(''),
        # The target host itself is often enough to name the operator --
        # smtpin.rzone.de is STRATO whether or not the banner says so.
        'provider': mailprovider.detect_provider([host]),
        'findings': findings,
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

    # Wer fragt, entscheidet mit ueber die Antwort: ein Mailserver stuft die
    # eigene Maschine oder das eigene Docker-Netz ueblicherweise als
    # vertrauenswuerdig ein (Postfix mynetworks) und nimmt von dort Post fuer
    # fremde Domains an. Das ist dann kein offenes Relay nach aussen, sieht
    # aus dieser Naehe aber genau so aus -- deshalb wird festgehalten, von
    # welcher Adresse aus geprueft wurde.
    try:
        result['source_ip'] = smtp.sock.getsockname()[0]
        result['peer_ip'] = smtp.sock.getpeername()[0]
        result['same_host'] = result['source_ip'] == result['peer_ip']
    except (OSError, AttributeError, IndexError):
        pass

    banner_text = _text(banner)
    result['banner'] = banner_text
    if code != 220:
        findings.append(_finding(FAIL, 'smtp_bad_banner', code=code))
        result['level'] = _worst(findings)
        smtp.close()
        return result
    findings.append(_finding(OK, 'smtp_connected'))

    # Identified from the greeting straight away, so an early return further
    # down (EHLO refused, for instance) still carries the software guess.
    result['software'] = mailprovider.detect_software(banner_text)

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
        if not result['software']['known']:
            # Second chance for a banner that gave nothing away: a couple of
            # ESMTP extensions are vendor-specific enough to name the product.
            result['software'] = mailprovider.detect_software(
                banner_text, result['features'])
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
            if result['relay_open'] and result['same_host']:
                # Gepruft wurde von derselben Maschine, auf der der
                # Mailserver laeuft. Ein "ja, ich nehme das an" sagt hier
                # nichts darueber aus, ob das auch aus dem Internet gilt --
                # als offenes Relay zu melden waere schlicht falsch.
                findings.append(_finding(WARN, 'smtp_relay_open_local',
                                         ip=result['source_ip']))
            elif result['relay_open']:
                findings.append(_finding(FAIL, 'smtp_open_relay'))
                if _is_private(result['source_ip']):
                    # Die Quelladresse ist privat, die Verbindung laeuft also
                    # ueber NAT oder aus einem Container heraus. Dann laesst
                    # sich von hier aus nicht entscheiden, ob der Mailserver
                    # ausgerechnet diese Quelle in mynetworks stehen hat --
                    # etwa weil beide auf derselben Maschine laufen.
                    findings.append(_finding(INFO, 'smtp_relay_source_hint',
                                             ip=result['source_ip']))
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
