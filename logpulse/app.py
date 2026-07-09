#!/usr/bin/env python3
import json
import logging
import os
import queue
import secrets
import signal
import sqlite3
import threading
import time
import urllib.request
from collections import defaultdict, deque
from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import (Flask, render_template, request, redirect,
                    url_for, make_response, abort, jsonify)
from werkzeug.middleware.proxy_fix import ProxyFix

import journal_reader

logging.basicConfig(format='[%(levelname)s] [%(asctime)s] %(message)s',
                     level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S', force=True)
log = logging.getLogger(__name__)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# In-App Konsole (Eigendiagnose von LogPulse selbst, analog gitpulse/syswatch)
_log_buffer: deque = deque(maxlen=300)


class _BufferHandler(logging.Handler):
    _fmt = logging.Formatter('[%(levelname)s] [%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    def emit(self, record):
        try:
            _log_buffer.append({'ts': int(record.created * 1000), 'level': record.levelname,
                                 'msg': self._fmt.format(record)})
        except Exception:
            pass


_buf_h = _BufferHandler()
_buf_h.setLevel(logging.DEBUG)
_root = logging.getLogger()
_root.setLevel(logging.DEBUG)
for _h in _root.handlers:
    if _h.level == logging.NOTSET:
        _h.setLevel(logging.INFO)
_root.addHandler(_buf_h)

app = Flask(__name__, template_folder='/app/templates', static_folder='/app/static')


class _IngressMiddleware:
    """Liest HA Supervisor X-Ingress-Path und setzt WSGI SCRIPT_NAME, damit
    Flasks url_for() hinter dem Ingress-Proxy korrekte URLs erzeugt."""
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

CONFIG_PATH   = '/data/options.json'
SESSIONS_PATH = '/data/sessions.json'
INGEST_STATE_PATH = '/data/ingest_state.json'
LOCALES_PATH  = '/app/locales'
DB_PATH       = '/config/logpulse.db'
SUPERVISOR_API = 'http://supervisor'

sessions: dict[str, float] = {}

_failed_attempts: dict[str, list[float]] = defaultdict(list)
_blocked_ips: dict[str, float] = {}
RATE_LIMIT_MAX    = 5
RATE_LIMIT_WINDOW = 10 * 60
RATE_LIMIT_BLOCK  = 15 * 60

_config_cache: dict = {}
_config_mtime: float = 0.0

_db_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

_wait_lock = threading.Lock()
_wait_queues: list[queue.Queue] = []

# Ingest-Pause: gesetzt = läuft, gecleart = pausiert. journal_reader.reader_loop
# wartet dann nur noch auf dieses Event statt journald zu lesen — spart CPU
# vollständig, solange niemand die Log-Erfassung braucht.
_pause_event = threading.Event()
_pause_event.set()

_res_stats = {'cpu_percent': 0.0, 'mem_mb': 0.0}

_addon_names_cache: dict = {}
_addon_names_ts: float = 0.0
ADDON_NAMES_TTL = 60


# ── Config / Sessions ───────────────────────────────────────────────────────

def load_config() -> dict:
    global _config_cache, _config_mtime
    try:
        mtime = os.path.getmtime(CONFIG_PATH)
        if mtime != _config_mtime:
            with open(CONFIG_PATH, 'r') as f:
                _config_cache = json.load(f)
            _config_mtime = mtime
    except Exception:
        pass
    return _config_cache or {}


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


def save_ingest_paused(paused: bool) -> None:
    try:
        with open(INGEST_STATE_PATH, 'w') as f:
            json.dump({'paused': paused}, f)
    except Exception as e:
        log.warning("Ingest-Status konnte nicht gespeichert werden: %s", e)


def load_ingest_paused() -> bool:
    try:
        with open(INGEST_STATE_PATH) as f:
            return bool(json.load(f).get('paused', False))
    except FileNotFoundError:
        return False
    except Exception as e:
        log.warning("Ingest-Status konnte nicht geladen werden: %s", e)
        return False


def create_session(hours: int) -> tuple[str, float]:
    token = secrets.token_hex(32)
    expires = time.time() + hours * 3600
    sessions[token] = expires
    save_sessions()
    return token, expires


def is_valid_session(token: str | None) -> bool:
    if not token or token not in sessions:
        return False
    if time.time() > sessions[token]:
        del sessions[token]
        return False
    return True


def _is_ingress() -> bool:
    """HA Ingress authentifiziert bereits selbst — Login nur beim Direktzugriff
    über den gemappten LAN-Port nötig (gleiche Konvention wie cardboard/gitpulse)."""
    return bool(request.script_root)


def get_client_ip(req) -> str:
    cf = req.headers.get('CF-Connecting-IP', '').strip()
    if cf:
        return cf
    return req.remote_addr or 'unknown'


def is_rate_limited(ip: str) -> bool:
    now = time.time()
    if ip in _blocked_ips:
        if now < _blocked_ips[ip]:
            return True
        del _blocked_ips[ip]
    return False


def record_failed_attempt(ip: str) -> None:
    now = time.time()
    _failed_attempts[ip].append(now)
    recent = [t for t in _failed_attempts[ip] if now - t < RATE_LIMIT_WINDOW]
    _failed_attempts[ip] = recent
    if len(recent) >= RATE_LIMIT_MAX:
        _blocked_ips[ip] = now + RATE_LIMIT_BLOCK
        log.warning("IP '%s' für %d Minuten gesperrt (zu viele fehlgeschlagene Logins)",
                    ip, RATE_LIMIT_BLOCK // 60)


def clear_failed_attempts(ip: str) -> None:
    _failed_attempts.pop(ip, None)
    _blocked_ips.pop(ip, None)


def load_translations(lang: str) -> dict:
    lang = lang if lang in ('de', 'en') else 'en'
    try:
        with open(f'{LOCALES_PATH}/{lang}.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def detect_language(req) -> str:
    lang = req.cookies.get('lang')
    if lang in ('de', 'en'):
        return lang
    accept = req.headers.get('Accept-Language', '')
    if 'de' in accept[:5].lower():
        return 'de'
    return 'en'


# ── SQLite ───────────────────────────────────────────────────────────────────

def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    return _conn


def init_db() -> None:
    with _db_lock:
        conn = get_conn()
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA auto_vacuum = INCREMENTAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS log_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                source TEXT NOT NULL,
                container TEXT,
                addon_name TEXT,
                identifier TEXT,
                priority INTEGER,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                cursor TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_log_ts ON log_entries(ts)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_log_source ON log_entries(source)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_log_container ON log_entries(container)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_log_level ON log_entries(level)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_log_cursor ON log_entries(cursor)")
        conn.commit()

        # Migration: log_fts (FTS5) + Insert/Delete-Trigger stammen aus v0.1.0,
        # seit v0.3.4 wird nur noch mit LIKE gesucht. Die Trigger liefen aber
        # bei jedem Log-Insert/-Delete unbemerkt weiter mit — doppelte
        # Schreiblast pro Zeile, FTS5-Segment-Merges wurden mit wachsender
        # DB immer teurer (CPU stieg mit der Laufzeit). Alte Installationen
        # einmalig bereinigen.
        has_fts = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='log_fts'"
        ).fetchone()
        if has_fts:
            conn.execute("DROP TRIGGER IF EXISTS log_entries_ai")
            conn.execute("DROP TRIGGER IF EXISTS log_entries_ad")
            conn.execute("DROP TABLE IF EXISTS log_fts")
            conn.commit()
            conn.execute("VACUUM")
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            log.info("Migration: veraltete FTS5-Tabelle log_fts entfernt (Altlast aus v0.1.0)")


def notify_new() -> None:
    with _wait_lock:
        for q in _wait_queues:
            try:
                q.put_nowait(True)
            except queue.Full:
                pass


# ── Supervisor-Helper (Container-Name -> Friendly Addon-Name) ──────────────

def _supervisor_token() -> str:
    return os.environ.get('SUPERVISOR_TOKEN', '')


def resolve_addon_name(container: str | None) -> str | None:
    """Löst 'addon_local_gitpulse' -> 'GitPulse' auf, via Supervisor /addons-Liste.
    Cached 60s, damit nicht bei jedem Log-Eintrag ein API-Call passiert."""
    global _addon_names_cache, _addon_names_ts
    if not container:
        return None
    now = time.time()
    if now - _addon_names_ts > ADDON_NAMES_TTL:
        token = _supervisor_token()
        mapping = {}
        if token:
            try:
                req = urllib.request.Request(
                    f'{SUPERVISOR_API}/addons',
                    headers={'Authorization': f'Bearer {token}'})
                with urllib.request.urlopen(req, timeout=3) as resp:
                    data = json.loads(resp.read())
                for addon in data.get('data', {}).get('addons', []):
                    slug = addon.get('slug', '')
                    name = addon.get('name', slug)
                    if slug:
                        mapping[f'addon_local_{slug}'] = name
                        mapping[f'addon_{slug}'] = name
                        mapping[slug] = name
            except Exception:
                pass
        _addon_names_cache = mapping
        _addon_names_ts = now
    return _addon_names_cache.get(container, container)


# ── Log-Query-Helper ─────────────────────────────────────────────────────────

def _build_filter(args, include_levels: bool = True):
    """Baut WHERE/FROM/Params aus den Query-Args. include_levels=False lässt den
    Level-Filter weg — genutzt für die Summary-Stats, die die echte Fehler-/
    Warnungs-Anzahl zeigen sollen, unabhängig davon welche Level-Checkboxen
    der Nutzer gerade aktiviert hat."""
    source = args.get('source')
    containers = [c for c in args.getlist('container') if c]
    levels = [l for l in args.getlist('level') if l] if include_levels else []
    q = (args.get('q') or '').strip()
    since = args.get('since', type=float)
    until = args.get('until', type=float)

    where = []
    params: list = []

    if source:
        where.append("source = ?")
        params.append(source)
    if containers:
        where.append("container IN (%s)" % ",".join("?" * len(containers)))
        params.extend(containers)
    if levels:
        where.append("level IN (%s)" % ",".join("?" * len(levels)))
        params.extend(levels)
    if since is not None:
        where.append("ts >= ?")
        params.append(since)
    if until is not None:
        where.append("ts <= ?")
        params.append(until)

    base = "FROM log_entries"
    if q:
        # Plain LIKE statt FTS5 MATCH: MATCH lässt sich nicht mit OR
        # kombinieren (SQLite-Limitierung), und die Suche soll auch
        # Container-/Add-on-Namen treffen, nicht nur den Nachrichtentext.
        like = f"%{q}%"
        where.append("(log_entries.message LIKE ? OR log_entries.container LIKE ? "
                     "OR log_entries.addon_name LIKE ? OR log_entries.identifier LIKE ?)")
        params.extend([like, like, like, like])

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    return base, where_sql, params


def query_logs(args) -> dict:
    base, where_sql, params = _build_filter(args)
    limit = min(args.get('limit', 200, type=int) or 200, 1000)
    offset = args.get('offset', 0, type=int) or 0

    sql = (f"SELECT log_entries.id, ts, source, container, addon_name, identifier, level, log_entries.message "
           f"{base}{where_sql} ORDER BY log_entries.id DESC LIMIT ? OFFSET ?")

    with _db_lock:
        conn = get_conn()
        rows = conn.execute(sql, params + [limit, offset]).fetchall()

    return {
        'entries': [
            {'id': r[0], 'ts': r[1], 'source': r[2], 'container': r[3],
             'addon_name': r[4], 'identifier': r[5], 'level': r[6], 'message': r[7]}
            for r in rows
        ]
    }


def query_stats(args) -> dict:
    """Echte Gesamt-/Level-Zahlen für die Summary-Bar — nicht durch das
    limit von /api/logs gedeckelt."""
    base, where_sql, params = _build_filter(args, include_levels=False)
    sql = f"SELECT level, COUNT(*) {base}{where_sql} GROUP BY level"
    with _db_lock:
        conn = get_conn()
        rows = conn.execute(sql, params).fetchall()
    by_level = {r[0]: r[1] for r in rows}
    total = sum(by_level.values())
    warning = by_level.get('WARNING', 0)
    error = by_level.get('ERROR', 0) + by_level.get('CRITICAL', 0)
    return {'total': total, 'warning': warning, 'error': error}


# ── Routes ───────────────────────────────────────────────────────────────────

@app.before_request
def _require_login():
    open_paths = ('/login', '/static', '/health', '/manifest.json', '/sw.js', '/favicon.ico')
    if request.path.startswith(open_paths):
        return None
    if _is_ingress():
        return None
    if not is_valid_session(request.cookies.get('lp_session')):
        # API-Routen bekommen 401 statt Redirect — ein fetch() folgt dem
        # Redirect sonst transparent und liefert die Login-HTML-Seite als
        # "Erfolg" zurück, res.json() scheitert dann still (siehe syswatch).
        if request.path.startswith('/api/'):
            return '', 401
        return redirect(url_for('login'))
    return None


@app.route('/health')
def health():
    return jsonify({'ok': True})


@app.route('/login', methods=['GET', 'POST'])
def login():
    config = load_config()
    lang = detect_language(request)
    t = load_translations(lang)
    error = None

    if _is_ingress() or is_valid_session(request.cookies.get('lp_session')):
        return redirect(url_for('index'))

    ip = get_client_ip(request)

    if request.method == 'POST':
        if is_rate_limited(ip):
            error = t.get('error_locked', 'Too many failed attempts. Please try again later.')
        elif (request.form.get('username') == config.get('username') and
              request.form.get('password') == config.get('password')):
            clear_failed_attempts(ip)
            log.info("Login erfolgreich: ip='%s' user='%s'", ip, config.get('username'))
            hours = int(config.get('session_hours', 24))
            token, expires = create_session(hours)
            resp = make_response(redirect(url_for('index')))
            resp.set_cookie('lp_session', token,
                             expires=datetime.fromtimestamp(expires, tz=timezone.utc),
                             httponly=True, samesite='Lax')
            return resp
        else:
            record_failed_attempt(ip)
            log.warning("Login fehlgeschlagen: ip='%s' user='%s'",
                        ip, request.form.get('username', '?'))
            error = t.get('error_credentials', 'Invalid credentials.')

    return render_template('login.html', t=t, lang=lang, error=error)


@app.route('/logout')
def logout():
    token = request.cookies.get('lp_session')
    if token in sessions:
        del sessions[token]
        save_sessions()
    resp = make_response(redirect(url_for('login')))
    resp.delete_cookie('lp_session')
    return resp


@app.route('/set-lang/<lang>')
def set_lang(lang: str):
    if lang not in ('de', 'en'):
        abort(400)
    ref = (request.referrer or '/').replace('\\', '')
    parsed = urlparse(ref)
    if parsed.scheme or parsed.netloc or not ref.startswith('/'):
        ref = '/'
    resp = make_response(redirect(ref))
    resp.set_cookie('lang', lang, max_age=365 * 24 * 3600, samesite='Lax')
    return resp


@app.route('/')
def index():
    lang = detect_language(request)
    t = load_translations(lang)
    return render_template('index.html', t=t, lang=lang, script_root=request.script_root)


@app.route('/manifest.json')
def manifest():
    base = request.script_root.rstrip('/')
    data = {
        'name': 'LogPulse',
        'short_name': 'LogPulse',
        'description': 'Zentrale, durchsuchbare Log-Historie aus journald',
        'start_url': base + '/',
        'scope': base + '/',
        'display': 'standalone',
        'orientation': 'portrait-primary',
        'background_color': '#0d1117',
        'theme_color': '#161b22',
        'icons': [
            {'src': url_for('static', filename='icon-192.png'), 'sizes': '192x192',
             'type': 'image/png', 'purpose': 'any maskable'},
            {'src': url_for('static', filename='icon-512.png'), 'sizes': '512x512',
             'type': 'image/png', 'purpose': 'any maskable'},
        ],
        'categories': ['utilities', 'productivity'],
        'lang': 'de',
    }
    resp = make_response(jsonify(data))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    resp.headers['Content-Type'] = 'application/manifest+json'
    return resp


@app.route('/sw.js')
def service_worker():
    base = request.script_root.rstrip('/')
    resp = make_response(render_template('sw.js', base=base))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    resp.headers['Content-Type'] = 'application/javascript'
    return resp


@app.route('/api/logs')
def api_logs():
    return jsonify(query_logs(request.args))


@app.route('/api/stats')
def api_stats():
    return jsonify(query_stats(request.args))


@app.route('/api/sources')
def api_sources():
    with _db_lock:
        conn = get_conn()
        rows = conn.execute(
            "SELECT source, container, addon_name, COUNT(*) "
            "FROM log_entries GROUP BY source, container, addon_name "
            "ORDER BY source, addon_name"
        ).fetchall()
    return jsonify({
        'sources': [
            {'source': r[0], 'container': r[1], 'addon_name': r[2], 'count': r[3]}
            for r in rows
        ]
    })


@app.route('/api/db/clear', methods=['POST'])
def api_db_clear():
    with _db_lock:
        conn = get_conn()
        conn.execute("DELETE FROM log_entries")
        conn.commit()
        conn.execute("VACUUM")
        # VACUUM schreibt im WAL-Modus zunächst nur in die -wal-Datei —
        # ohne expliziten TRUNCATE-Checkpoint bleibt die Hauptdatei (und die
        # WAL-Datei) auf der alten Größe, bis SQLite irgendwann von selbst
        # checkpointet.
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    log.info("Log-Datenbank auf Nutzerwunsch geleert")
    return jsonify({'ok': True})


@app.route('/api/dbinfo')
def api_dbinfo():
    size_bytes = 0
    for path in (DB_PATH, DB_PATH + '-wal', DB_PATH + '-shm'):
        try:
            size_bytes += os.path.getsize(path)
        except OSError:
            pass
    cfg = load_config()
    return jsonify({
        'size_mb': round(size_bytes / (1024 * 1024), 2),
        'max_mb': int(cfg.get('max_db_size_mb', 300)),
        'retention_days': int(cfg.get('retention_days', 14)),
    })


@app.route('/api/wait')
def api_wait():
    """Long-Polling statt SSE — SSE ist über HA-Nginx-Ingress unzuverlässig
    (Buffering), Long-Polling funktioniert dort nachweislich (siehe syswatch)."""
    client_q: queue.Queue = queue.Queue(maxsize=1)
    with _wait_lock:
        _wait_queues.append(client_q)
    try:
        try:
            client_q.get(timeout=30)
        except queue.Empty:
            pass
        return '', 204
    finally:
        with _wait_lock:
            try:
                _wait_queues.remove(client_q)
            except ValueError:
                pass


@app.route('/api/console')
def api_console():
    since = request.args.get('since', 0, type=int)
    entries = [e for e in _log_buffer if e['ts'] > since]
    return jsonify({'entries': entries})


@app.route('/api/ingest/status')
def api_ingest_status():
    return jsonify({'paused': not _pause_event.is_set()})


@app.route('/api/ingest/pause', methods=['POST'])
def api_ingest_pause():
    _pause_event.clear()
    save_ingest_paused(True)
    log.info("Log-Erfassung auf Nutzerwunsch pausiert")
    return jsonify({'ok': True, 'paused': True})


@app.route('/api/ingest/resume', methods=['POST'])
def api_ingest_resume():
    _pause_event.set()
    save_ingest_paused(False)
    log.info("Log-Erfassung fortgesetzt")
    return jsonify({'ok': True, 'paused': False})


@app.route('/api/sysinfo')
def api_sysinfo():
    return jsonify(_res_stats)


def _res_sampler_loop(interval: int = 3) -> None:
    """Eigener CPU-/RAM-Verbrauch via /proc/self — kein docker_api/cgroup-Zugriff
    nötig, funktioniert unprivilegiert in jedem Container (siehe SysWatch für
    das host-weite Pendant)."""
    clk_tck = os.sysconf('SC_CLK_TCK')
    prev_cpu = None
    prev_wall = None
    while True:
        try:
            with open('/proc/self/stat') as f:
                rest = f.read().rpartition(')')[2].split()
            utime, stime = int(rest[11]), int(rest[12])
            cpu_seconds = (utime + stime) / clk_tck
            wall = time.monotonic()
            if prev_cpu is not None:
                dt = wall - prev_wall
                if dt > 0:
                    _res_stats['cpu_percent'] = round(max(0.0, (cpu_seconds - prev_cpu) / dt * 100), 1)
            prev_cpu, prev_wall = cpu_seconds, wall

            with open('/proc/self/status') as f:
                for line in f:
                    if line.startswith('VmRSS:'):
                        _res_stats['mem_mb'] = round(int(line.split()[1]) / 1024, 1)
                        break
        except Exception:
            log.exception("Ressourcen-Sampler fehlgeschlagen")
        time.sleep(interval)


def _resolve_addon_name_wrapper(container):
    return resolve_addon_name(container)


def _handle_sigterm(signum, frame) -> None:
    """Sauberer Exit bei SIGTERM (HA-Supervisor-Stop/Update) — ohne eigenen Handler
    würde Python den Default-Handler laufen lassen (exit 143), worüber sich der
    Supervisor beschwert ("should trap SIGTERM ... exit with code 0"). Alle
    Hintergrund-Threads sind daemon=True (siehe main()), ein harter os._exit(0)
    ist daher sicher — kein offener State, der noch geflusht werden müsste
    (DB-Schreibzugriffe committen bereits pro Block, siehe get_conn())."""
    log.info("SIGTERM empfangen, beende sauber…")
    os._exit(0)


def main():
    signal.signal(signal.SIGTERM, _handle_sigterm)
    load_sessions()
    init_db()
    cfg = load_config()
    poll_timeout_ms = int(cfg.get('poll_timeout_ms', 5000))

    if load_ingest_paused():
        _pause_event.clear()

    threading.Thread(
        target=journal_reader.reader_loop,
        args=(get_conn, _db_lock, _resolve_addon_name_wrapper, notify_new, poll_timeout_ms),
        kwargs={'load_config': load_config, 'pause_event': _pause_event},
        daemon=True,
    ).start()

    threading.Thread(
        target=journal_reader.retention_loop,
        args=(get_conn, _db_lock, load_config, DB_PATH),
        daemon=True,
    ).start()

    threading.Thread(target=_res_sampler_loop, daemon=True).start()

    app.run(host='0.0.0.0', port=17795, debug=False, threaded=True)


if __name__ == '__main__':
    main()
