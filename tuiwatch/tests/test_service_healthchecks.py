"""Tests für den Selbsttest der angebundenen Fremddienste (Mailserver, Nextcloud-
Adressbuch) sowie für die Einstellung `force_ipv4`.

Kein Netz: smtplib und `requests.request` sind gemockt. Wichtig ist neben dem
Ergebnis vor allem, dass beide Checks NICHT kritisch sind — sonst zöge ein
ausgefallener Mailserver den HA-Sensor `binary_sensor.tuiwatch_api_available`
auf 'off' und löste den API-Alarm aus, obwohl die Preisverfolgung läuft.
"""
import importlib
import smtplib

import pytest

import nextcloud


@pytest.fixture
def m(tmp_path, monkeypatch):
    monkeypatch.setenv("TUIWATCH_DATA", str(tmp_path))
    monkeypatch.setenv("TUIWATCH_BASE", str(tmp_path))
    try:
        mod = importlib.import_module("app")
    except Exception as exc:
        pytest.skip(f"app nicht importierbar: {exc}")
    importlib.reload(mod)
    mod.DB_PATH = str(tmp_path / "tuiwatch.db")
    mod.init_db()
    return mod


_MAIL_CFG = {"smtp_host": "smtp.example.com", "smtp_port": 587,
             "smtp_user": "u@example.com", "smtp_password": "pw", "smtp_tls": True}
_NC_CFG = {"nc_addressbook_url": "https://nc.example.com/x/", "nc_user": "gerald",
           "nc_app_password": "pw"}

_PROPFIND_OK = b"""<?xml version="1.0" encoding="utf-8"?>
<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/remote.php/dav/addressbooks/users/gerald/contacts/</d:href>
    <d:propstat>
      <d:prop><d:displayname>Kontakte</d:displayname></d:prop>
      <d:status>HTTP/1.1 200 OK</d:status>
    </d:propstat>
  </d:response>
</d:multistatus>
"""


class _FakeSMTP:
    """Minimaler smtplib-Ersatz. `fail` wirft beim Verbinden, `auth_fail` beim Login."""
    fail = None
    auth_fail = False
    calls: list = []

    def __init__(self, host, port, timeout=None):
        type(self).calls.append((host, port))
        if type(self).fail:
            raise type(self).fail

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def ehlo(self):
        pass

    def starttls(self):
        pass

    def login(self, user, pw):
        if type(self).auth_fail:
            raise smtplib.SMTPAuthenticationError(535, b"nope")

    def noop(self):
        pass

    def sendmail(self, *a, **k):                      # pragma: no cover
        raise AssertionError("Der Selbsttest darf keine Mail verschicken")


def _smtp(monkeypatch, m, *, fail=None, auth_fail=False):
    _FakeSMTP.fail, _FakeSMTP.auth_fail, _FakeSMTP.calls = fail, auth_fail, []
    monkeypatch.setattr(m.smtplib, "SMTP", _FakeSMTP)
    monkeypatch.setattr(m.smtplib, "SMTP_SSL", _FakeSMTP)
    return _FakeSMTP


def _check(checks, name):
    return next(c for c in checks if c["name"] == name)


# ── Mailserver ────────────────────────────────────────────────────────────────

def test_smtp_probe_ok(m, monkeypatch):
    fake = _smtp(monkeypatch, m)
    monkeypatch.setattr(m, "load_config", lambda: dict(_MAIL_CFG))

    ok, detail = m.smtp_probe()

    assert ok
    assert fake.calls == [("smtp.example.com", 587)]
    assert "smtp.example.com:587" in detail and "STARTTLS" in detail


def test_smtp_probe_connect_error(m, monkeypatch):
    _smtp(monkeypatch, m, fail=TimeoutError("timeout"))
    monkeypatch.setattr(m, "load_config", lambda: dict(_MAIL_CFG))

    ok, detail = m.smtp_probe()

    assert not ok
    assert "TimeoutError" in detail


def test_smtp_probe_auth_error(m, monkeypatch):
    _smtp(monkeypatch, m, auth_fail=True)
    monkeypatch.setattr(m, "load_config", lambda: dict(_MAIL_CFG))

    ok, detail = m.smtp_probe()

    assert not ok
    assert "Anmeldung abgelehnt" in detail


def test_smtp_probe_ssl_mode_uses_smtp_ssl(m, monkeypatch):
    """smtp_tls aus = SSL/TLS direkt — derselbe Pfad wie beim echten Versand."""
    used = {}
    monkeypatch.setattr(m, "load_config", lambda: dict(_MAIL_CFG, smtp_tls=False,
                                                       smtp_port=465))
    _smtp(monkeypatch, m)
    monkeypatch.setattr(m.smtplib, "SMTP",
                        lambda *a, **k: used.setdefault("plain", True))
    monkeypatch.setattr(m.smtplib, "SMTP_SSL", _FakeSMTP)

    ok, detail = m.smtp_probe()

    assert ok and "SSL" in detail
    assert "plain" not in used


# ── Nextcloud-Adressbuch ──────────────────────────────────────────────────────

def test_check_addressbook_ok(monkeypatch):
    calls = {}

    class _Resp:
        status_code = 207
        content = _PROPFIND_OK

    def fake_request(method, url, **kw):
        calls.update(method=method, url=url, auth=kw.get("auth"),
                     depth=(kw.get("headers") or {}).get("Depth"))
        return _Resp()

    monkeypatch.setattr(nextcloud.requests, "request", fake_request)
    ok, detail = nextcloud.check_addressbook("https://nc.example.com/x/", "gerald", "pw")

    assert ok
    assert calls["method"] == "PROPFIND"          # kein Voll-Abzug aller vCards
    assert calls["depth"] == "0"
    assert calls["auth"] == ("gerald", "pw")
    assert "Kontakte" in detail


def test_check_addressbook_http_error(monkeypatch):
    class _Resp:
        status_code = 401
        content = b""

    monkeypatch.setattr(nextcloud.requests, "request", lambda *a, **k: _Resp())
    ok, detail = nextcloud.check_addressbook("https://nc.example.com/x/", "gerald", "x")

    assert not ok and detail == "HTTP 401"


def test_check_addressbook_timeout_is_reported_not_raised(monkeypatch):
    """Der gemeldete Fehlerfall: AAAA-Eintrag zeigt ins Leere, Verbindung läuft in
    den Zeitüberschreitungs-Fehler. Der Selbsttest muss das melden, nicht werfen."""
    def boom(*a, **k):
        raise nextcloud.requests.exceptions.ConnectTimeout("timed out")

    monkeypatch.setattr(nextcloud.requests, "request", boom)
    ok, detail = nextcloud.check_addressbook("https://nc.example.com/x/", "gerald", "pw")

    assert not ok and detail == "ConnectTimeout"


def test_check_addressbook_unconfigured():
    assert nextcloud.check_addressbook("", "", "") == (False, "nicht konfiguriert")


# ── Einbindung in den Selbsttest ──────────────────────────────────────────────

def test_no_checks_when_nothing_configured(m, monkeypatch):
    monkeypatch.setattr(m, "load_config", lambda: {})
    assert m._integration_healthchecks() == []


def test_both_services_checked_and_never_critical(m, monkeypatch):
    _smtp(monkeypatch, m)
    monkeypatch.setattr(m, "load_config", lambda: dict(_MAIL_CFG, **_NC_CFG))
    monkeypatch.setattr(m.nextcloud, "check_addressbook",
                        lambda *a, **k: (True, 'Adressbuch „Kontakte"'))

    checks = m._integration_healthchecks()

    assert {c["name"] for c in checks} == {"Mailserver (SMTP)", "Nextcloud-Adressbuch"}
    assert all(c["ok"] for c in checks)
    assert not any(c["critical"] for c in checks)


def test_probe_exception_becomes_failed_check(m, monkeypatch):
    monkeypatch.setattr(m, "load_config", lambda: dict(_NC_CFG))

    def boom(*a, **k):
        raise RuntimeError("kaputt")

    monkeypatch.setattr(m.nextcloud, "check_addressbook", boom)
    c = _check(m._integration_healthchecks(), "Nextcloud-Adressbuch")

    assert not c["ok"] and c["detail"] == "RuntimeError"


def test_failed_service_does_not_flip_ha_sensor(m, monkeypatch):
    """Mailserver tot, TUI-API in Ordnung: Sensor bleibt 'on', kein API-Alarm."""
    posts = []
    m.SUPERVISOR_TOKEN = "testtoken"
    monkeypatch.setattr(m, "load_config",
                        lambda: dict(_MAIL_CFG, ha_sensors=True))
    monkeypatch.setattr(m.http, "post",
                        lambda url, **kw: posts.append((url, kw.get("json"))))
    monkeypatch.setattr(m, "api_healthcheck", lambda **k: {
        "ok": True, "ts": 1000,
        "checks": [{"name": "Preis/Angebot-API", "ok": True, "critical": True}]})
    monkeypatch.setattr(m, "_flight_healthchecks", lambda: [])
    _smtp(monkeypatch, m, fail=TimeoutError("timeout"))
    alarms = []
    monkeypatch.setattr(m, "_check_api_alarm", lambda res: alarms.append(res))

    res = m._run_healthcheck()

    assert not _check(res["checks"], "Mailserver (SMTP)")["ok"]
    url, payload = next(p for p in posts if "api_available" in p[0])
    assert payload["state"] == "on"
    assert payload["attributes"]["failing"] == []


def test_flight_check_failure_does_not_swallow_service_checks(m, monkeypatch):
    """Eigener try-Block je Gruppe: wirft die Flugplan-Prüfung, müssen die
    Dienste-Checks trotzdem im Ergebnis stehen."""
    monkeypatch.setattr(m, "load_config", lambda: dict(_MAIL_CFG))
    monkeypatch.setattr(m, "api_healthcheck", lambda **k: {
        "ok": True, "ts": 1000, "checks": []})

    def boom():
        raise RuntimeError("Flugplan kaputt")

    monkeypatch.setattr(m, "_flight_healthchecks", boom)
    monkeypatch.setattr(m, "_check_api_alarm", lambda res: None)
    monkeypatch.setattr(m, "_push_health_sensor", lambda res: None)
    _smtp(monkeypatch, m)

    res = m._run_healthcheck()

    assert _check(res["checks"], "Mailserver (SMTP)")["ok"]


# ── force_ipv4 ────────────────────────────────────────────────────────────────

def test_force_ipv4_switches_urllib3_family(m, monkeypatch):
    import urllib3.util.connection as conn
    monkeypatch.setattr(m, "_HAS_IPV6_DEFAULT", True)
    conn.HAS_IPV6 = True

    monkeypatch.setattr(m, "load_config", lambda: {"force_ipv4": True})
    m._apply_ipv4_pref()
    assert conn.HAS_IPV6 is False
    assert conn.allowed_gai_family() == __import__("socket").AF_INET

    monkeypatch.setattr(m, "load_config", lambda: {"force_ipv4": False})
    m._apply_ipv4_pref()
    assert conn.HAS_IPV6 is True
