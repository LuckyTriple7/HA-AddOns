#!/usr/bin/env python3
"""MyPage — Homepage-Baukasten für Home Assistant.

Zwei Server in einem Prozess:
  - Port 17760: öffentliche Homepage (kein Login, Besucherzähler)
  - Port 17761: Admin-Panel (Login + Brute-Force-Schutz, auch via HA Ingress)
"""
import errno
import hashlib
import hmac
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
    from PIL import Image, ImageDraw, ImageFont
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False
from flask import (Flask, render_template, request, redirect, url_for,
                   make_response, jsonify, abort, send_from_directory,
                   send_file)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename, safe_join
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
WM_CACHE_DIR = Path(_DATA) / 'wm_cache'
WM_CACHE_DIR.mkdir(parents=True, exist_ok=True)

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
# ReDoS-sicher: Domain-Komponenten ohne Punkt, kein katastrophales Backtracking
_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+$')


def safe_under(base: Path, *parts: str) -> Path | None:
    """Pfad sicher innerhalb von base zusammensetzen — None bei Traversal-Versuch.
    Nutzt werkzeug.safe_join (von CodeQL als Sanitizer anerkannt)."""
    joined = safe_join(str(base), *[p for p in parts if p])
    return Path(joined) if joined is not None else None

# Kontaktformular-Rate-Limit (IP → Zeitstempel)
_contact_times: dict[str, list[float]] = defaultdict(list)
CONTACT_MAX_PER_HOUR = 5
MESSAGES_MAX = 200

# Brute-Force-Schutz
_failed_attempts: dict[str, list[float]] = defaultdict(list)
_blocked_ips:     dict[str, float]       = {}
_failed_login_times: list[float]         = []   # alle Fehlversuche (rollierend, für 24h-Sensor)
RATE_LIMIT_MAX    = 5
RATE_LIMIT_WINDOW = 10 * 60
RATE_LIMIT_BLOCK  = 15 * 60


def failed_logins_24h() -> int:
    """Fehlgeschlagene Logins der letzten 24 Stunden (Admin + Mitglieder)."""
    cutoff = time.time() - 86400
    _failed_login_times[:] = [t for t in _failed_login_times if t >= cutoff]
    return len(_failed_login_times)

# Kontakt-Captcha: stateless signiertes Rechen-Captcha (Secret pro Laufzeit)
_captcha_secret: bytes = secrets.token_bytes(32)


def make_captcha() -> dict:
    """Erzeugt eine einfache Rechenaufgabe + signiertes Token (kein State nötig)."""
    a, b = secrets.randbelow(9) + 1, secrets.randbelow(9) + 1
    ts = int(time.time())
    payload = f'{a}.{b}.{ts}'
    sig = hmac.new(_captcha_secret, payload.encode(), hashlib.sha256).hexdigest()[:16]
    return {'question': f'{a} + {b}', 'token': f'{payload}.{sig}'}


def check_captcha(token: str, answer: str) -> bool:
    """Prüft Token-Signatur, Alter (≤10 min) und ob die Antwort stimmt."""
    try:
        a, b, ts, sig = (token or '').split('.')
        payload = f'{a}.{b}.{ts}'
        expected = hmac.new(_captcha_secret, payload.encode(), hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(sig, expected):
            return False
        if time.time() - int(ts) > 600:
            return False
        return int(answer) == int(a) + int(b)
    except (ValueError, AttributeError, TypeError):
        return False


# Besucherzähler — Tages-Dedup in-memory (Privacy: nur gesalzene Hashes)
_visit_salt:  str = secrets.token_hex(16)
_seen_today:  set[str] = set()
_seen_day:    str = ''

ALLOWED_UPLOAD_EXT = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
ALLOWED_FONT_EXT = {'.woff2', '.woff', '.ttf', '.otf'}
FONTS_DIR = Path(_BASE) / 'fonts'
STATS_KEEP_DAYS = 365

# Mitgelieferte Web-Fonts (selbst gehostet, kein externer Request):
# Wert → (CSS-Familienname, Fallback-Stack, [(weight, dateiname), …])
WEB_FONTS = {
    'inter':        ("Inter",        "sans-serif",  [(400, 'Inter-400.woff2'), (700, 'Inter-700.woff2')]),
    'poppins':      ("Poppins",      "sans-serif",  [(400, 'Poppins-400.woff2'), (700, 'Poppins-600.woff2')]),
    'montserrat':   ("Montserrat",   "sans-serif",  [(400, 'Montserrat-400.woff2'), (700, 'Montserrat-700.woff2')]),
    'lato':         ("Lato",         "sans-serif",  [(400, 'Lato-400.woff2'), (700, 'Lato-700.woff2')]),
    'merriweather': ("Merriweather", "serif",       [(400, 'Merriweather-400.woff2'), (700, 'Merriweather-700.woff2')]),
}
SYSTEM_FONTS = {
    'system':  "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    'classic': "'Helvetica Neue', Helvetica, Arial, sans-serif",
    'rounded': "'Trebuchet MS', 'Segoe UI', Verdana, sans-serif",
    'serif':   "Georgia, 'Times New Roman', serif",
    'mono':    "ui-monospace, 'Cascadia Code', Consolas, monospace",
}

DEFAULT_SITE = {
    'profile': {
        'name': '', 'tagline_de': '', 'tagline_en': '',
        'bio_de': '', 'bio_en': '', 'avatar': '',
        'github': '', 'email': '', 'links': [],
    },
    'projects': [],
    'design': {
        'accent': '#58a6ff', 'mode': 'dark', 'layout': 'cards',
        'show_counter': True, 'show_nav': True, 'public_url': '',
        'site_title': '', 'footer_text': '', 'favicon': '',
        'storage_subdir': '',
        'welcome_from': '',
        'contact_enabled': False,
        'maintenance': False,
        'maintenance_text_de': '', 'maintenance_text_en': '',
        'font': 'system', 'custom_css': '',
        'custom_font': '', 'custom_font_name': '',
        'support_url': '', 'support_label': '',
        'booking_url': '', 'booking_label': '',
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
        'links': [],
        'faq': [],
        'services': [],
        'testimonials': [],
        'team': [],
        'events': [],
        'location': {},
    },
    'albums': [],
    'album_protect': False,
    'watermark_text': '',
    'section_order': [
        'news', 'blog', 'services', 'projects', 'skills', 'testimonials',
        'photos', 'team', 'timeline', 'events', 'links', 'faq', 'location',
    ],
    'hidden_sections': [],
}

# Reihenfolge der Startseiten-Abschnitte (Hero immer zuerst, Kontakt immer zuletzt)
SECTION_KEYS = list(DEFAULT_SITE['section_order'])


def render_md(text: str) -> str:
    """Markdown → HTML (Inhalte stammen ausschließlich vom Admin)."""
    return md_lib.markdown(text or '', extensions=['nl2br', 'sane_lists'])


# Social-Plattform-Erkennung anhand des Hostnamens (für Auto-Icons bei Links)
_SOCIAL_HOSTS = {
    'github.com': 'github', 'gitlab.com': 'gitlab',
    'instagram.com': 'instagram', 'tiktok.com': 'tiktok',
    'facebook.com': 'facebook', 'fb.com': 'facebook',
    'linkedin.com': 'linkedin', 'youtube.com': 'youtube', 'youtu.be': 'youtube',
    'twitter.com': 'x', 'x.com': 'x',
    't.me': 'telegram', 'telegram.org': 'telegram',
    'discord.com': 'discord', 'discord.gg': 'discord', 'discordapp.com': 'discord',
    'wa.me': 'whatsapp', 'whatsapp.com': 'whatsapp',
    'bsky.app': 'bluesky', 'xing.com': 'xing',
    'twitch.tv': 'twitch', 'reddit.com': 'reddit',
    'mastodon.social': 'mastodon',
}


def link_platform(url: str) -> str:
    """Liefert den Plattform-Schlüssel für eine URL (exakter Host-/Subdomain-Vergleich)."""
    host = (urlparse(url or '').hostname or '').lower().removeprefix('www.')
    if not host:
        return ''
    for h, key in _SOCIAL_HOSTS.items():
        if host == h or host.endswith('.' + h):
            return key
    if 'mastodon' in host:  # verteilte Mastodon-Instanzen grob erkennen
        return 'mastodon'
    return ''


public_app.jinja_env.globals['link_platform'] = link_platform


# Support-Plattform-Erkennung (für den Spenden-/Support-Button)
_SUPPORT_HOSTS = {
    'buymeacoffee.com': 'buymeacoffee', 'ko-fi.com': 'kofi',
    'paypal.com': 'paypal', 'paypal.me': 'paypal',
    'patreon.com': 'patreon', 'liberapay.com': 'liberapay',
}


def support_platform(url: str) -> str:
    """Plattform-Schlüssel für den Support-Button (Default: 'heart')."""
    host = (urlparse(url or '').hostname or '').lower().removeprefix('www.')
    if host == 'github.com' and '/sponsors/' in (urlparse(url).path or ''):
        return 'githubsponsors'
    for h, key in _SUPPORT_HOSTS.items():
        if host == h or host.endswith('.' + h):
            return key
    return 'heart'


public_app.jinja_env.globals['support_platform'] = support_platform


def parse_video(url: str) -> tuple[str, str]:
    """Erkennt YouTube/Vimeo und liefert (Anbieter, datenschutzfreundliche Embed-URL)."""
    u = (url or '').strip()
    if not u:
        return '', ''
    p = urlparse(u)
    host = (p.hostname or '').lower().removeprefix('www.')
    vid = ''
    if host == 'youtu.be':
        vid = p.path.lstrip('/').split('/')[0]
        return ('youtube', f'https://www.youtube-nocookie.com/embed/{vid}') if vid else ('', '')
    if host == 'youtube.com' or host.endswith('.youtube.com'):
        if p.path == '/watch':
            from urllib.parse import parse_qs
            vid = (parse_qs(p.query).get('v') or [''])[0]
        elif p.path.startswith(('/embed/', '/shorts/')):
            vid = p.path.split('/')[2]
        if re.fullmatch(r'[A-Za-z0-9_-]{6,20}', vid):
            return 'youtube', f'https://www.youtube-nocookie.com/embed/{vid}'
        return '', ''
    if host == 'vimeo.com' or host.endswith('.vimeo.com'):
        vid = next((seg for seg in p.path.split('/') if seg.isdigit()), '')
        return ('vimeo', f'https://player.vimeo.com/video/{vid}') if vid else ('', '')
    return '', ''


public_app.jinja_env.globals['parse_video'] = parse_video
public_app.jinja_env.globals['render_md'] = render_md

# Admin-App rendert öffentliche Templates (z. B. Blog-Vorschau) — dieselben Globals bereitstellen
admin_app.jinja_env.globals['parse_video'] = parse_video
admin_app.jinja_env.globals['render_md'] = render_md
admin_app.jinja_env.globals['link_platform'] = link_platform
admin_app.jinja_env.globals['support_platform'] = support_platform


def font_css(design: dict) -> tuple[str, str]:
    """Liefert (font-family-Stack, @font-face-CSS) für die gewählte Schrift."""
    f = design.get('font') or 'system'
    if f in SYSTEM_FONTS:
        return SYSTEM_FONTS[f], ''
    if f in WEB_FONTS:
        family, fallback, files = WEB_FONTS[f]
        faces = ''
        for weight, fn in files:
            faces += (f"@font-face{{font-family:'{family}';font-style:normal;"
                      f"font-weight:{weight};font-display:swap;"
                      f"src:url('/fonts/{fn}') format('woff2');}}\n")
        return f"'{family}', {fallback}", faces
    if f == 'custom' and design.get('custom_font'):
        url = design['custom_font']
        face = (f"@font-face{{font-family:'CustomFont';font-display:swap;"
                f"src:url('{url}');}}\n")
        return "'CustomFont', sans-serif", face
    return SYSTEM_FONTS['system'], ''


@public_app.context_processor
def _inject_font():
    """Stellt die gewählte Schrift allen öffentlichen Templates bereit (nicht nur der Startseite)."""
    try:
        fam, faces = font_css(load_site()['design'])
    except Exception:
        fam, faces = SYSTEM_FONTS['system'], ''
    return {'font_family': fam, 'font_faces': faces}


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


def send_email(subject: str, html_body: str, to: str | None = None,
               from_addr: str | None = None) -> None:
    cfg      = load_config()
    host     = (cfg.get('smtp_host') or '').strip()
    port     = int(cfg.get('smtp_port') or 587)
    user     = (cfg.get('smtp_user') or '').strip()
    password = (cfg.get('smtp_password') or '').strip()
    to       = (to or cfg.get('smtp_to') or '').strip()
    use_tls  = bool(cfg.get('smtp_tls', True))
    # Absender: expliziter from_addr (z. B. noreply-Alias) > globaler smtp_from > Login-User
    sender   = (from_addr or cfg.get('smtp_from') or user or f'mypage@{host}').strip()
    if not host or not to:
        return
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = sender
        msg['To']      = to
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        # Envelope-Sender = sichtbarer Absender (Alias muss am Postfach erlaubt sein)
        if use_tls:
            with smtplib.SMTP(host, port, timeout=15) as s:
                s.ehlo()
                s.starttls()
                s.ehlo()
                if user and password:
                    s.login(user, password)
                s.sendmail(sender, [to], msg.as_string())
        else:
            with smtplib.SMTP_SSL(host, port, timeout=15) as s:
                if user and password:
                    s.login(user, password)
                s.sendmail(sender, [to], msg.as_string())
        log.info("E-Mail an '%s' gesendet (Absender: %s)", to, sender)
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
    _failed_login_times.append(now)
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


def visit_log_max() -> int:
    """Konfigurierbares Limit für das Besucher-Log (Option visit_log_max)."""
    try:
        return max(50, min(10000, int(load_config().get('visit_log_max') or 500)))
    except (TypeError, ValueError):
        return 500


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
    del visit_log[:-visit_log_max()]

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


def _own_domain() -> str:
    """Eigene Basis-Domain (ohne www) — interne Navigation zählt nicht als Referrer."""
    host = urlparse(load_site()['design'].get('public_url') or '').netloc.lower()
    return host.split(':')[0].removeprefix('www.')


def _is_own_host(host: str, own: str) -> bool:
    """Exakter Vergleich oder echte Subdomain (Suffix mit Punkt) — nie Substring."""
    if not own or not host:
        return False
    host = host.split(':')[0]
    return host == own or host.endswith('.' + own)


def _is_local_host(host: str) -> bool:
    """True für private/lokale Hosts (interne Aufrufe), die als Referrer keinen Sinn ergeben."""
    h = host.split(':')[0].strip().lower()
    if not h:
        return True
    if h == 'localhost' or h.endswith(('.local', '.lan', '.internal', '.home', '.home.arpa')):
        return True
    try:
        ip = ipaddress.ip_address(h)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
    except ValueError:
        return '.' not in h   # bloßer Hostname ohne Punkt (z. B. "homeassistant") = lokal


def aggregate_visits(visit_log: list) -> tuple[list, list, list]:
    """Top-Referrer, Browser- und Länder-Verteilung aus dem Besucher-Log."""
    referrers: dict[str, int] = {}
    browsers:  dict[str, int] = {}
    countries: dict[str, int] = {}
    own = _own_domain()
    for v in visit_log:
        if v.get('bot'):
            continue
        host = urlparse(v.get('ref') or '').netloc.lower()
        if host and not _is_own_host(host, own) and not _is_local_host(host):
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
    Bewusst kein Fallback auf lokalen Speicher — das würde Datei-Chaos geben.
    Prüft den aktiven Ordner (nicht nur die Mount-Wurzel), um stale Handles zu erkennen."""
    if not SMB_MOUNTED:
        return True
    try:
        if not os.path.ismount(str(USERFILES_BASE)):
            return False
        os.listdir(userfiles_root())
        return True
    except OSError:
        return False


def drop_fs_caches() -> bool:
    """Dentry-/Inode-Cache verwerfen — entwertet stale SMB-Handles ohne Remount.
    Uploads (neue Dateien) funktionieren auch bei stale Cache, nur Reads alter
    Dateien hängen — oft reicht das hier schon."""
    try:
        with open('/proc/sys/vm/drop_caches', 'w') as f:
            f.write('2\n')
        return True
    except OSError:
        return False


_remount_lock = threading.Lock()
# noserverino: FritzBox liefert instabile Inode-Nummern → Client vergibt eigene
# (DER Fix gegen ESTALE direkt nach Uploads); cache=none/actimeo=1 als Gürtel+Hosenträger
SMB_MOUNT_OPTS = ('vers=3.0,uid=0,gid=0,file_mode=0755,dir_mode=0755,'
                  'noperm,sec=ntlmssp,nodfs,iocharset=utf8,soft,'
                  'noserverino,cache=none,actimeo=1')


def remount_smb() -> bool:
    """SMB-Mount erneuern (FritzBox trennt inaktive Verbindungen → stale handles)."""
    mountpoint = os.environ.get('MYPAGE_USERFILES', '')
    if not mountpoint:
        return False
    with _remount_lock:
        try:
            cfg = load_config()
            server = (cfg.get('smb_server') or '').strip()
            share  = (cfg.get('smb_share') or '').strip()
            if not server or not share:
                return False
            # force + lazy: harte Trennung, damit keine stale Superblocks übrig bleiben
            subprocess.run(['umount', '-f', '-l', mountpoint], capture_output=True, timeout=30)
            user = (cfg.get('smb_user') or '').strip()
            if user:
                # Zugangsdaten nie auf Platte (CodeQL #139): anonymes Tempfile, mount
                # liest es über den vererbten Filedescriptor (pass_fds ist Pflicht!)
                with tempfile.TemporaryFile(mode='w+') as cred:
                    cred.write(f"username={user}\npassword={cfg.get('smb_password') or ''}\n")
                    cred.flush()
                    cred.seek(0)
                    fd = cred.fileno()
                    os.set_inheritable(fd, True)
                    r = subprocess.run(['mount', '-t', 'cifs', f'//{server}/{share}', mountpoint,
                                        '-o', f'{SMB_MOUNT_OPTS},credentials=/proc/self/fd/{fd}'],
                                       capture_output=True, text=True, timeout=60,
                                       pass_fds=(fd,))
            else:
                r = subprocess.run(['mount', '-t', 'cifs', f'//{server}/{share}', mountpoint,
                                    '-o', f'{SMB_MOUNT_OPTS},guest'],
                                   capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                log.warning("SMB-Remount fehlgeschlagen: %s", (r.stderr or '').strip()[:200])
                return False
            # Erst als Erfolg melden, wenn die neue Session wirklich antwortet
            for _ in range(6):
                try:
                    os.listdir(mountpoint)
                    log.info("SMB-Mount erneuert und verifiziert")
                    return True
                except OSError:
                    time.sleep(0.5)
            log.warning("SMB-Remount: Mount ok, aber Share antwortet noch nicht")
            return False
        except Exception as e:
            log.warning("SMB-Remount-Fehler: %s", e)
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


_UID_RE = re.compile(r'^[a-f0-9]{6,32}$')


def user_dir(user: dict) -> Path:
    uid = user['id']
    if not _UID_RE.match(uid):
        abort(400)
    d = safe_under(userfiles_root(), uid)
    if d is None:
        abort(400)
    d.mkdir(parents=True, exist_ok=True)
    return d


def store_user_file(d: Path, f) -> Path | None:
    """Upload sicher in Benutzerordner speichern (Namens-Kollisionen durchnummerieren)."""
    name = secure_filename(f.filename or '')
    if not name:
        return None
    target = safe_under(d, name)
    if target is None:
        return None
    base, ext = os.path.splitext(name)
    n = 1
    while target.exists():
        # Unterstrich statt Klammern: übersteht secure_filename beim Download/Löschen
        nxt = safe_under(d, f'{base}_{n}{ext}')
        if nxt is None:
            return None
        target = nxt
        n += 1
    f.save(target)
    return target


def user_usage_bytes(user: dict) -> int:
    return sum(f.stat().st_size for f in user_dir(user).iterdir() if f.is_file())


def invalidate_user_sessions(uid: str) -> int:
    """Beendet alle aktiven Sitzungen eines Benutzers (z. B. nach Passwortwechsel)."""
    tokens = [t for t, v in user_sessions.items() if v[0] == uid]
    for t in tokens:
        del user_sessions[t]
    if tokens:
        save_user_sessions()
    return len(tokens)


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


def user_journal_max() -> int:
    """Konfigurierbares Limit für das Journal pro Benutzer (Option user_journal_max)."""
    try:
        return max(20, min(1000, int(load_config().get('user_journal_max') or 100)))
    except (TypeError, ValueError):
        return 100


def log_user_event(uid: str, action: str, detail: str = '', ip: str = '') -> None:
    """Journal-Eintrag pro Benutzer (Login, Upload, Download, Löschen, …)."""
    users = load_users()
    user = next((u for u in users if u['id'] == uid), None)
    if user is None:
        return
    entry = {'ts': int(time.time()), 'action': action, 'detail': detail[:150], 'ip': ip}
    journal = user.setdefault('journal', [])
    journal.append(entry)
    del journal[:-user_journal_max()]
    if action == 'login':
        user['last_login'] = {'ts': entry['ts'], 'ip': ip}
    save_users(users)


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
               to=user['email'],
               from_addr=(site['design'].get('welcome_from') or '').strip() or None)


def _smb_watchdog() -> None:
    """Stellt den SMB-Mount nach NAS-/FritzBox-Neustart automatisch wieder her."""
    if not os.environ.get('MYPAGE_USERFILES', ''):
        return
    while True:
        time.sleep(60)
        try:
            if storage_available():
                continue
            log.warning("SMB-Mount nicht verfügbar — versuche Remount ...")
            remount_smb()
        except Exception as e:
            log.warning("SMB-Watchdog-Fehler: %s", e)


# ── Home-Assistant-Sensoren ───────────────────────────────────────────────────

SUPERVISOR_TOKEN = os.environ.get('SUPERVISOR_TOKEN', '')


def push_ha_sensors() -> None:
    """Meldet Besucherzahlen als Sensoren an Home Assistant (Supervisor-API)."""
    if not SUPERVISOR_TOKEN:
        return
    stats = load_stats()
    site = load_site()
    today = stats['days'].get(date.today().isoformat(), {'views': 0, 'uniques': 0})
    storage_ok = storage_available()
    # Belegter Speicher aller Mitglieder-Dateien (MB) — bei SMB-Ausfall 0
    user_mb = 0.0
    if storage_ok:
        try:
            user_mb = round(sum(user_usage_bytes(u) for u in load_users()) / 1048576, 1)
        except OSError:
            user_mb = 0.0
    sensors = [
        ('mypage_views_total',    stats.get('total', 0), 'MyPage Aufrufe gesamt',  'mdi:counter',       'Aufrufe'),
        ('mypage_visitors_total', total_uniques(stats),  'MyPage Besucher gesamt', 'mdi:account-group', 'Besucher'),
        ('mypage_views_today',    today['views'],        'MyPage Aufrufe heute',   'mdi:eye',           'Aufrufe'),
        ('mypage_visitors_today', today['uniques'],      'MyPage Besucher heute',  'mdi:account',       'Besucher'),
        ('mypage_user_storage',   user_mb,               'MyPage Speicher Benutzerdateien', 'mdi:harddisk', 'MB'),
        ('mypage_failed_logins',  failed_logins_24h(),   'MyPage Fehllogins (24h)', 'mdi:lock-alert',   'Versuche'),
        ('mypage_messages',       len(load_messages()),  'MyPage Kontaktnachrichten', 'mdi:email',      'Nachrichten'),
        ('mypage_members',        len(load_users()),     'MyPage Benutzer',         'mdi:account-multiple', 'Benutzer'),
        ('mypage_projects',       len(site.get('projects', [])), 'MyPage Projekte',  'mdi:folder-multiple', 'Projekte'),
        ('mypage_posts',          len(site.get('posts', [])),    'MyPage Blog-Beiträge', 'mdi:post',     'Beiträge'),
        ('mypage_albums',         len(site.get('albums', [])),   'MyPage Fotoalben', 'mdi:image-multiple', 'Alben'),
    ]
    # Binary-Sensoren (state on/off)
    binary = [
        ('mypage_storage_online', storage_ok,  'MyPage Speicher erreichbar', 'mdi:nas',      'connectivity'),
        ('mypage_maintenance',    bool(site['design'].get('maintenance')), 'MyPage Wartungsmodus', 'mdi:wrench', None),
    ]
    headers = {'Authorization': f'Bearer {SUPERVISOR_TOKEN}'}
    try:
        for sid, state, name, icon, unit in sensors:
            http.post(f'http://supervisor/core/api/states/sensor.{sid}',
                      headers=headers, timeout=10,
                      json={'state': state,
                            'attributes': {'friendly_name': name, 'icon': icon,
                                           'unit_of_measurement': unit}})
        for bid, on, name, icon, dclass in binary:
            attrs = {'friendly_name': name, 'icon': icon}
            if dclass:
                attrs['device_class'] = dclass
            http.post(f'http://supervisor/core/api/states/binary_sensor.{bid}',
                      headers=headers, timeout=10,
                      json={'state': 'on' if on else 'off', 'attributes': attrs})
    except Exception as e:
        log.warning("HA-Sensoren konnten nicht aktualisiert werden: %s", e)


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
    p['date']      = _clean_str(raw.get('date'), 10)
    p['title_de']  = _clean_str(raw.get('title_de'), 150)
    p['title_en']  = _clean_str(raw.get('title_en'), 150)
    p['text_de']   = _clean_str(raw.get('text_de'), 30000)
    p['text_en']   = _clean_str(raw.get('text_en'), 30000)
    p['image']     = _clean_str(raw.get('image'), 500)
    p['video']     = _clean_str(raw.get('video'), 500)
    gallery = raw.get('gallery') or []
    if isinstance(gallery, list):
        p['gallery'] = [_clean_str(g, 500) for g in gallery if _clean_str(g, 500)][:30]
    else:
        p.setdefault('gallery', [])
    p['published'] = bool(raw.get('published', True))
    return p


def post_status(p: dict) -> str:
    """'draft' (Entwurf), 'scheduled' (Datum in Zukunft) oder 'published'."""
    if not p.get('published', True):
        return 'draft'
    if (p.get('date') or '') > date.today().isoformat():
        return 'scheduled'
    return 'published'


def post_visible(p: dict) -> bool:
    """Öffentlich sichtbar: veröffentlicht und Datum nicht in der Zukunft."""
    return post_status(p) == 'published'


def project_visible(p: dict) -> bool:
    return bool(p.get('published', True))


def sorted_posts(site: dict, public_only: bool = False) -> list:
    posts = sorted(site.get('posts', []), key=lambda p: p.get('date', ''), reverse=True)
    return [p for p in posts if post_visible(p)] if public_only else posts


def _albums_for_public(site: dict) -> list:
    """Alben mit Bildern; Bild-URLs auf die /album-img/-Route umgeschrieben
    (liefert je nach Einstellung Original oder Wasserzeichen-Version)."""
    out = []
    for a in site.get('albums', []):
        imgs = a.get('images') or []
        if not imgs:
            continue
        mapped = [('/album-img/' + u.removeprefix('/uploads/')) if u.startswith('/uploads/') else u
                  for u in imgs]
        out.append({**a, 'images': mapped})
    return out


def _normalize_album(raw: dict, existing: dict | None = None) -> dict:
    a = existing or {'id': uuid.uuid4().hex[:12]}
    a['title_de'] = _clean_str(raw.get('title_de'), 120)
    a['title_en'] = _clean_str(raw.get('title_en'), 120)
    a['desc_de']  = _clean_str(raw.get('desc_de'), 1000)
    a['desc_en']  = _clean_str(raw.get('desc_en'), 1000)
    images = raw.get('images') or []
    if isinstance(images, list):
        a['images'] = [_clean_str(g, 500) for g in images if _clean_str(g, 500)][:200]
    else:
        a.setdefault('images', [])
    return a


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
    p['video'] = _clean_str(raw.get('video'), 500)
    p['published'] = bool(raw.get('published', True))
    return p


def _has_detail(p: dict) -> bool:
    return bool((p.get('long_de') or p.get('long_en') or '').strip()
                or p.get('gallery') or p.get('video'))


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


def _mymemory_translate(text: str, src: str, dst: str) -> str:
    """Übersetzt einen kurzen Textabschnitt über MyMemory (kostenlos, kein Key)."""
    email = (load_config().get('translate_email') or '').strip()

    def _call(with_email: bool) -> dict:
        params = {'q': text, 'langpair': f'{src}|{dst}'}
        if with_email and email:
            params['de'] = email
        r = http.get('https://api.mymemory.translated.net/get', params=params, timeout=15)
        r.raise_for_status()
        return r.json()

    data = _call(bool(email))
    # Ungültige translate_email → MyMemory antwortet 403 INVALID EMAIL.
    # Dann ohne E-Mail (anonymes Limit) erneut versuchen, statt komplett zu scheitern.
    if (data.get('responseStatus') != 200 and email
            and 'EMAIL' in str(data.get('responseDetails', '')).upper()):
        log.warning("translate_email ungültig ('%s') — nutze anonymes Übersetzungs-Limit", email)
        data = _call(False)
    if data.get('responseStatus') == 200:
        return (data.get('responseData') or {}).get('translatedText', '')
    raise ValueError(data.get('responseDetails') or 'translation failed')


def _split_for_translation(text: str, limit: int = 450) -> list[str]:
    """Text an Zeilen-/Satzgrenzen in Stücke ≤ limit teilen (MyMemory-Limit)."""
    chunks, buf = [], ''
    # zuerst nach Zeilen, dann zu lange Zeilen nach Sätzen
    for line in text.split('\n'):
        if len(line) > limit:
            for part in re.split(r'(?<=[.!?]) ', line):
                while len(part) > limit:  # Notfall: hart schneiden
                    chunks.append(part[:limit]); part = part[limit:]
                if len(buf) + len(part) + 1 > limit:
                    chunks.append(buf); buf = part
                else:
                    buf = f'{buf} {part}'.strip()
        else:
            if len(buf) + len(line) + 1 > limit:
                chunks.append(buf); buf = line
            else:
                buf = f'{buf}\n{line}' if buf else line
    if buf:
        chunks.append(buf)
    return chunks or ['']


@admin_app.route('/api/translate', methods=['POST'])
def api_translate():
    err = _api_auth()
    if err:
        return err
    raw = request.get_json(silent=True) or {}
    text = _clean_str(raw.get('text'), 20000)
    src = raw.get('from') if raw.get('from') in ('de', 'en') else 'de'
    dst = raw.get('to') if raw.get('to') in ('de', 'en') else 'en'
    if not text.strip() or src == dst:
        return jsonify({'text': text})
    try:
        out = []
        for chunk in _split_for_translation(text):
            out.append(_mymemory_translate(chunk, src, dst) if chunk.strip() else chunk)
            time.sleep(0.3)  # höflich zur kostenlosen API
        return jsonify({'text': '\n'.join(out) if '\n' in text else ' '.join(out).strip()})
    except Exception as e:
        log.warning("Übersetzung fehlgeschlagen: %s", e)
        return jsonify({'error': 'translation failed'}), 502


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
    if raw.get('font') in (set(SYSTEM_FONTS) | set(WEB_FONTS) | {'custom'}):
        d['font'] = raw['font']
    if 'custom_css' in raw:
        # '<' komplett entfernen — in CSS nie nötig, macht jeden Tag-Ausbruch
        # aus dem <style>-Block unmöglich (auch </style><script>)
        d['custom_css'] = _clean_str(raw['custom_css'], 10000).replace('<', '')
    if 'public_url' in raw:
        url = _clean_str(raw['public_url'], 200).rstrip('/')
        d['public_url'] = url if url.startswith(('http://', 'https://')) or not url else ''
    if 'support_url' in raw:
        su = _clean_str(raw['support_url'], 500)
        d['support_url'] = su if su.startswith(('http://', 'https://')) or not su else ''
    if 'support_label' in raw:
        d['support_label'] = _clean_str(raw['support_label'], 40)
    if 'booking_url' in raw:
        bu = _clean_str(raw['booking_url'], 500)
        d['booking_url'] = bu if bu.startswith(('http://', 'https://')) or not bu else ''
    if 'booking_label' in raw:
        d['booking_label'] = _clean_str(raw['booking_label'], 40)
    for flag in ('show_counter', 'show_nav', 'contact_enabled', 'maintenance'):
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
    if isinstance(raw.get('links'), list):
        sec['links'] = [{
            'title_de': _clean_str(e.get('title_de'), 120),
            'title_en': _clean_str(e.get('title_en'), 120),
            'desc_de':  _clean_str(e.get('desc_de'), 300),
            'desc_en':  _clean_str(e.get('desc_en'), 300),
            'url':      _clean_str(e.get('url'), 500),
        } for e in raw['links'][:100]
            if isinstance(e, dict) and _clean_str(e.get('url'), 500).startswith(('http://', 'https://'))]
    if isinstance(raw.get('faq'), list):
        sec['faq'] = [{
            'q_de': _clean_str(e.get('q_de'), 300),
            'q_en': _clean_str(e.get('q_en'), 300),
            'a_de': _clean_str(e.get('a_de'), 3000),
            'a_en': _clean_str(e.get('a_en'), 3000),
        } for e in raw['faq'][:50]
            if isinstance(e, dict) and (_clean_str(e.get('q_de'), 300) or _clean_str(e.get('q_en'), 300))]
    if isinstance(raw.get('services'), list):
        sec['services'] = [{
            'icon':     _clean_str(e.get('icon'), 8),
            'title_de': _clean_str(e.get('title_de'), 120),
            'title_en': _clean_str(e.get('title_en'), 120),
            'desc_de':  _clean_str(e.get('desc_de'), 600),
            'desc_en':  _clean_str(e.get('desc_en'), 600),
            'price':    _clean_str(e.get('price'), 60),
        } for e in raw['services'][:40]
            if isinstance(e, dict) and (_clean_str(e.get('title_de'), 120) or _clean_str(e.get('title_en'), 120))]
    if isinstance(raw.get('testimonials'), list):
        sec['testimonials'] = [{
            'quote_de': _clean_str(e.get('quote_de'), 800),
            'quote_en': _clean_str(e.get('quote_en'), 800),
            'name':     _clean_str(e.get('name'), 120),
            'role_de':  _clean_str(e.get('role_de'), 120),
            'role_en':  _clean_str(e.get('role_en'), 120),
            'avatar':   _clean_str(e.get('avatar'), 500),
        } for e in raw['testimonials'][:40]
            if isinstance(e, dict) and (_clean_str(e.get('quote_de'), 800) or _clean_str(e.get('quote_en'), 800))]
    if isinstance(raw.get('team'), list):
        sec['team'] = [{
            'name':    _clean_str(e.get('name'), 120),
            'role_de': _clean_str(e.get('role_de'), 120),
            'role_en': _clean_str(e.get('role_en'), 120),
            'photo':   _clean_str(e.get('photo'), 500),
            'bio_de':  _clean_str(e.get('bio_de'), 600),
            'bio_en':  _clean_str(e.get('bio_en'), 600),
        } for e in raw['team'][:40]
            if isinstance(e, dict) and _clean_str(e.get('name'), 120)]
    if isinstance(raw.get('events'), list):
        sec['events'] = [{
            'date':     _clean_str(e.get('date'), 30),
            'title_de': _clean_str(e.get('title_de'), 160),
            'title_en': _clean_str(e.get('title_en'), 160),
            'location': _clean_str(e.get('location'), 160),
            'url':      _clean_str(e.get('url'), 500) if _clean_str(e.get('url'), 500).startswith(('http://', 'https://')) else '',
        } for e in raw['events'][:60]
            if isinstance(e, dict) and (_clean_str(e.get('title_de'), 160) or _clean_str(e.get('title_en'), 160))]
    if isinstance(raw.get('location'), dict):
        L = raw['location']
        def _coord(v):
            try:
                return f"{float(str(v).strip()):.6f}"
            except (ValueError, TypeError):
                return ''
        sec['location'] = {
            'name':     _clean_str(L.get('name'), 120),
            'address':  _clean_str(L.get('address'), 200),
            'hours_de': _clean_str(L.get('hours_de'), 500),
            'hours_en': _clean_str(L.get('hours_en'), 500),
            'lat':      _coord(L.get('lat')),
            'lng':      _coord(L.get('lng')),
            'show_map': bool(L.get('show_map')),
        }
    if isinstance(raw.get('section_order'), list):
        order = [k for k in raw['section_order'] if isinstance(k, str) and k in SECTION_KEYS]
        site['section_order'] = order + [k for k in SECTION_KEYS if k not in order]
    if isinstance(raw.get('hidden_sections'), list):
        site['hidden_sections'] = [k for k in raw['hidden_sections'] if isinstance(k, str) and k in SECTION_KEYS]
    if 'album_protect' in raw:
        site['album_protect'] = bool(raw['album_protect'])
    if 'watermark_text' in raw:
        site['watermark_text'] = _clean_str(raw['watermark_text'], 80)
    save_site(site)
    return jsonify({'ok': True})


@admin_app.route('/api/albums', methods=['POST'])
def api_album_create():
    err = _api_auth()
    if err:
        return err
    raw = request.get_json(silent=True) or {}
    if not (_clean_str(raw.get('title_de'), 120) or _clean_str(raw.get('title_en'), 120)):
        return jsonify({'error': 'title required'}), 400
    site = load_site()
    site.setdefault('albums', []).append(_normalize_album(raw))
    save_site(site)
    return jsonify({'ok': True})


@admin_app.route('/api/albums/<aid>', methods=['PUT', 'DELETE'])
def api_album_edit(aid: str):
    err = _api_auth()
    if err:
        return err
    site = load_site()
    albums = site.setdefault('albums', [])
    idx = next((i for i, a in enumerate(albums) if a.get('id') == aid), None)
    if idx is None:
        return jsonify({'error': 'not found'}), 404
    if request.method == 'DELETE':
        albums.pop(idx)
    else:
        albums[idx] = _normalize_album(request.get_json(silent=True) or {}, albums[idx])
    save_site(site)
    return jsonify({'ok': True})


@admin_app.route('/api/albums/<aid>/move', methods=['POST'])
def api_album_move(aid: str):
    err = _api_auth()
    if err:
        return err
    direction = (request.get_json(silent=True) or {}).get('dir', '')
    site = load_site()
    albums = site.setdefault('albums', [])
    idx = next((i for i, a in enumerate(albums) if a.get('id') == aid), None)
    if idx is None:
        return jsonify({'error': 'not found'}), 404
    new_idx = idx - 1 if direction == 'up' else idx + 1
    if 0 <= new_idx < len(albums):
        albums[idx], albums[new_idx] = albums[new_idx], albums[idx]
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
        for name in ('site.json', 'stats.json', 'messages.json', 'users.json'):
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
                # Nur bekannte Dateien zulassen; Zielpfad immer per safe_join
                # gegen Zip-Slip absichern
                if member in ('site.json', 'stats.json', 'messages.json', 'users.json'):
                    target = safe_under(Path(_DATA), member)
                elif member.startswith('uploads/'):
                    name = secure_filename(Path(member).name)
                    if not name or Path(name).suffix.lower() not in ALLOWED_UPLOAD_EXT:
                        continue
                    target = safe_under(UPLOADS_DIR, name)
                else:
                    continue
                if target is None:
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
                    'created': u.get('created', ''),
                    'last_login': u.get('last_login'),
                    'login_message': u.get('login_message', '')})
    return jsonify({'users': out, 'smtp': smtp_configured(),
                    'storage': str(userfiles_root()) if storage_ok else '',
                    'smb': SMB_MOUNTED, 'storage_ok': storage_ok,
                    'welcome_from': load_site()['design'].get('welcome_from', '')})


@admin_app.route('/api/member-settings', methods=['POST'])
def api_member_settings():
    """Globale Mitglieder-Einstellungen (Absender-Alias für Zugangs-Mails)."""
    err = _api_auth()
    if err:
        return err
    raw = request.get_json(silent=True) or {}
    wf = _clean_str(raw.get('welcome_from'), 150)
    if wf and not _EMAIL_RE.match(wf):
        return jsonify({'error': 'invalid email'}), 400
    site = load_site()
    site['design']['welcome_from'] = wf
    save_site(site)
    log.info("Willkommens-Absender gesetzt: %s", wf or '(Standard)')
    return jsonify({'ok': True})


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
        invalidate_user_sessions(uid)
        shutil.rmtree(user_dir(user), ignore_errors=True)
        log.info("Benutzer '%s' gelöscht", user['email'])
        return jsonify({'ok': True})
    raw = request.get_json(silent=True) or {}
    mail_sent = False
    if 'quota_mb' in raw:
        user['quota_mb'] = max(1, min(100000, int(raw.get('quota_mb') or 500)))
    if 'login_message' in raw:
        user['login_message'] = _clean_str(raw.get('login_message'), 2000)
    password = str(raw.get('password') or '')
    if password:
        if len(password) < 8:
            return jsonify({'error': 'password too short'}), 400
        user['pw_hash'] = generate_password_hash(password)
        # Passwortwechsel beendet alle bestehenden Sitzungen → Neuanmeldung nötig
        ended = invalidate_user_sessions(uid)
        if ended:
            log.info("Passwortwechsel: %d Sitzung(en) von '%s' beendet", ended, user['email'])
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
    invalidate_user_sessions(uid)  # altes Passwort → bestehende Sitzungen kappen
    log_user_event(uid, 'pw_reset')
    threading.Thread(target=send_welcome_email, args=(user, password), daemon=True).start()
    log.info("Zugangsdaten für '%s' erneut versendet (neues Passwort)", user['email'])
    return jsonify({'ok': True,
                    'no_url': not (load_site()['design'].get('public_url') or '').strip()})


@admin_app.route('/api/users/<uid>/journal')
def api_user_journal(uid: str):
    err = _api_auth()
    if err:
        return err
    user = _admin_get_user(uid)
    if user is None:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'journal': list(reversed(user.get('journal', [])))})


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
        log_user_event(uid, 'admin_upload', target.name)
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
        target = safe_under(d, safe)
        if safe and target is not None and target.is_file():
            target.unlink()
            log_user_event(uid, 'admin_delete', safe)
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
    base = USERFILES_BASE
    if request.method == 'POST':
        sub = _clean_str((request.get_json(silent=True) or {}).get('subdir'), 300).strip('/')
        if sub:
            p = safe_under(base, sub)
            if p is None or not p.is_dir():
                return jsonify({'error': 'invalid dir'}), 400
        site = load_site()
        site['design']['storage_subdir'] = sub
        save_site(site)
        log.info("Mitglieder-Speicherort: %s", userfiles_root())
        return jsonify({'ok': True})
    rel = _clean_str(request.args.get('path') or '', 300).strip('/')
    cur = safe_under(base, rel) if rel else base
    if cur is None or not cur.is_dir():
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
        if _has_detail(p) and project_visible(p):
            pages[f"p/{p['id']}/index.html"] = f"/p/{p['id']}"
    posts = sorted_posts(site, public_only=True)
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


@admin_app.route('/api/upload-font', methods=['POST'])
def api_upload_font():
    err = _api_auth()
    if err:
        return err
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'error': 'no file'}), 400
    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_FONT_EXT:
        return jsonify({'error': 'font type not allowed'}), 400
    name = uuid.uuid4().hex + ext
    target = safe_under(UPLOADS_DIR, name)
    if target is None:
        abort(400)
    f.save(target)
    # Anzeigename aus dem Originaldateinamen (ohne Endung)
    display = secure_filename(Path(f.filename).stem)[:40] or 'Eigene Schrift'
    site = load_site()
    site['design']['custom_font'] = '/uploads/' + name
    site['design']['custom_font_name'] = display
    site['design']['font'] = 'custom'
    save_site(site)
    log.info("Eigene Schrift hochgeladen: %s", display)
    return jsonify({'ok': True, 'name': display})


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
            target = safe_under(UPLOADS_DIR, name)
            if target is None:
                abort(400)
            img.save(target, 'WEBP', quality=82)
            return jsonify({'ok': True, 'url': '/uploads/' + name})
        except Exception as e:
            log.warning("Bild-Optimierung fehlgeschlagen, speichere Original: %s", e)
            f.stream.seek(0)
    # ext stammt aus dem Dateinamen, ist aber gegen ALLOWED_UPLOAD_EXT geprüft
    name = uuid.uuid4().hex + ext
    target = safe_under(UPLOADS_DIR, name)
    if target is None:
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
        'log':       list(reversed(stats.get('log', [])))[:min(visit_log_max(), 500)],
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


@public_app.route('/fonts/<path:filename>')
def public_fonts(filename: str):
    safe = secure_filename(filename)
    target = safe_under(FONTS_DIR, safe)
    if target is None or not target.is_file():
        abort(404)
    return send_from_directory(FONTS_DIR, safe, max_age=2592000)  # 30 Tage


def effective_watermark() -> str:
    """Wasserzeichen-Text: eigener Text > © + Domain > © MyPage."""
    site = load_site()
    txt = (site.get('watermark_text') or '').strip()
    if txt:
        return txt[:80]
    host = urlparse(site['design'].get('public_url') or '').netloc.removeprefix('www.')
    return f'© {host}' if host else '© MyPage'


def _render_watermark(src: Path, text: str) -> bytes | None:
    """Brennt das Wasserzeichen unten rechts ins Bild (mit Schatten für Lesbarkeit)."""
    if not _HAS_PIL:
        return None
    try:
        img = Image.open(src).convert('RGBA')
        w, h = img.size
        layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        size = max(14, int(w * 0.028))
        font = None
        for path in ('/usr/share/fonts/ttf-dejavu/DejaVuSans-Bold.ttf',
                     '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                     '/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf'):
            try:
                font = ImageFont.truetype(path, size)
                break
            except OSError:
                continue
        if font is None:
            try:
                font = ImageFont.load_default(size)  # Pillow ≥10: skalierbar
            except TypeError:
                font = ImageFont.load_default()
        box = draw.textbbox((0, 0), text, font=font)
        tw, th = box[2] - box[0], box[3] - box[1]
        margin = max(8, int(w * 0.015))
        x, y = w - tw - margin, h - th - margin - box[1]
        # Schatten + Text, halbtransparent
        draw.text((x + 1, y + 1), text, font=font, fill=(0, 0, 0, 140))
        draw.text((x, y), text, font=font, fill=(255, 255, 255, 190))
        out = Image.alpha_composite(img, layer).convert('RGB')
        buf = io.BytesIO()
        out.save(buf, 'WEBP', quality=82)
        return buf.getvalue()
    except Exception as e:
        log.warning("Wasserzeichen für '%s' fehlgeschlagen: %s", src.name, e)
        return None


@public_app.route('/album-img/<path:filename>')
def album_image(filename: str):
    """Album-Bild ausliefern — mit eingebranntem Wasserzeichen, wenn aktiviert."""
    safe = secure_filename(filename)
    src = safe_under(UPLOADS_DIR, safe)
    if not safe or src is None or not src.is_file():
        abort(404)
    site = load_site()
    if not site.get('album_protect'):
        return send_from_directory(UPLOADS_DIR, safe, max_age=86400)
    text = effective_watermark()
    # Cache-Schlüssel aus Text + Dateiname → Textänderung erzeugt neue Datei
    key = hashlib.sha256((text + '|' + safe).encode()).hexdigest()[:24]
    cached = WM_CACHE_DIR / f'{key}.webp'
    if not cached.is_file():
        data = _render_watermark(src, text)
        if data is None:
            return send_from_directory(UPLOADS_DIR, safe, max_age=86400)
        cached.write_bytes(data)
    return send_file(cached, mimetype='image/webp', max_age=86400)


def _base_url() -> str:
    site = load_site()
    return (site['design'].get('public_url') or request.url_root.rstrip('/')).rstrip('/')


@public_app.route('/favicon.ico')
def favicon():
    site = load_site()
    icon = site['design'].get('favicon') or site['profile'].get('avatar') or ''
    if icon.startswith('/uploads/'):
        return send_from_directory(UPLOADS_DIR, secure_filename(icon.removeprefix('/uploads/')), max_age=86400)
    if icon.startswith(('http://', 'https://')):
        return redirect(icon)
    return '', 204


@admin_app.route('/favicon.ico')
def admin_favicon():
    return send_from_directory(_BASE, 'icon.png', max_age=86400)


@public_app.route('/robots.txt')
def robots():
    return (f'User-agent: *\nAllow: /\nSitemap: {_base_url()}/sitemap.xml\n',
            200, {'Content-Type': 'text/plain'})


@public_app.route('/sitemap.xml')
def sitemap():
    site = load_site()
    base = _base_url()
    urls = [base + '/']
    urls += [f"{base}/p/{p['id']}" for p in site['projects'] if _has_detail(p) and project_visible(p)]
    posts = sorted_posts(site, public_only=True)
    if posts:
        urls.append(base + '/blog')
        urls += [f"{base}/blog/{p['id']}" for p in posts]
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for u in urls:
        xml += f'  <url><loc>{u}</loc></url>\n'
    xml += '</urlset>\n'
    return xml, 200, {'Content-Type': 'application/xml'}


@public_app.route('/icon.png')
def pwa_icon():
    site = load_site()
    icon = site['design'].get('favicon') or site['profile'].get('avatar') or ''
    if icon.startswith('/uploads/'):
        return send_from_directory(UPLOADS_DIR, secure_filename(icon.removeprefix('/uploads/')), max_age=86400)
    return send_from_directory(_BASE, 'icon.png', max_age=86400)


@public_app.route('/manifest.json')
def manifest():
    site = load_site()
    name = site['design'].get('site_title') or site['profile'].get('name') or 'MyPage'
    theme = '#f6f8fa' if site['design'].get('mode') == 'light' else '#0d1117'
    data = {
        'name': name, 'short_name': name[:18], 'start_url': '/', 'scope': '/',
        'display': 'standalone', 'background_color': theme, 'theme_color': theme,
        'icons': [
            {'src': '/icon.png', 'sizes': '192x192', 'type': 'image/png', 'purpose': 'any maskable'},
            {'src': '/icon.png', 'sizes': '512x512', 'type': 'image/png', 'purpose': 'any maskable'},
        ],
    }
    return jsonify(data), 200, {'Cache-Control': 'no-cache'}


@public_app.route('/sw.js')
def service_worker():
    # Minimaler Service Worker: macht die Seite installierbar, Network-first
    js = (
        "self.addEventListener('install', e => self.skipWaiting());\n"
        "self.addEventListener('activate', e => self.clients.claim());\n"
        "self.addEventListener('fetch', e => {\n"
        "  if (e.request.method !== 'GET') return;\n"
        "  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));\n"
        "});\n"
    )
    return js, 200, {'Content-Type': 'application/javascript', 'Cache-Control': 'no-cache'}


@public_app.route('/feed.xml')
def rss_feed():
    site = load_site()
    posts = sorted_posts(site, public_only=True)
    if not posts:
        abort(404)
    base = _base_url()
    lang = detect_language(request)
    loc = _loc_factory(lang)
    title = site['design'].get('site_title') or site['profile'].get('name') or 'MyPage'
    esc = html_mod.escape
    items = ''
    for p in posts[:30]:
        link = f"{base}/blog/{p['id']}"
        # YYYY-MM-DD → RFC-822 (für RSS-Reader)
        try:
            pub = datetime.strptime(p.get('date', ''), '%Y-%m-%d').strftime('%a, %d %b %Y 00:00:00 +0000')
        except ValueError:
            pub = ''
        teaser = re.sub('<[^>]+>', '', render_md(loc(p, 'text')))[:300]
        items += (f'    <item>\n'
                  f'      <title>{esc(loc(p, "title"))}</title>\n'
                  f'      <link>{esc(link)}</link>\n'
                  f'      <guid isPermaLink="true">{esc(link)}</guid>\n'
                  + (f'      <pubDate>{pub}</pubDate>\n' if pub else '')
                  + f'      <description>{esc(teaser)}</description>\n'
                  f'    </item>\n')
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<rss version="2.0"><channel>\n'
           f'    <title>{esc(title)}</title>\n'
           f'    <link>{esc(base)}/blog</link>\n'
           f'    <description>{esc(loc(site["profile"], "tagline"))}</description>\n'
           f'{items}</channel></rss>\n')
    return xml, 200, {'Content-Type': 'application/rss+xml; charset=utf-8'}


@public_app.errorhandler(404)
def not_found(_e):
    lang = detect_language(request)
    t = load_translations(lang)
    site = load_site()
    return render_template('404.html', t=t, lang=lang, site=site), 404


def _render_error(code: int, title_key: str, text_key: str, *, admin: bool = False):
    """Gestaltete Fehlerseite (DE/EN) für 403/413/500 — auf öffentlicher und Admin-App."""
    lang = detect_language(request)
    t = load_translations(lang)
    try:
        site = load_site()
    except Exception:
        site = json.loads(json.dumps(DEFAULT_SITE))
    return render_template('error.html', t=t, lang=lang, site=site, code=code,
                           err_title=t.get(title_key, ''), err_text=t.get(text_key, ''),
                           home_url='' if admin else '/',
                           home_label=t.get('err_back', 'Zurück') if admin else t.get('nf_home', '')), code


@public_app.errorhandler(403)
def _pub_403(_e):
    return _render_error(403, 'err_403_title', 'err_403_text')


@public_app.errorhandler(413)
def _pub_413(_e):
    return _render_error(413, 'err_413_title', 'err_413_text')


@public_app.errorhandler(500)
def _pub_500(_e):
    return _render_error(500, 'err_500_title', 'err_500_text')


@admin_app.errorhandler(403)
def _adm_403(_e):
    return _render_error(403, 'err_403_title', 'err_403_text', admin=True)


@admin_app.errorhandler(413)
def _adm_413(_e):
    return _render_error(413, 'err_413_title', 'err_413_text', admin=True)


@admin_app.errorhandler(500)
def _adm_500(_e):
    return _render_error(500, 'err_500_title', 'err_500_text', admin=True)


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
    projects = [dict(p, has_detail=_has_detail(p)) for p in site['projects'] if project_visible(p)]
    static_export = bool(request.args.get('static'))
    font_family, font_faces = font_css(site['design'])
    sections = site.get('sections', {})
    albums = _albums_for_public(site)
    latest_posts = sorted_posts(site, public_only=True)[:3]
    contact_enabled = bool(site['design'].get('contact_enabled')) and not static_export

    loc_block = sections.get('location') or {}
    loc_present = bool(loc_block.get('address') or loc_block.get('hours_de') or loc_block.get('hours_en'))

    # Eigenschaften je Abschnitt: (Anker, Übersetzungs-Schlüssel, ob Inhalt vorhanden)
    section_defs = {
        'news':         ('news',         'news_heading',         bool(sections.get('news'))),
        'blog':         ('blog',         'blog_heading',         bool(latest_posts)),
        'services':     ('services',     'services_heading',     bool(sections.get('services'))),
        'projects':     ('projects',     'projects',             bool(projects)),
        'skills':       ('skills',       'skills_heading',       bool(sections.get('skills'))),
        'testimonials': ('testimonials', 'testimonials_heading', bool(sections.get('testimonials'))),
        'photos':       ('photos',       'albums_heading',       bool(albums)),
        'team':         ('team',         'team_heading',         bool(sections.get('team'))),
        'timeline':     ('timeline',     'timeline_heading',     bool(sections.get('timeline'))),
        'events':       ('events',       'events_heading',       bool(sections.get('events'))),
        'links':        ('links',        'links_heading',        bool(sections.get('links'))),
        'faq':          ('faq',          'faq_heading',          bool(sections.get('faq'))),
        'location':     ('standort',     'location_heading',     loc_present),
    }
    # Gespeicherte Reihenfolge bereinigen: nur gültige Keys, fehlende hinten anhängen
    stored = [k for k in (site.get('section_order') or []) if k in section_defs]
    section_order = stored + [k for k in SECTION_KEYS if k not in stored]
    # Ausgeblendete Abschnitte entfernen (Inhalt bleibt erhalten, nur nicht sichtbar)
    hidden = set(site.get('hidden_sections') or [])
    section_order = [k for k in section_order if k not in hidden]

    # Navigations-Leiste: nur Sektionen mit Inhalt, in gewählter Reihenfolge
    nav_items = []
    if site['design'].get('show_nav', True):
        for key in section_order:
            anchor, label_key, present = section_defs[key]
            if present:
                nav_items.append({'anchor': anchor, 'label': t.get(label_key, label_key)})
        if contact_enabled:
            nav_items.append({'anchor': 'kontakt', 'label': t.get('contact_heading', 'contact_heading')})

    return render_template('public.html', t=t, lang=lang, site=site, loc=loc,
                           projects=projects,
                           font_family=font_family, font_faces=font_faces,
                           bio_html=render_md(loc(site['profile'], 'bio')),
                           email_parts=email_parts,
                           sections=sections,
                           albums=albums,
                           album_protect=bool(site.get('album_protect')),
                           latest_posts=latest_posts,
                           nav_items=nav_items,
                           section_order=section_order,
                           static_export=static_export,
                           contact_enabled=contact_enabled,
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
    posts = sorted_posts(site, public_only=True)
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
    if post is None or not post_visible(post):
        abort(404)
    count_visit(request)
    t = load_translations(lang)
    loc = _loc_factory(lang)
    return render_template('post.html', t=t, lang=lang, site=site, loc=loc, p=post,
                           text_html=render_md(loc(post, 'text')),
                           year=datetime.now(timezone.utc).year)


@admin_app.route('/preview/blog/<pid>')
def admin_blog_preview(pid: str):
    """Beitrags-Vorschau im Admin — rendert post.html für jeden Beitrag (auch Entwurf/geplant)."""
    err = _auth_required()
    if err:
        return err
    lang = detect_language(request)
    site = load_site()
    post = next((p for p in site.get('posts', []) if p.get('id') == pid), None)
    if post is None:
        abort(404)
    t = load_translations(lang)
    loc = _loc_factory(lang)
    return render_template('post.html', t=t, lang=lang, site=site, loc=loc, p=post,
                           text_html=render_md(loc(post, 'text')), preview=True,
                           year=datetime.now(timezone.utc).year)


@public_app.route('/p/<pid>')
def project_detail(pid: str):
    lang = detect_language(request)
    site = load_site()
    if site['design'].get('maintenance'):
        return _maintenance_page(site, lang)
    proj = next((p for p in site['projects'] if p.get('id') == pid), None)
    if proj is None or not _has_detail(proj) or not project_visible(proj):
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
        try:
            for f in sorted(user_dir(member).iterdir()):
                if f.is_file():
                    st = f.stat()
                    files.append({'name': f.name, 'size': st.st_size,
                                  'mtime': datetime.fromtimestamp(st.st_mtime).strftime('%d.%m.%Y %H:%M')})
                    used += st.st_size
        except OSError as e:
            log.warning("Dateiliste für '%s' fehlgeschlagen: %s", member['email'], e)
            storage_down = True
            files = []
    login_msg_html = render_md(member.get('login_message', '')) if member else ''
    return render_template('member.html', t=t, lang=lang, site=site, member=member,
                           files=files, used=used, quota=quota, msg=msg,
                           storage_down=storage_down, login_msg_html=login_msg_html,
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
    email = (request.form.get('email') or '').strip().lower()
    if is_rate_limited(ip):
        log.warning("Mitglieder-Login GESPERRT: '%s' von %s (zu viele Fehlversuche)",
                    email or '?', ip)
        return redirect('/bereich?msg=locked')
    password = request.form.get('password') or ''
    user = next((u for u in load_users() if u['email'] == email), None)
    if user is None or not check_password_hash(user['pw_hash'], password):
        record_failed_attempt(ip)
        log.warning("Mitglieder-Login FEHLGESCHLAGEN: '%s' von %s", email or '?', ip)
        return redirect('/bereich?msg=credentials')
    clear_failed_attempts(ip)
    token = secrets.token_hex(32)
    user_sessions[token] = [user['id'], time.time() + USER_SESSION_HOURS * 3600]
    save_user_sessions()
    log_user_event(user['id'], 'login', '', ip)
    resp = make_response(redirect('/bereich'))
    resp.set_cookie('usession', token, httponly=True, samesite='Lax',
                    max_age=USER_SESSION_HOURS * 3600)
    log.info("Mitglieder-Login ERFOLGREICH: '%s' von %s", email, ip)
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
    log_user_event(member['id'], 'upload', target.name, get_client_ip(request))
    log.info("Mitglied '%s': Datei '%s' hochgeladen", member['email'], target.name)
    return redirect('/bereich?msg=uploaded')


def _serve_user_file(d: Path, name: str):
    """Datei-Download mit explizitem Pfad-Check und Fehler-Logging (SMB kann zicken)."""
    safe = secure_filename(name)
    target = safe_under(d, safe)
    if not safe or target is None or not target.is_file():
        abort(404)
    try:
        # as_attachment: hochgeladene Dateien werden nie im Browser ausgeführt;
        # conditional=False vermeidet Range/ETag-Sonderfälle auf CIFS-Mounts
        return send_file(target, as_attachment=True, download_name=safe, conditional=False)
    except OSError as e:
        # FritzBox trennt inaktive SMB-Verbindungen → stale handle: neu mounten,
        # Dateizugriff verifizieren (mit Wartezeit) und erst dann erneut ausliefern
        if SMB_MOUNTED and e.errno in (errno.ESTALE, errno.EIO):
            # Stufe 1: nur den Cache verwerfen — die Session lebt meist noch
            if drop_fs_caches():
                try:
                    os.stat(target)
                    log.info("Stale Handle bei '%s' durch Cache-Drop behoben", safe)
                    return send_file(target, as_attachment=True, download_name=safe,
                                     conditional=False)
                except OSError:
                    pass
            # Stufe 2: harter Remount mit Verifikation
            log.warning("Stale SMB-Handle bei '%s' — Remount und zweiter Versuch", safe)
            for attempt in (1, 2):
                if not remount_smb():
                    break
                ready = False
                for _ in range(6):
                    try:
                        os.stat(target)
                        ready = True
                        break
                    except OSError as e_stat:
                        if e_stat.errno not in (errno.ESTALE, errno.EIO):
                            break
                        time.sleep(0.5)
                if ready:
                    try:
                        return send_file(target, as_attachment=True, download_name=safe,
                                         conditional=False)
                    except Exception as e2:
                        log.error("Download '%s' nach Remount %d fehlgeschlagen: %s",
                                  safe, attempt, e2)
                else:
                    log.warning("Datei '%s' nach Remount %d weiterhin stale", safe, attempt)
        log.error("Download '%s' fehlgeschlagen: %s", safe, e)
        abort(503)
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
    resp = _serve_user_file(user_dir(member), name)
    log_user_event(member['id'], 'download', secure_filename(name), get_client_ip(request))
    return resp


@public_app.route('/bereich/delete', methods=['POST'])
def member_delete():
    member = current_member(request)
    if member is None:
        abort(403)
    if not storage_available():
        return redirect('/bereich?msg=storage')
    name = secure_filename(request.form.get('name') or '')
    d = user_dir(member)
    target = safe_under(d, name)
    if name and target is not None and target.is_file():
        target.unlink()
        log_user_event(member['id'], 'delete', name, get_client_ip(request))
        log.info("Mitglied '%s': Datei '%s' gelöscht", member['email'], name)
    return redirect('/bereich')


@public_app.route('/contact/captcha')
def contact_captcha():
    return jsonify(make_captcha())


@public_app.route('/contact', methods=['POST'])
def contact():
    site = load_site()
    if site['design'].get('maintenance') or not site['design'].get('contact_enabled'):
        return jsonify({'error': 'disabled'}), 403
    # Honeypot: Bots füllen das versteckte Feld aus → still verwerfen
    if (request.form.get('website') or '').strip():
        return jsonify({'ok': True})
    # Rechen-Captcha gegen automatisierten Spam
    if not check_captcha(request.form.get('captcha_token'), request.form.get('captcha_answer')):
        return jsonify({'error': 'captcha'}), 400
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

    # Initialer SMB-Mount (run.sh setzt nur noch den Pfad, Zugangsdaten bleiben im Speicher)
    if SMB_MOUNTED and not storage_available():
        if remount_smb():
            log.info("SMB-Share beim Start gemountet")
        else:
            log.warning("SMB-Mount beim Start fehlgeschlagen — Dateibereich offline, "
                        "Watchdog versucht es jede Minute erneut")
    log.info("Mitglieder-Bereich: Speicher unter %s, Upload-Limit %d MB",
             userfiles_root(), upload_max)

    threading.Thread(target=_run_public, daemon=True).start()
    threading.Thread(target=refresh_project_stars, daemon=True).start()
    threading.Thread(target=_sensor_worker, daemon=True).start()
    threading.Thread(target=_geoip_worker, daemon=True).start()
    threading.Thread(target=_smb_watchdog, daemon=True).start()

    log.info("MyPage bereit — öffentlich: %d, Admin: %d", PUBLIC_PORT, ADMIN_PORT)
    admin_app.run(host='0.0.0.0', port=ADMIN_PORT, debug=False, threaded=True)
