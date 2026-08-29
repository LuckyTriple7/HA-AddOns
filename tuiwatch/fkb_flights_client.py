#!/usr/bin/env python3
"""Saisonflugplan ab/nach Karlsruhe/Baden-Baden (FKB, „Baden-Airpark").

Vierter Flugplan neben [str_flights_client.py](str_flights_client.py) (JSON-API,
Saisonstrecken), [fra_flights_client.py](fra_flights_client.py) (JSON, Einzelflüge)
und [muc_flights_client.py](muc_flights_client.py) (Saison-PDF). Datenmodell wie
STR/MUC: Saisonstrecken mit Wochentagsraster und Gültigkeit von–bis.

Quelle ist der „Saisonflugpläne"-Block auf `baden-airpark.de` (WordPress). Die
Tabelle wird per JavaScript aus `admin-ajax.php?action=flightmap` nachgeladen —
**POST mit JSON-Body**, kein Auth, kein Nonce, kein Referer-Zwang. Ein GET mit
denselben Werten als Query-Parametern liefert stillschweigend `posts: "empty"`.
Die Antwort ist JSON, enthält aber **fertig gerendertes HTML** statt Daten; es
gibt keinen JSON-Datensatz je Flug, deshalb wird hier geparst statt gemappt
(Details und Fallstricke: SCRAPING_FKB.md).
"""
import html
import logging
import re
import threading
import time

import requests

from scraper import USER_AGENT  # keine eigene UA-Konstante duplizieren

log = logging.getLogger("tuiwatch.fkbflights")

_AJAX_URL = "https://www.baden-airpark.de/wp/wp-admin/admin-ajax.php?action=flightmap"
_HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json",
            "Content-Type": "application/json"}

# Saisonflugpläne ändern sich nicht stündlich (Wochentagsraster über Monate) —
# derselbe Cache-Gedanke wie bei str_flights_client.py.
CACHE_TTL = 6 * 3600
_cache_lock = threading.Lock()
_cache: dict = {"rows": None, "fetched_at": 0.0}

_WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")

# Eine Tabellenzeile beginnt mit `<div role="row" class="flight-table__row …">`;
# jede Zelle trägt eine sprechende Klasse (`…__origin`, `…__type`, `…__validity`,
# `…__plane`, `…__airline`). Geparst wird bewusst pro Zelle über diese Klassen
# statt über feste Reihenfolge/Indizes — die Reihenfolge der Spalten wechselt
# zwischen Tages- und Saisonplan (live gesehen).
_ROW_RE = re.compile(r'<div role="row"[^>]*class="[^"]*flight-table__row[^"]*"[^>]*>'
                     r'(.*?)(?=<div role="row"|\Z)', re.S)
_CELL_RE = re.compile(r'<div role="cell"[^>]*class="[^"]*flight-table__col__(\w+)[^"]*"[^>]*>'
                      r'(.*?)(?=<div role="cell"|\Z)', re.S)
_SPAN_RE = re.compile(r'<span[^>]*>(.*?)</span>', re.S)
_ANCHOR_RE = re.compile(r'<a\b[^>]*>(.*?)</a>', re.S)
_TAG_RE = re.compile(r'<[^>]+>')
_DAY_RE = re.compile(r'<span[^>]*class="flight-day flight-day--(\d)"[^>]*>(.*?)</span>', re.S)
_SEATS_RE = re.compile(r'data-bs-title="([^"]*)"')
_AIRPORT_RE = re.compile(r'^(.*?)\s*\(([A-Z0-9]{3})\)$')
_TIMES_RE = re.compile(r'(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})')
_VALIDITY_RE = re.compile(r'(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}\.\d{2}\.\d{4})')
_SEASON_RE = re.compile(r'\(([^)]*flugplan[^)]*)\)', re.I)


def last_fetch_ts() -> float:
    """Zeitpunkt des letzten erfolgreichen Cache-Refreshs (0 = noch nie) — für
    die Zeitplan-Übersicht (app.py `_schedule_overview`)."""
    with _cache_lock:
        return _cache["fetched_at"]


def _text(fragment: str) -> str:
    """HTML-Fragment → sichtbarer Text (Tags raus, Entities auf, Leerraum eng)."""
    return re.sub(r"\s+", " ", html.unescape(_TAG_RE.sub(" ", fragment or ""))).strip()


def _iso_date(de: str) -> str:
    """`01.04.2026` → `2026-04-01` (ISO wie bei STR/MUC, damit sich Zeiträume
    vergleichen lassen)."""
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})$", de or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""


def _weekdays_short(cell: str) -> str:
    """Wochentagsraster der Zelle → `Mo, Di, Do` bzw. `täglich` (dieselbe
    Darstellung wie bei STR/MUC). Aktive Tage stehen als Kürzel im jeweiligen
    `flight-day--<n>`-Span, inaktive als `-`."""
    days = [_WEEKDAYS[int(n)] for n, txt in _DAY_RE.findall(cell)
            if _text(txt) not in ("", "-") and int(n) < 7]
    if not days:
        return "–"
    return ", ".join(days) if len(days) < 7 else "täglich"


def _parse_rows(posts_html: str, direction: str) -> list[dict]:
    """Gerendertes Tabellen-HTML → Verbindungsliste. Zeilen, denen Ziel oder
    Zeiten fehlen, werden übersprungen (kein Abbruch) — die Seite liefert je
    nach Saison auch Zwischenüberschriften und leere Platzhalterzeilen."""
    rows = []
    for row_html in _ROW_RE.findall(posts_html or ""):
        cells = {name: frag for name, frag in _CELL_RE.findall(row_html)}
        origin = cells.get("origin", "")
        spans = [_text(s) for s in _SPAN_RE.findall(origin)]
        spans = [s for s in spans if s]
        if not spans:
            continue
        m = _AIRPORT_RE.match(spans[0])
        airport_name = (m.group(1) if m else spans[0]).strip()
        airport_code = m.group(2) if m else ""
        flight_no = spans[1] if len(spans) > 1 else ""

        type_cell = cells.get("type", "")
        tm = _TIMES_RE.search(_text(type_cell))
        if not (airport_name and tm):
            continue
        validity = _text(cells.get("validity", ""))
        vm = _VALIDITY_RE.search(validity)
        sm = _SEASON_RE.search(validity)
        plane_cell = cells.get("plane", "")
        plane_spans = [_text(s) for s in _SPAN_RE.findall(plane_cell)]
        plane = next((s for s in plane_spans if s), "")
        seats = ""
        if (sem := _SEATS_RE.search(plane_cell)):
            seats = _text(sem.group(1))
        airline_cell = cells.get("airline", "")
        airline = _text((_ANCHOR_RE.search(airline_cell) or [None, ""])[1]) \
            if _ANCHOR_RE.search(airline_cell) else _text(airline_cell)

        # Flugnummer wie bei STR/MUC in Airline-Code + Nummer zerlegt, damit die
        # Anzeige dieselbe Form hat („FR 5182"). Ohne erkennbares Muster bleibt
        # der Code leer und die Zeile trägt nur die Nummer, wie geliefert.
        fm = re.match(r"([A-Z0-9]{2,3})\s*(\d{1,4}[A-Z]?)$", flight_no)
        rows.append({
            "direction": direction,
            "airline_code": fm.group(1) if fm else "",
            "airline_name": airline,
            "flight_no": f"{fm.group(1)} {fm.group(2)}" if fm else flight_no,
            "airport_code": airport_code,
            "airport_name": airport_name,
            # Der Saisonplan nennt kein Land — bleibt leer und wird in der
            # kombinierten Zielliste (all_flights_routes.py) aus den anderen
            # Flugplänen ergänzt, sofern dort dasselbe Ziel vorkommt.
            "country": "",
            "departure": tm.group(1),
            "arrival": tm.group(2),
            "weekdays_short": _weekdays_short(type_cell),
            "date_from": _iso_date(vm.group(1)) if vm else "",
            "date_till": _iso_date(vm.group(2)) if vm else "",
            "season": sm.group(1) if sm else "",
            "plane": plane,
            "seats": seats,
        })
    return rows


def _fetch_direction(direction: str, *, verbose: bool = False) -> list[dict] | None:
    """Kompletten Saisonplan einer Richtung holen (alle Ziele, alle Saisons).
    None bei technischem Fehler."""
    api_type = "departures" if direction == "departure" else "arrivals"
    # `type` MUSS ein String sein: als Liste (`["departures"]`) antwortet die
    # Seite mit `success: false` und einer PHP-Fehlermeldung
    # (`FlightType::tryFrom(): … array given`) — live gesehen.
    body = {"airport": "all", "date": None, "season": "all", "type": api_type,
            "flight": None, "plane": None, "page": 1, "offset": 0, "limit": -1}
    try:
        resp = requests.post(_AJAX_URL, json=body, headers=_HEADERS, timeout=30)
        if resp.status_code != 200:
            log.warning("FKB-Flugplan HTTP %s (%s)", resp.status_code, api_type)
            return None
        data = resp.json()
    except Exception as e:
        log.warning("FKB-Flugplan-Abruf fehlgeschlagen (%s): %s", api_type, e)
        return None
    if not data.get("success"):
        # `data` ist im Fehlerfall ein String (PHP-Meldung), kein Objekt.
        log.warning("FKB-Flugplan meldet Fehler (%s): %.200s", api_type, data.get("data"))
        return None
    posts = (data.get("data") or {}).get("posts") or ""
    if posts == "empty":
        log.warning("FKB-Flugplan leer (%s) — Anfrageform geändert?", api_type)
        return []
    rows = _parse_rows(posts, direction)
    if verbose:
        log.info("FKB-Flugplan %s: %d Verbindungen geparst", api_type, len(rows))
    return rows


def _fetch_all(*, verbose: bool = False) -> list[dict] | None:
    out: list[dict] = []
    for direction in ("departure", "arrival"):
        rows = _fetch_direction(direction, verbose=verbose)
        if rows is None:
            return None
        out.extend(rows)
    return out


def _cached_rows(*, verbose: bool = False) -> list[dict] | None:
    with _cache_lock:
        age = time.time() - _cache["fetched_at"]
        if _cache["rows"] is not None and age < CACHE_TTL:
            return _cache["rows"]
    rows = _fetch_all(verbose=verbose)
    if rows is None:
        # Bei Fehler den alten Stand weiter anbieten (falls vorhanden), statt
        # leer dazustehen — wie bei str_flights_client.py.
        with _cache_lock:
            return _cache["rows"]
    with _cache_lock:
        _cache["rows"] = rows
        _cache["fetched_at"] = time.time()
    return rows


def refresh(*, verbose: bool = False) -> bool:
    """Cache sofort erneuern (Warm-Worker/Knopf im Fenster)."""
    rows = _fetch_all(verbose=verbose)
    if rows is None:
        return False
    with _cache_lock:
        _cache["rows"] = rows
        _cache["fetched_at"] = time.time()
    return True


def list_destinations(*, verbose: bool = False) -> list[dict] | None:
    """Alle Ziele, die tatsächlich ab FKB angeflogen werden — nur Abflüge, über
    den IATA-Code dedupliziert, alphabetisch nach Name. Pendant zu
    str_/muc_flights_client.list_destinations(). None bei technischem Fehler."""
    rows = _cached_rows(verbose=verbose)
    if rows is None:
        return None
    seen: dict[str, dict] = {}
    for r in rows:
        if r["direction"] != "departure":
            continue
        code = r["airport_code"]
        if not code or code in seen:
            continue
        seen[code] = {"code": code, "name": r["airport_name"], "country": r["country"]}
    return sorted(seen.values(), key=lambda d: d["name"])


def search(query: str = "", direction: str = "", date_from: str = "",
           date_till: str = "", limit: int = 400, verbose: bool = False) -> dict | None:
    """Verbindungen filtern (gleiche Aufrufform wie muc_flights_client.search).

    `query` sucht in Zielcode und Ortsname; `direction` ist `departure` (ab FKB),
    `arrival` (nach FKB) oder leer; `date_from`/`date_till` sind Monate
    (`YYYY-MM`) und vergleichen gegen die Gültigkeitsspanne der Verbindung —
    Treffer schon bei Überschneidung, nicht erst bei vollständiger Abdeckung."""
    rows = _cached_rows(verbose=verbose)
    if rows is None:
        return None
    q = (query or "").strip().lower()
    df = (date_from or "").strip()[:7]
    dt = (date_till or "").strip()[:7]
    out = []
    for r in rows:
        if direction and r["direction"] != direction:
            continue
        # Zeilen ohne Gültigkeitsangabe nie wegfiltern (sonst verschwinden sie
        # bei jedem gesetzten Zeitraum), sondern nur echte Nicht-Überschneidung.
        if df and r["date_till"] and r["date_till"][:7] < df:
            continue
        if dt and r["date_from"] and r["date_from"][:7] > dt:
            continue
        if q and q not in " ".join((r["airport_code"], r["airport_name"],
                                    r["country"], r["airline_name"])).lower():
            continue
        out.append(r)
    out.sort(key=lambda r: (r["airport_name"], r["departure"], r["date_from"]))
    return {"rows": out[:limit], "total": len(out), "count": len(rows),
            "fetched_ts": last_fetch_ts()}
