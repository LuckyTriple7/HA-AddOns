"""Tests für das verzögerte Tracking-Start (start:false) beim Hinzufügen eines
Angebots aus der Suche — POST /api/offers mit start:false legt das Angebot an,
ohne sofort check_offer zu spawnen; erst POST /api/offers/<id>/start (oder die
Zimmerauswahl POST /api/rooms/<id>) startet die erste Prüfung. Verhindert, dass
ein u.U. falsches Zimmer aus dem Suchergebnis getrackt wird, bevor der Nutzer im
Zimmerauswahl-Dialog wählen konnte."""
import importlib

import pytest

pytest.importorskip("flask")

ING = {"X-Ingress-Path": "/test"}
URL = "https://www.tui.com/x/1/offer/?duration=7"


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


def test_add_offer_defaults_to_immediate_start(m, monkeypatch):
    spawned = []
    monkeypatch.setattr(m, "_spawn", lambda fn, *a: spawned.append((fn, a)))
    c = m.app.test_client()
    r = c.post("/api/offers", json={"url": URL}, headers=ING)
    assert r.status_code == 200
    assert r.get_json()["started"] is True
    assert len(spawned) == 1 and spawned[0][0] is m.check_offer


def test_add_offer_start_false_does_not_spawn_check(m, monkeypatch):
    spawned = []
    monkeypatch.setattr(m, "_spawn", lambda fn, *a: spawned.append((fn, a)))
    c = m.app.test_client()
    r = c.post("/api/offers", json={"url": URL, "start": False}, headers=ING)
    assert r.status_code == 200
    d = r.get_json()
    assert d["started"] is False
    assert spawned == []
    oid = d["id"]
    with m.db() as con:
        row = con.execute("SELECT COUNT(*) c FROM price_history WHERE offer_id=?", (oid,)).fetchone()
    assert row["c"] == 0   # wirklich nicht geprüft


def test_start_route_spawns_check_for_pending_offer(m, monkeypatch):
    spawned = []
    monkeypatch.setattr(m, "_spawn", lambda fn, *a: spawned.append((fn, a)))
    c = m.app.test_client()
    r = c.post("/api/offers", json={"url": URL, "start": False}, headers=ING)
    oid = r.get_json()["id"]
    assert spawned == []

    r2 = c.post(f"/api/offers/{oid}/start", headers=ING)
    assert r2.status_code == 200 and r2.get_json()["started"] is True
    assert len(spawned) == 1 and spawned[0] == (m.check_offer, (oid,))


def test_start_route_404_for_unknown_offer(m):
    c = m.app.test_client()
    r = c.post("/api/offers/9999/start", headers=ING)
    assert r.status_code == 404


def test_rooms_set_spawns_check_for_pending_offer(m, monkeypatch):
    spawned = []
    monkeypatch.setattr(m, "_spawn", lambda fn, *a: spawned.append((fn, a)))
    c = m.app.test_client()
    r = c.post("/api/offers", json={"url": URL, "start": False}, headers=ING)
    oid = r.get_json()["id"]
    assert spawned == []

    r2 = c.post(f"/api/rooms/{oid}", json={"code": "", "label": ""}, headers=ING)
    assert r2.status_code == 200 and r2.get_json()["started"] is True
    assert len(spawned) == 1 and spawned[0] == (m.check_offer, (oid,))
