#!/usr/bin/env python3
import json
import logging
import os
import queue
import re
import secrets
import time
import threading
from collections import defaultdict, deque
from datetime import datetime, timezone
from flask import (Flask, render_template, request, redirect,
                   url_for, make_response, abort, jsonify,
                   Response, stream_with_context)
from werkzeug.middleware.proxy_fix import ProxyFix
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
REPOS_PATH    = '/data/gitpulse_repos.json'   # überschreibt options.json Repos (überlebt Updates)
LOCALES_PATH  = '/app/locales'

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


def _gh_get_paginated(path: str, token: str, max_pages: int = 5) -> list:
    results = []
    url = f'{GITHUB_API}{path}' if path.startswith('/') else path
    page = 1
    while url and page <= max_pages:
        try:
            r = http.get(url, headers=_gh_headers(token),
                         params={'per_page': 100, 'page': page}, timeout=15)
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
                if 'rel="next"' in part:
                    m = re.search(r'<([^>]+)>', part)
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
                log.info("Token OK — Scopes: %s, Ablauf: %s", scopes or 'fine-grained', expires or 'kein Ablauf')
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


def _fetch_repo_data(repo: str, token: str) -> dict:
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
            'number':  iss['number'],
            'title':   iss['title'],
            'state':   iss['state'],
            'url':     iss['html_url'],
            'user':    iss['user']['login'],
            'avatar':  iss['user']['avatar_url'],
            'labels':  [l['name'] for l in iss.get('labels', [])],
            'created': iss['created_at'],
            'updated': iss['updated_at'],
        })

    runs_raw = _gh_get(f'/repos/{repo}/actions/runs', token, {'per_page': 25}) or {}
    runs = []
    for run in (runs_raw.get('workflow_runs') or [])[:25]:
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

    # Dispatchable workflows (haben workflow_dispatch trigger)
    wf_raw = _gh_get(f'/repos/{repo}/actions/workflows', token) or {}
    workflows = []
    for wf in (wf_raw.get('workflows') or []):
        if wf.get('state') == 'active':
            workflows.append({
                'id':   wf['id'],
                'name': wf['name'],
                'path': wf['path'],
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

    return {
        'repo':           repo,
        'owner':          owner,
        'name':           name,
        'default_branch': default_branch,
        'pulls':          pulls,
        'issues':         issues,
        'runs':           runs,
        'workflows':      workflows,
        'latest_release': latest_release,
        'open_prs':       len(pulls),
        'open_issues':    len(issues),
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


# ── SSE helpers ───────────────────────────────────────────────────────────────

def _notify_sse() -> None:
    with _sse_lock:
        for q in list(_sse_queues):
            try:
                q.put_nowait('update')
            except queue.Full:
                pass


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

    if _verbose():
        log.info("Polling %d eigene Repos, %d Watch-Repos", len(my_repos), len(watch_repos))

    # eigene Repos
    repo_data = []
    for repo in my_repos:
        try:
            data = _fetch_repo_data(repo, token)
            repo_data.append(data)
            if _verbose():
                log.info("%s — %d PRs, %d Issues", repo, data['open_prs'], data['open_issues'])
        except Exception as e:
            log.error("Repo %s Fehler: %s", repo, e)

    # Telegram: neue PRs / Issues / CI-Failures erkennen
    for rd in repo_data:
        rname = rd['repo']

        for pr in rd.get('pulls', []):
            key = pr['number']
            if key not in _seen_prs[rname]:
                if _first_poll_done and tg_token and tg_chat:
                    _send_telegram(tg_token, tg_chat,
                        f"🔀 Neuer PR: <b>{rname}</b>\n"
                        f"#{pr['number']} {pr['title']}\n"
                        f"von @{pr['user']}\n"
                        f"<a href=\"{pr['url']}\">PR öffnen</a>")
                _seen_prs[rname].add(key)

        for iss in rd.get('issues', []):
            key = iss['number']
            if key not in _seen_issues[rname]:
                if _first_poll_done and tg_token and tg_chat:
                    _send_telegram(tg_token, tg_chat,
                        f"🐛 Neues Issue: <b>{rname}</b>\n"
                        f"#{iss['number']} {iss['title']}\n"
                        f"von @{iss['user']}\n"
                        f"<a href=\"{iss['url']}\">Issue öffnen</a>")
                _seen_issues[rname].add(key)

        for run in rd.get('runs', []):
            run_id   = run['id']
            curr_con = run.get('conclusion')
            _con_icons  = {'success': '✅', 'failure': '❌', 'cancelled': '⏹', 'skipped': '⏭', 'timed_out': '⏱'}
            _con_labels = {'success': 'Erfolgreich', 'failure': 'Fehlgeschlagen', 'cancelled': 'Abgebrochen',
                           'skipped': 'Übersprungen', 'timed_out': 'Timeout'}
            _evt_labels = {'push': 'Push', 'pull_request': 'PR', 'workflow_dispatch': 'Manuell',
                           'schedule': 'Zeitplan', 'release': 'Release'}
            run_info = (f"<b>{run['name']}</b> #{run.get('run_number','')}\n"
                        f"Branch: {run.get('branch','?')} · {_evt_labels.get(run.get('event',''), run.get('event','?'))}\n"
                        f"von @{run.get('actor','?')} · {run.get('head_sha','')[:7]}\n")
            if run_id not in _known_run_conclusions:
                # Erster Kontakt mit diesem Run
                if _first_poll_done and tg_token and tg_chat:
                    if curr_con is None:
                        # Läuft gerade → "gestartet"
                        _send_telegram(tg_token, tg_chat,
                            f"▶️ <b>Workflow gestartet:</b> {rname}\n"
                            + run_info
                            + f"<a href=\"{run['url']}\">Details</a>")
                    else:
                        # Schon abgeschlossen wenn zuerst gesehen → nur Abschluss
                        icon  = _con_icons.get(curr_con, '⚠️')
                        label = _con_labels.get(curr_con, curr_con)
                        _send_telegram(tg_token, tg_chat,
                            f"{icon} <b>Workflow beendet:</b> {rname}\n"
                            + run_info
                            + f"Status: {label}\n"
                            + f"<a href=\"{run['url']}\">Details</a>")
            else:
                prev_con = _known_run_conclusions[run_id]
                if prev_con is None and curr_con is not None:
                    # Gerade abgeschlossen
                    if _first_poll_done and tg_token and tg_chat:
                        icon  = _con_icons.get(curr_con, '⚠️')
                        label = _con_labels.get(curr_con, curr_con)
                        _send_telegram(tg_token, tg_chat,
                            f"{icon} <b>Workflow beendet:</b> {rname}\n"
                            + run_info
                            + f"Status: {label}\n"
                            + f"<a href=\"{run['url']}\">Details</a>")
            _known_run_conclusions[run_id] = curr_con

    # Telegram Startup-Nachricht (einmalig beim ersten Poll)
    if not _first_poll_done and tg_token and tg_chat:
        msg = "🚀 <b>GitPulse gestartet</b>\n"
        if repo_data:
            msg += "\n<b>Eigene Repos:</b>"
            for rd in repo_data:
                prs    = rd.get('open_prs', 0)
                issues = rd.get('open_issues', 0)
                msg += f"\n• <b>{rd['name']}</b> — {prs} PR{'s' if prs != 1 else ''}, {issues} Issue{'s' if issues != 1 else ''}"
        else:
            msg += "\nKeine eigenen Repos konfiguriert."
        _send_telegram(tg_token, tg_chat, msg)

    _first_poll_done = True

    # Watch-Repos Releases
    releases = _fetch_releases(watch_repos, token, incl_betas)

    # Neue Releases erkennen + Telegram-Benachrichtigung
    new_releases = []
    for rel in releases:
        key = f"{rel['repo']}@{rel['tag']}"
        if key not in _seen_releases:
            new_releases.append(rel)
            _seen_releases.add(key)
            log.info("Neues Release: %s %s", rel['repo'], rel['tag'])
            if tg_token and tg_chat:
                label = '🔵 Pre-Release' if rel['prerelease'] else '🟢 Release'
                _send_telegram(tg_token, tg_chat,
                               f"{label}: <b>{rel['repo']}</b>\n"
                               f"Version: <code>{rel['tag']}</code>\n"
                               f"<a href=\"{rel['url']}\">Release-Seite</a>")

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
    if lang not in ('de', 'en'):
        lang = 'en'
    next_url = request.args.get('next', '/')
    resp = make_response(redirect(next_url))
    resp.set_cookie('lang', lang, max_age=365 * 86400, samesite='Lax')
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
    except Exception as e:
        log.error("PR-Merge Fehler: %s", e)
        return jsonify({'error': str(e)}), 500


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
    except Exception as e:
        log.error("Branches-Abfrage Fehler (%s): %s", repo, e)
        return jsonify({'error': str(e)}), 500


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
    except Exception as e:
        log.error("Workflow-Dispatch Fehler: %s", e)
        return jsonify({'error': str(e)}), 500


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


@app.route('/api/config/repos', methods=['GET'])
def api_config_repos_get():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    cfg        = load_config()
    user_repos = load_user_repos()
    if user_repos is not None:
        return jsonify({
            'source':      'user',
            'my_repos':    user_repos.get('my_repos', []),
            'watch_repos': user_repos.get('watch_repos', []),
        })
    return jsonify({
        'source':      'options',
        'my_repos':    [r for r in cfg.get('my_repos', [])    if r.strip()],
        'watch_repos': [r for r in cfg.get('watch_repos', []) if r.strip()],
    })


@app.route('/api/config/repos', methods=['POST'])
def api_config_repos_save():
    redir = _auth_required(request)
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    body        = request.get_json(silent=True) or {}
    my_repos    = [r.strip() for r in body.get('my_repos', [])    if r.strip()]
    watch_repos = [r.strip() for r in body.get('watch_repos', []) if r.strip()]
    save_user_repos({'my_repos': my_repos, 'watch_repos': watch_repos})
    _etag_cache.clear()  # frischer Poll für neue Repos
    log.info("Repo-Config gespeichert: %d eigene, %d Watch-Repos", len(my_repos), len(watch_repos))
    return jsonify({'status': 'saved', 'my_repos': my_repos, 'watch_repos': watch_repos})


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
    except Exception as e:
        log.error("Issue-Close Fehler: %s", e)
        return jsonify({'error': str(e)}), 500


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
    except Exception as e:
        log.error("Issue-Comment Fehler: %s", e)
        return jsonify({'error': str(e)}), 500


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
    except Exception as e:
        log.error("Workflow-Cancel Fehler: %s", e)
        return jsonify({'error': str(e)}), 500


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
    except Exception as e:
        log.error("Workflow-Rerun Fehler: %s", e)
        return jsonify({'error': str(e)}), 500


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
            log.info("GitHub-Token gültig (Scopes: %s)", scopes or 'fine-grained')
            if expires:
                log.info("Token läuft ab: %s", expires)
        else:
            log.warning("GitHub-Token ungültig oder nicht konfiguriert!")
    else:
        log.warning("Kein GitHub-Token in der Konfiguration gefunden.")

    # Poller-Thread
    t = threading.Thread(target=_poll_worker, daemon=True)
    t.start()

    log.info("GitPulse bereit auf Port 17792")
    app.run(host='0.0.0.0', port=17792, debug=False, threaded=True)
