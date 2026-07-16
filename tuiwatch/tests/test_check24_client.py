"""Tests für check24_client.py. Der eigentliche Netzwerk-Layer (`requests`) wird
gemockt (kein echter Check24-Zugriff im Testlauf) — anders als bis v0.55.4 ist das
jetzt möglich, weil fetch_offers()/search_hotel() reine JSON-HTTP-Aufrufe sind
(kein Playwright/Browser mehr nötig, siehe check24_client.py-Moduldocstring)."""
import requests

import check24_client as c24


def test_parse_hotel_link_valid():
    url = ("https://urlaub.check24.de/suche/hotel?airport=STR&transportType=flight"
           "&roomAllocation=A&departureDate=2027-04-28&returnDate=2027-05-09&days=exact"
           "&pageArea=package&dhs=11829&ds=h&sorting=categoryDistribution"
           "&offerSort=offerRanking&areaSort=topregion&extendedSearch=1&noRedirect=1"
           "&hotelId=11829")
    assert c24.parse_hotel_link(url) == {'hotel_id': '11829'}


def test_parse_hotel_link_missing_hotel_id():
    assert c24.parse_hotel_link("https://urlaub.check24.de/suche/hotel?areaId=551") is None


def test_parse_hotel_link_garbage():
    assert c24.parse_hotel_link("") is None
    assert c24.parse_hotel_link("not a url") is None
    assert c24.parse_hotel_link("https://example.com/?hotelId=abc") is None


def test_build_offer_url_contains_params():
    url = c24._build_offer_url('11829', '2027-04-28', '2027-05-09', 'STR', 'A')
    assert 'hotelId=11829' in url
    assert 'areaId=' not in url
    assert 'departureDate=2027-04-28' in url and 'returnDate=2027-05-09' in url
    assert 'airport=STR' in url
    assert 'cateringList=' not in url  # ohne board_hint kein Verpflegungsfilter


def test_build_offer_url_with_catering_list():
    url = c24._build_offer_url('11829', '2027-04-28', '2027-05-09', 'STR', 'A',
                               'allinclusive,allinclusivePlus')
    assert 'cateringList=allinclusive%2CallinclusivePlus' in url


def test_catering_list_for_board_maps_tui_texts():
    # Live per Netzwerk-Mitschnitt an Check24s eigenem Verpflegungs-Filter-Tab
    # ermittelt (cateringList-Query-Param) -- siehe SCRAPING_CHECK24.md.
    assert c24._catering_list_for_board('All Inclusive') == 'allinclusive,allinclusivePlus'
    assert c24._catering_list_for_board('Alles Inklusive') == 'allinclusive,allinclusivePlus'
    assert c24._catering_list_for_board('Vollpension') == (
        'fullboard,fullboardPlus,allinclusive,allinclusivePlus')
    assert c24._catering_list_for_board('Halbpension') == (
        'halfboard,halfboardPlus,fullboard,fullboardPlus,allinclusive,allinclusivePlus')
    assert c24._catering_list_for_board('Frühstück') == (
        'breakfast,halfboard,halfboardPlus,fullboard,fullboardPlus,allinclusive,allinclusivePlus')
    assert c24._catering_list_for_board('Ohne Verpflegung') == 'none'


def test_catering_list_for_board_unknown_returns_empty():
    assert c24._catering_list_for_board('') == ''
    assert c24._catering_list_for_board('irgendwas Unbekanntes') == ''


def test_search_hotel_empty_query_short_circuits(monkeypatch):
    # Darf nicht mal versuchen, requests.get aufzurufen.
    monkeypatch.setattr(requests, "get", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("requests.get haette bei leerer Anfrage nicht aufgerufen werden duerfen")))
    assert c24.search_hotel("") == []
    assert c24.search_hotel("   ") == []


_AUTOCOMPLETE_RESPONSE = {
    "data": [
        {"group": "destination", "label": "Reiseziele", "data": [
            {"label": "Gloria", "id": 69041, "type": "city"},
        ]},
        {"group": "hotel", "label": "Hotels", "data": [
            {"label": "Gloria Palace Amadores Thalasso & Hotel", "id": 11829,
             "regionName": "Gran Canaria", "countryName": "Spanien", "type": "hotel"},
            {"label": "Gloria Palace", "id": 1057953,
             "regionName": "Antalya", "countryName": "Türkei", "type": "hotel"},
        ]},
    ]
}


def test_search_hotel_parses_and_reduces_unambiguous_match(monkeypatch, fake_resp):
    monkeypatch.setattr(requests, "get", lambda *a, **k: fake_resp(_AUTOCOMPLETE_RESPONSE))
    out = c24.search_hotel("Gloria Palace Amadores Thalasso & Hotel")
    assert out == [{'hotel_id': '11829', 'name': 'Gloria Palace Amadores Thalasso & Hotel',
                    'location': 'Gran Canaria, Spanien'}]


def test_search_hotel_ambiguous_returns_all_candidates(monkeypatch, fake_resp):
    monkeypatch.setattr(requests, "get", lambda *a, **k: fake_resp(_AUTOCOMPLETE_RESPONSE))
    out = c24.search_hotel("Gloria")  # zu kurz/unspezifisch fuer eine eindeutige Reduktion
    assert {o['hotel_id'] for o in out} == {'11829', '1057953'}


def test_search_hotel_http_error_returns_none(monkeypatch, fake_resp):
    monkeypatch.setattr(requests, "get", lambda *a, **k: fake_resp({}, status=500))
    assert c24.search_hotel("irgendwas") is None


def _fake_offer_item(*, operator_alias="ITS Dynamisch", operator_code="ITSX",
                     room="Doppelzimmer Superior", meal_type="AllInclusive",
                     price=1259.0, transfer=True):
    return {
        "tourOperatorCode": operator_code, "tourOperatorAlias": operator_alias,
        "accommodationData": {
            "mealType": meal_type,
            "roomDescription": {"name": "Doppelzimmer", "description": room},
            "transfer": "Transfer" if transfer else None,
        },
        "price": {"effectivePrice": {"amount": price}},
    }


class _FakeSessionResp:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status

    def json(self):
        return self._data


def _mock_offer_post(monkeypatch, responses):
    """responses: Liste von dicts, nacheinander als POST-Antworten zurückgegeben
    (simuliert den Pending->Success-Poll-Zyklus)."""
    it = iter(responses)

    def fake_post(self, *a, **k):
        return _FakeSessionResp(next(it))
    monkeypatch.setattr(requests.Session, "post", fake_post)
    monkeypatch.setattr("time.sleep", lambda *a, **k: None)


def test_fetch_offers_parses_success_response(monkeypatch):
    items = {
        "1": _fake_offer_item(operator_alias="ITS Dynamisch", room="Doppelzimmer Superior",
                              meal_type="AllInclusive", price=1259.0),
        "2": _fake_offer_item(operator_alias="alltours dynamisch", room="Doppelzimmer Standard",
                              meal_type="HalfBoard", price=999.0),
    }
    _mock_offer_post(monkeypatch, [{"status": "Pending", "items": {}},
                                    {"status": "Success", "items": items}])
    res = c24.fetch_offers('240', '2026-12-06', '2026-12-13', 'STR')
    assert res['ok'] is True
    assert res['note'] == ''
    assert len(res['rows']) == 2
    # nach Preis sortiert
    assert res['rows'][0]['price'] == 999.0
    assert res['rows'][0]['operator'] == 'alltours dynamisch'
    assert res['rows'][0]['board'] == 'Halbpension'
    assert res['rows'][1]['board'] == 'All Inclusive'
    assert res['rows'][1]['transfer'] is True


def test_fetch_offers_board_hint_filters_strictly_no_fallback(monkeypatch):
    # Nur Halbpension-Angebote vorhanden, board_hint verlangt All Inclusive ->
    # KEIN Fallback auf ungefiltert (das war der Bugreport-Fehler bis v0.55.4).
    items = {"1": _fake_offer_item(meal_type="HalfBoard", price=999.0)}
    _mock_offer_post(monkeypatch, [{"status": "Success", "items": items}])
    res = c24.fetch_offers('240', '2026-12-06', '2026-12-13', 'STR', board_hint='All Inclusive')
    assert res['rows'] == []
    assert res['note'] == 'no_offers_for_board'


def test_fetch_offers_board_hint_matches_across_de_en_wording(monkeypatch):
    # Bugreport: TUI liefert "Alles Inklusive" (deutsch) als board, Check24s
    # mealType "AllInclusive" wird intern zu "All Inclusive" (englisch)
    # uebersetzt -- ein Substring-Textvergleich der beiden matcht nie, obwohl
    # cateringList serverseitig laengst richtig gefiltert hatte. Der Filter
    # muss stattdessen ueber die Check24-Tier-Codes vergleichen.
    items = {"1": _fake_offer_item(meal_type="AllInclusive", price=1231.0)}
    _mock_offer_post(monkeypatch, [{"status": "Success", "items": items}])
    res = c24.fetch_offers('240', '2026-12-06', '2026-12-13', 'STR', board_hint='Alles Inklusive')
    assert res['note'] == ''
    assert len(res['rows']) == 1
    assert res['rows'][0]['board'] == 'All Inclusive'


def test_fetch_offers_board_hint_includes_higher_tier(monkeypatch):
    # cateringList ist "diese Stufe oder besser" (Check24-eigene Semantik) --
    # bei board_hint="Vollpension" muss ein All-Inclusive-Angebot mit
    # durchrutschen, nicht nur exakte Vollpension-Treffer.
    items = {"1": _fake_offer_item(meal_type="AllInclusive", price=1231.0)}
    _mock_offer_post(monkeypatch, [{"status": "Success", "items": items}])
    res = c24.fetch_offers('240', '2026-12-06', '2026-12-13', 'STR', board_hint='Vollpension')
    assert len(res['rows']) == 1


def test_fetch_offers_error_status_is_not_available_not_error(monkeypatch):
    _mock_offer_post(monkeypatch, [{"status": "Error"}])
    res = c24.fetch_offers('999999', '2026-12-06', '2026-12-13', 'STR')
    assert res['ok'] is True
    assert res['rows'] == []
    assert res['note'] == 'not_available_exact_dates'
    assert 'hotelId=999999' in res['offer_url']


def test_fetch_offers_empty_status_resolves_immediately_as_not_available(monkeypatch):
    # Bugreport: gueltiges Hotel, aber 0 Angebote fuer exakt diese Termine --
    # Check24 antwortet sofort mit status="Empty" (weder "Success" noch "Error"),
    # live per Netzwerk-Mitschnitt gegen einen echten Fall verifiziert (Gloria
    # Palace Amadores, 11829, 03.-14.05.2027). Fehlte die Terminal-Status-Liste
    # "Empty", pollte der Loop bis zum Timeout (~60s) statt sofort zu erkennen,
    # dass es schlicht kein Angebot gibt.
    responses = [{"status": "Empty"}]
    _mock_offer_post(monkeypatch, responses)
    t_start = []
    monkeypatch.setattr("time.sleep", lambda *a, **k: t_start.append(1))
    res = c24.fetch_offers('11829', '2027-05-03', '2027-05-14', 'STR')
    assert res['ok'] is True
    assert res['rows'] == []
    assert res['note'] == 'not_available_exact_dates'
    assert 'hotelId=11829' in res['offer_url']
    assert not t_start  # sofort erkannt, kein einziger Poll-Sleep noetig


def test_fetch_offers_technical_error_returns_none(monkeypatch):
    def raising_post(self, *a, **k):
        raise requests.exceptions.ConnectionError("boom")
    monkeypatch.setattr(requests.Session, "post", raising_post)
    assert c24.fetch_offers('240', '2026-12-06', '2026-12-13', 'STR') is None


def test_fetch_offers_no_items_at_all(monkeypatch):
    _mock_offer_post(monkeypatch, [{"status": "Success", "items": {}}])
    res = c24.fetch_offers('240', '2026-12-06', '2026-12-13', 'STR')
    assert res['rows'] == []
    assert res['note'] == 'no_offers_parsed'
