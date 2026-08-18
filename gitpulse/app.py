#!/usr/bin/env python3
import base64
import hashlib
import hmac
import html as htmllib
import json
import logging
import os
import queue
import re
import secrets
import signal
import smtplib
import time
import threading
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlparse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import (Flask, render_template, request, redirect,
                   url_for, make_response, abort, jsonify,
                   Response, stream_with_context)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.serving import make_server
import requests as http

logging.basicConfig(format='[%(levelname)s] [%(asctime)s] %(message)s',
                    level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S', force=True)
log = logging.getLogger(__name__)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# ── In-App Console Log-Buffer ─────────────────────────────────────────────────
_log_buffer: deque = deque(maxlen=300)

class _BufferHandler(logging.Handler):
    _fmt = logging.Formatter('[%(levelname)s] [%(asctime)s] %(message)s',
                              datefmt='%Y-%m-%d %H:%M:%S')
    def emit(self, record):
        try:
            _log_buffer.append({
                'ts':    int(record.created * 1000),
                'level': record.levelname,
                'msg':   self._fmt.format(record),
            })
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

# ── Flask ─────────────────────────────────────────────────────────────────────
_BASE = os.environ.get('GITPULSE_BASE', '/app')
_DATA = os.environ.get('GITPULSE_DATA', '/data')
app = Flask(__name__, template_folder=_BASE + '/templates', static_folder=_BASE + '/static')


class _IngressMiddleware:
    """Reads HA Supervisor X-Ingress-Path and sets WSGI SCRIPT_NAME so that
    Flask's url_for() generates correct URLs behind the Ingress proxy."""
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

CONFIG_PATH    = _DATA + '/options.json'
SESSIONS_PATH  = _DATA + '/sessions.json'
REPOS_PATH     = _DATA + '/gitpulse_repos.json'
FAVORITES_PATH = _DATA + '/workflow_favorites.json'
GP_SETTINGS_PATH = _DATA + '/gitpulse_settings.json'
LOCALES_PATH   = _BASE + '/locales'

GITHUB_API    = 'https://api.github.com'
POLL_INTERVAL_DEFAULT = 300  # seconds

# ── State ─────────────────────────────────────────────────────────────────────
_config_cache: dict | None = None
_config_mtime: float = 0.0
sessions: dict[str, float] = {}

# SSE
_sse_queues: list = []
_sse_lock = threading.Lock()

# GitHub data cache
_gh_cache: dict = {
    'my_repos':    [],
    'releases':    [],
    'my_activity':           {'prs': [], 'issues': [], 'review_prs': []},
    'new_comments':          [],
    'gh_login':              '',
    'token_ok':    None,
    'token_scopes': '',
    'token_expires': '',
    'last_poll':   0,
    'error':       None,
    'rate_limit':  {'remaining': 5000, 'limit': 5000, 'reset': 0},
}
_gh_lock = threading.Lock()

# Seen releases (für Benachrichtigungen — persistent über Neustarts)
_SEEN_PATH = _DATA + '/seen_releases.json'
_seen_releases: set[str] = set()

# Seen activity — eigene PRs/Issues, persistent
_SEEN_ACTIVITY_PATH = _DATA + '/seen_activity.json'
_seen_activity: set[str] = set()   # "{owner}/{repo}#{number}:{state}"

# Gelesene Kommentar-Stände — "{repo}#{nummer}" → Kommentar-Anzahl beim letzten Lesen.
# Unbekannte Einträge werden beim ersten Poll still auf den Ist-Stand gesetzt, damit
# nicht die gesamte Historie als "neu" markiert wird.
_SEEN_COMMENTS_PATH = _DATA + '/seen_comments.json'
_seen_comment_totals: dict[str, int] = {}
_seen_comments_lock = threading.Lock()
_seen_comments_dirty = False

# GitHub-Login des authentifizierten Nutzers (wird beim ersten Poll gesetzt)
_gh_login: str = ''

# Kommentar-Zustand pro PR/Issue — Grundlage der "Neuer Kommentar"-Meldung.
# "{repo}#{nummer}" -> {"total": int, "ts": ISO-Zeit des neuesten bekannten Kommentars}
# Persistent, sonst gilt nach jedem Neustart der Ist-Stand als bekannt und
# Kommentare, die während des Neustarts kamen, lösen nie eine Meldung aus.
_COMMENT_STATE_PATH = _DATA + '/comment_state.json'
_comment_state: dict[str, dict] = {}
_comment_state_lock = threading.Lock()

# Höchstzahl an Items pro Poll, für die bei geänderter Kommentarzahl die Autoren
# nachgeladen werden (jedes Item kostet 1–3 API-Calls)
_COMMENT_CHECK_MAX = 25

# Kommentar-Panel: maximale Textlänge pro Kommentar und Anzahl gezeigter Kommentare
_COMMENT_BODY_MAX = 2000
_COMMENT_SHOW_MAX = 10

# Höchstzahl fremder PRs pro Poll, für die Review-Status/Kommentarzahl nachgeladen wird
_ACTIVITY_META_MAX = 40

# Repos ohne Releases — 404 bekommen, 1h warten bevor erneut geprüft wird
_NO_RELEASE_TTL = 3600
_no_release_repos: dict[str, float] = {}  # repo -> timestamp der letzten 404

# Tages-Digest — Datum des letzten gesendeten Digests (YYYY-MM-DD)
_last_digest_date: str = ''

# Review-Request-Tracking — PRs die zur Review angefragt wurden (in-memory)
_seen_review_prs: set[str] = set()

# ETag-Cache für bedingte GitHub-API-Anfragen (spart Rate-Limit)
_etag_cache: dict[str, tuple] = {}

# GitHub Rate-Limit State
_rate_limit: dict = {'remaining': 5000, 'limit': 5000, 'reset': 0}

# Telegram-Benachrichtigungs-Tracking (In-Memory, Reset bei Neustart)
# Erster Poll befüllt die Sets ohne Benachrichtigung, nur neue Einträge danach lösen aus
_first_poll_done: bool = False
_seen_prs:   dict[str, set] = defaultdict(set)   # repo → {pr_number, …}
_seen_issues: dict[str, set] = defaultdict(set)  # repo → {issue_number, …}
_known_run_conclusions: dict[int, str | None] = {}  # run_id → conclusion
_repo_stats: dict[str, dict] = {}  # repo → {stars, forks, watchers} für Änderungserkennung

# Doppel-Benachrichtigungen bei Security-Alerts unterdrücken.
# GitHub feuert für einen neuen Code-Scanning-Alert zwei Webhooks ("created" und
# "appeared_in_branch") — beide sollen zusammen nur eine Nachricht ergeben.
_ALERT_NOTIFY_TTL = 900   # Sekunden
_alert_notified: dict[str, float] = {}   # "cs:{repo}#{num}:{gruppe}" → timestamp
_alert_notify_lock = threading.Lock()

# ── Rate limiting ─────────────────────────────────────────────────────────────
_failed_attempts: dict[str, list[float]] = defaultdict(list)
_blocked_ips:     dict[str, float]       = {}
RATE_LIMIT_MAX    = 5
RATE_LIMIT_WINDOW = 10 * 60
RATE_LIMIT_BLOCK  = 15 * 60


# ── Config & Sessions ─────────────────────────────────────────────────────────

def load_user_repos() -> dict | None:
    """Gibt user-verwaltete Repos zurück oder None wenn nicht vorhanden (→ options.json nutzen)."""
    try:
        with open(REPOS_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception as e:
        log.warning("gitpulse_repos.json konnte nicht geladen werden: %s", e)
        return None


def save_user_repos(data: dict) -> None:
    try:
        with open(REPOS_PATH, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        log.warning("gitpulse_repos.json konnte nicht gespeichert werden: %s", e)


_GP_SETTINGS_DEFAULTS = {'main_branch': 'main', 'dev_branch': 'dev', 'autofix_branch_check': True}

def load_gitpulse_settings() -> dict:
    try:
        with open(GP_SETTINGS_PATH) as f:
            data = json.load(f)
            return {**_GP_SETTINGS_DEFAULTS, **data}
    except FileNotFoundError:
        return dict(_GP_SETTINGS_DEFAULTS)
    except Exception as e:
        log.warning("gitpulse_settings.json konnte nicht geladen werden: %s", e)
        return dict(_GP_SETTINGS_DEFAULTS)

def save_gitpulse_settings(data: dict) -> None:
    try:
        with open(GP_SETTINGS_PATH, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        log.warning("gitpulse_settings.json konnte nicht gespeichert werden: %s", e)


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


# ── Rate limiting ─────────────────────────────────────────────────────────────

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
    accept = req.headers.get('Accept-Language', '')
    if 'de' in accept[:5].lower():
        return 'de'
    return 'en'


def _verbose() -> bool:
    return bool(load_config().get('verbose_log', False))


# ── Seen Releases (Persistence) ───────────────────────────────────────────────

def load_seen_releases() -> None:
    global _seen_releases
    try:
        with open(_SEEN_PATH) as f:
            _seen_releases = set(json.load(f))
        log.info("Bekannte Releases geladen: %d Einträge", len(_seen_releases))
    except FileNotFoundError:
        pass
    except Exception as e:
        log.warning("seen_releases konnte nicht geladen werden: %s", e)


def save_seen_releases() -> None:
    try:
        with open(_SEEN_PATH, 'w') as f:
            json.dump(list(_seen_releases), f)
    except Exception as e:
        log.warning("seen_releases konnte nicht gespeichert werden: %s", e)


def load_seen_activity() -> None:
    global _seen_activity
    try:
        with open(_SEEN_ACTIVITY_PATH) as f:
            _seen_activity = set(json.load(f))
        log.info("Bekannte Aktivitäten geladen: %d Einträge", len(_seen_activity))
    except FileNotFoundError:
        pass
    except Exception as e:
        log.warning("seen_activity konnte nicht geladen werden: %s", e)


def save_seen_activity() -> None:
    try:
        with open(_SEEN_ACTIVITY_PATH, 'w') as f:
            json.dump(list(_seen_activity), f)
    except Exception as e:
        log.warning("seen_activity konnte nicht gespeichert werden: %s", e)


def load_comment_state() -> None:
    global _comment_state
    try:
        with open(_COMMENT_STATE_PATH) as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            _comment_state = {
                str(k): {'total': int(v.get('total', 0)), 'ts': str(v.get('ts', ''))}
                for k, v in raw.items() if isinstance(v, dict)
            }
        log.info("Kommentar-Zustand geladen: %d Einträge", len(_comment_state))
    except FileNotFoundError:
        pass
    except Exception as e:
        log.warning("comment_state konnte nicht geladen werden: %s", e)


def save_comment_state() -> None:
    with _comment_state_lock:
        snapshot = {k: dict(v) for k, v in _comment_state.items()}
    try:
        with open(_COMMENT_STATE_PATH, 'w') as f:
            json.dump(snapshot, f)
    except Exception as e:
        log.warning("comment_state konnte nicht gespeichert werden: %s", e)


def load_seen_comments() -> None:
    global _seen_comment_totals
    try:
        with open(_SEEN_COMMENTS_PATH) as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            _seen_comment_totals = {str(k): int(v) for k, v in raw.items()}
        log.info("Gelesene Kommentar-Stände geladen: %d Einträge", len(_seen_comment_totals))
    except FileNotFoundError:
        pass
    except Exception as e:
        log.warning("seen_comments konnte nicht geladen werden: %s", e)


def save_seen_comments() -> None:
    global _seen_comments_dirty
    with _seen_comments_lock:
        if not _seen_comments_dirty:
            return
        snapshot = dict(_seen_comment_totals)
        _seen_comments_dirty = False
    try:
        with open(_SEEN_COMMENTS_PATH, 'w') as f:
            json.dump(snapshot, f)
    except Exception as e:
        log.warning("seen_comments konnte nicht gespeichert werden: %s", e)


def _comments_new(repo: str, number: int, total: int) -> int:
    """Anzahl ungelesener Kommentare. Unbekannte Items werden still auf den Ist-Stand
    gesetzt (kein Nachmelden alter Kommentare)."""
    global _seen_comments_dirty
    key = f'{repo}#{number}'
    with _seen_comments_lock:
        seen = _seen_comment_totals.get(key)
        if seen is None:
            _seen_comment_totals[key] = total
            _seen_comments_dirty = True
            return 0
        if total < seen:            # Kommentare gelöscht → Stand nachziehen
            _seen_comment_totals[key] = total
            _seen_comments_dirty = True
            return 0
    return total - seen


def _mark_comments_read(repo: str, number: int, total: int) -> None:
    global _seen_comments_dirty
    with _seen_comments_lock:
        _seen_comment_totals[f'{repo}#{number}'] = max(0, int(total))
        _seen_comments_dirty = True
    save_seen_comments()


def _skip_own_comments(repo: str, number: int, count: int, total: int) -> int:
    """Eigene Kommentare als gelesen verbuchen: der Ungelesen-Stand wird um `count`
    angehoben, ohne fremde ungelesene Kommentare zu verschlucken. Gibt die neue
    Ungelesen-Zahl zurück."""
    global _seen_comments_dirty
    key = f'{repo}#{number}'
    with _seen_comments_lock:
        seen = _seen_comment_totals.get(key, total)
        if count > 0:
            seen = min(total, seen + count)
            _seen_comment_totals[key] = seen
            _seen_comments_dirty = True
        return max(0, total - seen)


# ── Workflow-Favoriten (Persistence) ──────────────────────────────────────────

def load_favorites() -> list:
    try:
        with open(FAVORITES_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except Exception as e:
        log.warning("workflow_favorites.json konnte nicht geladen werden: %s", e)
        return []


def save_favorites(favs: list) -> None:
    try:
        with open(FAVORITES_PATH, 'w') as f:
            json.dump(favs, f, indent=2)
    except Exception as e:
        log.warning("workflow_favorites.json konnte nicht gespeichert werden: %s", e)


# ── GitHub API ────────────────────────────────────────────────────────────────

def _update_rate_limit(headers) -> None:
    try:
        rem   = int(headers.get('X-RateLimit-Remaining', -1))
        limit = int(headers.get('X-RateLimit-Limit', 5000))
        reset = int(headers.get('X-RateLimit-Reset', 0))
        if rem >= 0:
            _rate_limit['remaining'] = rem
            _rate_limit['limit']     = limit
            _rate_limit['reset']     = reset
            if rem < 100:
                log.warning("GitHub Rate-Limit kritisch: %d/%d verbleibend, Reset um %s UTC",
                            rem, limit,
                            datetime.fromtimestamp(reset, tz=timezone.utc).strftime('%H:%M'))
    except Exception:
        pass


def _gh_headers(token: str) -> dict:
    return {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'GitPulse-HA-AddOn/1.0',
    }


def _gh_get(path: str, token: str, params: dict | None = None) -> dict | list | None:
    url       = f'{GITHUB_API}{path}' if path.startswith('/') else path
    cache_key = path + (str(sorted(params.items())) if params else '')
    hdrs      = _gh_headers(token)
    cached    = _etag_cache.get(cache_key)
    if cached:
        hdrs['If-None-Match'] = cached[0]
    try:
        r = http.get(url, headers=hdrs, params=params, timeout=15)
        _update_rate_limit(r.headers)
        if r.status_code == 304 and cached:
            return cached[1]
        if r.status_code == 200:
            data = r.json()
            etag = r.headers.get('ETag')
            if etag:
                _etag_cache[cache_key] = (etag, data)
            return data
        if r.status_code == 429:
            reset_ts = int(r.headers.get('X-RateLimit-Reset', time.time() + 60))
            log.warning("GitHub Rate-Limit überschritten — Reset um %s UTC",
                        datetime.fromtimestamp(reset_ts, tz=timezone.utc).strftime('%H:%M'))
        else:
            log.warning("GitHub API %s → HTTP %d", path, r.status_code)
        return None
    except Exception as e:
        log.error("GitHub API Fehler (%s): %s", path, e)
        return None


def _gh_get_paginated(path: str, token: str, max_pages: int = 5, params: dict | None = None) -> list:
    results = []
    url = f'{GITHUB_API}{path}' if path.startswith('/') else path
    base_params = {'per_page': 100, **(params or {})}
    page = 1
    while url and page <= max_pages:
        try:
            r = http.get(url, headers=_gh_headers(token),
                         params={**base_params, 'page': page}, timeout=15)
            _update_rate_limit(r.headers)
            if r.status_code != 200:
                break
            data = r.json()
            if not data:
                break
            results.extend(data)
            link = r.headers.get('Link', '')
            next_url = None
            for part in link.split(','):
                if 'rel="next"' in part and len(part) <= 4096:
                    m = re.search(r'<(https?://[^>\s]{1,2048})>', part)
                    if m:
                        next_url = m.group(1)
            url = next_url
            page += 1
        except Exception as e:
            log.error("Paginierung Fehler (%s): %s", path, e)
            break
    return results


def _check_token(token: str) -> tuple[bool, str, str]:
    """Returns (ok, scopes, expires_str)."""
    try:
        r = http.get(f'{GITHUB_API}/user', headers=_gh_headers(token), timeout=10)
        if r.status_code == 200:
            scopes  = r.headers.get('X-OAuth-Scopes', 'fine-grained')
            expires = r.headers.get('GitHub-Authentication-Token-Expiration', '')
            if _verbose():
                log.info("Token OK — Scopes: %d, Ablauf: %s", len((scopes or '').split(',')), bool(expires))
            return True, scopes, expires
        return False, '', ''
    except Exception as e:
        log.error("Token-Check fehlgeschlagen: %s", e)
        return False, '', ''


_CODE_FENCES     = ('```', '~~~')
# Kein `[^>]*`: bei vielen `<img` ohne schließendes `>` würde jeder Startpunkt
# erneut bis zum Textende laufen. `<` beendet den Scan sofort — und in einem Tag
# darf ohnehin kein `<` stehen.
_HTML_DROP_RE    = re.compile(r'<(?:img|picture|source|svg|iframe|video|audio)\b[^<>]*>', re.I)
_HTML_CELL_RE    = re.compile(r'</t[dh]\s*>', re.I)
_HTML_BREAK_RE   = re.compile(r'<br\s*/?>|</(?:p|div|li|ul|ol|tr|h[1-6]|blockquote|summary|details|table)\s*>', re.I)
_HTML_TAG_RE     = re.compile(r'</?[A-Za-z][A-Za-z0-9-]*(?:\s[^<>]*)?/?>')
_BLANK_LINES_RE  = re.compile(r'\n{3,}')


def _split_code(text: str) -> list[str]:
    """Text in [Fließtext, Code, Fließtext, …] zerlegen — Code auf ungeraden Indizes.

    Bewusst ein linearer Scan statt `(```[\\s\\S]*?```|…)`: ein solches Muster setzt
    an jeder öffnenden Fence neu an und läuft bei unabgeschlossenen Fences ins
    quadratische Backtracking (CodeQL py/polynomial-redos). Hier merkt sich der
    Scan stattdessen, dass es keinen weiteren Abschluss mehr gibt, und sucht
    kein zweites Mal danach.
    """
    parts: list[str] = []
    plain = i = 0
    n = len(text)
    fence_open = {'```': True, '~~~': True}  # False = kein Abschluss mehr im Rest
    tick_left  = True                        # False = kein Backtick mehr im Rest
    next_nl    = text.find('\n')
    while i < n:
        if 0 <= next_nl < i:
            next_nl = text.find('\n', i)
        ch = text[i]
        if ch != '`' and ch != '~':
            i += 1
            continue
        marker = text[i:i + 3]
        if marker in fence_open:
            if fence_open[marker]:
                end = text.find(marker, i + 3)
                if end >= 0:
                    parts.append(text[plain:i])
                    parts.append(text[i:end + 3])
                    plain = i = end + 3
                    continue
                fence_open[marker] = False
            i += 1
            continue
        if ch == '`' and tick_left:
            end = text.find('`', i + 1)
            if end < 0:
                tick_left = False
            # Inline-Code braucht mindestens ein Zeichen und bleibt in einer Zeile
            elif end > i + 1 and (next_nl < 0 or end < next_nl):
                parts.append(text[plain:i])
                parts.append(text[i:end + 1])
                plain = i = end + 1
                continue
        i += 1
    parts.append(text[plain:])
    return parts


def _drop_html_comments(text: str) -> str:
    """`<!-- … -->` entfernen. Auch hier linear statt `<!--[\\s\\S]*?-->`, das bei
    vielen unabgeschlossenen `<!--` jeden Start erneut bis zum Textende scannt."""
    if '<!--' not in text:
        return text
    out: list[str] = []
    pos = 0
    while True:
        start = text.find('<!--', pos)
        if start < 0:
            break
        end = text.find('-->', start + 4)
        if end < 0:
            break  # unabgeschlossen — Rest unverändert stehen lassen
        out.append(text[pos:start])
        pos = end + 3
    out.append(text[pos:])
    return ''.join(out)


def _strip_html(text: str) -> str:
    """Roh-HTML aus Markdown-Text entfernen.

    Kommentare werden in der Oberfläche escaped gerendert (kein XSS). GitHub-Texte
    enthalten aber oft HTML-Blöcke — Signaturen aus <p>/<a>/<img>, <details>-Boxen,
    Tabellen — die dadurch als Tag-Salat im Klartext stehen. Fenced- und Inline-Code
    bleibt unangetastet: dort ist HTML meist genau der Inhalt, den jemand zeigen will.
    """
    if not text or ('<' not in text and '&' not in text):
        return text or ''
    parts = _split_code(text)
    for i in range(0, len(parts), 2):  # ungerade Indizes sind die Code-Abschnitte
        chunk = _drop_html_comments(parts[i])
        chunk = _HTML_DROP_RE.sub('', chunk)
        chunk = _HTML_CELL_RE.sub(' ', chunk)
        chunk = _HTML_BREAK_RE.sub('\n', chunk)
        chunk = _HTML_TAG_RE.sub('', chunk)
        # Erst nach dem Strippen entschärfen, sonst würde ein bewusst escaptes
        # &lt;div&gt; zu einem echten Tag und gleich wieder wegfallen.
        chunk = htmllib.unescape(chunk).replace('\xa0', ' ')
        # Zeilenenden säubern, die letzte Zeile aber nicht: sie geht direkt in
        # einen folgenden Code-Abschnitt über, dort würde das Leerzeichen fehlen.
        lines = chunk.split('\n')
        chunk = '\n'.join([ln.rstrip() for ln in lines[:-1]] + lines[-1:])
        parts[i] = _BLANK_LINES_RE.sub('\n\n', chunk)
    return ''.join(parts).strip()


def _compute_review_state(reviews: list, requested: int = 0) -> str:
    """Aggregiert Review-Entscheidungen: 'approved', 'changes_requested', 'pending', 'none'.

    `requested` = Anzahl noch offener Review-Anfragen. GitHub zeigt einen PR auch
    dann als "Review ausstehend", wenn noch niemand ein Review abgegeben hat, aber
    Reviewer angefragt sind.
    """
    latest: dict[str, str] = {}
    for rev in reviews:
        state = rev.get('state', '')
        if state in ('APPROVED', 'CHANGES_REQUESTED'):
            latest[rev['user']['login']] = state
    states = set(latest.values())
    if 'CHANGES_REQUESTED' in states:
        return 'changes_requested'
    if 'APPROVED' in states:
        return 'approved'
    if reviews or requested:
        return 'pending'
    return 'none'


def _review_bodies_count(reviews: list) -> int:
    """Reviews mit Text zählen — die tauchen im GitHub-Verlauf als Kommentar auf,
    werden aber weder von `comments` noch von `review_comments` mitgezählt."""
    return sum(1 for rev in reviews if (rev.get('body') or '').strip())


def _fetch_repo_data(repo: str, token: str, run_limit: int = 25) -> dict:
    """Fetch PRs, Issues and latest workflow runs for one repo."""
    owner, name = repo.split('/', 1)

    repo_meta     = _gh_get(f'/repos/{repo}', token) or {}
    default_branch = repo_meta.get('default_branch', 'main')

    pulls_raw = _gh_get_paginated(f'/repos/{repo}/pulls', token) or []
    pulls = []
    for pr in pulls_raw:
        reviews_raw = _gh_get(f'/repos/{repo}/pulls/{pr["number"]}/reviews', token) or []
        # mergeable_state liefert nur der Einzel-PR-Endpoint, nicht die Liste.
        # GitHub berechnet den Wert asynchron → beim ersten Abruf oft "unknown".
        pr_detail = _gh_get(f'/repos/{repo}/pulls/{pr["number"]}', token) or {}
        _pr_reqs = pr_detail.get('requested_reviewers') or []
        _pr_cmts = ((pr_detail.get('comments') or 0)
                    + (pr_detail.get('review_comments') or 0)
                    + _review_bodies_count(reviews_raw))
        pulls.append({
            'number':       pr['number'],
            'title':        pr['title'],
            'state':        pr['state'],
            'draft':        pr.get('draft', False),
            'url':          pr['html_url'],
            'user':         pr['user']['login'],
            'avatar':       pr['user']['avatar_url'],
            'labels':       [l['name'] for l in pr.get('labels', [])],
            'created':      pr['created_at'],
            'updated':      pr['updated_at'],
            'mergeable':    pr_detail.get('mergeable_state') or '',
            'comments':     _pr_cmts,
            'comments_new': _comments_new(repo, pr['number'], _pr_cmts),
            'review_state': _compute_review_state(reviews_raw, len(_pr_reqs)),
            'reviewers':    [u.get('login', '') for u in _pr_reqs if u.get('login')],
            'body':         _strip_html(pr.get('body') or '')[:1500],
        })

    issues_raw = _gh_get_paginated(f'/repos/{repo}/issues', token) or []
    issues = []
    for iss in issues_raw:
        if 'pull_request' in iss:
            continue
        issues.append({
            'number':    iss['number'],
            'title':     iss['title'],
            'state':     iss['state'],
            'url':       iss['html_url'],
            'user':      iss['user']['login'],
            'avatar':    iss['user']['avatar_url'],
            'labels':    [l['name'] for l in iss.get('labels', [])],
            'created':   iss['created_at'],
            'updated':   iss['updated_at'],
            'closed_at': iss.get('closed_at'),
            'comments':     iss.get('comments') or 0,
            'comments_new': _comments_new(repo, iss['number'], iss.get('comments') or 0),
            'body':      _strip_html(iss.get('body') or '')[:1500],
        })

    closed_pulls_raw = _gh_get(f'/repos/{repo}/pulls', token,
                                {'state': 'closed', 'per_page': 50, 'sort': 'updated', 'direction': 'desc'}) or []
    closed_pulls = []
    for pr in (closed_pulls_raw if isinstance(closed_pulls_raw, list) else []):
        closed_pulls.append({
            'number':    pr['number'],
            'title':     pr['title'],
            'state':     pr['state'],
            'draft':     pr.get('draft', False),
            'url':       pr['html_url'],
            'user':      pr['user']['login'],
            'avatar':    pr['user']['avatar_url'],
            'labels':    [l['name'] for l in pr.get('labels', [])],
            'created':   pr['created_at'],
            'updated':   pr['updated_at'],
            'merged_at': pr.get('merged_at'),
            'comments':  (pr.get('comments') or 0) + (pr.get('review_comments') or 0),
            'comments_new': _comments_new(repo, pr['number'],
                                          (pr.get('comments') or 0) + (pr.get('review_comments') or 0)),
            'review_state': 'none',
        })

    # Issues-Endpoint mischt PRs+Issues; PRs werden viel häufiger "updated" als
    # Issues, daher reicht 1 Seite oft nicht — über mehrere Seiten sammeln,
    # bis genug echte Issues gefunden sind (Limit als Schutz vor Rate-Limit).
    closed_issues = []
    for _cpage in range(1, 6):
        _batch_raw = _gh_get(f'/repos/{repo}/issues', token,
                              {'state': 'closed', 'per_page': 50, 'page': _cpage,
                               'sort': 'updated', 'direction': 'desc'}) or []
        if not isinstance(_batch_raw, list) or not _batch_raw:
            break
        for iss in _batch_raw:
            if 'pull_request' in iss:
                continue
            closed_issues.append({
                'number':    iss['number'],
                'title':     iss['title'],
                'state':     iss['state'],
                'url':       iss['html_url'],
                'user':      iss['user']['login'],
                'avatar':    iss['user']['avatar_url'],
                'labels':    [l['name'] for l in iss.get('labels', [])],
                'created':   iss['created_at'],
                'updated':   iss['updated_at'],
                'closed_at': iss.get('closed_at'),
                'comments':     iss.get('comments') or 0,
                'comments_new': _comments_new(repo, iss['number'], iss.get('comments') or 0),
            })
        if len(closed_issues) >= 50:
            break
    closed_issues = closed_issues[:50]

    all_runs: list = []
    _page = 1
    while len(all_runs) < run_limit:
        _batch = min(100, run_limit - len(all_runs))
        _raw = _gh_get(f'/repos/{repo}/actions/runs', token, {'per_page': _batch, 'page': _page}) or {}
        _wf  = _raw.get('workflow_runs') or []
        if not _wf:
            break
        all_runs.extend(_wf)
        _page += 1
    runs = []
    for run in all_runs[:run_limit]:
        head_msg = (run.get('head_commit') or {}).get('message', '')
        runs.append({
            'id':           run['id'],
            'run_number':   run.get('run_number'),
            'workflow_id':  run.get('workflow_id'),
            'name':         run['name'],
            'status':       run['status'],
            'conclusion':   run.get('conclusion'),
            'url':          run['html_url'],
            'branch':       run.get('head_branch', ''),
            'created':      run['created_at'],
            'updated':      run.get('updated_at', ''),
            'event':        run.get('event', ''),
            'actor':        (run.get('actor') or {}).get('login', ''),
            'actor_avatar': (run.get('actor') or {}).get('avatar_url', ''),
            'head_sha':     run.get('head_sha', '')[:7],
            'head_message': head_msg.split('\n')[0][:80] if head_msg else '',
        })

    # Alle Workflows außer gelöschten für Verwaltung + Dispatch
    wf_raw = _gh_get(f'/repos/{repo}/actions/workflows', token) or {}
    workflows = []
    for wf in (wf_raw.get('workflows') or []):
        state = wf.get('state', 'active')
        if state == 'deleted':
            continue
        workflows.append({
            'id':          wf['id'],
            'name':        wf['name'],
            'path':        wf['path'],
            'state':       state,
            'dispatchable': state == 'active',
        })

    latest_release = None
    _last_404 = _no_release_repos.get(repo, 0)
    if time.time() - _last_404 > _NO_RELEASE_TTL:
        url = f'{GITHUB_API}/repos/{repo}/releases/latest'
        try:
            r = http.get(url, headers=_gh_headers(token), timeout=15)
            if r.status_code == 200:
                release_raw = r.json()
                latest_release = {
                    'tag':        release_raw['tag_name'],
                    'name':       release_raw.get('name') or release_raw['tag_name'],
                    'url':        release_raw['html_url'],
                    'date':       release_raw['published_at'],
                    'prerelease': release_raw.get('prerelease', False),
                }
            elif r.status_code == 404:
                _no_release_repos[repo] = time.time()
                log.info("%s hat noch keine Releases — nächste Prüfung in 1h", repo)
            else:
                log.warning("GitHub API /repos/%s/releases/latest → HTTP %d", repo, r.status_code)
        except Exception as e:
            log.error("GitHub API Fehler (%s/releases/latest): %s", repo, e)

    security = _fetch_security_alerts(repo, token)
    _sec_count = (len(security.get('dependabot', [])) +
                  len(security.get('code_scanning', [])) +
                  len(security.get('secret_scanning', [])))

    save_seen_comments()

    return {
        'repo':           repo,
        'owner':          owner,
        'name':           name,
        'default_branch': default_branch,
        'pulls':          pulls,
        'closed_pulls':   closed_pulls,
        'issues':         issues,
        'closed_issues':  closed_issues,
        'runs':           runs,
        'workflows':      workflows,
        'latest_release': latest_release,
        'open_prs':       len(pulls),
        'open_issues':    len(issues),
        'stars':          repo_meta.get('stargazers_count', 0),
        'forks':          repo_meta.get('forks_count', 0),
        'watchers':       repo_meta.get('watchers_count', 0),
        'security':       security,
        'insights': {
            'has_license':   bool(repo_meta.get('license')),
            'license_name':  (repo_meta.get('license') or {}).get('spdx_id', ''),
            'has_ci':        any(wf.get('state') == 'active' for wf in workflows),
            'security_count': _sec_count,
            'is_private':    bool(repo_meta.get('private', False)),
        },
    }


def _fetch_security_alerts(repo: str, token: str) -> dict:
    """Fetch open Dependabot, Code Scanning and Secret Scanning alerts for one repo."""
    def _safe(path: str) -> list:
        result = _gh_get_paginated(path, token, max_pages=10, params={'state': 'open'})
        return result if isinstance(result, list) else []

    def _fmt_dep(a: dict) -> dict:
        vuln  = a.get('security_vulnerability') or {}
        adv   = a.get('security_advisory') or {}
        pkg   = vuln.get('package') or {}
        fixed = (vuln.get('first_patched_version') or {}).get('identifier', '')
        return {
            'number':    a.get('number', '?'),
            'severity':  adv.get('severity') or 'unknown',
            'package':   pkg.get('name', '?'),
            'ecosystem': pkg.get('ecosystem', ''),
            'summary':   adv.get('summary', ''),
            'fixed_in':  fixed,
            'url':       a.get('html_url', ''),
        }

    def _fmt_cs(a: dict, branch: str = '') -> dict:
        rule = a.get('rule') or {}
        tool = a.get('tool') or {}
        loc  = ((a.get('most_recent_instance') or {}).get('location') or {})
        inst_ref = (a.get('most_recent_instance') or {}).get('ref', '')
        return {
            'number':      a.get('number', '?'),
            'severity':    rule.get('security_severity_level') or rule.get('severity', 'unknown'),
            'rule_id':     rule.get('id', ''),
            'description': rule.get('description', ''),
            'tool':        tool.get('name', 'CodeQL'),
            'path':        loc.get('path', ''),
            'line':        loc.get('start_line', ''),
            'url':         a.get('html_url', ''),
            'branch':      branch or inst_ref.replace('refs/heads/', ''),
        }

    def _fmt_ss(a: dict) -> dict:
        return {
            'number': a.get('number', '?'),
            'type':   a.get('secret_type_display_name') or a.get('secret_type', '?'),
            'url':    a.get('html_url', ''),
        }

    def _safe_dep(path: str) -> tuple[list, bool]:
        """Fetch Dependabot alerts. Returns (data, access_ok).
        Uses its own paginator (no explicit &page=N) because the Dependabot
        API returns HTTP 400 when per_page=100 + page=1 are combined."""
        url = f'{GITHUB_API}{path}' if path.startswith('/') else path
        try:
            r = http.get(url, headers=_gh_headers(token),
                         params={'state': 'open', 'per_page': 30}, timeout=10)
            if r.status_code == 403:
                try:
                    msg = (r.json().get('message') or '').lower()
                except Exception:
                    msg = ''
                if 'not enabled' in msg or 'disabled' in msg:
                    return [], None  # Dependabot nicht aktiviert (public repo)
                return [], False   # echter Scope-Fehler (fehlender security_events Scope)
            if r.status_code in (404, 451):
                return [], None    # Dependabot nicht aktiviert oder nicht verfügbar
            if r.status_code != 200:
                return [], True
            results = list(r.json()) if isinstance(r.json(), list) else []
            for _ in range(20):
                link = r.headers.get('Link', '')
                next_url = None
                for part in link.split(','):
                    if 'rel="next"' in part and len(part) <= 4096:
                        m = re.search(r'<(https?://[^>\s]{1,2048})>', part)
                        if m:
                            next_url = m.group(1)
                if not next_url:
                    break
                r = http.get(next_url, headers=_gh_headers(token), timeout=15)
                if r.status_code != 200:
                    break
                page_data = r.json() if isinstance(r.json(), list) else []
                if not page_data:
                    break
                results.extend(page_data)
            return results, True
        except Exception:
            return [], True

    dep, dep_access = _safe_dep(f'/repos/{repo}/dependabot/alerts')
    # Code Scanning liefert ohne ref-Filter nur Alerts vom Default-Branch (main) —
    # zusätzlich den konfigurierten Dev-Branch abfragen und mergen (dedupe per Alert-Nummer).
    gps   = load_gitpulse_settings()
    main_b = (gps.get('main_branch') or 'main').strip()
    dev_b  = (gps.get('dev_branch') or '').strip()
    cs_main = _safe(f'/repos/{repo}/code-scanning/alerts')
    cs = [_fmt_cs(a, main_b) for a in cs_main]
    if dev_b:
        cs_ids = {a['number'] for a in cs}
        cs_dev = _gh_get_paginated(f'/repos/{repo}/code-scanning/alerts', token, max_pages=10,
                                    params={'state': 'open', 'ref': f'refs/heads/{dev_b}'})
        if isinstance(cs_dev, list):
            cs.extend(_fmt_cs(a, dev_b) for a in cs_dev if a.get('number') not in cs_ids)
    ss  = _safe(f'/repos/{repo}/secret-scanning/alerts')
    return {
        'dependabot':        [_fmt_dep(a) for a in dep],
        'dependabot_access': dep_access,
        'code_scanning':     cs,
        'secret_scanning':   [_fmt_ss(a)  for a in ss],
    }


def _fetch_releases(repos: list[str], token: str, include_betas: bool) -> list[dict]:
    """Fetch latest releases for watch-repos."""
    results = []
    for repo in repos:
        try:
            releases_raw = _gh_get(f'/repos/{repo}/releases', token, {'per_page': 10}) or []
            for rel in releases_raw:
                is_pre = rel.get('prerelease', False)
                tag    = rel['tag_name']
                is_beta = bool(re.search(r'(alpha|beta|rc|dev|b\d)', tag, re.I))
                if is_beta and not include_betas:
                    continue
                results.append({
                    'repo':       repo,
                    'tag':        tag,
                    'name':       rel.get('name') or tag,
                    'url':        rel['html_url'],
                    'date':       rel['published_at'],
                    'prerelease': is_pre or is_beta,
                    'body':       _strip_html(rel.get('body') or '')[:500],
                })
                break  # nur neuestes Release pro Repo
        except Exception as e:
            log.error("Releases für %s: %s", repo, e)
    return results


def _now_iso() -> str:
    """UTC-Zeitstempel im GitHub-Format — direkt mit `created_at` vergleichbar."""
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _fetch_comments_merged(repo: str, number, is_pr: bool, token: str) -> list | None:
    """Alle Kommentare eines Issues/PRs, chronologisch sortiert. Bei PRs kommen
    Review-Texte und Inline-Review-Kommentare aus eigenen Endpunkten dazu — ohne
    sie fehlt genau das, womit Maintainer antworten (z.B. ein "Changes requested"
    mit Begründung). None = Abruf fehlgeschlagen."""

    def _entry(c: dict, kind: str, created_key: str = 'created_at', **extra) -> dict:
        user = c.get('user') or {}
        return {
            'user':    user.get('login', '?'),
            'avatar':  user.get('avatar_url', ''),
            'body':    _strip_html(c.get('body') or '')[:_COMMENT_BODY_MAX],
            'created': c.get(created_key) or '',
            'url':     c.get('html_url', ''),
            'kind':    kind,
            **extra,
        }

    r = http.get(
        f'{GITHUB_API}/repos/{repo}/issues/{number}/comments',
        headers=_gh_headers(token),
        params={'per_page': 100},
        timeout=15,
    )
    _update_rate_limit(r.headers)
    if r.status_code != 200:
        return None
    raw = r.json()
    merged = [_entry(c, 'comment') for c in (raw if isinstance(raw, list) else [])]

    if is_pr:
        for path, kind, ckey in (
            (f'/repos/{repo}/pulls/{number}/reviews',  'review',         'submitted_at'),
            (f'/repos/{repo}/pulls/{number}/comments', 'review_comment', 'created_at'),
        ):
            rr = http.get(f'{GITHUB_API}{path}', headers=_gh_headers(token),
                          params={'per_page': 100}, timeout=15)
            _update_rate_limit(rr.headers)
            if rr.status_code != 200:
                continue
            data = rr.json()
            for c in (data if isinstance(data, list) else []):
                if kind == 'review':
                    state = c.get('state', '')
                    # Leere PENDING/COMMENTED-Reviews sind reine Container
                    # für Inline-Kommentare — die kommen separat.
                    if not (c.get('body') or '').strip() and state not in ('APPROVED', 'CHANGES_REQUESTED'):
                        continue
                    merged.append(_entry(c, kind, ckey, state=state))
                else:
                    merged.append(_entry(c, kind, ckey, path=c.get('path') or ''))

    merged.sort(key=lambda c: c['created'] or '')
    return merged


def _check_comment_updates(items: list, token: str) -> list:
    """Prüft für jedes Item mit geänderter Kommentarzahl, wer die neuen Kommentare
    geschrieben hat.

    Eigene Kommentare werden still als gelesen verbucht (kein Bubble, keine
    Benachrichtigung); fremde Kommentare landen als Ereignis in der Rückgabe.
    `items` sind Dicts aus dem Poll (`repo`, `number`, `title`, `url`, `is_pr`,
    `comments`); deren `comments_new` wird dabei korrigiert.

    Beim ersten Auftauchen eines Items wird der Stand still übernommen, damit
    nicht die gesamte Historie nachgemeldet wird.
    """
    # Dasselbe Item kann mehrfach vorkommen (eigener PR im eigenen Repo steht in
    # repo_data und in my_activity) — einmal prüfen, alle Kopien korrigieren.
    groups: dict[str, list] = {}
    for it in items:
        repo = it.get('repo') or ''
        num  = it.get('number')
        if not repo or num is None:
            continue
        groups.setdefault(f'{repo}#{num}', []).append(it)

    events: list = []
    checked = 0
    dirty   = False
    for key, grp in groups.items():
        repo, _, num_s = key.rpartition('#')
        num   = int(num_s)
        total = max(int(g.get('comments') or 0) for g in grp)
        is_pr = any(g.get('is_pr') for g in grp)
        with _comment_state_lock:
            prev = _comment_state.get(key)
        if prev is not None and total == int(prev.get('total', 0)):
            continue
        if prev is None:
            # Unbekannt: Ist-Stand übernehmen, ohne Kommentare nachzumelden.
            with _comment_state_lock:
                _comment_state[key] = {'total': total, 'ts': _now_iso()}
            dirty = True
            continue
        if checked >= _COMMENT_CHECK_MAX:
            continue
        checked += 1
        try:
            merged = _fetch_comments_merged(repo, num, is_pr, token)
        except Exception as e:
            log.warning("Kommentar-Autoren für %s nicht ladbar: %s", key, e)
            continue
        if merged is None:
            continue
        prev_ts = str(prev.get('ts') or '')
        fresh   = [c for c in merged if (c.get('created') or '') > prev_ts]
        own     = [c for c in fresh if _gh_login and c.get('user') == _gh_login]
        foreign = [c for c in fresh if not (_gh_login and c.get('user') == _gh_login)]
        newest_ts = max([c.get('created') or '' for c in merged] + [prev_ts])
        with _comment_state_lock:
            _comment_state[key] = {'total': total, 'ts': newest_ts}
        dirty = True
        # Eigene Kommentare zählen nicht als ungelesen
        unread = _skip_own_comments(repo, num, len(own), total)
        for g in grp:
            g['comments_new'] = min(unread, int(g.get('comments') or 0))
        if foreign:
            last = foreign[-1]
            base = grp[0]
            events.append({
                'repo':   repo,
                'number': num,
                'title':  base.get('title') or '',
                'url':    base.get('url') or '',
                'is_pr':  is_pr,
                'mine':   any(g.get('mine') for g in grp),
                'count':  len(foreign),
                'author': last.get('user') or '?',
                'body':   (last.get('body') or '')[:200],
            })
    if dirty:
        save_comment_state()
        save_seen_comments()
    return events


def _pr_activity_meta(repo: str, number: int, token: str) -> dict:
    """Review-Status und vollständige Kommentarzahl eines PRs in einem fremden Repo.

    Die Search-API liefert nur `comments` (reine Issue-Kommentare). Review-Texte
    und Inline-Review-Kommentare fehlen dort komplett — genau die, mit denen
    Maintainer üblicherweise antworten. Beide Endpunkte laufen über `_gh_get`,
    also mit ETag-Cache: unveränderte PRs kosten kein Rate-Limit-Kontingent.
    """
    detail  = _gh_get(f'/repos/{repo}/pulls/{number}', token) or {}
    reviews = _gh_get(f'/repos/{repo}/pulls/{number}/reviews', token)
    if not isinstance(reviews, list):
        reviews = []
    requested = detail.get('requested_reviewers') or []
    return {
        'review_state':   _compute_review_state(reviews, len(requested)),
        'reviewers':      [u.get('login', '') for u in requested if u.get('login')],
        'mergeable':      detail.get('mergeable_state') or '',
        'extra_comments': _review_bodies_count(reviews) + (detail.get('review_comments') or 0),
    }


def _fetch_my_activity(login: str, token: str) -> dict:
    """Eigene offene PRs, Issues und Review-Requests via GitHub Search API."""
    if not login:
        return {'prs': [], 'issues': [], 'review_prs': []}
    prs, issues, review_prs = [], [], []

    def _search(q: str) -> list:
        try:
            r = http.get(
                f'{GITHUB_API}/search/issues',
                params={'q': q, 'per_page': 50, 'sort': 'updated'},
                headers=_gh_headers(token), timeout=15,
            )
            if r.status_code == 200:
                return r.json().get('items', [])
        except Exception as e:
            log.error("my_activity search '%s': %s", q, e)
        return []

    # Jeder PR kostet zwei Zusatzabfragen. Bei sehr vielen offenen PRs/Review-Anfragen
    # wird gedeckelt, damit ein Poll nicht das Rate-Limit leerräumt — der Rest bleibt
    # bei den Werten aus der Search-API.
    _meta_budget = [_ACTIVITY_META_MAX]

    def _fmt(item: dict) -> dict:
        _repo  = item['repository_url'].removeprefix(f'{GITHUB_API}/repos/')
        _cmts  = item.get('comments', 0) or 0
        _is_pr = 'pull_request' in item
        _meta  = {}
        if _is_pr and _meta_budget[0] > 0:
            _meta_budget[0] -= 1
            _meta = _pr_activity_meta(_repo, item['number'], token)
        _cmts += _meta.get('extra_comments', 0)
        return {
            'number':   item['number'],
            'title':    item['title'],
            'url':      item['html_url'],
            'repo':     _repo,
            'state':    item['state'],
            'draft':    item.get('draft', False),
            'updated':  item['updated_at'],
            'created':  item['created_at'],
            'comments': _cmts,
            'comments_new': _comments_new(_repo, item['number'], _cmts),
            'is_pr':        _is_pr,
            'review_state': _meta.get('review_state', 'none'),
            'reviewers':    _meta.get('reviewers', []),
            'mergeable':    _meta.get('mergeable', ''),
            'labels':   [l['name'] for l in item.get('labels', [])],
            'body':     _strip_html(item.get('body') or '')[:1000],
        }

    for item in _search(f'author:{login} type:pr state:open'):
        prs.append(_fmt(item))
    for item in _search(f'author:{login} type:issue state:open'):
        issues.append(_fmt(item))
    for item in _search(f'review-requested:{login} type:pr state:open'):
        review_prs.append(_fmt(item))

    save_seen_comments()
    return {'prs': prs, 'issues': issues, 'review_prs': review_prs}


def _send_telegram(token: str, chat_id: str, text: str) -> None:
    try:
        r = http.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            json={'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML',
                  'disable_web_page_preview': True},
            timeout=10,
        )
        if r.status_code != 200:
            log.warning("Telegram Fehler: %s", r.text[:200])
    except Exception as e:
        log.error("Telegram senden fehlgeschlagen: %s", e)


def _send_email(cfg: dict, subject: str, html_body: str) -> None:
    host     = cfg.get('smtp_host', '').strip()
    port     = int(cfg.get('smtp_port', 587))
    user     = cfg.get('smtp_user', '').strip()
    password = cfg.get('smtp_password', '').strip()
    to       = cfg.get('smtp_to', '').strip()
    use_tls  = bool(cfg.get('smtp_tls', True))
    if not host or not to:
        return
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = user or f'gitpulse@{host}'
        msg['To']      = to
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        if use_tls:
            with smtplib.SMTP(host, port, timeout=15) as s:
                s.ehlo()
                s.starttls()
                s.ehlo()
                if user and password:
                    s.login(user, password)
                s.sendmail(msg['From'], [to], msg.as_string())
        else:
            with smtplib.SMTP_SSL(host, port, timeout=15) as s:
                if user and password:
                    s.login(user, password)
                s.sendmail(msg['From'], [to], msg.as_string())
    except Exception as e:
        log.error("E-Mail senden fehlgeschlagen: %s", e)


def _email_html(title: str, lines: list[str]) -> str:
    body = ''.join(f'<p style="margin:4px 0">{l}</p>' for l in lines)
    return (
        '<div style="font-family:sans-serif;max-width:480px;padding:20px;'
        'background:#0d1117;color:#c9d1d9;border-radius:8px">'
        f'<h3 style="margin:0 0 12px;color:#58a6ff">{title}</h3>'
        f'{body}</div>'
    )


# ── SSE helpers ───────────────────────────────────────────────────────────────

def _notify_sse() -> None:
    with _sse_lock:
        for q in list(_sse_queues):
            try:
                q.put_nowait('update')
            except queue.Full:
                pass


# ── Webhook: einzelnen Repo neu laden ────────────────────────────────────────

def _trigger_repo_poll(repo_name: str) -> None:
    """Fetcht einen einzelnen Repo neu und aktualisiert den Cache (für Webhook-Events)."""
    cfg   = load_config()
    token = cfg.get('github_token', '').strip()
    if not token:
        return
    try:
        run_limit = min(500, max(1, int(cfg.get('workflow_run_limit', 25))))
        data = _fetch_repo_data(repo_name, token, min(50, run_limit))
        with _gh_lock:
            repos   = _gh_cache.get('my_repos', [])
            updated = False
            for i, rd in enumerate(repos):
                if rd['repo'] == repo_name:
                    # Runs mergen statt ersetzen — bestehende Liste wächst nie zurück auf 500
                    new_runs      = data.get('runs', [])
                    existing_runs = rd.get('runs', [])
                    existing_ids  = {r['id'] for r in existing_runs}
                    merged = [
                        next((r for r in new_runs if r['id'] == er['id']), er)
                        for er in existing_runs
                    ]
                    brand_new = [r for r in new_runs if r['id'] not in existing_ids]
                    data['runs'] = brand_new + merged
                    repos[i] = data
                    updated  = True
                    break
            if not updated:
                repos.append(data)
                _gh_cache['my_repos'] = repos
            _gh_cache['last_poll'] = int(time.time())
        _notify_sse()
        if _verbose():
            log.info("Webhook-Repo-Poll abgeschlossen: %s", repo_name)
    except Exception as e:
        log.error("Webhook-Repo-Poll Fehler (%s): %s", repo_name, e)


def _alert_notify_once(key: str) -> bool:
    """True, wenn für diesen Alert-Schlüssel im TTL-Fenster noch nicht benachrichtigt wurde.

    GitHub schickt pro neuem Code-Scanning-Alert mehrere Webhooks (z. B. "created"
    und "appeared_in_branch"). Beide bekommen denselben Schlüssel, damit nur der
    erste eine Nachricht auslöst.
    """
    now = time.time()
    with _alert_notify_lock:
        for k, ts in list(_alert_notified.items()):
            if now - ts > _ALERT_NOTIFY_TTL:
                del _alert_notified[k]
        if key in _alert_notified:
            return False
        _alert_notified[key] = now
        return True


def _tg_em(cfg: dict, tg_token: str, tg_chat: str, tg_notif: dict, em_notif: dict,
           key: str, tg_text: str, em_subject: str, em_lines: list) -> None:
    if tg_token and tg_chat and tg_notif.get(key, True):
        _send_telegram(tg_token, tg_chat, tg_text)
    if em_notif.get(key, True):
        _send_email(cfg, em_subject, _email_html(em_subject, em_lines))


def _send_daily_digest(cfg: dict, tg_token: str, tg_chat: str,
                       tg_notif: dict, em_notif: dict, repo_data: list) -> None:
    """Tages-Digest einmal täglich senden — zusätzlich zu Echtzeit-Benachrichtigungen."""
    total_prs     = sum(rd.get('open_prs', 0) for rd in repo_data)
    total_issues  = sum(rd.get('open_issues', 0) for rd in repo_data)
    total_sec     = sum((rd.get('insights') or {}).get('security_count', 0) for rd in repo_data)
    today_str     = datetime.now().strftime('%d.%m.%Y')
    subject_tg    = f"📋 <b>GitPulse Tages-Digest</b> — {today_str}"
    subject_em    = f"GitPulse Tages-Digest — {today_str}"
    lines_tg: list[str] = []
    lines_em: list[str] = []
    for rd in repo_data:
        prs    = rd.get('open_prs', 0)
        issues = rd.get('open_issues', 0)
        sec    = (rd.get('insights') or {}).get('security_count', 0)
        sec_s  = f' · 🔒 {sec}' if sec else ''
        lines_tg.append(f"• <b>{rd['name']}</b> — {prs} PR{'s' if prs!=1 else ''}, {issues} Issue{'s' if issues!=1 else ''}{sec_s}")
        lines_em.append(f"• <b>{rd['name']}</b> — {prs} PRs, {issues} Issues{sec_s}")
    lines_tg.append(f"\n<b>Gesamt: {total_prs} PRs, {total_issues} Issues"
                    + (f', 🔒 {total_sec} Alerts' if total_sec else '') + '</b>')
    lines_em.append(f"Gesamt: {total_prs} PRs, {total_issues} Issues"
                    + (f', 🔒 {total_sec} Alerts' if total_sec else ''))
    _tg_em(cfg, tg_token, tg_chat, tg_notif, em_notif, 'digest',
           subject_tg + '\n' + '\n'.join(lines_tg),
           subject_em, lines_em)
    log.info("Tages-Digest gesendet (%d Repos)", len(repo_data))


# ── Poll worker ───────────────────────────────────────────────────────────────

def _poll_worker() -> None:
    log.info("GitHub-Poller gestartet")
    while True:
        cfg = load_config()
        token = cfg.get('github_token', '').strip()
        interval = max(10, int(cfg.get('poll_interval', POLL_INTERVAL_DEFAULT)))

        if not token:
            log.warning("Kein GitHub-Token konfiguriert — überspringe Poll")
            time.sleep(interval)
            continue

        try:
            _do_poll(cfg, token)
        except Exception as e:
            log.error("Poll-Fehler: %s", e)
            with _gh_lock:
                _gh_cache['error'] = str(e)

        # Auto-Anpassung Schlafzeit bei Rate-Limit-Engpass
        rem   = _rate_limit.get('remaining', 5000)
        reset = _rate_limit.get('reset', 0)
        if rem <= 0 and reset > 0:
            wait = max(interval, reset - int(time.time()) + 10)
            log.warning("Rate-Limit erschöpft — warte %ds bis Reset", wait)
        elif rem < 100:
            wait = max(interval, interval * 3)
            log.warning("Rate-Limit sehr niedrig (%d verbleibend) — erhöhe Wartezeit auf %ds", rem, wait)
        elif rem < 500:
            wait = max(interval, interval * 2)
            log.info("Rate-Limit niedrig (%d verbleibend) — erhöhe Wartezeit auf %ds", rem, wait)
        else:
            wait = interval

        time.sleep(wait)


def _do_poll(cfg: dict, token: str) -> None:
    global _seen_releases, _seen_activity, _first_poll_done, _gh_login
    global _last_digest_date, _seen_review_prs

    token_ok, scopes, expires = _check_token(token)
    if not token_ok:
        with _gh_lock:
            _gh_cache['token_ok'] = False
            _gh_cache['error'] = 'Token ungültig oder abgelaufen'
        _notify_sse()
        return

    if not _gh_login:
        try:
            r = http.get(f'{GITHUB_API}/user', headers=_gh_headers(token), timeout=10)
            if r.status_code == 200:
                _gh_login = r.json().get('login', '')
                log.info("GitHub-Login: %s", _gh_login)
        except Exception as e:
            log.warning("GitHub-Login konnte nicht geladen werden: %s", e)

    user_repos = load_user_repos()
    if user_repos is not None:
        my_repos    = [r for r in user_repos.get('my_repos', [])    if r.strip()]
        watch_repos = [r for r in user_repos.get('watch_repos', []) if r.strip()]
    else:
        my_repos    = [r for r in cfg.get('my_repos', [])    if r.strip()]
        watch_repos = [r for r in cfg.get('watch_repos', []) if r.strip()]
    incl_betas = bool(cfg.get('include_ha_betas', True))
    tg_token   = cfg.get('telegram_bot_token', '').strip()
    tg_chat    = cfg.get('telegram_chat_id', '').strip()
    tg_notif   = (user_repos or {}).get('tg_notifications', {})
    em_notif   = (user_repos or {}).get('email_notifications', {})
    run_limit  = min(500, max(1, int(cfg.get('workflow_run_limit', 25))))

    if _verbose():
        log.info("Polling %d eigene Repos, %d Watch-Repos", len(my_repos), len(watch_repos))

    # eigene Repos
    repo_data = []
    for repo in my_repos:
        try:
            # Initialer Poll: volle run_limit laden; folgende Polls: nur 50 holen + mergen
            poll_limit = run_limit if not _first_poll_done else min(50, run_limit)
            data = _fetch_repo_data(repo, token, poll_limit)

            if _first_poll_done:
                with _gh_lock:
                    existing = next(
                        (rd for rd in _gh_cache.get('my_repos', []) if rd['repo'] == repo), None
                    )
                if existing:
                    new_runs = data.get('runs', [])
                    new_ids  = {r['id'] for r in new_runs}
                    # Bestehende Runs mit frischen Status-Daten aktualisieren
                    updated = [
                        next((r for r in new_runs if r['id'] == er['id']), er)
                        for er in existing.get('runs', [])
                    ]
                    # Neue Runs vorne einfügen
                    brand_new = [r for r in new_runs if r['id'] not in {er['id'] for er in existing.get('runs', [])}]
                    data['runs'] = brand_new + updated

            repo_data.append(data)
            if _verbose():
                pr_cnt = int(data['open_prs'])
                issue_cnt = int(data['open_issues'])
                log.info("%s — %d PRs, %d Issues", repo, pr_cnt, issue_cnt)
        except Exception as e:
            log.error("Repo %s Fehler: %s", repo, e)

    # Telegram: neue PRs / Issues / CI-Failures erkennen
    for rd in repo_data:
        rname = rd['repo']

        for pr in rd.get('pulls', []):
            key = pr['number']
            if key not in _seen_prs[rname]:
                if _first_poll_done:
                    _tg_em(cfg, tg_token, tg_chat, tg_notif, em_notif, 'new_pr',
                        f"🔀 Neuer PR: <b>{rname}</b>\n#{pr['number']} {pr['title']}\nvon @{pr['user']}\n<a href=\"{pr['url']}\">PR öffnen</a>",
                        f"Neuer PR: {rname}",
                        [f"#{pr['number']} {pr['title']}", f"von @{pr['user']}", f"<a href=\"{pr['url']}\">PR öffnen</a>"])
                _seen_prs[rname].add(key)

        for iss in rd.get('issues', []):
            key = iss['number']
            if key not in _seen_issues[rname]:
                if _first_poll_done:
                    _tg_em(cfg, tg_token, tg_chat, tg_notif, em_notif, 'new_issue',
                        f"🐛 Neues Issue: <b>{rname}</b>\n#{iss['number']} {iss['title']}\nvon @{iss['user']}\n<a href=\"{iss['url']}\">Issue öffnen</a>",
                        f"Neues Issue: {rname}",
                        [f"#{iss['number']} {iss['title']}", f"von @{iss['user']}", f"<a href=\"{iss['url']}\">Issue öffnen</a>"])
                _seen_issues[rname].add(key)

        for run in rd.get('runs', []):
            run_id   = run['id']
            curr_con = run.get('conclusion')
            _con_icons  = {'success': '✅', 'failure': '❌', 'cancelled': '⏹', 'skipped': '⏭', 'timed_out': '⏱'}
            _con_labels = {'success': 'Erfolgreich', 'failure': 'Fehlgeschlagen', 'cancelled': 'Abgebrochen',
                           'skipped': 'Übersprungen', 'timed_out': 'Timeout'}
            _evt_labels = {'push': 'Push', 'pull_request': 'PR', 'workflow_dispatch': 'Manuell',
                           'schedule': 'Zeitplan', 'release': 'Release'}
            run_info_tg = (f"<b>{run['name']}</b> #{run.get('run_number','')}\n"
                           f"Branch: {run.get('branch','?')} · {_evt_labels.get(run.get('event',''), run.get('event','?'))}\n"
                           f"von @{run.get('actor','?')} · {run.get('head_sha','')[:7]}\n")
            run_info_em = [f"<b>{run['name']}</b> #{run.get('run_number','')}",
                           f"Branch: {run.get('branch','?')} · {_evt_labels.get(run.get('event',''), run.get('event','?'))}",
                           f"von @{run.get('actor','?')} · {run.get('head_sha','')[:7]}"]
            if run_id not in _known_run_conclusions:
                if _first_poll_done:
                    if curr_con is None:
                        _tg_em(cfg, tg_token, tg_chat, tg_notif, em_notif, 'workflow_started',
                            f"▶️ <b>Workflow gestartet:</b> {rname}\n" + run_info_tg + f"<a href=\"{run['url']}\">Details</a>",
                            f"Workflow gestartet: {rname}",
                            run_info_em + [f"<a href=\"{run['url']}\">Details</a>"])
                    else:
                        icon  = _con_icons.get(curr_con, '⚠️')
                        label = _con_labels.get(curr_con, curr_con)
                        _tg_em(cfg, tg_token, tg_chat, tg_notif, em_notif, 'workflow_completed',
                            f"{icon} <b>Workflow beendet:</b> {rname}\n" + run_info_tg + f"Status: {label}\n<a href=\"{run['url']}\">Details</a>",
                            f"Workflow beendet: {rname} — {label}",
                            run_info_em + [f"Status: {label}", f"<a href=\"{run['url']}\">Details</a>"])
            else:
                prev_con = _known_run_conclusions[run_id]
                if prev_con is None and curr_con is not None:
                    icon  = _con_icons.get(curr_con, '⚠️')
                    label = _con_labels.get(curr_con, curr_con)
                    if _first_poll_done:
                        _tg_em(cfg, tg_token, tg_chat, tg_notif, em_notif, 'workflow_completed',
                            f"{icon} <b>Workflow beendet:</b> {rname}\n" + run_info_tg + f"Status: {label}\n<a href=\"{run['url']}\">Details</a>",
                            f"Workflow beendet: {rname} — {label}",
                            run_info_em + [f"Status: {label}", f"<a href=\"{run['url']}\">Details</a>"])
            _known_run_conclusions[run_id] = curr_con

    # Benachrichtigungen: Stars / Forks / Watchers Änderungen erkennen
    for rd in repo_data:
        rname = rd['repo']
        curr_stats = {
            'stars':    rd.get('stars', 0),
            'forks':    rd.get('forks', 0),
            'watchers': rd.get('watchers', 0),
        }
        if rname in _repo_stats and _first_poll_done:
            prev_stats = _repo_stats[rname]
            changes_tg = []
            changes_em = []
            if curr_stats['stars'] != prev_stats['stars']:
                diff = curr_stats['stars'] - prev_stats['stars']
                sign = '+' if diff > 0 else ''
                changes_tg.append(f"⭐ Stars: {prev_stats['stars']} → {curr_stats['stars']} ({sign}{diff})")
                changes_em.append(f"⭐ Stars: {prev_stats['stars']} → {curr_stats['stars']} ({sign}{diff})")
            if curr_stats['forks'] != prev_stats['forks']:
                diff = curr_stats['forks'] - prev_stats['forks']
                sign = '+' if diff > 0 else ''
                changes_tg.append(f"🍴 Forks: {prev_stats['forks']} → {curr_stats['forks']} ({sign}{diff})")
                changes_em.append(f"🍴 Forks: {prev_stats['forks']} → {curr_stats['forks']} ({sign}{diff})")
            if curr_stats['watchers'] != prev_stats['watchers']:
                diff = curr_stats['watchers'] - prev_stats['watchers']
                sign = '+' if diff > 0 else ''
                changes_tg.append(f"👁 Watchers: {prev_stats['watchers']} → {curr_stats['watchers']} ({sign}{diff})")
                changes_em.append(f"👁 Watchers: {prev_stats['watchers']} → {curr_stats['watchers']} ({sign}{diff})")
            if changes_tg:
                _tg_em(cfg, tg_token, tg_chat, tg_notif, em_notif, 'repo_stats',
                    f"📊 <b>Repo-Statistiken:</b> <b>{rname}</b>\n" + '\n'.join(changes_tg),
                    f"Repo-Statistiken: {rname}",
                    changes_em)
        _repo_stats[rname] = curr_stats

    # Startup-Nachricht (einmalig beim ersten Poll)
    if not _first_poll_done:
        msg_tg = "🚀 <b>GitPulse gestartet</b>\n"
        msg_em = ["🚀 <b>GitPulse gestartet</b>"]
        if repo_data:
            msg_tg += "\n<b>Eigene Repos:</b>"
            msg_em.append("<b>Eigene Repos:</b>")
            for rd in repo_data:
                prs    = rd.get('open_prs', 0)
                issues = rd.get('open_issues', 0)
                line   = f"• <b>{rd['name']}</b> — {prs} PR{'s' if prs != 1 else ''}, {issues} Issue{'s' if issues != 1 else ''}"
                msg_tg += f"\n{line}"
                msg_em.append(line)
        else:
            msg_tg += "\nKeine eigenen Repos konfiguriert."
            msg_em.append("Keine eigenen Repos konfiguriert.")
        _tg_em(cfg, tg_token, tg_chat, tg_notif, em_notif, 'startup',
               msg_tg, "GitPulse gestartet", msg_em)

    _first_poll_done = True

    # Watch-Repos Releases
    releases = _fetch_releases(watch_repos, token, incl_betas)

    # Neue Releases erkennen + Benachrichtigung
    new_releases = []
    for rel in releases:
        key = f"{rel['repo']}@{rel['tag']}"
        if key not in _seen_releases:
            new_releases.append(rel)
            _seen_releases.add(key)
            log.info("Neues Release: %s %s", rel['repo'], rel['tag'])
            rl_type = '🔵 Pre-Release' if rel['prerelease'] else '🟢 Release'
            _tg_em(cfg, tg_token, tg_chat, tg_notif, em_notif, 'releases',
                f"{rl_type}: <b>{rel['repo']}</b>\nVersion: <code>{rel['tag']}</code>\n<a href=\"{rel['url']}\">Release-Seite</a>",
                f"{rl_type}: {rel['repo']} {rel['tag']}",
                [f"Repo: <b>{rel['repo']}</b>", f"Version: <b>{rel['tag']}</b>", f"<a href=\"{rel['url']}\">Release-Seite</a>"])

    if new_releases:
        save_seen_releases()

    # Eigene Aktivität (PRs + Issues die ich erstellt habe)
    activity = _fetch_my_activity(_gh_login, token)
    activity_changed = False
    all_items = [('pr', pr) for pr in activity['prs']] + [('issue', iss) for iss in activity['issues']]
    for kind, item in all_items:
        key = f"{item['repo']}#{item['number']}:open"
        if _first_poll_done:
            if key not in _seen_activity:
                _seen_activity.add(key)
                activity_changed = True
                if kind == 'pr':
                    _tg_em(cfg, tg_token, tg_chat, tg_notif, em_notif, 'my_activity',
                        f"🔀 Neuer eigener PR: <b>{item['repo']}</b>\n<a href=\"{item['url']}\">#PR{item['number']} {item['title']}</a>",
                        f"Neuer eigener PR: {item['repo']} #{item['number']} {item['title']}",
                        [f"Repo: <b>{item['repo']}</b>", f"PR: <a href=\"{item['url']}\">#PR{item['number']} {item['title']}</a>"])
                else:
                    _tg_em(cfg, tg_token, tg_chat, tg_notif, em_notif, 'my_activity',
                        f"🐛 Neues eigenes Issue: <b>{item['repo']}</b>\n<a href=\"{item['url']}\">#I{item['number']} {item['title']}</a>",
                        f"Neues eigenes Issue: {item['repo']} #{item['number']} {item['title']}",
                        [f"Repo: <b>{item['repo']}</b>", f"Issue: <a href=\"{item['url']}\">#I{item['number']} {item['title']}</a>"])
        else:
            _seen_activity.add(key)
            activity_changed = True
    if activity_changed:
        save_seen_activity()

    # Neue Kommentare — eigene zählen nicht (weder Bubble noch Benachrichtigung).
    # Läuft auch beim ersten Poll nach einem Neustart: der Zustand ist persistent,
    # ein unbekanntes Item wird still übernommen, ein gewachsenes meldet sich.
    comment_items = []
    for rd in repo_data:
        for _lst, _is_pr in ((rd.get('pulls'), True), (rd.get('issues'), False),
                             (rd.get('closed_pulls'), True), (rd.get('closed_issues'), False)):
            for _it in (_lst or []):
                _it.setdefault('repo', rd['repo'])
                _it['is_pr'] = _is_pr
                comment_items.append(_it)
    for _kind, _it in all_items:
        _it['is_pr'] = _kind == 'pr'
        _it['mine']  = True
        comment_items.append(_it)
    for _rpr in activity.get('review_prs', []):
        _rpr['is_pr'] = True
        comment_items.append(_rpr)

    new_comments = _check_comment_updates(comment_items, token)
    for ev in new_comments:
        label = 'PR' if ev['is_pr'] else 'Issue'
        ref   = f"#PR{ev['number']}" if ev['is_pr'] else f"#I{ev['number']}"
        cnt_s = f"{ev['count']} neuer Kommentar{'e' if ev['count'] > 1 else ''}"
        where = f"auf deinem {label}" if ev['mine'] else f"an {label}"
        _tg_em(cfg, tg_token, tg_chat, tg_notif, em_notif, 'new_comment',
            f"💬 Neuer Kommentar {where}: <b>{ev['repo']}</b>\n"
            f"<a href=\"{ev['url']}\">{ref} {ev['title']}</a>\nvon @{ev['author']} · {cnt_s}",
            f"Neuer Kommentar {where} {ev['repo']} #{ev['number']}",
            [f"Repo: <b>{ev['repo']}</b>",
             f"{label}: <a href=\"{ev['url']}\">{ref} {ev['title']}</a>",
             f"von <b>@{ev['author']}</b> · {cnt_s}"])

    # Review-Requests: benachrichtigen wenn neue PRs zur Review angefragt wurden
    for rpr in activity.get('review_prs', []):
        rkey = f"{rpr['repo']}#{rpr['number']}"
        if rkey not in _seen_review_prs:
            if _first_poll_done:
                _tg_em(cfg, tg_token, tg_chat, tg_notif, em_notif, 'review_request',
                    f"🔍 Review angefragt: <b>{rpr['repo']}</b>\n<a href=\"{rpr['url']}\">#PR{rpr['number']} {rpr['title']}</a>",
                    f"Review angefragt: {rpr['repo']} #{rpr['number']} {rpr['title']}",
                    [f"Repo: <b>{rpr['repo']}</b>",
                     f"PR: <a href=\"{rpr['url']}\">#PR{rpr['number']} {rpr['title']}</a>"])
            _seen_review_prs.add(rkey)

    # Tages-Digest
    digest_hour = int(cfg.get('digest_hour', -1))
    if digest_hour >= 0 and _first_poll_done:
        now_dt = datetime.now()
        today  = now_dt.strftime('%Y-%m-%d')
        if now_dt.hour == digest_hour and today != _last_digest_date:
            _send_daily_digest(cfg, tg_token, tg_chat, tg_notif, em_notif, repo_data)
            _last_digest_date = today

    with _gh_lock:
        _gh_cache['my_repos']      = repo_data
        _gh_cache['releases']      = releases
        _gh_cache['my_activity']          = {
            'prs':        activity.get('prs', []),
            'issues':     activity.get('issues', []),
            'review_prs': activity.get('review_prs', []),
        }
        _gh_cache['new_comments']         = new_comments
        _gh_cache['gh_login']             = _gh_login
        _gh_cache['token_ok']      = True
        _gh_cache['token_scopes']  = scopes
        _gh_cache['token_expires'] = expires
        _gh_cache['last_poll']     = int(time.time())
        _gh_cache['error']         = None
        _gh_cache['new_releases']  = new_releases
        _gh_cache['rate_limit']    = dict(_rate_limit)

    _notify_sse()
    if _verbose():
        log.info("Poll abgeschlossen — %d Repos, %d Watch-Releases", len(repo_data), len(releases))


# ── Routes ────────────────────────────────────────────────────────────────────

def _is_ingress() -> bool:
    """True wenn der Request durch den HA Supervisor Ingress-Proxy kam."""
    return bool(request.script_root)


def _auth_required(req):
    if _is_ingress():
        return None  # HA übernimmt die Authentifizierung
    token = req.cookies.get('session')
    if not is_valid_session(token):
        return redirect(url_for('login'))
    return None


@app.route('/health')
def health():
    return 'OK', 200


@app.route('/manifest.json')
def manifest():
    base = request.script_root.rstrip('/')
    data = {
        'name': 'GitPulse',
        'short_name': 'GitPulse',
        'description': 'GitHub Control Panel für Home Assistant',
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


@app.route('/set-lang/<lang>')
def set_lang(lang: str):
    cookie_lang = 'en' if lang == 'en' else 'de'
    next_url = request.args.get('next', '/')
    next_url = next_url.replace('\\', '')
    parsed_next = urlparse(next_url)
    if parsed_next.scheme or parsed_next.netloc or not next_url.startswith('/'):
        next_url = '/'
    resp = make_response(redirect(next_url))
    resp.set_cookie('lang', cookie_lang, max_age=365 * 86400, samesite='Lax')
    return resp


@app.route('/login', methods=['GET', 'POST'])
def login():
    lang = detect_language(request)
    t    = load_translations(lang)
    cfg  = load_config()

    if _is_ingress() or is_valid_session(request.cookies.get('session')):
        return redirect(url_for('index'))

    error = None
    if request.method == 'POST':
        ip = get_client_ip(request)
        if is_rate_limited(ip):
            error = t.get('error_locked', 'Zu viele Fehlversuche. Bitte 15 Minuten warten.')
        else:
            uname = request.form.get('username', '')
            pwd   = request.form.get('password', '')
            if (uname == cfg.get('username', 'admin') and
                    pwd == cfg.get('password', 'secret')):
                clear_failed_attempts(ip)
                token, _ = create_session(int(cfg.get('session_hours', 24)))
                resp = make_response(redirect(url_for('index')))
                resp.set_cookie('session', token, httponly=True,
                                samesite='Lax', max_age=int(cfg.get('session_hours', 24)) * 3600)
                return resp
            else:
                record_failed_attempt(ip)
                error = t.get('error_credentials', 'Ungültige Anmeldedaten.')

    resp = make_response(render_template('login.html', t=t, lang=lang, error=error,
                                         script_root=request.script_root))
    return resp


@app.route('/logout')
def logout():
    token = request.cookies.get('session')
    if token and token in sessions:
        del sessions[token]
        save_sessions()
    resp = make_response(redirect('/login'))
    resp.delete_cookie('session')
    return resp


@app.route('/')
def index():
    redir = _auth_required(request)
    if redir:
        return redir
    lang = detect_language(request)
    t    = load_translations(lang)
    cfg  = load_config()
    resp = make_response(render_template('index.html', t=t, lang=lang,
                                         poll_interval=int(cfg.get('poll_interval', POLL_INTERVAL_DEFAULT)),
                                         addon_manager=bool(cfg.get('addon_manager', False)),
                                         script_root=request.script_root))
    return resp


@app.route('/api/data')
def api_data():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    with _gh_lock:
        data = dict(_gh_cache)
    return jsonify(data)


@app.route('/api/console')
def api_console():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    since = int(request.args.get('since', 0))
    entries = [e for e in list(_log_buffer) if e['ts'] > since]
    return jsonify(entries)


@app.route('/api/poll-now', methods=['POST'])
def api_poll_now():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    cfg   = load_config()
    token = cfg.get('github_token', '').strip()
    if not token:
        return jsonify({'error': 'Kein Token konfiguriert'}), 400
    threading.Thread(target=_do_poll, args=(cfg, token), daemon=True).start()
    return jsonify({'status': 'polling'})


@app.route('/api/seen-releases/reset', methods=['POST'])
def api_reset_seen():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    global _seen_releases
    # Alle aktuell bekannten Releases als gesehen markieren (nicht löschen)
    # → nächster Poll meldet sie nicht mehr als neu, kein Telegram doppelt
    with _gh_lock:
        releases = list(_gh_cache.get('releases', []))
        _gh_cache['new_releases'] = []   # Badge sofort weg
    for rel in releases:
        _seen_releases.add(f"{rel['repo']}@{rel['tag']}")
    save_seen_releases()
    log.info("Releases als gelesen markiert: %d Einträge gesamt", len(_seen_releases))
    return jsonify({'status': 'ok'})


@app.route('/api/pr/recent-closed')
def api_pr_recent_closed():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    repo_full = request.args.get('repo', '').strip()
    addon_dir = request.args.get('addon_dir', '').strip()
    if not repo_full or '/' not in repo_full:
        return jsonify({'error': 'invalid_params'}), 400
    token = load_config().get('github_token', '').strip()
    if not token:
        return jsonify({'error': 'no_token'}), 400
    try:
        r = http.get(
            f'{GITHUB_API}/repos/{repo_full}/pulls',
            headers=_gh_headers(token),
            params={'state': 'closed', 'per_page': 30, 'sort': 'updated', 'direction': 'desc'},
            timeout=15,
        )
        _update_rate_limit(r.headers)
        if r.status_code != 200:
            return jsonify({'error': f'github_{r.status_code}'}), 502
        prs = []
        needle = addon_dir.lower() if addon_dir else ''
        for pr in r.json():
            branch = pr.get('head', {}).get('ref', '')
            title  = pr.get('title', '')
            matches = bool(needle and (needle in branch.lower() or needle in title.lower()))
            prs.append({
                'number':    pr['number'],
                'title':     title,
                'body':      pr.get('body') or '',
                'merged_at': pr.get('merged_at'),
                'closed_at': pr.get('closed_at'),
                'branch':    branch,
                'matches':   matches,
            })
        return jsonify({'prs': prs})
    except Exception:
        log.exception("recent-closed PRs Fehler")
        return jsonify({'error': 'internal error'}), 500


@app.route('/api/pr/close', methods=['POST'])
def api_pr_close():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    body   = request.get_json(silent=True) or {}
    repo   = body.get('repo', '').strip()
    pr_nr  = body.get('number')
    if not repo or not pr_nr:
        return jsonify({'error': 'repo und number erforderlich'}), 400
    token = load_config().get('github_token', '').strip()
    if not token:
        return jsonify({'error': 'Kein Token konfiguriert'}), 400
    try:
        r = http.patch(
            f'{GITHUB_API}/repos/{repo}/pulls/{pr_nr}',
            headers=_gh_headers(token),
            json={'state': 'closed'},
            timeout=15,
        )
        _update_rate_limit(r.headers)
        if r.status_code == 200:
            log.info("PR #%s in %s geschlossen", pr_nr, repo)
            return jsonify({'status': 'closed'})
        msg = r.json().get('message', f'HTTP {r.status_code}')
        log.warning("PR-Close fehlgeschlagen: %s", msg)
        return jsonify({'error': msg}), r.status_code
    except Exception:
        log.exception("PR-Close Fehler")
        return jsonify({'error': 'internal error'}), 500


@app.route('/api/pr/merge', methods=['POST'])
def api_pr_merge():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    body  = request.get_json(silent=True) or {}
    repo  = body.get('repo', '').strip()
    pr_nr = body.get('number')
    method = body.get('method', 'merge')  # merge | squash | rebase
    if not repo or not pr_nr:
        return jsonify({'error': 'repo und number erforderlich'}), 400
    if method not in ('merge', 'squash', 'rebase'):
        return jsonify({'error': 'Ungültige Merge-Methode'}), 400
    token = load_config().get('github_token', '').strip()
    if not token:
        return jsonify({'error': 'Kein Token konfiguriert'}), 400
    try:
        r = http.put(
            f'{GITHUB_API}/repos/{repo}/pulls/{pr_nr}/merge',
            headers=_gh_headers(token),
            json={'merge_method': method},
            timeout=15,
        )
        if r.status_code == 200:
            log.info("PR #%s in %s gemergt (%s)", pr_nr, repo, method)
            return jsonify({'status': 'merged'})
        data = r.json()
        msg  = data.get('message', f'HTTP {r.status_code}')
        log.warning("PR-Merge fehlgeschlagen: %s", msg)
        return jsonify({'error': msg}), r.status_code
    except Exception:
        log.exception("PR-Merge Fehler")
        return jsonify({'error': 'internal error'}), 500


@app.route('/api/branches')
def api_branches():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    repo    = request.args.get('repo', '').strip()
    do_info = request.args.get('info', '0') == '1'
    if not repo:
        return jsonify({'error': 'repo fehlt'}), 400
    cfg   = load_config()
    token = cfg.get('github_token', '').strip()
    if not token:
        return jsonify({'error': 'kein Token'}), 400
    hdrs = _gh_headers(token)
    try:
        raw = _gh_get_paginated(f'/repos/{repo}/branches', token)
        branch_objs = [b for b in (raw or []) if isinstance(b, dict) and 'name' in b]

        if not do_info:
            return jsonify([b['name'] for b in branch_objs])

        _PROTECTED = {'main', 'master', 'dev', 'develop'}

        # Open PRs: head branch name → PR number
        raw_prs = _gh_get_paginated(f'/repos/{repo}/pulls', token, params={'state': 'open'})
        open_pr_map: dict[str, int] = {}
        for pr in (raw_prs or []):
            if isinstance(pr, dict):
                ref = (pr.get('head') or {}).get('ref')
                if ref:
                    open_pr_map[ref] = pr.get('number')

        # Compare base: first protected branch that actually exists
        existing = {b['name'] for b in branch_objs}
        compare_base = next(
            (c for c in ('main', 'master', 'dev', 'develop') if c in existing),
            None
        )

        # Parallel ahead_by checks (how many commits branch has that base doesn't)
        def _ahead(name: str):
            if not compare_base or name == compare_base:
                return None
            try:
                r = http.get(
                    f'{GITHUB_API}/repos/{repo}/compare/{compare_base}...{name}',
                    headers=hdrs, params={'per_page': 1}, timeout=10
                )
                return r.json().get('ahead_by') if r.status_code == 200 else None
            except Exception:
                return None

        non_prot = [b['name'] for b in branch_objs if b['name'].lower() not in _PROTECTED]
        with ThreadPoolExecutor(max_workers=6) as ex:
            ahead_map = dict(zip(non_prot, ex.map(_ahead, non_prot)))

        result = []
        for b in branch_objs:
            name = b['name']
            prot = name.lower() in _PROTECTED
            result.append({
                'name':         name,
                'protected':    prot,
                'open_pr':      open_pr_map.get(name),
                'ahead_by':     None if prot else ahead_map.get(name),
                'compare_base': compare_base,
            })
        return jsonify(result)
    except Exception:
        log.exception("Branches-Abfrage Fehler (%s)", repo)
        return jsonify({'error': 'internal error'}), 500


@app.route('/api/compare')
def api_compare():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    repo = request.args.get('repo', '').strip()
    base = request.args.get('base', '').strip()
    head = request.args.get('head', '').strip()
    if not repo or not base or not head:
        return jsonify({'error': 'repo, base und head erforderlich'}), 400
    token = load_config().get('github_token', '').strip()
    if not token:
        return jsonify({'error': 'kein Token'}), 400
    try:
        r = http.get(
            f'{GITHUB_API}/repos/{repo}/compare/{base}...{head}',
            headers=_gh_headers(token),
            timeout=15,
        )
        _update_rate_limit(r.headers)
        if r.status_code != 200:
            msg = r.json().get('message', f'HTTP {r.status_code}') if r.content else f'HTTP {r.status_code}'
            return jsonify({'error': msg}), r.status_code
        data = r.json()
        commits = [
            {
                'sha':      c['sha'],
                'short':    c['sha'][:7],
                'message':  c['commit']['message'].split('\n')[0][:120],
                'author':   c['commit']['author']['name'],
                'date':     c['commit']['author']['date'],
                'url':      c.get('html_url', ''),
                'is_merge': len(c.get('parents', [])) > 1,
            }
            for c in data.get('commits', [])
        ]
        return jsonify({'commits': commits, 'ahead_by': data.get('ahead_by', 0)})
    except Exception:
        log.exception("Compare-Fehler (%s %s...%s)", repo, base, head)
        return jsonify({'error': 'internal error'}), 500


@app.route('/api/cherry-pick', methods=['POST'])
def api_cherry_pick():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    data   = request.get_json(silent=True) or {}
    repo   = data.get('repo', '').strip()
    shas   = data.get('commits', [])
    target = data.get('target', '').strip()
    token  = load_config().get('github_token', '').strip()
    if not all([token, repo, shas, target]):
        return jsonify({'error': 'Parameter fehlen'}), 400
    hdrs = _gh_headers(token)
    try:
        # 1. Ziel-Branch HEAD SHA ermitteln
        r = http.get(f'{GITHUB_API}/repos/{repo}/git/ref/heads/{target}',
                     headers=hdrs, timeout=10)
        _update_rate_limit(r.headers)
        if r.status_code != 200:
            return jsonify({'error': f'Branch "{target}" nicht gefunden'}), 404
        base_sha = r.json()['object']['sha']

        # 2. Neuen Branch erstellen
        short    = shas[0][:7]
        ts       = int(time.time()) % 100000
        new_name = f'cherry-pick/{short}-to-{target}-{ts}'
        r2 = http.post(f'{GITHUB_API}/repos/{repo}/git/refs',
                       headers=hdrs,
                       json={'ref': f'refs/heads/{new_name}', 'sha': base_sha},
                       timeout=10)
        _update_rate_limit(r2.headers)
        if r2.status_code not in (201, 422):
            return jsonify({'error': f'Branch konnte nicht erstellt werden: {r2.text[:200]}'}), 500

        # 3. Commits einzeln anwenden
        errors: list[str] = []
        for sha in shas:
            commit_r = http.get(f'{GITHUB_API}/repos/{repo}/commits/{sha}',
                                headers=hdrs, timeout=15)
            _update_rate_limit(commit_r.headers)
            if commit_r.status_code != 200:
                errors.append(f'Commit {sha[:7]}: nicht ladbar')
                continue
            for f in commit_r.json().get('files', []):
                path   = f['filename']
                status = f['status']
                try:
                    if status == 'removed':
                        ex = http.get(f'{GITHUB_API}/repos/{repo}/contents/{path}',
                                      headers=hdrs, params={'ref': new_name}, timeout=10)
                        if ex.status_code == 200:
                            http.delete(f'{GITHUB_API}/repos/{repo}/contents/{path}',
                                        headers=hdrs,
                                        json={'message': f'cherry-pick {sha[:7]}: remove {path}',
                                              'sha': ex.json()['sha'], 'branch': new_name},
                                        timeout=10)
                    else:
                        if status == 'renamed':
                            old_path = f.get('previous_filename', '')
                            if old_path:
                                ex_old = http.get(f'{GITHUB_API}/repos/{repo}/contents/{old_path}',
                                                  headers=hdrs, params={'ref': new_name}, timeout=10)
                                if ex_old.status_code == 200:
                                    http.delete(f'{GITHUB_API}/repos/{repo}/contents/{old_path}',
                                                headers=hdrs,
                                                json={'message': f'cherry-pick {sha[:7]}: rename {old_path}',
                                                      'sha': ex_old.json()['sha'], 'branch': new_name},
                                                timeout=10)
                        cr = http.get(f'{GITHUB_API}/repos/{repo}/contents/{path}',
                                      headers=hdrs, params={'ref': sha}, timeout=10)
                        _update_rate_limit(cr.headers)
                        if cr.status_code != 200:
                            errors.append(f'{path}: Inhalt nicht ladbar')
                            continue
                        cdata = cr.json()
                        if cdata.get('encoding') != 'base64':
                            errors.append(f'{path}: unbekanntes Encoding (zu groß?)')
                            continue
                        b64 = cdata['content'].replace('\n', '')
                        ex  = http.get(f'{GITHUB_API}/repos/{repo}/contents/{path}',
                                       headers=hdrs, params={'ref': new_name}, timeout=10)
                        body: dict = {'message': f'cherry-pick {sha[:7]}: {path}',
                                      'content': b64, 'branch': new_name}
                        if ex.status_code == 200:
                            body['sha'] = ex.json()['sha']
                        put_r = http.put(f'{GITHUB_API}/repos/{repo}/contents/{path}',
                                         headers=hdrs, json=body, timeout=10)
                        _update_rate_limit(put_r.headers)
                        if put_r.status_code not in (200, 201):
                            errors.append(f'{path}: Schreiben fehlgeschlagen ({put_r.status_code})')
                except Exception as fe:
                    log.warning("Cherry-pick Datei-Fehler (%s %s): %s", repo, path, fe)
                    errors.append(f'{path}: Verarbeitung fehlgeschlagen')

        # 4. PR erstellen
        msg_list = []
        for sha in shas:
            cr  = http.get(f'{GITHUB_API}/repos/{repo}/commits/{sha}', headers=hdrs, timeout=10)
            msg = cr.json().get('commit', {}).get('message', sha[:7]).split('\n')[0] if cr.status_code == 200 else sha[:7]
            msg_list.append(f'- `{sha[:7]}` {msg}')
        n        = len(shas)
        pr_title = f'Cherry-pick: {n} commit{"s" if n != 1 else ""} → {target}'
        pr_body  = '🍒 Cherry-picked commits:\n\n' + '\n'.join(msg_list) + '\n\n*Created by GitPulse*'
        pr_r = http.post(f'{GITHUB_API}/repos/{repo}/pulls',
                         headers=hdrs,
                         json={'title': pr_title, 'head': new_name,
                               'base': target, 'body': pr_body},
                         timeout=15)
        _update_rate_limit(pr_r.headers)
        if pr_r.status_code == 201:
            pr = pr_r.json()
            log.info("Cherry-pick PR #%s erstellt (%s → %s)", pr['number'], new_name, target)
            return jsonify({'pr_url': pr['html_url'], 'pr_number': pr['number'],
                            'branch': new_name, 'errors': errors})
        return jsonify({'branch': new_name, 'errors': errors,
                        'error': f'PR nicht erstellt: {pr_r.json().get("message", pr_r.status_code)}'})
    except Exception:
        log.exception("Cherry-pick Fehler (%s)", repo)
        return jsonify({'error': 'Interner Fehler'}), 500


@app.route('/api/security/autofix', methods=['POST'])
def api_security_autofix():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    data         = request.get_json(silent=True) or {}
    repo         = data.get('repo', '').strip()
    alert_number = data.get('alert_number')
    token        = load_config().get('github_token', '').strip()
    if not all([token, repo, alert_number]):
        return jsonify({'error': 'Parameter fehlen'}), 400
    force = data.get('force', False)
    hdrs  = _gh_headers(token)
    try:
        # 0. Warnung wenn dev vor main liegt (Autofix könnte Datei mit alter Version überschreiben)
        gps = load_gitpulse_settings()
        if gps.get('autofix_branch_check', True) and not force:
            main_b = gps.get('main_branch', 'main') or 'main'
            dev_b  = gps.get('dev_branch',  'dev')  or 'dev'
            cmp = http.get(f'{GITHUB_API}/repos/{repo}/compare/{main_b}...{dev_b}', headers=hdrs, timeout=10)
            _update_rate_limit(cmp.headers)
            if cmp.status_code == 200:
                ahead_by = cmp.json().get('ahead_by', 0)
                if ahead_by > 0:
                    return jsonify({'error_code': 'branch_ahead', 'ahead_by': ahead_by}), 409

        # 1. Autofix-Generierung starten
        r = http.post(
            f'{GITHUB_API}/repos/{repo}/code-scanning/alerts/{alert_number}/autofix',
            headers=hdrs, timeout=30
        )
        _update_rate_limit(r.headers)
        if r.status_code == 403:
            return jsonify({'error': 'Zugriff verweigert — Token benötigt Schreibrechte auf "Code scanning alerts" und "Code quality". GitHub Copilot muss für das Repo aktiviert sein.'}), 403
        if r.status_code == 404:
            return jsonify({'error': f'Alert #{alert_number} nicht gefunden oder Code Scanning nicht aktiviert.'}), 404
        if r.status_code == 422:
            try:
                detail = r.json().get('message', r.text[:300])
            except Exception:
                detail = r.text[:300]
            return jsonify({'error_code': 'no_autofix', 'detail': detail}), 422
        if r.status_code not in (200, 202):
            try:
                detail = r.json().get('message', r.text[:200])
            except Exception:
                detail = r.text[:200]
            return jsonify({'error': f'Autofix konnte nicht gestartet werden (HTTP {r.status_code}): {detail}'}), 500

        # 2. Status aus POST-Response lesen (200 = bereits vorhanden, 202 = neu gestartet)
        try:
            status = r.json().get('status', 'pending')
        except Exception:
            status = 'pending'

        # Pollen bis "success" — überspringen wenn bereits fertig (max. 60 s)
        if status != 'success':
            for _ in range(20):
                time.sleep(3)
                poll = http.get(
                    f'{GITHUB_API}/repos/{repo}/code-scanning/alerts/{alert_number}/autofix',
                    headers=hdrs, timeout=10
                )
                _update_rate_limit(poll.headers)
                if poll.status_code != 200:
                    return jsonify({'error': f'Status-Abfrage fehlgeschlagen (HTTP {poll.status_code})'}), 500
                status = poll.json().get('status')
                log.info("Autofix Status %s #%s: %s", repo, alert_number, status)
                if status == 'success':
                    break
                if status == 'error':
                    return jsonify({'error_code': 'no_autofix', 'detail': 'generation failed'}), 400
            else:
                return jsonify({'error_code': 'timeout'}), 504

        # 3. Branch anlegen (commits-Endpoint setzt existierende Branch voraus)
        ts          = int(time.time()) % 100000
        short_name  = f'codeql/autofix-{alert_number}-{ts}'
        branch_ref  = f'refs/heads/{short_name}'

        # Basis-SHA des Default-Branch ermitteln
        repo_r = http.get(f'{GITHUB_API}/repos/{repo}', headers=hdrs, timeout=10)
        _update_rate_limit(repo_r.headers)
        default_branch = repo_r.json().get('default_branch', 'main') if repo_r.status_code == 200 else 'main'

        ref_r = http.get(f'{GITHUB_API}/repos/{repo}/git/ref/heads/{default_branch}', headers=hdrs, timeout=10)
        _update_rate_limit(ref_r.headers)
        if ref_r.status_code != 200:
            return jsonify({'error': f'Basis-Branch "{default_branch}" nicht gefunden'}), 500
        base_sha = ref_r.json()['object']['sha']

        create_r = http.post(
            f'{GITHUB_API}/repos/{repo}/git/refs',
            headers=hdrs,
            json={'ref': branch_ref, 'sha': base_sha},
            timeout=10
        )
        _update_rate_limit(create_r.headers)
        if create_r.status_code not in (200, 201):
            try:
                detail = create_r.json().get('message', create_r.text[:200])
            except Exception:
                detail = create_r.text[:200]
            return jsonify({'error': f'Branch konnte nicht angelegt werden: {detail}'}), 500

        # 4. Autofix in die neue Branch committen
        commit_r = http.post(
            f'{GITHUB_API}/repos/{repo}/code-scanning/alerts/{alert_number}/autofix/commits',
            headers=hdrs,
            json={'target_ref': branch_ref,
                  'message':    f'fix: CodeQL autofix for alert #{alert_number}'},
            timeout=15
        )
        _update_rate_limit(commit_r.headers)
        if commit_r.status_code == 201:
            result = commit_r.json()
            branch = result.get('target_ref', branch_ref).removeprefix('refs/heads/')
            log.info("CodeQL Autofix Branch erstellt: %s / %s", repo, branch)
            return jsonify({'ok': True, 'branch': branch, 'sha': result.get('sha', '')})
        try:
            detail = commit_r.json().get('message', commit_r.text[:300])
        except Exception:
            detail = commit_r.text[:300]
        log.error("Autofix Commit fehlgeschlagen (%s #%s): HTTP %s — %s", repo, alert_number, commit_r.status_code, detail)
        return jsonify({'error': f'Autofix-Commit fehlgeschlagen (HTTP {commit_r.status_code}): {detail}'}), 500
    except Exception:
        log.exception("Security-Autofix Fehler (%s #%s)", repo, alert_number)
        return jsonify({'error': 'Interner Fehler'}), 500


@app.route('/api/branch', methods=['DELETE'])
def api_delete_branch():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    data   = request.get_json(silent=True) or {}
    repo   = data.get('repo', '').strip()
    branch = data.get('branch', '').strip()
    token  = load_config().get('github_token', '').strip()
    if not all([token, repo, branch]):
        return jsonify({'error': 'Parameter fehlen'}), 400
    if branch.lower() in ('main', 'master', 'dev', 'develop'):
        return jsonify({'error': f'Branch "{branch}" ist geschützt'}), 403
    hdrs = _gh_headers(token)
    try:
        r = http.delete(f'{GITHUB_API}/repos/{repo}/git/refs/heads/{branch}',
                        headers=hdrs, timeout=10)
        _update_rate_limit(r.headers)
        if r.status_code == 204:
            log.info("Branch gelöscht: %s/%s", repo, branch)
            return jsonify({'ok': True})
        if r.status_code in (404, 422):
            return jsonify({'error': 'Branch nicht gefunden'}), 404
        return jsonify({'error': f'GitHub Fehler {r.status_code}'}), 500
    except Exception:
        log.exception("Branch-Delete Fehler (%s %s)", repo, branch)
        return jsonify({'error': 'Interner Fehler'}), 500


@app.route('/api/gitpulse-settings', methods=['GET'])
def api_gp_settings_get():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    return jsonify(load_gitpulse_settings())


@app.route('/api/gitpulse-settings', methods=['POST'])
def api_gp_settings_post():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    data = request.get_json(silent=True) or {}
    s = load_gitpulse_settings()
    if 'main_branch' in data:
        s['main_branch'] = str(data['main_branch']).strip() or 'main'
    if 'dev_branch' in data:
        s['dev_branch'] = str(data['dev_branch']).strip() or 'dev'
    if 'autofix_branch_check' in data:
        s['autofix_branch_check'] = bool(data['autofix_branch_check'])
    save_gitpulse_settings(s)
    return jsonify({'ok': True})


_branch_sync_cache: dict = {}   # {cache_key: (timestamp, result)}

@app.route('/api/stat/branch-sync')
def api_stat_branch_sync():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    cfg   = load_config()
    token = cfg.get('github_token', '').strip()
    if not token:
        return jsonify({'configured': False})
    gps      = load_gitpulse_settings()
    main_b   = gps.get('main_branch', 'main') or 'main'
    dev_b    = gps.get('dev_branch',  'dev')  or 'dev'

    user_repos  = load_user_repos()
    repos_raw   = (user_repos or {}).get('my_repos', cfg.get('my_repos', []))
    my_repos    = [r.strip() for r in repos_raw if r.strip()]
    if not my_repos:
        return jsonify({'configured': False})

    cache_key = f"{main_b}:{dev_b}:{','.join(sorted(my_repos))}"
    now       = time.time()
    if cache_key in _branch_sync_cache:
        ts, result = _branch_sync_cache[cache_key]
        if now - ts < 60:
            return jsonify(result)

    hdrs = _gh_headers(token)
    def _compare(repo):
        try:
            r = http.get(f'{GITHUB_API}/repos/{repo}/compare/{main_b}...{dev_b}',
                         headers=hdrs, timeout=10)
            _update_rate_limit(r.headers)
            if r.status_code != 200:
                return None
            d = r.json()
            return {'repo': repo, 'ahead_by': d.get('ahead_by', 0), 'behind_by': d.get('behind_by', 0)}
        except Exception:
            pass
        return None

    with ThreadPoolExecutor(max_workers=6) as ex:
        results = [r for r in ex.map(_compare, my_repos) if r]

    out = {'configured': True, 'main': main_b, 'dev': dev_b, 'repos': results}
    _branch_sync_cache[cache_key] = (now, out)
    return jsonify(out)


@app.route('/api/comments')
def api_comments():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    repo   = request.args.get('repo', '').strip()
    number = request.args.get('number', '').strip()
    is_pr  = request.args.get('type', '').strip().lower() == 'pr'
    if not repo or '/' not in repo or not number or not number.isdigit():
        return jsonify({'error': 'invalid params'}), 400
    token = load_config().get('github_token', '').strip()
    if not token:
        return jsonify({'error': 'no token'}), 400

    try:
        merged = _fetch_comments_merged(repo, number, is_pr, token)
        if merged is None:
            return jsonify({'error': 'HTTP error'}), 502
        shown_list = merged[-_COMMENT_SHOW_MAX:]

        # Panel geöffnet = gelesen. Bei PRs zählt die Übersicht zusätzlich die
        # Review-Kommentare mit, deshalb schickt das Frontend den angezeigten
        # Stand als "shown" mit — sonst bliebe die Ungelesen-Markierung hängen.
        try:
            _shown = int(request.args.get('shown', '0'))
        except ValueError:
            _shown = 0
        _mark_comments_read(repo, int(number), max(len(merged), _shown))
        return jsonify({'total': len(merged), 'comments': shown_list})
    except Exception:
        log.exception("Comments-Abfrage Fehler")
        return jsonify({'error': 'internal error'}), 500


@app.route('/api/workflow/dispatch', methods=['POST'])
def api_workflow_dispatch():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    body = request.get_json(silent=True) or {}
    repo        = body.get('repo', '').strip()
    workflow_id = body.get('workflow_id')
    ref         = body.get('ref', 'main').strip() or 'main'
    if not repo or not workflow_id:
        return jsonify({'error': 'repo und workflow_id erforderlich'}), 400
    token = load_config().get('github_token', '').strip()
    if not token:
        return jsonify({'error': 'Kein Token konfiguriert'}), 400
    try:
        r = http.post(
            f'{GITHUB_API}/repos/{repo}/actions/workflows/{workflow_id}/dispatches',
            headers=_gh_headers(token),
            json={'ref': ref},
            timeout=15,
        )
        if r.status_code == 204:
            log.info("Workflow %s in %s auf Branch '%s' gestartet", workflow_id, repo, ref)
            return jsonify({'status': 'dispatched'})
        try:
            msg = r.json().get('message', f'HTTP {r.status_code}')
        except Exception:
            msg = f'HTTP {r.status_code}'
        log.warning("Workflow-Dispatch fehlgeschlagen: %s", msg)
        return jsonify({'error': msg}), r.status_code
    except Exception:
        log.exception("Workflow-Dispatch Fehler")
        return jsonify({'error': 'internal error'}), 500


@app.route('/api/ci/jobs')
def api_ci_jobs():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    repo   = request.args.get('repo', '').strip()
    run_id = request.args.get('run_id', '')
    if not repo or not run_id:
        return jsonify({'error': 'repo und run_id erforderlich'}), 400
    token = load_config().get('github_token', '').strip()
    if not token:
        return jsonify({'error': 'Kein Token konfiguriert'}), 400
    data = _gh_get(f'/repos/{repo}/actions/runs/{run_id}/jobs', token) or {}
    jobs = []
    for job in (data.get('jobs') or []):
        jobs.append({
            'id':         job['id'],
            'name':       job['name'],
            'status':     job['status'],
            'conclusion': job.get('conclusion'),
            'started':    job.get('started_at'),
            'completed':  job.get('completed_at'),
            'steps': [
                {
                    'name':       s['name'],
                    'status':     s['status'],
                    'conclusion': s.get('conclusion'),
                    'number':     s['number'],
                    'started':    s.get('started_at'),
                    'completed':  s.get('completed_at'),
                } for s in (job.get('steps') or [])
            ],
        })
    return jsonify(jobs)


_TG_NOTIF_KEYS = (
    'startup', 'new_pr', 'pr_closed', 'new_issue',
    'workflow_started', 'workflow_completed',
    'releases', 'repo_stats', 'star_fork', 'security', 'my_activity',
    'new_comment', 'review_request', 'digest',
)


@app.route('/api/config/repos', methods=['GET'])
def api_config_repos_get():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    cfg        = load_config()
    user_repos = load_user_repos()
    tg_notif      = (user_repos or {}).get('tg_notifications', {})
    em_notif      = (user_repos or {}).get('email_notifications', {})
    tg_configured = bool(cfg.get('telegram_bot_token', '').strip() and cfg.get('telegram_chat_id', '').strip())
    em_configured = bool(cfg.get('smtp_host', '').strip() and cfg.get('smtp_to', '').strip())
    if user_repos is not None:
        return jsonify({
            'source':              'user',
            'my_repos':            user_repos.get('my_repos', []),
            'watch_repos':         user_repos.get('watch_repos', []),
            'tg_notifications':    tg_notif,
            'tg_configured':       tg_configured,
            'email_notifications': em_notif,
            'email_configured':    em_configured,
        })
    return jsonify({
        'source':              'options',
        'my_repos':            [r for r in cfg.get('my_repos', [])    if r.strip()],
        'watch_repos':         [r for r in cfg.get('watch_repos', []) if r.strip()],
        'tg_notifications':    tg_notif,
        'tg_configured':       tg_configured,
        'email_notifications': em_notif,
        'email_configured':    em_configured,
    })


@app.route('/api/config/repos', methods=['POST'])
def api_config_repos_save():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    body        = request.get_json(silent=True) or {}
    my_repos    = [r.strip() for r in body.get('my_repos', [])    if r.strip()]
    watch_repos = [r.strip() for r in body.get('watch_repos', []) if r.strip()]
    tg_raw      = body.get('tg_notifications') or {}
    em_raw      = body.get('email_notifications') or {}
    tg_notif    = {k: bool(tg_raw.get(k, True)) for k in _TG_NOTIF_KEYS}
    em_notif    = {k: bool(em_raw.get(k, True)) for k in _TG_NOTIF_KEYS}
    existing    = load_user_repos() or {}
    existing.update({'my_repos': my_repos, 'watch_repos': watch_repos,
                     'tg_notifications': tg_notif, 'email_notifications': em_notif})
    save_user_repos(existing)
    _etag_cache.clear()  # frischer Poll für neue Repos
    log.info("Repo-Config gespeichert: %d eigene, %d Watch-Repos", len(my_repos), len(watch_repos))
    return jsonify({'status': 'saved', 'my_repos': my_repos, 'watch_repos': watch_repos})


@app.route('/api/test-email', methods=['POST'])
def api_test_email():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    cfg = load_config()
    if not cfg.get('smtp_host', '').strip() or not cfg.get('smtp_to', '').strip():
        return jsonify({'error': 'SMTP nicht konfiguriert (smtp_host / smtp_to fehlen)'}), 400
    try:
        _send_email(cfg, 'GitPulse Test-E-Mail',
                    _email_html('GitPulse Test-E-Mail',
                                ['Dies ist eine Test-Nachricht von GitPulse.',
                                 'E-Mail-Benachrichtigungen sind korrekt konfiguriert. ✅']))
        return jsonify({'status': 'ok'})
    except Exception:
        log.exception("Test-E-Mail Fehler")
        return jsonify({'error': 'internal error'}), 500


@app.route('/api/issue/close', methods=['POST'])
def api_issue_close():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    body     = request.get_json(silent=True) or {}
    repo     = body.get('repo', '').strip()
    issue_nr = body.get('number')
    if not repo or not issue_nr:
        return jsonify({'error': 'repo und number erforderlich'}), 400
    token = load_config().get('github_token', '').strip()
    if not token:
        return jsonify({'error': 'Kein Token konfiguriert'}), 400
    try:
        r = http.patch(
            f'{GITHUB_API}/repos/{repo}/issues/{issue_nr}',
            headers=_gh_headers(token),
            json={'state': 'closed'},
            timeout=15,
        )
        _update_rate_limit(r.headers)
        if r.status_code == 200:
            log.info("Issue #%s in %s geschlossen", issue_nr, repo)
            return jsonify({'status': 'closed'})
        msg = r.json().get('message', f'HTTP {r.status_code}')
        log.warning("Issue-Close fehlgeschlagen: %s", msg)
        return jsonify({'error': msg}), r.status_code
    except Exception:
        log.exception("Issue-Close Fehler")
        return jsonify({'error': 'internal error'}), 500


@app.route('/api/issue/reopen', methods=['POST'])
def api_issue_reopen():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    body     = request.get_json(silent=True) or {}
    repo     = body.get('repo', '').strip()
    issue_nr = body.get('number')
    if not repo or not issue_nr:
        return jsonify({'error': 'repo und number erforderlich'}), 400
    token = load_config().get('github_token', '').strip()
    if not token:
        return jsonify({'error': 'Kein Token konfiguriert'}), 400
    try:
        r = http.patch(
            f'{GITHUB_API}/repos/{repo}/issues/{issue_nr}',
            headers=_gh_headers(token),
            json={'state': 'open'},
            timeout=15,
        )
        _update_rate_limit(r.headers)
        if r.status_code == 200:
            log.info("Issue #%s in %s wieder geöffnet", issue_nr, repo)
            return jsonify({'status': 'open'})
        msg = r.json().get('message', f'HTTP {r.status_code}')
        log.warning("Issue-Reopen fehlgeschlagen: %s", msg)
        return jsonify({'error': msg}), r.status_code
    except Exception:
        log.exception("Issue-Reopen Fehler")
        return jsonify({'error': 'internal error'}), 500


@app.route('/api/issue/comment', methods=['POST'])
def api_issue_comment():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    body     = request.get_json(silent=True) or {}
    repo     = body.get('repo', '').strip()
    issue_nr = body.get('number')
    comment  = body.get('body', '').strip()
    if not repo or not issue_nr or not comment:
        return jsonify({'error': 'repo, number und body erforderlich'}), 400
    token = load_config().get('github_token', '').strip()
    if not token:
        return jsonify({'error': 'Kein Token konfiguriert'}), 400
    try:
        r = http.post(
            f'{GITHUB_API}/repos/{repo}/issues/{issue_nr}/comments',
            headers=_gh_headers(token),
            json={'body': comment},
            timeout=15,
        )
        _update_rate_limit(r.headers)
        if r.status_code == 201:
            log.info("Kommentar zu Issue #%s in %s hinzugefügt", issue_nr, repo)
            return jsonify({'status': 'commented'})
        msg = r.json().get('message', f'HTTP {r.status_code}')
        log.warning("Issue-Comment fehlgeschlagen: %s", msg)
        return jsonify({'error': msg}), r.status_code
    except Exception:
        log.exception("Issue-Comment Fehler")
        return jsonify({'error': 'internal error'}), 500


@app.route('/api/workflow/cancel', methods=['POST'])
def api_workflow_cancel():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    body   = request.get_json(silent=True) or {}
    repo   = body.get('repo', '').strip()
    run_id = body.get('run_id')
    if not repo or not run_id:
        return jsonify({'error': 'repo und run_id erforderlich'}), 400
    token = load_config().get('github_token', '').strip()
    if not token:
        return jsonify({'error': 'Kein Token konfiguriert'}), 400
    try:
        r = http.post(
            f'{GITHUB_API}/repos/{repo}/actions/runs/{run_id}/cancel',
            headers=_gh_headers(token),
            json={},
            timeout=15,
        )
        if r.status_code == 202:
            log.info("Workflow-Run %s in %s abgebrochen", run_id, repo)
            return jsonify({'status': 'cancelled'})
        try:
            msg = r.json().get('message', f'HTTP {r.status_code}')
        except Exception:
            msg = f'HTTP {r.status_code}'
        log.warning("Workflow-Cancel fehlgeschlagen: %s", msg)
        return jsonify({'error': msg}), r.status_code
    except Exception:
        log.exception("Workflow-Cancel Fehler")
        return jsonify({'error': 'internal error'}), 500


@app.route('/api/workflow/rerun', methods=['POST'])
def api_workflow_rerun():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    body   = request.get_json(silent=True) or {}
    repo   = body.get('repo', '').strip()
    run_id = body.get('run_id')
    if not repo or not run_id:
        return jsonify({'error': 'repo und run_id erforderlich'}), 400
    token = load_config().get('github_token', '').strip()
    if not token:
        return jsonify({'error': 'Kein Token konfiguriert'}), 400
    try:
        r = http.post(
            f'{GITHUB_API}/repos/{repo}/actions/runs/{run_id}/rerun',
            headers=_gh_headers(token),
            json={},
            timeout=15,
        )
        if r.status_code == 201:
            log.info("Workflow-Run %s in %s neu gestartet", run_id, repo)
            return jsonify({'status': 'rerun'})
        try:
            msg = r.json().get('message', f'HTTP {r.status_code}')
        except Exception:
            msg = f'HTTP {r.status_code}'
        log.warning("Workflow-Rerun fehlgeschlagen: %s", msg)
        return jsonify({'error': msg}), r.status_code
    except Exception:
        log.exception("Workflow-Rerun Fehler")
        return jsonify({'error': 'internal error'}), 500


@app.route('/api/workflow/delete', methods=['POST'])
def api_workflow_delete():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    body   = request.get_json(silent=True) or {}
    repo   = body.get('repo', '').strip()
    run_id = body.get('run_id')
    if not repo or not run_id:
        return jsonify({'error': 'repo und run_id erforderlich'}), 400
    token = load_config().get('github_token', '').strip()
    if not token:
        return jsonify({'error': 'Kein Token konfiguriert'}), 400
    try:
        r = http.delete(
            f'{GITHUB_API}/repos/{repo}/actions/runs/{run_id}',
            headers=_gh_headers(token),
            timeout=15,
        )
        if r.status_code == 204:
            log.info("Workflow-Run %s in %s gelöscht", run_id, repo)
            # Aus lokalem Cache entfernen
            with _gh_lock:
                for rd in _gh_cache.get('my_repos', []):
                    if rd['repo'] == repo:
                        rd['runs'] = [run for run in rd.get('runs', []) if run['id'] != run_id]
            # _known_run_conclusions bewusst NICHT löschen: würde den Run beim nächsten
            # Poll als "neu" erscheinen lassen und Telegram fälschlicherweise auslösen
            return jsonify({'status': 'deleted'})
        try:
            msg = r.json().get('message', f'HTTP {r.status_code}')
        except Exception:
            msg = f'HTTP {r.status_code}'
        log.warning("Workflow-Delete fehlgeschlagen: %s", msg)
        return jsonify({'error': msg}), r.status_code
    except Exception as e:
        log.error("Workflow-Delete Fehler: %s", e)
        return jsonify({'error': 'internal_error'}), 500


@app.route('/api/workflow/toggle', methods=['POST'])
def api_workflow_toggle():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    body        = request.get_json(silent=True) or {}
    repo        = body.get('repo', '').strip()
    workflow_id = body.get('workflow_id')
    enable      = bool(body.get('enable', True))
    if not repo or not workflow_id:
        return jsonify({'error': 'missing_fields'}), 400
    token = load_config().get('github_token', '').strip()
    if not token:
        return jsonify({'error': 'no_token'}), 400
    action = 'enable' if enable else 'disable'
    try:
        r = http.put(
            f'{GITHUB_API}/repos/{repo}/actions/workflows/{workflow_id}/{action}',
            headers=_gh_headers(token), timeout=15,
        )
        if r.status_code == 204:
            new_state = 'active' if enable else 'disabled_manually'
            log.info("Workflow %s in %s: %s", workflow_id, repo, action)
            with _gh_lock:
                for rd in _gh_cache.get('my_repos', []):
                    if rd['repo'] == repo:
                        for wf in rd.get('workflows', []):
                            if wf['id'] == workflow_id:
                                wf['state'] = new_state
                                wf['dispatchable'] = enable
            return jsonify({'status': action + 'd', 'new_state': new_state})
        try:
            msg = r.json().get('message', f'HTTP {r.status_code}')
        except Exception:
            msg = f'HTTP {r.status_code}'
        return jsonify({'error': msg}), r.status_code
    except Exception:
        log.exception("Workflow-Toggle Fehler")
        return jsonify({'error': 'internal error'}), 500


@app.route('/webhook', methods=['POST'])
def github_webhook():
    """GitHub Webhook-Endpunkt — kein Session-Check, Authentifizierung via HMAC-Signatur."""
    cfg    = load_config()
    secret = cfg.get('webhook_secret', '').strip()

    # Kein Secret konfiguriert → Webhooks deaktiviert, Polling läuft weiter
    if not secret:
        return jsonify({'status': 'disabled'}), 200

    # Signatur prüfen
    sig      = request.headers.get('X-Hub-Signature-256', '')
    expected = 'sha256=' + hmac.new(secret.encode(), request.data, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        log.warning("Webhook: ungültige Signatur — abgelehnt")
        return 'Forbidden', 403

    event   = request.headers.get('X-GitHub-Event', '')
    payload = request.get_json(silent=True) or {}
    repo_full = (payload.get('repository') or {}).get('full_name', '')
    action    = payload.get('action', '')

    log.info("Webhook empfangen: %s [%s] für %s", event, action, repo_full)

    # Nur konfigurierte eigene Repos verarbeiten
    user_repos_data = load_user_repos()
    if user_repos_data is not None:
        my_repos = user_repos_data.get('my_repos', [])
    else:
        my_repos = cfg.get('my_repos', [])
    if repo_full not in my_repos:
        return jsonify({'status': 'ignored'}), 200

    tg_token  = cfg.get('telegram_bot_token', '').strip()
    tg_chat   = cfg.get('telegram_chat_id', '').strip()
    _wh_urepos = load_user_repos() or {}
    tg_notif  = _wh_urepos.get('tg_notifications', {})
    em_notif  = _wh_urepos.get('email_notifications', {})

    if event == 'pull_request':
        pr     = payload.get('pull_request', {})
        pr_num = pr.get('number')
        if action == 'opened':
            if pr_num:
                _seen_prs[repo_full].add(pr_num)  # Duplikat-Schutz für nächsten Poll
            if _first_poll_done:
                user_login = (pr.get('user') or {}).get('login','?')
                _tg_em(cfg, tg_token, tg_chat, tg_notif, em_notif, 'new_pr',
                    f"🔀 Neuer PR: <b>{repo_full}</b>\n#{pr_num} {pr.get('title','')}\nvon @{user_login}\n<a href=\"{pr.get('html_url','')}\">PR öffnen</a>",
                    f"Neuer PR: {repo_full}",
                    [f"#{pr_num} {pr.get('title','')}", f"von @{user_login}", f"<a href=\"{pr.get('html_url','')}\">PR öffnen</a>"])
        elif action == 'closed':
            merged = pr.get('merged', False)
            if _first_poll_done:
                icon = '⎇' if merged else '✕'
                verb = 'gemerged' if merged else 'geschlossen'
                user_login = (pr.get('user') or {}).get('login','?')
                _tg_em(cfg, tg_token, tg_chat, tg_notif, em_notif, 'pr_closed',
                    f"{icon} PR {verb}: <b>{repo_full}</b>\n#{pr_num} {pr.get('title','')}\nvon @{user_login}\n<a href=\"{pr.get('html_url','')}\">PR öffnen</a>",
                    f"PR {verb}: {repo_full}",
                    [f"#{pr_num} {pr.get('title','')}", f"von @{user_login}", f"<a href=\"{pr.get('html_url','')}\">PR öffnen</a>"])
            with _gh_lock:
                for rd in _gh_cache.get('my_repos', []):
                    if rd['repo'] == repo_full:
                        rd['pulls'] = [p for p in rd.get('pulls', []) if p.get('number') != pr_num]
                        rd['open_prs'] = len(rd['pulls'])
                        existing_closed = {p.get('number') for p in rd.get('closed_pulls', [])}
                        if pr_num and pr_num not in existing_closed:
                            rd.setdefault('closed_pulls', []).insert(0, {
                                'number':     pr_num,
                                'title':      pr.get('title', ''),
                                'state':      'closed',
                                'draft':      pr.get('draft', False),
                                'url':        pr.get('html_url', ''),
                                'user':       (pr.get('user') or {}).get('login', ''),
                                'avatar':     (pr.get('user') or {}).get('avatar_url', ''),
                                'labels':     [l['name'] for l in pr.get('labels', [])],
                                'created':    pr.get('created_at', ''),
                                'updated':    pr.get('updated_at', ''),
                                'merged_at':  pr.get('merged_at'),
                                'comments':   (pr.get('comments') or 0) + (pr.get('review_comments') or 0),
                                'review_state': 'none',
                            })
                            rd['closed_pulls'] = rd['closed_pulls'][:50]
                        break
            _notify_sse()
        threading.Thread(target=_trigger_repo_poll, args=(repo_full,), daemon=True).start()

    elif event == 'issues':
        issue   = payload.get('issue', {})
        iss_num = issue.get('number')
        if action == 'opened':
            if iss_num:
                _seen_issues[repo_full].add(iss_num)  # Duplikat-Schutz
            if _first_poll_done:
                user_login = (issue.get('user') or {}).get('login','?')
                _tg_em(cfg, tg_token, tg_chat, tg_notif, em_notif, 'new_issue',
                    f"🐛 Neues Issue: <b>{repo_full}</b>\n#{iss_num} {issue.get('title','')}\nvon @{user_login}\n<a href=\"{issue.get('html_url','')}\">Issue öffnen</a>",
                    f"Neues Issue: {repo_full}",
                    [f"#{iss_num} {issue.get('title','')}", f"von @{user_login}", f"<a href=\"{issue.get('html_url','')}\">Issue öffnen</a>"])
        threading.Thread(target=_trigger_repo_poll, args=(repo_full,), daemon=True).start()

    elif event in ('issue_comment', 'pull_request_review_comment'):
        # Sofort-Meldung für neue Kommentare. Eigene bleiben stumm; der Poll
        # meldet sie nicht nach, weil hier der Zeitstempel mitgezogen wird.
        if action == 'created':
            cmt   = payload.get('comment', {})
            item  = payload.get('issue') or payload.get('pull_request') or {}
            num   = item.get('number')
            author = (cmt.get('user') or {}).get('login', '?')
            is_pr  = event == 'pull_request_review_comment' or 'pull_request' in item
            created = cmt.get('created_at') or _now_iso()
            if num is not None:
                ckey = f'{repo_full}#{num}'
                with _comment_state_lock:
                    st = _comment_state.get(ckey)
                    if st is not None and created > str(st.get('ts') or ''):
                        st['ts'] = created
                        st['total'] = int(st.get('total', 0)) + 1
                if _gh_login and author == _gh_login:
                    if st is not None:
                        _skip_own_comments(repo_full, num, 1, int(st.get('total', 0)))
                        save_seen_comments()
                        save_comment_state()
                elif _first_poll_done:
                    label = 'PR' if is_pr else 'Issue'
                    ref   = f"#PR{num}" if is_pr else f"#I{num}"
                    title = item.get('title', '')
                    url   = cmt.get('html_url') or item.get('html_url', '')
                    snippet = _strip_html(cmt.get('body') or '')[:200]
                    _tg_em(cfg, tg_token, tg_chat, tg_notif, em_notif, 'new_comment',
                        f"💬 Neuer Kommentar an {label}: <b>{repo_full}</b>\n"
                        f"<a href=\"{url}\">{ref} {title}</a>\nvon @{author}\n{snippet}",
                        f"Neuer Kommentar an {label} {repo_full} #{num}",
                        [f"Repo: <b>{repo_full}</b>",
                         f"{label}: <a href=\"{url}\">{ref} {title}</a>",
                         f"von <b>@{author}</b>", snippet])
                    save_comment_state()
        threading.Thread(target=_trigger_repo_poll, args=(repo_full,), daemon=True).start()

    elif event == 'workflow_run':
        run    = payload.get('workflow_run', {})
        run_id = run.get('id')
        curr_con = run.get('conclusion')
        _con_icons  = {'success':'✅','failure':'❌','cancelled':'⏹','skipped':'⏭','timed_out':'⏱'}
        _con_labels = {'success':'Erfolgreich','failure':'Fehlgeschlagen','cancelled':'Abgebrochen',
                       'skipped':'Übersprungen','timed_out':'Timeout'}
        run_actor   = (run.get('triggering_actor') or run.get('actor') or {}).get('login','?')
        run_info_tg = (f"<b>{run.get('name','')}</b> #{run.get('run_number','')}\n"
                       f"Branch: {run.get('head_branch','?')} · von @{run_actor}\n")
        run_info_em = [f"<b>{run.get('name','')}</b> #{run.get('run_number','')}",
                       f"Branch: {run.get('head_branch','?')} · von @{run_actor}"]
        if action == 'requested':
            if run_id:
                _known_run_conclusions[run_id] = None  # Duplikat-Schutz
            if _first_poll_done:
                _tg_em(cfg, tg_token, tg_chat, tg_notif, em_notif, 'workflow_started',
                    f"▶️ <b>Workflow gestartet:</b> {repo_full}\n" + run_info_tg + f"<a href=\"{run.get('html_url','')}\">Details</a>",
                    f"Workflow gestartet: {repo_full}",
                    run_info_em + [f"<a href=\"{run.get('html_url','')}\">Details</a>"])
            # Neuen Run sofort in den Cache einfügen damit die UI ihn sofort sieht
            head_msg = (run.get('head_commit') or {}).get('message', '')
            new_entry = {
                'id':           run_id,
                'run_number':   run.get('run_number'),
                'workflow_id':  run.get('workflow_id'),
                'name':         run.get('name', ''),
                'status':       run.get('status', 'queued'),
                'conclusion':   run.get('conclusion'),
                'url':          run.get('html_url', ''),
                'branch':       run.get('head_branch', ''),
                'created':      run.get('created_at', ''),
                'updated':      run.get('updated_at', ''),
                'event':        run.get('event', ''),
                'actor':        (run.get('actor') or {}).get('login', ''),
                'actor_avatar': (run.get('actor') or {}).get('avatar_url', ''),
                'head_sha':     run.get('head_sha', '')[:7],
                'head_message': head_msg.split('\n')[0][:80] if head_msg else '',
            }
            with _gh_lock:
                for rd in _gh_cache.get('my_repos', []):
                    if rd['repo'] == repo_full:
                        existing = {r.get('id') for r in rd.get('runs', [])}
                        if run_id and run_id not in existing:
                            rd.setdefault('runs', []).insert(0, new_entry)
                        break
            _notify_sse()
        elif action == 'completed':
            if run_id:
                _known_run_conclusions[run_id] = curr_con  # Duplikat-Schutz
            if _first_poll_done:
                icon  = _con_icons.get(curr_con, '⚠️')
                label = _con_labels.get(curr_con, curr_con)
                _tg_em(cfg, tg_token, tg_chat, tg_notif, em_notif, 'workflow_completed',
                    f"{icon} <b>Workflow beendet:</b> {repo_full}\n" + run_info_tg + f"Status: {label}\n<a href=\"{run.get('html_url','')}\">Details</a>",
                    f"Workflow beendet: {repo_full} — {label}",
                    run_info_em + [f"Status: {label}", f"<a href=\"{run.get('html_url','')}\">Details</a>"])
            # Run-Status sofort im Cache patchen — kein Warten auf den vollen Poll
            with _gh_lock:
                for rd in _gh_cache.get('my_repos', []):
                    if rd['repo'] == repo_full:
                        for cr in rd.get('runs', []):
                            if cr.get('id') == run_id:
                                cr['status']     = run.get('status', cr['status'])
                                cr['conclusion'] = run.get('conclusion', cr.get('conclusion'))
                                cr['updated']    = run.get('updated_at', cr.get('updated', ''))
                                break
                        break
            _notify_sse()
        threading.Thread(target=_trigger_repo_poll, args=(repo_full,), daemon=True).start()

    elif event in ('push', 'create', 'delete'):
        threading.Thread(target=_trigger_repo_poll, args=(repo_full,), daemon=True).start()

    elif event == 'star':
        count = (payload.get('repository') or {}).get('stargazers_count', 0)
        if _first_poll_done:
            user = (payload.get('sender') or {}).get('login', '?')
            icon = '⭐' if action == 'created' else '💔'
            verb = 'erhalten' if action == 'created' else 'verloren'
            _tg_em(cfg, tg_token, tg_chat, tg_notif, em_notif, 'star_fork',
                f"{icon} <b>Star {verb}:</b> {repo_full}\nvon @{user} · jetzt {count} Stars",
                f"Star {verb}: {repo_full}",
                [f"von @{user}", f"jetzt {count} Stars"])
        with _gh_lock:
            for rd in _gh_cache.get('my_repos', []):
                if rd['repo'] == repo_full:
                    rd['stars'] = count
        _notify_sse()

    elif event == 'fork':
        forks  = (payload.get('repository') or {}).get('forks_count', 0)
        forkee = (payload.get('forkee') or {}).get('full_name', '?')
        if _first_poll_done:
            _tg_em(cfg, tg_token, tg_chat, tg_notif, em_notif, 'star_fork',
                f"🍴 <b>Neuer Fork:</b> {repo_full}\n→ {forkee} · jetzt {forks} Forks",
                f"Neuer Fork: {repo_full}",
                [f"→ {forkee}", f"jetzt {forks} Forks"])
        with _gh_lock:
            for rd in _gh_cache.get('my_repos', []):
                if rd['repo'] == repo_full:
                    rd['forks'] = forks
        _notify_sse()

    elif event == 'secret_scanning_alert':
        alert       = payload.get('alert', {})
        secret_type = alert.get('secret_type_display_name') or alert.get('secret_type', '?')
        alert_num   = alert.get('number', '?')
        alert_url   = alert.get('html_url', '')
        _action_map = {
            'created':         ('🚨', 'Neues Secret gefunden'),
            'publicly_leaked': ('🔓', 'Öffentlich geleakt!'),
            'validated':       ('⚠️', 'Als gültig bestätigt'),
            'reopened':        ('🔁', 'Erneut geöffnet'),
            'revoked':         ('✅', 'Token widerrufen'),
            'resolved':        ('✅', 'Behoben'),
        }
        icon, label = _action_map.get(action, ('⚠️', action))
        log.warning("Secret Scanning Alert [%s] in %s (#%s)", action, repo_full, alert_num)
        _tg_em(cfg, tg_token, tg_chat, tg_notif, em_notif, 'security',
            f"{icon} <b>Secret Scanning Alert:</b> {repo_full}\n#{alert_num} · {label}\nTyp: {secret_type}\n" + (f"<a href=\"{alert_url}\">Alert anzeigen</a>" if alert_url else ''),
            f"Secret Scanning Alert: {repo_full}",
            [f"#{alert_num} · {label}", f"Typ: {secret_type}"] + ([f"<a href=\"{alert_url}\">Alert anzeigen</a>"] if alert_url else []))
        threading.Thread(target=_trigger_repo_poll, args=(repo_full,), daemon=True).start()

    elif event == 'code_scanning_alert':
        alert     = payload.get('alert', {})
        alert_num = alert.get('number', '?')
        alert_url = alert.get('html_url', '')
        rule      = alert.get('rule', {})
        tool_name = (alert.get('tool') or {}).get('name', 'CodeQL')
        severity  = rule.get('security_severity_level') or rule.get('severity', '?')
        desc      = rule.get('description', '')
        instance  = (alert.get('most_recent_instance') or {})
        location  = (instance.get('location') or {})
        loc_str   = f"{location.get('path', '')}:{location.get('start_line', '')}" if location.get('path') else ''
        _sev_icons = {'critical': '🔴', 'high': '🟠', 'medium': '🟡', 'low': '🟢', 'note': 'ℹ️', 'warning': '⚠️'}
        _action_map = {
            'created':          ('gefunden'),
            'appeared_in_branch': ('in Branch gefunden'),
            'fixed':            ('behoben ✅'),
            'closed_by_user':   ('manuell geschlossen'),
            'dismissed':        ('ignoriert'),
            'reopened':         ('erneut geöffnet'),
            'reopened_by_user': ('manuell geöffnet'),
        }
        sev_icon = _sev_icons.get(severity, '⚠️')
        act_label = _action_map.get(action, action)
        log.warning("Code Scanning Alert [%s/%s] in %s: %s (#%s)", severity, action, repo_full, desc, alert_num)
        # "created" und "appeared_in_branch" beschreiben denselben neuen Alert und kommen
        # als zwei Webhooks — gemeinsamer Schlüssel, damit nur eine Nachricht rausgeht.
        _grp = 'open' if action in ('created', 'appeared_in_branch') else 'reopen'
        if action in ('created', 'appeared_in_branch', 'reopened', 'reopened_by_user') \
                and _alert_notify_once(f"cs:{repo_full}#{alert_num}:{_grp}"):
            em_lines = [f"#{alert_num} · {severity.upper()} · {act_label}", f"Tool: {tool_name}", desc]
            if loc_str: em_lines.append(f"📄 {loc_str}")
            if alert_url: em_lines.append(f"<a href=\"{alert_url}\">Alert anzeigen</a>")
            tg_msg = (f"{sev_icon} <b>Code Scanning Alert:</b> {repo_full}\n#{alert_num} · {severity.upper()} · {act_label}\nTool: {tool_name}\n{desc}\n"
                      + (f"📄 {loc_str}\n" if loc_str else '') + (f"<a href=\"{alert_url}\">Alert anzeigen</a>" if alert_url else ''))
            _tg_em(cfg, tg_token, tg_chat, tg_notif, em_notif, 'security',
                tg_msg, f"Code Scanning Alert: {repo_full} [{severity.upper()}]", em_lines)
        threading.Thread(target=_trigger_repo_poll, args=(repo_full,), daemon=True).start()

    elif event == 'dependabot_alert':
        alert    = payload.get('alert', {})
        alert_num = alert.get('number', '?')
        alert_url = alert.get('html_url', '')
        vuln     = alert.get('security_vulnerability', {})
        advisory = alert.get('security_advisory', {})
        pkg      = (vuln.get('package') or {})
        pkg_name = pkg.get('name', '?')
        ecosystem = pkg.get('ecosystem', '')
        severity  = advisory.get('severity') or alert.get('severity', '?')
        summary   = advisory.get('summary', '')
        fixed_in  = (vuln.get('first_patched_version') or {}).get('identifier', '')
        _sev_icons = {'critical': '🔴', 'high': '🟠', 'medium': '🟡', 'low': '🟢'}
        _action_map = {
            'created':        'Neue Schwachstelle',
            'dismissed':      'Ignoriert',
            'auto_dismissed': 'Automatisch ignoriert',
            'fixed':          'Behoben ✅',
            'reopened':       'Erneut geöffnet',
            'auto_reopened':  'Automatisch geöffnet',
            'reintroduced':   'Wieder eingeführt',
        }
        sev_icon  = _sev_icons.get(severity, '⚠️')
        act_label = _action_map.get(action, action)
        log.warning("Dependabot Alert [%s/%s] in %s: %s %s (#%s)", severity, action, repo_full, pkg_name, ecosystem, alert_num)
        if action in ('created', 'reopened', 'auto_reopened', 'reintroduced'):
            em_lines = [f"#{alert_num} · {severity.upper()} · {act_label}", f"Paket: {pkg_name} ({ecosystem})", summary]
            if fixed_in: em_lines.append(f"Fix verfügbar: {fixed_in}")
            if alert_url: em_lines.append(f"<a href=\"{alert_url}\">Alert anzeigen</a>")
            tg_msg = (f"{sev_icon} <b>Dependabot Alert:</b> {repo_full}\n#{alert_num} · {severity.upper()} · {act_label}\nPaket: {pkg_name} ({ecosystem})\n{summary}\n"
                      + (f"Fix verfügbar: {fixed_in}\n" if fixed_in else '') + (f"<a href=\"{alert_url}\">Alert anzeigen</a>" if alert_url else ''))
            _tg_em(cfg, tg_token, tg_chat, tg_notif, em_notif, 'security',
                tg_msg, f"Dependabot Alert: {repo_full} [{severity.upper()}]", em_lines)
        threading.Thread(target=_trigger_repo_poll, args=(repo_full,), daemon=True).start()

    return jsonify({'status': 'ok'}), 200


def _run_webhook_server() -> None:
    """Zweiter WSGI-Server auf Port 17793 — nur für GitHub-Webhook-Empfang.
    Ein WSGI-Wrapper blockiert alle Pfade außer POST /webhook, damit das
    komplette GitPulse-UI nicht auf dem Webhook-Port erreichbar ist."""

    class _WebhookOnly:
        """Lässt nur POST /webhook durch — alles andere → 403."""
        def __call__(self, environ, start_response):
            path   = environ.get('PATH_INFO', '')
            method = environ.get('REQUEST_METHOD', 'GET')
            if path == '/webhook' and method == 'POST':
                return app(environ, start_response)
            if path == '/webhook' and method == 'GET':
                start_response('200 OK', [('Content-Type', 'application/json')])
                return [b'{"status":"webhook endpoint ready","method":"POST required"}']
            start_response('403 Forbidden', [('Content-Type', 'text/plain')])
            return [b'Forbidden']

    try:
        srv = make_server('0.0.0.0', 17793, _WebhookOnly())
        log.info("Webhook-Listener bereit auf Port 17793")
        srv.serve_forever()
    except Exception as e:
        log.error("Webhook-Server Fehler: %s", e)


@app.route('/api/workflow/favorites', methods=['GET'])
def api_favorites_get():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    return jsonify(load_favorites())


@app.route('/api/workflow/favorites', methods=['POST'])
def api_favorites_add():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    body          = request.get_json(silent=True) or {}
    repo          = body.get('repo', '').strip()
    workflow_id   = body.get('workflow_id')
    workflow_name = body.get('workflow_name', '').strip()
    ref           = body.get('ref', '').strip()
    if not repo or not workflow_id or not workflow_name or not ref:
        return jsonify({'error': 'repo, workflow_id, workflow_name und ref erforderlich'}), 400
    favs = load_favorites()
    for fav in favs:
        if (fav['repo'] == repo and
                str(fav['workflow_id']) == str(workflow_id) and
                fav['ref'] == ref):
            return jsonify({'status': 'exists', 'id': fav['id']})
    new_fav = {
        'id':            secrets.token_hex(8),
        'repo':          repo,
        'workflow_id':   workflow_id,
        'workflow_name': workflow_name,
        'ref':           ref,
    }
    favs.append(new_fav)
    save_favorites(favs)
    log.info("Workflow-Favorit gespeichert: %s / %s @ %s", repo, workflow_name, ref)
    return jsonify({'status': 'saved', 'id': new_fav['id']})


@app.route('/api/workflow/favorites/<fav_id>', methods=['DELETE'])
def api_favorites_delete(fav_id: str):
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    favs     = load_favorites()
    new_favs = [f for f in favs if f['id'] != fav_id]
    if len(new_favs) == len(favs):
        return jsonify({'error': 'Favorit nicht gefunden'}), 404
    save_favorites(new_favs)
    log.info("Workflow-Favorit gelöscht: %s", fav_id)
    return jsonify({'status': 'deleted'})


@app.route('/events')
def events():
    redir = _auth_required(request)
    if redir:
        return abort(401)

    def stream():
        q: queue.Queue = queue.Queue(maxsize=10)
        with _sse_lock:
            _sse_queues.append(q)
        try:
            yield 'data: connected\n\n'
            while True:
                try:
                    q.get(timeout=30)
                    yield 'data: update\n\n'
                except queue.Empty:
                    yield ': ping\n\n'
        finally:
            with _sse_lock:
                try:
                    _sse_queues.remove(q)
                except ValueError:
                    pass

    return Response(stream_with_context(stream()),
                    mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache',
                             'X-Accel-Buffering': 'no'})


# ── Add-on Manager ────────────────────────────────────────────────────────────

def _gh_get_file_content(owner: str, repo: str, path: str, token: str, branch: str) -> dict | None:
    try:
        r = http.get(
            f'{GITHUB_API}/repos/{owner}/{repo}/contents/{path}',
            headers=_gh_headers(token), params={'ref': branch}, timeout=15
        )
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None

def _next_version_manual(current: str) -> str:
    parts = current.split('.')
    if len(parts) >= 3:
        parts = parts[:3]
        parts[2] = str(int(parts[2]) + 1)
        return '.'.join(parts)
    return current

@app.route('/api/addon-manager/addons')
def api_addon_manager_addons():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    cfg = load_config()
    token = cfg.get('github_token', '').strip()
    if not token:
        return jsonify({'error': 'no_token'}), 400
    repo_full = request.args.get('repo', '').strip()
    branch    = request.args.get('branch', 'dev').strip() or 'dev'
    if not repo_full or '/' not in repo_full:
        return jsonify({'error': 'invalid_repo'}), 400
    owner, repo = repo_full.split('/', 1)
    try:
        r = http.get(f'{GITHUB_API}/repos/{owner}/{repo}/contents/',
                     headers=_gh_headers(token), params={'ref': branch}, timeout=15)
        if r.status_code != 200:
            return jsonify({'error': 'api_error', 'status': r.status_code}), 502
        entries = r.json()
    except Exception:
        log.exception("addon-manager: Repo-Inhalt konnte nicht geladen werden")
        return jsonify({'error': 'internal error'}), 500
    dirs = sorted(e['name'] for e in entries if e['type'] == 'dir' and not e['name'].startswith('.'))
    addons = []
    for dir_name in dirs:
        cf = _gh_get_file_content(owner, repo, f'{dir_name}/config.yaml', token, branch)
        if not cf:
            continue
        try:
            content = base64.b64decode(cf['content']).decode('utf-8')
        except Exception:
            continue
        name = dir_name
        version = ''
        image = ''
        for line in content.splitlines():
            if line.startswith('name:') and not name or name == dir_name:
                name = line.split(':', 1)[1].strip().strip('"\'')
            if line.startswith('version:'):
                version = line.split(':', 1)[1].strip().strip('"\'')
            if line.startswith('image:'):
                image = line.split(':', 1)[1].strip().strip('"\'')
        if not version:
            continue
        addons.append({
            'dir':          dir_name,
            'name':         name,
            'version':      version,
            'next_version': _next_version_manual(version),
            'image':        image,
        })
    return jsonify({'addons': addons, 'repo': repo_full, 'branch': branch})


@app.route('/api/addon-manager/commit', methods=['POST'])
def api_addon_manager_commit():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    cfg = load_config()
    token = cfg.get('github_token', '').strip()
    if not token:
        return jsonify({'error': 'no_token'}), 400
    body          = request.get_json(silent=True) or {}
    repo_full     = body.get('repo', '').strip()
    addon_dir     = body.get('addon_dir', '').strip()
    new_version   = body.get('new_version', '').strip()
    changelog_txt = body.get('changelog_entry', '').strip()
    branch        = body.get('branch', 'dev').strip() or 'dev'
    if not repo_full or '/' not in repo_full:
        return jsonify({'error': 'invalid_repo'}), 400
    if not addon_dir or not new_version or not changelog_txt:
        return jsonify({'error': 'missing_fields'}), 400
    owner, repo = repo_full.split('/', 1)
    date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    config_path    = f'{addon_dir}/config.yaml'
    changelog_path = f'{addon_dir}/CHANGELOG.md'
    cf = _gh_get_file_content(owner, repo, config_path, token, branch)
    if not cf:
        return jsonify({'error': 'config_not_found'}), 404
    try:
        config_content = base64.b64decode(cf['content']).decode('utf-8')
        old_match = re.search(r'^version:\s*"([^"]+)"', config_content, re.MULTILINE)
        if not old_match:
            return jsonify({'error': 'version_not_found'}), 400
        old_version = old_match.group(1)
        new_config  = config_content.replace(f'version: "{old_version}"', f'version: "{new_version}"', 1)
        cl_content = ''
        clf = _gh_get_file_content(owner, repo, changelog_path, token, branch)
        if clf:
            cl_content = base64.b64decode(clf['content']).decode('utf-8')
        entry = f'\n## [{new_version}] - {date_str}\n\n{changelog_txt}\n'
        lines = cl_content.split('\n') if cl_content else ['']
        lines.insert(1, entry)
        new_changelog = '\n'.join(lines)
        # Git Trees API — atomarer Commit mit beiden Dateien
        ref_r = http.get(f'{GITHUB_API}/repos/{owner}/{repo}/git/ref/heads/{branch}',
                         headers=_gh_headers(token), timeout=15)
        if ref_r.status_code != 200:
            return jsonify({'error': 'branch_not_found'}), 404
        head_sha = ref_r.json()['object']['sha']
        commit_r = http.get(f'{GITHUB_API}/repos/{owner}/{repo}/git/commits/{head_sha}',
                            headers=_gh_headers(token), timeout=15)
        base_tree_sha = commit_r.json()['tree']['sha']
        tree_r = http.post(
            f'{GITHUB_API}/repos/{owner}/{repo}/git/trees',
            headers=_gh_headers(token),
            json={'base_tree': base_tree_sha, 'tree': [
                {'path': config_path,    'mode': '100644', 'type': 'blob', 'content': new_config},
                {'path': changelog_path, 'mode': '100644', 'type': 'blob', 'content': new_changelog},
            ]}, timeout=15
        )
        if tree_r.status_code != 201:
            return jsonify({'error': 'tree_failed'}), 502
        new_tree_sha = tree_r.json()['sha']
        commit_r2 = http.post(
            f'{GITHUB_API}/repos/{owner}/{repo}/git/commits',
            headers=_gh_headers(token),
            json={'message': f'chore: {addon_dir} v{new_version}',
                  'tree': new_tree_sha, 'parents': [head_sha]},
            timeout=15
        )
        if commit_r2.status_code != 201:
            return jsonify({'error': 'commit_failed'}), 502
        new_commit_sha = commit_r2.json()['sha']
        upd_r = http.patch(
            f'{GITHUB_API}/repos/{owner}/{repo}/git/refs/heads/{branch}',
            headers=_gh_headers(token),
            json={'sha': new_commit_sha}, timeout=15
        )
        if upd_r.status_code not in (200, 201):
            return jsonify({'error': 'ref_update_failed'}), 502
        log.info("addon-manager: %s v%s → v%s (%s)", addon_dir, old_version, new_version, new_commit_sha[:7])
        return jsonify({
            'status': 'committed',
            'old_version': old_version,
            'new_version': new_version,
            'commit_sha': new_commit_sha[:7],
            'commit_url': f'https://github.com/{owner}/{repo}/commit/{new_commit_sha}',
        })
    except Exception:
        log.exception("addon-manager: Commit fehlgeschlagen")
        return jsonify({'error': 'internal error'}), 500


@app.route('/api/addon-manager/image-check')
def api_addon_manager_image_check():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    cfg     = load_config()
    token   = cfg.get('github_token', '').strip()
    image   = request.args.get('image', '').strip()   # ghcr.io/owner/name
    version = request.args.get('version', '').strip()
    if not image or not version or not token:
        return jsonify({'error': 'missing_params'}), 400
    # image = ghcr.io/luckytriple7/claudecode → owner/name = luckytriple7/claudecode
    if len(image) > 300:
        return jsonify({'error': 'invalid_image'}), 400
    if '://' in image:
        parsed = urlparse(image)
        if parsed.hostname != 'ghcr.io':
            return jsonify({'error': 'invalid_image'}), 400
        repo_part = parsed.path.lstrip('/')
    else:
        # Prepend scheme so urlparse can properly validate the hostname
        parsed = urlparse(f'https://{image}')
        if parsed.hostname != 'ghcr.io':
            return jsonify({'error': 'invalid_image'}), 400
        repo_part = parsed.path.lstrip('/')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,99}/[A-Za-z0-9][A-Za-z0-9._-]{0,99}', repo_part):
        return jsonify({'error': 'invalid_image'}), 400
    owner = repo_part.split('/')[0]
    try:
        import base64 as _b64
        # GHCR token exchange requires "owner:token" Basic auth, not ":token"
        creds = _b64.b64encode(f'{owner}:{token}'.encode()).decode()
        tok_r = http.get(
            'https://ghcr.io/token',
            params={'scope': f'repository:{repo_part}:pull', 'service': 'ghcr.io'},
            headers={'Authorization': f'Basic {creds}'}, timeout=10
        )
        if tok_r.status_code != 200:
            return jsonify({'status': 'forbidden'})
        bearer = tok_r.json().get('token', '')
        man_r = http.head(
            f'https://ghcr.io/v2/{repo_part}/manifests/{version}',
            headers={
                'Authorization': f'Bearer {bearer}',
                'Accept': 'application/vnd.docker.distribution.manifest.v2+json,application/vnd.oci.image.index.v1+json',
            }, timeout=10
        )
        sc = man_r.status_code
        if sc == 200:
            return jsonify({'status': 'ok'})
        elif sc == 404:
            return jsonify({'status': 'building'})
        elif sc in (401, 403):
            return jsonify({'status': 'forbidden'})
        else:
            return jsonify({'status': 'unknown', 'http': sc})
    except Exception:
        log.exception("image-check fehlgeschlagen")
        return jsonify({'error': 'internal error'}), 500


@app.route('/api/addon-manager/history')
def api_addon_manager_history():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    cfg = load_config()
    token = cfg.get('github_token', '').strip()
    if not token:
        return jsonify({'error': 'no_token'}), 400
    repo_full = request.args.get('repo', '').strip()
    branch    = request.args.get('branch', 'dev').strip() or 'dev'
    addon_dir = request.args.get('addon_dir', '').strip()
    if not repo_full or '/' not in repo_full or not addon_dir:
        return jsonify({'error': 'invalid_params'}), 400
    if '/' in addon_dir or '..' in addon_dir:
        return jsonify({'error': 'invalid_addon_dir'}), 400
    owner, repo = repo_full.split('/', 1)
    config_path = f'{addon_dir}/config.yaml'
    try:
        r = http.get(
            f'{GITHUB_API}/repos/{owner}/{repo}/commits',
            headers=_gh_headers(token),
            params={'path': config_path, 'sha': branch, 'per_page': 10},
            timeout=15
        )
        if r.status_code != 200:
            return jsonify({'error': 'api_error', 'status': r.status_code}), 502
        commits = r.json()
    except Exception:
        log.exception("addon-manager: history laden fehlgeschlagen")
        return jsonify({'error': 'internal error'}), 500
    history = []
    for c in commits:
        sha  = c['sha']
        msg  = c['commit']['message'].split('\n')[0]
        date = c['commit']['committer']['date'][:10]
        cf   = _gh_get_file_content(owner, repo, config_path, token, sha)
        version = '?'
        if cf:
            try:
                content = base64.b64decode(cf['content']).decode('utf-8')
                mv = re.search(r'^version:\s*"([^"]+)"', content, re.MULTILINE)
                if mv:
                    version = mv.group(1)
            except Exception:
                pass
        history.append({'sha': sha, 'short_sha': sha[:7], 'message': msg, 'date': date, 'version': version})
    return jsonify({'history': history})


@app.route('/api/addon-manager/revert', methods=['POST'])
def api_addon_manager_revert():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    cfg = load_config()
    token = cfg.get('github_token', '').strip()
    if not token:
        return jsonify({'error': 'no_token'}), 400
    body       = request.get_json(silent=True) or {}
    repo_full  = body.get('repo', '').strip()
    addon_dir  = body.get('addon_dir', '').strip()
    target_sha = body.get('target_sha', '').strip()
    branch     = body.get('branch', 'dev').strip() or 'dev'
    if not repo_full or '/' not in repo_full or not addon_dir or not target_sha:
        return jsonify({'error': 'missing_fields'}), 400
    if not re.fullmatch(r'[0-9a-f]{7,40}', target_sha):
        return jsonify({'error': 'invalid_sha'}), 400
    if '/' in addon_dir or '..' in addon_dir:
        return jsonify({'error': 'invalid_addon_dir'}), 400
    owner, repo = repo_full.split('/', 1)
    config_path = f'{addon_dir}/config.yaml'
    try:
        cf = _gh_get_file_content(owner, repo, config_path, token, target_sha)
        if not cf:
            return jsonify({'error': 'config_not_found'}), 404
        old_config = base64.b64decode(cf['content']).decode('utf-8')
        mv = re.search(r'^version:\s*"([^"]+)"', old_config, re.MULTILINE)
        target_version = mv.group(1) if mv else '?'
        cf_cur = _gh_get_file_content(owner, repo, config_path, token, branch)
        current_version = '?'
        if cf_cur:
            mc = re.search(r'^version:\s*"([^"]+)"',
                           base64.b64decode(cf_cur['content']).decode('utf-8'), re.MULTILINE)
            if mc:
                current_version = mc.group(1)

        # Kompletten Ordner-Stand zum Ziel-Commit ermitteln (ganzer Add-on-Ordner, nicht nur config+changelog)
        target_root_r = http.get(f'{GITHUB_API}/repos/{owner}/{repo}/git/trees/{target_sha}',
                                  headers=_gh_headers(token), timeout=15)
        if target_root_r.status_code != 200:
            return jsonify({'error': 'target_tree_failed'}), 502
        target_entry = next((e for e in target_root_r.json().get('tree', [])
                              if e.get('path') == addon_dir and e.get('type') == 'tree'), None)
        if not target_entry:
            return jsonify({'error': 'addon_dir_not_found_at_target'}), 404
        target_dir_tree_sha = target_entry['sha']

        ref_r = http.get(f'{GITHUB_API}/repos/{owner}/{repo}/git/ref/heads/{branch}',
                         headers=_gh_headers(token), timeout=15)
        if ref_r.status_code != 200:
            return jsonify({'error': 'branch_not_found'}), 404
        head_sha = ref_r.json()['object']['sha']
        commit_r = http.get(f'{GITHUB_API}/repos/{owner}/{repo}/git/commits/{head_sha}',
                            headers=_gh_headers(token), timeout=15)
        base_tree_sha = commit_r.json()['tree']['sha']
        # Einzelner Tree-Eintrag vom Typ 'tree' ersetzt den kompletten Unterordner in einem Schritt —
        # alle anderen Add-on-Ordner und Repo-Dateien bleiben unangetastet.
        tree_r = http.post(
            f'{GITHUB_API}/repos/{owner}/{repo}/git/trees',
            headers=_gh_headers(token),
            json={'base_tree': base_tree_sha, 'tree': [
                {'path': addon_dir, 'mode': '040000', 'type': 'tree', 'sha': target_dir_tree_sha},
            ]}, timeout=15
        )
        if tree_r.status_code != 201:
            return jsonify({'error': 'tree_failed'}), 502
        new_tree_sha = tree_r.json()['sha']
        commit_r2 = http.post(
            f'{GITHUB_API}/repos/{owner}/{repo}/git/commits',
            headers=_gh_headers(token),
            json={'message': f'revert: {addon_dir} v{current_version} → v{target_version}',
                  'tree': new_tree_sha, 'parents': [head_sha]},
            timeout=15
        )
        if commit_r2.status_code != 201:
            return jsonify({'error': 'commit_failed'}), 502
        new_commit_sha = commit_r2.json()['sha']
        upd_r = http.patch(
            f'{GITHUB_API}/repos/{owner}/{repo}/git/refs/heads/{branch}',
            headers=_gh_headers(token),
            json={'sha': new_commit_sha}, timeout=15
        )
        if upd_r.status_code not in (200, 201):
            return jsonify({'error': 'ref_update_failed'}), 502
        log.info("addon-manager: revert %s v%s → v%s (%s)", addon_dir, current_version, target_version, new_commit_sha[:7])
        return jsonify({
            'status': 'reverted',
            'target_version': target_version,
            'commit_sha': new_commit_sha[:7],
            'commit_url': f'https://github.com/{owner}/{repo}/commit/{new_commit_sha}',
        })
    except Exception:
        log.exception("addon-manager: Revert fehlgeschlagen")
        return jsonify({'error': 'internal error'}), 500


# ── Startup ───────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    load_sessions()
    load_seen_releases()
    load_seen_activity()
    load_seen_comments()
    load_comment_state()

    # Initiales Token-Ablauf-Warning
    cfg   = load_config()
    token = cfg.get('github_token', '').strip()
    if token:
        ok, scopes, expires = _check_token(token)
        if ok:
            log.info("GitHub-Token gültig")
            if expires:
                log.info("Token-Ablauf: konfiguriert")
        else:
            log.warning("GitHub-Token ungültig oder nicht konfiguriert!")
    else:
        log.warning("Kein GitHub-Token in der Konfiguration gefunden.")

    # Poller-Thread
    t = threading.Thread(target=_poll_worker, daemon=True)
    t.start()

    # Webhook-Server auf Port 17793 — nur wenn Secret konfiguriert
    if cfg.get('webhook_secret', '').strip():
        wh = threading.Thread(target=_run_webhook_server, daemon=True)
        wh.start()
    else:
        log.info("Kein Webhook-Secret konfiguriert — Webhook deaktiviert, nur Polling aktiv")

    def _shutdown(signum, frame):
        log.info("Signal %s empfangen — GitPulse wird beendet", signum)
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT,  _shutdown)

    log.info("GitPulse bereit auf Port 17792")
    app.run(host='0.0.0.0', port=17792, debug=False, threaded=True)
