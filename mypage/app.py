#!/usr/bin/env python3
"""MyPage — Homepage-Baukasten für Home Assistant.

Zwei Server in einem Prozess:
  - Port 17760: öffentliche Homepage (kein Login, Besucherzähler)
  - Port 17761: Admin-Panel (Login + Brute-Force-Schutz, auch via HA Ingress)
"""
import copy
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
    from PIL import Image, ImageDraw, ImageFont, ImageOps
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

import game_66
import game_20ab
import game_schwimmen
import game_maumau
import game_jeopardy
import game_gluecksrad
import game_praesident

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
COMMENTS_PATH = _DATA + '/comments.json'
AUDIT_PATH = _DATA + '/audit.json'
SUBSCRIBERS_PATH = _DATA + '/subscribers.json'
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
# Kartenspiel-Spielstände (lokal im addon_config, NICHT auf dem SMB-Share)
GAMES_DIR = Path(_DATA) / 'games'
GAMES_DIR.mkdir(parents=True, exist_ok=True)
# Erlaubte Spieldateinamen (für Backup/Restore): <spiel>_<uid>.json /
# <spiel>hist_<uid>.json / gsessions_<uid>.json (Sitzungs-Log)
_GAME_FILE_RE = re.compile(
    r'^(?:(?:66|20ab|schwimmen|maumau|praesident|jeopardy|gluecksrad)(?:hist)?|gsessions)_[a-f0-9]{6,32}\.json$')
# Kartendecks (mitgeliefert, austauschbar) — /app/static/cards/<deck>/<rang><farbe>.svg
CARDS_DIR = Path(_BASE) / 'static' / 'cards'

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
_comments_lock = threading.Lock()
_audit_lock = threading.Lock()
_subs_lock = threading.Lock()
_slot_lock  = threading.Lock()
_game_lock  = threading.Lock()

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
        'comments_enabled': False,
        'registration_enabled': False,
        'registration_quota_mb': 500,
        'newsletter_enabled': False,
        'maintenance': False,
        'maintenance_text_de': '', 'maintenance_text_en': '',
        'banner_enabled': False, 'banner_dismissible': True,
        'banner_text_de': '', 'banner_text_en': '',
        'banner_link_url': '', 'banner_link_label_de': '', 'banner_link_label_en': '',
        'font': 'system', 'custom_css': '',
        'custom_font': '', 'custom_font_name': '',
        'support_url': '', 'support_label': '',
        'booking_url': '', 'booking_label': '',
        'indexnow': False,
        'allow_indexing': True,
        'easter_eggs': False, 'egg_message': '', 'egg_tagline': '',
        'mini_games': False,
        'reveal_effect': 'off', 'reveal_stagger': True,
        'card_deck': 'knoll',
        'meta_description_de': '', 'meta_description_en': '',
    },
    'posts': [],
    'pages': [],
    'forms': [],
    'legal': {
        'impressum_de': '', 'impressum_en': '',
        'privacy_de': '', 'privacy_en': '',
    },
    'sections': {
        'skills': [],
        'timeline': [],
        'timeline_title_de': '', 'timeline_title_en': '',
        'news': [],
        'links': [],
        'faq': [],
        'services': [],
        'testimonials': [],
        'team': [],
        'events': [],
        'location': {},
        'tips': [],
    },
    'albums': [],
    'album_protect': False,
    'watermark_text': '',
    'section_order': [
        'news', 'tips', 'blog', 'services', 'projects', 'skills', 'testimonials',
        'photos', 'team', 'timeline', 'events', 'links', 'faq', 'location',
    ],
    'hidden_sections': [],
    'members_sections': [],
    'tips_rotation': 'daily',
    'tips_random': False,
    'tips_stats': {},
    'indexnow_key': '',
    'slot_jackpot': 500,
}

# Reihenfolge der Startseiten-Abschnitte (Hero immer zuerst, Kontakt immer zuletzt)
SECTION_KEYS = list(DEFAULT_SITE['section_order'])


def render_md(text: str) -> str:
    """Markdown → HTML (Inhalte stammen ausschließlich vom Admin)."""
    return md_lib.markdown(text or '', extensions=['nl2br', 'sane_lists', 'tables', 'fenced_code'])


def _plain_excerpt(s: str, limit: int = 155) -> str:
    """HTML/Markdown-Text in einen kurzen Klartext-Auszug für Meta-Description wandeln."""
    txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s or '')).strip()
    return txt[:limit].rstrip()


def _locked_teaser(html: str, cap: int = 280) -> str:
    """Anriss für Mitglieder-only-Inhalte: höchstens die Hälfte des Textes
    (max. `cap` Zeichen) — so bleibt immer ein Teil verborgen, auch bei kurzen Texten."""
    plain = _plain_excerpt(html, 100000)
    cut = min(cap, len(plain) // 2)
    teaser = plain[:cut].rstrip()
    if len(teaser) < len(plain):
        teaser += ' …'
    return teaser


def _site_meta(site: dict, loc) -> str:
    """Basis-Beschreibung der Seite: eigenes SEO-Feld → Tagline → Bio-Auszug → Name."""
    d, p = site['design'], site['profile']
    return (loc(d, 'meta_description') or loc(p, 'tagline')
            or _plain_excerpt(render_md(loc(p, 'bio'))) or d.get('site_title') or p.get('name') or 'MyPage')


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


# ── Blog-Kommentare & -Reaktionen (Mitglieder) ────────────────────────────────
COMMENT_REACTIONS = ['👍', '❤️', '😄', '🎉', '👏']
COMMENTS_MAX_PER_POST = 500


def load_comments() -> dict:
    """Pro Beitrag: {post_id: {'comments': [...], 'reactions': {uid: emoji}}}"""
    with _comments_lock:
        try:
            with open(COMMENTS_PATH, encoding='utf-8') as f:
                d = json.load(f)
                return d if isinstance(d, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception as e:
            log.warning("comments.json konnte nicht geladen werden: %s", e)
            return {}


def save_comments(data: dict) -> None:
    with _comments_lock:
        try:
            with open(COMMENTS_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.warning("comments.json konnte nicht gespeichert werden: %s", e)


def _post_thread(data: dict, pid: str) -> dict:
    return data.setdefault(pid, {'comments': [], 'reactions': {}})


def _reaction_counts(reactions: dict) -> dict:
    """{uid: emoji} → {emoji: anzahl}"""
    counts: dict[str, int] = {}
    for emoji in (reactions or {}).values():
        counts[emoji] = counts.get(emoji, 0) + 1
    return counts


def _member_display_name(member: dict) -> str:
    return member.get('name') or (member.get('email') or '').split('@')[0] or 'Mitglied'


# ── Admin-Audit-Log ────────────────────────────────────────────────────────────
AUDIT_MAX = 500


def load_audit() -> list:
    with _audit_lock:
        try:
            with open(AUDIT_PATH, encoding='utf-8') as f:
                d = json.load(f)
                return d if isinstance(d, list) else []
        except FileNotFoundError:
            return []
        except Exception as e:
            log.warning("audit.json konnte nicht geladen werden: %s", e)
            return []


def log_audit(action: str, detail: str = '') -> None:
    """Sicherheitsrelevante Admin-Aktion protokollieren (Zeit, Aktion, Detail, IP)."""
    try:
        ip = get_client_ip(request)
    except Exception:
        ip = ''
    entry = {'ts': int(time.time()), 'action': action, 'detail': (detail or '')[:200], 'ip': ip}
    with _audit_lock:
        try:
            try:
                with open(AUDIT_PATH, encoding='utf-8') as f:
                    data = json.load(f)
                    if not isinstance(data, list):
                        data = []
            except FileNotFoundError:
                data = []
            data.append(entry)
            with open(AUDIT_PATH, 'w', encoding='utf-8') as f:
                json.dump(data[-AUDIT_MAX:], f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.warning("audit.json konnte nicht geschrieben werden: %s", e)


# ── Newsletter / Blog-Abo ──────────────────────────────────────────────────────
NEWSLETTER_CONFIRM_TTL = 7 * 86400                # Bestätigungslink 7 Tage gültig
NEWSLETTER_MAX_PER_HOUR = 5
_newsletter_times: dict[str, list[float]] = defaultdict(list)


def load_subscribers() -> list:
    with _subs_lock:
        try:
            with open(SUBSCRIBERS_PATH, encoding='utf-8') as f:
                d = json.load(f)
                return d if isinstance(d, list) else []
        except FileNotFoundError:
            return []
        except Exception as e:
            log.warning("subscribers.json konnte nicht geladen werden: %s", e)
            return []


def save_subscribers(data: list) -> None:
    with _subs_lock:
        try:
            with open(SUBSCRIBERS_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.warning("subscribers.json konnte nicht gespeichert werden: %s", e)


def newsletter_open() -> bool:
    """Abo möglich: aktiviert UND E-Mail-Versand + öffentliche URL vorhanden."""
    site = load_site()
    return (bool(site['design'].get('newsletter_enabled'))
            and smtp_configured()
            and bool((site['design'].get('public_url') or '').strip()))


def newsletter_rate_limited(ip: str) -> bool:
    now = time.time()
    _newsletter_times[ip] = [t for t in _newsletter_times[ip] if now - t < 3600]
    return len(_newsletter_times[ip]) >= NEWSLETTER_MAX_PER_HOUR


def record_newsletter_attempt(ip: str) -> None:
    _newsletter_times[ip].append(time.time())


def _unsub_link(sub: dict) -> str:
    base = (load_site()['design'].get('public_url') or '').rstrip('/')
    return f"{base}/newsletter/unsubscribe/{sub['id']}/{sub['utoken']}" if base else ''


def send_confirm_subscription(sub: dict, token: str) -> None:
    base = (load_site()['design'].get('public_url') or '').rstrip('/')
    if not base:
        return
    link = f"{base}/newsletter/confirm/{sub['id']}/{token}"
    title, esc = _site_title(), html_mod.escape
    lines = [f'Bitte bestätige dein Abo des Newsletters von <b>{esc(title)}</b> (Link 7 Tage gültig):',
             f'<a href="{esc(link)}">{esc(link)}</a>',
             'Erst nach dem Klick erhältst du künftige Nachrichten. Wenn du das nicht warst, ignoriere diese E-Mail.']
    send_email(f'Newsletter bestätigen – {title}',
               _email_html(f'📰 Newsletter bestätigen – {esc(title)}', lines),
               to=sub['email'], from_addr=_reg_from())


def send_newsletter_batch(subject: str, body_html: str, subs: list) -> int:
    """Sendet body_html an alle (bestätigten) Empfänger, je mit eigenem Abmelde-Link."""
    title, esc = _site_title(), html_mod.escape
    from_addr = _reg_from()
    sent = 0
    for sub in subs:
        footer = (f'<hr style="border:none;border-top:1px solid #30363d;margin:16px 0">'
                  f'<p style="font-size:12px;color:#8b949e;margin:0">'
                  f'Du erhältst diese E-Mail, weil du den Newsletter von {esc(title)} abonniert hast. '
                  f'<a href="{esc(_unsub_link(sub))}">Abmelden</a></p>')
        html = ('<div style="font-family:sans-serif;max-width:560px;padding:20px;'
                'background:#0d1117;color:#c9d1d9;border-radius:8px">'
                f'<h3 style="margin:0 0 12px;color:#58a6ff">{esc(subject)}</h3>'
                f'{body_html}{footer}</div>')
        send_email(subject, html, to=sub['email'], from_addr=from_addr)
        sent += 1
    return sent


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
        notify_ha_async(
            '🔒 MyPage: Verdächtige Anmeldeversuche',
            f'Die IP {ip} wurde nach {len(recent)} fehlgeschlagenen Login-Versuchen '
            f'für {RATE_LIMIT_BLOCK // 60} Minuten gesperrt.',
            notification_id=f'mypage_bruteforce_{ip}')


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


def bump_post_view(pid: str, req) -> int:
    """Zählt einen Aufruf eines Blog-Beitrags (ohne Bots/Export); liefert den neuen Stand."""
    cur = load_stats().get('posts', {}).get(pid, 0)
    if req.headers.get('X-MyPage-Export'):
        return cur
    ua = req.headers.get('User-Agent') or ''
    if (not ua) or any(b in ua.lower() for b in _BOT_UA):
        return cur
    stats = load_stats()
    posts = stats.setdefault('posts', {})
    posts[pid] = posts.get(pid, 0) + 1
    save_stats(stats)
    return posts[pid]


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


def top_pages(site: dict, visit_log: list, limit: int = 12) -> list:
    """Meistbesuchte Seiten aus dem Besucher-Log (ohne Bots). Für Blog-/Projekt-
    Detailseiten wird der Titel mitgeliefert, sonst nur der Pfad."""
    counts: dict[str, int] = {}
    for v in visit_log:
        if v.get('bot'):
            continue
        counts[v.get('path') or '/'] = counts.get(v.get('path') or '/', 0) + 1
    posts = {p.get('id'): p for p in site.get('posts', [])}
    projects = {p.get('id'): p for p in site.get('projects', [])}
    out = []
    for path, n in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:limit]:
        title = ''
        if path.startswith('/blog/'):
            po = posts.get(path.split('/blog/', 1)[1].split('/')[0])
            title = (po.get('title_de') or po.get('title_en')) if po else ''
        elif path.startswith('/p/'):
            pr = projects.get(path.split('/p/', 1)[1].split('/')[0])
            title = pr.get('title') if pr else ''
        out.append({'path': path, 'title': title, 'count': n})
    return out


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


def invalidate_user_sessions(uid: str, keep: str | None = None) -> int:
    """Beendet alle aktiven Sitzungen eines Benutzers (z. B. nach Passwortwechsel).
    Mit ``keep`` lässt sich ein Token (die aktuelle Sitzung) ausnehmen."""
    tokens = [t for t, v in user_sessions.items() if v[0] == uid and t != keep]
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


def is_member(req) -> bool:
    return current_member(req) is not None


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


# ── Self-Service-Passwort-Reset ────────────────────────────────────────────
RESET_TTL = 3600                                  # Token 1 Stunde gültig
RESET_MAX_PER_HOUR = 5                            # Anfragen pro IP/Stunde
_reset_times: dict[str, list[float]] = defaultdict(list)


def reset_enabled() -> bool:
    """Reset nur möglich, wenn E-Mail-Versand UND öffentliche URL konfiguriert sind."""
    return smtp_configured() and bool((load_site()['design'].get('public_url') or '').strip())


def reset_rate_limited(ip: str) -> bool:
    now = time.time()
    _reset_times[ip] = [t for t in _reset_times[ip] if now - t < 3600]
    return len(_reset_times[ip]) >= RESET_MAX_PER_HOUR


def record_reset_attempt(ip: str) -> None:
    _reset_times[ip].append(time.time())


def send_reset_email(user: dict, token: str) -> None:
    site = load_site()
    base = (site['design'].get('public_url') or '').rstrip('/')
    if not base:
        return
    link = f"{base}/bereich/reset/{user['id']}/{token}"
    title = site['design'].get('site_title') or site['profile'].get('name') or 'MyPage'
    esc = html_mod.escape
    lines = [f'Für dein Konto bei <b>{esc(title)}</b> wurde ein Zurücksetzen des Passworts angefordert.',
             'Klicke auf den folgenden Link, um ein neues Passwort zu setzen (1 Stunde gültig):',
             f'<a href="{esc(link)}">{esc(link)}</a>',
             'Wenn du das nicht warst, ignoriere diese E-Mail einfach — dein Passwort bleibt unverändert.']
    send_email(f'Passwort zurücksetzen – {title}',
               _email_html(f'🔑 Passwort zurücksetzen – {esc(title)}', lines),
               to=user['email'],
               from_addr=(site['design'].get('welcome_from') or '').strip() or None)


def _find_reset_user(users: list, uid: str, token: str) -> dict | None:
    """Liefert den Benutzer, wenn uid+Token zu einem gültigen, nicht abgelaufenen
    Reset-Eintrag passen — sonst None."""
    user = next((u for u in users if u['id'] == uid), None)
    if user is None:
        return None
    r = user.get('reset')
    if not r or time.time() > r.get('exp', 0):
        return None
    if not check_password_hash(r.get('hash', ''), token):
        return None
    return user


# ── Self-Service-Registrierung ─────────────────────────────────────────────
REGISTER_TTL = 86400                              # Bestätigungslink 24 h gültig
REGISTER_MAX_PER_HOUR = 5
_register_times: dict[str, list[float]] = defaultdict(list)


def registration_open() -> bool:
    """Registrierung möglich: aktiviert UND E-Mail-Versand + öffentliche URL vorhanden
    (E-Mail-Bestätigung ist Pflicht)."""
    site = load_site()
    return (bool(site['design'].get('registration_enabled'))
            and smtp_configured()
            and bool((site['design'].get('public_url') or '').strip()))


def register_rate_limited(ip: str) -> bool:
    now = time.time()
    _register_times[ip] = [t for t in _register_times[ip] if now - t < 3600]
    return len(_register_times[ip]) >= REGISTER_MAX_PER_HOUR


def record_register_attempt(ip: str) -> None:
    _register_times[ip].append(time.time())


def _find_verify_user(users: list, uid: str, token: str) -> dict | None:
    user = next((u for u in users if u['id'] == uid), None)
    if user is None:
        return None
    v = user.get('verify')
    if not v or time.time() > v.get('exp', 0):
        return None
    if not check_password_hash(v.get('hash', ''), token):
        return None
    return user


def _member_login_blocked(user: dict) -> str | None:
    """Grund, warum ein selbst-registriertes Konto noch nicht anmelden darf — sonst None."""
    if user.get('self_registered'):
        if not user.get('verified'):
            return 'unverified'
        if not user.get('approved'):
            return 'pending'
    return None


def _pending_approvals() -> int:
    """Anzahl selbst-registrierter Konten, die (E-Mail bestätigt) auf die Admin-Freigabe warten."""
    return sum(1 for u in load_users()
               if u.get('self_registered') and u.get('verified') and not u.get('approved'))


def _reg_from():
    return (load_site()['design'].get('welcome_from') or '').strip() or None


def _site_title() -> str:
    site = load_site()
    return site['design'].get('site_title') or site['profile'].get('name') or 'MyPage'


def send_verify_email(user: dict, token: str) -> None:
    site = load_site()
    base = (site['design'].get('public_url') or '').rstrip('/')
    if not base:
        return
    link = f"{base}/bereich/verify/{user['id']}/{token}"
    title, esc = _site_title(), html_mod.escape
    lines = [f'Willkommen bei <b>{esc(title)}</b>! Bitte bestätige deine E-Mail-Adresse, um die Registrierung abzuschließen (Link 24 Stunden gültig):',
             f'<a href="{esc(link)}">{esc(link)}</a>',
             'Danach schaltet der Betreiber dein Konto frei — du bekommst dann eine weitere E-Mail.',
             'Wenn du dich nicht registriert hast, ignoriere diese E-Mail einfach.']
    send_email(f'E-Mail bestätigen – {title}',
               _email_html(f'✅ E-Mail bestätigen – {esc(title)}', lines),
               to=user['email'], from_addr=_reg_from())


def send_already_registered_email(user: dict) -> None:
    site = load_site()
    base = (site['design'].get('public_url') or '').rstrip('/')
    title, esc = _site_title(), html_mod.escape
    lines = [f'Für diese E-Mail-Adresse besteht bei <b>{esc(title)}</b> bereits ein Konto.',
             (f'Du kannst dich hier anmelden: <a href="{esc(base)}/bereich">{esc(base)}/bereich</a>'
              if base else 'Du kannst dich im Mitgliederbereich anmelden.'),
             'Passwort vergessen? Nutze den „Passwort vergessen?"-Link auf der Login-Seite.',
             'Wenn du das nicht warst, kannst du diese E-Mail ignorieren.']
    send_email(f'Konto besteht bereits – {title}',
               _email_html(f'ℹ️ Konto besteht bereits – {esc(title)}', lines),
               to=user['email'], from_addr=_reg_from())


def send_activated_email(user: dict) -> None:
    site = load_site()
    base = (site['design'].get('public_url') or '').rstrip('/')
    title, esc = _site_title(), html_mod.escape
    url = (base + '/bereich') if base else ''
    lines = [f'Dein Konto bei <b>{esc(title)}</b> wurde freigeschaltet — du kannst dich jetzt anmelden.',
             (f'<a href="{esc(url)}">{esc(url)}</a>' if url else ''),
             f'<b>Benutzername:</b> {esc(user["email"])}']
    send_email(f'Konto freigeschaltet – {title}',
               _email_html(f'🎉 Konto freigeschaltet – {esc(title)}', [l for l in lines if l]),
               to=user['email'], from_addr=_reg_from())


def send_comment_reply_email(to_email: str, post_title: str, replier: str,
                             text: str, post_url: str) -> None:
    """Benachrichtigt den Autor eines Kommentars, dass jemand geantwortet hat."""
    title, esc = _site_title(), html_mod.escape
    lines = [f'{esc(replier)} hat auf deinen Kommentar zu „{esc(post_title)}" geantwortet:',
             f'<i>{esc(text[:300])}</i>',
             (f'<a href="{esc(post_url)}#comments">Zur Diskussion</a>' if post_url else '')]
    send_email(f'Neue Antwort auf deinen Kommentar – {title}',
               _email_html(f'💬 Neue Antwort – {esc(title)}', [l for l in lines if l]),
               to=to_email, from_addr=_reg_from())


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


def ha_notify_enabled() -> bool:
    """Persistente HA-Benachrichtigungen aktiv? (nur im Add-on, per Option abschaltbar)"""
    return bool(SUPERVISOR_TOKEN) and bool(load_config().get('ha_notify', True))


def notify_ha(title: str, message: str, notification_id: str | None = None) -> None:
    """Erzeugt/aktualisiert eine persistente Benachrichtigung in Home Assistant.
    Gleiche notification_id überschreibt → kein Zuspammen bei Wiederholungen."""
    if not ha_notify_enabled():
        return
    data = {'title': title, 'message': message}
    if notification_id:
        data['notification_id'] = notification_id
    try:
        http.post('http://supervisor/core/api/services/persistent_notification/create',
                  headers={'Authorization': f'Bearer {SUPERVISOR_TOKEN}'},
                  json=data, timeout=10)
    except Exception as e:
        log.warning("HA-Benachrichtigung fehlgeschlagen: %s", e)


def notify_ha_async(title: str, message: str, notification_id: str | None = None) -> None:
    """Wie notify_ha, aber ohne den Request zu blockieren."""
    if ha_notify_enabled():
        threading.Thread(target=notify_ha, args=(title, message, notification_id),
                         daemon=True).start()


def ha_dismiss(notification_id: str) -> None:
    """Eine persistente HA-Benachrichtigung wieder entfernen."""
    if not (SUPERVISOR_TOKEN and notification_id):
        return
    try:
        http.post('http://supervisor/core/api/services/persistent_notification/dismiss',
                  headers={'Authorization': f'Bearer {SUPERVISOR_TOKEN}'},
                  json={'notification_id': notification_id}, timeout=10)
    except Exception as e:
        log.warning("HA-Benachrichtigung entfernen fehlgeschlagen: %s", e)


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
    pending = _pending_approvals()
    sensors = [
        ('mypage_views_total',    stats.get('total', 0), 'MyPage Aufrufe gesamt',  'mdi:counter',       'Aufrufe'),
        ('mypage_visitors_total', total_uniques(stats),  'MyPage Besucher gesamt', 'mdi:account-group', 'Besucher'),
        ('mypage_views_today',    today['views'],        'MyPage Aufrufe heute',   'mdi:eye',           'Aufrufe'),
        ('mypage_visitors_today', today['uniques'],      'MyPage Besucher heute',  'mdi:account',       'Besucher'),
        ('mypage_user_storage',   user_mb,               'MyPage Speicher Benutzerdateien', 'mdi:harddisk', 'MB'),
        ('mypage_failed_logins',  failed_logins_24h(),   'MyPage Fehllogins (24h)', 'mdi:lock-alert',   'Versuche'),
        ('mypage_messages',       len(load_messages()),  'MyPage Kontaktnachrichten', 'mdi:email',      'Nachrichten'),
        ('mypage_members',        len(load_users()),     'MyPage Benutzer',         'mdi:account-multiple', 'Benutzer'),
        ('mypage_pending_approvals', pending,            'MyPage offene Freigaben', 'mdi:account-clock', 'Konten'),
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
    _update_pending_notification(pending)


_last_pending = -1


def _update_pending_notification(pending: int) -> None:
    """Stehende HA-Benachrichtigung, solange Selbst-Registrierungen auf Freigabe
    warten — nur bei Änderung der Anzahl (kein Zuspammen), Auflösung bei 0."""
    global _last_pending
    if not ha_notify_enabled() or pending == _last_pending:
        _last_pending = pending
        return
    if pending > 0:
        notify_ha('🔔 MyPage: Offene Freigaben',
                  f'{pending} selbst-registrierte(s) Konto/Konten warten auf deine Freigabe '
                  f'(Admin → Benutzer → „Freigeben").',
                  notification_id='mypage_pending_approvals')
    else:
        ha_dismiss('mypage_pending_approvals')
    _last_pending = pending


def _ha_sensors_async() -> None:
    """Sofortiger Sensor-/Benachrichtigungs-Push (z. B. bei Registrierung/Freigabe)."""
    if SUPERVISOR_TOKEN:
        threading.Thread(target=push_ha_sensors, daemon=True).start()


def _sensor_worker() -> None:
    if not SUPERVISOR_TOKEN:
        log.info("Kein SUPERVISOR_TOKEN — HA-Sensoren deaktiviert (Dev-Modus)")
        return
    while True:
        push_ha_sensors()
        time.sleep(120)


# ── Spiel-Sensoren (Live: wer spielt gerade was) ──────────────────────────────
_HA_GAME_LABELS = {'66': '66', '20ab': '20 AB', 'schwimmen': 'Schwimmen',
                   'maumau': 'Mau Mau', 'praesident': 'Präsident', 'jeopardy': 'Jeopardy',
                   'gluecksrad': 'Glücksrad'}


def _playing_overview() -> tuple[list, dict]:
    """Liefert (spieler, pro_spiel): wer spielt gerade welches Spiel."""
    players: list = []
    per_game: dict = {'66': [], '20ab': [], 'schwimmen': [], 'maumau': [], 'praesident': [], 'jeopardy': [], 'gluecksrad': []}
    for u in load_users():
        p = _user_playing(u['id'])
        if not p:
            continue
        name = u.get('name') or u.get('email') or u['id']
        players.append({'name': name, 'game': p['game'],
                        'game_label': _HA_GAME_LABELS.get(p['game'], p['game']),
                        'since': datetime.fromtimestamp(p['since'], timezone.utc).isoformat()})
        per_game.setdefault(p['game'], []).append(name)
    return players, per_game


def push_ha_games() -> None:
    """Meldet den Live-Spielstatus als Sensoren an Home Assistant."""
    if not SUPERVISOR_TOKEN:
        return
    players, per_game = _playing_overview()
    headers = {'Authorization': f'Bearer {SUPERVISOR_TOKEN}'}
    base = 'http://supervisor/core/api/states'
    try:
        http.post(f'{base}/sensor.mypage_spieler_aktiv', headers=headers, timeout=10,
                  json={'state': len(players),
                        'attributes': {'friendly_name': 'MyPage Spieler aktiv',
                                       'icon': 'mdi:cards-playing', 'unit_of_measurement': 'Spieler',
                                       'spieler': players,
                                       'pro_spiel': {_HA_GAME_LABELS[g]: len(v)
                                                     for g, v in per_game.items()}}})
        for g in ('66', '20ab', 'schwimmen', 'maumau', 'praesident', 'jeopardy', 'gluecksrad'):
            http.post(f'{base}/sensor.mypage_aktiv_{g}', headers=headers, timeout=10,
                      json={'state': len(per_game.get(g, [])),
                            'attributes': {'friendly_name': f'MyPage aktiv {_HA_GAME_LABELS[g]}',
                                           'icon': 'mdi:cards-playing-outline',
                                           'unit_of_measurement': 'Spieler',
                                           'spieler': per_game.get(g, [])}})
        http.post(f'{base}/binary_sensor.mypage_spielt_jemand', headers=headers, timeout=10,
                  json={'state': 'on' if players else 'off',
                        'attributes': {'friendly_name': 'MyPage spielt jemand',
                                       'icon': 'mdi:account-clock', 'count': len(players)}})
    except Exception as e:
        log.warning("HA-Spiel-Sensoren konnten nicht aktualisiert werden: %s", e)


def _ha_games_async() -> None:
    """Sofortiger Push (z. B. bei Spielstart/-ende), ohne den Request zu blockieren."""
    if SUPERVISOR_TOKEN:
        threading.Thread(target=push_ha_games, daemon=True).start()


def _ha_games_worker() -> None:
    if not SUPERVISOR_TOKEN:
        return
    while True:
        push_ha_games()
        time.sleep(30)  # Spielstatus ändert sich schneller als Besucherzahlen


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
    p['meta_de']   = _clean_str(raw.get('meta_de'), 300)
    p['meta_en']   = _clean_str(raw.get('meta_en'), 300)
    gallery = raw.get('gallery') or []
    if isinstance(gallery, list):
        p['gallery'] = [_clean_str(g, 500) for g in gallery if _clean_str(g, 500)][:30]
    else:
        p.setdefault('gallery', [])
    tags = raw.get('tags') or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(',')]
    p['tags'] = [_clean_str(t, 30) for t in tags if _clean_str(t, 30)][:8]
    p['published'] = bool(raw.get('published', True))
    p['members_only'] = bool(raw.get('members_only'))
    return p


def all_post_tags(site: dict) -> list:
    """Alle in sichtbaren Beiträgen vorkommenden Tags, alphabetisch, ohne Duplikate."""
    seen: dict[str, str] = {}
    for p in site.get('posts', []):
        if post_visible(p):
            for tag in p.get('tags', []):
                seen.setdefault(tag.lower(), tag)
    return [seen[k] for k in sorted(seen)]


def filter_posts(posts: list, query: str = '', tag: str = '') -> list:
    """Beiträge nach Volltext (Titel/Text, DE+EN) und/oder Tag filtern."""
    tag = (tag or '').strip().lower()
    if tag:
        posts = [p for p in posts if any(tag == x.lower() for x in p.get('tags', []))]
    q = (query or '').strip().lower()
    if q:
        def hit(p):
            hay = ' '.join([p.get('title_de', ''), p.get('title_en', ''),
                            p.get('text_de', ''), p.get('text_en', ''),
                            ' '.join(p.get('tags', []))]).lower()
            return all(word in hay for word in q.split())
        posts = [p for p in posts if hit(p)]
    return posts


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


def _albums_for_public(site: dict, viewer_member: bool = False) -> list:
    """Alben mit Bildern; Bild-URLs auf die /album-img/-Route umgeschrieben
    (liefert je nach Einstellung Original oder Wasserzeichen-Version).
    Mitglieder-only-Alben werden für Gäste gesperrt (ohne Bild-URLs)."""
    out = []
    for a in site.get('albums', []):
        imgs = a.get('images') or []
        if not imgs:
            continue
        if a.get('members_only') and not viewer_member:
            # gesperrt: keine Bild-URLs ausliefern, nur Titel + Anzahl
            out.append({**a, 'images': [], 'locked': True, 'photo_count': len(imgs)})
            continue
        mapped = [('/album-img/' + u.removeprefix('/uploads/')) if u.startswith('/uploads/') else u
                  for u in imgs]
        out.append({**a, 'images': mapped, 'locked': False, 'photo_count': len(imgs)})
    return out


def _normalize_album(raw: dict, existing: dict | None = None) -> dict:
    a = existing or {'id': uuid.uuid4().hex[:12]}
    a['title_de'] = _clean_str(raw.get('title_de'), 120)
    a['title_en'] = _clean_str(raw.get('title_en'), 120)
    a['desc_de']  = _clean_str(raw.get('desc_de'), 1000)
    a['desc_en']  = _clean_str(raw.get('desc_en'), 1000)
    a['members_only'] = bool(raw.get('members_only'))
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


# Slugs, die nicht als eigene Seite vergeben werden dürfen (Kollision mit echten Routen)
RESERVED_SLUGS = {
    'blog', 'bereich', 'p', 'api', 'uploads', 'fonts', 'cards', 'album-img',
    'impressum', 'datenschutz', 'contact', 'newsletter', 'sitemap', 'sitemap.xml',
    'robots', 'robots.txt', 'feed', 'feed.xml', 'manifest.json', 'sw.js',
    'favicon.ico', 'icon.png', 'health', 'set-lang', 'seite', 'preview', 'static',
}


def _slugify(s: str) -> str:
    """Freitext → URL-tauglicher Slug (a-z, 0-9, Bindestrich)."""
    s = (s or '').strip().lower()
    repl = {'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss'}
    for a, b in repl.items():
        s = s.replace(a, b)
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s[:60]


def _normalize_page(raw: dict, existing: dict | None = None) -> dict:
    p = existing or {'id': uuid.uuid4().hex[:12]}
    p['title_de'] = _clean_str(raw.get('title_de'), 120)
    p['title_en'] = _clean_str(raw.get('title_en'), 120)
    p['body_de']  = _clean_str(raw.get('body_de'), 50000)
    p['body_en']  = _clean_str(raw.get('body_en'), 50000)
    p['meta_de']  = _clean_str(raw.get('meta_de'), 300)
    p['meta_en']  = _clean_str(raw.get('meta_en'), 300)
    p['nav']      = bool(raw.get('nav', True))
    p['visible']  = bool(raw.get('visible', True))
    p['members_only'] = bool(raw.get('members_only'))
    return p


def _page_slug(site: dict, raw: dict, page_id: str) -> str:
    """Eindeutigen, gültigen Slug ermitteln (aus Eingabe oder Titel abgeleitet)."""
    slug = _slugify(raw.get('slug') or raw.get('title_de') or raw.get('title_en') or '')
    if not slug or slug in RESERVED_SLUGS:
        slug = 'seite-' + page_id[:6]
    base, n = slug, 2
    taken = {p['slug'] for p in site.get('pages', []) if p.get('id') != page_id}
    while slug in taken or slug in RESERVED_SLUGS:
        slug = f'{base}-{n}'
        n += 1
    return slug


def _find_page(site: dict, slug: str) -> dict | None:
    return next((p for p in site.get('pages', []) if p.get('slug') == slug), None)


def _nav_pages(site: dict, loc) -> list:
    """Sichtbare Seiten, die in der Navigation erscheinen sollen."""
    out = []
    for p in site.get('pages', []):
        if p.get('visible') and p.get('nav'):
            label = loc(p, 'title')
            if label:
                out.append({'href': '/seite/' + p['slug'], 'label': label})
    return out


# ── Formular-Baukasten ────────────────────────────────────────────────────────

FORM_FIELD_TYPES = {'text', 'textarea', 'email', 'tel', 'number', 'date',
                    'select', 'radio', 'checkbox'}


def _normalize_field(raw: dict) -> dict:
    f = {'id': _clean_str(raw.get('id'), 20) or uuid.uuid4().hex[:8]}
    ftype = raw.get('type')
    f['type'] = ftype if ftype in FORM_FIELD_TYPES else 'text'
    f['label_de'] = _clean_str(raw.get('label_de'), 120)
    f['label_en'] = _clean_str(raw.get('label_en'), 120)
    f['placeholder_de'] = _clean_str(raw.get('placeholder_de'), 120)
    f['placeholder_en'] = _clean_str(raw.get('placeholder_en'), 120)
    f['required'] = bool(raw.get('required'))
    opts = raw.get('options') or []
    if isinstance(opts, str):
        opts = opts.split('\n')
    f['options'] = [_clean_str(o, 100) for o in opts if _clean_str(o, 100)][:40]
    return f


def _normalize_form(raw: dict, existing: dict | None = None) -> dict:
    fm = existing or {'id': uuid.uuid4().hex[:12]}
    fm['title_de']   = _clean_str(raw.get('title_de'), 120)
    fm['title_en']   = _clean_str(raw.get('title_en'), 120)
    fm['intro_de']   = _clean_str(raw.get('intro_de'), 5000)
    fm['intro_en']   = _clean_str(raw.get('intro_en'), 5000)
    fm['success_de'] = _clean_str(raw.get('success_de'), 1000)
    fm['success_en'] = _clean_str(raw.get('success_en'), 1000)
    fm['enabled']    = bool(raw.get('enabled', True))
    fm['nav']        = bool(raw.get('nav', False))
    fm['notify']     = bool(raw.get('notify', True))
    fields = raw.get('fields') or []
    fm['fields'] = [_normalize_field(x) for x in fields if isinstance(x, dict)][:40]
    return fm


def _form_slug(site: dict, raw: dict, form_id: str) -> str:
    slug = _slugify(raw.get('slug') or raw.get('title_de') or raw.get('title_en') or '')
    if not slug:
        slug = 'formular-' + form_id[:6]
    base, n = slug, 2
    taken = {f['slug'] for f in site.get('forms', []) if f.get('id') != form_id}
    while slug in taken:
        slug = f'{base}-{n}'
        n += 1
    return slug


def _find_form(site: dict, slug: str) -> dict | None:
    return next((f for f in site.get('forms', []) if f.get('slug') == slug), None)


def _nav_forms(site: dict, loc) -> list:
    """Aktive Formulare mit gesetztem Navi-Schalter."""
    out = []
    for f in site.get('forms', []):
        if f.get('enabled') and f.get('nav'):
            label = loc(f, 'title')
            if label:
                out.append({'href': '/formular/' + f['slug'], 'label': label})
    return out


def _nav_links(site: dict, loc) -> list:
    """Navi-Einträge für eigene Seiten und Formulare."""
    return _nav_pages(site, loc) + _nav_forms(site, loc)


@public_app.context_processor
def _inject_banner():
    """Stellt das Ankündigungs-Banner allen öffentlichen Templates bereit."""
    try:
        d = load_site().get('design', {})
        if not d.get('banner_enabled'):
            return {'banner': None}
        loc = _loc_factory(detect_language(request))
        text = loc(d, 'banner_text')
        if not text:
            return {'banner': None}
        key = hashlib.sha256((text + (d.get('banner_link_url') or '')).encode()).hexdigest()[:12]
        return {'banner': {
            'text': text,
            'link_url': d.get('banner_link_url', ''),
            'link_label': loc(d, 'banner_link_label'),
            'dismissible': bool(d.get('banner_dismissible', True)),
            'key': key,
        }}
    except Exception:
        return {'banner': None}


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
                log_audit('admin_login')
                resp = make_response(redirect(url_for('admin_index')))
                resp.set_cookie('session', token, httponly=True,
                                samesite='Lax', max_age=hours * 3600)
                return resp
            record_failed_attempt(ip)
            log_audit('admin_login_failed', uname)
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
    site = load_site()
    pv = load_stats().get('posts', {})
    for p in site.get('posts', []):
        p['views'] = pv.get(p.get('id'), 0)
    return jsonify(site)


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
    log_audit('settings_profile')
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
    if raw.get('reveal_effect') in ('off', 'fade', 'slide', 'zoom', 'blur'):
        d['reveal_effect'] = raw['reveal_effect']
    if 'card_deck' in raw:
        # nur Decks zulassen, die als Ordner mitgeliefert sind
        slug = secure_filename(str(raw['card_deck']))
        if slug and (CARDS_DIR / slug).is_dir():
            d['card_deck'] = slug
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
    for flag in ('show_counter', 'show_nav', 'contact_enabled', 'comments_enabled',
                 'registration_enabled', 'newsletter_enabled', 'maintenance', 'indexnow',
                 'allow_indexing', 'easter_eggs', 'mini_games', 'reveal_stagger',
                 'banner_enabled', 'banner_dismissible'):
        if flag in raw:
            d[flag] = bool(raw[flag])
    if 'banner_link_url' in raw:
        bl = _clean_str(raw['banner_link_url'], 500)
        d['banner_link_url'] = bl if bl.startswith(('http://', 'https://', '/')) or not bl else ''
    if 'registration_quota_mb' in raw:
        d['registration_quota_mb'] = max(1, min(100000, int(raw.get('registration_quota_mb') or 500)))
    for k, maxlen in (('site_title', 80), ('footer_text', 300), ('favicon', 500),
                      ('maintenance_text_de', 1000), ('maintenance_text_en', 1000),
                      ('egg_message', 200), ('egg_tagline', 200),
                      ('banner_text_de', 200), ('banner_text_en', 200),
                      ('banner_link_label_de', 60), ('banner_link_label_en', 60),
                      ('meta_description_de', 300), ('meta_description_en', 300)):
        if k in raw:
            d[k] = _clean_str(raw[k], maxlen)
    if d.get('indexnow'):
        _indexnow_key(site)   # Schlüssel beim Aktivieren bereitstellen (speichert ggf.)
    save_site(site)
    log_audit('settings_design')
    return jsonify({'ok': True})


@admin_app.route('/api/indexnow/ping', methods=['POST'])
def api_indexnow_ping():
    err = _api_auth()
    if err:
        return err
    site = load_site()
    if not site['design'].get('indexnow'):
        return jsonify({'error': 'disabled'}), 400
    base = (site['design'].get('public_url') or '').rstrip('/')
    if not base.startswith(('http://', 'https://')):
        return jsonify({'error': 'no_url'}), 400
    urls = _public_url_list(site, base)
    indexnow_submit(urls)
    return jsonify({'ok': True, 'count': len(urls)})


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
    for k in ('timeline_title_de', 'timeline_title_en'):
        if k in raw:
            sec[k] = _clean_str(raw[k], 60)
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
    if isinstance(raw.get('tips'), list):
        out = []
        for e in raw['tips'][:100]:
            if not isinstance(e, dict):
                continue
            de = _clean_str(e.get('text_de'), 600)
            en = _clean_str(e.get('text_en'), 600)
            if not (de or en):
                continue
            tid = _clean_str(e.get('id'), 32) or uuid.uuid4().hex[:12]
            out.append({'id': tid, 'text_de': de, 'text_en': en})
        sec['tips'] = out
        # Statistik verwaister Tipps (gelöscht) aufräumen
        valid = {t['id'] for t in out}
        site['tips_stats'] = {k: v for k, v in (site.get('tips_stats') or {}).items() if k in valid}
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
    if isinstance(raw.get('members_sections'), list):
        site['members_sections'] = [k for k in raw['members_sections'] if isinstance(k, str) and k in SECTION_KEYS]
    if raw.get('tips_rotation') in ('daily', 'weekly'):
        site['tips_rotation'] = raw['tips_rotation']
    if 'tips_random' in raw:
        site['tips_random'] = bool(raw['tips_random'])
    if 'album_protect' in raw:
        site['album_protect'] = bool(raw['album_protect'])
    if 'watermark_text' in raw:
        site['watermark_text'] = _clean_str(raw['watermark_text'], 80)
    save_site(site)
    log_audit('settings_sections')
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


@admin_app.route('/api/comments')
def api_comments():
    """Alle Blog-Kommentare (zum Moderieren), neueste zuerst, inkl. Beitragstitel."""
    err = _api_auth()
    if err:
        return err
    site = load_site()
    titles = {p.get('id'): (p.get('title_de') or p.get('title_en') or p.get('id'))
              for p in site.get('posts', [])}
    out = []
    for pid, thread in load_comments().items():
        for c in thread.get('comments', []):
            out.append({**c, 'pid': pid, 'post_title': titles.get(pid, pid)})
    out.sort(key=lambda c: c.get('ts', 0), reverse=True)
    return jsonify({'comments': out[:500]})


@admin_app.route('/api/comments/<pid>/<cid>', methods=['DELETE'])
def api_comment_delete(pid: str, cid: str):
    err = _api_auth()
    if err:
        return err
    data = load_comments()
    thread = data.get(pid)
    if thread:
        kept = [c for c in thread.get('comments', []) if c.get('id') != cid]
        if len(kept) != len(thread.get('comments', [])):
            thread['comments'] = kept
            save_comments(data)
            return jsonify({'ok': True})
    return jsonify({'error': 'not found'}), 404


@admin_app.route('/api/audit')
def api_audit():
    """Admin-Audit-Log (neueste zuerst) zur Anzeige im Panel."""
    err = _api_auth()
    if err:
        return err
    return jsonify({'audit': list(reversed(load_audit()))[:300]})


@admin_app.route('/api/subscribers')
def api_subscribers():
    err = _api_auth()
    if err:
        return err
    subs = load_subscribers()
    out = [{'id': s['id'], 'email': s['email'], 'confirmed': bool(s.get('confirmed')),
            'ts': s.get('ts', 0)}
           for s in sorted(subs, key=lambda s: s.get('ts', 0), reverse=True)]
    return jsonify({'subscribers': out, 'total': len(subs),
                    'confirmed': sum(1 for s in subs if s.get('confirmed'))})


@admin_app.route('/api/subscribers/<sid>', methods=['DELETE'])
def api_subscriber_delete(sid: str):
    err = _api_auth()
    if err:
        return err
    subs = load_subscribers()
    new = [s for s in subs if s['id'] != sid]
    if len(new) == len(subs):
        return jsonify({'error': 'not found'}), 404
    save_subscribers(new)
    return jsonify({'ok': True})


@admin_app.route('/api/newsletter/send', methods=['POST'])
def api_newsletter_send():
    err = _api_auth()
    if err:
        return err
    if not smtp_configured():
        return jsonify({'error': 'no smtp'}), 400
    raw = request.get_json(silent=True) or {}
    subject = _clean_str(raw.get('subject'), 150)
    body = _clean_str(raw.get('body'), 20000)
    if not subject or not body:
        return jsonify({'error': 'missing'}), 400
    confirmed = [s for s in load_subscribers() if s.get('confirmed')]
    if not confirmed:
        return jsonify({'error': 'no recipients'}), 400
    body_html = render_md(body)
    threading.Thread(target=send_newsletter_batch, args=(subject, body_html, confirmed),
                     daemon=True).start()
    log_audit('newsletter_send', f'{len(confirmed)} Empfänger: {subject}')
    log.info("Newsletter '%s' an %d Empfänger ausgelöst", subject, len(confirmed))
    return jsonify({'ok': True, 'count': len(confirmed)})


@admin_app.route('/api/backup')
def api_backup():
    err = _api_auth()
    if err:
        return err
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for name in ('site.json', 'stats.json', 'messages.json', 'users.json',
                     'comments.json', 'audit.json', 'subscribers.json'):
            p = Path(_DATA) / name
            if p.is_file():
                z.write(p, name)
        for f in UPLOADS_DIR.iterdir():
            if f.is_file():
                z.write(f, 'uploads/' + f.name)
        # Kartenspiel-Spielstände + Verlauf (66_<uid>.json / 66hist_<uid>.json)
        if GAMES_DIR.is_dir():
            for f in sorted(GAMES_DIR.iterdir()):
                if f.is_file() and _GAME_FILE_RE.match(f.name):
                    z.write(f, 'games/' + f.name)
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
                if member in ('site.json', 'stats.json', 'messages.json', 'users.json',
                              'comments.json', 'audit.json', 'subscribers.json'):
                    target = safe_under(Path(_DATA), member)
                elif member.startswith('uploads/'):
                    name = secure_filename(Path(member).name)
                    if not name or Path(name).suffix.lower() not in ALLOWED_UPLOAD_EXT:
                        continue
                    target = safe_under(UPLOADS_DIR, name)
                elif member.startswith('games/'):
                    name = Path(member).name
                    if not _GAME_FILE_RE.match(name):
                        continue
                    try:
                        json.loads(z.read(member))  # muss valides JSON sein
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
                    target = safe_under(GAMES_DIR, name)
                else:
                    continue
                if target is None:
                    continue
                with open(target, 'wb') as dst:
                    dst.write(z.read(member))
                restored += 1
    except (zipfile.BadZipFile, json.JSONDecodeError, KeyError):
        return jsonify({'error': 'invalid backup'}), 400
    log_audit('restore', f'{restored} Datei(en)')
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
    log_audit('settings_legal')
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
    proj = _normalize_project(raw)
    site['projects'].append(proj)
    save_site(site)
    _indexnow_ping_project(site, proj)
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
    if request.method == 'PUT':
        _indexnow_ping_project(site, site['projects'][idx])
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
    post = _normalize_post(raw)
    site.setdefault('posts', []).append(post)
    save_site(site)
    _indexnow_ping_post(site, post)
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
    if request.method == 'PUT':
        _indexnow_ping_post(site, posts[idx])
    return jsonify({'ok': True})


@admin_app.route('/api/pages', methods=['POST'])
def api_page_create():
    err = _api_auth()
    if err:
        return err
    raw = request.get_json(silent=True) or {}
    if not (_clean_str(raw.get('title_de'), 120) or _clean_str(raw.get('title_en'), 120)):
        return jsonify({'error': 'title required'}), 400
    site = load_site()
    page = _normalize_page(raw)
    page['slug'] = _page_slug(site, raw, page['id'])
    site.setdefault('pages', []).append(page)
    save_site(site)
    return jsonify({'ok': True, 'slug': page['slug']})


@admin_app.route('/api/pages/<pid>', methods=['PUT', 'DELETE'])
def api_page_edit(pid: str):
    err = _api_auth()
    if err:
        return err
    site = load_site()
    pages = site.setdefault('pages', [])
    idx = next((i for i, p in enumerate(pages) if p.get('id') == pid), None)
    if idx is None:
        return jsonify({'error': 'not found'}), 404
    if request.method == 'DELETE':
        pages.pop(idx)
        save_site(site)
        return jsonify({'ok': True})
    raw = request.get_json(silent=True) or {}
    if not (_clean_str(raw.get('title_de'), 120) or _clean_str(raw.get('title_en'), 120)):
        return jsonify({'error': 'title required'}), 400
    pages[idx] = _normalize_page(raw, pages[idx])
    pages[idx]['slug'] = _page_slug(site, raw, pid)
    save_site(site)
    return jsonify({'ok': True, 'slug': pages[idx]['slug']})


@admin_app.route('/api/pages/reorder', methods=['POST'])
def api_pages_reorder():
    err = _api_auth()
    if err:
        return err
    order = (request.get_json(silent=True) or {}).get('order') or []
    if not isinstance(order, list):
        return jsonify({'error': 'invalid'}), 400
    site = load_site()
    pages = site.get('pages', [])
    pos = {pid: i for i, pid in enumerate(order)}
    pages.sort(key=lambda p: pos.get(p.get('id'), len(pos)))
    save_site(site)
    return jsonify({'ok': True})


@admin_app.route('/api/forms', methods=['POST'])
def api_form_create():
    err = _api_auth()
    if err:
        return err
    raw = request.get_json(silent=True) or {}
    if not (_clean_str(raw.get('title_de'), 120) or _clean_str(raw.get('title_en'), 120)):
        return jsonify({'error': 'title required'}), 400
    site = load_site()
    form = _normalize_form(raw)
    form['slug'] = _form_slug(site, raw, form['id'])
    site.setdefault('forms', []).append(form)
    save_site(site)
    return jsonify({'ok': True, 'slug': form['slug']})


@admin_app.route('/api/forms/<fid>', methods=['PUT', 'DELETE'])
def api_form_edit(fid: str):
    err = _api_auth()
    if err:
        return err
    site = load_site()
    forms = site.setdefault('forms', [])
    idx = next((i for i, f in enumerate(forms) if f.get('id') == fid), None)
    if idx is None:
        return jsonify({'error': 'not found'}), 404
    if request.method == 'DELETE':
        forms.pop(idx)
        save_site(site)
        return jsonify({'ok': True})
    raw = request.get_json(silent=True) or {}
    if not (_clean_str(raw.get('title_de'), 120) or _clean_str(raw.get('title_en'), 120)):
        return jsonify({'error': 'title required'}), 400
    forms[idx] = _normalize_form(raw, forms[idx])
    forms[idx]['slug'] = _form_slug(site, raw, fid)
    save_site(site)
    return jsonify({'ok': True, 'slug': forms[idx]['slug']})


@admin_app.route('/api/forms/reorder', methods=['POST'])
def api_forms_reorder():
    err = _api_auth()
    if err:
        return err
    order = (request.get_json(silent=True) or {}).get('order') or []
    if not isinstance(order, list):
        return jsonify({'error': 'invalid'}), 400
    site = load_site()
    forms = site.get('forms', [])
    pos = {fid: i for i, fid in enumerate(order)}
    forms.sort(key=lambda f: pos.get(f.get('id'), len(pos)))
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
                    'playing': _user_playing(u['id']),
                    'games_enabled': u.get('games_enabled', True),
                    'self_registered': bool(u.get('self_registered')),
                    'verified': u.get('verified', True),
                    'approved': u.get('approved', True),
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
    log_audit('settings_member')
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
    log_audit('user_create', email)
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
        log_audit('user_delete', user['email'])
        log.info("Benutzer '%s' gelöscht", user['email'])
        return jsonify({'ok': True})
    raw = request.get_json(silent=True) or {}
    mail_sent = False
    if 'quota_mb' in raw:
        user['quota_mb'] = max(1, min(100000, int(raw.get('quota_mb') or 500)))
        log_audit('user_quota', f"{user['email']} → {user['quota_mb']} MB")
    if 'login_message' in raw:
        user['login_message'] = _clean_str(raw.get('login_message'), 2000)
    if 'games_enabled' in raw:
        user['games_enabled'] = bool(raw['games_enabled'])
        log_audit('user_games', f"{user['email']}: {'an' if user['games_enabled'] else 'aus'}")
    if 'approved' in raw:
        was = user.get('approved', True)
        user['approved'] = bool(raw['approved'])
        # Freigabe eines selbst-registrierten Kontos → Aktivierungs-Mail
        if user['approved'] and not was and user.get('verified') and smtp_configured():
            threading.Thread(target=send_activated_email, args=(dict(user),), daemon=True).start()
        if user['approved'] and not was:
            log_audit('user_approve', user['email'])
        _ha_sensors_async()  # „offene Freigaben" sofort neu zählen
    password = str(raw.get('password') or '')
    if password:
        if len(password) < 8:
            return jsonify({'error': 'password too short'}), 400
        user['pw_hash'] = generate_password_hash(password)
        log_audit('user_password', user['email'])
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
    log_audit('user_resend', user['email'])
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


_ADMIN_GAMES = ('66', '20ab', 'schwimmen', 'maumau', 'praesident', 'jeopardy', 'gluecksrad')


def _user_playing(uid: str):
    """Live-Status: spielt das Mitglied gerade (Heartbeat < Timeout)? Welches Spiel?"""
    for game in _ADMIN_GAMES:
        if _sess_active(game, uid):
            s = _game_sessions.get((game, uid)) or {}
            return {'game': game, 'since': int(s.get('started') or s.get('last_seen') or 0)}
    return None


def _game_stats(uid: str) -> list:
    """Pro Spiel: gespielte Partien, Siege (Spieler), zuletzt gespielt — aus dem Verlauf."""
    srcs = (('66', load_game66_history(uid)),
            ('20ab', _ng_history('20ab', uid)),
            ('schwimmen', _ng_history('schwimmen', uid)),
            ('maumau', _ng_history('maumau', uid)),
            ('praesident', _ng_history('praesident', uid)),
            ('jeopardy', _ng_history('jeopardy', uid)),
            ('gluecksrad', _ng_history('gluecksrad', uid)))
    out = []
    for game, hist in srcs:
        out.append({'game': game, 'played': len(hist),
                    'wins': sum(1 for h in hist if h.get('winner') in ('p', 0)),
                    'last': max((h.get('ts', 0) for h in hist), default=0)})
    return out


@admin_app.route('/api/users/<uid>/games')
def api_user_games(uid: str):
    err = _api_auth()
    if err:
        return err
    user = _admin_get_user(uid)
    if user is None:
        return jsonify({'error': 'not found'}), 404
    sessions = _gsess_sweep(uid)  # Timeouts nachschließen, aktuelle Liste holen
    return jsonify({'playing': _user_playing(uid),
                    'stats': _game_stats(uid),
                    'sessions': list(reversed(sessions))[:100]})


@admin_app.route('/api/users/playing')
def api_users_playing():
    """Leichtgewichtig: nur der Live-Spielstatus aller Mitglieder (für Polling)."""
    err = _api_auth()
    if err:
        return err
    return jsonify({'playing': {u['id']: _user_playing(u['id']) for u in load_users()}})


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
        log_audit('settings_storage', sub or '(Standard)')
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
    for p in site.get('pages', []):
        if p.get('visible'):
            pages[f"seite/{p['slug']}/index.html"] = f"/seite/{p['slug']}"
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
            # EXIF-Orientierung anwenden (sonst erscheinen Handy-Hochkant-Fotos gedreht)
            # und damit zugleich Metadaten verwerfen (GPS/Kamera) — Datenschutz.
            img = ImageOps.exif_transpose(img)
            img.thumbnail((1600, 1600))
            if img.mode not in ('RGB', 'RGBA'):
                img = img.convert('RGBA' if 'A' in img.getbands() else 'RGB')
            name = uuid.uuid4().hex + '.webp'
            target = safe_under(UPLOADS_DIR, name)
            if target is None:
                abort(400)
            # ohne exif=... → das neu kodierte WebP enthält keine Metadaten mehr
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


def _unused_uploads(site: dict):
    """Hochgeladene Dateien, die nirgends mehr in site.json referenziert sind.

    Alle Uploads (Bilder in Seiten/Beiträgen/Projekten/Alben, Avatar, Favicon)
    werden in site.json als `/uploads/<name>` gespeichert. Dateinamen sind
    eindeutige UUIDs, daher ist ein Vorkommen-Scan über den JSON-Text sicher.
    """
    blob = json.dumps(site, ensure_ascii=False)
    orphans, total = [], 0
    for f in UPLOADS_DIR.iterdir():
        if f.is_file() and f.name not in blob:
            orphans.append(f)
            total += f.stat().st_size
    return orphans, total


@admin_app.route('/api/uploads/unused')
def api_uploads_unused():
    err = _api_auth()
    if err:
        return err
    orphans, total = _unused_uploads(load_site())
    return jsonify({'count': len(orphans), 'size_mb': round(total / 1048576, 1)})


@admin_app.route('/api/uploads/cleanup', methods=['POST'])
def api_uploads_cleanup():
    err = _api_auth()
    if err:
        return err
    orphans, total = _unused_uploads(load_site())
    removed = 0
    for f in orphans:
        try:
            f.unlink()
            removed += 1
        except OSError as e:
            log.warning("Aufräumen: %s konnte nicht gelöscht werden: %s", f.name, e)
    if removed:
        log_audit('uploads_cleanup', f'{removed} Datei(en)')
    return jsonify({'ok': True, 'removed': removed, 'freed_mb': round(total / 1048576, 1)})


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
        'pages':     top_pages(load_site(), stats.get('log', [])),
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


@public_app.route('/cards/<deck>/<path:filename>')
def public_cards(deck: str, filename: str):
    """Kartendeck-Grafiken (mitgeliefert, gemeinfrei) — pro Deck ein Unterordner."""
    safe_deck = secure_filename(deck)
    safe = secure_filename(filename)
    base = safe_under(CARDS_DIR, safe_deck)
    if base is None or not base.is_dir():
        abort(404)
    target = safe_under(base, safe)
    if target is None or not target.is_file():
        abort(404)
    return send_from_directory(base, safe, max_age=2592000)  # 30 Tage


@public_app.route('/bereich/jeopardy/theme.m4a')
def jeopardy_theme():
    """Optionale Jeopardy-Hintergrundmusik. NICHT mitgeliefert (Urheberrecht):
    Datei `jeopardy_theme.m4a` im Add-on-Config-Ordner ablegen, dann spielt sie.
    Fester Dateiname → kein Path-Traversal."""
    _require_member()
    path = Path(_DATA) / 'jeopardy_theme.m4a'
    if not path.is_file():
        abort(404)
    return send_from_directory(path.parent, path.name, max_age=86400)


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


def _public_url_list(site: dict, base: str) -> list:
    """Alle öffentlich indexierbaren URLs (Startseite, Projekt-Detailseiten, Blog)."""
    urls = [base + '/']
    urls += [f"{base}/seite/{p['slug']}" for p in site.get('pages', []) if p.get('visible')]
    urls += [f"{base}/p/{p['id']}" for p in site['projects'] if _has_detail(p) and project_visible(p)]
    posts = sorted_posts(site, public_only=True)
    if posts:
        urls.append(base + '/blog')
        urls += [f"{base}/blog/{p['id']}" for p in posts]
    return urls


def _indexnow_key(site: dict) -> str:
    """Liefert den IndexNow-Schlüssel (erzeugt ihn bei Bedarf und speichert)."""
    key = site.get('indexnow_key') or ''
    if not re.fullmatch(r'[a-f0-9]{32}', key):
        key = uuid.uuid4().hex
        site['indexnow_key'] = key
        save_site(site)
    return key


def indexnow_submit(urls: list) -> None:
    """Geänderte URLs an Bing (IndexNow) melden — nicht blockierend."""
    site = load_site()
    if not site['design'].get('indexnow') or not site['design'].get('allow_indexing', True):
        return
    base = (site['design'].get('public_url') or '').rstrip('/')
    if not base.startswith(('http://', 'https://')):
        return  # ohne öffentliche URL nicht möglich
    key = _indexnow_key(site)
    url_list = [u for u in dict.fromkeys(urls) if u][:1000]
    if not url_list:
        return
    payload = {
        'host': urlparse(base).netloc,
        'key': key,
        'keyLocation': f'{base}/{key}.txt',
        'urlList': url_list,
    }

    # Bedeutung der IndexNow-Statuscodes (ASCII, fuer ueberall sauberes Log)
    _IN_MSG = {
        200: 'OK - akzeptiert', 202: 'angenommen (Key wird noch geprueft)',
        400: 'ungueltige Anfrage', 403: 'Key nicht gueltig (Key-Datei erreichbar?)',
        422: 'URLs passen nicht zur Domain/Key', 429: 'zu viele Anfragen',
    }
    log.info("IndexNow -> Bing: sende %d URL(s) (%s ...)", len(url_list), url_list[0])

    def _worker():
        try:
            r = http.post('https://www.bing.com/indexnow', json=payload, timeout=10)
            note = _IN_MSG.get(r.status_code, '')
            if r.status_code in (200, 202):
                log.info("IndexNow -> Bing: %d URL(s) gemeldet (HTTP %s - %s)", len(url_list), r.status_code, note)
            else:
                log.warning("IndexNow -> Bing: HTTP %s - %s %s", r.status_code, note, (r.text or '')[:160].strip())
        except Exception as e:
            log.warning("IndexNow-Submit fehlgeschlagen: %s", e)

    threading.Thread(target=_worker, daemon=True).start()


def _indexnow_ping_post(site: dict, post: dict) -> None:
    base = (site['design'].get('public_url') or '').rstrip('/')
    if base.startswith(('http://', 'https://')) and post_visible(post):
        indexnow_submit([base + '/', base + '/blog', f"{base}/blog/{post['id']}"])


def _indexnow_ping_project(site: dict, proj: dict) -> None:
    base = (site['design'].get('public_url') or '').rstrip('/')
    if base.startswith(('http://', 'https://')) and _has_detail(proj) and project_visible(proj):
        indexnow_submit([base + '/', f"{base}/p/{proj['id']}"])


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
    site = load_site()
    if not site['design'].get('allow_indexing', True):
        return ('User-agent: *\nDisallow: /\n', 200, {'Content-Type': 'text/plain'})
    return (f'User-agent: *\nAllow: /\nSitemap: {_base_url()}/sitemap.xml\n',
            200, {'Content-Type': 'text/plain'})


@public_app.route('/<key>.txt')
def indexnow_keyfile(key: str):
    """IndexNow-Verifizierungsdatei: liefert den Schlüssel als Klartext."""
    site = load_site()
    stored = site.get('indexnow_key') or ''
    # Nur den serverseitig gespeicherten Schlüssel zurückgeben (nie den Request-Wert),
    # damit kein Benutzereingabe-Taint in die Antwort fließt.
    if re.fullmatch(r'[a-f0-9]{32}', key or '') and key == stored:
        return stored, 200, {'Content-Type': 'text/plain'}
    abort(404)


@public_app.route('/api/slot', methods=['GET', 'POST'])
def api_slot():
    """Progressiver Slot-Jackpot (für alle Besucher gemeinsam): jeder Spin +1, bei 777 zurück auf 500."""
    with _slot_lock:
        site = load_site()
        jp = int(site.get('slot_jackpot') or 500)
        if request.method == 'POST':
            data = request.get_json(silent=True) or {}
            if data.get('win'):
                site['slot_jackpot'] = 500
                save_site(site)
                return jsonify({'jackpot': 500, 'won': jp})
            jp = min(jp + 1, 100_000_000)
            site['slot_jackpot'] = jp
            save_site(site)
    return jsonify({'jackpot': jp})


# ── 66 / Schnapsen (Mitglieder-Spiel, server-autoritativ) ──────────────────────

def _game66_path(uid: str) -> Path | None:
    if not _UID_RE.match(uid or ''):
        return None
    return safe_under(GAMES_DIR, f'66_{uid}.json')


def load_game66(uid: str) -> dict | None:
    p = _game66_path(uid)
    if p is None:
        return None
    try:
        with open(p, encoding='utf-8') as f:
            st = json.load(f)
        return st if game_66.is_valid_state(st) else None
    except FileNotFoundError:
        return None
    except Exception as e:
        log.warning("66-Spielstand defekt (%s): %s", uid[:8], e)
        return None


def save_game66(uid: str, state: dict) -> None:
    p = _game66_path(uid)
    if p is None:
        return
    tmp = p.with_suffix('.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False)
    os.replace(tmp, p)  # atomar ersetzen → kein halb geschriebener Stand


GAME66_HISTORY_MAX = 50


def _game66_hist_path(uid: str) -> Path | None:
    if not _UID_RE.match(uid or ''):
        return None
    return safe_under(GAMES_DIR, f'66hist_{uid}.json')


def load_game66_history(uid: str) -> list:
    p = _game66_hist_path(uid)
    if p is None:
        return []
    try:
        with open(p, encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except FileNotFoundError:
        return []
    except Exception as e:
        log.warning("66-Verlauf defekt (%s): %s", uid[:8], e)
        return []


def append_game66_history(uid: str, entry: dict) -> None:
    p = _game66_hist_path(uid)
    if p is None:
        return
    hist = load_game66_history(uid)
    hist.append(entry)
    hist = hist[-GAME66_HISTORY_MAX:]
    tmp = p.with_suffix('.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(hist, f, ensure_ascii=False)
    os.replace(tmp, p)


def _record_match_if_over(uid: str, st: dict) -> bool:
    """Beendetes Match einmalig in den Verlauf schreiben. True, wenn aufgezeichnet."""
    if st.get('status') != 'match_over' or st.get('recorded'):
        return False
    st['recorded'] = True
    res = st.get('result') or {}
    append_game66_history(uid, {
        'ts': int(datetime.now(timezone.utc).timestamp()),
        'winner': res.get('winner'),
        'bummerl': dict(st.get('bummerl', {})),
        'rules': st.get('rules', 'standard'),
        'level': st.get('level', 'medium'),
        'deals': st.get('deal_no', 0),
    })
    return True


def _require_member():
    member = current_member(request)
    if member is None:
        abort(403)
    if member.get('games_enabled', True) is False:
        abort(403)  # Spiele für dieses Mitglied vom Admin deaktiviert
    return member


# ── Cross-Device-Session-Schutz (pro Mitglied & Spiel, in-memory) ──────────────
# Verhindert paralleles Spielen desselben Spielstands auf mehreren Geräten.
# Schlüssel: (spiel, uid). Token = 128-Bit-Hex. Timeout 30 s ohne Heartbeat.
_game_sessions: dict = {}
_sess_lock = threading.Lock()
_GAME_SESSION_TIMEOUT = 30  # Sekunden


def _sess_active(game: str, uid: str) -> bool:
    s = _game_sessions.get((game, uid))
    return bool(s and s.get('token')
                and (time.time() - s.get('last_seen', 0)) < _GAME_SESSION_TIMEOUT)


def _sess_claim(game: str, uid: str, force: bool = False) -> dict:
    with _sess_lock:
        active = _sess_active(game, uid)
        if active and not force:
            return {'locked': True}
        now = int(time.time())
        prev = _game_sessions.get((game, uid))
        takeover = bool(prev and active and force)
        token = secrets.token_hex(16)
        _game_sessions[(game, uid)] = {'token': token, 'last_seen': time.time(),
                                       'started': now}
        # Sitzungs-Log: neue Sitzung beginnen (alten offenen Eintrag passend schließen)
        _gsess_open(uid, game, now,
                    prev_last_seen=(None if takeover else (prev.get('last_seen') if prev else None)),
                    takeover=takeover)
    _ha_games_async()  # HA-Sensoren sofort aktualisieren (Spielstart)
    return {'token': token}


def _sess_heartbeat(game: str, uid: str, token: str) -> dict:
    with _sess_lock:
        s = _game_sessions.get((game, uid))
        if s and token and token == s.get('token'):
            s['last_seen'] = time.time()
            return {'ok': True}
        return {'error': 'invalid_token'}


def _sess_release(game: str, uid: str, token: str) -> dict:
    with _sess_lock:
        s = _game_sessions.get((game, uid))
        if s and token and token == s.get('token'):
            _game_sessions.pop((game, uid), None)
            _gsess_finish(uid, game, 'closed')  # sauber beendet (✕ / Zurück)
            _ha_games_async()  # HA-Sensoren sofort aktualisieren (Spielende)
            return {'ok': True}
        return {'error': 'invalid_token'}


def _sess_dispatch(game: str, uid: str, data: dict):
    """POST /api/<spiel>/session — claim/force/heartbeat/release."""
    action = str(data.get('action', ''))[:12]
    token = str(data.get('token', ''))[:64]
    if action == 'claim':
        return jsonify(_sess_claim(game, uid))
    if action == 'force':
        return jsonify(_sess_claim(game, uid, force=True))
    if action == 'heartbeat':
        return jsonify(_sess_heartbeat(game, uid, token))
    if action == 'release':
        return jsonify(_sess_release(game, uid, token))
    return jsonify({'error': 'unknown action'}), 400


def _sess_locked(game: str, uid: str, data: dict) -> bool:
    """True, wenn eine fremde Session aktiv ist und der Token nicht passt."""
    token = str(data.get('token', ''))[:64]
    s = _game_sessions.get((game, uid))
    if s and _sess_active(game, uid) and token != s.get('token'):
        return True
    # Heartbeat bei gültigem Token auffrischen (Spielaktionen zählen als Aktivität)
    if s and token and token == s.get('token'):
        s['last_seen'] = time.time()
    return False


# ── Persistentes Spielsitzungs-Log (pro Mitglied, überlebt Add-on-Neustarts) ──
# Hält Start/Ende jeder Spielsitzung dauerhaft fest (im Gegensatz zum reinen
# In-Memory-_game_sessions). Wird an den Session-Hooks claim/release/Übernahme
# geführt; Timeouts werden beim Lesen/Claim „nachgeschlossen".
GSESSIONS_MAX = 100


def _gsess_path(uid: str) -> Path | None:
    if not _UID_RE.match(uid or ''):
        return None
    return safe_under(GAMES_DIR, f'gsessions_{uid}.json')


def _gsess_load(uid: str) -> list:
    p = _gsess_path(uid)
    if p is None:
        return []
    try:
        with open(p, encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except FileNotFoundError:
        return []
    except Exception:
        return []


def _gsess_write(uid: str, rows: list) -> None:
    p = _gsess_path(uid)
    if p is None:
        return
    tmp = p.with_suffix('.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(rows[-GSESSIONS_MAX:], f, ensure_ascii=False)
    os.replace(tmp, p)


def _gsess_close_open(rows: list, game: str, end_ts: int, reason: str) -> bool:
    """Jüngsten offenen Eintrag des Spiels schließen. True, wenn etwas geschah."""
    for row in reversed(rows):
        if row.get('game') == game and row.get('end') is None:
            row['end'] = int(end_ts)
            row['reason'] = reason
            return True
    return False


def _gsess_open(uid: str, game: str, now: int, prev_last_seen=None,
                takeover: bool = False) -> None:
    """Neue Sitzung beginnen; einen evtl. noch offenen Eintrag vorher schließen."""
    rows = _gsess_load(uid)
    if takeover:
        _gsess_close_open(rows, game, now, 'takeover')
    else:
        # verwaister offener Eintrag (Timeout / Neustart) → an letzter Aktivität bzw. Start beenden
        for row in reversed(rows):
            if row.get('game') == game and row.get('end') is None:
                row['end'] = int(prev_last_seen) if prev_last_seen else int(row.get('start', now))
                row['reason'] = 'timeout'
                break
    rows.append({'game': game, 'start': int(now), 'end': None, 'reason': None})
    _gsess_write(uid, rows)


def _gsess_finish(uid: str, game: str, reason: str, end_ts=None) -> None:
    rows = _gsess_load(uid)
    if _gsess_close_open(rows, game, int(end_ts or time.time()), reason):
        _gsess_write(uid, rows)


def _gsess_sweep(uid: str) -> list:
    """Offene Einträge schließen, deren Session nicht mehr aktiv ist (Timeout).
    Liefert die aktuelle (ggf. aktualisierte) Sitzungsliste zurück."""
    with _sess_lock:
        rows = _gsess_load(uid)
        changed = False
        for row in rows:
            if row.get('end') is not None:
                continue
            game = row.get('game')
            if _sess_active(game, uid):
                continue  # läuft wirklich noch
            s = _game_sessions.get((game, uid))
            end = int(s['last_seen']) if s and s.get('last_seen') else int(row.get('start', 0))
            row['end'] = end
            row['reason'] = 'timeout'
            changed = True
        if changed:
            _gsess_write(uid, rows)
        return rows


@public_app.route('/bereich/66')
def game66_page():
    """Vollfenster-Spielseite (wird vom Mitgliederbereich als Iframe geöffnet)."""
    site = load_site()
    if site['design'].get('maintenance'):
        return _maintenance_page(site, detect_language(request))
    member = _require_member()
    lang = detect_language(request)
    t = load_translations(lang)
    deck = site['design'].get('card_deck') or 'knoll'
    return render_template('game_66.html', t=t, lang=lang, site=site,
                           member=member, deck=deck,
                           year=datetime.now(timezone.utc).year)


@public_app.route('/api/66/state')
def api_game66_state():
    member = _require_member()
    with _game_lock:
        st = load_game66(member['id'])
        if st is None:
            # Kein laufendes Spiel → Client zeigt den Startbildschirm (Auswahl/Fortsetzen)
            return jsonify({'status': 'no_game'})
        if st['status'] == 'playing' and st['turn'] == 'a':
            game_66.ai_run(st)
            save_game66(member['id'], st)
        if _record_match_if_over(member['id'], st):
            save_game66(member['id'], st)
    return jsonify(game_66.public_view(st))


@public_app.route('/api/66/move', methods=['POST'])
def api_game66_move():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('66', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    raw = data.get('action')
    if not isinstance(raw, dict):
        abort(400)
    # Nur whitelisted Felder übernehmen (kein ungeprüfter Client-Input ins Regelwerk)
    act = {'type': str(raw.get('type', ''))[:12]}
    if raw.get('card') is not None:
        act['card'] = str(raw.get('card'))[:2]
    if raw.get('marry'):
        act['marry'] = True
    with _game_lock:
        st = load_game66(member['id'])
        if st is None:
            abort(409)  # kein laufendes Spiel → Client soll /state holen
        # Undo nur für leichte Stufen (wie im Client: Button auf 'hard' verborgen)
        snapshot = (copy.deepcopy(st)
                    if st.get('level') in ('easy', 'medium') else None)
        # 'exchange' (Trumpf-Bube tauschen) und 'close' (zudrehen) lassen den Zug
        # beim Spieler — der folgende 'play'-Zug gehört zur selben Spielerrunde und
        # darf den Undo-Stand NICHT überschreiben (sonst nimmt Undo nur das Spielen,
        # nicht den Tausch/das Zudrehen zurück).
        prev_lock = bool(st.get('_undo_lock'))
        try:
            frames = game_66.apply_player_frames(st, act)
        except game_66.IllegalMove:
            # Ungültigen Zug ignorieren, aktuellen Stand zurückgeben (kein 500)
            return jsonify({'frames': [game_66.public_view(st)]})
        if snapshot is not None and not prev_lock:
            _ng_undo[('66', member['id'])] = snapshot
        st['_undo_lock'] = act['type'] in ('exchange', 'close')
        _record_match_if_over(member['id'], st)
        save_game66(member['id'], st)
    return jsonify({'frames': frames})


@public_app.route('/api/66/new', methods=['POST'])
def api_game66_new():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('66', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    rules = data.get('rules')
    rules = rules if rules in game_66.RULESETS else 'standard'
    level = data.get('level')
    level = level if level in game_66.LEVELS else 'medium'
    with _game_lock:
        st = game_66.new_match(rules=rules, level=level)
        frames = game_66.deal_frames(st)  # KI-Eröffnung animierbar
        _ng_undo.pop(('66', member['id']), None)  # alten Undo-Stand verwerfen
        save_game66(member['id'], st)
    return jsonify({'frames': frames})


@public_app.route('/api/66/undo', methods=['POST'])
def api_game66_undo():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('66', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    with _game_lock:
        snap = _ng_undo.pop(('66', member['id']), None)
        if snap is None:
            return jsonify({'error': 'no_undo'}), 400
        save_game66(member['id'], snap)  # auf den Stand vor dem letzten Zug zurück
    return jsonify(game_66.public_view(snap))


@public_app.route('/api/66/history')
def api_game66_history():
    member = _require_member()
    hist = load_game66_history(member['id'])
    return jsonify({'games': list(reversed(hist))})  # neueste zuerst


@public_app.route('/api/66/rules')
def api_game66_rules():
    _require_member()
    # Sprachabhängig aus game_66_rules_{lang}.md (DE-Fallback) — wie 20AB/Schwimmen
    return jsonify({'html': _ng_rules_html('66', detect_language(request))})


@public_app.route('/api/66/session', methods=['POST'])
def api_game66_session():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    return _sess_dispatch('66', member['id'], data)


# ── 20 AB & Schwimmen (Mitglieder-Spiele, server-autoritativ, pro Mitglied) ────
# Beide Spiele folgen demselben Muster wie 66: server-autoritativer Zustand,
# public_view() redigiert Gegnerhände, Persistenz als <spiel>_<uid>.json.
# KI-Schritte werden vom Client einzeln via /ai abgerufen (Animations-getrieben).

NG_HISTORY_MAX = 50
_ng_undo: dict = {}            # (spiel, uid) -> Snapshot vor dem letzten Spielerzug
_schwimmen_tour: dict = {}     # uid -> Turnierstand (in-memory, best effort)


def _ng_path(game: str, uid: str) -> Path | None:
    if game not in ('20ab', 'schwimmen', 'maumau', 'praesident', 'jeopardy', 'gluecksrad') or not _UID_RE.match(uid or ''):
        return None
    return safe_under(GAMES_DIR, f'{game}_{uid}.json')


def _ng_load(game: str, uid: str) -> dict | None:
    p = _ng_path(game, uid)
    if p is None:
        return None
    try:
        with open(p, encoding='utf-8') as f:
            st = json.load(f)
        return st if isinstance(st, dict) and 'status' in st else None
    except FileNotFoundError:
        return None
    except Exception as e:
        log.warning("%s-Spielstand defekt (%s): %s", game, uid[:8], e)
        return None


def _ng_save(game: str, uid: str, st: dict) -> None:
    p = _ng_path(game, uid)
    if p is None:
        return
    tmp = p.with_suffix('.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(st, f, ensure_ascii=False)
    os.replace(tmp, p)


def _ng_hist_path(game: str, uid: str) -> Path | None:
    if game not in ('20ab', 'schwimmen', 'maumau', 'praesident', 'jeopardy', 'gluecksrad') or not _UID_RE.match(uid or ''):
        return None
    return safe_under(GAMES_DIR, f'{game}hist_{uid}.json')


def _ng_history(game: str, uid: str) -> list:
    p = _ng_hist_path(game, uid)
    if p is None:
        return []
    try:
        with open(p, encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except FileNotFoundError:
        return []
    except Exception:
        return []


def _ng_history_write(game: str, uid: str, games: list) -> None:
    p = _ng_hist_path(game, uid)
    if p is None:
        return
    tmp = p.with_suffix('.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(games[-NG_HISTORY_MAX:], f, ensure_ascii=False)
    os.replace(tmp, p)


def _ng_rules_html(game: str, lang: str) -> str:
    fname = f'game_{game}_rules_{lang}.md'
    path = Path(_BASE) / fname
    if not path.is_file():
        path = Path(_BASE) / f'game_{game}_rules_de.md'
    try:
        text = path.read_text(encoding='utf-8')
    except OSError:
        text = ''
    # Inhalt stammt aus mitgelieferten Repo-Dokumenten (kein Nutzer-Input)
    return md_lib.markdown(text, extensions=['tables', 'sane_lists'])


def _ng_names(t: dict, prefix: str) -> dict:
    return {'p': t.get(f'{prefix}_player', 'Du'),
            'a1': t.get(f'{prefix}_ai1', 'KI 1'),
            'a2': t.get(f'{prefix}_ai2', 'KI 2')}


# ── 20 AB ──────────────────────────────────────────────────────────────────────

def _clean_20ab_move(raw: dict) -> dict:
    """Nur whitelisted Felder ins Regelwerk (kein ungeprüfter Client-Input)."""
    act = {'type': str(raw.get('type', ''))[:16]}
    if raw.get('card') is not None:
        act['card'] = str(raw.get('card'))[:2]
    if raw.get('suit') is not None:
        act['suit'] = str(raw.get('suit'))[:4]      # c/d/h/s oder 'next'
    if raw.get('value') is not None:
        act['value'] = str(raw.get('value'))[:8]     # 'yes'/'no'/'play'/'pass'
    if isinstance(raw.get('cards'), list):
        act['cards'] = [str(c)[:2] for c in raw['cards'][:6]]
    return act


def _record_20ab_if_over(uid: str, st: dict) -> None:
    if st.get('status') != 'game_over' or st.get('recorded'):
        return
    st['recorded'] = True
    games = _ng_history('20ab', uid)
    games.append({
        'ts': int(datetime.now(timezone.utc).timestamp()),
        'winner': st.get('winner', ''),
        'scores': st.get('scores', {}),
        'rounds': st.get('round_nr', 0),
        'level': st.get('level', 'medium'),
        'herz_blind': st.get('herz_blind_count', 0),
    })
    _ng_history_write('20ab', uid, games)


@public_app.route('/bereich/20ab')
def game20ab_page():
    site = load_site()
    if site['design'].get('maintenance'):
        return _maintenance_page(site, detect_language(request))
    member = _require_member()
    lang = detect_language(request)
    t = load_translations(lang)
    return render_template('game_20ab.html', t=t, lang=lang, site=site,
                           member=member, card_deck='knoll',
                           year=datetime.now(timezone.utc).year)


@public_app.route('/api/20ab/state')
def api_20ab_state():
    member = _require_member()
    st = _ng_load('20ab', member['id'])
    return jsonify({'state': game_20ab.public_view(st) if st else None})


@public_app.route('/api/20ab/new', methods=['POST'])
def api_20ab_new():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('20ab', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    level = data.get('level')
    level = level if level in ('easy', 'medium', 'hard') else 'medium'
    with _game_lock:
        st = game_20ab.new_game(level)
        _ng_undo.pop(('20ab', member['id']), None)
        _ng_save('20ab', member['id'], st)
    return jsonify({'state': game_20ab.public_view(st)})


@public_app.route('/api/20ab/move', methods=['POST'])
def api_20ab_move():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('20ab', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    if not data.get('type'):
        abort(400)
    act = _clean_20ab_move(data)
    with _game_lock:
        st = _ng_load('20ab', member['id'])
        if st is None:
            abort(409)
        snapshot = copy.deepcopy(st)
        try:
            game_20ab.apply_action(st, 'p', act)
        except game_20ab.IllegalMove:
            return jsonify({'state': game_20ab.public_view(st)})
        _ng_undo[('20ab', member['id'])] = snapshot
        _record_20ab_if_over(member['id'], st)
        _ng_save('20ab', member['id'], st)
    return jsonify({'state': game_20ab.public_view(st)})


@public_app.route('/api/20ab/ai', methods=['POST'])
def api_20ab_ai():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('20ab', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    t = load_translations(detect_language(request))
    names = _ng_names(t, 'g20')
    with _game_lock:
        st = _ng_load('20ab', member['id'])
        if st is None:
            abort(409)
        event = None
        s = st
        if s['status'] == 'herz_blind_ask' and s.get('trump_chooser') != 'p':
            who = s['trump_chooser']
            value = game_20ab.ai_herz_blind(s, who)
            game_20ab.apply_action(s, who, {'type': 'herz_blind', 'value': value})
            event = {'type': 'herz_blind', 'who': who, 'value': value, 'name': names[who]}
        elif s['status'] == 'trump_sel' and s.get('trump_chooser') != 'p':
            who = s['trump_chooser']
            chosen = game_20ab.ai_trump(s, who)
            was_next = (chosen == 'next')
            game_20ab.apply_action(s, who, {'type': 'choose_trump', 'suit': chosen})
            event = {'type': 'trump', 'who': who, 'suit': s.get('trump'),
                     'name': names[who], 'was_next': was_next,
                     'trump_card': s.get('trump_card')}
        elif s['status'] == 'bidding' and s.get('bid_turn') != 'p':
            who = s['bid_turn']
            value = game_20ab.ai_bid(s, who)
            game_20ab.apply_action(s, who, {'type': 'bid', 'value': value})
            event = {'type': 'bid', 'who': who, 'value': value, 'name': names[who]}
            if s.get('forced'):
                forced_p = s['bid_order'][2]
                event['forced_player'] = forced_p
                event['forced_name'] = names[forced_p]
        elif s['status'] == 'exchanging' and s.get('exchange_turn') != 'p':
            who = s['exchange_turn']
            cards = game_20ab.ai_exchange(s, who)
            game_20ab.apply_action(s, who, {'type': 'exchange', 'cards': cards})
            event = {'type': 'exchange', 'who': who, 'count': len(cards), 'name': names[who]}
        elif s['status'] == 'playing' and s.get('turn') != 'p':
            who = s['turn']
            card = game_20ab.ai_play(s, who)
            game_20ab.apply_action(s, who, {'type': 'play', 'card': card})
            event = {'type': 'play', 'who': who, 'card': card, 'name': names[who],
                     'card_name': game_20ab.card_name(card)}
        elif s['status'] == 'trick_done':
            winner = s.get('trick_result')
            game_20ab.apply_action(s, 'p', {'type': 'collect'})
            event = {'type': 'collect', 'winner': winner, 'name': names.get(winner, '')}
        _record_20ab_if_over(member['id'], st)
        _ng_save('20ab', member['id'], st)
    return jsonify({'state': game_20ab.public_view(st), 'event': event})


@public_app.route('/api/20ab/undo', methods=['POST'])
def api_20ab_undo():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('20ab', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    with _game_lock:
        snap = _ng_undo.pop(('20ab', member['id']), None)
        if snap is None:
            return jsonify({'error': 'no_undo'}), 400
        _ng_save('20ab', member['id'], snap)
    return jsonify({'state': game_20ab.public_view(snap)})


@public_app.route('/api/20ab/rules')
def api_20ab_rules():
    _require_member()
    return jsonify({'html': _ng_rules_html('20ab', detect_language(request))})


@public_app.route('/api/20ab/history')
def api_20ab_history():
    member = _require_member()
    return jsonify({'games': list(reversed(_ng_history('20ab', member['id'])))})


@public_app.route('/api/20ab/history/reset', methods=['POST'])
def api_20ab_history_reset():
    member = _require_member()
    _ng_history_write('20ab', member['id'], [])
    return jsonify({'ok': True})


@public_app.route('/api/20ab/session', methods=['POST'])
def api_20ab_session():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    return _sess_dispatch('20ab', member['id'], data)


# ── Schwimmen ──────────────────────────────────────────────────────────────────

def _clean_schwimmen_move(raw: dict) -> dict:
    act = {'type': str(raw.get('type', ''))[:16]}
    if raw.get('hand_card') is not None:
        act['hand_card'] = str(raw.get('hand_card'))[:2]
    if raw.get('table_card') is not None:
        act['table_card'] = str(raw.get('table_card'))[:2]
    return act


def _record_schwimmen_if_over(uid: str, st: dict) -> None:
    if st.get('status') != 'game_over' or st.get('recorded'):
        return
    st['recorded'] = True
    move_log = st.get('move_log', [])
    actions = {'swap_one': 0, 'swap_all': 0, 'pass': 0, 'knock': 0}
    for m in move_log:
        if m.get('who') == 'p' and m.get('action') in actions:
            actions[m['action']] += 1
    rr = st.get('round_result') or {}
    best_hand = (rr.get('values', {}) or {}).get('p') or 0.0
    games = _ng_history('schwimmen', uid)
    games.append({
        'ts': int(datetime.now(timezone.utc).timestamp()),
        'winner': st.get('winner', ''),
        'lives': st.get('lives', {}),
        'rounds': st.get('round_nr', 0),
        'level': st.get('level', 'medium'),
        'player_actions': actions,
        'best_hand': best_hand,
    })
    _ng_history_write('schwimmen', uid, games)
    # Turnierstand aktualisieren
    tour = _schwimmen_tour.get(uid)
    if tour and tour.get('active'):
        w = st.get('winner', '')
        if w:
            tour['wins'][w] = tour['wins'].get(w, 0) + 1
        tour['played'] += 1
        if tour['played'] >= tour['total']:
            tour['active'] = False


@public_app.route('/bereich/schwimmen')
def schwimmen_page():
    site = load_site()
    if site['design'].get('maintenance'):
        return _maintenance_page(site, detect_language(request))
    member = _require_member()
    lang = detect_language(request)
    t = load_translations(lang)
    return render_template('game_schwimmen.html', t=t, lang=lang, site=site,
                           member=member, card_deck='knoll',
                           year=datetime.now(timezone.utc).year)


@public_app.route('/api/schwimmen/state')
def api_schwimmen_state():
    member = _require_member()
    st = _ng_load('schwimmen', member['id'])
    return jsonify({'state': game_schwimmen.public_view(st) if st else None,
                    'tournament': _schwimmen_tour.get(member['id'])})


@public_app.route('/api/schwimmen/new', methods=['POST'])
def api_schwimmen_new():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('schwimmen', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    level = data.get('level')
    level = level if level in ('easy', 'medium', 'hard') else 'medium'
    with _game_lock:
        _schwimmen_tour.pop(member['id'], None)
        st = game_schwimmen.new_game(level)
        _ng_undo.pop(('schwimmen', member['id']), None)
        _ng_save('schwimmen', member['id'], st)
    return jsonify({'state': game_schwimmen.public_view(st), 'tournament': None})


@public_app.route('/api/schwimmen/move', methods=['POST'])
def api_schwimmen_move():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('schwimmen', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    if not data.get('type'):
        abort(400)
    act = _clean_schwimmen_move(data)
    with _game_lock:
        st = _ng_load('schwimmen', member['id'])
        if st is None:
            abort(409)
        snapshot = copy.deepcopy(st)
        try:
            game_schwimmen.apply_action(st, 'p', act)
        except game_schwimmen.IllegalMove:
            return jsonify({'state': game_schwimmen.public_view(st),
                            'tournament': _schwimmen_tour.get(member['id'])})
        _ng_undo[('schwimmen', member['id'])] = snapshot
        _record_schwimmen_if_over(member['id'], st)
        _ng_save('schwimmen', member['id'], st)
    return jsonify({'state': game_schwimmen.public_view(st),
                    'tournament': _schwimmen_tour.get(member['id'])})


@public_app.route('/api/schwimmen/ai', methods=['POST'])
def api_schwimmen_ai():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('schwimmen', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    t = load_translations(detect_language(request))
    names = _ng_names(t, 'gs')
    with _game_lock:
        st = _ng_load('schwimmen', member['id'])
        if st is None:
            abort(409)
        event = None
        if st['status'] == 'playing' and st.get('turn') != 'p':
            who = st['turn']
            action = game_schwimmen.ai_play(st, who)
            game_schwimmen.apply_action(st, who, action)
            event = {'type': action['type'], 'who': who, 'name': names[who]}
            if action['type'] == 'swap_one':
                event['hand_card'] = action.get('hand_card')
                event['table_card'] = action.get('table_card')
                event['hand_card_name'] = game_schwimmen.card_name(action['hand_card'])
                event['table_card_name'] = game_schwimmen.card_name(action['table_card'])
            if st.get('table_refreshed'):
                event['table_refreshed'] = True
        _record_schwimmen_if_over(member['id'], st)
        _ng_save('schwimmen', member['id'], st)
    return jsonify({'state': game_schwimmen.public_view(st), 'event': event,
                    'tournament': _schwimmen_tour.get(member['id'])})


@public_app.route('/api/schwimmen/undo', methods=['POST'])
def api_schwimmen_undo():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('schwimmen', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    with _game_lock:
        snap = _ng_undo.pop(('schwimmen', member['id']), None)
        if snap is None:
            return jsonify({'error': 'no_undo'}), 400
        _ng_save('schwimmen', member['id'], snap)
    return jsonify({'state': game_schwimmen.public_view(snap)})


@public_app.route('/api/schwimmen/hint')
def api_schwimmen_hint():
    member = _require_member()
    st = _ng_load('schwimmen', member['id'])
    if st is None:
        abort(409)
    return jsonify({'hint': game_schwimmen.hint_for_player(st)})


@public_app.route('/api/schwimmen/rules')
def api_schwimmen_rules():
    _require_member()
    return jsonify({'html': _ng_rules_html('schwimmen', detect_language(request))})


@public_app.route('/api/schwimmen/history')
def api_schwimmen_history():
    member = _require_member()
    return jsonify({'games': list(reversed(_ng_history('schwimmen', member['id'])))})


@public_app.route('/api/schwimmen/history/reset', methods=['POST'])
def api_schwimmen_history_reset():
    member = _require_member()
    _ng_history_write('schwimmen', member['id'], [])
    return jsonify({'ok': True})


@public_app.route('/api/schwimmen/session', methods=['POST'])
def api_schwimmen_session():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    return _sess_dispatch('schwimmen', member['id'], data)


@public_app.route('/api/schwimmen/tournament/state')
def api_schwimmen_tour_state():
    member = _require_member()
    return jsonify({'tournament': _schwimmen_tour.get(member['id'])})


@public_app.route('/api/schwimmen/tournament/new', methods=['POST'])
def api_schwimmen_tour_new():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('schwimmen', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    level = data.get('level')
    level = level if level in ('easy', 'medium', 'hard') else 'medium'
    try:
        total = min(max(int(data.get('games', 5)), 3), 9)
    except (TypeError, ValueError):
        total = 5
    with _game_lock:
        _schwimmen_tour[member['id']] = {
            'total': total, 'played': 0,
            'wins': {'p': 0, 'a1': 0, 'a2': 0},
            'level': level, 'active': True,
        }
        st = game_schwimmen.new_game(level)
        _ng_undo.pop(('schwimmen', member['id']), None)
        _ng_save('schwimmen', member['id'], st)
    return jsonify({'state': game_schwimmen.public_view(st),
                    'tournament': _schwimmen_tour.get(member['id'])})


@public_app.route('/api/schwimmen/tournament/next', methods=['POST'])
def api_schwimmen_tour_next():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('schwimmen', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    tour = _schwimmen_tour.get(member['id'])
    if not tour or not tour.get('active'):
        return jsonify({'error': 'no_tournament'}), 400
    with _game_lock:
        st = game_schwimmen.new_game(tour['level'])
        _ng_undo.pop(('schwimmen', member['id']), None)
        _ng_save('schwimmen', member['id'], st)
    return jsonify({'state': game_schwimmen.public_view(st),
                    'tournament': _schwimmen_tour.get(member['id'])})


# ── Mau Mau ────────────────────────────────────────────────────────────────────

def _clean_maumau_move(raw: dict) -> dict:
    """Nur whitelisted Felder ins Regelwerk (kein ungeprüfter Client-Input)."""
    act = {'type': str(raw.get('type', ''))[:16]}
    if raw.get('card') is not None:
        act['card'] = str(raw.get('card'))[:2]
    if raw.get('suit') is not None:
        act['suit'] = str(raw.get('suit'))[:1]      # h/d/s/c
    return act


def _clean_wins_target(raw) -> int:
    try:
        return min(max(int(raw), 1), 9)
    except (TypeError, ValueError):
        return 3


def _record_maumau_if_over(uid: str, st: dict) -> None:
    if st.get('status') != 'game_over' or st.get('recorded'):
        return
    st['recorded'] = True
    games = _ng_history('maumau', uid)
    games.append({
        'ts': int(datetime.now(timezone.utc).timestamp()),
        'winner': st.get('winner', ''),
        'wins': st.get('wins', {}),
        'rounds': st.get('round_nr', 0),
        'level': st.get('level', 'medium'),
    })
    _ng_history_write('maumau', uid, games)


@public_app.route('/bereich/maumau')
def maumau_page():
    site = load_site()
    if site['design'].get('maintenance'):
        return _maintenance_page(site, detect_language(request))
    member = _require_member()
    lang = detect_language(request)
    t = load_translations(lang)
    return render_template('game_maumau.html', t=t, lang=lang, site=site,
                           member=member, card_deck='knoll',
                           year=datetime.now(timezone.utc).year)


@public_app.route('/api/maumau/state')
def api_maumau_state():
    member = _require_member()
    st = _ng_load('maumau', member['id'])
    return jsonify({'state': game_maumau.public_view(st) if st else None})


@public_app.route('/api/maumau/new', methods=['POST'])
def api_maumau_new():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('maumau', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    level = data.get('level')
    level = level if level in ('easy', 'medium', 'hard') else 'medium'
    wins_target = _clean_wins_target(data.get('wins_target'))
    with _game_lock:
        st = game_maumau.new_game(level, wins_target=wins_target)
        _ng_undo.pop(('maumau', member['id']), None)
        _ng_save('maumau', member['id'], st)
    return jsonify({'state': game_maumau.public_view(st)})


@public_app.route('/api/maumau/move', methods=['POST'])
def api_maumau_move():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('maumau', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    if not data.get('type'):
        abort(400)
    act = _clean_maumau_move(data)
    with _game_lock:
        st = _ng_load('maumau', member['id'])
        if st is None:
            abort(409)
        snapshot = copy.deepcopy(st)
        try:
            game_maumau.apply_action(st, 'p', act)
        except game_maumau.IllegalMove:
            return jsonify({'state': game_maumau.public_view(st)})
        # 'wish' ist die Fortsetzung des Buben-Zugs (gleiche Spielerrunde) →
        # den Undo-Snapshot vom Buben-Spielen NICHT überschreiben, damit Undo den
        # Buben wieder auf die Hand legt und den Wunsch komplett aufhebt.
        if act['type'] != 'wish':
            _ng_undo[('maumau', member['id'])] = snapshot
        _record_maumau_if_over(member['id'], st)
        _ng_save('maumau', member['id'], st)
    return jsonify({'state': game_maumau.public_view(st)})


@public_app.route('/api/maumau/ai', methods=['POST'])
def api_maumau_ai():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('maumau', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    t = load_translations(detect_language(request))
    names = _ng_names(t, 'gmm')
    with _game_lock:
        st = _ng_load('maumau', member['id'])
        if st is None:
            abort(409)
        event = None
        if st['status'] in ('playing', 'drawn', 'wish_suit') and st.get('turn') != 'p':
            who = st['turn']
            action = game_maumau.ai_step(st, who)
            atype = action.get('type', '')
            if atype == 'play':
                card = action['card']
                game_maumau.apply_action(st, who, action)
                event = {'type': 'play', 'who': who, 'card': card,
                         'name': names[who], 'card_name': game_maumau.card_name(card)}
                if st['status'] == 'wish_suit':
                    wish_action = game_maumau.ai_wish(st, who)
                    game_maumau.apply_action(st, who, wish_action)
                    event['wished_suit'] = wish_action['suit']
            elif atype == 'draw':
                game_maumau.apply_action(st, who, action)
                event = {'type': 'draw', 'who': who, 'name': names[who],
                         'count': st.get('last_play', {}).get('count', 1)}
                if st['status'] == 'drawn':
                    card = st.get('can_play_drawn')
                    game_maumau.apply_action(st, who, game_maumau.ai_play_drawn(st, who))
                    event['played_drawn'] = card
                    event['card_name'] = game_maumau.card_name(card) if card else None
                    if st['status'] == 'wish_suit':
                        wish_action = game_maumau.ai_wish(st, who)
                        game_maumau.apply_action(st, who, wish_action)
                        event['wished_suit'] = wish_action['suit']
            elif atype == 'wish':
                game_maumau.apply_action(st, who, action)
                event = {'type': 'wish', 'who': who, 'suit': action['suit'], 'name': names[who]}
            elif atype == 'play_drawn':
                card = st.get('can_play_drawn')
                game_maumau.apply_action(st, who, action)
                event = {'type': 'play_drawn', 'who': who, 'card': card,
                         'name': names[who], 'card_name': game_maumau.card_name(card) if card else None}
                if st['status'] == 'wish_suit':
                    wish_action = game_maumau.ai_wish(st, who)
                    game_maumau.apply_action(st, who, wish_action)
                    event['wished_suit'] = wish_action['suit']
            elif atype == 'pass_drawn':
                game_maumau.apply_action(st, who, action)
                event = {'type': 'pass_drawn', 'who': who, 'name': names[who]}
        _record_maumau_if_over(member['id'], st)
        _ng_save('maumau', member['id'], st)
    return jsonify({'state': game_maumau.public_view(st), 'event': event})


@public_app.route('/api/maumau/undo', methods=['POST'])
def api_maumau_undo():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('maumau', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    with _game_lock:
        snap = _ng_undo.pop(('maumau', member['id']), None)
        if snap is None:
            return jsonify({'error': 'no_undo'}), 400
        _ng_save('maumau', member['id'], snap)
    return jsonify({'state': game_maumau.public_view(snap)})


@public_app.route('/api/maumau/rules')
def api_maumau_rules():
    _require_member()
    return jsonify({'html': _ng_rules_html('maumau', detect_language(request))})


@public_app.route('/api/maumau/history')
def api_maumau_history():
    member = _require_member()
    return jsonify({'games': list(reversed(_ng_history('maumau', member['id'])))})


@public_app.route('/api/maumau/history/reset', methods=['POST'])
def api_maumau_history_reset():
    member = _require_member()
    _ng_history_write('maumau', member['id'], [])
    return jsonify({'ok': True})


@public_app.route('/api/maumau/session', methods=['POST'])
def api_maumau_session():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    return _sess_dispatch('maumau', member['id'], data)


# ── Präsident ──────────────────────────────────────────────────────────────────

def _clean_praesident_move(raw: dict) -> dict:
    act = {'type': str(raw.get('type', ''))[:16]}
    if isinstance(raw.get('cards'), list):
        act['cards'] = [str(c)[:2] for c in raw['cards'][:4]]
    return act


def _record_praesident_if_over(uid: str, st: dict) -> None:
    if st.get('status') != 'game_over' or st.get('recorded'):
        return
    st['recorded'] = True
    games = _ng_history('praesident', uid)
    games.append({
        'ts': int(datetime.now(timezone.utc).timestamp()),
        'winner': st.get('winner', ''),
        'wins': st.get('wins', {}),
        'rounds': st.get('round_nr', 0),
        'level': st.get('level', 'medium'),
    })
    _ng_history_write('praesident', uid, games)


@public_app.route('/bereich/praesident')
def praesident_page():
    site = load_site()
    if site['design'].get('maintenance'):
        return _maintenance_page(site, detect_language(request))
    member = _require_member()
    lang = detect_language(request)
    t = load_translations(lang)
    return render_template('game_praesident.html', t=t, lang=lang, site=site,
                           member=member, card_deck='knoll',
                           year=datetime.now(timezone.utc).year)


@public_app.route('/api/praesident/state')
def api_praesident_state():
    member = _require_member()
    st = _ng_load('praesident', member['id'])
    return jsonify({'state': game_praesident.public_view(st) if st else None})


@public_app.route('/api/praesident/new', methods=['POST'])
def api_praesident_new():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('praesident', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    level = data.get('level')
    level = level if level in ('easy', 'medium', 'hard') else 'medium'
    wins_target = _clean_wins_target(data.get('wins_target'))
    with _game_lock:
        st = game_praesident.new_game(level, wins_target=wins_target)
        _ng_undo.pop(('praesident', member['id']), None)
        _ng_save('praesident', member['id'], st)
    return jsonify({'state': game_praesident.public_view(st)})


@public_app.route('/api/praesident/move', methods=['POST'])
def api_praesident_move():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('praesident', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    if not data.get('type'):
        abort(400)
    act = _clean_praesident_move(data)
    with _game_lock:
        st = _ng_load('praesident', member['id'])
        if st is None:
            abort(409)
        snapshot = copy.deepcopy(st)
        try:
            game_praesident.apply_action(st, 'p', act)
        except game_praesident.IllegalMove:
            return jsonify({'state': game_praesident.public_view(st)})
        _ng_undo[('praesident', member['id'])] = snapshot
        _record_praesident_if_over(member['id'], st)
        _ng_save('praesident', member['id'], st)
    return jsonify({'state': game_praesident.public_view(st)})


@public_app.route('/api/praesident/ai', methods=['POST'])
def api_praesident_ai():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('praesident', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    t = load_translations(detect_language(request))
    names = _ng_names(t, 'gp')
    with _game_lock:
        st = _ng_load('praesident', member['id'])
        if st is None:
            abort(409)
        event = None
        if st['status'] == 'swap_show':
            action = game_praesident.ai_step(st, st.get('swap_giving', ''))
            game_praesident.apply_action(st, st.get('swap_giving', ''), action)
            lp = st.get('last_play', {})
            event = {'type': 'swap_give', 'who': lp.get('who', ''), 'to': lp.get('to', ''),
                     'cards': lp.get('cards', []), 'name': names.get(lp.get('who', ''), ''),
                     'to_name': names.get(lp.get('to', ''), '')}
        elif st['status'] == 'swap_choose' and st.get('swap_receiving') != 'p':
            who = st['swap_receiving']
            game_praesident.apply_action(st, who, game_praesident.ai_step(st, who))
            lp = st.get('last_play', {})
            event = {'type': 'swap_choose', 'who': lp.get('who', ''), 'to': lp.get('to', ''),
                     'cards': lp.get('cards', []), 'name': names.get(lp.get('who', ''), ''),
                     'to_name': names.get(lp.get('to', ''), '')}
        elif st['status'] == 'trick_done':
            game_praesident.apply_action(st, '', {'type': 'collect'})
            lp = st.get('last_play', {})
            event = {'type': 'collect', 'who': lp.get('who', ''),
                     'name': names.get(lp.get('who', ''), '')}
        elif st['status'] == 'playing' and st.get('turn') != 'p':
            who = st['turn']
            action = game_praesident.ai_step(st, who)
            atype = action.get('type', '')
            if atype == 'play':
                cards = action['cards']
                game_praesident.apply_action(st, who, action)
                lp = st.get('last_play', {})
                event = {'type': 'play', 'who': who, 'cards': cards, 'name': names[who],
                         'card_names': [game_praesident.card_name(c) for c in cards],
                         'revolution': lp.get('revolution', False),
                         'finished': lp.get('finished', False),
                         'trick_done': lp.get('trick_done', False)}
            elif atype == 'pass':
                game_praesident.apply_action(st, who, action)
                lp = st.get('last_play', {})
                event = {'type': 'pass', 'who': who, 'name': names[who],
                         'trick_done': lp.get('trick_done', False)}
        _record_praesident_if_over(member['id'], st)
        _ng_save('praesident', member['id'], st)
    return jsonify({'state': game_praesident.public_view(st), 'event': event})


@public_app.route('/api/praesident/undo', methods=['POST'])
def api_praesident_undo():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('praesident', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    with _game_lock:
        snap = _ng_undo.pop(('praesident', member['id']), None)
        if snap is None:
            return jsonify({'error': 'no_undo'}), 400
        _ng_save('praesident', member['id'], snap)
    return jsonify({'state': game_praesident.public_view(snap)})


@public_app.route('/api/praesident/hint')
def api_praesident_hint():
    member = _require_member()
    st = _ng_load('praesident', member['id'])
    if st is None:
        abort(409)
    return jsonify({'hint': game_praesident.hint_for_player(st)})


@public_app.route('/api/praesident/rules')
def api_praesident_rules():
    _require_member()
    return jsonify({'html': _ng_rules_html('praesident', detect_language(request))})


@public_app.route('/api/praesident/history')
def api_praesident_history():
    member = _require_member()
    return jsonify({'games': list(reversed(_ng_history('praesident', member['id'])))})


@public_app.route('/api/praesident/history/reset', methods=['POST'])
def api_praesident_history_reset():
    member = _require_member()
    _ng_history_write('praesident', member['id'], [])
    return jsonify({'ok': True})


@public_app.route('/api/praesident/session', methods=['POST'])
def api_praesident_session():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    return _sess_dispatch('praesident', member['id'], data)


# ── Jeopardy ─────────────────────────────────────────────────────────────────

def _clean_jeopardy_move(raw: dict) -> dict:
    """Nur whitelisted Felder ins Regelwerk (kein ungeprüfter Client-Input).
    Zahlen werden in der Engine geklemmt (idx/elapsed_ms/amount)."""
    act = {'type': str(raw.get('type', ''))[:16]}
    if raw.get('cell') is not None:
        act['cell'] = str(raw.get('cell'))[:5]      # 'ci-vi'
    for k in ('idx', 'elapsed_ms', 'amount'):
        if raw.get(k) is not None:
            act[k] = raw.get(k)
    return act


_JEO_SEEN_Q_MAX = 150      # so viele zuletzt gesehene Fragen meiden (~5 Spiele)
_JEO_SEEN_CATS_MAX = 6      # = ein ganzes Board: keine Kategorie zwei Spiele in Folge
                           # (bei >12 Kategorien im Pool wird die Auswahl wieder zufälliger)


def _jeopardy_seen_path(uid: str) -> Path | None:
    if not _UID_RE.match(uid or ''):
        return None
    return safe_under(GAMES_DIR, f'jeopardyseen_{uid}.json')


def _jeopardy_seen_load(uid: str) -> dict:
    p = _jeopardy_seen_path(uid)
    if p is not None:
        try:
            with open(p, encoding='utf-8') as f:
                d = json.load(f)
            if isinstance(d, dict):
                return {'questions': list(d.get('questions', []))[-_JEO_SEEN_Q_MAX:],
                        'categories': list(d.get('categories', []))[-_JEO_SEEN_CATS_MAX:]}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
    return {'questions': [], 'categories': []}


def _jeopardy_seen_update(uid: str, st: dict) -> None:
    """Board-Fragen + Kategorien dieses Spiels merken, damit Folge-Spiele sie meiden."""
    p = _jeopardy_seen_path(uid)
    if p is None:
        return
    seen = _jeopardy_seen_load(uid)
    q = seen['questions'] + [c['q_de'] for c in st.get('clues', {}).values()]
    cats = seen['categories'] + [col['cat'] for col in st.get('board', [])]
    data = {'questions': q[-_JEO_SEEN_Q_MAX:], 'categories': cats[-_JEO_SEEN_CATS_MAX:]}
    tmp = p.with_suffix('.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, p)


def _record_jeopardy_if_over(uid: str, st: dict) -> None:
    if st.get('status') != 'game_over' or st.get('recorded'):
        return
    st['recorded'] = True
    games = _ng_history('jeopardy', uid)
    games.append({
        'ts': int(datetime.now(timezone.utc).timestamp()),
        'winner': st.get('winner', ''),
        'scores': st.get('scores', {}),
        'level': st.get('level', 'medium'),
    })
    _ng_history_write('jeopardy', uid, games)


@public_app.route('/bereich/jeopardy')
def jeopardy_page():
    site = load_site()
    if site['design'].get('maintenance'):
        return _maintenance_page(site, detect_language(request))
    member = _require_member()
    lang = detect_language(request)
    t = load_translations(lang)
    return render_template('game_jeopardy.html', t=t, lang=lang, site=site,
                           member=member, year=datetime.now(timezone.utc).year)


@public_app.route('/api/jeopardy/state')
def api_jeopardy_state():
    member = _require_member()
    st = _ng_load('jeopardy', member['id'])
    return jsonify({'state': game_jeopardy.public_view(st) if st else None})


@public_app.route('/api/jeopardy/new', methods=['POST'])
def api_jeopardy_new():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('jeopardy', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    level = data.get('level')
    level = level if level in ('easy', 'medium', 'hard') else 'medium'
    with _game_lock:
        seen = _jeopardy_seen_load(member['id'])
        st = game_jeopardy.new_game(level, recent_q=seen['questions'],
                                    recent_cats=seen['categories'])
        _jeopardy_seen_update(member['id'], st)
        _ng_save('jeopardy', member['id'], st)
    return jsonify({'state': game_jeopardy.public_view(st)})


@public_app.route('/api/jeopardy/move', methods=['POST'])
def api_jeopardy_move():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('jeopardy', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    if not data.get('type'):
        abort(400)
    act = _clean_jeopardy_move(data)
    with _game_lock:
        st = _ng_load('jeopardy', member['id'])
        if st is None:
            abort(409)
        try:
            game_jeopardy.apply_action(st, 'p', act)
        except game_jeopardy.IllegalMove:
            return jsonify({'state': game_jeopardy.public_view(st)})
        _record_jeopardy_if_over(member['id'], st)
        _ng_save('jeopardy', member['id'], st)
    return jsonify({'state': game_jeopardy.public_view(st)})


@public_app.route('/api/jeopardy/ai', methods=['POST'])
def api_jeopardy_ai():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('jeopardy', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    with _game_lock:
        st = _ng_load('jeopardy', member['id'])
        if st is None:
            abort(409)
        event = game_jeopardy.ai_step(st)
        _record_jeopardy_if_over(member['id'], st)
        _ng_save('jeopardy', member['id'], st)
    return jsonify({'state': game_jeopardy.public_view(st), 'event': event})


@public_app.route('/api/jeopardy/rules')
def api_jeopardy_rules():
    _require_member()
    return jsonify({'html': _ng_rules_html('jeopardy', detect_language(request))})


@public_app.route('/api/jeopardy/history')
def api_jeopardy_history():
    member = _require_member()
    return jsonify({'games': list(reversed(_ng_history('jeopardy', member['id'])))})


@public_app.route('/api/jeopardy/history/reset', methods=['POST'])
def api_jeopardy_history_reset():
    member = _require_member()
    _ng_history_write('jeopardy', member['id'], [])
    return jsonify({'ok': True})


@public_app.route('/api/jeopardy/session', methods=['POST'])
def api_jeopardy_session():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    return _sess_dispatch('jeopardy', member['id'], data)


# ── Glücksrad ────────────────────────────────────────────────────────────────

def _clean_gluecksrad_move(raw: dict) -> dict:
    """Nur whitelisted Felder ins Regelwerk (kein ungeprüfter Client-Input).
    Die Engine validiert Buchstaben/Status zusätzlich."""
    act = {'type': str(raw.get('type', ''))[:16]}
    if raw.get('letter') is not None:
        act['letter'] = str(raw.get('letter'))[:1].upper()
    if raw.get('answer') is not None:
        act['answer'] = str(raw.get('answer'))[:80]
    if 'accept' in raw:
        act['accept'] = bool(raw.get('accept'))
    if 'use' in raw:
        act['use'] = bool(raw.get('use'))
    if isinstance(raw.get('consonants'), list):
        act['consonants'] = [str(c)[:1].upper() for c in raw['consonants'][:5]]
    if raw.get('vowel') is not None:
        act['vowel'] = str(raw.get('vowel'))[:1].upper()
    return act


def _record_gluecksrad_if_over(uid: str, st: dict) -> None:
    if st.get('status') != 'game_over' or st.get('recorded'):
        return
    st['recorded'] = True
    win = game_gluecksrad._determine_winner(st)
    win_idx = win if isinstance(win, int) else (win[0] if win else 0)
    games = _ng_history('gluecksrad', uid)
    games.append({
        'ts': int(datetime.now(timezone.utc).timestamp()),
        # numerischer Sieger-Index (0 = Mensch) — so erwartet es das Spiel-Frontend
        'winner': win_idx,
        'players': [{'name': p['name'], 'total': p['total']} for p in st['players']],
        'level': st.get('level', 'medium'),
    })
    _ng_history_write('gluecksrad', uid, games)


@public_app.route('/bereich/gluecksrad')
def gluecksrad_page():
    site = load_site()
    if site['design'].get('maintenance'):
        return _maintenance_page(site, detect_language(request))
    member = _require_member()
    lang = detect_language(request)
    t = load_translations(lang)
    return render_template('game_gluecksrad.html', t=t, lang=lang, site=site,
                           member=member, year=datetime.now(timezone.utc).year)


@public_app.route('/api/gluecksrad/state')
def api_gluecksrad_state():
    member = _require_member()
    st = _ng_load('gluecksrad', member['id'])
    return jsonify({'state': game_gluecksrad.public_view(st) if st else None})


@public_app.route('/api/gluecksrad/new', methods=['POST'])
def api_gluecksrad_new():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('gluecksrad', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    level = data.get('level')
    level = level if level in ('easy', 'medium', 'hard') else 'medium'
    lang = detect_language(request)
    with _game_lock:
        st = game_gluecksrad.new_game(level, lang)
        _ng_save('gluecksrad', member['id'], st)
    return jsonify({'state': game_gluecksrad.public_view(st)})


@public_app.route('/api/gluecksrad/move', methods=['POST'])
def api_gluecksrad_move():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('gluecksrad', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    if not data.get('type'):
        abort(400)
    act = _clean_gluecksrad_move(data)
    with _game_lock:
        st = _ng_load('gluecksrad', member['id'])
        if st is None:
            abort(409)
        game_gluecksrad.apply_action(st, act)
        _record_gluecksrad_if_over(member['id'], st)
        _ng_save('gluecksrad', member['id'], st)
    return jsonify({'state': game_gluecksrad.public_view(st)})


@public_app.route('/api/gluecksrad/ai', methods=['POST'])
def api_gluecksrad_ai():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('gluecksrad', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    with _game_lock:
        st = _ng_load('gluecksrad', member['id'])
        if st is None:
            abort(409)
        event = game_gluecksrad.ai_step(st)
        _record_gluecksrad_if_over(member['id'], st)
        _ng_save('gluecksrad', member['id'], st)
    return jsonify({'state': game_gluecksrad.public_view(st), 'event': event})


@public_app.route('/api/gluecksrad/rules')
def api_gluecksrad_rules():
    _require_member()
    return jsonify({'html': _ng_rules_html('gluecksrad', detect_language(request))})


@public_app.route('/api/gluecksrad/history')
def api_gluecksrad_history():
    member = _require_member()
    return jsonify({'games': list(reversed(_ng_history('gluecksrad', member['id'])))})


@public_app.route('/api/gluecksrad/history/reset', methods=['POST'])
def api_gluecksrad_history_reset():
    member = _require_member()
    _ng_history_write('gluecksrad', member['id'], [])
    return jsonify({'ok': True})


@public_app.route('/api/gluecksrad/session', methods=['POST'])
def api_gluecksrad_session():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    return _sess_dispatch('gluecksrad', member['id'], data)


@public_app.route('/sitemap.xml')
def sitemap():
    site = load_site()
    base = _base_url()
    posts = sorted_posts(site, public_only=True)

    def _valid_date(d):
        return bool(re.match(r'^\d{4}-\d{2}-\d{2}$', str(d or '')))

    newest = max((p['date'] for p in posts if _valid_date(p.get('date'))), default='')
    # (URL, lastmod) — lastmod optional
    entries = [(base + '/', newest)]
    entries += [(f"{base}/seite/{p['slug']}", '') for p in site.get('pages', []) if p.get('visible')]
    entries += [(f"{base}/p/{p['id']}", '') for p in site['projects']
                if _has_detail(p) and project_visible(p)]
    if posts:
        entries.append((base + '/blog', newest))
        entries += [(f"{base}/blog/{p['id']}", p['date'] if _valid_date(p.get('date')) else '')
                    for p in posts]
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for loc, lastmod in entries:
        xml += f'  <url><loc>{loc}</loc>'
        if lastmod:
            xml += f'<lastmod>{lastmod}</lastmod>'
        xml += '</url>\n'
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
    viewer_member = is_member(request) and not static_export
    font_family, font_faces = font_css(site['design'])
    sections = site.get('sections', {})
    albums = _albums_for_public(site, viewer_member)
    if static_export:
        albums = [a for a in albums if not a.get('locked')]
    latest_posts = sorted_posts(site, public_only=True)[:3]
    contact_enabled = bool(site['design'].get('contact_enabled')) and not static_export

    loc_block = sections.get('location') or {}
    loc_present = bool(loc_block.get('address') or loc_block.get('hours_de') or loc_block.get('hours_en'))

    # Tipp des Tages/der Woche: deterministisch übers Datum (für alle Besucher gleich)
    tips = sections.get('tips') or []
    tips_weekly = site.get('tips_rotation') == 'weekly'
    tip_of_day = None
    if tips:
        period = date.today().toordinal()
        if tips_weekly:
            period //= 7
        if site.get('tips_random'):
            idx = (period * 2654435761) % 2147483647 % len(tips)
        else:
            idx = period % len(tips)
        tip_of_day = tips[idx]
        # Tatsächliche Anzeige festhalten (einmal pro Tag, nur echte Aufrufe)
        if not static_export and tip_of_day.get('id'):
            today_key = date.today().isoformat()
            tstats = site.setdefault('tips_stats', {})
            st = tstats.get(tip_of_day['id'])
            if not st or st.get('last') != today_key:
                tstats[tip_of_day['id']] = {'last': today_key, 'days': (st.get('days', 0) if st else 0) + 1}
                save_site(site)

    # Eigenschaften je Abschnitt: (Anker, Übersetzungs-Schlüssel, ob Inhalt vorhanden)
    section_defs = {
        'news':         ('news',         'news_heading',         bool(sections.get('news'))),
        'tips':         ('tips',         'tips_heading_week' if tips_weekly else 'tips_heading', bool(tips)),
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
    # Mitglieder-only-Sektionen: Gäste sehen sie nicht, eingeloggte Mitglieder schon
    member_secs = set(site.get('members_sections') or [])
    if not viewer_member:
        section_order = [k for k in section_order if k not in member_secs]

    # Frei konfigurierbare Überschrift für den Werdegang (leer = Standard „Werdegang")
    timeline_title = loc(sections, 'timeline_title')

    # Navigations-Leiste: nur Sektionen mit Inhalt, in gewählter Reihenfolge
    nav_items = []
    if site['design'].get('show_nav', True):
        for key in section_order:
            anchor, label_key, present = section_defs[key]
            if present:
                label = timeline_title if (key == 'timeline' and timeline_title) else t.get(label_key, label_key)
                nav_items.append({'anchor': anchor, 'label': label})
        if contact_enabled:
            nav_items.append({'anchor': 'kontakt', 'label': t.get('contact_heading', 'contact_heading')})
        # Eigene Seiten und Formulare als echte Links (mit Navi-Schalter) anhängen
        nav_items += _nav_links(site, loc)

    return render_template('public.html', t=t, lang=lang, site=site, loc=loc,
                           projects=projects,
                           font_family=font_family, font_faces=font_faces,
                           bio_html=render_md(loc(site['profile'], 'bio')),
                           meta_desc=_site_meta(site, loc),
                           email_parts=email_parts,
                           sections=sections,
                           albums=albums,
                           album_protect=bool(site.get('album_protect')),
                           latest_posts=latest_posts,
                           nav_items=nav_items,
                           section_order=section_order,
                           timeline_title=timeline_title,
                           tip_of_day=tip_of_day, tips_weekly=tips_weekly,
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
    all_posts = sorted_posts(site, public_only=True)
    if not all_posts:
        abort(404)
    query = _clean_str(request.args.get('q'), 80)
    tag = _clean_str(request.args.get('tag'), 30)
    posts = filter_posts(all_posts, query, tag)
    count_visit(request)
    t = load_translations(lang)
    loc = _loc_factory(lang)
    return render_template('blog.html', t=t, lang=lang, site=site, loc=loc,
                           posts=posts, tags=all_post_tags(site),
                           query=query, active_tag=tag,
                           newsletter_open=newsletter_open(),
                           nl=_clean_str(request.args.get('nl'), 20),
                           meta_desc=_site_meta(site, loc),
                           year=datetime.now(timezone.utc).year)


@public_app.route('/newsletter/subscribe', methods=['POST'])
def newsletter_subscribe():
    site = load_site()
    if site['design'].get('maintenance') or not newsletter_open():
        abort(403)
    ip = get_client_ip(request)
    # Honeypot + Rate-Limit → immer generische Rückmeldung (keine Enumeration)
    if (request.form.get('website') or '').strip() or newsletter_rate_limited(ip):
        return redirect('/blog?nl=sent')
    record_newsletter_attempt(ip)
    email = _clean_str(request.form.get('email'), 150).lower()
    if not _EMAIL_RE.match(email):
        return redirect('/blog?nl=invalidmail')
    subs = load_subscribers()
    existing = next((s for s in subs if s['email'] == email), None)
    token = secrets.token_urlsafe(24)
    if existing is None:
        subs.append({'id': uuid.uuid4().hex[:12], 'email': email, 'confirmed': False,
                     'ts': int(time.time()), 'utoken': secrets.token_urlsafe(16),
                     'confirm': {'hash': generate_password_hash(token),
                                 'exp': int(time.time()) + NEWSLETTER_CONFIRM_TTL}})
        save_subscribers(subs)
        threading.Thread(target=send_confirm_subscription, args=(subs[-1], token), daemon=True).start()
        log.info("Newsletter-Abo angefragt: '%s' von %s", email, ip)
    elif not existing.get('confirmed'):
        existing['confirm'] = {'hash': generate_password_hash(token),
                               'exp': int(time.time()) + NEWSLETTER_CONFIRM_TTL}
        save_subscribers(subs)
        threading.Thread(target=send_confirm_subscription, args=(existing, token), daemon=True).start()
    # bereits bestätigt → still nichts tun (generische Antwort schützt vor Enumeration)
    return redirect('/blog?nl=sent')


@public_app.route('/newsletter/confirm/<sid>/<token>')
def newsletter_confirm(sid: str, token: str):
    subs = load_subscribers()
    sub = next((s for s in subs if s['id'] == sid), None)
    ok = False
    if sub is not None:
        c = sub.get('confirm')
        if c and time.time() <= c.get('exp', 0) and check_password_hash(c.get('hash', ''), token):
            ok = True
    if not ok:
        return redirect('/blog?nl=invalid')
    sub['confirmed'] = True
    sub.pop('confirm', None)
    save_subscribers(subs)
    log.info("Newsletter-Abo bestätigt: '%s'", sub['email'])
    return redirect('/blog?nl=confirmed')


@public_app.route('/newsletter/unsubscribe/<sid>/<token>')
def newsletter_unsubscribe(sid: str, token: str):
    subs = load_subscribers()
    sub = next((s for s in subs if s['id'] == sid), None)
    if sub is not None and secrets.compare_digest(str(sub.get('utoken', '')), token):
        subs = [s for s in subs if s['id'] != sid]
        save_subscribers(subs)
        log.info("Newsletter-Abmeldung: '%s'", sub['email'])
        return redirect('/blog?nl=unsubscribed')
    return redirect('/blog?nl=invalid')


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
    views = bump_post_view(pid, request)
    t = load_translations(lang)
    loc = _loc_factory(lang)
    member = current_member(request)
    # Mitglieder-only: Gäste sehen nur einen Anriss + Login-Aufforderung
    locked = bool(post.get('members_only')) and member is None
    full_html = render_md(loc(post, 'text'))
    text_html = ('<p>' + _locked_teaser(full_html) + '</p>') if locked else full_html
    comments_enabled = bool(site['design'].get('comments_enabled')) and not locked
    cdata = load_comments().get(pid, {}) if comments_enabled else {}
    reactions = cdata.get('reactions', {})
    clist = cdata.get('comments', [])
    threaded = _thread_comments(clist)
    return render_template('post.html', t=t, lang=lang, site=site, loc=loc, p=post,
                           text_html=text_html, locked=locked,
                           meta_desc=(loc(post, 'meta') or _plain_excerpt(text_html) or _site_meta(site, loc)),
                           comments_enabled=comments_enabled,
                           member=member,
                           comments=threaded, comment_count=len(clist),
                           reaction_emojis=COMMENT_REACTIONS,
                           reaction_counts=_reaction_counts(reactions),
                           my_reaction=(reactions.get(member['id']) if member else None),
                           views=views,
                           year=datetime.now(timezone.utc).year)


def _thread_comments(clist: list) -> list:
    """Flache Kommentarliste in Threads gruppieren (eine Verschachtelungs-Ebene):
    Top-Level-Kommentare in Reihenfolge, jeweils mit ihren Antworten (.replies)."""
    by_parent: dict = {}
    for c in clist:
        by_parent.setdefault(c.get('parent') or None, []).append(c)
    out = []
    for c in by_parent.get(None, []):
        node = dict(c)
        node['replies'] = by_parent.get(c['id'], [])
        out.append(node)
    return out


def _visible_post(site: dict, pid: str) -> dict | None:
    post = next((p for p in site.get('posts', []) if p.get('id') == pid), None)
    return post if post is not None and post_visible(post) else None


@public_app.route('/blog/<pid>/comment', methods=['POST'])
def blog_comment(pid: str):
    site = load_site()
    if site['design'].get('maintenance') or not site['design'].get('comments_enabled'):
        abort(403)
    member = current_member(request)
    if member is None:
        abort(403)
    post = _visible_post(site, pid)
    if post is None:
        abort(404)
    text = _clean_str(request.form.get('text'), 2000).strip()
    if not text:
        return redirect(f'/blog/{pid}#comments')
    parent_id = _clean_str(request.form.get('parent'), 12)
    data = load_comments()
    thread = _post_thread(data, pid)
    clist = thread['comments']
    # Antwort: Ziel-Kommentar suchen; Verschachtelung auf eine Ebene flachklopfen
    parent_comment = next((c for c in clist if c['id'] == parent_id), None) if parent_id else None
    new = {'id': uuid.uuid4().hex[:12], 'uid': member['id'],
           'name': _member_display_name(member), 'text': text, 'ts': int(time.time())}
    if parent_comment is not None:
        new['parent'] = parent_comment.get('parent') or parent_comment['id']
    clist.append(new)
    thread['comments'] = clist[-COMMENTS_MAX_PER_POST:]
    save_comments(data)
    log_user_event(member['id'], 'comment', pid, get_client_ip(request))
    name = new['name']
    title = post.get('title_de') or post.get('title_en') or pid
    # Autor des beantworteten Kommentars per E-Mail informieren (nicht bei Selbstantwort)
    if (parent_comment is not None and parent_comment.get('uid')
            and parent_comment['uid'] != member['id'] and smtp_configured()):
        author = next((u for u in load_users() if u['id'] == parent_comment['uid']), None)
        if author and author.get('email'):
            base = (site['design'].get('public_url') or '').rstrip('/')
            url = f"{base}/blog/{pid}" if base else ''
            threading.Thread(target=send_comment_reply_email,
                             args=(author['email'], title, name, text, url), daemon=True).start()
    notify_ha_async('💬 MyPage: Neuer Kommentar',
                    f'{name} hat „{title}" kommentiert:\n\n{text[:300]}',
                    notification_id=f'mypage_comment_{pid}')
    log.info("Mitglied '%s' kommentierte Beitrag '%s'", member['email'], pid)
    return redirect(f'/blog/{pid}#comments')


@public_app.route('/blog/<pid>/react', methods=['POST'])
def blog_react(pid: str):
    site = load_site()
    if site['design'].get('maintenance') or not site['design'].get('comments_enabled'):
        return jsonify({'error': 'disabled'}), 403
    member = current_member(request)
    if member is None:
        return jsonify({'error': 'auth'}), 403
    if _visible_post(site, pid) is None:
        return jsonify({'error': 'not found'}), 404
    emoji = (request.get_json(silent=True) or {}).get('emoji', '')
    if emoji not in COMMENT_REACTIONS:
        return jsonify({'error': 'invalid'}), 400
    data = load_comments()
    thread = _post_thread(data, pid)
    reactions = thread.setdefault('reactions', {})
    if reactions.get(member['id']) == emoji:
        reactions.pop(member['id'], None)   # gleiche Reaktion → abwählen (Toggle)
        mine = None
    else:
        reactions[member['id']] = emoji
        mine = emoji
    save_comments(data)
    return jsonify({'ok': True, 'counts': _reaction_counts(reactions), 'mine': mine})


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
    text_html = render_md(loc(post, 'text'))
    return render_template('post.html', t=t, lang=lang, site=site, loc=loc, p=post,
                           text_html=text_html, preview=True,
                           meta_desc=(loc(post, 'meta') or _plain_excerpt(text_html) or _site_meta(site, loc)),
                           year=datetime.now(timezone.utc).year)


@admin_app.route('/preview/page/<pid>')
def admin_page_preview(pid: str):
    """Seiten-Vorschau im Admin — rendert page.html (auch unveröffentlicht)."""
    err = _auth_required()
    if err:
        return err
    lang = detect_language(request)
    site = load_site()
    page = next((p for p in site.get('pages', []) if p.get('id') == pid), None)
    if page is None:
        abort(404)
    t = load_translations(lang)
    loc = _loc_factory(lang)
    body_html = render_md(loc(page, 'body'))
    font_family, font_faces = font_css(site['design'])
    return render_template('page.html', t=t, lang=lang, site=site, loc=loc,
                           title=(loc(page, 'title') or t.get('page_untitled', '')),
                           body_html=body_html, nav_items=_nav_links(site, loc),
                           page_slug=page.get('slug', ''),
                           members_only=bool(page.get('members_only')),
                           font_family=font_family, font_faces=font_faces,
                           meta_desc=(loc(page, 'meta') or _plain_excerpt(body_html) or _site_meta(site, loc)),
                           year=datetime.now(timezone.utc).year)


@admin_app.route('/preview/form/<fid>')
def admin_form_preview(fid: str):
    """Formular-Vorschau im Admin — rendert form.html (auch unveröffentlicht)."""
    err = _auth_required()
    if err:
        return err
    lang = detect_language(request)
    site = load_site()
    form = next((f for f in site.get('forms', []) if f.get('id') == fid), None)
    if form is None:
        abort(404)
    return _render_form(form, site, lang)


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
    long_html = render_md(loc(proj, 'long'))
    return render_template('project.html', t=t, lang=lang, site=site, loc=loc, p=proj,
                           long_html=long_html,
                           meta_desc=(loc(proj, 'desc') or _plain_excerpt(long_html) or _site_meta(site, loc)),
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
                           can_reset=reset_enabled() if member is None else False,
                           can_register=registration_open() if member is None else False,
                           games_on=bool(member and member.get('games_enabled', True)),
                           year=datetime.now(timezone.utc).year)


def _member_auth_page(view: str, **extra):
    """Login-/Forgot-/Reset-/Register-Karte (immer ohne eingeloggtes Mitglied)."""
    lang = detect_language(request)
    t = load_translations(lang)
    site = load_site()
    return render_template('member.html', t=t, lang=lang, site=site, member=None,
                           files=[], used=0, quota=0, msg=extra.pop('msg', ''),
                           storage_down=False, login_msg_html='', view=view,
                           can_reset=reset_enabled(), can_register=registration_open(),
                           year=datetime.now(timezone.utc).year, **extra)


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
    blocked = _member_login_blocked(user)
    if blocked:
        log.info("Mitglieder-Login abgewiesen ('%s'): %s", email, blocked)
        return redirect('/bereich?msg=' + blocked)  # unverified | pending
    token = secrets.token_hex(32)
    user_sessions[token] = [user['id'], time.time() + USER_SESSION_HOURS * 3600]
    save_user_sessions()
    log_user_event(user['id'], 'login', '', ip)
    resp = make_response(redirect('/bereich'))
    resp.set_cookie('usession', token, httponly=True, samesite='Lax',
                    max_age=USER_SESSION_HOURS * 3600)
    log.info("Mitglieder-Login ERFOLGREICH: '%s' von %s", email, ip)
    return resp


@public_app.route('/bereich/forgot', methods=['GET', 'POST'])
def member_forgot():
    site = load_site()
    if site['design'].get('maintenance'):
        return _maintenance_page(site, detect_language(request))
    if not reset_enabled():
        return redirect('/bereich')
    if request.method == 'GET':
        return _member_auth_page('forgot')
    ip = get_client_ip(request)
    # Immer dieselbe, generische Antwort → keine Rückschlüsse, ob die E-Mail existiert.
    if reset_rate_limited(ip):
        log.warning("Passwort-Reset RATELIMIT von %s", ip)
        return _member_auth_page('forgot', msg='reset_sent')
    record_reset_attempt(ip)
    email = (request.form.get('email') or '').strip().lower()
    users = load_users()
    user = next((u for u in users if u['email'] == email), None) if _EMAIL_RE.match(email) else None
    if user is not None:
        token = secrets.token_urlsafe(32)
        user['reset'] = {'hash': generate_password_hash(token), 'exp': int(time.time()) + RESET_TTL}
        save_users(users)
        threading.Thread(target=send_reset_email, args=(dict(user), token), daemon=True).start()
        log.info("Passwort-Reset angefordert für '%s' von %s", email, ip)
    return _member_auth_page('forgot', msg='reset_sent')


@public_app.route('/bereich/reset/<uid>/<token>', methods=['GET', 'POST'])
def member_reset(uid: str, token: str):
    site = load_site()
    if site['design'].get('maintenance'):
        return _maintenance_page(site, detect_language(request))
    users = load_users()
    user = _find_reset_user(users, uid, token)
    if user is None:
        return _member_auth_page('reset', uid=uid, token=token, reset_valid=False)
    if request.method == 'GET':
        return _member_auth_page('reset', uid=uid, token=token, reset_valid=True)
    pw = request.form.get('password') or ''
    pw2 = request.form.get('password2') or ''
    if len(pw) < 8:
        return _member_auth_page('reset', uid=uid, token=token, reset_valid=True, msg='reset_short')
    if pw != pw2:
        return _member_auth_page('reset', uid=uid, token=token, reset_valid=True, msg='reset_mismatch')
    user['pw_hash'] = generate_password_hash(pw)
    user.pop('reset', None)
    save_users(users)
    invalidate_user_sessions(uid)  # alle alten Sitzungen kappen
    log_user_event(uid, 'pw_reset_self', '', get_client_ip(request))
    log.info("Passwort per Self-Service zurückgesetzt für '%s'", user['email'])
    return redirect('/bereich?msg=pwchanged')


@public_app.route('/bereich/register', methods=['GET', 'POST'])
def member_register():
    site = load_site()
    if site['design'].get('maintenance'):
        return _maintenance_page(site, detect_language(request))
    if not registration_open():
        return redirect('/bereich')
    if request.method == 'GET':
        return _member_auth_page('register', captcha=make_captcha())
    ip = get_client_ip(request)
    # Honeypot (Bots füllen das versteckte Feld) + Rate-Limit → generische Antwort
    if (request.form.get('website') or '').strip() or register_rate_limited(ip):
        return _member_auth_page('register', msg='register_sent')
    if not check_captcha(request.form.get('captcha_token'), request.form.get('captcha_answer')):
        return _member_auth_page('register', msg='register_captcha', captcha=make_captcha(),
                                 reg_email=_clean_str(request.form.get('email'), 150),
                                 reg_name=_clean_str(request.form.get('name'), 60))
    email = _clean_str(request.form.get('email'), 150).lower()
    pw = request.form.get('password') or ''
    pw2 = request.form.get('password2') or ''
    name = _clean_str(request.form.get('name'), 60)
    if not _EMAIL_RE.match(email):
        return _member_auth_page('register', msg='register_email', captcha=make_captcha(), reg_name=name)
    if len(pw) < 8:
        return _member_auth_page('register', msg='reset_short', captcha=make_captcha(),
                                 reg_email=email, reg_name=name)
    if pw != pw2:
        return _member_auth_page('register', msg='reset_mismatch', captcha=make_captcha(),
                                 reg_email=email, reg_name=name)
    record_register_attempt(ip)
    users = load_users()
    existing = next((u for u in users if u['email'] == email), None)
    token = secrets.token_urlsafe(32)
    if existing is None:
        quota = max(1, min(100000, int(site['design'].get('registration_quota_mb') or 500)))
        user = {'id': uuid.uuid4().hex[:12], 'email': email,
                'pw_hash': generate_password_hash(pw),
                'quota_mb': quota, 'created': date.today().isoformat(),
                'self_registered': True, 'verified': False, 'approved': False,
                'games_enabled': False,
                'verify': {'hash': generate_password_hash(token), 'exp': int(time.time()) + REGISTER_TTL}}
        if name:
            user['name'] = name
        users.append(user)
        save_users(users)
        threading.Thread(target=send_verify_email, args=(dict(user), token), daemon=True).start()
        notify_ha_async('🆕 MyPage: Neue Registrierung',
                        f'{email} hat ein Konto angelegt (wartet auf E-Mail-Bestätigung & Freigabe).',
                        notification_id=f'mypage_register_{user["id"]}')
        log.info("Selbst-Registrierung: '%s' von %s", email, ip)
    elif existing.get('self_registered') and not existing.get('verified'):
        # Konto besteht, aber noch unbestätigt → Bestätigungslink neu schicken
        existing['verify'] = {'hash': generate_password_hash(token), 'exp': int(time.time()) + REGISTER_TTL}
        save_users(users)
        threading.Thread(target=send_verify_email, args=(dict(existing), token), daemon=True).start()
    else:
        # E-Mail existiert bereits → keine Enumeration, stattdessen Hinweis-Mail
        threading.Thread(target=send_already_registered_email, args=(dict(existing),), daemon=True).start()
    return _member_auth_page('register', msg='register_sent')


@public_app.route('/bereich/verify/<uid>/<token>')
def member_verify(uid: str, token: str):
    site = load_site()
    if site['design'].get('maintenance'):
        return _maintenance_page(site, detect_language(request))
    users = load_users()
    user = _find_verify_user(users, uid, token)
    if user is None:
        return _member_auth_page('verify', verify_ok=False)
    user['verified'] = True
    user.pop('verify', None)
    save_users(users)
    notify_ha_async('✅ MyPage: Registrierung bestätigt',
                    f'{user["email"]} hat die E-Mail bestätigt und wartet auf Freigabe.',
                    notification_id=f'mypage_register_{uid}')
    _ha_sensors_async()  # „offene Freigaben"-Sensor/Hinweis sofort aktualisieren
    log.info("Registrierung bestätigt: '%s'", user['email'])
    return _member_auth_page('verify', verify_ok=True)


@public_app.route('/bereich/logout')
def member_logout():
    token = request.cookies.get('usession')
    if token and token in user_sessions:
        del user_sessions[token]
        save_user_sessions()
    resp = make_response(redirect('/bereich'))
    resp.delete_cookie('usession')
    return resp


@public_app.route('/bereich/profile', methods=['POST'])
def member_profile():
    member = current_member(request)
    if member is None:
        abort(403)
    users = load_users()
    user = next((u for u in users if u['id'] == member['id']), None)
    if user is None:
        abort(403)
    action = request.form.get('action', '')
    if action == 'name':
        user['name'] = _clean_str(request.form.get('name'), 60)
        save_users(users)
        log_user_event(user['id'], 'profile_name', '', get_client_ip(request))
        return redirect('/bereich?msg=profile_saved')
    if action == 'password':
        cur = request.form.get('current_password') or ''
        new = request.form.get('new_password') or ''
        new2 = request.form.get('new_password2') or ''
        if not check_password_hash(user['pw_hash'], cur):
            return redirect('/bereich?msg=pw_wrong')
        if len(new) < 8:
            return redirect('/bereich?msg=pw_short')
        if new != new2:
            return redirect('/bereich?msg=pw_mismatch')
        user['pw_hash'] = generate_password_hash(new)
        save_users(users)
        # andere Sitzungen kappen, die aktuelle behalten
        invalidate_user_sessions(user['id'], keep=request.cookies.get('usession'))
        log_user_event(user['id'], 'pw_change_self', '', get_client_ip(request))
        log.info("Mitglied '%s' hat das Passwort selbst geändert", user['email'])
        return redirect('/bereich?msg=pw_changed')
    return redirect('/bereich')


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
    msg_id = uuid.uuid4().hex[:12]
    msgs = load_messages()
    msgs.append({
        'id':    msg_id,
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
        notify_ha(f'📨 MyPage: Neue Nachricht von {name}',
                  (f'Von {name}' + (f' ({email})' if email else '') + f':\n\n{message[:400]}'),
                  notification_id=f'mypage_msg_{msg_id}')

    threading.Thread(target=_notify, daemon=True).start()
    log.info("Kontaktnachricht von '%s' gespeichert", name)
    return jsonify({'ok': True})


def _render_form(form: dict, site: dict, lang: str, *, error: str = '', ok: bool = False):
    t = load_translations(lang)
    loc = _loc_factory(lang)
    fields = []
    for f in form.get('fields', []):
        fields.append({
            'id': f['id'], 'type': f['type'], 'required': f.get('required'),
            'label': loc(f, 'label') or f['id'],
            'placeholder': loc(f, 'placeholder'),
            'options': f.get('options', []),
        })
    return render_template('form.html', t=t, lang=lang, site=site, loc=loc,
                           form=form, title=loc(form, 'title'),
                           intro_html=render_md(loc(form, 'intro')),
                           success_html=render_md(loc(form, 'success')) if ok else '',
                           fields=fields, captcha=make_captcha(),
                           nav_items=_nav_links(site, loc),
                           font_family=font_css(site['design'])[0],
                           font_faces=font_css(site['design'])[1],
                           error=error, ok=ok, form_slug=form['slug'],
                           meta_desc=(_plain_excerpt(render_md(loc(form, 'intro'))) or _site_meta(site, loc)),
                           year=datetime.now(timezone.utc).year)


@public_app.route('/formular/<slug>')
def custom_form(slug: str):
    lang = detect_language(request)
    site = load_site()
    if site['design'].get('maintenance'):
        return _maintenance_page(site, lang)
    form = _find_form(site, slug)
    if form is None or not form.get('enabled'):
        abort(404)
    count_visit(request)
    return _render_form(form, site, lang, ok=bool(request.args.get('ok')))


@public_app.route('/formular/<slug>', methods=['POST'])
def custom_form_submit(slug: str):
    lang = detect_language(request)
    site = load_site()
    if site['design'].get('maintenance'):
        return _maintenance_page(site, lang)
    form = _find_form(site, slug)
    if form is None or not form.get('enabled'):
        abort(404)
    t = load_translations(lang)
    # Honeypot: Bots füllen das versteckte Feld aus → still „erfolgreich"
    if (request.form.get('website') or '').strip():
        return redirect('/formular/' + slug + '?ok=1')
    if not check_captcha(request.form.get('captcha_token'), request.form.get('captcha_answer')):
        return _render_form(form, site, lang, error=t.get('form_err_captcha', ''))
    ip = get_client_ip(request)
    now = time.time()
    _contact_times[ip] = [x for x in _contact_times[ip] if now - x < 3600]
    if len(_contact_times[ip]) >= CONTACT_MAX_PER_HOUR:
        return _render_form(form, site, lang, error=t.get('form_err_rate', ''))

    loc = _loc_factory(lang)
    entries, sub_name, sub_email = [], '', ''
    for f in form.get('fields', []):
        label = loc(f, 'label') or f['id']
        if f['type'] == 'checkbox':
            val = t.get('form_yes', 'Ja') if request.form.get('f_' + f['id']) else t.get('form_no', 'Nein')
        else:
            val = _clean_str(request.form.get('f_' + f['id']), 3000)
        if f.get('required') and not (request.form.get('f_' + f['id']) or '').strip():
            return _render_form(form, site, lang, error=t.get('form_err_required', ''))
        entries.append({'label': label, 'value': val})
        if not sub_email and f['type'] == 'email' and val:
            sub_email = val[:150]
        if not sub_name and f['type'] == 'text' and val:
            sub_name = val[:80]

    _contact_times[ip].append(now)
    msg_id = uuid.uuid4().hex[:12]
    form_title = loc(form, 'title') or t.get('form_untitled', 'Formular')
    summary = '\n'.join(f"{e['label']}: {e['value']}" for e in entries)
    msgs = load_messages()
    msgs.append({
        'id': msg_id, 'ts': int(now),
        'name': sub_name or form_title, 'email': sub_email,
        'text': summary, 'form': form_title, 'fields': entries,
    })
    save_messages(msgs)

    if form.get('notify', True):
        def _notify():
            send_telegram(f"📋 MyPage — {form_title}:\n\n{summary[:800]}")
            esc = html_mod.escape
            lines = [f'<b>{esc(e["label"])}:</b> {esc(e["value"]).replace(chr(10), "<br>")}' for e in entries]
            send_email(f'MyPage — {form_title}', _email_html(f'📋 {esc(form_title)}', lines))
            notify_ha(f'📋 MyPage: {form_title}', summary[:400],
                      notification_id=f'mypage_form_{msg_id}')
        threading.Thread(target=_notify, daemon=True).start()
    log.info("Formular-Einsendung '%s' gespeichert", form_title)
    return redirect('/formular/' + slug + '?ok=1')


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


@public_app.route('/seite/<slug>')
def custom_page(slug: str):
    lang = detect_language(request)
    site = load_site()
    if site['design'].get('maintenance'):
        return _maintenance_page(site, lang)
    page = _find_page(site, slug)
    if page is None or not page.get('visible'):
        abort(404)
    count_visit(request)
    t = load_translations(lang)
    loc = _loc_factory(lang)
    title = loc(page, 'title') or t.get('page_untitled', '')
    full_html = render_md(loc(page, 'body'))
    locked = bool(page.get('members_only')) and not is_member(request)
    body_html = ('<p>' + _locked_teaser(full_html) + '</p>') if locked else full_html
    nav_items = _nav_links(site, loc) if site['design'].get('show_nav', True) else []
    font_family, font_faces = font_css(site['design'])
    return render_template('page.html', t=t, lang=lang, site=site, loc=loc,
                           title=title, body_html=body_html, nav_items=nav_items,
                           page_slug=slug, locked=locked,
                           members_only=bool(page.get('members_only')),
                           font_family=font_family, font_faces=font_faces,
                           meta_desc=(loc(page, 'meta') or _plain_excerpt(body_html)
                                      or _site_meta(site, loc)),
                           year=datetime.now(timezone.utc).year)


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
    threading.Thread(target=_ha_games_worker, daemon=True).start()
    threading.Thread(target=_geoip_worker, daemon=True).start()
    threading.Thread(target=_smb_watchdog, daemon=True).start()

    log.info("MyPage bereit — öffentlich: %d, Admin: %d", PUBLIC_PORT, ADMIN_PORT)
    admin_app.run(host='0.0.0.0', port=ADMIN_PORT, debug=False, threaded=True)
