#!/usr/bin/env python3
"""Flugplan ab Frankfurt Airport (FRA) — offenes JSON der Flughafen-Website.

Bewusst **getrennt** von [str_flights_client.py](str_flights_client.py) gehalten:
beide Flughäfen liefern völlig verschiedene Datenmodelle (STR: Saisonstrecken mit
Wochentagsraster, FRA: Einzelflüge je Datum), eine gemeinsame Abstraktion würde
beides verbiegen. Gemeinsam ist nur der Einstieg in der Oberfläche (✈️-Knopf mit
Flughafen-Auswahl).

Quelle (live per Netzwerk-Mitschnitt der Fluginfo-Seite ermittelt, Details:
SCRAPING_FRA.md):

    GET …/de/_jcr_content.flights.json/search?q=<Text>     → Flughafen-Suche
    GET …/de/_jcr_content.flights.json/filter?flighttype=departures
        &airport=<IATA[,IATA…]>&airline=<Code>&page=<n>    → Flüge

Kein Auth-Header, kein Referer, kein Cookie — nackter `requests.get` liefert 200.
"""
import logging
import re
import threading
import time

import requests

from scraper import USER_AGENT  # keine eigene UA-Konstante duplizieren

log = logging.getLogger("tuiwatch.fraflights")

_BASE = "https://www.frankfurt-airport.com/de/_jcr_content.flights.json"
_SEARCH_URL = f"{_BASE}/search"
_FILTER_URL = f"{_BASE}/filter"
_HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}

# Die Flugplandaten sind ein Saisonstand (Feld `lusaison`, wird einmal täglich
# erneuert) — ein lokaler Cache je Seite erspart bei jedem Tastenanschlag in der
# Suche den erneuten Abruf derselben 25er-Seiten.
_PAGE_TTL = 3 * 3600
_AIRPORT_TTL = 24 * 3600
_MAX_PAGES = 12          # 12 × 25 = 300 Flüge je Suche — deckt jeden Zeitraum ab
_cache_lock = threading.Lock()
_page_cache: dict = {}   # (typ, airports, page) -> (ts, json)
_airport_cache: dict = {}  # suchbegriff -> (ts, liste)

_IATA_RE = re.compile(r"^[A-Za-z]{3}$")


def _get(url: str, params: dict, verbose: bool = False):
    """GET mit JSON-Antwort; None bei Fehler (die Seite antwortet bei ungültigen
    Parametern mit HTML statt JSON — deshalb Content-Type nicht blind trauen)."""
    try:
        if verbose:
            log.info("FRA-Flugplan GET %s %s", url, params)
        resp = requests.get(url, params=params, headers=_HEADERS, timeout=20)
        if resp.status_code != 200:
            log.warning("FRA-Flugplan HTTP %s (%s)", resp.status_code, params)
            return None
        return resp.json()
    except Exception as e:
        log.warning("FRA-Flugplan-Abruf fehlgeschlagen (%s): %s", params, e)
        return None


# ── Flughafen-Suche ────────────────────────────────────────────────────────────

def search_airports(query: str, verbose: bool = False) -> list | None:
    """Flughäfen zu einem Suchbegriff (Ort, Land, IATA-Code). None bei Fehler.

    Rückgabe: [{code, name, country, region}] — `code` ist der IATA-Code, mit dem
    der Flug-Filter arbeitet."""
    q = (query or "").strip()
    if len(q) < 2:
        return []
    key = q.lower()
    now = time.time()
    with _cache_lock:
        hit = _airport_cache.get(key)
        if hit and now - hit[0] < _AIRPORT_TTL:
            return hit[1]
    data = _get(_SEARCH_URL, {"q": q}, verbose=verbose)
    if data is None:
        return None
    out = []
    for a in ((data.get("airports") or {}).get("data") or []):
        code = str(a.get("id") or "").strip().upper()
        if not code:
            continue
        out.append({
            "code": code,
            "name": str(a.get("name") or a.get("nameshort") or ""),
            "country": str(a.get("land") or ""),
            "region": str(a.get("regionorg") or ""),
        })
    with _cache_lock:
        _airport_cache[key] = (now, out)
    if verbose:
        log.info("FRA-Flugplan: %d Flughafen-Treffer für %r", len(out), q)
    return out


# ── Flüge ──────────────────────────────────────────────────────────────────────

def _fetch_page(flight_type: str, airports: str, page: int,
                verbose: bool = False) -> dict | None:
    key = (flight_type, airports, page)
    now = time.time()
    with _cache_lock:
        hit = _page_cache.get(key)
        if hit and now - hit[0] < _PAGE_TTL:
            return hit[1]
    params = {"flighttype": flight_type, "airport": airports, "page": page}
    data = _get(_FILTER_URL, params, verbose=verbose)
    if data is None:
        return None
    with _cache_lock:
        _page_cache[key] = (now, data)
    return data


def _row(it: dict) -> dict:
    """Ein Flug-Eintrag der API auf die Felder der Tabelle eingedampft.

    Alles hart auf str()/int() gecastet — das API ist nicht dokumentiert, und im
    STR-Pendant hat schon einmal ein unerwartetes Objekt statt eines Strings das
    Frontend-Rendering abgebrochen (siehe str_flights_client._row-Kommentar)."""
    sched = str(it.get("sched") or "")
    cs = it.get("cs")
    codeshares = [str(x) for x in cs] if isinstance(cs, list) else (
        [str(cs)] if cs else [])
    try:
        duration = int(it.get("duration") or 0) or None
    except (TypeError, ValueError):
        duration = None
    return {
        "date": sched[:10],
        "time": sched[11:16],
        "sched": sched,
        "arrival": str(it.get("schedArr") or "")[11:16],
        "flight_no": str(it.get("fnr") or ""),
        "airline_code": str(it.get("al") or ""),
        "airline_name": str(it.get("alname") or ""),
        "airport_code": str(it.get("iata") or ""),
        "airport_name": str(it.get("apname") or ""),
        "terminal": str(it.get("terminal") or ""),
        "hall": str(it.get("halle") or ""),
        "gate": str(it.get("gate") or ""),
        "checkin": str(it.get("schalter") or ""),
        "aircraft": str(it.get("ac") or ""),
        "registration": str(it.get("reg") or ""),
        "duration_min": duration,
        "stops": it.get("stops") if isinstance(it.get("stops"), int) else None,
        "codeshares": codeshares,
    }


def _find_start_page(flight_type: str, airports: str, date_from: str,
                     max_page: int, verbose: bool = False) -> int:
    """Erste Seite, deren letzter Flug im Zeitraum liegt — per Binärsuche.

    Die Antwort ist chronologisch sortiert (live verifiziert), ein Datumsfilter
    existiert im API nicht (`date`/`from`/`day` werden ignoriert). Statt sich von
    Seite 1 heranzublättern (bei weit entfernten Reisen 20+ Abrufe) reichen so
    ~log2(Seiten) Abrufe."""
    lo, hi, best = 1, max_page, 1
    while lo <= hi:
        mid = (lo + hi) // 2
        data = _fetch_page(flight_type, airports, mid, verbose=verbose)
        items = (data or {}).get("data") or []
        if not items:
            hi = mid - 1
            continue
        last = str(items[-1].get("sched") or "")[:7]
        if last < date_from:
            lo = mid + 1
        else:
            best = mid
            hi = mid - 1
    return best


def search_flights(query: str, flight_type: str = "departures",
                   date_from: str = "", date_till: str = "",
                   limit: int = 300, verbose: bool = False) -> dict | None:
    """Flüge ab/nach FRA zu einem Ziel. None bei Abruffehler.

    `query` ist ein IATA-Code (z. B. `LPA`) oder Freitext (Ort/Land) — Freitext
    wird über die Flughafen-Suche in bis zu 3 Codes aufgelöst und in **einem**
    Filter-Aufruf abgefragt (das API nimmt mehrere Codes kommagetrennt).
    `date_from`/`date_till` sind Monate (`YYYY-MM`) wie beim STR-Flugplan.

    Rückgabe: {airports, rows, results, truncated}."""
    q = (query or "").strip()
    if not q:
        return {"airports": [], "rows": [], "results": 0, "truncated": False}
    ft = "arrivals" if flight_type == "arrivals" else "departures"

    if _IATA_RE.match(q):
        codes = [q.upper()]
        airports = [{"code": q.upper(), "name": "", "country": "", "region": ""}]
    else:
        found = search_airports(q, verbose=verbose)
        if found is None:
            return None
        airports = found[:3]
        codes = [a["code"] for a in airports]
    if not codes:
        return {"airports": [], "rows": [], "results": 0, "truncated": False}
    key = ",".join(codes)

    first = _fetch_page(ft, key, 1, verbose=verbose)
    if first is None:
        return None
    max_page = int(first.get("maxpage") or 1)
    results = int(first.get("results") or 0)
    df = (date_from or "").strip()[:7]
    dt = (date_till or "").strip()[:7]

    start = _find_start_page(ft, key, df, max_page, verbose=verbose) if df else 1
    rows: list = []
    truncated = False
    for page in range(start, max_page + 1):
        data = first if page == 1 else _fetch_page(ft, key, page, verbose=verbose)
        if data is None:
            break
        items = data.get("data") or []
        if not items:
            break
        stop = False
        for it in items:
            month = str(it.get("sched") or "")[:7]
            if df and month < df:
                continue
            if dt and month > dt:
                stop = True          # sortiert → ab hier kommt nichts mehr
                break
            rows.append(_row(it))
        if stop:
            break
        if len(rows) >= limit or page - start + 1 >= _MAX_PAGES:
            truncated = page < max_page
            break
    if verbose:
        log.info("FRA-Flugplan: %d Flüge für %s (%s, %s–%s), gesamt %d",
                 len(rows), key, ft, df or "–", dt or "–", results)
    return {"airports": airports, "rows": rows[:limit], "results": results,
            "truncated": truncated or len(rows) > limit}
