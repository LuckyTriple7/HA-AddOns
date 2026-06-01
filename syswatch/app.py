#!/usr/bin/env python3
import json
import logging
import os
import queue
import secrets
import time
import threading
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from flask import (Flask, render_template, request, redirect,
                   url_for, make_response, abort, jsonify, send_from_directory,
                   Response, stream_with_context)
from werkzeug.middleware.proxy_fix import ProxyFix

try:
    import docker as docker_lib
    _docker_available = True
except ImportError:
    _docker_available = False

logging.basicConfig(format='[%(levelname)s] %(message)s', level=logging.INFO)
log = logging.getLogger(__name__)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

app = Flask(__name__, template_folder='/app/templates', static_folder='/app/static')
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

CONFIG_PATH   = '/data/options.json'
SESSIONS_PATH = '/data/sessions.json'
LOCALES_PATH  = '/app/locales'
HISTORY_SIZE  = 30
COLLECT_INTERVAL_DEFAULT = 3   # fallback if not set in config
MAX_WORKERS_DEFAULT      = 16  # parallel docker stats calls (4–64 reasonable range)

# HAOS exposes the Docker socket at different paths depending on version/config
DOCKER_SOCKET_CANDIDATES = [
    '/var/run/docker.sock',
    '/run/docker.sock',
    '/host/var/run/docker.sock',
    '/host/run/docker.sock',
]
SUPERVISOR_API = 'http://supervisor'

_config_cache = None
_config_mtime = 0.0
sessions: dict[str, float] = {}

# ── System stats (/proc) ──────────────────────────────────────────────────────
_prev_cpu: tuple[int, int] = (0, 0)  # (total_ticks, idle_ticks)


def _read_sysinfo() -> dict:
    global _prev_cpu
    info: dict = {'cpu_pct': 0.0, 'mem_total': 0, 'mem_used': 0, 'mem_pct': 0.0}

    # CPU % via /proc/stat (delta between two calls)
    try:
        with open('/proc/stat') as f:
            line = f.readline()
        parts  = [int(x) for x in line.split()[1:]]
        idle   = parts[3] + (parts[4] if len(parts) > 4 else 0)  # idle + iowait
        total  = sum(parts)
        pt, pi = _prev_cpu
        _prev_cpu = (total, idle)
        dt = total - pt
        di = idle  - pi
        if dt > 0:
            info['cpu_pct'] = round((1 - di / dt) * 100, 1)
    except Exception as e:
        log.debug("/proc/stat nicht lesbar: %s", e)

    # RAM via /proc/meminfo
    try:
        with open('/proc/meminfo') as f:
            raw = f.read()
        mi = {}
        for row in raw.splitlines():
            p = row.split()
            if len(p) >= 2:
                mi[p[0].rstrip(':')] = int(p[1]) * 1024  # kB → bytes
        total = mi.get('MemTotal', 0)
        avail = mi.get('MemAvailable', 0)
        used  = total - avail
        info.update({
            'mem_total': total,
            'mem_used':  used,
            'mem_pct':   round(used / total * 100, 1) if total else 0.0,
        })
    except Exception as e:
        log.debug("/proc/meminfo nicht lesbar: %s", e)

    # CPU frequency via /proc/cpuinfo
    try:
        with open('/proc/cpuinfo') as f:
            raw = f.read()
        freqs = [float(l.split(':')[1].strip())
                 for l in raw.splitlines() if l.startswith('cpu MHz')]
        if freqs:
            info['cpu_count']    = len(freqs)
            info['freq_ghz_avg'] = round(sum(freqs) / len(freqs) / 1000, 2)
            info['freq_ghz_max'] = round(max(freqs) / 1000, 2)
    except Exception as e:
        log.debug("/proc/cpuinfo nicht lesbar: %s", e)

    return info


# ── Rate limiting ──────────────────────────────────────────────────────────────
_failed_attempts: dict[str, list[float]] = defaultdict(list)
_blocked_ips:     dict[str, float]       = {}
RATE_LIMIT_MAX    = 5
RATE_LIMIT_WINDOW = 10 * 60
RATE_LIMIT_BLOCK  = 15 * 60

# ── Docker stats cache ─────────────────────────────────────────────────────────
_stats_cache: dict  = {'containers': [], 'sysinfo': {}, 'error': None, 'warning': None, 'ts': 0}
_last_elapsed: float = 0.0
_viewer_last_seen: float = time.time()  # assume active on startup
_viewer_paused:    bool  = False        # True wenn UI-Pause-Button gedrückt
_collector_mode:   str   = 'startup'    # 'active' | 'idle' | 'startup'
_collect_event             = threading.Event()  # wakes collector early on heartbeat
_sse_queues: list          = []
_sse_lock                  = threading.Lock()
VIEWER_TIMEOUT_DEFAULT = 180  # seconds without heartbeat → idle mode (30s–1800s)


def _notify_sse() -> None:
    """Signal all connected SSE clients that fresh data is available."""
    with _sse_lock:
        for q in list(_sse_queues):
            try:
                q.put_nowait('update')
            except queue.Full:
                pass
_stats_lock         = threading.Lock()
_history: dict[str, deque] = {}


# ── Config & sessions ──────────────────────────────────────────────────────────

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
        if sessions:
            log.info("Sessions geladen: %d aktive(s)", len(sessions))
    except FileNotFoundError:
        pass
    except Exception as e:
        log.warning("Sessions konnten nicht geladen werden: %s", e)


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


def get_client_ip(req) -> str:
    cf = req.headers.get('CF-Connecting-IP', '').strip()
    if cf:
        return cf
    return req.remote_addr or 'unknown'


# ── Rate limiting ──────────────────────────────────────────────────────────────

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


# ── i18n ───────────────────────────────────────────────────────────────────────

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


# ── Docker socket helpers ──────────────────────────────────────────────────────

def _find_docker_socket() -> str | None:
    for path in DOCKER_SOCKET_CANDIDATES:
        if os.path.exists(path):
            log.info("Docker-Socket gefunden: %s", path)
            return path
    return None


def _supervisor_token() -> str:
    return os.environ.get('SUPERVISOR_TOKEN', '')


def _collect_via_supervisor() -> list[dict]:
    """Fallback: Add-on-Stats über die HA Supervisor REST-API."""
    import urllib.request
    token = _supervisor_token()
    if not token:
        return []
    headers = {'Authorization': f'Bearer {token}'}

    try:
        req = urllib.request.Request(f'{SUPERVISOR_API}/addons', headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        addons = data.get('data', {}).get('addons', [])
    except Exception as e:
        log.error("Supervisor /addons Fehler: %s", e)
        return []

    results = []
    for addon in addons:
        slug  = addon.get('slug', '')
        state = addon.get('state', 'unknown')
        base  = {
            'id':        slug,
            'name':      addon.get('name', slug),
            'image':     f'HA Add-on',
            'status':    'running' if state == 'started' else state,
            'cpu_pct':   0.0,
            'mem_usage': 0,
            'mem_limit': 0,
            'mem_pct':   0.0,
            'net_rx':    0,
            'net_tx':    0,
            'blk_r':     0,
            'blk_w':     0,
            'pids':      0,
        }
        if state != 'started':
            results.append(base)
            continue
        try:
            req = urllib.request.Request(
                f'{SUPERVISOR_API}/addons/{slug}/stats', headers=headers)
            with urllib.request.urlopen(req, timeout=3) as resp:
                s = json.loads(resp.read()).get('data', {})
            results.append({
                **base,
                'cpu_pct':   round(s.get('cpu_percent', 0.0), 2),
                'mem_usage': s.get('memory_usage', 0),
                'mem_limit': s.get('memory_limit', 0),
                'mem_pct':   round(s.get('memory_percent', 0.0), 2),
                'net_rx':    s.get('network_rx', 0),
                'net_tx':    s.get('network_tx', 0),
                'blk_r':     s.get('blk_read', 0),
                'blk_w':     s.get('blk_write', 0),
            })
        except Exception as e:
            log.debug("Supervisor stats für '%s' fehlgeschlagen: %s", slug, e)
            results.append(base)

    return results


def _update_history_and_cache(results: list, warning: str | None = None) -> None:
    ts      = time.time()
    sysinfo = _read_sysinfo()
    for r in results:
        n = r['name']
        if n not in _history:
            _history[n] = deque(maxlen=HISTORY_SIZE)
        if r['status'] == 'running':
            _history[n].append({'ts': ts, 'cpu': r['cpu_pct'], 'mem': r['mem_pct']})
    for r in results:
        r['history'] = list(_history.get(r['name'], []))
    with _stats_lock:
        _stats_cache['containers'] = results
        _stats_cache['sysinfo']    = sysinfo
        _stats_cache['error']      = None
        _stats_cache['warning']    = warning
        _stats_cache['ts']         = ts
    _notify_sse()


# ── Docker stats ───────────────────────────────────────────────────────────────

def _parse_container(container) -> dict:
    name = container.name
    image = ''
    try:
        tags = container.image.tags
        image = tags[0] if tags else container.image.short_id
    except Exception:
        pass

    base = {
        'id': container.short_id,
        'name': name,
        'image': image,
        'status': container.status,
        'cpu_pct': 0.0,
        'mem_usage': 0,
        'mem_limit': 0,
        'mem_pct': 0.0,
        'net_rx': 0,
        'net_tx': 0,
        'blk_r': 0,
        'blk_w': 0,
        'pids': 0,
    }

    if container.status != 'running':
        return base

    try:
        raw = container.stats(stream=False)

        # CPU %
        cpu_delta = (raw['cpu_stats']['cpu_usage']['total_usage']
                     - raw['precpu_stats']['cpu_usage']['total_usage'])
        sys_delta = (raw['cpu_stats'].get('system_cpu_usage', 0)
                     - raw['precpu_stats'].get('system_cpu_usage', 0))
        ncpus = raw['cpu_stats'].get('online_cpus') or len(
            raw['cpu_stats']['cpu_usage'].get('percpu_usage') or [1])
        cpu_pct = (cpu_delta / sys_delta * ncpus * 100.0) if sys_delta > 0 else 0.0

        # Memory (subtract page cache for real RSS)
        mem_stats = raw.get('memory_stats', {})
        cache = (mem_stats.get('stats', {}) or {}).get('inactive_file',
                 (mem_stats.get('stats', {}) or {}).get('cache', 0))
        mem_usage = max(0, mem_stats.get('usage', 0) - cache)
        mem_limit = mem_stats.get('limit', 1) or 1
        mem_pct = mem_usage / mem_limit * 100.0

        # Network I/O
        net_rx = sum(v.get('rx_bytes', 0) for v in raw.get('networks', {}).values())
        net_tx = sum(v.get('tx_bytes', 0) for v in raw.get('networks', {}).values())

        # Block I/O
        blk_r = blk_w = 0
        for entry in (raw.get('blkio_stats', {}).get('io_service_bytes_recursive') or []):
            op  = entry.get('op', '').lower()
            val = entry.get('value', 0)
            if op == 'read':
                blk_r += val
            elif op == 'write':
                blk_w += val

        return {
            **base,
            'cpu_pct':   round(cpu_pct, 2),
            'mem_usage': mem_usage,
            'mem_limit': mem_limit,
            'mem_pct':   round(mem_pct, 2),
            'net_rx':    net_rx,
            'net_tx':    net_tx,
            'blk_r':     blk_r,
            'blk_w':     blk_w,
            'pids':      raw.get('pids_stats', {}).get('current', 0),
        }
    except Exception as e:
        log.debug("Stats für '%s' fehlgeschlagen: %s", name, e)
        return base


def _collect_once(max_workers: int = MAX_WORKERS_DEFAULT,
                  abort: threading.Event | None = None) -> None:
    global _stats_cache

    # Skip immediately if already signalled (e.g. user resumed before collection starts)
    if abort and abort.is_set():
        return

    # ── Attempt 1: Docker socket ───────────────────────────────────────────────
    if _docker_available:
        socket_path = _find_docker_socket()
        if socket_path:
            try:
                t0         = time.time()
                client     = docker_lib.DockerClient(base_url=f'unix://{socket_path}')
                containers = client.containers.list(all=True)
                workers    = min(max(len(containers), 1), max_workers)

                ex      = ThreadPoolExecutor(max_workers=workers)
                futures = [ex.submit(_parse_container, c) for c in containers]
                results = []
                aborted = False
                try:
                    for future in as_completed(futures):
                        if abort and abort.is_set():
                            log.info("Idle-Abfrage abgebrochen — Browser aktiv")
                            aborted = True
                            break
                        try:
                            results.append(future.result())
                        except Exception:
                            pass
                finally:
                    ex.shutdown(wait=False)  # laufende Threads laufen aus, keine neuen

                if aborted:
                    return  # Cache nicht aktualisieren; nächster Aktiv-Zyklus holt frisch

                elapsed      = time.time() - t0
                _last_elapsed = elapsed
                running      = sum(1 for r in results if r['status'] == 'running')
                log.info("Abfrage: %d Container (%d laufend) | %d Worker | %.1fs",
                         len(results), running, workers, elapsed)
                _update_history_and_cache(results)
                return
            except Exception as e:
                log.error("Docker-Socket-Fehler (%s): %s", socket_path, e)
                with _stats_lock:
                    _stats_cache['error'] = str(e)
                    _stats_cache['ts']    = time.time()
                return

    # ── Attempt 2: Supervisor API (HA add-ons only) ────────────────────────────
    results = _collect_via_supervisor()
    if results:
        _update_history_and_cache(
            results,
            warning='Docker-Socket nicht gefunden — zeige nur HA Add-ons (Supervisor API)',
        )
        return

    # ── Nothing worked ─────────────────────────────────────────────────────────
    tried = ', '.join(DOCKER_SOCKET_CANDIDATES)
    with _stats_lock:
        _stats_cache = {
            'containers': [],
            'warning':    None,
            'error':      (f'Docker-Socket nicht gefunden (probiert: {tried}) '
                           f'und Supervisor API nicht erreichbar. '
                           f'full_access: true in config.yaml prüfen.'),
            'ts':         time.time(),
        }


def _viewer_timeout() -> int:
    return max(30, min(1800, int(load_config().get('viewer_timeout', VIEWER_TIMEOUT_DEFAULT))))


def _is_viewer_active() -> bool:
    with _sse_lock:
        has_sse = len(_sse_queues) > 0
    return has_sse or (time.time() - _viewer_last_seen) < _viewer_timeout()


def _background_collector() -> None:
    global _collector_mode
    while True:
        active     = _is_viewer_active()
        new_mode   = 'active' if active else 'idle'

        if new_mode != _collector_mode:
            if new_mode == 'idle':
                if _viewer_paused:
                    log.info("Browser pausiert → IDLE-Modus (2 Worker, 60s Interval)")
                else:
                    log.info("Kein Browser aktiv seit %ds → IDLE-Modus (2 Worker, 60s Interval)",
                             _viewer_timeout())
            else:
                cfg = load_config()
                log.info("Browser verbunden → AKTIV-Modus (%d Worker, %ds Interval)",
                         max(4, min(64, int(cfg.get('collect_workers', MAX_WORKERS_DEFAULT)))),
                         max(2, int(cfg.get('collect_interval', COLLECT_INTERVAL_DEFAULT))))
            _collector_mode = new_mode

        try:
            if active:
                cfg  = load_config()
                _collect_once(
                    max_workers=max(4, min(64, int(cfg.get('collect_workers', MAX_WORKERS_DEFAULT))))
                )
                interval = max(2, int(cfg.get('collect_interval', COLLECT_INTERVAL_DEFAULT)))
            else:
                # abort=_collect_event: Sammlung sofort abbrechen wenn Browser Resume signalisiert
                _collect_once(max_workers=2, abort=_collect_event)
                interval = 60
        except Exception as e:
            log.error("Hintergrund-Collector-Fehler: %s", e)
            interval = 10
        _collect_event.wait(timeout=interval)
        _collect_event.clear()


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('/app/static', 'icon-192.png', mimetype='image/png')


@app.route('/manifest.json')
def manifest():
    resp = send_from_directory('/app/static', 'manifest.json',
                               mimetype='application/manifest+json')
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma']        = 'no-cache'
    resp.headers['Expires']       = '0'
    return resp


@app.route('/sw.js')
def sw():
    resp = send_from_directory('/app/static', 'sw.js',
                               mimetype='application/javascript')
    resp.headers['Cache-Control']         = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma']                = 'no-cache'
    resp.headers['Expires']               = '0'
    resp.headers['Service-Worker-Allowed'] = '/'
    return resp


@app.route('/health')
def health():
    return 'ok', 200


@app.route('/')
def index():
    if not is_valid_session(request.cookies.get('sw_session')):
        return redirect(url_for('login'))
    lang = detect_language(request)
    t    = load_translations(lang)
    return render_template('index.html', t=t, lang=lang)


@app.route('/login', methods=['GET', 'POST'])
def login():
    config = load_config()
    lang   = detect_language(request)
    t      = load_translations(lang)
    error  = None

    if is_valid_session(request.cookies.get('sw_session')):
        return redirect(url_for('index'))

    ip = get_client_ip(request)

    if request.method == 'POST':
        if is_rate_limited(ip):
            log.warning("Login blockiert (Rate Limit): ip='%s'", ip)
            error = t.get('error_locked', 'Too many failed attempts. Please try again later.')
        elif (request.form.get('username') == config.get('username') and
              request.form.get('password') == config.get('password')):
            clear_failed_attempts(ip)
            log.info("Login erfolgreich: ip='%s' user='%s'", ip, config.get('username'))
            hours = int(config.get('session_hours', 24))
            token, expires = create_session(hours)
            resp = make_response(redirect(url_for('index')))
            resp.set_cookie(
                'sw_session', token,
                expires=datetime.fromtimestamp(expires, tz=timezone.utc),
                httponly=True, samesite='Lax',
            )
            return resp
        else:
            record_failed_attempt(ip)
            log.warning("Login fehlgeschlagen: ip='%s' user='%s'",
                        ip, request.form.get('username', '?'))
            error = t.get('error_credentials', 'Invalid credentials.')

    return render_template('login.html', t=t, lang=lang, error=error)


@app.route('/logout')
def logout():
    token = request.cookies.get('sw_session')
    if token in sessions:
        del sessions[token]
        save_sessions()
    log.info("Abmeldung: ip='%s'", get_client_ip(request))
    resp = make_response(redirect(url_for('login')))
    resp.delete_cookie('sw_session')
    return resp


@app.route('/set-lang/<lang>')
def set_lang(lang: str):
    if lang not in ('de', 'en'):
        abort(400)
    ref  = request.referrer or url_for('index')
    resp = make_response(redirect(ref))
    resp.set_cookie('lang', lang, max_age=365 * 24 * 3600, samesite='Lax')
    return resp


# ── API ────────────────────────────────────────────────────────────────────────

@app.route('/api/wait')
def api_wait():
    """Long-polling: blocks until new stats are available, then returns 204.
    More reliable than SSE through HA nginx ingress (no streaming/buffering issues)."""
    if not is_valid_session(request.cookies.get('sw_session')):
        return '', 401

    client_q = queue.Queue(maxsize=1)
    with _sse_lock:
        _sse_queues.append(client_q)
    try:
        try:
            client_q.get(timeout=30)
        except queue.Empty:
            pass  # timeout — browser will retry immediately
        return '', 204
    finally:
        with _sse_lock:
            try:
                _sse_queues.remove(client_q)
            except ValueError:
                pass


@app.route('/api/viewer', methods=['POST'])
def api_viewer():
    """Browser signals active/paused state — immediately switches collector mode."""
    global _viewer_last_seen, _viewer_paused, _collector_mode
    if not is_valid_session(request.cookies.get('sw_session')):
        return '', 401
    body   = request.get_json(silent=True) or {}
    active = body.get('active', True)
    ip     = get_client_ip(request)
    if active:
        _viewer_paused    = False
        _viewer_last_seen = time.time()
        _collector_mode   = 'active'  # sofort aktiv, damit nächster /api/stats-Poll grün zeigt
        _collect_event.set()
        log.info("UI: Datenerfassung fortgesetzt (ip='%s')", ip)
    else:
        _viewer_paused    = True
        _viewer_last_seen = 0.0  # force idle immediately
        log.info("UI: Datenerfassung pausiert (ip='%s')", ip)
    return '', 204


@app.route('/api/heartbeat', methods=['POST'])
def api_heartbeat():
    global _viewer_last_seen, _viewer_paused, _collector_mode
    if not is_valid_session(request.cookies.get('sw_session')):
        return '', 401
    was_idle = _collector_mode == 'idle'  # _is_viewer_active() wäre unzuverlässig wenn longPoll schon verbunden
    _viewer_last_seen = time.time()
    _viewer_paused    = False
    if was_idle:
        _collector_mode = 'active'
        ip = get_client_ip(request)
        log.info("Heartbeat empfangen (ip='%s') — Wechsel IDLE→AKTIV", ip)
        _collect_event.set()  # 60s-Sleep sofort unterbrechen
    return '', 204


@app.route('/api/stats')
def api_stats():
    if not is_valid_session(request.cookies.get('sw_session')):
        return '', 401
    with _stats_lock:
        data = dict(_stats_cache)
    data['collector_mode'] = _collector_mode
    cfg = load_config()
    sleep_s = max(2, int(cfg.get('collect_interval', COLLECT_INTERVAL_DEFAULT)))
    data['cycle_s'] = round(_last_elapsed + sleep_s + 1.0, 1)  # 1s buffer for variability
    return jsonify(data)


@app.route('/api/container/<name>/logs')
def api_logs(name: str):
    if not is_valid_session(request.cookies.get('sw_session')):
        return '', 401
    socket_path = _find_docker_socket() if _docker_available else None
    if not socket_path:
        return jsonify({'error': 'Docker-Socket nicht verfügbar'}), 503
    try:
        client    = docker_lib.DockerClient(base_url=f'unix://{socket_path}')
        container = client.containers.get(name)
        logs      = container.logs(tail=200, timestamps=True).decode('utf-8', errors='replace')
        return jsonify({'logs': logs})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/container/<name>/restart', methods=['POST'])
def api_restart(name: str):
    if not is_valid_session(request.cookies.get('sw_session')):
        return '', 401
    # Require password confirmation for destructive action
    body     = request.get_json(silent=True) or {}
    config   = load_config()
    if body.get('password', '') != config.get('password', ''):
        log.warning("Neustart abgelehnt (falsches Passwort): container='%s'", name)
        return jsonify({'error': 'wrong_password'}), 403
    socket_path = _find_docker_socket() if _docker_available else None
    if not socket_path:
        return jsonify({'error': 'Docker-Socket nicht verfügbar'}), 503
    try:
        client    = docker_lib.DockerClient(base_url=f'unix://{socket_path}')
        container = client.containers.get(name)
        container.restart()
        log.info("Container neugestartet: %s", name)
        return jsonify({'ok': True})
    except Exception as e:
        log.error("Restart-Fehler für '%s': %s", name, e)
        return jsonify({'error': str(e)}), 500


@app.route('/api/container/<name>/kill', methods=['POST'])
def api_kill(name: str):
    if not is_valid_session(request.cookies.get('sw_session')):
        return '', 401
    body   = request.get_json(silent=True) or {}
    config = load_config()
    if body.get('password', '') != config.get('password', ''):
        log.warning("Kill abgelehnt (falsches Passwort): container='%s'", name)
        return jsonify({'error': 'wrong_password'}), 403
    socket_path = _find_docker_socket() if _docker_available else None
    if not socket_path:
        return jsonify({'error': 'Docker-Socket nicht verfügbar'}), 503
    try:
        client    = docker_lib.DockerClient(base_url=f'unix://{socket_path}')
        container = client.containers.get(name)
        container.kill()
        log.info("Container gekillt (SIGKILL): %s", name)
        return jsonify({'ok': True})
    except Exception as e:
        log.error("Kill-Fehler für '%s': %s", name, e)
        return jsonify({'error': str(e)}), 500


# ── Startup ────────────────────────────────────────────────────────────────────

def _log_startup() -> None:
    cfg = load_config()
    log.info("=" * 55)
    log.info("  HA SysWatch v0.2.0 startet auf Port 17790")
    log.info("  collect_interval : %ds  |  collect_workers: %d",
             max(2, int(cfg.get('collect_interval', COLLECT_INTERVAL_DEFAULT))),
             max(4, min(64, int(cfg.get('collect_workers',  MAX_WORKERS_DEFAULT)))))
    log.info("  session_hours    : %dh  |  idle timeout   : %ds",
             int(cfg.get('session_hours', 24)),
             max(30, min(1800, int(cfg.get('viewer_timeout', VIEWER_TIMEOUT_DEFAULT)))))
    log.info("  Docker-Socket-Kandidaten: %s", ', '.join(DOCKER_SOCKET_CANDIDATES))
    log.info("=" * 55)


load_sessions()
_log_startup()
threading.Thread(target=_background_collector, daemon=True, name='docker-collector').start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=17790, debug=False)
