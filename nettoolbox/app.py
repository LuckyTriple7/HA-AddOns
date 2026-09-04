#!/usr/bin/env python3
"""NetToolbox — network and mail diagnostics for Home Assistant.

Behind the Home Assistant Ingress proxy the Supervisor has already
authenticated the user, so no login is asked for. On the direct port the add-on
authenticates on its own. The same image also serves as a worker: give it a
token and it answers probe requests from another instance.
"""

import concurrent.futures
import functools
import json
import logging
import os
import re
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

import hasensors
import monitor
import settings as usersettings
import snapshots as dnssnapshots
import techrules
import users as useraccounts
import wapimport
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
BLOCKS_PATH = _DATA + '/blocks.json'
SECRET_PATH = _DATA + '/secret.key'
HISTORY_PATH = _DATA + '/history.json'
MONITOR_DB_PATH = _DATA + '/monitors.db'
SNAPSHOT_DB_PATH = _DATA + '/snapshots.db'
USERS_DB_PATH = _DATA + '/users.db'
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
    # The generated password itself never goes to the log -- add-on logs are
    # visible to anyone with HA UI access and may be retained/exported far
    # longer than options.json. It's written to CONFIG_PATH above; that file
    # already needs the same filesystem access as reading this log would.
    log.info("no options.json found — created one with username 'admin' and "
             "a generated password. Read it from %s.", CONFIG_PATH)


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
        allow_port_check=bool(cfg.get('port_check_enabled', True)),
        tech_extra_rules=bool(usersettings.effective(cfg).get('tech_extra_rules')),
        user_agent='NetToolbox/' + (APP_VERSION or '0'))


def notify_config() -> dict:
    """Read fresh every time a notification is about to be sent, so a saved
    change takes effect on the next monitor run without a restart. Add-on
    options are the fallback; settings.json (edited in the UI) wins."""
    return usersettings.effective(load_config())


_monitor_store = monitor.MonitorStore(MONITOR_DB_PATH)
_snapshot_store = dnssnapshots.SnapshotStore(SNAPSHOT_DB_PATH)
_user_store = useraccounts.UserStore(USERS_DB_PATH)


# ── Sessions ──────────────────────────────────────────────────────────────────

sessions: dict = {}
_sessions_lock = threading.Lock()


def save_sessions() -> None:
    try:
        now = time.time()
        with open(SESSIONS_PATH, 'w', encoding='utf-8') as f:
            json.dump({k: v for k, v in sessions.items() if v['exp'] > now}, f)
    except Exception:
        log.warning("sessions could not be saved")


def _session_value(raw) -> dict:
    """Bis 0.1.43 stand hinter dem Token nur die Ablaufzeit -- es gab ja nur
    ein Konto. Solche Einträge gelten weiter und zählen als der Betreiber;
    sonst würfe das Update jeden Angemeldeten hinaus."""
    if isinstance(raw, (int, float)):
        return {'exp': float(raw), 'uid': useraccounts.OPTIONS_ADMIN_ID,
                'must_change': False}
    if isinstance(raw, dict) and isinstance(raw.get('exp'), (int, float)):
        try:
            uid = int(raw.get('uid') or useraccounts.OPTIONS_ADMIN_ID)
        except (TypeError, ValueError):
            return {}
        return {'exp': float(raw['exp']), 'uid': uid,
                'must_change': bool(raw.get('must_change'))}
    return {}


def load_sessions() -> None:
    global sessions
    try:
        with open(SESSIONS_PATH, encoding='utf-8') as f:
            data = json.load(f)
        now = time.time()
        restored = {}
        for token, raw in (data or {}).items():
            value = _session_value(raw)
            if value and value['exp'] > now:
                restored[str(token)] = value
        sessions = restored
        if sessions:
            log.info("sessions restored: %d active", len(sessions))
    except FileNotFoundError:
        pass
    except Exception:
        log.warning("sessions could not be loaded")


def create_session(hours: int, uid: int, must_change: bool = False) -> str:
    token = secrets.token_hex(32)
    with _sessions_lock:
        sessions[token] = {'exp': time.time() + hours * 3600, 'uid': int(uid),
                           'must_change': bool(must_change)}
        save_sessions()
    return token


def session_info(token) -> dict:
    """Leeres dict = keine gültige Sitzung."""
    if not token or token not in sessions:
        return {}
    value = sessions[token]
    if time.time() > value['exp']:
        with _sessions_lock:
            sessions.pop(token, None)
        return {}
    return dict(value, token=token)


def clear_change_flag(token: str) -> None:
    """Nach dem Kennwortwechsel arbeitet dieselbe Sitzung weiter -- ein
    erzwungener zweiter Anmeldevorgang wäre reine Schikane."""
    with _sessions_lock:
        if token in sessions:
            sessions[token]['must_change'] = False
            save_sessions()


def drop_user_sessions(uid: int) -> int:
    """Gesperrt, gelöscht oder Kennwort zurückgesetzt: laufende Sitzungen des
    Kontos enden sofort und nicht erst in 24 Stunden."""
    with _sessions_lock:
        gone = [t for t, v in sessions.items() if v['uid'] == int(uid)]
        for token in gone:
            sessions.pop(token, None)
        if gone:
            save_sessions()
    return len(gone)


# ── Rate limiting ─────────────────────────────────────────────────────────────

RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW = 600
RATE_LIMIT_BLOCK = 900

_failed_attempts: dict = defaultdict(list)
_blocked_ips: dict = {}
_rate_lock = threading.Lock()
# One notification per block, not one per attempt -- an attack that keeps
# knocking must not turn the lockout itself into a mail flood. Holds when the
# already-notified block runs out; anything older means "a new block, notify".
_notified_blocks: dict = {}


def get_client_ip(req) -> str:
    return req.remote_addr or 'unknown'


def save_blocks() -> None:
    """Blocks and attempt counters outlive a restart -- an add-on update in the
    middle of an attack used to hand the attacker a clean slate. The caller
    holds _rate_lock."""
    try:
        now = time.time()
        attempts = {ip: [t for t in stamps if now - t < RATE_LIMIT_WINDOW]
                    for ip, stamps in _failed_attempts.items()}
        data = {'blocked': {ip: ts for ip, ts in _blocked_ips.items() if ts > now},
                'attempts': {ip: ts for ip, ts in attempts.items() if ts}}
        with open(BLOCKS_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f)
    except Exception:
        log.warning("login blocks could not be saved")


def load_blocks() -> None:
    try:
        with open(BLOCKS_PATH, encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        return
    except Exception:
        log.warning("login blocks could not be loaded")
        return
    if not isinstance(data, dict):
        return
    now = time.time()
    with _rate_lock:
        for ip, until in (data.get('blocked') or {}).items():
            if isinstance(until, (int, float)) and until > now:
                _blocked_ips[str(ip)] = float(until)
                # The notification for this block already went out before the
                # restart -- restoring it must not send a second one.
                _notified_blocks[str(ip)] = float(until)
        for ip, stamps in (data.get('attempts') or {}).items():
            keep = [float(t) for t in (stamps or [])
                    if isinstance(t, (int, float)) and now - t < RATE_LIMIT_WINDOW]
            if keep:
                _failed_attempts[str(ip)] = keep
        active = len(_blocked_ips)
    if active:
        log.info("login blocks restored: %d active", active)


def is_rate_limited(ip: str) -> bool:
    now = time.time()
    with _rate_lock:
        until = _blocked_ips.get(ip)
        if until is not None:
            if now < until:
                return True
            del _blocked_ips[ip]
            _failed_attempts.pop(ip, None)
            save_blocks()
            return False
        _failed_attempts[ip] = [t for t in _failed_attempts[ip]
                                if now - t < RATE_LIMIT_WINDOW]
        return False


def record_failed_attempt(ip: str, who: str = '') -> None:
    now = time.time()
    with _rate_lock:
        recent = [t for t in _failed_attempts[ip] if now - t < RATE_LIMIT_WINDOW]
        recent.append(now)
        _failed_attempts[ip] = recent
        blocked = len(recent) >= RATE_LIMIT_MAX
        fresh = False
        if blocked:
            _blocked_ips[ip] = now + RATE_LIMIT_BLOCK
            fresh = _notified_blocks.get(ip, 0.0) < now
            _notified_blocks[ip] = now + RATE_LIMIT_BLOCK
        save_blocks()
    if blocked:
        log.warning("login blocked for %d minutes after too many failures",
                    RATE_LIMIT_BLOCK // 60)
        if fresh:
            notify_login_event('blocked', ip, len(recent), who)


def clear_failed_attempts(ip: str) -> None:
    with _rate_lock:
        had = _failed_attempts.pop(ip, None) is not None
        had = (_blocked_ips.pop(ip, None) is not None) or had
        _notified_blocks.pop(ip, None)
        if had:
            save_blocks()


# ── Anmelde-Benachrichtigungen ────────────────────────────────────────────────
# Dieselben Kanäle wie die Wächter (settings.json bzw. Add-on-Optionen) und
# bewusst derselbe fest deutsche Wortlaut wie in monitor.py -- eine
# Benachrichtigung muss ohne die Übersetzungsschicht der Oberfläche auskommen.


def _notify_async(subject: str, body: str, email: bool, telegram: bool) -> None:
    """Im Hintergrund zustellen: ein SMTP-Server, der nicht antwortet, darf die
    Antwort auf den Anmeldeversuch nicht seine ganze Zeitgrenze lang aufhalten."""
    def run():
        cfg = notify_config()
        if email:
            ok, err = monitor.send_email(cfg, subject, body)
            if not ok and err != 'not_configured':
                log.warning("login notification: email failed: %s", err)
        if telegram:
            ok, err = monitor.send_telegram(cfg, subject + "\n" + body)
            if not ok and err != 'not_configured':
                log.warning("login notification: telegram failed: %s", err)
    threading.Thread(target=run, daemon=True).start()


# Host-Namen, IPv4 und IPv6 in Klammern, jeweils mit optionalem Port -- alles
# andere kommt nicht in die Nachricht.
_HOST_SHAPE = re.compile(r'^[A-Za-z0-9._:\[\]-]{1,100}$')


def _login_origin() -> str:
    """Die Adresse, die im Browser stand. Steht ein Reverse-Proxy davor, ist
    das die Domain und nicht Port 17798 -- "Anmeldung am Direktport 17798" ist
    dann schlicht falsch. Der Host-Header kommt vom Aufrufer und ist damit
    fälschbar; er wird deshalb nur übernommen, wenn er wie ein Hostname
    aussieht, und nie als anklickbarer Link ausgegeben."""
    try:
        host = request.host or ''
    except RuntimeError:  # außerhalb eines Requests aufgerufen
        host = ''
    if host and _HOST_SHAPE.match(host):
        return host
    return 'Port %d' % PORT


def _safe_name(raw: str) -> str:
    """Der Benutzername aus dem Formular kommt vom Aufrufer und landet in
    einer Mail. Nur die Zeichen, die ein Name haben darf -- alles andere wäre
    ein Weg, fremden Text in die Nachricht zu schreiben."""
    name = ''.join(c for c in str(raw or '') if c.isalnum() or c in '._-')
    return name[:32]


def public_base_url() -> str:
    """Adresse, unter der NetToolbox von außen erreichbar ist -- für Links in
    Mails. Eingetragenes sticht Ermitteltes: wer ein Konto über Ingress
    anlegt, ruft gerade Home Assistant auf, und dessen Adresse führt niemanden
    zur Anmeldung. Ohne Eintrag und über Ingress gibt es lieber keinen Link
    als einen falschen."""
    raw = str(notify_config().get('public_url') or '').strip()
    if raw:
        parts = urlsplit(raw)
        if (parts.scheme in ('http', 'https') and parts.netloc
                and _HOST_SHAPE.match(parts.netloc)):
            return urlunsplit((parts.scheme, parts.netloc,
                               parts.path.rstrip('/'), '', ''))
        return ''
    try:
        if _is_ingress():
            return ''
        host = request.host or ''
    except RuntimeError:
        return ''
    if host and _HOST_SHAPE.match(host):
        return request.scheme + '://' + host
    return ''


def notify_login_event(kind: str, ip: str, attempts: int = 0,
                       who: str = '') -> None:
    """kind 'blocked' -> zu viele Fehlversuche, 'ok' -> geglückte Anmeldung am
    Direktport. Über Ingress kommt hier nichts an: dort hat der Supervisor
    bereits angemeldet, es gibt kein Anmeldeformular."""
    cfg = notify_config()
    when = time.strftime('%Y-%m-%d %H:%M:%S')
    origin = _login_origin()
    if kind == 'blocked':
        email = bool(cfg.get('notify_login_fail_email', True))
        telegram = bool(cfg.get('notify_login_fail_telegram', True))
        subject = '🔴 [NetToolbox] Anmeldung gesperrt'
        name = _safe_name(who)
        body = ("Zu viele fehlgeschlagene Anmeldeversuche.\n\n"
                f"Aufgerufen über: {origin}\n"
                f"Benutzername: {name or '?'}\n"
                f"IP-Adresse: {ip}\n"
                f"Versuche: {attempts} in {RATE_LIMIT_WINDOW // 60} Minuten\n"
                f"Gesperrt für: {RATE_LIMIT_BLOCK // 60} Minuten\n"
                f"Zeitpunkt: {when}\n\n"
                "-- NetToolbox")
    else:
        email = bool(cfg.get('notify_login_ok_email', False))
        telegram = bool(cfg.get('notify_login_ok_telegram', False))
        subject = '🔵 [NetToolbox] Anmeldung erfolgreich'
        body = ("Erfolgreiche Anmeldung.\n\n"
                f"Aufgerufen über: {origin}\n"
                f"Benutzername: {_safe_name(who) or '?'}\n"
                f"IP-Adresse: {ip}\n"
                f"Zeitpunkt: {when}\n\n"
                "-- NetToolbox")
    if not email and not telegram:
        return
    _notify_async(subject, body, email, telegram)


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


# Hinter Ingress hat der Supervisor bereits angemeldet -- wer dort ankommt,
# bedient Home Assistant und damit auch die Add-on-Optionen, ist also ohnehin
# Betreiber. Ein eigenes Konto gibt es dort bewusst nicht: die Benutzer-
# Kopfzeilen des Supervisors kämen vom Client und wären fälschbar, sobald
# derselbe Port auch im LAN erreichbar ist. Mehrbenutzerbetrieb gilt deshalb
# nur für den Weg über den eigenen Port bzw. die Domain davor.
_INGRESS_ADMIN = {'id': useraccounts.OPTIONS_ADMIN_ID, 'username': 'ingress',
                  'is_admin': True, 'must_change': False, 'blocked': False,
                  'modules': '*', 'daily_quota': 0, 'via': 'ingress'}


def _options_admin() -> dict:
    """Das Konto aus den Add-on-Optionen. Es steht nicht in users.db und ist
    immer Betreiber -- es ist der Weg zurück, wenn in der Benutzerverwaltung
    etwas verriegelt wurde."""
    return {'id': useraccounts.OPTIONS_ADMIN_ID,
            'username': str(load_config().get('username') or 'admin'),
            'is_admin': True, 'must_change': False, 'blocked': False,
            'modules': '*', 'daily_quota': 0, 'via': 'options'}


def current_user() -> dict:
    """Leeres dict = niemand angemeldet. Je Anfrage einmal ermittelt."""
    cached = getattr(g, 'user', None)
    if cached is not None:
        return cached
    user = {}
    if _is_ingress():
        user = dict(_INGRESS_ADMIN)
    else:
        info = session_info(request.cookies.get('session'))
        if info:
            if info['uid'] == useraccounts.OPTIONS_ADMIN_ID:
                user = _options_admin()
            elif _user_store.available():
                try:
                    row = _user_store.get(info['uid'])
                except (useraccounts.UserError, Exception):
                    row = {}
                # Gesperrt oder gelöscht wirkt sofort, nicht erst beim
                # nächsten Anmelden.
                if row and not row.get('blocked'):
                    user = dict(row, via='account')
            if user:
                user['must_change'] = bool(info.get('must_change')) or bool(
                    user.get('must_change'))
                user['token'] = info['token']
    g.user = user
    return user


def current_uid() -> int:
    """Kennung des Anfragenden. Außerhalb einer Anfrage -- etwa aus einem
    Hintergrund-Thread -- gilt der Betreiber."""
    try:
        return int(current_user().get('id') or 0)
    except RuntimeError:
        return useraccounts.OPTIONS_ADMIN_ID


def _logged_in() -> bool:
    return bool(current_user())


# ── Module und Tageskontingent ────────────────────────────────────────────────
# Freischaltbar sind die Reiter, hinter denen Prüfungen stecken. "monitor"
# fehlt absichtlich -- Wächter sind Betreibersache; "history" ebenfalls -- der
# eigene Verlauf ist privat und immer sichtbar.

MODULES = ('report', 'dns', 'mail', 'reverse', 'tls', 'whois', 'http')

# Welche Prüfung zu welchem Reiter gehört. Aus der Oberfläche abgeleitet, nicht
# geraten: eine fehlende Zuordnung fällt beim Start auf (siehe _startup_checks).
PROBE_MODULE = {
    'dns': 'dns', 'dns_all': 'dns', 'txt': 'dns', 'soa': 'dns',
    'propagation': 'dns', 'dnssec': 'dns', 'aaaa_guard': 'dns',
    'mx': 'mail', 'mail_health': 'mail', 'blacklist': 'mail', 'dane': 'mail',
    'mailheader': 'mail', 'smtp': 'mail', 'spf': 'mail', 'dkim': 'mail',
    'dmarc': 'mail', 'mta_sts': 'mail', 'tls_rpt': 'mail', 'bimi': 'mail',
    'reverse': 'reverse', 'ipinfo': 'reverse', 'ping': 'reverse',
    'traceroute': 'reverse', 'ports': 'reverse', 'dualstack': 'reverse',
    'tls': 'tls',
    'whois': 'whois',
    'http': 'http', 'quic': 'http', 'seo': 'http', 'tech': 'http',
}


def clean_modules(raw) -> str:
    """'*' heißt alle. Sonst die bekannten Namen, kommagetrennt und in fester
    Reihenfolge -- was die Oberfläche schickt, wird nie übernommen wie es ist."""
    if raw in (None, '', '*'):
        return '*'
    if isinstance(raw, (list, tuple)):
        parts = [str(p).strip() for p in raw]
    else:
        parts = str(raw).replace(',', ' ').split()
    keep = [m for m in MODULES if m in parts]
    return ','.join(keep)


def user_modules(user: dict) -> set:
    raw = str(user.get('modules') or '*')
    if raw == '*':
        return set(MODULES)
    return {m for m in raw.replace(',', ' ').split() if m in MODULES}


def allowed_modules() -> list:
    """Reihenfolge wie in MODULES, damit die Oberfläche stabil bleibt."""
    user = current_user()
    if user.get('is_admin'):
        return list(MODULES)
    allowed = user_modules(user)
    return [m for m in MODULES if m in allowed]


def require_module(module: str) -> None:
    if not module:
        return
    user = current_user()
    if user.get('is_admin'):
        return
    if module not in user_modules(user):
        raise useraccounts.UserError('module_disabled')


def _today() -> str:
    return time.strftime('%Y-%m-%d')


def quota_state() -> dict:
    """Was die Oberfläche über das eigene Kontingent wissen darf."""
    user = current_user()
    limit = int(user.get('daily_quota') or 0)
    if user.get('is_admin') or limit <= 0 or not _user_store.available():
        return {'limit': 0, 'used': 0}
    return {'limit': limit,
            'used': _user_store.usage_today(user['id'], _today())}


def spend_quota() -> None:
    """Eine Abfrage abbuchen. Ein Gesamtbericht kostet ebenfalls genau eine --
    er beantwortet eine Frage, auch wenn intern neun Prüfungen laufen."""
    user = current_user()
    limit = int(user.get('daily_quota') or 0)
    if user.get('is_admin') or limit <= 0 or not _user_store.available():
        return
    if not _user_store.spend(user['id'], _today(), limit):
        raise useraccounts.UserError('quota_exhausted')


def log_activity(probe: str, target: str, level: str) -> None:
    """Protokoll für den Betreiber. Nur für angelegte Konten: das Konto aus
    den Optionen steht nicht in der Datenbank, seine Zeilen hätten dort kein
    Gegenüber."""
    uid = current_uid()
    if uid == useraccounts.OPTIONS_ADMIN_ID or not _user_store.available():
        return
    _user_store.log_activity(uid, probe, target, level)


def _is_admin() -> bool:
    return bool(current_user().get('is_admin'))


def _must_change() -> bool:
    return bool(current_user().get('must_change'))


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
    'bad_port': 400, 'ipv6_unsupported': 400,
    'too_many_values': 400, 'private_target': 403,
    'redirect_loop': 400, 'too_many_redirects': 400,
    'nxdomain': 404, 'no_records': 404, 'whois_no_referral': 404,
    'no_mail_host': 404, 'null_mx': 404, 'not_html': 415,
    'empty_header': 400, 'header_too_large': 413,
    'dane_unreachable': 502, 'dane_no_starttls': 502, 'dane_no_certificate': 502,
    'port_check_disabled': 403, 'too_many_ports': 400,
    'dns_timeout': 504, 'http_timeout': 504, 'worker_timeout': 504,
    'tls_timeout': 504, 'whois_timeout': 504, 'smtp_timeout': 504,
    'quic_response_timeout': 504, 'ping_timeout': 504, 'traceroute_timeout': 504,
    'geoip_failed': 400, 'geoip_rate_limited': 429, 'geoip_error': 502,
    'geoip_bad_response': 502,
    'worker_auth': 502, 'worker_unreachable': 502, 'worker_tls': 502,
    'worker_bad_response': 502, 'worker_error': 502,
    'monitor_not_found': 404, 'bad_probe': 400,
    'snapshot_not_found': 404, 'snapshot_store_broken': 503,
    'snapshot_domain_mismatch': 400,
    'user_exists': 409, 'user_not_found': 404, 'bad_username': 400,
    'bad_email': 400, 'weak_password': 400,
    'bad_quota': 400, 'self_target': 409, 'user_store_broken': 503,
    'module_disabled': 403, 'quota_exhausted': 429,
}


def api(rule: str, methods=('GET',), admin: bool = False):
    """Route decorator: auth, CSRF and uniform error mapping in one place."""
    def deco(fn):
        @app.route(rule, methods=list(methods), endpoint='api_' + fn.__name__)
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if not _logged_in():
                return jsonify({'error': 'unauthorized'}), 401
            # Solange das Startkennwort gilt, ist nichts anderes zu tun als
            # es zu wechseln -- sonst wäre der Zwang keiner.
            if _must_change():
                return jsonify({'error': 'password_change_required'}), 403
            if admin and not _is_admin():
                return jsonify({'error': 'forbidden'}), 403
            if request.method not in ('GET', 'HEAD'):
                if not _origin_ok() or not _csrf_ok():
                    return jsonify({'error': 'csrf'}), 403
            try:
                return fn(*args, **kwargs)
            except ProbeError as e:
                return (jsonify({'error': e.code, 'detail': e.detail}),
                        _ERROR_STATUS.get(e.code, 502))
            except monitor.MonitorError as e:
                return jsonify({'error': e.code}), _ERROR_STATUS.get(e.code, 400)
            except dnssnapshots.SnapshotError as e:
                return jsonify({'error': e.code}), _ERROR_STATUS.get(e.code, 400)
            except useraccounts.UserError as e:
                return jsonify({'error': e.code}), _ERROR_STATUS.get(e.code, 400)
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
    # Seit es mehrere Konten gibt, gehört jede Zeile zu einem davon. Ohne die
    # Kennung läge der Verlauf des einen offen vor dem anderen.
    entry = dict(entry, uid=current_uid())
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
    # Fixed-literal lookup, not a membership-checked passthrough of the
    # tainted path segment -- the cookie value is always one of these two
    # hardcoded strings, never the request data itself.
    lang = {'de': 'de', 'en': 'en'}.get(lang, 'en')
    resp = make_response(redirect(_safe_next(request.args.get('next', '/'))))
    resp.set_cookie('lang', lang, max_age=365 * 24 * 3600, samesite='Lax')
    return resp


def _check_credentials(name: str, secret: str):
    """Erst die angelegten Konten, dann das Konto aus den Add-on-Optionen.

    Ein gesperrtes Konto verhält sich wie ein falsches Kennwort -- welcher
    Name existiert, geht den Anfragenden nichts an.
    """
    if _user_store.available():
        user = _user_store.verify(name, secret)
        if user is not None:
            return dict(user, via='account')
    cfg = load_config()
    user_ok = secrets.compare_digest(name, str(cfg.get('username') or ''))
    # Beide Seiten hashen, damit ein falscher Name genauso lange dauert wie
    # ein falsches Kennwort.
    stored = generate_password_hash(str(cfg.get('password') or ''))
    pass_ok = check_password_hash(stored, secret)
    if user_ok and pass_ok:
        return _options_admin()
    return None


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
            name = request.form.get('username', '')
            secret = request.form.get('password', '')
            user = _check_credentials(name, secret)
            if user is not None:
                clear_failed_attempts(ip)
                notify_login_event('ok', ip, who=user['username'])
                hours = _cfg_int('session_hours', 24, 1, 720)
                if user['id'] != useraccounts.OPTIONS_ADMIN_ID:
                    _user_store.touch_login(user['id'])
                forced = bool(user.get('must_change'))
                resp = make_response(redirect(_safe_next(
                    '/password' if forced else '/')))
                resp.set_cookie('session',
                                create_session(hours, user['id'], forced),
                                httponly=True, samesite='Lax',
                                secure=request.is_secure, max_age=hours * 3600)
                return resp
            record_failed_attempt(ip, name)
            error = t.get('error_credentials', 'Invalid credentials.')
    return render_template('login.html', t=t, lang=lang, csrf=g.csrf,
                           error=error)


@app.route('/password', methods=['GET', 'POST'])
def change_password():
    """Eigenes Kennwort wechseln -- freiwillig oder erzwungen, wenn noch das
    Startkennwort gilt."""
    lang = detect_language(request)
    t = load_translations(lang)
    user = current_user()
    if not user:
        return redirect(url_for('login'))
    if user['id'] == useraccounts.OPTIONS_ADMIN_ID:
        # Dieses Kennwort steht in den Add-on-Optionen und wird dort geändert.
        return redirect(_safe_next('/'))
    error = ''
    if request.method == 'POST':
        if not _origin_ok() or not _csrf_ok():
            error = t.get('error_expired', 'Form expired.')
        else:
            current = request.form.get('current', '')
            fresh = request.form.get('new', '')
            again = request.form.get('again', '')
            if _user_store.verify(user['username'], current) is None:
                error = t.get('error_credentials', 'Invalid credentials.')
            elif fresh != again:
                error = t.get('pw_mismatch', 'Passwords do not match.')
            elif fresh == current:
                error = t.get('pw_same', 'Choose a different password.')
            else:
                try:
                    _user_store.set_password(user['id'], fresh,
                                             must_change=False)
                except useraccounts.UserError:
                    error = t.get('pw_weak', 'Password too short.')
                else:
                    clear_change_flag(user.get('token', ''))
                    log.info("password changed for an account")
                    return redirect(_safe_next('/'))
    return render_template('password.html', t=t, lang=lang, csrf=g.csrf,
                           error=error, username=user['username'],
                           forced=bool(user.get('must_change')),
                           minimum=useraccounts.PASSWORD_MIN)


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
    if _must_change():
        return redirect(url_for('change_password'))
    user = current_user()
    lang = detect_language(request)
    return render_template(
        'index.html', t=load_translations(lang), lang=lang, csrf=g.csrf,
        version=APP_VERSION, ingress=_is_ingress(),
        is_admin=bool(user.get('is_admin')),
        modules=allowed_modules(),
        account=(user['username'] if user.get('via') == 'account' else ''),
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
        'ha_sensors': ha_sensors_enabled(),
        'resolvers': build_context().resolvers,
        'quota': quota_state(),
        'modules': allowed_modules(),
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
    require_module(PROBE_MODULE.get(name))
    spend_quota()
    answer = get_backend().run(name, params)
    result = answer.get('result') or {}
    target = str(params.get('domain') or params.get('name')
                 or params.get('ip') or params.get('target') or '')[:253]
    history_add({
        'ts': int(time.time()),
        'probe': name,
        'target': target,
        'level': result.get('level', ''),
        'backend': answer.get('backend', 'local'),
        'ms': answer.get('ms', 0),
    })
    log_activity(name, target, result.get('level', ''))
    return jsonify({'probe': name, 'result': result,
                    'backend': answer.get('backend', 'local'),
                    'worker': answer.get('worker') or {},
                    'ms': answer.get('ms', 0)})


REPORT_STEPS = (
    # (Prüfung, Parametername). Reihenfolge = Reihenfolge im Bericht; die
    # Ausführung selbst läuft parallel, weil jede Prüfung für sich steht.
    ('dns_all', 'name'),
    ('dnssec', 'name'),
    ('whois', 'domain'),
    ('mail_health', 'domain'),
    ('mx', 'domain'),
    ('tls', 'target'),
    ('http', 'target'),
    ('seo', 'target'),
    ('tech', 'target'),
)
REPORT_WORKERS = 4
TECH_RULES_CHECK_SECONDS = 6 * 3600


def _report_step(name: str, params: dict) -> dict:
    """Eine Prüfung für den Gesamtbericht. Ein Fehlschlag ist ein Ergebnis:
    er wird als Zeile im Bericht vermerkt und reißt nie den ganzen Bericht
    mit — genau wie beim Monitoring."""
    try:
        answer = get_backend().run(name, params)
        return {'probe': name, 'result': answer.get('result') or {},
                'ms': answer.get('ms', 0)}
    except ProbeError as e:
        return {'probe': name, 'error': e.code, 'detail': e.detail[:120]}
    except Exception as e:  # noqa: BLE001 — ein Bericht bricht nie ganz ab
        log.warning("report step %s failed: %s", name, type(e).__name__)
        return {'probe': name, 'error': 'internal'}


@api('/api/report', methods=('POST',))
def report():
    body = request.get_json(silent=True) or {}
    domain = probes.clean_domain(str(body.get('domain') or ''))
    require_module('report')
    # Jede Teilprüfung zählt einzeln gegen das Rate-Limit, sonst wäre ein
    # Bericht ein Weg, es zu umgehen. Gegen das Tageskontingent zählt er
    # dagegen als eine Abfrage -- er beantwortet eine Frage.
    if not all(probe_budget_left() for _ in range(len(REPORT_STEPS) + 1)):
        return jsonify({'error': 'rate_limited'}), 429
    spend_quota()
    log_activity('report', domain, '')

    started = time.time()
    steps = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=REPORT_WORKERS) as pool:
        futures = {pool.submit(_report_step, name, {key: domain}): name
                   for name, key in REPORT_STEPS}
        done = {futures[f]: f.result() for f in
                concurrent.futures.as_completed(futures)}
    steps = [done[name] for name, _key in REPORT_STEPS if name in done]

    # Die Sperrlisten-Prüfung braucht erst eine IP, kommt deshalb hinterher.
    addresses = []
    for step in steps:
        if step['probe'] == 'dns_all':
            for record_set in (step.get('result') or {}).get('sets', []):
                if record_set['type'] == 'A':
                    addresses = record_set['records']
    if addresses:
        steps.append(_report_step('blacklist', {'ip': addresses[0]}))

    levels = [(s.get('result') or {}).get('level', '') for s in steps]
    level = ('fail' if 'fail' in levels else
             'warn' if 'warn' in levels else
             'info' if 'info' in levels else 'ok')
    history_add({'ts': int(started), 'probe': 'report', 'target': domain,
                 'level': level, 'backend': 'local',
                 'ms': int((time.time() - started) * 1000)})
    return jsonify({'domain': domain, 'ip': addresses[0] if addresses else '',
                    'steps': steps, 'level': level,
                    'ms': int((time.time() - started) * 1000),
                    'generated': int(started)})


def _snapshot_store_ready():
    if _snapshot_store.broken:
        raise dnssnapshots.SnapshotError('snapshot_store_broken')
    return _snapshot_store


@api('/api/snapshots', methods=('GET', 'POST'))
def snapshots_route():
    store = _snapshot_store_ready()
    require_module('dns')
    if request.method == 'GET':
        domain = str(request.args.get('domain') or '').strip().lower()[:253]
        return jsonify({'snapshots': store.list(domain)})
    if not probe_budget_left():
        return jsonify({'error': 'rate_limited'}), 429
    body = request.get_json(silent=True) or {}
    domain = probes.clean_domain(str(body.get('domain') or ''))
    label = str(body.get('label') or '')[:80]
    spend_quota()
    log_activity('snapshot', domain, '')
    records = dnssnapshots.capture(build_context(), domain)
    return jsonify({'snapshot': store.add(domain, records, label)})


@api('/api/snapshots/<int:snapshot_id>', methods=('GET', 'DELETE'))
def snapshot_route(snapshot_id: int):
    store = _snapshot_store_ready()
    require_module('dns')
    if request.method == 'DELETE':
        store.delete(snapshot_id)
        return jsonify({'ok': True})
    return jsonify({'snapshot': store.get(snapshot_id)})


@api('/api/snapshots/<int:snapshot_id>/compare', methods=('POST',))
def snapshot_compare(snapshot_id: int):
    """Gegen den jetzigen Stand oder gegen eine zweite Aufnahme."""
    store = _snapshot_store_ready()
    require_module('dns')
    snapshot = store.get(snapshot_id)
    body = request.get_json(silent=True) or {}
    against = str(body.get('against') or 'live')
    if against == 'live':
        if not probe_budget_left():
            return jsonify({'error': 'rate_limited'}), 429
        spend_quota()
        other = {'id': 0, 'domain': snapshot['domain'], 'ts': int(time.time()),
                 'label': '', 'records': dnssnapshots.capture(build_context(),
                                                              snapshot['domain'])}
    else:
        try:
            other = store.get(int(against))
        except (TypeError, ValueError):
            raise dnssnapshots.SnapshotError('snapshot_not_found')
        if other['domain'] != snapshot['domain']:
            raise dnssnapshots.SnapshotError('snapshot_domain_mismatch')
    # Immer aelter -> neuer, egal in welcher Reihenfolge die beiden kamen:
    # "hinzugefuegt" soll heissen, dass es jetzt da ist und vorher nicht.
    older, newer = ((snapshot, other) if snapshot['ts'] <= other['ts']
                    else (other, snapshot))
    return jsonify({'domain': snapshot['domain'],
                    'before': {'id': older['id'], 'ts': older['ts']},
                    'after': {'id': newer['id'], 'ts': newer['ts']},
                    'diff': dnssnapshots.compare(older['records'],
                                                 newer['records'])})


def _history_rows_for(uid: int) -> list:
    with _history_lock:
        rows = list(_history)
    # Zeilen ohne Kennung stammen aus der Zeit vor der Benutzerverwaltung und
    # gehören damit dem Betreiber.
    return [row for row in rows if int(row.get('uid') or 0) == uid]


@api('/api/history')
def history():
    return jsonify({'rows': _history_rows_for(current_uid())[:_history_limit()]})


@api('/api/history/clear', methods=('POST',))
def history_clear():
    uid = current_uid()
    with _history_lock:
        keep = [row for row in _history if int(row.get('uid') or 0) != uid]
        _history.clear()
        _history.extend(keep)
        rows = list(_history)
    try:
        if rows:
            with open(HISTORY_PATH, 'w', encoding='utf-8') as f:
                json.dump(rows, f)
        else:
            os.remove(HISTORY_PATH)
    except OSError:
        pass
    except Exception:
        log.warning("history could not be saved")
    return jsonify({'ok': True})


# ── Monitoring ────────────────────────────────────────────────────────────────


@api('/api/monitors', admin=True)
def monitors_list():
    return jsonify({'rows': _monitor_store.list_monitors(),
                    'probes': sorted(monitor.MONITOR_PROBES),
                    'available': _monitor_store.available()})


@api('/api/monitors', methods=('POST',), admin=True)
def monitors_create():
    body = request.get_json(silent=True) or {}
    name = str(body.get('name') or '').strip()
    target = str(body.get('target') or '').strip()
    probe_name = str(body.get('probe') or '')
    if not name or not target:
        raise ProbeError('empty_target')
    if probe_name not in monitor.MONITOR_PROBES:
        raise monitor.MonitorError('bad_probe')
    mid = _monitor_store.create_monitor(
        name, probe_name, target,
        interval_hours=int(body.get('interval_hours') or 6),
        notify_email=bool(body.get('notify_email', True)),
        notify_telegram=bool(body.get('notify_telegram', True)),
        enabled=bool(body.get('enabled', True)))
    push_ha_sensors()
    return jsonify({'id': mid})


@api('/api/monitors/<int:monitor_id>', methods=('PUT',), admin=True)
def monitors_update(monitor_id: int):
    body = request.get_json(silent=True) or {}
    fields = {k: body[k] for k in
             ('name', 'probe', 'target', 'interval_hours', 'enabled',
              'notify_email', 'notify_telegram') if k in body}
    _monitor_store.update_monitor(monitor_id, **fields)
    push_ha_sensors()
    return jsonify({'ok': True})


@api('/api/monitors/<int:monitor_id>', methods=('DELETE',), admin=True)
def monitors_delete(monitor_id: int):
    _monitor_store.get_monitor(monitor_id)
    _monitor_store.delete_monitor(monitor_id)
    push_ha_sensors()
    return jsonify({'ok': True})


@api('/api/monitors/<int:monitor_id>/run', methods=('POST',), admin=True)
def monitors_run(monitor_id: int):
    m = _monitor_store.get_monitor(monitor_id)
    result = monitor.run_monitor(_monitor_store, m, build_context(), notify_config())
    push_ha_sensors()
    return jsonify(result)


@api('/api/monitors/<int:monitor_id>/history', admin=True)
def monitors_history(monitor_id: int):
    _monitor_store.get_monitor(monitor_id)
    return jsonify({'rows': _monitor_store.history(monitor_id)})


# ── In-app settings (SMTP / Telegram) ──────────────────────────────────────────


@api('/api/settings', admin=True)
def settings_get():
    return jsonify({'values': usersettings.public_view(load_config()),
                    'crypto_available': usersettings.crypto_available()})


@api('/api/settings', methods=('POST',), admin=True)
def settings_save():
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        raise ProbeError('bad_params')
    changed = usersettings.save(body)
    if 'tech_extra_rules' in changed and body.get('tech_extra_rules'):
        # Wer den Schalter umlegt, will den Datensatz jetzt und nicht beim
        # naechsten Rundgang in sechs Stunden.
        if not wapimport.status()['available']:
            _start_tech_rules_fetch()
    return jsonify({'ok': True, 'changed': changed})


# ── Benutzerverwaltung ────────────────────────────────────────────────────────


def send_account_mail(user: dict, password: str, reset: bool) -> tuple:
    """Startkennwort an den Benutzer. Gibt (verschickt, Fehlercode) zurück --
    ohne Mailweg bekommt der Betreiber das Kennwort in der Antwort und gibt es
    selbst weiter, statt dass das Anlegen scheitert."""
    if not user.get('email'):
        return False, 'no_email'
    if reset:
        subject = '[NetToolbox] Neues Kennwort'
        intro = 'Für dein Konto wurde ein neues Startkennwort gesetzt.'
    else:
        subject = '[NetToolbox] Zugang eingerichtet'
        intro = 'Für dich wurde ein Zugang zu NetToolbox angelegt.'
    base = public_base_url()
    # Lieber gar keine Adresse als eine falsche: über Ingress ist die
    # aufgerufene Adresse die von Home Assistant, dort gibt es keine
    # Anmeldeseite. Dann steht in der Mail, dass der Betreiber sie nennt.
    where = ('Anmelden: ' + base + '/login' if base
             else 'Die Adresse zum Anmelden nennt dir der Betreiber.')
    body = (f"{intro}\n\n"
            f"{where}\n"
            f"Benutzername: {user['username']}\n"
            f"Startkennwort: {password}\n\n"
            "Das Kennwort gilt nur für die erste Anmeldung — danach fragt "
            "NetToolbox sofort nach einem eigenen.\n\n"
            "-- NetToolbox")
    # smtp_to zeigt sonst auf die Adresse für Wächter-Meldungen; hier soll die
    # Mail an den neuen Benutzer gehen.
    cfg = dict(notify_config(), smtp_to=user['email'])
    ok, error = monitor.send_email(cfg, subject, body)
    return ok, ('' if ok else (error or 'not_configured'))


def _link_missing() -> bool:
    """Die Mail konnte keinen Anmeldelink tragen -- der Betreiber soll das
    erfahren und die öffentliche Adresse eintragen."""
    return not public_base_url()


def _need_user_store() -> None:
    if not _user_store.available():
        raise useraccounts.UserError('user_store_broken')


def _reserved_name(name: str) -> bool:
    """Der Name aus den Add-on-Optionen darf nicht doppelt vergeben werden --
    sonst wäre nicht mehr entscheidbar, welches Konto gemeint ist."""
    return str(name or '').strip().lower() == str(
        load_config().get('username') or '').strip().lower()


@api('/api/users', admin=True)
def users_list():
    _need_user_store()
    return jsonify({'users': _user_store.list(),
                    'options_admin': _options_admin()['username'],
                    'self_id': current_user().get('id'),
                    'password_min': useraccounts.PASSWORD_MIN,
                    'modules': list(MODULES),
                    'today': {u['id']: _user_store.usage_today(u['id'], _today())
                              for u in _user_store.list()}})


@api('/api/users', methods=('POST',), admin=True)
def users_create():
    _need_user_store()
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        raise ProbeError('bad_params')
    if _reserved_name(body.get('username')):
        raise useraccounts.UserError('user_exists')
    user, password = _user_store.create(body.get('username'), body.get('email'),
                                        bool(body.get('is_admin')),
                                        body.get('note'))
    sent, error = send_account_mail(user, password, reset=False)
    log.info("account created (admin=%s, mail=%s)", bool(user['is_admin']), sent)
    # Das Kennwort nur zeigen, wenn es nicht schon per Mail unterwegs ist --
    # zwei Kopien desselben Geheimnisses sind eine zu viel.
    return jsonify({'ok': True, 'user': user, 'mail_sent': sent,
                    'mail_error': error, 'link_missing': _link_missing(),
                    'password': '' if sent else password})


@api('/api/users/<int:user_id>', methods=('PUT',), admin=True)
def users_update(user_id: int):
    _need_user_store()
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        raise ProbeError('bad_params')
    if user_id == current_user().get('id') and (
            'blocked' in body or 'is_admin' in body):
        # Sich selbst aussperren geht schief, egal wie gut gemeint.
        raise useraccounts.UserError('self_target')
    fields = {k: body[k] for k in
              ('email', 'note', 'blocked', 'is_admin', 'modules', 'daily_quota')
              if k in body}
    if 'modules' in fields:
        fields['modules'] = clean_modules(fields['modules'])
    user = _user_store.update(user_id, fields)
    if user['blocked']:
        drop_user_sessions(user_id)
    return jsonify({'ok': True, 'user': user})


@api('/api/users/<int:user_id>', methods=('DELETE',), admin=True)
def users_delete(user_id: int):
    _need_user_store()
    if user_id == current_user().get('id'):
        raise useraccounts.UserError('self_target')
    user = _user_store.delete(user_id)
    drop_user_sessions(user_id)
    with _history_lock:
        keep = [row for row in _history if int(row.get('uid') or 0) != user_id]
        _history.clear()
        _history.extend(keep)
    log.info("account deleted")
    return jsonify({'ok': True, 'username': user['username']})


@api('/api/users/<int:user_id>/log', admin=True)
def users_log(user_id: int):
    _need_user_store()
    _user_store.get(user_id)  # wirft user_not_found, wenn es das Konto nicht gibt
    return jsonify({'rows': _user_store.activity(user_id, 200),
                    'today': _user_store.usage_today(user_id, _today())})


@api('/api/users/<int:user_id>/log', methods=('DELETE',), admin=True)
def users_log_clear(user_id: int):
    _need_user_store()
    _user_store.get(user_id)
    _user_store.forget_user(user_id)
    return jsonify({'ok': True})


@api('/api/users/<int:user_id>/quota-reset', methods=('POST',), admin=True)
def users_quota_reset(user_id: int):
    _need_user_store()
    _user_store.get(user_id)
    _user_store.forget_day(user_id, _today())
    return jsonify({'ok': True})


@api('/api/users/<int:user_id>/reset', methods=('POST',), admin=True)
def users_reset(user_id: int):
    _need_user_store()
    user, password = _user_store.reset_password(user_id)
    # Ein zurückgesetztes Kennwort beendet laufende Sitzungen -- sonst bliebe
    # ein übernommenes Konto trotz Reset offen.
    drop_user_sessions(user_id)
    sent, error = send_account_mail(user, password, reset=True)
    log.info("account password reset (mail=%s)", sent)
    return jsonify({'ok': True, 'user': user, 'mail_sent': sent,
                    'mail_error': error, 'link_missing': _link_missing(),
                    'password': '' if sent else password})


# ── Zusatz-Datensatz fuer die Technik-Erkennung ───────────────────────────────

# Der Datensatz steht unter der GPL-3.0 und wird deshalb nicht mitgeliefert,
# sondern auf Wunsch in den Datenordner dieser Instanz geladen. Von hier aus
# wird er angestossen, beobachtet und wieder entfernt.

_tech_rules_lock = threading.Lock()
_tech_rules_last_error = ''


def _tech_rules_fetch() -> None:
    """Laeuft im Hintergrund; ein Fehlschlag bleibt fuer die Oberflaeche
    sichtbar, statt nur im Protokoll zu landen."""
    global _tech_rules_last_error
    try:
        info = wapimport.update(build_context())
        _tech_rules_last_error = ''
        log.info("Zusatz-Datensatz geladen: %d Techniken, %d Muster",
                 info['technologies'], info['patterns'])
    except ProbeError as e:
        _tech_rules_last_error = e.code
        log.warning("Zusatz-Datensatz nicht geladen: %s", e.code)
    except Exception as e:  # noqa: BLE001 — der Rest des Add-ons laeuft weiter
        _tech_rules_last_error = 'internal'
        log.warning("Zusatz-Datensatz nicht geladen: %s", type(e).__name__,
                    exc_info=_verbose())


def _start_tech_rules_fetch() -> bool:
    """Startet den Abruf, wenn nicht ohnehin schon einer laeuft."""
    if not _tech_rules_lock.acquire(blocking=False):
        return False
    try:
        if wapimport.status()['updating']:
            return False
        threading.Thread(target=_tech_rules_fetch, daemon=True).start()
        return True
    finally:
        _tech_rules_lock.release()


def _tech_rules_loop() -> None:
    """Haelt den Datensatz aktuell, solange er gewuenscht ist.

    Nachgesehen wird alle sechs Stunden, geholt wird nur, wenn der eigene
    Stand aelter als eine Woche ist -- der Datensatz aendert sich in Tagen,
    nicht in Minuten, und der Abruf sind gut drei Megabyte.
    """
    while True:
        try:
            cfg = usersettings.effective(load_config())
            if (cfg.get('tech_extra_rules')
                    and cfg.get('tech_rules_auto_update', True)
                    and wapimport.needs_update()):
                _tech_rules_fetch()
        except Exception:  # noqa: BLE001
            log.warning("Pflege des Zusatz-Datensatzes fehlgeschlagen",
                        exc_info=_verbose())
        time.sleep(TECH_RULES_CHECK_SECONDS)


def _tech_rules_view() -> dict:
    cfg = usersettings.effective(load_config())
    info = wapimport.status()
    info['enabled'] = bool(cfg.get('tech_extra_rules'))
    info['auto_update'] = bool(cfg.get('tech_rules_auto_update', True))
    info['builtin_rules'] = len(techrules.RULES)
    info['last_error'] = _tech_rules_last_error
    return info


@api('/api/tech-rules', admin=True)
def tech_rules_get():
    return jsonify(_tech_rules_view())


@api('/api/tech-rules/update', methods=('POST',), admin=True)
def tech_rules_update():
    if not _start_tech_rules_fetch():
        return jsonify({'ok': False, 'error': 'update_running'}), 409
    return jsonify({'ok': True, 'started': True})


@api('/api/tech-rules/remove', methods=('POST',), admin=True)
def tech_rules_remove():
    removed = wapimport.remove()
    return jsonify({'ok': True, 'removed': removed})


def _test_cfg(body: dict) -> dict:
    """The already-saved settings, with whatever non-empty fields the form
    currently holds layered on top -- so a test can run before hitting Save,
    the same 'empty secret means keep the saved one' rule as saving itself."""
    cfg = usersettings.effective(load_config())
    for key in usersettings.FIELDS:
        if key in body and body[key] not in (None, ''):
            cfg[key] = body[key]
    return cfg


@api('/api/settings/test-email', methods=('POST',), admin=True)
def settings_test_email():
    body = request.get_json(silent=True) or {}
    cfg = _test_cfg(body if isinstance(body, dict) else {})
    ok, error = monitor.send_email(
        cfg, '[NetToolbox] Testmail',
        'Diese Testmail bestätigt, dass die SMTP-Einstellungen von NetToolbox funktionieren.')
    if not ok:
        return jsonify({'ok': False, 'error': error or 'not_configured'}), 200
    return jsonify({'ok': True})


@api('/api/settings/test-telegram', methods=('POST',), admin=True)
def settings_test_telegram():
    body = request.get_json(silent=True) or {}
    cfg = _test_cfg(body if isinstance(body, dict) else {})
    ok, error = monitor.send_telegram(
        cfg, '[NetToolbox] Testnachricht — die Telegram-Einstellungen funktionieren.')
    if not ok:
        return jsonify({'ok': False, 'error': error or 'not_configured'}), 200
    return jsonify({'ok': True})


# ── Startup ───────────────────────────────────────────────────────────────────


# ── Home-Assistant-Entitäten ─────────────────────────────────────────────────

HA_PUSH_SECONDS = 60
_ha_push_failed = False


def ha_sensors_enabled() -> bool:
    return bool(load_config().get('ha_sensors', True)) and hasensors.available()


def push_ha_sensors() -> None:
    """Zustände aller Wächter nach Home Assistant schreiben.

    Bewusst wegwerfbar: schlägt das fehl, läuft das Monitoring unverändert
    weiter — die Entitäten sind eine Zugabe, keine Voraussetzung.
    """
    if not ha_sensors_enabled() or not _monitor_store.available():
        return
    global _ha_push_failed
    try:
        written = hasensors.push(_monitor_store.list_monitors())
        if _verbose() and written:
            log.info("%d Home-Assistant-Entitäten aktualisiert", written)
        # Eine abgelehnte Schreiboperation wirft nichts -- ohne diese Meldung
        # bliebe "es erscheint einfach nichts in Home Assistant" unerklärt.
        # Nur einmal, sonst füllt es bei dauerhaftem Fehler das Protokoll.
        if not written and not _ha_push_failed:
            _ha_push_failed = True
            log.warning("Home Assistant hat die Entitäten nicht angenommen — "
                        "steht homeassistant_api in der Add-on-Konfiguration?")
        elif written:
            _ha_push_failed = False
    except Exception:  # noqa: BLE001
        log.warning("Home-Assistant-Entitäten konnten nicht geschrieben werden",
                    exc_info=_verbose())


def _ha_push_loop() -> None:
    # Regelmäßig statt nur bei Änderungen: Zustände, die per States-API
    # gesetzt wurden, überleben einen Neustart von Home Assistant nicht und
    # müssen danach von selbst wieder auftauchen.
    while True:
        time.sleep(HA_PUSH_SECONDS)
        push_ha_sensors()


def _startup_checks() -> None:
    usersettings.init(_DATA)
    usersettings.migrate()
    wapimport.init(_DATA)
    threading.Thread(target=_tech_rules_loop, daemon=True).start()
    if not usersettings.crypto_available():
        log.warning("cryptography package unavailable — SMTP/Telegram secrets "
                    "entered in the UI cannot be saved")
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

    missing = sorted(set(probes.PROBES) - set(PROBE_MODULE))
    if missing:
        # Eine Prüfung ohne Reiter-Zuordnung liefe an der Freischaltung vorbei.
        log.warning("probes without a module: %s — they stay available to "
                    "everyone", ', '.join(missing))

    if _user_store.open():
        count = len(_user_store.list())
        if count:
            log.info("user accounts: %d", count)
    else:
        log.warning("user store could not be opened (%s) — only the account "
                    "from the add-on options can sign in", _user_store.broken)

    # Der Snapshot-Speicher haengt nicht am Monitoring: er wird auch dann
    # gebraucht, wenn niemand einen Waechter eingerichtet hat.
    if not _snapshot_store.open():
        log.warning("snapshot store could not be opened (%s) — DNS snapshots "
                    "unavailable", _snapshot_store.broken)

    if bool(cfg.get('monitoring_enabled', True)):
        if _monitor_store.open():
            poll = _cfg_int('monitoring_poll_seconds', 60, 10, 3600)
            threading.Thread(target=monitor.worker_loop,
                             args=(_monitor_store, build_context, notify_config, poll),
                             daemon=True).start()
            log.info("monitoring worker started (%ds poll)", poll)
            if ha_sensors_enabled():
                threading.Thread(target=_ha_push_loop, daemon=True).start()
                push_ha_sensors()
                log.info("Home-Assistant-Entitäten aktiv (alle %ds)",
                         HA_PUSH_SECONDS)
        else:
            log.warning("monitor store could not be opened — monitoring disabled")


if __name__ == '__main__':
    _bootstrap_options()
    load_sessions()
    load_blocks()
    history_load()
    _startup_checks()

    def _shutdown(signum, frame):
        log.info("signal %s received — NetToolbox is shutting down", signum)
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    log.info("NetToolbox %s ready on port %d", APP_VERSION or '?', PORT)
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
