"""Tests für das Tiefpunkt-Archiv (`market_basket.trough_of` / `trough_stats`).

Die heikle Stelle ist nicht das Minimum-Suchen, sondern die **Zensierung**: ein
Tiefpunkt am Rand der Beobachtung ist keine Erkenntnis, sondern ein Artefakt der
Messdauer. Ginge er in die Statistik ein, verschöbe sich der „typische
Buchungszeitpunkt" systematisch — links in Richtung Messbeginn, rechts weg von der
Abreise. Dazu die Frage, die den Bau ausgelöst hat: der Tiefpunkt muss das Löschen
der Messreihe überleben.
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
    mod = importlib.import_module("market_basket")
    mod._invalidate_curve()
    return mod


@pytest.fixture
def client(m, monkeypatch):
    monkeypatch.setattr(m, "_auth_ok", lambda req: True)
    m.app.config["TESTING"] = True
    return m.app.test_client()


def _day(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


def _series(m, basket, pcts, *, start_dte, start_offset=None):
    """Tagesbewegungen anlegen. `pcts[i]` gehört zum Tag `start_offset+i`, der Vorlauf
    zählt von `start_dte` herunter."""
    off = start_offset if start_offset is not None else -len(pcts)
    with m.db() as con:
        for i, p in enumerate(pcts):
            con.execute(
                "INSERT OR REPLACE INTO basket_moves (ts, day, basket, prev_day, gap_days, "
                "pct_median, n_matched, n_total, days_to_dep) VALUES (?,?,?,?,?,?,?,?,?)",
                (int(time.time()), _day(off + i), basket, _day(off + i - 1), 1,
                 p, 20, 20, start_dte - i))


def _levels(m, basket, day, dte, p50):
    with m.db() as con:
        con.execute(
            "INSERT OR REPLACE INTO basket_levels (ts, day, basket, days_to_dep, "
            "n_hotels, p25, p50, p75) VALUES (?,?,?,?,?,?,?,?)",
            (int(time.time()), day, basket, dte, 20, p50 * 0.9, p50, p50 * 1.1))


def _of(m, mb, basket):
    with m.db() as con:
        return mb.trough_of(con, basket)


# ── Der Tiefpunkt selbst ──────────────────────────────────────────────────────

def test_trough_is_the_minimum_of_the_chained_index(m, mb):
    """Runter, runter, hoch: der Tiefpunkt ist der Tag VOR dem Anstieg, nicht der
    letzte fallende Prozentwert."""
    # 12 Tage: 5× −1 %, dann 7× +1 %. Minimum nach dem fünften Tag.
    _series(m, "Kreta", [-1.0] * 5 + [1.0] * 7, start_dte=60)
    t = _of(m, mb, "Kreta")
    assert t["trough_day"] == _day(-12 + 4)
    assert t["trough_dte"] == 60 - 4
    assert t["trough_index"] == pytest.approx(100 * 0.99 ** 5, abs=0.05)


def test_gain_is_what_waiting_would_have_cost(m, mb):
    _series(m, "Kreta", [-10.0] + [0.0] * 8 + [10.0], start_dte=60)
    t = _of(m, mb, "Kreta")
    # Index 90 am Tiefpunkt, 99 am Ende → Warten kostete 10 %.
    assert t["gain_pct"] == pytest.approx(10.0, abs=0.1)


def test_trough_ignores_the_hotel_mix(m, mb):
    """Der Grund für die Rechnung auf dem verketteten Index: ein eingestreutes
    Billighotel drückt den Median-PREIS, ohne dass der Markt sich bewegt hätte.
    `basket_levels` zeigt dort sein Minimum, der Tiefpunkt darf ihm nicht folgen."""
    _series(m, "Kreta", [-1.0] * 5 + [1.0] * 7, start_dte=60)
    for i in range(12):
        # Preisniveau bricht an Tag 10 ein, obwohl die Tagesbewegung +1 % war.
        _levels(m, "Kreta", _day(-12 + i), 60 - i, 400.0 if i == 9 else 1000.0)
    t = _of(m, mb, "Kreta")
    assert t["trough_day"] == _day(-8), "Tiefpunkt folgt dem Index, nicht dem Rohpreis"
    assert t["trough_p50"] == 1000.0


def test_ties_take_the_earliest_day(m, mb):
    """Bei gleichem Index zählt die erste Gelegenheit — man kann nicht rückwirkend
    zum zweiten identischen Tiefpunkt buchen."""
    _series(m, "Kreta", [-5.0] + [0.0] * 9, start_dte=60)
    t = _of(m, mb, "Kreta")
    assert t["trough_day"] == _day(-10)


def test_short_series_has_no_trough(m, mb):
    _series(m, "Kreta", [-1.0], start_dte=60)
    assert _of(m, mb, "Kreta") is None


def test_lead_time_falls_back_to_levels(m, mb):
    """Fehlt der Vorlauf an der Tagesbewegung (Altbestand vor der Booking-Fassung),
    springt `basket_levels` ein."""
    _series(m, "Kreta", [-1.0] * 5 + [1.0] * 7, start_dte=60)
    with m.db() as con:
        con.execute("UPDATE basket_moves SET days_to_dep=NULL WHERE basket='Kreta'")
    for i in range(12):
        _levels(m, "Kreta", _day(-12 + i), 60 - i, 1000.0)
    assert _of(m, mb, "Kreta")["trough_dte"] == 56


# ── Zensierung ────────────────────────────────────────────────────────────────

def test_trough_on_the_first_day_is_marked_left_censored(m, mb):
    """Nur steigende Preise: das Minimum ist der Messbeginn — über den echten
    Tiefpunkt sagt das nichts."""
    _series(m, "Kreta", [1.0] * 12, start_dte=40)
    t = _of(m, mb, "Kreta")
    assert t["edge_start"] is True and t["usable"] is False


def test_observation_ending_far_from_departure_is_right_censored(m, mb):
    """Beobachtung endet 90 Tage vor Abreise — der Tiefpunkt kann noch kommen."""
    _series(m, "Kreta", [-1.0] * 3 + [1.0] * 9, start_dte=101)
    t = _of(m, mb, "Kreta")
    assert t["last_dte"] == 90
    assert t["censored"] is True and t["usable"] is False


def test_running_series_is_censored_by_construction(m, mb):
    """Eine laufende Messreihe braucht keine Sonderbehandlung: ihr letzter
    Beobachtungstag liegt zwangsläufig weit vor der Abreise."""
    _series(m, "Kreta", [-1.0] * 3 + [1.0] * 9, start_dte=200, start_offset=-12)
    assert _of(m, mb, "Kreta")["censored"] is True


def test_complete_observation_is_usable(m, mb):
    _series(m, "Kreta", [-1.0] * 3 + [1.0] * 9, start_dte=20)
    t = _of(m, mb, "Kreta")
    assert t["last_dte"] == 9 and t["edge_start"] is False
    assert t["censored"] is False and t["usable"] is True


def test_too_few_days_is_not_usable(m, mb):
    """Zwischen BASKET_MIN_DAYS (Tiefpunkt wird gezeigt) und TROUGH_MIN_DAYS
    (Tiefpunkt zählt in der Statistik) liegt bewusst eine Lücke."""
    _series(m, "Kreta", [1.0, -1.0, -1.0], start_dte=20)
    t = _of(m, mb, "Kreta")
    assert t is not None and t["n_days"] == 3 and t["usable"] is False


# ── Archiv: fortschreiben, überleben ──────────────────────────────────────────

def _rows(m):
    with m.db() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM basket_troughs ORDER BY first_day").fetchall()]


def test_update_keeps_one_row_per_recording(m, mb):
    _series(m, "Kreta", [-1.0] * 5 + [1.0] * 7, start_dte=60)
    with m.db() as con:
        assert mb._update_trough(con, "Kreta", 12345, "Kreta") is True
        assert mb._update_trough(con, "Kreta", 12345, "Kreta") is True
    assert len(_rows(m)) == 1


def test_restarted_recording_gets_its_own_row(m, mb):
    """Nach dem Löschen läuft dieselbe Suche unter demselben Namen weiter — die alte
    Erkenntnis darf davon nicht überschrieben werden."""
    _series(m, "Kreta", [-1.0] * 5 + [1.0] * 7, start_dte=60, start_offset=-200)
    with m.db() as con:
        mb._update_trough(con, "Kreta", 12345, "Kreta")
        con.execute("DELETE FROM basket_moves WHERE basket='Kreta'")
    _series(m, "Kreta", [1.0] * 12, start_dte=60, start_offset=-20)
    with m.db() as con:
        mb._update_trough(con, "Kreta", 12345, "Kreta")
    rows = _rows(m)
    assert len(rows) == 2
    assert rows[0]["first_day"] == _day(-200) and rows[1]["first_day"] == _day(-20)


def test_region_survives_an_update_without_region(m, mb):
    """Der Löschpfad ruft `_update_trough` ohne Region auf — `INSERT OR REPLACE`
    würde sie sonst ausnullen und die Regions-Statistik zerlegen."""
    _series(m, "Kreta", [-1.0] * 5 + [1.0] * 7, start_dte=60)
    with m.db() as con:
        mb._update_trough(con, "Kreta", 12345, "Kreta")
        mb._update_trough(con, "Kreta")
    r = _rows(m)[0]
    assert r["region_giata"] == 12345 and r["region"] == "Kreta"


def test_deleting_a_series_keeps_its_trough(m, mb, client):
    """Die eigentliche Anforderung: die Erkenntnis überlebt die Rohdaten."""
    _series(m, "Kreta", [-1.0] * 3 + [1.0] * 9, start_dte=20)
    with m.db() as con:
        mb._update_trough(con, "Kreta", 12345, "Kreta")
    r = client.delete("/api/market-basket/region", json={"region": "Kreta"})
    assert r.status_code == 200
    assert r.get_json()["troughs_kept"] == 1
    with m.db() as con:
        assert con.execute("SELECT COUNT(*) c FROM basket_moves").fetchone()["c"] == 0
    assert len(_rows(m)) == 1


def test_delete_writes_the_trough_before_dropping_the_data(m, mb, client):
    """Ohne das Fortschreiben ginge der Teil verloren, der seit dem letzten
    Barometer-Lauf entstanden ist — bei einer nie gelaufenen Reihe alles."""
    _series(m, "Kreta", [-1.0] * 3 + [1.0] * 9, start_dte=20)
    assert _rows(m) == []
    client.delete("/api/market-basket/region", json={"region": "Kreta"})
    assert len(_rows(m)) == 1


def test_purge_removes_the_trough_too(m, mb, client):
    _series(m, "Kreta", [-1.0] * 3 + [1.0] * 9, start_dte=20)
    with m.db() as con:
        mb._update_trough(con, "Kreta", 12345, "Kreta")
    r = client.delete("/api/market-basket/region",
                      json={"region": "Kreta", "purge_troughs": True})
    assert r.get_json()["troughs_deleted"] == 1
    assert _rows(m) == []


def test_backfill_runs_once(m, mb):
    _series(m, "Kreta", [-1.0] * 5 + [1.0] * 7, start_dte=60)
    with m.db() as con:
        con.execute("DELETE FROM meta WHERE key='basket_trough_backfill'")
        mb._backfill_troughs(con)
    assert len(_rows(m)) == 1
    with m.db() as con:
        con.execute("DELETE FROM basket_troughs")
        mb._backfill_troughs(con)
    assert _rows(m) == [], "zweiter Lauf muss folgenlos bleiben"


# ── Statistik ─────────────────────────────────────────────────────────────────

def _usable(m, mb, basket, trough_dte, *, gain=5.0, region=1):
    """Eine auswertbare Archivzeile direkt anlegen — die Statistik liest nur das
    Archiv, nicht die Rohdaten."""
    with m.db() as con:
        con.execute(
            "INSERT OR REPLACE INTO basket_troughs (ts, basket, region_giata, region, "
            "first_day, last_day, n_days, first_dte, last_dte, trough_day, trough_dte, "
            "trough_index, end_index, gain_pct, trough_p50, edge_start, censored) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (int(time.time()), basket, region, "R", _day(-60), _day(-1), 30,
             120, 10, _day(-30), trough_dte, 95.0, 100.0, gain, 900.0, 0, 0))


def _stats(m, mb, region=None):
    with m.db() as con:
        return mb.trough_stats(con, region)


def test_stats_need_a_minimum_of_series(m, mb):
    for i in range(mb.TROUGH_MIN_SAMPLES - 1):
        _usable(m, mb, f"S{i}", 40 + i)
    s = _stats(m, mb)
    assert s["ready"] is False and s["n"] == mb.TROUGH_MIN_SAMPLES - 1


def test_stats_report_the_median_lead_time(m, mb):
    for i, dte in enumerate([20, 40, 50, 60, 100]):
        _usable(m, mb, f"S{i}", dte, gain=float(i))
    s = _stats(m, mb)
    assert s["ready"] is True and s["n"] == 5
    assert s["median_dte"] == 50 and s["min_dte"] == 20 and s["max_dte"] == 100
    assert s["median_gain"] == 2.0


def test_stats_exclude_censored_rows(m, mb):
    """Sechs Zeilen, aber nur die fünf unzensierten dürfen zählen — sonst zöge ein
    früh abgebrochener Verlauf den typischen Tiefpunkt nach vorn."""
    for i, dte in enumerate([20, 40, 50, 60, 100]):
        _usable(m, mb, f"S{i}", dte)
    _usable(m, mb, "abgebrochen", 300)
    with m.db() as con:
        con.execute("UPDATE basket_troughs SET censored=1 WHERE basket='abgebrochen'")
    assert _stats(m, mb)["n"] == 5


def test_stats_exclude_left_censored_rows(m, mb):
    for i, dte in enumerate([20, 40, 50, 60, 100]):
        _usable(m, mb, f"S{i}", dte)
    _usable(m, mb, "angeschnitten", 300)
    with m.db() as con:
        con.execute("UPDATE basket_troughs SET edge_start=1 WHERE basket='angeschnitten'")
    assert _stats(m, mb)["n"] == 5


def test_stats_can_be_narrowed_to_a_region(m, mb):
    for i, dte in enumerate([20, 40, 50, 60, 100]):
        _usable(m, mb, f"A{i}", dte, region=111)
    for i, dte in enumerate([10, 12, 14, 16, 18]):
        _usable(m, mb, f"B{i}", dte, region=222)
    assert _stats(m, mb)["n"] == 10
    assert _stats(m, mb, 222)["median_dte"] == 14


def test_payload_marks_usable_rows(m, mb):
    for i, dte in enumerate([20, 40, 50, 60, 100]):
        _usable(m, mb, f"S{i}", dte)
    _usable(m, mb, "roh", 300)
    with m.db() as con:
        con.execute("UPDATE basket_troughs SET edge_start=1 WHERE basket='roh'")
    p = mb.trough_payload()
    assert p["stats"]["ready"] is True
    assert sum(1 for r in p["rows"] if r["usable"]) == 5
    assert [r for r in p["rows"] if r["basket"] == "roh"][0]["usable"] is False
    assert p["by_region"][0]["giata"] == 1


def test_route_serves_the_archive(m, mb, client):
    _usable(m, mb, "Kreta", 50)
    r = client.get("/api/booking-troughs")
    assert r.status_code == 200
    d = r.get_json()
    assert d["min_samples"] == mb.TROUGH_MIN_SAMPLES
    assert d["rows"][0]["basket"] == "Kreta"
