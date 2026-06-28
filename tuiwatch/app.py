#!/usr/bin/env python3
"""TUIWatch — Reisepreis-Tracker als Home-Assistant-Add-on.

Verfolgt den Preis konkreter TUI-Angebots-URLs über die Zeit: rendert die Seite
periodisch mit Headless-Chromium (siehe scraper.py), speichert jeden Messpunkt in
SQLite und zeigt Verlauf + Hoch/Runter-Anzeige in einer Weboberfläche.
"""
import json
import logging
import os
import re
import secrets
import sqlite3
import threading
import time
from collections import defaultdict, deque
from datetime import datetime
from urllib.parse import urlparse

import requests as http
from flask import (Flask, jsonify, make_response, redirect, render_template,
                   request, url_for)
from werkzeug.middleware.proxy_fix import ProxyFix

from scraper import (fetch_calendar, fetch_price, hotel_from_url, is_single_room,
                     travellers_from_url, with_travellers, without_room_code)

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
        # Migration: fehlende Spalten in bestehenden DBs nachrüsten
        ocols = {r['name'] for r in con.execute('PRAGMA table_info(offers)').fetchall()}
        for col in ('hotel', 'details', 'room', 'dep_airport', 'flight_out',
                    'flight_ret', 'cancellation', 'location', 'city', 'region',
                    'country', 'pdf_url'):
            if col not in ocols:
                con.execute(f"ALTER TABLE offers ADD COLUMN {col} TEXT DEFAULT ''")
        for col in ('target_price', 'stars', 'rating'):
            if col not in ocols:
                con.execute(f"ALTER TABLE offers ADD COLUMN {col} REAL")
        for col in ('rating_count', 'recommendation'):
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
        # Verwaiste tuiwatch-Sensoren entfernen (z. B. nach Löschen/Umbenennen)
        valid = set(mapping.values())
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
        log.warning("HA-Benachrichtigung fehlgeschlagen: %s", e)


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
        log.warning("Telegram-Benachrichtigung fehlgeschlagen: %s", e)


def _eur(v) -> str:
    try:
        return f"{int(round(v)):,}".replace(',', '.') + ' €'
    except Exception:
        return '–'


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
        _notify_ha(title, msg, f"change_{offer['id']}")
        _notify_telegram(f"{'📉' if diff<0 else '📈'} <b>{name}</b>\n"
                         f"{_eur(prev_price)} → <b>{_eur(new_price)}</b> ({arrow})\n{url}")


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
        prev_price = prev_price['price'] if prev_price else None
        url = offer['url']
        log.info("Prüfe Angebot #%d …", offer_id)

        # bis zu 2 Versuche (gegen sporadische Timeouts/Bot-Drosselung)
        res = {}
        for attempt in (1, 2):
            with _scrape_lock:
                res = fetch_price(url, verbose=_verbose())
            if res.get('ok'):
                break
            if res.get('detail'):
                log.warning("Angebot #%d Versuch %d: %s", offer_id, attempt, res['detail'])
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
                        'rating_count', 'recommendation'):
                if res.get(col) is not None and res.get(col) != '':
                    con.execute(f'UPDATE offers SET {col}=? WHERE id=?', (res[col], offer_id))

        if res.get('ok'):
            log.info("Angebot #%d: %.0f € (%s)", offer_id, res['price'], res.get('details', '')[:60])
            _maybe_notify(offer, prev_price, res.get('price'), offer.get('target_price'))
        else:
            # nach außen nur generische Note (bereits in res['note']); Detail steht im Log
            log.warning("Angebot #%d fehlgeschlagen: %s", offer_id, res.get('note'))
    except Exception as e:
        log.error("check_offer(#%d) Fehler: %s", offer_id, e)
    finally:
        with _checking_lock:
            _checking.discard(offer_id)
    push_ha_sensors()


def check_all(reason: str = '') -> None:
    with db() as con:
        ids = [r['id'] for r in con.execute('SELECT id FROM offers ORDER BY id').fetchall()]
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
            with db() as con:
                offers = [r['id'] for r in
                          con.execute('SELECT id FROM offers ORDER BY id').fetchall()]
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

@app.route('/api/offers', methods=['GET'])
def api_offers():
    if (err := _require_api()):
        return err
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
                'pdf_url': o['pdf_url'],
                'cancellation': o['cancellation'], 'stars': o['stars'],
                'rating': o['rating'], 'rating_count': o['rating_count'],
                'recommendation': o['recommendation'],
                'target_price': o['target_price'],
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
                'checking': checking,
                'comparable': not is_single_room(f"{o['room']} {o['details']}"),
            })
    return jsonify({'offers': out})


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
    try:
        with db() as con:
            cur = con.execute(
                'INSERT INTO offers (url, label, hotel, details, created) VALUES (?,?,?,?,?)',
                (url, label, hotel_from_url(url), '', int(time.time())))
            offer_id = cur.lastrowid
    except sqlite3.IntegrityError:
        return jsonify({'error': 'duplicate'}), 409
    log.info("Neues Angebot #%d hinzugefügt", offer_id)
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
        con.execute('DELETE FROM offers WHERE id=?', (offer_id,))
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
            con.execute('UPDATE offers SET label=? WHERE id=?',
                        ((data.get('label') or '').strip(), offer_id))
        if 'target_price' in data:
            tp = data.get('target_price')
            try:
                tp = float(tp) if tp not in (None, '', 0) else None
            except (TypeError, ValueError):
                tp = None
            con.execute('UPDATE offers SET target_price=? WHERE id=?', (tp, offer_id))
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


@app.route('/api/check/<int:offer_id>', methods=['POST'])
def api_check_one(offer_id: int):
    if (err := _require_api()):
        return err
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
    with _compare_lock:
        _compare_state.pop(offer_id, None)
    with _calendar_lock:
        _calendar_state.pop(offer_id, None)
    log.info("Angebot #%d zurückgesetzt (Verlauf + Caches gelöscht)", offer_id)
    _spawn(check_offer, offer_id)  # frische Erstabfrage
    return jsonify({'reset': offer_id, 'started': True})


@app.route('/api/check-now', methods=['POST'])
def api_check_now():
    if (err := _require_api()):
        return err
    _spawn(check_all, 'manuell')
    return jsonify({'started': True})


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
    _spawn(_run_compare, offer_id)
    return jsonify({'started': True})


@app.route('/api/compare/<int:offer_id>', methods=['GET'])
def api_compare_get(offer_id: int):
    if (err := _require_api()):
        return err
    return jsonify(_compare_payload(offer_id))


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
    _spawn(_run_calendar, offer_id)
    return jsonify({'started': True})


@app.route('/api/calendar/<int:offer_id>', methods=['GET'])
def api_calendar_get(offer_id: int):
    if (err := _require_api()):
        return err
    return jsonify(_calendar_payload(offer_id))


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
    threading.Thread(target=_poll_worker, daemon=True).start()
    port = int(os.environ.get('TUIWATCH_PORT', '17794'))
    log.info("TUIWatch startet auf Port %d", port)
    app.run(host='0.0.0.0', port=port, threaded=True)


if __name__ == '__main__':
    main()
