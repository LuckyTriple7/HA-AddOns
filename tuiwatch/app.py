#!/usr/bin/env python3
"""TUIWatch — Reisepreis-Tracker als Home-Assistant-Add-on.

Verfolgt den Preis konkreter TUI-Angebots-URLs über die Zeit: rendert die Seite
periodisch mit Headless-Chromium (siehe scraper.py), speichert jeden Messpunkt in
SQLite und zeigt Verlauf + Hoch/Runter-Anzeige in einer Weboberfläche.
"""
import csv
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
from collections import defaultdict, deque
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import urlparse

import requests as http
from flask import (Flask, jsonify, make_response, redirect, render_template,
                   request, send_file, url_for)
from werkzeug.middleware.proxy_fix import ProxyFix

from scraper import (_giata_from_url, _valid_img_url, api_healthcheck,
                     duration_from_url, fetch_airlines, fetch_airports,
                     fetch_calendar, fetch_destinations, fetch_hotel_image,
                     fetch_price, fetch_rooms, fetch_search, fetch_search_params,
                     hotel_from_url, is_single_room, region_giata_from_breadcrumb,
                     room_code_from_url, travellers_from_url, with_duration,
                     with_room_code, with_travellers, without_room_code)

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

# ── Pfade / Flask ──────────────────────────────────────────────────────────────
_BASE = os.environ.get('TUIWATCH_BASE', '/app')
_DATA = os.environ.get('TUIWATCH_DATA', '/data')
CONFIG_PATH = _DATA + '/options.json'
SESSIONS_PATH = _DATA + '/sessions.json'
DB_PATH = _DATA + '/tuiwatch.db'

POLL_INTERVAL_DEFAULT = 21600  # 6h — Reisepreise ändern sich langsam
MIN_POLL_INTERVAL = 600        # nie öfter als alle 10 min (Bot-Schutz/Fairness)

app = Flask(__name__, template_folder=_BASE + '/templates',
            static_folder=_BASE + '/static')


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
_cheaper_notified: dict[int, str] = {}  # Dedup für Günstigerer-Termin-Alarm
_fail_notified: set[int] = set()        # offer_ids mit aktivem Ausverkauft-/Fehler-Alarm
ERROR_ALARM_STREAK = 3                   # ab so vielen Fehlversuchen in Folge melden
_health_state: dict = {}                 # letzter API-Selbsttest {ok, ts, checks, running}
_health_lock = threading.Lock()
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
        # Kleiner Schlüssel-Wert-Speicher (z. B. letzter Digest-Versand, ISO-Woche).
        con.execute('''CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        )''')
        # Migration: fehlende Spalten in bestehenden DBs nachrüsten
        ocols = {r['name'] for r in con.execute('PRAGMA table_info(offers)').fetchall()}
        for col in ('hotel', 'details', 'room', 'dep_airport', 'flight_out',
                    'flight_ret', 'cancellation', 'location', 'city', 'region',
                    'country', 'pdf_url', 'return_date', 'image_url',
                    'booking_code', 'room_booking_code'):
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
        rating = ''
        if o.get('rating') is not None:
            rating = (f'HolidayCheck {str(o["rating"]).replace(".", ",")}/6'
                      + (f' · {o["recommendation"]}%' if o.get('recommendation') is not None else ''))
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
            + (f'<div style="font-size:12px;color:#777;margin-top:3px">{esc(rating)}</div>' if rating else '')
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
    _notify_telegram(f"✈️ <b>TUIWatch gestartet</b>\n{n} {word} geladen")


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

    def nm(o):
        return o.get('label') or o.get('hotel') or f"Angebot #{o['id']}"

    # ── Text (Telegram) ──
    tl = [f"📊 <b>TUIWatch — Wochenüberblick</b> ({datetime.now():%d.%m.%Y})",
          f"{len(offers)} aktive Reise(n) beobachtet."]
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

    html = (
        '<div style="font-family:system-ui,Arial,sans-serif;max-width:640px;margin:0 auto">'
        f'<h2 style="color:#10243e">📊 TUIWatch — Wochenüberblick</h2>'
        f'<p style="color:#555;font-size:13px">{datetime.now():%d.%m.%Y} · {len(offers)} aktive Reise(n) beobachtet.</p>'
        + section('🎯 Unter Wunschpreis', under,
                  lambda o: f'{link(o)}: <b>{_eur(o["price"])}</b> <span style="color:#777">(Ziel {_eur(o["target_price"])})</span>')
        + section('📉 Neuer Tiefstwert', lows,
                  lambda o: f'{link(o)}: <b>{_eur(o["price"])}</b>')
        + section('▼ Größte Rückgänge (7 Tage)', drops[:8],
                  lambda o: f'{link(o)}: {_eur(o["price"])} <span style="color:#1a7f37;font-weight:600">({_eur(o["_wk"])})</span>')
        + section('▲ Gestiegen (7 Tage)', rises[:5],
                  lambda o: f'{link(o)}: {_eur(o["price"])} <span style="color:#cf222e">(+{_eur(abs(o["_wk"]))})</span>')
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
        poll_interval=int(cfg.get('poll_interval', POLL_INTERVAL_DEFAULT))))


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
    return jsonify({'history': [dict(r) for r in rows]})


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


@app.route('/api/backup', methods=['GET'])
def api_backup():
    if (err := _require_api()):
        return err
    with db() as con:
        rows = con.execute('SELECT url, label, target_price, booked_price, image_url, '
                           'paused, archived FROM offers ORDER BY id').fetchall()
    data = {'tuiwatch_backup': 1, 'created': datetime.now().isoformat(),
            'offers': [{'url': r['url'], 'label': r['label'],
                        'target_price': r['target_price'],
                        'booked_price': r['booked_price'],
                        'image_url': r['image_url'] or '',
                        'paused': bool(r['paused']),
                        'archived': bool(r['archived'])}
                       for r in rows]}
    resp = make_response(json.dumps(data, ensure_ascii=False, indent=2))
    resp.headers['Content-Type'] = 'application/json; charset=utf-8'
    resp.headers['Content-Disposition'] = (
        f'attachment; filename="tuiwatch-backup-{datetime.now().strftime("%Y%m%d")}.json"')
    return resp


@app.route('/api/restore', methods=['POST'])
def api_restore():
    if (err := _require_api()):
        return err
    data = request.get_json(silent=True) or {}
    items = data.get('offers') if isinstance(data, dict) else data
    if not isinstance(items, list):
        return jsonify({'error': 'invalid'}), 400
    added, skipped, new_ids = 0, 0, []
    with db() as con:
        for it in items:
            url = (it.get('url') or '').strip() if isinstance(it, dict) else ''
            if not _valid_tui_url(url):
                skipped += 1
                continue
            def _price(v):
                try:
                    return float(v) if v not in (None, '', 0) else None
                except (TypeError, ValueError):
                    return None
            tp = _price(it.get('target_price'))
            bp = _price(it.get('booked_price'))
            img = (it.get('image_url') or '').strip()
            if not _valid_img_url(img):
                img = ''
            try:
                cur = con.execute(
                    'INSERT INTO offers (url, label, hotel, details, target_price, '
                    'booked_price, image_url, paused, archived, created) '
                    'VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (url, (it.get('label') or '').strip(), hotel_from_url(url), '',
                     tp, bp, img, 1 if it.get('paused') else 0,
                     1 if it.get('archived') else 0, int(time.time())))
                if not it.get('archived'):
                    new_ids.append(cur.lastrowid)  # archivierte nicht sofort prüfen
                added += 1
            except sqlite3.IntegrityError:
                skipped += 1  # URL schon vorhanden
    for oid in new_ids:
        _spawn(check_offer, oid)
    log.info("Wiederherstellung: %d hinzugefügt, %d übersprungen", added, skipped)
    return jsonify({'added': added, 'skipped': skipped})


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
                           airlines=airlines, direct=direct, verbose=_verbose())
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
                                  airlines=airlines, direct=direct, verbose=_verbose())
    else:
        url = (data.get('url') or '').strip()
        if not _valid_tui_url(url):
            return jsonify({'error': 'invalid_url'}), 400
        log.info("Suche: %s (TUI=%s, Verpflegung=%s)", url, operator_tui,
                 ','.join(boards) or '-')
        res = fetch_search(url, operator_tui=operator_tui, boards=boards,
                           airlines=airlines, direct=direct, verbose=_verbose())
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


_dest_cache: dict = {}     # parent → {parentName, items}
_airports_cache: list = []  # einmalig geladen


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


@app.route('/api/airports', methods=['GET'])
def api_airports():
    """Abflughäfen (TUI-Liste, einmalig gecacht)."""
    if (err := _require_api()):
        return err
    global _airports_cache
    if not _airports_cache:
        _airports_cache = fetch_airports()
    return jsonify({'airports': _airports_cache})


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

def main() -> None:
    init_db()
    load_sessions()
    _spawn(push_ha_sensors)  # vorhandene Preise sofort als Sensoren melden
    _spawn(_notify_startup)  # kurze Telegram-Statusmeldung (falls konfiguriert)
    _spawn(_run_healthcheck)  # API-Erreichbarkeit beim Start prüfen
    threading.Thread(target=_poll_worker, daemon=True).start()
    port = int(os.environ.get('TUIWATCH_PORT', '17794'))
    log.info("TUIWatch startet auf Port %d", port)
    app.run(host='0.0.0.0', port=port, threaded=True)


if __name__ == '__main__':
    main()
