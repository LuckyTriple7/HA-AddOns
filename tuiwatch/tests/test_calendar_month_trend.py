"""Tests für den Monatstrend des Preiskalenders (`price_calendar`).

Kein Netz. Der Fokus liegt auf der einen Stelle, an der die Rechnung kippen kann:
`calendar_history` ist delta-codiert, ein Reisetag ohne Zeile ist ein **unveränderter**
Tag, kein unbeobachteter. Zählt man nur die geänderten Tage, misst man ausschliesslich
Bewegung und der Index läuft davon. Dazu die Artefakt-Sperre, die Baseline und der
Carry-Forward-Backfill.
"""
import importlib
import time
from datetime import date, datetime, timedelta

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
    with mod.db() as con:
        con.execute("INSERT INTO offers (url, label, created) VALUES (?,?,?)",
                    ("https://www.tui.com/pauschalreisen/angebote/h/1/?duration=7",
                     "Testhotel", int(time.time())))
    return mod


@pytest.fixture
def pc(m):
    return importlib.import_module("price_calendar")


def _day(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


def _ts(offset_days: int) -> int:
    d = datetime.now() + timedelta(days=offset_days)
    return int(d.replace(hour=9, minute=0, second=0, microsecond=0).timestamp())


def _cal(prices: dict) -> dict:
    return {"ok": True, "days": [{"date": d, "price": p} for d, p in sorted(prices.items())]}


def _store(m, pc, prices, ts):
    """Kalender-Snapshot ablegen, als waere er zum Zeitpunkt `ts` abgerufen worden."""
    with m.db() as con:
        real_ts = int(time.time())
        pc._store_calendar_snapshot(con, 1, _cal(prices))
        # Der Schreibpfad stempelt mit "jetzt" — fuer die Zeitachse umdatieren.
        con.execute("UPDATE calendar_cache SET ts=? WHERE offer_id=1 AND ts=?", (ts, real_ts))
        con.execute("UPDATE calendar_history SET ts=? WHERE offer_id=1 AND ts=?", (ts, real_ts))
        day = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        con.execute("UPDATE calendar_month_moves SET ts=?, day=? WHERE offer_id=1 AND ts=?",
                    (ts, day, real_ts))


# ── Aggregation ────────────────────────────────────────────────────────────────

def test_unchanged_days_dampen_the_month(pc):
    """Der Kern: 1 von 10 Reisetagen steigt um 100 EUR. Das ist eine
    Monatsbewegung von ~1 %, nicht von 10 % — die neun ruhigen Tage gehoeren in den
    Nenner. Genau hier wuerde eine Auswertung nur der Delta-Zeilen falsch liegen."""
    prev = {f"2027-05-{d:02d}": 1000.0 for d in range(1, 11)}
    new = dict(prev)
    new["2027-05-01"] = 1100.0
    agg = pc._month_aggregate(prev, new, _day(0))
    pct, n_days, n_changed, sum_prev = agg["2027-05"]
    assert n_days == 10 and n_changed == 1
    assert sum_prev == 10000.0
    assert pct == pytest.approx(1.0, abs=0.001)


def test_quiet_month_is_zero_not_missing(pc):
    prev = {f"2027-05-{d:02d}": 900.0 for d in range(1, 6)}
    agg = pc._month_aggregate(prev, dict(prev), _day(0))
    assert agg["2027-05"][0] == 0.0
    assert agg["2027-05"][1] == 5      # beobachtet, nicht fehlend


def test_new_and_vanished_dates_are_excluded(pc):
    """Ein neu ins Fenster gerutschter Reisetag hat keinen Vergleichswert, ein
    herausgefallener keinen aktuellen — beide duerfen die Monatsbewegung nicht
    beeinflussen (sonst misst man die Fensterwanderung statt den Preis)."""
    prev = {"2027-05-01": 1000.0, "2027-05-02": 1000.0, "2027-05-03": 500.0}
    new = {"2027-05-01": 1000.0, "2027-05-02": 1000.0, "2027-05-04": 5000.0}
    pct, n_days, _ch, sum_prev = pc._month_aggregate(prev, new, _day(0))["2027-05"]
    assert n_days == 2 and sum_prev == 2000.0 and pct == 0.0


def test_absurd_jump_is_dropped_as_artifact(pc):
    prev = {f"2027-05-{d:02d}": 1000.0 for d in range(1, 11)}
    new = dict(prev)
    new["2027-05-01"] = 9000.0            # +800 %: Zimmerkategorie, kein Marktsignal
    pct, n_days, _ch, _sp = pc._month_aggregate(prev, new, _day(0))["2027-05"]
    assert n_days == 9 and pct == 0.0


def test_past_travel_dates_are_ignored(pc):
    prev = {_day(-5): 1000.0, _day(30): 1000.0}
    new = {_day(-5): 2000.0, _day(30): 1000.0}
    agg = pc._month_aggregate(prev, new, _day(0))
    assert all(v[1] == 1 for v in agg.values())      # nur der Zukunftstag zaehlt
    assert all(v[0] == 0.0 for v in agg.values())


def test_months_are_kept_apart(pc):
    prev = {"2027-05-01": 1000.0, "2027-06-01": 1000.0}
    new = {"2027-05-01": 1100.0, "2027-06-01": 900.0}
    agg = pc._month_aggregate(prev, new, _day(0))
    assert agg["2027-05"][0] == pytest.approx(10.0)
    assert agg["2027-06"][0] == pytest.approx(-10.0)


# ── Schreibpfad ────────────────────────────────────────────────────────────────

def test_first_fetch_writes_no_move(m, pc):
    """Der Erstabruf ist reine Baseline — ohne Vorwerte gibt es keine Bewegung."""
    _store(m, pc, {f"2027-05-{d:02d}": 1000.0 for d in range(1, 11)}, _ts(-3))
    with m.db() as con:
        assert con.execute("SELECT COUNT(*) c FROM calendar_month_moves").fetchone()["c"] == 0


def test_second_fetch_on_same_day_chains_within_the_day(m, pc):
    """Zwei Abrufe am selben Tag: 1000 -> 1100 -> 1200 auf einem von zehn Tagen sind
    zusammen +2 % Monatsbewegung. Wuerde die zweite Zeile die erste ersetzen, ginge
    der erste Schritt verloren und der Tag meldete nur +1 %."""
    base = {f"2027-05-{d:02d}": 1000.0 for d in range(1, 11)}
    _store(m, pc, base, _ts(-2))
    _store(m, pc, {**base, "2027-05-01": 1100.0}, _ts(0))
    _store(m, pc, {**base, "2027-05-01": 1200.0}, _ts(0))
    with m.db() as con:
        rows = con.execute("SELECT pct, n_changed FROM calendar_month_moves "
                           "WHERE month='2027-05'").fetchall()
    assert len(rows) == 1                       # ein Tageswert, nicht zwei
    assert rows[0]["pct"] == pytest.approx(2.0, abs=0.02)
    assert rows[0]["n_changed"] == 2


def test_repeated_identical_fetch_changes_nothing(m, pc):
    """Der Verkettung darf ein unveraenderter Zweitabruf nicht schaden."""
    base = {f"2027-05-{d:02d}": 1000.0 for d in range(1, 11)}
    _store(m, pc, base, _ts(-2))
    _store(m, pc, {**base, "2027-05-01": 1100.0}, _ts(0))
    _store(m, pc, {**base, "2027-05-01": 1100.0}, _ts(0))
    with m.db() as con:
        pct = con.execute("SELECT pct FROM calendar_month_moves "
                          "WHERE month='2027-05'").fetchone()["pct"]
    assert pct == pytest.approx(1.0, abs=0.01)


# ── Trend und Index ────────────────────────────────────────────────────────────

def test_trend_and_index_chain_daily_values(m, pc):
    """Drei Tage mit je +1 % verketten sich auf ~3,03 %, nicht auf 3,0 —
    Zinseszins, wie beim Markttrend."""
    base = {f"2027-05-{d:02d}": 1000.0 for d in range(1, 11)}
    _store(m, pc, base, _ts(-4))
    for i, factor in enumerate((1.01, 1.0201, 1.030301), start=1):
        _store(m, pc, {d: round(1000.0 * factor, 2) for d in base}, _ts(-4 + i))
    with m.db() as con:
        t = pc.month_trend(con, 1, "2027-05")
        idx = pc.month_index(con, 1, "2027-05")
    assert t["n"] == 3 and t["dir"] == "up"
    assert t["pct"] == pytest.approx(3.0, abs=0.1)
    assert idx["index"] == pytest.approx(103.0, abs=0.1)


def test_trend_needs_two_observation_days(m, pc):
    base = {f"2027-05-{d:02d}": 1000.0 for d in range(1, 11)}
    _store(m, pc, base, _ts(-2))
    _store(m, pc, {**base, "2027-05-01": 1100.0}, _ts(-1))
    with m.db() as con:
        assert pc.month_trend(con, 1, "2027-05") is None     # nur EIN Bewegungstag


def test_quiet_days_hold_the_index_flat(m, pc):
    """Zehn ruhige Tage nach einem Anstieg: der Index bleibt oben, laeuft aber nicht
    weiter. Wuerden ruhige Tage als 'keine Daten' gelten, waere die Kette kuerzer und
    der Trend haette dieselben +1 % noch tagelang als frische Bewegung gezeigt."""
    base = {f"2027-05-{d:02d}": 1000.0 for d in range(1, 11)}
    _store(m, pc, base, _ts(-12))
    _store(m, pc, {d: 1010.0 for d in base}, _ts(-11))
    for i in range(10):
        _store(m, pc, {d: 1010.0 for d in base}, _ts(-10 + i))
    with m.db() as con:
        t = pc.month_trend(con, 1, "2027-05")
        idx = pc.month_index(con, 1, "2027-05")
    # Streak = Anstiegstag plus die zehn ruhigen danach: seit 11 Tagen nichts
    # Gegenlaeufiges. Mit der strengen Zaehlweise des Barometers stuende hier 0.
    assert t["n"] == 11 and t["days"] == 11
    assert idx["index"] == pytest.approx(101.0, abs=0.05)


# ── Payload ────────────────────────────────────────────────────────────────────

def test_payload_lists_future_months_with_level_and_trend(m, pc):
    prices = {**{f"2027-05-{d:02d}": 1000.0 for d in range(1, 11)},
              **{f"2027-06-{d:02d}": 2000.0 for d in range(1, 11)}}
    _store(m, pc, prices, _ts(-3))
    _store(m, pc, {**prices, "2027-05-01": 1100.0}, _ts(-2))
    _store(m, pc, {**prices, "2027-05-01": 1200.0}, _ts(-1))
    p = pc.month_payload(1)
    months = {x["month"]: x for x in p["months"]}
    assert set(months) == {"2027-05", "2027-06"}
    assert months["2027-06"]["avg"] == 2000
    assert months["2027-05"]["trend"]["dir"] == "up"
    assert months["2027-06"]["trend"]["dir"] == "flat"
    assert p["observations"] == 2


def test_payload_without_calendar(m, pc):
    assert pc.month_payload(1)["months"] == []


# ── Backfill ───────────────────────────────────────────────────────────────────

def test_backfill_reconstructs_from_history_and_is_idempotent(m, pc):
    """Bestandsdaten: `calendar_month_moves` wird geleert und muss sich per
    Carry-Forward vollstaendig aus `calendar_history` wiederherstellen lassen."""
    base = {f"2027-05-{d:02d}": 1000.0 for d in range(1, 11)}
    _store(m, pc, base, _ts(-3))
    _store(m, pc, {**base, "2027-05-01": 1100.0}, _ts(-2))
    _store(m, pc, {**base, "2027-05-01": 1100.0, "2027-05-02": 1100.0}, _ts(-1))
    with m.db() as con:
        live = [(r["day"], r["pct"], r["n_days"]) for r in con.execute(
            "SELECT day, pct, n_days FROM calendar_month_moves ORDER BY day").fetchall()]
        con.execute("DELETE FROM calendar_month_moves")
        con.execute("DELETE FROM meta WHERE key='calendar_month_backfill'")
        pc._backfill_month_moves(con)
        back = [(r["day"], r["pct"], r["n_days"]) for r in con.execute(
            "SELECT day, pct, n_days FROM calendar_month_moves ORDER BY day").fetchall()]
    assert back == live
    with m.db() as con:
        pc._backfill_month_moves(con)      # Flag steht -> no-op
        assert con.execute("SELECT COUNT(*) c FROM calendar_month_moves").fetchone()["c"] == len(back)
