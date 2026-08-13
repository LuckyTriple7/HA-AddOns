"""Tests für die Booking-Kurve und die Buchungszeitpunkt-Ampel (`market_basket`).

Kein Netz. Der Fokus liegt auf den Stellen, an denen die Rechnung falsch werden KANN:
die Normierung auf Prozent pro Tag (Lücken im Betrieb), die Bucket-Grenzen, die
Mindestbelegung (nichts erfinden), der Perzentilrang auf dem verketteten Index statt
auf Rohpreisen, sowie die Renormierung und die Last-Minute-Sperre der Ampel.
"""
import importlib
import json
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
    mod = importlib.import_module("market_basket")
    mod._invalidate_curve()
    return mod


def _day(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


def _move_row(m, basket, day, pct, dte, *, gap=1, n_matched=20):
    with m.db() as con:
        con.execute(
            "INSERT OR REPLACE INTO basket_moves (ts, day, basket, prev_day, gap_days, "
            "pct_median, n_matched, n_total, days_to_dep) VALUES (?,?,?,?,?,?,?,?,?)",
            (int(time.time()), day, basket, day, gap, pct, n_matched, n_matched, dte))


def _snap(m, basket, day, hotels, dep_date):
    """hotels: [(giata, preis, board, naechte)]."""
    with m.db() as con:
        con.executemany(
            "INSERT INTO basket_snapshots (ts, day, basket, region_giata, giata, price, "
            "board, nights, dep_date) VALUES (?,?,?,?,?,?,?,?,?)",
            [(int(time.time()), day, basket, 1, str(g), p, b, n, dep_date)
             for g, p, b, n in hotels])


def _curve(m, mb):
    mb._invalidate_curve()
    with m.db() as con:
        return mb.booking_curve(con)


def _bucket(curve, label_part):
    return next(b for b in curve if label_part in b["label"])


# ── Vorlaufzeit an der Tagesbewegung ───────────────────────────────────────────

def test_move_stores_median_lead_of_matched_pairs(m, mb):
    """`days_to_dep` beschreibt genau die Hotels, die auch den Median erzeugt haben —
    nicht alle Hotels des Snapshots."""
    dep_a, dep_b = _day(100), _day(200)
    # Zwölf gematchte Hotels mit Abreise in 100 Tagen …
    _snap(m, "Kanaren", _day(-1), [(i, 1000.0, "AI", 7) for i in range(12)], dep_a)
    # … plus ein Hotel, das es nur heute gibt und dessen Abreise weit weg liegt.
    _snap(m, "Kanaren", _day(0), [(i, 1010.0, "AI", 7) for i in range(12)], dep_a)
    _snap(m, "Kanaren", _day(0), [(99, 900.0, "AI", 7)], dep_b)
    with m.db() as con:
        mv = mb._compute_move(con, "Kanaren", _day(0))
    assert mv["n_matched"] == 12
    assert mv["days_to_dep"] == 100      # das Ausreißer-Hotel zählt nicht mit


def test_days_to_dep_rejects_past_and_broken_dates(mb):
    assert mb._days_to_dep(_day(30), _day(0)) == 30
    assert mb._days_to_dep(_day(-1), _day(0)) is None     # Abreise vor dem Snapshot
    assert mb._days_to_dep("", _day(0)) is None
    assert mb._days_to_dep("kaputt", _day(0)) is None


# ── Bucket-Grenzen ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("dte,label", [
    (400, "ab 181"), (181, "ab 181"), (180, "180–121"), (121, "180–121"),
    (120, "120–91"), (91, "120–91"), (90, "90–61"), (61, "90–61"),
    (60, "60–31"), (31, "60–31"), (30, "30–8"), (8, "30–8"),
    (7, "unter 8"), (0, "unter 8"),
])
def test_bucket_boundaries(mb, dte, label):
    assert label in mb.BOOKING_BUCKETS[mb._bucket_index(dte)][2]


# ── Kurve ──────────────────────────────────────────────────────────────────────

def test_curve_needs_minimum_samples(m, mb):
    """Sieben Punkte reichen nicht — es wird nichts geraten, aber die Zahl der
    vorhandenen Punkte wird trotzdem gemeldet."""
    for i in range(7):
        _move_row(m, "Kanaren", _day(-i), -0.1, 100)
    b = _bucket(_curve(m, mb), "120–91")
    assert b["rate"] is None and b["n"] == 7


def test_curve_median_ignores_outlier_day(m, mb):
    """Ein einzelner Aktionscode-Tag darf die Kurve nicht kippen — deshalb Median
    statt Mittelwert über die Tagesraten."""
    for i in range(11):
        _move_row(m, "Kanaren", _day(-i), -0.2, 100)
    _move_row(m, "Mallorca", _day(-30), -25.0, 100)       # Ausreißer
    b = _bucket(_curve(m, mb), "120–91")
    assert b["rate"] == pytest.approx(-0.2, abs=0.001)     # Mittelwert läge bei ~-2.3


def test_curve_normalises_gap_days_to_per_day(m, mb):
    """Eine Bewegung über vier Tage Lücke ist ein Viertel Tagesbewegung. Ohne diese
    Normierung zöge sie die Kurve nach außen."""
    for i in range(10):
        _move_row(m, "Kanaren", _day(-i), -0.4, 100, gap=4)
    b = _bucket(_curve(m, mb), "120–91")
    assert b["rate"] == pytest.approx(-0.1, abs=0.001)


def test_curve_marks_single_series_as_thin(m, mb):
    for i in range(10):
        _move_row(m, "Kanaren", _day(-i), -0.2, 100)
    assert _bucket(_curve(m, mb), "120–91")["thin"] is True
    for i in range(10):
        _move_row(m, "Mallorca", _day(-i), -0.2, 100)
    c = _bucket(_curve(m, mb), "120–91")
    assert c["thin"] is False and c["n_series"] == 2


def test_curve_bucket_pct_compounds_over_its_width(m, mb):
    for i in range(10):
        _move_row(m, "Kanaren", _day(-i), 1.0, 100)
    b = _bucket(_curve(m, mb), "120–91")
    assert b["width"] == 30
    assert b["pct"] == pytest.approx((1.01 ** 30 - 1) * 100, abs=0.1)


# ── Erwartete Restbewegung ─────────────────────────────────────────────────────

def _fake_curve(mb, rates: dict):
    """Kurve mit vorgegebenen Tagesraten je Bucket-Label-Fragment."""
    out = []
    for lo, hi, label in mb.BOOKING_BUCKETS:
        rate = next((v for k, v in rates.items() if k in label), None)
        out.append({'lo': lo, 'hi': hi, 'label': label,
                    'width': mb._bucket_width(lo, hi), 'rate': rate,
                    'pct': None, 'n': 99, 'n_series': 9, 'thin': False})
    return out


def test_expected_remaining_chains_bucket_rates(mb):
    """20 Tage Vorlauf: 13 Tage im 30–8-Fenster (Vorlauf 20…8), 7 Tage im letzten."""
    curve = _fake_curve(mb, {'30–8': 0.5, 'unter 8': 1.0})
    exp = mb.expected_remaining(curve, 20)
    assert exp["coverage"] == 1.0
    assert exp["pct"] == pytest.approx(((1.005 ** 13) * (1.01 ** 7) - 1) * 100, abs=0.05)


def test_expected_remaining_needs_coverage(mb):
    """Deckt die Kurve nur das letzte Stück ab, gibt es bei 200 Tagen Vorlauf keine
    Aussage — lieber schweigen als zur Hälfte raten."""
    assert mb.expected_remaining(_fake_curve(mb, {'unter 8': 1.0}), 200) is None
    assert mb.expected_remaining(_fake_curve(mb, {'unter 8': 1.0}), 7) is not None


def test_expected_remaining_without_departure(mb):
    curve = _fake_curve(mb, {'30–8': 0.5})
    assert mb.expected_remaining(curve, None) is None
    assert mb.expected_remaining(curve, 0) is None


# ── Position im eigenen Verlauf ────────────────────────────────────────────────

def test_position_runs_on_chained_index_not_raw_prices(m, mb):
    """Der Rang muss auf dem verketteten Index laufen. Hier bewegt sich der Markt
    nicht (alle Tagesbewegungen 0), während sich die rohen Preisniveaus durch eine
    wechselnde Hotelauswahl verdoppeln — der Rang darf davon nichts merken."""
    for i in range(10):
        day = _day(-9 + i)
        _move_row(m, "Kanaren", day, 0.0, 100)
        with m.db() as con:
            con.execute(
                "INSERT OR REPLACE INTO basket_levels (ts, day, basket, days_to_dep, "
                "n_hotels, p25, p50, p75) VALUES (?,?,?,?,?,?,?,?)",
                (int(time.time()), day, "Kanaren", 100, 50,
                 500.0 + i * 100, 800.0 + i * 100, 1200.0 + i * 100))
    with m.db() as con:
        pos = mb.basket_position(con, "Kanaren")
    assert pos["n"] == 10
    assert pos["index"] == pytest.approx(100.0, abs=0.01)
    assert pos["rank"] == 100.0     # alle Tage gleich teuer -> alle <= heute


def test_position_ranks_cheapest_day_at_zero(m, mb):
    for i, pct in enumerate([-1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0]):
        _move_row(m, "Kanaren", _day(-6 + i), pct, 100)
    with m.db() as con:
        pos = mb.basket_position(con, "Kanaren")
    assert pos["rank"] == pytest.approx(100 / 7, abs=0.1)   # nur der heutige Tag
    assert pos["index"] < 100


def test_position_needs_minimum_history(m, mb):
    for i in range(mb.BOOKING_POSITION_MIN_DAYS - 1):
        _move_row(m, "Kanaren", _day(-i), -0.5, 100)
    with m.db() as con:
        assert mb.basket_position(con, "Kanaren") is None


# ── Ampel ──────────────────────────────────────────────────────────────────────

def _series(m, basket, *, pct, days, dte):
    for i in range(days):
        _move_row(m, basket, _day(-(days - 1) + i), pct, dte - (days - 1 - i))


def test_signal_green_when_prices_will_rise(m, mb):
    """Fallender Trend, günstige Position und ein erwarteter Anstieg bis zur
    Abreise ergeben zusammen 🟢."""
    _series(m, "Kanaren", pct=-0.5, days=12, dte=25)
    for other in ("Mallorca", "Kreta"):
        for i in range(12):
            _move_row(m, other, _day(-11 + i), 1.5, 20 - i)
    with m.db() as con:
        sig = mb.booking_signal(con, "Kanaren", mb.booking_curve(con))
    assert sig["ampel"] == "green"
    assert sig["components"]["expected"]["pct"] > 0


def test_signal_renormalises_missing_components(m, mb):
    """Ohne Kurve und ohne Historie bleibt nur der Trend (Gewicht 0.25) — das ist
    unter BOOKING_MIN_WEIGHT, also gibt es bewusst keine Ampel."""
    for i in range(3):
        _move_row(m, "Kanaren", _day(-2 + i), -3.0, None)
    with m.db() as con:
        sig = mb.booking_signal(con, "Kanaren", [])
    assert sig["ampel"] is None
    assert "trend" in sig["components"] and len(sig["components"]) == 1
    assert sig["note"]


def test_signal_never_red_in_last_minute_window(m, mb):
    """Unter 14 Tagen Vorlauf gibt es nichts mehr zu warten — höchstens 🟡."""
    _series(m, "Kanaren", pct=2.0, days=12, dte=8)
    for i in range(12):
        _move_row(m, "Mallorca", _day(-11 + i), -2.0, 5)
    with m.db() as con:
        sig = mb.booking_signal(con, "Kanaren", mb.booking_curve(con))
    assert sig["days_to_dep"] is not None and sig["days_to_dep"] < mb.BOOKING_LASTMINUTE_DAYS
    assert sig["ampel"] != "red"


def test_current_lead_shrinks_with_elapsed_days(m, mb):
    """Der letzte Lauf ist drei Tage her — der Vorlauf ist heute entsprechend
    kleiner, sonst fiele die Restbewegung zu optimistisch aus."""
    _move_row(m, "Kanaren", _day(-3), -0.5, 60)
    with m.db() as con:
        assert mb._current_dte(con, "Kanaren") == 57


# ── Backfill ───────────────────────────────────────────────────────────────────

def test_backfill_fills_lead_and_levels_and_is_idempotent(m, mb):
    """Alt-Daten (Bewegungen ohne Vorlauf, keine Niveaus) müssen aus den noch
    vorhandenen Snapshots nachgetragen werden — und nur einmal."""
    day = _day(-1)
    _snap(m, "Kanaren", day, [(i, 1000.0 + i * 10, "AI", 7) for i in range(10)], _day(90))
    _move_row(m, "Kanaren", day, -0.3, None)
    with m.db() as con:
        con.execute("DELETE FROM meta WHERE key='basket_booking_backfill'")
        mb._backfill_booking(con)
        row = con.execute("SELECT days_to_dep FROM basket_moves WHERE day=?", (day,)).fetchone()
        lv = con.execute("SELECT * FROM basket_levels WHERE day=?", (day,)).fetchone()
    assert row["days_to_dep"] == 91          # Abreise in 90 Tagen, Snapshot von gestern
    assert lv["n_hotels"] == 10 and lv["p25"] < lv["p50"] < lv["p75"]
    with m.db() as con:
        before = con.execute("SELECT COUNT(*) c FROM basket_levels").fetchone()["c"]
        mb._backfill_booking(con)            # zweiter Lauf: Flag steht, no-op
        assert con.execute("SELECT COUNT(*) c FROM basket_levels").fetchone()["c"] == before


# ── Angebots-Zuordnung ─────────────────────────────────────────────────────────

def test_offer_key_never_hits_the_network(m, mb, monkeypatch):
    """`basket_key_for_offer` hängt am 5-Sekunden-Poll der Angebotsliste — ein
    Breadcrumb-Abruf je Angebot wäre dort fatal."""
    def _boom(*a, **kw):
        raise AssertionError("Breadcrumb-Abruf im Angebots-Poll")
    monkeypatch.setattr(m, "region_giata_from_breadcrumb", _boom)
    url = "https://www.tui.com/pauschalreisen/angebote/hotel-x/12345/?duration=7"
    with m.db() as con:      # Hotel noch nicht im Cache -> keine Zuordnung, kein Abruf
        assert mb.basket_key_for_offer(con, url, "Kanaren", _day(30)) is None
    m._meta_set("basket_region_map", json.dumps({"12345": 777}))
    with m.db() as con:
        key = mb.basket_key_for_offer(con, url, "Gran Canaria", _day(30))
    assert key and "Gran Canaria" in key and "Nächte" in key


def test_offer_key_prefers_matching_saved_search(m, mb):
    url = "https://www.tui.com/pauschalreisen/angebote/hotel-x/12345/?duration=7"
    payload = {"dest": {"giata": 777, "label": "Gran Canaria"},
               "vom": _day(10), "bis": _day(60), "dur": 7, "trav": 2}
    with m.db() as con:
        con.execute("INSERT INTO saved_searches (name, payload, ts) VALUES (?,?,?)",
                    ("Mai auf Gran Canaria", json.dumps(payload), int(time.time())))
    m._meta_set("basket_region_map", json.dumps({"12345": 777}))
    with m.db() as con:
        key = mb.basket_key_for_offer(con, url, "Gran Canaria", _day(37))
    assert key == "Mai auf Gran Canaria"
