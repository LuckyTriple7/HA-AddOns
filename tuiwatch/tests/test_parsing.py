"""Regressionstests für die Parsing-/Normalisierungslogik in scraper.py.

Die reinen Helfer werden direkt geprüft; die netzbehafteten Funktionen
(fetch_price_api, fetch_search, fetch_calendar, fetch_destinations, fetch_airports,
region_giata_from_breadcrumb) werden gegen **echte, reduzierte** TUI-Antworten aus
tests/fixtures/ getestet, indem requests.get/post gemonkeypatcht werden. So fällt sofort
auf, wenn eine Code-Änderung die Auswertung dieser Antworten verändert."""
import scraper


# ── Reine Helfer (kein Netzwerk) ────────────────────────────────────────────────

def test_single_duration():
    assert scraper._single_duration("9-12") == "9"
    assert scraper._single_duration("7-") == "7"
    assert scraper._single_duration("10") == "10"
    assert scraper._single_duration("") == ""


def test_duration_and_travellers_from_url():
    url = "https://www.tui.com/x/123/offer/?duration=9-12&travellers=3"
    assert scraper.duration_from_url(url) == 9
    assert scraper.travellers_from_url(url) == 3
    assert scraper.travellers_from_url("https://www.tui.com/x/?foo=1") == 1


def test_hotel_and_giata_from_url():
    url = "https://www.tui.com/pauschalreisen/suchen/angebote/Riu-Funana/259516/offer/?x=1"
    assert scraper.hotel_from_url(url) == "Riu Funana"
    assert scraper._giata_from_url(url) == "259516"


def test_with_duration_widens_narrow_window():
    # Aus dem Kalender getrackter Einzeltermin: Fenster = genau 7 Nächte
    u = ("https://www.tui.com/x/259516/offer/"
         "?startDate=2027-01-14&endDate=2027-01-21&duration=7&travellers=1")
    # kürzere/gleiche Dauer: Fenster bleibt
    assert "endDate=2027-01-21" in scraper.with_duration(u, 7)
    # längere Dauer: endDate = startDate + n
    assert "endDate=2027-01-24" in scraper.with_duration(u, 10)
    assert "duration=10" in scraper.with_duration(u, 10)
    # breites Fenster bleibt unverändert
    w = ("https://www.tui.com/x/259516/offer/"
         "?startDate=2027-01-14&endDate=2027-06-30&duration=7&travellers=1")
    assert "endDate=2027-06-30" in scraper.with_duration(w, 10)


def test_with_travellers_and_without_room_code():
    u = "https://www.tui.com/x/?travellers=1&roomTypeOpCodes=DZX1&foo=2"
    assert "travellers=2" in scraper.with_travellers(u, 2)
    assert "roomTypeOpCodes" not in scraper.without_room_code(u)
    assert "foo=2" in scraper.without_room_code(u)


def test_to_amount():
    assert scraper._to_amount("1.452,00") == 1452.0
    assert scraper._to_amount("2.129 €".replace("€", "").strip()) == 2129.0
    assert scraper._to_amount("999") == 999.0
    assert scraper._to_amount("keine Zahl") is None


def test_map_board_types():
    assert scraper._map_board_types("AI") == "GT06-AI"
    assert scraper._map_board_types("AI,HP") == "GT06-AI,GT06-HP"
    assert scraper._map_board_types("GT06-AI") == "GT06-AI"
    assert scraper._map_board_types("") == ""


def test_slugify():
    assert scraper._slugify("Riu Funana") == "riu-funana"
    # deutsche Umlaute/ß werden transliteriert, Sonderzeichen zu '-' verdichtet
    assert scraper._slugify("Hotel Süd & Meer") == "hotel-sued-meer"
    assert scraper._slugify("Größe Straße") == "groesse-strasse"


def test_de_date_and_datetime():
    assert scraper._de_date("2027-05-01") == "01.05.2027"
    assert scraper._de_datetime("2027-05-01T07:35:00.000+02:00") == "01.05.2027, 07:35"
    assert scraper._de_date("") == ""


def test_search_params_from_url():
    url = ("https://www.tui.com/pauschalreisen/suchen/angebote/H/259516/offer/"
           "?startDate=2027-05-01&endDate=2027-05-30&duration=9-12&travellers=2"
           "&departureAirports=STR,FRA&boardTypes=AI&regionGiataIds=128"
           "&maxStopOvers=0&operators=TUID")
    p = scraper._search_params_from_url(url)
    assert p["regions"] == [128]
    assert p["duration"] == 9
    assert p["travellers"] == 2
    assert p["airports"] == ["STR", "FRA"]
    assert p["boards"] == ["AI"]
    assert p["operators"] == ["TUID"]      # operator_tui=True (Default)
    assert p["direct"] is True             # maxStopOvers=0
    # region-Override
    assert scraper._search_params_from_url(url, region=999)["regions"] == [999]


def test_offer_url_for():
    item = {"hotel": {"giataId": 123, "name": "Test Hotel"},
            "numberOfNights": 7, "boardCodes": ["AI"]}
    params = {"startDate": "2027-05-01", "endDate": "2027-05-08", "duration": 7,
              "travellers": 2, "airports": ["STR"], "operators": ["TUID"],
              "regions": [128], "direct": True}
    url = scraper.offer_url_for(item, params)
    assert "/angebote/test-hotel/123/offer/" in url
    assert "regionGiataIds=128" in url
    assert "duration=7" in url
    assert "travellers=2" in url
    assert "boardTypes=AI" in url
    assert "departureAirports=STR" in url
    assert "maxStopOvers=0" in url         # direct=True


# ── Netzbehaftete Normalisierung (gegen echte Fixtures, requests gemonkeypatcht) ──

def test_fetch_price_api(monkeypatch, fx, fake_resp):
    offer, rating, bc = fx("offer.json"), fx("rating.json"), fx("breadcrumb.json")

    def fake_get(u, **kw):
        if scraper.OFFER_API in u:
            return fake_resp(offer)
        if scraper.CONTENT_API in u:
            return fake_resp(rating)
        if u.startswith(scraper.BREADCRUMB_API):
            return fake_resp(bc)
        raise AssertionError("unerwartete URL: " + u)

    monkeypatch.setattr(scraper.requests, "get", fake_get)
    url = ("https://www.tui.com/pauschalreisen/suchen/angebote/Hotel-Riu-Funana/259516/"
           "offer/?startDate=2026-08-12&endDate=2026-08-19&duration=7&travellers=2")
    r = scraper.fetch_price_api(url)

    assert r["ok"] is True
    assert r["source"] == "api"
    assert r["hotel"] == "Hotel Riu Funana"
    assert r["price"] == 1452.0
    assert r["old_price"] == 1554.845
    assert r["discount"] == 7              # round((1554.845-1452)/1554.845*100)
    assert r["total_price"] == 2904.0
    assert r["nights_num"] == 7
    assert r["nights"] == "7 Nächte"
    assert r["board"] == "Alles Inklusive"
    assert "Double Standard" in r["room"]
    assert r["travellers_count"] == 2
    assert r["travellers"] == "2 Erwachsene"
    assert r["dep_airport"] == "Düsseldorf (DUS)"
    assert r["return_date"] == "2026-08-19"
    # cancellationType=REFUNDABLE ist NICHT kostenlos stornierbar → kein Badge
    assert r["cancellation"] == ""
    # Bewertung (rating.json) eingemischt
    assert r["stars"] == 4.5
    assert r["rating"] == 5
    assert r["recommendation"] == 83
    # Ort/Region aus dem Breadcrumb (regionGiata=88)
    assert r["region"].startswith("Kap Verde")


def test_fetch_price_api_empty_on_http400(monkeypatch, fx, fake_resp):
    def fake_get(u, **kw):
        return fake_resp({}, status=400)
    monkeypatch.setattr(scraper.requests, "get", fake_get)
    url = ("https://www.tui.com/pauschalreisen/suchen/angebote/H/259516/offer/"
           "?startDate=2027-05-01&endDate=2027-05-08&duration=20&travellers=2")
    r = scraper.fetch_price_api(url)
    # HTTP 400 = gültige Leermenge (kein technischer Fehler, KEIN None → kein Browser-Fallback)
    assert r is not None
    assert r["ok"] is False
    assert r["available"] is False
    assert "Kein Angebot" in r["note"]


def test_fetch_search_params(monkeypatch, fx, fake_resp):
    search = fx("search.json")
    monkeypatch.setattr(scraper.requests, "post", lambda *a, **k: fake_resp(search))
    res = scraper.fetch_search_params(region=128, start="2026-08-12", end="2026-08-19",
                                      duration=7, travellers=2, airports=["STR"])
    assert res["ok"] is True
    assert res["total"] == 255
    first = res["results"][0]
    assert first["name"] == "Riu Papayas"
    assert first["stars"] == 4
    assert first["nights"] == 7
    assert first["price"] == 2088
    assert "/offer/?" in first["offer_url"]
    assert "regionGiataIds=128" in first["offer_url"]


def test_fetch_search_no_region():
    # Ohne Region darf kein POST nötig sein → klare Leermeldung
    res = scraper._run_search({"regions": []})
    assert res["ok"] is False
    assert "Region" in res["note"]


def test_fetch_calendar(monkeypatch, fx, fake_resp):
    cal = fx("calendar.json")
    monkeypatch.setattr(scraper.requests, "get", lambda *a, **k: fake_resp(cal))
    url = ("https://www.tui.com/pauschalreisen/suchen/angebote/H/259516/offer/"
           "?startDate=2026-08-12&endDate=2026-08-19&duration=7&travellers=2")
    r = scraper.fetch_calendar(url)
    assert r["ok"] is True
    assert r["currency"] == "EUR"
    assert r["duration"] == 7
    # erwartete Werte direkt aus der Fixture ableiten
    days = {}
    for o in cal["offers"]:
        ad, pp = o["arrivalDate"], o["calculatedPricePerPerson"]
        days[ad] = min(days.get(ad, 1e9), pp)
    assert len(r["days"]) == len(days)
    cheapest = min(days, key=days.get)
    assert r["cheapest_date"] == cheapest
    assert r["cheapest_price"] == int(round(days[cheapest]))


def test_fetch_destinations(monkeypatch, fx, fake_resp):
    regions, sub = fx("destinations_regions.json"), fx("destinations_sub.json")
    monkeypatch.setattr(scraper.requests, "get", lambda *a, **k: fake_resp(regions))
    d = scraper.fetch_destinations()
    assert len(d["items"]) == len(regions["items"])
    labels = [i["label"] for i in d["items"]]
    assert labels == sorted(labels, key=str.lower)       # alphabetisch
    assert all("giata" in i and "level" in i for i in d["items"])

    monkeypatch.setattr(scraper.requests, "get", lambda *a, **k: fake_resp(sub))
    d2 = scraper.fetch_destinations(parent=100030)
    assert d2["parentName"] == "Spanien"


def test_fetch_airports(monkeypatch, fx, fake_resp):
    air = fx("airports.json")
    monkeypatch.setattr(scraper.requests, "get", lambda *a, **k: fake_resp(air))
    out = scraper.fetch_airports()
    assert len(out) == len(air)
    names = [a["name"] for a in out]
    assert names == sorted(names, key=str.lower)
    assert all(a["code"] for a in out)


def test_region_giata_from_breadcrumb(monkeypatch, fx, fake_resp):
    bc = fx("breadcrumb.json")
    monkeypatch.setattr(scraper.requests, "get", lambda *a, **k: fake_resp(bc))
    # letzter Eintrag mit level==1 → 88 (Kap Verde)
    assert scraper.region_giata_from_breadcrumb("259516") == 88
