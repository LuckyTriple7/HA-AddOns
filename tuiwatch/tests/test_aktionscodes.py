"""Tests für die öffentliche TUI-Aktionscode-Überwachung (ohne Netz/Browser).

- `parse_aktionscodes` (rein) direkt.
- Speicher/Dedup/Wiederkehr + Mindestwert über `_run_aktionscodes` mit gemocktem
  `fetch_aktionscodes`.
"""
import importlib

import pytest

from aktionscodes import parse_aktionscodes

_HTML = ("<p>Jetzt mit Code ACMYTUI30020260702 oder ACMYTUI15020260702 sparen, "
         "ohne Konto SAVE250 bzw. SAVE125. "
         "Aktionszeitraum 02.07. bis 07.07.2026; "
         "Reisezeitraum vom 02.07. bis 23.12.2026 (letzter Anreisetermin 20.12.2026)</p>")


def test_parse_aktionscodes():
    p = parse_aktionscodes(_HTML)
    assert [c["value"] for c in p["codes"]] == [300, 250, 150, 125]
    kinds = {c["value"]: c["kind"] for c in p["codes"]}
    assert kinds[300] == "myTUI" and kinds[125] == "ohne Konto"
    assert p["booking_until"] == "07.07.2026"
    assert p["travel_period"].startswith("02.07.") and "23.12.2026" in p["travel_period"]


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
    m.TRIPS_DIR = str(tmp_path / "trips")
    m._DATA = str(tmp_path)
    m.init_db()
    return m


def _mock(m, monkeypatch, codes, cfg=None, sink=None):
    s = sink if sink is not None else []
    monkeypatch.setattr(m, "load_config", lambda: cfg or {"notify_aktionscodes": True})
    monkeypatch.setattr(m, "_notify_ha", lambda *a, **k: s.append("ha"))
    monkeypatch.setattr(m, "_notify_telegram", lambda t: s.append("tg"))
    monkeypatch.setattr(m, "fetch_aktionscodes", lambda **k: {
        "ok": True, "codes": codes["v"], "booking_until": "07.07.2026",
        "travel_period": "02.07.–23.12.2026"})


def test_dedup_and_reappear(app_mod, monkeypatch):
    m = app_mod
    sent = []
    codes = {"v": [{"code": "ACMYTUI30020260702", "value": 300, "kind": "myTUI"},
                   {"code": "SAVE125", "value": 125, "kind": "ohne Konto"}]}
    _mock(m, monkeypatch, codes, sink=sent)

    m._run_aktionscodes()                       # beide neu → eine Sammel-Meldung
    assert sent.count("ha") == 1
    pay = m._aktionscodes_payload()
    assert len(pay["codes"]) == 2 and pay["booking_until"] == "07.07.2026"

    sent.clear()
    m._run_aktionscodes()                       # nichts neu (gleiche Codes)
    assert sent == []

    # 300er verschwindet → wird inaktiv; 125 bleibt (kein neuer)
    codes["v"] = [{"code": "SAVE125", "value": 125, "kind": "ohne Konto"}]
    sent.clear()
    m._run_aktionscodes()
    assert sent == []

    # 300er kommt zurück (mit neuem Datum im Code) → erneut melden
    codes["v"] = [{"code": "ACMYTUI30020260815", "value": 300, "kind": "myTUI"},
                  {"code": "SAVE125", "value": 125, "kind": "ohne Konto"}]
    sent.clear()
    m._run_aktionscodes()
    assert sent.count("ha") == 1


def test_min_filter(app_mod, monkeypatch):
    m = app_mod
    sent = []
    codes = {"v": [{"code": "ACMYTUI30020260702", "value": 300, "kind": "myTUI"},
                   {"code": "SAVE125", "value": 125, "kind": "ohne Konto"}]}
    _mock(m, monkeypatch, codes, cfg={"notify_aktionscodes": True, "aktionscode_min": 250}, sink=sent)
    m._run_aktionscodes()
    assert [c["value"] for c in m._aktionscodes_payload()["codes"]] == [300]   # 125 gefiltert


def test_ha_binary_sensor(app_mod, monkeypatch):
    """Bei aktivem ha_sensors + SUPERVISOR_TOKEN wird ein Binär-Sensor gemeldet:
    'on' mit Codes in den Attributen, 'off' + leere Liste sobald keine mehr da sind."""
    m = app_mod
    monkeypatch.setattr(m, "SUPERVISOR_TOKEN", "testtoken")
    calls = []
    monkeypatch.setattr(m.http, "post",
                        lambda url, **kw: calls.append((url, kw.get("json"))))
    codes = {"v": [{"code": "ACMYTUI30020260702", "value": 300, "kind": "myTUI"}]}
    _mock(m, monkeypatch, codes, cfg={"notify_aktionscodes": True, "ha_sensors": True})

    m._run_aktionscodes()
    url, payload = next(c for c in calls if "aktionscodes" in c[0])
    assert url.endswith("/states/binary_sensor.tuiwatch_aktionscodes")
    assert payload["state"] == "on"
    assert payload["attributes"]["count"] == 1
    assert payload["attributes"]["coupons"] == [
        {"code": "ACMYTUI30020260702", "value": 300, "kind": "myTUI"}]
    assert payload["attributes"]["booking_until"] == "07.07.2026"

    calls.clear()
    codes["v"] = []
    m._run_aktionscodes()
    url, payload = next(c for c in calls if "aktionscodes" in c[0])
    assert payload["state"] == "off"
    assert payload["attributes"]["coupons"] == []


def test_endpoint(app_mod, monkeypatch):
    m = app_mod
    codes = {"v": [{"code": "ACMYTUI30020260702", "value": 300, "kind": "myTUI"}]}
    _mock(m, monkeypatch, codes)
    c = m.app.test_client()
    ing = {"X-Ingress-Path": "/test"}
    assert c.get("/api/aktionscodes", headers=ing).status_code == 200
    assert c.get("/api/aktionscodes").status_code == 401     # ohne Ingress: Auth nötig
