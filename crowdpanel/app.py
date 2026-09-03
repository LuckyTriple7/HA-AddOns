#!/usr/bin/env python3
"""CrowdPanel — web front-end for a CrowdSec Local API.

Behind the Home Assistant Ingress proxy the Supervisor has already
authenticated the user, so no login is asked for. On the direct port the
add-on authenticates on its own: username, password and optional TOTP.
"""

import base64
import functools
import hashlib
import hmac
import io
import json
import logging
import os
import re
import secrets
import signal
import threading
import time
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, quote

from flask import (Flask, g, jsonify, make_response, redirect, render_template,
                   request, url_for)
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

import requests as http

from lapi import (ALERT_FETCH_LIMIT, DECISION_TYPES, DURATION_PRESETS, SCOPES,
                  LapiClient, LapiError, ValidationError, is_ip_or_range,
                  normalize_duration, normalize_scope, normalize_type,
                  normalize_value)
from metrics import MetricsClient, DEFAULT_PORT as PROMETHEUS_PORT
from archive import Archive

logging.basicConfig(format='[%(levelname)s] [%(asctime)s] %(message)s',
                    level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S', force=True)
log = logging.getLogger(__name__)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

try:
    import qrcode
    import qrcode.image.svg as qrsvg
    _HAS_QR = True
except ImportError:  # optional — without it the secret is shown as text
    _HAS_QR = False

# ── Paths ─────────────────────────────────────────────────────────────────────

_BASE = os.environ.get('CROWDPANEL_BASE', '/app')
_DATA = os.environ.get('CROWDPANEL_DATA', '/data')
_OPTS = os.environ.get('CROWDPANEL_OPTIONS', '/data')

CONFIG_PATH = _OPTS + '/options.json'
SESSIONS_PATH = _DATA + '/sessions.json'
TWOFA_PATH = _DATA + '/twofa.json'
SECRET_PATH = _DATA + '/secret.key'
ARCHIVE_PATH = _DATA + '/alerts.db'
LOCALES_PATH = _BASE + '/locales'

PORT = 17797

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


def _cfg_float(key: str, low: float, high: float) -> float | None:
    """Optionale Zahlenoption. Leer oder unbrauchbar heisst 'nicht gesetzt' —
    das ist etwas anderes als 0, denn 0/0 ist eine echte Koordinate."""
    raw = load_config().get(key)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value != value or value < low or value > high:
        return None
    return value


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
    _failed_attempts[ip] = [t for t in _failed_attempts[ip] if now - t < RATE_LIMIT_WINDOW]
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


# ── TOTP (RFC 6238, standard library only) ────────────────────────────────────
# Only relevant on the direct port; behind Ingress HA does the authentication.

TOTP_STEP = 30
TOTP_DIGITS = 6
TOTP_WINDOW = 1
BACKUP_CODE_COUNT = 10
PENDING_2FA_TTL = 300
TRUSTED_DEVICE_DAYS = 30
TOTP_ISSUER = 'CrowdPanel'

_pending_2fa: dict = {}
_2fa_lock = threading.Lock()


def load_2fa() -> dict:
    with _2fa_lock:
        try:
            with open(TWOFA_PATH, encoding='utf-8') as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception:
            # Security relevant: an unreadable file means 2FA counts as off.
            log.warning("twofa.json is unreadable — two-factor treated as disabled")
            return {}


def save_2fa(data: dict) -> None:
    with _2fa_lock:
        try:
            tmp = TWOFA_PATH + '.tmp'
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, TWOFA_PATH)
        except Exception:
            log.warning("twofa.json could not be saved")


def twofa_enabled() -> bool:
    d = load_2fa()
    return bool(d.get('enabled') and d.get('secret'))


def _new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode('ascii').rstrip('=')


def _totp_at(secret_b32: str, t: float) -> str:
    key = base64.b32decode(secret_b32 + '=' * (-len(secret_b32) % 8), casefold=True)
    counter = int(t // TOTP_STEP).to_bytes(8, 'big')
    h = hmac.new(key, counter, hashlib.sha1).digest()
    o = h[-1] & 0x0F
    num = int.from_bytes(h[o:o + 4], 'big') & 0x7FFFFFFF
    return str(num % (10 ** TOTP_DIGITS)).zfill(TOTP_DIGITS)


def totp_verify(secret_b32: str, code: str) -> bool:
    code = (code or '').strip().replace(' ', '')
    if not (secret_b32 and code.isdigit() and len(code) == TOTP_DIGITS):
        return False
    now = time.time()
    for w in range(-TOTP_WINDOW, TOTP_WINDOW + 1):
        if secrets.compare_digest(_totp_at(secret_b32, now + w * TOTP_STEP), code):
            return True
    return False


def _otpauth_uri(secret_b32: str, account: str) -> str:
    label = quote(f'{TOTP_ISSUER}:{account}')
    return (f'otpauth://totp/{label}?secret={secret_b32}'
            f'&issuer={quote(TOTP_ISSUER)}&digits={TOTP_DIGITS}&period={TOTP_STEP}')


def _qr_svg(data: str) -> str:
    """QR code as inline SVG — generated locally, the secret never leaves here."""
    if not _HAS_QR:
        return ''
    try:
        img = qrcode.make(data, image_factory=qrsvg.SvgPathImage, box_size=9, border=2)
        buf = io.BytesIO()
        img.save(buf)
        return buf.getvalue().decode('utf-8')
    except Exception:
        log.warning("QR code could not be generated")
        return ''


def _gen_backup_codes() -> tuple[list, list]:
    plain = ['-'.join(secrets.token_hex(2) for _ in range(2))
             for _ in range(BACKUP_CODE_COUNT)]
    return plain, [generate_password_hash(c) for c in plain]


def backup_code_consume(code: str) -> bool:
    code = (code or '').strip().lower()
    if not code:
        return False
    d = load_2fa()
    hashes = d.get('backup') or []
    for i, h in enumerate(hashes):
        if check_password_hash(h, code):
            hashes.pop(i)
            d['backup'] = hashes
            save_2fa(d)
            return True
    return False


def _pending_2fa_new() -> str:
    now = time.time()
    for k in [k for k, exp in _pending_2fa.items() if exp < now]:
        _pending_2fa.pop(k, None)
    token = secrets.token_hex(32)
    _pending_2fa[token] = now + PENDING_2FA_TTL
    return token


def _pending_2fa_valid(token) -> bool:
    if not token or token not in _pending_2fa:
        return False
    if time.time() > _pending_2fa[token]:
        _pending_2fa.pop(token, None)
        return False
    return True


def _trusted_prune(entries: dict) -> dict:
    now = time.time()
    return {k: v for k, v in (entries or {}).items() if v > now}


def create_trusted_session() -> str:
    token = secrets.token_hex(32)
    d = load_2fa()
    trusted = _trusted_prune(d.get('trusted'))
    trusted[token] = time.time() + TRUSTED_DEVICE_DAYS * 86400
    d['trusted'] = trusted
    save_2fa(d)
    return token


def is_trusted_session_valid(cookie_value) -> bool:
    if not cookie_value:
        return False
    try:
        token = _serializer('trust2fa').loads(
            cookie_value, max_age=TRUSTED_DEVICE_DAYS * 86400)
    except (BadSignature, SignatureExpired):
        return False
    d = load_2fa()
    trusted = _trusted_prune(d.get('trusted'))
    if len(trusted) != len(d.get('trusted') or {}):
        d['trusted'] = trusted
        save_2fa(d)
    return token in trusted


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

    Behind Ingress the add-on lives under a proxy prefix. A bare "/" would send
    the browser to Home Assistant itself, which then loads a second, complete
    Home Assistant inside the Ingress frame — so the prefix is put back on.
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
    """True when the request came through the HA Supervisor Ingress proxy."""
    return bool(request.script_root)


def _logged_in() -> bool:
    return _is_ingress() or is_valid_session(request.cookies.get('session'))


def _auth_required():
    if _logged_in():
        return None
    return redirect(url_for('login'))


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
    """Reject cross-site form posts. Ingress and direct port both report the
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


_LAPI_STATUS = {
    'not_configured': 503, 'no_url': 503, 'bad_url': 503,
    'auth_failed': 502, 'unreachable': 502,
    'http_error': 502, 'bad_response': 502,
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
            except ValidationError as e:
                return jsonify({'error': e.code}), 400
            except LapiError as e:
                return (jsonify({'error': e.code, 'status': e.status}),
                        _LAPI_STATUS.get(e.code, 502))
            except Exception:
                log.exception("unhandled error in %s", rule)
                return jsonify({'error': 'internal error'}), 500
        return wrapper
    return deco


# ── LAPI client ───────────────────────────────────────────────────────────────

_client = None
_client_lock = threading.Lock()


def get_client() -> LapiClient:
    global _client
    cfg = load_config()
    url = str(cfg.get('lapi_url') or '').strip()
    machine_id = str(cfg.get('machine_id') or '').strip()
    password = str(cfg.get('machine_password') or '')
    verify = bool(cfg.get('lapi_tls_verify', True))
    with _client_lock:
        if _client is None or not _client.same_as(url, machine_id, password, verify):
            _client = LapiClient(url, machine_id, password, verify=verify)
            if _verbose():
                log.info("LAPI client rebuilt for %s", url or '(unset)')
        return _client


# ── Prometheus client ─────────────────────────────────────────────────────────

_metrics_client = None
_metrics_lock = threading.Lock()


def _prometheus_url() -> str:
    """Configured endpoint, or the LAPI host on CrowdSec's default metrics port.

    Both URLs come from the add-on options, so they are as trusted as the LAPI
    URL itself — but only the host is carried over, never a path or credentials
    that happened to be part of lapi_url.
    """
    raw = str(load_config().get('prometheus_url') or '').strip()
    if raw:
        return raw.rstrip('/')
    parts = urlsplit(str(load_config().get('lapi_url') or '').strip())
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        return ''
    host = parts.hostname
    netloc = f'[{host}]:{PROMETHEUS_PORT}' if ':' in host else f'{host}:{PROMETHEUS_PORT}'
    return urlunsplit((parts.scheme, netloc, '', '', ''))


def get_metrics_client() -> MetricsClient:
    global _metrics_client
    url = _prometheus_url()
    verify = bool(load_config().get('lapi_tls_verify', True))
    with _metrics_lock:
        if _metrics_client is None or not _metrics_client.same_as(url, verify):
            _metrics_client = MetricsClient(url, verify=verify)
            if _verbose():
                log.info("metrics client rebuilt for %s", url or '(unset)')
        return _metrics_client


def _page_size() -> int:
    return _cfg_int('page_size', 100, 10, 1000)


def _body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _arg(name: str, limit: int = 64) -> str:
    return (request.args.get(name) or '').strip()[:limit]


def _since_arg() -> str:
    raw = _arg('since', 16)
    return normalize_duration(raw) if raw else ''


def _origin_arg(raw: str) -> str:
    if raw and not re.fullmatch(r'[A-Za-z0-9_.-]{1,32}', raw):
        raise ValidationError('bad_origin')
    return raw


def _server_filters() -> dict:
    """Filters the alert endpoint really honours — see lapi._ALERT_FILTERS."""
    out = {}
    scope = _arg('scope')
    if scope:
        out['scope'] = normalize_scope(scope)
        value = _arg('value')
        if value:
            out['value'] = normalize_value(out['scope'], value)
    dtype = _arg('type', 16)
    if dtype:
        out['decision_type'] = normalize_type(dtype)
    origin = _origin_arg(_arg('origin', 32))
    if origin:
        out['origin'] = origin
    since = _since_arg()
    if since:
        out['since'] = since
    return out


def _is_list_sync(alert: dict) -> bool:
    """A blocklist refresh, not a detection.

    CrowdSec reports every subscription update as one alert — "update: +15000/-0
    IPs", no events, thousands of decisions attached. Counted among the triggers
    it drowns out what actually happened.
    """
    if str(alert.get('kind') or '').lower() == 'capi':
        return True
    for dec in (alert.get('decisions') or [])[:1]:
        if str(dec.get('origin') or '') in ('CAPI', 'lists'):
            return True
    return False


# Herkünfte, die aus dieser Instanz stammen — im Gegensatz zu den abonnierten
# Listen und der Community-Blockliste, die zusammen 99 % der Einträge stellen.
LOCAL_ORIGINS = ('crowdsec', 'cscli')


def _decision_kind_arg() -> str:
    kind = _arg('kind', 16) or 'local'
    if kind not in ('local', 'lists', 'all'):
        raise ValidationError('bad_kind')
    return kind


def _kind_arg() -> str:
    kind = _arg('kind', 16) or 'detections'
    if kind not in ('detections', 'lists', 'all'):
        raise ValidationError('bad_kind')
    return kind


def _group_arg() -> str:
    group = _arg('group', 16) or 'none'
    if group not in ('none', 'source', 'scenario'):
        raise ValidationError('bad_group')
    return group


def _group_alerts(rows: list, group: str) -> list:
    """Fold the alert list into one row per source or per scenario.

    A flat list of a hundred alerts hides the thing that matters — that ninety
    of them are the same address. Counting them is what turns the list into an
    answer.
    """
    key_field = 'value' if group == 'source' else 'scenario'
    other_field = 'scenario' if group == 'source' else 'value'
    buckets: dict = {}
    for row in rows:
        key = row.get(key_field) or '-'
        bucket = buckets.get(key)
        if bucket is None:
            bucket = buckets[key] = {
                'key': key, 'count': 0,
                'country': row.get('country') or '',
                'as_name': row.get('as_name') or '',
                'first': row.get('created_at') or '',
                'last': row.get('created_at') or '',
                'events': 0, 'list_sync': bool(row.get('list_sync')),
                '_others': set(), 'ids': [],
            }
        bucket['count'] += 1
        bucket['events'] += int(row.get('events_count') or 0)
        stamp = row.get('created_at') or ''
        if stamp and stamp < bucket['first']:
            bucket['first'] = stamp
        if stamp and stamp > bucket['last']:
            bucket['last'] = stamp
        other = row.get(other_field)
        if other:
            bucket['_others'].add(other)
        if len(bucket['ids']) < 5 and row.get('id') is not None:
            bucket['ids'].append(row['id'])
        if not bucket['country']:
            bucket['country'] = row.get('country') or ''
        if not bucket['as_name']:
            bucket['as_name'] = row.get('as_name') or ''

    out = []
    for bucket in buckets.values():
        others = sorted(bucket.pop('_others'))
        bucket['others'] = others[:5]
        bucket['others_total'] = len(others)
        out.append(bucket)
    out.sort(key=lambda b: (-b['count'], b['key']))
    return out


def _text_match(row: dict, needle: str) -> bool:
    if not needle:
        return True
    needle = needle.lower()
    for key in ('value', 'scenario', 'country', 'as_name', 'origin', 'type'):
        if needle in str(row.get(key, '')).lower():
            return True
    return False


# ── Whitelist parsers (read-only view) ────────────────────────────────────────
# CrowdSec knows two kinds of exemption. Allowlists live in its database and are
# served by the LAPI. Whitelists are parser YAML files that act one step earlier,
# while the log line is being read — the LAPI never sees them. They are shown
# here by reading the files; changing them stays with cscli and an editor.

# Wurzel der CrowdSec-Konfiguration. Von hier hängen sowohl die
# Whitelist-Parser als auch alles ab, was aus dem Hub installiert wurde.
CROWDSEC_DIR_CANDIDATES = (
    '/homeassistant/.storage/crowdsec/config',
    '/config/.storage/crowdsec/config',
)
WHITELIST_CANDIDATES = tuple(
    base + '/parsers/s02-enrich' for base in CROWDSEC_DIR_CANDIDATES)

# Die Typen, die cscli unter "hub list" zusammenfasst. Parser und
# Postoverflows liegen eine Ebene tiefer in Stufenverzeichnissen.
HUB_TYPES = ('collections', 'parsers', 'postoverflows', 'scenarios',
             'appsec-configs', 'appsec-rules', 'contexts')
HUB_STAGED = ('parsers', 'postoverflows')
WHITELIST_MAX_BYTES = 256 * 1024
WHITELIST_SUFFIXES = ('.yaml', '.yml')


def _whitelist_dir() -> Path | None:
    configured = str(load_config().get('whitelist_dir') or '').strip()
    if not configured:
        base = _crowdsec_dir()
        if base is not None:
            staged = base / 'parsers' / 's02-enrich'
            if staged.is_dir():
                return staged
    for candidate in ([configured] if configured else list(WHITELIST_CANDIDATES)):
        try:
            path = Path(candidate).resolve()
        except (OSError, RuntimeError, ValueError):
            continue
        if path.is_dir():
            return path
    return None


def _crowdsec_dir() -> Path | None:
    configured = str(load_config().get('crowdsec_dir') or '').strip()
    for candidate in ([configured] if configured else list(CROWDSEC_DIR_CANDIDATES)):
        try:
            path = Path(candidate).resolve()
        except (OSError, RuntimeError, ValueError):
            continue
        if path.is_dir():
            return path
    return None


def _hub_item_name(entry: Path, kind: str) -> tuple[str, bool]:
    """Name of an installed item and whether it came from the hub.

    Hub items are symlinks into the hub directory; that directory lives inside
    the CrowdSec container and may not be readable from here. The author/name
    pair is then taken from the link target, which still carries it.
    """
    is_link = entry.is_symlink()
    try:
        with open(entry, encoding='utf-8', errors='replace') as f:
            for line in f:
                if line.startswith('name:'):
                    got = line.split(':', 1)[1].strip().strip('"\'')
                    if got:
                        return got, is_link
                if line.startswith(('filter:', 'description:', 'nodes:')):
                    break
    except OSError:
        pass

    if is_link:
        try:
            parts = os.readlink(entry).replace('\\', '/').split('/')
            if len(parts) >= 2 and parts[-2] not in ('', '.', '..'):
                return f'{parts[-2]}/{entry.stem}', True
        except OSError:
            pass
    return entry.stem, is_link


def _hub_scan_dir(folder: Path, kind: str, stage: str = '') -> list:
    items = []
    try:
        entries = sorted(folder.iterdir())
    except OSError:
        return items
    for entry in entries:
        if entry.suffix.lower() not in ('.yaml', '.yml'):
            continue
        name, from_hub = _hub_item_name(entry, kind)
        items.append({'name': name, 'file': entry.name, 'stage': stage,
                      'source': 'hub' if from_hub else 'local'})
    return items


# ── Bouncers and machines (read-only, straight from CrowdSec's database) ──────
# The LAPI does not expose either — cscli reads them from the local database.
# Since the configuration directory is mounted read-only anyway, the same file
# answers the question that matters most in daily use: is the bouncer still
# pulling?

DB_CANDIDATES = (
    '/homeassistant/.storage/crowdsec/data/crowdsec.db',
    '/config/.storage/crowdsec/data/crowdsec.db',
)


def _crowdsec_db() -> Path | None:
    configured = str(load_config().get('crowdsec_db') or '').strip()
    candidates = [configured] if configured else []
    if not configured:
        base = _crowdsec_dir()
        if base is not None:
            candidates.append(str(base.parent / 'data' / 'crowdsec.db'))
        candidates.extend(DB_CANDIDATES)
    for candidate in candidates:
        try:
            path = Path(candidate).resolve()
        except (OSError, RuntimeError, ValueError):
            continue
        if path.is_file():
            return path
    return None


def _db_rows(path: Path, table: str, wanted: tuple) -> list:
    """Read a table, but only the columns this CrowdSec version actually has."""
    uri = 'file:' + quote(str(path)) + '?mode=ro&immutable=0'
    try:
        con = sqlite3.connect(uri, uri=True, timeout=5)
    except sqlite3.Error:
        return []
    try:
        con.row_factory = sqlite3.Row
        have = {r[1] for r in con.execute(f'PRAGMA table_info({table})')}
        if not have:
            return []
        cols = [c for c in wanted if c in have]
        if not cols:
            return []
        sql = 'SELECT ' + ', '.join(f'"{c}"' for c in cols) + f' FROM "{table}"'
        return [{c: row[c] for c in cols} for row in con.execute(sql)]
    except sqlite3.Error:
        return []
    finally:
        con.close()


def _iso_utc(stamp) -> str:
    """CrowdSec writes timestamps in a few shapes; Home Assistant wants RFC 3339
    with a time zone. An unparsable value returns empty rather than guessing."""
    text = str(stamp or '').strip()
    if not text:
        return ''
    text = text.replace('Z', '+00:00').replace('z', '+00:00')
    if 'T' not in text and ' ' in text:
        text = text.replace(' ', 'T', 1)
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return ''
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _stamp_age(stamp) -> float | None:
    """Seconds since the timestamp, or None when there is none to read."""
    iso = _iso_utc(stamp)
    if not iso:
        return None
    return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds()


def _entity_slug(name: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '_', str(name or '').lower()).strip('_')
    return slug or 'unknown'


# Ein Bouncer, der seit dieser Zeitspanne nicht mehr abgeholt hat, setzt keine
# Sperren mehr durch. Oberfläche und Sensoren benutzen dieselbe Grenze.
BOUNCER_STALE_SECONDS = 600


def _bouncer_state() -> dict:
    """Bouncers and machines, in the shape both the UI and the sensors need."""
    path = _crowdsec_db()
    if path is None:
        return {'available': False, 'db': '', 'bouncers': [], 'machines': []}
    rows = _db_rows(path, 'bouncers',
                    ('name', 'type', 'version', 'ip_address', 'last_pull',
                     'revoked', 'auth_type', 'created_at', 'auto_created'))
    machines = _db_rows(path, 'machines',
                        ('machine_id', 'version', 'ip_address', 'last_heartbeat',
                         'is_validated', 'auth_type', 'created_at'))
    for row in rows:
        row['revoked'] = bool(row.get('revoked'))
        # Kindeinträge entstehen, wenn derselbe Schlüssel von einer anderen
        # Adresse benutzt wird. Sie holen nichts ab und lassen sich auch nicht
        # einzeln löschen — ein alter Zeitstempel ist bei ihnen normal.
        row['auto_created'] = bool(row.get('auto_created'))
    for row in machines:
        row['is_validated'] = bool(row.get('is_validated'))
    own = str(load_config().get('machine_id') or '').strip()
    for row in machines:
        row['self'] = bool(own) and row.get('machine_id') == own
    return {'available': True, 'db': str(path),
            'bouncers': rows, 'machines': machines}


def _bouncer_stale(row: dict) -> bool:
    """Kindeinträge sind ausgenommen — bei ihnen ist ein alter Zeitstempel der
    Normalfall, sie holen grundsätzlich nichts ab."""
    if row.get('auto_created'):
        return False
    if row.get('revoked'):
        return True
    age = _stamp_age(row.get('last_pull'))
    return age is None or age > BOUNCER_STALE_SECONDS


@api('/api/bouncers')
def bouncers():
    return jsonify(_bouncer_state())


# ── Map ───────────────────────────────────────────────────────────────────────
# CrowdSec reicht im Alarm nicht nur das Land durch, sondern auch Breiten- und
# Längengrad — gefüllt vom GeoIP-Enrichment. Ohne dieses Enrichment bleiben die
# Felder leer; dann meldet der Endpunkt das offen, statt eine leere Karte zu
# zeigen und den Grund zu verschweigen.

MAP_MAX_POINTS = 400

# Wie viele Archivzeilen eine Alarmabfrage hoechstens liest. Angezeigt werden
# davon nur ``page_size``; gebraucht werden alle, weil Gruppierung und
# Trefferzahl ueber den ganzen Zeitraum gehen.
ARCHIVE_SEARCH_LIMIT = 20000


# ── Alarm-Archiv ──────────────────────────────────────────────────────

_archive: Archive | None = None
_archive_lock = threading.Lock()


def archive_enabled() -> bool:
    return bool(load_config().get('archive_enabled', True))


def get_archive() -> Archive | None:
    """Das Archiv, oder None wenn es aus ist oder sich die Datei nicht anlegen
    laesst. Jeder Aufrufer muss mit None umgehen koennen — ohne Archiv
    antworten die Endpunkte wie vorher aus der LAPI."""
    global _archive
    if not archive_enabled():
        return None
    with _archive_lock:
        if _archive is None:
            candidate = Archive(ARCHIVE_PATH)
            if not candidate.open():
                return None
            _archive = candidate
    return _archive if _archive.available() else None


def archive_ready() -> Archive | None:
    """Das Archiv, sobald es einmal befuellt wurde. Vorher waere seine Antwort
    zwar schnell, aber leer — und eine leere Uebersicht ist schlechter als eine
    langsame."""
    arch = get_archive()
    return arch if arch is not None and arch.get_meta('last_sync') else None


def _archive_since_ts(since: str, fallback_hours: int = 24) -> int:
    """Die Zeitspanne der Oberflaeche (\"24h\", \"7d\") als Sekunde, ab der
    gesucht wird. Unlesbares faellt auf den Vorgabewert zurueck."""
    text = str(since or '').strip().lower()
    hours = float(fallback_hours)
    match = re.fullmatch(r'([0-9]+(?:\.[0-9]+)?)([hdm]?)', text)
    if match:
        number = float(match.group(1))
        unit = match.group(2) or 'h'
        hours = number * {'h': 1, 'd': 24, 'm': 1 / 60}[unit]
    return int(time.time() - max(0.0, hours) * 3600)


def _archive_sync() -> int:
    """Neue Erkennungen aus der LAPI ins Archiv holen.

    Beim ersten Lauf reicht die Abfrage so weit zurueck, wie
    ``archive_backfill_days`` erlaubt; danach nur noch bis kurz vor den
    juengsten bekannten Alarm. Die Ueberlappung von einer Stunde faengt Alarme
    ab, die zwischen zwei Laeufen mit aelterem Zeitstempel nachgereicht werden.
    """
    arch = get_archive()
    if arch is None:
        return 0
    client = get_client()
    if not client.configured():
        return 0
    backfill_hours = _cfg_int('archive_backfill_days', 30, 1, 3650) * 24
    newest = arch.newest_ts()
    if newest:
        hours = int((time.time() - newest) / 3600) + 2
        hours = max(1, min(hours, backfill_hours))
    else:
        hours = backfill_hours
    rows = [a for a in client.list_alerts(limit=ALERT_FETCH_LIMIT, since=f'{hours}h')
            if isinstance(a, dict)]
    added = arch.ingest([a for a in rows if not _is_list_sync(a)])
    arch.ingest_syncs([a for a in rows if _is_list_sync(a)])
    removed = arch.prune(_cfg_int('archive_days', 365, 0, 3650))
    arch.set_meta('last_sync', datetime.now(timezone.utc).isoformat())
    if _verbose() and (added or removed):
        log.info('alert archive: %d added, %d pruned', added, removed)
    return added


def _archive_worker() -> None:
    while True:
        try:
            _archive_sync()
        except (LapiError, ValidationError) as e:
            if _verbose():
                log.info('alert archive sync skipped: %s', getattr(e, 'code', ''))
        except Exception:
            log.exception('archive worker')
        time.sleep(_cfg_int('archive_interval', 300, 60, 86400))


@api('/api/archive')
def archive_state():
    """Was im Archiv steht — fuer die Anzeige in den Einstellungen."""
    if not archive_enabled():
        return jsonify({'enabled': False, 'available': False, 'rows': 0})
    arch = get_archive()
    if arch is None:
        return jsonify({'enabled': True, 'available': False, 'rows': 0})
    out = arch.stats()
    out['enabled'] = True
    out['days'] = _cfg_int('archive_days', 365, 0, 3650)
    out['interval'] = _cfg_int('archive_interval', 300, 60, 86400)
    return jsonify(out)


def _coord(raw) -> float | None:
    """Nur echte Koordinaten zählen. CrowdSec schreibt 0/0 in den Alarm, wenn
    das Enrichment nichts gefunden hat — und im Golf von Guinea sitzt niemand."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value != value or abs(value) > 180:
        return None
    return value


def _home_point() -> dict | None:
    """Der eigene Standort kommt aus der Konfiguration, nicht aus einer
    Abfrage nach draussen: die oeffentliche Adresse des Nutzers wandert nicht
    zu einem fremden Geo-Dienst, nur damit ein Punkt auf der Karte sitzt.
    Beide Koordinaten muessen gesetzt sein — eine allein ergibt keinen Ort."""
    lat = _cfg_float('server_lat', -90, 90)
    lon = _cfg_float('server_lon', -180, 180)
    if lat is None or lon is None:
        return None
    # 0/0 ist die Vorgabe der beiden Optionen und heisst 'nicht eingetragen' —
    # dieselbe Lesart wie bei den Alarmen, im Golf von Guinea sitzt niemand.
    if lat == 0 and lon == 0:
        return None
    label = str(load_config().get('server_label') or '').strip()
    return {'lat': round(lat, 4), 'lon': round(lon, 4), 'label': label[:80]}


@api('/api/map')
def attack_map():
    since = _since_arg() or '24h'
    arch = archive_ready()
    if arch is not None:
        points, located = arch.points(_archive_since_ts(since), MAP_MAX_POINTS)
        return jsonify({'since': since, 'points': points, 'located': located,
                        'alerts': arch.count_since(_archive_since_ts(since)),
                        'truncated': located > MAP_MAX_POINTS,
                        'source': 'archive', 'home': _home_point()})

    client = get_client()
    rows = client.list_alerts(limit=ALERT_FETCH_LIMIT, since=since)

    points: dict = {}
    total = 0
    for alert in rows:
        if not isinstance(alert, dict) or _is_list_sync(alert):
            continue
        total += 1
        src = alert.get('source') or {}
        value = src.get('value') or src.get('ip') or ''
        lat, lon = _coord(src.get('latitude')), _coord(src.get('longitude'))
        if not value or lat is None or lon is None or (lat == 0 and lon == 0):
            continue
        point = points.get(value)
        if point is None:
            point = {'value': value, 'lat': round(lat, 3), 'lon': round(lon, 3),
                     'country': src.get('cn') or '', 'as_name': src.get('as_name') or '',
                     'count': 0, 'scenarios': Counter()}
            points[value] = point
        point['count'] += 1
        if alert.get('scenario'):
            point['scenarios'][alert['scenario']] += 1

    ranked = sorted(points.values(), key=lambda p: (-p['count'], p['value']))
    out = []
    for point in ranked[:MAP_MAX_POINTS]:
        scenarios = point.pop('scenarios')
        point['scenario'] = scenarios.most_common(1)[0][0] if scenarios else ''
        out.append(point)

    return jsonify({'since': since, 'points': out,
                    'located': len(points), 'alerts': total,
                    'truncated': len(points) > MAP_MAX_POINTS,
                    'source': 'lapi', 'home': _home_point()})


@api('/api/metrics')
def prometheus_metrics():
    """CrowdSec's own counters. Unreachable is the normal case until someone
    opens the listener, so that is reported as a state, not as a failure."""
    client = get_metrics_client()
    if not client.configured():
        return jsonify({'available': False, 'url': client.url,
                        'reason': 'not_configured'})
    try:
        return jsonify(client.snapshot(force=_arg('force', 8) == '1'))
    except LapiError as e:
        return jsonify({'available': False, 'url': client.endpoint(),
                        'reason': e.code, 'status': e.status})


# ── History ───────────────────────────────────────────────────────────────────

@api('/api/history')
def history():
    """Detections per day for the last week. A single number for 24 hours says
    nothing about whether something is building up."""
    if _arg('bucket', 8) == 'hour':
        return _history_hours()
    days = _cfg_int('history_days', 7, 1, 3650)
    arch = archive_ready()
    source = 'archive'
    if arch is not None:
        detections, syncs = arch.history(days)
    else:
        # Ohne Archiv reicht der Verlauf nur so weit, wie CrowdSec seine Alarme
        # aufhebt — und jeder Aufruf holt sie alle.
        source = 'lapi'
        detections, syncs = Counter(), Counter()
        for alert in get_client().list_alerts(limit=ALERT_FETCH_LIMIT,
                                              since=f'{days * 24}h'):
            if not isinstance(alert, dict):
                continue
            stamp = str(alert.get('created_at') or alert.get('start_at') or '')[:10]
            if len(stamp) != 10:
                continue
            (syncs if _is_list_sync(alert) else detections)[stamp] += 1

    today = datetime.now(timezone.utc).date()
    series = []
    for back in range(days - 1, -1, -1):
        day = (today - timedelta(days=back)).isoformat()
        series.append({'day': day,
                       'detections': detections.get(day, 0),
                       'list_updates': syncs.get(day, 0)})
    return jsonify({'days': days, 'bucket': 'day', 'series': series,
                    'source': source,
                    'total': sum(s['detections'] for s in series)})


HISTORY_HOURS = 48


def _history_hours():
    """Derselbe Verlauf in Stundenschritten. Der Schlüssel heißt weiter „day“,
    damit die Oberfläche beide Auflösungen gleich behandeln kann; welche
    gemeint ist, sagt „bucket“."""
    arch = archive_ready()
    source = 'archive'
    if arch is not None:
        detections, syncs = arch.history_hours(HISTORY_HOURS)
    else:
        source = 'lapi'
        detections, syncs = Counter(), Counter()
        for alert in get_client().list_alerts(limit=ALERT_FETCH_LIMIT,
                                              since=f'{HISTORY_HOURS}h'):
            if not isinstance(alert, dict):
                continue
            stamp = str(alert.get('created_at') or alert.get('start_at') or '')
            # 2026-09-03T14:… — Datum und Stunde, wie die Archivabfrage sie bildet.
            if len(stamp) < 13 or stamp[10] != 'T':
                continue
            (syncs if _is_list_sync(alert) else detections)[stamp[:13]] += 1

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    series = []
    for back in range(HISTORY_HOURS - 1, -1, -1):
        slot = (now - timedelta(hours=back)).strftime('%Y-%m-%dT%H')
        series.append({'day': slot,
                       'detections': detections.get(slot, 0),
                       'list_updates': syncs.get(slot, 0)})
    return jsonify({'days': HISTORY_HOURS / 24, 'bucket': 'hour',
                    'series': series, 'source': source,
                    'total': sum(s['detections'] for s in series)})


@api('/api/hub')
def hub():
    """What is installed, read from the files — the same ground truth that
    `cscli hub list` reports. Versions are deliberately absent: cscli derives
    them from the hub index, and that index lives inside the CrowdSec
    container, not in the shared configuration directory."""
    base = _crowdsec_dir()
    if base is None:
        return jsonify({'available': False, 'dir': '', 'types': []})

    types = []
    for kind in HUB_TYPES:
        folder = base / kind
        if not folder.is_dir():
            continue
        items = []
        if kind in HUB_STAGED:
            for stage in sorted(p.name for p in folder.iterdir() if p.is_dir()):
                items.extend(_hub_scan_dir(folder / stage, kind, stage))
            items.extend(_hub_scan_dir(folder, kind))
        else:
            items = _hub_scan_dir(folder, kind)
        if items:
            items.sort(key=lambda i: (i['source'] != 'local', i['name']))
            types.append({'type': kind, 'count': len(items), 'items': items})
    return jsonify({'available': True, 'dir': str(base), 'types': types})


@api('/api/whitelists')
def whitelist_files():
    base = _whitelist_dir()
    if base is None:
        return jsonify({'available': False, 'dir': '', 'files': []})

    files = []
    try:
        entries = sorted(base.iterdir())
    except OSError:
        return jsonify({'available': False, 'dir': str(base), 'files': []})

    for entry in entries:
        if entry.suffix.lower() not in WHITELIST_SUFFIXES:
            continue
        try:
            resolved = entry.resolve()
            # A symlink must not lead out of the directory we were pointed at.
            if not resolved.is_relative_to(base) or not resolved.is_file():
                continue
            info = resolved.stat()
            item = {'name': entry.name, 'size': info.st_size,
                    'modified': datetime.fromtimestamp(info.st_mtime,
                                                       timezone.utc).isoformat()}
            if info.st_size > WHITELIST_MAX_BYTES:
                item['too_large'] = True
                item['content'] = ''
            else:
                item['content'] = resolved.read_text(encoding='utf-8',
                                                     errors='replace')
        except OSError:
            continue
        files.append(item)
    return jsonify({'available': True, 'dir': str(base), 'files': files})


# ── Routes without authentication ─────────────────────────────────────────────

@app.route('/health')
def health():
    return 'OK', 200


@app.route('/manifest.json')
def manifest():
    base = request.script_root.rstrip('/')
    data = {
        'name': 'CrowdPanel',
        'short_name': 'CrowdPanel',
        'description': 'CrowdSec control panel for Home Assistant',
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
        'categories': ['utilities', 'security'],
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


@app.route('/set-lang/<lang>')
def set_lang(lang: str):
    cookie_lang = 'en' if lang == 'en' else 'de'
    resp = make_response(redirect(_safe_next(request.args.get('next', '/'))))
    resp.set_cookie('lang', cookie_lang, max_age=365 * 86400, samesite='Lax')
    return resp


@app.route('/login', methods=['GET', 'POST'])
def login():
    lang = detect_language(request)
    t = load_translations(lang)
    cfg = load_config()

    if _logged_in():
        return redirect(url_for('index'))

    error = None
    if request.method == 'POST':
        ip = get_client_ip(request)
        if not _origin_ok() or not _csrf_ok():
            error = t.get('error_expired')
        elif is_rate_limited(ip):
            error = t.get('error_locked')
        else:
            username = request.form.get('username', '')
            password = request.form.get('password', '')
            ok = (secrets.compare_digest(username, str(cfg.get('username', 'admin')))
                  and secrets.compare_digest(password,
                                             str(cfg.get('password', 'changeme123'))))
            if ok:
                clear_failed_attempts(ip)
                hours = _cfg_int('session_hours', 24, 1, 720)
                if twofa_enabled() and not is_trusted_session_valid(
                        request.cookies.get('trust2fa')):
                    pending = _pending_2fa_new()
                    resp = make_response(redirect(url_for('twofa')))
                    resp.set_cookie('pre2fa', pending, httponly=True,
                                    samesite='Lax', max_age=PENDING_2FA_TTL)
                    return resp
                token = create_session(hours)
                resp = make_response(redirect(url_for('index')))
                resp.set_cookie('session', token, httponly=True, samesite='Lax',
                                max_age=hours * 3600)
                return resp
            record_failed_attempt(ip)
            error = t.get('error_credentials')

    return make_response(render_template('login.html', t=t, lang=lang, error=error,
                                         csrf=g.csrf))


@app.route('/2fa', methods=['GET', 'POST'])
def twofa():
    lang = detect_language(request)
    t = load_translations(lang)

    if _logged_in():
        return redirect(url_for('index'))
    if not _pending_2fa_valid(request.cookies.get('pre2fa')):
        return redirect(url_for('login'))

    error = None
    if request.method == 'POST':
        ip = get_client_ip(request)
        if not _origin_ok() or not _csrf_ok():
            error = t.get('error_expired')
        elif is_rate_limited(ip):
            error = t.get('error_locked')
        else:
            code = request.form.get('code', '')
            data = load_2fa()
            if totp_verify(str(data.get('secret') or ''), code) or backup_code_consume(code):
                clear_failed_attempts(ip)
                _pending_2fa.pop(request.cookies.get('pre2fa'), None)
                hours = _cfg_int('session_hours', 24, 1, 720)
                token = create_session(hours)
                resp = make_response(redirect(url_for('index')))
                resp.set_cookie('session', token, httponly=True, samesite='Lax',
                                max_age=hours * 3600)
                resp.delete_cookie('pre2fa')
                if request.form.get('trust') == 'on':
                    trusted = create_trusted_session()
                    resp.set_cookie('trust2fa',
                                    _serializer('trust2fa').dumps(trusted),
                                    httponly=True, samesite='Lax',
                                    max_age=TRUSTED_DEVICE_DAYS * 86400)
                return resp
            record_failed_attempt(ip)
            error = t.get('error_totp')

    return make_response(render_template('twofa.html', t=t, lang=lang, error=error,
                                         csrf=g.csrf))


@app.route('/logout')
def logout():
    token = request.cookies.get('session')
    if token:
        with _sessions_lock:
            if sessions.pop(token, None) is not None:
                save_sessions()
    resp = make_response(redirect(url_for('login')))
    resp.delete_cookie('session')
    return resp


# ── Page ──────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    redir = _auth_required()
    if redir:
        return redir
    lang = detect_language(request)
    t = load_translations(lang)
    cfg = load_config()
    return make_response(render_template(
        'index.html', t=t, lang=lang, csrf=g.csrf,
        ingress=_is_ingress(),
        scopes=SCOPES,
        decision_types=DECISION_TYPES,
        durations=DURATION_PRESETS,
        version=APP_VERSION,
        default_duration=str(cfg.get('default_ban_duration') or '4h'),
        refresh_interval=_cfg_int('refresh_interval', 30, 0, 3600),
        page_size=_page_size(),
        has_qr=_HAS_QR,
    ))


# ── API ───────────────────────────────────────────────────────────────────────

@api('/api/status')
def status():
    client = get_client()
    return jsonify({
        'lapi': client.ping(),
        'url': client.url,
        'machine_id': client.machine_id,
        'twofa': twofa_enabled(),
        'ingress': _is_ingress(),
        'sensors': ha_sensors_enabled(),
        'version': APP_VERSION,
        'supervisor': _supervisor_versions(),
    })


@api('/api/overview')
def overview():
    client = get_client()
    stats = client.decision_stats()
    alerts = [a for a in client.list_alerts(limit=ALERT_FETCH_LIMIT, since='24h')
              if isinstance(a, dict)]
    detections = [a for a in alerts if not _is_list_sync(a)]
    alert_scenarios = Counter(a.get('scenario') for a in detections
                              if a.get('scenario'))
    # Das Netz hinter der Adresse. Es steht in jedem angereicherten Alarm und
    # sagt mehr als das Land: ein Rechenzentrum ist keine Wohngegend.
    top_as = Counter()
    for alert in detections:
        name = ((alert.get('source') or {}).get('as_name') or '').strip()
        if name:
            top_as[name] += 1
    return jsonify({
        'decisions_total': stats['total'],
        'alerts_24h': len(detections),
        'list_updates_24h': len(alerts) - len(detections),
        'by_type': stats['by_type'],
        'top_countries': stats['top_countries'],
        'top_scenarios': stats['top_scenarios'],
        'by_origin': stats['by_origin'],
        'top_alert_scenarios': alert_scenarios.most_common(10),
        'top_as': top_as.most_common(10),
    })


@api('/api/decisions', methods=('GET', 'POST', 'DELETE'))
def decisions():
    client = get_client()

    if request.method == 'GET':
        # One alert can carry thousands of decisions — a community blocklist
        # update is a single alert with 15000 of them. Fetching stays cheap,
        # but the answer has to be capped or the table drowns the browser.
        rows = client.list_decisions(limit=ALERT_FETCH_LIMIT, **_server_filters())
        kind = _decision_kind_arg()
        if kind == 'local':
            rows = [r for r in rows if r.get('origin') in LOCAL_ORIGINS]
        elif kind == 'lists':
            rows = [r for r in rows if r.get('origin') not in LOCAL_ORIGINS]
        needle = _arg('q', 64)
        if needle:
            rows = [r for r in rows if _text_match(r, needle)]
        # Neueste zuerst, und zwar *vor* der Deckelung. Sonst bestimmt ein
        # einzelner Alarm die ganze Seite: Eine Blocklisten-Aktualisierung
        # bringt 15000 Entscheidungen mit demselben Zeitstempel mit, und die
        # eigenen Sperren wären nie zu sehen.
        rows.sort(key=lambda r: str(r.get('created_at') or ''), reverse=True)
        total = len(rows)
        cap = _page_size()
        return jsonify({'decisions': rows[:cap], 'count': min(total, cap),
                        'total': total, 'truncated': total > cap, 'kind': kind})

    if request.method == 'POST':
        body = _body()
        cfg = load_config()
        result = client.add_decision(
            scope=body.get('scope') or 'Ip',
            value=body.get('value') or '',
            dtype=body.get('type') or 'ban',
            duration=body.get('duration') or str(cfg.get('default_ban_duration') or '4h'),
            reason=body.get('reason') or '',
        )
        return jsonify({'status': 'added', **result})

    body = _body()
    if body.get('id') not in (None, ''):
        return jsonify({'status': 'deleted',
                        'deleted': client.delete_decision(body.get('id'))})

    scope = (body.get('scope') or '').strip()
    value = (body.get('value') or '').strip()
    if scope and value:
        return jsonify({'status': 'deleted',
                        'deleted': client.delete_by_target(scope, value)})

    filters = {}
    for key in ('ip', 'range'):
        term = (body.get(key) or '').strip()
        if term:
            kind = is_ip_or_range(term)
            if not kind:
                raise ValidationError('bad_ip')
            filters[kind[0]] = kind[1]
    dtype = (body.get('type') or '').strip()
    if dtype:
        filters['type'] = normalize_type(dtype)
    origin = _origin_arg((body.get('origin') or '').strip())
    if origin:
        filters['origin'] = origin
    return jsonify({'status': 'deleted',
                    'deleted': client.delete_decisions(**filters)})


@api('/api/alerts')
def alerts():
    filters = _server_filters()
    filters.pop('decision_type', None)
    kind = _kind_arg()
    group = _group_arg()
    needle = _arg('q', 64)
    cap = _page_size()

    # Das Archiv kennt nur Erkennungen und nur die eigenen Felder. Sobald nach
    # der Herkunft gefiltert wird oder Listenabgleiche gefragt sind, antwortet
    # wieder die LAPI — lieber langsam und vollstaendig als schnell und halb.
    arch = archive_ready() if kind == 'detections' and not filters.get('origin') else None
    if arch is not None:
        found = arch.search(since_ts=_archive_since_ts(filters.get('since') or '24h'),
                            needle=needle, value=filters.get('value') or '',
                            limit=ARCHIVE_SEARCH_LIMIT)
        out = [{'id': r['id'], 'scenario': r['scenario'], 'message': r['message'],
                'created_at': r['created_at'], 'events_count': r['events_count'],
                'simulated': bool(r['simulated']), 'value': r['value'],
                'country': r['country'], 'as_name': r['as_name'],
                'decisions': r['decision_count'], 'list_sync': False}
               for r in found]
        return _alert_answer(out, group, cap, 'archive')

    client = get_client()
    rows = client.list_alerts(limit=ALERT_FETCH_LIMIT, **filters)
    out = []
    for a in rows:
        if not isinstance(a, dict):
            continue
        sync = _is_list_sync(a)
        if (kind == 'detections' and sync) or (kind == 'lists' and not sync):
            continue
        src = a.get('source') or {}
        item = {
            'id': a.get('id'),
            'scenario': a.get('scenario') or '',
            'message': a.get('message') or '',
            'created_at': a.get('created_at') or a.get('start_at') or '',
            'events_count': a.get('events_count') or 0,
            'simulated': bool(a.get('simulated')),
            'value': src.get('value') or src.get('ip') or '',
            'country': src.get('cn') or '',
            'as_name': src.get('as_name') or '',
            'decisions': len(a.get('decisions') or []),
            'list_sync': sync,
        }
        if needle and not _text_match(
                {'value': item['value'], 'scenario': item['scenario'],
                 'country': item['country'], 'as_name': item['as_name']}, needle):
            continue
        out.append(item)

    return _alert_answer(out, group, cap, 'lapi')


def _alert_answer(out: list, group: str, cap: int, source: str):
    """Dieselbe Antwort, gleich woher die Zeilen kommen."""
    if group != 'none':
        groups = _group_alerts(out, group)
        total = len(groups)
        return jsonify({'group': group, 'groups': groups[:cap],
                        'count': min(total, cap), 'total': total, 'source': source,
                        'alerts_total': len(out), 'truncated': total > cap})

    total = len(out)
    return jsonify({'group': 'none', 'alerts': out[:cap], 'count': min(total, cap),
                    'total': total, 'source': source, 'truncated': total > cap})


@api('/api/alerts/<int:alert_id>')
def alert_detail(alert_id: int):
    data = get_client().get_alert(alert_id)
    if data is None:
        return jsonify({'error': 'not_found'}), 404
    return jsonify({'alert': data})


@api('/api/check')
def check():
    client = get_client()
    kind, active = client.decisions_for(_arg('value', 64))
    scope = 'Ip' if kind[0] == 'ip' else 'Range'
    arch = archive_ready()
    if arch is not None:
        # Aus dem Archiv reicht die Historie weiter zurueck als CrowdSecs eigene
        # Aufbewahrung — genau die Frage, die hier gestellt wird.
        history = arch.search(value=kind[1], limit=50)
    else:
        history = client.list_alerts(limit=50, scope=scope, value=kind[1])
    try:
        allow = client.allowlist_status(kind[1])
    except (LapiError, ValidationError):
        allow = None
    return jsonify({
        'value': kind[1],
        'kind': kind[0],
        'active': active,
        'history': [{
            'id': a.get('id'),
            'scenario': a.get('scenario') or '',
            'created_at': a.get('created_at') or a.get('start_at') or '',
            'events_count': a.get('events_count') or 0,
        } for a in history if isinstance(a, dict)],
        'allowlist': allow,
    })


@api('/api/allowlists')
def allowlists():
    return jsonify({'allowlists': get_client().allowlists()})


# ── 2FA management ────────────────────────────────────────────────────────────

_2fa_setup: dict = {}


@api('/api/2fa')
def twofa_state():
    return jsonify({'enabled': twofa_enabled(), 'ingress': _is_ingress(),
                    'has_qr': _HAS_QR})


@api('/api/2fa/setup', methods=('POST',))
def twofa_setup():
    secret = _new_totp_secret()
    _2fa_setup['secret'] = secret
    _2fa_setup['expires'] = time.time() + PENDING_2FA_TTL
    account = str(load_config().get('username', 'admin'))
    uri = _otpauth_uri(secret, account)
    return jsonify({'secret': secret, 'uri': uri, 'qr': _qr_svg(uri),
                    'has_qr': _HAS_QR})


@api('/api/2fa/enable', methods=('POST',))
def twofa_enable():
    secret = str(_2fa_setup.get('secret') or '')
    if not secret or time.time() > float(_2fa_setup.get('expires') or 0):
        _2fa_setup.clear()
        return jsonify({'error': 'setup_expired'}), 400
    if not totp_verify(secret, str(_body().get('code') or '')):
        return jsonify({'error': 'bad_code'}), 400
    plain, hashes = _gen_backup_codes()
    save_2fa({'enabled': True, 'secret': secret, 'backup': hashes, 'trusted': {}})
    _2fa_setup.clear()
    log.info("two-factor authentication enabled")
    return jsonify({'status': 'enabled', 'backup_codes': plain})


@api('/api/2fa/disable', methods=('POST',))
def twofa_disable():
    password = str(_body().get('password') or '')
    if not secrets.compare_digest(password,
                                  str(load_config().get('password', 'changeme123'))):
        return jsonify({'error': 'bad_password'}), 403
    save_2fa({'enabled': False, 'secret': '', 'backup': [], 'trusted': {}})
    log.info("two-factor authentication disabled")
    return jsonify({'status': 'disabled'})


SUPERVISOR_TOKEN = os.environ.get('SUPERVISOR_TOKEN', '')

# ── Version ───────────────────────────────────────────────────────────────────
# Welche Fassung läuft gerade? Diese Frage war über Store, Update-Entitäten und
# Portainer hinweg nicht verlässlich zu beantworten — die drei widersprachen
# sich. Deshalb nennt das Panel seine eigene Version selbst, gelesen aus der
# config.yaml im Image, und daneben das, was der Supervisor für neu hält.

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


def _supervisor_versions() -> dict:
    """installed/latest straight from the Supervisor, bypassing every cache."""
    if not SUPERVISOR_TOKEN:
        return {}
    try:
        r = http.get('http://supervisor/addons/self/info',
                     headers={'Authorization': 'Bearer ' + SUPERVISOR_TOKEN},
                     timeout=10)
        if r.status_code != 200:
            return {}
        data = (r.json() or {}).get('data') or {}
    except (http.RequestException, ValueError):
        return {}
    return {'installed': data.get('version') or '',
            'latest': data.get('version_latest') or '',
            'update_available': bool(data.get('update_available'))}


# ── Home Assistant sensors ────────────────────────────────────────────────────

_sensor_warned = False
# Welche Bouncer-Entitäten zuletzt gemeldet wurden — verschwindet ein Bouncer,
# wird seine Entität entfernt statt auf dem letzten Wert stehenzubleiben.
_bouncer_entities: set = set()


def ha_sensors_enabled() -> bool:
    return bool(SUPERVISOR_TOKEN) and bool(load_config().get('ha_sensors', True))


def push_ha_sensors() -> None:
    """Report the numbers to Home Assistant so they can drive automations.

    Nothing here is worth failing a request over — every error is logged and
    swallowed.
    """
    if not ha_sensors_enabled():
        return
    client = get_client()
    state = client.ping()
    online = bool(state.get('ok'))
    decisions = local = alerts_24h = 0
    if online:
        try:
            stats = client.decision_stats()
            decisions = stats['total']
            local = sum(count for origin, count in stats['by_origin']
                        if origin in ('crowdsec', 'cscli'))
            alerts = [a for a in client.list_alerts(limit=ALERT_FETCH_LIMIT, since='24h')
                      if isinstance(a, dict)]
            alerts_24h = sum(1 for a in alerts if not _is_list_sync(a))
        except (LapiError, ValidationError) as e:
            log.warning("sensor update skipped: %s", e.code)
            online = False

    headers = {'Authorization': 'Bearer ' + SUPERVISOR_TOKEN}

    def _put(entity: str, payload: dict) -> bool:
        # requests does not raise on 4xx, and a silently rejected sensor is
        # worse than none — the answer code is checked and reported once.
        try:
            r = http.post(f'http://supervisor/core/api/states/{entity}',
                          headers=headers, json=payload, timeout=10)
        except http.RequestException:
            return False
        if r.status_code >= 300:
            global _sensor_warned
            if not _sensor_warned:
                _sensor_warned = True
                log.warning("Home Assistant rejected sensor %s (HTTP %d) — "
                            "further failures are not repeated", entity, r.status_code)
            return False
        return True

    def _drop(entity: str) -> None:
        try:
            http.delete(f'http://supervisor/core/api/states/{entity}',
                        headers=headers, timeout=10)
        except http.RequestException:
            pass

    sensors = [
        ('crowdpanel_decisions', decisions, 'CrowdPanel active decisions',
         'mdi:shield-lock', 'decisions'),
        ('crowdpanel_decisions_local', local, 'CrowdPanel own decisions',
         'mdi:shield-search', 'decisions'),
        ('crowdpanel_alerts_24h', alerts_24h, 'CrowdPanel detections (24h)',
         'mdi:alert', 'alerts'),
    ]
    ok = 0
    for sid, value, name, icon, unit in sensors:
        ok += _put(f'sensor.{sid}',
                   {'state': value,
                    'attributes': {'friendly_name': name, 'icon': icon,
                                   'unit_of_measurement': unit,
                                   'state_class': 'measurement'}})
    ok += _put('binary_sensor.crowdpanel_lapi',
               {'state': 'on' if online else 'off',
                'attributes': {'friendly_name': 'CrowdPanel LAPI reachable',
                               'icon': 'mdi:lan-connect',
                               'device_class': 'connectivity'}})
    total = len(sensors) + 1

    # Bouncer: je einer eine eigene Entität, dazu zwei Summen. Ein Bouncer, der
    # nicht mehr abholt, setzt keine Sperre mehr durch — ohne Sensor fällt genau
    # das niemandem auf.
    bstate = _bouncer_state()
    if bstate.get('available'):
        rows = bstate.get('bouncers') or []
        current = set()
        taken: dict = {}
        for b in rows:
            slug = _entity_slug(b.get('name'))
            taken[slug] = taken.get(slug, 0) + 1
            if taken[slug] > 1:
                slug = f'{slug}_{taken[slug]}'
            entity = f'sensor.crowdpanel_bouncer_{slug}'
            current.add(entity)
            is_stale = _bouncer_stale(b)
            iso = _iso_utc(b.get('last_pull'))
            ok += _put(entity, {
                'state': iso or 'unknown',
                'attributes': {
                    'friendly_name': 'CrowdPanel bouncer ' + str(b.get('name') or slug),
                    'icon': 'mdi:shield-off-outline' if is_stale else 'mdi:shield-check',
                    'device_class': 'timestamp',
                    'bouncer_name': b.get('name') or '',
                    'bouncer_type': b.get('type') or '',
                    'version': b.get('version') or '',
                    'ip_address': b.get('ip_address') or '',
                    'auth_type': b.get('auth_type') or '',
                    'revoked': bool(b.get('revoked')),
                    'derived': bool(b.get('auto_created')),
                    'stale': is_stale,
                }})
            # Derselbe Zustand noch einmal als Problem-Binärsensor: „an" heißt,
            # dieser Bouncer setzt gerade nichts durch. Automatisierungen und die
            # Problem-Anzeige in Home Assistant brauchen genau diese Form, ein
            # Zeitstempel taugt dafür nicht.
            problem = f'binary_sensor.crowdpanel_bouncer_{slug}'
            current.add(problem)
            ok += _put(problem, {
                'state': 'on' if is_stale else 'off',
                'attributes': {
                    'friendly_name': 'CrowdPanel bouncer ' + str(b.get('name') or slug),
                    'icon': 'mdi:shield-off-outline' if is_stale else 'mdi:shield-check',
                    'device_class': 'problem',
                    'bouncer_name': b.get('name') or '',
                    'bouncer_type': b.get('type') or '',
                    'version': b.get('version') or '',
                    'ip_address': b.get('ip_address') or '',
                    'auth_type': b.get('auth_type') or '',
                    'last_pull': iso,
                    'revoked': bool(b.get('revoked')),
                    'derived': bool(b.get('auto_created')),
                    'stale_seconds': BOUNCER_STALE_SECONDS,
                }})
            total += 2
        for gone in _bouncer_entities - current:
            _drop(gone)
        _bouncer_entities.clear()
        _bouncer_entities.update(current)

        stale_rows = [b for b in rows if _bouncer_stale(b)]
        listed = [{'name': b.get('name') or '',
                   'last_pull': _iso_utc(b.get('last_pull')),
                   'revoked': bool(b.get('revoked')),
                   'derived': bool(b.get('auto_created')),
                   'stale': _bouncer_stale(b)} for b in rows]
        ok += _put('sensor.crowdpanel_bouncers',
                   {'state': sum(1 for b in rows
                                 if not b.get('auto_created') and not b.get('revoked')),
                    'attributes': {'friendly_name': 'CrowdPanel bouncers',
                                   'icon': 'mdi:shield-account',
                                   'unit_of_measurement': 'bouncers',
                                   'state_class': 'measurement',
                                   'bouncers': listed}})
        ok += _put('sensor.crowdpanel_bouncers_stale',
                   {'state': len(stale_rows),
                    'attributes': {'friendly_name': 'CrowdPanel bouncers not pulling',
                                   'icon': 'mdi:shield-alert',
                                   'unit_of_measurement': 'bouncers',
                                   'state_class': 'measurement',
                                   'stale_seconds': BOUNCER_STALE_SECONDS,
                                   'bouncers': [b['name'] for b in listed if b['stale']]}})
        ok += _put('binary_sensor.crowdpanel_bouncers',
                   {'state': 'on' if stale_rows else 'off',
                    'attributes': {'friendly_name': 'CrowdPanel bouncer problem',
                                   'icon': 'mdi:shield-alert',
                                   'device_class': 'problem',
                                   'stale_seconds': BOUNCER_STALE_SECONDS,
                                   'bouncers': [b['name'] for b in listed if b['stale']]}})
        total += 3

    if ok and _verbose():
        log.info("Home Assistant sensors updated (%d of %d)", ok, total)


def _sensor_worker() -> None:
    while True:
        interval = _cfg_int('ha_sensor_interval', 300, 60, 86400)
        try:
            push_ha_sensors()
        except Exception:
            log.exception("sensor worker")
        time.sleep(interval)


# ── Startup ───────────────────────────────────────────────────────────────────

def _startup_checks() -> None:
    cfg = load_config()
    if str(cfg.get('password', '')) == 'changeme123':
        log.warning("The default password is still set — change it in the add-on options")
    url = str(cfg.get('lapi_url') or '').strip()
    if not url:
        log.warning("lapi_url is empty — set the CrowdSec Local API address")
    elif urlsplit(url).scheme not in ('http', 'https'):
        log.warning("lapi_url is not an http(s) address — CrowdPanel stays disconnected")
    if not str(cfg.get('machine_id') or '').strip() or not str(cfg.get('machine_password') or ''):
        log.warning("machine_id/machine_password are empty — run "
                    "'cscli -c <config> machines add crowdpanel --password <secret>' "
                    "and copy the credentials into the add-on options")
        return
    state = get_client().ping()
    if state.get('ok'):
        log.info("CrowdSec LAPI reachable at %s (%d ms)", url, state.get('ms', 0))
    else:
        log.warning("CrowdSec LAPI not usable yet: %s", state.get('code'))


if __name__ == '__main__':
    load_sessions()
    _startup_checks()

    if archive_enabled() and get_archive() is not None:
        threading.Thread(target=_archive_worker, daemon=True).start()
        log.info("alert archive enabled (%s)", ARCHIVE_PATH)
    elif archive_enabled():
        log.warning("alert archive could not be opened — history stays with the LAPI")

    if ha_sensors_enabled():
        threading.Thread(target=_sensor_worker, daemon=True).start()
        log.info("Home Assistant sensors enabled")
    elif not SUPERVISOR_TOKEN:
        log.info("no Supervisor token — Home Assistant sensors unavailable")

    def _shutdown(signum, frame):
        log.info("signal %s received — CrowdPanel is shutting down", signum)
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    log.info("CrowdPanel ready on port %d", PORT)
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
