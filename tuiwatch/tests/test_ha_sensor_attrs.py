"""Tests für die Größe der Markttrend-Sensor-Attribute.

Home Assistant verwirft einen State, dessen Attribute serialisiert 16384 Bytes
überschreiten — ohne Fehler im Add-on, der Sensor friert einfach auf dem alten Wert
ein. Genau das war passiert, als je Messreihe die vollständigen Trend-, Index-,
Ampel- und Tiefpunkt-Objekte mitgeschickt wurden. Diese Tests halten fest, dass die
Attribute flach bleiben und dass die Notbremse greift, statt still zu scheitern.
"""
import importlib
import json

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


def _row(name="Kreta Mai 2026"):
    """Eine Barometer-Zeile in voller Tiefe, wie `basket_payload` sie liefert."""
    return {
        "region": name, "period": "01.05.2026 – 31.05.2026", "closed": False,
        "last_day": "2026-08-14",
        "trend": {"dir": "down", "pct": -3.8, "days": 4, "n": 56, "hotels": 210},
        "index": {"index": 100.4, "pct": 0.4, "since": 1784297369, "n": 113},
        "signal": {"basket": name, "days_to_dep": 74, "closed": False,
                   "ampel": "green", "score": 0.51, "note": "",
                   "components": {
                       "trend": {"value": 0.76, "pct": -3.8, "dir": "down",
                                 "weight": 0.25, "n": 14},
                       "position": {"value": 0.4, "rank": 30.0, "n": 113,
                                    "index": 100.4, "weight": 0.35},
                       "expected": {"value": 0.5, "pct": 5.0, "coverage": 0.82,
                                    "weight": 0.4}}},
        "level": {"day": "2026-08-14", "n_hotels": 210, "p25": 900.0,
                  "p50": 1150.0, "p75": 1400.0},
        "trough": {"basket": name, "first_day": "2026-06-15", "last_day": "2026-08-14",
                   "n_days": 50, "first_dte": 120, "last_dte": 70,
                   "trough_day": "2026-07-10", "trough_dte": 105,
                   "trough_index": 95.0, "end_index": 100.4, "gain_pct": 5.7,
                   "trough_p50": 1100.0, "edge_start": False, "censored": True,
                   "usable": False},
    }


def _size(attrs):
    return len(json.dumps(attrs, default=str, ensure_ascii=False).encode("utf-8"))


# ── Verdichtung ───────────────────────────────────────────────────────────────

def test_compact_region_keeps_only_scalars(m):
    c = m._compact_region(_row())
    assert c == {"region": "Kreta Mai 2026", "pct": -3.8, "dir": "down", "days": 4,
                 "index": 100.4, "ampel": "green", "days_to_dep": 74}
    assert all(not isinstance(v, (dict, list)) for v in c.values())


def test_compact_region_survives_missing_parts(m):
    """Eine Messreihe ohne Trend/Ampel darf nicht wegen fehlender Schlüssel kippen."""
    assert m._compact_region({"region": "Neu"}) == {"region": "Neu"}


def test_compact_region_omits_ampel_when_closed(m):
    r = _row()
    r["signal"] = {"ampel": None, "closed": True, "days_to_dep": 0, "components": {}}
    assert "ampel" not in m._compact_region(r)


def test_compaction_is_an_order_of_magnitude_smaller(m):
    """Der eigentliche Punkt: 20 Messreihen passen flach locker in die Grenze,
    ausführlich nicht."""
    rows = [_row(f"Ziel {i}") for i in range(20)]
    assert _size(rows) > m._HA_ATTR_LIMIT
    assert _size([m._compact_region(r) for r in rows]) < m._HA_ATTR_LIMIT / 3


# ── Notbremse ─────────────────────────────────────────────────────────────────

def test_fit_leaves_small_attrs_alone(m):
    attrs = {"friendly_name": "TUIWatch Markttrend", "index": 100.4,
             "baskets": [{"region": "Kreta", "pct": -3.8}]}
    before = dict(attrs)
    m._fit_ha_attrs(attrs)
    assert attrs == before and "truncated" not in attrs


def test_fit_drops_the_growing_lists_first(m):
    attrs = {"index": 100.4, "booking_curve": [{"window": "90–61 Tage", "pct": -7.0}],
             "baskets": [_row(f"Z {i}") for i in range(40)],
             "by_region": [{"region": "R", "pct": 1.0}]}
    m._fit_ha_attrs(attrs)
    assert "baskets" not in attrs
    assert attrs["truncated"] == ["baskets"]
    assert "booking_curve" in attrs and "by_region" in attrs, \
        "die feste Kurve wird zuletzt geopfert"


def test_fit_keeps_going_until_it_fits(m):
    attrs = {"baskets": [_row(f"A {i}") for i in range(40)],
             "by_region": [_row(f"B {i}") for i in range(40)],
             "booking_curve": [{"window": "x", "pct": 1.0}]}
    m._fit_ha_attrs(attrs)
    assert _size(attrs) <= m._HA_ATTR_LIMIT
    assert attrs["truncated"] == ["baskets", "by_region"]


def test_fit_reports_what_it_dropped(m, caplog):
    """Ein stilles Weglassen wäre schlimmer als das Problem — man suchte das
    fehlende Attribut in der falschen Ecke."""
    attrs = {"baskets": [_row(f"Z {i}") for i in range(40)]}
    with caplog.at_level("WARNING"):
        m._fit_ha_attrs(attrs)
    assert "baskets" in " ".join(r.getMessage() for r in caplog.records)


# ── Zusammenspiel ─────────────────────────────────────────────────────────────

def test_booking_attrs_stay_flat(m):
    """`booking` mit allen Komponenten war der zweite große Brocken — es ist raus,
    die Kurve auf zwei Felder je Fenster gekürzt."""
    attrs = {}
    basket = {
        "by_region": [_row("Kreta"), _row("Rhodos")],
        "troughs": {"ready": True, "n": 6, "median_dte": 30, "p25_dte": 28,
                    "p75_dte": 32, "median_gain": 19.6},
        "booking": {"enabled": True, "curve": [
            {"label": "90–61 Tage", "rate": -0.1, "pct": -3.0, "n": 40,
             "n_series": 5, "thin": False},
            {"label": "unter 8 Tage", "rate": None, "pct": None, "n": 0,
             "n_series": 0, "thin": False}]},
    }
    m._booking_attrs(attrs, basket)
    assert "booking" not in attrs, "die vollen Signal-Objekte gehören nicht in den Sensor"
    assert attrs["booking_curve"] == [{"window": "90–61 Tage", "pct": -3.0}], \
        "Fenster ohne Daten fallen raus statt als null-Zeilen Platz zu kosten"
    assert attrs["booking_green"] == ["Kreta", "Rhodos"]
    assert attrs["booking_ampel"] == "green" and attrs["trough_median_days"] == 30
