"""Ohne Home Assistant haben die HA-Felder nichts im Einstellungen-Dialog zu suchen.

`ha_sensors`, `notify_ha` und `ha_notify_service` laufen ausschliesslich ueber die
Supervisor-API. Faellt das SUPERVISOR_TOKEN weg (eigener Docker-Host, Server im
Netz), sind die drei Schalter wirkungslos — angezeigt wurden sie trotzdem.
"""
import importlib

import pytest

pytest.importorskip("flask")

ING = {"X-Ingress-Path": "/test"}


def _load(tmp_path, monkeypatch):
    monkeypatch.setenv("TUIWATCH_DATA", str(tmp_path))
    monkeypatch.setenv("TUIWATCH_BASE", str(tmp_path))
    try:
        m = importlib.import_module("app")
    except Exception as exc:                     # pragma: no cover
        pytest.skip(f"app nicht importierbar: {exc}")
    importlib.reload(m)
    m.DB_PATH = str(tmp_path / "tuiwatch.db")
    m.init_db()
    return m


def _keys(m):
    d = m.app.test_client().get("/api/settings", headers=ING).get_json()
    return {i["key"] for g in d["groups"] for i in g["items"]}


def test_ha_fields_hidden_without_supervisor(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    keys = _keys(_load(tmp_path, monkeypatch))
    assert not (keys & {"ha_sensors", "notify_ha", "ha_notify_service"})
    assert "telegram_bot_token" in keys        # der Rest der Gruppe bleibt


def test_ha_fields_shown_inside_addon(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "dummy")
    keys = _keys(_load(tmp_path, monkeypatch))
    assert {"ha_sensors", "notify_ha", "ha_notify_service"} <= keys


# ── Externe HA-Verbindung (ha_url + ha_token, ab 0.116.0) ───────────────────────

_EXT = {"ha_url": "http://192.168.178.10:8123/", "ha_token": "llat", "ha_sensors": True,
        "notify_ha": True}


def test_external_ha_fields_only_outside_addon(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    keys = _keys(_load(tmp_path, monkeypatch))
    assert {"ha_url", "ha_token"} <= keys
    monkeypatch.setenv("SUPERVISOR_TOKEN", "dummy")
    assert not (_keys(_load(tmp_path, monkeypatch)) & {"ha_url", "ha_token"})


def test_ha_fields_shown_with_external_connection(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    m = _load(tmp_path, monkeypatch)
    monkeypatch.setattr(m, "load_config", lambda: dict(_EXT))
    assert {"ha_sensors", "notify_ha", "ha_notify_service"} <= _keys(m)


def test_external_base_normalised(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    assert m._ha_external_base("http://ha.local:8123/") == "http://ha.local:8123/api"
    assert m._ha_external_base("https://ha.example.de/api") == "https://ha.example.de/api"
    assert m._ha_external_base("ftp://ha.local") == ""
    assert m._ha_external_base("ha.local:8123") == ""
    assert m._ha_external_base("") == ""


def test_ha_api_prefers_supervisor(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    monkeypatch.setattr(m, "load_config", lambda: dict(_EXT))
    monkeypatch.setattr(m, "SUPERVISOR_TOKEN", "sup")
    assert m._ha_api() == (m.HA_BASE, {"Authorization": "Bearer sup"})
    monkeypatch.setattr(m, "SUPERVISOR_TOKEN", "")
    assert m._ha_api() == ("http://192.168.178.10:8123/api",
                           {"Authorization": "Bearer llat"})
    monkeypatch.setattr(m, "load_config", lambda: {"ha_url": "http://x:8123"})
    assert m._ha_api() is None                   # Token fehlt


def test_notifications_go_to_external_ha(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    monkeypatch.setattr(m, "SUPERVISOR_TOKEN", "")
    monkeypatch.setattr(m, "load_config", lambda: dict(_EXT))
    posts = []
    monkeypatch.setattr(m.http, "post",
                        lambda url, **kw: posts.append((url, kw["headers"])))
    m._notify_ha("Titel", "Text", "t1")
    assert posts == [("http://192.168.178.10:8123/api/services/persistent_notification/create",
                      {"Authorization": "Bearer llat"})]


def test_external_token_does_not_unlock_ingress(tmp_path, monkeypatch):
    """Der externe Token darf den fälschbaren X-Ingress-Path nicht freischalten."""
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    monkeypatch.delenv("TUIWATCH_TRUST_INGRESS", raising=False)
    m = _load(tmp_path, monkeypatch)
    monkeypatch.setattr(m, "load_config", lambda: dict(_EXT, username="admin",
                                                       password="secret"))
    assert m._trust_ingress_header() is False


class _R:
    def __init__(self, status, data=None):
        self.status_code, self._data = status, data

    def json(self):
        if self._data is None:
            raise ValueError("kein JSON")
        return self._data


def _ha_test(m):
    return m.app.test_client().post("/api/settings/ha-test", headers=ING).get_json()


def test_ha_test_endpoint(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    m = _load(tmp_path, monkeypatch)
    monkeypatch.setattr(m, "SUPERVISOR_TOKEN", "")
    assert _ha_test(m)["error"] == "no_url"

    monkeypatch.setattr(m, "load_config", lambda: dict(_EXT))
    seen = []

    def ok(url, **kw):
        seen.append(url)
        return _R(200, {"version": "2026.9.2", "location_name": "Zuhause"})
    monkeypatch.setattr(m.http, "get", ok)
    posts = []
    monkeypatch.setattr(m.http, "post",
                        lambda url, **kw: posts.append((url, kw["json"])) or _R(200, []))
    d = _ha_test(m)
    assert d == {"ok": True, "mode": "external", "notified": True,
                 "version": "2026.9.2", "location": "Zuhause"}
    assert seen == ["http://192.168.178.10:8123/api/config"]
    # sichtbare Probe in HA, immer unter derselben ID
    assert posts[0][0] == "http://192.168.178.10:8123/api/services/persistent_notification/create"
    assert posts[0][1]["notification_id"] == "tuiwatch_verbindungstest"
    monkeypatch.setattr(m.http, "post", lambda url, **kw: _R(403))
    assert _ha_test(m)["notified"] is False

    monkeypatch.setattr(m.http, "get", lambda url, **kw: _R(401))
    assert _ha_test(m)["error"] == "auth"
    monkeypatch.setattr(m.http, "get", lambda url, **kw: _R(200))
    assert _ha_test(m)["error"] == "bad_response"

    def boom(url, **kw):
        raise m.http.exceptions.ConnectionError("geheimer Detailtext")
    monkeypatch.setattr(m.http, "get", boom)
    d = _ha_test(m)
    assert d["error"] == "unreachable" and "geheim" not in str(d)


def test_ha_test_names_missing_part(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    m = _load(tmp_path, monkeypatch)
    monkeypatch.setattr(m, "SUPERVISOR_TOKEN", "")
    for cfg, code in (({"ha_url": "ha.example.de", "ha_token": "t"}, "bad_url"),
                      ({"ha_url": "https://ha.example.de"}, "no_token"),
                      ({"ha_token": "t"}, "no_url")):
        monkeypatch.setattr(m, "load_config", lambda c=cfg: dict(c))
        assert _ha_test(m)["error"] == code
