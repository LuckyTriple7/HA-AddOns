"""Tests for the parts that need no network.

Everything here is a pure function: given this input, produce that output.
The probes themselves are deliberately left out -- they talk to real DNS and
real mail servers, and a test suite that needs the internet to pass is a test
suite nobody runs.

Run with:  python3 -m pytest tests -q     (from the add-on directory)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import blocklists  # noqa: E402
import geoip  # noqa: E402
import mailprovider  # noqa: E402
import netcore  # noqa: E402
import netutils  # noqa: E402
import seocheck  # noqa: E402
import smtpcheck  # noqa: E402
import tlscheck  # noqa: E402


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
