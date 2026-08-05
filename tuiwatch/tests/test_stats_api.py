"""Tests für die Tracking-Statistik (/api/stats): Ersparnis ggü. Höchstpreis,
größte Einzelbewegungen, Wochentags-Muster, Tiefstpreis-Rückschau."""
import importlib
import time
from datetime import datetime, timedelta

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
    mod.TRIPS_DIR = str(tmp_path / "trips")
    mod.init_db()
    return mod


def _mk_offer(m, url, hist, **cols):
    with m.db() as con:
        cur = con.execute(
            "INSERT INTO offers (url, hotel, created) VALUES (?,?,?)",
            (url, cols.pop("hotel", "Hotel X"), int(time.time())))
        oid = cur.lastrowid
        for k, v in cols.items():
            con.execute(f"UPDATE offers SET {k}=? WHERE id=?", (v, oid))
        for ts, price in hist:
            con.execute(
                "INSERT INTO price_history (offer_id, ts, price, ok) VALUES (?,?,?,1)",
                (oid, ts, price))
    return oid


def test_stats_saved_and_moves(m):
    t0 = int(time.time()) - 10 * 86400
    # aktiv: 1500 → 1800 → 1600  (Peak 1800, aktuell 1600 → 200 gespart;
    # größter Sturz −200, größter Anstieg +300)
    _mk_offer(m, "https://www.tui.com/a", [(t0, 1500), (t0 + 86400, 1800),
                                           (t0 + 2 * 86400, 1600)], hotel="Alpha")
    d = m.test_client_stats = m.app.test_client().get("/api/stats", headers=ING).get_json()
    assert d["offers_total"] == 1 and d["offers_active"] == 1
    assert d["points"] == 3
    assert d["saved_total"] == 200
    assert d["saved_rows"][0]["name"] == "Alpha"
    assert d["saved_rows"][0]["peak"] == 1800 and d["saved_rows"][0]["price"] == 1600
    assert d["top_drops"][0]["delta"] == -200
    assert d["top_rises"][0]["delta"] == 300
    # keine archivierten Angebote → keine Rückschau
    assert d["low_days_median"] is None


def test_stats_low_days_lookback(m):
    # archiviert, Reise vorbei: Abreise = return_date − Nächte; Tiefstpreis 20 Tage davor
    ret = datetime.now() - timedelta(days=30)
    start = ret - timedelta(days=7)          # 7 Nächte
    low_ts = int((start - timedelta(days=20)).timestamp())
    hi_ts = int((start - timedelta(days=40)).timestamp())
    _mk_offer(m, "https://www.tui.com/b", [(hi_ts, 1400), (low_ts, 1000)],
              hotel="Beta", archived=1,
              return_date=ret.strftime("%Y-%m-%d"),
              details="7 Nächte ab 01.01.2026 · 2 Erwachsene")
    d = m.app.test_client().get("/api/stats", headers=ING).get_json()
    assert d["low_days_n"] == 1
    assert d["low_days_median"] == 20
    # archiviert → zählt nicht als Ersparnis
    assert d["saved_total"] == 0


def test_stats_requires_auth(m):
    assert m.app.test_client().get("/api/stats").status_code == 401


def _add_calendar(m, oid, travel_date, rows):
    """rows = [(days_out, price)] → calendar_history-Einträge für ein Reisedatum."""
    from datetime import date as _date
    with m.db() as con:
        for days_out, price in rows:
            ts = int(datetime.combine(
                _date.fromisoformat(travel_date) - timedelta(days=days_out),
                datetime.min.time()).timestamp()) + 43200
            con.execute("INSERT INTO calendar_history (offer_id, travel_date, ts, price) "
                        "VALUES (?,?,?,?)", (oid, travel_date, ts, price))


def test_forecast_from_lead_curve(m):
    """Vorlaufzeit-Kurve: 3 Reisetermine zeigen 60→46 Tage vor Abreise +10 % —
    Prognose überträgt das auf den eigenen Termin (Abreise in 60 Tagen)."""
    ret = (datetime.now() + timedelta(days=67)).strftime("%Y-%m-%d")
    oid = _mk_offer(m, "https://www.tui.com/f", [(int(time.time()) - 3600, 1000)],
                    hotel="Gamma", return_date=ret,
                    details="7 Nächte ab 01.01.2027 · 2 Erwachsene")
    for i in range(3):   # drei Termine, je 2 Messungen (60 und 46 Tage vorher)
        tdate = (datetime.now() + timedelta(days=80 + i * 7)).strftime("%Y-%m-%d")
        _add_calendar(m, oid, tdate, [(60, 1000), (46, 1100)])

    d = m.app.test_client().get(f"/api/forecast/{oid}", headers=ING).get_json()
    assert d["ok"] is True
    assert d["days_to_departure"] == 60
    assert d["price"] == 1000
    pts = {p["days"]: p for p in d["points"]}
    # nur Horizont 14 hat beide Kurven-Buckets (60→Bucket 8, 46→Bucket 6);
    # 7/30 Tage haben keine Daten und werden ohne Markttrend ehrlich weggelassen
    assert list(pts) == [14]
    assert pts[14]["price"] == 1100
    assert d["basis"]["calendar_dates"] == 3


def test_forecast_needs_departure_and_data(m):
    # ohne Abreisedatum → ehrliche Absage
    oid = _mk_offer(m, "https://www.tui.com/g", [(int(time.time()), 900)])
    d = m.app.test_client().get(f"/api/forecast/{oid}", headers=ING).get_json()
    assert d["ok"] is False and "Abreisedatum" in d["note"]
    # mit Abreise, aber ohne Kalenderhistorie/Markttrend → ehrliche Absage
    ret = (datetime.now() + timedelta(days=37)).strftime("%Y-%m-%d")
    oid2 = _mk_offer(m, "https://www.tui.com/h", [(int(time.time()), 900)],
                     return_date=ret, details="7 Nächte ab 01.01.2027 · 2 Erwachsene")
    d = m.app.test_client().get(f"/api/forecast/{oid2}", headers=ING).get_json()
    assert d["ok"] is False
