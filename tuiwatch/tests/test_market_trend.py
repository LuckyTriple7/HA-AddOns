"""Tests für den globalen Markttrend (`price_moves`, `_market_trend`, `_months_out`,
Backfill) — destinationsübergreifend und unabhängig vom Fortbestehen eines Angebots.
Kein Netz nötig: `fetch_price` wird gemonkeypatcht."""
import importlib
import io
import json
import time
import zipfile

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


def _add_offer(m, url, region="Kanaren", country="Spanien", return_date="2027-03-15"):
    now = int(time.time())
    with m.db() as con:
        con.execute(
            "INSERT INTO offers (url, hotel, region, country, return_date, created) "
            "VALUES (?,?,?,?,?,?)",
            (url, "Test-Hotel", region, country, return_date, now))
        return con.execute("SELECT id FROM offers WHERE url=?", (url,)).fetchone()["id"]


def _mock_price(m, monkeypatch, price):
    monkeypatch.setattr(m, "fetch_price", lambda url, **k: {
        "ok": True, "price": price, "region": "Kanaren", "country": "Spanien",
        "return_date": "2027-03-15"})
    monkeypatch.setattr(m, "fetch_hotel_image", lambda url, **k: "")  # kein Netz


def test_first_check_writes_no_price_move(m, monkeypatch):
    oid = _add_offer(m, "https://example.invalid/a?duration=7")
    _mock_price(m, monkeypatch, 1000)
    m.check_offer(oid)
    with m.db() as con:
        n = con.execute("SELECT COUNT(*) c FROM price_moves").fetchone()["c"]
    assert n == 0   # kein Vorwert vorhanden -> keine Änderung berechenbar


def test_second_check_records_pct_change(m, monkeypatch):
    oid = _add_offer(m, "https://example.invalid/b?duration=7")
    _mock_price(m, monkeypatch, 1000)
    m.check_offer(oid)
    _mock_price(m, monkeypatch, 950)
    m.check_offer(oid)
    with m.db() as con:
        rows = con.execute("SELECT * FROM price_moves").fetchall()
    assert len(rows) == 1
    assert rows[0]["pct_change"] == pytest.approx(-5.0)
    assert rows[0]["region"] == "Kanaren"
    assert rows[0]["months_out"] is not None


def test_delete_offer_keeps_price_moves(m, monkeypatch):
    oid = _add_offer(m, "https://example.invalid/c?duration=7")
    _mock_price(m, monkeypatch, 1000)
    m.check_offer(oid)
    _mock_price(m, monkeypatch, 900)
    m.check_offer(oid)
    with m.db() as con:
        before = con.execute("SELECT COUNT(*) c FROM price_moves").fetchone()["c"]
    assert before == 1

    c = m.app.test_client()
    r = c.delete(f"/api/offers/{oid}", headers=ING)
    assert r.status_code == 200

    with m.db() as con:
        after = con.execute("SELECT COUNT(*) c FROM price_moves").fetchone()["c"]
        offer_gone = con.execute("SELECT 1 FROM offers WHERE id=?", (oid,)).fetchone()
    assert after == before          # Markttrend-Datenpunkte überleben die Löschung
    assert offer_gone is None


def test_months_out_estimation(m):
    now = int(time.time())
    # Rückreise in 5 Monaten + 7 Naechte -> Abreise in knapp 5 Monaten
    ret = (__import__("datetime").date.today()
           + __import__("datetime").timedelta(days=150 + 7)).isoformat()
    mo = m._months_out(ret, 7, now)
    assert mo in (4, 5)


def test_months_out_none_without_data(m):
    now = int(time.time())
    assert m._months_out("", 7, now) is None
    assert m._months_out("2027-03-15", None, now) is None
    assert m._months_out("not-a-date", 7, now) is None
    # Abreise in der Vergangenheit
    past = (__import__("datetime").date.today()
            - __import__("datetime").timedelta(days=10)).isoformat()
    assert m._months_out(past, 7, now) is None


def _seed_moves(m, region, pct_values, days_ago_start=13):
    now = int(time.time())
    with m.db() as con:
        for i, pct in enumerate(pct_values):
            ts = now - (days_ago_start - i) * 86400
            con.execute(
                "INSERT INTO price_moves (ts, region, country, months_out, pct_change) "
                "VALUES (?,?,?,?,?)", (ts, region, "Spanien", 5, pct))


def test_market_trend_none_with_too_few_samples(m):
    _seed_moves(m, "Kanaren", [1, 1, 1])   # < MARKET_TREND_MIN_SAMPLES
    with m.db() as con:
        assert m._market_trend(con, region="Kanaren") is None


def test_market_trend_detects_rising_prices(m):
    _seed_moves(m, "Kanaren", [1.0] * 8)
    with m.db() as con:
        t = m._market_trend(con, region="Kanaren")
    assert t is not None
    assert t["dir"] == "up"
    assert t["pct"] > 0
    assert t["n"] == 8


def test_market_trend_detects_falling_prices(m):
    _seed_moves(m, "Balearen", [-1.0] * 8)
    with m.db() as con:
        t = m._market_trend(con, region="Balearen")
    assert t is not None
    assert t["dir"] == "down"
    assert t["pct"] < 0


def test_market_trend_region_filter_is_isolated(m):
    _seed_moves(m, "Kanaren", [1.0] * 8)
    _seed_moves(m, "Balearen", [-1.0] * 8)
    with m.db() as con:
        kan = m._market_trend(con, region="Kanaren")
        bal = m._market_trend(con, region="Balearen")
        glob = m._market_trend(con)   # keine Region -> beide zusammen
    assert kan["dir"] == "up"
    assert bal["dir"] == "down"
    assert glob["n"] == 16


def test_backfill_populates_price_moves_from_history(m):
    oid = _add_offer(m, "https://example.invalid/d?duration=7")
    now = int(time.time())
    with m.db() as con:
        con.execute("DELETE FROM price_moves")
        for i, price in enumerate((1000, 950, 950, 900)):
            con.execute(
                "INSERT INTO price_history (offer_id, ts, price, ok) VALUES (?,?,?,1)",
                (oid, now - (4 - i) * 3600, price))
        con.execute("DELETE FROM meta WHERE key='price_moves_backfilled'")

    m.init_db()   # erneuter Aufruf muss den Backfill jetzt (erneut) auslösen

    with m.db() as con:
        rows = con.execute("SELECT pct_change FROM price_moves ORDER BY ts").fetchall()
    assert [round(r["pct_change"], 1) for r in rows] == [-5.0, 0.0, -5.3]


def test_backfill_runs_only_once(m):
    with m.db() as con:
        flag_before = con.execute(
            "SELECT value FROM meta WHERE key='price_moves_backfilled'").fetchone()
    assert flag_before is not None and flag_before["value"] == "1"

    with m.db() as con:
        con.execute("INSERT INTO price_moves (ts, region, country, months_out, pct_change) "
                    "VALUES (?,?,?,?,?)", (int(time.time()), "Marker", "", None, 0))
    m.init_db()   # Flag ist gesetzt -> Backfill darf NICHT nochmal laufen
    with m.db() as con:
        markers = con.execute(
            "SELECT COUNT(*) c FROM price_moves WHERE region='Marker'").fetchone()["c"]
    assert markers == 1


def test_backup_zip_contains_price_moves(m):
    _seed_moves(m, "Kanaren", [1.0, 2.0, 3.0])
    c = m.app.test_client()
    b = c.get("/api/backup", headers=ING)
    assert b.status_code == 200
    data = json.loads(zipfile.ZipFile(io.BytesIO(b.data)).read("data.json"))
    assert len(data["price_moves"]) == 3
    assert {round(p["pct_change"], 1) for p in data["price_moves"]} == {1.0, 2.0, 3.0}


def test_restore_reimports_price_moves_after_wipe(m):
    _seed_moves(m, "Kanaren", [1.0, 2.0, 3.0])
    c = m.app.test_client()
    b = c.get("/api/backup", headers=ING)

    with m.db() as con:
        con.execute("DELETE FROM price_moves")

    rr = c.post("/api/restore", headers=ING,
                data={"file": (io.BytesIO(b.data), "backup.zip")},
                content_type="multipart/form-data")
    assert rr.status_code == 200
    assert rr.get_json()["market_trend"] == 3
    with m.db() as con:
        n = con.execute("SELECT COUNT(*) c FROM price_moves").fetchone()["c"]
    assert n == 3


def test_restore_price_moves_is_not_duplicated_on_repeat(m):
    _seed_moves(m, "Kanaren", [1.0, 2.0, 3.0])
    c = m.app.test_client()
    b = c.get("/api/backup", headers=ING)

    # Angebote überleben nicht (gelöscht/nie da), Markttrend-Daten trotzdem vorhanden
    rr1 = c.post("/api/restore", headers=ING,
                 data={"file": (io.BytesIO(b.data), "b1.zip")},
                 content_type="multipart/form-data")
    assert rr1.get_json()["market_trend"] == 0   # bereits vorhanden -> dedupliziert

    with m.db() as con:
        con.execute("DELETE FROM price_moves")
    rr2 = c.post("/api/restore", headers=ING,
                 data={"file": (io.BytesIO(b.data), "b2.zip")},
                 content_type="multipart/form-data")
    assert rr2.get_json()["market_trend"] == 3   # jetzt leer -> alle 3 werden eingespielt

    rr3 = c.post("/api/restore", headers=ING,
                 data={"file": (io.BytesIO(b.data), "b3.zip")},
                 content_type="multipart/form-data")
    assert rr3.get_json()["market_trend"] == 0   # erneutes Einspielen dedupliziert
    with m.db() as con:
        n = con.execute("SELECT COUNT(*) c FROM price_moves").fetchone()["c"]
    assert n == 3
