#!/usr/bin/env python3
"""MyPage — Homepage-Baukasten für Home Assistant.

Zwei Server in einem Prozess:
  - Port 17760: öffentliche Homepage (kein Login, Besucherzähler)
  - Port 17761: Admin-Panel (Login + Brute-Force-Schutz, auch via HA Ingress)
"""
import hashlib
import html as html_mod
import io
import ipaddress
import json
import logging
import os
import re
import secrets
import shutil
import smtplib
import subprocess
import tempfile
import threading
import time
import uuid
import zipfile
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import markdown as md_lib
try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False
from flask import (Flask, render_template, request, redirect, url_for,
                   make_response, jsonify, abort, send_from_directory,
                   send_file)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import requests as http

logging.basicConfig(format='[%(levelname)s] [%(asctime)s] %(message)s',
                    level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S', force=True)
log = logging.getLogger(__name__)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

_BASE = os.environ.get('MYPAGE_BASE', '/app')
# Nutzdaten liegen im addon_config-Mapping (/addon_configs/<slug> auf dem Host),
# damit sie über den Share zugänglich sind; options.json verwaltet HA in /data.
_DATA = os.environ.get('MYPAGE_DATA', '/config')
_OPTS = os.environ.get('MYPAGE_OPTIONS', '/data')

CONFIG_PATH   = _OPTS + '/options.json'
SITE_PATH     = _DATA + '/site.json'
STATS_PATH    = _DATA + '/stats.json'
MESSAGES_PATH = _DATA + '/messages.json'
SESSIONS_PATH = _DATA + '/sessions.json'
USERS_PATH    = _DATA + '/users.json'
USESSIONS_PATH = _DATA + '/user_sessions.json'
UPLOADS_DIR   = Path(_DATA) / 'uploads'
# Benutzerdateien: optional auf SMB-Share (run.sh setzt MYPAGE_USERFILES nach Mount)
USERFILES_BASE = Path(os.environ.get('MYPAGE_USERFILES', _DATA + '/users'))
SMB_MOUNTED    = bool(os.environ.get('MYPAGE_USERFILES'))
LOCALES_PATH  = _BASE + '/locales'

PUBLIC_PORT = 17760
ADMIN_PORT  = 17761

GITHUB_API = 'https://api.github.com'

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
USERFILES_BASE.mkdir(parents=True, exist_ok=True)

# ── Flask-Apps ────────────────────────────────────────────────────────────────

public_app = Flask('mypage_public', template_folder=_BASE + '/templates')
admin_app  = Flask('mypage_admin',  template_folder=_BASE + '/templates')
admin_app.config['MAX_CONTENT_LENGTH'] = 64 * 1024 * 1024   # Backups können größer sein
# Öffentliche App: großzügig für Mitglieder-Uploads (Limit wird beim Start aus den
# Optionen gesetzt), Formularfelder (Kontakt) bleiben klein
public_app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024
public_app.config['MAX_FORM_MEMORY_SIZE'] = 2 * 1024 * 1024


class _IngressMiddleware:
    """Liest X-Ingress-Path vom HA Supervisor und setzt SCRIPT_NAME,
    damit url_for() hinter dem Ingress-Proxy korrekte URLs erzeugt."""
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


admin_app.wsgi_app  = _IngressMiddleware(ProxyFix(admin_app.wsgi_app,  x_for=1, x_proto=1, x_host=1))
public_app.wsgi_app = ProxyFix(public_app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# ── State ─────────────────────────────────────────────────────────────────────

_config_cache: dict | None = None
_config_mtime: float = 0.0
sessions: dict[str, float] = {}

_site_lock  = threading.Lock()
_stats_lock = threading.Lock()
_msg_lock   = threading.Lock()
_users_lock = threading.Lock()

# Mitglieder-Sessions (getrennt vom Admin)
user_sessions: dict[str, list] = {}  # token → [user_id, expires]
USER_SESSION_HOURS = 24 * 7
_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

# Kontaktformular-Rate-Limit (IP → Zeitstempel)
_contact_times: dict[str, list[float]] = defaultdict(list)
CONTACT_MAX_PER_HOUR = 5
MESSAGES_MAX = 200

# Brute-Force-Schutz
_failed_attempts: dict[str, list[float]] = defaultdict(list)
_blocked_ips:     dict[str, float]       = {}
RATE_LIMIT_MAX    = 5
RATE_LIMIT_WINDOW = 10 * 60
RATE_LIMIT_BLOCK  = 15 * 60

# Besucherzähler — Tages-Dedup in-memory (Privacy: nur gesalzene Hashes)
_visit_salt:  str = secrets.token_hex(16)
_seen_today:  set[str] = set()
_seen_day:    str = ''

ALLOWED_UPLOAD_EXT = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
STATS_KEEP_DAYS = 365

DEFAULT_SITE = {
    'profile': {
        'name': '', 'tagline_de': '', 'tagline_en': '',
        'bio_de': '', 'bio_en': '', 'avatar': '',
        'github': '', 'email': '', 'links': [],
    },
    'projects': [],
    'design': {
        'accent': '#58a6ff', 'mode': 'dark', 'layout': 'cards',
        'show_counter': True, 'public_url': '',
        'site_title': '', 'footer_text': '', 'favicon': '',
        'storage_subdir': '',
        'contact_enabled': False,
        'maintenance': False,
        'maintenance_text_de': '', 'maintenance_text_en': '',
    },
    'posts': [],
    'legal': {
        'impressum_de': '', 'impressum_en': '',
        'privacy_de': '', 'privacy_en': '',
    },
    'sections': {
        'skills': [],
        'timeline': [],
        'news': [],
    },
}


def render_md(text: str) -> str:
    """Markdown → HTML (Inhalte stammen ausschließlich vom Admin)."""
    return md_lib.markdown(text or '', extensions=['nl2br', 'sane_lists'])


# ── Config, Site-Daten & Sessions ─────────────────────────────────────────────

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


def load_site() -> dict:
    with _site_lock:
        try:
            with open(SITE_PATH, encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            return json.loads(json.dumps(DEFAULT_SITE))
        except Exception as e:
            log.warning("site.json konnte nicht geladen werden: %s", e)
            return json.loads(json.dumps(DEFAULT_SITE))
    # Fehlende Schlüssel mit Defaults auffüllen (für Updates)
    for section, defaults in DEFAULT_SITE.items():
        if section not in data:
            data[section] = json.loads(json.dumps(defaults))
        elif isinstance(defaults, dict):
            for k, v in defaults.items():
                data[section].setdefault(k, v)
    return data


def save_site(data: dict) -> None:
    with _site_lock:
        try:
            with open(SITE_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.warning("site.json konnte nicht gespeichert werden: %s", e)


def load_stats() -> dict:
    with _stats_lock:
        try:
            with open(STATS_PATH, encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {'total': 0, 'days': {}}
        except Exception as e:
            log.warning("stats.json konnte nicht geladen werden: %s", e)
            return {'total': 0, 'days': {}}


def save_stats(data: dict) -> None:
    with _stats_lock:
        try:
            with open(STATS_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f)
        except Exception as e:
            log.warning("stats.json konnte nicht gespeichert werden: %s", e)


def load_messages() -> list:
    with _msg_lock:
        try:
            with open(MESSAGES_PATH, encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return []
        except Exception as e:
            log.warning("messages.json konnte nicht geladen werden: %s", e)
            return []


def save_messages(data: list) -> None:
    with _msg_lock:
        try:
            with open(MESSAGES_PATH, 'w', encoding='utf-8') as f:
                json.dump(data[-MESSAGES_MAX:], f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.warning("messages.json konnte nicht gespeichert werden: %s", e)


def send_telegram(text: str) -> None:
    cfg = load_config()
    token = (cfg.get('telegram_bot_token') or '').strip()
    chat  = str(cfg.get('telegram_chat_id') or '').strip()
    if not token or not chat:
        return
    try:
        http.post(f'https://api.telegram.org/bot{token}/sendMessage',
                  json={'chat_id': chat, 'text': text}, timeout=10)
    except Exception as e:
        log.warning("Telegram-Benachrichtigung fehlgeschlagen: %s", e)


def smtp_configured() -> bool:
    return bool((load_config().get('smtp_host') or '').strip())


def send_email(subject: str, html_body: str, to: str | None = None) -> None:
    cfg      = load_config()
    host     = (cfg.get('smtp_host') or '').strip()
    port     = int(cfg.get('smtp_port') or 587)
    user     = (cfg.get('smtp_user') or '').strip()
    password = (cfg.get('smtp_password') or '').strip()
    to       = (to or cfg.get('smtp_to') or '').strip()
    use_tls  = bool(cfg.get('smtp_tls', True))
    if not host or not to:
        return
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = user or f'mypage@{host}'
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
        log.info("E-Mail-Benachrichtigung an '%s' gesendet", to)
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


def create_session(hours: int) -> str:
    token = secrets.token_hex(32)
    sessions[token] = time.time() + hours * 3600
    save_sessions()
    return token


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


# ── Brute-Force-Schutz ────────────────────────────────────────────────────────

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
    cookie = req.cookies.get('lang', '')
    if cookie in ('de', 'en'):
        return cookie
    accept = req.headers.get('Accept-Language', '')
    return 'de' if accept.lower().startswith('de') else 'en'


def _safe_next(raw: str) -> str:
    """Nur lokale Pfade als Redirect-Ziel zulassen (Open-Redirect-Schutz)."""
    nxt = (raw or '/').replace('\\', '')
    parsed = urlparse(nxt)
    if parsed.scheme or parsed.netloc or not nxt.startswith('/'):
        return '/'
    return nxt


# ── Besucherzähler ────────────────────────────────────────────────────────────

_BOT_UA = ('bot', 'crawl', 'spider', 'curl', 'wget', 'python-requests',
           'headless', 'lighthouse', 'pingdom', 'uptime')


VISIT_LOG_MAX = 500


def total_uniques(stats: dict) -> int:
    """Eindeutige Besucher gesamt — Altbestand wird aus den Tageswerten migriert."""
    if 'total_uniques' in stats:
        return stats['total_uniques']
    return sum(d.get('uniques', 0) for d in stats.get('days', {}).values())


# GeoIP-Lookup über ipapi.is (Opt-in, IPs werden nur bei aktivierter Option gesendet)
_geo_cache: dict[str, str] = {}  # ip → Ländercode ('' = abgefragt, kein Ergebnis)
GEO_CACHE_MAX       = 5000
GEO_LOOKUPS_PER_RUN = 20


def _geo_enabled() -> bool:
    return bool(load_config().get('geoip_lookup'))


def _cf_country(req) -> str:
    c = (req.headers.get('CF-IPCountry') or '').strip().upper()
    return c if len(c) == 2 and c.isalpha() and c != 'XX' else ''


def _lang_country(req) -> str:
    m = re.search(r'[a-zA-Z]{2,3}-([A-Za-z]{2})\b', req.headers.get('Accept-Language') or '')
    return m.group(1).upper() if m else ''


def _guess_country(req) -> str:
    """Besucherland: Cloudflare-Header > GeoIP-Cache > Accept-Language-Näherung."""
    ip = get_client_ip(req)
    return _cf_country(req) or _geo_cache.get(ip, '') or _lang_country(req)


def _lookup_ip(ip: str) -> str:
    """Land einer IP über ipapi.is — private/ungültige IPs werden nie gesendet."""
    try:
        addr = ipaddress.ip_address(ip)
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            return ''
    except ValueError:
        return ''
    try:
        params = {'q': ip}
        key = (load_config().get('geoip_api_key') or '').strip()
        if key:
            params['key'] = key
        r = http.get('https://api.ipapi.is/', params=params, timeout=10)
        if r.status_code == 200:
            code = ((r.json().get('location') or {}).get('country_code') or '').strip().upper()
            if len(code) == 2 and code.isalpha():
                return code
    except Exception as e:
        log.warning("GeoIP-Lookup fehlgeschlagen: %s", e)
    return ''


def _geoip_worker() -> None:
    """Trägt Länder für Log-Einträge ohne Land nach (max. 20 Lookups/Minute)."""
    while True:
        time.sleep(60)
        if not _geo_enabled():
            continue
        try:
            stats = load_stats()
            pending: list[str] = []
            for v in reversed(stats.get('log', [])):
                ip = v.get('ip') or ''
                if not v.get('country') and not v.get('bot') and ip and ip not in _geo_cache:
                    if ip not in pending:
                        pending.append(ip)
                if len(pending) >= GEO_LOOKUPS_PER_RUN:
                    break
            for ip in pending:
                if len(_geo_cache) >= GEO_CACHE_MAX:
                    _geo_cache.clear()
                _geo_cache[ip] = _lookup_ip(ip)
                time.sleep(1.5)
            if not pending:
                continue
            # Frisch laden und Cache anwenden, damit parallele Besuche nicht verloren gehen
            stats = load_stats()
            changed = False
            for v in stats.get('log', []):
                code = _geo_cache.get(v.get('ip') or '')
                if not v.get('country') and code:
                    v['country'] = code
                    changed = True
            if changed:
                save_stats(stats)
                log.info("GeoIP: %d IP(s) nachgeschlagen", len(pending))
        except Exception as e:
            log.warning("GeoIP-Worker-Fehler: %s", e)


def count_visit(req) -> None:
    global _seen_today, _seen_day
    if req.headers.get('X-MyPage-Export'):
        return  # interner Abruf für den statischen Export
    ua = req.headers.get('User-Agent') or ''
    is_bot = (not ua) or any(b in ua.lower() for b in _BOT_UA)
    ip = get_client_ip(req)
    today = date.today().isoformat()
    if today != _seen_day:
        _seen_day = today
        _seen_today = set()

    is_new = False
    if not is_bot:
        visitor = hashlib.sha256((ip + today + _visit_salt).encode()).hexdigest()[:16]
        is_new = visitor not in _seen_today
        _seen_today.add(visitor)

    stats = load_stats()
    # Besucher-Log (letzte Aufrufe inkl. Bots, für die Admin-Ansicht)
    visit_log = stats.setdefault('log', [])
    visit_log.append({
        'ts':   int(time.time()),
        'ip':   ip,
        'path': req.path[:100],
        'ua':   ua[:300],
        'ref':  (req.headers.get('Referer') or '')[:300],
        'lang': (req.headers.get('Accept-Language') or '')[:60],
        'country': _guess_country(req),
        'bot':  is_bot,
        'new':  is_new,
    })
    del visit_log[:-VISIT_LOG_MAX]

    if not is_bot:
        base_uniques = total_uniques(stats)
        day = stats['days'].setdefault(today, {'views': 0, 'uniques': 0})
        day['views'] += 1
        if is_new:
            day['uniques'] += 1
        stats['total'] = stats.get('total', 0) + 1
        stats['total_uniques'] = base_uniques + (1 if is_new else 0)
    # Alte Tage aufräumen
    if len(stats['days']) > STATS_KEEP_DAYS:
        for k in sorted(stats['days'])[:-STATS_KEEP_DAYS]:
            del stats['days'][k]
    save_stats(stats)


def _browser_name(ua: str) -> str:
    u = ua.lower()
    if 'edg/' in u:
        return 'Edge'
    if 'opr/' in u or 'opera' in u:
        return 'Opera'
    if 'firefox/' in u:
        return 'Firefox'
    if 'chrome/' in u or 'crios/' in u:
        return 'Chrome'
    if 'safari/' in u:
        return 'Safari'
    return 'Other'


def aggregate_visits(visit_log: list) -> tuple[list, list, list]:
    """Top-Referrer, Browser- und Länder-Verteilung aus dem Besucher-Log."""
    referrers: dict[str, int] = {}
    browsers:  dict[str, int] = {}
    countries: dict[str, int] = {}
    for v in visit_log:
        if v.get('bot'):
            continue
        host = urlparse(v.get('ref') or '').netloc
        if host:
            referrers[host] = referrers.get(host, 0) + 1
        b = _browser_name(v.get('ua') or '')
        browsers[b] = browsers.get(b, 0) + 1
        c = v.get('country') or ''
        if c:
            countries[c] = countries.get(c, 0) + 1
    top_ref = sorted(referrers.items(), key=lambda x: x[1], reverse=True)[:10]
    top_brw = sorted(browsers.items(),  key=lambda x: x[1], reverse=True)
    top_cty = sorted(countries.items(), key=lambda x: x[1], reverse=True)[:15]
    return ([{'name': k, 'count': c} for k, c in top_ref],
            [{'name': k, 'count': c} for k, c in top_brw],
            [{'name': k, 'count': c} for k, c in top_cty])


# ── Mitglieder (geheimer Bereich) ─────────────────────────────────────────────

def load_users() -> list:
    with _users_lock:
        try:
            with open(USERS_PATH, encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return []
        except Exception as e:
            log.warning("users.json konnte nicht geladen werden: %s", e)
            return []


def save_users(users: list) -> None:
    with _users_lock:
        try:
            with open(USERS_PATH, 'w', encoding='utf-8') as f:
                json.dump(users, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.warning("users.json konnte nicht gespeichert werden: %s", e)


def storage_available() -> bool:
    """False, wenn SMB konfiguriert ist, aber der Mount gerade nicht erreichbar ist.
    Bewusst kein Fallback auf lokalen Speicher — das würde Datei-Chaos geben."""
    if not SMB_MOUNTED:
        return True
    try:
        if not os.path.ismount(str(USERFILES_BASE)):
            return False
        os.listdir(USERFILES_BASE)
        return True
    except OSError:
        return False


def userfiles_root() -> Path:
    """Wurzel der Benutzerdateien — Basis (lokal oder SMB) + gewählter Unterordner."""
    base = USERFILES_BASE.resolve()
    sub = (load_site()['design'].get('storage_subdir') or '').strip().strip('/')
    if sub:
        p = (base / sub).resolve()
        if p == base or base in p.parents:
            return p
    return base


def user_dir(user: dict) -> Path:
    root = userfiles_root().resolve()
    uid_raw = str(user.get('id') or '')
    uid = secure_filename(uid_raw)
    if not uid or uid != uid_raw:
        raise ValueError('invalid user id')
    d = (root / uid).resolve()
    if d.parent != root:
        raise ValueError('invalid user directory path')
    d.mkdir(parents=True, exist_ok=True)
    return d


def store_user_file(d: Path, f) -> Path | None:
    """Upload sicher in Benutzerordner speichern (Namens-Kollisionen durchnummerieren)."""
    name = secure_filename(f.filename or '')
    if not name:
        return None
    target = (d / name).resolve()
    if target.parent != d.resolve():
        return None
    base, ext = os.path.splitext(name)
    n = 1
    while target.exists():
        # Unterstrich statt Klammern: übersteht secure_filename beim Download/Löschen
        target = d / f'{base}_{n}{ext}'
        n += 1
    f.save(target)
    return target


def user_usage_bytes(user: dict) -> int:
    return sum(f.stat().st_size for f in user_dir(user).iterdir() if f.is_file())


def save_user_sessions() -> None:
    try:
        now = time.time()
        with open(USESSIONS_PATH, 'w') as f:
            json.dump({k: v for k, v in user_sessions.items() if v[1] > now}, f)
    except Exception as e:
        log.warning("User-Sessions konnten nicht gespeichert werden: %s", e)


def load_user_sessions() -> None:
    global user_sessions
    try:
        with open(USESSIONS_PATH) as f:
            data = json.load(f)
        now = time.time()
        user_sessions = {k: v for k, v in data.items() if v[1] > now}
    except FileNotFoundError:
        pass
    except Exception as e:
        log.warning("User-Sessions konnten nicht geladen werden: %s", e)


def current_member(req) -> dict | None:
    token = req.cookies.get('usession')
    if not token or token not in user_sessions:
        return None
    uid, expires = user_sessions[token]
    if time.time() > expires:
        del user_sessions[token]
        return None
    return next((u for u in load_users() if u['id'] == uid), None)


def generate_member_password() -> str:
    """8 Zeichen, Groß/Klein/Zahlen, keine Sonderzeichen, keine verwechselbaren Zeichen."""
    up, low, dig = 'ABCDEFGHJKLMNPQRSTUVWXYZ', 'abcdefghjkmnpqrstuvwxyz', '23456789'
    chars = [secrets.choice(up), secrets.choice(low), secrets.choice(dig)]
    pool = up + low + dig
    while len(chars) < 8:
        chars.append(secrets.choice(pool))
    secrets.SystemRandom().shuffle(chars)
    return ''.join(chars)


def send_welcome_email(user: dict, password: str, subject: str | None = None) -> None:
    site = load_site()
    base = (site['design'].get('public_url') or '').rstrip('/')
    url = (base + '/bereich') if base else ''
    title = site['design'].get('site_title') or site['profile'].get('name') or 'MyPage'
    esc = html_mod.escape
    lines = [f'Hallo, für dich wurde ein persönlicher Dateibereich auf <b>{esc(title)}</b> eingerichtet.',
             f'<b>Login:</b> <a href="{esc(url)}">{esc(url)}</a>' if url else '',
             f'<b>Benutzername:</b> {esc(user["email"])}',
             f'<b>Passwort:</b> {esc(password)}',
             'Wenn du dieses Konto nicht erwartet hast, kannst du diese E-Mail ignorieren.']
    send_email(subject or f'Dein Zugang zu {title}',
               _email_html(f'🔑 Dein Zugang zu {esc(title)}', [l for l in lines if l]),
               to=user['email'])


def _smb_watchdog() -> None:
    """Stellt den SMB-Mount nach NAS-/FritzBox-Neustart automatisch wieder her."""
    mountpoint = os.environ.get('MYPAGE_USERFILES', '')
    if not mountpoint:
        return
    while True:
        time.sleep(60)
        try:
            cfg = load_config()
            server = (cfg.get('smb_server') or '').strip()
            share  = (cfg.get('smb_share') or '').strip()
            if not server or not share:
                continue
            healthy = False
            try:
                if os.path.ismount(mountpoint):
                    os.listdir(mountpoint)
                    healthy = True
            except OSError:
                healthy = False
            if healthy:
                continue
            log.warning("SMB-Mount nicht verfügbar — versuche Remount von //%s/%s ...", server, share)
            subprocess.run(['umount', '-l', mountpoint], capture_output=True, timeout=30)
            opts = ('vers=3.0,uid=0,gid=0,file_mode=0755,dir_mode=0755,'
                    'noperm,sec=ntlmssp,nodfs,iocharset=utf8,soft')
            user = (cfg.get('smb_user') or '').strip()
            if user:
                with tempfile.TemporaryFile(mode='w+t') as cred_file:
                    cred_file.write(f"username={user}\npassword={cfg.get('smb_password') or ''}\n")
                    cred_file.flush()
                    cred_file.seek(0)
                    cred_fd = cred_file.fileno()
                    opts_with_creds = f"{opts},credentials=/proc/self/fd/{cred_fd}"
                    r = subprocess.run(['mount', '-t', 'cifs', f'//{server}/{share}', mountpoint,
                                        '-o', opts_with_creds], capture_output=True, text=True, timeout=60)
            else:
                opts += ',guest'
                r = subprocess.run(['mount', '-t', 'cifs', f'//{server}/{share}', mountpoint,
                                    '-o', opts], capture_output=True, text=True, timeout=60)
            if r.returncode == 0:
                log.info("SMB-Mount wiederhergestellt")
            else:
                log.warning("SMB-Remount fehlgeschlagen: %s — nächster Versuch in 60 s",
                            (r.stderr or '').strip()[:200])
        except Exception as e:
            log.warning("SMB-Watchdog-Fehler: %s", e)


# ── Home-Assistant-Sensoren ───────────────────────────────────────────────────

SUPERVISOR_TOKEN = os.environ.get('SUPERVISOR_TOKEN', '')


def push_ha_sensors() -> None:
    """Meldet Besucherzahlen als Sensoren an Home Assistant (Supervisor-API)."""
    if not SUPERVISOR_TOKEN:
        return
    stats = load_stats()
    today = stats['days'].get(date.today().isoformat(), {'views': 0, 'uniques': 0})
    sensors = [
        ('mypage_views_total',    stats.get('total', 0), 'MyPage Aufrufe gesamt',  'mdi:counter',       'Aufrufe'),
        ('mypage_visitors_total', total_uniques(stats),  'MyPage Besucher gesamt', 'mdi:account-group', 'Besucher'),
        ('mypage_views_today',    today['views'],        'MyPage Aufrufe heute',   'mdi:eye',           'Aufrufe'),
        ('mypage_visitors_today', today['uniques'],      'MyPage Besucher heute',  'mdi:account',       'Besucher'),
    ]
    headers = {'Authorization': f'Bearer {SUPERVISOR_TOKEN}'}
    for sid, state, name, icon, unit in sensors:
        try:
            http.post(f'http://supervisor/core/api/states/sensor.{sid}',
                      headers=headers, timeout=10,
                      json={'state': state,
                            'attributes': {'friendly_name': name, 'icon': icon,
                                           'unit_of_measurement': unit}})
        except Exception as e:
            log.warning("HA-Sensor '%s' konnte nicht aktualisiert werden: %s", sid, e)
            return


def _sensor_worker() -> None:
    if not SUPERVISOR_TOKEN:
        log.info("Kein SUPERVISOR_TOKEN — HA-Sensoren deaktiviert (Dev-Modus)")
        return
    while True:
        push_ha_sensors()
        time.sleep(120)


# ── Blog-Posts ────────────────────────────────────────────────────────────────

def _normalize_post(raw: dict, existing: dict | None = None) -> dict:
    p = existing or {'id': uuid.uuid4().hex[:12]}
    p['date']     = _clean_str(raw.get('date'), 10)
    p['title_de'] = _clean_str(raw.get('title_de'), 150)
    p['title_en'] = _clean_str(raw.get('title_en'), 150)
    p['text_de']  = _clean_str(raw.get('text_de'), 30000)
    p['text_en']  = _clean_str(raw.get('text_en'), 30000)
    p['image']    = _clean_str(raw.get('image'), 500)
    return p


def sorted_posts(site: dict) -> list:
    return sorted(site.get('posts', []), key=lambda p: p.get('date', ''), reverse=True)


# ── GitHub-Import ─────────────────────────────────────────────────────────────

_GH_USER_RE = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$')
_GH_REPO_RE = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$')


def _gh_headers() -> dict:
    h = {'Accept': 'application/vnd.github+json',
         'User-Agent': 'MyPage-Addon'}
    token = (load_config().get('github_token') or '').strip()
    if token:
        h['Authorization'] = f'Bearer {token}'
    return h


def fetch_github_repos(user: str) -> list[dict]:
    """Öffentliche Repos eines Nutzers (max. 100, nach Sternen sortiert)."""
    if not _GH_USER_RE.match(user):
        raise ValueError('invalid user')
    r = http.get(f'{GITHUB_API}/users/{user}/repos',
                 params={'per_page': 100, 'sort': 'updated'},
                 headers=_gh_headers(), timeout=15)
    r.raise_for_status()
    repos = []
    for repo in r.json():
        if repo.get('fork'):
            continue
        repos.append({
            'full_name':   repo.get('full_name', ''),
            'name':        repo.get('name', ''),
            'description': repo.get('description') or '',
            'html_url':    repo.get('html_url', ''),
            'homepage':    repo.get('homepage') or '',
            'language':    repo.get('language') or '',
            'stars':       repo.get('stargazers_count', 0),
            'topics':      repo.get('topics', [])[:6],
        })
    repos.sort(key=lambda x: x['stars'], reverse=True)
    return repos


def fetch_github_readme(full_name: str) -> str:
    """README eines Repos als Markdown (leer bei Fehler)."""
    if not _GH_REPO_RE.match(full_name):
        return ''
    try:
        h = _gh_headers()
        h['Accept'] = 'application/vnd.github.raw+json'
        r = http.get(f'{GITHUB_API}/repos/{full_name}/readme', headers=h, timeout=15)
        if r.status_code == 200:
            return r.text[:20000]
    except Exception as e:
        log.warning("README von '%s' konnte nicht geladen werden: %s", full_name, e)
    return ''


def refresh_project_stars() -> None:
    """Aktualisiert Sterne-Zahlen importierter Projekte (1×/Stunde)."""
    while True:
        try:
            site = load_site()
            changed = False
            for p in site['projects']:
                repo = p.get('repo_full_name', '')
                if not repo or not _GH_REPO_RE.match(repo):
                    continue
                r = http.get(f'{GITHUB_API}/repos/{repo}', headers=_gh_headers(), timeout=15)
                if r.status_code == 200:
                    data = r.json()
                    new_stars = data.get('stargazers_count', p.get('stars', 0))
                    if new_stars != p.get('stars'):
                        p['stars'] = new_stars
                        changed = True
                time.sleep(1)
            if changed:
                save_site(site)
                log.info("Projekt-Sterne aktualisiert")
        except Exception as e:
            log.warning("Sterne-Update fehlgeschlagen: %s", e)
        time.sleep(3600)


# ── Hilfen: Projekt-Normalisierung ────────────────────────────────────────────

def _clean_str(v, maxlen: int = 2000) -> str:
    return str(v or '').strip()[:maxlen]


def _normalize_project(raw: dict, existing: dict | None = None) -> dict:
    p = existing or {'id': uuid.uuid4().hex[:12]}
    p['title']          = _clean_str(raw.get('title'), 120)
    p['desc_de']        = _clean_str(raw.get('desc_de'))
    p['desc_en']        = _clean_str(raw.get('desc_en'))
    p['image']          = _clean_str(raw.get('image'), 500)
    p['url']            = _clean_str(raw.get('url'), 500)
    p['repo_url']       = _clean_str(raw.get('repo_url'), 500)
    p['repo_full_name'] = _clean_str(raw.get('repo_full_name'), 150)
    p['language']       = _clean_str(raw.get('language'), 50)
    p['stars']          = max(0, int(raw.get('stars') or 0))
    p['long_de']        = _clean_str(raw.get('long_de'), 20000)
    p['long_en']        = _clean_str(raw.get('long_en'), 20000)
    gallery = raw.get('gallery') or []
    if isinstance(gallery, list):
        p['gallery'] = [_clean_str(g, 500) for g in gallery if _clean_str(g, 500)][:12]
    else:
        p.setdefault('gallery', [])
    tags = raw.get('tags') or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(',')]
    p['tags'] = [_clean_str(t, 30) for t in tags if _clean_str(t, 30)][:8]
    return p


def _has_detail(p: dict) -> bool:
    return bool((p.get('long_de') or p.get('long_en') or '').strip() or p.get('gallery'))


# ── Auth-Helfer (Admin) ───────────────────────────────────────────────────────

def _is_ingress() -> bool:
    return bool(request.script_root)


def _auth_required():
    if _is_ingress():
        return None  # HA übernimmt die Authentifizierung
    if not is_valid_session(request.cookies.get('session')):
        return redirect(url_for('login'))
    return None


def _api_auth():
    if _is_ingress():
        return None
    if not is_valid_session(request.cookies.get('session')):
        return jsonify({'error': 'unauthorized'}), 401
    return None


# ── Admin-Routen ──────────────────────────────────────────────────────────────

@admin_app.route('/health')
def admin_health():
    return 'OK', 200


@admin_app.route('/set-lang/<lang>')
def set_lang(lang: str):
    cookie_lang = 'en' if lang == 'en' else 'de'
    resp = make_response(redirect(_safe_next(request.args.get('next', '/'))))
    resp.set_cookie('lang', cookie_lang, max_age=365 * 86400, samesite='Lax')
    return resp


@admin_app.route('/login', methods=['GET', 'POST'])
def login():
    lang = detect_language(request)
    t = load_translations(lang)
    cfg = load_config()

    if _is_ingress() or is_valid_session(request.cookies.get('session')):
        return redirect(url_for('admin_index'))

    error = None
    if request.method == 'POST':
        ip = get_client_ip(request)
        if is_rate_limited(ip):
            error = t.get('error_locked', 'Zu viele Fehlversuche. Bitte 15 Minuten warten.')
        else:
            uname = request.form.get('username', '')
            pwd   = request.form.get('password', '')
            if (secrets.compare_digest(uname, str(cfg.get('username', 'admin'))) and
                    secrets.compare_digest(pwd, str(cfg.get('password', '')))):
                clear_failed_attempts(ip)
                hours = int(cfg.get('session_hours', 24))
                token = create_session(hours)
                resp = make_response(redirect(url_for('admin_index')))
                resp.set_cookie('session', token, httponly=True,
                                samesite='Lax', max_age=hours * 3600)
                return resp
            record_failed_attempt(ip)
            error = t.get('error_credentials', 'Ungültige Anmeldedaten.')

    return make_response(render_template('login.html', t=t, lang=lang, error=error))


@admin_app.route('/logout')
def logout():
    token = request.cookies.get('session')
    if token and token in sessions:
        del sessions[token]
        save_sessions()
    resp = make_response(redirect(url_for('login')))
    resp.delete_cookie('session')
    return resp


@admin_app.route('/')
def admin_index():
    redir = _auth_required()
    if redir:
        return redir
    lang = detect_language(request)
    t = load_translations(lang)
    return render_template('admin.html', t=t, lang=lang, ingress=_is_ingress())


@admin_app.route('/api/site')
def api_site():
    err = _api_auth()
    if err:
        return err
    return jsonify(load_site())


@admin_app.route('/api/profile', methods=['POST'])
def api_profile():
    err = _api_auth()
    if err:
        return err
    raw = request.get_json(silent=True) or {}
    site = load_site()
    prof = site['profile']
    for k, maxlen in (('name', 80), ('tagline_de', 200), ('tagline_en', 200),
                      ('bio_de', 3000), ('bio_en', 3000), ('avatar', 500),
                      ('github', 80), ('email', 150)):
        if k in raw:
            prof[k] = _clean_str(raw[k], maxlen)
    if 'links' in raw and isinstance(raw['links'], list):
        prof['links'] = [{'label': _clean_str(l.get('label'), 40),
                          'url':   _clean_str(l.get('url'), 500)}
                         for l in raw['links'][:10]
                         if isinstance(l, dict) and _clean_str(l.get('url'), 500)]
    save_site(site)
    return jsonify({'ok': True})


@admin_app.route('/api/design', methods=['POST'])
def api_design():
    err = _api_auth()
    if err:
        return err
    raw = request.get_json(silent=True) or {}
    site = load_site()
    d = site['design']
    accent = _clean_str(raw.get('accent'), 9)
    if re.match(r'^#[0-9A-Fa-f]{6}$', accent):
        d['accent'] = accent
    if raw.get('mode') in ('dark', 'light', 'auto'):
        d['mode'] = raw['mode']
    if raw.get('layout') in ('cards', 'list', 'minimal'):
        d['layout'] = raw['layout']
    if 'public_url' in raw:
        url = _clean_str(raw['public_url'], 200).rstrip('/')
        d['public_url'] = url if url.startswith(('http://', 'https://')) or not url else ''
    for flag in ('show_counter', 'contact_enabled', 'maintenance'):
        if flag in raw:
            d[flag] = bool(raw[flag])
    for k, maxlen in (('site_title', 80), ('footer_text', 300), ('favicon', 500),
                      ('maintenance_text_de', 1000), ('maintenance_text_en', 1000)):
        if k in raw:
            d[k] = _clean_str(raw[k], maxlen)
    save_site(site)
    return jsonify({'ok': True})


@admin_app.route('/api/sections', methods=['POST'])
def api_sections():
    err = _api_auth()
    if err:
        return err
    raw = request.get_json(silent=True) or {}
    site = load_site()
    sec = site['sections']
    if isinstance(raw.get('skills'), list):
        sec['skills'] = [_clean_str(s, 40) for s in raw['skills'] if _clean_str(s, 40)][:40]
    if isinstance(raw.get('timeline'), list):
        sec['timeline'] = [{
            'year':     _clean_str(e.get('year'), 30),
            'title_de': _clean_str(e.get('title_de'), 120),
            'title_en': _clean_str(e.get('title_en'), 120),
            'text_de':  _clean_str(e.get('text_de'), 1000),
            'text_en':  _clean_str(e.get('text_en'), 1000),
        } for e in raw['timeline'][:30] if isinstance(e, dict)]
    if isinstance(raw.get('news'), list):
        sec['news'] = [{
            'date':    _clean_str(e.get('date'), 30),
            'text_de': _clean_str(e.get('text_de'), 500),
            'text_en': _clean_str(e.get('text_en'), 500),
            'url':     _clean_str(e.get('url'), 500),
        } for e in raw['news'][:30] if isinstance(e, dict)]
    save_site(site)
    return jsonify({'ok': True})


@admin_app.route('/api/messages')
def api_messages():
    err = _api_auth()
    if err:
        return err
    return jsonify({'messages': list(reversed(load_messages()))})


@admin_app.route('/api/messages/<mid>', methods=['DELETE'])
def api_message_delete(mid: str):
    err = _api_auth()
    if err:
        return err
    msgs = load_messages()
    new = [m for m in msgs if m.get('id') != mid]
    if len(new) == len(msgs):
        return jsonify({'error': 'not found'}), 404
    save_messages(new)
    return jsonify({'ok': True})


@admin_app.route('/api/backup')
def api_backup():
    err = _api_auth()
    if err:
        return err
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for name in ('site.json', 'stats.json', 'messages.json'):
            p = Path(_DATA) / name
            if p.is_file():
                z.write(p, name)
        for f in UPLOADS_DIR.iterdir():
            if f.is_file():
                z.write(f, 'uploads/' + f.name)
    buf.seek(0)
    return send_file(buf, mimetype='application/zip', as_attachment=True,
                     download_name=f'mypage-backup-{date.today().isoformat()}.zip')


@admin_app.route('/api/restore', methods=['POST'])
def api_restore():
    err = _api_auth()
    if err:
        return err
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'error': 'no file'}), 400
    try:
        with zipfile.ZipFile(f) as z:
            names = z.namelist()
            if 'site.json' in names:
                json.loads(z.read('site.json'))  # muss valides JSON sein
            restored = 0
            for member in names:
                # Nur bekannte Dateien zulassen — Zip-Slip ausgeschlossen, da
                # Zielpfade aus Whitelist bzw. Basename + Extension-Check entstehen
                if member in ('site.json', 'stats.json', 'messages.json'):
                    target = Path(_DATA) / member
                elif member.startswith('uploads/'):
                    name = Path(member).name
                    if not name or Path(name).suffix.lower() not in ALLOWED_UPLOAD_EXT:
                        continue
                    target = UPLOADS_DIR / name
                else:
                    continue
                with open(target, 'wb') as dst:
                    dst.write(z.read(member))
                restored += 1
    except (zipfile.BadZipFile, json.JSONDecodeError, KeyError):
        return jsonify({'error': 'invalid backup'}), 400
    log.info("Backup wiederhergestellt: %d Datei(en)", restored)
    return jsonify({'ok': True, 'restored': restored})


@admin_app.route('/api/legal', methods=['POST'])
def api_legal():
    err = _api_auth()
    if err:
        return err
    raw = request.get_json(silent=True) or {}
    site = load_site()
    legal = site['legal']
    for k in ('impressum_de', 'impressum_en', 'privacy_de', 'privacy_en'):
        if k in raw:
            legal[k] = _clean_str(raw[k], 20000)
    save_site(site)
    return jsonify({'ok': True})


@admin_app.route('/api/projects', methods=['POST'])
def api_project_create():
    err = _api_auth()
    if err:
        return err
    raw = request.get_json(silent=True) or {}
    if not _clean_str(raw.get('title'), 120):
        return jsonify({'error': 'title required'}), 400
    site = load_site()
    site['projects'].append(_normalize_project(raw))
    save_site(site)
    return jsonify({'ok': True})


@admin_app.route('/api/projects/<pid>', methods=['PUT', 'DELETE'])
def api_project_edit(pid: str):
    err = _api_auth()
    if err:
        return err
    site = load_site()
    idx = next((i for i, p in enumerate(site['projects']) if p.get('id') == pid), None)
    if idx is None:
        return jsonify({'error': 'not found'}), 404
    if request.method == 'DELETE':
        site['projects'].pop(idx)
    else:
        raw = request.get_json(silent=True) or {}
        site['projects'][idx] = _normalize_project(raw, site['projects'][idx])
    save_site(site)
    return jsonify({'ok': True})


@admin_app.route('/api/projects/<pid>/move', methods=['POST'])
def api_project_move(pid: str):
    err = _api_auth()
    if err:
        return err
    direction = (request.get_json(silent=True) or {}).get('dir', '')
    site = load_site()
    projs = site['projects']
    idx = next((i for i, p in enumerate(projs) if p.get('id') == pid), None)
    if idx is None:
        return jsonify({'error': 'not found'}), 404
    new_idx = idx - 1 if direction == 'up' else idx + 1
    if 0 <= new_idx < len(projs):
        projs[idx], projs[new_idx] = projs[new_idx], projs[idx]
        save_site(site)
    return jsonify({'ok': True})


@admin_app.route('/api/posts', methods=['POST'])
def api_post_create():
    err = _api_auth()
    if err:
        return err
    raw = request.get_json(silent=True) or {}
    if not (_clean_str(raw.get('title_de'), 150) or _clean_str(raw.get('title_en'), 150)):
        return jsonify({'error': 'title required'}), 400
    site = load_site()
    site.setdefault('posts', []).append(_normalize_post(raw))
    save_site(site)
    return jsonify({'ok': True})


@admin_app.route('/api/posts/<pid>', methods=['PUT', 'DELETE'])
def api_post_edit(pid: str):
    err = _api_auth()
    if err:
        return err
    site = load_site()
    posts = site.setdefault('posts', [])
    idx = next((i for i, p in enumerate(posts) if p.get('id') == pid), None)
    if idx is None:
        return jsonify({'error': 'not found'}), 404
    if request.method == 'DELETE':
        posts.pop(idx)
    else:
        posts[idx] = _normalize_post(request.get_json(silent=True) or {}, posts[idx])
    save_site(site)
    return jsonify({'ok': True})


@admin_app.route('/api/users')
def api_users():
    err = _api_auth()
    if err:
        return err
    storage_ok = storage_available()
    out = []
    for u in load_users():
        used = user_usage_bytes(u) if storage_ok else 0
        out.append({'id': u['id'], 'email': u['email'], 'quota_mb': u.get('quota_mb', 500),
                    'used_mb': round(used / 1048576, 1),
                    'files': sum(1 for f in user_dir(u).iterdir() if f.is_file()) if storage_ok else 0,
                    'created': u.get('created', '')})
    return jsonify({'users': out, 'smtp': smtp_configured(),
                    'storage': str(userfiles_root()) if storage_ok else '',
                    'smb': SMB_MOUNTED, 'storage_ok': storage_ok})


@admin_app.route('/api/users', methods=['POST'])
def api_user_create():
    err = _api_auth()
    if err:
        return err
    raw = request.get_json(silent=True) or {}
    email = _clean_str(raw.get('email'), 150).lower()
    password = str(raw.get('password') or '')
    quota = max(1, min(100000, int(raw.get('quota_mb') or 500)))
    if not _EMAIL_RE.match(email):
        return jsonify({'error': 'invalid email'}), 400
    if len(password) < 8:
        return jsonify({'error': 'password too short'}), 400
    users = load_users()
    if any(u['email'] == email for u in users):
        return jsonify({'error': 'exists'}), 409
    user = {'id': uuid.uuid4().hex[:12], 'email': email,
            'pw_hash': generate_password_hash(password),
            'quota_mb': quota, 'created': date.today().isoformat()}
    users.append(user)
    save_users(users)
    user_dir(user)
    mail_sent = smtp_configured()
    if mail_sent:
        threading.Thread(target=send_welcome_email, args=(user, password), daemon=True).start()
    log.info("Benutzer '%s' angelegt (Quota %d MB)", email, quota)
    return jsonify({'ok': True, 'mail_sent': mail_sent,
                    'no_url': not (load_site()['design'].get('public_url') or '').strip()})


@admin_app.route('/api/users/<uid>', methods=['PUT', 'DELETE'])
def api_user_edit(uid: str):
    err = _api_auth()
    if err:
        return err
    users = load_users()
    user = next((u for u in users if u['id'] == uid), None)
    if user is None:
        return jsonify({'error': 'not found'}), 404
    if request.method == 'DELETE':
        users.remove(user)
        save_users(users)
        # Sessions des Benutzers beenden und Dateien entfernen
        for tok in [t for t, v in user_sessions.items() if v[0] == uid]:
            del user_sessions[tok]
        save_user_sessions()
        shutil.rmtree(user_dir(user), ignore_errors=True)
        log.info("Benutzer '%s' gelöscht", user['email'])
        return jsonify({'ok': True})
    raw = request.get_json(silent=True) or {}
    mail_sent = False
    if 'quota_mb' in raw:
        user['quota_mb'] = max(1, min(100000, int(raw.get('quota_mb') or 500)))
    password = str(raw.get('password') or '')
    if password:
        if len(password) < 8:
            return jsonify({'error': 'password too short'}), 400
        user['pw_hash'] = generate_password_hash(password)
        mail_sent = smtp_configured()
        if mail_sent:
            threading.Thread(target=send_welcome_email,
                             args=(user, password, f'Neues Passwort für deinen Bereich'),
                             daemon=True).start()
    save_users(users)
    return jsonify({'ok': True, 'mail_sent': mail_sent,
                    'no_url': not (load_site()['design'].get('public_url') or '').strip()})


def _admin_get_user(uid: str) -> dict | None:
    return next((u for u in load_users() if u['id'] == uid), None)


@admin_app.route('/api/users/<uid>/resend', methods=['POST'])
def api_user_resend(uid: str):
    """Zugangsdaten erneut senden — erzeugt ein neues Passwort (Hash kennt das alte nicht)."""
    err = _api_auth()
    if err:
        return err
    if not smtp_configured():
        return jsonify({'error': 'no smtp'}), 400
    users = load_users()
    user = next((u for u in users if u['id'] == uid), None)
    if user is None:
        return jsonify({'error': 'not found'}), 404
    password = generate_member_password()
    user['pw_hash'] = generate_password_hash(password)
    save_users(users)
    threading.Thread(target=send_welcome_email, args=(user, password), daemon=True).start()
    log.info("Zugangsdaten für '%s' erneut versendet (neues Passwort)", user['email'])
    return jsonify({'ok': True,
                    'no_url': not (load_site()['design'].get('public_url') or '').strip()})


@admin_app.route('/api/users/<uid>/files', methods=['GET', 'POST'])
def api_user_files(uid: str):
    err = _api_auth()
    if err:
        return err
    user = _admin_get_user(uid)
    if user is None:
        return jsonify({'error': 'not found'}), 404
    if not storage_available():
        return jsonify({'error': 'storage'}), 503
    d = user_dir(user)
    if request.method == 'POST':
        f = request.files.get('file')
        if not f or not f.filename:
            return jsonify({'error': 'no file'}), 400
        target = store_user_file(d, f)
        if target is None:
            return jsonify({'error': 'invalid name'}), 400
        if user_usage_bytes(user) > user.get('quota_mb', 500) * 1048576:
            target.unlink(missing_ok=True)
            return jsonify({'error': 'quota'}), 413
        log.info("Admin: Datei '%s' für '%s' hinterlegt", target.name, user['email'])
        return jsonify({'ok': True, 'name': target.name})
    files = []
    for f in sorted(d.iterdir()):
        if f.is_file():
            st = f.stat()
            files.append({'name': f.name, 'size': st.st_size,
                          'mtime': datetime.fromtimestamp(st.st_mtime).strftime('%d.%m.%Y %H:%M')})
    return jsonify({'files': files})


@admin_app.route('/api/users/<uid>/files/<path:name>', methods=['GET', 'DELETE'])
def api_user_file(uid: str, name: str):
    err = _api_auth()
    if err:
        return err
    user = _admin_get_user(uid)
    if user is None:
        return jsonify({'error': 'not found'}), 404
    if not storage_available():
        return jsonify({'error': 'storage'}), 503
    d = user_dir(user)
    if request.method == 'DELETE':
        safe = secure_filename(name)
        target = (d / safe).resolve()
        if safe and target.parent == d.resolve() and target.is_file():
            target.unlink()
            return jsonify({'ok': True})
        return jsonify({'error': 'not found'}), 404
    return _serve_user_file(d, name)


@admin_app.route('/api/storage', methods=['GET', 'POST'])
def api_storage():
    """Unterordner für Mitglieder-Dateien durchsuchen/festlegen (z. B. auf dem SMB-Share)."""
    err = _api_auth()
    if err:
        return err
    if not storage_available():
        return jsonify({'error': 'storage'}), 503
    base = USERFILES_BASE.resolve()
    if request.method == 'POST':
        sub = _clean_str((request.get_json(silent=True) or {}).get('subdir'), 300).strip('/')
        if sub:
            p = (base / sub).resolve()
            if not (p == base or base in p.parents) or not p.is_dir():
                return jsonify({'error': 'invalid dir'}), 400
        site = load_site()
        site['design']['storage_subdir'] = sub
        save_site(site)
        log.info("Mitglieder-Speicherort: %s", userfiles_root())
        return jsonify({'ok': True})
    rel = _clean_str(request.args.get('path') or '', 300).strip('/')
    cur = (base / rel).resolve() if rel else base
    if not (cur == base or base in cur.parents) or not cur.is_dir():
        return jsonify({'error': 'invalid dir'}), 400
    try:
        dirs = sorted(d.name for d in cur.iterdir() if d.is_dir())
    except OSError:
        dirs = []
    return jsonify({'base': str(base), 'path': rel, 'dirs': dirs, 'smb': SMB_MOUNTED,
                    'active': load_site()['design'].get('storage_subdir', '')})


@admin_app.route('/api/export')
def api_export():
    """Statischer HTML-Export der öffentlichen Seite (für z. B. GitHub Pages)."""
    err = _api_auth()
    if err:
        return err
    site = load_site()
    loc = _loc_factory('de')
    legal = site.get('legal', {})
    pages = {'index.html': '/?static=1'}
    for p in site['projects']:
        if _has_detail(p):
            pages[f"p/{p['id']}/index.html"] = f"/p/{p['id']}"
    posts = sorted_posts(site)
    if posts:
        pages['blog/index.html'] = '/blog'
        for po in posts:
            pages[f"blog/{po['id']}/index.html"] = f"/blog/{po['id']}"
    if loc(legal, 'impressum').strip():
        pages['impressum/index.html'] = '/impressum'
    if loc(legal, 'privacy').strip():
        pages['datenschutz/index.html'] = '/datenschutz'

    client = public_app.test_client()
    headers = {'Accept-Language': 'de', 'X-MyPage-Export': '1'}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for fname, path in pages.items():
            r = client.get(path, headers=headers)
            if r.status_code == 200:
                z.writestr(fname, r.data)
        for f in UPLOADS_DIR.iterdir():
            if f.is_file():
                z.write(f, 'uploads/' + f.name)
    buf.seek(0)
    return send_file(buf, mimetype='application/zip', as_attachment=True,
                     download_name=f'mypage-export-{date.today().isoformat()}.zip')


@admin_app.route('/api/upload', methods=['POST'])
def api_upload():
    err = _api_auth()
    if err:
        return err
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'error': 'no file'}), 400
    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXT:
        return jsonify({'error': 'file type not allowed'}), 400
    # Bilder verkleinern und als WebP speichern (GIFs unverändert, wegen Animation)
    if _HAS_PIL and ext != '.gif':
        try:
            img = Image.open(f.stream)
            img.thumbnail((1600, 1600))
            if img.mode not in ('RGB', 'RGBA'):
                img = img.convert('RGBA' if 'A' in img.getbands() else 'RGB')
            name = uuid.uuid4().hex + '.webp'
            target = (UPLOADS_DIR / name).resolve()
            if target.parent != UPLOADS_DIR.resolve():
                abort(400)
            img.save(target, 'WEBP', quality=82)
            return jsonify({'ok': True, 'url': '/uploads/' + name})
        except Exception as e:
            log.warning("Bild-Optimierung fehlgeschlagen, speichere Original: %s", e)
            f.stream.seek(0)
    name = uuid.uuid4().hex + ext
    target = (UPLOADS_DIR / name).resolve()
    if target.parent != UPLOADS_DIR.resolve():
        abort(400)
    f.save(target)
    return jsonify({'ok': True, 'url': '/uploads/' + name})


@admin_app.route('/api/github/repos')
def api_github_repos():
    err = _api_auth()
    if err:
        return err
    user = (request.args.get('user') or '').strip()
    if not _GH_USER_RE.match(user):
        return jsonify({'error': 'invalid username'}), 400
    try:
        return jsonify({'repos': fetch_github_repos(user)})
    except http.exceptions.RequestException:
        log.warning("GitHub-Repos für '%s' konnten nicht geladen werden", user)
        return jsonify({'error': 'github request failed'}), 502


@admin_app.route('/api/github/import', methods=['POST'])
def api_github_import():
    err = _api_auth()
    if err:
        return err
    raw = request.get_json(silent=True) or {}
    repos = raw.get('repos') or []
    import_readme = bool(raw.get('import_readme'))
    if not isinstance(repos, list):
        return jsonify({'error': 'invalid payload'}), 400
    site = load_site()
    existing = {p.get('repo_full_name') for p in site['projects'] if p.get('repo_full_name')}
    added = 0
    for repo in repos[:50]:
        if not isinstance(repo, dict):
            continue
        full_name = _clean_str(repo.get('full_name'), 150)
        if not full_name or not _GH_REPO_RE.match(full_name) or full_name in existing:
            continue
        site['projects'].append(_normalize_project({
            'long_de':        fetch_github_readme(full_name) if import_readme else '',
            'title':          repo.get('name') or full_name.split('/')[-1],
            'desc_de':        repo.get('description', ''),
            'desc_en':        repo.get('description', ''),
            'url':            repo.get('homepage', ''),
            'repo_url':       repo.get('html_url', ''),
            'repo_full_name': full_name,
            'language':       repo.get('language', ''),
            'stars':          repo.get('stars', 0),
            'tags':           repo.get('topics', []),
        }))
        existing.add(full_name)
        added += 1
    save_site(site)
    return jsonify({'ok': True, 'added': added})


@admin_app.route('/api/stats')
def api_stats():
    err = _api_auth()
    if err:
        return err
    stats = load_stats()
    today = date.today().isoformat()
    days = sorted(stats['days'].keys(), reverse=True)[:30]
    referrers, browsers, countries = aggregate_visits(stats.get('log', []))
    return jsonify({
        'total':         stats.get('total', 0),
        'total_uniques': total_uniques(stats),
        'today':         stats['days'].get(today, {'views': 0, 'uniques': 0}),
        'days':      [{'date': d, **stats['days'][d]} for d in days],
        'log':       list(reversed(stats.get('log', [])))[:100],
        'referrers': referrers,
        'browsers':  browsers,
        'countries': countries,
    })


@admin_app.route('/uploads/<path:filename>')
def admin_uploads(filename: str):
    err = _api_auth()
    if err:
        return err
    return send_from_directory(UPLOADS_DIR, filename, max_age=86400)


# ── Öffentliche Routen ────────────────────────────────────────────────────────

@public_app.route('/health')
def public_health():
    return 'OK', 200


@public_app.route('/set-lang/<lang>')
def public_set_lang(lang: str):
    cookie_lang = 'en' if lang == 'en' else 'de'
    resp = make_response(redirect(_safe_next(request.args.get('next', '/'))))
    resp.set_cookie('lang', cookie_lang, max_age=365 * 86400, samesite='Lax')
    return resp


@public_app.route('/uploads/<path:filename>')
def public_uploads(filename: str):
    return send_from_directory(UPLOADS_DIR, filename, max_age=86400)


def _base_url() -> str:
    site = load_site()
    return (site['design'].get('public_url') or request.url_root.rstrip('/')).rstrip('/')


@public_app.route('/favicon.ico')
def favicon():
    site = load_site()
    icon = site['design'].get('favicon') or site['profile'].get('avatar') or ''
    if icon.startswith('/uploads/'):
        return send_from_directory(UPLOADS_DIR, icon.removeprefix('/uploads/'), max_age=86400)
    if icon.startswith(('http://', 'https://')):
        return redirect(icon)
    return '', 204


@public_app.route('/robots.txt')
def robots():
    return (f'User-agent: *\nAllow: /\nSitemap: {_base_url()}/sitemap.xml\n',
            200, {'Content-Type': 'text/plain'})


@public_app.route('/sitemap.xml')
def sitemap():
    site = load_site()
    base = _base_url()
    urls = [base + '/']
    urls += [f"{base}/p/{p['id']}" for p in site['projects'] if _has_detail(p)]
    posts = sorted_posts(site)
    if posts:
        urls.append(base + '/blog')
        urls += [f"{base}/blog/{p['id']}" for p in posts]
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for u in urls:
        xml += f'  <url><loc>{u}</loc></url>\n'
    xml += '</urlset>\n'
    return xml, 200, {'Content-Type': 'application/xml'}


@public_app.errorhandler(404)
def not_found(_e):
    lang = detect_language(request)
    t = load_translations(lang)
    site = load_site()
    return render_template('404.html', t=t, lang=lang, site=site), 404


def _loc_factory(lang: str):
    def loc(obj: dict, key: str) -> str:
        if lang == 'en':
            return obj.get(f'{key}_en') or obj.get(f'{key}_de') or ''
        return obj.get(f'{key}_de') or obj.get(f'{key}_en') or ''
    return loc


def _maintenance_page(site: dict, lang: str):
    t = load_translations(lang)
    loc = _loc_factory(lang)
    text = loc(site.get('design', {}), 'maintenance_text') or t.get('maintenance_default', '')
    resp = make_response(render_template('maintenance.html', t=t, lang=lang, site=site,
                                         text_html=render_md(text)), 503)
    resp.headers['Retry-After'] = '3600'
    return resp


@public_app.route('/')
def public_index():
    count_visit(request)
    lang = detect_language(request)
    site = load_site()
    if site['design'].get('maintenance'):
        return _maintenance_page(site, lang)
    t = load_translations(lang)
    stats = load_stats()
    legal = site.get('legal', {})
    loc = _loc_factory(lang)
    email = site['profile'].get('email', '')
    email_parts = email.split('@', 1) if '@' in email else None
    projects = [dict(p, has_detail=_has_detail(p)) for p in site['projects']]
    static_export = bool(request.args.get('static'))
    return render_template('public.html', t=t, lang=lang, site=site, loc=loc,
                           projects=projects,
                           bio_html=render_md(loc(site['profile'], 'bio')),
                           email_parts=email_parts,
                           sections=site.get('sections', {}),
                           latest_posts=sorted_posts(site)[:3],
                           static_export=static_export,
                           contact_enabled=bool(site['design'].get('contact_enabled')) and not static_export,
                           total_visitors=total_uniques(stats),
                           has_impressum=bool(loc(legal, 'impressum').strip()),
                           has_privacy=bool(loc(legal, 'privacy').strip()),
                           has_members=bool(load_users()) and not static_export,
                           year=datetime.now(timezone.utc).year)


@public_app.route('/blog')
def blog_index():
    lang = detect_language(request)
    site = load_site()
    if site['design'].get('maintenance'):
        return _maintenance_page(site, lang)
    posts = sorted_posts(site)
    if not posts:
        abort(404)
    count_visit(request)
    t = load_translations(lang)
    loc = _loc_factory(lang)
    return render_template('blog.html', t=t, lang=lang, site=site, loc=loc,
                           posts=posts, year=datetime.now(timezone.utc).year)


@public_app.route('/blog/<pid>')
def blog_post(pid: str):
    lang = detect_language(request)
    site = load_site()
    if site['design'].get('maintenance'):
        return _maintenance_page(site, lang)
    post = next((p for p in site.get('posts', []) if p.get('id') == pid), None)
    if post is None:
        abort(404)
    count_visit(request)
    t = load_translations(lang)
    loc = _loc_factory(lang)
    return render_template('post.html', t=t, lang=lang, site=site, loc=loc, p=post,
                           text_html=render_md(loc(post, 'text')),
                           year=datetime.now(timezone.utc).year)


@public_app.route('/p/<pid>')
def project_detail(pid: str):
    lang = detect_language(request)
    site = load_site()
    if site['design'].get('maintenance'):
        return _maintenance_page(site, lang)
    proj = next((p for p in site['projects'] if p.get('id') == pid), None)
    if proj is None or not _has_detail(proj):
        abort(404)
    count_visit(request)
    t = load_translations(lang)
    loc = _loc_factory(lang)
    return render_template('project.html', t=t, lang=lang, site=site, loc=loc, p=proj,
                           long_html=render_md(loc(proj, 'long')),
                           year=datetime.now(timezone.utc).year)


# ── Mitglieder-Bereich (öffentliche App) ──────────────────────────────────────

def _member_page(member: dict | None, msg: str = ''):
    lang = detect_language(request)
    t = load_translations(lang)
    site = load_site()
    files = []
    used = quota = 0
    storage_down = member is not None and not storage_available()
    if member and not storage_down:
        quota = member.get('quota_mb', 500) * 1048576
        for f in sorted(user_dir(member).iterdir()):
            if f.is_file():
                st = f.stat()
                files.append({'name': f.name, 'size': st.st_size,
                              'mtime': datetime.fromtimestamp(st.st_mtime).strftime('%d.%m.%Y %H:%M')})
                used += st.st_size
    return render_template('member.html', t=t, lang=lang, site=site, member=member,
                           files=files, used=used, quota=quota, msg=msg,
                           storage_down=storage_down,
                           year=datetime.now(timezone.utc).year)


@public_app.route('/bereich')
def member_area():
    site = load_site()
    if site['design'].get('maintenance'):
        return _maintenance_page(site, detect_language(request))
    return _member_page(current_member(request), request.args.get('msg', ''))


@public_app.route('/bereich/login', methods=['POST'])
def member_login():
    ip = get_client_ip(request)
    if is_rate_limited(ip):
        return redirect('/bereich?msg=locked')
    email = (request.form.get('email') or '').strip().lower()
    password = request.form.get('password') or ''
    user = next((u for u in load_users() if u['email'] == email), None)
    if user is None or not check_password_hash(user['pw_hash'], password):
        record_failed_attempt(ip)
        return redirect('/bereich?msg=credentials')
    clear_failed_attempts(ip)
    token = secrets.token_hex(32)
    user_sessions[token] = [user['id'], time.time() + USER_SESSION_HOURS * 3600]
    save_user_sessions()
    resp = make_response(redirect('/bereich'))
    resp.set_cookie('usession', token, httponly=True, samesite='Lax',
                    max_age=USER_SESSION_HOURS * 3600)
    log.info("Mitglied '%s' angemeldet", email)
    return resp


@public_app.route('/bereich/logout')
def member_logout():
    token = request.cookies.get('usession')
    if token and token in user_sessions:
        del user_sessions[token]
        save_user_sessions()
    resp = make_response(redirect('/bereich'))
    resp.delete_cookie('usession')
    return resp


@public_app.route('/bereich/upload', methods=['POST'])
def member_upload():
    member = current_member(request)
    if member is None:
        abort(403)
    if not storage_available():
        return redirect('/bereich?msg=storage')
    f = request.files.get('file')
    if not f or not f.filename:
        return redirect('/bereich?msg=nofile')
    target = store_user_file(user_dir(member), f)
    if target is None:
        return redirect('/bereich?msg=nofile')
    quota = member.get('quota_mb', 500) * 1048576
    if user_usage_bytes(member) > quota:
        target.unlink(missing_ok=True)
        return redirect('/bereich?msg=quota')
    log.info("Mitglied '%s': Datei '%s' hochgeladen", member['email'], target.name)
    return redirect('/bereich?msg=uploaded')


def _serve_user_file(d: Path, name: str):
    """Datei-Download mit explizitem Pfad-Check und Fehler-Logging (SMB kann zicken)."""
    safe = secure_filename(name)
    target = (d / safe).resolve()
    if not safe or target.parent != d.resolve() or not target.is_file():
        abort(404)
    try:
        # as_attachment: hochgeladene Dateien werden nie im Browser ausgeführt;
        # conditional=False vermeidet Range/ETag-Sonderfälle auf CIFS-Mounts
        return send_file(target, as_attachment=True, download_name=safe, conditional=False)
    except Exception as e:
        log.error("Download '%s' fehlgeschlagen: %s", safe, e)
        abort(503)


@public_app.route('/bereich/dl/<path:name>')
def member_download(name: str):
    member = current_member(request)
    if member is None:
        abort(403)
    if not storage_available():
        return redirect('/bereich?msg=storage')
    return _serve_user_file(user_dir(member), name)


@public_app.route('/bereich/delete', methods=['POST'])
def member_delete():
    member = current_member(request)
    if member is None:
        abort(403)
    if not storage_available():
        return redirect('/bereich?msg=storage')
    name = secure_filename(request.form.get('name') or '')
    d = user_dir(member)
    target = (d / name).resolve()
    if name and target.parent == d.resolve() and target.is_file():
        target.unlink()
        log.info("Mitglied '%s': Datei '%s' gelöscht", member['email'], name)
    return redirect('/bereich')


@public_app.route('/contact', methods=['POST'])
def contact():
    site = load_site()
    if site['design'].get('maintenance') or not site['design'].get('contact_enabled'):
        return jsonify({'error': 'disabled'}), 403
    # Honeypot: Bots füllen das versteckte Feld aus → still verwerfen
    if (request.form.get('website') or '').strip():
        return jsonify({'ok': True})
    ip = get_client_ip(request)
    now = time.time()
    _contact_times[ip] = [x for x in _contact_times[ip] if now - x < 3600]
    if len(_contact_times[ip]) >= CONTACT_MAX_PER_HOUR:
        return jsonify({'error': 'rate limited'}), 429
    name    = _clean_str(request.form.get('name'), 80)
    email   = _clean_str(request.form.get('email'), 150)
    message = _clean_str(request.form.get('message'), 3000)
    if not name or not message:
        return jsonify({'error': 'missing fields'}), 400
    _contact_times[ip].append(now)
    msgs = load_messages()
    msgs.append({
        'id':    uuid.uuid4().hex[:12],
        'ts':    int(now),
        'name':  name,
        'email': email,
        'text':  message,
    })
    save_messages(msgs)
    def _notify():
        send_telegram(f"📨 MyPage — neue Nachricht von {name}"
                      + (f" ({email})" if email else "") + f":\n\n{message[:500]}")
        esc = html_mod.escape
        send_email(f'MyPage — neue Nachricht von {name}',
                   _email_html('📨 Neue Kontaktnachricht', [
                       f'<b>Von:</b> {esc(name)}' + (f' &lt;{esc(email)}&gt;' if email else ''),
                       f'<b>Nachricht:</b><br>{esc(message).replace(chr(10), "<br>")}',
                   ]))

    threading.Thread(target=_notify, daemon=True).start()
    log.info("Kontaktnachricht von '%s' gespeichert", name)
    return jsonify({'ok': True})


def _legal_page(kind: str):
    lang = detect_language(request)
    site = load_site()
    if site['design'].get('maintenance'):
        return _maintenance_page(site, lang)
    t = load_translations(lang)
    text = _loc_factory(lang)(site.get('legal', {}), kind)
    if not text.strip():
        abort(404)
    title = t.get('legal_' + kind, kind)
    return render_template('legal.html', t=t, lang=lang, site=site,
                           title=title, text=text,
                           year=datetime.now(timezone.utc).year)


@public_app.route('/impressum')
def impressum():
    return _legal_page('impressum')


@public_app.route('/datenschutz')
def datenschutz():
    return _legal_page('privacy')


# ── Main ──────────────────────────────────────────────────────────────────────

def _run_public():
    public_app.run(host='0.0.0.0', port=PUBLIC_PORT, debug=False, threaded=True)


if __name__ == '__main__':
    load_sessions()
    load_user_sessions()
    cfg = load_config()
    if cfg.get('password') in ('', 'changeme123'):
        log.warning("Standard-Passwort aktiv — bitte in den Add-on-Optionen ändern!")
    upload_max = max(1, min(4096, int(cfg.get('user_upload_max_mb') or 200)))
    public_app.config['MAX_CONTENT_LENGTH'] = upload_max * 1024 * 1024
    log.info("Mitglieder-Bereich: Speicher unter %s, Upload-Limit %d MB",
             userfiles_root(), upload_max)

    threading.Thread(target=_run_public, daemon=True).start()
    threading.Thread(target=refresh_project_stars, daemon=True).start()
    threading.Thread(target=_sensor_worker, daemon=True).start()
    threading.Thread(target=_geoip_worker, daemon=True).start()
    threading.Thread(target=_smb_watchdog, daemon=True).start()

    log.info("MyPage bereit — öffentlich: %d, Admin: %d", PUBLIC_PORT, ADMIN_PORT)
    admin_app.run(host='0.0.0.0', port=ADMIN_PORT, debug=False, threaded=True)
