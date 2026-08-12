#!/usr/bin/env python3
"""Flugplan ab/nach München Airport (MUC) — aus dem Saison-PDF des Flughafens.

Dritter, wieder eigenständiger Flugplan neben [str_flights_client.py](str_flights_client.py)
(JSON-API, Saisonstrecken) und [fra_flights_client.py](fra_flights_client.py)
(JSON, Einzelflüge). München bietet **kein** brauchbares API: die Flugtafel der
Website deckt nur ein Live-Fenster von rund ±2 Tagen ab (live geprüft). Der
komplette Saisonflugplan steht dagegen als **PDF** auf `munich-airport.de/flugplan`
— mit demselben Datenmodell wie Stuttgart (Wochentagsraster + Gültigkeit von–bis).

Ablauf: PDF-Link von der Seite auflösen (der Pfad enthält einen Hash und kann sich
bei jeder Neuerzeugung ändern → niemals hart kodieren), PDF laden, mit pdfplumber
parsen (~15 s, ~3.300 Flugzeilen), Ergebnis im Speicher halten. Das PDF wird
**täglich neu erzeugt** (Feld „Datenstand"), der abgedeckte Zeitraum bleibt aber
die laufende Saison — deshalb wird mehrmals täglich nur geprüft, ob sich URL oder
Dateigröße geändert haben, und nur dann neu geparst. Details: SCRAPING_MUC.md.
"""
import logging
import re
import threading
import time

import requests

from scraper import USER_AGENT  # keine eigene UA-Konstante duplizieren

log = logging.getLogger("tuiwatch.mucflights")

PAGE_URL = "https://www.munich-airport.de/flugplan"
_BASE = "https://www.munich-airport.de"
_HEADERS = {"User-Agent": USER_AGENT}

# Wie oft geprüft wird, ob ein neues PDF hängt (URL/Größe). Der eigentliche
# Download+Parse passiert nur, wenn sich dabei etwas geändert hat.
CHECK_INTERVAL = 3 * 3600

_PDF_LINK_RE = re.compile(r'href="(/_b/[^"]+/flugplan\.pdf)"', re.I)
_DATENSTAND_RE = re.compile(r"Datenstand:\s*(\d{2}\.\d{2}\.\d{4})")
_SEASON_RE = re.compile(r"ZEITRAUM SAISON:\s*(\d{2}\.\d{2}\.\d{4})\s*BIS\s*(\d{2}\.\d{2}\.\d{4})",
                        re.I)

# Eine Flugzeile des PDF, z. B.
#   S DE 1508 05:55 08:05 12-456- PMI 13.08.26 20.10.26 1 Condor
#   S EY 128 22:30 + 06:20 1234567 AUH 01.09.26 22.09.26 1 Etihad Airways
#   L DL 130 - 17:25 08:25 1234567 ATL 13.08.26 01.09.26 1 Delta Air Lines
# L = Landung in MUC (Zeit 1 = ab Ziel, Zeit 2 = an MUC),
# S = Start ab MUC   (Zeit 1 = ab MUC,  Zeit 2 = an Ziel).
# Live gegen die Flugtafel des Flughafens verifiziert (DE 1508 am 13.08.:
# 05:55 ab MUC → 08:05 an PMI). `-`/`+` markieren Vor-/Folgetag, die optionale
# zweite Codegruppe hinter dem Ziel ist ein Zwischenstopp.
_ROW_RE = re.compile(
    r"^([LS]) ([A-Z0-9]{2,3}) ?(\d{1,4}[A-Z]?) (-\d?)? ?(\d{2}:\d{2}) (\+\d?)? ?(\d{2}:\d{2})"
    r" ([1-7-]{7}) ([A-Z]{3})(?: ([A-Z]{3}))? (\d{2}\.\d{2}\.\d{2}) (\d{2}\.\d{2}\.\d{2})"
    r" (\S+)(?: (.+))?$")

_WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")

_lock = threading.Lock()
_state: dict = {
    "url": "", "size": 0, "datenstand": "", "season": "",
    "rows": [], "checked_ts": 0, "parsed_ts": 0,
}


def _weekdays_short(pattern: str) -> str:
    """`12-456-` → `Mo, Di, Do, Fr, Sa` (dieselbe Darstellung wie beim STR-Plan)."""
    days = [_WEEKDAYS[i] for i, c in enumerate(pattern[:7]) if c != "-"]
    return ", ".join(days) if len(days) < 7 else "täglich"


def _de_date(short: str) -> str:
    """`13.08.26` → `2026-08-13` (ISO, damit sich Zeiträume vergleichen lassen)."""
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{2})$", short or "")
    return f"20{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""


def resolve_pdf_url(verbose: bool = False) -> str:
    """Aktuelle PDF-Adresse von der Flugplan-Seite. Leer bei Fehler."""
    try:
        resp = requests.get(PAGE_URL, headers=_HEADERS, timeout=20)
        if resp.status_code != 200:
            log.warning("MUC-Flugplan: Seite HTTP %s", resp.status_code)
            return ""
        m = _PDF_LINK_RE.search(resp.text)
        if not m:
            log.warning("MUC-Flugplan: kein PDF-Link auf %s gefunden", PAGE_URL)
            return ""
        url = _BASE + m.group(1)
        if verbose:
            log.info("MUC-Flugplan: PDF-Link %s", url)
        return url
    except Exception as e:
        log.warning("MUC-Flugplan: Seite nicht abrufbar: %s", e)
        return ""


def _pdf_size(url: str) -> int:
    """Dateigröße per HEAD — Änderungsmerkmal, da der Server weder `Last-Modified`
    noch `ETag` schickt (live geprüft)."""
    try:
        resp = requests.head(url, headers=_HEADERS, timeout=15, allow_redirects=True)
        return int(resp.headers.get("Content-Length") or 0)
    except Exception:
        return 0


def _airport_names(pdf) -> dict:
    """Ziel-Überschriften der Tabellenseiten: IATA → (Stadt, Land).

    Die Überschrift steht in einer Zeile, aber in zwei Spalten (Stadt links bei
    x≈54, Land rechts bei x≈360) — die Textextraktion mischt die Reihenfolge je
    Seite, deshalb über die x-Position des `(CODE)`-Tokens getrennt statt über
    die Wortfolge. **Nur Tabellenseiten** auswerten: das Inhaltsverzeichnis am
    Heftanfang listet dieselben Codes in umgekehrter Spaltenfolge (Land links,
    Stadt rechts) und würde sonst Stadt und Land vertauschen."""
    out: dict = {}
    for page in pdf.pages:
        text = page.extract_text() or ""
        if not any(l.strip().startswith(("L ", "S ")) for l in text.split("\n")):
            continue  # Deckblatt, Airline-Verzeichnis, Inhaltsverzeichnis
        lines: dict = {}
        for w in page.extract_words():
            lines.setdefault(round(w["top"]), []).append(w)
        for words in lines.values():
            code_w = next((w for w in words
                           if re.fullmatch(r"\([A-Z]{3}\)", w["text"])), None)
            if not code_w:
                continue
            code = code_w["text"][1:-1]
            city = " ".join(w["text"] for w in words if w["x0"] < code_w["x0"])
            country = " ".join(w["text"] for w in words if w["x0"] > code_w["x0"])
            if city and code not in out:
                out[code] = (city, country)
    return out


def parse_pdf(data: bytes, verbose: bool = False) -> dict:
    """PDF-Bytes → {datenstand, season, rows}. Reine Funktion (kein Netz)."""
    import pdfplumber  # lazy: nur beim Neuparsen nötig
    import io

    rows: list = []
    datenstand = season = ""
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        names = _airport_names(pdf)
        for page in pdf.pages:
            text = page.extract_text() or ""
            if not datenstand and (m := _DATENSTAND_RE.search(text)):
                datenstand = m.group(1)
            if not season and (m := _SEASON_RE.search(text)):
                season = f"{m.group(1)}–{m.group(2)}"
            for line in text.split("\n"):
                line = line.strip()
                if not line.startswith(("L ", "S ")):
                    continue
                m = _ROW_RE.match(line)
                if not m:
                    continue
                (ls, al, no, prev_day, t1, next_day, t2, days, dest, stop,
                 valid_from, valid_till, terminal, airline) = m.groups()
                city, country = names.get(dest, ("", ""))
                dep_from_muc = ls == "S"
                rows.append({
                    "direction": "departure" if dep_from_muc else "arrival",
                    "airline_code": al,
                    "airline_name": (airline or "").strip(),
                    "flight_no": f"{al} {no}",
                    "airport_code": dest,
                    "airport_name": city or dest,
                    "country": country,
                    # Zeiten immer aus MUC-Sicht benennen: bei S ist Zeit 1 der
                    # Abflug ab MUC, bei L ist Zeit 2 die Ankunft in MUC.
                    "departure": t1,
                    "arrival": t2,
                    "prev_day": bool(prev_day),
                    "next_day": bool(next_day),
                    "weekdays": days,
                    "weekdays_short": _weekdays_short(days),
                    "stop": stop or "",
                    "date_from": _de_date(valid_from),
                    "date_till": _de_date(valid_till),
                    "terminal": terminal,
                })
    if verbose:
        log.info("MUC-Flugplan: %d Flugzeilen geparst (Datenstand %s, Saison %s)",
                 len(rows), datenstand or "?", season or "?")
    return {"datenstand": datenstand, "season": season, "rows": rows}


def refresh(force: bool = False, verbose: bool = False) -> bool:
    """Prüft auf ein neues PDF und parst es bei Bedarf. True = Daten vorhanden.

    Geprüft wird nur URL + Dateigröße (billig, ein GET auf die Seite + ein HEAD);
    das teure Parsen (~15 s) läuft nur, wenn sich davon etwas geändert hat."""
    url = resolve_pdf_url(verbose=verbose)
    if not url:
        return bool(_state["rows"])
    size = _pdf_size(url)
    with _lock:
        unchanged = (url == _state["url"] and size == _state["size"]
                     and _state["rows"])
        if unchanged and not force:
            _state["checked_ts"] = int(time.time())
            if verbose:
                log.info("MUC-Flugplan: unverändert (Datenstand %s)",
                         _state["datenstand"] or "?")
            return True
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=60)
        if resp.status_code != 200:
            log.warning("MUC-Flugplan: PDF HTTP %s", resp.status_code)
            return bool(_state["rows"])
        parsed = parse_pdf(resp.content, verbose=verbose)
    except Exception as e:
        log.warning("MUC-Flugplan: PDF nicht verarbeitbar: %s", e)
        return bool(_state["rows"])
    if not parsed["rows"]:
        log.warning("MUC-Flugplan: PDF enthielt keine erkennbaren Flugzeilen — "
                    "Layout geändert? (siehe SCRAPING_MUC.md)")
        return bool(_state["rows"])
    now = int(time.time())
    with _lock:
        _state.update(url=url, size=size, datenstand=parsed["datenstand"],
                      season=parsed["season"], rows=parsed["rows"],
                      checked_ts=now, parsed_ts=now)
    log.info("MUC-Flugplan aktualisiert: %d Verbindungen, Datenstand %s",
             len(parsed["rows"]), parsed["datenstand"] or "?")
    return True


def ensure_plan(verbose: bool = False) -> bool:
    """Sorgt dafür, dass Daten da sind; prüft höchstens alle CHECK_INTERVAL."""
    with _lock:
        fresh = _state["rows"] and (time.time() - _state["checked_ts"]) < CHECK_INTERVAL
    if fresh:
        return True
    return refresh(verbose=verbose)


def status() -> dict:
    """Stand der Daten (für die Fußzeile im Fenster)."""
    with _lock:
        return {"datenstand": _state["datenstand"], "season": _state["season"],
                "count": len(_state["rows"]), "checked_ts": _state["checked_ts"],
                "parsed_ts": _state["parsed_ts"], "url": _state["url"]}


def search(query: str = "", direction: str = "", date_from: str = "",
           date_till: str = "", limit: int = 400, verbose: bool = False) -> dict | None:
    """Verbindungen filtern. None, wenn (noch) keine Daten geladen werden konnten.

    `query` sucht in Zielcode, Stadt und Land; `direction` ist `departure`
    (ab MUC), `arrival` (nach MUC) oder leer; `date_from`/`date_till` sind Monate
    (`YYYY-MM`) wie bei den anderen beiden Flugplänen und vergleichen gegen die
    Gültigkeitsspanne der Verbindung."""
    if not ensure_plan(verbose=verbose):
        return None
    q = (query or "").strip().lower()
    df = (date_from or "").strip()[:7]
    dt = (date_till or "").strip()[:7]
    with _lock:
        rows = list(_state["rows"])
    out = []
    for r in rows:
        if direction and r["direction"] != direction:
            continue
        if df and r["date_till"][:7] < df:
            continue
        if dt and r["date_from"][:7] > dt:
            continue
        if q and q not in " ".join((r["airport_code"], r["airport_name"],
                                    r["country"])).lower():
            continue
        out.append(r)
    out.sort(key=lambda r: (r["airport_name"], r["departure"], r["date_from"]))
    res = status()
    res["rows"] = out[:limit]
    res["total"] = len(out)
    return res
