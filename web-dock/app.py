#!/usr/bin/env python3
import json
import logging
import os
import secrets
import socket
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from flask import (Flask, render_template, request, redirect,
                   url_for, make_response, abort, jsonify, send_from_directory,
                   send_file)
from werkzeug.middleware.proxy_fix import ProxyFix

logging.basicConfig(format='[%(levelname)s] %(message)s', level=logging.INFO)
log = logging.getLogger(__name__)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

app = Flask(__name__,
            template_folder='/app/templates',
            static_folder='/app/static')
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

CONFIG_PATH      = '/data/options.json'
SESSIONS_PATH    = '/data/sessions.json'
LOCALES_PATH     = '/app/locales'
ADDON_CONFIG_DIR = '/addon_config'

_config_cache = None
_config_mtime = 0.0
sessions: dict[str, float] = {}


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
            log.info("Sessions geladen: %d aktive Session(s)", len(sessions))
    except FileNotFoundError:
        pass
    except Exception as e:
        log.warning("Sessions konnten nicht geladen werden: %s", e)


load_sessions()

# ── Rate limiting ─────────────────────────────────────────────────────────────
_failed_attempts: dict[str, list[float]] = defaultdict(list)
_blocked_ips:     dict[str, float]       = {}
RATE_LIMIT_MAX    = 5
RATE_LIMIT_WINDOW = 10 * 60
RATE_LIMIT_BLOCK  = 15 * 60


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
        log.warning("IP '%s' für %d Minuten gesperrt (zu viele fehlgeschlagene Logins)", ip, RATE_LIMIT_BLOCK // 60)


def clear_failed_attempts(ip: str) -> None:
    _failed_attempts.pop(ip, None)
    _blocked_ips.pop(ip, None)


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


def check_port(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def active_sites(config: dict) -> list[dict]:
    return [s for s in config.get('sites', []) if s.get('enabled', True)
            and s.get('name') and s.get('host') and s.get('port')]


def enrich_sites(sites: list[dict]) -> list[dict]:
    result = []
    for idx, s in enumerate(sites):
        result.append({**s, 'idx': idx})
    return result


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
    resp.headers['Cache-Control']          = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma']                 = 'no-cache'
    resp.headers['Expires']               = '0'
    resp.headers['Service-Worker-Allowed'] = '/'
    return resp


@app.route('/site-icon/<int:idx>')
def site_icon(idx: int):
    if not is_valid_session(request.cookies.get('wd_session')):
        abort(401)
    config = load_config()
    sites  = active_sites(config)
    if idx < 0 or idx >= len(sites):
        abort(404)
    icon_file = sites[idx].get('icon', '').strip()
    if not icon_file:
        abort(404)
    icon_path = os.path.join(ADDON_CONFIG_DIR, icon_file)
    if not os.path.isfile(icon_path):
        abort(404)
    return send_file(icon_path, mimetype='image/png')


@app.route('/health')
def health():
    return 'ok', 200


@app.route('/status')
def status():
    if not is_valid_session(request.cookies.get('wd_session')):
        return '', 401
    config = load_config()
    sites  = active_sites(config)
    def check(entry):
        idx, s = entry
        return {'idx': idx, 'reachable': check_port(s['host'], int(s['port']))}
    with ThreadPoolExecutor(max_workers=len(sites) or 1) as ex:
        result = list(ex.map(check, enumerate(sites)))
    return jsonify(result)


@app.route('/proxy-offline')
def proxy_offline():
    name = request.headers.get('X-Site-Name', 'Dienst')
    lang = detect_language(request)
    t    = load_translations(lang)
    return render_template('proxy_offline.html', name=name, t=t, lang=lang), 502


@app.route('/auth-check')
def auth_check():
    if is_valid_session(request.cookies.get('wd_session')):
        return '', 200
    return '', 401


@app.route('/')
def index():
    if not is_valid_session(request.cookies.get('wd_session')):
        return redirect(url_for('login'))
    config = load_config()
    lang   = detect_language(request)
    t      = load_translations(lang)
    sites  = enrich_sites(active_sites(config))
    poll_interval = max(5, int(config.get('poll_interval', 30)))
    return render_template('index.html', sites=sites, t=t, lang=lang,
                           poll_interval=poll_interval)


@app.route('/login', methods=['GET', 'POST'])
def login():
    config = load_config()
    lang   = detect_language(request)
    t      = load_translations(lang)
    error  = None

    if is_valid_session(request.cookies.get('wd_session')):
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
                'wd_session', token,
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
    token = request.cookies.get('wd_session')
    if token in sessions:
        del sessions[token]
        save_sessions()
    resp = make_response(redirect(url_for('login')))
    resp.delete_cookie('wd_session')
    return resp


@app.route('/set-lang/<lang>')
def set_lang(lang: str):
    if lang not in ('de', 'en'):
        abort(400)
    ref = request.referrer or url_for('index')
    resp = make_response(redirect(ref))
    resp.set_cookie('lang', lang, max_age=365 * 24 * 3600, samesite='Lax')
    return resp


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)
