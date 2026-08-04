"""Tests für den Markttrend aus dem täglichen Regions-Warenkorb (`market_basket`).

Kein Netz: `fetch_search_params` wird gemonkeypatcht. Der Fokus liegt auf den
Stellen, an denen die Rechnung falsch werden KANN — Matched Pairs statt
Durchschnittsvergleich, Median statt Mittelwert, Board-/Nächte-Wechsel als
Nicht-Signal, und die Verkettung erst auf Tagesebene.
"""
import importlib
import time
from datetime import date, timedelta

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


@pytest.fixture
def mb(m):
    return importlib.import_module("market_basket")


def _day(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


def _snap(m, region, day, hotels):
    """hotels: [(giata, preis, board, naechte)] — Snapshot direkt in die DB legen."""
    with m.db() as con:
        con.executemany(
            "INSERT INTO basket_snapshots (ts, day, region, region_giata, giata, price, "
            "board, nights, dep_date) VALUES (?,?,?,?,?,?,?,?,?)",
            [(int(time.time()), day, region, 1, str(g), p, b, n, "2027-01-01")
             for g, p, b, n in hotels])


def _move(m, mb, region, day):
    with m.db() as con:
        return mb._compute_move(con, region, day)


# ── Tagesbewegung: Matched Pairs, Median, Board-/Nächte-Guard ──────────────────

def test_move_uses_median_of_matched_pairs(m, mb):
    # 12 Hotels, elf mit +2 %, eines mit einem absurden Ausreißer (+400 %).
    old = [(i, 1000.0, "AI", 7) for i in range(12)]
    new = [(i, 1020.0, "AI", 7) for i in range(11)] + [(11, 5000.0, "AI", 7)]
    _snap(m, "Kanaren", _day(-1), old)
    _snap(m, "Kanaren", _day(0), new)
    mv = _move(m, mb, "Kanaren", _day(0))
    assert mv is not None
    assert mv["n_matched"] == 12
    # Median ignoriert den Ausreißer — ein Mittelwert läge bei ~35 %.
    assert mv["pct_median"] == pytest.approx(2.0, abs=0.01)


def test_move_ignores_hotels_missing_in_one_snapshot(m, mb):
    """Neu hinzugekommene und verschwundene Hotels dürfen nicht als Preisbewegung
    zählen — sonst misst der Trend die Zusammensetzung des Warenkorbs."""
    _snap(m, "Kanaren", _day(-1),
          [(i, 1000.0, "AI", 7) for i in range(12)] + [(90, 300.0, "AI", 7)])
    _snap(m, "Kanaren", _day(0),
          [(i, 1000.0, "AI", 7) for i in range(12)] + [(91, 4000.0, "AI", 7)])
    mv = _move(m, mb, "Kanaren", _day(0))
    assert mv["n_matched"] == 12          # 90 und 91 fliegen raus
    assert mv["n_total"] == 13            # im Snapshot stehen sie trotzdem
    assert mv["pct_median"] == pytest.approx(0.0, abs=0.01)


def test_move_skips_board_and_nights_changes(m, mb):
    """Wechselt die Verpflegung oder die Dauer, ist der Preissprung ein anderer
    Angebotstyp und kein Marktsignal."""
    _snap(m, "Kanaren", _day(-1), [(i, 1000.0, "HP", 7) for i in range(12)])
    _snap(m, "Kanaren", _day(0),
          [(i, 1000.0, "HP", 7) for i in range(10)]
          + [(10, 1400.0, "AI", 7), (11, 1400.0, "HP", 10)])
    mv = _move(m, mb, "Kanaren", _day(0))
    assert mv["n_matched"] == 10
    assert mv["pct_median"] == pytest.approx(0.0, abs=0.01)


def test_move_needs_minimum_matched_hotels(m, mb):
    _snap(m, "Kanaren", _day(-1), [(i, 1000.0, "AI", 7) for i in range(5)])
    _snap(m, "Kanaren", _day(0), [(i, 1100.0, "AI", 7) for i in range(5)])
    assert _move(m, mb, "Kanaren", _day(0)) is None


def test_move_skipped_after_long_gap(m, mb):
    """War das Add-on eine Weile aus, ist der Sprung über die Lücke keine
    Tagesbewegung — die Kette beginnt neu."""
    _snap(m, "Kanaren", _day(-30), [(i, 1000.0, "AI", 7) for i in range(12)])
    _snap(m, "Kanaren", _day(0), [(i, 1200.0, "AI", 7) for i in range(12)])
    assert _move(m, mb, "Kanaren", _day(0)) is None


def test_first_snapshot_has_no_move(m, mb):
    _snap(m, "Kanaren", _day(0), [(i, 1000.0, "AI", 7) for i in range(12)])
    assert _move(m, mb, "Kanaren", _day(0)) is None


# ── Trend und Index über mehrere Tage ──────────────────────────────────────────

def _write_moves(m, region, values, *, start=-3):
    with m.db() as con:
        for k, pct in enumerate(values):
            con.execute(
                "INSERT INTO basket_moves (ts, day, region, prev_day, gap_days, "
                "pct_median, n_matched, n_total) VALUES (?,?,?,?,?,?,?,?)",
                (int(time.time()), _day(start + k), region, _day(start + k - 1), 1,
                 pct, 50, 60))


def test_trend_chains_daily_values(m, mb):
    _write_moves(m, "Kanaren", [-1.0, -1.0, -1.0])
    with m.db() as con:
        t = mb.basket_trend(con, region="Kanaren")
    assert t["dir"] == "down"
    # Verkettung, nicht Summe: 0.99^3 - 1 = -2.97 %
    assert t["pct"] == pytest.approx(-3.0, abs=0.1)
    assert t["days"] == 3
    assert t["hotels"] == 50


def test_trend_needs_two_days(m, mb):
    _write_moves(m, "Kanaren", [-5.0])
    with m.db() as con:
        assert mb.basket_trend(con, region="Kanaren") is None


def test_global_weights_regions_by_hotel_count(m, mb):
    """Zwei Regionen am selben Tag: die mit mehr verglichenen Hotels soll den
    Gesamtwert stärker prägen."""
    with m.db() as con:
        for region, pct, n in (("Gross", 2.0, 180), ("Klein", -2.0, 20)):
            for k in range(2):
                con.execute(
                    "INSERT INTO basket_moves (ts, day, region, prev_day, gap_days, "
                    "pct_median, n_matched, n_total) VALUES (?,?,?,?,?,?,?,?)",
                    (int(time.time()), _day(-1 + k), region, _day(-2 + k), 1, pct, n, n))
        t = mb.basket_trend(con)
    # gewichteter Tageswert: (2*180 + (-2)*20) / 200 = +1.6 % je Tag
    assert t["dir"] == "up"
    assert t["pct"] == pytest.approx(3.2, abs=0.1)


def test_index_covers_full_history(m, mb):
    _write_moves(m, "Kanaren", [1.0] * 5, start=-40)
    with m.db() as con:
        assert mb.basket_trend(con, region="Kanaren") is None   # außerhalb 14 Tage
        i = mb.basket_index(con, region="Kanaren")
    assert i["index"] == pytest.approx(105.1, abs=0.1)


# ── Kompletter Lauf ────────────────────────────────────────────────────────────

def _fake_search(m, monkeypatch, per_page):
    """`fetch_search_params` durch eine seitenweise Antwort ersetzen."""
    def _f(*, region, offset=0, **kw):
        return {"ok": True, "results": per_page.get(offset, [])}
    monkeypatch.setattr(m, "fetch_search_params", _f)


def test_run_basket_region_stores_snapshot_and_pages(m, mb, monkeypatch):
    page0 = [{"giata": i, "price": 900 + i, "board": "AI", "nights": 7,
              "date": "2027-01-01"} for i in range(1, 51)]
    page1 = [{"giata": 100 + i, "price": 1500 + i, "board": "AI", "nights": 7,
              "date": "2027-01-01"} for i in range(10)]
    _fake_search(m, monkeypatch, {0: page0, 50: page1})
    res = mb.run_basket_region("Kanaren", 128)
    assert res["hotels"] == 60          # zweite Seite wird geholt, dann Abbruch (<50)
    assert res["move"] is None          # erster Tag, kein Vorgänger
    with m.db() as con:
        n = con.execute("SELECT COUNT(*) c FROM basket_snapshots").fetchone()["c"]
    assert n == 60


def test_run_basket_region_second_day_yields_move(m, mb, monkeypatch):
    _snap(m, "Kanaren", _day(-1), [(i, 1000.0, "AI", 7) for i in range(1, 13)])
    rows = [{"giata": i, "price": 950.0, "board": "AI", "nights": 7,
             "date": "2027-01-01"} for i in range(1, 13)]
    _fake_search(m, monkeypatch, {0: rows})
    res = mb.run_basket_region("Kanaren", 128)
    assert res["move"]["pct_median"] == pytest.approx(-5.0, abs=0.01)


def test_rerun_same_day_replaces_snapshot(m, mb, monkeypatch):
    rows = [{"giata": i, "price": 1000.0, "board": "AI", "nights": 7,
             "date": "2027-01-01"} for i in range(1, 13)]
    _fake_search(m, monkeypatch, {0: rows})
    mb.run_basket_region("Kanaren", 128)
    mb.run_basket_region("Kanaren", 128)
    with m.db() as con:
        n = con.execute("SELECT COUNT(*) c FROM basket_snapshots").fetchone()["c"]
    assert n == 12          # nicht 24


def test_regions_come_from_saved_searches(m, mb):
    with m.db() as con:
        con.execute("INSERT INTO saved_searches (name, payload, ts) VALUES (?,?,?)",
                    ("Kanaren", '{"dest": {"giata": 128, "label": "Gran Canaria"}}',
                     int(time.time())))
    assert mb._basket_regions() == [{"giata": 128, "label": "Gran Canaria"}]


def test_disabled_option_skips_run(m, mb, monkeypatch):
    monkeypatch.setattr(m, "load_config", lambda: {"market_basket_enabled": False})
    called = []
    monkeypatch.setattr(mb, "run_baskets", lambda **kw: called.append(1))
    mb.maybe_run_baskets()
    assert not called


def test_lead_days_is_clamped(m, mb, monkeypatch):
    monkeypatch.setattr(m, "load_config", lambda: {"market_basket_lead_days": 5000})
    assert mb._lead_days() == 365
    monkeypatch.setattr(m, "load_config", lambda: {"market_basket_lead_days": "quatsch"})
    assert mb._lead_days() == mb.BASKET_LEAD_DAYS_DEFAULT


def test_prune_keeps_moves(m, mb):
    _snap(m, "Kanaren", _day(-mb.BASKET_RETENTION_DAYS - 5),
          [(i, 1000.0, "AI", 7) for i in range(3)])
    _write_moves(m, "Kanaren", [1.0, 1.0])
    with m.db() as con:
        mb._prune(con)
        snaps = con.execute("SELECT COUNT(*) c FROM basket_snapshots").fetchone()["c"]
        moves = con.execute("SELECT COUNT(*) c FROM basket_moves").fetchone()["c"]
    assert snaps == 0 and moves == 2


# ── API ────────────────────────────────────────────────────────────────────────

def _client(m, monkeypatch):
    monkeypatch.setattr(m, "_auth_ok", lambda req: True)
    m.app.config["TESTING"] = True
    return m.app.test_client()


def test_market_trend_endpoint_includes_basket(m, mb, monkeypatch):
    _write_moves(m, "Kanaren", [-1.0, -1.0])
    c = _client(m, monkeypatch)
    d = c.get("/api/market-trend").get_json()
    assert d["basket"]["global"]["trend"]["dir"] == "down"
    assert [r["region"] for r in d["basket"]["by_region"]] == ["Kanaren"]


def test_wochenueberblick_prefers_basket(m, mb):
    """Der Digest nimmt den Warenkorb, sobald der genug Tage hat — der schmalere
    Angebots-Trend ist nur Rückfallebene."""
    digest = importlib.import_module("digest")
    _write_moves(m, "Kanaren", [-1.0, -1.0])
    with m.db() as con:
        sec = digest._market_section(con)
    assert sec["src"] == "basket"
    assert sec["global"]["dir"] == "down"
    assert sec["regions"][0][0] == "Kanaren"
    assert digest._market_line(sec["global"]).startswith("▼ gefallen")


def test_wochenueberblick_falls_back_to_offers(m, mb):
    digest = importlib.import_module("digest")
    now = int(time.time())
    with m.db() as con:
        for k in range(8):
            con.execute("INSERT INTO price_moves (ts, region, country, months_out, "
                        "pct_change) VALUES (?,?,?,?,?)",
                        (now - k * 3600, "Kanaren", "Spanien", 3, 1.0))
        sec = digest._market_section(con)
    assert sec["src"] == "offers"
    assert sec["global"]["dir"] == "up"


def test_backup_roundtrip_keeps_basket_moves(m, mb, monkeypatch):
    """Der Index seit Aufzeichnungsbeginn hängt allein an `basket_moves` — die
    Zeilen müssen ein Backup/Restore überleben, sonst beginnt er nach einem Umzug
    wieder bei 100."""
    import io
    import json
    import zipfile
    _write_moves(m, "Kanaren", [-1.0, -1.0])
    c = _client(m, monkeypatch)
    blob = c.get("/api/backup").data
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        data = json.loads(z.read("data.json"))
    assert len(data["basket_moves"]) == 2
    with m.db() as con:
        con.execute("DELETE FROM basket_moves")
    r = c.post("/api/restore", data={"file": (io.BytesIO(blob), "backup.zip")},
               content_type="multipart/form-data").get_json()
    assert r["market_basket"] == 2
    with m.db() as con:
        assert mb.basket_trend(con, region="Kanaren")["dir"] == "down"


def test_basket_region_delete(m, mb, monkeypatch):
    _snap(m, "Kanaren", _day(0), [(i, 1000.0, "AI", 7) for i in range(3)])
    _write_moves(m, "Kanaren", [1.0, 1.0])
    c = _client(m, monkeypatch)
    d = c.delete("/api/market-basket/region", json={"region": "Kanaren"}).get_json()
    assert d["snapshots"] == 3 and d["moves"] == 2
