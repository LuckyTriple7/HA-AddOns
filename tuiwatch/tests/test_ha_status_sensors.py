"""Tests für die beiden Status-Binär-Sensoren `binary_sensor.tuiwatch_api_available`
und `binary_sensor.tuiwatch_cooldown_active` (kein Netz/Browser nötig)."""
import importlib

import pytest


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
    mod.SUPERVISOR_TOKEN = "testtoken"
    monkeypatch.setattr(mod, "load_config", lambda: {"ha_sensors": True})
    return mod


def _capture(m, monkeypatch):
    calls = []
    monkeypatch.setattr(m.http, "post",
                        lambda url, **kw: calls.append((url, kw.get("json"))))
    return calls


def test_health_sensor_on_when_all_critical_ok(m, monkeypatch):
    calls = _capture(m, monkeypatch)
    monkeypatch.setattr(m, "api_healthcheck", lambda **k: {
        "ok": True, "ts": 1000,
        "checks": [{"name": "Preis/Angebot-API", "ok": True, "critical": True}]})
    monkeypatch.setattr(m, "_check_api_alarm", lambda res: None)

    m._run_healthcheck()

    url, payload = next(c for c in calls if "api_available" in c[0])
    assert url.endswith("/states/binary_sensor.tuiwatch_api_available")
    assert payload["state"] == "on"
    assert payload["attributes"]["failing"] == []


def test_health_sensor_off_when_critical_endpoint_down(m, monkeypatch):
    calls = _capture(m, monkeypatch)
    monkeypatch.setattr(m, "api_healthcheck", lambda **k: {
        "ok": False, "ts": 1000,
        "checks": [{"name": "Preis/Angebot-API", "ok": False, "critical": True},
                   {"name": "Abflughäfen-API", "ok": True, "critical": False}]})
    monkeypatch.setattr(m, "_check_api_alarm", lambda res: None)

    m._run_healthcheck()

    url, payload = next(c for c in calls if "api_available" in c[0])
    assert payload["state"] == "off"
    assert payload["attributes"]["failing"] == ["Preis/Angebot-API"]


def test_health_sensor_survives_restart_from_cache(m, monkeypatch):
    monkeypatch.setattr(m, "api_healthcheck", lambda **k: {
        "ok": True, "ts": 1000,
        "checks": [{"name": "Preis/Angebot-API", "ok": True, "critical": True}]})
    monkeypatch.setattr(m, "_check_api_alarm", lambda res: None)
    m._run_healthcheck()

    calls = _capture(m, monkeypatch)
    m._push_health_sensor_from_cache()
    url, payload = next(c for c in calls if "api_available" in c[0])
    assert payload["state"] == "on"


def test_cooldown_sensor_on_while_active_off_after_expiry(m, monkeypatch):
    calls = _capture(m, monkeypatch)
    m._route_cooldowns["check_now"] = 1000.0
    monkeypatch.setattr(m.time, "time", lambda: 1010.0)   # 10s nach Auslösung, <60s

    m._push_cooldown_sensor()
    url, payload = next(c for c in calls if "cooldown_active" in c[0])
    assert url.endswith("/states/binary_sensor.tuiwatch_cooldown_active")
    assert payload["state"] == "on"
    assert payload["attributes"]["retry_after"] > 0

    calls.clear()
    monkeypatch.setattr(m.time, "time", lambda: 1070.0)   # 70s später: abgelaufen
    m._push_cooldown_sensor()
    url, payload = next(c for c in calls if "cooldown_active" in c[0])
    assert payload["state"] == "off"
    assert payload["attributes"]["retry_after"] == 0


def test_cooldown_peek_does_not_consume(m):
    assert m._cooldown_peek("x", 60) == 0        # nichts ausgelöst → frei, kein Setzen
    assert m._cooldown_peek("x", 60) == 0         # bleibt frei, da _peek nicht setzt
    m._cooldown_remaining("x", 60)                # jetzt real auslösen
    assert m._cooldown_peek("x", 60) > 0          # peek sieht aktiven Cooldown
    assert m._cooldown_peek("x", 60) > 0          # peek konsumiert ihn nicht erneut
