#!/usr/bin/env python3
import json
import logging
import os
import secrets
import signal
import socket
import subprocess
import time
import urllib.request
from collections import defaultdict
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from flask import (Flask, render_template, request, redirect,
                   url_for, make_response, abort, jsonify, send_from_directory)
from werkzeug.middleware.proxy_fix import ProxyFix

import addon_hosts

logging.basicConfig(format='[%(levelname)s] [%(asctime)s] %(message)s', level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S', force=True)
log = logging.getLogger(__name__)
# Werkzeug HTTP-Access-Logs unterdrücken – nginx übernimmt das
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# In-App Console: Log-Buffer (max 300 Einträge)
from collections import deque
_log_buffer: deque = deque(maxlen=300)

class _BufferHandler(logging.Handler):
    _fmt = logging.Formatter('[%(levelname)s] [%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    def emit(self, record):
        try:
            _log_buffer.append({'ts': int(record.created * 1000), 'level': record.levelname, 'msg': self._fmt.format(record)})
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

app = Flask(__name__,
            template_folder='/app/templates',
            static_folder='/app/static')


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
READSTATE_PATH = '/data/read_state.json'
LOCALES_PATH  = '/app/locales'

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

# ── Geräteübergreifender Gelesen-Stand ────────────────────────────────────────
# Ohne das lag der Stand nur im localStorage des jeweiligen Browsers: eine auf
# dem Handy gelesene Nachricht blieb am Desktop weiter als "neu" markiert.
read_state: dict[str, int] = {}


def load_read_state() -> None:
    global read_state
    try:
        with open(READSTATE_PATH) as f:
            data = json.load(f)
        read_state = {str(k).lower(): int(v) for k, v in data.items()
                      if isinstance(v, (int, float))}
    except FileNotFoundError:
        pass
    except Exception as e:
        log.warning("Gelesen-Stand konnte nicht geladen werden: %s", e)


def save_read_state() -> None:
    try:
        with open(READSTATE_PATH, 'w') as f:
            json.dump(read_state, f)
    except Exception as e:
        log.warning("Gelesen-Stand konnte nicht gespeichert werden: %s", e)


load_read_state()

# ── Rate limiting ─────────────────────────────────────────────────────────────
_failed_attempts: dict[str, list[float]] = defaultdict(list)
_blocked_ips:     dict[str, float]       = {}
RATE_LIMIT_MAX    = 5
RATE_LIMIT_WINDOW = 10 * 60   # 10-min-Fenster für Fehlversuche
RATE_LIMIT_BLOCK  = 15 * 60   # 15 min Sperre


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

ICON_SVG: dict[str, str] = {
    'whatsapp': (
        '<path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099'
        '-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644'
        '.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059'
        '-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198'
        '-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916'
        '-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0'
        '-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875'
        ' 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694'
        '.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248'
        '-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403'
        'h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648'
        '-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888'
        '-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c'
        '-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 '
        '0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 '
        '5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554'
        ' 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>'
    ),
    'telegram': (
        '<path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 '
        '12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321'
        '.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 '
        '1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065'
        '-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78'
        '-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014'
        '-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 '
        '3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752'
        '-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524'
        ' 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/>'
    ),
    'signal': (
        '<path d="M12 2C6.477 2 2 6.477 2 12c0 2.022.609 3.901 1.654 5.464'
        'L2.15 22l4.697-1.413A9.965 9.965 0 0 0 12 22c5.523 0 10-4.477 '
        '10-10S17.523 2 12 2z"/>'
    ),
}

BRAND_COLORS: dict[str, str] = {
    'whatsapp': '#25D366',
    'telegram': '#2AABEE',
    'signal':   '#3A76F0',
}


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


def is_ingress() -> bool:
    """True when the request arrives via HA Supervisor Ingress (auth handled by HA)."""
    return bool(request.environ.get('HTTP_X_INGRESS_PATH'))


def get_client_ip(req) -> str:
    # Cloudflare Tunnel sets CF-Connecting-IP with the real public IP
    cf = req.headers.get('CF-Connecting-IP', '').strip()
    if cf:
        return cf
    # Behind nginx: ProxyFix already resolved X-Forwarded-For into remote_addr
    return req.remote_addr or 'unknown'


_gateway_cache: str = ''


def get_internal_host() -> str:
    """Notnagel-Ziel: der HA-Host. Nur noch relevant, wenn die Supervisor-API
    keinen Container-Hostnamen liefert (siehe messenger_host)."""
    global _gateway_cache
    configured = load_config().get('internal_host', '').strip()
    if configured:
        return configured
    if _gateway_cache:
        return _gateway_cache
    _gateway_cache = '172.30.32.2'
    try:
        out = subprocess.check_output(['ip', 'route', 'show', 'default'],
                                      text=True, stderr=subprocess.DEVNULL)
        for token, value in zip(out.split(), out.split()[1:]):
            if token == 'via':
                _gateway_cache = value
                break
    except Exception:
        pass
    return _gateway_cache


def messenger_host(m: dict) -> str:
    """Zielhost eines Messenger-Add-ons.

    Container-Hostname aus der Supervisor-API zuerst — der funktioniert auch
    ohne veroeffentlichten Host-Port. Ein ausdruecklich gesetzter
    internal_host hat weiterhin Vorrang.
    """
    override = load_config().get('internal_host', '').strip()
    return addon_hosts.resolve_host(m.get('icon', ''), get_internal_host(), override)


def check_port(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def fetch_last_received(host: str, port: int, timeout: float = 2.0) -> dict | None:
    try:
        url = f'http://{host}:{port}/api/last-received'
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return data if data else None
    except Exception:
        return None


# Add-on-Status-Werte, die eine echte, nutzbare Messenger-Verbindung bedeuten
# ('authenticated' bei WhatsApp heisst nur "QR gescannt" — noch nicht sendebereit)
ADDON_STATUS_OK = {'connected', 'linked', 'ready'}


# Der Selbsttest der Add-ons laeuft dort ohnehin nur alle paar Stunden — die
# Statusabfrage des Portals kommt aber alle paar Sekunden. Deshalb gemerkt:
# Ergebnis 5 Minuten, "kennt die Route nicht" 30 Minuten.
_selfcheck_cache: dict[str, tuple[float, dict | None]] = {}
SELFCHECK_TTL_OK = 300.0
SELFCHECK_TTL_NONE = 1800.0


def fetch_selfcheck(host: str, port: int, timeout: float = 2.0) -> dict | None:
    """Liest /api/selfcheck des Add-ons: prueft dessen Innereien gegen Umbauten
    beim Anbieter. None, wenn das Add-on die Route nicht kennt — dann gibt es zu
    dieser Frage schlicht keine Aussage, was kein Fehler ist."""
    key = f'{host}:{port}'
    hit = _selfcheck_cache.get(key)
    if hit and (time.time() - hit[0]) < (SELFCHECK_TTL_NONE if hit[1] is None else SELFCHECK_TTL_OK):
        return hit[1]
    try:
        url = f'http://{host}:{port}/api/selfcheck'
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read())
            data = data if isinstance(data, dict) and 'ok' in data else None
    except Exception:
        data = None
    _selfcheck_cache[key] = (time.time(), data)
    return data


def fetch_addon_status(host: str, port: int, timeout: float = 2.0) -> dict | None:
    """Liest /api/status des Messenger-Add-ons. None, wenn es die Route nicht gibt."""
    try:
        url = f'http://{host}:{port}/api/status'
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return data if isinstance(data, dict) else None
    except Exception:
        return None


def fetch_messenger_status(host: str, m: dict) -> dict:
    port      = m['port']
    reachable = check_port(host, port)
    last      = fetch_last_received(host, port) if reachable else None
    api       = fetch_addon_status(host, port) if reachable else None
    name      = m.get('name', m['icon'])

    addon_status = str((api or {}).get('status') or '')
    detail       = str((api or {}).get('error') or '')

    if not reachable:
        state = 'offline'
    elif api is None:
        # Add-on ohne /api/status: offener Port bleibt das einzige Signal
        state = 'online'
    elif addon_status.lower() in ADDON_STATUS_OK:
        state = 'online'
    else:
        state = 'degraded'

    # Verbunden heisst noch nicht, dass alles funktioniert: der Selbsttest des
    # Add-ons meldet, wenn der Anbieter etwas umgebaut hat. Das ist ein eigener
    # Zustand — die Verbindung steht ja, nur ein Teil arbeitet nicht mehr.
    health = fetch_selfcheck(host, port) if state == 'online' else None
    if health and health.get('ok') is False:
        state = 'warn'
        betroffen = [x.get('feature') for x in
                     (health.get('broken') or []) + (health.get('changed') or []) if x.get('feature')]
        betroffen = list(dict.fromkeys(betroffen))
        if not detail:
            detail = ', '.join(betroffen)
        log.warning('Selbsttest %s:%s meldet Aenderungen beim Anbieter: %s',
                    name, port, ', '.join(betroffen) or '?')

    if state == 'online':
        preview = (last or {}).get('preview', '')
        log.debug('Poll %s:%s — online last="%s"', name, port, preview[:60] if preview else '—')
    elif state == 'degraded':
        log.warning('Poll %s:%s — erreichbar, aber nicht verbunden (status=%s error=%s)',
                    name, port, addon_status or '?', detail or '—')
    else:
        log.debug('Poll %s:%s — nicht erreichbar', name, port)

    return {
        'icon':          m['icon'].lower(),
        'name':          name,
        'reachable':     reachable,
        'state':         state,
        'addon_status':  addon_status,
        'detail':        detail,
        'last_received': last,
        'health':        None if health is None else {
            'ok': bool(health.get('ok')),
            'checked': health.get('checked'),
            'checked_shape': health.get('checkedShape'),
            'ts': health.get('ts'),
            'affected': [x.get('feature') for x in
                         (health.get('broken') or []) + (health.get('changed') or []) if x.get('feature')],
        },
    }


def enrich_messengers(messengers: list) -> list:
    result = []
    for m in messengers:
        icon_key = m.get('icon', '').lower()
        result.append({
            **m,
            'svg': ICON_SVG.get(icon_key, ICON_SVG.get('signal', '')),
            'color': BRAND_COLORS.get(icon_key, '#888'),
        })
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
    resp.headers['Cache-Control']        = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma']               = 'no-cache'
    resp.headers['Expires']              = '0'
    resp.headers['Service-Worker-Allowed'] = '/'
    return resp


@app.route('/health')
def health():
    return 'ok', 200


@app.route('/api/logs')
def api_logs():
    since = int(request.args.get('since', 0))
    entries = [e for e in _log_buffer if e['ts'] > since]
    return jsonify(entries)


@app.route('/status')
def status():
    if not is_ingress() and not is_valid_session(request.cookies.get('mp_session')):
        return '', 401
    config = load_config()
    messengers = [m for m in config.get('messengers', [])
                  if m.get('enabled', True) and m.get('icon') and m.get('port')]
    with ThreadPoolExecutor(max_workers=len(messengers) or 1) as ex:
        result = list(ex.map(lambda m: fetch_messenger_status(messenger_host(m), m),
                             messengers))
    for r in result:
        r['last_opened'] = read_state.get(r['icon'], 0)
    return jsonify(result)


@app.route('/api/mark-read', methods=['POST'])
def api_mark_read():
    if not is_ingress() and not is_valid_session(request.cookies.get('mp_session')):
        return '', 401
    icon = (request.form.get('icon') or '').strip().lower()
    known = {str(m.get('icon', '')).lower()
             for m in load_config().get('messengers', [])}
    if not icon or icon not in known:
        return '', 400
    ts = int(time.time() * 1000)
    if ts > read_state.get(icon, 0):
        read_state[icon] = ts
        save_read_state()
    return jsonify({'icon': icon, 'last_opened': read_state[icon]})


@app.route('/proxy-offline')
def proxy_offline():
    name = request.headers.get('X-Messenger-Name', 'Messenger')
    icon = request.headers.get('X-Messenger-Icon', '')
    lang = detect_language(request)
    t    = load_translations(lang)
    return render_template('proxy_offline.html', name=name, icon=icon, t=t, lang=lang), 502


@app.route('/auth-check')
def auth_check():
    """Called internally by nginx to validate the session cookie."""
    if is_ingress():
        return '', 200
    if is_valid_session(request.cookies.get('mp_session')):
        return '', 200
    return '', 401


@app.route('/')
def index():
    if not is_ingress() and not is_valid_session(request.cookies.get('mp_session')):
        return redirect(url_for('login'))
    config = load_config()
    lang = detect_language(request)
    t = load_translations(lang)
    messengers = enrich_messengers(
        [m for m in config.get('messengers', []) if m.get('enabled', True)]
    )
    poll_interval = max(5, int(config.get('poll_interval', 30)))
    return render_template('index.html', messengers=messengers, t=t, lang=lang,
                           poll_interval=poll_interval, ingress_mode=is_ingress())


@app.route('/login', methods=['GET', 'POST'])
def login():
    if is_ingress():
        return redirect(url_for('index'))
    config = load_config()
    lang = detect_language(request)
    t = load_translations(lang)
    error = None

    if is_valid_session(request.cookies.get('mp_session')):
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
                'mp_session', token,
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
    if is_ingress():
        return redirect(url_for('index'))
    token = request.cookies.get('mp_session')
    if token in sessions:
        del sessions[token]
        save_sessions()
    resp = make_response(redirect(url_for('login')))
    resp.delete_cookie('mp_session')
    return resp


@app.route('/set-lang/<lang>')
def set_lang(lang: str):
    if lang not in ('de', 'en'):
        abort(400)
    cookie_lang = 'en' if lang == 'en' else 'de'
    ref = request.referrer or '/'
    ref = ref.replace('\\', '')
    parsed_ref = urlparse(ref)
    if parsed_ref.scheme or parsed_ref.netloc or not ref.startswith('/'):
        ref = '/'
    resp = make_response(redirect(ref))
    resp.set_cookie('lang', cookie_lang, max_age=365 * 24 * 3600, samesite='Lax')
    return resp


def _handle_sigterm(signum, frame) -> None:
    """Sauberer Exit bei SIGTERM (HA-Supervisor-Stop/Update) — ohne eigenen Handler
    würde Python den Default-Handler laufen lassen (exit 143), worüber sich der
    Supervisor beschwert ("should trap SIGTERM ... exit with code 0"). Diese App
    startet keine Hintergrund-Threads (Flask läuft single-threaded, das
    Status-Polling passiert clientseitig per JS gegen /status) und Sessions
    werden bei jeder Änderung bereits synchron über save_sessions() persistiert
    — ein harter os._exit(0) ist daher sicher, es gibt keinen offenen State."""
    log.info("SIGTERM empfangen, beende sauber…")
    os._exit(0)


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, _handle_sigterm)
    # Flask läuft intern auf 5000; nginx lauscht auf 17770 und proxyt dorthin
    app.run(host='127.0.0.1', port=5000, debug=False)
