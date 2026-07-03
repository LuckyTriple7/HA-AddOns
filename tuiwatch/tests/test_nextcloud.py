"""Tests für den Nextcloud-CardDAV-Kontaktabruf (ohne Netz).

`parse_carddav_response`/`_unfold`/`_parse_vcard` sind rein und ohne Netz testbar;
`fetch_contacts` wird gegen ein gemocktes `requests.request` geprüft. Am Ende ein
Test für die `/api/contacts`-Route inkl. Cache.
"""
import importlib

import pytest

import nextcloud

pytest.importorskip("flask")

ING = {"X-Ingress-Path": "/test"}

# Zeile 1 endet bewusst mit einem Leerzeichen vor dem Fold (RFC 6350 §3.2: das
# Leerzeichen der Fortsetzungszeile ist ein reiner Einfüge-Marker, kein Original-
# Inhalt) — Unfold muss "Maria Elisabeth Langer-Mustermann" ergeben, nicht
# "Maria ElisabethLanger-Mustermann".
_VCARD_1 = (
    "BEGIN:VCARD\r\n"
    "VERSION:3.0\r\n"
    "FN:Maria Elisabeth \r\n"
    " Langer-Mustermann\r\n"
    "EMAIL;TYPE=HOME:maria@example.com\r\n"
    "END:VCARD\r\n"
)
_VCARD_2 = (
    "BEGIN:VCARD\r\n"
    "VERSION:3.0\r\n"
    "FN:Peter Beispiel\r\n"
    "EMAIL;TYPE=HOME:peter.privat@example.com\r\n"
    "EMAIL;TYPE=WORK:peter.arbeit@example.com\r\n"
    "END:VCARD\r\n"
)

_MULTISTATUS = f"""<?xml version="1.0" encoding="utf-8"?>
<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav">
  <d:response>
    <d:href>/remote.php/dav/addressbooks/users/gerald/contacts/1.vcf</d:href>
    <d:propstat>
      <d:prop>
        <d:getetag>"etag1"</d:getetag>
        <c:address-data>{_VCARD_1}</c:address-data>
      </d:prop>
      <d:status>HTTP/1.1 200 OK</d:status>
    </d:propstat>
  </d:response>
  <d:response>
    <d:href>/remote.php/dav/addressbooks/users/gerald/contacts/2.vcf</d:href>
    <d:propstat>
      <d:prop>
        <d:getetag>"etag2"</d:getetag>
        <c:address-data>{_VCARD_2}</c:address-data>
      </d:prop>
      <d:status>HTTP/1.1 200 OK</d:status>
    </d:propstat>
  </d:response>
</d:multistatus>
""".encode("utf-8")


def test_unfold_removes_only_fold_marker():
    assert nextcloud._unfold("FN:Maria Elisabeth \r\n Langer-Mustermann") == \
        "FN:Maria Elisabeth Langer-Mustermann"


def test_parse_vcard_single_email():
    contacts = nextcloud._parse_vcard(_VCARD_1)
    assert contacts == [{"name": "Maria Elisabeth Langer-Mustermann",
                         "email": "maria@example.com"}]


def test_parse_vcard_multiple_emails():
    contacts = nextcloud._parse_vcard(_VCARD_2)
    assert contacts == [
        {"name": "Peter Beispiel", "email": "peter.privat@example.com"},
        {"name": "Peter Beispiel", "email": "peter.arbeit@example.com"},
    ]


def test_parse_carddav_response_sorted_by_name():
    contacts = nextcloud.parse_carddav_response(_MULTISTATUS)
    assert [c["name"] for c in contacts] == [
        "Maria Elisabeth Langer-Mustermann", "Peter Beispiel", "Peter Beispiel"]
    assert {c["email"] for c in contacts} == {
        "maria@example.com", "peter.privat@example.com", "peter.arbeit@example.com"}


def test_fetch_contacts_ok(monkeypatch):
    calls = {}

    class _Resp:
        status_code = 207
        content = _MULTISTATUS

    def fake_request(method, url, **kw):
        calls["method"] = method
        calls["url"] = url
        calls["auth"] = kw.get("auth")
        return _Resp()

    monkeypatch.setattr(nextcloud.requests, "request", fake_request)
    contacts = nextcloud.fetch_contacts("https://nc.example.com/.../contacts/",
                                        "gerald", "app-pw", verbose=True)
    assert len(contacts) == 3
    assert calls["method"] == "REPORT"
    assert calls["auth"] == ("gerald", "app-pw")


def test_fetch_contacts_http_error_returns_empty(monkeypatch):
    class _Resp:
        status_code = 401
        content = b""

    monkeypatch.setattr(nextcloud.requests, "request", lambda *a, **k: _Resp())
    assert nextcloud.fetch_contacts("https://nc.example.com/x/", "gerald", "wrong") == []


def test_fetch_contacts_network_error_returns_empty(monkeypatch):
    def boom(*a, **k):
        raise ConnectionError("nope")
    monkeypatch.setattr(nextcloud.requests, "request", boom)
    assert nextcloud.fetch_contacts("https://nc.example.com/x/", "gerald", "pw") == []


def test_fetch_contacts_without_config_returns_empty():
    assert nextcloud.fetch_contacts("", "", "") == []


@pytest.fixture
def app_mod(tmp_path, monkeypatch):
    monkeypatch.setenv("TUIWATCH_DATA", str(tmp_path))
    monkeypatch.setenv("TUIWATCH_BASE", str(tmp_path))
    try:
        m = importlib.import_module("app")
    except Exception as exc:
        pytest.skip(f"app nicht importierbar: {exc}")
    importlib.reload(m)
    m.DB_PATH = str(tmp_path / "tuiwatch.db")
    m.init_db()
    m._contacts_cache = []
    return m


def test_api_contacts_unconfigured(app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "load_config", lambda: {})
    c = app_mod.app.test_client()
    r = c.get("/api/contacts", headers=ING)
    assert r.status_code == 200
    assert r.get_json() == {"configured": False, "contacts": []}


def test_api_contacts_cached(app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "load_config", lambda: {
        "nc_addressbook_url": "https://nc.example.com/x/", "nc_user": "gerald",
        "nc_app_password": "pw"})
    calls = []
    monkeypatch.setattr(app_mod, "fetch_contacts", lambda *a, **k: calls.append(1) or
                        [{"name": "Peter", "email": "peter@example.com"}])
    c = app_mod.app.test_client()
    r1 = c.get("/api/contacts", headers=ING).get_json()
    assert r1 == {"configured": True, "contacts": [{"name": "Peter", "email": "peter@example.com"}]}
    r2 = c.get("/api/contacts", headers=ING).get_json()
    assert r2 == r1
    assert len(calls) == 1   # zweiter Aufruf kam aus dem Cache

    c.get("/api/contacts?refresh=1", headers=ING)
    assert len(calls) == 2   # ?refresh=1 erzwingt Neuladen

    assert c.get("/api/contacts").status_code == 401   # ohne Ingress: Auth nötig
