"""Flugvarianten (v0.91.0): dieselbe Reise, unterschiedliche Flüge.

Die Angebots-API liefert für einen Zeitraum mehrere Offers, die sich nur im Flug
unterscheiden (früher/mehr Stopps ist meist billiger). Getrackt wird weiter der
günstigste — die Varianten werden zusätzlich ausgewiesen und lassen sich per
`flight_pin` fixieren.
"""
import copy

import scraper


def _offers(fx):
    """Zwei Varianten aus der echten Fixture: günstig+2 Stopps vs. teurer+direkt."""
    data = copy.deepcopy(fx("offer.json"))
    cheap, late = data["offers"][0], data["offers"][1]
    cheap["cheapest"] = True
    cheap["calculatedPricePerPerson"] = 1452
    cheap["departure"]["stopOver"] = 2
    late["cheapest"] = False
    late["calculatedPricePerPerson"] = 1520
    late["departure"]["stopOver"] = 0
    late["departure"]["departureDateTime"] = "2026-08-12T15:40:00.000+02:00"
    late["departure"]["airline"] = {"value": "Eurowings", "code": "EW"}
    data["offers"] = [cheap, late]
    return data


def test_flight_key_stable(fx):
    o = _offers(fx)["offers"][0]
    assert scraper._flight_key(o) == "X3|2|06:20|2026-08-12"


def test_flight_options_sorted_with_delta(fx):
    data = _offers(fx)
    offers = data["offers"]
    opts = scraper._flight_options(offers, offers[0])
    assert [o["price"] for o in opts] == [1452.0, 1520.0]
    assert [o["delta"] for o in opts] == [0.0, 68.0]
    assert [o["selected"] for o in opts] == [True, False]
    assert opts[1]["stops_out"] == 0 and opts[1]["airline"] == "Eurowings"
    # Aufpreis wird gegen die *getrackte* Variante gerechnet, nicht gegen die günstigste
    opts2 = scraper._flight_options(offers, offers[1])
    assert [o["delta"] for o in opts2] == [-68.0, 0.0]


def _patch_api(monkeypatch, fx, fake_resp, data):
    def fake_get(u, **kw):
        if scraper.OFFER_API in u:
            return fake_resp(data)
        if scraper.CONTENT_API in u:
            return fake_resp(fx("rating.json"))
        if u.startswith(scraper.BREADCRUMB_API):
            return fake_resp(fx("breadcrumb.json"))
        return fake_resp({}, 404)
    monkeypatch.setattr(scraper.requests, "get", fake_get)


URL = ("https://www.tui.com/pauschalreisen/suchen/angebote/Riu-Funana/259516/offer/"
       "?startDate=2026-08-12&endDate=2026-08-19&duration=7&travellers=2")


def test_pin_selects_other_flight(monkeypatch, fx, fake_resp):
    _patch_api(monkeypatch, fx, fake_resp, _offers(fx))

    r = scraper.fetch_price_api(URL, vacancy=False)
    assert r["price"] == 1452.0 and r["flight_pin_missed"] is False
    assert len(r["flight_options"]) == 2

    r2 = scraper.fetch_price_api(URL, vacancy=False, flight_pin="EW|0|15:40|2026-08-12")
    assert r2["price"] == 1520.0            # teurere, aber direkte Variante
    assert r2["flight_pin_missed"] is False
    assert "Eurowings" in r2["flight_out"] and "Direktflug" in r2["flight_out"]


def test_pin_gone_falls_back_to_cheapest(monkeypatch, fx, fake_resp):
    _patch_api(monkeypatch, fx, fake_resp, _offers(fx))
    r = scraper.fetch_price_api(URL, vacancy=False, flight_pin="LH|1|09:00|2026-08-12")
    assert r["price"] == 1452.0             # Fixierung ins Leere → günstigster Flug
    assert r["flight_pin_missed"] is True
