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


def test_map_board_types_bb_aliases_to_br():
    # Angebots-/Kalender-API nutzt fuer Fruehstueck intern BR statt BB (Seiten-URL,
    # Such-API und Hotelsuche verwenden BB) -- per Live-Test an mehreren Hotels
    # verifiziert, GT06-BB liefert sonst durchweg 0 Treffer. Siehe CHANGELOG.
    assert scraper._map_board_types("BB") == "GT06-BR"
    assert scraper._map_board_types("bb") == "GT06-BR"
    assert scraper._map_board_types("GT06-BB") == "GT06-BR"
    assert scraper._map_board_types("BB,HB") == "GT06-BR,GT06-HB"


def test_slugify():
    assert scraper._slugify("Riu Funana") == "riu-funana"
    # deutsche Umlaute/ß werden transliteriert, Sonderzeichen zu '-' verdichtet
    assert scraper._slugify("Hotel Süd & Meer") == "hotel-sued-meer"
    assert scraper._slugify("Größe Straße") == "groesse-strasse"


def test_de_date_and_datetime():
    assert scraper._de_date("2027-05-01") == "01.05.2027"
    assert scraper._de_datetime("2027-05-01T07:35:00.000+02:00") == "Sa 01.05.2027, 07:35"
    assert scraper._de_date("") == ""
    assert scraper._de_weekday("2027-05-03") == "Mo"
    assert scraper._de_weekday("") == ""


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
    # echte Board-Codes (HB/FB/BB/AO) werden 1:1 als boardCodes durchgereicht
    u2 = ("https://www.tui.com/pauschalreisen/suchen/angebote/H/1/offer/"
          "?duration=7&boardTypes=HB,AO")
    assert scraper._search_params_from_url(u2)["boards"] == ["HB", "AO"]


def test_offer_url_for():
    item = {"hotel": {"giataId": 123, "name": "Test Hotel"},
            "numberOfNights": 7, "boardCodes": ["AI"]}
    params = {"startDate": "2027-05-01", "endDate": "2027-05-08", "duration": 7,
              "travellers": 2, "airports": ["STR"], "operators": ["TUID"],
              "regions": [128], "airlines": ["X3", "VY"], "direct": True,
              "location": [9, 11]}
    url = scraper.offer_url_for(item, params)
    assert "/angebote/test-hotel/123/offer/" in url
    assert "regionGiataIds=128" in url
    assert "duration=7" in url
    assert "travellers=2" in url
    assert "boardTypes=AI" in url
    assert "departureAirports=STR" in url
    assert "maxStopOvers=0" in url         # direct=True
    # Airlines mit ';' getrennt (Offer-/Such-API-Format), URL-kodiert als %3B
    assert "airlines=X3%3BVY" in url
    # Lage-IDs ebenfalls mit ';' getrennt, wie im echten TUI-URL-Format
    assert "locationAttributes=9%3B11" in url


def test_search_params_from_url_location():
    # locationAttributes aus einer eingefügten URL lesen (';'-getrennt)
    url = ("https://www.tui.com/x/259516/offer/?regionGiataIds=128&duration=7"
           "&locationAttributes=9%3B11")
    p = scraper._search_params_from_url(url)
    assert p["location"] == [9, 11]
    # Override-Kwarg schlägt die URL
    p2 = scraper._search_params_from_url(url, location=[37])
    assert p2["location"] == [37]
    # keine locationAttributes in der URL -> leere Liste
    u2 = "https://www.tui.com/x/1/offer/?duration=7"
    assert scraper._search_params_from_url(u2)["location"] == []


def test_location_expression_and_payload():
    # Bekannte Codes je ID (per Live-Test gegen die echte TUI-Such-API verifiziert:
    # Baseline 33 Treffer -> id=9: 10, id=11: 21, Kombination 9+11: 10 Treffer).
    assert scraper._location_expression([9]) == "GT03-DIBE#ST03-DIRE"
    assert scraper._location_expression([9, 11]) == (
        "GT03-DIBE#ST03-DIRE + GT03-BEAC#ST03-SAND")
    assert scraper._location_expression([]) == ""
    assert scraper._location_expression([999]) == ""   # unbekannte ID -> ignoriert

    payload = scraper._build_search_payload(
        {"regions": [128], "duration": 7, "travellers": 2, "location": [9, 11]})
    assert payload["parameters"]["logicalExpression"] == (
        "GT03-DIBE#ST03-DIRE + GT03-BEAC#ST03-SAND")
    # ohne Lage-Filter bleibt logicalExpression leer (Standardverhalten unverändert)
    empty = scraper._build_search_payload({"regions": [128], "duration": 7})
    assert empty["parameters"]["logicalExpression"] == ""


def test_facility_expression_and_payload():
    # id 13 = "Nur Erwachsene" — per Playwright live abgefangen (echter Netzwerk-
    # Request auf tui.com mit facilityAttributes=13) und gegen die echte Such-API
    # verifiziert (Gran Canaria: 100 -> 28 Treffer, ausschließlich adults-only-artige
    # Hotels).
    assert scraper._facility_expression([13]) == "GT03#TUI-G0978"
    assert scraper._facility_expression([]) == ""
    assert scraper._facility_expression([999]) == ""   # unbekannte ID -> ignoriert

    payload = scraper._build_search_payload(
        {"regions": [128], "duration": 7, "travellers": 2, "facility": [13]})
    assert payload["parameters"]["logicalExpression"] == "GT03#TUI-G0978"

    # Lage- und Ausstattungs-Filter kombiniert (AND, wie bei mehreren Lage-IDs)
    combo = scraper._build_search_payload(
        {"regions": [128], "duration": 7, "location": [9], "facility": [13]})
    assert combo["parameters"]["logicalExpression"] == (
        "GT03-DIBE#ST03-DIRE + GT03#TUI-G0978")


def test_search_params_from_url_adults_only():
    url = "https://www.tui.com/x/259516/offer/?regionGiataIds=128&duration=7&facilityAttributes=13"
    assert scraper._search_params_from_url(url)["facility"] == [13]
    # ohne facilityAttributes in der URL und ohne Kwarg -> leere Liste
    u2 = "https://www.tui.com/x/1/offer/?duration=7"
    assert scraper._search_params_from_url(u2)["facility"] == []
    # Kwarg setzt den Filter auch ohne URL-Parameter
    assert scraper._search_params_from_url(u2, adults_only=True)["facility"] == [13]


def test_fetch_airlines():
    out = scraper.fetch_airlines()
    assert len(out) > 5
    names = [a["name"] for a in out]
    assert names == sorted(names, key=str.lower)         # alphabetisch
    codes = {a["name"]: a["code"] for a in out}
    assert codes.get("Eurowings") == "EW"
    assert codes.get("Condor") == "DE"
    assert all(a["code"] and a["name"] for a in out)


def test_search_params_airlines():
    # Airlines aus der URL (';'-getrennt) lesen
    url = ("https://www.tui.com/x/259516/offer/?regionGiataIds=128&duration=7"
           "&airlines=X3%3BVY")
    p = scraper._search_params_from_url(url)
    assert p["airlines"] == ["X3", "VY"]
    # Override schlägt URL
    p2 = scraper._search_params_from_url(url, airlines=["EW"])
    assert p2["airlines"] == ["EW"]


def test_build_search_payload_airlines():
    payload = scraper._build_search_payload(
        {"regions": [128], "duration": 7, "travellers": 2, "airlines": ["X3", "VY"]})
    assert payload["parameters"]["airlines"] == ["X3", "VY"]


def test_search_params_from_url_exact_duration():
    # duration=exact aus einer eingefügten URL muss erhalten bleiben (nicht None
    # werden) — die Such-API kennt "exact" selbst nicht, siehe
    # test_build_search_payload_exact_computes_nights.
    url = ("https://www.tui.com/x/1/offer/?startDate=2026-08-13&endDate=2026-08-16"
           "&duration=exact&regionGiataIds=128")
    assert scraper._search_params_from_url(url)["duration"] == "exact"


def test_build_search_payload_exact_computes_nights():
    # Die Such-API ignoriert "duration": "exact" (fällt sonst auf 7 Nächte zurück) —
    # daher aus dem Datumsfenster selbst die Nächtezahl berechnen und als Zahl senden.
    payload = scraper._build_search_payload({
        "regions": [128], "duration": "exact", "travellers": 2,
        "startDate": "2026-08-13", "endDate": "2026-08-16"})
    assert payload["parameters"]["duration"] == [3]


def test_build_search_payload_exact_without_dates():
    payload = scraper._build_search_payload(
        {"regions": [128], "duration": "exact", "travellers": 2})
    assert payload["parameters"]["duration"] == []


def test_build_search_payload_sorts_by_price_ascending():
    # Bugreport: TUIWatchs Hotelsuche zeigte deutlich teurere Hotels als tui.com
    # selbst fuer dieselben Parameter -- Ursache war "qualifier2DESC" (Best-
    # Match-Score) statt Preis als serverseitige Sortierung. Bei mehr Treffern
    # als resultsPerPage (z.B. 256 in einer Region, nur 50 abgeholt) fehlten die
    # guenstigsten Hotels dadurch komplett im abgeholten Batch -- clientseitiges
    # "Preis aufsteigend"-Sortieren (app.js) kann nur sortieren, was da ist.
    # "priceAsc" per Netzwerk-Mitschnitt von tui.com selbst verifiziert (liefert
    # dieselben guenstigen Hotels wie sortHotelsField=price&sortHotelsAsc=1).
    payload = scraper._build_search_payload({"regions": [128], "duration": 7})
    assert payload["parameters"]["sortingOrder"] == "priceAsc"


def test_build_search_payload_offset_sets_results_from():
    # "Mehr laden" (Pagination) -- die Such-API liefert pro Aufruf nur
    # resultsPerPage Treffer, offset=bereits geladene Treffer holt die naechste
    # Seite statt dieselben 50 erneut.
    payload = scraper._build_search_payload({"regions": [128], "duration": 7})
    assert payload["parameters"]["resultsFrom"] == 0
    payload2 = scraper._build_search_payload({"regions": [128], "duration": 7}, offset=50)
    assert payload2["parameters"]["resultsFrom"] == 50


def test_build_search_payload_results_total_cap_is_high_enough():
    # resultsTotal ist ein Anfrage-Cap, keine reine Info-Zahl -- die Such-API
    # deckelt ihre eigene Antwort-"resultsTotal" (echte Trefferzahl) darauf
    # (live verifiziert: Cap 300 bei 703 echten Treffern -> Antwort "300"). Bei
    # zu niedrigem Cap zeigt die UI ("von N Treffer") eine falsche, zu kleine
    # Gesamtzahl fuer grosse Regionen.
    payload = scraper._build_search_payload({"regions": [128], "duration": 7})
    assert payload["parameters"]["resultsTotal"] >= 1000


def test_room_code_helpers():
    base = "https://www.tui.com/x/123/offer/?startDate=2027-05-01&duration=7"
    u = scraper.with_room_code(base, "DZM3")
    assert "roomTypeOpCodes=DZM3" in u
    assert scraper.room_code_from_url(u) == "DZM3"
    # ersetzen
    assert scraper.room_code_from_url(scraper.with_room_code(u, "DZM1")) == "DZM1"
    # leerer Code entfernt die Festlegung
    assert "roomTypeOpCodes" not in scraper.with_room_code(u, "")
    assert scraper.room_code_from_url(base) == ""


def test_fetch_rooms(monkeypatch, fake_resp):
    payload = {"currency": "EUR", "offers": [
        {"calculatedPricePerPerson": 2116, "rooms": [
            {"code": "DZM3", "description": "Double Sea View Premium", "boardDescription": "Alles Inklusive"}]},
        {"calculatedPricePerPerson": 2081, "rooms": [
            {"code": "DZM1", "description": "Double Sea View", "boardDescription": "Alles Inklusive"}]},
        {"calculatedPricePerPerson": 3662, "rooms": [  # zweites (teureres) DZM1-Angebot
            {"code": "DZM1", "description": "Double Sea View", "boardDescription": "Alles Inklusive"}]},
    ]}
    monkeypatch.setattr(scraper.requests, "get", lambda *a, **k: fake_resp(payload))
    url = "https://www.tui.com/x/123/offer/?startDate=2027-05-01&duration=7&roomTypeOpCodes=DZM3"
    res = scraper.fetch_rooms(url)
    assert res["ok"] is True
    assert [r["code"] for r in res["rooms"]] == ["DZM1", "DZM3"]   # nach Preis sortiert
    assert res["rooms"][0]["price"] == 2081                        # günstigstes DZM1
    assert res["rooms"][0]["name"] == "Double Sea View"
    assert scraper.room_code_from_url(res["rooms"][1]["url"]) == "DZM3"


def test_fetch_rooms_empty_on_http400(monkeypatch, fake_resp):
    monkeypatch.setattr(scraper.requests, "get", lambda *a, **k: fake_resp({}, status=400))
    res = scraper.fetch_rooms("https://www.tui.com/x/123/offer/?duration=7")
    assert res is not None and res["ok"] is False


def test_valid_img_url():
    assert scraper._valid_img_url("https://pics.tui.com/pics/x.jpg") is True
    assert scraper._valid_img_url("https://www.tui.com/img.jpg") is True
    assert scraper._valid_img_url("http://pics.tui.com/x.jpg") is False     # kein https
    assert scraper._valid_img_url("https://evil.example.com/x.jpg") is False
    assert scraper._valid_img_url("https://pics.tui.com.evil.com/x.jpg") is False
    assert scraper._valid_img_url("") is False


def test_fetch_hotel_image(monkeypatch, fx, fake_resp):
    search, bc = fx("search.json"), fx("breadcrumb.json")
    monkeypatch.setattr(scraper.requests, "get", lambda *a, **k: fake_resp(bc))   # breadcrumb
    monkeypatch.setattr(scraper.requests, "post", lambda *a, **k: fake_resp(search))  # search
    # giataId aus der Such-Fixture (erster Treffer) verwenden → Bild gefunden
    giata = str(search["items"][0]["hotel"]["giataId"])
    url = (f"https://www.tui.com/pauschalreisen/suchen/angebote/Hotel/{giata}/offer/"
           "?startDate=2026-08-12&endDate=2026-08-19&duration=7&travellers=2")
    img = scraper.fetch_hotel_image(url)
    assert img.startswith("https://pics.tui.com/")
    # giataId, die nicht in den Treffern ist → kein Bild
    url2 = url.replace(f"/{giata}/", "/999999/")
    assert scraper.fetch_hotel_image(url2) == ""


# ── Netzbehaftete Normalisierung (gegen echte Fixtures, requests gemonkeypatcht) ──

def test_fetch_price_api(monkeypatch, fx, fake_resp):
    offer, rating, bc = fx("offer.json"), fx("rating.json"), fx("breadcrumb.json")
    vac = fx("vacancy.json")

    def fake_get(u, **kw):
        if scraper.OFFER_API in u:
            return fake_resp(offer)
        if scraper.CONTENT_API in u:
            return fake_resp(rating)
        if u.startswith(scraper.BREADCRUMB_API):
            return fake_resp(bc)
        if u.startswith(scraper.LAST_BOOKED_API):
            return fake_resp({"date": "2026-08-03T18:45:22.000Z",
                              "in_the_last_24_hours": False})
        raise AssertionError("unerwartete URL: " + u)

    def fake_post(u, **kw):
        assert u == scraper.VACANCY_API, "unerwarteter POST: " + u
        p = kw.get("json") or {}
        # Payload-Formate absichern: travelType muss ein Objekt sein (String → FAILED)
        assert p["offer"]["travelType"] == {"code": "TUR1", "brand": "TUR1",
                                            "tourOperator": "LTUR",
                                            "bookingTourOperator": "TUR1"}
        assert p["agency"] and p["channel"]
        # Zimmer-Reisende mit Alter + Preis aus personPrices zusammengeführt
        assert p["offer"]["rooms"][0]["travellers"][0] == {"id": 1, "age": 28, "price": 1452}
        return fake_resp(vac)

    monkeypatch.setattr(scraper.requests, "get", fake_get)
    monkeypatch.setattr(scraper.requests, "post", fake_post)
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
    # Buchungscodes + Flugnummer im Flugstring
    assert r["booking_code"] == "SID10006"           # hotel.product
    assert r["room_booking_code"] == "DZX1A"          # rooms[0].bookingCode
    assert "X3 7102" in r["flight_out"]               # Airline-Code + Flugnummer
    # cancellationType=REFUNDABLE ist NICHT kostenlos stornierbar → kein Badge
    assert r["cancellation"] == ""
    # Bewertung (rating.json) eingemischt
    assert r["stars"] == 4.5
    assert r["rating"] == 5
    assert r["recommendation"] == 83
    # Ort/Region aus dem Breadcrumb (regionGiata=88)
    assert r["region"].startswith("Kap Verde")
    # vacancy-check: Live-Bestätigung + Preis-Aufschlüsselung (Summen über alle Reisenden)
    assert r["vac_status"] == "OK"
    assert r["price_hotel"] == 1656.0
    assert r["price_flight_out"] == 592.0
    assert r["price_flight_ret"] == 656.0
    assert r["price_hotel"] + r["price_flight_out"] + r["price_flight_ret"] == r["total_price"]
    assert r["last_booked"] == "2026-08-03"
    # Buchungsdetails: Errata, bestätigte Segmente, Kontingent-Quelle, Badges
    assert len(r["errata"]) == 2 and "Flugzeiten" in r["errata"][0]
    assert [s["number"] for s in r["flight_segments"]["out"]] == ["7102", "7102"]
    assert r["flight_segments"]["out"][0]["cls"] == "Y"
    assert r["flight_segments"]["ret"][0]["dep"] == "SID"
    assert r["hotel_supplier"] == "DBH/MTS"
    assert r["flight_flags"] == {"charter": True, "seat": True, "svc": True}


def test_fetch_price_api_vacancy_failed_defensive(monkeypatch, fx, fake_resp):
    """FAILED vom vacancy-check darf weder ok noch available kippen (kann Drift sein)."""
    offer, rating, bc = fx("offer.json"), fx("rating.json"), fx("breadcrumb.json")

    def fake_get(u, **kw):
        if scraper.OFFER_API in u:
            return fake_resp(offer)
        if scraper.CONTENT_API in u:
            return fake_resp(rating)
        if u.startswith(scraper.BREADCRUMB_API):
            return fake_resp(bc)
        if u.startswith(scraper.LAST_BOOKED_API):
            return fake_resp({}, status=404)
        raise AssertionError("unerwartete URL: " + u)

    monkeypatch.setattr(scraper.requests, "get", fake_get)
    monkeypatch.setattr(scraper.requests, "post",
                        lambda *a, **k: fake_resp({"status": "FAILED"}))
    url = ("https://www.tui.com/pauschalreisen/suchen/angebote/Hotel-Riu-Funana/259516/"
           "offer/?startDate=2026-08-12&endDate=2026-08-19&duration=7&travellers=2")
    r = scraper.fetch_price_api(url)
    assert r["ok"] is True
    assert r["available"] is True          # offers[] vorhanden → verfügbar
    assert r["vac_status"] == "FAILED"     # aber nicht bestätigt
    assert r["price_hotel"] is None
    assert r["last_booked"] == ""


def test_fetch_price_api_no_vacancy_flag(monkeypatch, fx, fake_resp):
    """vacancy=False (Massen-Abrufe) darf den vacancy-check gar nicht erst aufrufen."""
    offer, rating, bc = fx("offer.json"), fx("rating.json"), fx("breadcrumb.json")

    def fake_get(u, **kw):
        if scraper.OFFER_API in u:
            return fake_resp(offer)
        if scraper.CONTENT_API in u:
            return fake_resp(rating)
        if u.startswith(scraper.BREADCRUMB_API):
            return fake_resp(bc)
        raise AssertionError("unerwartete URL: " + u)

    def fail_post(*a, **k):
        raise AssertionError("vacancy-check darf bei vacancy=False nicht aufgerufen werden")

    monkeypatch.setattr(scraper.requests, "get", fake_get)
    monkeypatch.setattr(scraper.requests, "post", fail_post)
    url = ("https://www.tui.com/pauschalreisen/suchen/angebote/Hotel-Riu-Funana/259516/"
           "offer/?startDate=2026-08-12&endDate=2026-08-19&duration=7&travellers=2")
    r = scraper.fetch_price_api(url, vacancy=False)
    assert r["ok"] is True
    assert r["vac_status"] == ""


def test_fetch_luggage(monkeypatch, fx, fake_resp):
    offer = fx("offer.json")["offers"][0]
    seen = {}

    def fake_post(u, **kw):
        assert u == scraper.LUGGAGE_API
        seen["body"] = kw.get("json")
        return fake_resp([
            {"luggage": {"adult": {"pcs": 1, "weight": 20}}, "state": "OK"},
            {"luggage": {"adult": {"pcs": 1, "weight": 15}}, "state": "OK"},
        ])

    monkeypatch.setattr(scraper.requests, "post", fake_post)
    assert scraper.fetch_luggage(offer) == {"out": "1×20 kg", "ret": "1×15 kg"}
    # Routen + Airline aus dem Offer-JSON abgeleitet
    assert seen["body"] == [
        {"airline": "X3", "route": "DUS-SID", "organizer": "LTUR"},
        {"airline": "X3", "route": "SID-DUS", "organizer": "LTUR"},
    ]


def test_fetch_payment_terms(monkeypatch, fx, fake_resp):
    offer = fx("offer.json")["offers"][0]

    def fake_get(u, **kw):
        assert u.startswith(scraper.HOTEL_CONTENT_API)
        return fake_resp({"contact": {"address": {"countryCode": "CV"}}})

    def fake_post(u, **kw):
        assert u == scraper.PAYMENT_API
        assert kw["headers"].get("X-Agency")          # ohne Header: HTTP 400
        svc = kw["json"]["services"][0]
        assert svc["countryCodes"] == ["CV"]
        assert svc["productCodes"] == ["SID10006"]
        return fake_resp({"paymentMethods": [], "depositPercentage": 25,
                          "finalPaymentDate": "2026-07-15T00:00:00"})

    monkeypatch.setattr(scraper.requests, "get", fake_get)
    monkeypatch.setattr(scraper.requests, "post", fake_post)
    assert scraper.fetch_payment_terms(offer, "259516") == {
        "deposit_pct": 25, "final_payment_date": "2026-07-15"}


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
    assert first["coupon"] is True   # Fixture-Hotel führt GT03-COUP in globalTypes
    assert first["locations"] == ["Sandstrand"]
    assert res["results"][1]["locations"] == ["Strand < 500m", "Sandstrand", "Ruhig"]


def test_fetch_search_params_coupon_false_without_flag(monkeypatch, fake_resp):
    # Hotel ohne GT03-COUP im globalTypes-Katalog → coupon:false
    payload = {"resultsTotal": 1, "items": [{
        "hotel": {"giataId": 1, "name": "Ohne Coupon", "category": "3",
                  "location": {}, "globalTypes": [{"code": "GT03-BEAC"}]},
        "price": {"perPerson": {"amount": 500}},
        "boardType": "", "numberOfNights": 7, "startDate": "2026-08-12T00:00:00",
    }]}
    monkeypatch.setattr(scraper.requests, "post", lambda *a, **k: fake_resp(payload))
    res = scraper.fetch_search_params(region=128, start="2026-08-12", end="2026-08-19",
                                      duration=7, travellers=2, airports=["STR"])
    assert res["results"][0]["coupon"] is False
    assert res["results"][0]["locations"] == []


def test_fetch_search_params_region_separate(monkeypatch, fake_resp):
    """`region` steht getrennt neben `location` — der Auto-Tag beim Tracken
    vergibt nur die Region, nicht „Ort, Region"."""
    payload = {"resultsTotal": 1, "items": [{
        "hotel": {"giataId": 1, "name": "Testhotel", "category": "4",
                  "location": {"city": "Palmar", "region": "Mauritius",
                               "country": "Mauritius"}, "globalTypes": []},
        "price": {"perPerson": {"amount": 1000}},
        "boardType": "AI", "numberOfNights": 7, "startDate": "2027-01-01T00:00:00",
    }]}
    monkeypatch.setattr(scraper.requests, "post", lambda *a, **k: fake_resp(payload))
    res = scraper.fetch_search_params(region=128, start="2027-01-01", end="2027-01-08",
                                      duration=7, travellers=2, airports=["STR"])
    first = res["results"][0]
    assert first["region"] == "Mauritius"
    assert first["location"] == "Palmar, Mauritius"      # Anzeige bleibt vollständig
    assert first["country"] == "Mauritius"


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


def test_build_destination_index(monkeypatch):
    """Globale Reiseziel-Suche: kompletter Baum wird flach indiziert, mit
    Breadcrumb-Pfad der übergeordneten Regionen und ohne Duplikate."""
    tree = {
        None:   [{"giata": 100030, "label": "Spanien"},
                 {"giata": 724, "label": "Türkei"}],
        100030: [{"giata": 851, "label": "Kanarische Inseln"},
                 {"giata": 100002, "label": "Balearen"}],
        851:    [{"giata": 128, "label": "Gran Canaria"},
                 {"giata": 135, "label": "Teneriffa"}],
    }
    monkeypatch.setattr(scraper, "fetch_destinations",
                        lambda parent=None: {"items": tree.get(parent, [])})
    idx = scraper.build_destination_index()
    by_label = {it["label"]: it for it in idx}
    # tief verschachteltes Ziel ist enthalten (würde der Picker erst nach 2 Klicks zeigen)
    assert "Kanarische Inseln" in by_label
    assert by_label["Kanarische Inseln"]["path"] == "Spanien"
    assert by_label["Gran Canaria"]["path"] == "Spanien › Kanarische Inseln"
    # Top-Level hat leeren Pfad, alphabetisch sortiert, keine Duplikate
    assert by_label["Spanien"]["path"] == ""
    labels = [it["label"] for it in idx]
    assert labels == sorted(labels, key=str.lower)
    assert len(labels) == len(set(it["giata"] for it in idx)) == 6
