#!/usr/bin/env python3
"""FRA-Zielliste über das Tagesbord einer **Drittseite** — NICHT der
Flughafen-Betreiber, NICHT die offizielle FRA-API (siehe fra_flights_client.py,
die für die gezielte Suche zuständig bleibt und unverändert ist).

Hintergrund: die offizielle FRA-API liefert keine Gesamtliste (siehe
SCRAPING_FRA.md — 123.289 Abflüge / 4.854 Seiten ohne Zielfilter, praktisch
nicht abholbar). `airport-frankfurt-am-main.de` (Fußzeile „© by FraHub")
betreibt dafür eine Ankunfts-/Abflugtafel, deren DataTable ihr Board per AJAX
aus einem eigenen JSON lädt:

    GET https://www.airport-frankfurt-am-main.de/flugzeiten/abflug-fra.json

Kein Auth, kein Cookie nötig, live per HTML-Quelltext gefunden (Skript
initialisiert `$('#flight-flights').DataTable({ajax:{url:'/flugzeiten/
abflug-fra.json', ...}})`). Antwort: `{"data":[{"0":"<span…>AS 8965…",
"1":"Condor","2":"Palma de Mallorca (PMI)","3":"13.08.2026 04:45", ...}]}` —
Feld `2` ist `"<Stadt> (<IATA>)"`.

**Grenzen (deshalb bewusst getrennt von str_/muc_flights_client.py):**
- Drittanbieter, keine amtliche Quelle — Genauigkeit/Vollständigkeit nicht
  verifizierbar wie bei Flughafen-eigenen Daten.
- Liefert nur den **heutigen** Tag, kein Datumsparameter gefunden — deshalb
  wird über `ROLLING_DAYS` hinweg akkumuliert (auf Platte gemerkt), damit
  auch nur wöchentlich fliegende Ziele auftauchen. Ergebnis bleibt eine
  Annäherung, kein amtlicher Fahrplan.
- Kein `country`-Feld im Board — nur Stadt+Code, `country` bleibt hier leer.

Nur für die Flugziel-**Übersichtstabelle** gedacht (siehe
all_flights_routes.py), nicht für die gezielte Suche."""
import json
import logging
import os
import re
import threading
import time

import requests

from scraper import USER_AGENT  # keine eigene UA-Konstante duplizieren

log = logging.getLogger("tuiwatch.fraboard")

_URL = "https://www.airport-frankfurt-am-main.de/flugzeiten/abflug-fra.json"
_HEADERS = {
    "User-Agent": USER_AGENT, "Accept": "application/json",
    "Referer": "https://www.airport-frankfurt-am-main.de/abflug-flughafen-frankfurt-airport",
}
_DEST_RE = re.compile(r"^(.*)\s\(([A-Z]{3})\)$")

_REFRESH_INTERVAL = 6 * 3600   # wie oft neu abgerufen wird
ROLLING_DAYS = 9                # >= 7, damit auch woechentliche Verbindungen
                                 # sicher mindestens einmal auftauchen

_DATA = os.environ.get("TUIWATCH_DATA", "/data")
_STATE_PATH = _DATA + "/fra_board_destinations.json"

_lock = threading.Lock()
_seen: dict[str, dict] = {}     # code -> {"name": str, "last_seen": "YYYY-MM-DD"}
_loaded = False
_last_fetch_ts = 0.0


def _ensure_loaded():
    """Zustand einmalig von Platte laden (lazy — kein Datei-I/O beim reinen
    Import des Moduls, z. B. in Tests)."""
    global _loaded, _seen
    if _loaded:
        return
    _loaded = True
    try:
        with open(_STATE_PATH, encoding="utf-8") as f:
            _seen = json.load(f)
    except FileNotFoundError:
        _seen = {}
    except Exception as e:
        log.warning("FRA-Board-Zustand nicht lesbar (%s): %s", _STATE_PATH, e)
        _seen = {}


def _save():
    try:
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(_seen, f, ensure_ascii=False)
    except Exception as e:
        log.warning("FRA-Board-Zustand nicht speicherbar (%s): %s", _STATE_PATH, e)


def refresh(*, verbose: bool = False) -> bool:
    """Heutigen Abflugtag abrufen und ins rollierende Fenster einmischen.
    True bei Erfolg (auch ohne neue Ziele), False bei Abruffehler."""
    global _last_fetch_ts
    _ensure_loaded()
    try:
        resp = requests.get(_URL, headers=_HEADERS, timeout=20)
        if resp.status_code != 200:
            log.warning("FRA-Board HTTP %s", resp.status_code)
            return False
        data = resp.json()
    except Exception as e:
        log.warning("FRA-Board-Abruf fehlgeschlagen: %s", e)
        return False
    rows = data.get("data") or []
    today = time.strftime("%Y-%m-%d")
    cutoff = time.strftime("%Y-%m-%d", time.localtime(time.time() - ROLLING_DAYS * 86400))
    with _lock:
        for r in rows:
            m = _DEST_RE.match(str(r.get("2") or "").strip())
            if not m:
                continue
            name, code = m.group(1).strip(), m.group(2)
            # AIRail: Lufthansa verkauft Bahn-Zubringer (Aachen, Berlin, Basel,
            # Hamburg — live im Board gesehen) unter eigenem IATA-artigem Code
            # im selben Board wie echte Flüge. Keine "Flugziele", raus.
            if "bahnhof" in name.lower():
                continue
            _seen[code] = {"name": name or _seen.get(code, {}).get("name", code),
                          "last_seen": today}
        # Ziele, die laenger als ROLLING_DAYS nicht mehr im Board auftauchten,
        # raus (koennten eingestellt sein) — haelt das Fenster aktuell statt
        # nur wachsend.
        for code in [c for c, e in _seen.items() if e["last_seen"] < cutoff]:
            del _seen[code]
        _last_fetch_ts = time.time()
        _save()
    if verbose:
        log.info("FRA-Board: %d Ziele im %d-Tage-Fenster (heute %d Zeilen gesehen)",
                 len(_seen), ROLLING_DAYS, len(rows))
    return True


def ensure_fresh(*, verbose: bool = False) -> bool:
    _ensure_loaded()
    with _lock:
        fresh = _last_fetch_ts and (time.time() - _last_fetch_ts) < _REFRESH_INTERVAL
    if fresh:
        return True
    ok = refresh(verbose=verbose)
    return ok or bool(_seen)  # alter Stand ist besser als nichts (Fail-Soft)


def list_destinations(*, verbose: bool = False) -> list[dict] | None:
    """Ziele im rollierenden Fenster, alphabetisch nach Name. None, wenn noch
    nie erfolgreich geladen werden konnte."""
    if not ensure_fresh(verbose=verbose):
        return None
    with _lock:
        if not _seen:
            return None
        return sorted(
            ({"code": c, "name": e["name"], "country": ""} for c, e in _seen.items()),
            key=lambda d: d["name"])
