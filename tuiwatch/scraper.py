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
from playwright.sync_api import sync_playwright

# Eigener Logger; hängt über den Root-Handler in der UI-Konsole (siehe app.py).
log = logging.getLogger("tuiwatch.scraper")

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

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
    except Exception:
        pass
    return ''


def travellers_from_url(url: str) -> int:
    """Liest die Reisendenzahl aus dem URL-Parameter `travellers=` (Default 1)."""
    try:
        for k, v in parse_qsl(urlparse(url).query, keep_blank_values=True):
            if k == 'travellers':
                n = int(v)
                return n if n > 0 else 1
    except Exception:
        pass
    return 1


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
_API_HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}


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


def _map_board_types(val: str) -> str:
    """Übersetzt die Verpflegungs-Kurzcodes der Seiten-URL (z. B. ``AI``) in die
    globalen Codes der API (``GT06-AI``). Mehrfachwerte (``,``/``;``) bleiben erhalten."""
    out = []
    for t in re.split(r'[;,]', val or ''):
        t = t.strip()
        if t:
            out.append(t if t.startswith('GT06-') else 'GT06-' + t)
    return ','.join(out)


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


def build_calendar_api_url(url: str) -> str:
    """Baut die Preiskalender-API-URL aus der Angebots-Seiten-URL. Übernimmt die
    Filter (Verpflegung, Veranstalter, Zimmercode, Abflughafen) und fragt die **volle
    buchbare Spanne** ab (heute bis ~14 Monate, mind. bis zum gewählten Zeitraum),
    damit man durch alle verfügbaren Monate blättern kann. Die Hervorhebung des
    gewählten Zeitraums macht fetch_calendar selbst."""
    p = urlparse(url)
    q = {k: v[0] for k, v in parse_qs(p.query, keep_blank_values=True).items()}

    def plus(d, days):
        return (d + timedelta(days=days)).isoformat()

    def parse(d, fallback):
        try:
            return date.fromisoformat(d)
        except Exception:
            return fallback

    today = date.today()
    we = parse(q.get('endDate', ''), today)
    sd = today.isoformat()
    ed = max(plus(today, 420), plus(we, 14))   # volle Inventarspanne, mind. bis Zeitraum +14 T

    params = {
        'searchscope': q.get('searchScope', 'PACKAGE'),
        # Der Kalender erwartet eine EINZELNE Dauer; aus Bereichen wie "7-"/"9-12"
        # nehmen wir die untere Zahl (so macht es auch die TUI-Seite).
        'duration': _single_duration(q.get('duration', '')),
        'adults': q.get('travellers', '1'),
        'giatas': _giata_from_url(url),
        'startSearchRange': sd, 'endSearchRange': ed,
        'tenant': 'tui.com',
        'airports': q.get('departureAirports', ''),
        'roomTypeOpCodes': q.get('roomTypeOpCodes', ''),
        # Achtung: der Kalender-Endpoint nutzt andere Parameternamen als der
        # Offer-Endpoint — Verpflegung = boardCodes, Veranstalter = tourOperators.
        'boardCodes': _map_board_types(q.get('boardTypes', '')),
        'tourOperators': q.get('operators', q.get('tourOperators', '')),
        'startDate': sd, 'endDate': ed,
    }
    return f"{CALENDAR_API}?{urlencode(params)}"


def fetch_calendar(url: str, *, verbose: bool = False) -> dict | None:
    """Liest den Preiskalender (günstigster Preis p. P. je Abreisetag) direkt aus der
    JSON-API. Rückgabe-dict oder None bei technischem Fehler."""
    try:
        cal_url = build_calendar_api_url(url)
        if verbose:
            log.info("Kalender-API GET %s", cal_url)
        resp = requests.get(cal_url, headers=_API_HEADERS, timeout=25)
        if resp.status_code != 200:
            if verbose:
                log.warning(f"Kalender HTTP {resp.status_code}")
            return None
        data = resp.json()
    except Exception as e:
        if verbose:
            log.warning(f"Kalender-Fehler: {type(e).__name__}: {e}")
        return None

    days: dict[str, float] = {}
    for o in data.get('offers') or []:
        ad = o.get('arrivalDate')
        pp = o.get('calculatedPricePerPerson')
        if ad and pp is not None:
            days[ad] = min(days.get(ad, float('inf')), pp)

    q = {k: v[0] for k, v in parse_qs(urlparse(url).query, keep_blank_values=True).items()}
    ws, we = q.get('startDate', ''), q.get('endDate', '')
    # Nächte (für die Rückreise-Berechnung beim Klick: endDate = Anreise + Nächte).
    # Aus Dauer-Bereichen wie "7-"/"9-12" die untere Zahl, wie es auch tui.com nutzt.
    try:
        nights = int(_single_duration(q.get('duration', '')))
    except (TypeError, ValueError):
        nights = None
    res = {
        'ok': bool(days),
        'currency': data.get('currency', 'EUR'),
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
    if verbose:
        log.info(f"Kalender: {len(days)} Tage, günstigster {res.get('cheapest_date')} "
              f"= {res.get('cheapest_price')} €")
    return res


def _de_date(iso: str) -> str:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", iso or "")
    return f"{m.group(3)}.{m.group(2)}.{m.group(1)}" if m else ""


def _de_datetime(iso: str) -> str:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})", iso or "")
    return f"{m.group(3)}.{m.group(2)}.{m.group(1)}, {m.group(4)}:{m.group(5)}" if m else ""


def _fmt_flight(leg: dict) -> str:
    if not leg:
        return ""
    dt = _de_datetime(leg.get("departureDateTime", ""))
    airline = (leg.get("airline") or {}).get("value", "")
    dep = (leg.get("departureAirport") or {}).get("code", "")
    arr = (leg.get("arrivalAirport") or {}).get("code", "")
    route = f"{dep}→{arr}" if dep and arr else ""
    so = leg.get("stopOver")
    stops = "Direktflug" if so in (0, None) else (
        "1 Zwischenstopp" if so == 1 else f"{so} Zwischenstopps")
    return " · ".join(x for x in (dt, route, airline, stops) if x)


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


def fetch_price_api(url: str, *, verbose: bool = False) -> dict | None:
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
            return None
        data = resp.json()
    except Exception as e:
        if verbose:
            log.warning(f"API-Fehler: {type(e).__name__}: {e}")
        return None

    r = _empty_result()
    r["source"] = "api"
    r["hotel"] = (data.get("hotel") or {}).get("name", "") or hotel_from_url(url)
    r["currency"] = data.get("currency", "EUR")
    offers = data.get("offers") or []
    if verbose:
        log.info("Offer-API: %d Angebot(e) zurück", len(offers))
    if not offers:
        r["available"] = False
        r["note"] = "Kein Angebot im gewählten Zeitraum"
        return r

    offer = next((o for o in offers if o.get("cheapest")), None) or \
        min(offers, key=lambda o: o.get("calculatedPricePerPerson") or float("inf"))

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

    nights = offer.get("lengthOfStay")
    r["nights"] = f"{nights} Nächte" if nights else ""

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
    r["ok"] = True
    if verbose:
        log.info(f"API ok: {r['price']} € p.P. · {r['hotel']} · "
              f"Sterne={r.get('stars')} Bewertung={r.get('rating')}")
    return r


def fetch_price(url: str, *, timeout_ms: int = 60000, check_availability: bool = True,
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
    api = fetch_price_api(url, verbose=verbose)
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
