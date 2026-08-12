"""Tests für fra_flights_client.py (Flugplan ab Frankfurt).

Der Netzwerk-Layer wird gemockt — geprüft werden die Eigenheiten des FRA-JSON,
die im echten Betrieb weh tun: kein Datumsfilter im API (deshalb Binärsuche über
die Seiten), 25 Einträge pro Seite ohne Einfluss, Freitext→IATA-Auflösung und die
Normalisierung der Trefferzeilen (siehe SCRAPING_FRA.md).
"""
from datetime import datetime, timedelta

import pytest

import fra_flights_client as fra


@pytest.fixture(autouse=True)
def _clear_cache():
    """Modul-Cache je Test leeren — sonst verfälschen frühere Aufrufe das Ergebnis."""
    fra._page_cache.clear()
    fra._airport_cache.clear()
    yield
    fra._page_cache.clear()
    fra._airport_cache.clear()


def _flight(day: int, no: str = "DE 1404") -> dict:
    d = datetime(2026, 8, 13) + timedelta(days=day)
    return {
        "sched": d.strftime("%Y-%m-%dT11:45:00+0200"),
        "schedArr": d.strftime("%Y-%m-%dT15:25:00+0000"),
        "fnr": no, "al": "DE", "alname": "Condor",
        "iata": "LPA", "apname": "Gran Canaria",
        "terminal": "1", "halle": "B", "gate": "B4", "schalter": "656-688",
        "ac": "A32B", "reg": "DAIAG", "duration": 280, "stops": 0,
        "cs": ["EK 3946", "EY 6925"],
    }


class _Resp:
    def __init__(self, data, status=200):
        self._d, self.status_code = data, status

    def json(self):
        return self._d


def _fake_api(monkeypatch, total_days: int = 250, calls: list | None = None):
    """25 Flüge je Seite, ein Flug pro Tag ab 13.08.2026 — wie das echte API
    chronologisch sortiert."""
    pages = [[_flight(d) for d in range(i, min(i + 25, total_days))]
             for i in range(0, total_days, 25)]

    def fake_get(url, params=None, **kw):
        params = params or {}
        if calls is not None:
            calls.append(params)
        if url.endswith("/search"):
            return _Resp({"airports": {"data": [
                {"id": "SPC", "name": "La Palma", "land": "Spain", "regionorg": "Süd-Europa"},
                {"id": "PMI", "name": "Palma de Mallorca", "land": "Spain",
                 "regionorg": "Süd-Europa"},
                {"id": "", "name": "kaputt"},        # ohne Code → wird verworfen
            ]}})
        page = int(params.get("page") or 1)
        items = pages[page - 1] if 1 <= page <= len(pages) else []
        return _Resp({"data": items, "results": total_days,
                      "maxpage": len(pages), "page": page, "entriesperpage": 25})

    monkeypatch.setattr(fra.requests, "get", fake_get)


def test_row_normalisation(monkeypatch):
    _fake_api(monkeypatch)
    res = fra.search_flights("LPA", date_till="2026-08")
    r = res["rows"][0]
    assert r["date"] == "2026-08-13" and r["time"] == "11:45"
    # schedArr trägt einen falschen Offset (+0000) — nur die Uhrzeit zählt
    assert r["arrival"] == "15:25"
    assert r["flight_no"] == "DE 1404" and r["airline_name"] == "Condor"
    assert r["terminal"] == "1" and r["gate"] == "B4" and r["checkin"] == "656-688"
    assert r["aircraft"] == "A32B" and r["duration_min"] == 280 and r["stops"] == 0
    assert r["codeshares"] == ["EK 3946", "EY 6925"]


def test_iata_code_skips_airport_search(monkeypatch):
    calls: list = []
    _fake_api(monkeypatch, calls=calls)
    res = fra.search_flights("LPA", date_till="2026-08")
    assert res["airports"] == [{"code": "LPA", "name": "", "country": "", "region": ""}]
    assert not any("q" in c for c in calls), "IATA-Code braucht keine Flughafen-Suche"


def test_freitext_resolves_to_multiple_codes(monkeypatch):
    calls: list = []
    _fake_api(monkeypatch, calls=calls)
    res = fra.search_flights("Palma", date_till="2026-08")
    assert [a["code"] for a in res["airports"]] == ["SPC", "PMI"]
    # Mehrere Ziele gehen als kommagetrennte Liste in EINEN Filter-Aufruf
    assert any(c.get("airport") == "SPC,PMI" for c in calls)


def test_month_range_filters_rows(monkeypatch):
    _fake_api(monkeypatch)
    res = fra.search_flights("LPA", date_from="2026-11", date_till="2026-11")
    assert res["rows"], "November muss Treffer haben"
    assert all(r["date"][:7] == "2026-11" for r in res["rows"])
    assert len(res["rows"]) == 30           # ein Flug je Novembertag


def test_start_page_found_by_binary_search(monkeypatch):
    """Ohne Datumsfilter im API muss die Startseite gesucht werden — aber nicht
    Seite für Seite (das wären bei 10 Seiten Vorlauf 10 Abrufe)."""
    calls: list = []
    _fake_api(monkeypatch, calls=calls)
    fra.search_flights("LPA", date_from="2026-12", date_till="2026-12")
    pages = [int(c["page"]) for c in calls if "page" in c]
    assert 1 not in pages[1:], "Seite 1 nur einmal (Kopfdaten)"
    assert len(pages) < 10, f"zu viele Seitenabrufe: {pages}"


def test_truncation_flag(monkeypatch):
    _fake_api(monkeypatch, total_days=1000)
    res = fra.search_flights("LPA")
    assert len(res["rows"]) == 300          # 12 Seiten × 25
    assert res["truncated"] is True


def test_arrivals_type_passed_through(monkeypatch):
    calls: list = []
    _fake_api(monkeypatch, calls=calls)
    fra.search_flights("LPA", flight_type="arrivals", date_till="2026-08")
    assert all(c.get("flighttype") == "arrivals" for c in calls if "flighttype" in c)
    # Alles außer 'arrivals' fällt auf 'departures' zurück (das API antwortet auf
    # ungültige Werte mit HTML statt JSON)
    calls.clear()
    fra.search_flights("LPA", flight_type="bogus", date_till="2026-08")
    assert all(c.get("flighttype") == "departures" for c in calls if "flighttype" in c)


def test_http_error_returns_none(monkeypatch):
    monkeypatch.setattr(fra.requests, "get",
                        lambda *a, **kw: _Resp({}, status=503))
    assert fra.search_flights("LPA") is None
    assert fra.search_airports("Palma") is None


def test_empty_query_short_circuits(monkeypatch):
    monkeypatch.setattr(fra.requests, "get",
                        lambda *a, **kw: pytest.fail("kein Abruf bei leerer Suche"))
    assert fra.search_flights("")["rows"] == []
    assert fra.search_airports("a") == []
