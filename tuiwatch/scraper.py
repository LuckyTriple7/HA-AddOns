#!/usr/bin/env python3
"""TUI-Angebotspreis per Headless-Chromium auslesen.

Die TUI-Angebotsseite rendert Preise erst per JavaScript; ein statischer Abruf
liefert nichts. Wir laden die Seite mit Playwright/Chromium, klicken den
Cookie-Consent weg und lesen die **erste (= günstigste) Angebotskarte**
(`div.offer-card__content`) aus — das ist der konkrete, buchbare Preis
("Günstigster Preis") inkl. Flugdetails. Optional wird "Verfügbarkeit prüfen"
geklickt, um Verfügbarkeit + bestätigten Gesamtpreis zu erfassen.

Lokal nutzt Playwright sein gebündeltes Chromium; im Add-on-Container wird das
System-Chromium über die Umgebungsvariable CHROMIUM_PATH gesetzt.

Details zur Wartung bei TUI-Layout-Änderungen: siehe SCRAPING.md.
"""
import logging
import os
import re
import time
from datetime import date, datetime, timedelta
from urllib.parse import (parse_qs, parse_qsl, unquote, urlencode, urlparse,
                          urlunparse)

import requests
# playwright wird nur für den Browser-Fallback gebraucht und erst dort (lazy) importiert
# (siehe _fetch_price_browser). So lässt sich scraper.py auch ohne installiertes
# playwright importieren — z. B. für die Parsing-Tests.

# Eigener Logger; hängt über den Root-Handler in der UI-Konsole (siehe app.py).
log = logging.getLogger("tuiwatch.scraper")

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36")

CONSENT_SELECTORS = [
    "#cmm-accept-all",
    "button[data-testid='uc-accept-all-button']",
    "#onetrust-accept-btn-handler",
    "button:has-text('Alle akzeptieren')",
    "button:has-text('Akzeptieren')",
    "button:has-text('Zustimmen')",
]

BEST_OFFER_SELECTOR = "div.tui-hotel-best-offer"   # nur als Lade-Signal
OFFER_CARD_SELECTOR = "div.offer-card__content"    # konkrete Angebote (aufst. sortiert)
HOTEL_NAME_SELECTOR = "h1.tui-hotel-name__title"

_PRICE_RE = re.compile(r"pro Person\s*([\d.\s]+(?:,\d{2})?)\s*€", re.IGNORECASE)
_OLDPRICE_RE = re.compile(r"(\d{1,2})\s*%\s*([\d.\s]+(?:,\d{2})?)\s*€")  # "- 7% 2.129 €"
_TOTAL_RE = re.compile(r"Gesamtpreis\s*([\d.\s]+(?:,\d{2})?)\s*€", re.IGNORECASE)
_AIRPORT_RE = re.compile(r"^.+\([A-Z]{3}\)$")
_ROOMCODE_RE = re.compile(r"\([A-Z]{2,}\d+[A-Z0-9]*\)")          # z. B. (DZX1)
_FLIGHTLINE_RE = re.compile(r"\d{1,2}\.\d{2}\.\d{4},?\s*\d{1,2}:\d{2}")
_NIGHTS_RE = re.compile(r"\d+\s*Nächte")
_TRAVELLERS_RE = re.compile(r"\d+\s*(Erwachsene[r]?|Kind|Kinder)")
BOARD_TYPES = ("Alles Inklusive", "All Inclusive", "Vollpension", "Halbpension",
               "Frühstück", "Übernachtung", "Ohne Verpflegung")


def hotel_from_url(url: str) -> str:
    """Fallback-Hotelname aus der URL: …/angebote/Riu-Papayas/2781/… → 'Riu Papayas'."""
    try:
        parts = [p for p in urlparse(url).path.split('/') if p]
        if 'angebote' in parts:
            seg = parts[parts.index('angebote') + 1]
            name = unquote(seg).replace('-', ' ').strip()
            return name if name and not name.isdigit() else ''
    except Exception as e:
        log.debug("hotel_from_url: URL nicht parsbar (%s): %s", url, e)
    return ''


def travellers_from_url(url: str) -> int:
    """Liest die Reisendenzahl aus dem URL-Parameter `travellers=` (Default 1)."""
    try:
        for k, v in parse_qsl(urlparse(url).query, keep_blank_values=True):
            if k == 'travellers':
                n = int(v)
                return n if n > 0 else 1
    except Exception as e:
        log.debug("travellers_from_url: URL nicht parsbar (%s): %s", url, e)
    return 1


def duration_from_url(url: str) -> int | None:
    """Liest die Reisedauer (Nächte) aus dem URL-Parameter `duration=`. Bereiche wie
    '9-12'/'7-' → untere Zahl (via _single_duration). None, wenn nicht vorhanden."""
    try:
        for k, v in parse_qsl(urlparse(url).query, keep_blank_values=True):
            if k == 'duration':
                d = _single_duration(v)
                return int(d) if d else None
    except (TypeError, ValueError):
        pass
    return None


def _replace_query(url: str, *, set_params: dict | None = None,
                   drop_keys: tuple = ()) -> str:
    """Baut die URL mit veränderter Query neu auf (Reihenfolge bleibt erhalten)."""
    p = urlparse(url)
    pairs = parse_qsl(p.query, keep_blank_values=True)
    set_params = set_params or {}
    seen: set[str] = set()
    out = []
    for k, v in pairs:
        if k in drop_keys:
            continue
        if k in set_params:
            out.append((k, str(set_params[k])))
            seen.add(k)
        else:
            out.append((k, v))
    for k, v in set_params.items():
        if k not in seen:
            out.append((k, str(v)))
    return urlunparse(p._replace(query=urlencode(out)))


def with_travellers(url: str, n: int) -> str:
    """Gibt die URL mit `travellers=n` zurück."""
    return _replace_query(url, set_params={'travellers': n})


def without_room_code(url: str) -> str:
    """Entfernt `roomTypeOpCodes` (Fallback, falls fester Zimmercode eine andere
    Belegung verhindert)."""
    return _replace_query(url, drop_keys=('roomTypeOpCodes',))


def with_room_code(url: str, code: str) -> str:
    """Gibt die URL mit fixem Zimmer (`roomTypeOpCodes=code`) zurück; leerer Code →
    entfernt die Festlegung (= wieder automatisch das günstigste Zimmer)."""
    code = (code or '').strip()
    if not code:
        return without_room_code(url)
    return _replace_query(url, set_params={'roomTypeOpCodes': code})


def room_code_from_url(url: str) -> str:
    """Liest den aktuell fixierten Zimmercode (`roomTypeOpCodes`) aus der URL (oder '')."""
    try:
        for k, v in parse_qsl(urlparse(url).query, keep_blank_values=True):
            if k == 'roomTypeOpCodes' and v.strip():
                return v.strip()
    except (TypeError, ValueError):
        pass
    return ''


def transfer_included_from_url(url: str) -> bool:
    """Liest `transferIncluded` aus der URL (Default True, siehe build_offer_api_url)."""
    try:
        for k, v in parse_qsl(urlparse(url).query, keep_blank_values=True):
            if k == 'transferIncluded':
                return v.strip().lower() != 'false'
    except (TypeError, ValueError):
        pass
    return True


def with_transfer_included(url: str, included: bool) -> str:
    """Gibt die URL mit fest gesetztem `transferIncluded` zurück. Manche Hotels
    (z. B. Selbstanreise/Mietwagen-Regionen) bieten gar kein Transfer-Paket —
    dort liefert die Offer-API bei transferIncluded=true 0 Treffer, obwohl auf
    tui.com ganz normal buchbare (Nicht-Transfer-)Angebote existieren."""
    return _replace_query(url, set_params={'transferIncluded': 'true' if included else 'false'})


def _url_has_transfer_param(url: str) -> bool:
    try:
        return any(k == 'transferIncluded'
                   for k, _ in parse_qsl(urlparse(url).query, keep_blank_values=True))
    except (TypeError, ValueError):
        return False


def with_duration(url: str, n: int) -> str:
    """Gibt die URL mit `duration=n` (Nächte) zurück. Falls die URL ein festes
    Reisefenster (`startDate`/`endDate`) hat, das schmaler als die gewünschte Dauer ist
    (z. B. ein aus dem Kalender getrackter Einzeltermin: Fenster = exakt 7 Nächte), wird
    `endDate` auf `startDate + n` geweitet — sonst liefert die API für längere Dauern
    kein Angebot. Breitere Fenster bleiben unverändert."""
    params: dict = {'duration': n}
    q = {k: v for k, v in parse_qsl(urlparse(url).query, keep_blank_values=True)}
    sd, ed = q.get('startDate', ''), q.get('endDate', '')
    try:
        d0 = date.fromisoformat(sd)
        need = (d0 + timedelta(days=int(n))).isoformat()
        cur = date.fromisoformat(ed) if ed else None
        if cur is None or cur < date.fromisoformat(need):
            params['endDate'] = need
    except (TypeError, ValueError):
        pass
    return _replace_query(url, set_params=params)


def is_single_room(text: str) -> bool:
    """True, wenn der Text auf ein Einzelzimmer hindeutet (kein 2-Personen-Vergleich)."""
    t = (text or '').lower()
    return 'einzelzimmer' in t or 'single room' in t or 'single-room' in t


def _to_amount(raw: str) -> float | None:
    s = (raw or '').strip().replace(" ", "").replace("\xa0", "")
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _parse_flights(lines: list[str]) -> tuple[str, list[str]]:
    """Liest Abflughafen + bis zu zwei Flug-Legs aus den Kartenzeilen.
    Rückgabe: (abflughafen, [hin, rück]) als lesbare Strings."""
    airport = ''
    for ln in lines[:4]:
        if _AIRPORT_RE.match(ln):
            airport = ln
            break
    legs: list[str] = []
    for i, ln in enumerate(lines):
        if _FLIGHTLINE_RE.search(ln):
            datetime_txt = re.sub(r"\s+", " ", ln).strip()
            airline, stops = '', ''
            for nxt in lines[i + 1:i + 4]:
                if nxt in ('Direktflug',) or 'Stopp' in nxt or 'Umstieg' in nxt or 'Zwischenstopp' in nxt:
                    stops = nxt
                elif not airline and nxt not in BOARD_TYPES and not _FLIGHTLINE_RE.search(nxt) \
                        and 'Flugdetails' not in nxt:
                    airline = nxt
            parts = [datetime_txt] + [x for x in (airline, stops) if x]
            legs.append(" · ".join(parts))
        if len(legs) >= 2:
            break
    return airport, legs


def _parse_card(text: str) -> dict:
    """Extrahiert Preis/Flug/Zimmer-Daten aus dem Text einer Angebotskarte."""
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines() if ln.strip()]
    out: dict = {}

    m = _PRICE_RE.search(text)
    out['price'] = _to_amount(m.group(1)) if m else None
    om = _OLDPRICE_RE.search(text)
    if om:
        out['discount'] = int(om.group(1))
        out['old_price'] = _to_amount(om.group(2))

    # Zimmer = Zeile mit Zimmer-Code (DZX1), nicht der Flughafen
    for ln in lines:
        if _ROOMCODE_RE.search(ln) and not _AIRPORT_RE.match(ln):
            out['room'] = ln
            break
    for ln in lines:
        for b in BOARD_TYPES:
            if ln.startswith(b):
                out['board'] = ln
                break
        if out.get('board'):
            break
    nm = _NIGHTS_RE.search(text)
    out['nights'] = nm.group(0).strip() if nm else ''
    tm = _TRAVELLERS_RE.search(text)
    out['travellers'] = tm.group(0).strip() if tm else ''

    airport, legs = _parse_flights(lines)
    out['dep_airport'] = airport
    out['flight_out'] = legs[0] if len(legs) > 0 else ''
    out['flight_ret'] = legs[1] if len(legs) > 1 else ''
    return out


def _empty_result() -> dict:
    return {"ok": False, "price": None, "currency": "EUR", "old_price": None,
            "discount": None, "hotel": "", "room": "", "board": "", "nights": "",
            "travellers": "", "dep_airport": "", "flight_out": "", "flight_ret": "",
            "details": "", "available": None, "total_price": None,
            "cancellation": "", "stars": None, "rating": None, "rating_count": None,
            "recommendation": None, "location": "", "city": "", "region": "",
            "country": "", "pdf_url": "", "travellers_count": None,
            "booking_code": "", "room_booking_code": "",
            "vac_status": "", "price_hotel": None, "price_flight_out": None,
            "price_flight_ret": None, "last_booked": "",
            "errata": None, "flight_segments": None, "hotel_supplier": None,
            "flight_flags": None,
            "flight_options": None, "flight_pin_missed": False,
            "luggage": None, "deposit_pct": None, "final_payment_date": "",
            "source": "", "note": "", "detail": ""}


# ── JSON-API (bevorzugt) ────────────────────────────────────────────────────────
# Die TUI-Angebotsseite versorgt sich aus offenen JSON-Endpoints (CloudFront), die
# direkt – ohne Browser – abrufbar sind. Das ist schneller und robuster als das
# Parsen des gerenderten HTML. Bricht das (z. B. Host rotiert), greift der
# Browser-Fallback _fetch_price_browser(). Siehe SCRAPING.md.
OFFER_API = "https://d2z3tkv1undzra.cloudfront.net/data"      # Angebote inkl. Preis
CONTENT_API = "https://d1pagbczmuq2ek.cloudfront.net/data"    # Sterne + Bewertung
CALENDAR_API = "https://d18axsujemfwj.cloudfront.net/data"    # Preiskalender (Tag→Preis)
# Breadcrumb (Ort/Region) auf stabilem API-Host; .../{tenant}/{locale}/{typ=3 Hotel}/{giataId}
BREADCRUMB_API = "https://api.cloud.tui.com/breadcrumb/v1/data/TUICOM/de-DE/3/"
HOTELINFO_PDF = "https://www.tui.com/api/hotelInfoPdf"  # Hotelbeschreibung als PDF
# Hotelsuche (Region → Trefferliste). POST mit JSON-Body, stabiler API-Host.
SEARCH_API = "https://api.cloud.tui.com/hotel-offer-cards/v2/search/TUICOM"
# Reiseziel-Picker (Regionen/Unterregionen) + Abflughäfen.
DEST_API = "https://api.cloud.tui.com/search-destination/v2"
AIRPORTS_API = "https://api.cloud.tui.com/search-departure-airport/v2"
VACANCY_API = "https://d2z3tkv1undzra.cloudfront.net/vacancy-check"  # Live-Bestätigung (ATCOMRES)
LUGGAGE_API = "https://api.cloud.tui.com/flight-luggage-api/get"     # Inklusiv-Gepäck je Flugroute
LAST_BOOKED_API = "https://d3hw3spwqlykxv.cloudfront.net/hotel-last-booked/TUICOM/"
HOTEL_CONTENT_API = "https://d2tzlxlrauxuk9.cloudfront.net/data"     # Adresse inkl. countryCode
PAYMENT_API = "https://www.tui.com/api/paymentService/payments"      # Zahlarten/Anzahlung
# Konstanten, mit denen das TUI-Buchungs-Frontend selbst die Endpoints aufruft
# (per Netzwerk-Mitschnitt ermittelt, siehe SCRAPING.md → vacancy-check).
_BOOKING_AGENCY = "021245"
_BOOKING_AGENT = "0000"
_BOOKING_CHANNEL = "TUIIA"
_API_HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}
_SEARCH_HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json",
                   "Content-Type": "application/json", "Origin": "https://www.tui.com",
                   "Referer": "https://www.tui.com/"}


def _giata_from_url(url: str) -> str:
    """giataId aus dem Pfad …/angebote/<Hotel>/<giataId>/… ."""
    try:
        parts = [p for p in urlparse(url).path.split('/') if p]
        if 'angebote' in parts:
            for seg in parts[parts.index('angebote') + 1:parts.index('angebote') + 3]:
                if seg.isdigit():
                    return seg
    except Exception:
        pass
    return ''


# Die Angebots-/Kalender-API (CloudFront) nutzt für "Frühstück" intern ``BR``, während
# Seiten-URL, Such-API und die eigene Hotelsuche (siehe index.html) ``BB`` verwenden —
# per Live-Test an 3 unabhängigen Hotels verifiziert (giata 6649/6672/20514/674842):
# GT06-BB liefert dort durchweg 0 Treffer, GT06-BR die echten Frühstücks-Angebote.
# AI/HB/FB/AO passen unverändert (kein Eintrag hier nötig).
_BOARD_CODE_ALIASES = {'BB': 'BR'}


def _map_board_types(val: str) -> str:
    """Übersetzt die Verpflegungs-Kurzcodes der Seiten-URL (z. B. ``AI``) in die
    globalen Codes der Angebots-/Kalender-API (``GT06-AI``). Mehrfachwerte (``,``/``;``)
    bleiben erhalten. ``BB`` (Frühstück) wird dabei auf ``BR`` übersetzt, siehe
    _BOARD_CODE_ALIASES."""
    out = []
    for t in re.split(r'[;,]', val or ''):
        t = t.strip().upper()
        if not t:
            continue
        bare = t[5:] if t.startswith('GT06-') else t
        bare = _BOARD_CODE_ALIASES.get(bare, bare)
        out.append('GT06-' + bare)
    return ','.join(out)


# „Lage"-Filter (URL-Parameter `locationAttributes=<id>`, mit `;` kombinierbar): anders
# als bei der Verpflegung kennt die Such-API (SEARCH_API) keine einfache ID — tui.com
# übersetzt sie selbst client-seitig in einen kryptischen `logicalExpression`-Code,
# bevor die Anfrage rausgeht (per Live-Test gegen die echte API ermittelt und
# verifiziert: ein einfaches `"locationAttributes": [9]`-Feld wird stillschweigend
# ignoriert). Mehrere Attribute werden mit ` + ` (AND, per Live-Test bestätigt: schränkt
# die Trefferzahl weiter ein) zu einem gemeinsamen Ausdruck verbunden.
_LOCATION_ATTRS: dict[int, str] = {
    9: "GT03-DIBE#ST03-DIRE",                                          # Direkt am Strand
    10: "( GT03-DIBE#ST03-D500M | GT03-DIBE#ST03-D100M | "
        "GT03-DIBE#ST03-D200M | GT03-DIBE#ST03-D300M | "
        "GT03-DIBE#ST03-D400M | GT03-DIBE#ST03-D50M )",                # Strand < 500m
    11: "GT03-BEAC#ST03-SAND",                                         # Sandstrand
    12: "GT03-OUTS",                                                   # Außerhalb des Ortes
    14: "GT03-QUIE",                                                   # Ruhig
    37: "GT13-SESI",                                                   # Meerseite
}


def _location_expression(ids: list) -> str:
    """Baut aus den Lage-Filter-IDs den `logicalExpression`-String für die Such-API.
    Unbekannte IDs werden ignoriert (kein Fehler)."""
    parts = [_LOCATION_ATTRS[i] for i in ids if i in _LOCATION_ATTRS]
    return " + ".join(parts)


# „Ausstattung"-Filter (URL-Parameter `facilityAttributes=<id>`) — gleiches Prinzip wie
# `_LOCATION_ATTRS`: kein einfaches Feld, sondern ein `logicalExpression`-Code. Der Code
# für „Nur Erwachsene" (id 13) wurde nicht durch Raten ermittelt, sondern per Playwright
# live abgefangen (echten `hotel-offer-cards`-POST-Request auf tui.com mitgeschnitten,
# mit `facilityAttributes=13` in der Such-URL) und anschließend gegen die echte Such-API
# verifiziert (100 → 28 Treffer für Gran Canaria, ausschließlich adults-only-artige Hotels).
_FACILITY_ATTRS: dict[int, str] = {
    13: "GT03#TUI-G0978",   # Nur Erwachsene (Adults Only)
}


def _facility_expression(ids: list) -> str:
    """Baut aus den Ausstattungs-Filter-IDs den `logicalExpression`-String für die
    Such-API. Unbekannte IDs werden ignoriert (kein Fehler)."""
    parts = [_FACILITY_ATTRS[i] for i in ids if i in _FACILITY_ATTRS]
    return " + ".join(parts)


# Live gegen die echte Suche verifiziert (locationAttributes=<id> filtern, dann prüfen,
# welcher Code bei ALLEN gefilterten Treffern im hotelseitigen globalTypes-Katalog
# steckt): 5 von 6 Lage-Attributen sind darüber pro Hotel ablesbar — anders als die
# `_LOCATION_ATTRS`-Ausdrücke (die den Filter-Query bauen), stehen hier direkt die
# globalTypes-Codes drin, die ein Treffer trägt. "Meerseite" (id 37) fehlt bewusst:
# der Filter funktioniert (GT13-SESI schränkt ein), aber kein GT13-Code taucht je im
# globalTypes zurückgegebener Hotels auf (0/50 in zwei unabhängigen Stichproben) —
# nicht aus dem Suchresponse anzeigbar, nur serverseitig filterbar.
_LOCATION_BADGES: dict[int, tuple[str, frozenset]] = {
    9: ("Direkt am Strand", frozenset({"GT03-DIBE/ST03-DIRE"})),
    10: ("Strand < 500m", frozenset({
        "GT03-DIBE/ST03-D500M", "GT03-DIBE/ST03-D100M", "GT03-DIBE/ST03-D200M",
        "GT03-DIBE/ST03-D300M", "GT03-DIBE/ST03-D400M", "GT03-DIBE/ST03-D50M"})),
    11: ("Sandstrand", frozenset({"GT03-BEAC/ST03-SAND"})),
    12: ("Außerhalb", frozenset({"GT03-OUTS"})),
    14: ("Ruhig", frozenset({"GT03-QUIE"})),
}


def _location_labels(hotel_codes) -> list:
    """Welche Lage-Badges (siehe `_LOCATION_BADGES`) für ein Hotel zutreffen,
    anhand seiner globalTypes-Codes aus dem Suchtreffer."""
    codes = set(hotel_codes or [])
    return [label for label, candidates in _LOCATION_BADGES.values()
            if codes & candidates]


def build_offer_api_url(url: str, travellers: int | None = None) -> str:
    """Baut die Offer-JSON-API-URL aus den Parametern der Angebots-Seiten-URL.
    Wichtig: **alle** Filter der Original-URL (Verpflegung, Veranstalter, Zimmer-/
    Sicht-Typen, Stopps, Preisgrenzen) werden übernommen — sonst liefert die API ein
    anderes (billigeres) Angebot als das vom Nutzer gewählte."""
    p = urlparse(url)
    q = {k: v[0] for k, v in parse_qs(p.query, keep_blank_values=True).items()}
    params = {
        'giataId': _giata_from_url(url), 'locale': 'de_DE', 'tenant': 'TUICOM',
        'startDate': q.get('startDate', ''), 'endDate': q.get('endDate', ''),
        'durations': q.get('duration', ''),
        'searchScope': q.get('searchScope', 'PACKAGE'),
        'travellers': str(travellers) if travellers else q.get('travellers', '1'),
        'maxStopOvers': q.get('maxStopOvers', ''),
        'roomTypes': q.get('roomTypes', ''),
        'boardTypes': _map_board_types(q.get('boardTypes', '')),
        'extraTypes': q.get('extraTypes', ''),
        'viewTypes': q.get('viewTypes', ''),
        'airports': q.get('departureAirports', ''),
        'airlines': q.get('airlines', ''),
        'roomTypeOpCodes': q.get('roomTypeOpCodes', ''),
        'tourOperators': q.get('operators', q.get('tourOperators', '')),
        'departureMinTime': '', 'departureMaxTime': '', 'returnMinTime': '',
        'returnMaxTime': '',
        'minPrice': q.get('minPrice', ''), 'maxPrice': q.get('maxPrice', ''),
        'campaignGlobalTypes': 'GT07-DISC;GT07-TOY;GT07-SAVE',
        'lang': 'de_DE',
        # Pauschalreise inkl. Transfer: Standard true (so wie tui.com), Wert aus der
        # Original-URL hat aber Vorrang, falls dort explizit gesetzt.
        'transferIncluded': q.get('transferIncluded', 'true'),
    }
    return f"{OFFER_API}?{urlencode(params)}"


def _single_duration(d: str) -> str:
    """Aus einer Dauer-Angabe (auch Bereich wie '7-' oder '9-12') die untere Zahl."""
    m = re.match(r'\d+', d or '')
    return m.group(0) if m else (d or '')


def build_calendar_api_url(url: str, *, start: str, end: str) -> str:
    """Baut die Preiskalender-API-URL aus der Angebots-Seiten-URL für ein konkretes
    Suchfenster [start, end]. Übernimmt die Filter (Verpflegung, Veranstalter, Zimmercode,
    Abflughafen). Die Kalender-API liefert nur ein begrenztes Fenster (~12 Monate) ab
    `startSearchRange`; fetch_calendar ruft diese URL daher mehrfach mit fortlaufendem
    Startdatum auf (Paginierung) und fügt die Ergebnisse zusammen."""
    p = urlparse(url)
    q = {k: v[0] for k, v in parse_qs(p.query, keep_blank_values=True).items()}
    params = {
        'searchscope': q.get('searchScope', 'PACKAGE'),
        # Der Kalender erwartet eine EINZELNE Dauer; aus Bereichen wie "7-"/"9-12"
        # nehmen wir die untere Zahl (so macht es auch die TUI-Seite).
        'duration': _single_duration(q.get('duration', '')),
        'adults': q.get('travellers', '1'),
        'giatas': _giata_from_url(url),
        'startSearchRange': start, 'endSearchRange': end,
        'tenant': 'tui.com',
        'airports': q.get('departureAirports', ''),
        'roomTypeOpCodes': q.get('roomTypeOpCodes', ''),
        # Achtung: der Kalender-Endpoint nutzt andere Parameternamen als der
        # Offer-Endpoint — Verpflegung = boardCodes, Veranstalter = tourOperators.
        'boardCodes': _map_board_types(q.get('boardTypes', '')),
        'tourOperators': q.get('operators', q.get('tourOperators', '')),
        'startDate': start, 'endDate': end,
    }
    return f"{CALENDAR_API}?{urlencode(params)}"


def fetch_calendar(url: str, *, verbose: bool = False) -> dict | None:
    """Liest den Preiskalender (günstigster Preis p. P. je Abreisetag) direkt aus der
    JSON-API. Deckt die volle Spanne vom aktuellen Monat bis über den Reisezeitraum
    hinaus ab: Da die API pro Aufruf nur ~12 Monate ab `startSearchRange` liefert, wird
    ab heute mehrfach paginiert (jeweils weiter ab dem zuletzt gelieferten Datum) und die
    Tage werden zusammengeführt. Rückgabe-dict oder None bei technischem Fehler."""
    q = {k: v[0] for k, v in parse_qs(urlparse(url).query, keep_blank_values=True).items()}
    ws, we = q.get('startDate', ''), q.get('endDate', '')

    def _parse(d):
        try:
            return date.fromisoformat(d)
        except Exception:
            return None

    today = date.today()
    trip_end = _parse(we) or _parse(ws) or today
    # Zielhorizont: großzügig über den Reisezeitraum hinaus (bzw. mind. ~18 Monate).
    target = max(trip_end + timedelta(days=180), today + timedelta(days=540))
    target_iso = target.isoformat()

    days: dict[str, float] = {}
    currency = 'EUR'
    cursor = today                 # zurück bis zum aktuellen Monat
    prev_max: str | None = None
    any_ok = False
    for _ in range(6):             # Sicherheits-Cap gegen Endlosschleifen
        cal_url = build_calendar_api_url(url, start=cursor.isoformat(), end=target_iso)
        if verbose:
            log.info("Kalender-API GET %s", cal_url)
        try:
            resp = requests.get(cal_url, headers=_API_HEADERS, timeout=25)
            if resp.status_code != 200:
                if verbose:
                    log.warning(f"Kalender HTTP {resp.status_code}")
                break
            data = resp.json()
        except Exception as e:
            if verbose:
                log.warning(f"Kalender-Fehler: {type(e).__name__}: {e}")
            break
        any_ok = True
        currency = data.get('currency', currency)
        batch_max: str | None = None
        for o in data.get('offers') or []:
            ad = o.get('arrivalDate')
            pp = o.get('calculatedPricePerPerson')
            if ad and pp is not None:
                days[ad] = min(days.get(ad, float('inf')), pp)
                if batch_max is None or ad > batch_max:
                    batch_max = ad
        if batch_max is None:                      # nichts (mehr) im Fenster
            break
        if prev_max is not None and batch_max <= prev_max:
            break                                  # kein Fortschritt → Inventarende
        prev_max = batch_max
        if batch_max >= target_iso:                # Zielhorizont erreicht
            break
        cursor = (_parse(batch_max[:10]) or today) + timedelta(days=1)

    if not any_ok:
        return None
    # Nächte (für die Rückreise-Berechnung beim Klick: endDate = Anreise + Nächte).
    # Aus Dauer-Bereichen wie "7-"/"9-12" die untere Zahl, wie es auch tui.com nutzt.
    try:
        nights = int(_single_duration(q.get('duration', '')))
    except (TypeError, ValueError):
        nights = None
    res = {
        'ok': bool(days),
        'currency': currency,
        'window_start': ws, 'window_end': we,
        'duration': nights,
        'days': [{'date': d, 'price': int(round(days[d]))} for d in sorted(days)],
    }
    in_window = {d: pr for d, pr in days.items()
                 if (not ws or d >= ws) and (not we or d <= we)}
    if in_window:
        cd = min(in_window, key=in_window.get)
        res['tracked_date'] = cd
        res['tracked_price'] = int(round(in_window[cd]))
    if days:
        od = min(days, key=days.get)
        res['cheapest_date'] = od
        res['cheapest_price'] = int(round(days[od]))
        # Teuerster Termin als Gegenstück: erst mit beiden Enden lässt sich die
        # Spanne einschätzen — ein „günstigster Termin" allein sagt nichts darüber,
        # wie viel die Wahl des Datums überhaupt ausmacht.
        xd = max(days, key=days.get)
        res['priciest_date'] = xd
        res['priciest_price'] = int(round(days[xd]))
    if verbose:
        log.info(f"Kalender: {len(days)} Tage, günstigster {res.get('cheapest_date')} "
              f"= {res.get('cheapest_price')} €, teuerster {res.get('priciest_date')} "
              f"= {res.get('priciest_price')} €")
    return res


def fetch_rooms(url: str, *, verbose: bool = False) -> dict | None:
    """Liest die wählbaren Zimmer(-kategorien) für ein Angebot aus der Offer-API. Ohne
    `roomTypeOpCodes`-Filter liefert die API alle Zimmer; wir gruppieren nach Zimmercode
    und nehmen je Zimmer den günstigsten Preis p. P. Rückgabe:
    {ok, currency, rooms:[{code, name, board, price, url}]} (nach Preis sortiert) oder
    {ok:False, note} bzw. None bei technischem Fehler."""
    try:
        api = build_offer_api_url(without_room_code(url))
        if verbose:
            log.info("Zimmer-API GET %s", api)
        resp = requests.get(api, headers=_API_HEADERS, timeout=25)
        if resp.status_code != 200:
            if resp.status_code in (400, 404, 422):
                return {"ok": False, "rooms": [], "note": "Keine Zimmer im gewählten Zeitraum"}
            return None
        data = resp.json()
    except Exception as e:
        if verbose:
            log.warning(f"Zimmer-Fehler: {type(e).__name__}: {e}")
        return None

    if not data.get("offers") and not _url_has_transfer_param(url):
        # Fallback wie in fetch_price_api: Hotels ohne Transfer-Paket liefern bei
        # transferIncluded=true (Default) 0 Zimmer, obwohl auf tui.com welche buchbar sind.
        try:
            api2 = build_offer_api_url(with_transfer_included(without_room_code(url), False))
            resp2 = requests.get(api2, headers=_API_HEADERS, timeout=25)
            data2 = resp2.json() if resp2.status_code == 200 else {}
            if data2.get("offers"):
                data = data2
                if verbose:
                    log.info("Zimmer-API: Fallback ohne Transfer-Paket → %d Angebot(e)",
                             len(data["offers"]))
        except Exception:
            pass

    rooms: dict[str, dict] = {}
    for o in data.get("offers") or []:
        rm = (o.get("rooms") or [{}])[0]
        code = (rm.get("code") or "").strip()
        price = o.get("calculatedPricePerPerson")
        if not code or price is None:
            continue
        cur = rooms.get(code)
        if cur is None or price < cur["price"]:
            rooms[code] = {
                "code": code,
                "name": rm.get("description", "") or code,
                "board": rm.get("boardDescription", ""),
                "price": float(price),
                "url": with_room_code(url, code),
            }
    out = sorted(rooms.values(), key=lambda r: r["price"])
    for r in out:
        r["price"] = int(round(r["price"]))
    if verbose:
        log.info("Zimmer: %d Kategorien (%s)", len(out),
                 ", ".join(f"{r['code']}={r['price']}" for r in out) or "keine")
    return {"ok": bool(out), "currency": data.get("currency", "EUR"), "rooms": out,
            "note": "" if out else "Keine Zimmer gefunden"}


# ── Hotelsuche (Region → Trefferliste) ──────────────────────────────────────────

def _slugify(name: str) -> str:
    s = (name or "").strip().lower()
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "hotel"


def _split_multi(val: str) -> list:
    return [x.strip() for x in re.split(r"[;,]", val or "") if x.strip()]


_GIATA_IMG_RE = re.compile(r'https?://i\.giatamedia\.com/s\.php\?[^"\'\s>]+')
_GIATA_PAGE_RE = re.compile(r'[?&]site=(\d+)')
_GIATA_UID = "782"  # TUIs GIATA-Kundennummer, aus TUI-Angebotslinks bekannt


def fetch_giata_image_urls(giata: str, limit: int = 24, max_pages: int = 8) -> list[dict]:
    """Bilder-URLs von der öffentlichen GIATA-Hotelseite (com=sc). Liefert nur
    die Original-URLs (i.giatamedia.com) zum direkten Einbetten — kein Download,
    keine eigene Speicherung der Bilddaten. Die Seite listet Kataloge, nicht
    Fotos — bei vielen Katalogen (>~30) ist das Ergebnis paginiert (`&site=N`);
    ohne die Folgeseiten fehlen dann echte, zusätzliche Hotelfotos."""
    if not giata:
        return []
    base = (f"https://hg15.giatamedia.com/index2.php?uid={_GIATA_UID}&com=sc"
            f"&gid={giata}&frame=0&from=ks&catlang%5B%5D=de")
    seen = set()
    out = []
    total_pages = 1
    page = 1
    fetch_failed = False
    while page <= total_pages and page <= max_pages and len(out) < limit:
        page_url = base if page == 1 else f"{base}&site={page}"
        try:
            resp = requests.get(page_url, headers={"User-Agent": USER_AGENT}, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            log.warning("GIATA-Bilder giataId %s (Seite %d) nicht abrufbar: %s", giata, page, e)
            fetch_failed = True
            break
        if page == 1:
            page_nums = [int(n) for n in _GIATA_PAGE_RE.findall(resp.text)]
            if page_nums:
                total_pages = max(page_nums)
        for src in _GIATA_IMG_RE.findall(resp.text):
            src = src.replace('&amp;', '&')
            q = parse_qs(urlparse(src).query)
            iid = q.get('iid', [None])[0]
            key = iid or src
            if key in seen:
                continue
            seen.add(key)
            out.append({'thumb': re.sub(r'size=\d+', 'size=150', src),
                        'full': re.sub(r'size=\d+', 'size=800', src)})
            if len(out) >= limit:
                break
        page += 1
    if not out and not fetch_failed:
        log.warning("GIATA-Bilder giataId %s: Seite(n) geladen, aber keine Bilder gefunden", giata)
    return out


def region_giata_from_breadcrumb(giata: str) -> int | None:
    """Ermittelt die Region-/Insel-giataId zu einem Hotel über die Breadcrumb-API:
    der **letzte `level==1`-Eintrag** ist die konkrete Region (z. B. Gran Canaria=128,
    Kap Verde=88). None, wenn nicht ermittelbar."""
    if not giata:
        return None
    try:
        resp = requests.get(f"{BREADCRUMB_API}{giata}", headers=_API_HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        bc = resp.json()
        if not isinstance(bc, list):
            return None
        regions = [e.get("giataId") for e in bc if e.get("level") == 1
                   and isinstance(e.get("giataId"), int)]
        return regions[-1] if regions else None
    except Exception:
        return None


def _search_params_from_url(url: str, *, region: int | None = None,
                            operator_tui: bool = True, boards: list | None = None,
                            airlines: list | None = None, location: list | None = None,
                            direct: bool = False, adults_only: bool = False,
                            transfer_included: bool = False) -> dict:
    """Kanonische Suchparameter aus einer TUI-Such-/Angebots-URL (für URL- und
    Angebots-Modus). `region` überschreibt `regionGiataIds`, `airlines` (Liste von
    IATA-Codes) überschreibt den Airline-Filter der URL."""
    q = {k: v[0] for k, v in parse_qs(urlparse(url).query, keep_blank_values=True).items()}
    if region:
        regions = [int(region)]
    else:
        regions = [int(x) for x in _split_multi(q.get("regionGiataIds", "")) if x.isdigit()]
    try:
        adults = int(q.get("travellers", "1") or "1")
    except ValueError:
        adults = 1
    dur = _single_duration(q.get("duration", ""))
    ops = (["TUID"] if operator_tui
           else _split_multi(q.get("operators", q.get("tourOperators", ""))))
    board_codes = [b for b in (boards or []) if b] or _split_multi(q.get("boardTypes", ""))
    airline_codes = [a for a in (airlines or []) if a] or _split_multi(q.get("airlines", ""))
    loc_ids = [int(x) for x in (location or []) if str(x).isdigit()] or \
        [int(x) for x in _split_multi(q.get("locationAttributes", "")) if x.isdigit()]
    facility_ids = [13] if (adults_only or "13" in _split_multi(q.get("facilityAttributes", ""))) else []
    return {
        "searchScope": q.get("searchScope", "PACKAGE"),
        "startDate": q.get("startDate", ""), "endDate": q.get("endDate", ""),
        "duration": ("exact" if dur.strip().lower() == "exact"
                     else (int(dur) if dur.isdigit() else None)),
        "travellers": adults, "airports": _split_multi(q.get("departureAirports", "")),
        "operators": ops, "boards": board_codes, "airlines": airline_codes,
        "location": loc_ids,
        "facility": facility_ids,
        "regions": regions,
        "direct": direct or (q.get("maxStopOvers", "") == "0"),
        "transfer_included": transfer_included or (q.get("transferIncluded", "") == "true"),
    }


def _build_search_payload(p: dict, *, offset: int = 0) -> dict:
    """POST-Body aus kanonischen Suchparametern. `offset` = resultsFrom für
    "mehr laden" (Pagination) — die Such-API liefert pro Aufruf nur
    resultsPerPage Treffer, nicht alle auf einmal (live verifiziert)."""
    dur = p.get("duration")
    if dur == "exact":
        # Die Such-API kennt keinen "exact"-Wert (anders als die Angebots-URL) — sie
        # ignoriert ihn stillschweigend und fällt auf 7 Nächte zurück. Für "genau der
        # gewählte Zeitraum" daher die Nächte aus dem Datumsfenster selbst berechnen.
        try:
            dur = (date.fromisoformat(p.get("endDate", ""))
                   - date.fromisoformat(p.get("startDate", ""))).days
        except (TypeError, ValueError):
            dur = None
    params = {
        "searchScope": p.get("searchScope") or "PACKAGE",
        "startDate": p.get("startDate", ""), "endDate": p.get("endDate", ""),
        "duration": [dur] if dur else [],
        "rooms": [{"numberOfAdults": p.get("travellers") or 2, "childAges": [],
                   "roomCodes": [], "boardCodes": p.get("boards") or []}],
        "airports": p.get("airports") or [], "airlines": p.get("airlines") or [],
        "tourOperators": p.get("operators") or [],
        "logicalExpression": " + ".join(e for e in (
            _location_expression(p.get("location") or []),
            _facility_expression(p.get("facility") or [])) if e),
        # "qualifier2DESC" (Best-Match/Qualitaets-Score) sortierte serverseitig nach
        # etwas anderem als Preis -- bei mehr Treffern als resultsPerPage (z.B. 256
        # in einer Region, nur 50 abgeholt) fehlten dadurch die guenstigsten Hotels
        # komplett im abgeholten Batch, das clientseitige "Preis aufsteigend"-Sortieren
        # (app.js sortSearchResults) konnte sie nicht mehr finden -- sie waren nie in
        # den Daten. tui.com selbst nutzt fuer "sortHotelsField=price&sortHotelsAsc=1"
        # "priceAsc" (live per Netzwerk-Mitschnitt verifiziert), liefert exakt die
        # fehlenden guenstigen Hotels.
        # Default False = alle Hotels (mit/ohne Transfer-Paket), wie bisher. True (per
        # "Transfer inklusive"-Filter in der Suchmaske) grenzt die Such-API selbst
        # server-seitig auf Hotels MIT Transfer-Paket ein (live verifiziert: giataId
        # ohne Transfer-Paket verschwindet komplett aus den Treffern) -- kein Fallback
        # hier, das ist ein bewusster harter Filter.
        "transferIncluded": bool(p.get("transfer_included")), "sortingOrder": "priceAsc",
        "secondarySortingOrder": "", "identifier": "HLP",
        "giataRegions": p.get("regions") or [],
        # resultsTotal ist hier ein Anfrage-Cap, keine reine Info-Zahl -- die API
        # deckelt ihre eigene Antwort-"resultsTotal" (echte Trefferzahl) auf diesen
        # Wert (live verifiziert: Cap 300 bei 703 echten Treffern -> Antwort "300"
        # statt "703"). 1000 statt 300, damit die "von N Treffer"-Anzeige in der UI
        # bei großen Regionen nicht falsch zu niedrig ist.
        "resultsTotal": 1000, "resultsFrom": offset, "resultsPerPage": 50,
    }
    if p.get("direct"):           # nur Direktflug → max. 0 Zwischenstopps
        params["stopOver"] = 0
    # Sterne und Weiterempfehlung gehören in die Anfrage, nicht in einen Nachfilter:
    # die API sortiert nach Preis aufsteigend, in den ersten 50 Treffern stehen also
    # fast nur einfache Hotels. Clientseitig gefiltert blieb davon eine Handvoll übrig
    # und der Rest musste seitenweise nachgeladen werden.
    #
    # Beide Feldnamen stammen aus einem Mitschnitt der echten tui.com-Suche (dieselbe
    # API, siehe SCRAPING.md): `category` als ZAHL = „ab n Sonnen" (Liste/String →
    # HTTP 400), `recommendations` als Liste mit Vergleichsoperator. Live gegengeprüft
    # gegen die Trefferzahl der Website: 272 → 206 (category=4) → 135 (+ 80 %
    # Weiterempfehlung) — die Website zeigt für dieselben Filter exakt 135.
    try:
        cat = int(p.get("min_category") or 0)
    except (TypeError, ValueError):
        cat = 0
    if 1 <= cat <= 5:
        params["category"] = cat
    try:
        rec = float(p.get("min_recommend") or 0)
    except (TypeError, ValueError):
        rec = 0
    if 0 < rec <= 100:
        params["recommendations"] = [{"name": "recommendationsTotal",
                                      "operator": "gt", "value": int(rec)}]
    # Höchstpreis pro Person — ebenfalls aus dem Mitschnitt: schlichtes `maxPrice`.
    try:
        mx = float(p.get("max_price") or 0)
    except (TypeError, ValueError):
        mx = 0
    if mx > 0:
        params["maxPrice"] = int(mx)
    return {"parameters": params}


def offer_url_for(item: dict, params: dict) -> str:
    """Trackbare Hotel-Angebots-URL aus einem Such-Treffer + den Suchparametern (gleiche
    Form wie sonst vom Nutzer eingefügte URLs)."""
    h = item.get("hotel") or {}
    giata = str(h.get("giataId", ""))
    slug = _slugify(h.get("name", "") or "hotel")
    boards = item.get("boardCodes") or []
    # Für die trackbare Angebots-URL die konkrete Nächtezahl des Treffers nehmen;
    # bei „exact" gibt es keine feste Dauer → aus dem Treffer (numberOfNights).
    dur = params.get("duration")
    if not dur or dur == "exact":
        dur = item.get("numberOfNights")
    q = {
        "startDate": params.get("startDate", ""), "endDate": params.get("endDate", ""),
        "duration": str(dur or ""), "travellers": str(params.get("travellers") or 1),
        "searchScope": params.get("searchScope") or "PACKAGE",
        "departureAirports": ",".join(params.get("airports") or []),
        "operators": ",".join(params.get("operators") or []) or "TUID",
        "sortOffersAsc": "1", "sortOffersField": "campaignOffers",
    }
    regions = params.get("regions") or []
    if regions:
        q["regionGiataIds"] = ",".join(str(r) for r in regions)
    if boards:
        q["boardTypes"] = boards[0]
    if params.get("location"):
        q["locationAttributes"] = ";".join(str(i) for i in params["location"])
    if params.get("airlines"):
        # Offer-/Such-API trennt Airlines mit ';' (nicht ',') — siehe build_offer_api_url
        q["airlines"] = ";".join(params["airlines"])
    if params.get("direct"):
        q["maxStopOvers"] = "0"
    if params.get("transfer_included"):
        # Filter war beim Suchen aktiv (nur Hotels MIT Transfer-Paket) — beim Tracken
        # fest in die URL übernehmen, sonst würde die spätere Preisprüfung mangels
        # explizitem Parameter fälschlich den 0-Treffer-Fallback (ohne Transfer) ziehen.
        q["transferIncluded"] = "true"
    query = urlencode({k: v for k, v in q.items() if v != ""})
    return f"https://www.tui.com/pauschalreisen/suchen/angebote/{slug}/{giata}/offer/?{query}"


def _run_search(params: dict, *, offset: int = 0, verbose: bool = False) -> dict | None:
    """Führt die Hotelsuche für kanonische Parameter aus → normalisierte Treffer.
    {ok,total,results[]}; None bei technischem Fehler; {ok:False,note} ohne Region.
    `offset` (resultsFrom) für "mehr laden" — liefert die nächste Seite ab
    diesem Treffer-Index, nicht die ersten resultsPerPage erneut."""
    if not params.get("regions"):
        return {"ok": False, "total": 0, "results": [], "note": "Keine Region gewählt"}
    payload = _build_search_payload(params, offset=offset)
    try:
        if verbose:
            log.info(
                "Such-API POST %s regionen=%s zeitraum=%s-%s dauer=%s trav=%s "
                "boards=%s lage=%s airports=%s airlines=%s operators=%s direct=%s offset=%s",
                SEARCH_API, params["regions"], params.get("startDate"),
                params.get("endDate"), params.get("duration"), params.get("travellers"),
                params.get("boards"), params.get("location"), params.get("airports"),
                params.get("airlines"), params.get("operators"), params.get("direct"), offset)
        resp = requests.post(SEARCH_API, json=payload, headers=_SEARCH_HEADERS, timeout=30)
        if resp.status_code != 200:
            if verbose:
                log.warning("Such-API HTTP %s", resp.status_code)
            return None
        data = resp.json()
    except Exception as e:
        if verbose:
            log.warning("Such-API-Fehler: %s: %s", type(e).__name__, e)
        return None
    results = []
    for it in data.get("items") or []:
        h = it.get("hotel") or {}
        loc = h.get("location") or {}
        pp = (it.get("price") or {}).get("perPerson") or {}
        adv = (it.get("price") or {}).get("advantage")
        try:
            stars = int(str(h.get("category", "")).strip()[0]) if h.get("category") else None
        except (ValueError, IndexError):
            stars = None
        loc_parts = [x for x in (loc.get("city"), loc.get("region")) if x]
        global_codes = [g.get("code") for g in (h.get("globalTypes") or [])]
        # GT03-COUP im hotelseitigen globalTypes-Katalog markiert Teilnahme an aktuellen
        # TUI-Aktionscodes/Coupons (live gegen tui.com verifiziert: korreliert exakt mit
        # dem "myTUI Aktionscode"-Badge auf der echten Suchseite).
        coupon = "GT03-COUP" in global_codes
        results.append({
            "giata": h.get("giataId"), "name": h.get("name", ""), "stars": stars,
            "recommendation": h.get("holidayCheckRecommendationRate"),
            "reviews": h.get("holidayCheckNumberOfCurrentReviews"),
            # location = „Ort, Region" für die Anzeige; region getrennt, weil der
            # Auto-Tag beim Tracken nur die Region vergibt (Ort ist zu speziell).
            "location": ", ".join(loc_parts), "region": loc.get("region", ""),
            "country": loc.get("country", ""),
            "price": pp.get("amount"), "old_price": pp.get("originalAmount"),
            "discount": abs(adv) if adv else None,
            "board": it.get("boardType", ""), "nights": it.get("numberOfNights"),
            "date": (it.get("startDate") or "")[:10],
            "locations": _location_labels(global_codes),
            "image": (h.get("images") or [{}])[0].get("url", ""),
            "coupon": coupon,
            "offer_url": offer_url_for(it, params),
        })
    if verbose:
        log.info("Such-API: %d Treffer (gesamt %s)", len(results), data.get("resultsTotal"))
    return {"ok": True, "total": data.get("resultsTotal", len(results)), "results": results}


def fetch_search(url: str, *, operator_tui: bool = True, boards: list | None = None,
                 region: int | None = None, airlines: list | None = None,
                 location: list | None = None,
                 direct: bool = False, adults_only: bool = False,
                 transfer_included: bool = False, min_category: int = 0,
                 min_recommend: float = 0, max_price: float = 0,
                 offset: int = 0, verbose: bool = False) -> dict | None:
    """Hotelsuche aus einer TUI-Such-/Angebots-URL (`region` überschreibt die Region)."""
    params = _search_params_from_url(url, region=region, operator_tui=operator_tui,
                                     boards=boards, airlines=airlines, location=location,
                                     direct=direct, adults_only=adults_only,
                                     transfer_included=transfer_included)
    params["min_category"] = min_category
    params["min_recommend"] = min_recommend
    params["max_price"] = max_price
    return _run_search(params, offset=offset, verbose=verbose)


def fetch_search_params(*, region: int, start: str, end: str, duration, travellers,
                        airports: list | None = None, operator_tui: bool = True,
                        boards: list | None = None, airlines: list | None = None,
                        location: list | None = None,
                        direct: bool = False, adults_only: bool = False,
                        transfer_included: bool = False, min_category: int = 0,
                        min_recommend: float = 0, max_price: float = 0,
                        offset: int = 0, verbose: bool = False) -> dict | None:
    """Hotelsuche direkt aus Maskenfeldern (ohne URL) — für die eigene Suchmaske."""
    # „exact" ist ein nativer TUI-Wert (duration=exact): Reisedauer = genau der
    # gewählte Zeitraum. Als String unverändert durchreichen, sonst Nächte als int.
    if isinstance(duration, str) and duration.strip().lower() == "exact":
        dur = "exact"
    else:
        try:
            dur = int(duration)
        except (TypeError, ValueError):
            dur = None
    try:
        adults = int(travellers)
    except (TypeError, ValueError):
        adults = 2
    params = {
        "searchScope": "PACKAGE", "startDate": start or "", "endDate": end or "",
        "duration": dur, "travellers": adults,
        "airports": [a for a in (airports or []) if a],
        "operators": ["TUID"] if operator_tui else [],
        "boards": [b for b in (boards or []) if b],
        "airlines": [a for a in (airlines or []) if a],
        "location": [int(i) for i in (location or []) if str(i).isdigit()],
        "facility": [13] if adults_only else [],
        "regions": [int(region)] if region else [], "direct": bool(direct),
        "transfer_included": bool(transfer_included),
        "min_category": min_category, "min_recommend": min_recommend,
        "max_price": max_price,
    }
    return _run_search(params, offset=offset, verbose=verbose)


def _valid_img_url(u: str) -> bool:
    """Nur https-Bilder von TUI zulassen (kein Speichern/Anzeigen fremder URLs)."""
    try:
        p = urlparse(u or "")
    except (ValueError, TypeError):
        return False
    return p.scheme == "https" and p.hostname is not None and (
        p.hostname == "tui.com" or p.hostname.endswith(".tui.com"))


def fetch_hotel_image(url: str, *, verbose: bool = False) -> str:
    """Ermittelt das Hotelbild zu einer Angebots-URL. Quelle ist ausschließlich die
    Such-API (`hotel.images`): Region über den Breadcrumb bestimmen, in dieser Region
    suchen (mit den Parametern der Angebots-URL) und den Treffer mit passender giataId
    nehmen. Gibt eine validierte pics.tui.com-URL zurück oder '' (kein Fehler)."""
    giata = _giata_from_url(url)
    if not giata:
        return ""
    region = region_giata_from_breadcrumb(giata)
    if not region:
        return ""
    params = _search_params_from_url(url, region=region)
    res = _run_search(params, verbose=verbose)
    if not (res and res.get("ok")):
        return ""
    for r in res.get("results") or []:
        if str(r.get("giata")) == str(giata):
            img = r.get("image") or ""
            return img if _valid_img_url(img) else ""
    if verbose:
        log.info("Hotelbild: giataId %s nicht in Regionssuche gefunden", giata)
    return ""


def fetch_destinations(parent=None) -> dict | None:
    """Reiseziel-Liste für den Picker. `parent=None` → Top-Level-Regionen, sonst die
    Unterregionen zu `parent`. Rückgabe {parentName, items:[{giata,label,level}]}."""
    base = f"{DEST_API}/de/package/TUICOM/giata"
    url = f"{base}/regions" if not parent else f"{base}/subregions/{parent}"
    try:
        resp = requests.get(url, headers=_API_HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        data = resp.json()
    except Exception:
        return None
    raw = (data.get("items") or {}) if isinstance(data, dict) else {}
    items = [{"giata": int(g) if str(g).isdigit() else g,
              "label": v.get("label", ""), "level": v.get("level")}
             for g, v in raw.items() if isinstance(v, dict)]
    items.sort(key=lambda x: (x.get("label") or "").lower())
    return {"parentName": data.get("parentName", "") if isinstance(data, dict) else "",
            "items": items}


def build_destination_index(max_depth=5) -> list:
    """Crawlt den kompletten Reiseziel-Baum und liefert eine flache Liste
    [{giata, label, path}] für die globale Suche über alle Ebenen. `path` ist der
    Breadcrumb der übergeordneten Regionen (z. B. "Spanien › Kanarische Inseln").

    Achtung: macht ~1000+ API-Aufrufe (ein Aufruf je Knoten). Nur im Hintergrund
    bzw. gecacht verwenden — nicht pro Suchanfrage."""
    out: list = []
    seen: set = set()

    def crawl(parent, trail, depth):
        if depth > max_depth:
            return
        d = fetch_destinations(parent)
        if not d:
            return
        for it in d.get("items", []):
            g = it.get("giata")
            label = it.get("label", "")
            if g is None or g in seen:
                continue
            seen.add(g)
            out.append({"giata": g, "label": label, "path": " › ".join(trail)})
            crawl(g, trail + [label], depth + 1)

    crawl(None, [], 0)
    out.sort(key=lambda x: (x.get("label") or "").lower())
    return out


# Kuratierte Liste gängiger TUI-Fluggesellschaften (IATA-Codes). TUI bietet keinen
# offenen Endpunkt für die Filterliste; die Codes entsprechen denen, die die Such- und
# Offer-API im Parameter `airlines` erwarten (mehrere mit ';' getrennt, siehe
# build_offer_api_url/offer_url_for). Bei Bedarf hier ergänzen.
TUI_AIRLINES = [
    {"code": "A3", "name": "Aegean Airlines"},
    {"code": "SM", "name": "Air Cairo"},
    {"code": "AF", "name": "Air France"},
    {"code": "OS", "name": "Austrian Airlines"},
    {"code": "BA", "name": "British Airways"},
    {"code": "DE", "name": "Condor"},
    {"code": "XC", "name": "Corendon Airlines"},
    {"code": "4Y", "name": "Discover Airlines"},
    {"code": "U2", "name": "EasyJet"},
    {"code": "WK", "name": "Edelweiss"},
    {"code": "EK", "name": "Emirates"},
    {"code": "E4", "name": "Enter Air"},
    {"code": "EY", "name": "Etihad Airways"},
    {"code": "EW", "name": "Eurowings"},
    {"code": "KL", "name": "KLM"},
    {"code": "LH", "name": "Lufthansa"},
    {"code": "T3", "name": "Marabu"},
    {"code": "PC", "name": "Pegasus Airlines"},
    {"code": "FR", "name": "Ryanair"},
    {"code": "LX", "name": "SWISS"},
    {"code": "XQ", "name": "SunExpress"},
    {"code": "TP", "name": "TAP Air Portugal"},
    {"code": "TK", "name": "Turkish Airlines"},
    {"code": "X3", "name": "TUI fly"},
    {"code": "TB", "name": "TUI fly Belgium"},
    {"code": "VY", "name": "Vueling"},
    {"code": "W6", "name": "Wizz Air"},
]


def fetch_airlines() -> list:
    """Fluggesellschaften für den (optionalen) Such-Filter: [{code,name}], nach Name
    sortiert. Kuratierte Liste (TUI hat keinen offenen Endpunkt dafür)."""
    return sorted((dict(a) for a in TUI_AIRLINES), key=lambda a: a["name"].lower())


def fetch_airports() -> list:
    """Abflughäfen aus der TUI-API: [{code,name,preselected}]."""
    try:
        resp = requests.get(f"{AIRPORTS_API}/departureAirports/TUICOM/de-DE",
                            headers=_API_HEADERS, timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:
        return []
    out = [{"code": a.get("key", ""), "name": a.get("name", ""),
            "preselected": bool(a.get("preselected"))}
           for a in data if isinstance(a, dict) and a.get("key")]
    out.sort(key=lambda x: x["name"].lower())
    return out


# Bekanntes Referenz-Hotel für den API-Selbsttest (Riu Funana, Kapverden) + Region
# Gran Canaria. Nur lesende Abfragen; dient ausschließlich der Erreichbarkeitsprüfung.
_HC_GIATA = "259516"
_HC_REGION = 128


def api_healthcheck(*, verbose: bool = False) -> dict:
    """Prüft alle genutzten TUI-Endpunkte mit je einer leichten Lese-Abfrage und meldet,
    ob sie noch erwartungsgemäß antworten. Rückgabe:
    {ok: bool, ts: int, checks: [{name, ok, detail}]}. `ok` ist True, wenn alle
    *kritischen* Endpunkte (Preis, Suche, Reiseziele) funktionieren."""
    today = date.today()
    sd = (today + timedelta(days=30)).isoformat()
    ed = (today + timedelta(days=37)).isoformat()
    checks: list[dict] = []

    def add(name, ok, detail, critical=False):
        checks.append({"name": name, "ok": bool(ok), "detail": detail,
                       "critical": critical})

    # 1) Preis/Angebot (OFFER_API) — kritisch (Kern des Trackings). Die Antwort
    #    wird für die vacancy-/payment-Checks unten weiterverwendet (Testangebot).
    offer_data: dict = {}
    try:
        q = {"giataId": _HC_GIATA, "locale": "de_DE", "tenant": "TUICOM",
             "startDate": sd, "endDate": ed, "durations": "7",
             "searchScope": "PACKAGE", "travellers": "2"}
        r = requests.get(f"{OFFER_API}?{urlencode(q)}", headers=_API_HEADERS, timeout=20)
        body = r.json() if r.status_code == 200 else None
        ok = r.status_code == 200 and isinstance(body, (dict, list))
        if isinstance(body, dict):
            offer_data = body
        add("Preis/Angebot-API", ok, f"HTTP {r.status_code}", critical=True)
    except Exception as e:
        add("Preis/Angebot-API", False, type(e).__name__, critical=True)

    # 2) Hotelsuche (SEARCH_API) — kritisch
    try:
        res = fetch_search_params(region=_HC_REGION, start=sd, end=ed, duration=7,
                                  travellers=2, verbose=verbose)
        ok = bool(res and res.get("ok"))
        detail = f"{res.get('total', 0)} Treffer" if ok else "kein Ergebnis"
        add("Hotelsuche-API", ok, detail, critical=True)
    except Exception as e:
        add("Hotelsuche-API", False, type(e).__name__, critical=True)

    # 3) Reiseziele (DEST_API) — kritisch für die Suchmaske
    try:
        d = fetch_destinations()
        n = len((d or {}).get("items") or [])
        add("Reiseziele-API", n > 0, f"{n} Regionen", critical=True)
    except Exception as e:
        add("Reiseziele-API", False, type(e).__name__, critical=True)

    # 4) Abflughäfen (AIRPORTS_API)
    try:
        a = fetch_airports()
        add("Abflughäfen-API", len(a) > 0, f"{len(a)} Flughäfen")
    except Exception as e:
        add("Abflughäfen-API", False, type(e).__name__)

    # 5) Preiskalender (CALENDAR_API)
    try:
        q = {"giatas": _HC_GIATA, "adults": "2", "duration": "7",
             "searchscope": "PACKAGE", "tenant": "tui.com",
             "startDate": sd, "endDate": (today + timedelta(days=300)).isoformat(),
             "startSearchRange": sd,
             "endSearchRange": (today + timedelta(days=300)).isoformat()}
        r = requests.get(f"{CALENDAR_API}?{urlencode(q)}", headers=_API_HEADERS, timeout=20)
        ok = r.status_code == 200 and isinstance(r.json(), dict)
        add("Preiskalender-API", ok, f"HTTP {r.status_code}")
    except Exception as e:
        add("Preiskalender-API", False, type(e).__name__)

    # 6) Bewertung/Sterne (CONTENT_API)
    try:
        r = requests.get(f"{CONTENT_API}?giataId={_HC_GIATA}&locale=de_DE",
                         headers=_API_HEADERS, timeout=20)
        ok = r.status_code == 200 and isinstance(r.json(), dict)
        add("Bewertungs-API", ok, f"HTTP {r.status_code}")
    except Exception as e:
        add("Bewertungs-API", False, type(e).__name__)

    # 7) Ort/Region (BREADCRUMB_API)
    try:
        r = requests.get(f"{BREADCRUMB_API}{_HC_GIATA}", headers=_API_HEADERS, timeout=20)
        ok = r.status_code == 200 and isinstance(r.json(), list)
        add("Breadcrumb-API", ok, f"HTTP {r.status_code}")
    except Exception as e:
        add("Breadcrumb-API", False, type(e).__name__)

    # 8) Live-Bestätigung (VACANCY_API) — nicht kritisch, aber Basis für Preis-Split
    #    und Nicht-mehr-buchbar-Alarm. Wichtig als Drift-Wächter: ändert TUI das
    #    Payload-Format (wie beim travelType-Objekt), bleibt der Status dauerhaft
    #    FAILED und der Alarm wäre sonst still tot.
    hc_offers = offer_data.get("offers") or []
    hc_offer = next((o for o in hc_offers if o.get("cheapest")),
                    hc_offers[0] if hc_offers else None)
    try:
        if hc_offer:
            v = _fetch_vacancy(offer_data, hc_offer, verbose=verbose)
            st = v.get("vac_status") or ""
            add("Buchbarkeits-API", st == "OK",
                st or "keine Antwort")
        else:
            add("Buchbarkeits-API", False, "kein Testangebot")
    except Exception as e:
        add("Buchbarkeits-API", False, type(e).__name__)

    # 9) Inklusiv-Gepäck (LUGGAGE_API) — HTTP/Struktur reicht (state je Route variiert)
    try:
        r = requests.post(LUGGAGE_API,
                          json=[{"airline": "X3", "route": "DUS-SID", "organizer": "TUID"}],
                          headers=_API_HEADERS, timeout=20)
        ok = r.status_code == 200 and isinstance(r.json(), list)
        add("Gepäck-API", ok, f"HTTP {r.status_code}")
    except Exception as e:
        add("Gepäck-API", False, type(e).__name__)

    # 10) Zahlungskonditionen (PAYMENT_API, testet nebenbei den Hotel-Content-
    #     Endpoint für den Ländercode)
    try:
        if hc_offer:
            p = fetch_payment_terms(hc_offer, _HC_GIATA, verbose=verbose)
            add("Zahlungs-API", bool(p),
                (f"{p.get('deposit_pct')}% Anzahlung" if p else "keine Konditionen"))
        else:
            add("Zahlungs-API", False, "kein Testangebot")
    except Exception as e:
        add("Zahlungs-API", False, type(e).__name__)

    # 11) Zuletzt gebucht (LAST_BOOKED_API)
    try:
        r = requests.get(f"{LAST_BOOKED_API}{_HC_GIATA}", headers=_API_HEADERS, timeout=20)
        ok = r.status_code == 200 and isinstance(r.json(), dict)
        add("Zuletzt-gebucht-API", ok, f"HTTP {r.status_code}")
    except Exception as e:
        add("Zuletzt-gebucht-API", False, type(e).__name__)

    all_critical_ok = all(c["ok"] for c in checks if c["critical"])
    if verbose:
        log.info("API-Selbsttest: %s", ", ".join(
            f"{c['name']}={'OK' if c['ok'] else 'FEHLER'}" for c in checks))
    return {"ok": all_critical_ok, "ts": int(time.time()), "checks": checks}


def _de_date(iso: str) -> str:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", iso or "")
    return f"{m.group(3)}.{m.group(2)}.{m.group(1)}" if m else ""


_DE_WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


def _de_weekday(iso: str) -> str:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", iso or "")
    if not m:
        return ""
    try:
        d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return ""
    return _DE_WEEKDAYS[d.weekday()]


def _de_datetime(iso: str) -> str:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})", iso or "")
    if not m:
        return ""
    wd = _de_weekday(iso)
    date = f"{m.group(3)}.{m.group(2)}.{m.group(1)}"
    return f"{wd + ' ' if wd else ''}{date}, {m.group(4)}:{m.group(5)}"


def _fmt_flight(leg: dict) -> str:
    if not leg:
        return ""
    dt = _de_datetime(leg.get("departureDateTime", ""))
    al = leg.get("airline") or {}
    airline = al.get("value", "")
    num = str(leg.get("number", "") or "").strip()
    code = al.get("code", "")
    # Airline + Flugnummer, z. B. "TUIfly X3 7102"
    airline_part = " ".join(x for x in (airline, f"{code} {num}".strip() if num else "") if x)
    dep = (leg.get("departureAirport") or {}).get("code", "")
    arr = (leg.get("arrivalAirport") or {}).get("code", "")
    route = f"{dep}→{arr}" if dep and arr else ""
    so = leg.get("stopOver")
    stops = "Direktflug" if so in (0, None) else (
        "1 Zwischenstopp" if so == 1 else f"{so} Zwischenstopps")
    return " · ".join(x for x in (dt, route, airline_part, stops) if x)


def _flight_key(offer: dict) -> str:
    """Stabiler Schlüssel einer Flugvariante: Airline|Stopps|Abflugzeit|Anreisetag.

    Die Angebots-API liefert für denselben Zeitraum mehrere Offers, die sich nur in
    den Flügen unterscheiden. Der Schlüssel identifiziert eine davon wieder, ohne
    die getrackte URL umzuschreiben (Preis/Datum ändern sich, die Flugkombi nicht).
    """
    dep = offer.get("departure") or {}
    code = ((dep.get("airline") or {}).get("code") or "").strip()
    so = dep.get("stopOver")
    t = (dep.get("departureDateTime") or "")[11:16]
    return f"{code}|{'' if so is None else so}|{t}|{offer.get('arrivalDate', '') or ''}"


def _flight_options(offers: list, chosen: dict, limit: int = 12) -> list:
    """Alle Flugvarianten des Abrufs als kompakte Liste (aufsteigend nach Preis).

    Getrackt wird weiter nur eine Variante — die Liste macht sichtbar, was ein
    späterer/direkterer Flug kosten würde (`delta` = Aufpreis gegenüber der
    getrackten Variante)."""
    base = chosen.get("calculatedPricePerPerson")
    out = []
    for o in offers:
        dep = o.get("departure") or {}
        ret = o.get("return") or {}
        p = o.get("calculatedPricePerPerson")
        out.append({
            "key": _flight_key(o),
            "price": float(p) if p is not None else None,
            "delta": (round(float(p) - float(base), 2)
                      if p is not None and base is not None else None),
            "out": _fmt_flight(dep),
            "ret": _fmt_flight(ret),
            "airline": ((dep.get("airline") or {}).get("value") or ""),
            "stops_out": dep.get("stopOver"),
            "stops_ret": ret.get("stopOver"),
            "arrival_date": o.get("arrivalDate", "") or "",
            "nights": o.get("lengthOfStay"),
            "selected": o is chosen,
        })
    out.sort(key=lambda x: (x["price"] is None, x["price"] or 0))
    top = out[:limit]
    # Die verfolgte Variante muss immer dabei sein — bei einer fixierten teuren
    # Variante könnte sie sonst hinter der Kappungsgrenze liegen.
    if not any(v["selected"] for v in top):
        sel = next((v for v in out if v["selected"]), None)
        if sel:
            top = top[:limit - 1] + [sel]
    return top


def _fetch_rating(giata: str, verbose: bool = False) -> dict:
    """Sterne + HolidayCheck-Bewertung aus dem TUI-Content-Endpoint (optional)."""
    out: dict = {}
    if not giata:
        return out
    try:
        resp = requests.get(f"{CONTENT_API}?giataId={giata}&locale=de_DE",
                            headers=_API_HEADERS, timeout=15)
        if resp.status_code != 200:
            return out
        d = resp.json()
        hc = d.get("holidayCheckRatings") or {}
        if d.get("category") is not None:
            out["stars"] = d.get("category")
        if hc.get("averageRating") is not None:
            out["rating"] = hc.get("averageRating")
        if hc.get("countReviewsCurrent") is not None:
            out["rating_count"] = hc.get("countReviewsCurrent")
        if hc.get("recommendation") is not None:
            out["recommendation"] = hc.get("recommendation")
    except Exception as e:
        if verbose:
            log.info(f"Bewertung nicht abrufbar: {e}")
    return out


def _fetch_location(giata: str, region_giata=None, verbose: bool = False) -> dict:
    """Ort + Region aus dem Breadcrumb (z. B. 'Playa del Ingles, Gran Canaria')."""
    out: dict = {}
    if not giata:
        return out
    try:
        resp = requests.get(f"{BREADCRUMB_API}{giata}", headers=_API_HEADERS, timeout=15)
        if resp.status_code != 200:
            return out
        bc = resp.json()
        if not isinstance(bc, list) or len(bc) < 2:
            return out
        # letzter Eintrag = Hotel; Stadt = direkt darüber
        city = bc[-2].get('name', '') if len(bc) >= 2 else ''
        # Region: per regionGiata matchen, sonst tiefster (letzter) Level-1-Eintrag
        region = ''
        if region_giata is not None:
            region = next((e.get('name', '') for e in bc
                           if e.get('giataId') == region_giata), '')
        if not region:
            l1 = [e.get('name', '') for e in bc if e.get('level') == 1]
            region = l1[-1] if l1 else (bc[-3].get('name', '') if len(bc) >= 3 else '')
        country = next((e.get('name', '') for e in bc if e.get('level') == 0), '')
        parts = []
        for x in (city, region):
            if x and x not in parts:
                parts.append(x)
        out = {'city': city, 'region': region, 'country': country,
               'location': ', '.join(parts)}
        if verbose:
            log.info(f"Ort: {out['location']}")
    except Exception as e:
        if verbose:
            log.info(f"Ort nicht abrufbar: {e}")
    return out


def _build_vacancy_payload(data: dict, offer: dict) -> dict:
    """Baut den vacancy-check-Body aus dem Offer-JSON nach. Feld-Formate exakt wie
    im Buchungs-Frontend beobachtet — Achtung: `travelType` ist hier ein **Objekt**
    (im Offer-JSON nur ein String), sonst antwortet der Endpoint mit FAILED."""
    trav = {t["id"]: t for t in (offer.get("travellers") or data.get("travellers") or [])}
    pp = {p["id"]: p.get("price") for p in offer.get("personPrices", [])}
    rooms = [{
        "id": i,
        "code": rm.get("code"),
        "board": rm.get("board"),
        "boardCode": rm.get("boardCode"),
        "description": rm.get("description"),
        "boardDescription": rm.get("boardDescription"),
        "title": rm.get("description"),
        "travellers": [{"id": t["id"], "age": trav.get(t["id"], {}).get("age"),
                        "price": pp.get(t["id"])}
                       for t in rm.get("travellers", [])],
        "supplier": offer.get("supplier", {}),
        "transferIncluded": rm.get("transferIncluded"),
        "trainToFlight": rm.get("trainToFlight"),
    } for i, rm in enumerate(offer.get("rooms", []), 1)]
    return {
        "scope": "PACKAGE", "tenant": "TUICOM", "locale": "de_DE",
        "agency": _BOOKING_AGENCY, "agent": _BOOKING_AGENT, "channel": _BOOKING_CHANNEL,
        "offer": {
            "tempId": offer.get("tempId", ""),
            "startDate": offer.get("arrivalDate", ""),
            "checkInDate": offer.get("checkInDate", ""),
            "nights": offer.get("lengthOfStay"),
            "hotel": offer.get("hotel", {}),
            "programType": offer.get("programType", ""),
            "currency": offer.get("currency", "EUR"),
            "cancellationType": offer.get("cancellationType", ""),
            "travelType": {"code": offer.get("travelType", ""),
                           "brand": offer.get("brand", ""),
                           "tourOperator": offer.get("tourOperator", ""),
                           "bookingTourOperator": offer.get("bookingTourOperator", "")},
            "departureFlight": offer.get("departure", {}),
            "returnFlight": offer.get("return", {}),
            "rooms": rooms,
            "price": {"totalNetPrice": offer.get("totalPrice"),
                      "discountAmount": offer.get("discount"),
                      "travellersCount": len(trav) or 1,
                      "earlyBird": False,
                      "priceByUnit": (offer.get("rooms") or [{}])[0].get("priceByUnit", False)},
        },
    }


def _sum_traveller_prices(node: dict) -> float | None:
    """Summe der Reisenden-Preise eines vacancy-check-Blocks (Flug/Zimmer)."""
    total = 0.0
    found = False
    for t in (node or {}).get("travellers", []):
        amt = (t.get("price") or {}).get("amount")
        if amt is not None:
            total += float(amt)
            found = True
    return total if found else None


def _fetch_vacancy(data: dict, offer: dict, verbose: bool = False) -> dict:
    """Live-Bestätigung über den vacancy-check-Endpoint (das, was der Knopf
    „Verfügbarkeit prüfen" auf tui.com auslöst). Liefert den Status aus dem
    Veranstaltersystem plus die Preis-Aufschlüsselung Hotel/Hinflug/Rückflug,
    die die Angebotsseite selbst nie anzeigt. Fehler → leeres dict (defensiv:
    unbekannter Status ist KEIN Nichtverfügbar-Signal)."""
    out: dict = {}
    try:
        resp = requests.post(VACANCY_API, json=_build_vacancy_payload(data, offer),
                             headers=_API_HEADERS, timeout=30)
        if resp.status_code != 200:
            if verbose:
                log.info(f"vacancy-check HTTP {resp.status_code}")
            return out
        j = resp.json()
        status = j.get("status") or ""
        out["vac_status"] = status
        if status == "OK":
            # Veranstalter-Hinweise zur konkreten Buchung (sonst erst im Checkout
            # sichtbar): Wasserflugzeug-Zeiten, Gepäcklimits, Sicherheitshinweise …
            out["errata"] = [e.strip() for e in (j.get("errata") or []) if e and e.strip()]
            # Bestätigte Flugsegmente (Zeiten, Flugnummern, Buchungsklasse) — Basis
            # für den Flugzeiten-Änderungs-Alarm und die Umsteige-Anzeige
            def _segs(node):
                return [{
                    "dep": s.get("departureAirport", ""),
                    "arr": s.get("arrivalAirport", ""),
                    "start": s.get("startDate", ""),
                    "end": s.get("endDate", ""),
                    "airline": s.get("airline", ""),
                    "number": s.get("flightNumber", ""),
                    "cls": s.get("bookingClass", ""),
                    "fare": s.get("fareBase", ""),
                } for s in (node or {}).get("segments", [])]
            out["flight_segments"] = {"out": _segs(j.get("outboundFlight")),
                                      "ret": _segs(j.get("inboundFlight"))}
            # Badges: Charter (TUI-interner Flug) vs. Linienflug, Sitzplatz
            # reservierbar, Sonderleistungen buchbar
            ob, ib = j.get("outboundFlight") or {}, j.get("inboundFlight") or {}
            out["flight_flags"] = {
                "charter": bool(ob.get("isInternal")) and bool(ib.get("isInternal")),
                "seat": any(s.get("seatReservable")
                            for n in (ob, ib) for s in n.get("segments", [])),
                "svc": bool(ob.get("specialServiceBookable")
                            or ib.get("specialServiceBookable")),
            }
            # Kontingent-Quelle: leeres supplier-Objekt = TUI-eigenes Kontingent,
            # sonst Bettenbank (z. B. DBH/MTS)
            sup = ((j.get("hotel") or {}).get("rooms") or [{}])[0].get("supplier") or {}
            out["hotel_supplier"] = "/".join(
                x for x in (sup.get("provider"), sup.get("supplierCode")) if x)
            hotel_sum = None
            for rm in (j.get("hotel") or {}).get("rooms", []):
                s = _sum_traveller_prices(rm)
                if s is not None:
                    hotel_sum = (hotel_sum or 0.0) + s
            if hotel_sum is None:
                amt = ((j.get("hotel") or {}).get("price") or {}).get("amount")
                hotel_sum = float(amt) if amt is not None else None
            out["price_hotel"] = hotel_sum
            out["price_flight_out"] = _sum_traveller_prices(j.get("outboundFlight"))
            out["price_flight_ret"] = _sum_traveller_prices(j.get("inboundFlight"))
            if verbose:
                log.info("vacancy-check OK: Hotel=%s Hin=%s Rück=%s (System %s)",
                         out["price_hotel"], out["price_flight_out"],
                         out["price_flight_ret"], j.get("system", "?"))
        elif verbose:
            log.info(f"vacancy-check Status: {status}")
    except Exception as e:
        if verbose:
            log.info(f"vacancy-check nicht abrufbar: {e}")
    return out


def _fetch_last_booked(giata: str, verbose: bool = False) -> str:
    """„Zuletzt gebucht am …" für dieses Hotel (ISO-Datum oder '')."""
    if not giata:
        return ""
    try:
        resp = requests.get(f"{LAST_BOOKED_API}{giata}", headers=_API_HEADERS, timeout=15)
        if resp.status_code == 200:
            return (resp.json().get("date") or "")[:10]
    except Exception as e:
        if verbose:
            log.info(f"last-booked nicht abrufbar: {e}")
    return ""


def fetch_luggage(offer: dict, verbose: bool = False) -> dict:
    """Inklusiv-Gepäck für Hin-/Rückflug eines Offer-JSON-Angebots.
    Rückgabe {'out': '1×20 kg', 'ret': '1×20 kg'} oder {} — die Beschriftung
    (Hin/Rück, p. P.) übernimmt lokalisiert das Frontend."""
    try:
        legs = []
        for leg in (offer.get("departure"), offer.get("return")):
            leg = leg or {}
            al = (leg.get("airline") or {}).get("code", "")
            dep = (leg.get("departureAirport") or {}).get("code", "")
            arr = (leg.get("arrivalAirport") or {}).get("code", "")
            if not (al and dep and arr):
                return {}
            legs.append({"airline": al, "route": f"{dep}-{arr}",
                         "organizer": offer.get("tourOperator", "")})
        resp = requests.post(LUGGAGE_API, json=legs, headers=_API_HEADERS, timeout=15)
        if resp.status_code != 200:
            return {}
        parts = []
        for e in resp.json():
            if e.get("state") != "OK":
                return {}
            ad = (e.get("luggage") or {}).get("adult") or {}
            if ad.get("pcs") is None or ad.get("weight") is None:
                return {}
            parts.append(f"{ad['pcs']}×{ad['weight']} kg")
        if len(parts) != 2:
            return {}
        if verbose:
            log.info(f"Gepäck: {parts[0]} / {parts[1]}")
        return {"out": parts[0], "ret": parts[1]}
    except Exception as e:
        if verbose:
            log.info(f"Gepäck nicht abrufbar: {e}")
        return {}


def _fetch_country_code(giata: str) -> str:
    """ISO-Ländercode des Hotels (z. B. 'GR') aus dem Hotel-Content-Endpoint —
    der Breadcrumb kennt nur Ländernamen, paymentService will den Code."""
    try:
        resp = requests.get(f"{HOTEL_CONTENT_API}?giataId={giata}&locale=de_DE&tenant=TUICOM",
                            headers=_API_HEADERS, timeout=15)
        if resp.status_code == 200:
            return ((resp.json().get("contact") or {}).get("address") or {}) \
                .get("countryCode", "") or ""
    except Exception:
        pass
    return ""


def fetch_payment_terms(offer: dict, giata: str, verbose: bool = False) -> dict:
    """Anzahlung (%) und Restzahlungstermin über den paymentService.
    Rückgabe {'deposit_pct': .., 'final_payment_date': 'YYYY-MM-DD'} oder {}."""
    out: dict = {}
    try:
        country = _fetch_country_code(giata)
        if not country:
            return out
        body = {"tenant": "tuicom",
                "cancellationType": offer.get("cancellationType", ""),
                "isOmnichannel": False, "isPackagetour": True,
                "services": [{"system": "ATCOMRES",
                              "tourOperator": offer.get("tourOperator", ""),
                              "startDate": offer.get("arrivalDate", ""),
                              "countryCodes": [country],
                              "productCodes": [(offer.get("hotel") or {}).get("product", "")]}]}
        headers = dict(_API_HEADERS)
        headers["X-Agency"] = _BOOKING_AGENCY   # ohne: HTTP 400 "insufficient headers"
        resp = requests.post(PAYMENT_API, json=body, headers=headers, timeout=20)
        if resp.status_code != 200:
            return out
        j = resp.json()
        if j.get("depositPercentage") is not None:
            out["deposit_pct"] = j["depositPercentage"]
        if j.get("finalPaymentDate"):
            out["final_payment_date"] = j["finalPaymentDate"][:10]
        if verbose and out:
            log.info("Zahlung: %s%% Anzahlung, Rest bis %s",
                     out.get("deposit_pct"), out.get("final_payment_date"))
    except Exception as e:
        if verbose:
            log.info(f"Zahlungskonditionen nicht abrufbar: {e}")
    return out


def fetch_price_api(url: str, *, vacancy: bool = True, extras: bool = False,
                    flight_pin: str = "", verbose: bool = False) -> dict | None:
    """Liest Preis/Details direkt aus der JSON-API. Rückgabe:
       - dict mit ok=True bei Treffer,
       - dict mit ok=False + Note bei *gültiger* Leermenge (kein Angebot im Zeitraum),
       - None bei technischem Fehler (→ Aufrufer macht Browser-Fallback)."""
    try:
        api = build_offer_api_url(url)
        if verbose:
            log.info("Offer-API GET %s", api)
        resp = requests.get(api, headers=_API_HEADERS, timeout=25)
        if resp.status_code != 200:
            if verbose:
                log.warning(f"API HTTP {resp.status_code}")
            if resp.status_code in (400, 404, 422):
                # Kein Angebot für diese Parameter (z. B. Dauer ohne Flüge) — das ist
                # KEIN technischer Fehler, daher kein (langsamer) Browser-Fallback.
                r = _empty_result()
                r["source"] = "api"
                r["available"] = False
                r["note"] = "Kein Angebot im gewählten Zeitraum"
                r["hotel"] = hotel_from_url(url)
                return r
            return None
        data = resp.json()
    except Exception as e:
        if verbose:
            log.warning(f"API-Fehler: {type(e).__name__}: {e}")
        return None

    offers = data.get("offers") or []
    if not offers and not _url_has_transfer_param(url):
        # Manche Hotels (Selbstanreise-Regionen) bieten kein Transfer-Paket -- der
        # Default transferIncluded=true liefert dort 0 Treffer, obwohl auf tui.com
        # buchbare Angebote existieren (live verifiziert: mit Transfer-Paket liefern
        # true/false identische Treffer+Preise, ohne Transfer-Paket liefert nur false
        # Treffer). Fallback nur, wenn der Nutzer die URL nicht bereits per Checkbox
        # explizit festgelegt hat.
        try:
            resp2 = requests.get(build_offer_api_url(with_transfer_included(url, False)),
                                  headers=_API_HEADERS, timeout=25)
            data2 = resp2.json() if resp2.status_code == 200 else {}
            if data2.get("offers"):
                data = data2
                offers = data.get("offers") or []
                if verbose:
                    log.info("Offer-API: Fallback ohne Transfer-Paket → %d Angebot(e)",
                             len(offers))
        except Exception:
            pass

    r = _empty_result()
    r["source"] = "api"
    r["hotel"] = (data.get("hotel") or {}).get("name", "") or hotel_from_url(url)
    r["currency"] = data.get("currency", "EUR")
    if verbose:
        log.info("Offer-API: %d Angebot(e) zurück", len(offers))
    if not offers:
        r["available"] = False
        r["note"] = "Kein Angebot im gewählten Zeitraum"
        return r

    cheapest = next((o for o in offers if o.get("cheapest")), None) or \
        min(offers, key=lambda o: o.get("calculatedPricePerPerson") or float("inf"))
    offer = cheapest
    if flight_pin:
        # Fixierte Flugvariante: günstigstes Offer mit passendem Schlüssel. Fällt der
        # Flug aus dem Angebot (Airline/Zeit weg), wieder günstigster + Hinweis.
        match = [o for o in offers if _flight_key(o) == flight_pin]
        if match:
            offer = min(match, key=lambda o: o.get("calculatedPricePerPerson")
                        or float("inf"))
        else:
            r["flight_pin_missed"] = True
            if verbose:
                log.info("Offer-API: fixierte Flugvariante %s nicht mehr im Angebot "
                         "→ günstigster Flug", flight_pin)
    r["flight_options"] = _flight_options(offers, offer)

    price = offer.get("calculatedPricePerPerson")
    old = offer.get("calculatedOriginalPricePerPerson")
    r["price"] = float(price) if price is not None else None
    if old and price and old > price:
        r["old_price"] = float(old)
        r["discount"] = round((old - price) / old * 100)
    if offer.get("totalPrice") is not None:
        r["total_price"] = float(offer["totalPrice"])  # Gesamtpreis aller Reisenden
    if r["price"] is None:
        r["note"] = "Preis im API-Angebot fehlt"
        return None  # lieber Browser-Fallback versuchen

    room0 = (offer.get("rooms") or [{}])[0]
    room_desc = room0.get("description", "")
    room_code = room0.get("code", "")
    r["room"] = f"{room_desc} ({room_code})" if room_code else room_desc
    r["board"] = room0.get("boardDescription", "")
    r["booking_code"] = (data.get("hotel") or {}).get("product", "")  # z. B. LPA21031
    r["room_booking_code"] = room0.get("bookingCode", "")             # z. B. DZM1A

    nights = offer.get("lengthOfStay")
    r["nights"] = f"{nights} Nächte" if nights else ""
    try:
        r["nights_num"] = int(nights) if nights else None
    except (TypeError, ValueError):
        r["nights_num"] = None

    trav = data.get("travellers") or offer.get("travellers") or []
    r["travellers_count"] = len(trav) or None
    adults = sum(1 for t in trav if (t.get("age") if t.get("age") is not None else 99) >= 18)
    kids = len(trav) - adults
    tparts = []
    if adults:
        tparts.append(f"{adults} Erwachsene{'r' if adults == 1 else ''}")
    if kids:
        tparts.append(f"{kids} Kind{'er' if kids > 1 else ''}")
    r["travellers"] = ", ".join(tparts) or (f"{len(trav)} Reisende" if trav else "")

    dep = offer.get("departure") or {}
    da = dep.get("departureAirport") or {}
    if da.get("value"):
        r["dep_airport"] = f"{da['value']} ({da.get('code', '')})"
    r["flight_out"] = _fmt_flight(dep)
    r["flight_ret"] = _fmt_flight(offer.get("return") or {})

    if offer.get("cancellationType") == "FREE_REFUNDABLE":
        r["cancellation"] = "kostenlos stornierbar"

    # Rückreisedatum (ISO) — für das automatische Archivieren abgelaufener Reisen.
    # Bevorzugt der Rückflug; sonst Anreisedatum + Nächte.
    ret = offer.get("return") or {}
    m = re.match(r"(\d{4}-\d{2}-\d{2})", ret.get("departureDateTime", "") or "")
    if m:
        r["return_date"] = m.group(1)
    else:
        am = re.match(r"(\d{4}-\d{2}-\d{2})", offer.get("arrivalDate", "") or "")
        if am and nights:
            try:
                d = datetime.strptime(am.group(1), "%Y-%m-%d") + timedelta(days=int(nights))
                r["return_date"] = d.strftime("%Y-%m-%d")
            except (TypeError, ValueError):
                pass

    date_de = _de_date(offer.get("arrivalDate", ""))
    r["details"] = " · ".join(x for x in (
        (f"{nights} Nächte ab {date_de}" if nights and date_de else r["nights"]),
        r["travellers"], room_desc, r["board"],
        (f"inkl. Flug ab {r['dep_airport']}" if r["dep_airport"] else "")) if x)

    giata = _giata_from_url(url)
    r.update(_fetch_rating(giata, verbose=verbose))
    r.update(_fetch_location(giata, (data.get("hotel") or {}).get("regionGiata"),
                             verbose=verbose))

    # Hotelbeschreibung als PDF (alle Parameter stehen im Offer-JSON)
    product = (data.get("hotel") or {}).get("product", "")
    operator = offer.get("tourOperator", "")
    arrival = offer.get("arrivalDate", "")
    if product and operator and arrival:
        r["pdf_url"] = HOTELINFO_PDF + "?" + urlencode({
            "bookingtype": "2", "date": _de_date(arrival),
            "bookingsequence": product, "operator": operator,
            "provider": (offer.get("supplier") or {}).get("provider", ""),
            "giata": giata, "promotion": offer.get("programType", ""),
        })

    r["available"] = True
    if vacancy:
        # Live-Bestätigung + Preis-Aufschlüsselung Hotel/Flüge (ATCOMRES).
        # Defensiv: nur ein explizites OK bestätigt; FAILED wird gespeichert,
        # überschreibt aber nicht available (kann auch Payload-/API-Drift sein).
        r.update(_fetch_vacancy(data, offer, verbose=verbose))
        r["last_booked"] = _fetch_last_booked(giata, verbose=verbose)
    if extras:
        # Quasi-statische Zusatzinfos (Gepäck, Anzahlung/Restzahlung) — der
        # Aufrufer holt sie nur, solange sie am Angebot noch fehlen.
        r["luggage"] = fetch_luggage(offer, verbose=verbose) or None
        r.update(fetch_payment_terms(offer, giata, verbose=verbose))
    r["ok"] = True
    if verbose:
        log.info(f"API ok: {r['price']} € p.P. · {r['hotel']} · "
              f"Sterne={r.get('stars')} Bewertung={r.get('rating')}")
    return r


def fetch_price(url: str, *, timeout_ms: int = 60000, check_availability: bool = True,
                extras: bool = False, flight_pin: str = "",
                verbose: bool = False) -> dict:
    """Liest den konkreten 'Günstigster Preis' einer TUI-Angebots-URL.

    Bevorzugt die JSON-API (schnell, robust); bei technischem Fehler automatischer
    Fallback auf das Auslesen der gerenderten Seite (_fetch_price_browser).

    Rückgabe (immer dict, nie Exception nach außen):
        ok, price, currency, old_price, discount, hotel, room, board, nights,
        travellers, dep_airport, flight_out, flight_ret, details,
        available (bool|None), total_price, cancellation, stars, rating,
        rating_count, recommendation, source, note
    """
    # check_availability steuert im API-Pfad den vacancy-check (Live-Bestätigung
    # + Preis-Split) — Massen-Abrufe (Vergleiche, Nächte-Matrix) sparen ihn aus.
    api = fetch_price_api(url, vacancy=check_availability, extras=extras,
                          flight_pin=flight_pin, verbose=verbose)
    if api is not None:
        return api  # API hat gültig geantwortet (Treffer oder echte Leermenge)
    # API technisch fehlgeschlagen → Browser-Fallback (immer sichtbar, gelb)
    log.warning("JSON-API nicht erreichbar → Browser-Fallback (langsamer)")
    rb = _fetch_price_browser(url, timeout_ms=timeout_ms,
                              check_availability=check_availability, verbose=verbose)
    rb["source"] = "browser"
    for k in ("cancellation", "stars", "rating", "rating_count", "recommendation"):
        rb.setdefault(k, None if k != "cancellation" else "")
    return rb


def _fetch_price_browser(url: str, *, timeout_ms: int = 60000,
                         check_availability: bool = True,
                         verbose: bool = False) -> dict:
    """Fallback: liest den Preis aus der gerenderten Seite (Headless-Chromium)."""
    from playwright.sync_api import sync_playwright  # lazy: nur für den Fallback nötig
    r = _empty_result()
    r["source"] = "browser"
    chromium_path = os.environ.get("CHROMIUM_PATH") or None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=chromium_path,
                                        args=["--no-sandbox", "--disable-dev-shm-usage"])
            ctx = browser.new_context(locale="de-DE", user_agent=USER_AGENT,
                                      viewport={"width": 1366, "height": 2200})
            page = ctx.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                time.sleep(2)
                for sel in CONSENT_SELECTORS:
                    try:
                        el = page.query_selector(sel)
                        if el and el.is_visible():
                            el.click()
                            if verbose:
                                log.info(f"Consent geklickt: {sel}")
                            break
                    except Exception:
                        pass

                try:
                    page.wait_for_selector(BEST_OFFER_SELECTOR, timeout=30000)
                except Exception:
                    pass
                try:
                    page.wait_for_selector(OFFER_CARD_SELECTOR, timeout=20000)
                except Exception:
                    pass
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass

                # Hotelname
                name_el = page.query_selector(HOTEL_NAME_SELECTOR)
                r["hotel"] = (name_el.inner_text().strip() if name_el else '') or hotel_from_url(url)

                # Erste echte Angebotskarte (= günstigste, da aufsteigend sortiert).
                # Muss Preis UND Flug/Verfügbarkeit enthalten, damit keine
                # "Empfehlungs"-Karte (anderes Hotel) erwischt wird.
                cards = page.query_selector_all(OFFER_CARD_SELECTOR)
                card = None
                for el in cards:
                    try:
                        t = el.inner_text() or ""
                    except Exception:
                        continue
                    if "pro Person" in t and "€" in t and \
                            ("Verfügbarkeit" in t or _FLIGHTLINE_RE.search(t)):
                        card = el
                        break
                if not card:  # Fallback: erste Karte mit Preis
                    for el in cards:
                        try:
                            if "pro Person" in (el.inner_text() or ""):
                                card = el
                                break
                        except Exception:
                            continue
                if not card:
                    r["note"] = "Keine Angebotskarte gefunden (Layout geändert oder kein Angebot)"
                    return r

                parsed = _parse_card(card.inner_text())
                r.update({k: parsed.get(k, r[k]) for k in
                          ("price", "old_price", "discount", "room", "board",
                           "nights", "travellers", "dep_airport", "flight_out", "flight_ret")})
                if r["price"] is None:
                    r["note"] = "Preis ('pro Person …') nicht erkannt"
                    return r

                # Lesbare Kurzbeschreibung
                r["details"] = " · ".join(x for x in (
                    r["nights"], r["travellers"], r["room"], r["board"],
                    (f"ab {r['dep_airport']}" if r['dep_airport'] else "")) if x)

                # Verfügbarkeit prüfen (optional)
                if check_availability:
                    try:
                        avail_btn = card.query_selector("button:has-text('Verfügbarkeit')")
                        if avail_btn:
                            avail_btn.click()
                            # auf Ergebnis warten
                            deadline = time.time() + 25
                            while time.time() < deadline:
                                ct = card.inner_text() or ""
                                if "verfügbar" in ct.lower() or "Gesamtpreis" in ct \
                                        or "nicht verfügbar" in ct.lower():
                                    break
                                time.sleep(1)
                            ct = card.inner_text() or ""
                            if "nicht verfügbar" in ct.lower():
                                r["available"] = False
                            elif "verfügbar" in ct.lower() or "Gesamtpreis" in ct:
                                r["available"] = True
                            # Gesamtpreis kann außerhalb der Karte stehen → seitenweit suchen
                            tm = _TOTAL_RE.search(ct)
                            if not tm:
                                gp = page.query_selector("text=/Gesamtpreis/")
                                if gp:
                                    parent = gp.evaluate_handle("e => e.parentElement").as_element()
                                    if parent:
                                        tm = _TOTAL_RE.search(parent.inner_text() or "")
                            if tm:
                                r["total_price"] = _to_amount(tm.group(1))
                            if verbose:
                                log.info(f"Verfügbarkeit={r['available']} total={r['total_price']}")
                    except Exception as e:
                        if verbose:
                            log.info(f"Verfügbarkeitsprüfung fehlgeschlagen: {e}")

                r["ok"] = True
                return r
            finally:
                browser.close()
    except Exception as e:  # pragma: no cover
        # Security: keine Exception-Details nach außen (UI/Sensor) — nur generisch.
        # Das technische Detail wird vom Aufrufer ins Log geschrieben.
        r["note"] = "Abruf fehlgeschlagen"
        r["detail"] = f"{type(e).__name__}: {e}"[:300]
        return r


if __name__ == "__main__":
    import json
    import sys
    test_url = sys.argv[1] if len(sys.argv) > 1 else (
        "https://www.tui.com/pauschalreisen/suchen/angebote/Riu-Papayas/2781/offer/"
        "?startDate=2027-05-01&endDate=2027-05-30&duration=10&travellers=1"
        "&searchScope=PACKAGE&showTotalPrice=0&regionGiataIds=128"
        "&departureAirports=STR&earlyBird=0&sortOffersAsc=1"
        "&sortOffersField=campaignOffers&roomTypeOpCodes=DZX1")
    print(json.dumps(fetch_price(test_url, verbose=True), ensure_ascii=False, indent=2))
