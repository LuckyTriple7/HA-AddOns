"""Tests fuer die Robustheits-Fixes aus dem Code-Review: _json_loads_safe()
(kaputtes JSON in DB-Feldern crasht Endpunkte nicht mehr) und die neue
Zimmercode-Validierung in POST /api/rooms/<id>."""
import importlib
import time

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


def _add_offer(m, url="https://www.tui.com/x/1/offer/?duration=7"):
    with m.db() as con:
        cur = con.execute(
            "INSERT INTO offers (url, hotel, created) VALUES (?,?,?)",
            (url, "Test-Hotel", int(time.time())))
        return cur.lastrowid


# ── _json_loads_safe ──────────────────────────────────────────────────────────

def test_json_loads_safe_returns_default_on_garbage(m):
    assert m._json_loads_safe("{kaputt", []) == []
    assert m._json_loads_safe("{kaputt", {}) == {}


def test_json_loads_safe_parses_valid_json(m):
    assert m._json_loads_safe('{"a": 1}', {}) == {"a": 1}


def test_calendar_payload_survives_corrupted_cache_row(m):
    oid = _add_offer(m)
    with m.db() as con:
        con.execute("INSERT INTO calendar_cache (offer_id, ts, data) VALUES (?,?,?)",
                   (oid, int(time.time()), "{nicht valides json"))
    out = m._calendar_payload(oid)
    assert out["status"] == "done"   # kein Crash, sinnvoller Fallback statt Exception


def test_offers_list_survives_corrupted_tags(m):
    oid = _add_offer(m)
    with m.db() as con:
        con.execute("UPDATE offers SET tags=? WHERE id=?", ("{kaputt", oid))
    c = m.app.test_client()
    r = c.get("/api/offers", headers=ING)
    assert r.status_code == 200
    offer = next(o for o in r.get_json()["offers"] if o["id"] == oid)
    assert offer["tags"] == []


# ── Zimmercode-Validierung ───────────────────────────────────────────────────

def test_rooms_set_rejects_invalid_code(m):
    oid = _add_offer(m)
    c = m.app.test_client()
    r = c.post(f"/api/rooms/{oid}", headers=ING, json={"code": "'; DROP TABLE offers;--"})
    assert r.status_code == 400 and r.get_json()["error"] == "invalid_code"
    with m.db() as con:
        assert con.execute("SELECT url FROM offers WHERE id=?", (oid,)).fetchone() is not None


def test_rooms_set_accepts_valid_code(m, monkeypatch):
    monkeypatch.setattr(m, "_spawn", lambda fn, *a: None)
    oid = _add_offer(m)
    c = m.app.test_client()
    r = c.post(f"/api/rooms/{oid}", headers=ING, json={"code": "DZM1", "label": "Doppelzimmer"})
    assert r.status_code == 200
    with m.db() as con:
        url = con.execute("SELECT url FROM offers WHERE id=?", (oid,)).fetchone()["url"]
    assert "roomTypeOpCodes=DZM1" in url


def test_rooms_set_accepts_empty_code(m, monkeypatch):
    monkeypatch.setattr(m, "_spawn", lambda fn, *a: None)
    oid = _add_offer(m)
    c = m.app.test_client()
    r = c.post(f"/api/rooms/{oid}", headers=ING, json={"code": ""})
    assert r.status_code == 200
