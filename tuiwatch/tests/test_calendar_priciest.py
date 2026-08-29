"""Tests für den teuersten Termin im Preiskalender.

Der günstigste Termin wurde schon immer ausgewiesen — ohne sein Gegenstück sagt er
aber nichts darüber, wie viel die Wahl des Reisedatums überhaupt ausmacht.
"""
import importlib
import json
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


DAYS = [{"date": "2027-03-01", "price": 900},
        {"date": "2027-03-08", "price": 1500},
        {"date": "2027-03-15", "price": 1200}]


def _store(m, offer_id, cal):
    """Angebot mit **explizit** dieser id anlegen, dann den Kalender daran hängen.

    Ohne die feste id vergibt SQLite fortlaufend ab 1, und der Kalender hing an
    einer offer_id, die es gar nicht gab. Das fiel nie auf, solange die
    Fremdschlüssel nicht erzwungen wurden — jetzt schon."""
    with m.db() as con:
        con.execute("INSERT INTO offers (id, url, created) VALUES (?,?,?)",
                    (offer_id, f"https://x.invalid/angebote/H/{offer_id}/", int(time.time())))
        con.execute("INSERT OR REPLACE INTO calendar_cache (offer_id, ts, data) VALUES (?,?,?)",
                    (offer_id, int(time.time()), json.dumps(cal)))


def test_payload_reports_the_priciest_date(m):
    price_calendar = importlib.import_module("price_calendar")
    _store(m, 1, {"ok": True, "days": DAYS, "cheapest_date": "2027-03-01",
                  "cheapest_price": 900, "priciest_date": "2027-03-08",
                  "priciest_price": 1500})
    out = price_calendar._calendar_payload(1)
    assert out["priciest_date"] == "2027-03-08" and out["priciest_price"] == 1500


def test_old_snapshots_get_the_priciest_computed(m):
    """Kalender, die vor dieser Änderung abgerufen wurden, haben das Feld nicht —
    es wird aus den Tagesdaten nachgerechnet, statt einen Neuabruf zu verlangen."""
    price_calendar = importlib.import_module("price_calendar")
    _store(m, 2, {"ok": True, "days": DAYS, "cheapest_date": "2027-03-01",
                  "cheapest_price": 900})
    out = price_calendar._calendar_payload(2)
    assert out["priciest_date"] == "2027-03-08" and out["priciest_price"] == 1500


def test_empty_calendar_has_no_priciest(m):
    price_calendar = importlib.import_module("price_calendar")
    _store(m, 3, {"ok": True, "days": []})
    out = price_calendar._calendar_payload(3)
    assert "priciest_date" not in out


def test_scraper_sets_both_extremes(monkeypatch):
    """Direkt beim Abruf mitgeliefert, damit neue Snapshots das Feld gespeichert
    haben und der Fallback im Payload nur für Altdaten greifen muss."""
    scraper = importlib.import_module("scraper")
    offers = [{"arrivalDate": "2027-03-01", "calculatedPricePerPerson": 900},
              {"arrivalDate": "2027-03-08", "calculatedPricePerPerson": 1500},
              {"arrivalDate": "2027-03-15", "calculatedPricePerPerson": 1200}]

    class R:
        status_code = 200

        @staticmethod
        def json():
            return {"currency": "EUR", "offers": offers}

    monkeypatch.setattr(scraper.requests, "get", lambda *a, **k: R())
    monkeypatch.setattr(scraper.requests, "post", lambda *a, **k: R())
    res = scraper.fetch_calendar("https://www.tui.com/angebote/H/1/?duration=7")
    assert res and res["ok"]
    assert res["cheapest_date"] == "2027-03-01" and res["cheapest_price"] == 900
    assert res["priciest_date"] == "2027-03-08" and res["priciest_price"] == 1500
