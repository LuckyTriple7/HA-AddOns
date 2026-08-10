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
_cache_lock = threading.Lock()
_cache: dict = {"items": None, "fetched_at": 0.0}


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


def search_connections(query: str = "", *, flight_type: str = "", verbose: bool = False) -> list[dict] | None:
    """Verbindungen nach Zielflughafen (Code/Name) oder Land filtern.
    `flight_type`: '' (beide), 'Departure' oder 'Arrival'. None bei
    technischem Fehler (kein Cache-Stand vorhanden), sonst Liste (leer bei
    keinem Treffer) von
    {type, airline_code, airline_name, flight_no, airport_code, airport_name,
     country, weekdays_short, departure, arrival, via, date_from, date_till}."""
    items = _cached_items(verbose=verbose)
    if items is None:
        return None
    q = (query or "").strip().lower()
    ft = (flight_type or "").strip()
    out = []
    for it in items:
        if ft and it.get("Type") != ft:
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
