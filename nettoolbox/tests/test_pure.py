"""Tests for the parts that need no network.

Everything here is a pure function: given this input, produce that output.
The probes themselves are deliberately left out -- they talk to real DNS and
real mail servers, and a test suite that needs the internet to pass is a test
suite nobody runs.

Run with:  python3 -m pytest tests -q     (from the add-on directory)
"""

import json
import os
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import blocklists  # noqa: E402
import geoip  # noqa: E402
import hasensors  # noqa: E402
import mailheader  # noqa: E402
import mailprovider  # noqa: E402
import netcore  # noqa: E402
import nettech  # noqa: E402
import netutils  # noqa: E402
import portcheck  # noqa: E402
import seocheck  # noqa: E402
import techrules  # noqa: E402
import wapimport  # noqa: E402
import smtpcheck  # noqa: E402
import tlscheck  # noqa: E402
import tlsextra  # noqa: E402


# ── netcore: input validation ────────────────────────────────────────────────

@pytest.mark.parametrize('raw, expected', [
    ('example.com', 'example.com'),
    ('  Example.COM.  ', 'example.com'),
    ('https://example.com/pfad?x=1', 'example.com'),
    ('user@example.com', 'example.com'),
    ('example.com:443', 'example.com'),
    ('_dmarc.example.com', '_dmarc.example.com'),
    ('bücher.de', 'xn--bcher-kva.de'),
])
def test_clean_domain(raw, expected):
    assert netcore.clean_domain(raw) == expected


@pytest.mark.parametrize('raw', ['', '   ', '-bad-.com', 'a' * 260 + '.com'])
def test_clean_domain_rejects(raw):
    with pytest.raises(netcore.ProbeError):
        netcore.clean_domain(raw)


def test_clean_ip_and_rrtype():
    assert netcore.clean_ip(' 203.0.113.10 ') == '203.0.113.10'
    assert netcore.clean_ip('2001:db8::1') == '2001:db8::1'
    assert netcore.clean_rrtype('mx') == 'MX'
    with pytest.raises(netcore.ProbeError):
        netcore.clean_ip('nope')
    with pytest.raises(netcore.ProbeError):
        netcore.clean_rrtype('NOTATYPE')


@pytest.mark.parametrize('ip, public', [
    ('8.8.8.8', True), ('2606:4700::1111', True),
    ('192.168.1.1', False), ('127.0.0.1', False),
    ('169.254.169.254', False), ('10.0.0.1', False),
    ('::1', False), ('nonsense', False),
])
def test_ip_is_public(ip, public):
    assert netcore.ip_is_public(ip) is public


def test_reverse_name():
    assert netcore.reverse_name('203.0.113.10') == '10.113.0.203.in-addr.arpa.'


# ── mailprovider: operator and software identification ───────────────────────

@pytest.mark.parametrize('host, name', [
    ('aspmx.l.google.com', 'Google Workspace'),
    ('foo.mail.protection.outlook.com', 'Microsoft 365'),
    ('smtpin.rzone.de', 'STRATO'),
    ('mx01.hornetsecurity.com', 'Hornetsecurity'),
])
def test_provider_for_host(host, name):
    assert mailprovider.provider_for_host(host)['name'] == name


def test_provider_matches_suffix_not_substring():
    """The whole point of matching on a suffix: an attacker-owned name that
    merely contains a known one must not be credited to that operator."""
    assert mailprovider.provider_for_host('google.com.attacker.net') == {}
    assert mailprovider.provider_for_host('notoutlook.com') == {}


def test_provider_longest_suffix_wins():
    hit = mailprovider.provider_for_host('x.mail.protection.outlook.com')
    assert hit['matched'] == 'mail.protection.outlook.com'


def test_detect_provider_groups_and_reports_unknown():
    out = mailprovider.detect_provider(['aspmx.l.google.com',
                                        'alt1.aspmx.l.google.com',
                                        'mail.selfhosted.example'])
    assert out['names'] == ['Google Workspace']
    assert out['unknown'] == ['mail.selfhosted.example']
    assert out['known'] is True


@pytest.mark.parametrize('banner, name, version', [
    ('220 mail.example.com ESMTP Postfix (Debian/GNU)', 'Postfix', ''),
    ('220 host ESMTP Exim 4.96 Thu', 'Exim', '4.96'),
    ('220 mail.gizmonet.eu ESMTP Postcow', 'Postfix (mailcow)', ''),
    ('220 smtpin.rzone.de ESMTP RZmta 55.6.2 ready', 'RZmta (STRATO)', '55.6.2'),
    ('220 EX01 Microsoft ESMTP MAIL Service ready', 'Microsoft Exchange', ''),
])
def test_detect_software(banner, name, version):
    out = mailprovider.detect_software(banner)
    assert (out['name'], out['version']) == (name, version)


def test_detect_software_falls_back_to_ehlo():
    out = mailprovider.detect_software('220 ESMTP', ['SIZE', 'XEXCH50'])
    assert out['name'] == 'Microsoft Exchange'
    assert out['source'] == 'ehlo'


def test_detect_software_admits_defeat():
    assert mailprovider.detect_software('220 ESMTP ready')['known'] is False


def test_greeting_style_is_a_hint_not_a_name():
    """Ein anonymisiertes Banner laesst nur noch den Wortlaut der Begruessung
    -- der wird als Stil gemeldet und ausdruecklich als solcher markiert."""
    out = mailprovider.detect_software(
        '220 mail2.example.de ESMTP (bd055ad7d576)', [],
        'mail2.example.de Hello host [203.0.113.1], pleased to meet you')
    assert out['name'] == 'sendmail'
    assert out['source'] == 'greeting'
    assert out['style_only'] is True


def test_banner_beats_greeting():
    out = mailprovider.detect_software(
        '220 mail ESMTP Postfix', [], 'mail Hello, pleased to meet you')
    assert out['name'] == 'Postfix'
    assert out.get('style_only') is None


# ── smtpcheck: target parsing ────────────────────────────────────────────────

@pytest.mark.parametrize('raw, host, port, explicit', [
    ('example.com', 'example.com', 25, False),
    ('mail.example.com:587', 'mail.example.com', 587, True),
    ('203.0.113.10', '203.0.113.10', 25, False),
])
def test_smtp_parse_target(raw, host, port, explicit):
    assert smtpcheck._parse_target(raw) == (host, port, explicit)


def test_smtp_parse_target_rejects_bad_port():
    with pytest.raises(netcore.ProbeError):
        smtpcheck._parse_target('example.com:99999')


def test_smtp_is_private():
    assert smtpcheck._is_private('172.17.0.2') is True
    assert smtpcheck._is_private('81.169.145.97') is False
    assert smtpcheck._is_private('') is False


# ── blocklists ───────────────────────────────────────────────────────────────

def test_reverse_octets():
    assert blocklists._reverse_octets('127.0.0.2') == '2.0.0.127'


def test_every_zone_entry_is_complete():
    for entry in blocklists.RBL_ZONES:
        label, zone, lookup = entry
        assert label and zone
        assert lookup == '' or lookup.startswith('http')


# ── geoip ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('raw, asn, name', [
    ('AS15169 Google LLC', 'AS15169', 'Google LLC'),
    ('AS200924 sis2', 'AS200924', 'sis2'),
    ('', '', ''),
    ('Some Network', '', 'Some Network'),
])
def test_split_as(raw, asn, name):
    assert geoip._split_as(raw) == (asn, name)


# ── netutils: output parsing ─────────────────────────────────────────────────

PING_OUTPUT = """PING example.com (203.0.113.10) 56(84) bytes of data.
64 bytes from 203.0.113.10: icmp_seq=1 ttl=54 time=12.3 ms
64 bytes from 203.0.113.10: icmp_seq=2 ttl=54 time=11.8 ms

--- example.com ping statistics ---
2 packets transmitted, 2 received, 0% packet loss, time 1001ms
rtt min/avg/max/mdev = 11.800/12.050/12.300/0.250 ms
"""


def test_ping_line_parsing():
    replies = list(netutils._PING_LINE_RE.finditer(PING_OUTPUT))
    assert len(replies) == 2
    assert replies[0].group(3) == '12.3'
    summary = netutils._PING_SUMMARY_RE.search(PING_OUTPUT)
    assert summary.groups() == ('2', '2', '0')
    rtt = netutils._PING_RTT_RE.search(PING_OUTPUT)
    assert rtt.group(2) == '12.050'


def test_family_flag():
    assert netutils._family_flag('') == []
    assert netutils._family_flag('4') == ['-4']
    assert netutils._family_flag('6') == ['-6']
    with pytest.raises(netcore.ProbeError):
        netutils._family_flag('7')


# ── seocheck: HTML parsing and scoring ───────────────────────────────────────

SAMPLE_HTML = """<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <title>  Eine   Seite  </title>
  <meta name="description" content="Beschreibung der Seite">
  <meta name="viewport" content="width=device-width">
  <meta property="og:title" content="Eine Seite">
  <link rel="canonical" href="https://example.com/">
  <link rel="alternate" hreflang="en" href="https://example.com/en">
  <script type="application/ld+json">{"@type": "WebSite", "name": "x"}</script>
</head>
<body>
  <h1>Titel</h1>
  <h3>Uebersprungen</h3>
  <img src="a.png" alt="mit Text">
  <img src="http://unsicher.example/b.png">
  <p>Etwas Text im Body.</p>
  <script>var ignoriert = "kein Seitentext";</script>
</body>
</html>"""


@pytest.fixture(scope='module')
def page():
    parsed = seocheck._Page()
    parsed.feed(SAMPLE_HTML)
    parsed.close()
    return parsed


def test_page_head_fields(page):
    assert ' '.join(page.title.split()) == 'Eine Seite'
    assert page.html_lang == 'de'
    assert page.charset == 'utf-8'
    assert page.metas['description'] == 'Beschreibung der Seite'
    assert page.metas['og:title'] == 'Eine Seite'
    assert page.canonical == 'https://example.com/'
    assert page.hreflang == [{'lang': 'en', 'href': 'https://example.com/en'}]


def test_page_counts_headings_and_images(page):
    assert [lvl for lvl, _text in page.headings] == [1, 3]
    assert page.images_total == 2
    assert page.images_no_alt == 1


def test_page_skips_script_text(page):
    text = ' '.join(''.join(page.text_parts).split())
    assert 'Etwas Text im Body.' in text
    assert 'kein Seitentext' not in text


def test_jsonld_types(page):
    assert seocheck._jsonld_types(page.jsonld) == ['WebSite']


def test_jsonld_survives_broken_json():
    assert seocheck._jsonld_types(['{nicht wirklich json']) == []


def test_score_ignores_info_findings():
    findings = [{'level': 'info', 'code': 'x', 'args': {}}] * 5
    assert seocheck._score(findings) == 100
    findings.append({'level': 'fail', 'code': 'y', 'args': {}})
    assert seocheck._score(findings) == 85
    assert seocheck._score([{'level': 'fail', 'code': 'z', 'args': {}}] * 20) == 0


# ── tlscheck: Platzhalter-Zertifikat ─────────────────────────────────────────

def _tls_result(**over):
    base = {'self_signed': True, 'hostname_match': False, 'days_left': 365000,
            'subject': '*', 'san': []}
    base.update(over)
    return base


def test_placeholder_certificate_detected():
    """Das Standardzertifikat von NPMplus: CN "*", keine SAN, gueltig bis 3026."""
    assert tlscheck._looks_like_placeholder(_tls_result()) is True


@pytest.mark.parametrize('over', [
    {'self_signed': False},          # regulaer ausgestellt
    {'hostname_match': True},        # passt zum Namen, also kein Platzhalter
    {'days_left': 90},               # normale Laufzeit
    {'subject': 'intern.example', 'san': ['intern.example']},  # eigene CA
])
def test_placeholder_certificate_not_overreported(over):
    assert tlscheck._looks_like_placeholder(_tls_result(**over)) is False


def test_der_to_certdict_survives_garbage():
    assert tlscheck._der_to_certdict(b'') == {}
    assert tlscheck._der_to_certdict(b'kein zertifikat') == {}


# ── mailheader: Kopfanalyse ──────────────────────────────────────────────────

SAMPLE_HEADER = """Return-Path: <newsletter@example-marketing.com>
Received: from mx.ziel.de (mx.ziel.de [203.0.113.9]) by mail.ziel.de (Postfix) with ESMTPS id 4X2 for <kunde@ziel.de>; Wed, 3 Sep 2026 09:15:31 +0200
Received: from smtp.absender.de (smtp.absender.de [198.51.100.20]) by mx.ziel.de (Postfix) with ESMTP id 3B1 for <kunde@ziel.de>; Wed, 3 Sep 2026 09:03:11 +0200
Authentication-Results: mx.ziel.de; spf=pass smtp.mailfrom=example-marketing.com; dkim=fail header.d=absender.de; dmarc=fail (p=none) header.from=absender.de
DKIM-Signature: v=1; a=rsa-sha256; c=relaxed/relaxed; d=absender.de; s=selector1; bh=abc
From: "Ein Absender" <info@absender.de>
To: kunde@ziel.de
Subject: Testnachricht
Date: Wed, 3 Sep 2026 09:03:00 +0200
Message-ID: <abc123@absender.de>
Reply-To: antwort@ganzwoanders.example
"""


@pytest.fixture(scope='module')
def header():
    return mailheader.analyse(SAMPLE_HEADER)


def test_header_reads_the_verdicts(header):
    assert header['auth'] == {'spf': 'pass', 'dkim': 'fail', 'dmarc': 'fail'}
    assert header['level'] == 'fail'


def test_header_orders_hops_oldest_first(header):
    """Received-Zeilen stehen neueste zuerst -- gelesen wird der Weg aber
    von A nach B."""
    assert [h['by'] for h in header['hops']] == ['mx.ziel.de', 'mail.ziel.de']
    assert header['hops'][0]['from'] == 'smtp.absender.de'
    assert header['hops'][0]['ip'] == '198.51.100.20'
    assert header['hops'][1]['delay'] == 740.0
    assert header['total_seconds'] == 740.0


def test_header_spots_missing_alignment(header):
    codes = [f['code'] for f in header['findings']]
    assert 'hdr_return_path_mismatch' in codes
    assert 'hdr_reply_to_differs' in codes
    assert 'hdr_hop_very_slow' in codes


def test_header_reads_dkim_tags(header):
    assert header['dkim_signatures'] == [{'domain': 'absender.de',
                                          'selector': 'selector1',
                                          'algorithm': 'rsa-sha256',
                                          'canonicalisation': 'relaxed/relaxed'}]


def test_header_detects_gateway_and_mta():
    """Genau der Fall, um den es ging: von aussen sagt der Mailserver
    nichts, im Kopf einer Mail steht beides."""
    sample = ("Received: from gw.example ([10.0.0.20]) by mx.example with ESMTP; "
              "Wed, 3 Sep 2026 10:00:05 +0200\n"
              "Received: by notes01.example (Lotus Domino Release 12.0.2FP3) "
              "with ESMTP; Wed, 3 Sep 2026 10:00:01 +0200\n"
              "X-Barracuda-Spam-Score: 0.20\n"
              "From: a@example.de\nSubject: x\n")
    names = [s['name'] for s in mailheader.analyse(sample)['stations']]
    assert 'HCL/IBM Domino (Notes)' in names
    assert 'Barracuda (ESG / Spam Firewall)' in names


def test_header_station_evidence_prefers_the_version():
    sample = ("Received: by notes01.example (Lotus Domino Release 12.0.2FP3) with "
              "ESMTP; Wed, 3 Sep 2026 10:00:01 +0200\nX-Lotus-FromDomain: X\n"
              "From: a@example.de\n")
    station = [s for s in mailheader.analyse(sample)['stations']
               if s['name'].startswith('HCL')][0]
    assert '12.0.2fp3' in station['evidence']


def test_header_rejects_empty_and_oversized():
    with pytest.raises(ValueError):
        mailheader.analyse('   ')
    with pytest.raises(ValueError):
        mailheader.analyse('X: ' + 'a' * (mailheader.MAX_HEADER_BYTES + 10))


def test_header_survives_a_fragment():
    """Ein halber Kopf ohne Received-Zeilen darf nicht scheitern, sondern
    soll genau das als Fund melden."""
    out = mailheader.analyse('From: a@b.de\nSubject: nur ein Ausschnitt')
    assert 'hdr_no_received' in [f['code'] for f in out['findings']]
    assert out['from_domain'] == 'b.de'


# ── hasensors: Entitaeten fuer Home Assistant ────────────────────────────────

class _FakeResponse:
    status_code = 200


class _FakeSession:
    """Faengt die Schreibzugriffe ab -- kein Test schreibt in ein echtes
    Home Assistant."""

    def __init__(self):
        self.calls = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append((url.rsplit('/states/', 1)[-1], json))
        return _FakeResponse()


@pytest.fixture
def pushed(monkeypatch):
    session = _FakeSession()
    monkeypatch.setattr(hasensors.requests, 'Session', lambda: session)
    monkeypatch.setattr(hasensors, 'SUPERVISOR_TOKEN', 'test-token')
    monitors = [
        {'id': 1, 'name': 'Mein Server', 'probe': 'tls', 'target': 'example.com',
         'interval_hours': 6, 'enabled': 1, 'last_level': 'ok',
         'last_summary': 'Zertifikat noch 60 Tage gültig', 'last_run_ts': 1700000000,
         'last_error': ''},
        {'id': 2, 'name': 'Mein Server', 'probe': 'seo', 'target': 'example.com',
         'interval_hours': 24, 'enabled': 1, 'last_level': 'warn',
         'last_summary': 'SEO-Punktestand 71/100', 'last_run_ts': 1700000001,
         'last_error': ''},
    ]
    written = hasensors.push(monitors)
    return session, written


def test_push_writes_one_entity_per_monitor_plus_summaries(pushed):
    session, written = pushed
    assert written == 4
    assert [entity for entity, _payload in session.calls] == [
        'sensor.nettoolbox_mein_server',
        'sensor.nettoolbox_mein_server_2',   # gleicher Name -> ID haengt dran
        'sensor.nettoolbox_probleme',
        'binary_sensor.nettoolbox_problem',
    ]


def test_push_carries_state_and_attributes(pushed):
    session, _written = pushed
    _entity, payload = session.calls[0]
    assert payload['state'] == 'ok'
    assert payload['attributes']['ziel'] == 'example.com'
    assert payload['attributes']['pruefung'] == 'TLS-Zertifikat'
    assert payload['attributes']['friendly_name'] == 'NetToolbox Mein Server'


def test_push_counts_only_warn_and_fail_as_problems(pushed):
    session, _written = pushed
    problems = dict(session.calls)['sensor.nettoolbox_probleme']
    assert problems['state'] == 1
    assert dict(session.calls)['binary_sensor.nettoolbox_problem']['state'] == 'on'


def test_push_without_supervisor_does_nothing(monkeypatch):
    monkeypatch.setattr(hasensors, 'SUPERVISOR_TOKEN', '')
    assert hasensors.push([{'id': 1, 'name': 'x'}]) == 0


# ── tlsextra: Kette, CAA, DANE ───────────────────────────────────────────────

def _self_signed_der(common_name='test.example'):
    """Ein echtes Zertifikat, in Sekundenbruchteilen erzeugt -- damit die
    DER-Verarbeitung gegen etwas Echtes läuft und nicht gegen eine Attrappe."""
    import datetime
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Testfall')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=30))
            .sign(key, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.DER)


@pytest.mark.parametrize('issuer, identifier', [
    ("R11", ''),
    ("Let's Encrypt", 'letsencrypt.org'),
    ('Sectigo Public Server Authentication CA DV E36', 'sectigo.com'),
    ('DigiCert Global G2 TLS RSA SHA256 2020 CA1', 'digicert.com'),
    ('Irgendeine Interne CA', ''),
])
def test_caa_identifier(issuer, identifier):
    assert tlsextra.caa_identifier(issuer) == identifier


def test_describe_chain_reads_real_certificates():
    chain = tlsextra.describe_chain([_self_signed_der('blatt.example')])
    assert chain[0]['subject'] == 'blatt.example'
    assert chain[0]['self_issued'] is True


def test_describe_chain_marks_unreadable_entries():
    chain = tlsextra.describe_chain([b'kaputt'])
    assert chain[0]['error'] == 'unreadable'


def test_chain_findings_name_the_missing_intermediate():
    codes = [f['code'] for f in tlsextra.chain_findings(
        [], 'unable to get local issuer certificate')]
    assert 'tls_chain_incomplete' in codes


def test_chain_findings_flag_a_lonely_leaf():
    chain = [{'self_issued': False}]
    codes = [f['code'] for f in tlsextra.chain_findings(chain, '')]
    assert codes == ['tls_chain_leaf_only']


def test_tlsa_digest_matches_openssl_convention():
    """Selector 0 = ganzes Zertifikat, 1 = öffentlicher Schlüssel;
    Matching 1 = SHA-256, 2 = SHA-512."""
    import hashlib
    der = _self_signed_der()
    assert tlsextra._tlsa_digest(der, 0, 1) == hashlib.sha256(der).hexdigest()
    assert len(tlsextra._tlsa_digest(der, 1, 1)) == 64
    assert len(tlsextra._tlsa_digest(der, 1, 2)) == 128
    assert tlsextra._tlsa_digest(der, 0, 0) == der.hex()
    with pytest.raises(ValueError):
        tlsextra._tlsa_digest(der, 0, 9)


# ── portcheck ────────────────────────────────────────────────────────────────

def test_port_list_is_sane():
    """Eine feste, kurze Liste -- kein Scanner. Jeder Eintrag vollstaendig,
    keine Dopplungen, und die riskanten Dienste sind als solche markiert."""
    ports = [p for p, _service, _expected in portcheck.PORTS]
    assert len(ports) == len(set(ports))
    assert all(1 <= p <= 65535 for p in ports)
    riskant = {p for p, _s, expected in portcheck.PORTS if not expected}
    assert {3306, 5432, 6379, 3389, 27017} <= riskant


@pytest.mark.parametrize('spec, expected', [
    ('', []),
    ('80', [80]),
    ('80,443', [80, 443]),
    ('8000-8003', [8000, 8001, 8002, 8003]),
    ('443, 80 , 443', [80, 443]),
    ('8000-7998', [7998, 7999, 8000]),
])
def test_parse_ports(spec, expected):
    assert portcheck.parse_ports(spec) == expected


@pytest.mark.parametrize('spec', ['abc', '0', '70000', '1-70000', '5-'])
def test_parse_ports_rejects_nonsense(spec):
    with pytest.raises(netcore.ProbeError):
        portcheck.parse_ports(spec)


def test_parse_ports_caps_the_range():
    """Eine Reihe von tausenden Ports waere ein Vollscanner und dauerte
    ewig -- die Grenze ist Absicht."""
    with pytest.raises(netcore.ProbeError) as excinfo:
        portcheck.parse_ports('1-5000')
    assert excinfo.value.code == 'too_many_ports'


def test_family_constants():
    assert portcheck._family_const('4') == socket.AF_INET
    assert portcheck._family_const('6') == socket.AF_INET6
    assert portcheck._family_const('') == socket.AF_UNSPEC


def test_probe_port_reports_closed_on_refusal(monkeypatch):
    """Abgelehnt ist nicht dasselbe wie unbeantwortet -- genau darauf kommt
    es bei der Fehlersuche an."""
    class _Sock:
        def __init__(self, *a, **kw):
            pass

        def settimeout(self, _t):
            pass

        def connect(self, _addr):
            raise ConnectionRefusedError()

        def close(self):
            pass

    monkeypatch.setattr(portcheck.socket, 'socket', _Sock)
    assert portcheck._probe_port(socket.AF_INET, '203.0.113.1', 25) == 'closed'


def test_probe_port_reports_filtered_on_timeout(monkeypatch):
    class _Sock:
        def __init__(self, *a, **kw):
            pass

        def settimeout(self, _t):
            pass

        def connect(self, _addr):
            raise socket.timeout()

        def close(self):
            pass

    monkeypatch.setattr(portcheck.socket, 'socket', _Sock)
    assert portcheck._probe_port(socket.AF_INET, '203.0.113.1', 25) == 'filtered'


# ── translations ─────────────────────────────────────────────────────────────

def test_locales_have_the_same_keys():
    import json
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, 'locales', 'de.json'), encoding='utf-8') as f:
        de = json.load(f)
    with open(os.path.join(here, 'locales', 'en.json'), encoding='utf-8') as f:
        en = json.load(f)
    assert set(de) == set(en)
    assert not [k for k, v in de.items() if not str(v).strip()]


# ── Technik-Erkennung ────────────────────────────────────────────────────────

def test_every_rule_field_is_a_tuple_of_patterns():
    """Ein vergessenes Komma macht aus ('x',) das nackte 'x' -- die Schleife
    liefe dann ueber die einzelnen Zeichen und wuerde alles erkennen."""
    for rule in techrules.RULES:
        for key in ('html', 'script', 'cookie', 'url', 'implies'):
            assert isinstance(rule.get(key, ()), tuple), (rule['name'], key)
        for key in ('headers', 'meta'):
            for pair in rule.get(key, ()):
                assert isinstance(pair, tuple) and len(pair) == 2, (rule['name'], key)


def test_every_pattern_compiles():
    for rule in techrules.RULES:
        for key in ('html', 'script', 'cookie', 'url'):
            for pattern in rule.get(key, ()):
                nettech._compiled(pattern)
        for key in ('headers', 'meta'):
            for _name, pattern in rule.get(key, ()):
                nettech._compiled(pattern)


def test_rule_names_are_unique_and_implies_resolve():
    names = [r['name'] for r in techrules.RULES]
    assert len(names) == len(set(names))
    known = set(names)
    for rule in techrules.RULES:
        for implied in rule.get('implies', ()):
            assert implied in known, implied


def test_suffix_match_is_never_a_substring_search():
    assert nettech._suffix_match('ns1.wixdns.net', techrules.NS_SUFFIXES) == 'Wix DNS'
    assert nettech._suffix_match('wixdns.net.attacker.example',
                                 techrules.NS_SUFFIXES) == ''


def test_suffix_match_takes_the_longest():
    table = (('outlook.com', 'kurz'), ('mail.protection.outlook.com', 'lang'))
    assert nettech._suffix_match('mx.mail.protection.outlook.com', table) == 'lang'


def _subject(headers=None, metas=None, cookies=None, resources=None,
             body='', url='https://example.com/'):
    return nettech._Subject(headers or {}, metas or {}, cookies or [],
                            resources or [], body, url)


def _scan_one(name, subject):
    rule = next(r for r in nettech._builtin_rules() if r['name'] == name)
    hits = nettech._Hits()
    nettech._scan([rule], subject, hits, time.monotonic() + 5)
    return hits


def test_scan_finds_wordpress_and_implies_php():
    hits = _scan_one('WordPress', _subject(metas={'generator': 'WordPress 6.5.2'}))
    nettech._apply_implies(nettech._builtin_rules(), hits)
    wp = hits.by_name[nettech._key('WordPress')]
    assert wp['version'] == '6.5.2'
    assert wp['confidence'] == nettech.HIGH
    # Abgeleitetes bleibt abgeleitet: PHP wurde nicht gemessen, nur gefolgert.
    assert hits.by_name[nettech._key('PHP')]['confidence'] == nettech.LOW


def test_scan_reads_cookie_names_not_values():
    assert nettech._key('PHP') in _scan_one(
        'PHP', _subject(cookies=[('PHPSESSID', 'abc')])).by_name
    # Derselbe Text als Cookie-*Wert* darf nichts ausloesen.
    assert not _scan_one('PHP', _subject(cookies=[('sid', 'PHPSESSID')])).by_name


def test_literal_prefilter_never_hides_a_real_hit():
    """Der Vorfilter darf nur ausschliessen, was das Muster ohnehin nicht
    findet -- sonst waere er kein Beschleuniger, sondern ein Fehler."""
    for rule in nettech._builtin_rules():
        for test in rule['tests']:
            if not test['l']:
                continue
            assert test['l'] in test['p'].lower(), (rule['name'], test['p'])


def test_imported_pattern_conversion():
    parsed = wapimport._parse_pattern(r'Joomla!\;version:\1\;confidence:50')
    assert parsed['p'] == 'Joomla!'
    assert parsed['v'] == '1'
    assert parsed['c'] == 50
    # Verschachtelte Quantifizierer werden gar nicht erst uebernommen.
    assert wapimport._parse_pattern(r'(a+)+b') == {}
    # Ungueltige Muster ebenso wenig.
    assert wapimport._parse_pattern('(unbalanced') == {}


def test_imported_confidence_can_only_lower_the_level():
    assert nettech._confidence('header', 100) == nettech.HIGH
    assert nettech._confidence('header', 50) == nettech.MEDIUM
    assert nettech._confidence('header', 10) == nettech.LOW
    # Eine schwache Fundstelle wird durch hohe Angabe nicht besser.
    assert nettech._confidence('html', 100) == nettech.MEDIUM


def test_imported_cookie_rule_matches_name_and_value():
    rule = {'name': 'Fremd', 'cat': 'misc', 'source': nettech.EXTRA,
            'tests': [{'k': 'cookie', 'f': 'sessid', 'p': '^abc', 'l': '', 'c': 100}]}
    hits = nettech._Hits()
    nettech._scan([rule], _subject(cookies=[('sessid', 'abcdef')]), hits,
                  time.monotonic() + 5)
    assert nettech._key('Fremd') in hits.by_name
    hits2 = nettech._Hits()
    nettech._scan([rule], _subject(cookies=[('sessid', 'xyz')]), hits2,
                  time.monotonic() + 5)
    assert not hits2.by_name


def test_requires_drops_a_hit_without_its_base():
    rules = [{'name': 'Plugin', 'cat': 'misc', 'requires': ['Basis'],
              'tests': [], 'source': nettech.EXTRA}]
    hits = nettech._Hits()
    hits.add(rules[0], 'html', 'irgendwas')
    nettech._drop_unmet_requirements(rules, hits)
    assert nettech._key('Plugin') not in hits.by_name


def test_same_technology_from_both_sets_lands_in_one_row():
    """Der Zusatz-Datensatz schreibt "Nginx" und "Nuxt.js" -- ohne gemeinsamen
    Schluessel stuende das doppelt in der Liste."""
    assert nettech._key('Nginx') == nettech._key('nginx')
    assert nettech._key('Nuxt.js') == nettech._key('Nuxt')
    assert nettech._key('Vue.js') == nettech._key('Vue')
    hits = nettech._Hits()
    extra = {'name': 'Nginx', 'cat': 'misc', 'source': nettech.EXTRA, 'tests': []}
    builtin = {'name': 'nginx', 'cat': 'server', 'source': nettech.BUILTIN,
               'site': 'nginx.org', 'tests': []}
    hits.add(extra, 'header', 'server: nginx')
    hits.add(builtin, 'header', 'server: nginx')
    assert len(hits.by_name) == 1
    row = hits.by_name[nettech._key('nginx')]
    # Der eigene Satz bestimmt Name und Kategorie, weil die Oberflaeche daran haengt.
    assert (row['name'], row['cat'], row['source']) == ('nginx', 'server', nettech.BUILTIN)


def test_cookie_parsing_keeps_flags_and_never_the_value():
    rows = nettech._parse_cookies([
        'sid=geheim123; Path=/; HttpOnly; Secure; SameSite=Lax',
        'tracker=xyz; Expires=Wed, 09 Jun 2027 10:18:14 GMT; Domain=.example.com',
        'tmp=1; Max-Age=3600',
    ])
    assert [r['name'] for r in rows] == ['sid', 'tracker', 'tmp']
    # Der Wert selbst darf nirgends im Ergebnis stehen -- nur seine Laenge.
    assert 'geheim123' not in json.dumps(rows)
    assert rows[0]['value_length'] == len('geheim123')
    assert (rows[0]['secure'], rows[0]['http_only'], rows[0]['same_site']) == (True, True, 'Lax')
    assert rows[0]['session'] is True
    # Max-Age geht laut RFC 6265 vor Expires und zaehlt in Sekunden.
    assert rows[2]['session'] is False and rows[2]['days'] == 0
    # Ein festes Datum in der Zukunft: die Restlaufzeit schrumpft mit jedem
    # Tag, gepruefte Eigenschaft ist deshalb nur "persistent, nicht Sitzung".
    assert rows[1]['domain'] == 'example.com'
    assert rows[1]['session'] is False and rows[1]['days'] > 0


def test_cookie_findings_only_fire_when_something_is_missing():
    good = nettech._parse_cookies(['a=1; Secure; HttpOnly; SameSite=Strict'])
    assert nettech._cookie_findings(good, https=True) == []
    bad = nettech._parse_cookies(['a=1'])
    codes = [f['code'] for f in nettech._cookie_findings(bad, https=True)]
    assert codes == ['tech_cookie_insecure', 'tech_cookie_no_httponly',
                     'tech_cookie_no_samesite']
    # Ohne HTTPS ist ein fehlendes Secure kein Vorwurf.
    assert 'tech_cookie_insecure' not in [
        f['code'] for f in nettech._cookie_findings(bad, https=False)]


def test_third_party_hosts_skip_own_domain_and_namespaces():
    hosts = nettech._third_party([
        'https://www.example.com/a.js',
        'https://cdn.example.com/b.js',
        'https://fonts.gstatic.com/x.woff',
        'https://fonts.gstatic.com/y.woff',
        'http://www.w3.org/2000/svg',
        '/relativ.js',
    ], 'www.example.com')
    assert [h['host'] for h in hosts] == ['fonts.gstatic.com']
    assert hosts[0]['count'] == 2


def test_category_mapping_falls_back_to_misc():
    catalogue = {'1': 'CMS', '99': 'Etwas Neues'}
    assert wapimport._category([1], catalogue) == 'cms'
    assert wapimport._category([99], catalogue) == 'misc'
    assert wapimport._category([], catalogue) == 'misc'


def test_tech_findings_and_categories_are_translated():
    import json
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, 'locales', 'de.json'), encoding='utf-8') as f:
        de = json.load(f)
    codes = ('tech_found', 'tech_nothing', 'tech_server_version',
             'tech_powered_by', 'tech_aspnet_version', 'tech_generator_version',
             'tech_trackers', 'tech_no_consent', 'tech_spa', 'tech_truncated')
    for code in codes:
        assert 'f_' + code in de, code
    for rule in techrules.RULES:
        assert 'tech_cat_' + rule['cat'] in de, rule['cat']
    for extra in ('dns', 'mail'):
        assert 'tech_cat_' + extra in de
