"""Tests fuer die Datenbank-Wartung (Backlog #18/#19): Verlauf verdichten und
Speicherplatz zurueckgeben.

Der heikle Teil ist das Verdichten — es loescht Zeilen. Die Tests halten fest,
dass genau die Kennzahlen erhalten bleiben, die die Oberflaeche anzeigt
(niedrigster/hoechster Preis, Preisverlauf, Kalender-Bewegung, Vorjahreswert),
dass junge Daten nie angefasst werden und dass ohne Einstellung nichts passiert.
"""
import importlib
import time
from datetime import date, timedelta

import pytest

pytest.importorskip("flask")

ING = {"X-Ingress-Path": "/test"}
TAG = 86400


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


@pytest.fixture
def mt(m):
    return importlib.import_module("maintenance")


def _offer(m, url="https://example.invalid/wartung"):
    with m.db() as con:
        return con.execute("INSERT INTO offers (url, hotel, created) VALUES (?,?,?)",
                           (url, "Test-Hotel", int(time.time()))).lastrowid


def _preise(m, oid, rows):
    """rows: [(ts, price)] — direkt in price_history."""
    with m.db() as con:
        con.executemany(
            "INSERT INTO price_history (offer_id, ts, price, ok, available) "
            "VALUES (?,?,?,1,1)", [(oid, ts, p) for ts, p in rows])


def _alt(tage: int, stunde: int = 12) -> int:
    """Zeitstempel vor `tage` Tagen, zur angegebenen Stunde (Ortszeit)."""
    t = time.localtime(time.time() - tage * TAG)
    return int(time.mktime((t.tm_year, t.tm_mon, t.tm_mday, stunde, 0, 0, 0, 0, -1)))


def _rows(m, tabelle, oid):
    with m.db() as con:
        return con.execute(f"SELECT COUNT(*) c FROM {tabelle} WHERE offer_id=?",
                           (oid,)).fetchone()["c"]


# ── Preisverlauf ───────────────────────────────────────────────────────────────

def test_verdichten_behaelt_erste_letzte_guenstigste_teuerste(m, mt):
    """Der Kern: die Kennzahlen der Angebotskarte duerfen sich nicht aendern."""
    oid = _offer(m)
    tag = [(_alt(400, h), p) for h, p in
           [(6, 900), (9, 850), (12, 1100), (15, 990), (18, 870), (21, 950)]]
    _preise(m, oid, tag)
    vorher = next(o for o in m._collect_offers() if o["id"] == oid)
    with m.db() as con:
        mt.compact_history(con, 12)
    m._stats_cache_drop()
    nachher = next(o for o in m._collect_offers() if o["id"] == oid)
    assert _rows(m, "price_history", oid) == 4          # erste, letzte, min, max
    for feld in ("min_price", "max_price", "price"):
        assert vorher[feld] == nachher[feld], feld


def test_verdichten_laesst_junge_zeilen_in_ruhe(m, mt):
    oid = _offer(m)
    _preise(m, oid, [(_alt(5, h), 900 + h) for h in range(6, 22, 3)])
    with m.db() as con:
        mt.compact_history(con, 12)
    assert _rows(m, "price_history", oid) == 6


def test_verdichten_ruehrt_fehlversuche_nicht_an(m, mt):
    """Fehlgeschlagene Abrufe (ok=0) speisen die Stoerungsliste."""
    oid = _offer(m)
    with m.db() as con:
        con.executemany(
            "INSERT INTO price_history (offer_id, ts, price, ok, available) VALUES (?,?,?,0,0)",
            [(oid, _alt(400, h), None) for h in range(0, 24, 2)])
        mt.compact_history(con, 12)
    assert _rows(m, "price_history", oid) == 12


def test_vorschau_loescht_nichts(m, mt):
    oid = _offer(m)
    _preise(m, oid, [(_alt(400, h), 900 + h) for h in range(0, 24, 2)])
    with m.db() as con:
        res = mt.compact_history(con, 12, dry_run=True)
    assert res["price_history"] > 0 and res["dry_run"] is True
    assert _rows(m, "price_history", oid) == 12


# ── Kalenderhistorie ───────────────────────────────────────────────────────────

def test_kalender_behaelt_baseline_juengste_und_wochenstand(m, mt):
    """Ohne die Baseline zaehlte `_calendar_moves` den Reisetag nicht mehr als
    bewegt; ohne die juengste Zeile faende der Vorjahresvergleich nichts."""
    oid = _offer(m)
    reisetag = "2027-05-01"
    with m.db() as con:
        con.executemany(
            "INSERT INTO calendar_history (offer_id, travel_date, ts, price) VALUES (?,?,?,?)",
            [(oid, reisetag, _alt(400 - i), 800 + i) for i in range(0, 30, 2)])
        vorher = m._calendar_moves(con, oid)[reisetag]
        mt.compact_history(con, 12)
        rows = con.execute("SELECT ts, price FROM calendar_history WHERE offer_id=? "
                           "ORDER BY ts", (oid,)).fetchall()
        nachher = m._calendar_moves(con, oid)[reisetag]
    assert 2 <= len(rows) < 15                       # ausgeduennt, nicht geleert
    assert rows[0]["price"] == 800                   # Baseline steht
    assert nachher["price"] == vorher["price"]       # juengster Preis unveraendert


def test_kalender_verdichtet_je_reisetag_getrennt(m, mt):
    oid = _offer(m)
    with m.db() as con:
        con.executemany(
            "INSERT INTO calendar_history (offer_id, travel_date, ts, price) VALUES (?,?,?,?)",
            [(oid, d, _alt(400 - i), 700 + i)
             for d in ("2027-05-01", "2027-05-02") for i in range(0, 30, 2)])
        mt.compact_history(con, 12)
        je_tag = {r["travel_date"]: r["c"] for r in con.execute(
            "SELECT travel_date, COUNT(*) c FROM calendar_history WHERE offer_id=? "
            "GROUP BY travel_date", (oid,)).fetchall()}
    assert set(je_tag) == {"2027-05-01", "2027-05-02"}
    assert all(2 <= c < 15 for c in je_tag.values())


# ── Einstellung und Routen ─────────────────────────────────────────────────────

def test_ohne_einstellung_passiert_nichts(m, mt, monkeypatch):
    """Voreinstellung ist aus — Verlaufsdaten wegzuwerfen ist nichts, was
    ungefragt passieren darf."""
    monkeypatch.setattr(m, "load_config", lambda: {})
    assert mt._configured_months() == 0
    monkeypatch.setattr(m, "load_config", lambda: {"history_compact_months": 2})
    assert mt._configured_months() == 0          # unter dem Minimum -> aus
    monkeypatch.setattr(m, "load_config", lambda: {"history_compact_months": 12})
    assert mt._configured_months() == 12


def test_route_verdichtet_nur_mit_apply(m, mt):
    oid = _offer(m)
    _preise(m, oid, [(_alt(400, h), 900 + h) for h in range(0, 24, 2)])
    c = m.app.test_client()
    vor = c.post("/api/db/compact", json={"months": 12}, headers=ING).get_json()
    assert vor["dry_run"] is True and _rows(m, "price_history", oid) == 12
    nach = c.post("/api/db/compact", json={"months": 12, "apply": True},
                  headers=ING).get_json()
    assert nach["dry_run"] is False
    # Hier steigen die Preise monoton: die guenstigste Messung IST die erste, die
    # teuerste die letzte — es bleiben also zwei Zeilen, nicht vier.
    assert _rows(m, "price_history", oid) == 2


def test_route_lehnt_zu_kleine_grenze_ab(m, mt):
    r = m.app.test_client().post("/api/db/compact", json={"months": 1}, headers=ING)
    assert r.status_code == 400 and r.get_json()["error"] == "too_small"


def test_stats_route_nennt_groesse_und_zeilen(m, mt):
    oid = _offer(m)
    _preise(m, oid, [(_alt(3), 900)])
    d = m.app.test_client().get("/api/db/stats", headers=ING).get_json()
    assert d["bytes"] > 0
    assert d["rows"]["price_history"] == 1
    assert "reclaimable" in d and d["compact_months"] == 0


def test_vacuum_gibt_platz_zurueck(m, mt):
    """Nach dem Loeschen vieler Zeilen schrumpft die Datei erst durch VACUUM."""
    oid = _offer(m)
    _preise(m, oid, [(_alt(400) + i, 900 + (i % 50)) for i in range(20000)])
    with m.db() as con:
        con.execute("DELETE FROM price_history WHERE offer_id=?", (oid,))
    vorher = m.db_file_size()
    res = mt.vacuum()
    assert res["after"] < vorher
    assert res["freed"] > 0
