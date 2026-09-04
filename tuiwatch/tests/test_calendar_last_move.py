"""Tests für `_calendar_last_move_ts`: ein Query für ALLE Angebote statt eines
`_calendar_moves()` je Angebot in `_collect_offers`.

`/api/offers` wird von jedem offenen Browser alle 5 s geholt und brauchte davon
nur `max(ts)` — holte dafür aber sämtliche `calendar_history`-Zeilen jedes
Angebots nach Python. Die Tests halten fest, dass die neue Abfrage exakt dasselbe
Ergebnis liefert und das `calendar_alert`-Flag unverändert funktioniert.
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
    mod.init_db()
    return mod


def _add_offer(m, url, return_date="2027-03-15"):
    now = int(time.time())
    with m.db() as con:
        con.execute(
            "INSERT INTO offers (url, hotel, region, country, return_date, created) "
            "VALUES (?,?,?,?,?,?)",
            (url, "Test-Hotel", "Kanaren", "Spanien", return_date, now))
        return con.execute("SELECT id FROM offers WHERE url=?", (url,)).fetchone()["id"]


def _hist(con, offer_id, rows):
    """rows: [(travel_date, ts, price), …] — direkt in calendar_history."""
    con.executemany(
        "INSERT INTO calendar_history (offer_id, travel_date, ts, price) VALUES (?,?,?,?)",
        [(offer_id, d, ts, p) for d, ts, p in rows])


def test_gleiches_ergebnis_wie_calendar_moves(m):
    """Referenzvergleich gegen die alte Auswertung — inklusive der Fälle
    'nur Baseline' (ein Datenpunkt) und 'gar keine Kalenderdaten'."""
    a = _add_offer(m, "https://example.invalid/a")
    b = _add_offer(m, "https://example.invalid/b")
    c = _add_offer(m, "https://example.invalid/c")     # bleibt ohne History
    with m.db() as con:
        _hist(con, a, [("2027-05-01", 1000, 500), ("2027-05-01", 1200, 480),
                       ("2027-05-02", 1100, 520), ("2027-05-02", 1500, 511),
                       ("2027-05-03", 1900, 400)])     # nur Baseline -> zählt nicht
        _hist(con, b, [("2027-06-01", 900, 700)])      # nur Baseline
    with m.db() as con:
        neu = m._calendar_last_move_ts(con)
        for oid in (a, b, c):
            alt = max((v["ts"] for v in m._calendar_moves(con, oid).values()), default=0)
            assert neu.get(oid, 0) == alt, f"Angebot {oid}"
    assert neu.get(a) == 1500       # jüngste Bewegung, NICHT die Baseline von 1900
    assert b not in neu and c not in neu


def test_ein_query_fuer_alle_angebote(m):
    """Der eigentliche Punkt: die Kosten hängen nicht mehr an der Angebotszahl."""
    ids = [_add_offer(m, f"https://example.invalid/{i}") for i in range(5)]
    with m.db() as con:
        for n, oid in enumerate(ids):
            _hist(con, oid, [("2027-05-01", 1000, 500), ("2027-05-01", 2000 + n, 480)])
    with m.db() as con:
        calls = []
        orig = con.execute

        class Counting:
            def execute(self, sql, *a):
                calls.append(sql)
                return orig(sql, *a)
        neu = m._calendar_last_move_ts(Counting())
    assert len(calls) == 1
    assert neu == {oid: 2000 + n for n, oid in enumerate(ids)}


def test_calendar_alert_in_collect_offers(m):
    """End-to-End über `_collect_offers`: gemeldet wird nur, was NACH dem zuletzt
    gesehenen Stand (`calendar_seen_ts`) passiert ist."""
    oid = _add_offer(m, "https://example.invalid/alert")
    with m.db() as con:
        _hist(con, oid, [("2027-05-01", 1000, 500), ("2027-05-01", 2000, 480)])
        con.execute("UPDATE offers SET calendar_seen_ts=? WHERE id=?", (1500, oid))
    assert next(o for o in m._collect_offers() if o["id"] == oid)["calendar_alert"] is True

    with m.db() as con:                       # Nutzer hat den Kalender angesehen
        con.execute("UPDATE offers SET calendar_seen_ts=? WHERE id=?", (2000, oid))
    assert next(o for o in m._collect_offers() if o["id"] == oid)["calendar_alert"] is False


def test_kein_alert_ohne_kalenderdaten(m):
    oid = _add_offer(m, "https://example.invalid/leer")
    assert next(o for o in m._collect_offers() if o["id"] == oid)["calendar_alert"] is False
