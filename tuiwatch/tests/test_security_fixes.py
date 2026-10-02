"""Befunde der Sicherheitsprüfung vom 26.09.2026 (0.117.1)."""
import importlib
import io
import json
import os
import zipfile

import pytest

pytest.importorskip("flask")

ING = {"X-Ingress-Path": "/test"}


@pytest.fixture
def m(tmp_path, monkeypatch):
    monkeypatch.setenv("TUIWATCH_DATA", str(tmp_path))
    monkeypatch.setenv("TUIWATCH_BASE", os.path.dirname(os.path.dirname(__file__)))
    try:
        mod = importlib.import_module("app")
    except Exception as exc:                     # pragma: no cover
        pytest.skip(f"app nicht importierbar: {exc}")
    importlib.reload(mod)
    mod.DB_PATH = str(tmp_path / "tuiwatch.db")
    mod.init_db()
    mod.settings_store.init(str(tmp_path))
    mod._key_gate.update(fails=0, until=0.0)
    return mod


# ── #4 Adresse geändert → Geheimnis verfällt ──────────────────────────────────

def test_changing_target_clears_bound_secret(m):
    if not m.settings_store.crypto_ready():
        pytest.skip("cryptography fehlt")
    st = m.settings_store
    st.save({"ha_url": "http://ha.local:8123", "ha_token": "geheim"})
    assert st.load()["ha_token"] == "geheim"
    changed = st.save({"ha_url": "https://angreifer.example"})
    assert "ha_token" in changed and not st.load().get("ha_token")
    # Adresse und Token zusammen geändert → Token bleibt der neue
    st.save({"ha_url": "http://ha2.local:8123", "ha_token": "neu"})
    assert st.load()["ha_token"] == "neu"
    # Nur das Token ändern lässt die Adresse unberührt
    st.save({"smtp_host": "smtp.a.de", "smtp_password": "pw"})
    st.save({"smtp_password": "pw2"})
    assert st.load()["smtp_password"] == "pw2"


def test_settings_api_reports_cleared_secret(m):
    if not m.settings_store.crypto_ready():
        pytest.skip("cryptography fehlt")
    c = m.app.test_client()
    c.post("/api/settings", headers=ING, json={"values": {
        "nc_addressbook_url": "https://nc.a.de/x", "nc_app_password": "pw"}})
    d = c.post("/api/settings", headers=ING, json={"values": {
        "nc_addressbook_url": "https://nc.b.de/x"}}).get_json()
    assert d["cleared"] == ["nc_app_password"]


# ── #3 Restore ersetzt Einstellungen nur mit Passwort ─────────────────────────

def _backup_zip(settings: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("data.json", json.dumps({"offers": []}))
        zf.writestr("settings.json", json.dumps(settings))
    return buf.getvalue()


def test_restore_replace_settings_needs_password(m, monkeypatch):
    monkeypatch.setattr(m, "load_config", lambda: {"password": "secret"})
    m.settings_store.save({"verbose_log": True})
    c = m.app.test_client()
    data = {"file": (io.BytesIO(_backup_zip({"ha_url": "https://boese.example"})), "b.zip"),
            "replace_settings": "1"}
    r = c.post("/api/restore", headers=ING, data=data, content_type="multipart/form-data")
    assert r.status_code == 403
    assert "boese" not in open(m.SETTINGS_PATH, encoding="utf-8").read()
    data = {"file": (io.BytesIO(_backup_zip({"ha_url": "https://ok.example"})), "b.zip"),
            "replace_settings": "1", "password": "secret"}
    r = c.post("/api/restore", headers=ING, data=data, content_type="multipart/form-data")
    assert r.status_code == 200
    assert "ok.example" in open(m.SETTINGS_PATH, encoding="utf-8").read()


# ── #8 gleicher Passwort-Default wie /login ───────────────────────────────────

def test_key_gate_uses_login_default(m, monkeypatch):
    monkeypatch.setattr(m, "load_config", lambda: {})
    with m.app.test_request_context():
        assert m._key_gate_check("") is not None          # leer kommt nicht mehr durch
        assert m._key_gate_check("secret") is None


# ── #5 Telegram-Token nie ins Log ─────────────────────────────────────────────

def test_telegram_error_does_not_log_token(m, monkeypatch, caplog):
    monkeypatch.setattr(m, "load_config",
                        lambda: {"telegram_bot_token": "123:GEHEIM", "telegram_chat_id": "1"})

    def boom(url, **kw):
        raise m.http.exceptions.ConnectionError(f"Max retries exceeded with url: {url}")
    monkeypatch.setattr(m.http, "post", boom)
    with caplog.at_level("ERROR"):
        m._notify_telegram("x")
    assert "GEHEIM" not in caplog.text and "ConnectionError" in caplog.text


# ── #9 GIATA-ID nur numerisch ─────────────────────────────────────────────────

def test_giata_images_rejects_non_numeric(m, monkeypatch):
    called = []
    monkeypatch.setattr(m, "fetch_giata_image_urls", lambda g: called.append(g) or [])
    c = m.app.test_client()
    assert c.get("/api/giata_images/12%26x%3D1", headers=ING).status_code == 400
    assert called == []
    assert c.get("/api/giata_images/123456", headers=ING).status_code == 200


# ── #6 Secure-Cookie bei HTTPS ────────────────────────────────────────────────

def test_session_cookie_secure_over_https(m, monkeypatch):
    monkeypatch.setattr(m, "load_config",
                        lambda: {"username": "admin", "password": "secret", "session_hours": 1})
    c = m.app.test_client()
    r = c.post("/login", data={"username": "admin", "password": "secret"},
               base_url="https://localhost")
    assert "Secure" in r.headers["Set-Cookie"]
    r = m.app.test_client().post("/login", data={"username": "admin", "password": "secret"})
    assert "Secure" not in r.headers["Set-Cookie"]


# ── Hilfe „Diese Verbindung“ für trusted_proxies ──────────────────────────────

def test_connection_info_suggests_docker_network(m, monkeypatch):
    monkeypatch.setattr(m, "load_config", lambda: {"trusted_proxies": ""})
    c = m.app.test_client()
    d = c.get("/api/connection-info", headers=dict(ING, **{"X-Forwarded-For": "93.184.216.34"}),
              environ_base={"REMOTE_ADDR": "172.18.0.5"}).get_json()
    assert d["peer"] == "172.18.0.5" and d["detected"] == "172.18.0.5"
    assert d["trusted"] is False and d["suggestion"] == "172.18.0.0/16"
    monkeypatch.setattr(m, "load_config", lambda: {"trusted_proxies": "172.18.0.0/16"})
    d = c.get("/api/connection-info", headers=dict(ING, **{"X-Forwarded-For": "93.184.216.34"}),
              environ_base={"REMOTE_ADDR": "172.18.0.5"}).get_json()
    assert d["trusted"] is True and d["detected"] == "93.184.216.34" and d["suggestion"] == ""


def test_connection_info_without_proxy_suggests_nothing(m):
    d = m.app.test_client().get("/api/connection-info", headers=ING).get_json()
    assert d["forwarded"] == [] and d["suggestion"] == ""


def test_client_ip_x_real_ip_and_cloudflare(m, monkeypatch):
    import ipaddress

    class R:
        def __init__(self, h, ra="172.30.32.1"):
            self.headers, self.remote_addr = h, ra
    nets = [ipaddress.ip_network("172.30.32.0/23")]
    monkeypatch.setattr(m, "_trusted_proxy_nets", lambda: nets)
    # NPM setzt X-Real-IP auf seinen Absender
    assert m.get_client_ip(R({"X-Real-IP": "45.83.12.7"})) == "45.83.12.7"
    # Cloudflare-Kopf zählt NICHT, solange der Absender davor kein eigener Proxy ist
    assert m.get_client_ip(R({"X-Real-IP": "45.83.12.7",
                              "CF-Connecting-IP": "1.1.1.1"})) == "45.83.12.7"
    # Cloudflare-Netz eingetragen → ganzer Weg vertraut → CF-Kopf gilt
    nets.append(ipaddress.ip_network("162.158.0.0/15"))
    assert m.get_client_ip(R({"X-Real-IP": "162.158.1.5",
                              "CF-Connecting-IP": "93.184.216.34"})) == "93.184.216.34"


def test_waitress_keeps_proxy_headers(m):
    assert m._WAITRESS_PROXY_KW == {"clear_untrusted_proxy_headers": False}


# ── Seitenwerte nach dem Speichern (0.117.3) ──────────────────────────────────

def test_ui_flags_count_perplexity_as_ai(m):
    assert m._ui_flags({"perplexity_api_key": "p"})["ai"] is True
    assert m._ui_flags({})["ai"] is False


def test_settings_save_returns_ui_flags(m):
    d = m.app.test_client().post("/api/settings", headers=ING, json={"values": {
        "enable_check24_compare": True}}).get_json()
    assert d["ui"]["check24"] is True
