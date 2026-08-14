#!/usr/bin/env python3
"""Flugplan ab Stuttgart Airport (STR) — offenes, unauthentifiziertes JSON-API
des Flughafen-Betreibers (Azure API Management Backend, kein eigener STR-Dienst).

Live per Netzwerk-Mitschnitt ermittelt (Browser-DevTools, echter Seitenaufruf
von stuttgart-airport.com/de/reisende-besucher/reiseangebote/flugziele):
`GetConnections` liefert die komplette Flugplan-Tabelle als JSON, ohne
Auth-Header, ohne Referer-Pflicht, ohne CORS-Preflight — reiner `requests`-GET
reproduzierbar, kein Playwright nötig (Details: SCRAPING_STR.md). Die
Haupt-Website selbst (stuttgart-airport.com) sitzt hinter Akamai und blockt
Cloud-/Rechenzentrums-IPs pauschal per Edge-Rule — das API-Backend
(fsg-datahub.azure-api.net) ist davon nicht betroffen (live verifiziert).
"""
import logging
import threading
import time

import requests

from scraper import USER_AGENT  # keine eigene UA-Konstante duplizieren

log = logging.getLogger("tuiwatch.strflights")

_API_URL = "https://fsg-datahub.azure-api.net/legacy/Flightplan/GetConnections"
_HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}

# Flugplandaten ändern sich nicht minütlich (Saison-/Wochentagsraster) — ein
# lokaler Cache mit mehrstündiger TTL erspart es, bei jedem Modal-Öffnen bzw.
# jedem Tastenanschlag in der Suche erneut die komplette Liste (~2000 Einträge)
# vom Flughafen-Backend zu holen.
_CACHE_TTL = 6 * 3600
CACHE_TTL = _CACHE_TTL  # oeffentlicher Alias fuer den Warm-Worker/Zeitplan (app.py)
_cache_lock = threading.Lock()
_cache: dict = {"items": None, "fetched_at": 0.0}


def last_fetch_ts() -> float:
    """Zeitpunkt des letzten erfolgreichen Cache-Refreshs (0 = noch nie) — für
    die Zeitplan-Übersicht (app.py `_schedule_overview`)."""
    with _cache_lock:
        return _cache["fetched_at"]


def _fetch_all(*, verbose: bool = False) -> list[dict] | None:
    """Holt die komplette, ungefilterte Verbindungsliste (Departure + Arrival)
    vom API. None bei technischem Fehler."""
    out: list[dict] = []
    for flight_type in ("Departure", "Arrival"):
        try:
            resp = requests.get(_API_URL, headers=_HEADERS, timeout=20, params={
                "pagesize": 9999, "page": 1,
                "from": "nullT00:00:00.000Z", "till": "nullT23:59:00.000Z",
                "type": flight_type, "category": "", "airline": "",
                "airport": "", "country": "",
            })
            if resp.status_code != 200:
                log.warning("STR-Flugplan HTTP %s (type=%s)", resp.status_code, flight_type)
                return None
            data = resp.json()
        except Exception as e:
            log.warning("STR-Flugplan-Abruf fehlgeschlagen (type=%s): %s", flight_type, e)
            return None
        out.extend(data.get("Items") or [])
    if verbose:
        log.info("STR-Flugplan geladen: %d Verbindungen", len(out))
    return out


def _cached_items(*, verbose: bool = False) -> list[dict] | None:
    with _cache_lock:
        age = time.time() - _cache["fetched_at"]
        if _cache["items"] is not None and age < _CACHE_TTL:
            return _cache["items"]
    items = _fetch_all(verbose=verbose)
    if items is None:
        # Bei Fehler weiter den alten Cache-Stand anbieten (falls vorhanden),
        # statt Nutzer:innen mit leerem Ergebnis dastehen zu lassen.
        with _cache_lock:
            return _cache["items"]
    with _cache_lock:
        _cache["items"] = items
        _cache["fetched_at"] = time.time()
    return items


_WEEKDAY_KEYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_WEEKDAY_SHORT = {"Monday": "Mo", "Tuesday": "Di", "Wednesday": "Mi", "Thursday": "Do",
                  "Friday": "Fr", "Saturday": "Sa", "Sunday": "So"}


def _weekdays_short(weekdays: dict) -> str:
    return "".join(_WEEKDAY_SHORT[k] for k in _WEEKDAY_KEYS if weekdays.get(k)) or "–"


def list_destinations(*, verbose: bool = False) -> list[dict] | None:
    """Alle Zielflughäfen, die tatsächlich ab STR angeflogen werden — nur
    Departure-Zeilen, über den Code dedupliziert, alphabetisch nach Name.
    Für eine Gesamtübersicht ohne Sucheingabe (kombinierte Flugziel-Suche,
    siehe all_flights_routes.py). None bei technischem Fehler (kein
    Cache-Stand vorhanden)."""
    items = _cached_items(verbose=verbose)
    if items is None:
        return None
    seen: dict[str, dict] = {}
    for it in items:
        if it.get("Type") != "Departure":
            continue
        ap = it.get("Airport") or {}
        code = str(ap.get("Code") or "").strip()
        if not code or code in seen:
            continue
        seen[code] = {"code": code, "name": str(ap.get("Name") or ""),
                      "country": str(ap.get("Country") or "")}
    return sorted(seen.values(), key=lambda d: d["name"])


def search_connections(query: str = "", *, flight_type: str = "", date_from: str = "",
                       date_till: str = "", verbose: bool = False) -> list[dict] | None:
    """Verbindungen nach Zielflughafen (Code/Name) oder Land filtern.
    `flight_type`: '' (beide), 'Departure' oder 'Arrival'. `date_from`/
    `date_till`: Monatsgranularität 'YYYY-MM' (leer = keine Grenze) — ein
    Eintrag zählt als Treffer, wenn sein Saisonzeitraum (DateFrom–DateTill)
    das gewünschte Fenster überschneidet, nicht erst wenn er es vollständig
    umschließt (Standard-Intervall-Überlappungstest). None bei technischem
    Fehler (kein Cache-Stand vorhanden), sonst Liste (leer bei keinem
    Treffer) von
    {type, airline_code, airline_name, flight_no, airport_code, airport_name,
     country, weekdays_short, departure, arrival, via, date_from, date_till}."""
    items = _cached_items(verbose=verbose)
    if items is None:
        return None
    q = (query or "").strip().lower()
    ft = (flight_type or "").strip()
    # 'YYYY-MM' vergleicht sich als Text genauso wie als Datum (fixe Breite),
    # kein date-Parsing nötig — Monatsgranularität reicht (Wunsch: "als
    # Zeitraum reicht der Monat und das Jahr").
    df = (date_from or "").strip()[:7]
    dt = (date_till or "").strip()[:7]
    out = []
    for it in items:
        if ft and it.get("Type") != ft:
            continue
        if df and (it.get("DateTill") or "")[:7] < df:
            continue
        if dt and (it.get("DateFrom") or "")[:7] > dt:
            continue
        ap = it.get("Airport") or {}
        if q:
            haystack = " ".join(str(x or "") for x in (
                ap.get("Code"), ap.get("Name"), ap.get("Country"))).lower()
            if q not in haystack:
                continue
        al = it.get("Airline") or {}
        # `Via` ist entgegen der ursprünglichen Annahme (SCRAPING_STR.md) bei
        # Flügen mit Zwischenstopp KEIN Flughafencode-String, sondern ein
        # volles Airport-Objekt wie `Airport` selbst ({"Code": "LPA", "Name":
        # ..., "Country": ...}) — live verifiziert (7 von 4119 Einträgen, u. a.
        # Zwischenstopp LPA). Ungeprüft ans Frontend durchgereicht crashte dort
        # esc() mit "(s||'').replace is not a function" (Bugreport, Suche nach
        # "LPA" fand scheinbar 0 Treffer, weil das Rendering nach dem ersten
        # betroffenen Ergebnis abbrach). Nur den Code extrahieren, wie beim
        # Zielflughafen.
        via = it.get("Via")
        via_code = via.get("Code") if isinstance(via, dict) else via
        # Alle übrigen Felder ebenfalls hart auf str() casten, als Absicherung
        # gegen künftige Typüberraschungen aus diesem nicht offiziell
        # dokumentierten Drittanbieter-API.
        out.append({
            "type": str(it.get("Type") or ""),
            "airline_code": str(al.get("Code") or ""),
            "airline_name": str(al.get("Name") or ""),
            "flight_no": str(it.get("FlightName") or ""),
            "airport_code": str(ap.get("Code") or ""),
            "airport_name": str(ap.get("Name") or ""),
            "country": str(ap.get("Country") or ""),
            "weekdays_short": _weekdays_short(it.get("Weekdays") or {}),
            "departure": str(it.get("Departure") or ""),
            "arrival": str(it.get("Arrival") or ""),
            "via": str(via_code or ""),
            "date_from": str(it.get("DateFrom") or "")[:10],
            "date_till": str(it.get("DateTill") or "")[:10],
        })
    # Nach Zielflughafen, dann nach Abflugzeit sortiert — stabile,
    # nachvollziehbare Reihenfolge statt API-Originalreihenfolge (die nach
    # internem Datensatz-Import sortiert ist, nicht alphabetisch/zeitlich).
    out.sort(key=lambda r: (r["airport_name"], r["departure"]))
    return out


# Flugnummer-Details (Airline, Streckenbestätigung) über adsbdb.com — offene
# Community-Datenbank, kein Key, CORS offen (access-control-allow-origin: *),
# hier trotzdem server-seitig proxied wie alle anderen externen Abrufe im
# Add-on (Caching, ein Aufrufmuster, kein Drittanbieter-Call direkt aus dem
# Browser). Liefert die *planmäßige Standardroute* zu einem Callsign
# (Fluggesellschafts-Code + Flugnummer, z. B. "EW2262") — keine Live-Ortung,
# kein Bezug zum tatsächlichen Flugzeug/Tag (dafür bräuchte es einen
# ADS-B-Empfänger/Live-Feed, hat das Add-on nicht).
_CALLSIGN_URL = "https://api.adsbdb.com/v0/callsign/"
_CALLSIGN_CACHE_TTL = 12 * 3600
_callsign_cache_lock = threading.Lock()
_callsign_cache: dict = {}


def lookup_callsign(callsign: str, *, verbose: bool = False) -> dict | None:
    """Airline + Standardstrecke zu einem Callsign. Rückgabe
    {'ok': True, 'found': bool, ...} — 'found': False heißt adsbdb kennt
    diesen Callsign nicht (keine Routendaten hinterlegt, keine Fehlerlage).
    None bei technischem Fehler (Netzwerk/HTTP/Parsing)."""
    callsign = (callsign or "").strip().upper()
    if not callsign:
        return {"ok": True, "found": False}
    with _callsign_cache_lock:
        cached = _callsign_cache.get(callsign)
        if cached and time.time() - cached[0] < _CALLSIGN_CACHE_TTL:
            return cached[1]
    try:
        resp = requests.get(_CALLSIGN_URL + callsign, headers=_HEADERS, timeout=10)
    except Exception as e:
        log.warning("adsbdb-Abruf fehlgeschlagen (callsign=%s): %s", callsign, e)
        return None
    if resp.status_code == 404:
        result = {"ok": True, "found": False}
    elif resp.status_code != 200:
        log.warning("adsbdb HTTP %s (callsign=%s)", resp.status_code, callsign)
        return None
    else:
        try:
            route = ((resp.json() or {}).get("response") or {}).get("flightroute")
        except Exception as e:
            log.warning("adsbdb-Antwort nicht lesbar (callsign=%s): %s", callsign, e)
            return None
        if not route:
            result = {"ok": True, "found": False}
        else:
            al = route.get("airline") or {}
            origin = route.get("origin") or {}
            dest = route.get("destination") or {}
            result = {
                "ok": True, "found": True,
                "callsign_icao": str(route.get("callsign_icao") or ""),
                "callsign_iata": str(route.get("callsign_iata") or ""),
                "airline_name": str(al.get("name") or ""),
                "origin_name": str(origin.get("name") or ""),
                "origin_iata": str(origin.get("iata_code") or ""),
                "origin_city": str(origin.get("municipality") or ""),
                "origin_country": str(origin.get("country_name") or ""),
                "dest_name": str(dest.get("name") or ""),
                "dest_iata": str(dest.get("iata_code") or ""),
                "dest_city": str(dest.get("municipality") or ""),
                "dest_country": str(dest.get("country_name") or ""),
            }
    with _callsign_cache_lock:
        _callsign_cache[callsign] = (time.time(), result)
    if verbose:
        log.info("adsbdb %s: %s", callsign, "gefunden" if result["found"] else "keine Routendaten")
    return result
