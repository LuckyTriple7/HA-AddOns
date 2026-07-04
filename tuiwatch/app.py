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
import smtplib
import sqlite3
import threading
import time
import zipfile
from collections import defaultdict, deque
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from urllib.parse import quote, urlparse

import anthropic
import requests as http
from flask import (Flask, jsonify, make_response, redirect, render_template,
                   request, send_file, url_for)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import safe_join

from scraper import (_giata_from_url, _valid_img_url, api_healthcheck,
                     build_destination_index,
                     duration_from_url, fetch_airlines, fetch_airports,
                     fetch_calendar, fetch_destinations, fetch_hotel_image,
                     fetch_price, fetch_rooms, fetch_search, fetch_search_params,
                     hotel_from_url, is_single_room, region_giata_from_breadcrumb,
                     room_code_from_url, travellers_from_url, with_duration,
                     with_room_code, with_travellers, without_room_code)
from aktionscodes import fetch_aktionscodes
from nextcloud import fetch_contacts
from packliste import default_packing_rows
from tripparser import (_clean_text, _parse_eur, check_fields, extract_pdf_text,
                        parse_tui_pdf, parse_tui_text)

logging.basicConfig(format='[%(levelname)s] [%(asctime)s] %(message)s',
                    level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S', force=True)
log = logging.getLogger(__name__)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# ── In-App Log-Buffer (für Konsole im UI) ──────────────────────────────────────
_log_buffer: deque = deque(maxlen=200)


class _BufferHandler(logging.Handler):
    _fmt = logging.Formatter('[%(levelname)s] [%(asctime)s] %(message)s',
                             datefmt='%Y-%m-%d %H:%M:%S')

    def emit(self, record):
        try:
            _log_buffer.append({'ts': int(record.created * 1000),
                                'level': record.levelname,
                                'msg': self._fmt.format(record)})
        except Exception:
            pass


logging.getLogger().addHandler(_BufferHandler())

APP_VERSION = "0.39.23"  # muss mit config.yaml/version bei jedem Bump mitgezogen werden

# ── Pfade / Flask ──────────────────────────────────────────────────────────────
_BASE = os.environ.get('TUIWATCH_BASE', '/app')
_DATA = os.environ.get('TUIWATCH_DATA', '/data')
CONFIG_PATH = _DATA + '/options.json'
SESSIONS_PATH = _DATA + '/sessions.json'
DB_PATH = _DATA + '/tuiwatch.db'
TRIPS_DIR = _DATA + '/trips'   # dauerhaft gespeicherte Reise-PDFs

POLL_INTERVAL_DEFAULT = 21600  # 6h — Reisepreise ändern sich langsam
MIN_POLL_INTERVAL = 600        # nie öfter als alle 10 min (Bot-Schutz/Fairness)
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
_aktion_state: dict = {}               # transienter Status des Aktionscode-Abrufs {running|error|ts}
_aktion_lock = threading.Lock()
_cheaper_notified: dict[int, str] = {}  # Dedup für Günstigerer-Termin-Alarm
_fail_notified: set[int] = set()        # offer_ids mit aktivem Ausverkauft-/Fehler-Alarm
ERROR_ALARM_STREAK = 3                   # ab so vielen Fehlversuchen in Folge melden
_health_state: dict = {}                 # letzter API-Selbsttest {ok, ts, checks, running}
_health_lock = threading.Lock()
_ai_summary_cache: dict = {}              # giata/Name → {summary, ts} — spart wiederholte API-Calls
_AI_SUMMARY_TTL = 24 * 3600
_AI_MODELS = ('claude-opus-4-8', 'claude-sonnet-5', 'claude-haiku-4-5', 'claude-fable-5')
_api_down_notified = False                # ob aktuell ein API-Ausfall gemeldet ist

# einfache Login-Drossel
_failed_attempts: dict[str, list[float]] = defaultdict(list)
_blocked_ips: dict[str, float] = {}
RATE_LIMIT_MAX, RATE_LIMIT_WINDOW, RATE_LIMIT_BLOCK = 5, 600, 900


# ── Config & Sessions ──────────────────────────────────────────────────────────

def load_config() -> dict:
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
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
            return_date  TEXT DEFAULT '',
            target_price REAL,
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
        con.execute('''CREATE TABLE IF NOT EXISTS nights_cache (
            offer_id INTEGER PRIMARY KEY,
            ts       INTEGER NOT NULL,
            base     INTEGER,
            span     INTEGER,
            rows     TEXT NOT NULL DEFAULT '[]',
            FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE CASCADE
        )''')
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
                    'booking_code', 'room_booking_code', 'tags'):
            if col not in ocols:
                con.execute(f"ALTER TABLE offers ADD COLUMN {col} TEXT DEFAULT ''")
        for col in ('target_price', 'booked_price', 'stars', 'rating', 'total_price'):
            if col not in ocols:
                con.execute(f"ALTER TABLE offers ADD COLUMN {col} REAL")
        for col in ('rating_count', 'recommendation', 'travellers_count',
                    'paused', 'archived'):
            if col not in ocols:
                con.execute(f"ALTER TABLE offers ADD COLUMN {col} INTEGER")
        hcols = {r['name'] for r in con.execute('PRAGMA table_info(price_history)').fetchall()}
        if 'available' not in hcols:
            con.execute("ALTER TABLE price_history ADD COLUMN available INTEGER")
        # Backfill: Hotelname aus der URL für Einträge ohne Namen
        for r in con.execute("SELECT id, url FROM offers WHERE hotel='' OR hotel IS NULL").fetchall():
            name = hotel_from_url(r['url'])
            if name:
                con.execute('UPDATE offers SET hotel=? WHERE id=?', (name, r['id']))
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
    """Meldet je Angebot einen Sensor an HA: Wert=Preis (€) bzw. 'unavailable',
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
                state = int(round(last['price'])) if ok else 'unavailable'
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
            s_state = 'unavailable'
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

def _notify_ha(title: str, message: str, tag: str) -> None:
    if not (SUPERVISOR_TOKEN and load_config().get('notify_ha', True)):
        return
    try:
        http.post(f'{HA_BASE}/services/persistent_notification/create',
                  headers={'Authorization': f'Bearer {SUPERVISOR_TOKEN}'}, timeout=10,
                  json={'title': title, 'message': message, 'notification_id': f'tuiwatch_{tag}'})
    except Exception as e:
        log.error("HA-Benachrichtigung fehlgeschlagen: %s", e)


def _notify_telegram(text: str) -> None:
    cfg = load_config()
    token = (cfg.get('telegram_bot_token') or '').strip()
    chat = (cfg.get('telegram_chat_id') or '').strip()
    if not (token and chat):
        return
    try:
        http.post(f'https://api.telegram.org/bot{token}/sendMessage', timeout=10,
                  json={'chat_id': chat, 'text': text, 'parse_mode': 'HTML',
                        'disable_web_page_preview': True})
    except Exception as e:
        log.error("Telegram-Benachrichtigung fehlgeschlagen: %s", e)


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
            codeparts.append(f'GIATA {esc(o["giata"])}')
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
    except Exception:
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

    # 1) Wunschpreis erreicht (nur beim Übergang über die Schwelle)
    if target and new_price <= target and (prev_price is None or prev_price > target):
        title = f"🎯 Wunschpreis erreicht: {name}"
        msg = f"{name}\nWunschpreis {_eur(target)} erreicht — jetzt {_eur(new_price)}\n{url}"
        log.info("🎯 Wunschpreis erreicht (#%d %s): %s ≤ %s → Benachrichtigung",
                 offer['id'], name, _eur(new_price), _eur(target))
        _notify_ha(title, msg, f"target_{offer['id']}")
        _notify_telegram(f"🎯 <b>Wunschpreis erreicht</b>\n{name}\nJetzt <b>{_eur(new_price)}</b> "
                         f"(Ziel {_eur(target)})\n{url}")
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
        _notify_ha(title, msg, f"change_{offer['id']}")
        _notify_telegram(f"{'📉' if diff<0 else '📈'} <b>{name}</b>\n"
                         f"{_eur(prev_price)} → <b>{_eur(new_price)}</b> ({arrow})\n{url}")


def _check_cheaper_date(offer: dict, current_price: float) -> None:
    """Holt den Preiskalender (frischt zugleich den Cache auf) und meldet, wenn ein
    anderer Abreisetag deutlich günstiger ist als der getrackte Preis."""
    cfg = load_config()
    cal = fetch_calendar(offer['url'], verbose=_verbose())
    if not cal or not cal.get('ok'):
        return
    try:
        with db() as con:
            con.execute('INSERT OR REPLACE INTO calendar_cache (offer_id, ts, data) '
                        'VALUES (?,?,?)', (offer['id'], int(time.time()), json.dumps(cal)))
    except Exception as e:
        log.warning("Kalender-Cache #%d nicht aktualisiert: %s", offer['id'], e)
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
    oid = offer['id']
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
    log.info("💡 Günstigerer Termin (#%d %s): %s am %s (%s günstiger) → Benachrichtigung",
             offer['id'], name, _eur(cp), d_de, _eur(diff))
    _notify_ha(f"💡 Günstigerer Termin: {name}",
               f"{name}\nAm {d_de} nur {_eur(cp)} — {_eur(diff)} günstiger als dein "
               f"Termin ({_eur(current_price)})\n{offer.get('url','')}",
               f"cheaper_{offer['id']}")
    _notify_telegram(f"💡 <b>Günstigerer Termin</b>\n{name}\nAm {d_de}: <b>{_eur(cp)}</b> "
                     f"({_eur(diff)} günstiger als {_eur(current_price)})\n{offer.get('url','')}")


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
    log.info("💰 Günstiger als gebucht (#%d %s): %s statt %s (%s gespart) → Benachrichtigung",
             oid, name, _eur(current_price), _eur(booked), _eur(diff))
    _notify_ha(f"💰 Günstiger als gebucht: {name}",
               f"{name}\nJetzt {_eur(current_price)} — {_eur(diff)} günstiger als dein "
               f"gebuchter Preis ({_eur(booked)}). Umbuchen könnte sich lohnen.\n"
               f"{offer.get('url','')}", f"booked_{oid}")
    _notify_telegram(f"💰 <b>Günstiger als gebucht: {name}</b>\nJetzt <b>{_eur(current_price)}</b> "
                     f"({_eur(diff)} unter deinem gebuchten Preis {_eur(booked)})\n"
                     f"{offer.get('url','')}")


def _check_error_alarm(offer: dict) -> None:
    """Meldet, wenn ein Angebot ERROR_ALARM_STREAK-mal in Folge kein Ergebnis lieferte."""
    if not load_config().get('notify_errors', True):
        return
    oid = offer['id']
    with db() as con:
        rows = con.execute('SELECT ok FROM price_history WHERE offer_id=? ORDER BY ts DESC '
                           'LIMIT ?', (oid, ERROR_ALARM_STREAK)).fetchall()
    streak = 0
    for r in rows:
        if r['ok'] == 0:
            streak += 1
        else:
            break
    if streak < ERROR_ALARM_STREAK or oid in _fail_notified:
        return
    _fail_notified.add(oid)
    name = offer.get('label') or offer.get('hotel') or f"Angebot #{oid}"
    log.warning("⚠ Ausverkauft-/Fehler-Alarm (#%d %s): %d× kein Ergebnis → Benachrichtigung",
                oid, name, streak)
    _notify_ha(f"⚠ Kein Angebot: {name}",
               f"{name}\nSeit {streak} Prüfungen kein Preis/Angebot — evtl. ausgebucht "
               f"oder die URL ist veraltet.\n{offer.get('url','')}", f"error_{oid}")
    _notify_telegram(f"⚠ <b>Kein Angebot mehr: {name}</b>\nSeit {streak} Prüfungen kein "
                     f"Preis — evtl. ausgebucht oder URL veraltet.\n{offer.get('url','')}")


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
            prev_price = con.execute(
                'SELECT price FROM price_history WHERE offer_id=? AND ok=1 AND price IS NOT NULL '
                'ORDER BY ts DESC LIMIT 1', (offer_id,)).fetchone()
        if not offer:
            return
        offer = dict(offer)
        if offer.get('archived'):
            log.info("Angebot #%d ist archiviert – keine Live-Abfrage", offer_id)
            return
        prev_price = prev_price['price'] if prev_price else None
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
            for col in ('hotel', 'details', 'room', 'dep_airport', 'flight_out',
                        'flight_ret', 'location', 'city', 'region', 'country',
                        'pdf_url', 'cancellation', 'stars', 'rating',
                        'rating_count', 'recommendation', 'total_price',
                        'travellers_count', 'return_date',
                        'booking_code', 'room_booking_code'):
                if res.get(col) is not None and res.get(col) != '':
                    con.execute(f'UPDATE offers SET {col}=? WHERE id=?', (res[col], offer_id))

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
            _maybe_notify(offer, prev_price, res.get('price'), offer.get('target_price'))
            _clear_error_alarm(offer)
            if load_config().get('notify_cheaper_date', True) and res.get('price'):
                _check_cheaper_date(offer, res['price'])
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
            _check_error_alarm(offer)
        else:
            # echter Abruf-Fehler → rot (Detail steht ggf. schon oben im Log)
            log.error("Angebot #%d (%s): Abruf fehlgeschlagen – %s", offer_id, name, res.get('note'))
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
               'rows': json.loads(row['rows'])}
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
               'span': row['span'], 'rows': json.loads(row['rows'])}
    else:
        out = {'status': 'idle', 'rows': []}
    if st.get('status') == 'error':
        out['error'] = st.get('note', 'Nächte-Vergleich fehlgeschlagen')
    return out


# ── Preiskalender (on-demand, gespeichert) ──────────────────────────────────────

def _run_calendar(offer_id: int) -> None:
    """Liest den Preiskalender (Preis je Abreisetag) und speichert ihn in der DB."""
    try:
        with db() as con:
            offer = con.execute('SELECT url FROM offers WHERE id=?', (offer_id,)).fetchone()
        if not offer:
            with _calendar_lock:
                _calendar_state[offer_id] = {'status': 'error', 'note': 'Angebot nicht gefunden'}
            return
        res = fetch_calendar(offer['url'], verbose=_verbose())
        if not res or not res.get('ok'):
            log.warning("Preiskalender #%d: keine Daten/nicht abrufbar", offer_id)
            with _calendar_lock:
                _calendar_state[offer_id] = {'status': 'error', 'note': 'Preiskalender nicht abrufbar'}
            return
        with db() as con:
            con.execute('INSERT OR REPLACE INTO calendar_cache (offer_id, ts, data) VALUES (?,?,?)',
                        (offer_id, int(time.time()), json.dumps(res)))
        with _calendar_lock:
            _calendar_state.pop(offer_id, None)
        log.info("Preiskalender #%d: %d Tage, günstigster %s (%s €)", offer_id,
                 len(res.get('days', [])), res.get('cheapest_date'), res.get('cheapest_price'))
    except Exception as e:
        log.error("Preiskalender #%d Fehler: %s", offer_id, e)
        with _calendar_lock:
            _calendar_state[offer_id] = {'status': 'error', 'note': 'Preiskalender fehlgeschlagen'}


def _calendar_payload(offer_id: int) -> dict:
    with _calendar_lock:
        st = dict(_calendar_state.get(offer_id) or {})
    if st.get('status') == 'running':
        return {'status': 'running'}
    with db() as con:
        row = con.execute('SELECT ts, data FROM calendar_cache WHERE offer_id=?',
                          (offer_id,)).fetchone()
    if row:
        out = json.loads(row['data'])
        out['status'] = 'done'
        out['ts'] = row['ts']
    else:
        out = {'status': 'idle'}
    if st.get('status') == 'error':
        out['error'] = st.get('note', 'Preiskalender fehlgeschlagen')
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


def _poll_worker() -> None:
    """Prüft Angebote fälligkeitsbasiert: ein Angebot wird erst wieder abgefragt,
    wenn seit seinem letzten Check (auch über Neustarts hinweg) das Intervall
    verstrichen ist. So löst ein Add-on-Neustart keine sofortige Komplettabfrage aus."""
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
            _auto_archive_expired()
            with db() as con:
                offers = [r['id'] for r in con.execute(
                    'SELECT id FROM offers WHERE COALESCE(paused,0)=0 '
                    'AND COALESCE(archived,0)=0 ORDER BY id').fetchall()]
                last_map = {r['offer_id']: r['m'] for r in con.execute(
                    'SELECT offer_id, MAX(ts) m FROM price_history GROUP BY offer_id').fetchall()}
            due = []
            for oid in offers:
                age = now - (last_map.get(oid) or 0)
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


def _build_digest() -> dict | None:
    """Baut die wöchentliche Zusammenfassung (größte Rückgänge, neue Tiefstwerte, unter
    Wunschpreis). Rückgabe {subject, html, text} oder None, wenn es nichts zu melden gibt."""
    offers = [o for o in _collect_offers() if not o['archived'] and o.get('price') is not None]
    if not offers:
        return None
    with db() as con:
        for o in offers:
            o['_wk'] = _week_change(con, o['id'], o['price'])
    drops = sorted([o for o in offers if o['_wk'] is not None and o['_wk'] < 0],
                   key=lambda o: o['_wk'])
    rises = sorted([o for o in offers if o['_wk'] is not None and o['_wk'] > 0],
                   key=lambda o: -o['_wk'])
    lows = [o for o in offers if o.get('min_price') is not None
            and o.get('samples', 0) > 2 and o['price'] <= o['min_price']]
    under = [o for o in offers if o.get('target_price') and o['price'] <= o['target_price']]
    trips = _upcoming_trips()

    try:                                             # aktuelle öffentliche Aktionscodes
        _aktion = json.loads(_meta_get('aktion_last', '') or '{}')
    except Exception:
        _aktion = {}
    akc = _aktion.get('codes') or []
    ai_summary = _ai_digest_summary(offers, drops, rises, lows, under, trips, akc)

    def nm(o):
        return o.get('label') or o.get('hotel') or f"Angebot #{o['id']}"

    # ── Text (Telegram) ──
    tl = [f"📊 <b>TUIWatch — Wochenüberblick</b> ({datetime.now():%d.%m.%Y})",
          f"{len(offers)} aktive Reise(n) beobachtet."]
    if ai_summary:
        tl.append(f"\n🤖 {ai_summary}")
    if trips:
        tl.append("\n🧳 <b>Bevorstehende Reisen:</b>")
        for t in trips:
            rng = f"{t['start_date']} – {t['end_date']}" if t.get('end_date') else t['start_date']
            tl.append(f"• {t['destination']}: {rng} (in {t['days_until']} Tagen)")
    if under:
        tl.append("\n🎯 <b>Unter Wunschpreis:</b>")
        tl += [f"• {nm(o)}: <b>{_eur(o['price'])}</b> (Ziel {_eur(o['target_price'])})" for o in under[:8]]
    if lows:
        tl.append("\n📉 <b>Neuer Tiefstwert:</b>")
        tl += [f"• {nm(o)}: <b>{_eur(o['price'])}</b>" for o in lows[:8]]
    if drops:
        tl.append("\n▼ <b>Größte Rückgänge (7 Tage):</b>")
        tl += [f"• {nm(o)}: {_eur(o['price'])} ({_eur(o['_wk'])})" for o in drops[:8]]
    if rises:
        tl.append("\n▲ <b>Gestiegen (7 Tage):</b>")
        tl += [f"• {nm(o)}: {_eur(o['price'])} (+{_eur(abs(o['_wk']))})" for o in rises[:5]]
    if akc:
        tl.append("\n🎟 <b>TUI-Aktionscodes:</b>")
        tl += [f"• {c.get('value')} € — {c.get('code')}"
               + (f" ({c['kind']})" if c.get('kind') else '') for c in akc]
        _ctx = ([f"buchbar bis {_aktion['booking_until']}"] if _aktion.get('booking_until') else []) \
            + ([f"Reisezeitraum {_aktion['travel_period']}"] if _aktion.get('travel_period') else [])
        if _ctx:
            tl.append(" · ".join(_ctx))
    text = "\n".join(tl)

    # ── HTML (E-Mail) ──
    def esc(s):
        return (str(s or '')).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    def section(title, items, fmt):
        if not items:
            return ''
        rows = ''.join(f'<li style="margin:4px 0">{fmt(o)}</li>' for o in items)
        return (f'<h3 style="margin:18px 0 6px;color:#10243e;font-size:15px">{title}</h3>'
                f'<ul style="margin:0;padding-left:18px;color:#333;font-size:14px">{rows}</ul>')

    def link(o):
        return f'<a href="{esc(o["url"])}" style="color:#0b65d8;text-decoration:none">{esc(nm(o))}</a>'

    akc_html = ''
    if akc:
        _ctxh = ' · '.join(
            ([f'buchbar bis {esc(_aktion["booking_until"])}'] if _aktion.get('booking_until') else [])
            + ([f'Reisezeitraum {esc(_aktion["travel_period"])}'] if _aktion.get('travel_period') else []))
        _rows = ''.join(
            f'<li style="margin:4px 0"><b>{esc(c.get("value"))} €</b> — {esc(c.get("code"))}'
            + (f' <span style="color:#777">({esc(c["kind"])})</span>' if c.get('kind') else '') + '</li>'
            for c in akc)
        akc_html = ('<h3 style="margin:18px 0 6px;color:#10243e;font-size:15px">🎟 TUI-Aktionscodes</h3>'
                    + (f'<p style="margin:0 0 6px;color:#777;font-size:13px">{_ctxh}</p>' if _ctxh else '')
                    + f'<ul style="margin:0;padding-left:18px;color:#333;font-size:14px">{_rows}</ul>')

    ai_html = ''
    if ai_summary:
        _ai_inline = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', esc(ai_summary)).replace('\n', '<br>')
        ai_html = (f'<div style="background:#f0f4fa;border-radius:8px;padding:12px 14px;'
                  f'color:#10243e;font-size:14px;margin:0 0 16px;line-height:1.5">'
                  f'🤖 {_ai_inline}</div>')

    html = (
        '<div style="font-family:system-ui,Arial,sans-serif;max-width:640px;margin:0 auto">'
        f'<h2 style="color:#10243e">📊 TUIWatch — Wochenüberblick</h2>'
        f'<p style="color:#555;font-size:13px">{datetime.now():%d.%m.%Y} · {len(offers)} aktive Reise(n) beobachtet.</p>'
        + ai_html
        + section('🧳 Bevorstehende Reisen', trips,
                  lambda t: f'<b>{esc(t["destination"])}</b> — {esc(t["start_date"])}'
                            + (f' – {esc(t["end_date"])}' if t.get('end_date') else '')
                            + f' <span style="color:#777">(in {t["days_until"]} Tagen)</span>')
        + section('🎯 Unter Wunschpreis', under,
                  lambda o: f'{link(o)}: <b>{_eur(o["price"])}</b> <span style="color:#777">(Ziel {_eur(o["target_price"])})</span>')
        + section('📉 Neuer Tiefstwert', lows,
                  lambda o: f'{link(o)}: <b>{_eur(o["price"])}</b>')
        + section('▼ Größte Rückgänge (7 Tage)', drops[:8],
                  lambda o: f'{link(o)}: {_eur(o["price"])} <span style="color:#1a7f37;font-weight:600">({_eur(o["_wk"])})</span>')
        + section('▲ Gestiegen (7 Tage)', rises[:5],
                  lambda o: f'{link(o)}: {_eur(o["price"])} <span style="color:#cf222e">(+{_eur(abs(o["_wk"]))})</span>')
        + akc_html
        + '</div>'
    )
    return {'subject': f'TUIWatch — Wochenüberblick {datetime.now():%d.%m.%Y}',
            'html': html, 'text': text}


def send_digest_now() -> bool:
    """Baut und verschickt den Digest sofort über alle konfigurierten Kanäle
    (Telegram + E-Mail). True, wenn mindestens ein Kanal bedient wurde."""
    digest = _build_digest()
    if not digest:
        log.info("Digest: nichts zu berichten")
        return False
    sent = False
    cfg = load_config()
    if (cfg.get('telegram_bot_token') or '').strip() and (cfg.get('telegram_chat_id') or '').strip():
        _notify_telegram(digest['text'])
        sent = True
    to = (cfg.get('smtp_to') or '').strip()
    if smtp_configured() and to:
        try:
            send_email(digest['subject'], digest['html'], to)
            sent = True
        except Exception as e:
            log.error("Digest-E-Mail fehlgeschlagen: %s", e)
    if sent:
        log.info("Digest verschickt")
    else:
        log.info("Digest: kein Kanal konfiguriert (Telegram/SMTP)")
    return sent


def _maybe_send_digest() -> None:
    """Verschickt den Wochen-Digest am eingestellten Wochentag, höchstens 1×/ISO-Woche.
    War das Add-on am Stichtag aus, wird später in der Woche nachgeholt."""
    cfg = load_config()
    if not cfg.get('digest_enabled'):
        return
    today = date.today()
    target = min(7, max(1, int(cfg.get('digest_weekday', 1) or 1)))
    if today.isoweekday() < target:
        return
    y, w, _ = today.isocalendar()
    wk = f"{y}-W{w:02d}"
    if _meta_get('last_digest') == wk:
        return
    if send_digest_now():
        _meta_set('last_digest', wk)
    else:
        # Kein Kanal konfiguriert → nicht jede Runde neu versuchen
        _meta_set('last_digest', wk)


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
        ai_enabled=bool((cfg.get('anthropic_api_key') or '').strip()),
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
            avail = None
            if last and last['available'] is not None:
                avail = bool(last['available'])
            out.append({
                'id': o['id'], 'url': o['url'], 'label': o['label'],
                'hotel': o['hotel'], 'details': o['details'], 'room': o['room'],
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
                'return_date': o['return_date'] or '',
                'tags': (json.loads(o['tags']) if o['tags'] else []),
                'cancellation': o['cancellation'], 'stars': o['stars'],
                'rating': o['rating'], 'rating_count': o['rating_count'],
                'recommendation': o['recommendation'],
                'target_price': o['target_price'],
                'booked_price': o['booked_price'],
                'price': last['price'] if last else None,
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
                'comparable': not is_single_room(f"{o['room']} {o['details']}"),
            })
    return out


@app.route('/api/offers', methods=['GET'])
def api_offers():
    if (err := _require_api()):
        return err
    return jsonify({'offers': _collect_offers()})


def _valid_tui_url(url: str) -> bool:
    try:
        p = urlparse(url)
    except Exception:
        return False
    return p.scheme in ('http', 'https') and p.hostname is not None \
        and (p.hostname == 'tui.com' or p.hostname.endswith('.tui.com'))


@app.route('/api/offers', methods=['POST'])
def api_add_offer():
    if (err := _require_api()):
        return err
    data = request.get_json(silent=True) or {}
    url = (data.get('url') or '').strip()
    label = (data.get('label') or '').strip()
    if not _valid_tui_url(url):
        return jsonify({'error': 'invalid_url'}), 400
    img = (data.get('image') or '').strip()      # optional: Bild aus der Suche
    if not _valid_img_url(img):
        img = ''
    try:
        with db() as con:
            cur = con.execute(
                'INSERT INTO offers (url, label, hotel, details, image_url, created) '
                'VALUES (?,?,?,?,?,?)',
                (url, label, hotel_from_url(url), '', img, int(time.time())))
            offer_id = cur.lastrowid
    except sqlite3.IntegrityError:
        return jsonify({'error': 'duplicate'}), 409
    log.info("Neues Angebot #%d hinzugefügt: %s", offer_id,
             label or hotel_from_url(url) or url)
    _spawn(check_offer, offer_id)  # sofort einmal prüfen
    return jsonify({'id': offer_id, 'started': True})


@app.route('/api/offers/<int:offer_id>', methods=['DELETE'])
def api_delete_offer(offer_id: int):
    if (err := _require_api()):
        return err
    with db() as con:
        con.execute('DELETE FROM price_history WHERE offer_id=?', (offer_id,))
        con.execute('DELETE FROM compare_cache WHERE offer_id=?', (offer_id,))
        con.execute('DELETE FROM calendar_cache WHERE offer_id=?', (offer_id,))
        con.execute('DELETE FROM nights_cache WHERE offer_id=?', (offer_id,))
        con.execute('DELETE FROM cheaper_state WHERE offer_id=?', (offer_id,))
        con.execute('DELETE FROM booked_state WHERE offer_id=?', (offer_id,))
        con.execute('DELETE FROM offer_events WHERE offer_id=?', (offer_id,))
        con.execute('DELETE FROM offers WHERE id=?', (offer_id,))
    _cheaper_notified.pop(offer_id, None)
    _fail_notified.discard(offer_id)
    log.info("Angebot #%d gelöscht", offer_id)
    push_ha_sensors()  # entfernt verwaisten Sensor + nummeriert ggf. neu
    return jsonify({'deleted': offer_id})


@app.route('/api/offers/<int:offer_id>', methods=['PATCH'])
def api_update_offer(offer_id: int):
    if (err := _require_api()):
        return err
    data = request.get_json(silent=True) or {}
    events = []  # (type, text) → nach dem db-Block protokollieren (Marker im Verlauf)
    with db() as con:
        if 'label' in data:
            lbl = (data.get('label') or '').strip()
            con.execute('UPDATE offers SET label=? WHERE id=?', (lbl, offer_id))
            log.info("Angebot #%d umbenannt: %s", offer_id, lbl or '(Hotelname)')
        if 'target_price' in data:
            tp = data.get('target_price')
            try:
                tp = float(tp) if tp not in (None, '', 0) else None
            except (TypeError, ValueError):
                tp = None
            con.execute('UPDATE offers SET target_price=? WHERE id=?', (tp, offer_id))
            log.info("Wunschpreis #%d %s", offer_id,
                     f"gesetzt: {tp:.0f} €" if tp else "entfernt")
            if tp:
                events.append(('target', f"Wunschpreis {_eur(tp)}"))
        if 'booked_price' in data:
            bp = data.get('booked_price')
            try:
                bp = float(bp) if bp not in (None, '', 0) else None
            except (TypeError, ValueError):
                bp = None
            con.execute('UPDATE offers SET booked_price=? WHERE id=?', (bp, offer_id))
            if bp is None:  # Buchung zurückgenommen → Alarm-Dedup zurücksetzen
                con.execute('DELETE FROM booked_state WHERE offer_id=?', (offer_id,))
            log.info("Gebuchter Preis #%d %s", offer_id,
                     f"gesetzt: {bp:.0f} €" if bp else "entfernt")
            if bp:
                events.append(('booked', f"Gebucht für {_eur(bp)}"))
        if 'paused' in data:
            con.execute('UPDATE offers SET paused=? WHERE id=?',
                        (1 if data.get('paused') else 0, offer_id))
            log.info("Angebot #%d %s", offer_id,
                     "pausiert" if data.get('paused') else "fortgesetzt")
        if 'archived' in data:
            arch = 1 if data.get('archived') else 0
            con.execute('UPDATE offers SET archived=? WHERE id=?', (arch, offer_id))
            log.info("Angebot #%d %s", offer_id,
                     "archiviert" if arch else "reaktiviert")
        if 'tags' in data:
            raw = data.get('tags') or []
            if not isinstance(raw, list):
                raw = []
            seen = set()
            tags = []
            for t in raw:
                t = str(t).strip()
                if t and t not in seen:
                    seen.add(t)
                    tags.append(t)
            con.execute('UPDATE offers SET tags=? WHERE id=?',
                        (json.dumps(tags, ensure_ascii=False), offer_id))
            log.info("Angebot #%d Tags gesetzt: %s", offer_id, ', '.join(tags) or '(keine)')
    for t, txt in events:
        _log_event(offer_id, t, txt)
    if 'archived' in data:
        push_ha_sensors()  # Übersicht/Summary-Sensor neu berechnen
    return jsonify({'id': offer_id, 'ok': True})


@app.route('/api/history/<int:offer_id>', methods=['GET'])
def api_history(offer_id: int):
    if (err := _require_api()):
        return err
    with db() as con:
        rows = con.execute(
            'SELECT ts, price, old_price, discount, ok, note FROM price_history '
            'WHERE offer_id=? ORDER BY ts', (offer_id,)).fetchall()
        events = con.execute(
            'SELECT ts, type, text FROM offer_events WHERE offer_id=? ORDER BY ts',
            (offer_id,)).fetchall()
    return jsonify({'history': [dict(r) for r in rows],
                    'events': [dict(e) for e in events]})


@app.route('/api/history/<int:offer_id>/csv', methods=['GET'])
def api_history_csv(offer_id: int):
    if (err := _require_api()):
        return err
    with db() as con:
        offer = con.execute('SELECT hotel, label FROM offers WHERE id=?', (offer_id,)).fetchone()
        rows = con.execute(
            'SELECT ts, price, old_price, discount, available, ok, note FROM price_history '
            'WHERE offer_id=? ORDER BY ts', (offer_id,)).fetchall()
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=';')
    w.writerow(['Zeitpunkt', 'Preis (EUR)', 'Vergleichspreis (EUR)', 'Rabatt %',
                'Verfuegbar', 'OK', 'Hinweis'])
    for r in rows:
        avail = '' if r['available'] is None else ('ja' if r['available'] else 'nein')
        w.writerow([datetime.fromtimestamp(r['ts']).strftime('%Y-%m-%d %H:%M:%S'),
                    '' if r['price'] is None else int(round(r['price'])),
                    '' if r['old_price'] is None else int(round(r['old_price'])),
                    r['discount'] if r['discount'] is not None else '',
                    avail, 'ja' if r['ok'] else 'nein', (r['note'] or '').replace('\n', ' ')])
    name = _slug((offer['label'] or offer['hotel']) if offer else '') or f'angebot_{offer_id}'
    resp = make_response('﻿' + buf.getvalue())  # BOM → Umlaute in Excel korrekt
    resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
    resp.headers['Content-Disposition'] = f'attachment; filename="tuiwatch_{name}.csv"'
    return resp


@app.route('/api/check/<int:offer_id>', methods=['POST'])
def api_check_one(offer_id: int):
    if (err := _require_api()):
        return err
    log.info("Manuelle Prüfung angefordert: Angebot #%d", offer_id)
    _spawn(check_offer, offer_id)
    return jsonify({'started': True})


@app.route('/api/reset/<int:offer_id>', methods=['POST'])
def api_reset_offer(offer_id: int):
    """Setzt ein Angebot zurück: löscht Preisverlauf + Vergleichs-/Kalender-Cache und
    startet eine frische Erstabfrage. Angebot selbst (URL, Name, Wunschpreis) bleibt."""
    if (err := _require_api()):
        return err
    with db() as con:
        if not con.execute('SELECT 1 FROM offers WHERE id=?', (offer_id,)).fetchone():
            return jsonify({'error': 'not_found'}), 404
        con.execute('DELETE FROM price_history WHERE offer_id=?', (offer_id,))
        con.execute('DELETE FROM compare_cache WHERE offer_id=?', (offer_id,))
        con.execute('DELETE FROM calendar_cache WHERE offer_id=?', (offer_id,))
        con.execute('DELETE FROM nights_cache WHERE offer_id=?', (offer_id,))
        con.execute('DELETE FROM cheaper_state WHERE offer_id=?', (offer_id,))
        con.execute('DELETE FROM booked_state WHERE offer_id=?', (offer_id,))
        con.execute('DELETE FROM offer_events WHERE offer_id=?', (offer_id,))
    _log_event(offer_id, 'reset', 'Tracking zurückgesetzt')
    with _compare_lock:
        _compare_state.pop(offer_id, None)
    with _calendar_lock:
        _calendar_state.pop(offer_id, None)
    with _nights_lock:
        _nights_state.pop(offer_id, None)
    _cheaper_notified.pop(offer_id, None)
    _fail_notified.discard(offer_id)
    log.info("Angebot #%d zurückgesetzt (Verlauf + Caches gelöscht)", offer_id)
    _spawn(check_offer, offer_id)  # frische Erstabfrage
    return jsonify({'reset': offer_id, 'started': True})


@app.route('/api/check-now', methods=['POST'])
def api_check_now():
    if (err := _require_api()):
        return err
    _spawn(check_all, 'manuell')
    return jsonify({'started': True})


@app.route('/api/email', methods=['GET', 'POST'])
def api_email():
    if (err := _require_api()):
        return err
    if request.method == 'GET':  # UI fragt Status/Vorbelegung ab
        return jsonify({'configured': smtp_configured(),
                        'default_to': (load_config().get('smtp_to') or '').strip()})
    if not smtp_configured():
        return jsonify({'error': 'smtp_not_configured'}), 400
    data = request.get_json(silent=True) or {}
    to = (data.get('to') or load_config().get('smtp_to') or '').strip()
    if not to:
        return jsonify({'error': 'no_recipient'}), 400
    offers = [o for o in _collect_offers() if not o.get('archived')]
    # Optional: nur eine Auswahl versenden (Sammelaktion über die Checkboxen)
    ids = data.get('ids')
    if isinstance(ids, list) and ids:
        want = {int(i) for i in ids if str(i).isdigit()}
        offers = [o for o in offers if o['id'] in want]
    if not offers:
        return jsonify({'error': 'no_offers'}), 400
    html = _email_html_offers(offers)
    subject = f"TUIWatch – {len(offers)} Reisepreise ({datetime.now().strftime('%d.%m.%Y')})"
    try:
        send_email(subject, html, to)
    except Exception as e:
        log.error("E-Mail-Versand fehlgeschlagen: %s", e)  # Detail nur ins Log
        return jsonify({'error': 'send_failed'}), 502
    log.info("Angebots-E-Mail an %s gesendet (%d Angebote)", to, len(offers))
    return jsonify({'sent': True, 'to': to, 'count': len(offers)})


_HISTORY_COLS = ('ts', 'price', 'old_price', 'discount', 'available', 'ok', 'note')
_EVENT_COLS = ('ts', 'type', 'text')
# Feste Whitelist der beim Restore einspielbaren Angebots-Spalten (Spaltennamen kommen
# damit NIE aus den Backup-Daten → keine per String gebaute Query aus Nutzerquellen).
_OFFER_RESTORE_COLS = (
    'url', 'label', 'hotel', 'details', 'room', 'dep_airport', 'flight_out', 'flight_ret',
    'location', 'city', 'region', 'country', 'pdf_url', 'cancellation', 'stars', 'rating',
    'rating_count', 'recommendation', 'total_price', 'travellers_count', 'paused',
    'archived', 'return_date', 'target_price', 'booked_price', 'image_url', 'booking_code',
    'room_booking_code', 'tags', 'created',
)


def _table_columns(con, table: str) -> list:
    return [r['name'] for r in con.execute(f'PRAGMA table_info({table})').fetchall()]


_BACKUP_META_KEYS = (
    'travel_dna', 'ai_usage_totals', 'ai_usage_today', 'ai_usage_month',
    'custom_prompt_advisor_enabled', 'custom_prompt_advisor_text',
    'custom_prompt_compare_enabled', 'custom_prompt_compare_text',
    'custom_prompt_summary_enabled', 'custom_prompt_summary_text',
)


def _build_backup_zip() -> bytes:
    """Baut das vollständige Backup-ZIP: data.json (Angebote inkl. Preisverlauf & Marker,
    gebuchte Reisen, gespeicherte Suchen, KI-Verlauf & KI-Einstellungen) + die Reise-PDFs
    unter trips/. Genutzt vom Download-Endpoint und vom automatischen Backup."""
    with db() as con:
        ocols = [c for c in _table_columns(con, 'offers') if c != 'id']
        offers = []
        for r in con.execute('SELECT * FROM offers ORDER BY id').fetchall():
            o = {c: r[c] for c in ocols}
            oid = r['id']
            o['history'] = [{c: h[c] for c in _HISTORY_COLS} for h in con.execute(
                'SELECT ts, price, old_price, discount, available, ok, note '
                'FROM price_history WHERE offer_id=? ORDER BY ts', (oid,)).fetchall()]
            o['events'] = [{c: e[c] for c in _EVENT_COLS} for e in con.execute(
                'SELECT ts, type, text FROM offer_events WHERE offer_id=? ORDER BY ts',
                (oid,)).fetchall()]
            offers.append(o)
        trips = [{c: t[c] for c in _TRIP_COLUMNS} for t in con.execute(
            f"SELECT {', '.join(_TRIP_COLUMNS)} FROM trips ORDER BY id").fetchall()]
        searches = [{c: s[c] for c in ('name', 'payload', 'ts')} for s in con.execute(
            'SELECT name, payload, ts FROM saved_searches ORDER BY id').fetchall()]
        # Zusatz-PDFs je Reise nur über booking_code referenzierbar sichern (Trip-IDs
        # ändern sich beim Restore) — Reisen ohne Buchungsnummer werden ausgelassen.
        attachments = []
        for a in con.execute(
                'SELECT trip_attachments.filename, trip_attachments.orig_name, '
                'trip_attachments.created, trips.booking_code '
                'FROM trip_attachments JOIN trips ON trips.id = trip_attachments.trip_id '
                'WHERE trips.booking_code IS NOT NULL ORDER BY trip_attachments.id').fetchall():
            attachments.append(dict(a))
        # Packliste je Reise nur über booking_code referenzierbar sichern (wie Anhänge) —
        # Reisen ohne Buchungsnummer werden ausgelassen.
        packing_items = []
        for pi in con.execute(
                'SELECT trip_packing_items.category, trip_packing_items.label, '
                'trip_packing_items.checked, trips.booking_code '
                'FROM trip_packing_items JOIN trips ON trips.id = trip_packing_items.trip_id '
                'WHERE trips.booking_code IS NOT NULL ORDER BY trip_packing_items.id').fetchall():
            packing_items.append(dict(pi))
        ai_analyses = [dict(r) for r in con.execute(
            'SELECT kind, title, model, summary, usage, ts FROM ai_analyses ORDER BY id').fetchall()]
        meta_rows = con.execute(
            f"SELECT key, value FROM meta WHERE key IN ({','.join('?' for _ in _BACKUP_META_KEYS)})",
            _BACKUP_META_KEYS).fetchall()
        meta = {r['key']: r['value'] for r in meta_rows}
    data = {'tuiwatch_backup': 3, 'created': datetime.now().isoformat(),
            'offers': offers, 'trips': trips, 'saved_searches': searches,
            'trip_attachments': attachments, 'trip_packing_items': packing_items,
            'ai_analyses': ai_analyses, 'meta': meta}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('data.json', json.dumps(data, ensure_ascii=False, indent=2))
        seen = set()
        for t in trips:
            name = (t.get('pdf_name') or '').strip()
            if not name or name in seen:
                continue
            seen.add(name)
            p = _trip_pdf_path(name)
            if p and p.exists():
                z.write(str(p), f'trips/{Path(name).name}')
        seen_att = set()
        for a in attachments:
            name = (a.get('filename') or '').strip()
            if not name or name in seen_att:
                continue
            seen_att.add(name)
            p = _trip_pdf_path(name)
            if p and p.exists():
                z.write(str(p), f'attachments/{Path(name).name}')
    return buf.getvalue()


@app.route('/api/backup', methods=['GET'])
def api_backup():
    """Vollständiges Backup als ZIP herunterladen."""
    if (err := _require_api()):
        return err
    resp = make_response(_build_backup_zip())
    resp.headers['Content-Type'] = 'application/zip'
    resp.headers['Content-Disposition'] = (
        f'attachment; filename="tuiwatch-backup-{datetime.now().strftime("%Y%m%d")}.zip"')
    return resp


# ── Automatisches Backup (nach /config = addon_config) ─────────────────────────

BACKUP_DIR = os.environ.get('TUIWATCH_BACKUP_DIR', '/config/backups')
AUTO_BACKUP_INTERVAL = 7 * 86400   # wöchentlich
_AUTO_BACKUP_RE = re.compile(r'^tuiwatch-backup-\d{8}-\d{6}\.zip$')


def _run_auto_backup(keep: int) -> None:
    """Schreibt ein Backup-ZIP nach BACKUP_DIR und behält nur die letzten `keep`.
    So überlebt die Historie (Angebote, Reisen, Suchen) auch eine Neuinstallation
    des Add-ons — /addon_config wird dabei nicht gelöscht."""
    base = Path(BACKUP_DIR)
    base.mkdir(parents=True, exist_ok=True)
    target = base / f"tuiwatch-backup-{datetime.now():%Y%m%d-%H%M%S}.zip"
    target.write_bytes(_build_backup_zip())
    keep = max(1, keep)
    # Rotation: nur eigene, exakt passende Backup-Dateien anfassen
    old = sorted(p for p in base.glob('tuiwatch-backup-*.zip')
                 if _AUTO_BACKUP_RE.match(p.name))
    for p in old[:-keep]:
        try:
            p.unlink()
        except OSError as e:
            log.warning("Altes Auto-Backup %s nicht löschbar: %s", p.name, e)
    log.info("Auto-Backup geschrieben: %s (%d behalten)", target.name, min(len(old), keep))


def _maybe_auto_backup() -> None:
    """Legt höchstens 1×/Woche ein Backup unter /addon_config/backups ab (falls aktiviert).
    War das Add-on am Stichtag aus, wird beim nächsten Poll nachgeholt."""
    cfg = load_config()
    if not cfg.get('auto_backup', True):
        return
    try:
        last = int(_meta_get('last_auto_backup', 0) or 0)
    except (TypeError, ValueError):
        last = 0
    if time.time() - last < AUTO_BACKUP_INTERVAL:
        return
    try:
        keep = int(cfg.get('auto_backup_keep', 5) or 5)
    except (TypeError, ValueError):
        keep = 5
    try:
        _run_auto_backup(keep)
        _meta_set('last_auto_backup', str(int(time.time())))
    except Exception as e:
        log.error("Auto-Backup fehlgeschlagen: %s", e)


def _restore_offer(con, it: dict, ocols: set, existing_urls: set) -> str:
    """Ein Angebot aus dem Backup einspielen (nicht-destruktiv, Upsert per URL).
    Rückgabe: 'added' | 'skipped'; bei 'added' werden Verlauf & Marker mitgeschrieben."""
    def _price(v):
        try:
            return float(v) if v not in (None, '', 0) else None
        except (TypeError, ValueError):
            return None
    url = (it.get('url') or '').strip()
    if not _valid_tui_url(url) or url in existing_urls:
        return 'skipped'
    # Werte NUR aus der festen Spalten-Whitelist übernehmen (Spaltennamen sind Code-
    # Konstanten, nie aus den Daten), sicherheitskritische Felder bereinigen.
    row = {c: it.get(c) for c in _OFFER_RESTORE_COLS if c in ocols}
    row['url'] = url
    row['label'] = (it.get('label') or '').strip()
    row['hotel'] = (it.get('hotel') or hotel_from_url(url) or '')
    if 'target_price' in row:
        row['target_price'] = _price(it.get('target_price'))
    if 'booked_price' in row:
        row['booked_price'] = _price(it.get('booked_price'))
    if 'image_url' in row:
        img = (it.get('image_url') or '').strip()
        row['image_url'] = img if _valid_img_url(img) else ''
    row['paused'] = 1 if it.get('paused') else 0
    row['archived'] = 1 if it.get('archived') else 0
    row['created'] = int(it.get('created') or time.time())
    # Spaltenliste ausschließlich aus der Konstante (feste Reihenfolge, keine Nutzerdaten)
    cols = [c for c in _OFFER_RESTORE_COLS if c in row]
    try:
        cur = con.execute(
            f"INSERT INTO offers ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
            [row[c] for c in cols])
    except sqlite3.IntegrityError:
        return 'skipped'
    oid = cur.lastrowid
    existing_urls.add(url)
    for h in (it.get('history') or []):
        if not isinstance(h, dict):
            continue
        con.execute(
            'INSERT INTO price_history (offer_id, ts, price, old_price, discount, '
            'available, ok, note) VALUES (?,?,?,?,?,?,?,?)',
            (oid, int(h.get('ts') or 0), h.get('price'), h.get('old_price'),
             h.get('discount'), h.get('available'),
             1 if h.get('ok') else 0, (h.get('note') or '')))
    for e in (it.get('events') or []):
        if not isinstance(e, dict) or not e.get('type'):
            continue
        con.execute('INSERT INTO offer_events (offer_id, ts, type, text) VALUES (?,?,?,?)',
                    (oid, int(e.get('ts') or 0), str(e.get('type')), (e.get('text') or '')))
    return oid


@app.route('/api/restore', methods=['POST'])
def api_restore():
    """Wiederherstellung aus einem Backup — akzeptiert die ZIP (vollständig) oder das
    alte JSON (nur Angebote). Nicht-destruktiv: bestehende Angebote/Reisen/Suchen bleiben,
    fehlende werden ergänzt (Upsert per URL / Buchungsnummer / Name)."""
    if (err := _require_api()):
        return err
    up = request.files.get('file')
    raw = up.read() if up is not None else None
    pdfs: dict[str, bytes] = {}
    att_pdfs: dict[str, bytes] = {}
    data = None
    if raw:
        if raw[:2] == b'PK':                       # ZIP-Archiv
            try:
                zf = zipfile.ZipFile(io.BytesIO(raw))
                data = json.loads(zf.read('data.json').decode('utf-8'))
            except (zipfile.BadZipFile, KeyError, ValueError, UnicodeDecodeError):
                return jsonify({'error': 'invalid'}), 400
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if info.filename.startswith('trips/'):
                    base = Path(info.filename).name
                    if base.lower().endswith('.pdf') and 0 < info.file_size <= MAX_PDF_BYTES:
                        pdfs[base] = zf.read(info)
                elif info.filename.startswith('attachments/'):
                    base = Path(info.filename).name
                    if base.lower().endswith('.pdf') and 0 < info.file_size <= MAX_PDF_BYTES:
                        att_pdfs[base] = zf.read(info)
        else:                                       # hochgeladene JSON-Datei
            try:
                data = json.loads(raw.decode('utf-8'))
            except (ValueError, UnicodeDecodeError):
                return jsonify({'error': 'invalid'}), 400
    else:
        data = request.get_json(silent=True)

    if isinstance(data, list):                      # ganz altes Format = reine Angebotsliste
        data = {'offers': data}
    if not isinstance(data, dict) or not isinstance(data.get('offers', []), list):
        return jsonify({'error': 'invalid'}), 400

    offers = data.get('offers') or []
    trips = data.get('trips') or []
    searches = data.get('saved_searches') or []
    trip_attachments = data.get('trip_attachments') or []
    packing_items = data.get('trip_packing_items') or []
    ai_analyses = data.get('ai_analyses') or []
    meta = data.get('meta') or {}
    added, skipped, new_ids = 0, 0, []
    trips_n, searches_n, attachments_n, packing_n, ai_n, settings_n = 0, 0, 0, 0, 0, 0
    with db() as con:
        ocols = set(_table_columns(con, 'offers'))
        existing_urls = {r['url'] for r in con.execute('SELECT url FROM offers').fetchall()}
        for it in offers:
            if not isinstance(it, dict):
                skipped += 1
                continue
            res = _restore_offer(con, it, ocols, existing_urls)
            if res == 'skipped':
                skipped += 1
            else:
                added += 1
                if not it.get('archived'):
                    new_ids.append(res)             # archivierte nicht sofort prüfen
        if isinstance(trips, list) and trips:
            Path(TRIPS_DIR).mkdir(parents=True, exist_ok=True)
            for t in trips:
                if not isinstance(t, dict):
                    continue
                pdf_name = (t.get('pdf_name') or '').strip()
                if pdf_name and pdf_name in pdfs:
                    p = _trip_pdf_path(pdf_name)
                    if p:
                        p.write_bytes(pdfs[pdf_name])
                vals = [int(t.get(c) or time.time()) if c == 'created' else t.get(c)
                        for c in _TRIP_COLUMNS]
                booking = (t.get('booking_code') or '').strip()
                ex = (con.execute('SELECT id FROM trips WHERE booking_code=?', (booking,)).fetchone()
                      if booking else None)
                if ex:
                    con.execute('UPDATE trips SET '
                                + ', '.join(f'{c}=?' for c in _TRIP_COLUMNS)
                                + ' WHERE id=?', vals + [ex['id']])
                    trips_n += 1
                    continue
                try:
                    con.execute(
                        f"INSERT INTO trips ({', '.join(_TRIP_COLUMNS)}) "
                        f"VALUES ({', '.join('?' for _ in _TRIP_COLUMNS)})", vals)
                    trips_n += 1
                except sqlite3.IntegrityError:
                    pass
        if isinstance(trip_attachments, list) and trip_attachments:
            Path(TRIPS_DIR).mkdir(parents=True, exist_ok=True)
            for a in trip_attachments:
                if not isinstance(a, dict):
                    continue
                booking = (a.get('booking_code') or '').strip()
                filename = (a.get('filename') or '').strip()
                orig_name = (a.get('orig_name') or '').strip()
                if not booking or not filename or not orig_name:
                    continue
                trip_row = con.execute(
                    'SELECT id FROM trips WHERE booking_code=?', (booking,)).fetchone()
                if not trip_row:
                    continue
                exists = con.execute(
                    'SELECT id FROM trip_attachments WHERE trip_id=? AND filename=?',
                    (trip_row['id'], filename)).fetchone()
                if exists:
                    continue
                if filename in att_pdfs:
                    p = _trip_pdf_path(filename)
                    if p:
                        p.write_bytes(att_pdfs[filename])
                con.execute(
                    'INSERT INTO trip_attachments (trip_id, filename, orig_name, created) '
                    'VALUES (?,?,?,?)',
                    (trip_row['id'], filename, orig_name, int(a.get('created') or time.time())))
                attachments_n += 1
        if isinstance(packing_items, list) and packing_items:
            for pi in packing_items:
                if not isinstance(pi, dict):
                    continue
                booking = (pi.get('booking_code') or '').strip()
                category = (pi.get('category') or '').strip()
                label = (pi.get('label') or '').strip()
                if not booking or not category or not label:
                    continue
                trip_row = con.execute(
                    'SELECT id FROM trips WHERE booking_code=?', (booking,)).fetchone()
                if not trip_row:
                    continue
                exists = con.execute(
                    'SELECT id FROM trip_packing_items WHERE trip_id=? AND category=? AND label=?',
                    (trip_row['id'], category, label)).fetchone()
                if exists:
                    continue
                con.execute(
                    'INSERT INTO trip_packing_items (trip_id, category, label, checked, created) '
                    'VALUES (?,?,?,?,?)',
                    (trip_row['id'], category, label, 1 if pi.get('checked') else 0, int(time.time())))
                con.execute('UPDATE trips SET packing_seeded=1 WHERE id=?', (trip_row['id'],))
                packing_n += 1
        if isinstance(searches, list):
            for s in searches:
                if not isinstance(s, dict):
                    continue
                name = (s.get('name') or '').strip()
                if not name:
                    continue
                payload = s.get('payload')
                if not isinstance(payload, str):
                    payload = json.dumps(payload or {}, ensure_ascii=False)
                ts = int(s.get('ts') or time.time())
                ex = con.execute('SELECT id FROM saved_searches WHERE name=?', (name,)).fetchone()
                if ex:
                    con.execute('UPDATE saved_searches SET payload=?, ts=? WHERE id=?',
                                (payload, ts, ex['id']))
                else:
                    con.execute('INSERT INTO saved_searches (name, payload, ts) VALUES (?,?,?)',
                                (name, payload, ts))
                    searches_n += 1
        if isinstance(ai_analyses, list) and ai_analyses:
            for a in ai_analyses:
                if not isinstance(a, dict):
                    continue
                kind = (a.get('kind') or '').strip()
                title = (a.get('title') or '').strip()
                ts = a.get('ts')
                if not kind or not title or ts is None:
                    continue
                exists = con.execute(
                    'SELECT id FROM ai_analyses WHERE kind=? AND title=? AND ts=?',
                    (kind, title, ts)).fetchone()
                if exists:
                    continue
                con.execute(
                    'INSERT INTO ai_analyses (kind, title, model, summary, usage, ts) '
                    'VALUES (?,?,?,?,?,?)',
                    (kind, title, a.get('model'), a.get('summary'), a.get('usage'), ts))
                ai_n += 1
            con.execute('DELETE FROM ai_analyses WHERE id NOT IN '
                        '(SELECT id FROM ai_analyses ORDER BY id DESC LIMIT ?)', (_AI_HISTORY_MAX,))
        if isinstance(meta, dict):
            # Nicht-destruktiv wie der Rest des Restores: nur setzen, wenn lokal noch
            # nichts hinterlegt ist — laufende Zaehler/Einstellungen werden nie mit
            # (moeglicherweise aelteren) Backup-Werten ueberschrieben.
            for k in _BACKUP_META_KEYS:
                if k not in meta:
                    continue
                if con.execute('SELECT 1 FROM meta WHERE key=?', (k,)).fetchone():
                    continue
                con.execute('INSERT INTO meta (key, value) VALUES (?,?)', (k, str(meta[k])))
                settings_n += 1
    for oid in new_ids:
        _spawn(check_offer, oid)
    log.info("Wiederherstellung: %d Angebote (+%d übersprungen), %d Reisen, %d Suchen, "
             "%d Reise-Anhänge, %d Packliste-Items, %d KI-Verlauf, %d KI-Einstellungen",
             added, skipped, trips_n, searches_n, attachments_n, packing_n, ai_n, settings_n)
    return jsonify({'added': added, 'skipped': skipped, 'trips': trips_n, 'searches': searches_n,
                    'attachments': attachments_n, 'packing_items': packing_n,
                    'ai_history': ai_n, 'settings': settings_n})


@app.route('/api/compare/<int:offer_id>', methods=['POST'])
def api_compare_start(offer_id: int):
    if (err := _require_api()):
        return err
    with _compare_lock:
        if _compare_state.get(offer_id, {}).get('status') == 'running':
            return jsonify({'started': True, 'already': True})
    with db() as con:
        o = con.execute('SELECT room, details FROM offers WHERE id=?', (offer_id,)).fetchone()
    if not o:
        return jsonify({'error': 'not_found'}), 404
    if is_single_room(f"{o['room']} {o['details']}"):
        return jsonify({'error': 'single_room'}), 409
    with _compare_lock:
        _compare_state[offer_id] = {'status': 'running'}
    log.info("Pro-Person-Vergleich gestartet: Angebot #%d", offer_id)
    _spawn(_run_compare, offer_id)
    return jsonify({'started': True})


@app.route('/api/compare/<int:offer_id>', methods=['GET'])
def api_compare_get(offer_id: int):
    if (err := _require_api()):
        return err
    return jsonify(_compare_payload(offer_id))


@app.route('/api/nights/<int:offer_id>', methods=['POST'])
def api_nights_start(offer_id: int):
    if (err := _require_api()):
        return err
    data = request.get_json(silent=True) or {}
    try:
        span = int(data.get('span', 3))
    except (TypeError, ValueError):
        span = 3
    span = max(1, min(NIGHTS_SPAN_MAX, span))
    with _nights_lock:
        if _nights_state.get(offer_id, {}).get('status') == 'running':
            return jsonify({'started': True, 'already': True})
    with db() as con:
        o = con.execute('SELECT id FROM offers WHERE id=?', (offer_id,)).fetchone()
    if not o:
        return jsonify({'error': 'not_found'}), 404
    with _nights_lock:
        _nights_state[offer_id] = {'status': 'running'}
    log.info("Nächte-Vergleich gestartet: Angebot #%d (±%d)", offer_id, span)
    _spawn(_run_nights, offer_id, span)
    return jsonify({'started': True})


@app.route('/api/nights/<int:offer_id>', methods=['GET'])
def api_nights_get(offer_id: int):
    if (err := _require_api()):
        return err
    return jsonify(_nights_payload(offer_id))


@app.route('/api/search', methods=['POST'])
def api_search():
    """Hotelsuche — entweder über eine eingefügte TUI-Such-/Region-URL oder über ein
    bestehendes Angebot (`offer_id`): dann werden Region (URL bzw. Breadcrumb) und die
    Reiseparameter aus dem Angebot übernommen. Add-on-Filter (Veranstalter TUI,
    Verpflegung) gehen in die Such-Query, danach Nachfilter nach Sternen/Weiterempfehlung."""
    if (err := _require_api()):
        return err
    data = request.get_json(silent=True) or {}
    operator_tui = bool(data.get('operator_tui', True))
    direct = bool(data.get('direct'))
    boards = [str(b).strip() for b in (data.get('boards') or []) if str(b).strip()]
    airlines = [str(a).strip() for a in (data.get('airlines') or []) if str(a).strip()]
    location = [int(i) for i in (data.get('location') or []) if str(i).strip().isdigit()]

    def _num(key):
        try:
            return float(data.get(key) or 0)
        except (TypeError, ValueError):
            return 0
    min_stars, min_recommend = _num('min_stars'), _num('min_recommend')

    region = None
    offer_id = data.get('offer_id')
    search_region = data.get('region')  # Param-Modus aus der Suchmaske
    if offer_id:
        with db() as con:
            o = con.execute('SELECT url, label, hotel FROM offers WHERE id=?',
                            (offer_id,)).fetchone()
        if not o:
            return jsonify({'error': 'not_found'}), 404
        url = o['url']
        if 'regionGiataIds=' not in (urlparse(url).query or ''):
            region = region_giata_from_breadcrumb(_giata_from_url(url))
            if not region:
                return jsonify({'error': 'no_region',
                                'note': 'Region zum Angebot nicht ermittelbar'}), 400
        src = f"Angebot #{offer_id} ({o['label'] or o['hotel'] or ''})"
        res = fetch_search(url, operator_tui=operator_tui, boards=boards, region=region,
                           airlines=airlines, location=location, direct=direct,
                           verbose=_verbose())
    elif search_region:
        try:
            region = int(search_region)
        except (TypeError, ValueError):
            return jsonify({'error': 'no_region'}), 400
        airports = [str(a).strip() for a in (data.get('airport') and [data.get('airport')]
                    or data.get('airports') or []) if str(a).strip()]
        log.info("Suche: Region %s %s–%s/%sN, %s Reisende, ab %s (TUI=%s, Verpfl.=%s)",
                 region, data.get('start'), data.get('end'), data.get('duration'),
                 data.get('travellers'), ','.join(airports) or '-', operator_tui,
                 ','.join(boards) or '-')
        res = fetch_search_params(region=region, start=(data.get('start') or '').strip(),
                                  end=(data.get('end') or '').strip(),
                                  duration=data.get('duration'),
                                  travellers=data.get('travellers'), airports=airports,
                                  operator_tui=operator_tui, boards=boards,
                                  airlines=airlines, location=location, direct=direct,
                                  verbose=_verbose())
    else:
        url = (data.get('url') or '').strip()
        if not _valid_tui_url(url):
            return jsonify({'error': 'invalid_url'}), 400
        log.info("Suche: %s (TUI=%s, Verpflegung=%s)", url, operator_tui,
                 ','.join(boards) or '-')
        res = fetch_search(url, operator_tui=operator_tui, boards=boards,
                           airlines=airlines, location=location, direct=direct,
                           verbose=_verbose())
    if res is None:
        return jsonify({'error': 'search_failed'}), 502
    if not res.get('ok'):
        return jsonify({'error': 'no_region', 'note': res.get('note', '')}), 400
    # bereits (aktiv) getrackte Hotels (per giataId) markieren — Archiv zählt nicht
    with db() as con:
        tracked = {g for g in (_giata_from_url(r['url'])
                   for r in con.execute(
                       'SELECT url FROM offers WHERE COALESCE(archived,0)=0').fetchall()) if g}
    out = []
    for r in res['results']:
        if min_stars and (r.get('stars') or 0) < min_stars:
            continue
        if min_recommend and (r.get('recommendation') or 0) < min_recommend:
            continue
        r['tracked'] = str(r.get('giata')) in tracked
        out.append(r)
    log.info("Suche: %d Treffer, %d nach Filter", len(res['results']), len(out))
    return jsonify({'results': out, 'total': res.get('total', len(out)),
                    'matched': len(out)})


_AI_SECTIONS = (
    "- Lage & Strand (Entfernung zu Strand/Zentrum, Umgebung)\n"
    "- Zimmer (Größe, Zustand, Unterschiede zwischen Kategorien)\n"
    "- Restaurants & Bars (Auswahl, Buffet vs. à la carte, Qualität)\n"
    "- Pool, Wellness & Sport\n"
    "- Ausstattung & Familientauglichkeit\n"
    "- Klima zur Reisezeit: historische Klimawerte für Ort und Reisemonat — "
    "durchschnittliche Wassertemperatur, Lufttemperatur, Sonnenstunden/Regentage, "
    "möglichst ortsgenau für das jeweilige Hotel/den Küstenabschnitt statt nur "
    "fürs Land als Ganzes recherchiert über Klimatabellen (z. B. Seetemperatur- "
    "und Klima-Seiten für den Ort/Monat). Keine Tagesvorhersage, sondern der "
    "langjährige Durchschnitt für diese Jahreszeit\n"
    "- Wind: für jedes Hotel einzeln eine konkrete Zahl nennen (km/h oder "
    "Beaufort, für den Reisemonat, ortsgenau recherchiert) — keine allgemeinen "
    "Regionsangaben („in der Region weht oft Wind“), sondern explizit pro "
    "Hotel/Ort. Vergleiche die Werte direkt: welches Hotel ist spürbar "
    "windiger/ruhiger als die anderen\n"
)


_CUSTOM_PROMPT_MAX_LEN = 4000  # Zeichen — ganzer Instruktionsblock, großzügiger als
                               # die 500-Zeichen-Freitextfelder im Reiseberater-Fragebogen

_DEFAULT_ADVISOR_INSTRUCTIONS = (
    "Nutze die Websuche, um für die genannte Reisezeit reale, aktuelle Klimadaten zu "
    "prüfen — Lufttemperatur, Wassertemperatur, Regentage und Windverhältnisse. Wind "
    "unterscheidet sich oft stark innerhalb eines Landes/einer Region je nach "
    "konkreter Insel/Küstenabschnitt (z. B. Kapverden: Sal deutlich weniger windig als "
    "Boa Vista im selben Monat) — recherchiere daher möglichst auf Ebene der konkreten "
    "Insel/Teilregion/des Orts, nicht nur für das Land als Ganzes, und nenne diese "
    "Teilregion explizit im Vorschlag statt nur das übergeordnete Land. Leite daraus "
    "tatsächlich passende, real existierende Ziele ab — keine erfundenen Orte. "
    "Berücksichtige nach Möglichkeit auch, was den Nutzer im Urlaub stört, sowie "
    "Freitext-Angaben zu früheren Urlauben/Vorlieben, falls vorhanden — erkenne darin "
    "genannte Hotelketten/-typen/Regionen und leite daraus ähnliche Empfehlungen ab.\n\n"
    "Schlage 3 konkrete Reiseziele vor (Ort/Region + passender Urlaubstyp, kein "
    "bestimmtes Hotel nötig). Für jeden Vorschlag eine Markdown-Überschrift "
    "(#### 🏆/🥈/🥉 Ziel-Name), danach als Stichpunkte eine kurze Begründung, die "
    "konkret auf das Profil oben eingeht (Klima zur Reisezeit, Passung zu Interessen/"
    "Aktivitäten/Reiseart/Budget/Mitreisenden/Hotelwünschen). Ergänze danach einen "
    "Abschnitt „#### 🔀 Alternative“ mit einem Ziel, das vom genannten Profil bewusst "
    "etwas abweicht (z. B. eine weniger bekannte Nachbarregion), aber ähnlich gut "
    "passen könnte. Ergänze außerdem einen Abschnitt „#### 🎲 Überraschung“ mit einem "
    "Ziel außerhalb der genannten Ziel-Region (z. B. ein anderer Kontinent/eine andere "
    "Weltgegend als die gewählte, aber trotzdem passend zu Interessen/Reiseart/Budget/"
    "Wetter) — ein Land, an das der Nutzer wahrscheinlich nicht von selbst gedacht "
    "hätte. Schreibe auf Deutsch, sprich den Nutzer dabei durchgehend mit „Du“ an "
    "(informell, nicht „Sie“), ehrlich und ohne zu übertreiben — wenn ein Wunsch (z. B. "
    "Budget, Reisezeit oder TUI-Verfügbarkeit) schwer erfüllbar ist, sag das offen."
)

_ADVISOR_SAFETY_TRAILER = (
    "\nWichtig, unabhängig vom Text oben: Halte dich weiterhin an alle oben genannten "
    "Ausschlüsse (Länder, Reisewarnungen, ggf. TUI-Verfügbarkeit) — auch beim "
    "Alternative- und Überraschung-Vorschlag."
)

_DEFAULT_COMPARE_INSTRUCTIONS = (
    "Nutze die Websuche gezielt nach aktuellen Reisebewertungen (z. B. HolidayCheck, "
    "Tripadvisor, Google), Hotel-Infoseiten sowie Klimatabellen/historischen Wetter- "
    "und Wassertemperaturdaten inkl. Windverhältnisse zu den oben genannten Hotels/"
    "Orten und Reisemonaten. Wind unterscheidet sich oft stark innerhalb eines "
    "Landes/einer Region je nach konkreter Insel/Küstenabschnitt — recherchiere "
    "möglichst ortsgenau je Hotel statt nur fürs Land als Ganzes.\n\n"
    "Vergleiche entlang dieser Punkte, gerne ausführlich:\n"
    + _AI_SECTIONS + "- Preis-Leistung\n\n"
    "Schließe mit einer kompakten Markdown-Tabelle (Hotel vs. Bewertung je Punkt, "
    "Wind als eigene Zeile mit konkreten km/h-Werten je Hotel) und "
    "einer klaren Empfehlung, welches Hotel für wen (z. B. Familie, Paar, Party, Ruhe) "
    "am besten passt. Schreibe auf Deutsch, sprich den Nutzer dabei durchgehend mit "
    "„Du“ an (informell, nicht „Sie“), sachlich, ausschließlich basierend auf dem, "
    "was du in den Bewertungen/Quellen findest. Wenn zu einem Punkt nichts Verlässliches "
    "auffindbar ist, sag das kurz statt zu spekulieren. Gib direkt die fertige Antwort "
    "aus — keine Zwischenkommentare wie „Ich werde jetzt recherchieren“ oder „Lassen "
    "Sie mich noch prüfen“."
)

_DEFAULT_SUMMARY_INSTRUCTIONS = (
    "Nutze die Websuche gezielt nach aktuellen Reisebewertungen (z. B. HolidayCheck, "
    "Tripadvisor, Google), Hotel-Infoseiten sowie Klimatabellen/historischen Wetter- "
    "und Wassertemperaturdaten für Ort und Reisemonat.\n\n"
    "Gliedere die Antwort in diese Abschnitte, gerne ausführlich:\n"
    + _AI_SECTIONS + "- Fazit: Preis-Leistung und für wen das Hotel geeignet ist\n\n"
    "Schreibe auf Deutsch, sprich den Nutzer dabei durchgehend mit „Du“ an (informell, "
    "nicht „Sie“), sachlich, ausschließlich basierend auf dem, was du in den "
    "Bewertungen/Quellen findest. Wenn zu einem Punkt nichts Verlässliches auffindbar "
    "ist, sag das kurz statt zu spekulieren. Gib direkt die fertige Antwort aus — keine "
    "Zwischenkommentare wie „Ich werde jetzt recherchieren“ oder „Lassen Sie mich noch "
    "prüfen“."
)

_PROMPT_FEATURES = {'advisor': _DEFAULT_ADVISOR_INSTRUCTIONS, 'compare': _DEFAULT_COMPARE_INSTRUCTIONS,
                    'summary': _DEFAULT_SUMMARY_INSTRUCTIONS}


def _hotel_fact_lines(h: dict, *, label: str = "Hotel") -> list[str]:
    """Fakten-Zeilen für einen Prompt-Block aus einem Suchergebnis-Objekt."""
    name = (h.get('name') or '').strip()
    location = (h.get('location') or '').strip()
    country = (h.get('country') or '').strip()
    lines = [f"{label}: {name}", f"Ort: {location}" + (f", {country}" if country else "")]
    if h.get('stars'):
        lines.append(f"Sterne: {h['stars']}")
    if h.get('recommendation') is not None:
        lines.append(f"HolidayCheck-Weiterempfehlung: {h['recommendation']}%"
                      + (f" ({h['reviews']} Bewertungen)" if h.get('reviews') else ""))
    if h.get('board'):
        lines.append(f"Verpflegung im Angebot: {h['board']}")
    if h.get('price'):
        lines.append(f"Reisepreis: {h['price']} € p.P."
                      + (f", {h['nights']} Nächte" if h.get('nights') else ""))
    if h.get('date'):
        lines.append(f"Reisezeitraum: ab {h['date']}")
    if h.get('details'):
        lines.append(f"Details: {h['details']}")
    return lines


_AI_PRICING = {  # USD pro 1 Mio Tokens (Input/Output) — Anthropic-Listenpreise,
                 # ohne evtl. befristete Einführungsrabatte. Nur zur groben
                 # Kosten-Schätzung, kein echtes Guthaben (das zeigt nur die Console).
    'claude-opus-4-8':  {'input': 5.0,  'output': 25.0},
    'claude-sonnet-5':  {'input': 3.0,  'output': 15.0},
    'claude-haiku-4-5': {'input': 1.0,  'output': 5.0},
    'claude-fable-5':   {'input': 10.0, 'output': 50.0},
}


def _ai_call_cost(model: str, usage: dict) -> float:
    """Geschätzte Kosten (USD) für genau diesen einen Aufruf."""
    price = _AI_PRICING.get(model, _AI_PRICING['claude-opus-4-8'])
    cost = usage.get('input_tokens', 0) / 1_000_000 * price['input']
    cost += usage.get('output_tokens', 0) / 1_000_000 * price['output']
    cost += usage.get('cache_read_input_tokens', 0) / 1_000_000 * price['input'] * 0.1
    cost += usage.get('cache_creation_input_tokens', 0) / 1_000_000 * price['input'] * 1.25
    return round(cost, 4)


def _ai_usage_calc(models: dict) -> dict:
    """Verrechnet ein {model: counters}-Dict zu Aufrufen/Tokens/geschätzten
    Kosten (USD), je Modell mit eigenem Preis (siehe _AI_PRICING)."""
    cost = 0.0
    calls = input_tokens = output_tokens = 0
    for model, t in models.items():
        price = _AI_PRICING.get(model, _AI_PRICING['claude-opus-4-8'])
        cost += t.get('input_tokens', 0) / 1_000_000 * price['input']
        cost += t.get('output_tokens', 0) / 1_000_000 * price['output']
        cost += t.get('cache_read_input_tokens', 0) / 1_000_000 * price['input'] * 0.1
        cost += t.get('cache_creation_input_tokens', 0) / 1_000_000 * price['input'] * 1.25
        calls += t.get('calls', 0)
        input_tokens += t.get('input_tokens', 0)
        output_tokens += t.get('output_tokens', 0)
    return {'calls': calls, 'input_tokens': input_tokens, 'output_tokens': output_tokens,
            'estimated_usd': round(cost, 4)}


def _ai_usage_period_calc(meta_key: str, id_field: str, current_id: str) -> dict:
    """Liest einen periodischen Zähler-Bucket (Tag/Monat) aus `meta` — bei
    abgelaufener Periode (anderes Datum/Monat als `current_id`) gilt er als leer,
    ohne die gespeicherten Daten selbst zu löschen (das passiert erst beim
    nächsten `_record_ai_usage`-Aufruf für die neue Periode)."""
    try:
        stored = json.loads(_meta_get(meta_key) or '{}')
    except (TypeError, ValueError):
        stored = {}
    models = (stored.get('models') or {}) if stored.get(id_field) == current_id else {}
    return _ai_usage_calc(models)


def _ai_usage_totals() -> dict:
    """Aufsummierte Token-Nutzung + geschätzte Kosten (USD): gesamt (seit je),
    heute und diesen Monat — je Modell separat verrechnet."""
    try:
        totals = json.loads(_meta_get('ai_usage_totals') or '{}')
    except (TypeError, ValueError):
        totals = {}
    result = _ai_usage_calc(totals)
    result['today'] = _ai_usage_period_calc('ai_usage_today', 'date', time.strftime('%Y-%m-%d'))
    result['month'] = _ai_usage_period_calc('ai_usage_month', 'month', time.strftime('%Y-%m'))
    return result


def _record_ai_usage_bucket(meta_key: str, id_field: str | None, current_id: str | None,
                            model: str, usage: dict) -> None:
    """Addiert einen KI-Aufruf zu einem Zähler-Bucket in `meta`. Für periodische
    Buckets (id_field gesetzt, z. B. 'date'/'month') wird bei Periodenwechsel auf
    0 zurückgesetzt statt unbegrenzt zu wachsen; für den Gesamt-Bucket (id_field
    None) bleibt das bisherige flache {model: counters}-Format erhalten."""
    try:
        stored = json.loads(_meta_get(meta_key) or '{}')
    except (TypeError, ValueError):
        stored = {}
    if id_field:
        if stored.get(id_field) != current_id:
            stored = {id_field: current_id, 'models': {}}
        models = stored.setdefault('models', {})
    else:
        models = stored
    t = models.setdefault(model, {'input_tokens': 0, 'output_tokens': 0,
                                   'cache_creation_input_tokens': 0,
                                   'cache_read_input_tokens': 0, 'calls': 0})
    for key in ('input_tokens', 'output_tokens', 'cache_creation_input_tokens',
                'cache_read_input_tokens'):
        t[key] += usage.get(key, 0)
    t['calls'] += 1
    _meta_set(meta_key, json.dumps(stored))


def _record_ai_usage(model: str, usage: dict) -> dict:
    """Nutzung eines frischen KI-Aufrufs zu Gesamt-, Tages- und Monats-Zählern
    addieren und die aktualisierten Gesamtwerte zurückgeben."""
    _record_ai_usage_bucket('ai_usage_totals', None, None, model, usage)
    _record_ai_usage_bucket('ai_usage_today', 'date', time.strftime('%Y-%m-%d'), model, usage)
    _record_ai_usage_bucket('ai_usage_month', 'month', time.strftime('%Y-%m'), model, usage)
    return _ai_usage_totals()


_AI_HISTORY_MAX = 300  # ältere Einträge werden beim Speichern verworfen


def _save_ai_analysis(kind: str, title: str, model: str, text: str, usage: dict) -> int:
    """Fertiges KI-Fazit/-Vergleich dauerhaft ablegen, damit es später über den
    KI-Verlauf wieder einsehbar (und per E-Mail versendbar) ist — unabhängig vom
    24h-Cache. Gibt die neue Zeilen-ID zurück."""
    with db() as con:
        cur = con.execute('INSERT INTO ai_analyses (kind, title, model, summary, usage, ts) '
                          'VALUES (?,?,?,?,?,?)',
                          (kind, title[:300], model, text, json.dumps(usage or {}), int(time.time())))
        aid = cur.lastrowid
        con.execute('DELETE FROM ai_analyses WHERE id NOT IN '
                    '(SELECT id FROM ai_analyses ORDER BY id DESC LIMIT ?)', (_AI_HISTORY_MAX,))
    return aid


def _ai_config():
    """(api_key, model) aus den Add-on-Optionen; model fällt auf Opus zurück,
    falls leer oder ungültig."""
    cfg = load_config()
    api_key = (cfg.get('anthropic_api_key') or '').strip()
    model = cfg.get('anthropic_model') or 'claude-opus-4-8'
    if model not in _AI_MODELS:
        model = 'claude-opus-4-8'
    return api_key, model


def _ai_request(api_key: str, model: str, prompt: str, *, max_tokens: int,
                log_ctx: str, use_web_search: bool = True, output_schema: dict | None = None):
    """Reiner Claude-Aufruf ohne Flask-Abhängigkeit (kein jsonify) — nutzbar sowohl
    aus Request-Handlern als auch aus Hintergrund-Threads (z. B. Wochenüberblick),
    die keinen Flask-App-Context haben. Rückgabe: (text, usage, error_code);
    error_code ist None bei Erfolg, sonst 'failed' / 'refused' / 'empty'.
    `usage` = {input_tokens, output_tokens, cache_creation_input_tokens,
    cache_read_input_tokens}. Mit `output_schema` antwortet Claude als validiertes
    JSON nach diesem Schema (structured outputs) — `text` ist dann der JSON-String."""
    kwargs = {}
    if use_web_search:
        # allowed_callers=["direct"]: Haiku unterstützt kein programmatic tool
        # calling — ohne das Flag lehnt die API web_search auf diesem Modell ab.
        kwargs['tools'] = [{"type": "web_search_20260209", "name": "web_search",
                            "allowed_callers": ["direct"]}]
    if output_schema is not None:
        kwargs['output_config'] = {'format': {'type': 'json_schema', 'schema': output_schema}}
    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=model, max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}], **kwargs,
        )
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
        log.warning("KI-Anfrage fehlgeschlagen (%s): %s", log_ctx, e)
        return None, None, 'failed'
    if resp.stop_reason == 'refusal':
        return None, None, 'refused'
    text = "\n\n".join(b.text for b in resp.content if b.type == 'text').strip()
    if not text:
        return None, None, 'empty'
    u = resp.usage
    usage = {'input_tokens': u.input_tokens, 'output_tokens': u.output_tokens,
             'cache_creation_input_tokens': getattr(u, 'cache_creation_input_tokens', 0) or 0,
             'cache_read_input_tokens': getattr(u, 'cache_read_input_tokens', 0) or 0}
    return text, usage, None


def _ai_call(api_key: str, model: str, prompt: str, *, max_tokens: int, log_ctx: str):
    """Flask-Route-Wrapper um `_ai_request`: gleiche Erfolgs-Rückgabe (text, usage,
    None), Fehler als (None, None, (jsonify(...), status)) — für Endpunkte, die
    innerhalb eines Request-Handlers laufen."""
    text, usage, code = _ai_request(api_key, model, prompt, max_tokens=max_tokens,
                                    log_ctx=log_ctx)
    if code == 'failed':
        return None, None, (jsonify({'error': 'ai_failed'}), 502)
    if code == 'refused':
        return None, None, (jsonify({'error': 'ai_refused'}), 502)
    if code == 'empty':
        return None, None, (jsonify({'error': 'ai_empty'}), 502)
    return text, usage, None


_AI_TAG_VOCAB = [
    "Familie", "Strand", "Party & Nachtleben", "Ruhe & Erholung", "Wellness & Spa",
    "Sport & Aktiv", "Luxus", "Budget", "Alleinreisende", "Kultur & Sightseeing",
    "Adults Only", "Golf",
]
_AI_TAG_SCHEMA = {
    "type": "object",
    "properties": {"tags": {"type": "array", "items": {"type": "string"}, "maxItems": 4}},
    "required": ["tags"], "additionalProperties": False,
}


def _ai_auto_tags(h: dict, api_key: str, model: str) -> list | None:
    """2-4 passende Schlagworte aus einer festen Liste für ein Angebot vergeben
    (structured output, kein Websuche nötig). None bei jedem Fehler."""
    prompt = (
        "Vergib 2 bis 4 passende Schlagworte für folgendes Hotel/Reise-Angebot, "
        "ausschließlich aus dieser Liste (exakten Wortlaut übernehmen):\n"
        + ", ".join(_AI_TAG_VOCAB) + "\n\n"
        + "\n".join(_hotel_fact_lines(h)) + "\n\n"
        "Wähle nur Schlagworte, die durch die Fakten wirklich gestützt sind (z. B. "
        "'Familie' nur bei Hinweisen auf Kinderclub/Familienhotel, 'Party & "
        "Nachtleben' nur bei entsprechender Lage/Ausstattung). Lieber weniger, aber "
        "treffende Tags als geraten."
    )
    text, usage, code = _ai_request(api_key, model, prompt, max_tokens=300,
                                    log_ctx="Auto-Tags", use_web_search=False,
                                    output_schema=_AI_TAG_SCHEMA)
    if code or not text:
        return None
    try:
        tags = [t for t in json.loads(text).get('tags', []) if t in _AI_TAG_VOCAB]
    except (ValueError, AttributeError):
        return None
    usage['estimated_usd'] = _ai_call_cost(model, usage)
    _record_ai_usage(model, usage)
    return tags


@app.route('/api/ai/auto-tags', methods=['POST'])
def api_ai_auto_tags():
    """Vergibt automatisch Tags für 1..N ausgewählte Angebote (Sammelaktion) —
    ergänzt bestehende Tags, überschreibt sie nicht."""
    if (err := _require_api()):
        return err
    api_key, model = _ai_config()
    if not api_key:
        return jsonify({'error': 'no_api_key',
                        'note': 'Kein Anthropic API-Key in den Add-on-Einstellungen hinterlegt'}), 400
    data = request.get_json(silent=True) or {}
    ids = data.get('ids')
    if not isinstance(ids, list) or not ids:
        return jsonify({'error': 'invalid'}), 400
    want = {int(i) for i in ids if str(i).isdigit()}
    offers_by_id = {o['id']: o for o in _collect_offers() if o['id'] in want}
    results = {}
    for oid, o in offers_by_id.items():
        h = {'name': o.get('label') or o.get('hotel'), 'location': o.get('location'),
             'country': o.get('country'), 'stars': o.get('stars'),
             'recommendation': o.get('recommendation'), 'reviews': o.get('rating_count'),
             'price': o.get('price'), 'details': o.get('details')}
        tags = _ai_auto_tags(h, api_key, model)
        if tags is None:
            continue
        merged = list(dict.fromkeys((o.get('tags') or []) + tags))
        with db() as con:
            con.execute('UPDATE offers SET tags=? WHERE id=?',
                        (json.dumps(merged, ensure_ascii=False), oid))
        results[oid] = merged
    return jsonify({'results': results})


def _hotel_summary_prompt(hotel: dict, instructions: str) -> str:
    """Baut den KI-Fazit-Prompt: feste Hotel-Fakten + (ggf. vom Nutzer angepasste)
    Instruktionen."""
    facts = ("Erstelle eine ausführliche, ehrliche Einschätzung zu folgendem Hotel:\n\n"
             + "\n".join(_hotel_fact_lines(hotel)))
    return facts + "\n\n" + instructions


@app.route('/api/ai/hotel-summary', methods=['POST'])
def api_ai_hotel_summary():
    """Ausführliche KI-Einschätzung zu einem Hotel aus den Suchergebnissen (Lage,
    Zimmer, Gastronomie, Pool, Ausstattung, Fazit) — Claude durchsucht dafür live
    das Web nach Bewertungen. Gecacht je Hotel (giataId), um wiederholte teure
    Abrufe beim erneuten Öffnen zu vermeiden."""
    if (err := _require_api()):
        return err
    api_key, model = _ai_config()
    if not api_key:
        return jsonify({'error': 'no_api_key',
                        'note': 'Kein Anthropic API-Key in den Add-on-Einstellungen hinterlegt'}), 400
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'invalid'}), 400
    instructions = _prompt_instructions('summary', _DEFAULT_SUMMARY_INSTRUCTIONS)
    instr_hash = hashlib.sha1(instructions.encode('utf-8')).hexdigest()[:10]
    giata = data.get('giata')
    cache_key = f'{instr_hash}:' + (str(giata) if giata else name.lower())
    cached = _ai_summary_cache.get(cache_key)
    if cached and time.time() - cached['ts'] < _AI_SUMMARY_TTL:
        return jsonify({'summary': cached['summary'], 'usage': cached.get('usage'),
                        'totals': _ai_usage_totals(), 'id': cached.get('id'), 'cached': True})

    prompt = _hotel_summary_prompt(data, instructions)
    text, usage, err = _ai_call(api_key, model, prompt, max_tokens=4096, log_ctx=name)
    if err:
        return err
    usage['estimated_usd'] = _ai_call_cost(model, usage)
    totals = _record_ai_usage(model, usage)
    aid = _save_ai_analysis('single', name, model, text, usage)
    _ai_summary_cache[cache_key] = {'summary': text, 'usage': usage, 'id': aid, 'ts': time.time()}
    return jsonify({'summary': text, 'usage': usage, 'totals': totals, 'id': aid, 'cached': False})


@app.route('/api/ai/ask', methods=['POST'])
def api_ai_ask():
    """Freitext-Frage über das aktuelle Portfolio (alle nicht-archivierten
    Angebote): Preis, Ort, Sterne/Weiterempfehlung, Trend, Wunschpreis, Tags."""
    if (err := _require_api()):
        return err
    api_key, model = _ai_config()
    if not api_key:
        return jsonify({'error': 'no_api_key',
                        'note': 'Kein Anthropic API-Key in den Add-on-Einstellungen hinterlegt'}), 400
    data = request.get_json(silent=True) or {}
    question = (data.get('question') or '').strip()
    if not question:
        return jsonify({'error': 'invalid'}), 400
    offers = [o for o in _collect_offers() if not o.get('archived')]
    if not offers:
        return jsonify({'error': 'no_offers'}), 400

    def nm(o):
        return o.get('label') or o.get('hotel') or f"Angebot #{o['id']}"

    lines = []
    for o in offers:
        parts = [nm(o)]
        if o.get('location'):
            parts.append(o['location'])
        if o.get('stars'):
            parts.append(f"{o['stars']}★")
        if o.get('recommendation') is not None:
            parts.append(f"{o['recommendation']}% Weiterempfehlung")
        if o.get('price') is not None:
            parts.append(f"{_eur(o['price'])} p.P.")
        if o.get('delta'):
            parts.append(f"Δ letzte Prüfung {_eur(o['delta'])}")
        if o.get('target_price'):
            parts.append(f"Wunschpreis {_eur(o['target_price'])}")
        if o.get('return_date'):
            parts.append(f"Rückreise {o['return_date']}")
        if o.get('tags'):
            parts.append("Tags: " + ", ".join(o['tags']))
        lines.append("- " + " · ".join(str(p) for p in parts))

    prompt = (
        "Hier ist mein aktuelles Portfolio getrackter Reisen/Hotels bei TUIWatch:\n\n"
        + "\n".join(lines) + "\n\n"
        f"Frage dazu: {question}\n\n"
        "Antworte auf Deutsch, sprich den Nutzer dabei durchgehend mit „Du“ an "
        "(informell, nicht „Sie“), konkret und ausschließlich basierend auf den "
        "obigen Daten. Nenne die betroffenen Hotels beim Namen. Wenn die Daten die "
        "Frage nicht beantworten können, sag das offen statt zu spekulieren."
    )
    text, usage, err = _ai_call(api_key, model, prompt, max_tokens=1500, log_ctx="Portfolio-Frage")
    if err:
        return err
    usage['estimated_usd'] = _ai_call_cost(model, usage)
    totals = _record_ai_usage(model, usage)
    aid = _save_ai_analysis('ask', question, model, text, usage)
    return jsonify({'summary': text, 'usage': usage, 'totals': totals, 'id': aid, 'cached': False})


@app.route('/api/ai/prompt-settings', methods=['GET', 'POST'])
def api_ai_prompt_settings():
    """Eigene KI-Prompt-Vorlagen für Reiseberater/Hotelvergleich einsehen/speichern.
    GET liefert je Feature Default-Text + gespeicherten Custom-Text + Enabled-Flag;
    POST speichert je Feature unabhängig (toleriert Teil-Updates)."""
    if (err := _require_api()):
        return err
    if request.method == 'GET':
        return jsonify({
            feature: {
                'default': default,
                'enabled': _meta_get(f'custom_prompt_{feature}_enabled') == '1',
                'text': _meta_get(f'custom_prompt_{feature}_text') or '',
            }
            for feature, default in _PROMPT_FEATURES.items()
        })
    data = request.get_json(silent=True) or {}
    for feature in _PROMPT_FEATURES:
        fdata = data.get(feature)
        if not isinstance(fdata, dict):
            continue
        text = (fdata.get('text') or '').strip()[:_CUSTOM_PROMPT_MAX_LEN]
        _meta_set(f'custom_prompt_{feature}_enabled', '1' if fdata.get('enabled') else '0')
        _meta_set(f'custom_prompt_{feature}_text', text)
    return jsonify({'saved': True})


_ADVISOR_FIELDS = ('region', 'excluded_countries', 'excluded_countries_other', 'interests',
                   'travel_type', 'companions', 'budget', 'duration', 'month', 'temp', 'sea',
                   'rain', 'activities', 'accommodation', 'accommodation_size', 'hotel_wishes',
                   'flight_time', 'airports', 'dislikes', 'perfect_holiday', 'past_trips')
_ADVISOR_LIST_FIELDS = {'interests', 'travel_type', 'activities', 'hotel_wishes', 'airports',
                        'dislikes', 'excluded_countries'}
_ADVISOR_TEXT_FIELDS = {'perfect_holiday', 'past_trips', 'excluded_countries_other'}
_ADVISOR_LABELS = {
    'region': 'Ziel-Region', 'excluded_countries': 'Kommt nicht in Frage',
    'excluded_countries_other': 'Weitere ausgeschlossene Länder',
    'interests': 'Wichtig im Urlaub', 'travel_type': 'Reiseart',
    'companions': 'Reist mit', 'budget': 'Budget pro Person', 'duration': 'Reisedauer',
    'month': 'Reisezeit', 'temp': 'Gewünschte Temperatur', 'sea': 'Meer/Wasser',
    'rain': 'Niederschlag', 'activities': 'Gewünschte Aktivitäten',
    'accommodation': 'Unterkunftsart', 'accommodation_size': 'Hotelgröße',
    'hotel_wishes': 'Hotelwünsche', 'flight_time': 'Flugzeit', 'airports': 'Abflughafen',
    'dislikes': 'Nervt im Urlaub', 'perfect_holiday': 'Perfekter Urlaub laut Nutzer (Freitext)',
    'past_trips': 'Frühere Urlaubserfahrungen (Freitext)',
}


def _advisor_prompt(p: dict, prev_dna: dict | None = None) -> str:
    """Baut den Reiseberater-Prompt aus dem kompletten Profil (Region/Interessen/
    Reiseart/Budget/Reisezeit/Wetter/Aktivitäten/Unterkunft/Hotelwünsche/Flug/
    Abneigungen/Freitext) — freie KI-Empfehlung, nicht auf eigene Angebote
    beschränkt, mit Websuche für reale/aktuelle Klimadaten. `prev_dna` (optional)
    ist das aus früheren Anfragen gespeicherte Reise-DNA-Profil (Zusatzkontext)."""
    lines = ["Ein Nutzer sucht per Reiseberater-Fragebogen sein nächstes Urlaubsziel. "
             "Sein Profil:\n"]
    for key in _ADVISOR_FIELDS:
        val = p.get(key)
        if isinstance(val, list):
            val = ", ".join(str(v).strip() for v in val if str(v).strip())
        if val:
            lines.append(f"- {_ADVISOR_LABELS[key]}: {val}")
    if 'Pauschalreise (TUI)' in (p.get('travel_type') or []):
        lines.append(
            "\nWichtig: Der Nutzer will eine Pauschalreise (Flug + Hotel) über TUI "
            "buchen. Empfehle ausschließlich Ziele/Regionen, die TUI tatsächlich im "
            "Programm hat — prüfe das per Websuche (z. B. auf tui.com oder aktuellen "
            "TUI-Katalogseiten für das Zielland). Kein Ziel vorschlagen, das TUI "
            "nachweislich nicht anbietet."
        )
    if p.get('excluded_countries') or p.get('excluded_countries_other'):
        lines.append(
            "\nWichtig: Schlage unter keinen Umständen Ziele in den oben unter "
            "„Kommt nicht in Frage“/„Weitere ausgeschlossene Länder“ genannten "
            "Ländern/Regionen vor — auch nicht als Alternative."
        )
    if prev_dna:
        dna_line = ", ".join(f"{label} {value}%" for label, value in prev_dna.items())
        lines.append(
            f"\nZusatzkontext aus früheren Reiseberater-Anfragen dieses Nutzers "
            f"(Reise-DNA, grobe Tendenz, nicht überbewerten): {dna_line}."
        )
    lines.append(
        "\nUnabhängig von den Angaben oben: Prüfe für jedes in Betracht gezogene "
        "Land per Websuche, ob aktuell eine Reisewarnung oder ein Sicherheitshinweis "
        "des Auswärtigen Amts (oder vergleichbare offizielle Warnung) besteht, und "
        "schlage solche Länder nicht vor, außer der Nutzer hat sie oben ausdrücklich "
        "gewünscht (z. B. als Ziel-Region genannt)."
    )
    lines.append("\n" + _prompt_instructions('advisor', _DEFAULT_ADVISOR_INSTRUCTIONS))
    lines.append(_ADVISOR_SAFETY_TRAILER)
    return "\n".join(lines)


def _advisor_dna_scores(p: dict) -> dict:
    """Deterministisches Reise-DNA-Profil aus den Fragebogen-Antworten (kein
    zusätzlicher KI-Call) — je Kategorie ein grober 0-100-Score aus passenden
    Signalen über mehrere Fragen hinweg."""
    def has(key, *vals):
        v = p.get(key)
        if isinstance(v, list):
            return any(x in v for x in vals)
        return v in vals

    checks = {
        '🌴 Strand': [has('interests', '🌴 Strand'),
                     has('hotel_wishes', 'direkte Strandlage', 'Sandstrand', 'Hausriff'),
                     has('sea', '28°C+ (tropisch warm)', '24–27°C (angenehm warm)')],
        '🏛️ Kultur': [has('interests', '🏛️ Kultur'), has('activities', 'Museen', 'Fotografieren')],
        '🎉 Nachtleben': [has('interests', '🎉 Nachtleben')],
        '⛰️ Aktiv': [has('interests', '🚶 Wandern', '🚴 Radfahren'),
                    has('activities', 'Wandern', 'Mountainbike', 'Skifahren', 'Surfen', 'Golf')],
        '🍹 Entspannung': [has('interests', '🍹 Entspannung'), has('hotel_wishes', 'Spa', 'Ruhe')],
        '🍽️ Kulinarik': [has('interests', '🍽️ Essen'), has('activities', 'Kulinarik', 'Wein')],
        '👨‍👩‍👧 Familie': [has('interests', '👨‍👩‍👧 Familie'), has('companions', 'Familie'),
                        has('hotel_wishes', 'Familienhotel', 'Kinderpool', 'Rutschen')],
        '💰 Preisbewusst': [has('budget', 'bis 500 €'), has('budget', '500–1000 €')],
    }
    return {label: min(100, 15 + 35 * sum(1 for s in signals if s))
            for label, signals in checks.items()}


def _advisor_dna_update(new_scores: dict) -> dict:
    """Verschmilzt neue DNA-Werte mit dem gespeicherten Profil (gleitender
    Mittelwert) und persistiert sie in `meta`, damit sich das Profil über
    mehrere Reiseberater-Anfragen hinweg stabilisiert statt bei jedem Aufruf
    komplett neu zu sein."""
    try:
        prev = json.loads(_meta_get('travel_dna') or '{}')
    except (TypeError, ValueError):
        prev = {}
    prev_scores = prev.get('scores') or {}
    merged = {label: val if label not in prev_scores else round((prev_scores[label] + val) / 2)
              for label, val in new_scores.items()}
    _meta_set('travel_dna', json.dumps(
        {'scores': merged, 'count': (prev.get('count') or 0) + 1, 'updated_ts': int(time.time())},
        ensure_ascii=False))
    return merged


def _advisor_dna_table(scores: dict) -> str:
    rows = "\n".join(f"| {label} | {value}% |" for label, value in scores.items())
    return f"\n\n#### 🧬 Deine Reise-DNA\n| Kategorie | Ausprägung |\n|---|---|\n{rows}\n"


@app.route('/api/ai/travel-advisor', methods=['POST'])
def api_ai_travel_advisor():
    """KI-Reiseberater: aus einem kurzen Profil (Region, Interessen, Reiseart,
    Budget, Reisezeit, Wetterwünsche) schlägt Claude 3 passende Ziele vor — freie
    Empfehlung aus KI-Wissen + Websuche, unabhängig vom eigenen Angebots-Portfolio."""
    if (err := _require_api()):
        return err
    api_key, model = _ai_config()
    if not api_key:
        return jsonify({'error': 'no_api_key',
                        'note': 'Kein Anthropic API-Key in den Add-on-Einstellungen hinterlegt'}), 400
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({'error': 'invalid'}), 400
    profile = {}
    for key in _ADVISOR_FIELDS:
        val = data.get(key)
        if key in _ADVISOR_LIST_FIELDS:
            if isinstance(val, list):
                profile[key] = [str(v).strip()[:40] for v in val if str(v).strip()][:15]
        elif key in _ADVISOR_TEXT_FIELDS:
            if isinstance(val, str) and val.strip():
                profile[key] = val.strip()[:500]
        elif isinstance(val, str) and val.strip():
            profile[key] = val.strip()[:60]
    if not any(profile.values()):
        return jsonify({'error': 'invalid'}), 400

    try:
        prev_dna = (json.loads(_meta_get('travel_dna') or '{}')).get('scores') or {}
    except (TypeError, ValueError):
        prev_dna = {}
    prompt = _advisor_prompt(profile, prev_dna)
    title = profile.get('region') or 'Reiseberater'
    if profile.get('month'):
        title += ' · ' + profile['month']
    if profile.get('interests'):
        title += ' · ' + ', '.join(profile['interests'][:3])
    text, usage, err = _ai_call(api_key, model, prompt, max_tokens=3072, log_ctx='Reiseberater')
    if err:
        return err
    dna = _advisor_dna_update(_advisor_dna_scores(profile))
    text += _advisor_dna_table(dna)
    usage['estimated_usd'] = _ai_call_cost(model, usage)
    totals = _record_ai_usage(model, usage)
    aid = _save_ai_analysis('advisor', title, model, text, usage)
    return jsonify({'summary': text, 'usage': usage, 'totals': totals, 'id': aid, 'dna': dna,
                    'cached': False})


def _compare_prompt(hotels: list[dict], instructions: str) -> str:
    """Baut den Hotelvergleichs-Prompt: feste Hotel-Fakten-Blöcke + (ggf. vom
    Nutzer angepasste) Instruktionen."""
    blocks = ["\n".join(_hotel_fact_lines(h, label=f"Hotel {i}"))
              for i, h in enumerate(hotels, 1)]
    facts = ("Vergleiche ausführlich die folgenden Hotels für eine Reiseentscheidung:\n\n"
             + "\n\n".join(blocks))
    return facts + "\n\n" + instructions


@app.route('/api/ai/hotel-compare', methods=['POST'])
def api_ai_hotel_compare():
    """Vergleicht 2–5 Hotels aus den Suchergebnissen in einem KI-Aufruf: gleiche
    Kriterien wie beim Einzel-Fazit, plus Vergleichstabelle und Empfehlung, welches
    Hotel für wen (Familie, Paar, Ruhe, …) am besten passt."""
    if (err := _require_api()):
        return err
    api_key, model = _ai_config()
    if not api_key:
        return jsonify({'error': 'no_api_key',
                        'note': 'Kein Anthropic API-Key in den Add-on-Einstellungen hinterlegt'}), 400
    data = request.get_json(silent=True) or {}
    hotels = [h for h in (data.get('hotels') or [])
              if isinstance(h, dict) and (h.get('name') or '').strip()][:5]
    if len(hotels) < 2:
        return jsonify({'error': 'invalid'}), 400

    instructions = _prompt_instructions('compare', _DEFAULT_COMPARE_INSTRUCTIONS)
    instr_hash = hashlib.sha1(instructions.encode('utf-8')).hexdigest()[:10]
    cache_key = (f'cmp:{instr_hash}:'
                 + '|'.join(sorted(str(h.get('giata') or (h.get('name') or '').lower())
                                   for h in hotels)))
    cached = _ai_summary_cache.get(cache_key)
    if cached and time.time() - cached['ts'] < _AI_SUMMARY_TTL:
        return jsonify({'summary': cached['summary'], 'usage': cached.get('usage'),
                        'totals': _ai_usage_totals(), 'id': cached.get('id'), 'cached': True})

    prompt = _compare_prompt(hotels, instructions)
    text, usage, err = _ai_call(api_key, model, prompt, max_tokens=6144,
                                log_ctx=f"Vergleich {len(hotels)} Hotels")
    if err:
        return err
    usage['estimated_usd'] = _ai_call_cost(model, usage)
    totals = _record_ai_usage(model, usage)
    title = ' · '.join(h.get('name', '') for h in hotels)
    aid = _save_ai_analysis('compare', title, model, text, usage)
    _ai_summary_cache[cache_key] = {'summary': text, 'usage': usage, 'id': aid, 'ts': time.time()}
    return jsonify({'summary': text, 'usage': usage, 'totals': totals, 'id': aid, 'cached': False})


def _ai_md_to_html(text: str) -> str:
    """Sehr einfacher Markdown→HTML-Renderer fürs E-Mail-Layout (Überschriften,
    Listen, Tabellen, **fett**) — spiegelt die JS-Variante `aiMdLite` im Frontend."""
    def esc(s):
        return _esc_html(s)

    def inline(s):
        return re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s)

    def row(l):
        return [inline(c.strip()) for c in l.strip().strip('|').split('|')]

    lines = esc(text).split('\n')
    html, in_list, i = [], False, 0

    def close_list():
        nonlocal in_list
        if in_list:
            html.append('</ul>')
            in_list = False

    while i < len(lines):
        line = lines[i].strip()
        if not line:
            close_list()
            i += 1
            continue
        if line.startswith('|') and i + 1 < len(lines) \
                and re.match(r'^\|?[\s:|-]+\|?$', lines[i + 1].strip()):
            close_list()
            header = row(line)
            body_rows, j = [], i + 2
            while j < len(lines) and lines[j].strip().startswith('|'):
                body_rows.append(row(lines[j]))
                j += 1
            html.append('<table style="width:100%;border-collapse:collapse;'
                        'margin:8px 0 16px;font-size:13px"><thead><tr>'
                        + ''.join(f'<th style="text-align:left;padding:6px 8px;'
                                 f'border-bottom:1px solid #ddd;color:#777">{c}</th>'
                                 for c in header)
                        + '</tr></thead><tbody>'
                        + ''.join('<tr>' + ''.join(
                            f'<td style="padding:6px 8px;border-bottom:1px solid #eee">{c}</td>'
                            for c in r) + '</tr>' for r in body_rows)
                        + '</tbody></table>')
            i = j
            continue
        h = re.match(r'^#{1,4}\s+(.*)', line)
        b = re.match(r'^[-*]\s+(.*)', line)
        if h:
            close_list()
            html.append(f'<h3 style="margin:18px 0 6px;color:#10243e;font-size:15px">'
                        f'{inline(h.group(1))}</h3>')
        elif b:
            if not in_list:
                html.append('<ul style="margin:0;padding-left:18px;color:#333;font-size:14px">')
                in_list = True
            html.append(f'<li style="margin:4px 0">{inline(b.group(1))}</li>')
        else:
            close_list()
            html.append(f'<p style="margin:0 0 10px;color:#333;font-size:14px;'
                        f'line-height:1.45">{inline(line)}</p>')
        i += 1
    close_list()
    return ''.join(html)


@app.route('/api/ai/email', methods=['POST'])
def api_ai_email():
    """Eine gespeicherte KI-Analyse (Fazit oder Vergleich, per ID aus `ai_analyses`)
    als HTML-Mail versenden — funktioniert für frische wie für Verlaufs-Ergebnisse,
    da beide immer eine ID haben. Empfänger optional aus dem Nextcloud-Adressbuch
    (bestehender `/api/contacts`-Autocomplete im UI)."""
    if (err := _require_api()):
        return err
    if not smtp_configured():
        return jsonify({'error': 'smtp_not_configured'}), 400
    data = request.get_json(silent=True) or {}
    to = (data.get('to') or load_config().get('smtp_to') or '').strip()
    if not to:
        return jsonify({'error': 'no_recipient'}), 400
    aid = data.get('id')
    with db() as con:
        row = con.execute('SELECT * FROM ai_analyses WHERE id=?', (aid,)).fetchone() if aid else None
    if not row:
        return jsonify({'error': 'not_found'}), 404
    kind_label = 'KI-Vergleich' if row['kind'] == 'compare' else 'KI-Fazit'
    subject = f"TUIWatch — {kind_label}: {row['title']}"[:200]
    html = (
        '<div style="font-family:system-ui,Arial,sans-serif;max-width:640px;margin:0 auto">'
        f'<h2 style="color:#10243e">🤖 {kind_label}</h2>'
        f'<p style="color:#555;font-size:13px">{_esc_html(row["title"])}</p>'
        + _ai_md_to_html(row['summary'])
        + '</div>'
    )
    try:
        send_email(subject, html, to)
    except Exception as e:
        log.error("KI-Analyse-E-Mail fehlgeschlagen: %s", e)
        return jsonify({'error': 'send_failed'}), 502
    log.info("KI-Analyse #%s per E-Mail an %s gesendet", aid, to)
    return jsonify({'sent': True, 'to': to})


@app.route('/api/ai/history', methods=['GET'])
def api_ai_history():
    """Liste bisheriger KI-Fazits/-Vergleiche (neueste zuerst) für den KI-Verlauf."""
    if (err := _require_api()):
        return err
    with db() as con:
        rows = con.execute(
            'SELECT id, kind, title, model, ts, substr(summary,1,160) AS preview '
            'FROM ai_analyses ORDER BY id DESC LIMIT ?', (_AI_HISTORY_MAX,)).fetchall()
    return jsonify({'items': [dict(r) for r in rows]})


@app.route('/api/ai/history/<int:aid>', methods=['GET'])
def api_ai_history_get(aid: int):
    """Vollständigen gespeicherten Analyse-Eintrag laden (fürs erneute Anzeigen)."""
    if (err := _require_api()):
        return err
    with db() as con:
        row = con.execute('SELECT * FROM ai_analyses WHERE id=?', (aid,)).fetchone()
    if not row:
        return jsonify({'error': 'not_found'}), 404
    d = dict(row)
    try:
        d['usage'] = json.loads(d.get('usage') or '{}')
    except (TypeError, ValueError):
        d['usage'] = {}
    return jsonify(d)


@app.route('/api/ai/history/<int:aid>', methods=['DELETE'])
def api_ai_history_delete(aid: int):
    if (err := _require_api()):
        return err
    with db() as con:
        con.execute('DELETE FROM ai_analyses WHERE id=?', (aid,))
    return jsonify({'ok': True})


_dest_cache: dict = {}     # parent → {parentName, items}
_airports_cache: list = []  # einmalig geladen
_contacts_cache: list = []  # Nextcloud-Adressbuch, gecacht bis ?refresh=1

# ── Reiseziel-Index (globale Suche über alle Ebenen) ───────────────────────────
# Der Picker lädt je Ebene nach (Land → Region → Insel …). Für eine Suche, die auch
# tief verschachtelte Ziele wie "Kanarische Inseln" (unter Spanien) findet, halten
# wir einen flachen Index des kompletten Baums vor. Der Aufbau ist teuer (~1000+
# API-Aufrufe), daher persistiert in der DB und nur beim Start bzw. manuell erneuert
# — Regionen ändern sich selten.
_DEST_INDEX_TTL = 14 * 86400  # 14 Tage
_dest_index: list = []
_dest_index_ts: int = 0
_dest_index_lock = threading.Lock()
_dest_index_building = False


def _load_dest_index() -> None:
    """Persistierten Reiseziel-Index aus der DB in den Speicher laden."""
    global _dest_index, _dest_index_ts
    raw = _meta_get('dest_index')
    if raw:
        try:
            _dest_index = json.loads(raw)
            _dest_index_ts = int(_meta_get('dest_index_ts') or 0)
        except Exception:
            _dest_index = []


def _build_dest_index() -> None:
    """Kompletten Reiseziel-Baum crawlen (teuer!) und persistieren. Läuft im
    Hintergrund; parallele Aufrufe werden zusammengefasst."""
    global _dest_index, _dest_index_ts, _dest_index_building
    with _dest_index_lock:
        if _dest_index_building:
            return
        _dest_index_building = True
    try:
        log.info("Reiseziel-Index wird aufgebaut …")
        items = build_destination_index()
        if items:
            _dest_index = items
            _dest_index_ts = int(time.time())
            _meta_set('dest_index', json.dumps(items, ensure_ascii=False))
            _meta_set('dest_index_ts', _dest_index_ts)
            log.info("Reiseziel-Index bereit: %d Einträge", len(items))
        else:
            log.warning("Reiseziel-Index leer geblieben (API nicht erreichbar?)")
    finally:
        _dest_index_building = False


def _ensure_dest_index() -> None:
    """Beim Start: Index aus DB laden; wenn leer oder veraltet, neu aufbauen."""
    _load_dest_index()
    if not _dest_index or (int(time.time()) - _dest_index_ts) > _DEST_INDEX_TTL:
        _build_dest_index()


def _search_dest_index(q: str, limit: int = 60) -> list:
    """Treffer im Index (Teilstring im Namen), Präfix-Treffer zuerst."""
    ql = q.lower()
    out = [it for it in _dest_index if ql in (it.get('label') or '').lower()]
    out.sort(key=lambda it: (not (it.get('label') or '').lower().startswith(ql),
                             (it.get('label') or '').lower()))
    return out[:limit]


@app.route('/api/destinations', methods=['GET'])
def api_destinations():
    """Reiseziele für den Picker (Top-Level oder Unterregionen zu ?parent=…)."""
    if (err := _require_api()):
        return err
    parent = (request.args.get('parent') or '').strip() or None
    if parent not in _dest_cache:
        d = fetch_destinations(parent)
        if d is None:
            return jsonify({'error': 'unavailable'}), 502
        _dest_cache[parent] = d
    return jsonify(_dest_cache[parent])


@app.route('/api/destinations/search', methods=['GET'])
def api_destinations_search():
    """Globale Reiseziel-Suche über alle Ebenen (nutzt den gecachten Index)."""
    if (err := _require_api()):
        return err
    q = (request.args.get('q') or '').strip()
    if not _dest_index and not _dest_index_building:
        _spawn(_build_dest_index)  # erster Aufbau on-demand
    if len(q) < 2:
        return jsonify({'items': [], 'building': _dest_index_building,
                        'ready': bool(_dest_index)})
    return jsonify({'items': _search_dest_index(q),
                    'building': _dest_index_building, 'ready': bool(_dest_index),
                    'ts': _dest_index_ts})


@app.route('/api/destinations/reindex', methods=['POST'])
def api_destinations_reindex():
    """Reiseziel-Index manuell neu aufbauen (Hintergrund)."""
    if (err := _require_api()):
        return err
    _spawn(_build_dest_index)
    return jsonify({'ok': True, 'building': True})


# ── Suchabo: gespeicherte Suche beobachten (Sammel-Alarm) ───────────────────────

def _search_from_fav_payload(p: dict) -> dict | None:
    """Führt die Suche eines gespeicherten Favoriten aus (gleiche Payload-Form wie das
    UI sie speichert) und wendet die Nachfilter Sterne/Weiterempfehlung an."""
    dest = p.get('dest') or {}
    try:
        region = int(dest.get('giata'))
    except (TypeError, ValueError):
        return None
    duration = 'exact' if p.get('exact') else (p.get('dur') or 7)
    res = fetch_search_params(
        region=region, start=(p.get('vom') or '').strip(), end=(p.get('bis') or '').strip(),
        duration=duration, travellers=p.get('trav') or 2,
        airports=[a for a in [(p.get('airport') or '').strip()] if a],
        operator_tui=p.get('tui') is not False,
        boards=[str(b) for b in (p.get('boards') or []) if str(b).strip()],
        airlines=[str(a) for a in (p.get('airlines') or []) if str(a).strip()],
        location=[int(i) for i in (p.get('location') or []) if str(i).strip().isdigit()],
        direct=bool(p.get('direct')), verbose=_verbose())
    if not res or not res.get('ok'):
        return res

    def _num(v):
        try:
            return float(v or 0)
        except (TypeError, ValueError):
            return 0
    min_stars, min_rec = _num(p.get('stars')), _num(p.get('rec'))
    out = [r for r in res['results']
           if (not min_stars or (r.get('stars') or 0) >= min_stars)
           and (not min_rec or (r.get('recommendation') or 0) >= min_rec)]
    return {'ok': True, 'results': out}


def _esc_html(s) -> str:
    return str(s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _notify_search_watch(name: str, new: list, limit: float) -> None:
    """Meldet neue/tiefere Suchabo-Treffer per HA + Telegram."""
    head = (f"{len(new)} Hotels" if len(new) != 1 else "1 Hotel") + f" unter {_eur(limit)}"
    plain = [f"• {r.get('name')}: {_eur(r.get('price'))}"
             + (f" — {r['location']}" if r.get('location') else '') for r in new[:8]]
    tg = [f'• <a href="{_esc_html(r.get("offer_url"))}">{_esc_html(r.get("name"))}</a>: '
          f'<b>{_eur(r.get("price"))}</b>'
          + (f" — {_esc_html(r['location'])}" if r.get('location') else '') for r in new[:8]]
    more = f"… und {len(new) - 8} weitere" if len(new) > 8 else ''
    _notify_ha(f"🔎 Suchabo „{name}“: {head}",
               "\n".join(plain + ([more] if more else [])), f"watch_{_slug(name)}")
    _notify_telegram(f"🔎 <b>Suchabo „{_esc_html(name)}“</b>\n{head}\n"
                     + "\n".join(tg + ([more] if more else [])))


def _check_search_watch(sid: int) -> dict | None:
    """Führt EIN Suchabo aus: Suche laufen lassen, Treffer ≤ Schwellenpreis ermitteln
    und neue bzw. weiter gefallene Hotels melden. `seen` merkt je Hotel (giata) den
    tiefsten gemeldeten Preis — steigt ein Hotel über die Schwelle, wird es vergessen
    und beim nächsten Unterschreiten erneut gemeldet. Rückgabe {hits, new} oder None."""
    with db() as con:
        row = con.execute('SELECT * FROM saved_searches WHERE id=?', (sid,)).fetchone()
    if not row or not row['watch'] or not row['max_price']:
        return None
    try:
        payload = json.loads(row['payload'])
    except Exception:
        payload = {}
    res = _search_from_fav_payload(payload)
    ts = int(time.time())
    if not res or not res.get('ok'):
        with db() as con:
            con.execute('UPDATE saved_searches SET last_checked=? WHERE id=?', (ts, sid))
        log.warning("Suchabo „%s“: Suche fehlgeschlagen (%s)", row['name'],
                    (res or {}).get('note') or 'API-Fehler')
        return None
    limit = float(row['max_price'])
    hits = [r for r in res['results'] if r.get('price') is not None and r['price'] <= limit]
    try:
        seen = json.loads(row['seen'] or '{}')
    except Exception:
        seen = {}
    new, now_seen = [], {}
    for r in hits:
        g = str(r.get('giata') or '')
        if not g:
            continue
        prev = seen.get(g)
        if prev is None or r['price'] < prev:
            new.append(r)
        now_seen[g] = min(prev, r['price']) if prev is not None else r['price']
    hits_slim = [{k: r.get(k) for k in ('giata', 'name', 'price', 'location', 'stars',
                                        'recommendation', 'board', 'nights', 'date',
                                        'offer_url', 'image')} for r in hits]
    with db() as con:
        con.execute('UPDATE saved_searches SET seen=?, hits=?, last_checked=? WHERE id=?',
                    (json.dumps(now_seen), json.dumps(hits_slim, ensure_ascii=False), ts, sid))
    if new:
        try:
            _notify_search_watch(row['name'], new, limit)
        except Exception as e:
            log.error("Suchabo-Benachrichtigung fehlgeschlagen: %s", e)
    log.info("Suchabo „%s“: %d Treffer ≤ %s, davon %d neu", row['name'],
             len(hits), _eur(limit), len(new))
    return {'hits': hits_slim, 'new': len(new)}


def _maybe_check_watches() -> None:
    """Prüft fällige Suchabos (höchstens 1×/poll_interval je Abo, mindestens 1 h Abstand
    — Fairness gegenüber der Such-API)."""
    try:
        interval = int(load_config().get('poll_interval', POLL_INTERVAL_DEFAULT)
                       or POLL_INTERVAL_DEFAULT)
    except (TypeError, ValueError):
        interval = POLL_INTERVAL_DEFAULT
    interval = max(3600, interval)
    now = int(time.time())
    with db() as con:
        due = [r['id'] for r in con.execute(
            'SELECT id FROM saved_searches WHERE COALESCE(watch,0)=1 '
            'AND COALESCE(max_price,0)>0 AND COALESCE(last_checked,0)<=? ORDER BY id',
            (now - interval,)).fetchall()]
    for sid in due:
        try:
            _check_search_watch(sid)
        except Exception as e:
            log.error("Suchabo #%d fehlgeschlagen: %s", sid, e)


@app.route('/api/searches', methods=['GET', 'POST'])
def api_searches():
    """Gespeicherte Suchen (Favoriten) — in der DB, geräteübergreifend.
    GET → Liste; POST {name, payload} → anlegen/aktualisieren (per Name)."""
    if (err := _require_api()):
        return err
    if request.method == 'GET':
        with db() as con:
            rows = con.execute(
                'SELECT id, name, payload, watch, max_price, last_checked, hits '
                'FROM saved_searches ORDER BY name COLLATE NOCASE').fetchall()
        out = []
        for r in rows:
            try:
                payload = json.loads(r['payload'])
            except Exception:
                payload = {}
            try:
                hits = json.loads(r['hits'] or '[]')
            except Exception:
                hits = []
            out.append({'id': r['id'], 'name': r['name'], 'payload': payload,
                        'watch': bool(r['watch']), 'max_price': r['max_price'],
                        'last_checked': r['last_checked'], 'hits': hits})
        return jsonify({'searches': out})
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name_required'}), 400
    payload = json.dumps(data.get('payload') or {}, ensure_ascii=False)
    ts = int(time.time())
    with db() as con:
        row = con.execute('SELECT id FROM saved_searches WHERE name=?', (name,)).fetchone()
        if row:
            con.execute('UPDATE saved_searches SET payload=?, ts=? WHERE id=?',
                        (payload, ts, row['id']))
            sid = row['id']
        else:
            cur = con.execute(
                'INSERT INTO saved_searches (name, payload, ts) VALUES (?,?,?)',
                (name, payload, ts))
            sid = cur.lastrowid
    return jsonify({'ok': True, 'id': sid})


@app.route('/api/searches/<int:sid>', methods=['DELETE'])
def api_searches_delete(sid):
    """Gespeicherte Suche löschen."""
    if (err := _require_api()):
        return err
    with db() as con:
        con.execute('DELETE FROM saved_searches WHERE id=?', (sid,))
    return jsonify({'ok': True})


@app.route('/api/searches/<int:sid>', methods=['PATCH'])
def api_searches_patch(sid):
    """Suchabo-Einstellungen einer gespeicherten Suche: {watch, max_price}."""
    if (err := _require_api()):
        return err
    data = request.get_json(silent=True) or {}
    with db() as con:
        row = con.execute('SELECT id, name, watch FROM saved_searches WHERE id=?',
                          (sid,)).fetchone()
        if not row:
            return jsonify({'error': 'not_found'}), 404
        if 'max_price' in data:
            mp = data.get('max_price')
            try:
                mp = float(mp) if mp not in (None, '', 0) else None
            except (TypeError, ValueError):
                mp = None
            con.execute('UPDATE saved_searches SET max_price=? WHERE id=?', (mp, sid))
        if 'watch' in data:
            on = 1 if data.get('watch') else 0
            con.execute('UPDATE saved_searches SET watch=? WHERE id=?', (on, sid))
            if on and not row['watch']:
                # frisch aktiviert → Meldegedächtnis zurücksetzen, damit der nächste
                # Lauf den aktuellen Stand unter der Schwelle einmal komplett meldet
                con.execute("UPDATE saved_searches SET seen='{}', hits='[]', "
                            "last_checked=0 WHERE id=?", (sid,))
            log.info("Suchabo „%s“ %s", row['name'], "aktiviert" if on else "deaktiviert")
    return jsonify({'ok': True})


@app.route('/api/searches/<int:sid>/check', methods=['POST'])
def api_searches_check(sid):
    """Suchabo sofort prüfen (synchron) — liefert die aktuellen Treffer zurück."""
    if (err := _require_api()):
        return err
    with db() as con:
        row = con.execute('SELECT watch, max_price FROM saved_searches WHERE id=?',
                          (sid,)).fetchone()
    if not row:
        return jsonify({'error': 'not_found'}), 404
    if not row['watch'] or not row['max_price']:
        return jsonify({'error': 'not_watching'}), 400
    res = _check_search_watch(sid)
    if res is None:
        return jsonify({'error': 'search_failed'}), 502
    return jsonify({'ok': True, 'hits': res['hits'], 'new': res['new']})


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


@app.route('/api/trips/next', methods=['GET'])
def api_trips_next():
    """Nächste bevorstehende Reise fürs Header-Countdown (ohne PII wie Reisende/Preise)."""
    if (err := _require_api()):
        return err
    return jsonify({'trip': _next_trip()})


@app.route('/api/trips', methods=['GET'])
def api_trips():
    """Liste gebuchter Reisen + aggregierte Statistik."""
    if (err := _require_api()):
        return err
    with db() as con:
        rows = con.execute(
            'SELECT id, booking_code, booking_date, title, destination, hotel, '
            'hotel_code, start_date, end_date, nights, travellers, total_price, '
            'package_price, net_per_night, meal, pdf_name, orig_name FROM trips '
            'ORDER BY start_date DESC, id DESC').fetchall()
    trips = [dict(r) for r in rows]
    for t in trips:
        t['has_pdf'] = bool(t.get('pdf_name'))
    nights_sum = sum((t['nights'] or 0) for t in trips)
    total_sum = sum((t['total_price'] or 0.0) for t in trips)
    package_sum = sum((t['package_price'] or 0.0) for t in trips)
    # Eigener Anteil je Reise = Gesamtpreis / Anzahl Reisende, aufsummiert.
    own_sum = sum((t['total_price'] or 0.0) / (t['travellers'] or 1) for t in trips)
    # Personen-Nächte (Nächte × Reisende) → Ø-Preis pro Person und Nacht, damit Solo- und
    # Gruppenreisen vergleichbar sind.
    pers_nights = sum((t['nights'] or 0) * (t['travellers'] or 1) for t in trips)
    stats = {
        'count': len(trips),
        'nights_sum': nights_sum,
        'total_sum': round(total_sum, 2),
        'own_sum': round(own_sum, 2),
        'package_sum': round(package_sum, 2),
        'avg_per_night': round(total_sum / pers_nights, 2) if pers_nights else 0.0,
    }
    # Aufschlüsselung pro Reisejahr (nach Reisebeginn)
    years: dict = {}
    for t in trips:
        y = (t['start_date'] or '')[:4]
        if not y:
            continue
        a = years.setdefault(y, {'year': y, 'count': 0, 'nights_sum': 0,
                                 'total_sum': 0.0, 'own_sum': 0.0, '_pn': 0})
        a['count'] += 1
        a['nights_sum'] += t['nights'] or 0
        a['total_sum'] += t['total_price'] or 0.0
        a['own_sum'] += (t['total_price'] or 0.0) / (t['travellers'] or 1)
        a['_pn'] += (t['nights'] or 0) * (t['travellers'] or 1)
    by_year = []
    for y in sorted(years, reverse=True):
        a = years[y]
        pn = a.pop('_pn')
        a['total_sum'] = round(a['total_sum'], 2)
        a['own_sum'] = round(a['own_sum'], 2)
        a['avg_per_night'] = round(a['total_sum'] / pn, 2) if pn else 0.0
        by_year.append(a)
    return jsonify({'trips': trips, 'stats': stats, 'by_year': by_year})


@app.route('/api/trips/<int:tid>', methods=['GET'])
def api_trip_detail(tid):
    """Vollständige Detaildaten einer Reise (geparstes JSON)."""
    if (err := _require_api()):
        return err
    with db() as con:
        row = con.execute('SELECT * FROM trips WHERE id=?', (tid,)).fetchone()
    if not row:
        return jsonify({'error': 'not_found'}), 404
    trip = dict(row)
    try:
        trip['data'] = json.loads(trip.get('data') or '{}')
    except Exception:
        trip['data'] = {}
    trip['has_pdf'] = bool(trip.get('pdf_name'))
    trip['warnings'] = check_fields(trip['data'])
    with db() as con:
        atts = con.execute(
            'SELECT id, orig_name, created FROM trip_attachments WHERE trip_id=? ORDER BY id',
            (tid,)).fetchall()
        if not row['packing_seeded']:
            con.executemany(
                'INSERT INTO trip_packing_items '
                '(trip_id, category, label, checked, created) VALUES (?,?,?,?,?)',
                [(tid,) + r for r in default_packing_rows(int(time.time()))])
            con.execute('UPDATE trips SET packing_seeded=1 WHERE id=?', (tid,))
        packing = con.execute(
            'SELECT id, category, label, checked FROM trip_packing_items '
            'WHERE trip_id=? ORDER BY id', (tid,)).fetchall()
    trip['attachments'] = [dict(a) for a in atts]
    trip['packing'] = [dict(p) for p in packing]
    return jsonify(trip)


# Alle Feld-Labels, die check_fields() melden kann — für die „erkannt/leer"-Übersicht
# im Debug-Modus (feste Reihenfolge wie im PDF).
_TRIP_FIELD_LABELS = ('Buchungsnummer', 'Buchungsdatum', 'Reiseziel', 'Hotel',
                      'Reisezeitraum', 'Nächte', 'Verpflegung', 'Gesamtpreis',
                      'Reisende', 'Flüge', 'Hinflug', 'Rückflug')


def _trip_debug_payload(raw: bytes) -> dict:
    """Debug-Sicht auf eine Reise-PDF: bereinigter Volltext (Basis der Feld-Regexes),
    geparstes JSON, Warnungen und je Feld erkannt/leer. Inhalte können PII enthalten —
    sie gehen nur an den (authentifizierten) Aufrufer, nichts davon ins Log."""
    try:
        full = extract_pdf_text(io.BytesIO(raw))
    except Exception:
        return {'ok': False, 'error': 'text_failed'}
    cleaned = _clean_text(full)
    data, parse_error = None, None
    try:
        data = parse_tui_text(full)
    except Exception as exc:
        parse_error = type(exc).__name__
    warnings = check_fields(data) if data else list(_TRIP_FIELD_LABELS)
    fields = [{'label': lbl, 'ok': lbl not in warnings} for lbl in _TRIP_FIELD_LABELS]
    return {'ok': True, 'cleaned_text': cleaned, 'data': data,
            'parse_error': parse_error, 'warnings': warnings, 'fields': fields}


@app.route('/api/trips/<int:tid>/debug', methods=['GET'])
def api_trip_debug(tid):
    """Debug-Modus zu einer gespeicherten Reise-PDF (bereinigter Text + Parse-Ergebnis).
    Hilft, bei einer TUI-Layout-Änderung zu sehen, WARUM ein Feld nicht erkannt wurde."""
    if (err := _require_api()):
        return err
    with db() as con:
        row = con.execute('SELECT pdf_name FROM trips WHERE id=?', (tid,)).fetchone()
    if not row or not row['pdf_name']:
        return jsonify({'error': 'not_found'}), 404
    p = _trip_pdf_path(row['pdf_name'])
    if p is None or not p.exists():
        return jsonify({'error': 'not_found'}), 404
    return jsonify(_trip_debug_payload(p.read_bytes()))


@app.route('/api/trips/debug', methods=['POST'])
def api_trip_debug_upload():
    """Debug-Modus für eine hochgeladene PDF, OHNE sie zu speichern — z. B. wenn der
    Import mit „nicht lesbar" fehlschlägt."""
    if (err := _require_api()):
        return err
    file = request.files.get('pdf')
    if file is None or not file.filename:
        return jsonify({'error': 'no_file'}), 400
    raw = file.read()
    if not raw:
        return jsonify({'error': 'empty'}), 400
    if len(raw) > MAX_PDF_BYTES:
        return jsonify({'error': 'too_large'}), 413
    return jsonify(_trip_debug_payload(raw))


# Erlaubte Spalten der trips-Tabelle (feste Whitelist, exakte Insert-/Update-Reihenfolge).
# Bewusst als Konstante, damit CodeQL sieht: die SQL-Struktur stammt aus Code, nicht aus Daten.
_TRIP_COLUMNS = (
    'booking_code', 'booking_date', 'title', 'destination', 'hotel', 'hotel_code',
    'start_date', 'end_date', 'nights', 'travellers', 'total_price', 'package_price',
    'net_per_night', 'meal', 'data', 'pdf_name', 'orig_name', 'created',
)


_AI_TRIP_FIELD_SCHEMA = {
    "type": "object",
    "properties": {
        "buchungsnummer": {"type": ["string", "null"]},
        "buchungsdatum": {"type": ["string", "null"]},
        "reiseziel": {"type": ["string", "null"]},
        "hotel_name": {"type": ["string", "null"]},
        "reisezeitraum_von": {"type": ["string", "null"],
                              "description": "Anreisedatum, Format TT.MM.JJJJ"},
        "reisezeitraum_bis": {"type": ["string", "null"],
                              "description": "Abreisedatum, Format TT.MM.JJJJ"},
        "naechte": {"type": ["integer", "null"]},
        "verpflegung": {"type": ["string", "null"]},
        "gesamtpreis": {"type": ["string", "null"],
                       "description": "Format '1.234,56' (deutsches Zahlenformat, ohne €)"},
        "reisende_anzahl": {"type": ["integer", "null"]},
    },
    "required": ["buchungsnummer", "buchungsdatum", "reiseziel", "hotel_name",
                "reisezeitraum_von", "reisezeitraum_bis", "naechte", "verpflegung",
                "gesamtpreis", "reisende_anzahl"],
    "additionalProperties": False,
}


def _ai_fill_trip_fields(data: dict, warnings: list, cleaned_text: str,
                         api_key: str, model: str) -> tuple[dict, list]:
    """Ergänzt NUR die von `check_fields()` als fehlend markierte Top-Level-Felder
    per KI aus dem PDF-Text — überschreibt nie bereits vom Regex-Parser erkannte
    Werte (der bleibt die primäre, vertrauenswürdigere Quelle). Fällt TUI-Text ohne
    Key/Fehler auf die unveränderten Regex-Daten zurück. Rückgabe: (data, filled_labels)."""
    if not warnings or not api_key:
        return data, []
    prompt = (
        "Extrahiere aus folgendem Text einer TUI-Reisebestätigung NUR diese Felder "
        "als JSON. Fehlt eine Information wirklich, gib null zurück statt zu raten "
        "oder zu erfinden.\n\n" + cleaned_text[:6000]
    )
    try:
        text, usage, code = _ai_request(api_key, model, prompt, max_tokens=800,
                                        log_ctx="PDF-Fallback", use_web_search=False,
                                        output_schema=_AI_TRIP_FIELD_SCHEMA)
        if code or not text:
            return data, []
        ai = json.loads(text)
        usage['estimated_usd'] = _ai_call_cost(model, usage)
        _record_ai_usage(model, usage)
    except Exception as e:
        log.warning("PDF-Fallback (KI) fehlgeschlagen: %s", e)
        return data, []

    filled = []
    if "Buchungsnummer" in warnings and ai.get('buchungsnummer'):
        data['buchungsnummer'] = ai['buchungsnummer']
        filled.append("Buchungsnummer")
    if "Buchungsdatum" in warnings and ai.get('buchungsdatum'):
        data['buchungsdatum'] = ai['buchungsdatum']
        filled.append("Buchungsdatum")
    if "Reiseziel" in warnings and ai.get('reiseziel'):
        data['reiseziel'] = ai['reiseziel']
        filled.append("Reiseziel")
    if "Hotel" in warnings and ai.get('hotel_name'):
        data.setdefault('hotel', {})['name'] = ai['hotel_name']
        filled.append("Hotel")
    if "Reisezeitraum" in warnings and ai.get('reisezeitraum_von') and ai.get('reisezeitraum_bis'):
        data['reisezeitraum'] = {'von': ai['reisezeitraum_von'], 'bis': ai['reisezeitraum_bis']}
        filled.append("Reisezeitraum")
    if "Nächte" in warnings and ai.get('naechte'):
        data['naechte'] = ai['naechte']
        filled.append("Nächte")
    if "Verpflegung" in warnings and ai.get('verpflegung'):
        data['verpflegung'] = ai['verpflegung']
        filled.append("Verpflegung")
    if "Gesamtpreis" in warnings and ai.get('gesamtpreis'):
        data['gesamtpreis'] = ai['gesamtpreis']
        filled.append("Gesamtpreis")
    if "Reisende" in warnings and ai.get('reisende_anzahl'):
        # nur die Anzahl zählt für `travellers` beim Import — keine synthetischen Namen
        data['reisende'] = [{} for _ in range(ai['reisende_anzahl'])]
        filled.append("Reisende")
    return data, filled


@app.route('/api/trips/import', methods=['POST'])
def api_trip_import():
    """TUI-Reisebestätigungs-PDF hochladen, parsen, dauerhaft speichern (Upsert
    per Buchungsnummer)."""
    if (err := _require_api()):
        return err
    file = request.files.get('pdf')
    if file is None or not file.filename:
        return jsonify({'error': 'no_file'}), 400
    if Path(file.filename).suffix.lower() != '.pdf':
        return jsonify({'error': 'not_pdf'}), 400

    raw = file.read()
    if not raw:
        return jsonify({'error': 'empty'}), 400
    if len(raw) > MAX_PDF_BYTES:
        return jsonify({'error': 'too_large'}), 413

    try:
        data = parse_tui_pdf(io.BytesIO(raw))
    except Exception as exc:
        log.warning("PDF-Import fehlgeschlagen: %s", exc)
        return jsonify({'error': 'parse_failed'}), 422

    # KI-Fallback: fehlende Felder (Regex-Parser bei TUI-Layout-Änderung o. Ä.
    # gescheitert) ergänzen, ohne bereits erkannte Werte zu überschreiben. Best
    # effort — ohne Key oder bei jedem Fehler bleiben die Regex-Daten unverändert.
    ai_filled = []
    pre_warnings = check_fields(data)
    ai_key, ai_model = _ai_config()
    if pre_warnings and ai_key:
        try:
            cleaned = _clean_text(extract_pdf_text(io.BytesIO(raw)))
            data, ai_filled = _ai_fill_trip_fields(data, pre_warnings, cleaned, ai_key, ai_model)
        except Exception as e:
            log.warning("PDF-Fallback (KI) fehlgeschlagen: %s", e)
        if ai_filled:
            log.info("Reise-Import: KI-Fallback ergänzte %s", ", ".join(ai_filled))

    booking = (data.get('buchungsnummer') or '').strip()
    ts = int(time.time())
    pdf_name = f"{booking or ('trip_' + str(ts))}.pdf"
    target = _trip_pdf_path(pdf_name)
    if target is None:
        return jsonify({'error': 'bad_name'}), 400

    Path(TRIPS_DIR).mkdir(parents=True, exist_ok=True)
    try:
        target.write_bytes(raw)
    except OSError as exc:
        log.warning("PDF speichern fehlgeschlagen: %s", exc)
        return jsonify({'error': 'store_failed'}), 500

    orig = Path(file.filename).name
    row = {
        'booking_code': booking or None,
        'booking_date': data.get('buchungsdatum'),
        'title': _trip_title(data),
        'destination': data.get('reiseziel'),
        'hotel': (data.get('hotel') or {}).get('name'),
        'hotel_code': (data.get('hotel') or {}).get('code'),
        'start_date': _iso_date((data.get('reisezeitraum') or {}).get('von')),
        'end_date': _iso_date((data.get('reisezeitraum') or {}).get('bis')),
        'nights': data.get('naechte'),
        'travellers': len(data.get('reisende') or []) or None,
        'total_price': _parse_eur_num(data.get('gesamtpreis')),
        'package_price': _parse_eur_num(data.get('paketpreis')),
        'net_per_night': _parse_eur_num(data.get('preis_pro_person_nacht_paket')),
        'meal': data.get('verpflegung'),
        'data': json.dumps(data, ensure_ascii=False),
        'pdf_name': pdf_name,
        'orig_name': orig,
        'created': ts,
    }
    # Feste Whitelist der Spalten (konstant im Code, NICHT aus row.keys() abgeleitet),
    # damit die SQL-Struktur nicht von request-nahen Daten abhängt. Reihenfolge fix.
    cols = _TRIP_COLUMNS
    assert set(row) == set(cols), "row weicht von der erlaubten Spaltenliste ab"
    values = [row[c] for c in cols]
    with db() as con:
        existing = None
        if booking:
            existing = con.execute(
                'SELECT id, pdf_name FROM trips WHERE booking_code=?', (booking,)).fetchone()
        if existing:
            # ggf. alte PDF mit abweichendem Namen entfernen
            old = existing['pdf_name']
            if old and old != pdf_name:
                op = _trip_pdf_path(old)
                if op and op.exists():
                    try:
                        op.unlink()
                    except OSError:
                        pass
            setclause = ', '.join(f'{c}=?' for c in cols)
            con.execute(f'UPDATE trips SET {setclause} WHERE id=?',
                        values + [existing['id']])
            tid = existing['id']
        else:
            placeholders = ', '.join('?' for _ in cols)
            cur = con.execute(
                f'INSERT INTO trips ({", ".join(cols)}) VALUES ({placeholders})',
                values)
            tid = cur.lastrowid
    warnings = check_fields(data)
    if warnings:
        log.warning("Reise-Import #%s: nicht erkannte Felder: %s",
                    booking or tid, ", ".join(warnings))
    log.info("Reise importiert: %s (#%s)", row['title'], booking or tid)
    return jsonify({'ok': True, 'id': tid, 'data': data, 'warnings': warnings,
                    'ai_filled': ai_filled})


@app.route('/api/trips/<int:tid>/pdf', methods=['GET'])
def api_trip_pdf(tid):
    """Gespeicherte Reise-PDF ausliefern (öffnen/herunterladen)."""
    if (err := _require_api()):
        return err
    with db() as con:
        row = con.execute('SELECT pdf_name, orig_name FROM trips WHERE id=?',
                          (tid,)).fetchone()
    if not row or not row['pdf_name']:
        return jsonify({'error': 'not_found'}), 404
    p = _trip_pdf_path(row['pdf_name'])
    if p is None or not p.exists():
        return jsonify({'error': 'not_found'}), 404
    return send_file(str(p), mimetype='application/pdf',
                     download_name=row['orig_name'] or 'reise.pdf')


@app.route('/api/trips/<int:tid>/attachments', methods=['POST'])
def api_trip_attachment_upload(tid):
    """Weiteres PDF zu einer Reise hochladen (z. B. Reiseplan) — reine Ablage,
    kein Parsing/Auswertung."""
    if (err := _require_api()):
        return err
    with db() as con:
        if not con.execute('SELECT id FROM trips WHERE id=?', (tid,)).fetchone():
            return jsonify({'error': 'not_found'}), 404
    file = request.files.get('pdf')
    if file is None or not file.filename:
        return jsonify({'error': 'no_file'}), 400
    if Path(file.filename).suffix.lower() != '.pdf':
        return jsonify({'error': 'not_pdf'}), 400
    raw = file.read()
    if not raw:
        return jsonify({'error': 'empty'}), 400
    if len(raw) > MAX_PDF_BYTES:
        return jsonify({'error': 'too_large'}), 413

    filename = f"att_{tid}_{secrets.token_hex(8)}.pdf"
    target = _trip_pdf_path(filename)
    if target is None:
        return jsonify({'error': 'bad_name'}), 400
    Path(TRIPS_DIR).mkdir(parents=True, exist_ok=True)
    try:
        target.write_bytes(raw)
    except OSError as exc:
        log.warning("Anhang speichern fehlgeschlagen: %s", exc)
        return jsonify({'error': 'store_failed'}), 500

    orig = Path(file.filename).name
    ts = int(time.time())
    with db() as con:
        cur = con.execute(
            'INSERT INTO trip_attachments (trip_id, filename, orig_name, created) '
            'VALUES (?,?,?,?)', (tid, filename, orig, ts))
        aid = cur.lastrowid
    log.info("Anhang zu Reise #%d gespeichert: %s", tid, orig)
    return jsonify({'ok': True, 'id': aid, 'orig_name': orig, 'created': ts})


@app.route('/api/trips/<int:tid>/attachments/<int:aid>', methods=['GET'])
def api_trip_attachment_get(tid, aid):
    """Gespeichertes Zusatz-PDF ausliefern (öffnen/herunterladen)."""
    if (err := _require_api()):
        return err
    with db() as con:
        row = con.execute(
            'SELECT filename, orig_name FROM trip_attachments WHERE id=? AND trip_id=?',
            (aid, tid)).fetchone()
    if not row:
        return jsonify({'error': 'not_found'}), 404
    p = _trip_pdf_path(row['filename'])
    if p is None or not p.exists():
        return jsonify({'error': 'not_found'}), 404
    return send_file(str(p), mimetype='application/pdf',
                     download_name=row['orig_name'] or 'anhang.pdf')


@app.route('/api/trips/<int:tid>/attachments/<int:aid>', methods=['DELETE'])
def api_trip_attachment_delete(tid, aid):
    """Zusatz-PDF wieder entfernen."""
    if (err := _require_api()):
        return err
    with db() as con:
        row = con.execute(
            'SELECT filename FROM trip_attachments WHERE id=? AND trip_id=?',
            (aid, tid)).fetchone()
        if not row:
            return jsonify({'error': 'not_found'}), 404
        con.execute('DELETE FROM trip_attachments WHERE id=?', (aid,))
    p = _trip_pdf_path(row['filename'])
    if p and p.exists():
        try:
            p.unlink()
        except OSError as exc:
            log.warning("Anhang löschen fehlgeschlagen: %s", exc)
    return jsonify({'ok': True})


# Obergrenze für Packliste-Items je Reise — die Vorlage hat 66 Einträge und füllt eine
# gedruckte A4-Seite zweispaltig bereits gut; 70 lässt ein paar eigene Ergänzungen zu,
# ohne dass das Druckblatt umbricht.
MAX_PACKING_ITEMS = 70


def _packing_item_owned(con, tid, iid):
    return con.execute(
        'SELECT id FROM trip_packing_items WHERE id=? AND trip_id=?', (iid, tid)).fetchone()


@app.route('/api/trips/<int:tid>/packing', methods=['POST'])
def api_trip_packing_add(tid):
    """Eigenes Item zur Packliste hinzufügen."""
    if (err := _require_api()):
        return err
    body = request.get_json(silent=True) or {}
    category = (body.get('category') or '').strip()
    label = (body.get('label') or '').strip()
    if not category or not label or len(category) > 60 or len(label) > 200:
        return jsonify({'error': 'invalid'}), 400
    with db() as con:
        if not con.execute('SELECT id FROM trips WHERE id=?', (tid,)).fetchone():
            return jsonify({'error': 'not_found'}), 404
        count = con.execute(
            'SELECT COUNT(*) c FROM trip_packing_items WHERE trip_id=?', (tid,)).fetchone()['c']
        if count >= MAX_PACKING_ITEMS:
            return jsonify({'error': 'limit_reached'}), 409
        cur = con.execute(
            'INSERT INTO trip_packing_items (trip_id, category, label, checked, created) '
            'VALUES (?,?,?,0,?)', (tid, category, label, int(time.time())))
    return jsonify({'ok': True, 'id': cur.lastrowid})


@app.route('/api/trips/<int:tid>/packing/<int:iid>', methods=['PATCH'])
def api_trip_packing_update(tid, iid):
    """Item abhaken/umbenennen/umkategorisieren — nur mitgeschickte Felder ändern."""
    if (err := _require_api()):
        return err
    body = request.get_json(silent=True) or {}
    fields, params = [], []
    if 'checked' in body:
        fields.append('checked=?')
        params.append(1 if body.get('checked') else 0)
    if 'label' in body:
        label = (body.get('label') or '').strip()
        if not label or len(label) > 200:
            return jsonify({'error': 'invalid'}), 400
        fields.append('label=?')
        params.append(label)
    if 'category' in body:
        category = (body.get('category') or '').strip()
        if not category or len(category) > 60:
            return jsonify({'error': 'invalid'}), 400
        fields.append('category=?')
        params.append(category)
    if not fields:
        return jsonify({'error': 'invalid'}), 400
    with db() as con:
        if not _packing_item_owned(con, tid, iid):
            return jsonify({'error': 'not_found'}), 404
        con.execute(f'UPDATE trip_packing_items SET {", ".join(fields)} WHERE id=?',
                    params + [iid])
    return jsonify({'ok': True})


@app.route('/api/trips/<int:tid>/packing/<int:iid>', methods=['DELETE'])
def api_trip_packing_delete(tid, iid):
    """Packliste-Item entfernen."""
    if (err := _require_api()):
        return err
    with db() as con:
        if not _packing_item_owned(con, tid, iid):
            return jsonify({'error': 'not_found'}), 404
        con.execute('DELETE FROM trip_packing_items WHERE id=?', (iid,))
    return jsonify({'ok': True})


@app.route('/api/trips/<int:tid>/packing/reset', methods=['POST'])
def api_trip_packing_reset(tid):
    """Packliste auf die Vorlage zurücksetzen — eigene Einträge/Haken gehen verloren."""
    if (err := _require_api()):
        return err
    with db() as con:
        if not con.execute('SELECT id FROM trips WHERE id=?', (tid,)).fetchone():
            return jsonify({'error': 'not_found'}), 404
        con.execute('DELETE FROM trip_packing_items WHERE trip_id=?', (tid,))
        con.executemany(
            'INSERT INTO trip_packing_items '
            '(trip_id, category, label, checked, created) VALUES (?,?,?,?,?)',
            [(tid,) + r for r in default_packing_rows(int(time.time()))])
        con.execute('UPDATE trips SET packing_seeded=1 WHERE id=?', (tid,))
    return jsonify({'ok': True})


@app.route('/api/trips/<int:tid>', methods=['DELETE'])
def api_trip_delete(tid):
    """Reise löschen — inkl. der dauerhaft gespeicherten PDF und aller Anhänge."""
    if (err := _require_api()):
        return err
    with db() as con:
        row = con.execute('SELECT pdf_name FROM trips WHERE id=?', (tid,)).fetchone()
        if not row:
            return jsonify({'error': 'not_found'}), 404
        atts = con.execute(
            'SELECT filename FROM trip_attachments WHERE trip_id=?', (tid,)).fetchall()
        con.execute('DELETE FROM trip_attachments WHERE trip_id=?', (tid,))
        con.execute('DELETE FROM trip_packing_items WHERE trip_id=?', (tid,))
        con.execute('DELETE FROM trips WHERE id=?', (tid,))
    for a in atts:
        p = _trip_pdf_path(a['filename'])
        if p and p.exists():
            try:
                p.unlink()
            except OSError as exc:
                log.warning("Anhang löschen fehlgeschlagen: %s", exc)
    if row['pdf_name']:
        p = _trip_pdf_path(row['pdf_name'])
        if p and p.exists():
            try:
                p.unlink()
            except OSError as exc:
                log.warning("PDF löschen fehlgeschlagen: %s", exc)
    return jsonify({'ok': True})


@app.route('/api/airports', methods=['GET'])
def api_airports():
    """Abflughäfen (TUI-Liste, einmalig gecacht)."""
    if (err := _require_api()):
        return err
    global _airports_cache
    if not _airports_cache:
        _airports_cache = fetch_airports()
    return jsonify({'airports': _airports_cache})


@app.route('/api/contacts', methods=['GET'])
def api_contacts():
    """Nextcloud-Adressbuch (CardDAV), einmalig gecacht — ?refresh=1 erzwingt Neuladen."""
    if (err := _require_api()):
        return err
    if not nc_configured():
        return jsonify({'configured': False, 'contacts': []})
    global _contacts_cache
    if not _contacts_cache or request.args.get('refresh') == '1':
        cfg = load_config()
        _contacts_cache = fetch_contacts(
            cfg.get('nc_addressbook_url', ''), cfg.get('nc_user', ''),
            cfg.get('nc_app_password', ''), verbose=_verbose())
    return jsonify({'configured': True, 'contacts': _contacts_cache})


@app.route('/api/airlines', methods=['GET'])
def api_airlines():
    """Fluggesellschaften für den optionalen Such-Filter (kuratierte Liste)."""
    if (err := _require_api()):
        return err
    return jsonify({'airlines': fetch_airlines()})


@app.route('/api/calendar/<int:offer_id>', methods=['POST'])
def api_calendar_start(offer_id: int):
    if (err := _require_api()):
        return err
    with _calendar_lock:
        if _calendar_state.get(offer_id, {}).get('status') == 'running':
            return jsonify({'started': True, 'already': True})
    with db() as con:
        exists = con.execute('SELECT 1 FROM offers WHERE id=?', (offer_id,)).fetchone()
    if not exists:
        return jsonify({'error': 'not_found'}), 404
    with _calendar_lock:
        _calendar_state[offer_id] = {'status': 'running'}
    log.info("Preiskalender-Abruf gestartet: Angebot #%d", offer_id)
    _spawn(_run_calendar, offer_id)
    return jsonify({'started': True})


@app.route('/api/calendar/<int:offer_id>', methods=['GET'])
def api_calendar_get(offer_id: int):
    if (err := _require_api()):
        return err
    return jsonify(_calendar_payload(offer_id))


@app.route('/api/rooms/<int:offer_id>', methods=['GET'])
def api_rooms_get(offer_id: int):
    """Wählbare Zimmerkategorien (mit Preis p. P.) für ein Angebot — live abgefragt."""
    if (err := _require_api()):
        return err
    with db() as con:
        o = con.execute('SELECT url FROM offers WHERE id=?', (offer_id,)).fetchone()
    if not o:
        return jsonify({'error': 'not_found'}), 404
    with _scrape_lock:
        res = fetch_rooms(o['url'], verbose=_verbose())
    if res is None:
        return jsonify({'ok': False, 'note': 'Zimmer konnten nicht geladen werden'}), 502
    res['current'] = room_code_from_url(o['url'])
    return jsonify(res)


@app.route('/api/rooms/<int:offer_id>', methods=['POST'])
def api_rooms_set(offer_id: int):
    """Fixiert ein Zimmer (`code`) für das Angebot — danach wird der Preis dieses Zimmers
    verfolgt. Leerer Code = wieder automatisch das günstigste Zimmer."""
    if (err := _require_api()):
        return err
    data = request.get_json(silent=True) or {}
    code = (data.get('code') or '').strip()
    label = (data.get('label') or '').strip()
    with db() as con:
        o = con.execute('SELECT url FROM offers WHERE id=?', (offer_id,)).fetchone()
        if not o:
            return jsonify({'error': 'not_found'}), 404
        new_url = with_room_code(o['url'], code)
        try:
            con.execute('UPDATE offers SET url=? WHERE id=?', (new_url, offer_id))
        except sqlite3.IntegrityError:
            return jsonify({'error': 'duplicate',
                            'note': 'Dieses Zimmer wird bereits als eigenes Angebot verfolgt'}), 409
    log.info("Angebot #%d: Zimmer %s gewählt", offer_id, code or '(günstigstes)')
    if code:
        _log_event(offer_id, 'room',
                   f"Zimmer: {label} ({code})" if label else f"Zimmer: {code}")
    else:
        _log_event(offer_id, 'room', "Zimmer: günstigstes (automatisch)")
    _spawn(check_offer, offer_id)
    return jsonify({'ok': True, 'started': True})


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


def main() -> None:
    init_db()
    load_sessions()
    _spawn(push_ha_sensors)  # vorhandene Preise sofort als Sensoren melden
    _spawn(_notify_startup)  # kurze Telegram-Statusmeldung (falls konfiguriert)
    _spawn(_run_healthcheck)  # API-Erreichbarkeit beim Start prüfen
    _spawn(_ensure_dest_index)  # Reiseziel-Index (globale Suche) laden/aufbauen
    threading.Thread(target=_poll_worker, daemon=True).start()
    threading.Thread(target=_aktionscodes_sensor_worker, daemon=True).start()
    port = int(os.environ.get('TUIWATCH_PORT', '17794'))
    log.info("TUIWatch startet auf Port %d", port)
    app.run(host='0.0.0.0', port=port, threaded=True)


if __name__ == '__main__':
    main()
