"""Tests für die reinen (Playwright-freien) Funktionen aus check24_client.py:
Link-Parsing, URL-Aufbau und das Zerlegen des gerenderten Angebots-Seitentexts in
einzelne Karten. Der eigentliche Playwright-Abruf (fetch_offers) wird hier bewusst
NICHT gegen einen echten Browser getestet — analog zu scraper.py, wo ebenfalls nur
die reinen Parsing-Funktionen unit-getestet werden, nicht `_fetch_price_browser()`.
"""
import check24_client as c24


def test_parse_hotel_link_valid():
    url = ("https://urlaub.check24.de/suche/hotel?airport=STR&transportType=flight"
           "&roomAllocation=A&departureDate=2027-04-28&returnDate=2027-05-09&days=exact"
           "&pageArea=package&areaId=551&dhs=11829&ds=h&sorting=categoryDistribution"
           "&offerSort=offerRanking&areaSort=topregion&extendedSearch=1&noRedirect=1"
           "&hotelId=11829")
    assert c24.parse_hotel_link(url) == {'hotel_id': '11829', 'area_id': '551'}


def test_parse_hotel_link_missing_params():
    assert c24.parse_hotel_link("https://urlaub.check24.de/suche/hotel?areaId=551") is None
    assert c24.parse_hotel_link("https://urlaub.check24.de/suche/hotel?hotelId=11829") is None


def test_parse_hotel_link_garbage():
    assert c24.parse_hotel_link("") is None
    assert c24.parse_hotel_link("not a url") is None
    assert c24.parse_hotel_link("https://example.com/?hotelId=abc&areaId=551") is None


def test_build_hotel_list_url_contains_all_params():
    url = c24._build_hotel_list_url('11829', '551', '2027-04-28', '2027-05-09', 'STR', 'A')
    assert 'hotelId=11829' in url and 'areaId=551' in url and 'dhs=11829' in url
    assert 'departureDate=2027-04-28' in url and 'returnDate=2027-05-09' in url
    assert 'airport=STR' in url


_CARD_TEXT = (
    "12 Tage | 11 Nächte Stuttgart (STR) ↔ Las Palmas (LPA)\n"
    "Do, 22.04.2027 | 1 Stopp\n10:50\nStuttgart\n7:00 Std.\n16:50\nLas Palmas\n"
    "1x Doppelzimmer Standard\nDB1 - Double Room Classic\nFrühstück\nHotel-Transfer\n"
    "Balkon/Terrasse\nnur Handgepäck\nStornierung kostenpflichtig\n1.529,00 €\nzur Buchung\n"
    "12 Tage | 11 Nächte Stuttgart (STR) ↔ Las Palmas (LPA)\n"
    "1x Doppelzimmer Superior\nDoppelzimmer Superior\nAll Inclusive\nohne Hotel-Transfer\n"
    "1.607,00 €\nzur Buchung\n"
)


def test_parse_offer_blocks_extracts_rows():
    rows = c24._parse_offer_blocks(_CARD_TEXT)
    assert len(rows) == 2
    assert rows[0]['room'] == 'Doppelzimmer Standard'
    assert rows[0]['board'] == 'Frühstück'
    assert rows[0]['price'] == 1529.0
    assert rows[0]['transfer'] is True
    assert rows[1]['room'] == 'Doppelzimmer Superior'
    assert rows[1]['board'] == 'All Inclusive'
    assert rows[1]['price'] == 1607.0
    assert rows[1]['transfer'] is False


def test_parse_offer_blocks_no_match_returns_empty():
    assert c24._parse_offer_blocks("Keine Angebote hier, nur Fließtext ohne Preise.") == []
