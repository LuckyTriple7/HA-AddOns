"""Zwei-Faktor-Anmeldung (twofa.py + /login-Schritt 2, ab 0.117.0)."""
import base64
import importlib
import os

import pytest

pytest.importorskip("flask")

ING = {"X-Ingress-Path": "/test"}
CFG = {"username": "admin", "password": "secret", "session_hours": 24,
       "twofa_remember_days": 30}


@pytest.fixture
def m(tmp_path, monkeypatch):
    monkeypatch.setenv("TUIWATCH_DATA", str(tmp_path))
    # Quellordner als Basis: /login rendert templates/login.html
    monkeypatch.setenv("TUIWATCH_BASE", os.path.dirname(os.path.dirname(__file__)))
    try:
        mod = importlib.import_module("app")
    except Exception as exc:                     # pragma: no cover
        pytest.skip(f"app nicht importierbar: {exc}")
    importlib.reload(mod)
    mod.DB_PATH = str(tmp_path / "tuiwatch.db")
    mod.init_db()
    mod.twofa.init(str(tmp_path))
    cfg = dict(CFG)
    monkeypatch.setattr(mod, "load_config", lambda: cfg)
    mod._test_cfg = cfg
    mod._failed_attempts.clear()
    mod._blocked_ips.clear()
    return mod


def _enable(m):
    secret = m.twofa.start_setup()
    codes = m.twofa.confirm_setup(m.twofa._totp_at(secret, __import__("time").time()))
    assert codes and len(codes) == 10
    return secret, codes


def _now_code(m, secret):
    # nächstes Zeitfenster: der Code aus dem Aktivieren gilt nicht noch einmal
    return m.twofa._totp_at(secret, __import__("time").time() + m.twofa.TOTP_STEP)


def _login(c, user="admin", pw="secret"):
    return c.post("/login", data={"username": user, "password": pw})


def test_totp_rfc6238_vector(m):
    # RFC 6238 Anhang B, SHA1, T=59 → 94287082 (8 Stellen) → 287082 bei 6 Stellen
    secret = base64.b32encode(b"12345678901234567890").decode()
    assert m.twofa._totp_at(secret, 59) == "287082"


def test_login_without_2fa_unchanged(m):
    c = m.app.test_client()
    r = _login(c)
    assert r.status_code == 302 and c.get_cookie("session")


def test_wrong_password_still_rejected(m):
    c = m.app.test_client()
    r = _login(c, pw="falsch")
    assert r.status_code == 200 and c.get_cookie("session") is None


def test_login_asks_for_code_then_grants(m):
    secret, _ = _enable(m)
    c = m.app.test_client()
    r = _login(c)
    assert r.status_code == 200 and b'name="step" value="code"' in r.data
    assert c.get_cookie("session") is None
    r = c.post("/login", data={"step": "code", "code": "000000"})
    assert c.get_cookie("session") is None and "Ungültiger Code".encode() in r.data
    r = c.post("/login", data={"step": "code", "code": _now_code(m, secret)})
    assert r.status_code == 302 and c.get_cookie("session")
    assert c.get_cookie(m.twofa.TRUST_COOKIE) is None      # nicht angehakt


def test_code_step_needs_password_first(m):
    secret, _ = _enable(m)
    c = m.app.test_client()
    r = c.post("/login", data={"step": "code", "code": _now_code(m, secret)})
    assert r.status_code == 302 and c.get_cookie("session") is None


def test_backup_code_works_once(m):
    _, codes = _enable(m)
    for expect_ok in (True, False):
        c = m.app.test_client()
        _login(c)
        c.post("/login", data={"step": "code", "code": codes[0]})
        assert bool(c.get_cookie("session")) is expect_ok


def test_remember_device_skips_code(m):
    secret, _ = _enable(m)
    c = m.app.test_client()
    _login(c)
    c.post("/login", data={"step": "code", "code": _now_code(m, secret),
                           "remember_device": "1"})
    trust = c.get_cookie(m.twofa.TRUST_COOKIE)
    assert trust is not None and trust.max_age == 30 * 86400
    c.delete_cookie("session")
    r = _login(c)
    assert r.status_code == 302 and c.get_cookie("session")   # kein Code nötig
    # Nur der Hash liegt auf der Platte
    assert trust.value not in open(m.twofa._path, encoding="utf-8").read()


def test_remember_off_or_forgotten_asks_again(m):
    secret, _ = _enable(m)
    c = m.app.test_client()
    _login(c)
    c.post("/login", data={"step": "code", "code": _now_code(m, secret),
                           "remember_device": "1"})
    c.delete_cookie("session")
    m._test_cfg["twofa_remember_days"] = 0          # Option aus → sofort wirksam
    assert _login(c).status_code == 200 and c.get_cookie("session") is None
    m._test_cfg["twofa_remember_days"] = 30
    m.twofa.forget_devices()
    assert _login(c).status_code == 200 and c.get_cookie("session") is None


def test_no_remember_checkbox_when_days_zero(m):
    _enable(m)
    m._test_cfg["twofa_remember_days"] = 0
    r = _login(m.app.test_client())
    assert b"remember_device" not in r.data


def test_api_setup_enable_disable(m):
    c = m.app.test_client()
    assert c.get("/api/2fa").status_code == 401             # ohne Anmeldung
    d = c.post("/api/2fa/setup", headers=ING).get_json()
    assert d["secret"] and d["uri"].startswith("otpauth://totp/TUIWatch")
    assert c.post("/api/2fa/enable", headers=ING, json={"code": "000000"}).status_code == 400
    r = c.post("/api/2fa/enable", headers=ING,
               json={"code": m.twofa._totp_at(d["secret"], __import__("time").time())})
    assert r.status_code == 200 and len(r.get_json()["backup_codes"]) == 10
    assert c.get("/api/2fa", headers=ING).get_json()["enabled"] is True
    assert c.post("/api/2fa/setup", headers=ING).status_code == 400   # schon aktiv
    assert c.post("/api/2fa/disable", headers=ING, json={"code": "1"}).status_code == 400
    assert m.twofa.enabled()
    r = c.post("/api/2fa/disable", headers=ING, json={"code": _now_code(m, d["secret"])})
    assert r.status_code == 200 and not m.twofa.enabled()


def test_corrupt_file_fails_closed(m):
    secret, codes = _enable(m)
    open(m.twofa._path, "w").write("{kaputt")
    assert m.twofa.enabled() is True
    assert not m.twofa.check_code(_now_code(m, secret))
    assert not m.twofa.check_code(codes[0])
    c = m.app.test_client()
    assert c.post("/api/2fa/disable", headers=ING, json={}).status_code == 200
    assert m.twofa.enabled() is False


def test_totp_code_cannot_be_replayed(m):
    secret, _ = _enable(m)
    code = _now_code(m, secret)
    assert m.twofa.check_code(code) is True
    assert m.twofa.check_code(code) is False


def test_setup_code_not_reusable_for_login(m):
    secret = m.twofa.start_setup()
    code = m.twofa._totp_at(secret, __import__("time").time())
    assert m.twofa.confirm_setup(code)
    assert m.twofa.check_code(code) is False


def test_emergency_option_skips_code_without_deleting(m, monkeypatch):
    _enable(m)
    monkeypatch.setattr(m, "load_options", lambda: {"twofa_reset": True})
    c = m.app.test_client()
    assert _login(c).status_code == 302 and c.get_cookie("session")
    assert m.twofa.enabled()                       # nichts gelöscht
    assert c.get("/api/2fa").get_json()["bypassed"] is True
