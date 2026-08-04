#!/usr/bin/env python3
"""TUIWatch — Reisepreis-Tracker als Home-Assistant-Add-on.

Verfolgt den Preis konkreter TUI-Angebots-URLs über die Zeit: rendert die Seite
periodisch mit Headless-Chromium (siehe scraper.py), speichert jeden Messpunkt in
SQLite und zeigt Verlauf + Hoch/Runter-Anzeige in einer Weboberfläche.
"""
import csv
import hashlib
import io
import json
import logging
import os
import re
import secrets
import signal
import smtplib
import sqlite3
import threading
import time
import zipfile
from collections import defaultdict, deque
from datetime import date, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import anthropic
import requests as http
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from flask import (Flask, jsonify, make_response, redirect, render_template,
                   request, send_file, url_for)
from waitress import serve
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import safe_join

from scraper import (_giata_from_url, _valid_img_url, api_healthcheck,
                     build_destination_index,
                     duration_from_url, fetch_airlines, fetch_airports,
                     fetch_calendar, fetch_destinations, fetch_giata_image_urls,
                     fetch_hotel_image,
                     fetch_price, fetch_rooms, fetch_search, fetch_search_params,
                     hotel_from_url, is_single_room, region_giata_from_breadcrumb,
                     room_code_from_url, transfer_included_from_url, travellers_from_url,
                     with_duration, with_room_code, with_transfer_included, with_travellers,
                     without_room_code)
import check24_client
from aktionscodes import fetch_aktionscodes
from nextcloud import fetch_contacts
from packliste import PACKING_TEMPLATE, default_packing_rows
from tripparser import (_clean_text, _fmt_eur, _parse_eur, apply_derived_fields,
                        check_fields, extract_pdf_text, parse_tui_pdf, parse_tui_text)

logging.basicConfig(format='[%(levelname)s] [%(asctime)s] %(message)s',
                    level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S', force=True)
log = logging.getLogger(__name__)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# ── In-App Log-Buffer (für Konsole im UI) ──────────────────────────────────────
_log_buffer: deque = deque(maxlen=200)
# Warnungen/Fehler separat (fürs ⚠-Panel im UI): der INFO-lastige Hauptpuffer
# rotiert sie sonst schnell raus — stille Fehlpfade waren live mehrfach nur mit
# Log-Wühlen diagnostizierbar.
_warn_buffer: deque = deque(maxlen=100)


class _BufferHandler(logging.Handler):
    _fmt = logging.Formatter('[%(levelname)s] [%(asctime)s] %(message)s',
                             datefmt='%Y-%m-%d %H:%M:%S')

    def emit(self, record):
        try:
            entry = {'ts': int(record.created * 1000),
                     'level': record.levelname,
                     'msg': self._fmt.format(record)}
            _log_buffer.append(entry)
            if record.levelno >= logging.WARNING:
                _warn_buffer.append(entry)
        except Exception:
            pass


logging.getLogger().addHandler(_BufferHandler())

APP_VERSION = "0.61.1"  # muss mit config.yaml/version bei jedem Bump mitgezogen werden

# ── Pfade / Flask ──────────────────────────────────────────────────────────────
_BASE = os.environ.get('TUIWATCH_BASE', '/app')
_DATA = os.environ.get('TUIWATCH_DATA', '/data')
CONFIG_PATH = _DATA + '/options.json'
SESSIONS_PATH = _DATA + '/sessions.json'
DB_PATH = _DATA + '/tuiwatch.db'
TRIPS_DIR = _DATA + '/trips'   # dauerhaft gespeicherte Reise-PDFs

POLL_INTERVAL_DEFAULT = 21600  # 6h — Reisepreise ändern sich langsam
MIN_POLL_INTERVAL = 600        # nie öfter als alle 10 min (Bot-Schutz/Fairness)
HISTORY_ONLY_HOUR = 9   # fixer Tages-Slot für Preisverlauf-Angebote (lokale Zeit)
HISTORY_ONLY_SPREAD_MIN = 60  # Streuung in Minuten ab HISTORY_ONLY_HOUR (kein Burst um Punkt 9)
MAX_PDF_BYTES = 16 * 1024 * 1024  # 16 MB Upload-Limit für Reise-PDFs

app = Flask(__name__, template_folder=_BASE + '/templates',
            static_folder=_BASE + '/static')
app.config['MAX_CONTENT_LENGTH'] = MAX_PDF_BYTES


class _IngressMiddleware:
    """Setzt SCRIPT_NAME aus dem HA-Supervisor-Header, damit url_for() hinter
    dem Ingress-Proxy korrekte URLs erzeugt."""

    def __init__(self, wsgi_app):
        self._app = wsgi_app

    def __call__(self, environ, start_response):
        prefix = environ.get('HTTP_X_INGRESS_PATH', '').rstrip('/')
        if prefix:
            environ['SCRIPT_NAME'] = prefix
            path = environ.get('PATH_INFO', '')
            if path.startswith(prefix):
                environ['PATH_INFO'] = path[len(prefix):] or '/'
        return self._app(environ, start_response)


app.wsgi_app = _IngressMiddleware(ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1))

# ── State ──────────────────────────────────────────────────────────────────────
sessions: dict[str, float] = {}
_scrape_lock = threading.Lock()      # nur ein Chromium gleichzeitig
_checking: set[int] = set()          # offer_ids, die gerade geprüft werden
_checking_lock = threading.Lock()
_compare_state: dict[int, dict] = {}  # offer_id → transienter Status {running|error}
_compare_lock = threading.Lock()
_calendar_state: dict[int, dict] = {}  # offer_id → transienter Status {running|error}
_calendar_lock = threading.Lock()
_nights_state: dict[int, dict] = {}    # offer_id → transienter Status {running|error}
_nights_lock = threading.Lock()
_check24_state: dict[int, dict] = {}   # offer_id → transienter Status {running|error}
_check24_lock = threading.Lock()       # schützt _check24_state
_check24_scrape_lock = threading.Lock()  # serialisiert Check24-Abrufe (eigenes Chromium je Aufruf)
_aktion_state: dict = {}               # transienter Status des Aktionscode-Abrufs {running|error|ts}
_aktion_lock = threading.Lock()
_cheaper_notified: dict[int, str] = {}  # Dedup für Günstigerer-Termin-Alarm
_fail_notified: set[int] = set()        # offer_ids mit aktivem Ausverkauft-/Fehler-Alarm
ERROR_ALARM_STREAK = 3                   # ab so vielen Fehlversuchen in Folge melden
_health_state: dict = {}                 # letzter API-Selbsttest {ok, ts, checks, running}
_health_lock = threading.Lock()
_ai_summary_cache: dict = {}              # giata/Name → {summary, ts} — spart wiederholte API-Calls
_AI_SUMMARY_TTL = 24 * 3600
_booking_score_cache: dict = {}           # offer_id → {result, usage, ts}
_ai_cache_lock = threading.Lock()         # schützt _ai_summary_cache/_booking_score_cache — ohne Lock
                                           # können zwei parallele Requests (threaded=True) fürs gleiche
                                           # Angebot je einen bezahlten KI-Call auslösen statt Cache-Hit
_region_outlook_cache: dict = {}          # region → {result, usage, ts}
_calendar_outlook_cache: dict = {}        # offer_id → {summary, usage, ts}
_BOOKING_SCORE_TTL = 6 * 3600             # kürzer als Hotel-Fazit: Preisdaten ändern sich häufiger
_CALENDAR_FRESH_SECONDS = 7 * 86400       # Preiskalender für den Buchungsscore ab diesem Alter neu abrufen
_AI_MODELS = ('claude-opus-5', 'claude-sonnet-5', 'claude-haiku-4-5', 'claude-fable-5')
_GEMINI_MODELS = ('gemini-3.1-pro', 'gemini-3.6-flash', 'gemini-3.5-flash', 'gemini-2.5-flash')
_PERPLEXITY_MODELS = ('sonar', 'sonar-pro', 'sonar-reasoning-pro', 'sonar-deep-research')
_api_down_notified = False                # ob aktuell ein API-Ausfall gemeldet ist

# einfache Login-Drossel
_failed_attempts: dict[str, list[float]] = defaultdict(list)
_blocked_ips: dict[str, float] = {}
RATE_LIMIT_MAX, RATE_LIMIT_WINDOW, RATE_LIMIT_BLOCK = 5, 600, 900

# Cooldowns für scraping-lastige Routen (check-now/search/searches-check) — schützt
# TUIs Server vor wiederholtem Klicken/Skript-Aufrufen, die die eigene IP dort blocken
# könnten. Kein Fehlversuchs-Zähler wie oben, nur ein simpler Zeitstempel pro Key.
_route_cooldowns: dict[str, float] = {}


def _cooldown_remaining(key: str, seconds: int) -> int:
    """0 und setzt den Zeitstempel, wenn `key` zuletzt vor mehr als `seconds` ausgelöst
    wurde — sonst verbleibende Sekunden (>0), ohne den Zeitstempel zu berühren."""
    now = time.time()
    remaining = seconds - (now - _route_cooldowns.get(key, 0))
    if remaining > 0:
        return int(remaining) + 1
    _route_cooldowns[key] = now
    return 0


def _cooldown_peek(key: str, seconds: int) -> int:
    """Wie `_cooldown_remaining`, aber rein lesend — setzt/verändert den Zeitstempel
    nicht. Für den HA-Sensor, der den Cooldown nur anzeigen, nicht auslösen soll."""
    remaining = seconds - (time.time() - _route_cooldowns.get(key, 0))
    return int(remaining) + 1 if remaining > 0 else 0


def _push_cooldown_sensor() -> None:
    """Meldet HA einen Binär-Sensor: 'on', solange der globale 'Jetzt prüfen'-Cooldown
    (60s, `/api/check-now`) aktiv ist. Läuft per Timer, damit der Sensor auch beim
    Ablauf des Cooldowns von selbst auf 'off' geht, nicht erst beim nächsten Klick."""
    if not _ha_enabled():
        return
    remaining = _cooldown_peek('check_now', 60)
    attrs = {'friendly_name': 'TUIWatch Cooldown aktiv', 'icon': 'mdi:timer-sand',
             'retry_after': remaining}
    try:
        http.post(f'{HA_BASE}/states/binary_sensor.tuiwatch_cooldown_active',
                  headers={'Authorization': f'Bearer {SUPERVISOR_TOKEN}'}, timeout=10,
                  json={'state': 'on' if remaining else 'off', 'attributes': attrs})
    except Exception as e:
        log.warning("HA-Cooldown-Sensor aktualisieren fehlgeschlagen: %s", e)


# ── Config & Sessions ──────────────────────────────────────────────────────────

def load_config() -> dict:
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}   # normal vor dem ersten Schreiben durch den HA-Supervisor
    except Exception as e:
        log.warning("options.json nicht lesbar (%s): %s", CONFIG_PATH, e)
        return {}


def _verbose() -> bool:
    return bool(load_config().get('verbose_log', False))


def save_sessions() -> None:
    try:
        now = time.time()
        with open(SESSIONS_PATH, 'w') as f:
            json.dump({k: v for k, v in sessions.items() if v > now}, f)
    except Exception as e:
        log.warning("Sessions konnten nicht gespeichert werden: %s", e)


def load_sessions() -> None:
    global sessions
    try:
        with open(SESSIONS_PATH) as f:
            data = json.load(f)
        now = time.time()
        sessions = {k: v for k, v in data.items() if v > now}
    except FileNotFoundError:
        pass
    except Exception as e:
        log.warning("Sessions konnten nicht geladen werden: %s", e)


def create_session(hours: int) -> str:
    token = secrets.token_hex(32)
    sessions[token] = time.time() + hours * 3600
    save_sessions()
    return token


def is_valid_session(token: str | None) -> bool:
    if not token or token not in sessions:
        return False
    if time.time() > sessions[token]:
        del sessions[token]
        return False
    return True


def touch_session(token: str, hours: int) -> None:
    """Verlängert eine aktive Session bei Nutzung (sliding expiry) — sonst läuft
    sie exakt session_hours nach dem Login ab, auch bei durchgehender Nutzung
    (Ursache für unerwartete Logouts trotz aktivem Tab). Schreibt die
    Sessions-Datei nur, wenn seit der letzten Verlängerung schon >1h vergangen
    ist (spart Disk-I/O bei jedem Request)."""
    if token not in sessions:
        return
    new_exp = time.time() + hours * 3600
    if new_exp - sessions[token] > 3600:
        sessions[token] = new_exp
        save_sessions()


def get_client_ip(req) -> str:
    cf = req.headers.get('CF-Connecting-IP', '').strip()
    return cf or (req.remote_addr or 'unknown')


def is_rate_limited(ip: str) -> bool:
    now = time.time()
    if ip in _blocked_ips:
        if now < _blocked_ips[ip]:
            return True
        del _blocked_ips[ip]
    _failed_attempts[ip] = [t for t in _failed_attempts[ip] if now - t < RATE_LIMIT_WINDOW]
    return False


def record_failed_attempt(ip: str) -> None:
    now = time.time()
    _failed_attempts[ip] = [t for t in _failed_attempts[ip] if now - t < RATE_LIMIT_WINDOW]
    _failed_attempts[ip].append(now)
    if len(_failed_attempts[ip]) >= RATE_LIMIT_MAX:
        _blocked_ips[ip] = now + RATE_LIMIT_BLOCK
        log.warning("IP '%s' für %d min gesperrt (zu viele Fehlversuche)", ip, RATE_LIMIT_BLOCK // 60)


def clear_failed_attempts(ip: str) -> None:
    _failed_attempts.pop(ip, None)
    _blocked_ips.pop(ip, None)


def _json_loads_safe(text, default):
    """json.loads mit Fallback statt Crash — für Felder, die die App selbst per
    json.dumps geschrieben hat (also normalerweise valide sind), aber theoretisch
    durch DB-Korruption/manuelle Eingriffe kaputt sein könnten. Loggt eine Warnung,
    damit sowas nicht stillschweigend untergeht."""
    try:
        return json.loads(text)
    except (ValueError, TypeError) as e:
        log.warning("Kaputtes JSON in DB-Feld ignoriert: %s", e)
        return default


# ── Datenbank ──────────────────────────────────────────────────────────────────

def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    with db() as con:
        con.execute('''CREATE TABLE IF NOT EXISTS offers (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            url         TEXT UNIQUE NOT NULL,
            label       TEXT DEFAULT '',
            hotel       TEXT DEFAULT '',
            details     TEXT DEFAULT '',
            room        TEXT DEFAULT '',
            dep_airport TEXT DEFAULT '',
            flight_out  TEXT DEFAULT '',
            flight_ret  TEXT DEFAULT '',
            location    TEXT DEFAULT '',
            city        TEXT DEFAULT '',
            region      TEXT DEFAULT '',
            country     TEXT DEFAULT '',
            pdf_url     TEXT DEFAULT '',
            cancellation TEXT DEFAULT '',
            stars        REAL,
            rating       REAL,
            rating_count INTEGER,
            recommendation INTEGER,
            total_price  REAL,
            travellers_count INTEGER,
            paused       INTEGER DEFAULT 0,
            archived     INTEGER DEFAULT 0,
            history_only INTEGER DEFAULT 0,
            return_date  TEXT DEFAULT '',
            target_price REAL,
            board            TEXT DEFAULT '',
            check24_hotel_id TEXT DEFAULT '',
            check24_area_id  TEXT DEFAULT '',
            check24_link     TEXT DEFAULT '',
            notify_muted          INTEGER NOT NULL DEFAULT 0,
            notify_calendar_muted INTEGER NOT NULL DEFAULT 0,
            created     INTEGER NOT NULL
        )''')
        con.execute('''CREATE TABLE IF NOT EXISTS price_history (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            offer_id  INTEGER NOT NULL,
            ts        INTEGER NOT NULL,
            price     REAL,
            old_price REAL,
            discount  INTEGER,
            available INTEGER,
            ok        INTEGER NOT NULL DEFAULT 0,
            note      TEXT DEFAULT '',
            FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE CASCADE
        )''')
        con.execute('CREATE INDEX IF NOT EXISTS idx_hist_offer ON price_history(offer_id, ts)')
        # Globaler Markttrend: Preisänderungen je Check, bewusst NICHT an offer_id
        # gebunden (kein FK) — überlebt daher das Löschen des zugehörigen Angebots.
        con.execute('''CREATE TABLE IF NOT EXISTS price_moves (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ts         INTEGER NOT NULL,
            region     TEXT DEFAULT '',
            country    TEXT DEFAULT '',
            months_out INTEGER,
            pct_change REAL NOT NULL
        )''')
        con.execute('CREATE INDEX IF NOT EXISTS idx_moves_ts ON price_moves(ts)')
        con.execute('CREATE INDEX IF NOT EXISTS idx_moves_region ON price_moves(region, months_out, ts)')
        con.execute('''CREATE TABLE IF NOT EXISTS compare_cache (
            offer_id INTEGER PRIMARY KEY,
            ts       INTEGER NOT NULL,
            base     INTEGER,
            rows     TEXT NOT NULL DEFAULT '[]',
            FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE CASCADE
        )''')
        con.execute('''CREATE TABLE IF NOT EXISTS calendar_cache (
            offer_id INTEGER PRIMARY KEY,
            ts       INTEGER NOT NULL,
            data     TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE CASCADE
        )''')
        # Delta-codierte Preishistorie je Reisedatum (nicht je Angebots-Poll wie
        # price_history): eine Zeile nur wenn sich der Preis für dieses (offer_id,
        # travel_date) seit dem letzten Snapshot geändert hat, siehe
        # _store_calendar_snapshot() — sonst würde die Tabelle bei 400-700+ Tagen je
        # Kalender explodieren.
        con.execute('''CREATE TABLE IF NOT EXISTS calendar_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            offer_id    INTEGER NOT NULL,
            travel_date TEXT NOT NULL,
            ts          INTEGER NOT NULL,
            price       INTEGER NOT NULL,
            FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE CASCADE
        )''')
        con.execute('CREATE INDEX IF NOT EXISTS idx_calhist_offer_date '
                    'ON calendar_history(offer_id, travel_date, ts)')
        con.execute('''CREATE TABLE IF NOT EXISTS nights_cache (
            offer_id INTEGER PRIMARY KEY,
            ts       INTEGER NOT NULL,
            base     INTEGER,
            span     INTEGER,
            rows     TEXT NOT NULL DEFAULT '[]',
            FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE CASCADE
        )''')
        # Gecachtes Ergebnis des Check24-Preisvergleichs (siehe check24_client.py) —
        # ein Eintrag je Angebot, analog zu compare_cache/nights_cache.
        con.execute('''CREATE TABLE IF NOT EXISTS check24_cache (
            offer_id  INTEGER PRIMARY KEY,
            ts        INTEGER NOT NULL,
            query     TEXT NOT NULL DEFAULT '{}',
            tui_price REAL,
            rows      TEXT NOT NULL DEFAULT '[]',
            offer_url TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE CASCADE
        )''')
        c24cols = {r['name'] for r in con.execute('PRAGMA table_info(check24_cache)').fetchall()}
        if 'offer_url' not in c24cols:
            con.execute("ALTER TABLE check24_cache ADD COLUMN offer_url TEXT NOT NULL DEFAULT ''")
        # Merkt den zuletzt gemeldeten Günstigerer-Termin (Datum+Preis), damit der
        # Alarm Neustarts übersteht und nur bei einem WIRKLICH neuen Tiefstwert kommt.
        con.execute('''CREATE TABLE IF NOT EXISTS cheaper_state (
            offer_id INTEGER PRIMARY KEY,
            cdate    TEXT,
            cprice   REAL,
            ts       INTEGER NOT NULL,
            FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE CASCADE
        )''')
        # Merkt den zuletzt gemeldeten Tiefstwert unter dem gebuchten Preis (Dedup für
        # den „günstiger als gebucht"-Alarm, neustart-fest).
        con.execute('''CREATE TABLE IF NOT EXISTS booked_state (
            offer_id INTEGER PRIMARY KEY,
            price    REAL,
            ts       INTEGER NOT NULL,
            FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE CASCADE
        )''')
        # Ereignisse je Angebot (für Marker im Verlauf-Diagramm): Zimmerwechsel,
        # gebuchter Preis, Wunschpreis, Zurücksetzen …
        con.execute('''CREATE TABLE IF NOT EXISTS offer_events (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            offer_id INTEGER NOT NULL,
            ts       INTEGER NOT NULL,
            type     TEXT NOT NULL,
            text     TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE CASCADE
        )''')
        # Kleiner Schlüssel-Wert-Speicher (z. B. letzter Digest-Versand, ISO-Woche).
        con.execute('''CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        )''')
        # Gesehene TUI-Aktionscodes (Dedup für den „neuer Aktionscode"-Alarm, neustart-fest).
        # ckey = Art|Wert (z. B. "myTUI|300"); active=0, wenn die Aktion aktuell weg ist.
        con.execute('''CREATE TABLE IF NOT EXISTS aktionscode_state (
            ckey       TEXT PRIMARY KEY,
            code       TEXT,
            value      INTEGER,
            kind       TEXT,
            active     INTEGER NOT NULL DEFAULT 1,
            first_seen INTEGER NOT NULL,
            last_seen  INTEGER NOT NULL
        )''')
        # Gespeicherte Suchen (Favoriten) — in der DB statt im Browser, damit sie
        # geräteübergreifend verfügbar sind. payload = JSON der Sucheingaben.
        con.execute('''CREATE TABLE IF NOT EXISTS saved_searches (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            name    TEXT NOT NULL,
            payload TEXT NOT NULL DEFAULT '{}',
            ts      INTEGER NOT NULL,
            watch        INTEGER DEFAULT 0,
            max_price    REAL,
            last_checked INTEGER,
            seen         TEXT DEFAULT '{}',
            hits         TEXT DEFAULT '[]'
        )''')
        # Migration: Suchabo-Spalten in bestehenden DBs nachrüsten (watch = „diese Suche
        # beobachten", max_price = Schwellenpreis, seen = gemeldete Hotels {giata: preis},
        # hits = letzte Treffer unter der Schwelle fürs UI)
        scols = {r['name'] for r in con.execute('PRAGMA table_info(saved_searches)').fetchall()}
        if 'watch' not in scols:
            con.execute("ALTER TABLE saved_searches ADD COLUMN watch INTEGER DEFAULT 0")
        if 'max_price' not in scols:
            con.execute("ALTER TABLE saved_searches ADD COLUMN max_price REAL")
        if 'last_checked' not in scols:
            con.execute("ALTER TABLE saved_searches ADD COLUMN last_checked INTEGER")
        if 'seen' not in scols:
            con.execute("ALTER TABLE saved_searches ADD COLUMN seen TEXT DEFAULT '{}'")
        if 'hits' not in scols:
            con.execute("ALTER TABLE saved_searches ADD COLUMN hits TEXT DEFAULT '[]'")
        # Verlauf der KI-Fazits/-Vergleiche (dauerhaft, unabhängig vom 24h-Cache in
        # _ai_summary_cache) — damit frühere Analysen später wieder einsehbar sind.
        con.execute('''CREATE TABLE IF NOT EXISTS ai_analyses (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            kind    TEXT NOT NULL,
            title   TEXT NOT NULL,
            model   TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL,
            usage   TEXT DEFAULT '{}',
            ts      INTEGER NOT NULL
        )''')
        acols = {r['name'] for r in con.execute('PRAGMA table_info(ai_analyses)').fetchall()}
        if 'prompt' not in acols:
            con.execute("ALTER TABLE ai_analyses ADD COLUMN prompt TEXT NOT NULL DEFAULT ''")
        if 'offer_id' not in acols:
            # verknüpft Buchungsscores mit dem Angebot → Score-Verlauf je Angebot
            con.execute("ALTER TABLE ai_analyses ADD COLUMN offer_id INTEGER")
        if 'conversation' not in acols:
            # komplette Turn-Historie (JSON-Array [{role, content}, ...]) für
            # Folgefragen (siehe ai_routes.py::api_ai_history_followup) — leer bei
            # Einträgen ohne Folgefrage, wird dann aus prompt+summary rekonstruiert
            con.execute("ALTER TABLE ai_analyses ADD COLUMN conversation TEXT NOT NULL DEFAULT ''")
        # Reisen-Datenbank: gebuchte Reisen (PDF-Import). data = komplettes Parse-JSON,
        # pdf_name = Dateiname im TRIPS_DIR (dauerhaft gespeichert).
        con.execute('''CREATE TABLE IF NOT EXISTS trips (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_code  TEXT UNIQUE,
            booking_date  TEXT,
            title         TEXT,
            destination   TEXT,
            hotel         TEXT,
            hotel_code    TEXT,
            start_date    TEXT,
            end_date      TEXT,
            nights        INTEGER,
            travellers    INTEGER,
            total_price   REAL,
            package_price REAL,
            net_per_night REAL,
            meal          TEXT,
            data          TEXT NOT NULL DEFAULT '{}',
            pdf_name      TEXT,
            orig_name     TEXT,
            created       INTEGER NOT NULL
        )''')
        # Zusätzliche PDFs zu einer Reise (z. B. Reiseplan) — reine Ablage, kein Parsing.
        con.execute('''CREATE TABLE IF NOT EXISTS trip_attachments (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id     INTEGER NOT NULL,
            filename    TEXT NOT NULL,
            orig_name   TEXT NOT NULL,
            created     INTEGER NOT NULL
        )''')
        # Verlauf gesendeter Benachrichtigungen (HA/Telegram) — „kam die Meldung an?"
        # ohne HA-Log; wird auf die letzten 500 Einträge beschnitten.
        con.execute('''CREATE TABLE IF NOT EXISTS notify_log (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            ts      INTEGER NOT NULL,
            channel TEXT NOT NULL,
            title   TEXT,
            message TEXT,
            tag     TEXT,
            ok      INTEGER NOT NULL DEFAULT 1
        )''')
        # Packliste je Reise — Vorlage aus packliste.py wird beim ersten Öffnen einmalig
        # eingespielt (trips.packing_seeded), danach frei editierbar/löschbar/ergänzbar.
        # Reihenfolge ergibt sich aus der (monoton steigenden) id — keine separate
        # sort_order-Spalte nötig, seedet/hängt neue Items in Einfügereihenfolge an.
        con.execute('''CREATE TABLE IF NOT EXISTS trip_packing_items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id     INTEGER NOT NULL,
            category    TEXT NOT NULL,
            label       TEXT NOT NULL,
            checked     INTEGER NOT NULL DEFAULT 0,
            created     INTEGER NOT NULL
        )''')
        # Migration: net_per_night in bestehenden trips-Tabellen nachrüsten
        tcols = {r['name'] for r in con.execute('PRAGMA table_info(trips)').fetchall()}
        if 'net_per_night' not in tcols:
            con.execute("ALTER TABLE trips ADD COLUMN net_per_night REAL")
        if 'packing_seeded' not in tcols:
            con.execute("ALTER TABLE trips ADD COLUMN packing_seeded INTEGER DEFAULT 0")
        # Migration: fehlende Spalten in bestehenden DBs nachrüsten
        ocols = {r['name'] for r in con.execute('PRAGMA table_info(offers)').fetchall()}
        for col in ('hotel', 'details', 'room', 'dep_airport', 'flight_out',
                    'flight_ret', 'cancellation', 'location', 'city', 'region',
                    'country', 'pdf_url', 'return_date', 'image_url',
                    'booking_code', 'room_booking_code', 'tags', 'board',
                    'check24_hotel_id', 'check24_area_id', 'check24_link'):
            if col not in ocols:
                con.execute(f"ALTER TABLE offers ADD COLUMN {col} TEXT DEFAULT ''")
        for col in ('target_price', 'booked_price', 'stars', 'rating', 'total_price'):
            if col not in ocols:
                con.execute(f"ALTER TABLE offers ADD COLUMN {col} REAL")
        for col in ('rating_count', 'recommendation', 'travellers_count',
                    'paused', 'archived', 'history_only'):
            if col not in ocols:
                con.execute(f"ALTER TABLE offers ADD COLUMN {col} INTEGER")
        if 'calendar_seen_ts' not in ocols:
            con.execute("ALTER TABLE offers ADD COLUMN calendar_seen_ts INTEGER NOT NULL DEFAULT 0")
        if 'notify_muted' not in ocols:
            con.execute("ALTER TABLE offers ADD COLUMN notify_muted INTEGER NOT NULL DEFAULT 0")
        if 'notify_calendar_muted' not in ocols:
            con.execute("ALTER TABLE offers ADD COLUMN notify_calendar_muted INTEGER NOT NULL DEFAULT 0")
        hcols = {r['name'] for r in con.execute('PRAGMA table_info(price_history)').fetchall()}
        if 'available' not in hcols:
            con.execute("ALTER TABLE price_history ADD COLUMN available INTEGER")
        # Backfill: Hotelname aus der URL für Einträge ohne Namen
        for r in con.execute("SELECT id, url FROM offers WHERE hotel='' OR hotel IS NULL").fetchall():
            name = hotel_from_url(r['url'])
            if name:
                con.execute('UPDATE offers SET hotel=? WHERE id=?', (name, r['id']))
        # Einmaliger Backfill des Markttrends aus der vorhandenen Preishistorie (sonst
        # bräuchte der Trend erst wieder Tage/Wochen, um genug neue Datenpunkte zu sammeln)
        if not con.execute("SELECT 1 FROM meta WHERE key='price_moves_backfilled'").fetchone():
            _backfill_price_moves(con)
            con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('price_moves_backfilled','1')")
        # Warenkorb-Markttrend (tägliche Regionssuche) — Schema liegt im eigenen Modul,
        # das erst am Dateiende importiert wird; zur Laufzeit von init_db() ist es da.
        market_basket.init_basket_db(con)
    Path(TRIPS_DIR).mkdir(parents=True, exist_ok=True)
    log.info("Datenbank bereit: %s", DB_PATH)


def _last_two_prices(con, offer_id: int) -> list:
    rows = con.execute(
        'SELECT price FROM price_history WHERE offer_id=? AND ok=1 AND price IS NOT NULL '
        'ORDER BY ts DESC LIMIT 2', (offer_id,)).fetchall()
    return [r['price'] for r in rows]


def _trend_for(con, offer_id: int) -> dict | None:
    """Grobe Tendenz aus dem Preisverlauf: vergleicht den Mittelwert der älteren mit der
    jüngeren Hälfte der letzten Messpunkte. Rückgabe {dir:'up'|'down'|'flat', pct} oder
    None bei zu wenigen Daten (kein Hellsehen, nur ein Hinweis aus der eigenen History)."""
    rows = con.execute(
        'SELECT price FROM price_history WHERE offer_id=? AND ok=1 AND price IS NOT NULL '
        'ORDER BY ts DESC LIMIT 12', (offer_id,)).fetchall()
    prices = [r['price'] for r in rows][::-1]  # ältester → neuester
    if len(prices) < 4:
        return None
    half = len(prices) // 2
    old = prices[:half]
    new = prices[half:]
    a = sum(old) / len(old)
    b = sum(new) / len(new)
    if not a:
        return None
    pct = (b - a) / a * 100
    direction = 'down' if pct <= -2 else ('up' if pct >= 2 else 'flat')
    return {'dir': direction, 'pct': round(pct, 1)}


# ── Globaler Markttrend (destinationsübergreifend, überlebt Angebots-Löschung) ──
# Anders als `_trend_for` (ein Angebot, absolute Preise) wird hier die prozentuale
# Änderung JEDES Angebots zu seinem eigenen Vorpreis erfasst und in `price_moves`
# abgelegt (kein FK zu offers). So sind die Werte über verschiedene Hotels hinweg
# vergleichbar (ein 900€- und ein 3000€-Hotel verzerren sich nicht gegenseitig) und
# die Tabelle bleibt bestehen, wenn das erzeugende Angebot gelöscht wird.

MARKET_TREND_MIN_SAMPLES = 6
MARKET_TREND_DEFAULT_THRESHOLD = 1.0  # % kumulierte Bewegung im Fenster, ab der es nicht mehr "flat" ist


def _market_trend_threshold() -> float:
    """Schwelle (%) für den Markttrend, konfigurierbar über `market_trend_threshold`
    in den Add-on-Einstellungen (sonst Standardwert)."""
    try:
        return float(load_config().get('market_trend_threshold', MARKET_TREND_DEFAULT_THRESHOLD))
    except (TypeError, ValueError):
        return MARKET_TREND_DEFAULT_THRESHOLD


def _months_out(return_date: str, nights: int | None, ts: int) -> int | None:
    """Grobe Schätzung, wie viele Monate vor Abreise ein Check stattfand. Es gibt kein
    persistiertes Abreisedatum, daher: Abreise ≈ Rückreisedatum − Reisedauer (Dauer aus
    dem `duration=`-URL-Parameter). None, wenn `return_date`/`nights` fehlen, das Datum
    nicht parsebar ist, oder die Abreise schon in der Vergangenheit liegt."""
    if not return_date or not nights:
        return None
    try:
        ret = date.fromisoformat(return_date[:10])
    except ValueError:
        return None
    dep = ret - timedelta(days=nights)
    days = (dep - datetime.fromtimestamp(ts).date()).days
    if days < 0:
        return None
    return round(days / 30.44)


def _backfill_price_moves(con) -> None:
    """Einmaliger Backfill von `price_moves` aus der vorhandenen `price_history` beim
    ersten Start nach diesem Feature. Nutzt je Angebot dessen AKTUELLES region/country/
    return_date + Dauer als Näherung für alle historischen Punkte (pro Check wurden diese
    Werte bisher nicht mitgeschrieben) — für die meisten Angebote (feste Such-URL) eine
    brauchbare Annahme."""
    offers = con.execute('SELECT id, url, region, country, return_date FROM offers').fetchall()
    for o in offers:
        nights = duration_from_url(o['url'])
        rows = con.execute(
            'SELECT ts, price FROM price_history WHERE offer_id=? AND ok=1 AND price IS NOT NULL '
            'ORDER BY ts ASC', (o['id'],)).fetchall()
        room_change_ts = {r['ts'] for r in con.execute(
            "SELECT ts FROM offer_events WHERE offer_id=? AND type='room'", (o['id'],)).fetchall()}
        prev = None
        for r in rows:
            # Preisschritt über einen Zimmerwechsel hinweg ist kein Marktsignal, sondern
            # nur ein anderer Zimmertyp/-preis -> Zählung an dieser Stelle neu beginnen.
            # `>=` statt `>` an der unteren Grenze: ts ist nur sekundengenau, ein
            # schneller Zimmerwechsel kann dieselbe Sekunde wie der vorherige Check haben.
            room_changed = prev and any(prev['ts'] <= rc <= r['ts'] for rc in room_change_ts)
            if prev and prev['price'] and not room_changed:
                pct = (r['price'] - prev['price']) / prev['price'] * 100
                months_out = _months_out(o['return_date'], nights, r['ts'])
                con.execute(
                    'INSERT INTO price_moves (ts, region, country, months_out, pct_change) '
                    'VALUES (?,?,?,?,?)',
                    (r['ts'], o['region'] or '', o['country'] or '', months_out, pct))
            prev = r


def _compound_pct(values: list) -> float:
    """Kumulierte %-Bewegung (Zinseszins-Verkettung) statt Mittelwert — sonst verwässern
    viele 0%-Checks (Preis unverändert seit letztem Poll) einen echten, aber seltenen
    Anstieg im Schnitt fast auf null."""
    c = 1.0
    for p in values:
        c *= (1 + p / 100)
    return (c - 1) * 100


def _market_moves_query(region: str | None, months_out: int | None,
                         cutoff: int | None = None) -> tuple[str, list]:
    """Fester Query-Text (keine laufzeitabhängige String-Verkettung — CodeQL stuft
    dynamisch aus Bedingungen zusammengesetzte SQL-Strings pauschal als riskant ein,
    selbst wenn nur Werte parametrisiert werden). Jeder Filter ist ein `(? IS NULL OR
    spalte=?)`-Paar; nicht gesetzte Filter (`None`) sind dadurch automatisch No-ops,
    ohne die Query je nach Aufrufer unterschiedlich zusammenzubauen."""
    q = ('SELECT ts, pct_change FROM price_moves '
         'WHERE (? IS NULL OR ts>=?) AND (? IS NULL OR region=?) '
         'AND (? IS NULL OR months_out=?) ORDER BY ts ASC')
    params = [cutoff, cutoff, region, region, months_out, months_out]
    return q, params


def _market_trend(con, *, region: str | None = None, months_out: int | None = None,
                   window_days: int = 14) -> dict | None:
    """Marktweiter Preistrend über alle geprüften Angebote (optional nach Destination/
    Vorlaufzeit gefiltert), aus den in `price_moves` gesammelten Prozent-Änderungen der
    letzten `window_days` Tage. None bei zu wenigen Datenpunkten (kein Hellsehen)."""
    cutoff = int(time.time()) - window_days * 86400
    q, params = _market_moves_query(region, months_out, cutoff)
    rows = con.execute(q, params).fetchall()
    if len(rows) < MARKET_TREND_MIN_SAMPLES:
        return None
    deadband = _market_trend_threshold()
    cum_pct = _compound_pct([r['pct_change'] for r in rows])
    direction = ('down' if cum_pct <= -deadband
                 else ('up' if cum_pct >= deadband else 'flat'))
    # Tages-Streak: aufeinanderfolgende jüngste Tage, deren KUMULIERTE Tagesbewegung
    # noch zur Gesamtrichtung passt (bzw. bei 'flat' nahe Null bleibt)
    by_day: dict[str, list] = defaultdict(list)
    for r in rows:
        day = datetime.fromtimestamp(r['ts']).strftime('%Y-%m-%d')
        by_day[day].append(r['pct_change'])
    days_sorted = sorted(by_day)
    streak = 0
    for day in reversed(days_sorted):
        day_pct = _compound_pct(by_day[day])
        same_sign = ((direction == 'up' and day_pct > 0)
                     or (direction == 'down' and day_pct < 0)
                     or (direction == 'flat' and abs(day_pct) < deadband))
        if not same_sign:
            break
        streak += 1
    return {'dir': direction, 'pct': round(cum_pct, 1), 'days': streak, 'n': len(rows)}


def _market_index(con, *, region: str | None = None,
                   months_out: int | None = None) -> dict | None:
    """Preisindex seit Beginn der Aufzeichnung (Basis 100) — im Unterschied zu
    `_market_trend` kein rollierendes Zeitfenster, sondern die komplette Historie.
    Fängt langsame Bewegungen ab, die außerhalb eines 14-Tage-Fensters liegen (z. B.
    ein Anstieg über mehrere Wochen mit ruhigen Phasen dazwischen). None bei zu
    wenigen Datenpunkten."""
    q, params = _market_moves_query(region, months_out)
    rows = con.execute(q, params).fetchall()
    if len(rows) < MARKET_TREND_MIN_SAMPLES:
        return None
    pct = _compound_pct([r['pct_change'] for r in rows])
    return {'index': round(100 + pct, 1), 'pct': round(pct, 1),
            'since': rows[0]['ts'], 'n': len(rows)}


# ── Home-Assistant-Sensoren ────────────────────────────────────────────────────

SUPERVISOR_TOKEN = os.environ.get('SUPERVISOR_TOKEN', '')
HA_BASE = 'http://supervisor/core/api'


def _ha_enabled() -> bool:
    return bool(SUPERVISOR_TOKEN) and bool(load_config().get('ha_sensors', True))


def _slug(s: str) -> str:
    s = (s or '').lower()
    s = (s.replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue')
          .replace('ß', 'ss'))
    s = re.sub(r'[^a-z0-9]+', '_', s).strip('_')
    return s or 'angebot'


def _entity_ids() -> dict[int, str]:
    """offer_id → entity_id: sensor.tuiwatch_<hotelslug>, bei gleichem Hotel _2/_3 …"""
    with db() as con:
        offers = con.execute('SELECT id, hotel, url FROM offers ORDER BY id').fetchall()
    counts: dict[str, int] = {}
    mapping: dict[int, str] = {}
    for o in offers:
        base = 'tuiwatch_' + _slug(o['hotel'] or hotel_from_url(o['url']) or f"angebot_{o['id']}")
        counts[base] = counts.get(base, 0) + 1
        n = counts[base]
        mapping[o['id']] = 'sensor.' + (base if n == 1 else f'{base}_{n}')
    return mapping


def push_ha_sensors() -> None:
    """Meldet je Angebot einen Sensor an HA: Wert=Preis (€) bzw. 'unknown' (kein
    Preis ermittelbar — 'unavailable' wäre in HA-Konvention für einen kaputten/
    nicht erreichbaren Sensor reserviert, hier ist der Sensor selbst ja da),
    Attribut 'description' = Reise-Eckdaten. Räumt verwaiste Sensoren auf."""
    if not _ha_enabled():
        return
    headers = {'Authorization': f'Bearer {SUPERVISOR_TOKEN}'}
    mapping = _entity_ids()
    try:
        with db() as con:
            for oid, eid in mapping.items():
                o = con.execute('SELECT * FROM offers WHERE id=?', (oid,)).fetchone()
                last = con.execute('SELECT * FROM price_history WHERE offer_id=? '
                                   'ORDER BY ts DESC LIMIT 1', (oid,)).fetchone()
                stats = con.execute(
                    'SELECT MIN(price) mn, MAX(price) mx, AVG(price) av '
                    'FROM price_history WHERE offer_id=? AND ok=1 AND price IS NOT NULL',
                    (oid,)).fetchone()
                ok = bool(last and last['ok'] and last['price'] is not None)
                state = int(round(last['price'])) if ok else 'unknown'
                attrs = {
                    'friendly_name': o['label'] or o['hotel'] or f'TUI-Angebot #{oid}',
                    'icon': 'mdi:airplane-clock',
                    'description': o['details'] or '',
                    'hotel': o['hotel'] or '',
                    'room': o['room'] or '',
                    'departure_airport': o['dep_airport'] or '',
                    'flight_outbound': o['flight_out'] or '',
                    'flight_return': o['flight_ret'] or '',
                    'url': o['url'],
                }
                if o['location']:
                    attrs['location'] = o['location']
                    attrs['region'] = o['region'] or ''
                    attrs['country'] = o['country'] or ''
                if o['pdf_url']:
                    attrs['hotel_pdf'] = o['pdf_url']
                if o['total_price'] is not None:
                    attrs['total_price'] = int(round(o['total_price']))
                if o['travellers_count']:
                    attrs['travellers'] = o['travellers_count']
                if o['cancellation']:
                    attrs['cancellation'] = o['cancellation']
                if o['stars'] is not None:
                    attrs['stars'] = o['stars']
                if o['rating'] is not None:
                    attrs['rating'] = o['rating']
                    attrs['rating_count'] = o['rating_count']
                    attrs['recommendation'] = o['recommendation']
                if last and last['available'] is not None:
                    attrs['available'] = bool(last['available'])
                if o['target_price']:
                    attrs['target_price'] = int(round(o['target_price']))
                if o['booked_price']:
                    attrs['booked_price'] = int(round(o['booked_price']))
                    if ok and last['price'] is not None:
                        attrs['booked_diff'] = int(round(last['price'] - o['booked_price']))
                if o['image_url']:
                    attrs['image'] = o['image_url']
                if o['booking_code']:
                    attrs['booking_code'] = o['booking_code']
                if o['room_booking_code']:
                    attrs['room_booking_code'] = o['room_booking_code']
                if ok:
                    attrs['unit_of_measurement'] = '€'
                    if last['old_price']:
                        attrs['old_price'] = int(round(last['old_price']))
                    if last['discount']:
                        attrs['discount'] = last['discount']
                    if stats and stats['mn'] is not None:
                        attrs['min_price'] = int(round(stats['mn']))
                        attrs['max_price'] = int(round(stats['mx']))
                        attrs['avg_price'] = int(round(stats['av']))
                        s30 = con.execute(
                            'SELECT AVG(price) av, COUNT(*) c FROM price_history '
                            'WHERE offer_id=? AND ok=1 AND price IS NOT NULL AND ts>=?',
                            (oid, int(time.time()) - 30 * 86400)).fetchone()
                        if s30['c'] >= 2 and s30['av']:
                            attrs['avg_price_30d'] = int(round(s30['av']))
                if last and last['ts']:
                    attrs['last_checked'] = datetime.fromtimestamp(last['ts']).isoformat()
                http.post(f'{HA_BASE}/states/{eid}', headers=headers, timeout=10,
                          json={'state': state, 'attributes': attrs})
        # Übersichts-Sensor (günstigstes Angebot, Anzahl unter Wunschpreis …)
        summary_eid = 'sensor.tuiwatch_uebersicht'
        ov = _collect_offers()
        active = [o for o in ov if not o.get('archived')]
        ok_offers = [o for o in active if o.get('ok') and o.get('price') is not None]
        s_attrs = {'friendly_name': 'TUIWatch Übersicht', 'icon': 'mdi:airplane-clock',
                   'total_offers': len(active),
                   'archived_offers': sum(1 for o in ov if o.get('archived')),
                   'paused_offers': sum(1 for o in active if o.get('paused'))}
        if ok_offers:
            cheapest = min(ok_offers, key=lambda o: o['price'])
            s_attrs['unit_of_measurement'] = '€'
            s_attrs['cheapest_offer'] = cheapest.get('label') or cheapest.get('hotel') or ''
            s_attrs['cheapest_price'] = int(round(cheapest['price']))
            s_attrs['cheapest_location'] = cheapest.get('location') or ''
            s_attrs['offers_below_target'] = sum(
                1 for o in ok_offers if o.get('target_price') and o['price'] <= o['target_price'])
            s_state = int(round(cheapest['price']))
        else:
            s_state = 'unknown'
        http.post(f'{HA_BASE}/states/{summary_eid}', headers=headers, timeout=10,
                  json={'state': s_state, 'attributes': s_attrs})

        # Verwaiste tuiwatch-Sensoren entfernen (z. B. nach Löschen/Umbenennen)
        valid = set(mapping.values()) | {summary_eid}
        states = http.get(f'{HA_BASE}/states', headers=headers, timeout=10).json()
        for st in states:
            ent = st.get('entity_id', '')
            if ent.startswith('sensor.tuiwatch_') and ent not in valid:
                http.delete(f'{HA_BASE}/states/{ent}', headers=headers, timeout=10)
    except Exception as e:
        log.warning("HA-Sensoren aktualisieren fehlgeschlagen: %s", e)


# ── Benachrichtigungen (HA + Telegram) ─────────────────────────────────────────

def _log_notification(channel: str, title: str, message: str, tag: str, ok: bool) -> None:
    """Protokolliert eine gesendete (oder fehlgeschlagene) Benachrichtigung im
    Verlauf (notify_log) fürs 🔔-Panel im UI. Behält die letzten 500 Einträge."""
    try:
        with db() as con:
            con.execute('INSERT INTO notify_log (ts, channel, title, message, tag, ok) '
                        'VALUES (?,?,?,?,?,?)',
                        (int(time.time()), channel, title, message, tag, 1 if ok else 0))
            con.execute('DELETE FROM notify_log WHERE id NOT IN '
                        '(SELECT id FROM notify_log ORDER BY id DESC LIMIT 500)')
    except Exception as e:
        log.warning("notify_log nicht beschreibbar: %s", e)


def _notify_ha(title: str, message: str, tag: str, muted: bool = False) -> None:
    """`muted=True` (Angebot/Kalender stummgeschaltet) überspringt den eigentlichen
    HA-Versand, protokolliert die Meldung aber trotzdem in notify_log — das
    🔔-Panel im UI soll Preisänderungen unabhängig von der Stummschaltung zeigen."""
    if muted:
        _log_notification('ha', title, message, tag, True)
        return
    if not (SUPERVISOR_TOKEN and load_config().get('notify_ha', True)):
        return
    ok = True
    try:
        http.post(f'{HA_BASE}/services/persistent_notification/create',
                  headers={'Authorization': f'Bearer {SUPERVISOR_TOKEN}'}, timeout=10,
                  json={'title': title, 'message': message, 'notification_id': f'tuiwatch_{tag}'})
    except Exception as e:
        ok = False
        log.error("HA-Benachrichtigung fehlgeschlagen: %s", e)
    _log_notification('ha', title, message, tag, ok)


def _notify_telegram(text: str, muted: bool = False) -> None:
    """Siehe _notify_ha — `muted=True` protokolliert nur, sendet aber nicht."""
    if muted:
        _log_notification('telegram', '', text, '', True)
        return
    cfg = load_config()
    token = (cfg.get('telegram_bot_token') or '').strip()
    chat = (cfg.get('telegram_chat_id') or '').strip()
    if not (token and chat):
        return
    ok = True
    try:
        http.post(f'https://api.telegram.org/bot{token}/sendMessage', timeout=10,
                  json={'chat_id': chat, 'text': text, 'parse_mode': 'HTML',
                        'disable_web_page_preview': True})
    except Exception as e:
        ok = False
        log.error("Telegram-Benachrichtigung fehlgeschlagen: %s", e)
    _log_notification('telegram', '', text, '', ok)


def _eur(v) -> str:
    try:
        return f"{int(round(v)):,}".replace(',', '.') + ' €'
    except Exception:
        return '–'


# ── E-Mail (SMTP, Muster wie MyPage) ────────────────────────────────────────────

def smtp_configured() -> bool:
    return bool((load_config().get('smtp_host') or '').strip())


def nc_configured() -> bool:
    cfg = load_config()
    return bool((cfg.get('nc_addressbook_url') or '').strip()
                and (cfg.get('nc_user') or '').strip())


def send_email(subject: str, html_body: str, to: str) -> None:
    """Verschickt eine HTML-Mail. Wirft bei Fehler (Aufrufer fängt ab)."""
    cfg = load_config()
    host = (cfg.get('smtp_host') or '').strip()
    port = int(cfg.get('smtp_port') or 587)
    user = (cfg.get('smtp_user') or '').strip()
    password = (cfg.get('smtp_password') or '').strip()
    use_tls = bool(cfg.get('smtp_tls', True))
    sender = (cfg.get('smtp_from') or user or f'tuiwatch@{host}').strip()
    to = (to or '').strip()
    if not host:
        raise RuntimeError('SMTP nicht konfiguriert')
    if not to:
        raise RuntimeError('Kein Empfänger')
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = to
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))
    if use_tls:
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.ehlo(); s.starttls(); s.ehlo()
            if user and password:
                s.login(user, password)
            s.sendmail(sender, [to], msg.as_string())
    else:
        with smtplib.SMTP_SSL(host, port, timeout=20) as s:
            if user and password:
                s.login(user, password)
            s.sendmail(sender, [to], msg.as_string())
    log.info("E-Mail an %s gesendet (%s)", to, sender)


def _email_html_offers(offers: list[dict]) -> str:
    """Baut eine optisch ansprechende HTML-Mail mit allen Angeboten (Inline-Styles)."""
    def esc(s):
        return (str(s or '')).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    cards = []
    for o in offers:
        price = _eur(o['price']) if o.get('price') is not None else '–'
        stars = '★' * int(round(o['stars'])) if o.get('stars') else ''
        # Delta
        delta = ''
        if o.get('delta') is not None and o['delta'] != 0:
            up = o['delta'] > 0
            delta = (f'<span style="color:{"#cf222e" if up else "#1a7f37"};font-weight:700">'
                     f'{"▲ +" if up else "▼ "}{_eur(abs(o["delta"]))}</span>')
        sub = []
        if o.get('old_price') and o.get('price') and o['old_price'] > o['price']:
            sub.append(f'<span style="text-decoration:line-through;color:#888">{_eur(o["old_price"])}</span>'
                       + (f' −{o["discount"]}%' if o.get('discount') else ''))
        rating_html = ''
        if o.get('rating') is not None:
            rating = (f'HolidayCheck {str(o["rating"]).replace(".", ",")}/6'
                      + (f' · {o["recommendation"]}%' if o.get('recommendation') is not None else ''))
            hc_q = quote(f"site:holidaycheck.de {o.get('hotel') or o.get('label') or ''} "
                         f"{o.get('region') or o.get('country') or ''}".strip())
            rating_html = (f'<a href="https://www.google.com/search?q={hc_q}" '
                           f'style="color:#777;text-decoration:none">{esc(rating)} ↗</a>')
        flights = ''
        if o.get('flight_out') or o.get('flight_ret'):
            fl = []
            if o.get('flight_out'):
                fl.append(f'<div>✈ <b>Hin:</b> {esc(o["flight_out"])}</div>')
            if o.get('flight_ret'):
                fl.append(f'<div>✈ <b>Rück:</b> {esc(o["flight_ret"])}</div>')
            flights = (f'<div style="font-size:13px;color:#444;margin-top:6px">'
                       f'{"".join(fl)}</div>')
        total = ''
        if o.get('travellers_count') and o['travellers_count'] > 1 and o.get('total_price'):
            total = f'<div style="font-size:13px;color:#444">Gesamt {_eur(o["total_price"])} · {o["travellers_count"]} Reisende</div>'
        avail = ''
        if o.get('available') is True:
            avail = '<span style="color:#1a7f37;font-weight:600">✓ verfügbar</span>'
        elif o.get('available') is False:
            avail = '<span style="color:#cf222e;font-weight:600">✗ nicht verfügbar</span>'
        canc = f' · {esc(o["cancellation"])}' if o.get('cancellation') else ''
        codeparts = []
        if o.get('booking_code'):
            codeparts.append(f'Buchungscode <b>{esc(o["booking_code"])}</b>')
        if o.get('room_booking_code'):
            codeparts.append(f'Zimmer {esc(o["room_booking_code"])}')
        if o.get('giata'):
            giata_url = ('https://hg15.giatamedia.com/index2.php?uid=782&com=sc&gid='
                         f'{esc(o["giata"])}&frame=0&from=ks&catlang[]=de')
            codeparts.append(f'<a href="{giata_url}" style="color:#0b65d8;text-decoration:none">'
                              f'GIATA {esc(o["giata"])} ↗</a>')
        codes = ' · '.join(codeparts)
        title = esc(o.get('label') or o.get('hotel') or f"Angebot #{o['id']}")
        links = (f'<a href="{esc(o["url"])}" style="color:#0b65d8;text-decoration:none;font-weight:600">'
                 f'Auf tui.com ansehen ↗</a>')
        if o.get('pdf_url'):
            links += (f' &nbsp;·&nbsp; <a href="{esc(o["pdf_url"])}" '
                      f'style="color:#0b65d8;text-decoration:none">Hotel-PDF</a>')
        cards.append(
            '<tr><td style="padding:0 0 14px">'
            '<table width="100%" cellpadding="0" cellspacing="0" style="background:#fff;'
            'border:1px solid #e2e6ea;border-radius:10px;border-collapse:separate">'
            '<tr><td style="padding:14px 16px">'
            f'<div style="font-size:17px;font-weight:700;color:#10243e">{title} '
            f'<span style="color:#d29922">{stars}</span></div>'
            + (f'<div style="font-size:13px;color:#0b65d8">📍 {esc(o["location"])}</div>' if o.get('location') else '')
            + (f'<div style="font-size:13px;color:#555;margin-top:3px">{esc(o["details"])}</div>' if o.get('details') else '')
            + (f'<div style="font-size:12px;color:#777;margin-top:3px">{rating_html}</div>' if rating_html else '')
            + flights
            + '<div style="margin-top:10px">'
            f'<span style="font-size:24px;font-weight:800;color:#10243e">{price}</span>'
            ' <span style="font-size:12px;color:#777">pro Person</span> '
            f'&nbsp;{delta}</div>'
            + (f'<div style="font-size:13px;color:#777">{"".join(sub)}</div>' if sub else '')
            + total
            + (f'<div style="font-size:13px;margin-top:6px">{avail}{canc}</div>' if (avail or canc) else '')
            + (f'<div style="font-size:12px;color:#777;margin-top:6px">🧾 {codes}</div>' if codes else '')
            + f'<div style="margin-top:10px;font-size:14px">{links}</div>'
            '</td></tr></table></td></tr>'
        )
    now = datetime.now().strftime('%d.%m.%Y %H:%M')
    return (
        '<div style="background:#eef2f8;padding:20px 0;font-family:-apple-system,Segoe UI,Roboto,sans-serif">'
        '<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">'
        '<table width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%">'
        '<tr><td style="padding:0 16px 16px">'
        '<div style="font-size:22px;font-weight:800;color:#0b65d8">✈ TUIWatch</div>'
        f'<div style="font-size:13px;color:#666">Deine verfolgten Reisepreise · Stand {now}</div>'
        '</td></tr>'
        f'<tr><td style="padding:0 16px"><table width="100%" cellpadding="0" cellspacing="0">{"".join(cards)}</table></td></tr>'
        '<tr><td style="padding:10px 16px 0;font-size:11px;color:#99a">Generiert von '
        '<a href="https://github.com/LuckyTriple7/HA-AddOns" style="color:#0b65d8;text-decoration:none">TUIWatch</a>'
        ', einer App für Home Assistant · '
        '<a href="https://github.com/LuckyTriple7/HA-AddOns" style="color:#0b65d8;text-decoration:none">github.com/LuckyTriple7/HA-AddOns</a>'
        '</td></tr>'
        '</table></td></tr></table></div>'
    )


def _notify_startup() -> None:
    """Kurze Telegram-Statusmeldung beim Start (nur wenn Telegram konfiguriert ist)."""
    cfg = load_config()
    if not ((cfg.get('telegram_bot_token') or '').strip()
            and (cfg.get('telegram_chat_id') or '').strip()):
        return
    try:
        with db() as con:
            n = con.execute('SELECT COUNT(*) c FROM offers').fetchone()['c']
    except Exception as e:
        log.warning("Startup-Meldung: Angebotszahl nicht lesbar: %s", e)
        n = 0
    word = 'Reise' if n == 1 else 'Reisen'
    _notify_telegram(f"✈️ <b>TUIWatch gestartet</b> (v{APP_VERSION})\n{n} {word} geladen")


def _maybe_notify(offer: dict, prev_price: float | None, new_price: float | None,
                  target: float | None) -> None:
    """Schickt Benachrichtigungen bei Preisänderung und erreichtem Wunschpreis."""
    if new_price is None:
        return
    cfg = load_config()
    name = offer.get('label') or offer.get('hotel') or f"Angebot #{offer['id']}"
    url = offer.get('url', '')
    muted = bool(offer.get('notify_muted'))

    # 1) Wunschpreis erreicht (nur beim Übergang über die Schwelle)
    if target and new_price <= target and (prev_price is None or prev_price > target):
        title = f"🎯 Wunschpreis erreicht: {name}"
        msg = f"{name}\nWunschpreis {_eur(target)} erreicht — jetzt {_eur(new_price)}\n{url}"
        log.info("🎯 Wunschpreis erreicht (#%d %s): %s ≤ %s → Benachrichtigung",
                 offer['id'], name, _eur(new_price), _eur(target))
        _notify_ha(title, msg, f"target_{offer['id']}", muted=muted)
        _notify_telegram(f"🎯 <b>Wunschpreis erreicht</b>\n{name}\nJetzt <b>{_eur(new_price)}</b> "
                         f"(Ziel {_eur(target)})\n{url}", muted=muted)
        return  # nicht zusätzlich die Änderungsmeldung senden

    # 2) Preisänderung
    if cfg.get('notify_price_change', True) and prev_price is not None and new_price != prev_price:
        diff = new_price - prev_price
        if diff < 0:
            title = f"📉 Preis gefallen: {name}"
            arrow = f"▼ {_eur(abs(diff))}"
        else:
            title = f"📈 Preis gestiegen: {name}"
            arrow = f"▲ {_eur(diff)}"
        msg = f"{name}\n{_eur(prev_price)} → {_eur(new_price)} ({arrow})\n{url}"
        log.info("Benachrichtigung (#%d %s): %s → %s gesendet", offer['id'], name,
                 _eur(prev_price), _eur(new_price))
        _notify_ha(title, msg, f"change_{offer['id']}", muted=muted)
        _notify_telegram(f"{'📉' if diff<0 else '📈'} <b>{name}</b>\n"
                         f"{_eur(prev_price)} → <b>{_eur(new_price)}</b> ({arrow})\n{url}", muted=muted)


def _check_cheaper_date(offer: dict, current_price: float,
                        force_refresh: bool = False, notify: bool = True) -> None:
    """Meldet, wenn ein anderer Abreisetag deutlich günstiger ist als der getrackte
    Preis. Nutzt für den Kalender-Abruf dieselbe TTL wie der Buchungsscore-Pfad
    (_CALENDAR_FRESH_SECONDS, ~7 Tage): ist der Cache noch frisch, wird NICHT neu
    abgerufen (bis zu 6 teure HTTP-Requests je Check), sondern der vorhandene
    Snapshot aus calendar_cache für die Benachrichtigungslogik weiterverwendet — die
    'günstigerer Termin'-Prüfung bleibt dadurch bei JEDEM Preis-Check aktiv, nur der
    teure Kalender-Abruf selbst wird gedrosselt.

    `force_refresh=True` ignoriert die TTL und holt den Kalender immer frisch (für
    history_only-Angebote, die ohnehin nur 1×/Tag geprüft werden — siehe check_offer).
    `notify=False` speichert Kalender-Cache/-History weiterhin, überspringt aber den
    Kalender-Trend-Alarm und den 'günstigerer Termin'-Alarm am Ende dieser Funktion."""
    cfg = load_config()
    oid = offer['id']
    with db() as con:
        cached = con.execute('SELECT ts, data FROM calendar_cache WHERE offer_id=?',
                             (oid,)).fetchone()
    cal = None
    if not force_refresh and cached and time.time() - cached['ts'] < _CALENDAR_FRESH_SECONDS:
        try:
            cal = json.loads(cached['data'])
        except (ValueError, TypeError):
            cal = None
    if cal is None:
        cal = fetch_calendar(offer['url'], verbose=_verbose())
        if not cal or not cal.get('ok'):
            return
        try:
            with db() as con:
                changed = _store_calendar_snapshot(con, oid, cal)
            if notify:
                _check_calendar_trend_alert(oid, changed)
        except Exception as e:
            log.warning("Kalender-Cache #%d nicht aktualisiert: %s", oid, e)
    if not notify:
        return
    if not cal.get('ok'):
        return
    cd, cp = cal.get('cheapest_date'), cal.get('cheapest_price')
    if not cd or cp is None:
        return
    min_diff = max(1, int(cfg.get('cheaper_date_min_diff', 50) or 0))
    diff = current_price - cp
    if cd == cal.get('tracked_date') or diff < min_diff:
        return
    # Persistenter Dedup: nur melden, wenn es ein WIRKLICH neuer Tiefstwert ist —
    # also ein anderer Abreisetag ODER (gleicher Tag) ein nochmals tieferer Preis.
    # Reine Schwankungen nach oben und Wiederholungen über Neustarts lösen nichts aus.
    with db() as con:
        prev = con.execute('SELECT cdate, cprice FROM cheaper_state WHERE offer_id=?',
                           (oid,)).fetchone()
    if prev and prev['cdate'] == cd and prev['cprice'] is not None and cp >= prev['cprice']:
        return  # selber Termin, kein neuer Tiefstpreis
    with db() as con:
        con.execute('INSERT OR REPLACE INTO cheaper_state (offer_id, cdate, cprice, ts) '
                    'VALUES (?,?,?,?)', (oid, cd, cp, int(time.time())))
    _cheaper_notified[oid] = f"{cd}:{cp}"
    name = offer.get('label') or offer.get('hotel') or f"Angebot #{offer['id']}"
    d_de = '.'.join(reversed(cd.split('-')))  # YYYY-MM-DD → DD.MM.YYYY
    muted = bool(offer.get('notify_muted'))
    log.info("💡 Günstigerer Termin (#%d %s): %s am %s (%s günstiger) → Benachrichtigung",
             offer['id'], name, _eur(cp), d_de, _eur(diff))
    _notify_ha(f"💡 Günstigerer Termin: {name}",
               f"{name}\nAm {d_de} nur {_eur(cp)} — {_eur(diff)} günstiger als dein "
               f"Termin ({_eur(current_price)})\n{offer.get('url','')}",
               f"cheaper_{offer['id']}", muted=muted)
    _notify_telegram(f"💡 <b>Günstigerer Termin</b>\n{name}\nAm {d_de}: <b>{_eur(cp)}</b> "
                     f"({_eur(diff)} günstiger als {_eur(current_price)})\n{offer.get('url','')}", muted=muted)


def _check_booked_drop(offer: dict, current_price: float) -> None:
    """Meldet, wenn der aktuelle Preis deutlich UNTER den gebuchten Preis gefallen ist
    (Umbuchen könnte sich lohnen). Persistenter Dedup über `booked_state`: erst wieder bei
    einem neuen Tiefstwert. Gated durch `notify_booked_drop`."""
    cfg = load_config()
    if not cfg.get('notify_booked_drop', True):
        return
    booked = offer.get('booked_price')
    if not booked:
        return
    min_diff = max(1, int(cfg.get('booked_drop_min_diff', 50) or 0))
    diff = booked - current_price          # >0 = günstiger als gebucht
    if diff < min_diff:
        return
    oid = offer['id']
    with db() as con:
        prev = con.execute('SELECT price FROM booked_state WHERE offer_id=?',
                           (oid,)).fetchone()
    if prev and prev['price'] is not None and current_price >= prev['price']:
        return  # kein neuer Tiefstwert seit der letzten Meldung
    with db() as con:
        con.execute('INSERT OR REPLACE INTO booked_state (offer_id, price, ts) '
                    'VALUES (?,?,?)', (oid, current_price, int(time.time())))
    name = offer.get('label') or offer.get('hotel') or f"Angebot #{oid}"
    muted = bool(offer.get('notify_muted'))
    log.info("💰 Günstiger als gebucht (#%d %s): %s statt %s (%s gespart) → Benachrichtigung",
             oid, name, _eur(current_price), _eur(booked), _eur(diff))
    _notify_ha(f"💰 Günstiger als gebucht: {name}",
               f"{name}\nJetzt {_eur(current_price)} — {_eur(diff)} günstiger als dein "
               f"gebuchter Preis ({_eur(booked)}). Umbuchen könnte sich lohnen.\n"
               f"{offer.get('url','')}", f"booked_{oid}", muted=muted)
    _notify_telegram(f"💰 <b>Günstiger als gebucht: {name}</b>\nJetzt <b>{_eur(current_price)}</b> "
                     f"({_eur(diff)} unter deinem gebuchten Preis {_eur(booked)})\n"
                     f"{offer.get('url','')}", muted=muted)


def _error_streak(oid: int) -> int:
    """Anzahl aufeinanderfolgender Fehlschläge (neuester zuerst, bricht beim ersten
    ok=1 ab) — Basis für Auto-Pause und Fehler-Alarm."""
    with db() as con:
        rows = con.execute('SELECT ok FROM price_history WHERE offer_id=? ORDER BY ts DESC '
                           'LIMIT ?', (oid, ERROR_ALARM_STREAK)).fetchall()
    streak = 0
    for r in rows:
        if r['ok'] == 0:
            streak += 1
        else:
            break
    return streak


def _auto_pause_on_error_streak(offer: dict, streak: int) -> None:
    """Pausiert ein Angebot automatisch nach ERROR_ALARM_STREAK Fehlschlägen in Folge —
    keine sinnlosen Wiederholversuche auf eine tote URL/dauerhaft ausgebuchtes Hotel.
    Gilt für alle Angebotstypen (auch history_only), unabhängig von notify_errors."""
    if streak < ERROR_ALARM_STREAK or offer.get('paused'):
        return
    oid = offer['id']
    with db() as con:
        con.execute('UPDATE offers SET paused=1 WHERE id=?', (oid,))
    name = offer.get('label') or offer.get('hotel') or f"Angebot #{oid}"
    log.warning("⏸ Angebot #%d (%s) automatisch pausiert: %d× kein Ergebnis in Folge",
                oid, name, streak)
    _log_event(oid, 'pause', f"Automatisch pausiert nach {streak}× fehlgeschlagenem Abruf")


def _check_error_alarm(offer: dict) -> None:
    """Meldet, wenn ein Angebot ERROR_ALARM_STREAK-mal in Folge kein Ergebnis lieferte,
    und pausiert es dabei automatisch (siehe _auto_pause_on_error_streak)."""
    oid = offer['id']
    streak = _error_streak(oid)
    _auto_pause_on_error_streak(offer, streak)
    if not load_config().get('notify_errors', True):
        return
    if streak < ERROR_ALARM_STREAK or oid in _fail_notified:
        return
    _fail_notified.add(oid)
    name = offer.get('label') or offer.get('hotel') or f"Angebot #{oid}"
    log.warning("⚠ Ausverkauft-/Fehler-Alarm (#%d %s): %d× kein Ergebnis → Benachrichtigung",
                oid, name, streak)
    _notify_ha(f"⚠ Kein Angebot: {name}",
               f"{name}\nSeit {streak} Prüfungen kein Preis/Angebot — evtl. ausgebucht "
               f"oder die URL ist veraltet. Wurde automatisch pausiert.\n{offer.get('url','')}",
               f"error_{oid}")
    _notify_telegram(f"⚠ <b>Kein Angebot mehr: {name}</b>\nSeit {streak} Prüfungen kein "
                     f"Preis — evtl. ausgebucht oder URL veraltet. Wurde automatisch "
                     f"pausiert.\n{offer.get('url','')}")


def _clear_error_alarm(offer: dict) -> None:
    """Entwarnung, wenn ein zuvor gemeldetes Angebot wieder Ergebnisse liefert."""
    oid = offer['id']
    if oid not in _fail_notified:
        return
    _fail_notified.discard(oid)
    name = offer.get('label') or offer.get('hotel') or f"Angebot #{oid}"
    log.info("✅ Entwarnung (#%d %s): wieder verfügbar → Benachrichtigung", oid, name)
    _notify_ha(f"✅ Wieder verfügbar: {name}",
               f"{name} liefert wieder einen Preis.\n{offer.get('url','')}", f"error_{oid}")
    _notify_telegram(f"✅ <b>Wieder verfügbar: {name}</b>")


def _meta_get(key: str, default=None):
    with db() as con:
        row = con.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
    return row['value'] if row else default


def _meta_set(key: str, value: str) -> None:
    with db() as con:
        con.execute('INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)', (key, str(value)))


def _prompt_instructions(feature: str, default: str) -> str:
    """Effektiver Instruktions-Textblock für ein anpassbares KI-Feature
    ('advisor'/'compare'): Custom-Text aus `meta`, falls Checkbox aktiv UND
    Text nicht leer — sonst die Standard-Vorlage."""
    if _meta_get(f'custom_prompt_{feature}_enabled') != '1':
        return default
    return (_meta_get(f'custom_prompt_{feature}_text') or '').strip() or default


def _log_event(offer_id: int, type_: str, text: str) -> None:
    """Speichert ein Ereignis (für Marker im Verlauf-Diagramm)."""
    try:
        with db() as con:
            con.execute('INSERT INTO offer_events (offer_id, ts, type, text) VALUES (?,?,?,?)',
                        (offer_id, int(time.time()), type_, text))
    except Exception as e:
        log.warning("Event #%d (%s) nicht gespeichert: %s", offer_id, type_, e)


def _check_api_alarm(res: dict) -> None:
    """Meldet, wenn ein KRITISCHER TUI-Endpunkt im Selbsttest ausfällt (TUI hat evtl. die
    API geändert) — und gibt Entwarnung, sobald wieder alles läuft. Zustand persistent."""
    global _api_down_notified
    if not load_config().get('notify_api_errors', True):
        return
    bad = [c['name'] for c in res.get('checks', []) if c.get('critical') and not c['ok']]
    was_down = _meta_get('api_down') == '1'
    if bad and not was_down:
        _api_down_notified = True
        _meta_set('api_down', '1')
        names = ', '.join(bad)
        log.warning("⚠ API-Alarm: kritische Endpunkte gestört: %s → Benachrichtigung", names)
        _notify_ha("⚠ TUIWatch: TUI-API gestört",
                   f"Kritische TUI-Endpunkte antworten nicht: {names}.\nPreisprüfungen "
                   f"schlagen vermutlich fehl — evtl. hat TUI die API geändert.", "api")
        _notify_telegram(f"⚠ <b>TUI-API gestört</b>\nKritische Endpunkte: {names}\n"
                         f"Preisprüfungen schlagen vermutlich fehl.")
    elif not bad and was_down:
        _api_down_notified = False
        _meta_set('api_down', '0')
        log.info("✅ API-Entwarnung: alle Endpunkte wieder OK → Benachrichtigung")
        _notify_ha("✅ TUIWatch: TUI-API wieder OK",
                   "Alle kritischen TUI-Endpunkte antworten wieder.", "api")
        _notify_telegram("✅ <b>TUI-API wieder OK</b>")


# ── Scraping-Worker ────────────────────────────────────────────────────────────

def check_offer(offer_id: int) -> None:
    """Prüft ein Angebot (Playwright) und speichert einen Messpunkt."""
    with _checking_lock:
        if offer_id in _checking:
            return
        _checking.add(offer_id)
    try:
        with db() as con:
            offer = con.execute('SELECT * FROM offers WHERE id=?', (offer_id,)).fetchone()
            prev_row = con.execute(
                'SELECT ts, price FROM price_history WHERE offer_id=? AND ok=1 AND price IS NOT NULL '
                'ORDER BY ts DESC LIMIT 1', (offer_id,)).fetchone()
            # Zimmerwechsel seit dem letzten Preis-Check? Dann macht dessen Preisschritt
            # keine Marktbewegung, sondern nur einen anderen Zimmertyp/-preis sichtbar —
            # für den Markttrend (`price_moves`) muss die Zählung neu beginnen. `>=`
            # statt `>`: ts ist nur sekundengenau, ein schneller Zimmerwechsel direkt
            # nach dem ersten Check (typisch: Tracken → sofort Zimmerauswahl-Dialog)
            # landet oft in derselben Sekunde wie der vorherige Preis-Check.
            room_changed = bool(prev_row) and con.execute(
                "SELECT 1 FROM offer_events WHERE offer_id=? AND type='room' AND ts>=? LIMIT 1",
                (offer_id, prev_row['ts'])).fetchone()
        if not offer:
            return
        offer = dict(offer)
        if offer.get('archived'):
            log.info("Angebot #%d ist archiviert – keine Live-Abfrage", offer_id)
            return
        prev_price = prev_row['price'] if prev_row else None
        url = offer['url']
        name = offer.get('label') or offer.get('hotel') or hotel_from_url(url) or f"#{offer_id}"
        log.info("Prüfe Angebot #%d: %s …", offer_id, name)

        # bis zu 2 Versuche (gegen sporadische Timeouts/Bot-Drosselung)
        res = {}
        for attempt in (1, 2):
            with _scrape_lock:
                res = fetch_price(url, verbose=_verbose())
            if res.get('ok'):
                break
            if res.get('detail'):
                log.error("Angebot #%d (%s) Versuch %d: %s", offer_id, name, attempt, res['detail'])
            if attempt == 1:
                time.sleep(3)

        ts = int(time.time())
        avail = res.get('available')
        with db() as con:
            con.execute(
                'INSERT INTO price_history (offer_id, ts, price, old_price, discount, available, ok, note) '
                'VALUES (?,?,?,?,?,?,?,?)',
                (offer_id, ts, res.get('price'), res.get('old_price'), res.get('discount'),
                 (1 if avail else 0) if avail is not None else None,
                 1 if res.get('ok') else 0, res.get('note', '')))
            for col in ('hotel', 'details', 'room', 'board', 'dep_airport', 'flight_out',
                        'flight_ret', 'location', 'city', 'region', 'country',
                        'pdf_url', 'cancellation', 'stars', 'rating',
                        'rating_count', 'recommendation', 'total_price',
                        'travellers_count', 'return_date',
                        'booking_code', 'room_booking_code'):
                if res.get(col) is not None and res.get(col) != '':
                    con.execute(f'UPDATE offers SET {col}=? WHERE id=?', (res[col], offer_id))
            if res.get('ok') and res.get('price') is not None and prev_price and not room_changed:
                pct = (res['price'] - prev_price) / prev_price * 100
                region = res.get('region') or offer.get('region') or ''
                country = res.get('country') or offer.get('country') or ''
                ret_date = res.get('return_date') or offer.get('return_date') or ''
                months_out = _months_out(ret_date, duration_from_url(url), ts)
                con.execute(
                    'INSERT INTO price_moves (ts, region, country, months_out, pct_change) '
                    'VALUES (?,?,?,?,?)', (ts, region, country, months_out, pct))

        if res.get('ok'):
            extra = []
            if res.get('travellers_count') and res['travellers_count'] > 1 and res.get('total_price'):
                extra.append(f"Gesamt {res['total_price']:.0f} €")
            if res.get('available') is not None:
                extra.append('verfügbar' if res['available'] else 'nicht verfügbar')
            log.info("Angebot #%d (%s): %.0f € pro Person%s [%s]", offer_id, name, res['price'],
                     (' · ' + ' · '.join(extra)) if extra else '', res.get('source', '?'))
            if prev_price is not None and res['price'] != prev_price:
                log.info("Angebot #%d (%s): Preis %s → %.0f € (%+.0f €)", offer_id, name,
                         f"{prev_price:.0f}", res['price'], res['price'] - prev_price)
            if offer.get('history_only'):
                # Nur Verlauf/Kalender pflegen, keine Benachrichtigungen — siehe
                # _check_cheaper_date (force_refresh sorgt für tägliche Kalenderdaten,
                # da history_only-Angebote ohnehin nur 1×/Tag geprüft werden).
                if res.get('price'):
                    _check_cheaper_date(offer, res['price'], force_refresh=True, notify=False)
            else:
                _maybe_notify(offer, prev_price, res.get('price'), offer.get('target_price'))
                _clear_error_alarm(offer)
                if load_config().get('notify_cheaper_date', True) and res.get('price'):
                    # Preis geändert? Dann Kalender sofort neu abrufen statt bis zu
                    # 7 Tage auf den nächsten TTL-Ablauf zu warten (siehe
                    # _check_cheaper_date) — Kalender soll mit dem aktuellen Preis
                    # Schritt halten, nicht tagealt hinterherhinken.
                    price_changed = prev_price is not None and res['price'] != prev_price
                    _check_cheaper_date(offer, res['price'], force_refresh=price_changed)
                if res.get('price') and offer.get('booked_price'):
                    _check_booked_drop(offer, res['price'])
            # Hotelbild einmalig nachladen (nur wenn noch keins vorhanden)
            if not offer.get('image_url'):
                try:
                    with _scrape_lock:
                        img = fetch_hotel_image(url, verbose=_verbose())
                    if img:
                        with db() as con:
                            con.execute('UPDATE offers SET image_url=? WHERE id=?',
                                        (img, offer_id))
                        log.info("Angebot #%d: Hotelbild gespeichert", offer_id)
                except Exception as e:
                    log.warning("Hotelbild #%d nicht abrufbar: %s", offer_id, e)
        elif (res.get('note') or '').startswith('Kein Angebot'):
            # kein Crash, sondern ausgebucht/kein Treffer im Zeitraum → gelb
            log.warning("Angebot #%d (%s): kein Angebot im Zeitraum", offer_id, name)
            if offer.get('history_only'):
                _auto_pause_on_error_streak(offer, _error_streak(offer_id))
            else:
                _check_error_alarm(offer)
        else:
            # echter Abruf-Fehler → rot (Detail steht ggf. schon oben im Log)
            log.error("Angebot #%d (%s): Abruf fehlgeschlagen – %s", offer_id, name, res.get('note'))
            if offer.get('history_only'):
                _auto_pause_on_error_streak(offer, _error_streak(offer_id))
            else:
                _check_error_alarm(offer)
    except Exception as e:
        log.error("check_offer(#%d) Fehler: %s", offer_id, e)
    finally:
        with _checking_lock:
            _checking.discard(offer_id)
    push_ha_sensors()


def check_all(reason: str = '') -> None:
    with db() as con:
        ids = [r['id'] for r in con.execute(
            'SELECT id FROM offers WHERE COALESCE(paused,0)=0 '
            'AND COALESCE(archived,0)=0 ORDER BY id').fetchall()]
    if ids:
        log.info("Prüfe %d Angebot(e)%s", len(ids), f' ({reason})' if reason else '')
    for oid in ids:
        check_offer(oid)


# ── Pro-Person-Vergleich (on-demand, nicht persistiert) ─────────────────────────

def _run_compare(offer_id: int) -> None:
    """Ruft dasselbe Angebot live für die aktuelle Reisendenzahl und für 2 Personen
    ab (bei aktuell=2: 2 ↔ 1) und speichert das Ergebnis in compare_cache (DB),
    damit es erhalten bleibt und nicht bei jedem Öffnen neu abgefragt wird."""
    try:
        with db() as con:
            offer = con.execute('SELECT url FROM offers WHERE id=?', (offer_id,)).fetchone()
        if not offer:
            with _compare_lock:
                _compare_state[offer_id] = {'status': 'error', 'note': 'Angebot nicht gefunden'}
            return
        url = offer['url']
        base = travellers_from_url(url)
        counts = sorted({base, 2} if base != 2 else {2, 1})
        rows = []
        for n in counts:
            target = with_travellers(url, n)
            with _scrape_lock:
                res = fetch_price(target, check_availability=False, verbose=_verbose())
            if not res.get('ok'):
                # Fallback: fester Zimmercode kann eine andere Belegung verhindern
                with _scrape_lock:
                    res = fetch_price(without_room_code(target),
                                      check_availability=False, verbose=_verbose())
            price = res.get('price')
            rows.append({
                'travellers': n,
                'ok': bool(res.get('ok') and price is not None),
                'price': price,
                'total': round(price * n) if price is not None else None,
                'is_base': n == base,
                'note': '' if res.get('ok') else 'nicht abrufbar',
            })
        with db() as con:
            con.execute('INSERT OR REPLACE INTO compare_cache (offer_id, ts, base, rows) '
                        'VALUES (?,?,?,?)',
                        (offer_id, int(time.time()), base, json.dumps(rows)))
        with _compare_lock:
            _compare_state.pop(offer_id, None)
        log.info("Vergleich #%d fertig: %s", offer_id,
                 ', '.join(f"{r['travellers']}P={r['price']}" for r in rows))
    except Exception as e:
        log.error("Vergleich #%d Fehler: %s", offer_id, e)
        with _compare_lock:
            _compare_state[offer_id] = {'status': 'error', 'note': 'Vergleich fehlgeschlagen'}


def _compare_payload(offer_id: int) -> dict:
    """Aktueller Vergleichszustand: laufend / Fehler / gespeichertes Ergebnis / leer."""
    with _compare_lock:
        st = dict(_compare_state.get(offer_id) or {})
    if st.get('status') == 'running':
        return {'status': 'running', 'rows': []}
    with db() as con:
        row = con.execute('SELECT ts, base, rows FROM compare_cache WHERE offer_id=?',
                          (offer_id,)).fetchone()
    if row:
        out = {'status': 'done', 'ts': row['ts'], 'base': row['base'],
               'rows': _json_loads_safe(row['rows'], [])}
    else:
        out = {'status': 'idle', 'rows': []}
    if st.get('status') == 'error':
        out['error'] = st.get('note', 'Vergleich fehlgeschlagen')
    return out


# ── Nächte-Vergleich (on-demand, gespeichert) ───────────────────────────────────

NIGHTS_SPAN_MAX = 7  # max. Spanne ±N (begrenzt die Anzahl Live-Abfragen pro Lauf)


def _run_nights(offer_id: int, span: int) -> None:
    """Ruft dasselbe Angebot live für benachbarte Reisedauern ab (Basis ±span Nächte)
    und speichert das Ergebnis in nights_cache. So sieht man, ob eine Nacht kürzer/
    länger deutlich günstiger ist (pro Person und pro Nacht). Manche Dauern liefern
    kein Angebot (nicht an jedem Tag gibt es Flüge)."""
    try:
        with db() as con:
            offer = con.execute('SELECT url FROM offers WHERE id=?', (offer_id,)).fetchone()
        if not offer:
            with _nights_lock:
                _nights_state[offer_id] = {'status': 'error', 'note': 'Angebot nicht gefunden'}
            return
        url = offer['url']
        base = duration_from_url(url)
        if not base:
            with _nights_lock:
                _nights_state[offer_id] = {'status': 'error', 'note': 'Reisedauer unbekannt'}
            return
        travellers = travellers_from_url(url)
        # Basis + ±span Nächte, nie unter 2 Nächten, dedupliziert + sortiert
        nights_set = {base}
        for d in range(1, span + 1):
            if base - d >= 2:
                nights_set.add(base - d)
            nights_set.add(base + d)
        order = sorted(nights_set)
        total = len(order)
        with _nights_lock:
            _nights_state[offer_id] = {'status': 'running', 'done': 0, 'total': total}
        rows = []
        for i, n in enumerate(order):
            with _scrape_lock:
                res = fetch_price(with_duration(url, n),
                                  check_availability=False, verbose=_verbose())
            if not res.get('ok'):
                # Fallback: fester Zimmercode kann eine andere Dauer verhindern
                with _scrape_lock:
                    res = fetch_price(without_room_code(with_duration(url, n)),
                                      check_availability=False, verbose=_verbose())
            price = res.get('price')
            ok = bool(res.get('ok') and price is not None)
            note = '' if ok else 'nicht abrufbar'
            # TUI liefert bei nicht buchbarer Dauer das nächstliegende Angebot (z. B.
            # immer das 7-Nächte-Paket). Nur akzeptieren, wenn die tatsächliche Dauer
            # der angefragten entspricht — sonst gibt es für n kein Angebot.
            actual = res.get('nights_num')
            if ok and actual is not None and actual != n:
                ok = False
                price = None
                note = 'nicht abrufbar'
            rows.append({
                'nights': n,
                'ok': ok,
                'price': price,
                'per_night': round(price / n) if ok and n else None,
                'total': round(price * travellers) if ok else None,
                'is_base': n == base,
                'note': note,
            })
            with _nights_lock:
                _nights_state[offer_id] = {'status': 'running', 'done': i + 1,
                                           'total': total}
        with db() as con:
            con.execute('INSERT OR REPLACE INTO nights_cache (offer_id, ts, base, span, rows) '
                        'VALUES (?,?,?,?,?)',
                        (offer_id, int(time.time()), base, span, json.dumps(rows)))
        with _nights_lock:
            _nights_state.pop(offer_id, None)
        log.info("Nächte-Vergleich #%d fertig (Basis %d N, ±%d): %s", offer_id, base, span,
                 ', '.join(f"{r['nights']}N={r['price']}" for r in rows if r['ok']) or 'keine Treffer')
    except Exception as e:
        log.error("Nächte-Vergleich #%d Fehler: %s", offer_id, e)
        with _nights_lock:
            _nights_state[offer_id] = {'status': 'error', 'note': 'Nächte-Vergleich fehlgeschlagen'}


def _nights_payload(offer_id: int) -> dict:
    """Aktueller Zustand: laufend / Fehler / gespeichertes Ergebnis / leer."""
    with _nights_lock:
        st = dict(_nights_state.get(offer_id) or {})
    if st.get('status') == 'running':
        return {'status': 'running', 'rows': [],
                'done': st.get('done', 0), 'total': st.get('total', 0)}
    with db() as con:
        row = con.execute('SELECT ts, base, span, rows FROM nights_cache WHERE offer_id=?',
                          (offer_id,)).fetchone()
    if row:
        out = {'status': 'done', 'ts': row['ts'], 'base': row['base'],
               'span': row['span'], 'rows': _json_loads_safe(row['rows'], [])}
    else:
        out = {'status': 'idle', 'rows': []}
    if st.get('status') == 'error':
        out['error'] = st.get('note', 'Nächte-Vergleich fehlgeschlagen')
    return out


# ── Check24-Vergleich (on-demand, gespeichert) ──────────────────────────────────

def _run_check24_compare(offer_id: int) -> None:
    """Ruft den gepinnten Check24-Hotel-Link live ab (Playwright, siehe
    check24_client.py) und speichert das Ergebnis in check24_cache (DB). Läuft im
    Hintergrund-Thread, analog zu _run_compare()/_run_nights()."""
    try:
        with db() as con:
            o = con.execute(
                'SELECT url, check24_hotel_id, room, board, details, dep_airport, return_date'
                ' FROM offers WHERE id=?', (offer_id,)).fetchone()
            last = con.execute(
                'SELECT price FROM price_history WHERE offer_id=? ORDER BY ts DESC LIMIT 1',
                (offer_id,)).fetchone()
        tui_price = last['price'] if last else None
        if not o:
            with _check24_lock:
                _check24_state[offer_id] = {'status': 'error', 'note': 'Angebot nicht gefunden'}
            return
        if not o['check24_hotel_id']:
            with _check24_lock:
                _check24_state[offer_id] = {'status': 'error', 'note': 'Kein Check24-Hotel verknüpft'}
            return
        q = {k: v[0] for k, v in parse_qs(urlparse(o['url']).query).items()}
        # URL-Parameter startDate/endDate/departureAirports sind das (ggf. flexible)
        # Such-Zeitfenster, NICHT das tatsächlich gebuchte Datum -- bei einer
        # mehrmonatigen Flex-Suche kommen so absurde Check24-Anfragen raus (z.B.
        # 20.07.-17.10. statt der echten 7 Nächte ab 06.12.). Die echten Werte
        # stehen in details ("... Nächte ab DD.MM.YYYY") und return_date/dep_airport.
        m = re.search(r'ab (\d{2})\.(\d{2})\.(\d{4})', o['details'] or '')
        departure_date = f'{m.group(3)}-{m.group(2)}-{m.group(1)}' if m else q.get('startDate', '')
        return_date = o['return_date'] or q.get('endDate', '')
        am = re.search(r'\(([A-Z]{3})\)', o['dep_airport'] or '')
        airport = am.group(1) if am else (q.get('departureAirports', '') or '').split(',')[0]
        query = {'departure_date': departure_date, 'return_date': return_date,
                 'airport': airport, 'room_hint': o['room'] or '', 'board_hint': o['board'] or ''}
        res = None
        for attempt in range(2):
            with _check24_scrape_lock:
                res = check24_client.fetch_offers(
                    o['check24_hotel_id'], departure_date, return_date,
                    airport, room_hint=o['room'] or '', board_hint=o['board'] or '',
                    verbose=_verbose())
            if res is not None:
                break
            time.sleep(3)
        if res is None:
            with _check24_lock:
                _check24_state[offer_id] = {'status': 'error', 'note': 'Check24 nicht erreichbar'}
            return
        with db() as con:
            con.execute('INSERT OR REPLACE INTO check24_cache (offer_id, ts, query, tui_price, rows, offer_url) '
                        'VALUES (?,?,?,?,?,?)',
                        (offer_id, int(time.time()), json.dumps(query, ensure_ascii=False),
                         tui_price, json.dumps(res.get('rows', [])), res.get('offer_url', '')))
        with _check24_lock:
            _check24_state.pop(offer_id, None)
        log.info("Check24-Vergleich #%d fertig: %d Angebot(e), Hinweis=%s",
                 offer_id, len(res.get('rows', [])), res.get('note') or '-')
    except Exception as e:
        log.error("Check24-Vergleich #%d Fehler: %s", offer_id, e)
        with _check24_lock:
            _check24_state[offer_id] = {'status': 'error', 'note': 'Check24-Vergleich fehlgeschlagen'}


def _check24_payload(offer_id: int) -> dict:
    """Aktueller Zustand: laufend / Fehler / gespeichertes Ergebnis / leer."""
    with _check24_lock:
        st = dict(_check24_state.get(offer_id) or {})
    if st.get('status') == 'running':
        return {'status': 'running', 'rows': []}
    with db() as con:
        row = con.execute('SELECT ts, query, tui_price, rows, offer_url FROM check24_cache WHERE offer_id=?',
                          (offer_id,)).fetchone()
    if row:
        out = {'status': 'done', 'ts': row['ts'], 'query': _json_loads_safe(row['query'], {}),
               'tui_price': row['tui_price'], 'rows': _json_loads_safe(row['rows'], []),
               'offer_url': row['offer_url'] or ''}
    else:
        out = {'status': 'idle', 'rows': []}
    if st.get('status') == 'error':
        out['error'] = st.get('note', 'Check24-Vergleich fehlgeschlagen')
    return out


# ── TUI-Aktionscodes (öffentlich, ohne Login) ───────────────────────────────────

def _store_aktionscodes(codes: list, ts: int) -> list:
    """Codes (nach Wert+Art) in aktionscode_state ablegen und die **neu erschienenen**
    zurückgeben. „Neu" = vorher nicht aktiv — deckt den täglichen Datumswechsel im Code ab
    und meldet erneut, wenn eine beendete Aktion später wiederkommt. Ohne Netz testbar."""
    keys_now, new = set(), []
    with db() as con:
        for c in codes:
            key = f"{c.get('kind', '')}|{c.get('value')}"
            keys_now.add(key)
            row = con.execute('SELECT active FROM aktionscode_state WHERE ckey=?',
                              (key,)).fetchone()
            if row is None:
                con.execute('INSERT INTO aktionscode_state (ckey, code, value, kind, active, '
                            'first_seen, last_seen) VALUES (?,?,?,?,1,?,?)',
                            (key, c.get('code') or '', c.get('value'), c.get('kind') or '', ts, ts))
                new.append(c)
            elif not row['active']:
                con.execute('UPDATE aktionscode_state SET code=?, active=1, last_seen=? '
                            'WHERE ckey=?', (c.get('code') or '', ts, key))
                new.append(c)
            else:
                con.execute('UPDATE aktionscode_state SET code=?, last_seen=? WHERE ckey=?',
                            (c.get('code') or '', ts, key))
        # nicht mehr vorhandene Aktionen inaktiv setzen → später erneut meldbar
        for r in con.execute('SELECT ckey FROM aktionscode_state WHERE active=1').fetchall():
            if r['ckey'] not in keys_now:
                con.execute('UPDATE aktionscode_state SET active=0 WHERE ckey=?', (r['ckey'],))
    return new


def _push_aktionscodes_sensor(codes: list, info: dict) -> None:
    """Meldet HA einen Binär-Sensor: 'on', solange aktuell TUI-Aktionscodes verfügbar
    sind (Codes als Liste in den Attributen), sonst 'off'."""
    if not _ha_enabled():
        return
    attrs = {
        'friendly_name': 'TUIWatch Aktionscodes', 'icon': 'mdi:ticket-percent',
        'device_class': 'occupancy',
        'count': len(codes),
        'coupons': [{'code': c.get('code') or '', 'value': c.get('value'),
                     'kind': c.get('kind') or ''} for c in codes],
    }
    if info.get('booking_until'):
        attrs['booking_until'] = info['booking_until']
    if info.get('travel_period'):
        attrs['travel_period'] = info['travel_period']
    try:
        http.post(f'{HA_BASE}/states/binary_sensor.tuiwatch_aktionscodes',
                  headers={'Authorization': f'Bearer {SUPERVISOR_TOKEN}'}, timeout=10,
                  json={'state': 'on' if codes else 'off', 'attributes': attrs})
    except Exception as e:
        log.warning("HA-Aktionscode-Sensor aktualisieren fehlgeschlagen: %s", e)


def _notify_aktionscodes(new: list, info: dict) -> None:
    lines = [f"• {c.get('value')} € — Code {c.get('code')}"
             + (f" ({c['kind']})" if c.get('kind') else '') for c in new]
    extra = []
    if info.get('booking_until'):
        extra.append(f"buchbar bis {info['booking_until']}")
    if info.get('travel_period'):
        extra.append(f"Reisezeitraum {info['travel_period']}")
    body = "\n".join(lines) + ("\n" + " · ".join(extra) if extra else "")
    head = f"{len(new)} neue TUI-Aktionscodes" if len(new) != 1 else "Neuer TUI-Aktionscode"
    _notify_ha(f"🎟 {head}", body, "aktionscodes")
    _notify_telegram(f"🎟 <b>{head}</b>\n{body}")


def _run_aktionscodes() -> None:
    """Aktionscodes abrufen, speichern, neue melden. Läuft im Hintergrund-Thread."""
    with _aktion_lock:
        if _aktion_state.get('running'):
            return
        _aktion_state.clear()
        _aktion_state['running'] = True
    try:
        res = fetch_aktionscodes(verbose=_verbose())
    except Exception as e:
        res = {'ok': False, 'error': f'{type(e).__name__}: {e}'}
    ts = int(time.time())
    _meta_set('aktion_checked', str(ts))
    if not res.get('ok'):
        log.warning("Aktionscode-Abruf fehlgeschlagen: %s", res.get('error'))
        with _aktion_lock:
            _aktion_state.clear()
            _aktion_state.update({'error': res.get('error') or 'Abruf fehlgeschlagen', 'ts': ts})
        return
    cfg = load_config()
    try:
        min_val = int(cfg.get('aktionscode_min', 0) or 0)
    except (TypeError, ValueError):
        min_val = 0
    codes = [c for c in (res.get('codes') or []) if (c.get('value') or 0) >= min_val]
    info = {'booking_until': res.get('booking_until', ''),
            'travel_period': res.get('travel_period', '')}
    _meta_set('aktion_last', json.dumps({'ts': ts, 'codes': codes, **info}, ensure_ascii=False))
    _push_aktionscodes_sensor(codes, info)
    new = _store_aktionscodes(codes, ts)
    if new and cfg.get('notify_aktionscodes', True):
        try:
            _notify_aktionscodes(new, info)
        except Exception as e:
            log.error("Aktionscode-Benachrichtigung fehlgeschlagen: %s", e)
    log.info("Aktionscode-Abruf: %d Codes, %d neu", len(codes), len(new))
    with _aktion_lock:
        _aktion_state.clear()
        _aktion_state['ts'] = ts


def _push_aktionscodes_sensor_from_cache() -> None:
    """Sensor aus dem letzten gespeicherten Abruf erneut an HA melden (kein Netz-Fetch).
    Ein HA-Neustart (nicht der des Add-ons) wirft den Sensor aus HAs State-Machine —
    erst ein erneutes Setzen bringt ihn zurück. Läuft daher per Timer alle 2 Minuten,
    nicht nur einmalig beim Add-on-Start."""
    try:
        last = json.loads(_meta_get('aktion_last', '') or '{}')
    except Exception:
        return
    if not last:
        return
    info = {'booking_until': last.get('booking_until', ''),
            'travel_period': last.get('travel_period', '')}
    _push_aktionscodes_sensor(last.get('codes') or [], info)


def _maybe_check_aktionscodes() -> None:
    """Aktionscodes höchstens alle `aktionscode_interval` Sekunden prüfen (Standard 6 h)."""
    with _aktion_lock:
        if _aktion_state.get('running'):
            return
    try:
        interval = int(load_config().get('aktionscode_interval', 21600) or 21600)
    except (TypeError, ValueError):
        interval = 21600
    try:
        last = int(_meta_get('aktion_checked', 0) or 0)
    except (TypeError, ValueError):
        last = 0
    if time.time() - last >= max(1800, interval):
        _run_aktionscodes()


def _aktionscodes_payload() -> dict:
    with _aktion_lock:
        st = dict(_aktion_state)
    try:
        last = json.loads(_meta_get('aktion_last', '') or '{}')
    except Exception:
        last = {}
    return {
        'running': bool(st.get('running')),
        'error': st.get('error'),
        'ts': last.get('ts') or (int(_meta_get('aktion_checked', 0) or 0) or None),
        'codes': last.get('codes') or [],
        'booking_until': last.get('booking_until', ''),
        'travel_period': last.get('travel_period', ''),
    }


@app.route('/api/aktionscodes', methods=['GET'])
def api_aktionscodes_get():
    if (err := _require_api()):
        return err
    return jsonify(_aktionscodes_payload())


@app.route('/api/aktionscodes', methods=['POST'])
def api_aktionscodes_check():
    if (err := _require_api()):
        return err
    with _aktion_lock:
        if _aktion_state.get('running'):
            return jsonify({'started': True, 'already': True})
    _spawn(_run_aktionscodes)
    return jsonify({'started': True})


def _history_only_wait_seconds(oid: int, last_ts: int, now: int) -> int:
    """Sekunden bis zum nächsten fixen Preisverlauf-Check: täglich um HISTORY_ONLY_HOUR
    Uhr (lokale Zeit) + ein individueller, stabiler Offset je Angebot (oid % Spread) —
    verteilt die Checks über HISTORY_ONLY_SPREAD_MIN Minuten statt alle exakt zur
    selben Sekunde auszulösen. <=0 bedeutet: jetzt fällig."""
    dt = datetime.fromtimestamp(now)
    slot = dt.replace(hour=HISTORY_ONLY_HOUR, minute=0, second=0, microsecond=0) \
        + timedelta(minutes=oid % HISTORY_ONLY_SPREAD_MIN)
    slot_ts = int(slot.timestamp())
    if last_ts >= slot_ts:
        slot_ts += 86400  # heutiger Slot wurde schon geprüft → morgiger Slot
    return slot_ts - now


def _poll_worker() -> None:
    """Prüft Angebote fälligkeitsbasiert: ein Angebot wird erst wieder abgefragt,
    wenn seit seinem letzten Check (auch über Neustarts hinweg) das Intervall
    verstrichen ist. So löst ein Add-on-Neustart keine sofortige Komplettabfrage aus.
    Preisverlauf-Angebote (history_only) folgen stattdessen einem festen, gestreuten
    Tages-Slot (siehe _history_only_wait_seconds)."""
    log.info("Preis-Poller gestartet")
    time.sleep(5)  # kurzer Vorlauf, damit der Webserver zuerst hochkommt
    while True:
        interval = max(MIN_POLL_INTERVAL,
                       int(load_config().get('poll_interval', POLL_INTERVAL_DEFAULT)))
        next_in = interval
        try:
            now = int(time.time())
            _maybe_periodic_health()  # API-Selbsttest 1×/Tag — VOR den Preisprüfungen
            _maybe_send_digest()      # wöchentliche Zusammenfassung (falls aktiviert)
            _maybe_check_aktionscodes()   # öffentliche TUI-Aktionscodes
            _maybe_auto_backup()      # wöchentliches Backup nach /addon_config
            _maybe_check_watches()    # Suchabos (gespeicherte Suchen mit Schwellenpreis)
            _maybe_refresh_calendars()  # Preiskalender 1×/Tag je Angebot auffrischen
            market_basket.maybe_run_baskets()  # Warenkorb je gespeicherter Suche, 1×/Tag
            _auto_archive_expired()
            with db() as con:
                offers = [(r['id'], bool(r['history_only'])) for r in con.execute(
                    'SELECT id, history_only FROM offers WHERE COALESCE(paused,0)=0 '
                    'AND COALESCE(archived,0)=0 ORDER BY id').fetchall()]
                last_map = {r['offer_id']: r['m'] for r in con.execute(
                    'SELECT offer_id, MAX(ts) m FROM price_history GROUP BY offer_id').fetchall()}
            due = []
            for oid, history_only in offers:
                last_ts = last_map.get(oid) or 0
                if history_only:
                    wait = _history_only_wait_seconds(oid, last_ts, now)
                    if wait <= 0:
                        due.append(oid)
                    else:
                        next_in = min(next_in, wait)
                    continue
                age = now - last_ts
                if age >= interval:
                    due.append(oid)
                else:
                    next_in = min(next_in, interval - age)
            if due:
                log.info("Prüfe %d fällige(s) Angebot(e)", len(due))
                for oid in due:
                    check_offer(oid)
                continue  # danach sofort neu bewerten, was als Nächstes fällig ist
        except Exception as e:
            log.error("Poll-Fehler: %s", e)
            next_in = interval
        time.sleep(max(30, min(next_in, interval)))


def _maybe_refresh_calendars() -> None:
    """Hält Preiskalender aktuell: 1×/Tag je aktivem Angebot. Da beim Tracken der
    Kalender ohnehin sofort mitabgerufen wird (Erstabruf in _check_cheaper_date),
    betrifft das praktisch alle Angebote — der calendar_cache-Join ist nur Guard
    für Sonderfälle (z. B. notify_cheaper_date deaktiviert). Macht
    calendar_history dichter → Trend-Ansicht und das Kalender-Bewegungs-Signal
    im Buchungsscore werden aussagekräftiger; ergänzt den Sofort-Refresh bei
    Preisänderung. Max. 10 je Poll-Zyklus (je ~3 HTTP-Requests), älteste zuerst.
    Abschaltbar über calendar_daily_refresh."""
    if not load_config().get('calendar_daily_refresh', True):
        return
    cutoff = int(time.time()) - 86400
    with db() as con:
        rows = con.execute(
            'SELECT c.offer_id FROM calendar_cache c JOIN offers o ON o.id = c.offer_id '
            'WHERE COALESCE(o.paused,0)=0 AND COALESCE(o.archived,0)=0 AND c.ts<=? '
            'ORDER BY c.ts LIMIT 10', (cutoff,)).fetchall()
    for r in rows:
        log.info("Täglicher Kalender-Refresh: Angebot #%d", r['offer_id'])
        _run_calendar(r['offer_id'])


def _maybe_periodic_health() -> None:
    """Führt den API-Selbsttest höchstens 1×/Tag aus (am Anfang eines Poll-Zyklus,
    also noch vor den Preisprüfungen). So ist die Footer-Ampel stets aktuell und ein
    API-Ausfall wird gemeldet, bevor die Preisabfragen daran scheitern."""
    with _health_lock:
        last = _health_state.get('ts', 0)
        running = _health_state.get('running')
    if running:
        return
    if time.time() - (last or 0) >= 86400:
        _run_healthcheck()


def _push_health_sensor(res: dict) -> None:
    """Meldet HA einen Binär-Sensor: 'on', solange alle kritischen TUI-Endpunkte im
    letzten Selbsttest erreichbar waren, sonst 'off'."""
    if not _ha_enabled():
        return
    bad = [c['name'] for c in (res.get('checks') or []) if c.get('critical') and not c.get('ok')]
    attrs = {
        'friendly_name': 'TUIWatch API verfügbar', 'icon': 'mdi:api',
        'device_class': 'connectivity',
        'failing': bad,
    }
    if res.get('ts'):
        attrs['checked_at'] = datetime.fromtimestamp(res['ts']).isoformat()
    try:
        http.post(f'{HA_BASE}/states/binary_sensor.tuiwatch_api_available',
                  headers={'Authorization': f'Bearer {SUPERVISOR_TOKEN}'}, timeout=10,
                  json={'state': 'off' if bad else 'on', 'attributes': attrs})
    except Exception as e:
        log.warning("HA-API-Sensor aktualisieren fehlgeschlagen: %s", e)


def _push_health_sensor_from_cache() -> None:
    """Sensor aus dem letzten Selbsttest erneut an HA melden (kein neuer Netz-Check) —
    überlebt einen HA-Neustart wie der Coupon-Sensor (siehe
    `_push_aktionscodes_sensor_from_cache`)."""
    with _health_lock:
        res = dict(_health_state)
    if not res or res.get('running'):
        return
    _push_health_sensor(res)


def _push_market_trend_sensor() -> None:
    """Meldet HA einen Sensor mit dem marktweiten Preistrend — State = kumulierte
    %-Bewegung der letzten 14 Tage, oder 'unknown' bei zu wenigen Daten (NIE
    'unavailable' — das wäre HA-Konvention für einen kaputten Sensor, hier ist der
    Sensor selbst ja da). Attribute ergänzen den Index seit Aufzeichnungsbeginn
    (`_market_index`), der auch langsame, über Wochen verteilte Bewegungen zeigt.
    Als Quelle hat der Warenkorb Vorrang (`market_basket`: die gespeicherten Suchen,
    täglich neu ausgeführt — hunderte Hotels für die eigenen Reisetermine statt nur
    der eigenen Angebote); erst wenn der noch keine zwei Tagesbewegungen gesammelt
    hat, greift der angebotsbasierte Trend. Das Attribut
    `source` sagt, welche Quelle den State gerade liefert — beide Werte stehen
    zusätzlich unter `offers`/`basket` im Attributbaum.
    Berechnung und POST sind bewusst GETRENNT abgesichert: bricht die Berechnung bei
    einer ungewöhnlichen Datenkonstellation (z. B. einzelne Region mit Sonderfällen)
    mit einer Exception ab, soll das NICHT den ganzen Refresh-Zyklus killen und die
    Entity dadurch bei HA verwaisen lassen — lieber mit 'unknown' posten und den
    Fehler loggen, als stillschweigend gar nicht zu posten."""
    if not _ha_enabled():
        return
    state, attrs = 'unknown', {'friendly_name': 'TUIWatch Markttrend', 'icon': 'mdi:chart-line',
                                'unit_of_measurement': '%'}
    try:
        with db() as con:
            glob_trend = _market_trend(con)
            glob_index = _market_index(con)
            regions = [r['region'] for r in con.execute(
                "SELECT DISTINCT region FROM price_moves WHERE region!=''").fetchall()]
            by_region = []
            for r in sorted(regions):
                t, i = _market_trend(con, region=r), _market_index(con, region=r)
                if t or i:
                    by_region.append({'region': r, 'trend': t, 'index': i})
        basket = market_basket.basket_payload()
        bt, bi = basket['global']['trend'], basket['global']['index']
        attrs['by_region'] = by_region
        attrs['offers'] = {'trend': glob_trend, 'index': glob_index}
        attrs['basket'] = {'trend': bt, 'index': bi, 'by_region': basket['by_region'],
                           'last_day': basket['last_day']}
        src_trend, src_index = (bt, bi) if bt else (glob_trend, glob_index)
        attrs['source'] = 'basket' if bt else 'offers'
        if src_trend:
            attrs.update(direction=src_trend['dir'], days=src_trend['days'],
                         samples=src_trend['n'])
            if src_trend.get('hotels'):
                attrs['hotels'] = src_trend['hotels']
        if src_index:
            attrs.update(index=src_index['index'], index_pct=src_index['pct'],
                         index_since=datetime.fromtimestamp(src_index['since']).isoformat())
        state = src_trend['pct'] if src_trend else 'unknown'
    except Exception as e:
        log.warning("Markttrend-Berechnung fehlgeschlagen (poste trotzdem 'unknown'): %s: %s",
                     type(e).__name__, e)
    try:
        http.post(f'{HA_BASE}/states/sensor.tuiwatch_markttrend',
                  headers={'Authorization': f'Bearer {SUPERVISOR_TOKEN}'}, timeout=10,
                  json={'state': state, 'attributes': attrs})
    except Exception as e:
        log.warning("HA-Markttrend-Sensor aktualisieren fehlgeschlagen: %s", e)


def _run_healthcheck() -> dict:
    """Führt den API-Selbsttest aus und legt das Ergebnis in _health_state ab."""
    with _health_lock:
        if _health_state.get('running'):
            return dict(_health_state)
        _health_state['running'] = True
    try:
        res = api_healthcheck(verbose=_verbose())
    except Exception as e:
        log.error("API-Selbsttest fehlgeschlagen: %s", e)
        res = {'ok': False, 'ts': int(time.time()), 'checks': [],
               'note': 'Selbsttest fehlgeschlagen'}
    with _health_lock:
        _health_state.clear()
        _health_state.update(res)
    bad = [c['name'] for c in res.get('checks', []) if not c['ok']]
    if bad:
        log.warning("API-Selbsttest: Probleme bei %s", ', '.join(bad))
    else:
        log.info("API-Selbsttest: alle Endpunkte OK")
    try:
        _check_api_alarm(res)
    except Exception as e:
        log.error("API-Alarm-Prüfung fehlgeschlagen: %s", e)
    _push_health_sensor(res)
    return res


def _week_change(con, offer_id: int, current: float, days: int = 7):
    """Preisänderung des Angebots über die letzten `days` Tage (current − ältester Preis
    im Fenster). None, wenn im Fenster kein Vergleichswert vorliegt."""
    if current is None:
        return None
    since = int(time.time()) - days * 86400
    row = con.execute(
        'SELECT price FROM price_history WHERE offer_id=? AND ok=1 AND price IS NOT NULL '
        'AND ts>=? ORDER BY ts ASC LIMIT 1', (offer_id, since)).fetchone()
    if not row or row['price'] is None:
        return None
    return current - row['price']


def _ai_digest_summary(offers, drops, rises, lows, under, trips, akc) -> str | None:
    """Kurze KI-Zusammenfassung des Wochenüberblicks als Fließtext (2-4 Sätze).
    Best effort: liefert None bei fehlendem Key oder jedem Fehler — blockiert den
    Versand nie. Läuft aus dem Poll-Hintergrund-Thread, daher `_ai_request` (kein
    Flask-App-Context nötig) statt `_ai_call`."""
    api_key, model = _ai_config()
    if not api_key:
        return None

    def nm(o):
        return o.get('label') or o.get('hotel') or f"Angebot #{o['id']}"

    lines = [f"{len(offers)} aktive Reise(n) beobachtet."]
    if trips:
        lines.append("Bevorstehende Reisen: " + "; ".join(
            f"{t['destination']} in {t['days_until']} Tagen" for t in trips[:5]))
    if under:
        lines.append("Unter Wunschpreis: " + "; ".join(
            f"{nm(o)} {_eur(o['price'])} (Ziel {_eur(o['target_price'])})" for o in under[:8]))
    if lows:
        lines.append("Neuer Tiefstwert: " + "; ".join(
            f"{nm(o)} {_eur(o['price'])}" for o in lows[:8]))
    if drops:
        lines.append("Größte Rückgänge (7 Tage): " + "; ".join(
            f"{nm(o)} {_eur(o['price'])} ({_eur(o['_wk'])})" for o in drops[:8]))
    if rises:
        lines.append("Gestiegen (7 Tage): " + "; ".join(
            f"{nm(o)} {_eur(o['price'])} (+{_eur(abs(o['_wk']))})" for o in rises[:5]))
    if akc:
        lines.append("Aktuelle TUI-Aktionscodes: " + "; ".join(
            f"{c.get('value')} € {c.get('code')}" for c in akc))
    if len(lines) == 1:
        return None  # nichts Nennenswertes außer der reinen Zählung

    prompt = (
        "Fasse folgenden wöchentlichen Reisepreis-Überblick in 2-4 knappen Sätzen "
        "auf Deutsch zusammen, sprich den Nutzer dabei mit „Du“ an (informell, nicht "
        "„Sie“) — für jemanden, der die Details gleich darunter noch in Listenform "
        "sieht. Hebe das Wichtigste hervor (größte Ersparnis, dringendste "
        "Gelegenheit); keine Wiederholung aller Einzelwerte, kein Fließtext-Vorspann "
        "wie 'Hier ist eine Zusammenfassung'.\n\n"
        + "\n".join(lines)
    )
    try:
        text, usage, code = _ai_request(api_key, model, prompt, max_tokens=500,
                                        log_ctx="Wochenüberblick", use_web_search=False)
        if code or not text:
            return None
        usage['estimated_usd'] = _ai_call_cost(model, usage)
        _record_ai_usage(model, usage)
        return text
    except Exception as e:
        log.warning("KI-Zusammenfassung für Wochenüberblick fehlgeschlagen: %s", e)
        return None


def _spawn(fn, *args) -> None:
    threading.Thread(target=fn, args=args, daemon=True).start()


# ── Auth-Helfer ────────────────────────────────────────────────────────────────

def _is_ingress() -> bool:
    return bool(request.script_root)


def _auth_ok(req) -> bool:
    if _is_ingress():
        return True  # HA Ingress authentifiziert selbst
    return is_valid_session(req.cookies.get('session'))


def _require_api():
    return None if _auth_ok(request) else (jsonify({'error': 'unauthorized'}), 401)


@app.after_request
def _slide_session(resp):
    """Sliding-Session: aktive Nutzung verlängert Ablauf & Cookie, statt exakt
    session_hours nach dem Login abzulaufen (siehe touch_session)."""
    if not _is_ingress():
        token = request.cookies.get('session')
        if token and is_valid_session(token):
            hours = int(load_config().get('session_hours', 24))
            touch_session(token, hours)
            resp.set_cookie('session', token, httponly=True, samesite='Lax',
                            max_age=hours * 3600)
    return resp


# ── Routen: Seiten ─────────────────────────────────────────────────────────────

@app.route('/health')
def health():
    return 'OK', 200


@app.route('/api/dbsize', methods=['GET'])
def api_dbsize():
    """Größe der SQLite-Datei für die Footer-Anzeige."""
    if (err := _require_api()):
        return err
    try:
        size = os.path.getsize(DB_PATH)
    except OSError:
        size = 0
    return jsonify({'bytes': size})


_giata_images_cache: dict = {}  # giata → {'ts': float, 'images': [...]}
_GIATA_IMAGES_TTL = 3600


@app.route('/api/giata_images/<giata>', methods=['GET'])
def api_giata_images(giata):
    """Bilder-URLs von der öffentlichen GIATA-Hotelseite für die Foto-Galerie —
    nur Links (i.giatamedia.com), Bilder werden nicht heruntergeladen/gespeichert."""
    if (err := _require_api()):
        return err
    cached = _giata_images_cache.get(giata)
    if cached and time.time() - cached['ts'] < _GIATA_IMAGES_TTL:
        return jsonify({'images': cached['images']})
    images = fetch_giata_image_urls(giata)
    _giata_images_cache[giata] = {'ts': time.time(), 'images': images}
    return jsonify({'images': images})


@app.route('/api/ai/usage', methods=['GET'])
def api_ai_usage():
    """Aufsummierte KI-Kosten (heute/Monat/gesamt) für die Footer-Anzeige — ohne
    selbst einen KI-Aufruf auszulösen."""
    if (err := _require_api()):
        return err
    return jsonify(_ai_usage_totals())


# ── PWA (installierbar) ──────────────────────────────────────────────────────────

@app.route('/manifest.json')
def manifest():
    root = request.script_root or ''
    resp = jsonify({
        'name': 'TUIWatch – Reisepreis-Tracker', 'short_name': 'TUIWatch',
        'lang': 'de', 'start_url': root + '/', 'scope': root + '/',
        'display': 'standalone', 'background_color': '#0d1117', 'theme_color': '#0d1117',
        'icons': [
            {'src': root + '/icon-192.png', 'sizes': '192x192', 'type': 'image/png',
             'purpose': 'any maskable'},
            {'src': root + '/icon-512.png', 'sizes': '512x512', 'type': 'image/png',
             'purpose': 'any maskable'},
        ],
    })
    resp.headers['Cache-Control'] = 'no-cache'
    return resp


_SW_JS = """const C='tuiwatch-v1';
self.addEventListener('install',e=>self.skipWaiting());
self.addEventListener('activate',e=>self.clients.claim());
self.addEventListener('fetch',e=>{
  if(e.request.method!=='GET') return;
  e.respondWith(fetch(e.request).then(r=>{
    try{ if(r&&r.ok){ const c=r.clone(); caches.open(C).then(x=>x.put(e.request,c)); } }catch(_){ }
    return r;
  }).catch(()=>caches.match(e.request)));
});
"""


@app.route('/sw.js')
def service_worker():
    resp = make_response(_SW_JS)
    resp.headers['Content-Type'] = 'application/javascript'
    resp.headers['Cache-Control'] = 'no-cache'
    return resp


@app.route('/icon-192.png')
def icon_192():
    return send_file(_BASE + '/icon-192.png')


@app.route('/icon-512.png')
def icon_512():
    return send_file(_BASE + '/icon-512.png')


@app.route('/login', methods=['GET', 'POST'])
def login():
    cfg = load_config()
    if _is_ingress() or is_valid_session(request.cookies.get('session')):
        return redirect(url_for('index'))
    error = None
    if request.method == 'POST':
        ip = get_client_ip(request)
        if is_rate_limited(ip):
            error = 'Zu viele Fehlversuche. Bitte 15 Minuten warten.'
        elif (request.form.get('username', '') == cfg.get('username', 'admin') and
              request.form.get('password', '') == cfg.get('password', 'secret')):
            clear_failed_attempts(ip)
            token = create_session(int(cfg.get('session_hours', 24)))
            resp = make_response(redirect(url_for('index')))
            resp.set_cookie('session', token, httponly=True, samesite='Lax',
                            max_age=int(cfg.get('session_hours', 24)) * 3600)
            return resp
        else:
            record_failed_attempt(ip)
            error = 'Ungültige Anmeldedaten.'
    return make_response(render_template('login.html', error=error,
                                         script_root=request.script_root))


@app.route('/logout')
def logout():
    token = request.cookies.get('session')
    if token in sessions:
        del sessions[token]
        save_sessions()
    resp = make_response(redirect('/login'))
    resp.delete_cookie('session')
    return resp


@app.route('/')
def index():
    if not _auth_ok(request):
        return redirect(url_for('login'))
    cfg = load_config()
    return make_response(render_template(
        'index.html', script_root=request.script_root,
        poll_interval=int(cfg.get('poll_interval', POLL_INTERVAL_DEFAULT)),
        ai_enabled=bool((cfg.get('anthropic_api_key') or '').strip()
                        or (cfg.get('gemini_api_key') or '').strip()),
        trippilot_home_location=(cfg.get('trippilot_home_location') or '').strip(),
        is_ingress=_is_ingress(),
        check24_enabled=bool(cfg.get('enable_check24_compare', False)),
        app_version=APP_VERSION))


# ── Routen: API ────────────────────────────────────────────────────────────────

def _auto_archive_expired() -> int:
    """Archiviert Angebote automatisch, deren Rückreisedatum in der Vergangenheit
    liegt. Solche Reisen lassen sich nicht mehr live abfragen — sie bleiben aber als
    Verlauf/Überblick erhalten. Gibt die Anzahl neu archivierter Angebote zurück."""
    today = time.strftime('%Y-%m-%d')
    with db() as con:
        rows = con.execute(
            "SELECT id, COALESCE(label,'') l, COALESCE(hotel,'') h FROM offers "
            "WHERE COALESCE(archived,0)=0 AND return_date IS NOT NULL "
            "AND return_date != '' AND return_date < ?", (today,)).fetchall()
        if rows:
            con.execute(
                "UPDATE offers SET archived=1 WHERE COALESCE(archived,0)=0 "
                "AND return_date IS NOT NULL AND return_date != '' AND return_date < ?",
                (today,))
    for r in rows:
        log.info("Angebot #%d (%s) automatisch archiviert (Reise abgelaufen)",
                 r['id'], r['l'] or r['h'] or f"#{r['id']}")
    return len(rows)


_OFFER_NIGHTS_RE = re.compile(r'^(\d+)\s*Nächte')


def _offer_nights(details: str) -> int | None:
    """Nächte-Anzahl aus dem 'details'-Text ('10 Nächte ab 18.09.2025 · ...') —
    kein eigenes DB-Feld, der Scraper schreibt sie nur als führenden Textteil.
    None, wenn nicht erkennbar (z. B. bei history_only-Altdaten)."""
    m = _OFFER_NIGHTS_RE.match((details or '').strip())
    return int(m.group(1)) if m else None


def _collect_offers() -> list[dict]:
    """Baut die Angebotsliste (mit letztem Preis, Delta, Statistik) — genutzt von
    der API, dem E-Mail-Versand und dem Übersichts-Sensor."""
    _auto_archive_expired()
    out = []
    with db() as con:
        offers = con.execute('SELECT * FROM offers ORDER BY id').fetchall()
        for o in offers:
            last = con.execute(
                'SELECT * FROM price_history WHERE offer_id=? ORDER BY ts DESC LIMIT 1',
                (o['id'],)).fetchone()
            prices = _last_two_prices(con, o['id'])
            delta = None
            if len(prices) == 2:
                delta = prices[0] - prices[1]
            last_ok_price = prices[0] if prices else None
            stats = con.execute(
                'SELECT MIN(price) mn, MAX(price) mx, AVG(price) av, COUNT(*) c '
                'FROM price_history WHERE offer_id=? AND ok=1 AND price IS NOT NULL',
                (o['id'],)).fetchone()
            # 30-Tage-Schnitt: ordnet den aktuellen Preis ein („8 % unter Ø 30 T")
            s30 = con.execute(
                'SELECT AVG(price) av, COUNT(*) c FROM price_history '
                'WHERE offer_id=? AND ok=1 AND price IS NOT NULL AND ts>=?',
                (o['id'], int(time.time()) - 30 * 86400)).fetchone()
            avg30 = round(s30['av']) if s30['c'] >= 2 and s30['av'] else None
            cur_price = last['price'] if last else None
            vs_avg30 = None
            if avg30 and cur_price is not None and s30['av']:
                vs_avg30 = round((cur_price - s30['av']) / s30['av'] * 100, 1)
            trend = _trend_for(con, o['id'])
            checking = o['id'] in _checking
            # Nur echte Bewegungen (>=2 bekannte Preise je Reisedatum) zaehlen als
            # Aenderung, nicht der allererste Kalender-Abruf (reine Baseline).
            cal_moves = _calendar_moves(con, o['id'])
            last_move_ts = max((v['ts'] for v in cal_moves.values()), default=0)
            calendar_alert = bool(last_move_ts and last_move_ts > (o['calendar_seen_ts'] or 0))
            avail = None
            if last and last['available'] is not None:
                avail = bool(last['available'])
            out.append({
                'id': o['id'], 'url': o['url'], 'label': o['label'],
                'hotel': o['hotel'], 'details': o['details'], 'room': o['room'],
                'nights': _offer_nights(o['details']),
                'dep_airport': o['dep_airport'],
                'flight_out': o['flight_out'], 'flight_ret': o['flight_ret'],
                'location': o['location'], 'city': o['city'],
                'region': o['region'], 'country': o['country'],
                'pdf_url': o['pdf_url'], 'image_url': o['image_url'] or '',
                'booking_code': o['booking_code'] or '',
                'room_booking_code': o['room_booking_code'] or '',
                'giata': _giata_from_url(o['url']),
                'total_price': o['total_price'],
                'travellers_count': o['travellers_count'],
                'paused': bool(o['paused']),
                'archived': bool(o['archived']),
                'notify_muted': bool(o['notify_muted']),
                'notify_calendar_muted': bool(o['notify_calendar_muted']),
                'history_only': bool(o['history_only']),
                'return_date': o['return_date'] or '',
                'tags': (_json_loads_safe(o['tags'], []) if o['tags'] else []),
                'cancellation': o['cancellation'], 'stars': o['stars'],
                'rating': o['rating'], 'rating_count': o['rating_count'],
                'recommendation': o['recommendation'],
                'target_price': o['target_price'],
                'booked_price': o['booked_price'],
                'price': last['price'] if last else None,
                'last_ok_price': last_ok_price,
                'old_price': last['old_price'] if last else None,
                'discount': last['discount'] if last else None,
                'available': avail,
                'ok': bool(last['ok']) if last else None,
                'note': last['note'] if last else '',
                'last_ts': last['ts'] if last else None,
                'delta': delta,
                'min_price': stats['mn'], 'max_price': stats['mx'],
                'avg_price': round(stats['av']) if stats['av'] is not None else None,
                'samples': stats['c'],
                'avg30_price': avg30, 'vs_avg30': vs_avg30,
                'trend': trend,
                'checking': checking,
                'calendar_alert': calendar_alert,
                'comparable': not is_single_room(f"{o['room']} {o['details']}"),
                'board': o['board'] or '',
                'check24_linked': bool(o['check24_hotel_id']),
            })
    return out


@app.route('/api/healthcheck', methods=['GET', 'POST'])
def api_healthcheck_route():
    """GET: letztes Selbsttest-Ergebnis (oder noch leer). POST: neuen Selbsttest
    starten und auf das Ergebnis warten."""
    if (err := _require_api()):
        return err
    if request.method == 'POST':
        return jsonify(_run_healthcheck())
    with _health_lock:
        st = dict(_health_state)
    return jsonify(st)


@app.route('/api/market-trend')
def api_market_trend():
    """Marktweiter Preistrend über alle geprüften Angebote: ein rollierendes 14-Tage-
    Fenster (`trend`, reagiert auf aktuelle Bewegung) sowie ein Index seit Beginn der
    Aufzeichnung (`index`, Basis 100 — fängt auch langsame Bewegungen über mehrere
    Wochen), jeweils global und aufgeschlüsselt nach Destination.
    `basket` ergänzt dieselben Kennzahlen aus dem täglichen Regions-Warenkorb
    (`market_basket`) — gleiche Datenform, aber auf Basis aller Hotels einer Region
    statt nur der eigenen getrackten Angebote."""
    if (err := _require_api()):
        return err
    with db() as con:
        regions = [r['region'] for r in con.execute(
            "SELECT DISTINCT region FROM price_moves WHERE region!=''").fetchall()]
        glob = {'trend': _market_trend(con), 'index': _market_index(con)}
        by_region = []
        for r in sorted(regions):
            t, i = _market_trend(con, region=r), _market_index(con, region=r)
            if t or i:
                by_region.append({'region': r, 'trend': t, 'index': i})
    return jsonify({'global': glob, 'by_region': by_region,
                    'basket': market_basket.basket_payload()})


@app.route('/api/market-trend/recompute', methods=['POST'])
def api_market_trend_recompute():
    """Markttrend komplett neu aus `price_history`/`offer_events` aufbauen — z. B.
    nachdem ein Zimmerwechsel-Preissprung fälschlich mitgezählt wurde (vor einer
    Korrektur an der Berechnungslogik) oder um eine spätere Fehlerbehebung rückwirkend
    auf die bereits gesammelten Daten anzuwenden, ohne sie komplett zu verlieren."""
    if (err := _require_api()):
        return err
    with db() as con:
        con.execute('DELETE FROM price_moves')
        _backfill_price_moves(con)
        n = con.execute('SELECT COUNT(*) c FROM price_moves').fetchone()['c']
    log.info("Markttrend neu berechnet: %d Datenpunkte", n)
    return jsonify({'recomputed': n})


@app.route('/api/market-trend/region', methods=['DELETE'])
def api_market_trend_region_delete():
    """Markttrend-Daten EINER Destination löschen — Neustart der Aufzeichnung für
    diese Region (z. B. nach verfälschten Datenpunkten), die übrigen Regionen
    bleiben unberührt. Hinweis: ein späteres „Neu berechnen" baut ALLE Regionen
    aus dem Preisverlauf neu auf und stellt die Punkte damit wieder her."""
    if (err := _require_api()):
        return err
    region = ((request.get_json(silent=True) or {}).get('region') or '').strip()
    if not region:
        return jsonify({'error': 'invalid'}), 400
    with db() as con:
        n = con.execute('DELETE FROM price_moves WHERE region=?', (region,)).rowcount
    log.info("Markttrend-Daten für Region „%s“ gelöscht: %d Datenpunkte", region, n)
    return jsonify({'deleted': n, 'region': region})


@app.route('/api/digest', methods=['POST'])
def api_digest():
    """Verschickt den Wochenüberblick sofort (Test/Sofortversand)."""
    if (err := _require_api()):
        return err
    sent = send_digest_now()
    if sent:
        return jsonify({'sent': True})
    return jsonify({'sent': False, 'note': 'Nichts zu berichten oder kein Kanal '
                    '(Telegram/SMTP) konfiguriert.'})


@app.route('/api/console')
def api_console():
    if (err := _require_api()):
        return err
    return jsonify({'lines': list(_log_buffer)})


@app.route('/api/notifications', methods=['GET'])
def api_notifications():
    """Verlauf der gesendeten Benachrichtigungen (HA/Telegram), neueste zuerst."""
    if (err := _require_api()):
        return err
    with db() as con:
        rows = con.execute(
            'SELECT ts, channel, title, message, tag, ok FROM notify_log '
            'ORDER BY id DESC LIMIT 200').fetchall()
    return jsonify({'items': [dict(r) for r in rows]})


@app.route('/api/errors', methods=['GET'])
def api_errors():
    """Letzte Warnungen/Fehler aus dem In-Memory-Puffer (seit Add-on-Start),
    neueste zuerst — Diagnose ohne HA-Log."""
    if (err := _require_api()):
        return err
    return jsonify({'items': list(reversed(_warn_buffer))})


# Läuft app.py als Skript (run.sh: `python3 app.py`), heißt DIESES Modul
# '__main__' — `import app` in den Blueprint-Modulen würde app.py dann ein
# ZWEITES Mal ausführen (Doppel-Initialisierung + Zirkular-Crash beim
# register_blueprint, live in 0.48.2 passiert). Alias registrieren, damit
# '__main__' und 'app' dasselbe Modul-Objekt sind; unter pytest (Import als
# 'app') ist der Alias ein No-Op.
import sys  # noqa: E402
sys.modules.setdefault('app', sys.modules[__name__])

import ai_client  # noqa: E402
_ai_request = ai_client._ai_request
_ai_request_messages = ai_client._ai_request_messages
_ai_request_anthropic = ai_client._ai_request_anthropic
_ai_request_anthropic_messages = ai_client._ai_request_anthropic_messages
_GEMINI_REFUSAL_REASONS = ai_client._GEMINI_REFUSAL_REASONS
_gemini_sanitize_schema = ai_client._gemini_sanitize_schema
_GEMINI_THINKING_TOKEN_RESERVE = ai_client._GEMINI_THINKING_TOKEN_RESERVE
_ai_request_gemini = ai_client._ai_request_gemini
_ai_request_gemini_messages = ai_client._ai_request_gemini_messages
_ai_request_perplexity = ai_client._ai_request_perplexity
_ai_request_perplexity_messages = ai_client._ai_request_perplexity_messages
_ai_call = ai_client._ai_call
_ai_call_messages = ai_client._ai_call_messages

import price_calendar  # noqa: E402
app.register_blueprint(price_calendar.bp)
_store_calendar_snapshot = price_calendar._store_calendar_snapshot
_MONTH_NAMES_DE = price_calendar._MONTH_NAMES_DE
_month_name_de = price_calendar._month_name_de
_format_month_list_de = price_calendar._format_month_list_de
_check_calendar_trend_alert = price_calendar._check_calendar_trend_alert
_run_calendar = price_calendar._run_calendar
_calendar_moves = price_calendar._calendar_moves
_calendar_top_moves = price_calendar._calendar_top_moves
_calendar_date_history = price_calendar._calendar_date_history
_calendar_moves_since = price_calendar._calendar_moves_since
_calendar_payload = price_calendar._calendar_payload
api_calendar_start = price_calendar.api_calendar_start
api_calendar_get = price_calendar.api_calendar_get
api_calendar_day_history = price_calendar.api_calendar_day_history

import watch  # noqa: E402
app.register_blueprint(watch.bp)
_search_from_fav_payload = watch._search_from_fav_payload
_esc_html = watch._esc_html
_notify_search_watch = watch._notify_search_watch
_check_search_watch = watch._check_search_watch
_maybe_check_watches = watch._maybe_check_watches
api_searches = watch.api_searches
api_searches_delete = watch.api_searches_delete
api_searches_patch = watch.api_searches_patch
api_searches_check = watch.api_searches_check

import ai_routes  # noqa: E402
app.register_blueprint(ai_routes.bp)
_contacts_cache = ai_routes._contacts_cache
_airports_cache = ai_routes._airports_cache
_dest_cache = ai_routes._dest_cache
_AI_SECTIONS = ai_routes._AI_SECTIONS
_CUSTOM_PROMPT_MAX_LEN = ai_routes._CUSTOM_PROMPT_MAX_LEN
_DEFAULT_ADVISOR_INSTRUCTIONS = ai_routes._DEFAULT_ADVISOR_INSTRUCTIONS
_ADVISOR_SAFETY_TRAILER = ai_routes._ADVISOR_SAFETY_TRAILER
_DEFAULT_COMPARE_INSTRUCTIONS = ai_routes._DEFAULT_COMPARE_INSTRUCTIONS
_DEFAULT_SUMMARY_INSTRUCTIONS = ai_routes._DEFAULT_SUMMARY_INSTRUCTIONS
_DAYTRIP_REGION_VALUE = ai_routes._DAYTRIP_REGION_VALUE
_region_values = ai_routes._region_values
_DEFAULT_DAYTRIP_INSTRUCTIONS = ai_routes._DEFAULT_DAYTRIP_INSTRUCTIONS
_PROMPT_FEATURES = ai_routes._PROMPT_FEATURES
_hotel_fact_lines = ai_routes._hotel_fact_lines
_AI_PRICING = ai_routes._AI_PRICING
_ai_call_cost = ai_routes._ai_call_cost
_ai_usage_calc = ai_routes._ai_usage_calc
_ai_usage_period_calc = ai_routes._ai_usage_period_calc
_ai_usage_totals = ai_routes._ai_usage_totals
_record_ai_usage_bucket = ai_routes._record_ai_usage_bucket
_record_ai_usage = ai_routes._record_ai_usage
_AI_HISTORY_MAX = ai_routes._AI_HISTORY_MAX
_save_ai_analysis = ai_routes._save_ai_analysis
_ai_active_provider = ai_routes._ai_active_provider
_ai_config = ai_routes._ai_config
_ai_config_for = ai_routes._ai_config_for
_AI_TAG_VOCAB = ai_routes._AI_TAG_VOCAB
_AI_TAG_SCHEMA = ai_routes._AI_TAG_SCHEMA
_ai_auto_tags = ai_routes._ai_auto_tags
api_ai_auto_tags = ai_routes.api_ai_auto_tags
_BOOKING_SCORE_SCHEMA = ai_routes._BOOKING_SCORE_SCHEMA
_BOOKING_SCORE_INSTRUCTIONS = ai_routes._BOOKING_SCORE_INSTRUCTIONS
_calendar_seasonal_summary = ai_routes._calendar_seasonal_summary
_offer_booking_facts = ai_routes._offer_booking_facts
_calendar_outlook_facts = ai_routes._calendar_outlook_facts
_CALENDAR_OUTLOOK_INSTRUCTIONS = ai_routes._CALENDAR_OUTLOOK_INSTRUCTIONS
_calendar_outlook_prompt = ai_routes._calendar_outlook_prompt
_booking_score_prompt = ai_routes._booking_score_prompt
_region_outlook_prompt = ai_routes._region_outlook_prompt
_hotel_summary_prompt = ai_routes._hotel_summary_prompt
api_ai_hotel_summary = ai_routes.api_ai_hotel_summary
_ai_score_request = ai_routes._ai_score_request
api_ai_calendar_outlook = ai_routes.api_ai_calendar_outlook
api_ai_booking_score = ai_routes.api_ai_booking_score
api_ai_region_outlook = ai_routes.api_ai_region_outlook
api_ai_ask = ai_routes.api_ai_ask
api_ai_prompt_settings = ai_routes.api_ai_prompt_settings
api_ai_provider = ai_routes.api_ai_provider
_ADVISOR_FIELDS = ai_routes._ADVISOR_FIELDS
_ADVISOR_LIST_FIELDS = ai_routes._ADVISOR_LIST_FIELDS
_ADVISOR_TEXT_FIELDS = ai_routes._ADVISOR_TEXT_FIELDS
_ADVISOR_LABELS = ai_routes._ADVISOR_LABELS
_advisor_prompt = ai_routes._advisor_prompt
_advisor_dna_scores = ai_routes._advisor_dna_scores
_advisor_dna_update = ai_routes._advisor_dna_update
_advisor_dna_table = ai_routes._advisor_dna_table
api_ai_travel_advisor = ai_routes.api_ai_travel_advisor
_compare_prompt = ai_routes._compare_prompt
api_ai_hotel_compare = ai_routes.api_ai_hotel_compare
_ai_md_to_html = ai_routes._ai_md_to_html
api_ai_email = ai_routes.api_ai_email
api_ai_history = ai_routes.api_ai_history
api_ai_history_get = ai_routes.api_ai_history_get
api_ai_history_delete = ai_routes.api_ai_history_delete
_AI_RETRY_MARKDOWN_CONFIG = ai_routes._AI_RETRY_MARKDOWN_CONFIG
api_ai_history_repeat = ai_routes.api_ai_history_repeat

def _table_columns(con, table: str) -> list:
    return [r['name'] for r in con.execute(f'PRAGMA table_info({table})').fetchall()]


# ── Automatisches Backup (nach /config = addon_config) ─────────────────────────

BACKUP_DIR = os.environ.get('TUIWATCH_BACKUP_DIR', '/config/backups')




# ── Reisen-Datenbank (gebuchte Reisen via PDF-Import) ───────────────────────────

def _parse_eur_num(s):
    """'1.736,00' -> 1736.0 ; None bei leer/0 (für saubere Statistik-Summen)."""
    v = _parse_eur(s)
    return v if v else None


def _iso_date(de: str):
    """'14.01.2027' -> '2027-01-14' (sortierbar); None bei Fehler."""
    if not de:
        return None
    try:
        return datetime.strptime(de.strip(), '%d.%m.%Y').strftime('%Y-%m-%d')
    except (ValueError, AttributeError):
        return None


def _trip_pdf_path(pdf_name: str):
    """Sicheren Pfad zur Reise-PDF im TRIPS_DIR liefern (Path-Traversal-Schutz).
    Gibt None zurück, wenn der Name unzulässig ist oder aus dem TRIPS_DIR ausbräche."""
    if not pdf_name:
        return None
    name = Path(pdf_name).name
    if not re.fullmatch(r'[A-Za-z0-9._-]{1,120}', name):
        return None
    joined = safe_join(str(TRIPS_DIR), name)
    return Path(joined) if joined is not None else None


def _trip_title(data: dict) -> str:
    """'Gran Canaria 2026' o. Ä. aus Reiseziel/Hotel + Reisejahr."""
    ziel = (data.get('reiseziel') or data.get('hotel', {}).get('name') or 'Reise').strip()
    von = (data.get('reisezeitraum') or {}).get('von') or ''
    jahr = von[-4:] if len(von) >= 4 else ''
    return f"{ziel} {jahr}".strip()


# Erlaubte Spalten der trips-Tabelle (feste Whitelist, exakte Insert-/Update-Reihenfolge).
# Bewusst als Konstante, damit CodeQL sieht: die SQL-Struktur stammt aus Code, nicht aus
# Daten. Bleibt in app.py: Backup/Restore UND trips_routes nutzen sie.
_TRIP_COLUMNS = (
    'booking_code', 'booking_date', 'title', 'destination', 'hotel', 'hotel_code',
    'start_date', 'end_date', 'nights', 'travellers', 'total_price', 'package_price',
    'net_per_night', 'meal', 'data', 'pdf_name', 'orig_name', 'created',
)


def _trip_departure(row) -> tuple[datetime | None, bool]:
    """Abflug-Datetime einer Reise: Hinflug-Zeit aus data.fluege, sonst 00:00 des
    Reisebeginns. Rückgabe (datetime|None, has_time)."""
    try:
        data = json.loads(row['data'] or '{}')
    except (json.JSONDecodeError, TypeError):
        data = {}
    dep_time = next((f.get('abflug_zeit') for f in data.get('fluege') or []
                      if f.get('typ') == 'Hinflug'), None)
    try:
        return (datetime.fromisoformat(f"{row['start_date']}T{dep_time or '00:00'}:00"),
                dep_time is not None)
    except ValueError:
        return None, False


def _next_trip() -> dict | None:
    """Nächste bevorstehende Reise (Abflug in der Zukunft) fürs Header-Countdown."""
    today = date.today().isoformat()
    with db() as con:
        rows = con.execute(
            'SELECT id, destination, hotel, start_date, data FROM trips '
            'WHERE start_date >= ? ORDER BY start_date ASC LIMIT 5', (today,)).fetchall()
    now = datetime.now()
    for r in rows:
        dep_dt, has_time = _trip_departure(r)
        if dep_dt and dep_dt >= now:
            return {'destination': r['destination'] or r['hotel'] or '',
                    'departure': dep_dt.isoformat(), 'has_time': has_time}
    return None


def _upcoming_trips(limit: int = 10) -> list[dict]:
    """Alle bevorstehenden Reisen (Abflug in der Zukunft), sortiert nach Startdatum —
    für den Wochen-Digest (Header zeigt nur die nächste, hier alle künftigen)."""
    today = date.today().isoformat()
    with db() as con:
        rows = con.execute(
            'SELECT destination, hotel, start_date, end_date, nights, data FROM trips '
            'WHERE start_date >= ? ORDER BY start_date ASC LIMIT ?', (today, limit)).fetchall()
    now = datetime.now()
    out = []
    for r in rows:
        dep_dt, has_time = _trip_departure(r)
        if not dep_dt or dep_dt < now:
            continue
        out.append({
            'destination': r['destination'] or r['hotel'] or '',
            'hotel': r['hotel'] or '', 'start_date': r['start_date'],
            'end_date': r['end_date'], 'nights': r['nights'],
            'departure': dep_dt.isoformat(), 'has_time': has_time,
            'days_until': (dep_dt.date() - date.today()).days,
        })
    return out




import offers_routes  # noqa: E402
app.register_blueprint(offers_routes.bp)
api_offers = offers_routes.api_offers
_normalize_tags = offers_routes._normalize_tags
_valid_tui_url = offers_routes._valid_tui_url
api_add_offer = offers_routes.api_add_offer
api_start_offer = offers_routes.api_start_offer
api_delete_offer = offers_routes.api_delete_offer
api_update_offer = offers_routes.api_update_offer
api_history = offers_routes.api_history
api_history_csv = offers_routes.api_history_csv
api_check_one = offers_routes.api_check_one
api_reset_offer = offers_routes.api_reset_offer
api_check_now = offers_routes.api_check_now
api_email = offers_routes.api_email
_HISTORY_COLS = offers_routes._HISTORY_COLS
_EVENT_COLS = offers_routes._EVENT_COLS
_OFFER_RESTORE_COLS = offers_routes._OFFER_RESTORE_COLS
api_compare_start = offers_routes.api_compare_start
api_compare_get = offers_routes.api_compare_get
api_nights_start = offers_routes.api_nights_start
api_nights_get = offers_routes.api_nights_get
api_search = offers_routes.api_search
_DEST_INDEX_TTL = offers_routes._DEST_INDEX_TTL
_dest_index_lock = offers_routes._dest_index_lock
_dest_index_building = offers_routes._dest_index_building
_load_dest_index = offers_routes._load_dest_index
_build_dest_index = offers_routes._build_dest_index
_ensure_dest_index = offers_routes._ensure_dest_index
_search_dest_index = offers_routes._search_dest_index
api_destinations = offers_routes.api_destinations
api_destinations_search = offers_routes.api_destinations_search
api_destinations_reindex = offers_routes.api_destinations_reindex
api_airports = offers_routes.api_airports
api_contacts = offers_routes.api_contacts
api_airlines = offers_routes.api_airlines
api_rooms_get = offers_routes.api_rooms_get
api_rooms_set = offers_routes.api_rooms_set

# Route-Module (Blueprints) — erst hier importieren: sie greifen per
# `import app as A` auf die oben definierten Primitiven zu.
import trips_routes  # noqa: E402
import backup_routes  # noqa: E402
import check24_routes  # noqa: E402
import market_basket  # noqa: E402
app.register_blueprint(trips_routes.bp)
app.register_blueprint(backup_routes.bp)
app.register_blueprint(check24_routes.bp)
app.register_blueprint(market_basket.bp)

# Warenkorb-Markttrend: `init_db` und der Poll-Worker greifen oben schon auf
# `market_basket` zu — beides läuft erst zur Laufzeit, da ist der Import hier durch.
basket_trend = market_basket.basket_trend
basket_index = market_basket.basket_index
basket_payload = market_basket.basket_payload
run_baskets = market_basket.run_baskets
run_basket = market_basket.run_basket
maybe_run_baskets = market_basket.maybe_run_baskets

# Rückwärtskompatible Re-Exports: der Poller (oben) und die Tests sprechen die
# Auto-Backup-Funktionen weiter über den app-Namespace an (monkeypatch-Ziel).
_run_auto_backup = backup_routes._run_auto_backup
_maybe_auto_backup = backup_routes._maybe_auto_backup
import digest  # noqa: E402
_build_digest = digest._build_digest
send_digest_now = digest.send_digest_now
_maybe_send_digest = digest._maybe_send_digest

# ── Start ──────────────────────────────────────────────────────────────────────

def _aktionscodes_sensor_worker() -> None:
    """Meldet den Coupon-Sensor alle 2 Minuten erneut aus dem Cache an HA — ein
    HA-Neustart wirft den Sensor aus HAs State-Machine, das Add-on selbst läuft
    dabei aber weiter und merkt davon nichts. Ohne diesen Timer bliebe der Sensor
    bis zum nächsten Live-Abruf (Stunden) bzw. Add-on-Neustart verschwunden."""
    while True:
        try:
            _push_aktionscodes_sensor_from_cache()
        except Exception as e:
            log.warning("Coupon-Sensor-Refresh fehlgeschlagen: %s", e)
        time.sleep(120)


def _health_sensor_worker() -> None:
    """Wie `_aktionscodes_sensor_worker`, aber für den API-Verfügbar-Sensor: meldet
    das letzte Selbsttest-Ergebnis alle 2 Minuten erneut, damit er einen HA-Neustart
    übersteht, obwohl der Selbsttest selbst nur ~1×/Tag läuft."""
    while True:
        try:
            _push_health_sensor_from_cache()
        except Exception as e:
            log.warning("API-Sensor-Refresh fehlgeschlagen: %s", e)
        time.sleep(120)


def _cooldown_sensor_worker() -> None:
    """Meldet den Cooldown-Sensor alle 5 Sekunden an HA — kurzes Intervall, weil der
    Cooldown selbst nur 60s dauert und sowohl den HA-Neustart überstehen als auch
    beim Ablauf zeitnah von selbst auf 'off' gehen soll."""
    while True:
        try:
            _push_cooldown_sensor()
        except Exception as e:
            log.warning("Cooldown-Sensor-Refresh fehlgeschlagen: %s", e)
        time.sleep(5)


def _market_trend_sensor_worker() -> None:
    """Meldet den Markttrend-Sensor alle 2 Minuten neu — die zugrunde liegenden Daten
    ändern sich zwar langsam (neue Punkte nur je Poll-Intervall pro Angebot), aber
    states-API-Sensoren wie dieser überleben einen HA-Core-Neustart NICHT von selbst
    (verschwinden aus der State Machine, bis neu gepostet wird). Wie bei
    `_health_sensor_worker`/`_aktionscodes_sensor_worker` hält das kurze Intervall
    das Zeitfenster klein, in dem der Sensor nach einem HA-Neustart 'nicht verfügbar'
    statt seines letzten Werts zeigt."""
    while True:
        try:
            _push_market_trend_sensor()
        except Exception as e:
            log.warning("Markttrend-Sensor-Refresh fehlgeschlagen: %s", e)
        time.sleep(120)


def _handle_sigterm(signum, frame) -> None:
    """Sauberer Exit bei SIGTERM (HA-Supervisor-Stop/Update) — ohne eigenen Handler
    würde Python den Default-Handler laufen lassen (exit 143), worüber sich der
    Supervisor beschwert ("should trap SIGTERM ... exit with code 0"). Alle
    Hintergrund-Threads sind daemon=True (siehe main()), ein harter os._exit(0)
    ist daher sicher — kein offener State, der noch geflusht werden müsste
    (DB-Schreibzugriffe committen bereits pro `with db() as con:`-Block)."""
    log.info("SIGTERM empfangen, beende sauber…")
    os._exit(0)


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_sigterm)
    init_db()
    load_sessions()
    _spawn(push_ha_sensors)  # vorhandene Preise sofort als Sensoren melden
    _spawn(_notify_startup)  # kurze Telegram-Statusmeldung (falls konfiguriert)
    _spawn(_run_healthcheck)  # API-Erreichbarkeit beim Start prüfen
    _spawn(_ensure_dest_index)  # Reiseziel-Index (globale Suche) laden/aufbauen
    threading.Thread(target=_poll_worker, daemon=True).start()
    threading.Thread(target=_aktionscodes_sensor_worker, daemon=True).start()
    threading.Thread(target=_health_sensor_worker, daemon=True).start()
    threading.Thread(target=_cooldown_sensor_worker, daemon=True).start()
    threading.Thread(target=_market_trend_sensor_worker, daemon=True).start()
    port = int(os.environ.get('TUIWATCH_PORT', '17794'))
    log.info("TUIWatch startet auf Port %d", port)
    # Werkzeugs Dev-Server (app.run) verzoegert unter Last durch die Hintergrund-
    # Worker (Poller, Aktionscodes, Health, ...) neue Verbindungen spuerbar —
    # der externe cert_expiry-Sensor lief deshalb wiederholt in Timeouts.
    # waitress bedient eingehende Requests ueber einen eigenen Thread-Pool,
    # unabhaengig von der Auslastung der Hintergrund-Threads.
    # threads=8 reichte nicht: _scrape_lock/_check24_scrape_lock serialisieren
    # fetch_price ueber Poller UND manuelle UI-Aktionen (Zimmer-/Naechte-Vergleich)
    # hinweg, mehrere gleichzeitige Lock-Waits konnten alle Threads belegen und
    # neue Verbindungen (inkl. Docker-HEALTHCHECK) blockieren.
    serve(app, host='0.0.0.0', port=port, threads=32)


if __name__ == '__main__':
    main()
