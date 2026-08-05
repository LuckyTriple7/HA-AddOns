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
