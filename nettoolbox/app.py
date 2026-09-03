#!/usr/bin/env python3
"""NetToolbox — network and mail diagnostics for Home Assistant.

Behind the Home Assistant Ingress proxy the Supervisor has already
authenticated the user, so no login is asked for. On the direct port the add-on
authenticates on its own. The same image also serves as a worker: give it a
token and it answers probe requests from another instance.
"""

import functools
import json
import logging
import os
import secrets
import signal
import threading
import time
from collections import defaultdict, deque
from urllib.parse import urlsplit, urlunsplit

from flask import (Flask, g, jsonify, make_response, redirect,
                   render_template, request, url_for)
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

import probes
from netcore import Context, ProbeError
from remote import TOKEN_HEADER, LocalBackend, RemoteBackend

logging.basicConfig(format='[%(levelname)s] [%(asctime)s] %(message)s',
                    level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S', force=True)
log = logging.getLogger(__name__)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# ── Paths ─────────────────────────────────────────────────────────────────────

_BASE = os.environ.get('NETTOOLBOX_BASE', '/app')
_DATA = os.environ.get('NETTOOLBOX_DATA', '/data')
_OPTS = os.environ.get('NETTOOLBOX_OPTIONS', '/data')

CONFIG_PATH = _OPTS + '/options.json'
SESSIONS_PATH = _DATA + '/sessions.json'
SECRET_PATH = _DATA + '/secret.key'
HISTORY_PATH = _DATA + '/history.json'
LOCALES_PATH = _BASE + '/locales'

PORT = int(os.environ.get('NETTOOLBOX_PORT', '17798'))
SUPERVISOR_TOKEN = os.environ.get('SUPERVISOR_TOKEN', '')

app = Flask(__name__, template_folder=_BASE + '/templates',
            static_folder=_BASE + '/static')
app.config['MAX_CONTENT_LENGTH'] = 256 * 1024


class _IngressMiddleware:
    """Reads the Supervisor's X-Ingress-Path and sets WSGI SCRIPT_NAME so that
    url_for() produces correct URLs behind the Ingress proxy."""

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


app.wsgi_app = _IngressMiddleware(ProxyFix(app.wsgi_app, x_for=1, x_proto=1,
                                           x_host=1))

# ── Configuration ─────────────────────────────────────────────────────────────

_config_cache: dict = {}
_config_mtime: float = 0.0


# Standalone (no Supervisor) has nothing that writes options.json from the
# config.yaml schema the way the Supervisor does — without this, the direct
# port would have no username/password and login could never succeed.
_STANDALONE_DEFAULTS = {
    'username': 'admin',
    'session_hours': 24,
    'worker_url': '', 'worker_token': '', 'worker_tls_verify': True,
    'worker_enabled': False,
    'resolvers': ['9.9.9.9', '1.1.1.1', '8.8.8.8'],
    'dns_timeout': 5, 'http_timeout': 10,
    'allow_private_targets': False,
    'rate_limit_per_min': 60, 'history_size': 200, 'verbose_log': False,
}


def _bootstrap_options() -> None:
    if SUPERVISOR_TOKEN or os.path.exists(CONFIG_PATH):
        return
    password = secrets.token_urlsafe(9)
    options = dict(_STANDALONE_DEFAULTS, password=password)
    try:
        os.makedirs(_OPTS, exist_ok=True)
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(options, f, indent=2)
    except OSError:
        log.error("could not write %s — direct-port login stays unusable", CONFIG_PATH)
        return
    log.info("no options.json found — created one with username 'admin' and "
             "password '%s'. Change it in %s.", password, CONFIG_PATH)


def load_config() -> dict:
    global _config_cache, _config_mtime
    try:
        mtime = os.path.getmtime(CONFIG_PATH)
        if mtime != _config_mtime:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                _config_cache = json.load(f)
            _config_mtime = mtime
    except Exception:
        pass
    return _config_cache or {}


def _cfg_int(key: str, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(int(load_config().get(key, default)), high))
    except (TypeError, ValueError):
        return default


def _cfg_str(key: str) -> str:
    return str(load_config().get(key) or '').strip()


def _verbose() -> bool:
    return bool(load_config().get('verbose_log'))


def _load_or_create_secret_key() -> str:
    try:
        with open(SECRET_PATH, 'r', encoding='utf-8') as f:
            key = f.read().strip()
        if key:
            return key
    except FileNotFoundError:
        pass
    except Exception:
        log.warning("secret.key could not be read — generating a new one")
    key = secrets.token_hex(32)
    try:
        os.makedirs(os.path.dirname(SECRET_PATH), exist_ok=True)
        fd = os.open(SECRET_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(key)
    except Exception:
        log.warning("secret.key could not be written — sessions reset on restart")
    return key


app.config['SECRET_KEY'] = _load_or_create_secret_key()


def _serializer(salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(str(app.config['SECRET_KEY']), salt=salt)


def build_context() -> Context:
    cfg = load_config()
    resolvers = cfg.get('resolvers') or ['9.9.9.9', '1.1.1.1']
    if isinstance(resolvers, str):
        resolvers = [r for r in resolvers.replace(',', ' ').split() if r]
    return Context(
        resolvers=[str(r).strip() for r in resolvers if str(r).strip()][:8],
        dns_timeout=float(_cfg_int('dns_timeout', 5, 1, 60)),
        http_timeout=float(_cfg_int('http_timeout', 10, 1, 120)),
        allow_private=bool(cfg.get('allow_private_targets')),
        user_agent='NetToolbox/' + (APP_VERSION or '0'))


# ── Sessions ──────────────────────────────────────────────────────────────────

sessions: dict = {}
_sessions_lock = threading.Lock()


def save_sessions() -> None:
    try:
        now = time.time()
        with open(SESSIONS_PATH, 'w', encoding='utf-8') as f:
            json.dump({k: v for k, v in sessions.items() if v > now}, f)
    except Exception:
        log.warning("sessions could not be saved")


def load_sessions() -> None:
    global sessions
    try:
        with open(SESSIONS_PATH, encoding='utf-8') as f:
            data = json.load(f)
        now = time.time()
        sessions = {k: v for k, v in data.items() if v > now}
        if sessions:
            log.info("sessions restored: %d active", len(sessions))
    except FileNotFoundError:
        pass
    except Exception:
        log.warning("sessions could not be loaded")


def create_session(hours: int) -> str:
    token = secrets.token_hex(32)
    with _sessions_lock:
        sessions[token] = time.time() + hours * 3600
        save_sessions()
    return token


def is_valid_session(token) -> bool:
    if not token or token not in sessions:
        return False
    if time.time() > sessions[token]:
        with _sessions_lock:
            sessions.pop(token, None)
        return False
    return True


# ── Rate limiting ─────────────────────────────────────────────────────────────

RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW = 600
RATE_LIMIT_BLOCK = 900

_failed_attempts: dict = defaultdict(list)
_blocked_ips: dict = {}


def get_client_ip(req) -> str:
    return req.remote_addr or 'unknown'


def is_rate_limited(ip: str) -> bool:
    now = time.time()
    if ip in _blocked_ips:
        if now < _blocked_ips[ip]:
            return True
        del _blocked_ips[ip]
    _failed_attempts[ip] = [t for t in _failed_attempts[ip]
                            if now - t < RATE_LIMIT_WINDOW]
    return False


def record_failed_attempt(ip: str) -> None:
    now = time.time()
    recent = [t for t in _failed_attempts[ip] if now - t < RATE_LIMIT_WINDOW]
    recent.append(now)
    _failed_attempts[ip] = recent
    if len(recent) >= RATE_LIMIT_MAX:
        _blocked_ips[ip] = now + RATE_LIMIT_BLOCK
        log.warning("login blocked for %d minutes after too many failures",
                    RATE_LIMIT_BLOCK // 60)


def clear_failed_attempts(ip: str) -> None:
    _failed_attempts.pop(ip, None)
    _blocked_ips.pop(ip, None)


# Probes cost other people's DNS servers, so the number per minute is capped
# no matter who is asking.
_probe_times: deque = deque()
_probe_lock = threading.Lock()


def probe_budget_left() -> bool:
    limit = _cfg_int('rate_limit_per_min', 60, 0, 6000)
    if limit <= 0:
        return True
    now = time.time()
    with _probe_lock:
        while _probe_times and now - _probe_times[0] > 60:
            _probe_times.popleft()
        if len(_probe_times) >= limit:
            return False
        _probe_times.append(now)
    return True


# ── i18n ──────────────────────────────────────────────────────────────────────


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
    accept = (req.headers.get('Accept-Language') or '').lower()
    return 'de' if accept.startswith('de') else 'en'


def _safe_next(raw: str) -> str:
    """Only local paths may be redirect targets (open-redirect protection).

    Behind Ingress the add-on lives under a proxy prefix, so the prefix is put
    back on — a bare "/" would load Home Assistant inside its own frame.
    """
    root = request.script_root or ''
    nxt = (raw or '/').replace('\\', '')
    parts = urlsplit(nxt)
    if parts.scheme or parts.netloc or not nxt.startswith('/'):
        return (root + '/') if root else '/'
    path = parts.path or '/'
    if root and path != root and not path.startswith(root + '/'):
        path = root + path
    return urlunsplit(('', '', path, parts.query, parts.fragment))


# ── Auth / CSRF ───────────────────────────────────────────────────────────────

CSRF_TTL = 12 * 3600


def _is_ingress() -> bool:
    return bool(request.script_root)


def _logged_in() -> bool:
    return _is_ingress() or is_valid_session(request.cookies.get('session'))


@app.before_request
def _csrf_prepare():
    raw = ''
    cookie = request.cookies.get('csrf')
    if cookie:
        try:
            raw = _serializer('csrf').loads(cookie, max_age=CSRF_TTL)
        except (BadSignature, SignatureExpired):
            raw = ''
    g.csrf_new = not raw
    g.csrf = raw or secrets.token_hex(16)


@app.after_request
def _csrf_emit(resp):
    if getattr(g, 'csrf_new', False):
        resp.set_cookie('csrf', _serializer('csrf').dumps(g.csrf),
                        httponly=True, samesite='Lax', max_age=CSRF_TTL)
    return resp


def _origin_ok() -> bool:
    """Reject cross-site posts. Ingress and direct port both report the
    browser-visible host here, so a same-host comparison holds in both."""
    host = request.host or ''
    for header in ('Origin', 'Referer'):
        value = request.headers.get(header) or ''
        if value:
            return urlsplit(value).netloc == host
    return True


def _csrf_ok() -> bool:
    sent = request.headers.get('X-CSRF-Token', '') or request.form.get('_csrf', '')
    return bool(sent) and secrets.compare_digest(sent, getattr(g, 'csrf', ''))


_ERROR_STATUS = {
    'unknown_probe': 400, 'bad_params': 400, 'bad_param': 400,
    'empty_target': 400, 'bad_target': 400, 'target_too_long': 400,
    'bad_ip': 400, 'bad_selector': 400, 'bad_rrtype': 400, 'bad_url': 400,
    'too_many_values': 400, 'private_target': 403,
    'nxdomain': 404, 'no_records': 404,
    'dns_timeout': 504, 'http_timeout': 504, 'worker_timeout': 504,
    'worker_auth': 502, 'worker_unreachable': 502, 'worker_tls': 502,
    'worker_bad_response': 502, 'worker_error': 502,
}


def api(rule: str, methods=('GET',)):
    """Route decorator: auth, CSRF and uniform error mapping in one place."""
    def deco(fn):
        @app.route(rule, methods=list(methods), endpoint='api_' + fn.__name__)
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if not _logged_in():
                return jsonify({'error': 'unauthorized'}), 401
            if request.method not in ('GET', 'HEAD'):
                if not _origin_ok() or not _csrf_ok():
                    return jsonify({'error': 'csrf'}), 403
            try:
                return fn(*args, **kwargs)
            except ProbeError as e:
                return (jsonify({'error': e.code, 'detail': e.detail}),
                        _ERROR_STATUS.get(e.code, 502))
            except Exception:
                log.exception("unhandled error in %s", rule)
                return jsonify({'error': 'internal'}), 500
        return wrapper
    return deco


# ── Backend selection ─────────────────────────────────────────────────────────

_remote = None
_remote_lock = threading.Lock()


def get_backend():
    """Remote when a worker is configured, local otherwise."""
    global _remote
    url = _cfg_str('worker_url')
    token = str(load_config().get('worker_token') or '')
    verify = bool(load_config().get('worker_tls_verify', True))
    if not url or not token:
        return LocalBackend(build_context())
    with _remote_lock:
        if _remote is None or not _remote.same_as(url, token, verify):
            _remote = RemoteBackend(url, token, verify)
            if _verbose():
                log.info("probe worker set to %s", url)
        return _remote


# ── History ───────────────────────────────────────────────────────────────────

_history: deque = deque(maxlen=500)
_history_lock = threading.Lock()


def _history_limit() -> int:
    return _cfg_int('history_size', 200, 0, 5000)


def history_add(entry: dict) -> None:
    if _history_limit() <= 0:
        return
    with _history_lock:
        _history.appendleft(entry)
        while len(_history) > _history_limit():
            _history.pop()
        rows = list(_history)
    try:
        with open(HISTORY_PATH, 'w', encoding='utf-8') as f:
            json.dump(rows, f)
    except Exception:
        log.warning("history could not be saved")


def history_load() -> None:
    try:
        with open(HISTORY_PATH, encoding='utf-8') as f:
            rows = json.load(f)
        if isinstance(rows, list):
            with _history_lock:
                _history.extend(rows[:500])
    except FileNotFoundError:
        pass
    except Exception:
        log.warning("history could not be loaded")


# ── Version ───────────────────────────────────────────────────────────────────


def _own_version() -> str:
    try:
        with open(_BASE + '/config.yaml', encoding='utf-8') as f:
            for line in f:
                if line.startswith('version:'):
                    return line.split(':', 1)[1].strip().strip('"\'')
    except OSError:
        pass
    return ''


APP_VERSION = _own_version()


# ── Worker endpoints ──────────────────────────────────────────────────────────
# The other half of the split: this instance doing the work for someone else.


def worker_enabled() -> bool:
    cfg = load_config()
    return bool(cfg.get('worker_enabled')) and bool(str(cfg.get('worker_token') or ''))


def _worker_token_ok() -> bool:
    sent = request.headers.get(TOKEN_HEADER, '')
    expected = str(load_config().get('worker_token') or '')
    return bool(sent) and bool(expected) and secrets.compare_digest(sent, expected)


def worker_route(rule: str):
    def deco(fn):
        @app.route(rule, methods=['POST'], endpoint='worker_' + fn.__name__)
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if not worker_enabled():
                return jsonify({'ok': False, 'error': 'worker_disabled'}), 403
            if not _worker_token_ok():
                # Deliberately vague: a wrong token learns nothing from this.
                return jsonify({'ok': False, 'error': 'unauthorized'}), 401
            try:
                return fn(*args, **kwargs)
            except ProbeError as e:
                return jsonify({'ok': False, 'error': e.code,
                                'detail': e.detail}), 200
            except Exception:
                log.exception("worker error in %s", rule)
                return jsonify({'ok': False, 'error': 'internal'}), 500
        return wrapper
    return deco


@worker_route('/worker/info')
def worker_info():
    return jsonify({'ok': True, 'worker': {
        'version': APP_VERSION,
        'probes': sorted(probes.PROBES),
        'allow_private': bool(load_config().get('allow_private_targets')),
    }})


@worker_route('/worker/probe')
def worker_probe():
    if not probe_budget_left():
        return jsonify({'ok': False, 'error': 'rate_limited'}), 200
    body = request.get_json(silent=True) or {}
    name = str(body.get('probe') or '')
    params = body.get('params') or {}
    if not isinstance(params, dict):
        raise ProbeError('bad_params')
    started = time.monotonic()
    result = probes.run(name, params, build_context())
    return jsonify({'ok': True, 'result': result, 'worker': {
        'version': APP_VERSION,
        'ms': int((time.monotonic() - started) * 1000)}})


# ── Pages ─────────────────────────────────────────────────────────────────────


@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'version': APP_VERSION})


@app.route('/manifest.json')
def manifest():
    t = load_translations(detect_language(request))
    resp = jsonify({
        'name': t.get('app_title', 'NetToolbox'),
        'short_name': t.get('app_title', 'NetToolbox'),
        'start_url': (request.script_root or '') + '/',
        'scope': (request.script_root or '') + '/',
        'display': 'standalone',
        'background_color': '#0d1117',
        'theme_color': '#0d1117',
        'icons': [
            {'src': url_for('static', filename='icon-192.png'),
             'sizes': '192x192', 'type': 'image/png'},
            {'src': url_for('static', filename='icon-512.png'),
             'sizes': '512x512', 'type': 'image/png'},
        ],
    })
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.route('/set-lang/<lang>')
def set_lang(lang: str):
    lang = lang if lang in ('de', 'en') else 'en'
    resp = make_response(redirect(_safe_next(request.args.get('next', '/'))))
    resp.set_cookie('lang', lang, max_age=365 * 24 * 3600, samesite='Lax')
    return resp


@app.route('/login', methods=['GET', 'POST'])
def login():
    lang = detect_language(request)
    t = load_translations(lang)
    if _is_ingress():
        return redirect(_safe_next('/'))
    error = ''
    if request.method == 'POST':
        ip = get_client_ip(request)
        if is_rate_limited(ip):
            error = t.get('error_locked', 'Too many attempts.')
        elif not _origin_ok() or not _csrf_ok():
            error = t.get('error_expired', 'Form expired.')
        else:
            cfg = load_config()
            user_ok = secrets.compare_digest(
                request.form.get('username', ''), str(cfg.get('username') or ''))
            # Hash both sides so a wrong user name costs the same time as a
            # wrong password.
            stored = generate_password_hash(str(cfg.get('password') or ''))
            pass_ok = check_password_hash(stored, request.form.get('password', ''))
            if user_ok and pass_ok:
                clear_failed_attempts(ip)
                hours = _cfg_int('session_hours', 24, 1, 720)
                resp = make_response(redirect(_safe_next('/')))
                resp.set_cookie('session', create_session(hours),
                                httponly=True, samesite='Lax',
                                secure=request.is_secure, max_age=hours * 3600)
                return resp
            record_failed_attempt(ip)
            error = t.get('error_credentials', 'Invalid credentials.')
    return render_template('login.html', t=t, lang=lang, csrf=g.csrf,
                           error=error)


@app.route('/logout')
def logout():
    token = request.cookies.get('session')
    if token:
        with _sessions_lock:
            sessions.pop(token, None)
            save_sessions()
    resp = make_response(redirect(_safe_next('/login')))
    resp.delete_cookie('session')
    return resp


@app.route('/')
def index():
    if not _logged_in():
        return redirect(url_for('login'))
    lang = detect_language(request)
    return render_template(
        'index.html', t=load_translations(lang), lang=lang, csrf=g.csrf,
        version=APP_VERSION, ingress=_is_ingress(),
        probe_names=sorted(probes.PROBES),
        target_kind=probes.TARGET_KIND,
        rr_types=list(probes.COMMON_TYPES) + ['CNAME', 'PTR', 'SRV', 'DS',
                                              'DNSKEY', 'TLSA', 'NAPTR'],
        resolvers=[{'label': label, 'server': server}
                   for label, server in probes.PUBLIC_RESOLVERS])


# ── API ───────────────────────────────────────────────────────────────────────


@api('/api/status')
def status():
    backend = get_backend()
    state = backend.ping()
    return jsonify({
        'version': APP_VERSION,
        'ingress': _is_ingress(),
        'backend': state,
        'worker_enabled': worker_enabled(),
        'allow_private': bool(load_config().get('allow_private_targets')),
        'resolvers': build_context().resolvers,
    })


@api('/api/probe', methods=('POST',))
def probe():
    if not probe_budget_left():
        return jsonify({'error': 'rate_limited'}), 429
    body = request.get_json(silent=True) or {}
    name = str(body.get('probe') or '')
    if name not in probes.PROBES:
        raise ProbeError('unknown_probe', name[:40])
    params = body.get('params') or {}
    if not isinstance(params, dict):
        raise ProbeError('bad_params')
    answer = get_backend().run(name, params)
    result = answer.get('result') or {}
    history_add({
        'ts': int(time.time()),
        'probe': name,
        'target': str(params.get('domain') or params.get('name')
                      or params.get('ip') or '')[:253],
        'level': result.get('level', ''),
        'backend': answer.get('backend', 'local'),
        'ms': answer.get('ms', 0),
    })
    return jsonify({'probe': name, 'result': result,
                    'backend': answer.get('backend', 'local'),
                    'worker': answer.get('worker') or {},
                    'ms': answer.get('ms', 0)})


@api('/api/history')
def history():
    with _history_lock:
        return jsonify({'rows': list(_history)[:_history_limit()]})


@api('/api/history/clear', methods=('POST',))
def history_clear():
    with _history_lock:
        _history.clear()
    try:
        os.remove(HISTORY_PATH)
    except OSError:
        pass
    return jsonify({'ok': True})


# ── Startup ───────────────────────────────────────────────────────────────────


def _startup_checks() -> None:
    cfg = load_config()
    if str(cfg.get('password') or '') == 'changeme123' and not SUPERVISOR_TOKEN:
        log.warning("the default password is still set — change it in the "
                    "add-on options before opening the direct port")
    if cfg.get('allow_private_targets'):
        log.warning("allow_private_targets is on — this instance will probe "
                    "addresses inside your own network on request")
    if worker_enabled():
        log.info("worker mode active — /worker/probe accepts token requests")
    url = _cfg_str('worker_url')
    if url:
        if not str(cfg.get('worker_token') or ''):
            log.warning("worker_url is set but worker_token is empty — probes "
                        "stay local")
        else:
            state = get_backend().ping()
            if state.get('ok'):
                log.info("probe worker reachable at %s (%d ms)", url,
                         state.get('ms', 0))
            else:
                log.warning("probe worker not usable yet: %s",
                            state.get('error'))


if __name__ == '__main__':
    _bootstrap_options()
    load_sessions()
    history_load()
    _startup_checks()

    def _shutdown(signum, frame):
        log.info("signal %s received — NetToolbox is shutting down", signum)
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    log.info("NetToolbox %s ready on port %d", APP_VERSION or '?', PORT)
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
