#!/usr/bin/env python3
"""Check24-Preisvergleich (andere Reiseveranstalter) für ein gepinntes Hotel.

Frueher (bis v0.55.4) wurde angenommen, Check24 habe kein offenes JSON-API und
die Angebotsseite muesse per Playwright gerendert werden, weil die Antwort von
`/suche/json/dynamic/offer` ein verschluesseltes `cryptString`-Feld enthaelt.
Live-Analyse (Netzwerk-Mitschnitt eines echten Seitenaufrufs) hat das widerlegt:
`cryptString` ist nur ein Buchungs-/Verfuegbarkeits-Token (`data-vacancy`, wird
beim eigentlichen Buchen an `/suche/json/dynamic/store-vacancy` zurueckgeschickt)
-- Preis, Zimmer, Verpflegung, Veranstalter stehen im selben JSON bereits im
Klartext (`price.effectivePrice.amount`, `accommodationData.mealType`, ...).
Der Endpoint ist ein simpler Job/Poll-POST, per `requests` reproduzierbar, kein
Browser noetig. Ebenso ist die Hotelsuche (`search_hotel`) ein normales
JSON-GET (`/autocompleter-destination`), kein clientseitiges Autocomplete ohne
Server-Roundtrip wie zuvor angenommen. Details/Beispiele: SCRAPING_CHECK24.md.
"""
import logging
import time
import uuid
from difflib import SequenceMatcher
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from scraper import USER_AGENT  # keine eigene UA-Konstante duplizieren

log = logging.getLogger("tuiwatch.check24")

_AUTOCOMPLETE_URL = "https://urlaub.check24.de/autocompleter-destination"
_OFFER_API_URL = "https://urlaub.check24.de/suche/json/dynamic/offer"
_HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "de-DE,de;q=0.9"}


def parse_hotel_link(url: str) -> dict | None:
    """hotelId aus einem Check24-Link (z. B. https://urlaub.check24.de/suche/
    angebot?...&hotelId=11829 oder .../suche/hotel?...&hotelId=11829). Nur
    hotelId ist Pflicht (areaId wird nicht gebraucht) — Fail-Soft wie
    scraper._giata_from_url."""
    try:
        q = parse_qs(urlparse((url or '').strip()).query)
    except Exception:
        return None
    hotel_id = (q.get('hotelId') or [''])[0]
    if not hotel_id.isdigit():
        return None
    return {'hotel_id': hotel_id}


# Check24s Verpflegungs-Filter ("Mind. Frühstück"/"Mind. Halbpension"/...) auf der
# Angebotsseite ist ein Query-Param, kein reiner Anzeige-Tab: ein Klick auf den Tab
# haengt `cateringList=<data-min-value>` an die URL (live per Netzwerk-Mitschnitt
# ermittelt, siehe SCRAPING_CHECK24.md). `data-min-value` ist "diese Stufe oder
# besser" — genau das richtige Verhalten, um zu verhindern, dass z. B. ein
# Halbpension-Angebot als "billigere Alternative" zu einem All-Inclusive-TUI-
# Angebot durchrutscht (Bugreport: TUI-Angebot AI, Check24 zeigte ungefiltert
# auch deutlich günstigere HP-Angebote).
_CATERING_LIST = {
    'none': 'none',
    'breakfast': 'breakfast,halfboard,halfboardPlus,fullboard,fullboardPlus,allinclusive,allinclusivePlus',
    'halfboard': 'halfboard,halfboardPlus,fullboard,fullboardPlus,allinclusive,allinclusivePlus',
    'fullboard': 'fullboard,fullboardPlus,allinclusive,allinclusivePlus',
    'allinclusive': 'allinclusive,allinclusivePlus',
}
# TUI-Verpflegungstexte (scraper.BOARD_TYPES) auf die Check24-Tab-Keys oben gemappt.
_BOARD_TO_CATERING_KEY = {
    'alles inklusive': 'allinclusive', 'all inclusive': 'allinclusive',
    'vollpension': 'fullboard', 'halbpension': 'halfboard',
    'frühstück': 'breakfast', 'übernachtung': 'none', 'ohne verpflegung': 'none',
}
# Umgekehrte Richtung: Check24s eigene mealType-Werte aus der Angebots-JSON
# (PascalCase, z. B. "AllInclusive") auf deutsche Texte, damit board_hint
# (aus offers.board, TUI-Text) per Substring dagegen matchen kann.
_MEAL_TYPE_TO_BOARD = {
    'AllInclusive': 'All Inclusive', 'AllInclusivePlus': 'All Inclusive Plus',
    'FullBoard': 'Vollpension', 'FullBoardPlus': 'Vollpension Plus',
    'HalfBoard': 'Halbpension', 'HalfBoardPlus': 'Halbpension Plus',
    'Breakfast': 'Frühstück', 'RoomOnly': 'Ohne Verpflegung', 'None': 'Ohne Verpflegung',
}


def _catering_list_for_board(board_hint: str) -> str:
    """cateringList-Query-Wert für einen TUI-Verpflegungstext, oder '' wenn
    unbekannt/leer (dann wird ungefiltert nach Verpflegung gesucht)."""
    key = _BOARD_TO_CATERING_KEY.get((board_hint or '').strip().lower(), '')
    return _CATERING_LIST.get(key, '')


def _build_offer_url(hotel_id: str, departure_date: str, return_date: str,
                     airport: str, room_allocation: str, catering_list: str = '') -> str:
    params = {
        'airport': airport or '', 'transportType': 'flight',
        'roomAllocation': room_allocation or 'A',
        'departureDate': departure_date, 'returnDate': return_date, 'days': 'exact',
        'pageArea': 'package', 'ds': 'h', 'sorting': 'categoryDistribution',
        'offerSort': 'offerRanking', 'areaSort': 'topregion', 'extendedSearch': '1',
        'noRedirect': '1', 'hotelId': hotel_id,
    }
    if catering_list:
        params['cateringList'] = catering_list
    return 'https://urlaub.check24.de/suche/hotel?' + urlencode(params)


def search_hotel(query: str, *, verbose: bool = False) -> list[dict] | None:
    """Sucht Hotels über Check24s Zielsuchfeld-API und liefert Kandidaten
    [{'hotel_id','name','location'}], sortiert wie von Check24 vorgeschlagen.
    None bei technischem Fehler, leere Liste bei keinem Treffer."""
    query = (query or '').strip()
    if not query:
        return []
    try:
        resp = requests.get(_AUTOCOMPLETE_URL,
                            params={'v': '2_0_0', 'term': query, 'agent': 'urlaub'},
                            headers={**_HEADERS, 'Accept': 'application/json'}, timeout=15)
        if resp.status_code != 200:
            log.warning("Check24-Hotelsuche HTTP %s (query=%r)", resp.status_code, query)
            return None
        data = resp.json()
    except Exception as e:
        log.warning("Check24-Hotelsuche fehlgeschlagen (query=%r): %s", query, e)
        return None

    out = []
    for grp in data.get('data') or []:
        if grp.get('group') != 'hotel':
            continue
        for item in grp.get('data') or []:
            hotel_id = item.get('id')
            if not hotel_id:
                continue
            location = ', '.join(x for x in (item.get('regionName'), item.get('countryName')) if x)
            out.append({'hotel_id': str(hotel_id), 'name': item.get('label') or '', 'location': location})

    # Die Suche matched auch Teilstrings/Umgebung (Ort, Region) mit, nicht nur
    # den Hotelnamen selbst — bei einer langen, spezifischen TUI-Hotelbezeichnung
    # kommen daher oft mehrere kaum verwandte Treffer zurück. Nach Ähnlichkeit zur
    # Anfrage sortieren; ist der beste Treffer eindeutig (nahezu exakter Name,
    # klarer Abstand zum zweitbesten), nur diesen zurückgeben — dann kann das
    # Frontend ohne Rückfrage direkt verknüpfen (kein Klick durch eine
    # Trefferliste nötig).
    qn = query.strip().lower()
    for o in out:
        o['_score'] = SequenceMatcher(None, qn, o['name'].strip().lower()).ratio()
    out.sort(key=lambda o: o['_score'], reverse=True)
    if out and out[0]['_score'] >= 0.92 and (len(out) == 1 or out[0]['_score'] - out[1]['_score'] >= 0.08):
        out = out[:1]
    for o in out:
        del o['_score']
    if not out:
        log.warning("Check24-Hotelsuche %r: 0 Treffer", query)
    elif verbose:
        log.info("Check24-Hotelsuche %r: %d Treffer", query, len(out))
    return out


def fetch_offers(hotel_id: str, departure_date: str, return_date: str,
                 airport: str, *, room_allocation: str = 'A', room_hint: str = '',
                 board_hint: str = '', verbose: bool = False) -> dict | None:
    """Liefert {'ok': bool, 'rows': [...], 'note': str, 'offer_url': str} oder
    None bei technischem Fehler (Aufrufer wiederholt dann, Konvention wie
    scraper.fetch_price_api()). Jede Zeile:
    {'operator','room','board','price','transfer','ok'}."""
    catering_list = _catering_list_for_board(board_hint)
    search_url = _build_offer_url(hotel_id, departure_date, return_date, airport,
                                  room_allocation, catering_list)
    form = {
        'transactionId': str(uuid.uuid4()), 'clientId': str(uuid.uuid4()),
        'previousSearchUrl': '', 'disableCache': '1', 'forceFailedVacancies': '0',
        'forceEstaHint': '0', 'forceErrorVacancies': '0', 'forceFlightTimeChange': '0',
        'forceCancellationNotAvailable': '0', 'searchUrl': search_url,
        'withTravelExperts': '1', 'isWithServiceInformation': '0', 'isWithPriceAlarm': '1',
    }
    headers = {**_HEADERS, 'Referer': search_url, 'X-Requested-With': 'XMLHttpRequest',
              'Content-Type': 'application/x-www-form-urlencoded'}
    data = None
    try:
        with requests.Session() as sess:
            # Job/Poll-Protokoll: derselbe POST erzeugt beim ersten Aufruf den
            # Suchjob (status "Pending") und liefert bei Wiederholung dessen
            # Fortschritt, bis "Success" (Angebote fertig, live beobachtet
            # ~8-15s) oder "Error" (z. B. Hotel/Termine ungültig). Kein
            # separater Poll-Endpoint nötig — live per Netzwerk-Mitschnitt
            # verifiziert, siehe SCRAPING_CHECK24.md.
            for _ in range(20):
                resp = sess.post(_OFFER_API_URL, data=form, headers=headers, timeout=20)
                if resp.status_code != 200:
                    log.warning("Check24-Abruf HTTP %s (hotelId=%s)", resp.status_code, hotel_id)
                    return None
                data = resp.json()
                if data.get('status') in ('Success', 'Error'):
                    break
                time.sleep(1.5)
            else:
                log.warning("Check24-Abruf Timeout (hotelId=%s)", hotel_id)
                return None
    except Exception as e:
        log.warning("Check24-Abruf fehlgeschlagen (hotelId=%s): %s", hotel_id, e)
        return None

    if data.get('status') == 'Error':
        # Kein technischer Fehler i. d. R. — ungültiges Hotel/Terminkombi ohne
        # Angebot (Datenverfügbarkeit, kein Protokollfehler).
        if verbose:
            log.info("Check24: Hotel %s an gewünschten Terminen nicht verfügbar", hotel_id)
        return {'ok': True, 'rows': [], 'note': 'not_available_exact_dates', 'offer_url': search_url}

    # Für den Board-Filter unten wird der rohe Check24-mealType parallel zur Zeile
    # mitgeführt (nicht im Rückgabe-dict) -- ein Textvergleich auf dem übersetzten
    # 'board'-Anzeigetext war ein Bugreport: TUI liefert "Alles Inklusive"
    # (deutsch), unser _MEAL_TYPE_TO_BOARD übersetzt AllInclusive aber zu "All
    # Inclusive" (englisch) -- "alles inklusive" in "all inclusive" matcht nie,
    # obwohl cateringList serverseitig längst korrekt gefiltert hatte.
    built = []
    for item in (data.get('items') or {}).values():
        price = (((item.get('price') or {}).get('effectivePrice') or {}).get('amount'))
        if price is None:
            continue
        acc = item.get('accommodationData') or {}
        room_desc = acc.get('roomDescription') or {}
        room = room_desc.get('description') or room_desc.get('name') or ''
        meal_type = acc.get('mealType') or ''
        board = _MEAL_TYPE_TO_BOARD.get(meal_type, meal_type)
        row = {
            'operator': item.get('tourOperatorAlias') or item.get('tourOperatorCode') or '',
            'room': room, 'board': board, 'price': float(price),
            'transfer': bool(acc.get('transfer')),
            'ok': True,
        }
        built.append((row, meal_type))

    rows = [r for r, _ in built]
    rows_before_board = rows
    if board_hint:
        # Bewusst KEIN Fallback auf ungefiltert bei 0 Treffern (anders als bei
        # room_hint unten): genau das führte zum ersten Bugreport ("Check24
        # zeigt deutlich günstigere Angebote, Verpflegung stimmt nicht").
        allowed_tiers = {t.lower() for t in catering_list.split(',')} if catering_list else set()
        if allowed_tiers:
            # Gegen dieselben Tier-Codes vergleichen, die schon in der
            # cateringList-Anfrage steckten (case-insensitive) -- robust
            # gegen DE/EN-Wortlaut-Unterschiede zwischen TUI- und
            # Check24-Anzeigetexten.
            rows = [r for r, mt in built if mt.lower() in allowed_tiers]
        else:
            # board_hint ohne bekannte Tier-Zuordnung (siehe
            # _BOARD_TO_CATERING_KEY) -- schwächerer Textfilter als Notlösung.
            bh = board_hint.strip().lower()
            rows = [r for r in rows if bh in (r['board'] or '').lower()]
    if room_hint:
        rh = room_hint.strip().lower()
        filtered = [r for r in rows if rh in (r['room'] or '').lower()]
        rows = filtered or rows
    rows.sort(key=lambda r: r['price'])
    if not rows:
        note = 'no_offers_for_board' if (board_hint and rows_before_board) else 'no_offers_parsed'
        return {'ok': True, 'rows': [], 'note': note, 'offer_url': search_url}
    return {'ok': True, 'rows': rows, 'note': '', 'offer_url': search_url}
