"""Automatischer Zimmerwechsel: günstigstes Zimmer ausgebucht → nächstteureres.

Ein Angebot ohne fixiertes Zimmer verfolgt immer das günstigste. Ist das weg,
springt der Preis, ohne dass sich am Markt etwas bewegt hat. Der Wechsel wird als
`offer_events`-Eintrag (type='room_auto') am Zeitstempel des Messpunkts festgehalten —
daraus baut das Frontend die Hinweiszeile im Verlauf — und der Preisschritt bleibt
aus dem Markttrend (`price_moves`) heraus.
"""
import importlib
import time

import pytest

pytest.importorskip("flask")


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
    mod.TRIPS_DIR = str(tmp_path / "trips")
    mod.init_db()
    monkeypatch.setattr(mod, "_notify_ha", lambda *a, **k: None)
    monkeypatch.setattr(mod, "_notify_telegram", lambda *a, **k: None)
    monkeypatch.setattr(mod, "fetch_hotel_image", lambda url, **k: "")
    monkeypatch.setattr(mod, "fetch_calendar", lambda *a, **k: None)
    return mod


def _add_offer(m, url="https://example.invalid/r?duration=7"):
    with m.db() as con:
        cur = con.execute("INSERT INTO offers (url, hotel, created) VALUES (?,?,?)",
                          (url, "Myrina Beach", int(time.time())))
        return cur.lastrowid


def _events(m, oid, type_="room_auto"):
    with m.db() as con:
        return [r["text"] for r in con.execute(
            "SELECT text FROM offer_events WHERE offer_id=? AND type=? ORDER BY ts",
            (oid, type_)).fetchall()]


# ── Reine Erkennung ────────────────────────────────────────────────────────────

def test_detects_changed_room(m):
    txt = m._room_change_text({"room": "Doppelzimmer"},
                              {"ok": True, "room": "Executive Double room side sea view"})
    assert txt == "Zimmer gewechselt: Doppelzimmer → Executive Double room side sea view"


def test_no_event_without_real_change(m):
    same = {"ok": True, "room": "Doppelzimmer"}
    assert m._room_change_text({"room": "Doppelzimmer"}, same) == ""
    assert m._room_change_text({"room": " Doppelzimmer "}, same) == ""   # nur Leerraum
    # Erstbefüllung (vorher nichts gespeichert) meldet nicht
    assert m._room_change_text({"room": ""}, same) == ""
    assert m._room_change_text({}, same) == ""
    # Abruf ohne Zimmerangabe oder fehlgeschlagen ebenfalls nicht
    assert m._room_change_text({"room": "Doppelzimmer"}, {"ok": True, "room": ""}) == ""
    assert m._room_change_text({"room": "Doppelzimmer"},
                               {"ok": False, "room": "Suite"}) == ""


# ── Zusammenspiel mit check_offer ──────────────────────────────────────────────

def test_check_offer_logs_room_switch_at_measurement_ts(m, monkeypatch):
    oid = _add_offer(m)
    monkeypatch.setattr(m, "fetch_price", lambda url, **k: {
        "ok": True, "price": 1759, "room": "Doppelzimmer", "region": "Griechenland"})
    m.check_offer(oid)
    assert _events(m, oid) == []          # Erstbefüllung ist still

    monkeypatch.setattr(m, "fetch_price", lambda url, **k: {
        "ok": True, "price": 2221, "room": "Executive Double room side sea view",
        "region": "Griechenland"})
    m.check_offer(oid)

    assert _events(m, oid) == [
        "Zimmer gewechselt: Doppelzimmer → Executive Double room side sea view"]
    with m.db() as con:
        ev_ts = con.execute("SELECT ts FROM offer_events WHERE offer_id=?", (oid,)).fetchone()["ts"]
        last_ts = con.execute("SELECT MAX(ts) AS t FROM price_history WHERE offer_id=?",
                              (oid,)).fetchone()["t"]
        room = con.execute("SELECT room FROM offers WHERE id=?", (oid,)).fetchone()["room"]
    # Ereignis hängt exakt am Messpunkt — sonst ordnete die Verlaufstabelle den
    # Hinweis dem nächsten (späteren) Preis zu.
    assert ev_ts == last_ts
    assert room == "Executive Double room side sea view"


def test_room_switch_keeps_price_jump_out_of_market_trend(m, monkeypatch):
    oid = _add_offer(m)
    monkeypatch.setattr(m, "fetch_price", lambda url, **k: {
        "ok": True, "price": 1759, "room": "Doppelzimmer",
        "region": "Griechenland", "country": "Griechenland", "return_date": "2026-10-28"})
    m.check_offer(oid)
    monkeypatch.setattr(m, "fetch_price", lambda url, **k: {
        "ok": True, "price": 2221, "room": "Executive Double room side sea view",
        "region": "Griechenland", "country": "Griechenland", "return_date": "2026-10-28"})
    m.check_offer(oid)
    with m.db() as con:
        moves = con.execute("SELECT COUNT(*) AS n FROM price_moves").fetchone()["n"]
    assert moves == 0        # +26 % waren nur ein anderer Zimmertyp

    # Der nächste Check im selben Zimmer zählt wieder normal mit
    monkeypatch.setattr(m, "fetch_price", lambda url, **k: {
        "ok": True, "price": 2300, "room": "Executive Double room side sea view",
        "region": "Griechenland", "country": "Griechenland", "return_date": "2026-10-28"})
    m.check_offer(oid)
    with m.db() as con:
        moves = con.execute("SELECT COUNT(*) AS n FROM price_moves").fetchone()["n"]
    assert moves == 1


def test_history_api_delivers_event_for_the_table(m, monkeypatch):
    """Die Hinweiszeile im Verlauf baut das Frontend aus `events` — die Route muss
    den Zimmerwechsel also mitliefern."""
    oid = _add_offer(m)
    monkeypatch.setattr(m, "fetch_price", lambda url, **k: {
        "ok": True, "price": 1759, "room": "Doppelzimmer"})
    m.check_offer(oid)
    monkeypatch.setattr(m, "fetch_price", lambda url, **k: {
        "ok": True, "price": 2221, "room": "Suite"})
    m.check_offer(oid)

    m.app.config["TESTING"] = True
    monkeypatch.setattr(m, "_require_api", lambda: None)
    with m.app.test_client() as c:
        data = c.get(f"/api/history/{oid}").get_json()
    rooms = [e for e in data["events"] if e["type"] == "room_auto"]
    assert len(rooms) == 1 and rooms[0]["text"].endswith("→ Suite")
    # Zuordnung im Frontend: jüngster Messpunkt, der nicht nach dem Ereignis liegt
    # — hier der zweite (gleicher Zeitstempel), also die Zeile mit dem Preissprung.
    hist = data["history"]
    assert hist[0]["ts"] <= rooms[0]["ts"] == hist[1]["ts"]
