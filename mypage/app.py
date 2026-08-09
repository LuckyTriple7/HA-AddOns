#!/usr/bin/env python3
"""MyPage — Homepage-Baukasten für Home Assistant.

Zwei Server in einem Prozess:
  - Port 17760: öffentliche Homepage (kein Login, Besucherzähler)
  - Port 17761: Admin-Panel (Login + Brute-Force-Schutz, auch via HA Ingress)
"""
import base64
import copy
import csv
import errno
import hashlib
import hmac
import html as html_mod
import io
import ipaddress
import json
import logging
import mimetypes
import os
import re
import secrets
import shutil
import signal
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
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse, urlsplit, urlunsplit

import markdown as md_lib
from markupsafe import Markup, escape
try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False
try:
    # Optional: PDF-Erzeugung für Bibliothek-Einträge. Braucht System-Bibliotheken
    # (pango/cairo). Fehlt das Paket, fällt der PDF-Button auf die Druckansicht
    # zurück — das Add-on startet in jedem Fall.
    from weasyprint import HTML as _WeasyHTML
    _HAS_WEASY = True
except Exception:
    _HAS_WEASY = False
try:
    # Optional: KI-Bilderzeugung (Google Gemini) für Bibliothek-Titelbilder.
    # Fehlt das Paket, bleibt der Knopf im Admin aus — das Add-on startet
    # in jedem Fall. Breites except wie oben: das SDK baut beim Import
    # Pydantic-Modelle auf und kann dabei auch anders als mit ImportError
    # scheitern.
    from google import genai
    from google.genai import errors as genai_errors
    from google.genai import types as genai_types
    _HAS_GENAI = True
except Exception:
    _HAS_GENAI = False
from flask import (Flask, render_template, request, redirect, url_for,
                   make_response, jsonify, abort, send_from_directory,
                   send_file)
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from waitress import serve
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
import game_kniffel
import game_chicago

logging.basicConfig(format='[%(levelname)s] [%(asctime)s] %(message)s',
                    level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S', force=True)
log = logging.getLogger(__name__)
logging.getLogger('werkzeug').setLevel(logging.ERROR)
# fontTools protokolliert beim PDF-Erzeugen jeden Teilschritt der Schrift-Optimierung
# ("glyf pruned", "GDEF pruned", …) auf INFO — pro PDF dutzende Zeilen. Nur Warnungen.
for _noisy in ('fontTools', 'fontTools.subset', 'fontTools.ttLib'):
    logging.getLogger(_noisy).setLevel(logging.WARNING)
# google-genai meldet bei jeder Anfrage „AFC is enabled with max remote calls: 10"
# auf INFO — eine Einstellung, die MyPage gar nicht nutzt. Nur Warnungen.
logging.getLogger('google_genai').setLevel(logging.WARNING)

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
AI_USAGE_PATH = _DATA + '/ai_usage.json'   # Gemini-Verbrauch je Monat und Modell
USESSIONS_PATH = _DATA + '/user_sessions.json'
DM_PATH       = _DATA + '/dm.json'          # Mitglieder-Direktnachrichten (Text verschlüsselt)
DMKEY_PATH    = _DATA + '/dm.key'           # Fernet-Schlüssel für die DM-Verschlüsselung
TWOFA_PATH    = _DATA + '/admin_2fa.json'   # TOTP-Secret + Backup-Codes (Admin-2FA)
SECRETKEY_PATH = _DATA + '/secret.key'      # Flask SECRET_KEY (signiert das trust2fa-Cookie)
POLLS_PATH    = _DATA + '/polls.json'       # Umfrage-Stimmen (getrennt von site.json)
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
# Zwischenablage des KI-Studios: frisch erzeugte Bilder liegen hier, bis der
# Admin sie übernimmt. Bewusst NICHT unter uploads/ — was dort liegt, ist sofort
# öffentlich abrufbar und landet im Backup. Verworfene Entwürfe sollen spurlos
# verschwinden; write_backup_zip listet die Ordner einzeln auf, dieser fehlt dort.
AI_TMP_DIR = Path(_DATA) / 'ai_tmp'
AI_TMP_DIR.mkdir(parents=True, exist_ok=True)
# Kartenspiel-Spielstände (lokal im addon_config, NICHT auf dem SMB-Share)
GAMES_DIR = Path(_DATA) / 'games'
GAMES_DIR.mkdir(parents=True, exist_ok=True)
# Mitglieder-Avatare fürs Verzeichnis (lokal, klein, NICHT auf dem SMB-Share)
MEMBER_AVATARS_DIR = Path(_DATA) / 'member_avatars'
MEMBER_AVATARS_DIR.mkdir(parents=True, exist_ok=True)
# Verschlüsselte Datei-Anhänge der Mitglieder-Nachrichten (lokal, NICHT auf SMB)
DM_FILES_DIR = Path(_DATA) / 'dm_files'
DM_FILES_DIR.mkdir(parents=True, exist_ok=True)
# Bibliothek-Dokumente (hochgeladene und erzeugte PDFs). Eigener Ordner, damit sie
# nicht über die offene /uploads/-Route inline im Browser landen können.
DOCS_DIR = Path(_DATA) / 'docs'
DOCS_DIR.mkdir(parents=True, exist_ok=True)
_DOC_FILE_RE = re.compile(r'^[a-f0-9]{32}\.pdf$')
# Dauerhaftes Besucher-Archiv (optional, Option visit_file_log). Liegt im
# Add-on-Konfigurationsordner und ist damit über den Share erreichbar:
# \\<host>\addon_configs\XXX_mypage\visits\visits-JJJJ-MM.csv
VISITS_DIR = Path(_DATA) / 'visits'
_VISIT_FILE_RE = re.compile(r'^visits-(\d{4})-(\d{2})\.csv$')
_visit_file_lock = threading.Lock()
VISIT_CSV_COLUMNS = ('datum', 'ip', 'land', 'browser', 'system', 'pfad', 'referrer',
                     'sprache', 'bot', 'neuer_besucher', 'user_agent')
# Automatische tägliche Backups — landen unter addon_configs/<slug>_mypage/autobackup/,
# also im selben Ordner wie die Daten (map: app_config:rw). Bewusst NICHT Teil des
# Backup-Inhalts, sonst würde sich jedes Backup mit allen Vorgängern selbst aufblähen.
BACKUPS_DIR = Path(_DATA) / 'autobackup'
BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
AUTO_BACKUP_KEEP_DEFAULT = 7
_AUTO_BACKUP_RE = re.compile(r'^mypage-auto-\d{4}-\d{2}-\d{2}\.zip$')
# Erlaubte Spieldateinamen (für Backup/Restore): <spiel>_<uid>.json /
# <spiel>hist_<uid>.json / gsessions_<uid>.json (Sitzungs-Log)
_GAME_FILE_RE = re.compile(
    r'^(?:(?:66|20ab|schwimmen|maumau|praesident|jeopardy|gluecksrad|kniffel|chicago)(?:hist)?|gsessions)_[a-f0-9]{6,32}\.json$')
# Kartendecks (mitgeliefert, austauschbar) — /app/static/cards/<deck>/<rang><farbe>.svg
CARDS_DIR = Path(_BASE) / 'static' / 'cards'

# ── Flask-Apps ────────────────────────────────────────────────────────────────

def _load_or_create_secret_key(path: str) -> str:
    try:
        if os.path.exists(path):
            with open(path, encoding='ascii') as f:
                return f.read().strip()
        key = secrets.token_hex(32)
        with open(path, 'w', encoding='ascii') as f:
            f.write(key)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return key
    except Exception as e:
        log.warning("Secret-Key konnte nicht geladen/erzeugt werden: %s", e)
        return secrets.token_hex(32)   # nur für diesen Prozesslauf gültig


public_app = Flask('mypage_public', template_folder=_BASE + '/templates')
admin_app  = Flask('mypage_admin',  template_folder=_BASE + '/templates')
admin_app.config['SECRET_KEY'] = _load_or_create_secret_key(SECRETKEY_PATH)
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
_dm_lock    = threading.Lock()
_2fa_lock   = threading.Lock()
_subs_lock = threading.Lock()
_slot_lock  = threading.Lock()
_game_lock  = threading.Lock()
_polls_lock = threading.Lock()

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
# Marker im Dateinamen für KI-erzeugte Bilder (`<uuid>-ai.webp`). Daran macht die
# Auslieferung die vorgeschriebene Kennzeichnung fest — siehe _store_upload_image.
AI_IMAGE_SUFFIX = '-ai'
# Dokumente bewusst getrennt: sie dürfen NICHT über /uploads/<name> ausgeliefert
# werden (dort landen sie inline im Browser), sondern nur über die Bibliothek-Route
# mit Content-Disposition: attachment.
ALLOWED_DOC_EXT = {'.pdf'}
DOC_MAX_BYTES = 25 * 1024 * 1024
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
        'share_enabled': False,
        'dm_enabled': False,
        'dm_ha_notify': False,
        'directory_enabled': False,
        'search_enabled': False,
        'registration_enabled': False,
        'registration_quota_mb': 500,
        'newsletter_enabled': False,
        'weekly_review': False,
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
        'google_verify': '', 'bing_verify': '',
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
        'countdown': {},
        'freetext': {},
        'poll': {},
    },
    'albums': [],
    'album_protect': False,
    'watermark_text': '',
    'library': {
        'label_de': '', 'label_en': '',
        'intro_de': '', 'intro_en': '',
        'nav': True,
        'categories': [],
        'entries': [],
    },
    'section_order': [
        'news', 'countdown', 'tips', 'freetext', 'poll', 'blog', 'services', 'projects', 'skills', 'testimonials',
        'photos', 'library', 'team', 'timeline', 'events', 'links', 'faq', 'location',
    ],
    'hidden_sections': [],
    'members_sections': [],
    'redirects': [],
    'tips_rotation': 'daily',
    'tips_random': False,
    'tips_stats': {},
    'indexnow_key': '',
    'slot_jackpot': 500,
    # KI-Vorgaben aus dem Admin. Leer = die Add-on-Optionen gelten; ein gesetzter
    # Wert schlägt sie, damit ein Modellwechsel ohne HA-Neustart möglich ist.
    'ai': {
        'image_model': '', 'text_model': '', 'image_ratio': '',
        'translate_provider': 'mymemory',
    },
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


def _reading_minutes(html: str) -> int:
    """Geschätzte Lesezeit in Minuten aus dem Klartext (≈200 Wörter/Min, min. 1)."""
    plain = re.sub(r'<[^>]+>', ' ', html or '')
    words = len(plain.split())
    return max(1, round(words / 200))


def _related_posts(site: dict, post: dict, loc, limit: int = 3) -> list:
    """Bis zu `limit` sichtbare andere Beiträge, die Schlagwörter mit `post` teilen
    (nach Anzahl gemeinsamer Tags, dann Datum sortiert)."""
    tags = {str(t).lower() for t in (post.get('tags') or [])}
    if not tags:
        return []
    scored = []
    for p in site.get('posts', []):
        if p.get('id') == post.get('id') or not post_visible(p):
            continue
        shared = tags & {str(t).lower() for t in (p.get('tags') or [])}
        if shared:
            scored.append((len(shared), p.get('date') or '', p))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [{'id': p['id'], 'title': loc(p, 'title'), 'date': p.get('date') or '',
             'image': p.get('image') or ''} for _, _, p in scored[:limit]]


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

def _atomic_write_json(path: str, data, *, indent: int | None = None,
                       ensure_ascii: bool = False, mode: int | None = None) -> None:
    """Schreibt JSON atomar: erst vollständig in <datei>.tmp, dann os.replace().

    Ein einfaches open(path, 'w') kürzt die Zieldatei sofort auf 0 Byte. Stirbt der
    Prozess in diesem Moment (z. B. SIGKILL beim Add-on-Stop), bleibt eine leere oder
    halbe Datei zurück. os.replace() ist auf einem Dateisystem atomar — es existiert
    immer entweder der alte oder der neue Stand, nie etwas dazwischen.
    """
    tmp = f'{path}.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)
        f.flush()
        os.fsync(f.fileno())   # erst auf die Platte, dann umbenennen
    if mode is not None:
        try:
            os.chmod(tmp, mode)   # Rechte vor dem Umbenennen setzen — kein offenes Fenster
        except OSError:
            pass
    os.replace(tmp, path)


def _quarantine_corrupt(path: str, exc: Exception) -> None:
    """Beschädigte Datei zur Seite legen, statt sie beim nächsten Speichern zu verlieren.

    Ohne das würde nach einem Lesefehler mit Standardwerten weitergearbeitet und der
    nächste save_*()-Aufruf die (evtl. reparierbaren) Reste überschreiben.
    """
    name = os.path.basename(path)
    try:
        backup = f'{path}.corrupt-{datetime.now().strftime("%Y%m%d-%H%M%S")}'
        os.replace(path, backup)
        log.error("%s ist beschädigt (%s) — gesichert als %s. Es wird mit Standardwerten "
                  "weitergearbeitet!", name, exc, os.path.basename(backup))
    except Exception as e:
        log.error("%s ist beschädigt (%s) und konnte nicht gesichert werden: %s", name, exc, e)
    notify_ha_async(
        '⚠️ MyPage: Beschädigte Datendatei',
        f'{name} konnte nicht gelesen werden und wurde zur Seite gelegt. '
        f'MyPage arbeitet vorerst mit Standardwerten — bitte ein Backup einspielen.',
        notification_id=f'mypage_corrupt_{name}')


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
            # Beschädigte site.json nicht still mit Defaults überschreiben — sonst
            # setzt der nächste save_site() die komplette Seite zurück.
            _quarantine_corrupt(SITE_PATH, e)
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
            _atomic_write_json(SITE_PATH, data, indent=2)
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
            _quarantine_corrupt(STATS_PATH, e)
            return {'total': 0, 'days': {}}


def save_stats(data: dict) -> None:
    with _stats_lock:
        try:
            _atomic_write_json(STATS_PATH, data)
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
            _quarantine_corrupt(MESSAGES_PATH, e)
            return []


def save_messages(data: list) -> None:
    with _msg_lock:
        try:
            _atomic_write_json(MESSAGES_PATH, data[-MESSAGES_MAX:], indent=2)
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
            _quarantine_corrupt(COMMENTS_PATH, e)
            return {}


def save_comments(data: dict) -> None:
    with _comments_lock:
        try:
            _atomic_write_json(COMMENTS_PATH, data, indent=2)
        except Exception as e:
            log.warning("comments.json konnte nicht gespeichert werden: %s", e)


def _post_thread(data: dict, pid: str) -> dict:
    return data.setdefault(pid, {'comments': [], 'reactions': {}})


# ── Umfrage (Startseiten-Sektion) ─────────────────────────────────────────────
# Definition (Frage + Optionen) liegt in site.json; die Stimmen getrennt in
# polls.json: {'id': <umfrage-id>, 'votes': {'u:<uid>'|'c:<cookie>': opt_idx}}
POLL_VOTES_MAX = 20000  # Schutz vor Cookie-Spam anonymer Besucher


def load_poll_votes() -> dict:
    with _polls_lock:
        try:
            with open(POLLS_PATH, encoding='utf-8') as f:
                d = json.load(f)
                return d if isinstance(d, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception as e:
            _quarantine_corrupt(POLLS_PATH, e)
            return {}


def save_poll_votes(data: dict) -> None:
    with _polls_lock:
        try:
            _atomic_write_json(POLLS_PATH, data)
        except Exception as e:
            log.warning("polls.json konnte nicht gespeichert werden: %s", e)


def _active_poll(site: dict) -> dict | None:
    """Umfrage nur, wenn Frage und mindestens 2 Optionen gepflegt sind."""
    poll = (site.get('sections') or {}).get('poll') or {}
    opts = poll.get('options') or []
    if poll.get('id') and (poll.get('question_de') or poll.get('question_en')) and len(opts) >= 2:
        return poll
    return None


def _poll_counts(poll: dict, votes: dict) -> list:
    """Stimmen je Option zählen; Stimmen gehören nur zur aktuellen Umfrage-ID."""
    counts = [0] * len(poll.get('options') or [])
    if votes.get('id') != poll.get('id'):
        return counts
    for v in (votes.get('votes') or {}).values():
        if isinstance(v, int) and 0 <= v < len(counts):
            counts[v] += 1
    return counts


def _reaction_counts(reactions: dict) -> dict:
    """{uid: emoji} → {emoji: anzahl}"""
    counts: dict[str, int] = {}
    for emoji in (reactions or {}).values():
        counts[emoji] = counts.get(emoji, 0) + 1
    return counts


def _member_display_name(member: dict) -> str:
    return member.get('name') or (member.get('email') or '').split('@')[0] or 'Mitglied'


# ── Mitglieder-Verzeichnis (opt-in: Avatar + Kurz-Bio) ────────────────────────
DIRECTORY_BIO_MAX = 300


def directory_on() -> bool:
    return bool(load_site()['design'].get('directory_enabled'))


def _has_avatar(uid: str) -> bool:
    if not _UID_RE.match(uid):
        return False
    p = safe_under(MEMBER_AVATARS_DIR, f'{uid}.jpg')
    return p is not None and p.is_file()


def _save_member_avatar(uid: str, f) -> bool:
    """Speichert ein quadratisch zugeschnittenes, verkleinertes JPEG (ohne EXIF)."""
    if not (_HAS_PIL and _UID_RE.match(uid) and f and f.filename):
        return False
    if Path(f.filename).suffix.lower() not in ALLOWED_UPLOAD_EXT:
        return False
    try:
        img = Image.open(f.stream)
        img = ImageOps.exif_transpose(img)            # Handy-Drehung + Metadaten weg
        img = ImageOps.fit(img, (256, 256))           # mittig quadratisch zuschneiden
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img.save(MEMBER_AVATARS_DIR / f'{uid}.jpg', 'JPEG', quality=85)
        return True
    except Exception as e:
        log.warning("Avatar konnte nicht gespeichert werden: %s", e)
        return False


def _delete_member_avatar(uid: str) -> None:
    if _UID_RE.match(uid):
        try:
            (MEMBER_AVATARS_DIR / f'{uid}.jpg').unlink(missing_ok=True)
        except OSError:
            pass


def _directory_members() -> list:
    """Alle Mitglieder, die sich fürs Verzeichnis sichtbar gemacht haben."""
    out = [{'id': u['id'], 'name': _member_display_name(u), 'bio': u.get('bio', ''),
            'avatar': _has_avatar(u['id']), 'can_dm': _dm_can_receive(u)}
           for u in load_users() if u.get('dir_visible')]
    out.sort(key=lambda x: x['name'].lower())
    return out


# ── Mitglieder-Direktnachrichten (Ende-zu-Ende auf der Platte verschlüsselt) ───
# Nachrichtentexte werden mit Fernet (AES-128-CBC + HMAC) verschlüsselt in dm.json
# abgelegt; nur Metadaten (wer/wann/gelesen) liegen im Klartext, damit Postfach und
# Ungelesen-Zähler ohne Entschlüsseln funktionieren.
try:
    from cryptography.fernet import Fernet, InvalidToken
    _HAS_CRYPTO = True
except Exception:  # Bibliothek fehlt (z. B. Minimal-Standalone) → Funktion deaktiviert
    _HAS_CRYPTO = False

_dm_fernet = None
DM_MAX_PER_PAIR = 500  # max. gespeicherte Nachrichten je Unterhaltung
DM_MAX_LEN = 4000      # max. Zeichen pro Nachricht
DM_ATT_MAX_BYTES = 25 * 1024 * 1024   # 25 MB pro Datei-Anhang
DM_ATT_EXT = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.pdf', '.txt', '.md', '.csv',
              '.zip', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods',
              '.mp3', '.m4a', '.ogg', '.wav', '.mp4', '.webm', '.mov'}
_FID_RE = re.compile(r'^[a-f0-9]{32}$')
ADMIN_DM_ID = '__admin__'  # Pseudo-Absender für Admin-Rundnachrichten (kein echtes Konto)


def _admin_dm_name() -> str:
    site = load_site()
    return site['design'].get('site_title') or site['profile'].get('name') or 'Team'


def _get_fernet():
    """Lädt (oder erzeugt einmalig) den DM-Schlüssel. None, wenn cryptography fehlt."""
    global _dm_fernet
    if _dm_fernet is not None:
        return _dm_fernet
    if not _HAS_CRYPTO:
        return None
    try:
        if os.path.exists(DMKEY_PATH):
            with open(DMKEY_PATH, 'rb') as f:
                key = f.read().strip()
        else:
            key = Fernet.generate_key()
            with open(DMKEY_PATH, 'wb') as f:
                f.write(key)
            try:
                os.chmod(DMKEY_PATH, 0o600)
            except OSError:
                pass
            log.info("DM-Verschlüsselungsschlüssel neu erzeugt")
        _dm_fernet = Fernet(key)
        return _dm_fernet
    except Exception as e:
        log.warning("DM-Schlüssel konnte nicht geladen/erzeugt werden: %s", e)
        return None


def _dm_reset_fernet() -> None:
    """Cache verwerfen — nach einem Restore kann dm.key ausgetauscht worden sein."""
    global _dm_fernet
    _dm_fernet = None


def dm_feature_on() -> bool:
    """Globaler Schalter + funktionsfähige Verschlüsselung."""
    return bool(load_site()['design'].get('dm_enabled')) and _get_fernet() is not None


def _dm_encrypt(text: str) -> str:
    f = _get_fernet()
    if f is None:
        return ''
    return f.encrypt(text.encode('utf-8')).decode('ascii')


def _dm_decrypt(token: str) -> str:
    f = _get_fernet()
    if f is None or not token:
        return ''
    try:
        return f.decrypt(token.encode('ascii')).decode('utf-8')
    except Exception:  # InvalidToken / beschädigte Daten → leer statt Absturz
        return ''


def load_dm() -> list:
    with _dm_lock:
        try:
            with open(DM_PATH, encoding='utf-8') as f:
                d = json.load(f)
                return d if isinstance(d, list) else []
        except FileNotFoundError:
            return []
        except Exception as e:
            _quarantine_corrupt(DM_PATH, e)
            return []


def save_dm(data: list) -> None:
    with _dm_lock:
        try:
            _atomic_write_json(DM_PATH, data, indent=2)
        except Exception as e:
            log.warning("dm.json konnte nicht gespeichert werden: %s", e)


def _dm_user_active(u: dict) -> bool:
    """Konto darf Nachrichten empfangen (freigegeben + verifiziert)."""
    return u.get('approved', True) is not False and u.get('verified', True) is not False


def _dm_can_receive(u: dict) -> bool:
    return _dm_user_active(u) and u.get('dm_enabled', True) is not False


def _dm_recipients(me_id: str) -> list:
    """Anschreibbare Mitglieder (Empfang an, ohne mich selbst), nach Name sortiert."""
    out = [{'id': u['id'], 'name': _member_display_name(u)}
           for u in load_users()
           if u['id'] != me_id and _dm_can_receive(u)]
    out.sort(key=lambda x: x['name'].lower())
    return out


def _dm_hidden(m: dict, me_id: str) -> bool:
    """True, wenn das Mitglied diese Nachricht für sich gelöscht hat."""
    return me_id in (m.get('del') or [])


def _dm_unread(me_id: str) -> int:
    return sum(1 for m in load_dm()
               if m.get('to') == me_id and not m.get('read') and not _dm_hidden(m, me_id))


def _dm_conversations(me_id: str) -> list:
    """Unterhaltungen des Mitglieds, neueste zuerst, mit Vorschau & Ungelesen-Zähler."""
    users = {u['id']: u for u in load_users()}
    convo: dict[str, dict] = {}
    for m in load_dm():
        frm, to = m.get('frm'), m.get('to')
        if me_id not in (frm, to) or _dm_hidden(m, me_id):
            continue
        partner = to if frm == me_id else frm
        c = convo.setdefault(partner, {'partner': partner, 'last_ts': 0,
                                       'unread': 0, '_tok': '', '_att': None, 'mine': False})
        ts = m.get('ts', 0)
        if ts >= c['last_ts']:
            c['last_ts'] = ts
            c['_tok'] = m.get('body', '')
            c['_att'] = m.get('att')
            c['mine'] = (frm == me_id)
        if to == me_id and not m.get('read'):
            c['unread'] += 1
    out = []
    for pid, c in convo.items():
        if pid == ADMIN_DM_ID:
            c['name'], c['gone'], c['admin'] = _admin_dm_name(), False, True
        else:
            u = users.get(pid)
            c['name'] = _member_display_name(u) if u else '—'
            c['gone'] = u is None
            c['admin'] = False
        prev = _dm_decrypt(c.pop('_tok', ''))[:90]
        att = c.pop('_att', None)
        c['preview'] = prev or (('📎 ' + att.get('name', '')) if att else '')
        out.append(c)
    out.sort(key=lambda x: x['last_ts'], reverse=True)
    return out


def _dm_thread(me_id: str, partner_id: str) -> list:
    """Nachrichten zwischen mir und Partner (chronologisch). Markiert eingehende als gelesen."""
    msgs = load_dm()
    out, changed = [], False
    for m in msgs:
        if {m.get('frm'), m.get('to')} == {me_id, partner_id} and not _dm_hidden(m, me_id):
            if m.get('to') == me_id and not m.get('read'):
                m['read'] = True
                changed = True
            out.append({'id': m.get('id'), 'ts': m.get('ts', 0),
                        'mine': m.get('frm') == me_id,
                        'text': _dm_decrypt(m.get('body', '')),
                        'att': m.get('att')})
    if changed:
        save_dm(msgs)
    out.sort(key=lambda x: x['ts'])
    return out


def _dm_att_path(fid: str) -> Path | None:
    return safe_under(DM_FILES_DIR, fid) if _FID_RE.match(fid or '') else None


def _dm_att_store(f) -> dict | None:
    """Validiert + verschlüsselt einen Datei-Anhang. Liefert {fid,name,size} oder None."""
    if not (f and f.filename):
        return None
    name = secure_filename(f.filename)
    if not name or Path(name).suffix.lower() not in DM_ATT_EXT:
        return None
    data = f.read(DM_ATT_MAX_BYTES + 1)
    if not data or len(data) > DM_ATT_MAX_BYTES:
        return None
    fer = _get_fernet()
    if fer is None:
        return None
    fid = uuid.uuid4().hex
    try:
        with open(DM_FILES_DIR / fid, 'wb') as out:
            out.write(fer.encrypt(data))
    except Exception as e:
        log.warning("DM-Anhang konnte nicht gespeichert werden: %s", e)
        return None
    return {'fid': fid, 'name': name, 'size': len(data)}


def _dm_att_read(fid: str) -> bytes | None:
    p = _dm_att_path(fid)
    fer = _get_fernet()
    if p is None or fer is None or not p.is_file():
        return None
    try:
        return fer.decrypt(p.read_bytes())
    except Exception:
        return None


def _dm_att_delete(fid: str) -> None:
    p = _dm_att_path(fid)
    if p is not None:
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass


def _dm_purge(msgs: list) -> list:
    """Entfernt Nachrichten endgültig, sobald kein lebendes Mitglied sie mehr behält;
    löscht dabei auch die verschlüsselten Anhang-Dateien."""
    uids = {u['id'] for u in load_users()}
    keep = []
    for m in msgs:
        dels = set(m.get('del') or [])
        alive = {p for p in (m.get('frm'), m.get('to')) if p in uids and p not in dels}
        if alive:
            keep.append(m)
        else:
            att = m.get('att')
            if att and att.get('fid'):
                _dm_att_delete(att['fid'])
    return keep


def _dm_delete_for(me_id: str, mid: str = '', partner_id: str = '') -> None:
    """Markiert eine Nachricht (mid) oder eine ganze Unterhaltung (partner_id)
    als für ``me_id`` gelöscht und räumt vollständig gelöschte Einträge auf."""
    msgs = load_dm()
    for m in msgs:
        if me_id not in (m.get('frm'), m.get('to')):
            continue
        hit = (mid and m.get('id') == mid) or \
              (partner_id and {m.get('frm'), m.get('to')} == {me_id, partner_id})
        if hit:
            d = m.setdefault('del', [])
            if me_id not in d:
                d.append(me_id)
    save_dm(_dm_purge(msgs))


def _dm_send(frm: str, to: str, text: str, att: dict | None = None) -> None:
    msgs = load_dm()
    msg = {'id': uuid.uuid4().hex[:12], 'frm': frm, 'to': to,
           'ts': int(time.time()), 'read': False, 'body': _dm_encrypt(text)}
    if att:
        msg['att'] = att
    msgs.append(msg)
    # History je Unterhaltung kappen (älteste dieses Paars zuerst entfernen)
    pair_idx = [i for i, m in enumerate(msgs)
                if {m.get('frm'), m.get('to')} == {frm, to}]
    if len(pair_idx) > DM_MAX_PER_PAIR:
        for i in pair_idx[:len(pair_idx) - DM_MAX_PER_PAIR]:
            a = (msgs[i].get('att') or {}).get('fid')
            if a:
                _dm_att_delete(a)
            msgs[i] = None
        msgs = [m for m in msgs if m is not None]
    save_dm(msgs)


def _dm_owner_notify(to_id: str) -> None:
    """Optionaler HA-Push an den Betreiber: Mitglied X hat ungelesene Nachrichten.
    Bewusst ohne Inhalt; je Empfänger zusammengefasst (gleiche notification_id)."""
    if not load_site()['design'].get('dm_ha_notify'):
        return
    user = next((u for u in load_users() if u['id'] == to_id), None)
    if user is None:
        return
    n = _dm_unread(to_id)
    name = _member_display_name(user)
    notify_ha_async('📨 MyPage: Neue Mitglieder-Nachricht',
                    f'{name} hat {n} ungelesene Nachricht(en) im Postfach.',
                    notification_id=f'mypage_dm_{to_id}')


def _dm_broadcast(text: str) -> int:
    """Admin-Rundnachricht (verschlüsselt) an alle Mitglieder. Liefert die Anzahl."""
    text = (text or '').strip()[:DM_MAX_LEN]
    if not text:
        return 0
    body = _dm_encrypt(text)          # ein Token für alle (gleicher Inhalt)
    now = int(time.time())
    msgs = load_dm()
    n = 0
    for u in load_users():
        msgs.append({'id': uuid.uuid4().hex[:12], 'frm': ADMIN_DM_ID, 'to': u['id'],
                     'ts': now, 'read': False, 'body': body})
        n += 1
    save_dm(msgs)
    return n


# ── DM-Erinnerung: ungelesen seit 3 h → E-Mail (ohne Inhalt, nur Link) ─────────
DM_REMINDER_AFTER = 3 * 3600   # erst nach 3 Stunden erinnern
DM_REMINDER_EVERY = 900        # Prüf-Intervall (15 min)


def send_dm_reminder(email: str, name: str, base: str, lang: str = 'de') -> None:
    """Neutrale Erinnerung – bewusst ohne Absender/Inhalt, nur Link zum Postfach."""
    site = load_site()
    title = site['design'].get('site_title') or site['profile'].get('name') or 'MyPage'
    esc = html_mod.escape
    m = load_translations(lang if lang in ('de', 'en') else 'de')
    link = f"{base}/bereich/nachrichten"
    lines = [m['mail_dm_hello'].format(name=esc(name)),
             m['mail_dm_body'],
             m['mail_link'].format(link=esc(link)),
             m['mail_dm_privacy']]
    send_email(m['mail_dm_subject'].format(title=title),
               _email_html(m['mail_dm_heading'].format(title=esc(title)), lines),
               to=email,
               from_addr=(site['design'].get('welcome_from') or '').strip() or None)


def _dm_check_reminders() -> None:
    """Findet je Empfänger ungelesene Nachrichten, die älter als 3 h sind und noch
    nicht erinnert wurden, verschickt eine neutrale Mail und markiert sie (``rem``)."""
    if not smtp_configured():
        return
    site = load_site()
    if not site['design'].get('dm_enabled'):
        return
    base = (site['design'].get('public_url') or '').rstrip('/')
    if not base:
        return
    now = time.time()
    msgs = load_dm()
    overdue: dict[str, list] = {}
    for m in msgs:
        to = m.get('to')
        if (to and not m.get('read') and not m.get('rem')
                and not _dm_hidden(m, to)
                and (now - m.get('ts', 0)) >= DM_REMINDER_AFTER):
            overdue.setdefault(to, []).append(m)
    if not overdue:
        return
    users = {u['id']: u for u in load_users()}
    changed = False
    for to_id, items in overdue.items():
        for m in items:               # nur einmal erinnern, egal ob Mail klappt
            m['rem'] = True
            changed = True
        u = users.get(to_id)
        if u and u.get('email'):
            threading.Thread(target=send_dm_reminder,
                             args=(u['email'], _member_display_name(u), base, _member_lang(u)),
                             daemon=True).start()
            log.info("DM-Erinnerung an '%s' (%d ungelesen)", u['email'], len(items))
    if changed:
        save_dm(msgs)


def _dm_reminder_worker() -> None:
    while True:
        time.sleep(DM_REMINDER_EVERY)
        try:
            _dm_check_reminders()
        except Exception as e:
            log.warning("DM-Erinnerung fehlgeschlagen: %s", e)


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
            _quarantine_corrupt(SUBSCRIBERS_PATH, e)
            return []


def save_subscribers(data: list) -> None:
    with _subs_lock:
        try:
            _atomic_write_json(SUBSCRIBERS_PATH, data, indent=2)
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
        _atomic_write_json(SESSIONS_PATH, {k: v for k, v in sessions.items() if v > now})
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


def _is_public_ip(value: str) -> bool:
    """True nur für gültige, öffentlich routbare IP-Adressen."""
    try:
        addr = ipaddress.ip_address((value or '').strip())
    except ValueError:
        return False
    return not (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified)


def get_client_ip(req) -> str:
    """Beste verfügbare Besucher-IP.

    Hinter Cloudflare Tunnel / Reverse Proxy ist `remote_addr` die Adresse des
    letzten Zwischenglieds — im HA-Setup das Docker-Bridge-Gateway (172.30.32.1),
    für alle Besucher dieselbe. Deshalb zuerst die Kopfzeilen auswerten, in denen
    die echte Adresse steht, und dabei die erste **öffentliche** nehmen: die
    Zwischenglieder hängen ihre eigenen (privaten) Adressen an die Kette an.
    """
    for header in ('CF-Connecting-IP', 'True-Client-IP', 'X-Real-IP'):
        value = (req.headers.get(header) or '').strip()
        if _is_public_ip(value):
            return value
    for part in (req.headers.get('X-Forwarded-For') or '').split(','):
        if _is_public_ip(part):
            return part.strip()
    return req.remote_addr or 'unknown'


_PROXY_IP_HEADERS = ('CF-Connecting-IP', 'True-Client-IP', 'X-Real-IP', 'X-Forwarded-For')
_last_ip_warning = 0.0


def _warn_missing_client_ip(req, ip: str) -> None:
    """Einmal pro Stunde melden, dass keine öffentliche Besucher-IP ankommt.

    Ohne diesen Hinweis wäre nur zu sehen, dass das Besucher-Log leer bleibt —
    die Ursache (Proxy reicht die Adresse nicht durch) stünde nirgends. Die
    tatsächlich vorhandenen Kopfzeilen mitzuloggen macht die Suche kurz.
    """
    global _last_ip_warning
    now = time.time()
    if now - _last_ip_warning < 3600:
        return
    _last_ip_warning = now
    seen = [h for h in _PROXY_IP_HEADERS if req.headers.get(h)]
    log.warning(
        "Besucher-IP ist nicht öffentlich (%s) — der Proxy reicht die echte Adresse "
        "nicht durch. Vorhandene Kopfzeilen: %s. Betroffene Aufrufe erscheinen nicht "
        "im Besucher-Log; Aufrufzähler laufen weiter.",
        ip, ', '.join(seen) or 'keine')


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


# ── Zwei-Faktor-Authentifizierung (Admin, nur Direkt-Login) ───────────────────
# TOTP nach RFC 6238 mit der Standardbibliothek — keine externe Krypto-Lib nötig.
# Greift NUR beim Login über Port 17761; über HA-Ingress übernimmt HA die Auth.
TOTP_STEP = 30          # Sekunden pro Code
TOTP_DIGITS = 6
TOTP_WINDOW = 1         # ±1 Zeitfenster Toleranz (Uhren-Drift)
BACKUP_CODE_COUNT = 10
# Kurzlebige Merker zwischen Schritt 1 (Passwort) und Schritt 2 (Code)
_pending_2fa: dict[str, float] = {}   # token → Ablaufzeit
PENDING_2FA_TTL = 300
TRUSTED_DEVICE_DAYS = 30   # "dieses Gerät merken" — überspringt den 2FA-Schritt


def load_2fa() -> dict:
    with _2fa_lock:
        try:
            with open(TWOFA_PATH, encoding='utf-8') as f:
                d = json.load(f)
                return d if isinstance(d, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception as e:
            # Sicherheitsrelevant: ohne lesbare Datei gilt 2FA als deaktiviert
            _quarantine_corrupt(TWOFA_PATH, e)
            return {}


def save_2fa(data: dict) -> None:
    with _2fa_lock:
        try:
            _atomic_write_json(TWOFA_PATH, data, indent=2, mode=0o600)
        except Exception as e:
            log.warning("admin_2fa.json konnte nicht gespeichert werden: %s", e)


def twofa_enabled() -> bool:
    d = load_2fa()
    return bool(d.get('enabled') and d.get('secret'))


def _new_totp_secret() -> str:
    """Zufälliges Base32-Secret (160 Bit) ohne Padding."""
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
    site = load_site()
    issuer = (site['design'].get('site_title') or site['profile'].get('name') or 'MyPage')[:40]
    from urllib.parse import quote
    label = quote(f'{issuer}:{account}')
    return (f'otpauth://totp/{label}?secret={secret_b32}'
            f'&issuer={quote(issuer)}&digits={TOTP_DIGITS}&period={TOTP_STEP}')


def _qr_svg(data: str) -> str:
    """QR-Code als Inline-SVG (lokal erzeugt — Secret verlässt den Server nie)."""
    try:
        import qrcode
        import qrcode.image.svg as qrsvg
        img = qrcode.make(data, image_factory=qrsvg.SvgPathImage, box_size=9, border=2)
        buf = io.BytesIO()
        img.save(buf)
        return buf.getvalue().decode('utf-8')
    except Exception as e:
        log.warning("QR-Code konnte nicht erzeugt werden: %s", e)
        return ''


def _gen_backup_codes() -> tuple[list, list]:
    """Liefert (Klartext-Codes für die einmalige Anzeige, Hashes für die Platte)."""
    plain = ['-'.join(secrets.token_hex(2) for _ in range(2)) for _ in range(BACKUP_CODE_COUNT)]
    return plain, [generate_password_hash(c) for c in plain]


def backup_code_consume(code: str) -> bool:
    """Prüft einen Backup-Code und verbraucht ihn (Einmal-Nutzung)."""
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


def _pending_2fa_valid(token: str | None) -> bool:
    if not token or token not in _pending_2fa:
        return False
    if time.time() > _pending_2fa[token]:
        _pending_2fa.pop(token, None)
        return False
    return True


def _trusted_prune(entries: dict) -> dict:
    now = time.time()
    return {k: v for k, v in (entries or {}).items() if v > now}


def _trusted_cookie_serializer() -> URLSafeTimedSerializer:
    """Signiert/liest den trust2fa-Cookie-Wert — der rohe Token landet nie im Klartext im Cookie."""
    return URLSafeTimedSerializer(str(admin_app.config.get('SECRET_KEY', '')), salt='trust2fa')


def create_trusted_session() -> str:
    """Neue Geräte-Session anlegen (gleiches Muster wie create_session())."""
    token = secrets.token_hex(32)
    d = load_2fa()
    trusted = _trusted_prune(d.get('trusted'))
    trusted[token] = time.time() + TRUSTED_DEVICE_DAYS * 86400
    d['trusted'] = trusted
    save_2fa(d)
    return token


def is_trusted_session_valid(cookie_value: str | None) -> bool:
    if not cookie_value:
        return False
    try:
        token = _trusted_cookie_serializer().loads(cookie_value, max_age=TRUSTED_DEVICE_DAYS * 86400)
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
    cookie = req.cookies.get('lang', '')
    if cookie in ('de', 'en'):
        return cookie
    accept = req.headers.get('Accept-Language', '')
    return 'de' if accept.lower().startswith('de') else 'en'


def _safe_next(raw: str) -> str:
    """Nur lokale Pfade als Redirect-Ziel zulassen (Open-Redirect-Schutz)."""
    nxt = (raw or '/').replace('\\', '')
    parts = urlsplit(nxt)
    if parts.scheme or parts.netloc or not nxt.startswith('/'):
        return '/'
    # Aus geparsten Komponenten neu zusammensetzen → Taint-Kette unterbrochen
    return urlunsplit(('', '', parts.path or '/', parts.query, parts.fragment))


# ── Besucherzähler ────────────────────────────────────────────────────────────

_BOT_UA = ('bot', 'crawl', 'spider', 'curl', 'wget', 'python-requests',
           'headless', 'lighthouse', 'pingdom', 'uptime')


def visit_log_max() -> int:
    """Konfigurierbares Limit für das Besucher-Log (Option visit_log_max)."""
    try:
        return max(50, min(10000, int(load_config().get('visit_log_max') or 500)))
    except (TypeError, ValueError):
        return 500


def visit_file_keep_months() -> int:
    """Wie viele Monatsdateien das Besucher-Archiv behält (0 = unbegrenzt)."""
    try:
        return max(0, min(120, int(load_config().get('visit_file_keep') or 12)))
    except (TypeError, ValueError):
        return 12


def _prune_visit_files() -> None:
    """Zu alte Monatsdateien entfernen (nach Dateiname, nicht nach Zeitstempel)."""
    keep = visit_file_keep_months()
    if keep <= 0:
        return
    try:
        files = sorted(f for f in VISITS_DIR.iterdir()
                       if f.is_file() and _VISIT_FILE_RE.match(f.name))
    except OSError:
        return
    for old in files[:-keep]:
        old.unlink(missing_ok=True)


def append_visit_file(entry: dict) -> None:
    """Einen Aufruf ans dauerhafte Besucher-Archiv anhängen (CSV, eine Datei je Monat).

    Bewusst getrennt vom Ringpuffer in `stats.json`: der hält nur die letzten
    Aufrufe, hier bleibt die vollständige Historie erhalten und ist über den
    Add-on-Konfigurations-Share direkt in Excel/LibreOffice zu öffnen.
    """
    if not load_config().get('visit_file_log'):
        return
    stamp = datetime.fromtimestamp(entry['ts'], timezone.utc).astimezone()
    target = VISITS_DIR / f'visits-{stamp:%Y-%m}.csv'
    ua = entry.get('ua', '')
    row = {
        'datum':          stamp.strftime('%Y-%m-%d %H:%M:%S'),
        'ip':             entry.get('ip', ''),
        'land':           entry.get('country', ''),
        'browser':        _browser_name(ua),
        'system':         _os_name(ua),
        'pfad':           entry.get('path', ''),
        'referrer':       entry.get('ref', ''),
        'sprache':        entry.get('lang', ''),
        'bot':            '1' if entry.get('bot') else '0',
        'neuer_besucher': '1' if entry.get('new') else '0',
        'user_agent':     ua,
    }
    try:
        with _visit_file_lock:
            VISITS_DIR.mkdir(parents=True, exist_ok=True)
            new_month = not target.exists()
            # Trennzeichen ';' — deutsche Excel-Installationen öffnen CSV sonst
            # als eine einzige Spalte. Der csv-Writer maskiert Anführungszeichen
            # und Semikolons in User-Agent und Referrer selbst.
            with open(target, 'a', encoding='utf-8-sig', newline='') as f:
                w = csv.DictWriter(f, fieldnames=VISIT_CSV_COLUMNS, delimiter=';')
                if new_month:
                    w.writeheader()
                w.writerow(row)
            if new_month:
                _prune_visit_files()
    except OSError as e:
        log.warning("Besucher-Archiv konnte nicht geschrieben werden: %s", e)


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
    # Besucher-Log (letzte Aufrufe inkl. Bots, für die Admin-Ansicht).
    # Nur öffentliche IPs: eigene Aufrufe aus dem Heimnetz und die internen
    # Zugriffe von Home Assistant selbst sagen nichts über Besucher aus. Kommt
    # ausschließlich das Docker-Gateway an, reicht der Proxy die echte Adresse
    # nicht durch — dann steht statt vieler nutzloser Zeilen ein Hinweis im Log.
    if not _is_public_ip(ip):
        _warn_missing_client_ip(req, ip)
    else:
        entry = {
            'ts':   int(time.time()),
            'ip':   ip,
            'path': req.path[:100],
            'ua':   ua[:300],
            'ref':  (req.headers.get('Referer') or '')[:300],
            'lang': (req.headers.get('Accept-Language') or '')[:60],
            'country': _guess_country(req),
            'bot':  is_bot,
            'new':  is_new,
        }
        visit_log = stats.setdefault('log', [])
        visit_log.append(entry)
        del visit_log[:-visit_log_max()]
        # Dauerhaftes Archiv (optional) — der Ringpuffer oben vergisst alte Aufrufe
        append_visit_file(entry)

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


def _os_name(ua: str) -> str:
    """Betriebssystem aus dem User-Agent — dieselbe grobe Einteilung wie im Admin."""
    u = ua.lower()
    if 'android' in u:
        return 'Android'
    if 'iphone' in u or 'ipad' in u or 'ios' in u:
        return 'iOS'
    if 'windows' in u:
        return 'Windows'
    if 'mac os' in u or 'macintosh' in u:
        return 'macOS'
    if 'cros' in u:
        return 'ChromeOS'
    if 'linux' in u:
        return 'Linux'
    return ''


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
            _quarantine_corrupt(USERS_PATH, e)
            return []


def save_users(users: list) -> None:
    with _users_lock:
        try:
            _atomic_write_json(USERS_PATH, users, indent=2)
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
        _atomic_write_json(USESSIONS_PATH,
                           {k: v for k, v in user_sessions.items() if v[1] > now})
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


def _member_lang(user: dict | None) -> str:
    """Bevorzugte E-Mail-Sprache eines Mitglieds (de/en), Standard Deutsch."""
    lang = (user or {}).get('lang')
    return lang if lang in ('de', 'en') else 'de'


def send_welcome_email(user: dict, password: str, subject: str | None = None) -> None:
    site = load_site()
    base = (site['design'].get('public_url') or '').rstrip('/')
    url = (base + '/bereich') if base else ''
    title = site['design'].get('site_title') or site['profile'].get('name') or 'MyPage'
    esc = html_mod.escape
    m = load_translations(_member_lang(user))
    lines = [m['mail_welcome_intro'].format(title=esc(title)),
             m['mail_welcome_login'].format(url=esc(url)) if url else '',
             m['mail_username_label'].format(email=esc(user['email'])),
             m['mail_password_label'].format(password=esc(password)),
             m['mail_welcome_ignore']]
    send_email(subject or m['mail_welcome_subject'].format(title=title),
               _email_html(m['mail_welcome_heading'].format(title=esc(title)), [l for l in lines if l]),
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
    m = load_translations(_member_lang(user))
    lines = [m['mail_reset_intro'].format(title=esc(title)),
             m['mail_reset_cta'],
             m['mail_link'].format(link=esc(link)),
             m['mail_reset_ignore']]
    send_email(m['mail_reset_subject'].format(title=title),
               _email_html(m['mail_reset_heading'].format(title=esc(title)), lines),
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
    m = load_translations(_member_lang(user))
    lines = [m['mail_verify_intro'].format(title=esc(title)),
             m['mail_link'].format(link=esc(link)),
             m['mail_verify_after'],
             m['mail_verify_ignore']]
    send_email(m['mail_verify_subject'].format(title=title),
               _email_html(m['mail_verify_heading'].format(title=esc(title)), lines),
               to=user['email'], from_addr=_reg_from())


def send_already_registered_email(user: dict) -> None:
    site = load_site()
    base = (site['design'].get('public_url') or '').rstrip('/')
    title, esc = _site_title(), html_mod.escape
    m = load_translations(_member_lang(user))
    lines = [m['mail_exists_intro'].format(title=esc(title)),
             (m['mail_exists_login'].format(base=esc(base)) if base else m['mail_exists_login_nourl']),
             m['mail_exists_forgot'],
             m['mail_exists_ignore']]
    send_email(m['mail_exists_subject'].format(title=title),
               _email_html(m['mail_exists_heading'].format(title=esc(title)), lines),
               to=user['email'], from_addr=_reg_from())


def send_activated_email(user: dict) -> None:
    site = load_site()
    base = (site['design'].get('public_url') or '').rstrip('/')
    title, esc = _site_title(), html_mod.escape
    url = (base + '/bereich') if base else ''
    m = load_translations(_member_lang(user))
    lines = [m['mail_activated_intro'].format(title=esc(title)),
             (f'<a href="{esc(url)}">{esc(url)}</a>' if url else ''),
             m['mail_username_label'].format(email=esc(user['email']))]
    send_email(m['mail_activated_subject'].format(title=title),
               _email_html(m['mail_activated_heading'].format(title=esc(title)), [l for l in lines if l]),
               to=user['email'], from_addr=_reg_from())


def send_comment_reply_email(to_email: str, post_title: str, replier: str,
                             text: str, post_url: str, lang: str = 'de') -> None:
    """Benachrichtigt den Autor eines Kommentars, dass jemand geantwortet hat."""
    title, esc = _site_title(), html_mod.escape
    m = load_translations(lang if lang in ('de', 'en') else 'de')
    lines = [m['mail_reply_intro'].format(replier=esc(replier), post=esc(post_title)),
             m['mail_reply_quote'].format(text=esc(text[:300])),
             (m['mail_reply_cta'].format(url=esc(post_url)) if post_url else '')]
    send_email(m['mail_reply_subject'].format(title=title),
               _email_html(m['mail_reply_heading'].format(title=esc(title)), [l for l in lines if l]),
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
                   'gluecksrad': 'Glücksrad', 'kniffel': 'Kniffel', 'chicago': 'Chicago'}


def _playing_overview() -> tuple[list, dict]:
    """Liefert (spieler, pro_spiel): wer spielt gerade welches Spiel."""
    players: list = []
    per_game: dict = {'66': [], '20ab': [], 'schwimmen': [], 'maumau': [], 'praesident': [], 'jeopardy': [], 'gluecksrad': [], 'kniffel': [], 'chicago': []}
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
        for g in ('66', '20ab', 'schwimmen', 'maumau', 'praesident', 'jeopardy', 'gluecksrad', 'kniffel', 'chicago'):
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


# ── Wöchentlicher Statistik-Rückblick (HA-Benachrichtigung + optional E-Mail) ──

def _iso_week(d: date) -> str:
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _weekly_summary() -> dict:
    """Kennzahlen der letzten 7 Tage inkl. Trend gegenüber der Vorwoche."""
    stats = load_stats()
    days = stats.get('days', {})
    today = date.today()

    def _sum(a: int, b: int) -> tuple[int, int]:
        v = u = 0
        for i in range(a, b):
            d = days.get((today - timedelta(days=i)).isoformat())
            if d:
                v += d.get('views', 0)
                u += d.get('uniques', 0)
        return v, u

    views, uniques = _sum(0, 7)          # letzte 7 Tage (heute … −6)
    prev_views, _ = _sum(7, 14)          # Vorwoche
    cutoff = int(time.time()) - 7 * 86400
    log_week = [v for v in stats.get('log', []) if v.get('ts', 0) >= cutoff]
    pages = top_pages(load_site(), log_week, limit=1)
    cutoff_day = (today - timedelta(days=7)).isoformat()
    new_members = sum(1 for u in load_users() if (u.get('created') or '') >= cutoff_day)
    new_messages = sum(1 for m in load_messages() if m.get('ts', 0) >= cutoff)
    trend = round((views - prev_views) / prev_views * 100) if prev_views else None
    return {'views': views, 'uniques': uniques, 'trend': trend,
            'top_page': (pages[0] if pages else None),
            'new_members': new_members, 'new_messages': new_messages}


def _send_weekly_review() -> None:
    """Verschickt den Wochenrückblick als HA-Benachrichtigung und (falls SMTP
    konfiguriert) als E-Mail an die Admin-Adresse. Texte bewusst auf Deutsch —
    konsistent zu den übrigen HA-Benachrichtigungen."""
    s = _weekly_summary()
    if s['trend'] is None:
        trend_txt = '—'
    else:
        arrow = '▲' if s['trend'] > 0 else ('▼' if s['trend'] < 0 else '■')
        trend_txt = f"{arrow} {abs(s['trend'])} % ggü. Vorwoche"
    tp = s['top_page']
    top_txt = (f"{tp.get('title') or tp.get('path')} ({tp['count']})") if tp else '—'
    lines = [
        f"Aufrufe: {s['views']}  ({trend_txt})",
        f"Eindeutige Besucher: {s['uniques']}",
        f"Top-Seite: {top_txt}",
        f"Neue Mitglieder: {s['new_members']}",
        f"Neue Nachrichten: {s['new_messages']}",
    ]
    notify_ha('📊 MyPage: Wochenrückblick', '\n'.join(lines),
              notification_id='mypage_weekly_review')
    if smtp_configured():
        title = (load_site()['design'].get('site_title') or 'MyPage')
        html = _email_html(f'📊 Wochenrückblick — {title}', lines)
        send_email(f'📊 Wochenrückblick — {title}', html)
    log.info("Wochenrückblick verschickt (Aufrufe %d, Besucher %d)", s['views'], s['uniques'])


def _weekly_review_worker() -> None:
    """Schickt montags ab 8 Uhr einen Wochenrückblick — höchstens einmal pro
    ISO-Woche, nur wenn im Design-Tab aktiviert."""
    while True:
        time.sleep(3600)
        try:
            if not load_site()['design'].get('weekly_review'):
                continue
            now = datetime.now()
            if now.weekday() != 0 or now.hour < 8:   # Montag, ab 8 Uhr
                continue
            wk = _iso_week(date.today())
            if load_stats().get('weekly_review_sent') == wk:
                continue
            _send_weekly_review()
            stats = load_stats()
            stats['weekly_review_sent'] = wk
            save_stats(stats)
        except Exception as e:
            log.warning("Wochenrückblick-Worker: %s", e)


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


SEARCH_SNIPPET_LEN = 170
SEARCH_MAX_RESULTS = 80
SEARCH_MAX_WORDS = 8


def _search_words(query: str) -> list:
    """Suchanfrage → Liste klein geschriebener Suchwörter (begrenzt)."""
    return [w for w in (query or '').strip().lower().split() if w][:SEARCH_MAX_WORDS]


def _search_snippet(text: str, words: list) -> str:
    """Klartext-Auszug rund um den ersten Treffer."""
    plain = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', text or '')).strip()
    if not plain:
        return ''
    low = plain.lower()
    pos = -1
    for w in words:
        i = low.find(w)
        if i != -1 and (pos == -1 or i < pos):
            pos = i
    if pos <= 0:
        snippet = plain[:SEARCH_SNIPPET_LEN]
        prefix = ''
    else:
        start = max(0, pos - SEARCH_SNIPPET_LEN // 3)
        snippet = plain[start:start + SEARCH_SNIPPET_LEN]
        prefix = '… ' if start > 0 else ''
    if len(prefix) + len(snippet) < len(prefix) + len(plain[(pos if pos > 0 else 0):]):
        snippet = snippet.rstrip() + ' …'
    return prefix + snippet


def _search_highlight(text: str, words: list) -> Markup:
    """Text escapen und Suchwörter mit <mark> hervorheben (XSS-sicher)."""
    out = str(escape(text or ''))
    for w in sorted({w for w in words if w}, key=len, reverse=True):
        wesc = re.escape(str(escape(w)))
        out = re.sub(f'({wesc})', r'<mark>\1</mark>', out, flags=re.IGNORECASE)
    return Markup(out)


def site_search(site: dict, query: str, loc, viewer_is_member: bool) -> list:
    """Seitenweite Volltextsuche über Beiträge, Projekte und Seiten.
    Liefert eine Liste {kind, title, title_html, url, snippet, locked}."""
    words = _search_words(query)
    if not words:
        return []
    results: list = []

    def consider(kind, title, url, body, members_only):
        hay = (str(title) + ' ' + str(body)).lower()
        if not all(w in hay for w in words):
            return
        locked = bool(members_only) and not viewer_is_member
        snippet = '' if locked else _search_snippet(body, words)
        results.append({
            'kind': kind,
            'title': title or '…',
            'title_html': _search_highlight(title or '…', words),
            'url': url,
            'snippet': _search_highlight(snippet, words) if snippet else '',
            'locked': locked,
        })

    for p in sorted_posts(site, public_only=True):
        body = ' '.join([loc(p, 'text'), ' '.join(p.get('tags', []))])
        consider('blog', loc(p, 'title'), '/blog/' + p['id'], body, p.get('members_only'))

    for p in site.get('projects', []):
        if not project_visible(p):
            continue
        body = ' '.join([loc(p, 'desc'), loc(p, 'long'), ' '.join(p.get('tags', []))])
        url = '/p/' + p['id'] if _has_detail(p) else (p.get('url') or '/#projects')
        consider('project', p.get('title', ''), url, body, False)

    for p in site.get('pages', []):
        if not p.get('visible'):
            continue
        consider('page', loc(p, 'title'), '/seite/' + p.get('slug', ''),
                 loc(p, 'body'), p.get('members_only'))

    for e in _lib_public_entries(site):
        body = ' '.join([loc(e, 'summary'), loc(e, 'body'), ' '.join(e.get('tags', []))])
        consider('library', loc(e, 'title'), '/bibliothek/' + e.get('slug', ''),
                 body, e.get('members_only'))

    return results[:SEARCH_MAX_RESULTS]


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


_MD_IMG_SRC_RE = re.compile(r'(<img\b[^>]*?\bsrc=")/uploads/([^"]+)(")', re.I)


def _overlay_url(url: str) -> str:
    """`/uploads/<name>` → `/img/<name>`; alles andere bleibt, wie es ist.

    Nur über `/img/` kommen Wasserzeichen und KI-Kennzeichnung ins Bild — die
    offene `/uploads/`-Route liefert immer das unveränderte Original aus.
    """
    return ('/img/' + url.removeprefix('/uploads/')) if url.startswith('/uploads/') else url


def _overlay_html_images(html: str) -> str:
    """Bilder in gerendertem Markdown auf die `/img/`-Route umhängen.

    Betrifft nur lokale Uploads; eingebundene Fremd-URLs bleiben unangetastet,
    weil an ihnen weder Wasserzeichen noch KI-Marker etwas zu suchen haben.
    """
    return _MD_IMG_SRC_RE.sub(r'\1/img/\2\3', html)


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
    'blog', 'bereich', 'p', 'api', 'uploads', 'fonts', 'cards', 'album-img', 'img',
    'impressum', 'datenschutz', 'contact', 'newsletter', 'sitemap', 'sitemap.xml',
    'robots', 'robots.txt', 'feed', 'feed.xml', 'manifest.json', 'sw.js',
    'favicon.ico', 'icon.png', 'health', 'set-lang', 'seite', 'preview', 'static',
    'suche', 'search', 'bibliothek', 'library',
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


# ── Bibliothek (Markdown-Sammlung mit Kategorien und PDF) ─────────────────────
#
# Bewusst generisch gehalten: Anzeigename und Kategorien sind frei wählbar, die
# Sammlung kann also ebenso „Reiseführer" wie „Rezepte" oder „Handbücher" sein.
# Ein Eintrag ist Markdown (DE/EN) plus optional ein PDF — entweder selbst
# hochgeladen oder aus dem Markdown erzeugt (siehe _library_pdf_build).

LIB_PDF_MODES = {'none', 'upload', 'generated'}


def _library(site: dict) -> dict:
    """Bibliothek-Block inkl. fehlender Schlüssel (alte site.json)."""
    lib = site.get('library')
    if not isinstance(lib, dict):
        lib = {}
        site['library'] = lib
    lib.setdefault('label_de', '')
    lib.setdefault('label_en', '')
    lib.setdefault('intro_de', '')
    lib.setdefault('intro_en', '')
    lib.setdefault('nav', True)
    if not isinstance(lib.get('categories'), list):
        lib['categories'] = []
    if not isinstance(lib.get('entries'), list):
        lib['entries'] = []
    return lib


def _library_label(site: dict, loc, t: dict) -> str:
    """Anzeigename der Sammlung — eigener Text oder Standard „Bibliothek"."""
    return loc(_library(site), 'label') or t.get('library_heading', 'Bibliothek')


def _normalize_lib_cat(raw: dict, existing: dict | None = None) -> dict:
    c = existing or {'id': uuid.uuid4().hex[:12]}
    c['name_de'] = _clean_str(raw.get('name_de'), 60)
    c['name_en'] = _clean_str(raw.get('name_en'), 60)
    c['icon']    = _clean_str(raw.get('icon'), 8)
    return c


def _normalize_lib_entry(site: dict, raw: dict, existing: dict | None = None) -> dict:
    e = existing or {'id': uuid.uuid4().hex[:12]}
    e['title_de']   = _clean_str(raw.get('title_de'), 140)
    e['title_en']   = _clean_str(raw.get('title_en'), 140)
    e['summary_de'] = _clean_str(raw.get('summary_de'), 400)
    e['summary_en'] = _clean_str(raw.get('summary_en'), 400)
    e['body_de']    = _clean_str(raw.get('body_de'), 80000)
    e['body_en']    = _clean_str(raw.get('body_en'), 80000)
    e['meta_de']    = _clean_str(raw.get('meta_de'), 300)
    e['meta_en']    = _clean_str(raw.get('meta_en'), 300)
    e['image']      = _clean_str(raw.get('image'), 500)
    cat = _clean_str(raw.get('cat'), 32)
    known = {c.get('id') for c in _library(site).get('categories', [])}
    e['cat'] = cat if cat in known else ''
    tags = raw.get('tags') or []
    if isinstance(tags, str):
        tags = tags.split(',')
    e['tags'] = [_clean_str(x, 30) for x in tags if _clean_str(x, 30)][:8]
    e['visible']      = bool(raw.get('visible', True))
    e['members_only'] = bool(raw.get('members_only'))
    mode = raw.get('pdf_mode')
    e['pdf_mode'] = mode if mode in LIB_PDF_MODES else 'none'
    # Dateinamen nie aus der Anfrage übernehmen — nur bereits gespeicherte, exakt
    # passende Namen behalten (gesetzt werden sie ausschließlich vom Upload bzw.
    # von der PDF-Erzeugung).
    pdf = _clean_str(raw.get('pdf'), 40)
    e['pdf'] = pdf if _DOC_FILE_RE.match(pdf) else ''
    e.setdefault('pdf_gen', '')
    e.setdefault('pdf_hash', '')
    e['updated'] = date.today().isoformat()
    return e


def _lib_entry_slug(site: dict, raw: dict, entry_id: str) -> str:
    slug = _slugify(raw.get('slug') or raw.get('title_de') or raw.get('title_en') or '')
    if not slug:
        slug = 'eintrag-' + entry_id[:6]
    base, n = slug, 2
    taken = {e.get('slug') for e in _library(site).get('entries', []) if e.get('id') != entry_id}
    while slug in taken:
        slug = f'{base}-{n}'
        n += 1
    return slug


def _find_lib_entry(site: dict, slug: str) -> dict | None:
    return next((e for e in _library(site).get('entries', []) if e.get('slug') == slug), None)


def _lib_public_entries(site: dict) -> list:
    """Veröffentlichte Einträge (Mitglieder-only bleibt gelistet, nur der Text ist gesperrt)."""
    return [e for e in _library(site).get('entries', []) if e.get('visible')]


def _lib_entry_pdf_name(e: dict) -> str:
    """Auszuliefernde PDF-Datei eines Eintrags ('' wenn keine)."""
    if e.get('pdf_mode') == 'upload':
        return e.get('pdf') or ''
    if e.get('pdf_mode') == 'generated':
        return e.get('pdf_gen') or ''
    return ''


def _nav_library(site: dict, loc, t: dict) -> list:
    """Navi-Eintrag der Bibliothek (nur mit sichtbaren Einträgen und aktivem Schalter)."""
    lib = _library(site)
    if not lib.get('nav') or not _lib_public_entries(site):
        return []
    return [{'href': '/bibliothek', 'label': _library_label(site, loc, t)}]


def _lib_pdf_fetcher(url: str, lang: str = 'de'):
    """URL-Fetcher für WeasyPrint — liefert ausschließlich lokale Uploads aus.

    WeasyPrint lädt referenzierte Ressourcen (`<img src>`, `url()`) sonst selbst
    per HTTP nach. Da der Markdown-Text beliebige Adressen enthalten darf, wäre
    das ein SSRF-Weg in interne Dienste (Supervisor, Router, Metadaten-Endpunkte),
    dessen Antwort im erzeugten PDF landet. Deshalb: nur lokale Dateien, alles
    andere wird abgelehnt.

    `/img/<datei>` bekommt dieselbe Behandlung wie im Web — Wasserzeichen und
    KI-Kennzeichnung müssen im PDF genauso drin sein, sonst wäre das Herunterladen
    des PDF der einfachste Weg, die Kennzeichnung loszuwerden.
    """
    for prefix, overlay in (('/img/', True), ('/uploads/', False)):
        if not url.startswith(prefix):
            continue
        name = url[len(prefix):]
        target = safe_under(UPLOADS_DIR, name)
        if target is None or not target.is_file():
            break
        if overlay:
            text = _image_overlay_text(target.name, load_site(), lang)
            if text:
                data = _render_watermark(target, text)
                if data is not None:
                    return {'file_obj': io.BytesIO(data), 'mime_type': 'image/webp'}
        return {'file_obj': open(target, 'rb'),
                'mime_type': mimetypes.guess_type(target.name)[0] or 'application/octet-stream'}
    raise ValueError(f'externe Ressource im PDF blockiert: {url[:80]}')


# Bei jeder Änderung an _lib_pdf_html hochzählen — erzwingt Neuaufbau der PDFs.
_LIB_PDF_LAYOUT = 3


def _lib_pdf_html(site: dict, entry: dict, lang: str, t: dict) -> str:
    """Druckfertiges HTML eines Eintrags (Deckblatt-Kopf + Markdown + Seitenzahlen)."""
    loc = _loc_factory(lang)
    accent = site.get('design', {}).get('accent') or '#3b82f6'
    cat = next((c for c in _library(site).get('categories', [])
                if c.get('id') == entry.get('cat')), None)
    # Kategorie-Icon bleibt draußen: der PDF-Font (DejaVu) kennt keine Emoji und
    # WeasyPrint setzt dafür ein leeres Kästchen. Im Web rendert es der Browser.
    subtitle = ' · '.join(x for x in [
        (loc(cat, 'name') if cat else ''),
        entry.get('updated') or '',
    ] if x)
    page_label = t.get('pdf_page', 'Seite')
    return f"""<!DOCTYPE html><html lang="{escape(lang)}"><head><meta charset="utf-8">
<title>{escape(loc(entry, 'title'))}</title><style>
@page {{ size: A4; margin: 20mm 18mm 18mm;
  @bottom-center {{ content: "{escape(page_label)} " counter(page) " / " counter(pages);
                    font-size: 9pt; color: #666; }} }}
body {{ font-family: "DejaVu Sans", sans-serif; font-size: 10.5pt; line-height: 1.55; color: #111; }}
h1.doc-title {{ font-size: 20pt; margin: 0 0 2mm; color: {escape(accent)}; }}
.doc-sub {{ font-size: 9pt; color: #666; margin-bottom: 8mm;
            border-bottom: 1px solid #ddd; padding-bottom: 3mm; }}
h1, h2, h3 {{ line-height: 1.25; margin: 6mm 0 2mm; page-break-after: avoid; }}
h2 {{ font-size: 14pt; }} h3 {{ font-size: 12pt; }}
p {{ margin: 0 0 3mm; }} ul, ol {{ margin: 0 0 3mm 6mm; }}
img {{ max-width: 100%; }}
blockquote {{ border-left: 2pt solid {escape(accent)}; margin: 3mm 0; padding: 0 4mm; color: #444; }}
pre {{ background: #f4f4f4; padding: 3mm; border-radius: 2mm; white-space: pre-wrap;
       font-family: "DejaVu Sans Mono", monospace; font-size: 9pt; }}
code {{ font-family: "DejaVu Sans Mono", monospace; font-size: 9pt; }}
table {{ border-collapse: collapse; width: 100%; margin: 3mm 0; page-break-inside: avoid; }}
th, td {{ border: 0.5pt solid #bbb; padding: 1.5mm 2mm; text-align: left; font-size: 9.5pt; }}
th {{ background: #f0f0f0; }}
hr {{ border: none; border-top: 0.5pt solid #ccc; margin: 5mm 0; }}
</style></head><body>
<h1 class="doc-title">{escape(loc(entry, 'title'))}</h1>
{f'<div class="doc-sub">{escape(subtitle)}</div>' if subtitle else ''}
{_overlay_html_images(render_md(loc(entry, 'body')))}
</body></html>"""


def _lib_pdf_source_hash(site: dict, entry: dict) -> str:
    """Fingerabdruck über alles, was das PDF beeinflusst — Grundlage fürs Caching.

    `_LIB_PDF_LAYOUT` mitzählen, damit Änderungen an `_lib_pdf_html` bestehende
    PDFs entwerten — sonst bleibt bei unverändertem Text das alte Layout stehen.
    """
    src = json.dumps([_LIB_PDF_LAYOUT,
                      entry.get('title_de'), entry.get('title_en'),
                      entry.get('body_de'), entry.get('body_en'),
                      entry.get('cat'), entry.get('updated'),
                      site.get('design', {}).get('accent'),
                      # Wasserzeichen wird in die Bilder eingebrannt — ändert es
                      # sich, muss das PDF neu gebaut werden
                      bool(site.get('album_protect')),
                      effective_watermark() if site.get('album_protect') else ''],
                     ensure_ascii=False)
    return hashlib.sha256(src.encode('utf-8')).hexdigest()[:16]


def _library_pdf_build(site: dict, entry: dict, lang: str = 'de') -> str | None:
    """Erzeugt (oder bestätigt) das PDF eines Eintrags. Gibt den Dateinamen zurück.

    Bei unverändertem Quelltext wird die vorhandene Datei wiederverwendet —
    PDF-Rendern kostet spürbar CPU und soll nicht bei jedem Speichern laufen.
    """
    if not _HAS_WEASY:
        return None
    src_hash = _lib_pdf_source_hash(site, entry)
    old = entry.get('pdf_gen') or ''
    if (entry.get('pdf_hash') == src_hash and _DOC_FILE_RE.match(old)
            and (DOCS_DIR / old).is_file()):
        return old
    t = load_translations(lang)
    html = _lib_pdf_html(site, entry, lang, t)
    name = uuid.uuid4().hex + '.pdf'
    target = safe_under(DOCS_DIR, name)
    if target is None:
        return None
    _WeasyHTML(string=html, base_url='/',
               url_fetcher=lambda url: _lib_pdf_fetcher(url, lang)).write_pdf(target=str(target))
    # Vorgänger erst nach erfolgreichem Rendern entfernen
    if _DOC_FILE_RE.match(old):
        old_path = safe_under(DOCS_DIR, old)
        if old_path is not None:
            old_path.unlink(missing_ok=True)
    entry['pdf_gen'] = name
    entry['pdf_hash'] = src_hash
    return name


def _library_pdf_drop(entry: dict, keep: str = '') -> None:
    """Löscht die PDF-Dateien eines Eintrags (außer `keep`) vom Datenträger."""
    for name in {entry.get('pdf') or '', entry.get('pdf_gen') or ''}:
        if name and name != keep and _DOC_FILE_RE.match(name):
            p = safe_under(DOCS_DIR, name)
            if p is not None:
                p.unlink(missing_ok=True)


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


def _nav_links(site: dict, loc, t: dict | None = None, with_library: bool = True) -> list:
    """Navi-Einträge für Bibliothek, eigene Seiten und Formulare.

    Auf der Startseite steckt die Bibliothek bereits als Abschnitt in der
    Sektions-Navigation (Anker `#library`) — dort `with_library=False`, sonst
    stünde sie doppelt in der Leiste.
    """
    lib = _nav_library(site, loc, t or {}) if with_library else []
    return lib + _nav_pages(site, loc) + _nav_forms(site, loc)


# ── Weiterleitungen (301/302) ─────────────────────────────────────────────────

def _redirect_path(p: str) -> str:
    """Pfad normalisieren: führender Slash, ohne Query/Anker, ohne End-Slash."""
    p = _clean_str(p, 300).split('?')[0].split('#')[0]
    if not p.startswith('/'):
        p = '/' + p
    return p.rstrip('/') if len(p) > 1 else p


def _normalize_redirect(raw: dict) -> dict:
    to = _clean_str(raw.get('to'), 500)
    if to and not to.startswith(('http://', 'https://', '/')):
        to = '/' + to
    return {'from': _redirect_path(raw.get('from')), 'to': to,
            'permanent': bool(raw.get('permanent', True))}


def _find_redirect(site: dict, path: str) -> dict | None:
    target = _redirect_path(path)
    if target == '/':
        return None   # Startseite nie umleiten
    for r in site.get('redirects', []):
        if r.get('from') == target and r.get('to'):
            return r
    return None


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
    step = 'password'

    def _grant_session(ip):
        clear_failed_attempts(ip)
        hours = int(cfg.get('session_hours', 24))
        token = create_session(hours)
        log_audit('admin_login')
        resp = make_response(redirect(url_for('admin_index')))
        resp.set_cookie('session', token, httponly=True, samesite='Lax', max_age=hours * 3600)
        resp.delete_cookie('pre2fa')
        return resp

    def _grant_session_trusted(ip):
        resp = _grant_session(ip)
        if request.form.get('remember_device'):
            token = create_trusted_session()
            if token:
                cookie_value = _trusted_cookie_serializer().dumps(token)
                resp.set_cookie('trust2fa', cookie_value, httponly=True, samesite='Lax',
                                 max_age=TRUSTED_DEVICE_DAYS * 86400)
        return resp

    if request.method == 'POST':
        ip = get_client_ip(request)
        if is_rate_limited(ip):
            error = t.get('error_locked', 'Zu viele Fehlversuche. Bitte 15 Minuten warten.')
        elif request.form.get('step') == 'code':
            # Schritt 2: TOTP- oder Backup-Code (nur nach erfolgreichem Passwort)
            if not _pending_2fa_valid(request.cookies.get('pre2fa')):
                return redirect(url_for('login'))   # Vormerkung abgelaufen → neu starten
            code = request.form.get('code', '')
            secret = load_2fa().get('secret', '')
            if totp_verify(secret, code) or backup_code_consume(code):
                _pending_2fa.pop(request.cookies.get('pre2fa'), None)
                return _grant_session_trusted(ip)
            record_failed_attempt(ip)
            log_audit('admin_login_2fa_failed')
            error = t.get('error_2fa_code', 'Ungültiger Code.')
            step = 'code'
        else:
            # Schritt 1: Benutzername + Passwort
            uname = request.form.get('username', '')
            pwd   = request.form.get('password', '')
            if (secrets.compare_digest(uname, str(cfg.get('username', 'admin'))) and
                    secrets.compare_digest(pwd, str(cfg.get('password', '')))):
                if twofa_enabled() and not is_trusted_session_valid(request.cookies.get('trust2fa')):
                    pre = _pending_2fa_new()
                    resp = make_response(render_template('login.html', t=t, lang=lang,
                                                         error=None, step='code'))
                    resp.set_cookie('pre2fa', pre, httponly=True, samesite='Lax',
                                    max_age=PENDING_2FA_TTL)
                    return resp
                return _grant_session(ip)
            record_failed_attempt(ip)
            log_audit('admin_login_failed', uname)
            error = t.get('error_credentials', 'Ungültige Anmeldedaten.')

    return make_response(render_template('login.html', t=t, lang=lang, error=error, step=step))


@admin_app.route('/logout')
def logout():
    token = request.cookies.get('session')
    if token and token in sessions:
        del sessions[token]
        save_sessions()
    resp = make_response(redirect(url_for('login')))
    resp.delete_cookie('session')
    return resp


@admin_app.route('/api/2fa')
def api_2fa_status():
    err = _api_auth()
    if err:
        return err
    d = load_2fa()
    return jsonify({'enabled': twofa_enabled(), 'ingress': _is_ingress(),
                    'backup_remaining': len(d.get('backup') or [])})


@admin_app.route('/api/2fa/setup', methods=['POST'])
def api_2fa_setup():
    err = _api_auth()
    if err:
        return err
    secret = _new_totp_secret()
    d = load_2fa()
    d['pending'] = secret           # erst nach Code-Bestätigung aktiv
    save_2fa(d)
    account = str(load_config().get('username', 'admin'))
    uri = _otpauth_uri(secret, account)
    return jsonify({'secret': secret, 'uri': uri, 'qr': _qr_svg(uri), 'account': account})


@admin_app.route('/api/2fa/enable', methods=['POST'])
def api_2fa_enable():
    err = _api_auth()
    if err:
        return err
    code = (request.get_json(silent=True) or {}).get('code', '')
    d = load_2fa()
    pending = d.get('pending', '')
    if not pending:
        return jsonify({'error': 'no setup'}), 400
    if not totp_verify(pending, code):
        return jsonify({'error': 'bad code'}), 400
    plain, hashes = _gen_backup_codes()
    save_2fa({'enabled': True, 'secret': pending, 'backup': hashes})
    log_audit('admin_2fa_enabled')
    log.info("Admin-2FA aktiviert")
    return jsonify({'ok': True, 'backup_codes': plain})


@admin_app.route('/api/2fa/disable', methods=['POST'])
def api_2fa_disable():
    err = _api_auth()
    if err:
        return err
    code = (request.get_json(silent=True) or {}).get('code', '')
    d = load_2fa()
    if not twofa_enabled():
        return jsonify({'ok': True})
    if not (totp_verify(d.get('secret', ''), code) or backup_code_consume(code)):
        return jsonify({'error': 'bad code'}), 400
    save_2fa({'enabled': False, 'secret': '', 'backup': []})
    log_audit('admin_2fa_disabled')
    log.info("Admin-2FA deaktiviert")
    return jsonify({'ok': True})


@admin_app.route('/api/2fa/backup', methods=['POST'])
def api_2fa_backup():
    err = _api_auth()
    if err:
        return err
    code = (request.get_json(silent=True) or {}).get('code', '')
    d = load_2fa()
    if not twofa_enabled():
        return jsonify({'error': 'not enabled'}), 400
    if not totp_verify(d.get('secret', ''), code):
        return jsonify({'error': 'bad code'}), 400
    plain, hashes = _gen_backup_codes()
    d['backup'] = hashes
    save_2fa(d)
    log_audit('admin_2fa_backup_regen')
    return jsonify({'ok': True, 'backup_codes': plain})


@admin_app.route('/api/broadcast', methods=['POST'])
def api_broadcast():
    err = _api_auth()
    if err:
        return err
    if not dm_feature_on():
        return jsonify({'error': 'dm disabled'}), 400
    text = _clean_str((request.get_json(silent=True) or {}).get('text'), DM_MAX_LEN).strip()
    if not text:
        return jsonify({'error': 'empty'}), 400
    n = _dm_broadcast(text)
    log_audit('dm_broadcast', f'{n} Empfänger')
    log.info("Admin-Rundnachricht an %d Mitglieder verschickt", n)
    return jsonify({'ok': True, 'count': n})


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
    # Gemini nur, wenn im KI-Tab ausgewählt UND ein Key hinterlegt ist. Scheitert
    # es, übernimmt MyMemory — eine schlechtere Übersetzung ist besser als keine.
    if _ai_translate_provider() == 'gemini' and _ai_rate_take(_ai_text_times,
                                                             AI_TEXT_MAX_PER_HOUR):
        try:
            return jsonify({'text': _gemini_translate(text, src, dst)})
        except Exception as e:
            log.warning("KI-Übersetzung fehlgeschlagen (%s) — weiche auf MyMemory aus",
                        type(e).__name__)
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
                 'banner_enabled', 'banner_dismissible', 'share_enabled', 'dm_enabled',
                 'dm_ha_notify', 'directory_enabled', 'search_enabled', 'weekly_review'):
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
    for k in ('google_verify', 'bing_verify'):
        if k in raw:
            v = _clean_str(raw[k], 300)
            m = re.search(r'content=["\']([^"\']+)["\']', v)  # ganzes Meta-Tag erlaubt
            if m:
                v = m.group(1)
            d[k] = re.sub(r'[^A-Za-z0-9_\-]', '', v)[:120]   # nur unbedenkliche Zeichen
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
    if isinstance(raw.get('freetext'), dict):
        ft = raw['freetext']
        sec['freetext'] = {
            'title_de':   _clean_str(ft.get('title_de'), 160),
            'title_en':   _clean_str(ft.get('title_en'), 160),
            'content_de': _clean_str(ft.get('content_de'), 20000),
            'content_en': _clean_str(ft.get('content_en'), 20000),
        }
    if isinstance(raw.get('poll'), dict):
        pl = raw['poll']
        opts = []
        if isinstance(pl.get('options'), list):
            for o in pl['options'][:5]:
                if not isinstance(o, dict):
                    continue
                de = _clean_str(o.get('label_de'), 120)
                en = _clean_str(o.get('label_en'), 120)
                if de or en:
                    opts.append({'label_de': de, 'label_en': en})
        q_de = _clean_str(pl.get('question_de'), 300)
        q_en = _clean_str(pl.get('question_en'), 300)
        if q_de or q_en:
            pid = _clean_str(pl.get('id'), 32)
            if not re.fullmatch(r'[a-f0-9]{12}', pid or ''):
                pid = uuid.uuid4().hex[:12]
            sec['poll'] = {'id': pid, 'question_de': q_de, 'question_en': q_en,
                           'options': opts}
        else:
            sec['poll'] = {}
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
    if isinstance(raw.get('countdown'), dict):
        cd = raw['countdown']
        target = _clean_str(cd.get('target'), 20)
        # erwartet datetime-local-Format YYYY-MM-DDTHH:MM
        if not re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$', target):
            target = ''
        size = _clean_str(cd.get('size'), 1)
        if size not in ('s', 'm', 'l'):
            size = 'm'
        sec['countdown'] = {
            'target':      target,
            'size':        size,
            'title_de':    _clean_str(cd.get('title_de'), 120),
            'title_en':    _clean_str(cd.get('title_en'), 120),
            'subtitle_de': _clean_str(cd.get('subtitle_de'), 300),
            'subtitle_en': _clean_str(cd.get('subtitle_en'), 300),
            'expired_de':  _clean_str(cd.get('expired_de'), 120),
            'expired_en':  _clean_str(cd.get('expired_en'), 120),
            'image':       _clean_str(cd.get('image'), 500),
            'notify':      bool(cd.get('notify')),
        } if target else {}
    save_site(site)
    log_audit('settings_sections')
    return jsonify({'ok': True})


@admin_app.route('/api/poll/reset', methods=['POST'])
def api_poll_reset():
    """Alle abgegebenen Stimmen der aktuellen Umfrage löschen."""
    err = _api_auth()
    if err:
        return err
    save_poll_votes({})
    log_audit('poll_reset')
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


def write_backup_zip(fp) -> None:
    """Schreibt ein vollständiges Backup in ein Datei-Objekt (BytesIO oder offene Datei).

    Gemeinsame Basis für den Download-Button und das automatische Backup — damit
    können beide nicht auseinanderlaufen.
    """
    with zipfile.ZipFile(fp, 'w', zipfile.ZIP_DEFLATED) as z:
        for name in ('site.json', 'stats.json', 'messages.json', 'users.json',
                     'comments.json', 'audit.json', 'subscribers.json',
                     'dm.json', 'dm.key', 'admin_2fa.json', 'secret.key',
                     'ai_usage.json'):
            p = Path(_DATA) / name
            if p.is_file():
                z.write(p, name)
        for f in UPLOADS_DIR.iterdir():
            if f.is_file():
                z.write(f, 'uploads/' + f.name)
        # Bibliothek-PDFs (hochgeladen und erzeugt)
        if DOCS_DIR.is_dir():
            for f in sorted(DOCS_DIR.iterdir()):
                if f.is_file() and _DOC_FILE_RE.match(f.name):
                    z.write(f, 'docs/' + f.name)
        # Kartenspiel-Spielstände + Verlauf (66_<uid>.json / 66hist_<uid>.json)
        if GAMES_DIR.is_dir():
            for f in sorted(GAMES_DIR.iterdir()):
                if f.is_file() and _GAME_FILE_RE.match(f.name):
                    z.write(f, 'games/' + f.name)
        # Mitglieder-Avatare (<uid>.jpg)
        if MEMBER_AVATARS_DIR.is_dir():
            for f in sorted(MEMBER_AVATARS_DIR.iterdir()):
                if f.is_file() and re.fullmatch(r'[a-f0-9]{6,32}\.jpg', f.name):
                    z.write(f, 'member_avatars/' + f.name)
        # Verschlüsselte DM-Anhänge (<fid>)
        if DM_FILES_DIR.is_dir():
            for f in sorted(DM_FILES_DIR.iterdir()):
                if f.is_file() and _FID_RE.match(f.name):
                    z.write(f, 'dm_files/' + f.name)


def list_auto_backups() -> list:
    """Vorhandene automatische Backups, neueste zuerst."""
    try:
        files = [f for f in BACKUPS_DIR.iterdir()
                 if f.is_file() and _AUTO_BACKUP_RE.match(f.name)]
    except OSError:
        return []
    out = []
    for f in sorted(files, key=lambda p: p.name, reverse=True):
        try:
            out.append({'name': f.name, 'size': f.stat().st_size,
                        'date': f.name[12:22]})
        except OSError:
            continue
    return out


def _rotate_auto_backups(keep: int) -> None:
    for old in list_auto_backups()[keep:]:
        try:
            (BACKUPS_DIR / old['name']).unlink()
            log.info("Altes automatisches Backup entfernt: %s", old['name'])
        except OSError as e:
            log.warning("Altes Backup '%s' konnte nicht entfernt werden: %s", old['name'], e)


def create_auto_backup(keep: int) -> Path | None:
    """Schreibt das Backup des heutigen Tages (atomar) und rotiert die alten weg."""
    target = BACKUPS_DIR / f'mypage-auto-{date.today().isoformat()}.zip'
    tmp = target.with_suffix('.tmp')
    try:
        with open(tmp, 'wb') as f:
            write_backup_zip(f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)   # nie ein halb geschriebenes Backup sichtbar
    except Exception as e:
        log.warning("Automatisches Backup fehlgeschlagen: %s", e)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return None
    log.info("Automatisches Backup erstellt: %s (%.1f MB)",
             target.name, target.stat().st_size / 1048576)
    _rotate_auto_backups(keep)
    return target


def auto_backup_loop() -> None:
    """Sorgt dafür, dass es pro Tag ein Backup gibt.

    Stündlich prüfen statt alle 24 h schlafen: übersteht Neustarts, ohne bei jedem
    Start ein zusätzliches Backup anzulegen (die Datei des Tages existiert dann schon).
    """
    while True:
        try:
            keep = int(load_config().get('auto_backup_keep', AUTO_BACKUP_KEEP_DEFAULT) or 0)
            if keep > 0:
                if not (BACKUPS_DIR / f'mypage-auto-{date.today().isoformat()}.zip').exists():
                    create_auto_backup(keep)
                else:
                    _rotate_auto_backups(keep)   # geänderte Aufbewahrung sofort anwenden
        except Exception as e:
            log.warning("Automatisches Backup: Durchlauf fehlgeschlagen: %s", e)
        time.sleep(3600)


@admin_app.route('/api/backup')
def api_backup():
    err = _api_auth()
    if err:
        return err
    buf = io.BytesIO()
    write_backup_zip(buf)
    buf.seek(0)
    return send_file(buf, mimetype='application/zip', as_attachment=True,
                     download_name=f'mypage-backup-{date.today().isoformat()}.zip')


def _auto_backup_path(name: str) -> Path | None:
    """Pfad zu einem automatischen Backup — nur exakt passende Namen, sonst None."""
    if not _AUTO_BACKUP_RE.match(name or ''):
        return None
    return safe_under(BACKUPS_DIR, name)


@admin_app.route('/api/backups')
def api_backups_list():
    err = _api_auth()
    if err:
        return err
    keep = int(load_config().get('auto_backup_keep', AUTO_BACKUP_KEEP_DEFAULT) or 0)
    return jsonify({'backups': list_auto_backups(), 'keep': keep})


@admin_app.route('/api/backups/run', methods=['POST'])
def api_backups_run():
    err = _api_auth()
    if err:
        return err
    keep = int(load_config().get('auto_backup_keep', AUTO_BACKUP_KEEP_DEFAULT) or 0)
    if keep <= 0:
        return jsonify({'error': 'disabled'}), 400
    target = create_auto_backup(keep)
    if target is None:
        return jsonify({'error': 'backup failed'}), 500
    log_audit('backup_auto_manual', target.name)
    return jsonify({'ok': True, 'name': target.name})


@admin_app.route('/api/backups/<name>')
def api_backups_download(name: str):
    err = _api_auth()
    if err:
        return err
    p = _auto_backup_path(name)
    if p is None or not p.is_file():
        return jsonify({'error': 'not found'}), 404
    return send_file(p, mimetype='application/zip', as_attachment=True,
                     download_name=p.name)


@admin_app.route('/api/backups/<name>', methods=['DELETE'])
def api_backups_delete(name: str):
    err = _api_auth()
    if err:
        return err
    p = _auto_backup_path(name)
    if p is None or not p.is_file():
        return jsonify({'error': 'not found'}), 404
    try:
        p.unlink()
    except OSError:
        log.warning("Backup '%s' konnte nicht gelöscht werden", p.name)
        return jsonify({'error': 'delete failed'}), 500
    log_audit('backup_auto_delete', p.name)
    return jsonify({'ok': True})


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
                              'comments.json', 'audit.json', 'subscribers.json', 'dm.json',
                              'admin_2fa.json', 'ai_usage.json'):
                    target = safe_under(Path(_DATA), member)
                elif member in ('dm.key', 'secret.key'):  # Binär-/Text-Schlüssel, kein JSON
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
                elif member.startswith('member_avatars/'):
                    name = Path(member).name
                    if not re.fullmatch(r'[a-f0-9]{6,32}\.jpg', name):
                        continue
                    target = safe_under(MEMBER_AVATARS_DIR, name)
                elif member.startswith('dm_files/'):
                    name = Path(member).name
                    if not _FID_RE.match(name):
                        continue
                    target = safe_under(DM_FILES_DIR, name)
                elif member.startswith('docs/'):
                    name = Path(member).name
                    if not _DOC_FILE_RE.match(name):
                        continue
                    # Inhalt prüfen — im Backup darf unter .pdf nichts anderes stecken
                    if not z.read(member).startswith(b'%PDF-'):
                        continue
                    target = safe_under(DOCS_DIR, name)
                else:
                    continue
                if target is None:
                    continue
                with open(target, 'wb') as dst:
                    dst.write(z.read(member))
                restored += 1
    except (zipfile.BadZipFile, json.JSONDecodeError, KeyError):
        return jsonify({'error': 'invalid backup'}), 400
    _dm_reset_fernet()  # evtl. neuen dm.key übernehmen
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


# ── KI-Bilderzeugung (Google Gemini) ──────────────────────────────────────────
#
# Titelbilder für Bibliothek-Einträge von Hand zu beschaffen ist mühsam. Gemini
# erzeugt sie auf Zuruf; ohne hinterlegten API-Key bleibt die Funktion komplett
# unsichtbar. Die erzeugte Datei landet über dieselbe Pipeline wie jeder Upload
# unter /uploads/ — nie als Fremd-URL im Eintrag, sonst scheitert die
# PDF-Erzeugung an `_lib_pdf_fetcher` (die lässt bewusst nur lokale Dateien zu).

GEMINI_IMAGE_MODELS = ('gemini-3.1-flash-image', 'gemini-3.1-flash-lite-image',
                       'gemini-3-pro-image', 'gemini-2.5-flash-image')
# Rückfall für die Textmodelle: die Auswahl im KI-Studio kommt normalerweise
# live von `client.models.list()`, weil Google die Namen laufend ändert. Nur
# wenn dieser Aufruf scheitert, greift diese Liste — Reihenfolge = Vorauswahl.
GEMINI_TEXT_MODELS = ('gemini-3.6-flash', 'gemini-3.5-flash', 'gemini-3.1-pro-preview',
                      'gemini-2.5-pro', 'gemini-2.5-flash')
GEMINI_IMAGE_RATIOS = ('16:9', '3:2', '4:3', '1:1', '3:4', '2:3', '9:16', '21:9')
GEMINI_IMAGE_TIMEOUT_MS = 120_000   # google-genai erwartet Millisekunden
GEMINI_TEXT_TIMEOUT_MS = 180_000    # Text mit zwei Sprachen dauert länger
AI_IMAGE_PROMPT_MAX = 1200
AI_IMAGE_MAX_PER_HOUR = 20
_ai_image_times: list[float] = []
AI_TEXT_TOPIC_MAX = 4000
AI_TEXT_MAX_PER_HOUR = 60           # Text ist deutlich billiger als ein Bild
_ai_text_times: list[float] = []
AI_STUDIO_MAX_IMAGES = 4            # pro Anfrage; jedes Bild zählt einzeln aufs Limit
AI_TMP_TTL = 3600                   # Entwürfe verfallen nach einer Stunde
# Modellnamen wandern in die Anfrage-URL. Streng prüfen, statt auf die Liste zu
# vertrauen: die kommt live von Google und darf nichts durchreichen, was einen
# Pfad verlassen könnte.
_AI_MODEL_RE = re.compile(r'^[a-z0-9][a-z0-9.\-]{2,63}$')
_AI_TMP_RE = re.compile(r'^[a-f0-9]{32}$')

AI_TEXT_KINDS = ('blog', 'news', 'project', 'library', 'seo')
AI_TEXT_TONES = ('sachlich', 'locker', 'technisch', 'werblich', 'persoenlich')
AI_TEXT_LENGTHS = {'kurz': 150, 'mittel': 400, 'lang': 800}
AI_TRANSLATE_PROVIDERS = ('mymemory', 'gemini')

# Abbruchgründe, bei denen Gemini die Anfrage inhaltlich abgelehnt hat — davon
# ist der Nutzer zu unterscheiden von einem technischen Fehler, denn hier hilft
# nur eine andere Beschreibung, kein erneuter Versuch.
_GEMINI_IMAGE_REFUSALS = {
    genai_types.FinishReason.SAFETY, genai_types.FinishReason.PROHIBITED_CONTENT,
    genai_types.FinishReason.BLOCKLIST, genai_types.FinishReason.RECITATION,
    genai_types.FinishReason.SPII, genai_types.FinishReason.IMAGE_SAFETY,
    genai_types.FinishReason.IMAGE_PROHIBITED_CONTENT,
    genai_types.FinishReason.IMAGE_RECITATION,
} if _HAS_GENAI else set()


def _gemini_key() -> str:
    return (load_config().get('gemini_api_key') or '').strip()


def gemini_text_enabled() -> bool:
    """Ob Textfunktionen (Studio, KI-Übersetzung) angeboten werden dürfen."""
    return _HAS_GENAI and bool(_gemini_key())


def gemini_image_enabled() -> bool:
    """Ob der Knopf „Bild generieren" angeboten werden darf.

    Pillow gehört mit ins Gate: ohne sie ließe sich die Antwort von Gemini nicht
    in ein WebP wandeln, der Knopf wäre also wirkungslos.
    """
    return gemini_text_enabled() and _HAS_PIL


_gemini_client_cache: tuple[str, object] | None = None
_gemini_client_lock = threading.Lock()


def _gemini_client():
    """Client mit dem hinterlegten Schlüssel. Nur aufrufen, wenn ein Key da ist.

    Der Client wird zwischengespeichert und muss es auch bleiben: Ein Einzeiler
    wie `_gemini_client().models.generate_content(...)` erzeugt ein Objekt ohne
    Referenz, das der Sammler mitten im Aufruf einziehen darf. Sein Destruktor
    schließt die HTTP-Verbindung, und die laufende Anfrage endet mit
    „Cannot send a request, as the client has been closed" — noch bevor sie
    Google erreicht. Aufrufer binden das Ergebnis zusätzlich an eine lokale
    Variable, damit das auch ohne diesen Cache hält.

    Ein Wechsel des API-Keys in den Add-on-Optionen baut den Client neu auf.
    """
    global _gemini_client_cache
    key = _gemini_key()
    with _gemini_client_lock:
        if _gemini_client_cache is not None and _gemini_client_cache[0] == key:
            return _gemini_client_cache[1]
        client = genai.Client(api_key=key)
        _gemini_client_cache = (key, client)
        return client


def _ai_settings(site: dict | None = None) -> dict:
    """Die im Admin gewählten KI-Vorgaben aus site.json.

    Liegt hier nichts, greifen die Add-on-Optionen — der Admin darf die
    HA-Konfiguration überschreiben, ohne sie anzufassen.
    """
    ai = (site if site is not None else load_site()).get('ai')
    return ai if isinstance(ai, dict) else {}


def _ai_model_or(candidate: str, fallback: str) -> str:
    c = (candidate or '').strip()
    return c if _AI_MODEL_RE.match(c) else fallback


def _gemini_image_model() -> str:
    cfg = (load_config().get('gemini_image_model') or '').strip()
    default = cfg if cfg in GEMINI_IMAGE_MODELS else GEMINI_IMAGE_MODELS[0]
    return _ai_model_or(_ai_settings().get('image_model'), default)


def _gemini_text_model() -> str:
    return _ai_model_or(_ai_settings().get('text_model'), GEMINI_TEXT_MODELS[0])


def _gemini_image_ratio() -> str:
    cfg = (load_config().get('gemini_image_ratio') or '').strip()
    default = cfg if cfg in GEMINI_IMAGE_RATIOS else GEMINI_IMAGE_RATIOS[0]
    r = (_ai_settings().get('image_ratio') or '').strip()
    return r if r in GEMINI_IMAGE_RATIOS else default


def _ai_translate_provider() -> str:
    p = (_ai_settings().get('translate_provider') or '').strip()
    if p not in AI_TRANSLATE_PROVIDERS:
        return 'mymemory'
    # Ohne Key wäre „gemini" ein Versprechen, das die Übersetzung nicht halten kann
    return p if (p != 'gemini' or gemini_text_enabled()) else 'mymemory'


def _ai_rate_take(times: list[float], limit: int, n: int = 1) -> bool:
    """Rollierendes Stundenlimit. Bewusst global statt je IP: es schützt das
    Bezahlkontingent bei Google, nicht eine Ressource dieses Servers.

    Die Buchung passiert vor dem Aufruf — ein Fehlversuch kostet bei Google auch.
    """
    now = time.time()
    times[:] = [x for x in times if now - x < 3600]
    if len(times) + n > limit:
        return False
    times.extend([now] * n)
    return True


def _gemini_generate_image(prompt: str, *, model: str = '', ratio: str = '',
                           ref: tuple[bytes, str] | None = None
                           ) -> tuple[bytes | None, str, str]:
    """Erzeugt ein Bild über Gemini. Zurück: (Bilddaten, MIME-Typ, Fehlercode).

    `ref` ist ein optionales Vorlagenbild (Daten, MIME) — damit wird aus der
    Anfrage eine Abwandlung statt einer Neuschöpfung.

    Fehlercodes: '' (Erfolg), 'refused', 'empty', 'failed'. Die Ausnahme selbst
    geht ausschließlich ins Log, nie an den Client.
    """
    model = model or _gemini_image_model()
    ratio = ratio or _gemini_image_ratio()
    contents: list = [prompt]
    if ref is not None:
        contents.append(genai_types.Part.from_bytes(data=ref[0], mime_type=ref[1]))
    try:
        client = _gemini_client()
        resp = client.models.generate_content(
            model=model, contents=contents,
            config=genai_types.GenerateContentConfig(
                response_modalities=['IMAGE'],
                image_config=genai_types.ImageConfig(aspect_ratio=ratio),
                # Das SDK setzt von sich aus kein Timeout — ohne das hier könnte
                # ein hängender Aufruf dauerhaft einen Waitress-Thread binden.
                http_options=genai_types.HttpOptions(timeout=GEMINI_IMAGE_TIMEOUT_MS),
            ),
        )
        cands = resp.candidates or []
        if cands and cands[0].finish_reason in _GEMINI_IMAGE_REFUSALS:
            log.info("Gemini hat die Bildanfrage abgelehnt: %s", cands[0].finish_reason)
            _ai_usage_record(model, resp)
            return None, '', 'refused'
        for part in (resp.parts or []):
            if part.inline_data is not None and part.inline_data.data:
                _ai_usage_record(model, resp, images=1)
                return (part.inline_data.data,
                        part.inline_data.mime_type or 'image/png', '')
        _ai_usage_record(model, resp)
    except genai_errors.APIError as e:
        # Bewusst nur der Statuscode: die Meldung des SDK kann die vollständige
        # Anfrage-URL samt API-Key enthalten, die hat im Add-on-Log nichts zu suchen.
        log.warning("Gemini-Bildanfrage fehlgeschlagen (%s): Status %s",
                    model, getattr(e, 'code', '') or type(e).__name__)
        return None, '', 'failed'
    except Exception as e:
        # Absichtlich breit: SDK-interne Fehler dürfen nicht als HTML-Fehlerseite
        # beim Frontend landen, das ausschließlich JSON erwartet.
        log.error("Gemini-Bildanfrage (%s) unerwartet fehlgeschlagen: %s: %s",
                  model, type(e).__name__, e)
        return None, '', 'failed'
    log.warning("Gemini-Antwort (%s) enthielt kein Bild", model)
    return None, '', 'empty'


@admin_app.route('/api/ai/image-support')
def api_ai_image_support():
    err = _api_auth()
    if err:
        return err
    return jsonify({'available': gemini_image_enabled()})


@admin_app.route('/api/ai/image', methods=['POST'])
def api_ai_image():
    err = _api_auth()
    if err:
        return err
    if not gemini_image_enabled():
        return jsonify({'error': 'no_api_key'}), 400
    prompt = _clean_str((request.get_json(silent=True) or {}).get('prompt'),
                        AI_IMAGE_PROMPT_MAX)
    if len(prompt) < 3:
        return jsonify({'error': 'invalid'}), 400
    if not _ai_rate_take(_ai_image_times, AI_IMAGE_MAX_PER_HOUR):
        return jsonify({'error': 'rate_limited'}), 429
    data, _mime, code = _gemini_generate_image(prompt)
    if code:
        return jsonify({'error': {'refused': 'ai_refused',
                                  'empty': 'ai_empty'}.get(code, 'ai_failed')}), 502
    try:
        # ai=True → Dateiname trägt den Marker, an dem die Auslieferung später
        # die Pflicht-Kennzeichnung „KI generiert" festmacht
        name = _store_upload_image(data, ai=True)
    except Exception as e:
        log.warning("KI-Bild konnte nicht gespeichert werden: %s", e)
        name = None
    if not name:
        return jsonify({'error': 'image_failed'}), 502
    log.info("KI-Titelbild erzeugt (%s, %s): %s", _gemini_image_model(),
             _gemini_image_ratio(), name)
    return jsonify({'ok': True, 'url': '/uploads/' + name})


# ── KI-Studio ─────────────────────────────────────────────────────────────────
#
# Der Bild-Knopf in der Bibliothek legt sein Ergebnis sofort unter uploads/ ab —
# das ist dort richtig, weil das Bild direkt in den offenen Eintrag wandert. Im
# Studio wird dagegen ausprobiert: mehrere Entwürfe, die meisten davon Ausschuss.
# Die landen erst in ai_tmp/ und wechseln nur auf ausdrückliches „Speichern" in
# die Uploads. So wächst die Bildersammlung nicht mit jedem Fehlversuch, und ein
# verworfener Entwurf war nie öffentlich abrufbar.

_ai_tmp: dict[str, dict] = {}       # id → {mime, ts, prompt}
_ai_models_cache: tuple[float, dict] | None = None
AI_REF_MAX_BYTES = 8 * 1024 * 1024
_AI_REF_MIME = {'.webp': 'image/webp', '.png': 'image/png', '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg', '.gif': 'image/gif'}

_GEMINI_TEXT_REFUSALS = {
    genai_types.FinishReason.SAFETY, genai_types.FinishReason.PROHIBITED_CONTENT,
    genai_types.FinishReason.BLOCKLIST, genai_types.FinishReason.RECITATION,
    genai_types.FinishReason.SPII,
} if _HAS_GENAI else set()


def _ai_tmp_sweep() -> None:
    """Abgelaufene Entwürfe löschen — auch die, deren Eintrag ein Neustart
    verloren hat. Deshalb über die Dateizeit statt über die Registry."""
    now = time.time()
    for tid, meta in list(_ai_tmp.items()):
        if now - meta.get('ts', 0) > AI_TMP_TTL:
            _ai_tmp.pop(tid, None)
    try:
        for f in AI_TMP_DIR.iterdir():
            try:
                if f.is_file() and now - f.stat().st_mtime > AI_TMP_TTL:
                    f.unlink()
            except OSError:
                pass
    except OSError:
        pass


def _ai_tmp_file(tid: str) -> Path | None:
    if not _AI_TMP_RE.match(tid or ''):
        return None
    p = safe_under(AI_TMP_DIR, tid + '.img')
    return p if (p is not None and p.is_file()) else None


def _ai_ref_image(url: str) -> tuple[bytes, str] | None:
    """Vorlagenbild aus den eigenen Uploads laden. Fremd-URLs sind bewusst nicht
    erlaubt: der Server soll auf Zuruf des Browsers nichts nachladen (SSRF)."""
    name = (url or '').strip().rsplit('/', 1)[-1]
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXT:
        return None
    p = safe_under(UPLOADS_DIR, name)
    if p is None or not p.is_file() or p.stat().st_size > AI_REF_MAX_BYTES:
        return None
    return p.read_bytes(), _AI_REF_MIME.get(ext, 'image/png')


def _ai_model_lists() -> dict:
    """Verfügbare Modelle bei Google erfragen (eine Stunde gecacht).

    Google benennt Modelle laufend um und stellt alte ab. Eine fest verdrahtete
    Liste wäre nach jedem Wechsel falsch und würde ein Add-on-Update erzwingen —
    also live fragen und nur im Fehlerfall auf die Konstanten zurückfallen.
    """
    global _ai_models_cache
    if _ai_models_cache and time.time() - _ai_models_cache[0] < 3600:
        return _ai_models_cache[1]
    out = {'image': list(GEMINI_IMAGE_MODELS), 'text': list(GEMINI_TEXT_MODELS)}
    if gemini_text_enabled():
        try:
            img, txt = [], []
            client = _gemini_client()
            for m in client.models.list():
                short = (m.name or '').rsplit('/', 1)[-1]
                if not _AI_MODEL_RE.match(short):
                    continue
                if 'generateContent' not in (m.supported_actions or []):
                    continue
                if any(x in short for x in ('embedding', 'aqa', 'tts', 'audio',
                                            'veo', 'imagen', 'learnlm')):
                    continue
                (img if 'image' in short else txt).append(short)
            if img or txt:
                out = {'image': sorted(set(img), reverse=True),
                       'text': sorted(set(txt), reverse=True)}
        except Exception as e:
            # Nicht schlimm: die Konstanten reichen zum Arbeiten
            log.info("Gemini-Modellliste nicht abrufbar (%s) — nutze Vorgabeliste",
                     type(e).__name__)
    _ai_models_cache = (time.time(), out)
    return out


@admin_app.route('/api/ai/status')
def api_ai_status():
    err = _api_auth()
    if err:
        return err
    now = time.time()
    img_used = len([x for x in _ai_image_times if now - x < 3600])
    txt_used = len([x for x in _ai_text_times if now - x < 3600])
    return jsonify({
        'image': gemini_image_enabled(), 'text': gemini_text_enabled(),
        'image_model': _gemini_image_model(), 'text_model': _gemini_text_model(),
        'image_ratio': _gemini_image_ratio(), 'ratios': list(GEMINI_IMAGE_RATIOS),
        'translate_provider': _ai_translate_provider(),
        'image_used': img_used, 'image_max': AI_IMAGE_MAX_PER_HOUR,
        'text_used': txt_used, 'text_max': AI_TEXT_MAX_PER_HOUR,
        'max_images': AI_STUDIO_MAX_IMAGES,
    })


@admin_app.route('/api/ai/models')
def api_ai_models():
    err = _api_auth()
    if err:
        return err
    return jsonify(_ai_model_lists())


@admin_app.route('/api/ai/settings', methods=['POST'])
def api_ai_settings():
    err = _api_auth()
    if err:
        return err
    raw = request.get_json(silent=True) or {}
    site = load_site()
    ai = site.get('ai') if isinstance(site.get('ai'), dict) else {}
    for key in ('image_model', 'text_model'):
        v = _clean_str(raw.get(key), 64)
        if v and _AI_MODEL_RE.match(v):
            ai[key] = v
    ratio = _clean_str(raw.get('image_ratio'), 10)
    if ratio in GEMINI_IMAGE_RATIOS:
        ai['image_ratio'] = ratio
    prov = _clean_str(raw.get('translate_provider'), 20)
    if prov in AI_TRANSLATE_PROVIDERS:
        ai['translate_provider'] = prov
    site['ai'] = ai
    save_site(site)
    return jsonify({'ok': True, 'translate_provider': _ai_translate_provider()})


@admin_app.route('/api/ai/studio/image', methods=['POST'])
def api_ai_studio_image():
    err = _api_auth()
    if err:
        return err
    if not gemini_image_enabled():
        return jsonify({'error': 'no_api_key'}), 400
    raw = request.get_json(silent=True) or {}
    prompt = _clean_str(raw.get('prompt'), AI_IMAGE_PROMPT_MAX)
    if len(prompt) < 3:
        return jsonify({'error': 'invalid'}), 400
    model = _ai_model_or(raw.get('model'), _gemini_image_model())
    ratio = raw.get('ratio') if raw.get('ratio') in GEMINI_IMAGE_RATIOS else _gemini_image_ratio()
    try:
        count = max(1, min(AI_STUDIO_MAX_IMAGES, int(raw.get('count') or 1)))
    except (TypeError, ValueError):
        count = 1
    ref = _ai_ref_image(raw.get('ref') or '') if raw.get('ref') else None
    if raw.get('ref') and ref is None:
        return jsonify({'error': 'bad_ref'}), 400
    if not _ai_rate_take(_ai_image_times, AI_IMAGE_MAX_PER_HOUR, count):
        return jsonify({'error': 'rate_limited'}), 429
    _ai_tmp_sweep()
    images, last = [], 'failed'
    for _ in range(count):
        data, mime, code = _gemini_generate_image(prompt, model=model, ratio=ratio,
                                                  ref=ref)
        if code:
            last = code
            continue
        tid = uuid.uuid4().hex
        target = safe_under(AI_TMP_DIR, tid + '.img')
        if target is None:
            continue
        try:
            target.write_bytes(data)
        except OSError as e:
            log.warning("KI-Entwurf konnte nicht zwischengespeichert werden: %s", e)
            continue
        _ai_tmp[tid] = {'mime': mime, 'ts': time.time(), 'prompt': prompt}
        images.append({'id': tid, 'url': 'api/ai/studio/preview/' + tid})
    if not images:
        return jsonify({'error': {'refused': 'ai_refused',
                                  'empty': 'ai_empty'}.get(last, 'ai_failed')}), 502
    log.info("KI-Studio: %d Bildentwurf/-entwürfe erzeugt (%s, %s%s)",
             len(images), model, ratio, ', mit Vorlage' if ref else '')
    return jsonify({'ok': True, 'images': images})


@admin_app.route('/api/ai/studio/preview/<tid>')
def api_ai_studio_preview(tid: str):
    err = _api_auth()
    if err:
        return err
    p = _ai_tmp_file(tid)
    if p is None:
        return jsonify({'error': 'not_found'}), 404
    mime = (_ai_tmp.get(tid) or {}).get('mime') or 'image/png'
    resp = send_file(p, mimetype=mime)
    # Entwürfe sind flüchtig — ein Cache-Treffer nach dem Verwerfen wäre irritierend
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@admin_app.route('/api/ai/studio/image/keep', methods=['POST'])
def api_ai_studio_keep():
    err = _api_auth()
    if err:
        return err
    tid = _clean_str((request.get_json(silent=True) or {}).get('id'), 40)
    p = _ai_tmp_file(tid)
    if p is None:
        return jsonify({'error': 'not_found'}), 404
    try:
        # ai=True → Dateiname trägt den Marker, an dem die Auslieferung später
        # die Pflicht-Kennzeichnung „KI generiert" festmacht
        name = _store_upload_image(p.read_bytes(), ai=True)
    except Exception as e:
        log.warning("KI-Entwurf konnte nicht übernommen werden: %s", e)
        name = None
    if not name:
        return jsonify({'error': 'image_failed'}), 502
    try:
        p.unlink()
    except OSError:
        pass
    _ai_tmp.pop(tid, None)
    log.info("KI-Entwurf übernommen: %s", name)
    return jsonify({'ok': True, 'url': '/uploads/' + name})


@admin_app.route('/api/ai/studio/image/discard', methods=['POST'])
def api_ai_studio_discard():
    err = _api_auth()
    if err:
        return err
    tid = _clean_str((request.get_json(silent=True) or {}).get('id'), 40)
    p = _ai_tmp_file(tid)
    if p is not None:
        try:
            p.unlink()
        except OSError:
            pass
    _ai_tmp.pop(tid, None)
    return jsonify({'ok': True})


# ── KI-Texte ──────────────────────────────────────────────────────────────────

_AI_TEXT_KIND_DE = {
    'blog': 'ein Blogartikel',
    'news': 'eine kurze Neuigkeit (zwei bis vier Sätze, ohne Zwischenüberschriften)',
    'project': 'eine Projektbeschreibung für ein Technik- oder Softwareprojekt',
    'library': 'eine Zusammenfassung für einen Eintrag in einer Wissens-Bibliothek',
    'seo': 'ausschließlich Titel und SEO-Beschreibung; das Feld „text" bleibt leer',
}
_AI_TEXT_TONE_DE = {
    'sachlich': 'sachlich und nüchtern',
    'locker': 'locker und persönlich, aber nicht anbiedernd',
    'technisch': 'technisch präzise, für ein fachkundiges Publikum',
    'werblich': 'werbend und begeisternd, ohne Übertreibung',
    'persoenlich': 'in der Ich-Form, erzählend',
}


def _ai_text_schema(langs: list[str]):
    """JSON-Schema für die Antwort — erzwingt beide Sprachen in einem Aufruf.

    Ohne Schema liefert das Modell gern Fließtext mit Vorrede; damit bekommt das
    Frontend verlässlich Titel, SEO-Text, Fließtext und Schlagwörter getrennt.
    """
    one = genai_types.Schema(
        type=genai_types.Type.OBJECT,
        properties={
            'title': genai_types.Schema(type=genai_types.Type.STRING),
            'meta':  genai_types.Schema(type=genai_types.Type.STRING),
            'text':  genai_types.Schema(type=genai_types.Type.STRING),
            'tags':  genai_types.Schema(type=genai_types.Type.ARRAY,
                                        items=genai_types.Schema(type=genai_types.Type.STRING)),
        },
        required=['title', 'meta', 'text', 'tags'],
    )
    return genai_types.Schema(
        type=genai_types.Type.OBJECT,
        properties={lg: one for lg in langs},
        required=list(langs),
    )


def _gemini_generate_text(*, topic: str, kind: str, tone: str, length: str,
                          langs: list[str], mode: str, model: str
                          ) -> tuple[dict | None, str]:
    """Erzeugt Titel, SEO-Beschreibung, Fließtext und Schlagwörter je Sprache.

    Zurück: (Ergebnis, Fehlercode) mit denselben Codes wie bei den Bildern.
    """
    words = AI_TEXT_LENGTHS.get(length, 400)
    sys = (
        "Du bist Redakteur einer persönlichen Website. Du lieferst fertige, "
        "veröffentlichungsreife Inhalte: keine Rückfragen, keine Meta-Kommentare, "
        "keine Platzhalter wie [hier einfügen], keine erfundenen Zahlen oder Zitate. "
        "Feldbedeutung: 'title' = Überschrift ohne Markdown-Zeichen; "
        "'meta' = SEO-Beschreibung, ein Satz, höchstens 155 Zeichen; "
        "'text' = Fließtext in Markdown, Zwischenüberschriften ab '##', keine H1; "
        "'tags' = drei bis sechs kurze Schlagwörter, klein geschrieben."
    )
    parts = [
        f"Gewünscht ist {_AI_TEXT_KIND_DE.get(kind, _AI_TEXT_KIND_DE['blog'])}.",
        f"Thema und Stichpunkte:\n{topic}",
        f"Tonfall: {_AI_TEXT_TONE_DE.get(tone, _AI_TEXT_TONE_DE['sachlich'])}.",
        f"Zielumfang: rund {words} Wörter je Sprache.",
    ]
    if len(langs) > 1:
        parts.append(
            "Schreibe die deutsche und die englische Fassung jeweils eigenständig "
            "und idiomatisch — die englische ist keine Wort-für-Wort-Übersetzung."
            if mode != 'translate' else
            "Schreibe zuerst die deutsche Fassung. Die englische Fassung ist deren "
            "treue Übersetzung mit gleicher Gliederung und gleicher Länge."
        )
    else:
        parts.append("Sprache der Ausgabe: "
                     + ("Deutsch." if langs[0] == 'de' else "Englisch."))
    try:
        client = _gemini_client()
        resp = client.models.generate_content(
            model=model, contents=['\n\n'.join(parts)],
            config=genai_types.GenerateContentConfig(
                system_instruction=sys,
                response_mime_type='application/json',
                response_schema=_ai_text_schema(langs),
                http_options=genai_types.HttpOptions(timeout=GEMINI_TEXT_TIMEOUT_MS),
            ),
        )
        _ai_usage_record(model, resp)
        cands = resp.candidates or []
        if cands and cands[0].finish_reason in _GEMINI_TEXT_REFUSALS:
            log.info("Gemini hat die Textanfrage abgelehnt: %s", cands[0].finish_reason)
            return None, 'refused'
        data = json.loads(resp.text or '')
        if not isinstance(data, dict):
            return None, 'empty'
    except genai_errors.APIError as e:
        # Nur der Statuscode: die SDK-Meldung kann die Anfrage-URL samt Key enthalten
        log.warning("Gemini-Textanfrage fehlgeschlagen (%s): Status %s",
                    model, getattr(e, 'code', '') or type(e).__name__)
        return None, 'failed'
    except (ValueError, TypeError) as e:
        log.warning("Gemini-Textantwort (%s) war kein gültiges JSON: %s", model, type(e).__name__)
        return None, 'empty'
    except Exception as e:
        log.error("Gemini-Textanfrage (%s) unerwartet fehlgeschlagen: %s: %s",
                  model, type(e).__name__, e)
        return None, 'failed'
    out = {}
    for lg in langs:
        d = data.get(lg) if isinstance(data.get(lg), dict) else {}
        tags = d.get('tags') if isinstance(d.get('tags'), list) else []
        out[lg] = {
            'title': _clean_str(d.get('title'), 150),
            'meta':  _clean_str(d.get('meta'), 300),
            'text':  _clean_str(d.get('text'), 30000),
            'tags':  [_clean_str(t, 40) for t in tags[:8] if _clean_str(t, 40)],
        }
    if not any(v['title'] or v['text'] for v in out.values()):
        return None, 'empty'
    return out, ''


@admin_app.route('/api/ai/text', methods=['POST'])
def api_ai_text():
    err = _api_auth()
    if err:
        return err
    if not gemini_text_enabled():
        return jsonify({'error': 'no_api_key'}), 400
    raw = request.get_json(silent=True) or {}
    topic = _clean_str(raw.get('topic'), AI_TEXT_TOPIC_MAX)
    if len(topic) < 3:
        return jsonify({'error': 'invalid'}), 400
    kind = raw.get('kind') if raw.get('kind') in AI_TEXT_KINDS else 'blog'
    tone = raw.get('tone') if raw.get('tone') in AI_TEXT_TONES else 'sachlich'
    length = raw.get('length') if raw.get('length') in AI_TEXT_LENGTHS else 'mittel'
    mode = 'translate' if raw.get('mode') == 'translate' else 'native'
    wanted = raw.get('langs')
    langs = [lg for lg in ('de', 'en') if isinstance(wanted, list) and lg in wanted]
    if not langs:
        langs = ['de']
    model = _ai_model_or(raw.get('model'), _gemini_text_model())
    if not _ai_rate_take(_ai_text_times, AI_TEXT_MAX_PER_HOUR):
        return jsonify({'error': 'rate_limited'}), 429
    data, code = _gemini_generate_text(topic=topic, kind=kind, tone=tone,
                                       length=length, langs=langs, mode=mode,
                                       model=model)
    if code:
        return jsonify({'error': {'refused': 'ai_refused',
                                  'empty': 'ai_empty'}.get(code, 'ai_failed')}), 502
    log.info("KI-Text erzeugt (%s, %s, %s)", model, kind, '+'.join(langs))
    return jsonify({'ok': True, 'result': data})


# ── KI-Verbrauch ──────────────────────────────────────────────────────────────
#
# Die Stundenlimits verhindern Ausreißer, sagen aber nichts darüber, was der
# Monat gekostet hat. Google liefert je Antwort die Token-Zahlen mit — die sind
# hier die Wahrheit. Preise liefert die API NICHT, und eine fest verdrahtete
# Preistabelle wäre nach der nächsten Anpassung still falsch. Deshalb pflegt sie
# der Admin selbst: Zahlen von Google, Preis vom Nutzer. Ohne Preis bleibt es bei
# Tokens. Maßgeblich ist und bleibt die Abrechnung in der Google Cloud Console.

AI_USAGE_KEEP_MONTHS = 24
_ai_usage_lock = threading.Lock()

# Vorbelegung der Preistabelle: Listenpreise von ai.google.dev/pricing, Stand
# August 2026 — von Hand gepflegt wie in TUIWatch (`_AI_PRICING`), weil es für
# die Gemini-API keine Preis-Schnittstelle gibt. Der Preiskatalog von Google
# Cloud wäre die einzige Alternative, verlangt aber ein OAuth-Konto statt eines
# API-Keys und scheidet damit für ein Add-on aus.
#
# Ein im Admin eingetragener Preis schlägt diese Werte immer. Bewusst NICHT
# vollständig: Google benennt Modelle laufend um, und ein geratener Preis wäre
# schlimmer als eine leere Zeile — die fragt nach, eine falsche Zahl nicht. Was
# hier fehlt, bleibt leer, bis es jemand einträgt.
GEMINI_DEFAULT_PRICES = {
    # Textmodelle: USD je 1 Mio Tokens
    'gemini-3.6-flash':            {'in': 1.5,  'out': 7.5},
    'gemini-3.5-flash':            {'in': 1.5,  'out': 9.0},
    'gemini-3.5-flash-lite':       {'in': 0.3,  'out': 2.5},
    'gemini-3.1-flash-lite':       {'in': 0.25, 'out': 1.5},
    # dasselbe Modell, je nach Auflistung mit und ohne -preview
    'gemini-3.1-pro-preview':      {'in': 2.0,  'out': 12.0},
    'gemini-3.1-pro':              {'in': 2.0,  'out': 12.0},
    'gemini-2.5-pro':              {'in': 1.25, 'out': 10.0},
    'gemini-2.5-flash':            {'in': 0.3,  'out': 2.5},
    'gemini-2.5-flash-lite':       {'in': 0.1,  'out': 0.4},
    # Bildmodelle: USD je erzeugtem Bild in 1K-Auflösung. Ein Eingabepreis steht
    # hier bewusst nicht — Google weist ihn für diese Modelle nicht getrennt aus.
    'gemini-3.1-flash-image':      {'image': 0.067},
    'gemini-3.1-flash-lite-image': {'image': 0.0336},
    'gemini-3-pro-image':          {'image': 0.134},
    'gemini-2.5-flash-image':      {'image': 0.039},
}


def _ai_price_for(model: str, prices: dict) -> dict:
    """Eigener Preis je Spalte, sonst Vorgabe.

    Spaltenweise mischen statt den ganzen Eintrag zu ersetzen: wer nur den
    Ausgabepreis einträgt, soll nicht stillschweigend den Eingabepreis der
    Vorgabe verlieren. Das Ergebnis wäre eine zu niedrige Summe, die niemandem
    auffällt — und genau dafür ist die Anzeige nicht da.
    """
    return {**(GEMINI_DEFAULT_PRICES.get(model) or {}), **(prices.get(model) or {})}


def _ai_usage_load() -> dict:
    try:
        with open(AI_USAGE_PATH, encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}
    except Exception as e:
        log.warning("ai_usage.json nicht lesbar (%s) — starte mit leerem Verbrauch", e)
        data = {}
    if not isinstance(data.get('months'), dict):
        data['months'] = {}
    if not isinstance(data.get('prices'), dict):
        data['prices'] = {}
    return data


def _ai_usage_record(model: str, resp, images: int = 0) -> None:
    """Bucht eine Anfrage auf den laufenden Monat.

    Wird auch bei abgelehnten oder leeren Antworten aufgerufen: die kosten die
    Eingabe-Tokens genauso. Fehlschläge ohne Antwort tauchen nicht auf — dort
    gibt es nichts zu buchen.
    """
    um = getattr(resp, 'usage_metadata', None)

    def _n(attr: str) -> int:
        try:
            return max(0, int(getattr(um, attr, 0) or 0))
        except (TypeError, ValueError):
            return 0

    # Denk-Tokens werden wie Ausgabe abgerechnet und gehören deshalb dazu
    tin, tout = _n('prompt_token_count'), _n('candidates_token_count') + _n('thoughts_token_count')
    month = date.today().strftime('%Y-%m')
    with _ai_usage_lock:
        data = _ai_usage_load()
        row = data['months'].setdefault(month, {}).setdefault(
            model, {'calls': 0, 'in': 0, 'out': 0, 'images': 0})
        row['calls'] += 1
        row['in'] += tin
        row['out'] += tout
        row['images'] += images
        for old in sorted(data['months'])[:-AI_USAGE_KEEP_MONTHS]:
            del data['months'][old]
        try:
            _atomic_write_json(AI_USAGE_PATH, data, indent=2)
        except Exception as e:
            log.warning("KI-Verbrauch konnte nicht gespeichert werden: %s", e)


def _ai_usage_cost(row: dict, price: dict) -> float:
    """Kosten einer Zeile. Preise sind je Million Tokens bzw. je Bild."""
    return round((row.get('in', 0) / 1e6) * float(price.get('in') or 0)
                 + (row.get('out', 0) / 1e6) * float(price.get('out') or 0)
                 + row.get('images', 0) * float(price.get('image') or 0), 4)


@admin_app.route('/api/ai/usage')
def api_ai_usage():
    err = _api_auth()
    if err:
        return err
    with _ai_usage_lock:
        data = _ai_usage_load()
    months, prices = data['months'], data['prices']
    out = {}
    for month in sorted(months, reverse=True)[:12]:
        rows = []
        for model in sorted(months[month]):
            row = dict(months[month][model])
            row['model'] = model
            row['cost'] = _ai_usage_cost(row, _ai_price_for(model, prices))
            rows.append(row)
        out[month] = rows
    # Auch die gerade eingestellten Modelle anbieten, damit ein Preis schon vor
    # der ersten Anfrage hinterlegt werden kann
    known = sorted({m for mo in months.values() for m in mo}
                   | {_gemini_image_model(), _gemini_text_model()} | set(prices))
    return jsonify({'months': out, 'prices': prices, 'models': known,
                    'defaults': GEMINI_DEFAULT_PRICES,
                    'can_fetch': bool(_billing_key()),
                    'current': date.today().strftime('%Y-%m')})


# Der öffentliche Preiskatalog von Google Cloud nimmt einen API-Schlüssel — aber
# nicht den aus AI Studio: der ist auf die Generative Language API beschränkt und
# wird hier mit API_KEY_SERVICE_BLOCKED abgewiesen. Deshalb ein zweiter,
# getrennter Schlüssel aus einem Projekt, in dem die Cloud Billing API
# freigeschaltet ist. Ohne diesen Schlüssel bleibt der Knopf unsichtbar.
#
# Der Katalog liefert Fließtext („Gemini 2.5 Flash Input Tokens"), keine
# Modell-IDs. Die Zuordnung ist deshalb geraten und wird dem Admin zur Prüfung
# in die Felder gelegt, statt direkt gespeichert zu werden.
CLOUD_BILLING_API = 'https://cloudbilling.googleapis.com/v1'
# Nicht auf einen exakten Namen festnageln: wie Google den Dienst im Katalog
# nennt, ist nicht zugesichert und hat sich schon geändert. Alle Dienste, deren
# Name einen dieser Bausteine enthält, werden durchsucht.
GEMINI_BILLING_HINTS = ('generative language', 'gemini')
AI_SKU_SAMPLES = 40   # Beispiele für die Oberfläche, wenn nichts zugeordnet wurde
# Modalitäts-Zuschläge: Google rechnet Bild-, Video- und Audio-EINGABE getrennt
# vom Text ab. Diese Dimension bildet die Preistabelle nicht ab — solche Posten
# als Textpreis zu buchen wäre schlicht falsch, also bleiben sie außen vor.
_SKU_MODALITIES = ('image', 'video', 'audio')
# Sondertarife: Google führt Stapelverarbeitung, zwischengespeicherte Eingaben,
# feinabgestimmte Modelle und Recherche-Aufschläge als eigene Posten. MyPage ruft
# nichts davon auf — solche Zeilen als Normaltarif zu übernehmen ergäbe eine
# Summe, die zu niedrig ist und deshalb nicht auffällt.
_SKU_SKIP = ('batch', 'cach', 'tuning', 'tuned', 'grounding', 'search',
             'provisioned', 'free tier')

# Der `reason` aus Googles Fehlerkörper ist die einzige belastbare Auskunft.
# Nach dem Statuscode zu gehen wäre falsch: „Dienst nicht freigeschaltet" und
# „Schlüssel auf andere Dienste beschränkt" sind beide 403, verlangen aber
# verschiedene Schritte.
_BILLING_REASONS = {
    'SERVICE_DISABLED':              'billing_disabled',
    'API_KEY_INVALID':               'key_rejected',
    'API_KEY_SERVICE_BLOCKED':       'key_rejected',
    'API_KEY_HTTP_REFERRER_BLOCKED': 'key_rejected',
    'CREDENTIALS_MISSING':           'key_rejected',
}


def _billing_key() -> str:
    return (load_config().get('gemini_billing_key') or '').strip()


def _billing_error(r) -> tuple[str, str]:
    """(Fehlercode, roher Grund) aus einer Google-Fehlerantwort.

    Der rohe Grund geht mit an die Oberfläche: bei einem unbekannten Fall soll
    dort stehen, was Google wirklich sagt, statt einer geratenen Empfehlung.
    """
    try:
        err = (r.json() or {}).get('error') or {}
        reasons = [d.get('reason') for d in (err.get('details') or [])
                   if isinstance(d, dict) and d.get('reason')]
    except ValueError:
        reasons = []
    for reason in reasons:
        if reason in _BILLING_REASONS:
            return _BILLING_REASONS[reason], reason
    return 'failed', (reasons[0] if reasons else f'HTTP {r.status_code}')


def _sku_kind(desc: str, unit: str, model: str) -> str | None:
    """Welche Preisspalte ein Posten füllt — oder None, wenn er nicht passt.

    Reihenfolge ist entscheidend: „Image Input Tokens" ist der Aufschlag für ein
    Bild als EINGABE, nicht der Preis eines erzeugten Bildes. Wer hier zuerst auf
    „image" prüft, schreibt bei jedem Textmodell einen Bildpreis ein.

    Bei Bildmodellen ist die Ausgabe genau das erzeugte Bild; Google rechnet sie
    trotzdem in Tokens ab. Die landen deshalb als Ausgabepreis — die
    Verbrauchszählung führt für diese Modelle ebenfalls Ausgabe-Tokens, das
    rechnet sich von selbst zusammen.
    """
    if any(w in desc for w in _SKU_SKIP):
        return None
    if 'image' in model:
        # Bildmodelle ausschließlich über den Posten je Bild. Ein Token-Posten
        # daneben würde neben dem Bildpreis ein zweites Mal zählen, und welcher
        # der beiden gemeint ist, entscheidet erst der Tarif des Nutzers.
        return 'image' if ('image' in unit or 'per image' in desc) else None
    if any(w in desc for w in _SKU_MODALITIES):
        return None
    if 'output' in desc:
        return 'out'
    if 'input' in desc or 'prompt' in desc:
        return 'in'
    return None


def _sku_price(sku: dict, kind: str) -> float | None:
    """Preis eines Postens in der Einheit, die die Preistabelle erwartet.

    Google nennt den Betrag je Verrechnungseinheit (units + nanos). Token-Preise
    stehen je Token und müssen auf eine Million hochgerechnet werden; ein Preis
    je Bild darf das gerade nicht. Passt die Einheit zu nichts davon, lieber
    None als eine Zahl, die um Faktor 10^6 danebenliegt.
    """
    try:
        expr = (sku.get('pricingInfo') or [])[-1]['pricingExpression']
        rate = (expr.get('tieredRates') or [])[-1]['unitPrice']
        price = int(rate.get('units') or 0) + int(rate.get('nanos') or 0) / 1e9
    except (LookupError, TypeError, ValueError):
        return None
    if price <= 0:
        return None
    if kind == 'image':
        return round(price, 6)
    unit = str(expr.get('usageUnitDescription') or expr.get('usageUnit') or '').lower()
    if 'million' in unit:
        return round(price, 6)
    if 'count' in unit or 'token' in unit:
        return round(price * 1e6, 6)
    return None


def _billing_pages(url: str, field: str, key: str, cap: int = 40) -> tuple[list, str, str]:
    """Blättert eine Katalog-Liste vollständig durch.

    Google liefert die Dienste seitenweise (mehrere tausend Einträge, auch bei
    großem pageSize). Ein einzelner Aufruf würde die gesuchte Zeile schlicht
    verfehlen. Zurück: (Einträge, Fehlercode, Grund).
    """
    items, token = [], ''
    for _ in range(cap):
        params = {'key': key, 'pageSize': 5000}
        if token:
            params['pageToken'] = token
        r = http.get(url, params=params, timeout=30)
        if not r.ok:
            return [], *_billing_error(r)
        data = r.json()
        items.extend(data.get(field) or [])
        token = data.get('nextPageToken') or ''
        if not token:
            break
    return items, '', ''


def _gemini_fetch_prices(models: list[str]) -> tuple[dict | None, str, str]:
    """Preisvorschläge aus dem Cloud-Preiskatalog.

    Zurück: (Ergebnis, Fehlercode, roher Grund von Google). Das Ergebnis trägt
    neben den Preisen auch die gelesenen Dienstnamen und ein paar
    Posten-Bezeichnungen — ohne die ist bei „nichts zugeordnet" nicht zu
    erkennen, ob der falsche Dienst durchsucht wurde oder ob Google seine Posten
    nur anders benennt als erwartet.
    """
    key = _billing_key()
    try:
        services, code, reason = _billing_pages(f'{CLOUD_BILLING_API}/services',
                                                'services', key)
        if code:
            return None, code, reason
        matched = [s for s in services
                   if any(h in str(s.get('displayName', '')).lower()
                          for h in GEMINI_BILLING_HINTS)]
        log.info("Preiskatalog: %d Dienste gelesen, %d passen (%s)", len(services),
                 len(matched), ', '.join(s.get('displayName', '') for s in matched))
        if not matched:
            return ({'prices': {}, 'services': [], 'samples': [],
                     'service_count': len(services), 'sku_count': 0},
                    'service_not_found', '')
        skus = []
        for s in matched:
            page, code, reason = _billing_pages(f"{CLOUD_BILLING_API}/{s['name']}/skus",
                                                'skus', key)
            if code:
                return None, code, reason
            skus.extend(page)
    except Exception as e:
        # Nur der Typ: die Meldung von requests enthält die URL samt Key
        log.warning("Preiskatalog nicht abrufbar: %s", type(e).__name__)
        return None, 'failed', type(e).__name__
    # Längster Treffer gewinnt, sonst schnappt sich „gemini-3.5-flash" die SKUs
    # von „gemini-3.5-flash-lite"
    wanted = sorted(((m, m.replace('-', ' ').lower()) for m in models),
                    key=lambda x: -len(x[1]))
    out: dict[str, dict] = {}
    for sku in skus:
        desc = str(sku.get('description') or '').lower()
        model = next((m for m, needle in wanted if needle in desc), None)
        if not model:
            continue
        try:
            expr = (sku.get('pricingInfo') or [])[-1]['pricingExpression']
            unit = str(expr.get('usageUnitDescription') or expr.get('usageUnit') or '').lower()
        except (LookupError, TypeError):
            unit = ''
        kind = _sku_kind(desc, unit, model)
        price = _sku_price(sku, kind) if kind else None
        if kind and price:
            # Google führt denselben Posten in mehreren Stufen und Regionen. Bei
            # mehreren Kandidaten gewinnt der höchste: unter dem Normaltarif zu
            # liegen wäre der gefährliche Irrtum — eine zu niedrige Summe fällt
            # niemandem auf, eine zu hohe schon.
            row = out.setdefault(model, {})
            if price > row.get(kind, 0):
                row[kind] = price
    log.info("Preiskatalog: %d Posten gelesen, %d Modelle zugeordnet",
             len(skus), len(out))
    return ({'prices': out,
             'services': [s.get('displayName', '') for s in matched],
             # Nur bei Fehlschlag mitschicken — sonst ist es unnötiger Ballast
             'samples': ([] if out else
                         sorted({str(x.get('description') or '') for x in skus})[:AI_SKU_SAMPLES]),
             'service_count': len(services), 'sku_count': len(skus)},
            '', '')


@admin_app.route('/api/ai/prices/fetch', methods=['POST'])
def api_ai_prices_fetch():
    err = _api_auth()
    if err:
        return err
    if not _billing_key():
        return jsonify({'error': 'no_billing_key'}), 400
    raw = (request.get_json(silent=True) or {}).get('models')
    models = [m for m in (raw if isinstance(raw, list) else [])[:60]
              if isinstance(m, str) and _AI_MODEL_RE.match(m)]
    if not models:
        return jsonify({'error': 'invalid'}), 400
    result, code, reason = _gemini_fetch_prices(models)
    if code:
        log.info("Preiskatalog abgelehnt (%s): %s", code, reason)
        payload = {'error': code, 'reason': reason}
        if isinstance(result, dict):   # Diagnose auch im Fehlerfall mitgeben
            payload['service_count'] = result.get('service_count', 0)
        return jsonify(payload), 502
    return jsonify({'ok': True, **result})


@admin_app.route('/api/ai/prices', methods=['POST'])
def api_ai_prices():
    err = _api_auth()
    if err:
        return err
    raw = (request.get_json(silent=True) or {}).get('prices')
    if not isinstance(raw, dict):
        return jsonify({'error': 'invalid'}), 400
    clean = {}
    for model, p in list(raw.items())[:60]:
        if not _AI_MODEL_RE.match(str(model)) or not isinstance(p, dict):
            continue
        vals = {}
        for k in ('in', 'out', 'image'):
            try:
                v = round(float(p.get(k) or 0), 6)
            except (TypeError, ValueError):
                v = 0.0
            if v > 0:
                vals[k] = v
        if vals:
            clean[model] = vals
    with _ai_usage_lock:
        data = _ai_usage_load()
        data['prices'] = clean
        try:
            _atomic_write_json(AI_USAGE_PATH, data, indent=2)
        except Exception as e:
            log.warning("KI-Preise konnten nicht gespeichert werden: %s", e)
            return jsonify({'error': 'save_failed'}), 500
    return jsonify({'ok': True})


def _gemini_translate(text: str, src: str, dst: str) -> str:
    """Übersetzt in einem Rutsch — Gemini kommt mit 20 000 Zeichen zurecht.

    Das Zerlegen in 450-Zeichen-Häppchen wie bei MyMemory würde hier schaden:
    ohne den Zusammenhang übersetzt jedes Stück für sich, und Markdown-Blöcke
    zerfielen mitten im Satz. Ausnahmen fliegen bewusst nach oben — der Aufrufer
    fällt dann auf MyMemory zurück.
    """
    names = {'de': 'Deutsch', 'en': 'Englisch'}
    model = _gemini_text_model()
    client = _gemini_client()
    resp = client.models.generate_content(
        model=model, contents=[text],
        config=genai_types.GenerateContentConfig(
            system_instruction=(
                f"Übersetze den Text von {names[src]} nach {names[dst]}. "
                "Antworte ausschließlich mit der Übersetzung — keine Vorrede, keine "
                "Anführungszeichen, keine Erklärung. Markdown, Links, Code-Blöcke, "
                "Zeilenumbrüche und Emojis bleiben unverändert erhalten. "
                "Eigennamen und Produktnamen werden nicht übersetzt."
            ),
            http_options=genai_types.HttpOptions(timeout=GEMINI_TEXT_TIMEOUT_MS),
        ),
    )
    _ai_usage_record(model, resp)
    out = (resp.text or '').strip()
    if not out:
        raise ValueError('empty translation')
    return out


# ── Bibliothek (Admin) ────────────────────────────────────────────────────────

@admin_app.route('/api/library/settings', methods=['POST'])
def api_library_settings():
    err = _api_auth()
    if err:
        return err
    raw = request.get_json(silent=True) or {}
    site = load_site()
    lib = _library(site)
    lib['label_de'] = _clean_str(raw.get('label_de'), 60)
    lib['label_en'] = _clean_str(raw.get('label_en'), 60)
    lib['intro_de'] = _clean_str(raw.get('intro_de'), 2000)
    lib['intro_en'] = _clean_str(raw.get('intro_en'), 2000)
    lib['nav'] = bool(raw.get('nav', True))
    save_site(site)
    return jsonify({'ok': True})


@admin_app.route('/api/library/categories', methods=['POST'])
def api_library_cat_create():
    err = _api_auth()
    if err:
        return err
    raw = request.get_json(silent=True) or {}
    if not (_clean_str(raw.get('name_de'), 60) or _clean_str(raw.get('name_en'), 60)):
        return jsonify({'error': 'name required'}), 400
    site = load_site()
    lib = _library(site)
    if len(lib['categories']) >= 40:
        return jsonify({'error': 'too many'}), 400
    lib['categories'].append(_normalize_lib_cat(raw))
    save_site(site)
    return jsonify({'ok': True})


@admin_app.route('/api/library/categories/<cid>', methods=['PUT', 'DELETE'])
def api_library_cat_edit(cid: str):
    err = _api_auth()
    if err:
        return err
    site = load_site()
    lib = _library(site)
    cats = lib['categories']
    idx = next((i for i, c in enumerate(cats) if c.get('id') == cid), None)
    if idx is None:
        return jsonify({'error': 'not found'}), 404
    if request.method == 'DELETE':
        cats.pop(idx)
        # Einträge nicht mitlöschen — sie rutschen in „ohne Kategorie"
        for e in lib['entries']:
            if e.get('cat') == cid:
                e['cat'] = ''
        save_site(site)
        return jsonify({'ok': True})
    raw = request.get_json(silent=True) or {}
    if not (_clean_str(raw.get('name_de'), 60) or _clean_str(raw.get('name_en'), 60)):
        return jsonify({'error': 'name required'}), 400
    cats[idx] = _normalize_lib_cat(raw, cats[idx])
    save_site(site)
    return jsonify({'ok': True})


@admin_app.route('/api/library/categories/reorder', methods=['POST'])
def api_library_cat_reorder():
    err = _api_auth()
    if err:
        return err
    order = (request.get_json(silent=True) or {}).get('order') or []
    if not isinstance(order, list):
        return jsonify({'error': 'invalid'}), 400
    site = load_site()
    cats = _library(site)['categories']
    pos = {cid: i for i, cid in enumerate(order)}
    cats.sort(key=lambda c: pos.get(c.get('id'), len(pos)))
    save_site(site)
    return jsonify({'ok': True})


def _library_apply_pdf(site: dict, entry: dict) -> str:
    """PDF-Zustand eines Eintrags nach dem Speichern herstellen.

    Gibt einen Statuscode für die Oberfläche zurück: '' (nichts zu tun),
    'generated' (frisch erzeugt) oder 'unavailable' (WeasyPrint fehlt).
    """
    mode = entry.get('pdf_mode')
    if mode == 'generated':
        try:
            if _library_pdf_build(site, entry):
                return 'generated'
        except Exception as e:
            log.warning("PDF-Erzeugung für Bibliothek-Eintrag '%s' fehlgeschlagen: %s",
                        entry.get('slug'), e)
            return 'error'
        return 'unavailable'
    if mode == 'upload':
        _library_pdf_drop(entry, keep=entry.get('pdf') or '')
        entry['pdf_gen'], entry['pdf_hash'] = '', ''
    else:
        _library_pdf_drop(entry)
        entry['pdf'], entry['pdf_gen'], entry['pdf_hash'] = '', '', ''
    return ''


@admin_app.route('/api/library/entries', methods=['POST'])
def api_library_entry_create():
    err = _api_auth()
    if err:
        return err
    raw = request.get_json(silent=True) or {}
    if not (_clean_str(raw.get('title_de'), 140) or _clean_str(raw.get('title_en'), 140)):
        return jsonify({'error': 'title required'}), 400
    site = load_site()
    lib = _library(site)
    entry = _normalize_lib_entry(site, raw)
    entry['slug'] = _lib_entry_slug(site, raw, entry['id'])
    lib['entries'].append(entry)
    pdf_state = _library_apply_pdf(site, entry)
    save_site(site)
    return jsonify({'ok': True, 'slug': entry['slug'], 'pdf': pdf_state})


@admin_app.route('/api/library/entries/<eid>', methods=['PUT', 'DELETE'])
def api_library_entry_edit(eid: str):
    err = _api_auth()
    if err:
        return err
    site = load_site()
    lib = _library(site)
    entries = lib['entries']
    idx = next((i for i, e in enumerate(entries) if e.get('id') == eid), None)
    if idx is None:
        return jsonify({'error': 'not found'}), 404
    if request.method == 'DELETE':
        _library_pdf_drop(entries[idx])
        entries.pop(idx)
        save_site(site)
        return jsonify({'ok': True})
    raw = request.get_json(silent=True) or {}
    if not (_clean_str(raw.get('title_de'), 140) or _clean_str(raw.get('title_en'), 140)):
        return jsonify({'error': 'title required'}), 400
    entries[idx] = _normalize_lib_entry(site, raw, entries[idx])
    entries[idx]['slug'] = _lib_entry_slug(site, raw, eid)
    pdf_state = _library_apply_pdf(site, entries[idx])
    save_site(site)
    return jsonify({'ok': True, 'slug': entries[idx]['slug'], 'pdf': pdf_state})


@admin_app.route('/api/library/entries/<eid>/copy', methods=['POST'])
def api_library_entry_copy(eid: str):
    """Eintrag duplizieren — Kopie landet direkt hinter dem Original, als Entwurf.

    Entwurf, weil eine Kopie fast immer noch überarbeitet wird: sie hätte sonst
    denselben Text sofort ein zweites Mal öffentlich (und in der Sitemap).
    """
    err = _api_auth()
    if err:
        return err
    site = load_site()
    lib = _library(site)
    entries = lib['entries']
    idx = next((i for i, e in enumerate(entries) if e.get('id') == eid), None)
    if idx is None:
        return jsonify({'error': 'not found'}), 404
    src = entries[idx]
    copy = json.loads(json.dumps(src))
    copy['id'] = uuid.uuid4().hex[:12]
    copy['visible'] = False
    # Suffix je Titelsprache — sonst stünde am englischen Titel „(Kopie)"
    for lang, key in (('de', 'title_de'), ('en', 'title_en')):
        if copy.get(key):
            suffix = load_translations(lang).get('library_copy_suffix') or '(Kopie)'
            copy[key] = _clean_str(f'{copy[key]} {suffix}', 140)
    copy['pdf'], copy['pdf_gen'], copy['pdf_hash'] = '', '', ''
    copy['slug'] = _lib_entry_slug(site, {'slug': src.get('slug', '')}, copy['id'])
    copy['updated'] = date.today().isoformat()
    entries.insert(idx + 1, copy)
    # Ein hochgeladenes PDF bekommt eine eigene Datei — teilten sich Original und
    # Kopie eine, würde das Löschen des einen dem anderen die Datei wegnehmen.
    if copy.get('pdf_mode') == 'upload' and _DOC_FILE_RE.match(src.get('pdf') or ''):
        source = safe_under(DOCS_DIR, src['pdf'])
        name = uuid.uuid4().hex + '.pdf'
        target = safe_under(DOCS_DIR, name)
        if source is not None and source.is_file() and target is not None:
            shutil.copyfile(source, target)
            copy['pdf'] = name
    pdf_state = _library_apply_pdf(site, copy)
    save_site(site)
    return jsonify({'ok': True, 'id': copy['id'], 'slug': copy['slug'], 'pdf': pdf_state})


@admin_app.route('/api/library/entries/reorder', methods=['POST'])
def api_library_entry_reorder():
    err = _api_auth()
    if err:
        return err
    order = (request.get_json(silent=True) or {}).get('order') or []
    if not isinstance(order, list):
        return jsonify({'error': 'invalid'}), 400
    site = load_site()
    entries = _library(site)['entries']
    pos = {eid: i for i, eid in enumerate(order)}
    entries.sort(key=lambda e: pos.get(e.get('id'), len(pos)))
    save_site(site)
    return jsonify({'ok': True})


@admin_app.route('/api/library/upload-doc', methods=['POST'])
def api_library_upload_doc():
    """PDF-Upload für einen Bibliothek-Eintrag (getrennt von /api/upload für Bilder)."""
    err = _api_auth()
    if err:
        return err
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'error': 'no file'}), 400
    if Path(f.filename).suffix.lower() not in ALLOWED_DOC_EXT:
        return jsonify({'error': 'file type not allowed'}), 400
    name = uuid.uuid4().hex + '.pdf'
    target = safe_under(DOCS_DIR, name)
    if target is None:
        abort(400)
    f.save(target)
    if target.stat().st_size > DOC_MAX_BYTES:
        target.unlink(missing_ok=True)
        return jsonify({'error': 'too large'}), 413
    # Inhalt prüfen, nicht nur die Endung — ein umbenanntes HTML soll nicht als
    # „PDF" im Download landen.
    with open(target, 'rb') as fh:
        if fh.read(5) != b'%PDF-':
            target.unlink(missing_ok=True)
            return jsonify({'error': 'not a pdf'}), 400
    return jsonify({'ok': True, 'name': name, 'size': target.stat().st_size})


@admin_app.route('/api/library/pdf-support')
def api_library_pdf_support():
    err = _api_auth()
    if err:
        return err
    return jsonify({'available': _HAS_WEASY})


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


@admin_app.route('/api/redirects', methods=['POST'])
def api_redirects():
    err = _api_auth()
    if err:
        return err
    items = (request.get_json(silent=True) or {}).get('redirects')
    if not isinstance(items, list):
        return jsonify({'error': 'invalid'}), 400
    seen, out = set(), []
    for r in items[:200]:
        if not isinstance(r, dict):
            continue
        nr = _normalize_redirect(r)
        if not nr['from'] or nr['from'] == '/' or not nr['to'] or nr['from'] in seen:
            continue
        seen.add(nr['from'])
        out.append(nr)
    site = load_site()
    site['redirects'] = out
    save_site(site)
    log_audit('settings_redirects', f'{len(out)} Regel(n)')
    return jsonify({'ok': True, 'count': len(out)})


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
                    'dm_enabled': u.get('dm_enabled', True),
                    'self_registered': bool(u.get('self_registered')),
                    'verified': u.get('verified', True),
                    'approved': u.get('approved', True),
                    'lang': _member_lang(u),
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
    lang = raw.get('lang') if raw.get('lang') in ('de', 'en') else 'de'
    user = {'id': uuid.uuid4().hex[:12], 'email': email,
            'pw_hash': generate_password_hash(password),
            'quota_mb': quota, 'lang': lang, 'created': date.today().isoformat()}
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
    if 'dm_enabled' in raw:
        user['dm_enabled'] = bool(raw['dm_enabled'])
        log_audit('user_dm', f"{user['email']}: {'an' if user['dm_enabled'] else 'aus'}")
    if 'lang' in raw and raw['lang'] in ('de', 'en'):
        user['lang'] = raw['lang']
        log_audit('user_lang', f"{user['email']} → {user['lang'].upper()}")
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
            pw_subject = load_translations(_member_lang(user))['mail_pw_subject']
            threading.Thread(target=send_welcome_email,
                             args=(user, password, pw_subject),
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


_ADMIN_GAMES = ('66', '20ab', 'schwimmen', 'maumau', 'praesident', 'jeopardy', 'gluecksrad', 'kniffel', 'chicago')


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
    lib_entries = _lib_public_entries(site)
    if lib_entries:
        pages['bibliothek/index.html'] = '/bibliothek'
        for e in lib_entries:
            pages[f"bibliothek/{e['slug']}/index.html"] = f"/bibliothek/{e['slug']}"
            # PDF unter derselben Adresse wie im Live-Betrieb — der Button im
            # exportierten HTML zeigt damit auf eine echte Datei.
            if _lib_entry_pdf_name(e) and not e.get('members_only'):
                pages[f"bibliothek/{e['slug']}.pdf"] = f"/bibliothek/{e['slug']}.pdf"
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


def _store_upload_image(src, *, max_side: int = 1600, quality: int = 82,
                        ai: bool = False) -> str | None:
    """Bild verkleinern, Metadaten verwerfen und als WebP in UPLOADS_DIR ablegen.

    `src` ist ein Datei-Objekt oder rohe Bilddaten; zurück kommt der erzeugte
    Dateiname (`<uuid>.webp`) oder None, wenn Pillow fehlt.

    Gemeinsam genutzt von `/api/upload` und der KI-Bilderzeugung — beide müssen
    dieselben Zusagen einhalten: höchstens 1600 px, WebP, und ohne EXIF neu
    kodiert, damit kein GPS-Standort mit ins Netz geht. Eine zweite Kopie dieser
    Logik würde über die Zeit auseinanderlaufen und aus der Datenschutzzusage
    einen Zufall machen. Der UUID-Dateiname ist ebenfalls Pflicht: `_unused_uploads`
    erkennt verwaiste Dateien über einen Vorkommen-Scan im JSON-Text.

    Mit `ai=True` bekommt der Dateiname das Suffix `-ai`. Daran — und nur daran —
    erkennt die Bild-Auslieferung später, dass sie „KI generiert" einbrennen muss.
    Der Marker steckt bewusst im Dateinamen statt in site.json: er übersteht
    Backup und Wiederherstellung, gilt auch für ein Bild, das in mehreren
    Einträgen benutzt wird, und die Auslieferroute braucht dafür keinen Zustand.

    Lesefehler werden bewusst durchgereicht — die Aufrufer entscheiden über den
    Rückfall.
    """
    if not _HAS_PIL:
        return None
    img = Image.open(io.BytesIO(src) if isinstance(src, (bytes, bytearray)) else src)
    # EXIF-Orientierung anwenden (sonst erscheinen Handy-Hochkant-Fotos gedreht)
    # und damit zugleich Metadaten verwerfen (GPS/Kamera) — Datenschutz.
    img = ImageOps.exif_transpose(img)
    img.thumbnail((max_side, max_side))
    if img.mode not in ('RGB', 'RGBA'):
        img = img.convert('RGBA' if 'A' in img.getbands() else 'RGB')
    name = uuid.uuid4().hex + (AI_IMAGE_SUFFIX if ai else '') + '.webp'
    target = safe_under(UPLOADS_DIR, name)
    if target is None:
        return None
    # ohne exif=... → das neu kodierte WebP enthält keine Metadaten mehr
    img.save(target, 'WEBP', quality=quality)
    return name


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
    if ext != '.gif':
        try:
            name = _store_upload_image(f.stream)
            if name:
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


UPLOADS_LIST_MAX = 300


@admin_app.route('/api/uploads/list')
def api_uploads_list():
    """Vorhandene Bilder für den Medien-Browser im Admin.

    Neueste zuerst und auf UPLOADS_LIST_MAX begrenzt — bei einigen hundert
    Bildern wäre die Galerie sonst weder ladbar noch überschaubar. `used` sagt,
    ob die Datei irgendwo in site.json steckt; so ist erkennbar, was nur
    herumliegt (etwa ein verworfenes KI-Bild), ohne es gleich zu löschen.
    """
    err = _api_auth()
    if err:
        return err
    blob = json.dumps(load_site(), ensure_ascii=False)
    files = []
    for f in UPLOADS_DIR.iterdir():
        if not f.is_file() or f.suffix.lower() not in ALLOWED_UPLOAD_EXT:
            continue
        try:
            st = f.stat()
        except OSError:
            continue
        if st.st_size <= 0:
            continue    # abgebrochener Upload — gäbe nur eine kaputte Kachel
        files.append({'url': '/uploads/' + f.name, 'size': st.st_size,
                      'mtime': int(st.st_mtime), 'used': f.name in blob})
    files.sort(key=lambda x: x['mtime'], reverse=True)
    return jsonify({'files': files[:UPLOADS_LIST_MAX], 'total': len(files)})


def _unused_in(directory: Path, site: dict):
    """Dateien in `directory`, die nirgends mehr in site.json referenziert sind.

    Dateinamen sind durchweg eindeutige UUIDs, daher ist ein Vorkommen-Scan über
    den JSON-Text sicher und deckt jede Fundstelle ab, ohne die Struktur zu kennen.
    """
    blob = json.dumps(site, ensure_ascii=False)
    orphans, total = [], 0
    for f in directory.iterdir():
        if f.is_file() and f.name not in blob:
            orphans.append(f)
            total += f.stat().st_size
    return orphans, total


def _unused_uploads(site: dict):
    """Hochgeladene Bilder, die nirgends mehr referenziert sind.

    Alle Uploads (Bilder in Seiten/Beiträgen/Projekten/Alben, Avatar, Favicon)
    stehen in site.json als `/uploads/<name>`.
    """
    return _unused_in(UPLOADS_DIR, site)


def _unused_docs(site: dict):
    """PDFs der Bibliothek, zu denen es keinen Eintrag mehr gibt.

    Im Normalbetrieb räumt die Bibliothek selbst auf (neu gerendert, Modus
    gewechselt, Eintrag gelöscht). Übrig bleibt, was daran vorbeigeht: ein
    abgebrochenes Rendern zwischen Schreiben und Eintragen in site.json, oder
    eine Wiederherstellung aus einem Backup mit weniger Einträgen.
    """
    return _unused_in(DOCS_DIR, site)


def _cleanup_dir(orphans, total, audit_tag: str):
    """Waisen löschen und das Ergebnis als JSON-Antwort zurückgeben."""
    removed = 0
    for f in orphans:
        try:
            f.unlink()
            removed += 1
        except OSError as e:
            log.warning("Aufräumen: %s konnte nicht gelöscht werden: %s", f.name, e)
    if removed:
        log_audit(audit_tag, f'{removed} Datei(en)')
    return jsonify({'ok': True, 'removed': removed, 'freed_mb': round(total / 1048576, 1)})


@admin_app.route('/api/uploads/unused')
def api_uploads_unused():
    err = _api_auth()
    if err:
        return err
    orphans, total = _unused_uploads(load_site())
    return jsonify({'count': len(orphans), 'size_mb': round(total / 1048576, 1)})


@admin_app.route('/api/uploads/delete', methods=['POST'])
def api_uploads_delete():
    """Ein einzelnes Bild löschen — für den Fall, dass ein gespeichertes Bild
    doch nicht gefällt. Das Sammel-Aufräumen im Tab System ist dafür zu grob.

    Eingebundene Bilder bleiben tabu: sonst reißt ein Beitrag oder ein
    Bibliothek-Eintrag ein Loch, das erst beim Betrachten auffällt. Geprüft
    wird mit demselben Vorkommen-Scan wie beim Aufräumen.
    """
    err = _api_auth()
    if err:
        return err
    name = Path(_clean_str((request.get_json(silent=True) or {}).get('name'), 120)).name
    if Path(name).suffix.lower() not in ALLOWED_UPLOAD_EXT:
        return jsonify({'error': 'invalid'}), 400
    p = safe_under(UPLOADS_DIR, name)
    if p is None or not p.is_file():
        return jsonify({'error': 'not_found'}), 404
    if name in json.dumps(load_site(), ensure_ascii=False):
        return jsonify({'error': 'in_use'}), 409
    try:
        p.unlink()
    except OSError as e:
        log.warning("Bild '%s' konnte nicht gelöscht werden: %s", name, e)
        return jsonify({'error': 'delete_failed'}), 500
    log_audit('upload_delete', name)
    return jsonify({'ok': True})


@admin_app.route('/api/uploads/cleanup', methods=['POST'])
def api_uploads_cleanup():
    err = _api_auth()
    if err:
        return err
    return _cleanup_dir(*_unused_uploads(load_site()), 'uploads_cleanup')


@admin_app.route('/api/docs/unused')
def api_docs_unused():
    err = _api_auth()
    if err:
        return err
    orphans, total = _unused_docs(load_site())
    return jsonify({'count': len(orphans), 'size_mb': round(total / 1048576, 1)})


@admin_app.route('/api/docs/cleanup', methods=['POST'])
def api_docs_cleanup():
    err = _api_auth()
    if err:
        return err
    return _cleanup_dir(*_unused_docs(load_site()), 'docs_cleanup')


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
    """Öffentliche Auslieferung hochgeladener Dateien.

    KI-erzeugte Bilder bekommen auch hier die Kennzeichnung eingebrannt. Sonst
    wäre der direkte Aufruf dieser Adresse — die in jedem Seitenquelltext steht —
    der einfachste Weg, an eine ungekennzeichnete Fassung zu kommen; das
    Wasserzeichen der Alben ist eine Komfortfunktion, die Kennzeichnung nicht.
    """
    if _is_ai_image(filename):
        return _serve_image_with_overlay(filename, detect_language(request))
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


def _is_ai_image(name: str) -> bool:
    """Ob der Dateiname als KI-erzeugt markiert ist (Suffix `-ai` vor der Endung)."""
    return Path(name).stem.endswith(AI_IMAGE_SUFFIX)


def _image_overlay_text(name: str, site: dict, lang: str) -> str:
    """Text, der in dieses Bild eingebrannt wird — leer heißt: Original ausliefern.

    Zwei voneinander unabhängige Gründe, kombiniert zu einer Zeile:
    das Wasserzeichen (nur bei aktivierter Option „Bilder schützen") und die
    Kennzeichnung KI-erzeugter Bilder. Letztere hängt **nicht** an der Option:
    sie erfüllt die Transparenzpflicht für KI-Inhalte und darf sich deshalb
    nicht versehentlich abschalten lassen.
    """
    parts = []
    if site.get('album_protect'):
        parts.append(effective_watermark())
    if _is_ai_image(name):
        parts.append(load_translations(lang).get('img_ai_label') or 'KI generiert')
    return ' · '.join(p for p in parts if p)


def _serve_image_with_overlay(filename: str, lang: str):
    """Bild ausliefern, bei Bedarf mit eingebranntem Text (Cache in WM_CACHE_DIR)."""
    safe = secure_filename(filename)
    src = safe_under(UPLOADS_DIR, safe)
    if not safe or src is None or not src.is_file():
        abort(404)
    text = _image_overlay_text(safe, load_site(), lang)
    if not text:
        return send_from_directory(UPLOADS_DIR, safe, max_age=86400)
    # Cache-Schlüssel aus Text + Dateiname → geänderter Text erzeugt eine neue
    # Datei, alte Stände werden dadurch nie ausgeliefert
    key = hashlib.sha256((text + '|' + safe).encode()).hexdigest()[:24]
    cached = WM_CACHE_DIR / f'{key}.webp'
    if not cached.is_file():
        data = _render_watermark(src, text)
        if data is None:
            return send_from_directory(UPLOADS_DIR, safe, max_age=86400)
        cached.write_bytes(data)
    return send_file(cached, mimetype='image/webp', max_age=86400)


@public_app.route('/album-img/<path:filename>')
def album_image(filename: str):
    """Album-Bild ausliefern — mit eingebranntem Wasserzeichen, wenn aktiviert.

    Bleibt als eigener Pfad bestehen, obwohl `/img/` dasselbe tut: die Adresse
    steckt in bereits veröffentlichten Seiten und in Suchmaschinen-Indizes.
    """
    return _serve_image_with_overlay(filename, detect_language(request))


@public_app.route('/img/<path:filename>')
def overlay_image(filename: str):
    """Bild mit Wasserzeichen/KI-Kennzeichnung — genutzt von der Bibliothek."""
    return _serve_image_with_overlay(filename, detect_language(request))


def _base_url() -> str:
    site = load_site()
    return (site['design'].get('public_url') or request.url_root.rstrip('/')).rstrip('/')


def _public_url_list(site: dict, base: str) -> list:
    """Alle öffentlich indexierbaren URLs (Startseite, Projekte, Blog, Bibliothek).

    Grundlage für den IndexNow-Ping — was hier fehlt, wird Bing/Yandex nie gemeldet.
    """
    urls = [base + '/']
    urls += [f"{base}/seite/{p['slug']}" for p in site.get('pages', []) if p.get('visible')]
    urls += [f"{base}/p/{p['id']}" for p in site['projects'] if _has_detail(p) and project_visible(p)]
    posts = sorted_posts(site, public_only=True)
    if posts:
        urls.append(base + '/blog')
        urls += [f"{base}/blog/{p['id']}" for p in posts]
    lib_entries = _lib_public_entries(site)
    if lib_entries:
        urls.append(base + '/bibliothek')
        urls += [f"{base}/bibliothek/{e['slug']}" for e in lib_entries]
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
    if game not in ('20ab', 'schwimmen', 'maumau', 'praesident', 'jeopardy', 'gluecksrad', 'kniffel', 'chicago') or not _UID_RE.match(uid or ''):
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
    if game not in ('20ab', 'schwimmen', 'maumau', 'praesident', 'jeopardy', 'gluecksrad', 'kniffel', 'chicago') or not _UID_RE.match(uid or ''):
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


# ── Bestenliste (alle Spiele, alle Mitglieder) ─────────────────────────────────

LB_GAMES = ('66', '20ab', 'schwimmen', 'maumau', 'praesident',
            'jeopardy', 'gluecksrad', 'kniffel', 'chicago')
_LB_GAME_META = {  # Übersetzungs-Schlüssel der Spieltitel + Kachel-Icon
    '66': ('g66_title', '🃏'), '20ab': ('g20_title', '🎴'), 'schwimmen': ('gs_title', '🏊'),
    'maumau': ('gmm_title', '🐱'), 'praesident': ('gp_title', '👑'), 'jeopardy': ('gj_title', '🎯'),
    'gluecksrad': ('ggr_title', '🎡'), 'kniffel': ('gk_title', '🎲'), 'chicago': ('gc_title', '🌆'),
}


def _game_history_any(game: str, uid: str) -> list:
    return load_game66_history(uid) if game == '66' else _ng_history(game, uid)


def _hist_entry_won(game: str, entry: dict) -> bool:
    """Hat der Mensch diese Partie gewonnen? (Glücksrad: Sieger-Index 0 = Mensch)"""
    w = entry.get('winner')
    return w == 0 if game == 'gluecksrad' else w == 'p'


def _leaderboard(users: list) -> dict:
    """Gesamt- und Pro-Spiel-Rangliste aus den Spielverläufen aller Mitglieder.
    Nur Mitglieder mit mindestens einer aufgezeichneten Partie erscheinen."""
    total_rows = []
    per_game = {g: [] for g in LB_GAMES}
    for u in users:
        uid = u.get('id') or ''
        if not _UID_RE.match(uid):
            continue
        name = _member_display_name(u)
        t_games = t_wins = played = 0
        for g in LB_GAMES:
            hist = _game_history_any(g, uid)
            if not hist:
                continue
            wins = sum(1 for e in hist if isinstance(e, dict) and _hist_entry_won(g, e))
            played += 1
            t_games += len(hist)
            t_wins += wins
            per_game[g].append({'uid': uid, 'name': name, 'wins': wins, 'games': len(hist)})
        if t_games:
            total_rows.append({'uid': uid, 'name': name, 'wins': t_wins,
                               'games': t_games, 'played': played})
    def _rank(r):
        return (-r['wins'], -r['games'], r['name'].lower())
    total_rows.sort(key=_rank)
    for g in LB_GAMES:
        per_game[g].sort(key=_rank)
    return {'total': total_rows, 'per_game': per_game}


@public_app.route('/bereich/bestenliste')
def leaderboard_page():
    site = load_site()
    if site['design'].get('maintenance'):
        return _maintenance_page(site, detect_language(request))
    member = _require_member()
    lang = detect_language(request)
    t = load_translations(lang)
    lb = _leaderboard(load_users())
    game_names = {g: t.get(k, g) for g, (k, _) in _LB_GAME_META.items()}
    game_icons = {g: i for g, (_, i) in _LB_GAME_META.items()}
    font_family, font_faces = font_css(site['design'])
    return render_template('leaderboard.html', t=t, lang=lang, site=site, member=member,
                           lb=lb, lb_games=[g for g in LB_GAMES if lb['per_game'][g]],
                           game_names=game_names, game_icons=game_icons,
                           font_family=font_family, font_faces=font_faces,
                           year=datetime.now(timezone.utc).year)


# ── Erfolge/Abzeichen (live aus vorhandenen Daten berechnet, keine Speicherung) ─

def _member_achievements(member: dict, file_count: int) -> list:
    """Abzeichen-Liste fürs Mitglied: (id, icon, verdient, Fortschritt).
    Namen/Beschreibungen kommen aus den Locales (ach_<id>_name/_desc)."""
    uid = member['id']
    total_games = total_wins = played = 0
    for g in LB_GAMES:
        hist = _game_history_any(g, uid)
        if not hist:
            continue
        played += 1
        total_games += len(hist)
        total_wins += sum(1 for e in hist if isinstance(e, dict) and _hist_entry_won(g, e))
    comments_cnt = sum(1 for th in load_comments().values()
                       for c in (th.get('comments') or []) if c.get('uid') == uid)
    dm_sent = sum(1 for m in load_dm() if m.get('frm') == uid)
    years = 0
    try:
        years = (date.today() - date.fromisoformat(member.get('created') or '')).days // 365
    except ValueError:
        pass
    defs = [
        ('first_game',    '🎮', total_games, 1),
        ('games_25',      '🕹️', total_games, 25),
        ('games_100',     '🏟️', total_games, 100),
        ('first_win',     '🏆', total_wins, 1),
        ('wins_10',       '🥇', total_wins, 10),
        ('wins_50',       '👑', total_wins, 50),
        ('allrounder',    '🎲', played, len(LB_GAMES)),
        ('first_comment', '💬', comments_cnt, 1),
        ('comments_10',   '📣', comments_cnt, 10),
        ('first_dm',      '✉️', dm_sent, 1),
        ('first_file',    '📁', file_count, 1),
        ('year_1',        '🎂', years, 1),
    ]
    return [{'id': aid, 'icon': icon, 'earned': cur >= target,
             'cur': min(cur, target), 'target': target}
            for aid, icon, cur, target in defs]


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


# ── Kniffel (Würfelspiel, Mitglieder) ───────────────────────────────────────────
# Spielfeld-Seite. API/Engine folgen in der nächsten Etappe.

@public_app.route('/bereich/kniffel')
def gamekniffel_page():
    site = load_site()
    if site['design'].get('maintenance'):
        return _maintenance_page(site, detect_language(request))
    member = _require_member()
    lang = detect_language(request)
    t = load_translations(lang)
    return render_template('game_kniffel.html', t=t, lang=lang, site=site,
                           member=member, year=datetime.now(timezone.utc).year)


def _clean_kniffel_move(raw: dict) -> dict:
    """Nur whitelisted Felder ins Regelwerk (kein ungeprüfter Client-Input)."""
    act = {'type': str(raw.get('type', ''))[:8]}   # roll | hold | score
    if isinstance(raw.get('held'), list):
        act['held'] = [bool(x) for x in raw['held'][:5]]
    if raw.get('cat') is not None:
        act['cat'] = str(raw.get('cat'))[:16]
    return act


def _record_kniffel_if_over(uid: str, st: dict) -> None:
    if st.get('status') != 'game_over' or st.get('recorded'):
        return
    st['recorded'] = True
    totals = {p: game_kniffel.total_score(st, p) for p in st['players']}
    games = _ng_history('kniffel', uid)
    games.append({
        'ts': int(datetime.now(timezone.utc).timestamp()),
        'winner': st.get('winner', ''),
        'scores': totals,
        'score': totals.get('p', 0),
        'level': st.get('level', 'medium'),
        'opponents': st.get('opponents', 2),
    })
    _ng_history_write('kniffel', uid, games)


@public_app.route('/api/kniffel/state')
def api_kniffel_state():
    member = _require_member()
    st = _ng_load('kniffel', member['id'])
    return jsonify({'state': game_kniffel.public_view(st) if st else None})


@public_app.route('/api/kniffel/new', methods=['POST'])
def api_kniffel_new():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('kniffel', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    level = data.get('level')
    level = level if level in ('easy', 'medium', 'hard') else 'medium'
    opponents = 2 if int(data.get('opponents') or 2) == 2 else 1
    with _game_lock:
        st = game_kniffel.new_game(level, opponents)
        _ng_undo.pop(('kniffel', member['id']), None)
        _ng_save('kniffel', member['id'], st)
    return jsonify({'state': game_kniffel.public_view(st)})


@public_app.route('/api/kniffel/move', methods=['POST'])
def api_kniffel_move():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('kniffel', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    if not data.get('type'):
        abort(400)
    act = _clean_kniffel_move(data)
    with _game_lock:
        st = _ng_load('kniffel', member['id'])
        if st is None:
            abort(409)
        snapshot = copy.deepcopy(st)
        try:
            game_kniffel.apply_action(st, 'p', act)
        except game_kniffel.IllegalMove:
            return jsonify({'state': game_kniffel.public_view(st)})
        if act.get('type') == 'score':
            _ng_undo[('kniffel', member['id'])] = snapshot
        _record_kniffel_if_over(member['id'], st)
        _ng_save('kniffel', member['id'], st)
    return jsonify({'state': game_kniffel.public_view(st)})


@public_app.route('/api/kniffel/ai', methods=['POST'])
def api_kniffel_ai():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('kniffel', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    t = load_translations(detect_language(request))
    names = _ng_names(t, 'gk')
    with _game_lock:
        st = _ng_load('kniffel', member['id'])
        if st is None:
            abort(409)
        event = None
        if st['status'] == 'playing' and st['turn'] != 'p':
            who = st['turn']
            act = game_kniffel.ai_step(st)
            game_kniffel.apply_action(st, who, act)
            event = {'type': act['type'], 'who': who, 'name': names.get(who, '')}
            if act['type'] == 'roll':
                event['dice'] = st['dice'][:]
                event['held'] = st['held'][:]
                event['rolls_left'] = st['rolls_left']
            else:
                event['cat'] = act.get('cat')
                event['value'] = st['sheets'][who].get(act.get('cat'))
        _record_kniffel_if_over(member['id'], st)
        _ng_save('kniffel', member['id'], st)
    return jsonify({'state': game_kniffel.public_view(st), 'event': event})


@public_app.route('/api/kniffel/undo', methods=['POST'])
def api_kniffel_undo():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('kniffel', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    with _game_lock:
        snap = _ng_undo.pop(('kniffel', member['id']), None)
        if snap is None:
            return jsonify({'error': 'no_undo'}), 400
        _ng_save('kniffel', member['id'], snap)
    return jsonify({'state': game_kniffel.public_view(snap)})


@public_app.route('/api/kniffel/rules')
def api_kniffel_rules():
    _require_member()
    return jsonify({'html': _ng_rules_html('kniffel', detect_language(request))})


@public_app.route('/api/kniffel/history')
def api_kniffel_history():
    member = _require_member()
    return jsonify({'games': list(reversed(_ng_history('kniffel', member['id'])))})


@public_app.route('/api/kniffel/history/reset', methods=['POST'])
def api_kniffel_history_reset():
    member = _require_member()
    _ng_history_write('kniffel', member['id'], [])
    return jsonify({'ok': True})


@public_app.route('/api/kniffel/session', methods=['POST'])
def api_kniffel_session():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    return _sess_dispatch('kniffel', member['id'], data)


# ── Chicago / Tschigg (Würfelspiel, Mitglieder) ─────────────────────────────────

@public_app.route('/bereich/chicago')
def gamechicago_page():
    site = load_site()
    if site['design'].get('maintenance'):
        return _maintenance_page(site, detect_language(request))
    member = _require_member()
    lang = detect_language(request)
    t = load_translations(lang)
    return render_template('game_chicago.html', t=t, lang=lang, site=site,
                           member=member, year=datetime.now(timezone.utc).year)


def _clean_chicago_move(raw: dict) -> dict:
    act = {'type': str(raw.get('type', ''))[:10]}    # roll | convert6 | stand
    if isinstance(raw.get('held'), list):
        act['held'] = [bool(x) for x in raw['held'][:3]]
    if raw.get('valuation') is not None:
        act['valuation'] = str(raw.get('valuation'))[:6]   # gross | klein
    if raw.get('direction') is not None:
        act['direction'] = str(raw.get('direction'))[:5]   # hoch | tief
    return act


def _record_chicago_if_over(uid: str, st: dict) -> None:
    if st.get('status') != 'game_over' or st.get('recorded'):
        return
    st['recorded'] = True
    games = _ng_history('chicago', uid)
    games.append({
        'ts': int(datetime.now(timezone.utc).timestamp()),
        'winner': 'p' if st.get('loser') != 'p' else '',   # gewonnen = nicht Verlierer
        'loser': st.get('loser', ''),
        'level': st.get('level', 'medium'),
        'opponents': st.get('opponents', 2),
        'chicago': bool(st.get('human_chicago')),           # per Chicago (drei 1er) gewonnen
    })
    _ng_history_write('chicago', uid, games)


@public_app.route('/api/chicago/state')
def api_chicago_state():
    member = _require_member()
    st = _ng_load('chicago', member['id'])
    return jsonify({'state': game_chicago.public_view(st) if st else None})


@public_app.route('/api/chicago/new', methods=['POST'])
def api_chicago_new():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('chicago', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    level = data.get('level')
    level = level if level in ('easy', 'medium', 'hard') else 'medium'
    humans = max(1, min(3, int(data.get('humans') or 1)))
    ai = max(0, min(3, int(data.get('ai') if data.get('ai') is not None
                           else data.get('opponents', 2))))
    names = data.get('names') if isinstance(data.get('names'), dict) else {}
    with _game_lock:
        st = game_chicago.new_game(level, humans=humans, ai=ai, names=names)
        _ng_save('chicago', member['id'], st)
    return jsonify({'state': game_chicago.public_view(st)})


@public_app.route('/api/chicago/move', methods=['POST'])
def api_chicago_move():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('chicago', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    if not data.get('type'):
        abort(400)
    act = _clean_chicago_move(data)
    with _game_lock:
        st = _ng_load('chicago', member['id'])
        if st is None:
            abort(409)
        # Hotseat: der Zug gilt für den aktuell am Gerät sitzenden MENSCHEN
        cur = st.get('turn')
        humans = st.get('humans', ['p'])
        if cur not in humans:
            return jsonify({'state': game_chicago.public_view(st)})
        try:
            game_chicago.apply_action(st, cur, act)
        except game_chicago.IllegalMove:
            return jsonify({'state': game_chicago.public_view(st)})
        _record_chicago_if_over(member['id'], st)
        _ng_save('chicago', member['id'], st)
    return jsonify({'state': game_chicago.public_view(st)})


@public_app.route('/api/chicago/concede', methods=['POST'])
def api_chicago_concede():
    """Mensch hat per Chicago gewonnen und beendet das Spiel (ohne den KIs zuzusehen)."""
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('chicago', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    with _game_lock:
        st = _ng_load('chicago', member['id'])
        if st is None:
            abort(409)
        if st.get('status') != 'game_over' and game_chicago.human_chicago_won(st):
            game_chicago.end_after_human_chicago(st)
            _record_chicago_if_over(member['id'], st)
            _ng_save('chicago', member['id'], st)
    return jsonify({'state': game_chicago.public_view(st)})


@public_app.route('/api/chicago/names', methods=['POST'])
def api_chicago_names():
    """Namen menschlicher Spieler jederzeit ändern."""
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('chicago', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    names = data.get('names') if isinstance(data.get('names'), dict) else {}
    with _game_lock:
        st = _ng_load('chicago', member['id'])
        if st is None:
            abort(409)
        game_chicago.set_names(st, names)
        _ng_save('chicago', member['id'], st)
    return jsonify({'state': game_chicago.public_view(st)})


@public_app.route('/api/chicago/ai', methods=['POST'])
def api_chicago_ai():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    if _sess_locked('chicago', member['id'], data):
        return jsonify({'error': 'session_locked'}), 423
    t = load_translations(detect_language(request))
    names = _ng_names(t, 'gc')
    names['a3'] = t.get('gc_ai3', 'KI 3')
    with _game_lock:
        st = _ng_load('chicago', member['id'])
        if st is None:
            abort(409)
        event = None
        humans = st.get('humans', ['p'])
        if st['status'] in ('opener_roll', 'follower_roll', 'follower_choose') and st['turn'] not in humans:
            who = st['turn']
            act = game_chicago.ai_step(st)
            game_chicago.apply_action(st, who, act)
            event = {'type': act['type'], 'who': who, 'name': names.get(who, who),
                     'dice': st['dice'][:], 'held': st['held'][:],
                     'rolls_used': st['rolls_used'], 'last': st.get('last')}
        _record_chicago_if_over(member['id'], st)
        _ng_save('chicago', member['id'], st)
    return jsonify({'state': game_chicago.public_view(st), 'event': event})


@public_app.route('/api/chicago/rules')
def api_chicago_rules():
    _require_member()
    return jsonify({'html': _ng_rules_html('chicago', detect_language(request))})


@public_app.route('/api/chicago/history')
def api_chicago_history():
    member = _require_member()
    return jsonify({'games': list(reversed(_ng_history('chicago', member['id'])))})


@public_app.route('/api/chicago/history/reset', methods=['POST'])
def api_chicago_history_reset():
    member = _require_member()
    _ng_history_write('chicago', member['id'], [])
    return jsonify({'ok': True})


@public_app.route('/api/chicago/session', methods=['POST'])
def api_chicago_session():
    member = _require_member()
    data = request.get_json(silent=True) or {}
    return _sess_dispatch('chicago', member['id'], data)


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
    lib_entries = _lib_public_entries(site)
    if lib_entries:
        entries.append((base + '/bibliothek', ''))
        entries += [(f"{base}/bibliothek/{e['slug']}",
                     e['updated'] if _valid_date(e.get('updated')) else '')
                    for e in lib_entries]
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
    site = load_site()
    # Eingerichtete Weiterleitung? Greift nur für nicht (mehr) existierende Pfade.
    rd = _find_redirect(site, request.path)
    if rd:
        # rd['to'] stammt aus der gespeicherten Konfiguration (Admin), nicht aus der Anfrage
        return redirect(rd['to'], code=301 if rd.get('permanent', True) else 302)
    lang = detect_language(request)
    t = load_translations(lang)
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
    font_family, font_faces = font_css(site['design'])
    resp = make_response(render_template('maintenance.html', t=t, lang=lang, site=site, loc=loc,
                                         text_html=render_md(text),
                                         font_family=font_family, font_faces=font_faces,
                                         cd=(site.get('sections') or {}).get('countdown') or {},
                                         newsletter_open=newsletter_open(),
                                         nl=_clean_str(request.args.get('nl'), 20)), 503)
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
    # Bibliothek: Anriss als Karussell — es scrollt seitwärts, die Startseite wird
    # also nicht länger. 12 statt 6 Karten, darüber verweist „Alle anzeigen".
    library_entries = _lib_view_entries(site, loc)[:12]
    library_total = len(_lib_public_entries(site))
    # Schlagwörter nur aus den gezeigten Karten — die Filterleiste auf der Startseite
    # arbeitet im Browser über genau diese Kacheln, ein Chip ohne Treffer wäre eine Sackgasse.
    library_tags = _lib_tag_list(library_entries)

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

    cd = sections.get('countdown') or {}
    countdown_title = loc(cd, 'title')
    ft = sections.get('freetext') or {}
    freetext_title = loc(ft, 'title')

    # Umfrage: Ergebnis-Sicht des Besuchers (eigene Stimme über Mitglied/Cookie)
    poll = _active_poll(site) if not static_export else None
    poll_view = None
    if poll:
        votes = load_poll_votes()
        vkey = None
        pm = current_member(request)
        if pm is not None:
            vkey = 'u:' + pm['id']
        else:
            cid = request.cookies.get('pollvid') or ''
            if re.fullmatch(r'[a-f0-9]{32}', cid):
                vkey = 'c:' + cid
        voted = (votes.get('votes') or {}).get(vkey) if votes.get('id') == poll['id'] else None
        if not isinstance(voted, int) or not 0 <= voted < len(poll['options']):
            voted = None
        counts = _poll_counts(poll, votes)
        poll_view = {'question': loc(poll, 'question'),
                     'options': [loc(o, 'label') for o in poll['options']],
                     'counts': counts, 'total': sum(counts), 'voted': voted}

    # Eigenschaften je Abschnitt: (Anker, Übersetzungs-Schlüssel, ob Inhalt vorhanden)
    section_defs = {
        'news':         ('news',         'news_heading',         bool(sections.get('news'))),
        'countdown':    ('countdown',    'countdown_heading',    bool(cd.get('target'))),
        'tips':         ('tips',         'tips_heading_week' if tips_weekly else 'tips_heading', bool(tips)),
        'freetext':     ('freetext',     'freetext_heading',     bool(loc(ft, 'content'))),
        'poll':         ('umfrage',      'poll_heading',         bool(poll_view)),
        'blog':         ('blog',         'blog_heading',         bool(latest_posts)),
        'services':     ('services',     'services_heading',     bool(sections.get('services'))),
        'projects':     ('projects',     'projects',             bool(projects)),
        'skills':       ('skills',       'skills_heading',       bool(sections.get('skills'))),
        'testimonials': ('testimonials', 'testimonials_heading', bool(sections.get('testimonials'))),
        'photos':       ('photos',       'albums_heading',       bool(albums)),
        'library':      ('library',      'library_heading',      bool(library_entries)),
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
    # Frei konfigurierbarer Name der Sammlung (leer = Standard „Bibliothek")
    library_heading = _library_label(site, loc, t)

    # Navigations-Leiste: nur Sektionen mit Inhalt, in gewählter Reihenfolge
    nav_items = []
    if site['design'].get('show_nav', True):
        for key in section_order:
            anchor, label_key, present = section_defs[key]
            # Der Navi-Schalter der Bibliothek gilt auch hier: sonst stünde die
            # Sammlung trotz abgeschaltetem Schalter als Sprungmarke in der Leiste,
            # nur weil der Abschnitt auf der Startseite sichtbar ist.
            if key == 'library' and not _library(site).get('nav'):
                continue
            if present:
                if key == 'timeline' and timeline_title:
                    label = timeline_title
                elif key == 'countdown' and countdown_title:
                    label = countdown_title
                elif key == 'freetext' and freetext_title:
                    label = freetext_title
                elif key == 'library':
                    label = library_heading
                else:
                    label = t.get(label_key, label_key)
                nav_items.append({'anchor': anchor, 'label': label})
        if contact_enabled:
            nav_items.append({'anchor': 'kontakt', 'label': t.get('contact_heading', 'contact_heading')})
        # Eigene Seiten und Formulare als echte Links (mit Navi-Schalter) anhängen.
        # Die Bibliothek nur dann als eigenen Link, wenn sie hier NICHT schon als
        # Abschnitt in der Leiste steht — sonst stünde sie doppelt. Ist der Abschnitt
        # ausgeblendet oder auf Mitglieder beschränkt, bleibt der Link der einzige Weg
        # zur Übersicht.
        lib_in_nav = ('library' in section_order and section_defs['library'][2]
                      and _library(site).get('nav'))
        nav_items += _nav_links(site, loc, t, with_library=not lib_in_nav)

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
                           library_entries=library_entries,
                           library_total=library_total,
                           library_tags=library_tags,
                           library_heading=library_heading,
                           countdown_title=countdown_title,
                           newsletter_open=newsletter_open() and not static_export,
                           nl=_clean_str(request.args.get('nl'), 20),
                           nav_items=nav_items,
                           section_order=section_order,
                           timeline_title=timeline_title,
                           tip_of_day=tip_of_day, tips_weekly=tips_weekly,
                           poll_view=poll_view,
                           static_export=static_export,
                           contact_enabled=contact_enabled,
                           total_visitors=total_uniques(stats),
                           has_impressum=bool(loc(legal, 'impressum').strip()),
                           has_privacy=bool(loc(legal, 'privacy').strip()),
                           has_members=bool(load_users()) and not static_export,
                           search_on=bool(site['design'].get('search_enabled')) and not static_export,
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


@public_app.route('/suche')
def site_search_page():
    lang = detect_language(request)
    site = load_site()
    if site['design'].get('maintenance'):
        return _maintenance_page(site, lang)
    if not site['design'].get('search_enabled'):
        abort(404)
    query = _clean_str(request.args.get('q'), 80)
    loc = _loc_factory(lang)
    member = current_member(request)
    results = site_search(site, query, loc, member is not None) if query else []
    count_visit(request)
    t = load_translations(lang)
    kind_labels = {
        'blog':    t.get('search_kind_blog', 'Blog'),
        'project': t.get('search_kind_project', 'Projekt'),
        'page':    t.get('search_kind_page', 'Seite'),
        'library': _library_label(site, loc, t),
    }
    nav_items = _nav_links(site, loc, t) if site['design'].get('show_nav', True) else []
    return render_template('search.html', t=t, lang=lang, site=site, loc=loc,
                           query=query, results=results, kind_labels=kind_labels,
                           nav_items=nav_items,
                           meta_desc=_site_meta(site, loc),
                           year=datetime.now(timezone.utc).year)


@public_app.route('/newsletter/subscribe', methods=['POST'])
def newsletter_subscribe():
    site = load_site()
    # Abo bewusst auch im Wartungsmodus erlauben (Coming-Soon-Countdown „Benachrichtige mich")
    if not newsletter_open():
        abort(403)
    ip = get_client_ip(request)
    back = _safe_next(request.form.get('next') or '/blog')   # zurück zur Herkunftsseite
    # Honeypot + Rate-Limit → immer generische Rückmeldung (keine Enumeration)
    if (request.form.get('website') or '').strip() or newsletter_rate_limited(ip):
        return redirect(f'{back}?nl=sent')
    record_newsletter_attempt(ip)
    email = _clean_str(request.form.get('email'), 150).lower()
    if not _EMAIL_RE.match(email):
        return redirect(f'{back}?nl=invalidmail')
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
    return redirect(f'{back}?nl=sent')


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
    share_on = bool(site['design'].get('share_enabled')) and not locked
    return render_template('post.html', t=t, lang=lang, site=site, loc=loc, p=post,
                           text_html=text_html, locked=locked,
                           read_min=_reading_minutes(full_html),
                           related=([] if locked else _related_posts(site, post, loc)),
                           share_on=share_on, share_url=f"{_base_url()}/blog/{pid}",
                           share_title=loc(post, 'title'),
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


@public_app.route('/api/poll/vote', methods=['POST'])
def api_poll_vote():
    """Stimme zur Startseiten-Umfrage abgeben (Mitglied per Konto, Gast per Cookie).
    Erneutes Abstimmen ändert die eigene Stimme."""
    site = load_site()
    if site['design'].get('maintenance'):
        return jsonify({'error': 'disabled'}), 403
    poll = _active_poll(site)
    if poll is None or 'poll' in (site.get('hidden_sections') or []):
        return jsonify({'error': 'no_poll'}), 404
    member = current_member(request)
    if 'poll' in (site.get('members_sections') or []) and member is None:
        return jsonify({'error': 'auth'}), 403
    try:
        idx = int((request.get_json(silent=True) or {}).get('option'))
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid'}), 400
    if not 0 <= idx < len(poll['options']):
        return jsonify({'error': 'invalid'}), 400
    new_cookie = None
    if member is not None:
        vkey = 'u:' + member['id']
    else:
        cid = request.cookies.get('pollvid') or ''
        if not re.fullmatch(r'[a-f0-9]{32}', cid):
            cid = secrets.token_hex(16)
            new_cookie = cid
        vkey = 'c:' + cid
    votes = load_poll_votes()
    if votes.get('id') != poll['id']:
        votes = {'id': poll['id'], 'votes': {}}
    vmap = votes.setdefault('votes', {})
    if vkey not in vmap and len(vmap) >= POLL_VOTES_MAX:
        return jsonify({'error': 'full'}), 429
    vmap[vkey] = idx
    save_poll_votes(votes)
    counts = _poll_counts(poll, votes)
    resp = jsonify({'ok': True, 'counts': counts, 'total': sum(counts), 'voted': idx})
    if new_cookie:
        resp.set_cookie('pollvid', new_cookie, max_age=365 * 86400,
                        httponly=True, samesite='Lax')
    return resp


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
        return redirect(f"/blog/{post['id']}#comments")
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
                             args=(author['email'], title, name, text, url, _member_lang(author)),
                             daemon=True).start()
    notify_ha_async('💬 MyPage: Neuer Kommentar',
                    f'{name} hat „{title}" kommentiert:\n\n{text[:300]}',
                    notification_id=f'mypage_comment_{pid}')
    log.info("Mitglied '%s' kommentierte Beitrag '%s'", member['email'], pid)
    return redirect(f"/blog/{post['id']}#comments")


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
                           body_html=body_html, nav_items=_nav_links(site, loc, t),
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
                           share_on=bool(site['design'].get('share_enabled')),
                           share_url=f"{_base_url()}/p/{pid}", share_title=proj.get('title', ''),
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
    achievements = _member_achievements(member, len(files)) if member else []
    return render_template('member.html', t=t, lang=lang, site=site, member=member,
                           achievements=achievements,
                           ach_earned=sum(1 for a in achievements if a['earned']),
                           files=files, used=used, quota=quota, msg=msg,
                           storage_down=storage_down, login_msg_html=login_msg_html,
                           can_reset=reset_enabled() if member is None else False,
                           can_register=registration_open() if member is None else False,
                           games_on=bool(member and member.get('games_enabled', True)),
                           dm_feature=bool(member) and dm_feature_on(),
                           dm_unread=_dm_unread(member['id']) if member else 0,
                           dm_recv_on=bool(member) and member.get('dm_enabled', True) is not False,
                           dir_feature=bool(member) and directory_on(),
                           dir_visible=bool(member) and bool(member.get('dir_visible')),
                           has_avatar=bool(member) and _has_avatar(member['id']),
                           member_lang=_member_lang(member) if member else 'de',
                           member_mail=bool(member) and smtp_configured(),
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
                'quota_mb': quota, 'lang': detect_language(request),
                'created': date.today().isoformat(),
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
    if action == 'dm':
        user['dm_enabled'] = request.form.get('dm_enabled') == '1'
        save_users(users)
        log_user_event(user['id'], 'profile_dm',
                       'an' if user['dm_enabled'] else 'aus', get_client_ip(request))
        return redirect('/bereich?msg=profile_saved')
    if action == 'lang':
        lang = request.form.get('lang')
        if lang in ('de', 'en'):
            user['lang'] = lang
            save_users(users)
            log_user_event(user['id'], 'profile_lang', lang.upper(), get_client_ip(request))
        return redirect('/bereich?msg=profile_saved')
    if action == 'directory' and directory_on():
        user['bio'] = _clean_str(request.form.get('bio'), DIRECTORY_BIO_MAX)
        user['dir_visible'] = request.form.get('dir_visible') == '1'
        save_users(users)
        log_user_event(user['id'], 'profile_directory',
                       'sichtbar' if user['dir_visible'] else 'verborgen', get_client_ip(request))
        return redirect('/bereich?msg=profile_saved')
    if action == 'avatar' and directory_on():
        if _save_member_avatar(user['id'], request.files.get('avatar')):
            log_user_event(user['id'], 'profile_avatar', '', get_client_ip(request))
            return redirect('/bereich?msg=profile_saved')
        return redirect('/bereich?msg=avatar_err')
    if action == 'avatar_del':
        _delete_member_avatar(user['id'])
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
    if action == 'delete_account':
        # DSGVO Art. 17 — Konto + alle eigenen Daten unwiderruflich löschen
        if not check_password_hash(user['pw_hash'], request.form.get('current_password') or ''):
            return redirect('/bereich?msg=del_pw_wrong')
        uid, email = user['id'], user['email']
        save_users([u for u in users if u['id'] != uid])
        invalidate_user_sessions(uid)
        shutil.rmtree(user_dir(user), ignore_errors=True)
        _delete_member_avatar(uid)
        log_audit('user_self_delete', email)
        log.info("Mitglied '%s' hat sein Konto selbst gelöscht", email)
        resp = make_response(redirect('/bereich?msg=account_deleted'))
        resp.delete_cookie('usession')
        return resp
    return redirect('/bereich')


@public_app.route('/bereich/export')
def member_export():
    """DSGVO-Datenauskunft (Art. 15/20): ZIP mit allen eigenen Daten."""
    member = current_member(request)
    if member is None:
        abort(403)
    user = next((u for u in load_users() if u['id'] == member['id']), None)
    if user is None:
        abort(403)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        account = {k: user.get(k) for k in
                   ('id', 'email', 'name', 'created', 'lang', 'quota_mb',
                    'dir_visible', 'bio', 'dm_enabled', 'games_enabled')}
        z.writestr('konto.json', json.dumps(account, ensure_ascii=False, indent=2))
        # Eigene Blog-Kommentare
        mine = []
        for pid, data in load_comments().items():
            for c in data.get('comments', []):
                if c.get('uid') == user['id']:
                    mine.append({'beitrag': pid, 'text': c.get('text'), 'ts': c.get('ts'),
                                 'datum': datetime.fromtimestamp(c.get('ts', 0)).isoformat()})
        z.writestr('kommentare.json', json.dumps(mine, ensure_ascii=False, indent=2))
        # Von mir gesendete Nachrichten (entschlüsselt) — empfangene exportiert der Absender
        sent = [{'an': m.get('to'), 'ts': m.get('ts'),
                 'datum': datetime.fromtimestamp(m.get('ts', 0)).isoformat(),
                 'text': _dm_decrypt(m.get('body', ''))}
                for m in load_dm() if m.get('frm') == user['id']]
        z.writestr('gesendete_nachrichten.json', json.dumps(sent, ensure_ascii=False, indent=2))
        # Hochgeladene Dateien
        if storage_available():
            try:
                for f in user_dir(user).iterdir():
                    if f.is_file():
                        z.write(f, f'dateien/{f.name}')
            except OSError as e:
                log.warning("Export: Dateien für '%s' nicht lesbar: %s", user['email'], e)
        av = MEMBER_AVATARS_DIR / f"{user['id']}.jpg"
        if av.exists():
            z.write(av, 'profilbild.jpg')
    buf.seek(0)
    log_user_event(user['id'], 'data_export', '', get_client_ip(request))
    log.info("Mitglied '%s' hat seine Daten exportiert", user['email'])
    return send_file(buf, mimetype='application/zip', as_attachment=True,
                     download_name=f'meine-daten-{date.today().isoformat()}.zip')


@public_app.route('/bereich/avatar/<uid>')
def member_avatar(uid: str):
    if current_member(request) is None:
        abort(403)
    if not _UID_RE.match(uid) or not _has_avatar(uid):
        abort(404)
    return send_from_directory(MEMBER_AVATARS_DIR, f'{uid}.jpg', max_age=300)


@public_app.route('/bereich/verzeichnis')
def member_directory():
    member = current_member(request)
    if member is None:
        abort(403)
    if not directory_on():
        return redirect('/bereich')
    lang = detect_language(request)
    t = load_translations(lang)
    site = load_site()
    return render_template('directory.html', t=t, lang=lang, site=site, member=member,
                           members=_directory_members(), me_id=member['id'],
                           dm_on=dm_feature_on(),
                           year=datetime.now(timezone.utc).year)


_dm_send_times: dict[str, float] = {}  # einfache Spam-Bremse je Mitglied


def _dm_render(member, view, **extra):
    lang = detect_language(request)
    t = load_translations(lang)
    site = load_site()
    return render_template('dm.html', view=view, t=t, lang=lang, site=site,
                           member=member, me_name=_member_display_name(member),
                           dm_on=member.get('dm_enabled', True) is not False,
                           year=datetime.now(timezone.utc).year, **extra)


@public_app.route('/bereich/nachrichten')
def dm_inbox():
    member = current_member(request)
    if member is None:
        abort(403)
    if not dm_feature_on():
        return redirect('/bereich')
    return _dm_render(member, 'inbox',
                      conversations=_dm_conversations(member['id']),
                      recipients=_dm_recipients(member['id']),
                      msg=request.args.get('msg', ''))


@public_app.route('/bereich/nachrichten/<uid>')
def dm_thread(uid: str):
    member = current_member(request)
    if member is None:
        abort(403)
    is_admin = uid == ADMIN_DM_ID
    if not dm_feature_on() or uid == member['id'] or (not is_admin and not _UID_RE.match(uid)):
        return redirect('/bereich/nachrichten')
    partner = None if is_admin else next((u for u in load_users() if u['id'] == uid), None)
    thread = _dm_thread(member['id'], uid)
    # Ohne Verlauf nur öffnen, wenn ein echtes (anschreibbares) Mitglied dahinter steht
    if not thread and (is_admin or partner is None):
        return redirect('/bereich/nachrichten')
    can_reply = (not is_admin) and partner is not None and _dm_can_receive(partner)
    pname = _admin_dm_name() if is_admin else (_member_display_name(partner) if partner else '—')
    return _dm_render(member, 'thread',
                      partner={'id': uid, 'name': pname,
                               'gone': (not is_admin) and partner is None,
                               'admin': is_admin},
                      thread=thread, can_reply=can_reply,
                      msg=request.args.get('msg', ''))


@public_app.route('/bereich/nachrichten/send', methods=['POST'])
def dm_send():
    member = current_member(request)
    if member is None:
        abort(403)
    if not dm_feature_on():
        return redirect('/bereich')
    to = (request.form.get('to') or '').strip()
    text = (request.form.get('text') or '').strip()
    if not _UID_RE.match(to) or to == member['id']:
        return redirect('/bereich/nachrichten?msg=dm_err')
    target = next((u for u in load_users() if u['id'] == to), None)
    if target is None or not _dm_can_receive(target):
        return redirect('/bereich/nachrichten?msg=dm_off')
    text = text[:DM_MAX_LEN]
    # optionaler Datei-Anhang (verschlüsselt abgelegt)
    fup = request.files.get('file')
    att = None
    if fup and fup.filename:
        att = _dm_att_store(fup)
        if att is None:
            return redirect(_safe_next(f'/bereich/nachrichten/{to}?msg=dm_att_err'))
    if not text and att is None:
        return redirect(_safe_next(f'/bereich/nachrichten/{to}'))
    now = time.time()
    if now - _dm_send_times.get(member['id'], 0) < 1.5:  # Spam-Bremse
        if att and att.get('fid'):
            _dm_att_delete(att['fid'])
        return redirect(_safe_next(f'/bereich/nachrichten/{to}?msg=dm_slow'))
    _dm_send_times[member['id']] = now
    _dm_send(member['id'], to, text, att)
    _dm_owner_notify(to)
    log_user_event(member['id'], 'dm_send', to, get_client_ip(request))
    return redirect(_safe_next(f'/bereich/nachrichten/{to}?msg=dm_sent'))


@public_app.route('/bereich/nachrichten/datei/<mid>')
def dm_attachment(mid: str):
    member = current_member(request)
    if member is None:
        abort(403)
    if not dm_feature_on():
        abort(403)
    me = member['id']
    msg = next((m for m in load_dm() if m.get('id') == mid), None)
    # nur Teilnehmer der Nachricht, die sie nicht für sich gelöscht haben
    if (msg is None or me not in (msg.get('frm'), msg.get('to'))
            or _dm_hidden(msg, me) or not msg.get('att')):
        abort(404)
    data = _dm_att_read(msg['att'].get('fid', ''))
    if data is None:
        abort(404)
    resp = make_response(data)
    resp.headers['Content-Type'] = 'application/octet-stream'  # nie inline ausführen
    resp.headers['Content-Disposition'] = (
        'attachment; filename="' + secure_filename(msg['att'].get('name') or 'datei') + '"')
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    return resp


@public_app.route('/bereich/nachrichten/del', methods=['POST'])
def dm_delete():
    member = current_member(request)
    if member is None:
        abort(403)
    if not dm_feature_on():
        return redirect('/bereich')
    me = member['id']
    mid = (request.form.get('mid') or '').strip()
    convo = (request.form.get('convo') or '').strip()
    if convo != ADMIN_DM_ID and not _UID_RE.match(convo):
        convo = ''
    if mid:
        _dm_delete_for(me, mid=mid[:32])
        dest = f'/bereich/nachrichten/{convo}' if convo else '/bereich/nachrichten'
    elif convo:
        _dm_delete_for(me, partner_id=convo)
        dest = '/bereich/nachrichten'
    else:
        return redirect('/bereich/nachrichten')
    log_user_event(me, 'dm_delete', convo or mid, get_client_ip(request))
    return redirect(_safe_next(f'{dest}?msg=dm_deleted'))


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
                           nav_items=_nav_links(site, loc, t),
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
    nav_items = _nav_links(site, loc, t) if site['design'].get('show_nav', True) else []
    font_family, font_faces = font_css(site['design'])
    return render_template('page.html', t=t, lang=lang, site=site, loc=loc,
                           title=title, body_html=body_html, nav_items=nav_items,
                           page_slug=slug, locked=locked,
                           members_only=bool(page.get('members_only')),
                           font_family=font_family, font_faces=font_faces,
                           meta_desc=(loc(page, 'meta') or _plain_excerpt(body_html)
                                      or _site_meta(site, loc)),
                           year=datetime.now(timezone.utc).year)


# ── Bibliothek (öffentlich) ───────────────────────────────────────────────────

def _lib_view_entries(site: dict, loc, cat: str = '', query: str = '', tag: str = '') -> list:
    """Sichtbare Einträge als Anzeige-Objekte, optional nach Kategorie/Schlagwort/Suche gefiltert."""
    cats = {c['id']: c for c in _library(site).get('categories', []) if c.get('id')}
    words = [w for w in (query or '').lower().split() if w]
    want_tag = (tag or '').lower()
    out = []
    for e in _lib_public_entries(site):
        if cat and e.get('cat') != cat:
            continue
        if want_tag and want_tag not in {str(x).lower() for x in (e.get('tags') or [])}:
            continue
        if words:
            hay = ' '.join([loc(e, 'title'), loc(e, 'summary'), loc(e, 'body'),
                            ' '.join(e.get('tags') or [])]).lower()
            if not all(w in hay for w in words):
                continue
        c = cats.get(e.get('cat'))
        out.append({
            'slug': e.get('slug', ''),
            'title': loc(e, 'title'),
            'summary': loc(e, 'summary') or _plain_excerpt(render_md(loc(e, 'body'))),
            'image': _overlay_url(e.get('image') or ''),
            'tags': e.get('tags') or [],
            'updated': e.get('updated') or '',
            'cat_name': (loc(c, 'name') if c else ''),
            'cat_icon': (c.get('icon') if c else ''),
            'has_pdf': bool(_lib_entry_pdf_name(e)),
            'members_only': bool(e.get('members_only')),
        })
    return out


def _lib_used_categories(site: dict, loc) -> list:
    """Kategorien, die mindestens einen sichtbaren Eintrag haben (für die Filterleiste)."""
    used = {e.get('cat') for e in _lib_public_entries(site)}
    return [{'id': c['id'], 'name': loc(c, 'name'), 'icon': c.get('icon') or ''}
            for c in _library(site).get('categories', [])
            if c.get('id') in used and loc(c, 'name')]


def _lib_tag_list(entries: list) -> list:
    """Schlagwörter der übergebenen Einträge, alphabetisch, ohne Dubletten.

    Groß-/Kleinschreibung wird zusammengefasst (»Griechenland« und »griechenland«
    sind ein Chip), angezeigt wird die erste vorkommende Schreibweise.
    """
    seen = {}
    for e in entries:
        for tag in (e.get('tags') or []):
            key = str(tag).lower()
            if key and key not in seen:
                seen[key] = str(tag)
    return [seen[k] for k in sorted(seen)]


def _lib_used_tags(site: dict) -> list:
    """Schlagwörter aller öffentlich sichtbaren Einträge."""
    return _lib_tag_list(_lib_public_entries(site))


def _lib_filter_url(cat: str = '', tag: str = '', query: str = '') -> str:
    """/bibliothek-Adresse mit den gesetzten Filtern (leere werden weggelassen)."""
    parts = [(k, v) for k, v in (('cat', cat), ('tag', tag), ('q', query)) if v]
    return '/bibliothek' + ('?' + urlencode(parts) if parts else '')


@public_app.route('/bibliothek')
def library_index():
    lang = detect_language(request)
    site = load_site()
    if site['design'].get('maintenance'):
        return _maintenance_page(site, lang)
    if not _lib_public_entries(site):
        abort(404)
    t = load_translations(lang)
    loc = _loc_factory(lang)
    cat = _clean_str(request.args.get('cat'), 32)
    tag = _clean_str(request.args.get('tag'), 30)
    query = _clean_str(request.args.get('q'), 80)
    count_visit(request)
    intro = loc(_library(site), 'intro')
    # Filter-Chips als fertige Adressen — jeder Chip behält die übrigen Filter bei,
    # ein erneuter Klick auf den aktiven Chip hebt ihn auf.
    cat_chips = [{'label': (f"{c['icon']} {c['name']}".strip()), 'active': c['id'] == cat,
                  'href': _lib_filter_url('' if c['id'] == cat else c['id'], tag, query)}
                 for c in _lib_used_categories(site, loc)]
    tag_chips = [{'label': x, 'active': x.lower() == tag.lower(),
                  'href': _lib_filter_url(cat, '' if x.lower() == tag.lower() else x, query)}
                 for x in _lib_used_tags(site)]
    return render_template('library.html', t=t, lang=lang, site=site, loc=loc,
                           heading=_library_label(site, loc, t),
                           intro_html=render_md(intro) if intro else '',
                           entries=_lib_view_entries(site, loc, cat, query, tag),
                           cat_chips=cat_chips, tag_chips=tag_chips,
                           all_cats_url=_lib_filter_url('', tag, query),
                           all_tags_url=_lib_filter_url(cat, '', query),
                           active_cat=cat, active_tag=tag, query=query,
                           nav_items=(_nav_links(site, loc, t, with_library=False)
                                      if site['design'].get('show_nav', True) else []),
                           meta_desc=(_plain_excerpt(render_md(intro)) if intro
                                      else _site_meta(site, loc)),
                           year=datetime.now(timezone.utc).year)


def _render_library_entry(site: dict, entry: dict, lang: str, preview: bool = False):
    t = load_translations(lang)
    loc = _loc_factory(lang)
    cat = next((c for c in _library(site).get('categories', [])
                if c.get('id') == entry.get('cat')), None)
    full_html = _overlay_html_images(render_md(loc(entry, 'body')))
    locked = bool(entry.get('members_only')) and not preview and not is_member(request)
    body_html = ('<p>' + _locked_teaser(full_html) + '</p>') if locked else full_html
    return render_template(
        'library_entry.html', t=t, lang=lang, site=site, loc=loc, e=entry,
        hero_img=_overlay_url(entry.get('image') or ''),
        heading=_library_label(site, loc, t),
        title=loc(entry, 'title') or t.get('library_untitled', ''),
        body_html=body_html, locked=locked,
        members_only=bool(entry.get('members_only')),
        cat_name=(loc(cat, 'name') if cat else ''),
        cat_icon=((cat.get('icon') or '') if cat else ''),
        cat_id=(cat.get('id') if cat else ''),
        pdf_ready=bool(_lib_entry_pdf_name(entry)) and not locked,
        nav_items=(_nav_links(site, loc, t, with_library=False)
                   if site['design'].get('show_nav', True) else []),
        # Bewusst `body_html` (bei Mitglieder-Einträgen der Anriss) statt des
        # vollen Textes — sonst stünde der gesperrte Inhalt in der Meta-Description.
        meta_desc=(loc(entry, 'meta') or loc(entry, 'summary')
                   or _plain_excerpt(body_html) or _site_meta(site, loc)),
        year=datetime.now(timezone.utc).year)


@public_app.route('/bibliothek/<slug>')
def library_entry(slug: str):
    lang = detect_language(request)
    site = load_site()
    if site['design'].get('maintenance'):
        return _maintenance_page(site, lang)
    entry = _find_lib_entry(site, slug)
    if entry is None or not entry.get('visible'):
        abort(404)
    count_visit(request)
    return _render_library_entry(site, entry, lang)


@public_app.route('/bibliothek/<slug>.pdf')
def library_entry_pdf(slug: str):
    """PDF eines Eintrags — immer als Datei-Download, nie inline im Browser.

    Die Endung steht bewusst in der Route (statt `/pdf` als Unterpfad): so ist die
    Adresse im statischen Export eine ganz normale Datei, der Link bleibt gleich.
    """
    site = load_site()
    if site['design'].get('maintenance'):
        abort(404)
    entry = _find_lib_entry(site, slug)
    if entry is None or not entry.get('visible'):
        abort(404)
    if entry.get('members_only') and not is_member(request):
        abort(404)
    name = _lib_entry_pdf_name(entry)
    if not _DOC_FILE_RE.match(name or ''):
        abort(404)
    target = safe_under(DOCS_DIR, name)
    if target is None or not target.is_file():
        abort(404)
    loc = _loc_factory(detect_language(request))
    fname = (_slugify(loc(entry, 'title')) or slug) + '.pdf'
    resp = send_file(target, mimetype='application/pdf',
                     as_attachment=True, download_name=fname)
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    return resp


@admin_app.route('/preview/library/<eid>')
def admin_library_preview(eid: str):
    """Eintrags-Vorschau im Admin — rendert auch Entwürfe und gesperrte Einträge."""
    err = _auth_required()
    if err:
        return err
    site = load_site()
    entry = next((e for e in _library(site).get('entries', []) if e.get('id') == eid), None)
    if entry is None:
        abort(404)
    return _render_library_entry(site, entry, detect_language(request), preview=True)


# ── Main ──────────────────────────────────────────────────────────────────────

def _serve(app, port: int, threads: int) -> None:
    """Startet eine App mit Waitress (produktionstauglicher WSGI-Server).

    Der in Flask eingebaute Werkzeug-Server ist ein Entwicklungsserver: er legt pro
    Anfrage einen neuen Thread an (unbegrenzt) und kennt weder Verbindungslimit noch
    Timeout für hängende Verbindungen. Waitress arbeitet mit festem Thread-Pool und
    Warteschlange, puffert Anfragen/Antworten und begrenzt beides.
    """
    opts = {}
    # An MAX_CONTENT_LENGTH koppeln, sonst würde Waitress große Uploads schon abweisen,
    # bevor Flask sein eigenes (konfigurierbares) Limit prüft. Nur setzen wenn bekannt —
    # Waitress lehnt None ab (TypeError) und hat sonst einen sinnvollen Standard (1 GB).
    limit = int(app.config.get('MAX_CONTENT_LENGTH') or 0)
    if limit > 0:
        opts['max_request_body_size'] = limit
    serve(app, host='0.0.0.0', port=port, threads=threads,
          ident=None,   # keine Server-Version im Response-Header
          # Waitress entfernt X-Forwarded-*-Kopfzeilen standardmäßig, bevor die
          # Anwendung sie sieht (clear_untrusted_proxy_headers=True). Dadurch kam
          # seit der Umstellung auf Waitress (v0.8.10) hinter Reverse Proxy /
          # Cloudflare Tunnel nur noch die Adresse des letzten Zwischenglieds an —
          # im HA-Setup für alle Besucher dasselbe Docker-Gateway. ProxyFix wertet
          # die Kopfzeilen aus, bekam sie aber nie zu sehen.
          # Damit ist X-Forwarded-For wieder fälschbar (wie vor v0.8.10); die
          # Auswertung nimmt deshalb die erste *öffentliche* Adresse der Kette.
          clear_untrusted_proxy_headers=False,
          **opts)


def _run_public():
    _serve(public_app, PUBLIC_PORT, threads=8)


def _handle_sigterm(signum, frame) -> None:
    """Sauberer Exit bei SIGTERM (HA-Supervisor-Stop/Update) — ohne eigenen Handler
    würde Python den Default-Handler laufen lassen (exit 143), worüber sich der
    Supervisor beschwert ("should trap SIGTERM ... exit with code 0"). Alle
    Hintergrund-Threads sind daemon=True (siehe unten), ein harter os._exit(0)
    ist daher sicher — Schreibzugriffe laufen über `with open(...) as f:`-Blöcke,
    die beim jeweiligen Abschluss bereits geschlossen/geflusht sind."""
    log.info("SIGTERM empfangen, beende sauber…")
    os._exit(0)


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, _handle_sigterm)
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
    threading.Thread(target=_dm_reminder_worker, daemon=True).start()
    threading.Thread(target=_weekly_review_worker, daemon=True).start()
    threading.Thread(target=auto_backup_loop, daemon=True).start()

    log.info("MyPage bereit — öffentlich: %d, Admin: %d", PUBLIC_PORT, ADMIN_PORT)
    _serve(admin_app, ADMIN_PORT, threads=4)
