#!/usr/bin/env python3
"""TUIWatch — Reisepreis-Tracker als Home-Assistant-Add-on.

Verfolgt den Preis konkreter TUI-Angebots-URLs über die Zeit: rendert die Seite
periodisch mit Headless-Chromium (siehe scraper.py), speichert jeden Messpunkt in
SQLite und zeigt Verlauf + Hoch/Runter-Anzeige in einer Weboberfläche.
"""
import json
import logging
import os
import secrets
import sqlite3
import threading
import time
from collections import defaultdict, deque
from datetime import datetime
from urllib.parse import urlparse

from flask import (Flask, jsonify, make_response, redirect, render_template,
                   request, url_for)
from werkzeug.middleware.proxy_fix import ProxyFix

from scraper import fetch_price, hotel_from_url

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
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            url     TEXT UNIQUE NOT NULL,
            label   TEXT DEFAULT '',
            hotel   TEXT DEFAULT '',
            details TEXT DEFAULT '',
            created INTEGER NOT NULL
        )''')
        # Migration: hotel-Spalte für bestehende DBs nachrüsten
        cols = {r['name'] for r in con.execute('PRAGMA table_info(offers)').fetchall()}
        if 'hotel' not in cols:
            con.execute("ALTER TABLE offers ADD COLUMN hotel TEXT DEFAULT ''")
        # Backfill: Hotelname aus der URL für Einträge ohne Namen
        for r in con.execute("SELECT id, url FROM offers WHERE hotel='' OR hotel IS NULL").fetchall():
            name = hotel_from_url(r['url'])
            if name:
                con.execute('UPDATE offers SET hotel=? WHERE id=?', (name, r['id']))
        con.execute('''CREATE TABLE IF NOT EXISTS price_history (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            offer_id  INTEGER NOT NULL,
            ts        INTEGER NOT NULL,
            price     REAL,
            old_price REAL,
            discount  INTEGER,
            ok        INTEGER NOT NULL DEFAULT 0,
            note      TEXT DEFAULT '',
            FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE CASCADE
        )''')
        con.execute('CREATE INDEX IF NOT EXISTS idx_hist_offer ON price_history(offer_id, ts)')
    log.info("Datenbank bereit: %s", DB_PATH)


def _last_two_prices(con, offer_id: int) -> list:
    rows = con.execute(
        'SELECT price FROM price_history WHERE offer_id=? AND ok=1 AND price IS NOT NULL '
        'ORDER BY ts DESC LIMIT 2', (offer_id,)).fetchall()
    return [r['price'] for r in rows]


# ── Scraping-Worker ────────────────────────────────────────────────────────────

def check_offer(offer_id: int) -> None:
    """Prüft ein Angebot (Playwright) und speichert einen Messpunkt."""
    with _checking_lock:
        if offer_id in _checking:
            return
        _checking.add(offer_id)
    try:
        with db() as con:
            row = con.execute('SELECT url FROM offers WHERE id=?', (offer_id,)).fetchone()
        if not row:
            return
        url = row['url']
        log.info("Prüfe Angebot #%d …", offer_id)
        with _scrape_lock:
            res = fetch_price(url, verbose=_verbose())
        ts = int(time.time())
        with db() as con:
            con.execute(
                'INSERT INTO price_history (offer_id, ts, price, old_price, discount, ok, note) '
                'VALUES (?,?,?,?,?,?,?)',
                (offer_id, ts, res.get('price'), res.get('old_price'),
                 res.get('discount'), 1 if res.get('ok') else 0, res.get('note', '')))
            # Details immer aktualisieren, Hotelname falls erkannt
            if res.get('details'):
                con.execute('UPDATE offers SET details=? WHERE id=?', (res['details'], offer_id))
            if res.get('hotel'):
                con.execute('UPDATE offers SET hotel=? WHERE id=?', (res['hotel'], offer_id))
        if res.get('ok'):
            log.info("Angebot #%d: %.0f € (%s)", offer_id, res['price'], res.get('details', '')[:60])
        else:
            log.warning("Angebot #%d fehlgeschlagen: %s", offer_id, res.get('note'))
    except Exception as e:
        log.error("check_offer(#%d) Fehler: %s", offer_id, e)
    finally:
        with _checking_lock:
            _checking.discard(offer_id)


def check_all(reason: str = '') -> None:
    with db() as con:
        ids = [r['id'] for r in con.execute('SELECT id FROM offers ORDER BY id').fetchall()]
    if ids:
        log.info("Prüfe %d Angebot(e)%s", len(ids), f' ({reason})' if reason else '')
    for oid in ids:
        check_offer(oid)


def _poll_worker() -> None:
    log.info("Preis-Poller gestartet")
    # kurzer Vorlauf, damit der Webserver zuerst hochkommt
    time.sleep(5)
    while True:
        try:
            check_all('Intervall')
        except Exception as e:
            log.error("Poll-Fehler: %s", e)
        interval = max(MIN_POLL_INTERVAL,
                       int(load_config().get('poll_interval', POLL_INTERVAL_DEFAULT)))
        time.sleep(interval)


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
            checking = o['id'] in _checking
            out.append({
                'id': o['id'], 'url': o['url'], 'label': o['label'],
                'hotel': o['hotel'], 'details': o['details'],
                'price': last['price'] if last else None,
                'old_price': last['old_price'] if last else None,
                'discount': last['discount'] if last else None,
                'ok': bool(last['ok']) if last else None,
                'note': last['note'] if last else '',
                'last_ts': last['ts'] if last else None,
                'delta': delta,
                'checking': checking,
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
        con.execute('DELETE FROM offers WHERE id=?', (offer_id,))
    log.info("Angebot #%d gelöscht", offer_id)
    return jsonify({'deleted': offer_id})


@app.route('/api/offers/<int:offer_id>', methods=['PATCH'])
def api_rename_offer(offer_id: int):
    if (err := _require_api()):
        return err
    data = request.get_json(silent=True) or {}
    label = (data.get('label') or '').strip()
    with db() as con:
        con.execute('UPDATE offers SET label=? WHERE id=?', (label, offer_id))
    return jsonify({'id': offer_id, 'label': label})


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


@app.route('/api/check-now', methods=['POST'])
def api_check_now():
    if (err := _require_api()):
        return err
    _spawn(check_all, 'manuell')
    return jsonify({'started': True})


@app.route('/api/console')
def api_console():
    if (err := _require_api()):
        return err
    return jsonify({'lines': list(_log_buffer)})


# ── Start ──────────────────────────────────────────────────────────────────────

def main() -> None:
    init_db()
    load_sessions()
    threading.Thread(target=_poll_worker, daemon=True).start()
    port = int(os.environ.get('TUIWATCH_PORT', '17794'))
    log.info("TUIWatch startet auf Port %d", port)
    app.run(host='0.0.0.0', port=port, threaded=True)


if __name__ == '__main__':
    main()
