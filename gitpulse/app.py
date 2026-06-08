#!/usr/bin/env python3
import base64
import hashlib
import hmac
import json
import logging
import os
import queue
import re
import secrets
import smtplib
import time
import threading
from collections import defaultdict, deque
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
app = Flask(__name__, template_folder='/app/templates', static_folder='/app/static')


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

CONFIG_PATH   = '/data/options.json'
SESSIONS_PATH = '/data/sessions.json'
REPOS_PATH      = '/data/gitpulse_repos.json'   # überschreibt options.json Repos (überlebt Updates)
FAVORITES_PATH  = '/data/workflow_favorites.json'
LOCALES_PATH    = '/app/locales'

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
    'token_ok':    None,
    'token_scopes': '',
    'token_expires': '',
    'last_poll':   0,
    'error':       None,
    'rate_limit':  {'remaining': 5000, 'limit': 5000, 'reset': 0},
}
_gh_lock = threading.Lock()

# Seen releases (für Benachrichtigungen — persistent über Neustarts)
_SEEN_PATH = '/data/seen_releases.json'
_seen_releases: set[str] = set()

# Repos ohne Releases — 404 einmal bekommen, bis Neustart überspringen
_no_release_repos: set[str] = set()

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


def _compute_review_state(reviews: list) -> str:
    """Aggregiert Review-Entscheidungen: 'approved', 'changes_requested', 'pending', 'none'."""
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
    if reviews:
        return 'pending'
    return 'none'


def _fetch_repo_data(repo: str, token: str, run_limit: int = 25) -> dict:
    """Fetch PRs, Issues and latest workflow runs for one repo."""
    owner, name = repo.split('/', 1)

    repo_meta     = _gh_get(f'/repos/{repo}', token) or {}
    default_branch = repo_meta.get('default_branch', 'main')

    pulls_raw = _gh_get_paginated(f'/repos/{repo}/pulls', token) or []
    pulls = []
    for pr in pulls_raw:
        reviews_raw = _gh_get(f'/repos/{repo}/pulls/{pr["number"]}/reviews', token) or []
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
            'mergeable':    pr.get('mergeable_state', ''),
            'comments':     (pr.get('comments') or 0) + (pr.get('review_comments') or 0),
            'review_state': _compute_review_state(reviews_raw),
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
            'review_state': 'none',
        })

    closed_issues_raw = _gh_get(f'/repos/{repo}/issues', token,
                                 {'state': 'closed', 'per_page': 50, 'sort': 'updated', 'direction': 'desc'}) or []
    closed_issues = []
    for iss in (closed_issues_raw if isinstance(closed_issues_raw, list) else []):
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
        })

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

    # Alle Workflows (inkl. deaktivierte) für Verwaltung + Dispatch
    wf_raw = _gh_get(f'/repos/{repo}/actions/workflows', token) or {}
    workflows = []
    for wf in (wf_raw.get('workflows') or []):
        state = wf.get('state', 'active')
        workflows.append({
            'id':          wf['id'],
            'name':        wf['name'],
            'path':        wf['path'],
            'state':       state,
            'dispatchable': state == 'active',
        })

    latest_release = None
    if repo not in _no_release_repos:
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
                _no_release_repos.add(repo)
                log.info("%s hat noch keine Releases — Abfrage bis Neustart übersprungen", repo)
            else:
                log.warning("GitHub API /repos/%s/releases/latest → HTTP %d", repo, r.status_code)
        except Exception as e:
            log.error("GitHub API Fehler (%s/releases/latest): %s", repo, e)

    security = _fetch_security_alerts(repo, token)

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

    def _fmt_cs(a: dict) -> dict:
        rule = a.get('rule') or {}
        tool = a.get('tool') or {}
        loc  = ((a.get('most_recent_instance') or {}).get('location') or {})
        return {
            'number':      a.get('number', '?'),
            'severity':    rule.get('security_severity_level') or rule.get('severity', 'unknown'),
            'rule_id':     rule.get('id', ''),
            'description': rule.get('description', ''),
            'tool':        tool.get('name', 'CodeQL'),
            'path':        loc.get('path', ''),
            'line':        loc.get('start_line', ''),
            'url':         a.get('html_url', ''),
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
            if r.status_code in (403, 404, 451):
                return [], False
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
    cs  = _safe(f'/repos/{repo}/code-scanning/alerts')
    ss  = _safe(f'/repos/{repo}/secret-scanning/alerts')
    return {
        'dependabot':        [_fmt_dep(a) for a in dep],
        'dependabot_access': dep_access,
        'code_scanning':     [_fmt_cs(a)  for a in cs],
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
                    'body':       (rel.get('body') or '')[:500],
                })
                break  # nur neuestes Release pro Repo
        except Exception as e:
            log.error("Releases für %s: %s", repo, e)
    return results


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
        data = _fetch_repo_data(repo_name, token, run_limit)
        with _gh_lock:
            repos   = _gh_cache.get('my_repos', [])
            updated = False
            for i, rd in enumerate(repos):
                if rd['repo'] == repo_name:
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


def _tg_em(cfg: dict, tg_token: str, tg_chat: str, tg_notif: dict, em_notif: dict,
           key: str, tg_text: str, em_subject: str, em_lines: list) -> None:
    if tg_token and tg_chat and tg_notif.get(key, True):
        _send_telegram(tg_token, tg_chat, tg_text)
    if em_notif.get(key, True):
        _send_email(cfg, em_subject, _email_html(em_subject, em_lines))


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
    global _seen_releases, _first_poll_done

    token_ok, scopes, expires = _check_token(token)
    if not token_ok:
        with _gh_lock:
            _gh_cache['token_ok'] = False
            _gh_cache['error'] = 'Token ungültig oder abgelaufen'
        _notify_sse()
        return

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
            data = _fetch_repo_data(repo, token, run_limit)
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

    with _gh_lock:
        _gh_cache['my_repos']      = repo_data
        _gh_cache['releases']      = releases
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
    repo  = request.args.get('repo', '').strip()
    if not repo:
        return jsonify({'error': 'repo fehlt'}), 400
    cfg   = load_config()
    token = cfg.get('github_token', '').strip()
    if not token:
        return jsonify({'error': 'kein Token'}), 400
    try:
        branches = _gh_get_paginated(f'/repos/{repo}/branches', token)
        names = [b['name'] for b in (branches or []) if isinstance(b, dict) and 'name' in b]
        return jsonify(names)
    except Exception:
        log.exception("Branches-Abfrage Fehler (%s)", repo)
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
    'releases', 'repo_stats', 'star_fork', 'security',
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
        if action in ('created', 'appeared_in_branch', 'reopened', 'reopened_by_user'):
            em_lines = [f"#{alert_num} · {severity.upper()} · {act_label}", f"Tool: {tool_name}", desc]
            if loc_str: em_lines.append(f"📄 {loc_str}")
            if alert_url: em_lines.append(f"<a href=\"{alert_url}\">Alert anzeigen</a>")
            tg_msg = (f"{sev_icon} <b>Code Scanning Alert:</b> {repo_full}\n#{alert_num} · {severity.upper()} · {act_label}\nTool: {tool_name}\n{desc}\n"
                      + (f"📄 {loc_str}\n" if loc_str else '') + (f"<a href=\"{alert_url}\">Alert anzeigen</a>" if alert_url else ''))
            _tg_em(cfg, tg_token, tg_chat, tg_notif, em_notif, 'security',
                tg_msg, f"Code Scanning Alert: {repo_full} [{severity.upper()}]", em_lines)

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
    repo_part = image.removeprefix('ghcr.io/') if image.startswith('ghcr.io/') else image
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
    config_path    = f'{addon_dir}/config.yaml'
    changelog_path = f'{addon_dir}/CHANGELOG.md'
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
        clf = _gh_get_file_content(owner, repo, changelog_path, token, target_sha)
        old_changelog = base64.b64decode(clf['content']).decode('utf-8') if clf else ''
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
                {'path': config_path,    'mode': '100644', 'type': 'blob', 'content': old_config},
                {'path': changelog_path, 'mode': '100644', 'type': 'blob', 'content': old_changelog},
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

    log.info("GitPulse bereit auf Port 17792")
    app.run(host='0.0.0.0', port=17792, debug=False, threaded=True)
