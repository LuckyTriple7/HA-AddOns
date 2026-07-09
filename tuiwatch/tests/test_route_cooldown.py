"""Tests für `_cooldown_remaining()` und dessen Einsatz auf den scraping-lastigen
Routen (/api/check-now, /api/search, /api/searches/<id>/check) — schützt TUIs
Server vor wiederholtem Klicken/Skript-Aufrufen, die die eigene IP dort blocken
könnten. Kein Netzzugriff nötig (check_all/fetch_search werden nicht erreicht,
der Cooldown greift schon davor)."""
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


def test_cooldown_remaining_blocks_within_window(m):
    assert m._cooldown_remaining("k", 60) == 0          # erster Aufruf: frei
    assert m._cooldown_remaining("k", 60) > 0            # sofort danach: blockiert
    assert m._cooldown_remaining("other-key", 60) == 0   # anderer Key: unabhängig


def test_check_now_returns_429_on_repeat_call(m, monkeypatch):
    spawned = []
    monkeypatch.setattr(m, "_spawn", lambda fn, *a: spawned.append((fn, a)))
    c = m.app.test_client()
    r1 = c.post("/api/check-now", headers=ING)
    assert r1.status_code == 200 and len(spawned) == 1
    r2 = c.post("/api/check-now", headers=ING)
    assert r2.status_code == 429
    assert r2.get_json()["retry_after"] > 0
    assert len(spawned) == 1   # zweiter Aufruf hat check_all nicht erneut gestartet


def test_searches_check_cooldown_is_per_search(m, monkeypatch):
    c = m.app.test_client()
    payload = {"dest": {"giata": 123, "label": "Kanaren"}, "airport": "DUS",
               "vom": "2027-03-01", "bis": "2027-03-15", "dur": 7, "exact": False,
               "trav": 2, "tui": True, "direct": False, "boards": [],
               "location": [], "airlines": [], "stars": 0, "rec": 0}
    sid1 = c.post("/api/searches", headers=ING, json={"name": "A", "payload": payload}).get_json()["id"]
    sid2 = c.post("/api/searches", headers=ING, json={"name": "B", "payload": payload}).get_json()["id"]
    for sid in (sid1, sid2):
        c.patch(f"/api/searches/{sid}", headers=ING, json={"watch": True, "max_price": 500})
    monkeypatch.setattr(m, "_check_search_watch", lambda sid: {"hits": [], "new": 0})
    assert c.post(f"/api/searches/{sid1}/check", headers=ING).status_code == 200
    assert c.post(f"/api/searches/{sid1}/check", headers=ING).status_code == 429
    # anderes Suchabo: eigener Cooldown, nicht vom ersten betroffen
    assert c.post(f"/api/searches/{sid2}/check", headers=ING).status_code == 200
