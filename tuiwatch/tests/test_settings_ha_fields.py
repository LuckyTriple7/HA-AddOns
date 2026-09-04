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
