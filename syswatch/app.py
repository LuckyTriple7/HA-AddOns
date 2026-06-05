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

logging.basicConfig(format='[%(levelname)s] [%(asctime)s] %(message)s', level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S', force=True)
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
_ha_status_cache: dict  = {}
_ha_status_ts:    float = 0.0
_notif_cpu_ts:      float = 0.0   # letzter Versand CPU-Alert
_notif_ram_ts:      float = 0.0   # letzter Versand RAM-Alert
_notif_cpu_above:    bool  = False  # war CPU zuletzt über Schwellenwert?
_notif_ram_above:    bool  = False  # war RAM zuletzt über Schwellenwert?
_notif_cpu_over_since: float = 0.0  # seit wann CPU über Schwellenwert (für Verzögerung)
_notif_ram_over_since: float = 0.0
_notif_cpu_ok_since:  float = 0.0  # seit wann CPU unter Schwellenwert (für Entwarnung)
_notif_ram_ok_since:  float = 0.0
NOTIF_COOLDOWN               = 600  # 10 Min Cooldown zwischen gleichen Alerts

# Container-Zustandsüberwachung
_prev_running:      set[str]        = set()
_prev_running_init: bool            = False
_manually_stopped:    dict[str, float] = {}  # name → timestamp (vom SysWatch-Button ausgelöst)
_manually_started:    dict[str, float] = {}  # name → timestamp
_pending_restart_msgs: dict[str, dict] = {}  # name → {message_id, chat_id} für Callback-Nachrichten
_auto_chat_id:         str             = ''  # automatisch erkannte Chat-ID (ersetzt manuelle Konfig)
MANUAL_ACTION_TTL                     = 90   # Sekunden bis manueller Eintrag verfällt

# Verlaufs-DB (SQLite, 24h-Minuten-Buckets)
import sqlite3 as _sqlite3
_DB_PATH        = '/config/syswatch_history.db'
_db_lock        = threading.Lock()
_hist_last_min:  int   = 0   # letzter geschriebener Minuten-Bucket (Unix-Timestamp)
_hist_cpu_acc:   list  = []  # Akkumulator bis zum nächsten Minuten-Flush
_hist_ram_acc:   list  = []

# Hardware-Sensoren (Temp + Lüfter), gecacht
_hw_cache:  dict  = {'cpu_temp': None, 'fans': []}
_hw_ts:     float = 0.0
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

def _verbose() -> bool:
    return bool(load_config().get('verbose_log', False))


def _find_docker_socket() -> str | None:
    for path in DOCKER_SOCKET_CANDIDATES:
        if os.path.exists(path):
            if _verbose():
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


def _get_ha_status() -> dict:
    """Holt HA Status + Versionen via Supervisor API (parallel), 60s Cache."""
    global _ha_status_cache, _ha_status_ts
    now = time.time()
    if _ha_status_cache and now - _ha_status_ts < 60:
        return _ha_status_cache

    import urllib.request
    token = _supervisor_token()
    empty = {'connected': False, 'supported': None, 'healthy': None,
             'core_version': '', 'supervisor_version': '', 'os_version': '',
             'host_ip': '', 'hostname': ''}
    if not token:
        _ha_status_cache = empty; _ha_status_ts = now
        return empty

    headers = {'Authorization': f'Bearer {token}'}

    def _fetch(path: str) -> dict:
        try:
            req = urllib.request.Request(f'{SUPERVISOR_API}{path}', headers=headers)
            with urllib.request.urlopen(req, timeout=3) as resp:
                return json.loads(resp.read()).get('data', {})
        except Exception:
            return {}

    with ThreadPoolExecutor(max_workers=4) as ex:
        f_sup  = ex.submit(_fetch, '/supervisor/info')
        f_core = ex.submit(_fetch, '/core/info')
        f_os   = ex.submit(_fetch, '/os/info')
        f_net  = ex.submit(_fetch, '/network/info')
        d_sup, d_core, d_os, d_net = (
            f_sup.result(), f_core.result(), f_os.result(), f_net.result())

    # Host-IP aus erster verbundener Netzwerkschnittstelle
    host_ip = ''
    for iface in d_net.get('interfaces', []):
        if not iface.get('connected', False):
            continue
        addrs = (iface.get('ipv4') or {}).get('address', [])
        if addrs:
            host_ip = addrs[0].split('/')[0]  # '192.168.1.1/24' → '192.168.1.1'
            break

    if d_sup:
        result = {
            'connected':          True,
            'supported':          bool(d_sup.get('supported', True)),
            'healthy':            bool(d_sup.get('healthy', True)),
            'supervisor_version': d_sup.get('version', ''),
            'core_version':       d_core.get('version', ''),
            'os_version':         d_os.get('version', ''),
            'host_ip':            host_ip,
            'hostname':           d_net.get('hostname', ''),
        }
    else:
        result = {**empty, 'host_ip': host_ip, 'hostname': ''}
    _ha_status_cache = result; _ha_status_ts = now
    return result


def _supervisor_addon_slug(name: str) -> str | None:
    """Sucht den Slug eines HA Add-ons anhand seines Namens oder Slugs."""
    import urllib.request
    token = _supervisor_token()
    if not token:
        return None
    headers = {'Authorization': f'Bearer {token}'}
    try:
        req = urllib.request.Request(f'{SUPERVISOR_API}/addons', headers=headers)
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
        # Docker-Containernamen beginnen mit 'addon_', Supervisor-Slugs nicht
        name_as_slug = name.removeprefix('addon_')
        for addon in data.get('data', {}).get('addons', []):
            slug = addon.get('slug', '')
            if (addon.get('name', '').lower() == name.lower()
                    or slug == name or slug == name_as_slug):
                return slug
    except Exception:
        pass
    return None


def _supervisor_action(slug: str, action: str) -> bool:
    """Führt start/stop/restart für ein HA Add-on über die Supervisor API aus."""
    import urllib.request
    token = _supervisor_token()
    if not token:
        return False
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    try:
        req = urllib.request.Request(
            f'{SUPERVISOR_API}/addons/{slug}/{action}',
            data=b'{}', headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status == 200
    except Exception as e:
        log.error("Supervisor %s für '%s' fehlgeschlagen: %s", action, slug, e)
        return False


def _get_supervisor_stopped_addons() -> list[dict]:
    """HA entfernt gestoppte Add-on-Container aus Docker — Supervisor API liefert sie trotzdem."""
    import urllib.request
    token = _supervisor_token()
    if not token:
        log.debug("Supervisor-Token fehlt — gestoppte Add-ons nicht abfragbar")
        return []
    headers = {'Authorization': f'Bearer {token}'}
    try:
        req = urllib.request.Request(f'{SUPERVISOR_API}/addons', headers=headers)
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
        addons = data.get('data', {}).get('addons', [])
    except Exception as e:
        log.warning("Supervisor API /addons Fehler: %s", e)
        return []
    stopped = []
    for addon in addons:
        state = addon.get('state', 'unknown')
        if state == 'started':
            continue  # läuft — ist bereits im Docker-Ergebnis
        stopped.append({
            'id':        addon.get('slug', ''),
            'name':      addon.get('name', addon.get('slug', '')),
            'image':     'HA Add-on',
            'status':    state,
            'cpu_pct':   0.0, 'mem_usage': 0, 'mem_limit': 0, 'mem_pct': 0.0,
            'net_rx':    0,   'net_tx':    0,
            'blk_r':     0,   'blk_w':     0,
            'pids':      0,
            'ports_mapped': [],
        })
    if stopped and _verbose():
        log.info("Supervisor: %d gestoppte Add-on(s): %s",
                 len(stopped), ', '.join(a['name'] for a in stopped))
    return stopped


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

    ports_mapped = []
    _seen_ports: set = set()
    try:
        for cport, bindings in (container.ports or {}).items():
            if not bindings:
                continue
            parts     = cport.split('/')
            cport_num = parts[0]
            proto     = parts[1] if len(parts) > 1 else 'tcp'
            for b in bindings:
                hp  = b.get('HostPort', '')
                key = (hp, cport_num, proto)
                if hp and key not in _seen_ports:
                    _seen_ports.add(key)
                    ports_mapped.append({'host': hp, 'container': cport_num, 'proto': proto})
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
        'ports_mapped': ports_mapped,
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

                # Gestoppte HA Add-ons ergänzen (HA entfernt ihre Docker-Container)
                docker_names = {r['name'] for r in results}
                for addon in _get_supervisor_stopped_addons():
                    if addon['name'] not in docker_names:
                        results.append(addon)

                elapsed      = time.time() - t0
                _last_elapsed = elapsed
                running      = sum(1 for r in results if r['status'] == 'running')
                stopped_cnt  = len(results) - running
                if _verbose():
                    log.info("Abfrage: %d Container (%d laufend, %d gestoppt) | %d Worker | %.1fs",
                             len(results), running, stopped_cnt, workers, elapsed)
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


def _get_effective_chat_id() -> str:
    """Gibt konfigurierte oder automatisch erkannte Chat-ID zurück."""
    configured = str(load_config().get('telegram_chat_id', '')).strip()
    return configured or _auto_chat_id


def _telegram_api(method: str, http_timeout: int = 10, **kwargs) -> dict | None:
    """Generischer Telegram Bot-API Aufruf. Gibt JSON-Result zurück oder None bei Fehler."""
    cfg   = load_config()
    token = str(cfg.get('telegram_bot_token', '')).strip()
    if not token:
        return None
    import urllib.request
    try:
        payload = json.dumps(kwargs).encode()
        req = urllib.request.Request(
            f'https://api.telegram.org/bot{token}/{method}',
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=http_timeout) as resp:
            return json.loads(resp.read())
    except Exception as e:
        if method != 'getUpdates':  # getUpdates-Timeouts sind normal beim Long-Polling
            log.warning("[Telegram] %s fehlgeschlagen: %s", method, e)
        return None


def _fmt_bytes(n: float) -> str:
    for unit in ('B', 'KiB', 'MiB', 'GiB'):
        if n < 1024 or unit == 'GiB':
            return f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} GiB'


def _send_telegram(msg: str, reply_markup: dict | None = None) -> dict | None:
    """Sendet eine Telegram-Nachricht. Gibt {message_id, chat_id} zurück wenn reply_markup gesetzt."""
    chat_id = _get_effective_chat_id()
    if not chat_id:
        return None
    preview = msg.replace('\n', ' ').replace('<b>', '').replace('</b>', '').replace('<code>', '').replace('</code>', '')
    log.info("[Telegram] → %s", preview[:120])
    kwargs: dict = {'chat_id': chat_id, 'text': msg, 'parse_mode': 'HTML'}
    if reply_markup:
        kwargs['reply_markup'] = json.dumps(reply_markup)
    result = _telegram_api('sendMessage', **kwargs)
    if result and result.get('ok'):
        log.info("[Telegram] Gesendet.")
        if reply_markup:
            return {'message_id': result['result']['message_id'], 'chat_id': chat_id}
    elif result:
        log.warning("[Telegram] Fehlgeschlagen: %s", result.get('description', '?'))
    return None


def _edit_telegram_message(chat_id: str, message_id: int, text: str) -> None:
    """Bearbeitet eine existierende Telegram-Nachricht und entfernt alle Inline-Buttons."""
    _telegram_api('editMessageText',
                  chat_id=chat_id,
                  message_id=message_id,
                  text=text,
                  parse_mode='HTML',
                  reply_markup=json.dumps({'inline_keyboard': []}))


def _telegram_unexpected_stop_notif(name: str) -> None:
    """Sendet Stop-Benachrichtigung mit ▶ Starten-Button und speichert message_id."""
    keyboard = {'inline_keyboard': [[{'text': '▶ Starten', 'callback_data': f'start:{name}'}]]}
    result = _send_telegram(
        f'💥 <b>HA SysWatch</b> — Container unerwartet gestoppt\n<code>{name}</code>',
        reply_markup=keyboard,
    )
    if result:
        _pending_restart_msgs[name] = result


def _start_container_core(name: str) -> tuple[bool, str]:
    """Startet Container via Docker (Fallback: Supervisor). Gibt (ok, fehlermeldung) zurück."""
    socket_path = _find_docker_socket() if _docker_available else None
    if socket_path:
        try:
            client    = docker_lib.DockerClient(base_url=f'unix://{socket_path}')
            container = client.containers.get(name)
            container.start()
            log.info("Container gestartet: %s", name)
            _manually_started[name] = time.time()
            return True, ''
        except docker_lib.errors.NotFound:
            pass
        except Exception as e:
            log.error("Start-Fehler (Docker) für '%s': %s", name, e)
            return False, str(e)
    slug = _supervisor_addon_slug(name)
    if slug and _supervisor_action(slug, 'start'):
        log.info("Add-on gestartet (Supervisor): %s (slug=%s)", name, slug)
        _manually_started[name] = time.time()
        return True, ''
    return False, f'Container nicht gefunden: {name}'


def _handle_telegram_callback(cq: dict) -> None:
    """Verarbeitet Inline-Keyboard-Callbacks (▶ Starten)."""
    global _auto_chat_id
    cq_id      = cq['id']
    chat_id    = str(cq.get('from', {}).get('id', ''))
    data       = cq.get('data', '')
    message_id = cq.get('message', {}).get('message_id')

    allowed = _get_effective_chat_id()
    if allowed and chat_id != allowed:
        _telegram_api('answerCallbackQuery', callback_query_id=cq_id, text='❌ Nicht autorisiert')
        return

    if data.startswith('start:'):
        name = data[len('start:'):]
        _telegram_api('answerCallbackQuery', callback_query_id=cq_id,
                      text=f'▶ Starte {name}…', show_alert=False)
        ok, err = _start_container_core(name)
        new_text = (
            f'💥 <b>HA SysWatch</b> — Container gestoppt\n<code>{name}</code>\n\n'
            f'{"⏳ <i>Startbefehl gesendet…</i>" if ok else f"❌ <i>Start fehlgeschlagen: {err}</i>"}'
        )
        if message_id:
            threading.Thread(target=_edit_telegram_message,
                             args=(chat_id, message_id, new_text), daemon=True).start()


def _telegram_polling_loop() -> None:
    """Hintergrund-Thread: empfängt Telegram-Updates via Long-Polling und verarbeitet Callbacks."""
    global _auto_chat_id
    offset       = 0
    _was_active  = False
    while True:
        cfg   = load_config()
        token = str(cfg.get('telegram_bot_token', '')).strip()
        if not token:
            if _was_active:
                log.info("[Telegram] Bot-Token entfernt — Polling deaktiviert")
                _was_active = False
            time.sleep(15)
            continue
        if not _was_active:
            log.info("[Telegram] Polling aktiv (Token gesetzt)")
            _was_active = True

        result = _telegram_api('getUpdates', http_timeout=35,
                               offset=offset, timeout=30,
                               allowed_updates=['callback_query', 'message'])
        if not result:
            time.sleep(5)
            continue
        if not result.get('ok'):
            log.warning("[Telegram] getUpdates Fehler: %s", result.get('description'))
            time.sleep(10)
            continue
        for update in result.get('result', []):
            offset = update['update_id'] + 1

            # Chat-ID aus erster Nachricht oder Callback auto-lernen
            if not _auto_chat_id and not str(load_config().get('telegram_chat_id', '')).strip():
                src = (update.get('callback_query', {}).get('from')
                       or update.get('message', {}).get('from') or {})
                cid = str(src.get('id', ''))
                if cid:
                    _auto_chat_id = cid
                    log.info("[Telegram] Chat-ID automatisch erkannt: %s", cid)
                    _send_telegram(f'✅ <b>HA SysWatch</b> verbunden\nChat-ID <code>{cid}</code> erkannt — Benachrichtigungen aktiv.')

            if 'callback_query' in update:
                try:
                    _handle_telegram_callback(update['callback_query'])
                except Exception as e:
                    log.error("[Telegram] Callback-Fehler: %s", e)


def _check_container_changes() -> None:
    """Erkennt unerwartete Container-Stops und Starts, sendet Telegram-Benachrichtigung."""
    global _prev_running, _prev_running_init
    with _stats_lock:
        containers = _stats_cache.get('containers', [])
    current_running = {c['name'] for c in containers if c['status'] == 'running'}

    if not _prev_running_init:
        _prev_running_init = True
        _prev_running = current_running
        return

    now = time.time()

    # veraltete manuelle Einträge bereinigen
    for d in (_manually_stopped, _manually_started):
        for k in [k for k, ts in d.items() if now - ts > MANUAL_ACTION_TTL]:
            del d[k]

    newly_stopped = _prev_running - current_running
    newly_started = current_running - _prev_running

    for name in newly_stopped:
        if name in _manually_stopped:
            del _manually_stopped[name]   # manuell ausgelöst → keine Notification
        else:
            threading.Thread(target=_telegram_unexpected_stop_notif,
                             args=(name,), daemon=True).start()

    for name in newly_started:
        # Offene Stop-Nachricht mit ▶ Button → auf ✅ editieren (Button entfernen)
        has_pending = name in _pending_restart_msgs
        if has_pending:
            info = _pending_restart_msgs.pop(name)
            threading.Thread(target=_edit_telegram_message, daemon=True, args=(
                info['chat_id'], info['message_id'],
                f'✅ <b>HA SysWatch</b> — Container läuft wieder\n<code>{name}</code>',
            )).start()

        if name in _manually_started:
            del _manually_started[name]   # manuell ausgelöst → keine ▶️-Notification
        elif not has_pending:
            # Kein offener Stop-Alert → separates ▶️
            threading.Thread(target=_send_telegram, daemon=True, args=(
                f'▶️ <b>HA SysWatch</b> — Container gestartet\n<code>{name}</code>',
            )).start()

    _prev_running = current_running


def _check_thresholds() -> None:
    """Prüft CPU/RAM-Schwellenwerte mit konfigurierbarer Auslöse- und Entwarungsverzögerung."""
    global _notif_cpu_ts, _notif_ram_ts
    global _notif_cpu_above, _notif_ram_above
    global _notif_cpu_over_since, _notif_ram_over_since
    global _notif_cpu_ok_since, _notif_ram_ok_since
    now = time.time()
    cfg = load_config()
    cpu_limit   = int(cfg.get('notify_cpu_threshold',   0))
    ram_limit   = int(cfg.get('notify_ram_threshold',   0))
    if not cpu_limit and not ram_limit:
        return
    over_delay  = max(0, int(cfg.get('notify_over_duration',  0)))
    clear_delay = max(0, int(cfg.get('notify_clear_duration', 120)))
    with _stats_lock:
        si         = _stats_cache.get('sysinfo', {})
        containers = _stats_cache.get('containers', [])
    running = [c for c in containers if c.get('status') == 'running']
    cpu_pct = si.get('cpu_pct', 0.0)
    ram_pct = si.get('mem_pct', 0.0)

    def _top5_lines(sort_key: str, fmt) -> str:
        top = sorted(running, key=lambda c: c.get(sort_key, 0), reverse=True)[:5]
        return '\n'.join(f'  {i+1}. {c["name"]}: <b>{fmt(c)}</b>'
                         for i, c in enumerate(top))

    def _alert(metric: str, pct: float, limit: int) -> None:
        label = 'CPU-Last' if metric == 'cpu' else 'RAM-Auslastung'
        sym   = 'CPU'      if metric == 'cpu' else 'RAM'
        if metric == 'cpu':
            top5 = _top5_lines('cpu_pct', lambda c: f'{c.get("cpu_pct", 0):.1f}%')
        else:
            top5 = _top5_lines('mem_usage',
                               lambda c: f'{_fmt_bytes(c.get("mem_usage", 0))} ({c.get("mem_pct", 0):.1f}%)')
        threading.Thread(target=_send_telegram, daemon=True, args=(
            f'⚠️ <b>HA SysWatch</b> — Hohe {label}\n'
            f'System-{sym}: <b>{pct:.1f}%</b> (Schwellenwert: {limit}%, seit {over_delay}s)\n\n'
            f'<b>Top 5 {sym}:</b>\n{top5}',
        )).start()

    def _clear(metric: str, pct: float, limit: int) -> None:
        label = 'CPU-Last' if metric == 'cpu' else 'RAM-Auslastung'
        sym   = 'CPU'      if metric == 'cpu' else 'RAM'
        threading.Thread(target=_send_telegram, daemon=True, args=(
            f'✅ <b>HA SysWatch</b> — {label} normal\n'
            f'System-{sym}: <b>{pct:.1f}%</b> (unter {limit}% seit {clear_delay}s)',
        )).start()

    # CPU
    if cpu_limit:
        if cpu_pct >= cpu_limit:
            _notif_cpu_ok_since = 0.0
            if _notif_cpu_over_since == 0.0:
                _notif_cpu_over_since = now
            if (not _notif_cpu_above or now - _notif_cpu_ts > NOTIF_COOLDOWN) \
                    and now - _notif_cpu_over_since >= over_delay:
                _notif_cpu_above = True
                _notif_cpu_ts    = now
                _alert('cpu', cpu_pct, cpu_limit)
        else:
            _notif_cpu_over_since = 0.0
            if _notif_cpu_above:
                if _notif_cpu_ok_since == 0.0:
                    _notif_cpu_ok_since = now
                elif now - _notif_cpu_ok_since >= clear_delay:
                    _notif_cpu_above    = False
                    _notif_cpu_ok_since = 0.0
                    _clear('cpu', cpu_pct, cpu_limit)

    # RAM
    if ram_limit:
        if ram_pct >= ram_limit:
            _notif_ram_ok_since = 0.0
            if _notif_ram_over_since == 0.0:
                _notif_ram_over_since = now
            if (not _notif_ram_above or now - _notif_ram_ts > NOTIF_COOLDOWN) \
                    and now - _notif_ram_over_since >= over_delay:
                _notif_ram_above = True
                _notif_ram_ts    = now
                _alert('ram', ram_pct, ram_limit)
        else:
            _notif_ram_over_since = 0.0
            if _notif_ram_above:
                if _notif_ram_ok_since == 0.0:
                    _notif_ram_ok_since = now
                elif now - _notif_ram_ok_since >= clear_delay:
                    _notif_ram_above    = False
                    _notif_ram_ok_since = 0.0
                    _clear('ram', ram_pct, ram_limit)


def _init_history_db() -> None:
    """Erstellt die SQLite-Tabelle für den Systemverlauf, löscht Einträge > 24h."""
    with _db_lock:
        con = _sqlite3.connect(_DB_PATH, check_same_thread=False)
        con.execute('''CREATE TABLE IF NOT EXISTS sys_history (
            ts  INTEGER PRIMARY KEY,
            cpu REAL,
            ram REAL
        )''')
        cutoff = int(time.time()) - 86400
        con.execute('DELETE FROM sys_history WHERE ts < ?', (cutoff,))
        con.commit()
        con.close()
    log.info("History-DB initialisiert: %s", _DB_PATH)


def _flush_history_minute(ts_min: int, cpu_avg: float, ram_avg: float) -> None:
    """Schreibt einen Minuten-Durchschnitt in die DB und löscht Einträge > 24h."""
    cutoff = ts_min - 86400
    with _db_lock:
        try:
            con = _sqlite3.connect(_DB_PATH, check_same_thread=False)
            con.execute('INSERT OR REPLACE INTO sys_history (ts, cpu, ram) VALUES (?,?,?)',
                        (ts_min, round(cpu_avg, 1), round(ram_avg, 1)))
            con.execute('DELETE FROM sys_history WHERE ts < ?', (cutoff,))
            con.commit()
            con.close()
        except Exception as e:
            log.warning("History-DB Schreibfehler: %s", e)


def _tick_history(cpu_pct: float, ram_pct: float) -> None:
    """Akkumuliert CPU/RAM-Werte und flusht einmal pro Minute in die DB."""
    global _hist_last_min, _hist_cpu_acc, _hist_ram_acc
    _hist_cpu_acc.append(cpu_pct)
    _hist_ram_acc.append(ram_pct)
    cur_min = int(time.time() // 60) * 60
    if cur_min > _hist_last_min and _hist_cpu_acc:
        cpu_avg = sum(_hist_cpu_acc) / len(_hist_cpu_acc)
        ram_avg = sum(_hist_ram_acc) / len(_hist_ram_acc)
        _hist_last_min   = cur_min
        _hist_cpu_acc    = []
        _hist_ram_acc    = []
        threading.Thread(target=_flush_history_minute,
                         args=(cur_min, cpu_avg, ram_avg), daemon=True).start()


def _read_cpu_temp() -> float | None:
    """Liest CPU-Temperatur aus /sys/class/thermal/ (in °C)."""
    import glob
    preferred = ('cpu', 'x86', 'acpitz', 'soc', 'package', 'core')
    paths = sorted(glob.glob('/sys/class/thermal/thermal_zone*/temp'))
    # Bevorzuge CPU-nahe Zonen
    for path in paths:
        try:
            zone_type = open(path.replace('/temp', '/type')).read().strip().lower()
            if any(t in zone_type for t in preferred):
                temp = int(open(path).read().strip()) / 1000.0
                if 0 < temp < 150:
                    return temp
        except Exception:
            pass
    # Fallback: erste verfügbare Zone
    for path in paths:
        try:
            temp = int(open(path).read().strip()) / 1000.0
            if 0 < temp < 150:
                return temp
        except Exception:
            pass
    return None


def _read_fan_speeds() -> list[dict]:
    """Liest Lüfter-RPM aus /sys/class/hwmon/."""
    import glob
    fans = []
    for hwmon in sorted(glob.glob('/sys/class/hwmon/hwmon*')):
        for fan_in in sorted(glob.glob(f'{hwmon}/fan*_input')):
            try:
                rpm = int(open(fan_in).read().strip())
                idx = fan_in.split('fan')[1].split('_')[0]
                try:
                    label = open(fan_in.replace('_input', '_label')).read().strip()
                except Exception:
                    label = f'Fan {idx}'
                fans.append({'label': label, 'rpm': rpm})
            except Exception:
                pass
    return fans


def _update_hw_sensors() -> None:
    """Aktualisiert den HW-Sensor-Cache (CPU-Temp + Lüfter), max. alle 5s."""
    global _hw_cache, _hw_ts
    now = time.time()
    if now - _hw_ts < 5:
        return
    _hw_ts    = now
    _hw_cache = {'cpu_temp': _read_cpu_temp(), 'fans': _read_fan_speeds()}


_startup_notif_sent: bool = False


def _send_startup_notification() -> None:
    """Sendet einmalig beim ersten abgeschlossenen Zyklus eine Startup-Meldung an Telegram."""
    global _startup_notif_sent
    if _startup_notif_sent:
        return
    _startup_notif_sent = True

    import datetime as _dt
    now_str = _dt.datetime.now().strftime('%d.%m.%Y %H:%M:%S')
    ha = _get_ha_status()
    with _stats_lock:
        containers = _stats_cache.get('containers', [])
    running = sum(1 for c in containers if c.get('status') == 'running')
    total   = len(containers)

    parts = [f'🟢 <b>HA SysWatch gestartet</b>', f'📅 {now_str}']
    if ha.get('core_version'):
        parts.append(f'🏠 HA {ha["core_version"]}  ·  Supervisor {ha.get("supervisor_version", "?")}  ·  OS {ha.get("os_version", "?")}')
    parts.append(f'🐳 {running} Container laufend / {total} gesamt')
    if ha.get('host_ip'):
        parts.append(f'🌐 {ha["host_ip"]}')

    threading.Thread(target=_send_telegram, args=('\n'.join(parts),), daemon=True).start()


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
                _check_container_changes()
                _check_thresholds()
                _update_hw_sensors()
                with _stats_lock:
                    _si = _stats_cache.get('sysinfo', {})
                _tick_history(_si.get('cpu_pct', 0.0), _si.get('mem_pct', 0.0))
                _send_startup_notification()
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
    cfg  = load_config()
    return render_template('index.html', t=t, lang=lang,
                           show_stopped=cfg.get('show_stopped', False))


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


@app.route('/api/sysinfo/history')
def api_sysinfo_history():
    if not is_valid_session(request.cookies.get('sw_session')):
        return '', 401
    try:
        with _db_lock:
            con  = _sqlite3.connect(_DB_PATH, check_same_thread=False)
            rows = con.execute(
                'SELECT ts, cpu, ram FROM sys_history ORDER BY ts'
            ).fetchall()
            con.close()
        data = [{'ts': r[0], 'c': r[1], 'r': r[2]} for r in rows]
    except Exception as e:
        log.warning("History-DB Lesefehler: %s", e)
        data = []
    return jsonify({'data': data})


@app.route('/api/test/telegram', methods=['POST'])
def api_test_telegram():
    if not is_valid_session(request.cookies.get('sw_session')):
        return '', 401
    with _stats_lock:
        si         = _stats_cache.get('sysinfo', {})
        containers = _stats_cache.get('containers', [])
    running = [c for c in containers if c.get('status') == 'running']
    cpu_top = sorted(running, key=lambda c: c.get('cpu_pct', 0), reverse=True)[:5]
    ram_top = sorted(running, key=lambda c: c.get('mem_usage', 0), reverse=True)[:5]
    cpu_lines = '\n'.join(f'  {i+1}. {c["name"]}: <b>{c.get("cpu_pct", 0):.1f}%</b>'
                          for i, c in enumerate(cpu_top))
    ram_lines = '\n'.join(
        f'  {i+1}. {c["name"]}: <b>{_fmt_bytes(c.get("mem_usage", 0))} ({c.get("mem_pct", 0):.1f}%)</b>'
        for i, c in enumerate(ram_top))
    msg = (
        f'🧪 <b>HA SysWatch</b> — Test-Benachrichtigung\n'
        f'System-CPU: <b>{si.get("cpu_pct", 0):.1f}%</b>  |  RAM: <b>{si.get("mem_pct", 0):.1f}%</b>\n\n'
        f'<b>Top 5 CPU:</b>\n{cpu_lines}\n\n'
        f'<b>Top 5 RAM:</b>\n{ram_lines}'
    )
    threading.Thread(target=_send_telegram, args=(msg,), daemon=True).start()
    return jsonify({'ok': True})


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
    data['ha_status']      = _get_ha_status()
    data['cpu_temp']       = _hw_cache.get('cpu_temp')
    data['fans']           = _hw_cache.get('fans', [])
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
        _manually_stopped[name] = time.time()
        return jsonify({'ok': True})
    except Exception as e:
        log.error("Kill-Fehler für '%s': %s", name, e)
        return jsonify({'error': str(e)}), 500


@app.route('/api/container/<name>/start', methods=['POST'])
def api_start(name: str):
    if not is_valid_session(request.cookies.get('sw_session')):
        return '', 401
    body   = request.get_json(silent=True) or {}
    config = load_config()
    if body.get('password', '') != config.get('password', ''):
        log.warning("Start abgelehnt (falsches Passwort): container='%s'", name)
        return jsonify({'error': 'wrong_password'}), 403
    ok, err = _start_container_core(name)
    if ok:
        return jsonify({'ok': True})
    return jsonify({'error': err}), (404 if 'nicht gefunden' in err else 500)


@app.route('/api/container/<name>/stop', methods=['POST'])
def api_stop(name: str):
    if not is_valid_session(request.cookies.get('sw_session')):
        return '', 401
    body   = request.get_json(silent=True) or {}
    config = load_config()
    if body.get('password', '') != config.get('password', ''):
        log.warning("Stop abgelehnt (falsches Passwort): container='%s'", name)
        return jsonify({'error': 'wrong_password'}), 403
    socket_path = _find_docker_socket() if _docker_available else None
    if not socket_path:
        return jsonify({'error': 'Docker-Socket nicht verfügbar'}), 503
    try:
        client    = docker_lib.DockerClient(base_url=f'unix://{socket_path}')
        container = client.containers.get(name)
        container.stop(timeout=10)
        log.info("Container gestoppt: %s", name)
        _manually_stopped[name] = time.time()
        return jsonify({'ok': True})
    except Exception as e:
        log.error("Stop-Fehler für '%s': %s", name, e)
        return jsonify({'error': str(e)}), 500


# ── Startup ────────────────────────────────────────────────────────────────────

def _log_startup() -> None:
    cfg = load_config()
    log.info("=" * 55)
    log.info("  HA SysWatch startet auf Port 17790")
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
_init_history_db()
threading.Thread(target=_background_collector,   daemon=True, name='docker-collector').start()
threading.Thread(target=_telegram_polling_loop, daemon=True, name='telegram-polling').start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=17790, debug=False)
