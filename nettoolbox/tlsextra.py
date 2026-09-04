"""Was über das einzelne Zertifikat hinausgeht: Kette, CAA und DANE.

Drei Fragen, die eine einfache Zertifikatsprüfung offenlässt:

* **Kette:** Liefert der Server alle Zwischenzertifikate mit? Fehlt eines,
  verzeihen Browser das (sie holen es über AIA nach), Java, Python und
  Mailserver nicht — daraus entsteht das klassische "bei mir geht es doch".
* **CAA:** Im DNS steht, welche Zertifizierungsstelle für die Domain
  ausstellen darf. Ob das ausgelieferte Zertifikat von genau der stammt,
  vergleicht sonst niemand.
* **DANE:** Für Mailserver kann im DNS ein TLSA-Eintrag stehen, der das
  Zertifikat festnagelt. Passt er nicht mehr zum ausgelieferten Zertifikat,
  lehnen prüfende Absender die Zustellung ab — ein Ausfall, der ohne
  Nachsehen unsichtbar bleibt.
"""

import hashlib
import re
import smtplib
import socket
import ssl

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

from netcore import Context, ProbeError, clean_domain, mx_hosts, query

OK, INFO, WARN, FAIL = 'ok', 'info', 'warn', 'fail'

SMTP_PORT = 25
SMTP_TIMEOUT = 15
_HELO_NAME = 'nettoolbox.local'

# Aussteller-Name im Zertifikat -> Kennung, wie sie in einem CAA-Eintrag
# steht. Verglichen wird auf Teilstring im Organisations- oder Common-Name,
# weil die Namen der Ausstellungs-Zwischenzertifikate ständig wechseln
# ("R11", "E5", "WE1"), der Organisationsname aber nicht.
CAA_ISSUERS = (
    ("let's encrypt", 'letsencrypt.org'),
    ('sectigo', 'sectigo.com'),
    ('zerossl', 'sectigo.com'),
    ('digicert', 'digicert.com'),
    ('globalsign', 'globalsign.com'),
    ('google trust services', 'pki.goog'),
    ('gts ', 'pki.goog'),
    ('amazon', 'amazon.com'),
    ('buypass', 'buypass.com'),
    ('entrust', 'entrust.net'),
    ('identrust', 'identrust.com'),
    ('actalis', 'actalis.it'),
    ('ssl.com', 'ssl.com'),
    ('certum', 'certum.pl'),
    ('harica', 'harica.gr'),
    ('telekom security', 'telesec.de'),
    ('t-systems', 'telesec.de'),
    ('microsoft', 'microsoft.com'),
    ('starfield', 'starfieldtech.com'),
    ('go daddy', 'godaddy.com'),
)


def _finding(level: str, code: str, **args) -> dict:
    return {'level': level, 'code': code, 'args': args}


def _worst(findings: list) -> str:
    for level in (FAIL, WARN):
        if any(f['level'] == level for f in findings):
            return level
    return OK


# ── Kette ────────────────────────────────────────────────────────────────────


def _name_field(name, oid) -> str:
    try:
        values = name.get_attributes_for_oid(oid)
    except Exception:  # noqa: BLE001
        return ''
    return str(values[0].value) if values else ''


def describe_chain(der_list: list) -> list:
    """Die vom Server gelieferten Zertifikate als lesbare Liste.

    Reihenfolge wie geliefert: Blatt zuerst, danach die Zwischenzertifikate.
    """
    out = []
    for index, der in enumerate(der_list or []):
        try:
            cert = x509.load_der_x509_certificate(der)
        except Exception:  # noqa: BLE001
            out.append({'position': index, 'subject': '', 'issuer': '',
                        'error': 'unreadable'})
            continue
        subject_cn = _name_field(cert.subject, x509.oid.NameOID.COMMON_NAME)
        issuer_cn = _name_field(cert.issuer, x509.oid.NameOID.COMMON_NAME)
        issuer_org = _name_field(cert.issuer,
                                 x509.oid.NameOID.ORGANIZATION_NAME)
        not_after = getattr(cert, 'not_valid_after_utc', None) or cert.not_valid_after
        out.append({
            'position': index,
            'subject': subject_cn or _name_field(cert.subject,
                                                 x509.oid.NameOID.ORGANIZATION_NAME),
            'issuer': issuer_cn or issuer_org,
            'issuer_org': issuer_org,
            'not_after': not_after.strftime('%Y-%m-%d'),
            'self_issued': cert.subject == cert.issuer,
            'error': '',
        })
    return out


def chain_findings(chain: list, verify_error: str) -> list:
    """Der eine Fehler, den Browser verzeihen und sonst niemand."""
    findings = []
    low = (verify_error or '').lower()
    if 'unable to get local issuer' in low:
        # Genau das Bild eines fehlenden Zwischenzertifikats: der Server
        # liefert das Blatt, aber nicht den Weg zur Wurzel.
        findings.append(_finding(FAIL, 'tls_chain_incomplete'))
    if chain:
        if len(chain) == 1 and not chain[0].get('self_issued'):
            findings.append(_finding(WARN, 'tls_chain_leaf_only'))
        else:
            findings.append(_finding(OK, 'tls_chain_ok', count=len(chain)))
        if any(c.get('self_issued') for c in chain[1:]):
            # Das Wurzelzertifikat mitzuliefern ist nicht falsch, aber
            # überflüssig -- es kostet bei jeder Verbindung Bytes.
            findings.append(_finding(INFO, 'tls_chain_root_included'))
    return findings


# ── CAA ──────────────────────────────────────────────────────────────────────


def caa_identifier(issuer: str) -> str:
    text = (issuer or '').lower()
    for needle, identifier in CAA_ISSUERS:
        if needle in text:
            return identifier
    return ''


def check_caa(ctx: Context, domain: str, issuer: str) -> dict:
    """CAA-Einträge der Domain gegen den tatsächlichen Aussteller.

    CAA wird vom Namen aufwärts geerbt; gefragt wird deshalb bis zur
    zweiten Ebene hinauf, so wie es eine Zertifizierungsstelle täte.
    """
    labels = domain.split('.')
    records, source = [], ''
    for start in range(len(labels) - 1):
        name = '.'.join(labels[start:])
        try:
            answer = query(ctx, name, 'CAA')
        except ProbeError:
            continue
        if answer.records:
            records, source = answer.records, name
            break

    allowed = []
    for row in records:
        # Format: '0 issue "letsencrypt.org"'
        m = re.match(r'^\s*\d+\s+(issue|issuewild|iodef)\s+"?([^"]*)"?', row.strip())
        if m and m.group(1) in ('issue', 'issuewild'):
            value = m.group(2).split(';')[0].strip().lower()
            if value and value not in allowed:
                allowed.append(value)

    identifier = caa_identifier(issuer)
    result = {'records': records, 'source': source, 'allowed': allowed,
              'issuer': issuer, 'issuer_identifier': identifier,
              'matches': None}
    if not records:
        result['findings'] = [_finding(INFO, 'caa_missing')]
        return result
    if allowed == ['']:
        result['findings'] = [_finding(INFO, 'caa_forbids_all')]
        return result
    if not identifier:
        result['findings'] = [_finding(INFO, 'caa_issuer_unknown', issuer=issuer)]
        return result
    result['matches'] = identifier in allowed
    result['findings'] = [
        _finding(OK, 'caa_match', issuer=identifier) if result['matches']
        else _finding(WARN, 'caa_mismatch', issuer=identifier,
                      allowed=', '.join(allowed))]
    return result


# ── DANE / TLSA ──────────────────────────────────────────────────────────────


def _tlsa_digest(der: bytes, selector: int, matching: int) -> str:
    """Der Vergleichswert, den ein TLSA-Eintrag festhält."""
    cert = x509.load_der_x509_certificate(der)
    if selector == 1:
        data = cert.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo)
    else:
        data = cert.public_bytes(serialization.Encoding.DER)
    if matching == 0:
        return data.hex()
    if matching == 1:
        return hashlib.sha256(data).hexdigest()
    if matching == 2:
        return hashlib.sha512(data).hexdigest()
    raise ValueError('matching')


def _starttls_certificate(host: str, port: int = SMTP_PORT) -> bytes:
    """Das Zertifikat, das der Mailserver nach STARTTLS ausliefert."""
    smtp = smtplib.SMTP(timeout=SMTP_TIMEOUT)
    try:
        smtp.connect(host, port)
        smtp._host = host
        smtp.ehlo(_HELO_NAME)
        if 'starttls' not in smtp.esmtp_features:
            raise ProbeError('dane_no_starttls', host)
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        smtp.starttls(context=context)
        der = smtp.sock.getpeercert(binary_form=True)
        if not der:
            raise ProbeError('dane_no_certificate', host)
        return der
    except (socket.timeout, socket.gaierror, ConnectionRefusedError, OSError,
            smtplib.SMTPException) as e:
        raise ProbeError('dane_unreachable', f'{host}: {e}')
    finally:
        try:
            smtp.close()
        except Exception:  # noqa: BLE001
            pass


def check_dane(ctx: Context, domain: str) -> dict:
    """TLSA-Einträge aller MX-Server gegen deren echtes Zertifikat.

    Ohne DNSSEC ist DANE wertlos -- ein TLSA-Eintrag, den jeder unterwegs
    fälschen kann, sichert nichts. Deshalb steht die DNSSEC-Lage hier mit
    im Ergebnis.
    """
    domain = clean_domain(domain)
    findings = []
    signed = False
    try:
        signed = bool(query(ctx, domain, 'SOA').authenticated)
    except ProbeError:
        pass

    hosts = [host for _pref, host in mx_hosts(ctx, domain) if host]
    if not hosts:
        raise ProbeError('no_mail_host', domain)

    rows = []
    for host in hosts:
        row = {'host': host, 'records': [], 'matched': None, 'error': '',
               'digest_seen': ''}
        name = f'_25._tcp.{host}'
        try:
            answer = query(ctx, name, 'TLSA')
            row['records'] = answer.records
            row['dnssec'] = bool(answer.authenticated)
        except ProbeError as e:
            row['error'] = e.code
            rows.append(row)
            continue
        if not row['records']:
            rows.append(row)
            continue
        try:
            der = _starttls_certificate(host)
        except ProbeError as e:
            row['error'] = e.code
            rows.append(row)
            continue
        matched = False
        for record in row['records']:
            parts = record.split()
            if len(parts) < 4:
                continue
            try:
                usage, selector, matching = (int(parts[0]), int(parts[1]),
                                             int(parts[2]))
                expected = ''.join(parts[3:]).lower()
                seen = _tlsa_digest(der, selector, matching)
            except (ValueError, TypeError):
                continue
            row['digest_seen'] = seen
            row['usage'] = usage
            if seen == expected:
                matched = True
                break
        row['matched'] = matched
        rows.append(row)

    with_records = [r for r in rows if r['records']]
    if not with_records:
        findings.append(_finding(INFO, 'dane_none', count=len(rows)))
    else:
        bad = [r for r in with_records if r['matched'] is False]
        good = [r for r in with_records if r['matched'] is True]
        if bad:
            findings.append(_finding(FAIL, 'dane_mismatch',
                                     hosts=', '.join(r['host'] for r in bad)))
        if good:
            findings.append(_finding(OK, 'dane_match', count=len(good)))
        if not signed:
            # Ein TLSA-Eintrag in einer unsignierten Zone ist Dekoration.
            findings.append(_finding(WARN, 'dane_without_dnssec'))
        else:
            findings.append(_finding(OK, 'dane_dnssec_ok'))
    errored = [r for r in rows if r['error']]
    if errored:
        findings.append(_finding(INFO, 'dane_errors', count=len(errored)))

    return {'domain': domain, 'dnssec': signed, 'rows': rows,
            'findings': findings, 'level': _worst(findings)}
