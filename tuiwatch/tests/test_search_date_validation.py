"""Tests fuer die Datums-Validierung in POST /api/search (region-Modus): TUIs
Such-API antwortet auf Zeitraeume in der Vergangenheit mit einem nichtssagenden
HTTP 500 statt einem sauberen Fehler -- wird jetzt vorher serverseitig abgefangen,
kein Netzzugriff noetig (`fetch_search_params` darf dafuer gar nicht erst
aufgerufen werden)."""
import importlib

import pytest

pytest.importorskip("flask")

ING = {"X-Ingress-Path": "/test"}


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


def _search_calls(m, monkeypatch):
    calls = []
    monkeypatch.setattr(m, "fetch_search_params",
                        lambda **kw: (calls.append(kw), {"ok": True, "total": 0, "results": []})[1])
    return calls


def test_rejects_past_start_date(m, monkeypatch):
    calls = _search_calls(m, monkeypatch)
    c = m.app.test_client()
    r = c.post("/api/search", headers=ING,
              json={"region": 735, "start": "2020-01-01", "end": "2020-01-08", "duration": 7})
    assert r.status_code == 400
    assert r.get_json()["error"] == "past_date"
    assert calls == []   # kein unnötiger Aufruf an TUI


def test_rejects_end_before_start(m, monkeypatch):
    calls = _search_calls(m, monkeypatch)
    c = m.app.test_client()
    r = c.post("/api/search", headers=ING,
              json={"region": 735, "start": "2027-08-10", "end": "2027-08-01", "duration": 7})
    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid_dates"
    assert calls == []


def test_rejects_malformed_date(m, monkeypatch):
    calls = _search_calls(m, monkeypatch)
    c = m.app.test_client()
    r = c.post("/api/search", headers=ING,
              json={"region": 735, "start": "nicht-valide", "end": "2027-08-08"})
    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid_dates"
    assert calls == []


def test_accepts_future_dates(m, monkeypatch):
    calls = _search_calls(m, monkeypatch)
    c = m.app.test_client()
    r = c.post("/api/search", headers=ING,
              json={"region": 735, "start": "2027-08-01", "end": "2027-08-08", "duration": 7})
    assert r.status_code == 200
    assert len(calls) == 1


def test_accepts_missing_dates(m, monkeypatch):
    """Kein Zeitraum angegeben (z.B. andere Suchmodi) -- Validierung greift nur,
    wenn ueberhaupt ein Datum gesetzt ist."""
    calls = _search_calls(m, monkeypatch)
    c = m.app.test_client()
    r = c.post("/api/search", headers=ING, json={"region": 735})
    assert r.status_code == 200
    assert len(calls) == 1


def test_offset_passed_through_for_load_more(m, monkeypatch):
    """"Mehr laden" schickt offset=bereits geladene Treffer mit -- muss bis zu
    fetch_search_params() durchgereicht werden (resultsFrom serverseitig)."""
    calls = _search_calls(m, monkeypatch)
    c = m.app.test_client()
    r = c.post("/api/search", headers=ING,
              json={"region": 735, "start": "2027-08-01", "end": "2027-08-08",
                    "duration": 7, "offset": 50})
    assert r.status_code == 200
    assert calls[0]["offset"] == 50


def test_offset_missing_defaults_to_zero(m, monkeypatch):
    calls = _search_calls(m, monkeypatch)
    c = m.app.test_client()
    c.post("/api/search", headers=ING, json={"region": 735})
    assert calls[0]["offset"] == 0


def test_offset_negative_clamped_to_zero(m, monkeypatch):
    calls = _search_calls(m, monkeypatch)
    c = m.app.test_client()
    c.post("/api/search", headers=ING, json={"region": 735, "offset": -5})
    assert calls[0]["offset"] == 0


def test_offset_non_numeric_defaults_to_zero(m, monkeypatch):
    calls = _search_calls(m, monkeypatch)
    c = m.app.test_client()
    c.post("/api/search", headers=ING, json={"region": 735, "offset": "abc"})
    assert calls[0]["offset"] == 0
