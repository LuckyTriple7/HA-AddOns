#!/usr/bin/env python3
"""MyPage — Homepage-Baukasten für Home Assistant.

Zwei Server in einem Prozess:
  - Port 17760: öffentliche Homepage (kein Login, Besucherzähler)
  - Port 17761: Admin-Panel (Login + Brute-Force-Schutz, auch via HA Ingress)
"""
import base64
import bisect
import copy
import csv
import errno
import gzip
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
from array import array
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import make_msgid, formatdate
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from datetime import time as dtime
from pathlib import Path
from urllib.parse import urlencode, urlparse, urlsplit, urlunsplit

import markdown as md_lib
from markupsafe import Markup, escape

import pdfimport
import settings as settings_store
import travelblog as tb
import visitexplorer as vx
try:
    from PIL import (Image, ImageChops, ImageDraw, ImageFilter, ImageFont,
                     ImageOps, PngImagePlugin)
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
                   send_file, g, has_request_context, Response)
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

CONFIG_PATH   = _OPTS + '/options.json'   # Home Assistant: Login-Notzugang
# Alle übrigen Einstellungen pflegt der Admin selbst (settings.json + settings.key).
# Der Schlüssel liegt unter Home Assistant bewusst NICHT bei den Daten: /config ist
# dort der über den Samba-Share einsehbare Add-on-Konfigurationsordner, und Schloss
# und Schlüssel nebeneinander wären keine Verschlüsselung. Standalone bleibt er bei
# den Daten — dort ist /data nur containerintern und wäre nach einem Neuaufbau weg.
# Läuft MyPage als Home-Assistant-Add-on? Entscheidet an mehreren Stellen, woher
# der Admin-Login kommt: unter HA aus den Add-on-Optionen, sonst aus
# admin_login.json im Datenordner (gehasht, beim ersten Start erzeugt).
ON_SUPERVISOR = bool(os.environ.get('SUPERVISOR_TOKEN'))
_KEY_DIR = _OPTS if ON_SUPERVISOR else _DATA
settings_store.init(_DATA, _KEY_DIR)
SETTINGS_PATH = settings_store.path()
SETTINGS_KEY_PATH = settings_store.key_path()
SITE_PATH     = _DATA + '/site.json'
STATS_PATH    = _DATA + '/stats.json'
MESSAGES_PATH = _DATA + '/messages.json'
COMMENTS_PATH = _DATA + '/comments.json'
AUDIT_PATH = _DATA + '/audit.json'
SUBSCRIBERS_PATH = _DATA + '/subscribers.json'
SESSIONS_PATH = _DATA + '/sessions.json'
USERS_PATH    = _DATA + '/users.json'
AI_USAGE_PATH = _DATA + '/ai_usage.json'   # Gemini-Verbrauch je Monat und Modell
AI_DRAFTS_PATH = _DATA + '/ai_drafts.json'  # gespeicherte Entwürfe des Text-Studios
AI_PROMPTS_PATH = _DATA + '/ai_prompts.json'  # Prompt-Bibliothek des Bild-Studios
UPLOADS_META_PATH = _DATA + '/uploads_meta.json'  # Alternativtexte je Bilddatei
# Letzte Störung je Bereich, für die Zustandsanzeige im Admin. Bewusst eine
# eigene Datei und NICHT im Backup: Ein zurückgespielter Stand brächte sonst
# Warnungen von vorgestern mit, die längst behoben sind.
HEALTH_PATH = _DATA + '/health.json'
# Die letzten Warnungen und Fehler, damit sie im Admin sichtbar sind. Ebenfalls
# nicht im Backup: ein Protokoll von vorgestern gehört nicht in einen
# wiederhergestellten Stand.
LOGBUF_PATH = _DATA + '/logbuf.json'


class _AdminLogHandler(logging.Handler):
    """Hält die letzten Warnungen und Fehler für die Anzeige im Admin fest.

    Bisher gingen alle Meldungen ausschließlich nach `stdout` und damit ins
    Add-on-Protokoll von Home Assistant — wer dort nicht nachsieht, erfährt von
    einer misslungenen Bildverkleinerung oder einer beschädigten Datei nie.

    Gehalten wird im Speicher; auf die Platte geht der Puffer nur alle paar
    Sekunden, damit ein Schwall gleichartiger Meldungen nicht zum Dauerschreiben
    wird. Wiederholungen derselben Zeile erhöhen einen Zähler, statt den Puffer
    zu füllen — sonst verdrängt eine Meldung im Sekundentakt alles andere.

    Ein Protokoll darf nie etwas auslösen: alles hier ist in `try` gefasst, und
    im Fehlerfall passiert schlicht nichts.
    """

    KEEP = 300
    FLUSH_SECONDS = 5

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.entries: list[dict] = []
        self._lock = threading.Lock()
        self._last_write = 0.0

    def emit(self, record):
        try:
            msg = record.getMessage()[:400]
            with self._lock:
                last = self.entries[-1] if self.entries else None
                if last and last['msg'] == msg and last['level'] == record.levelname:
                    last['n'] += 1
                    last['ts'] = int(record.created)
                else:
                    self.entries.append({'ts': int(record.created),
                                         'level': record.levelname,
                                         'msg': msg, 'n': 1})
                    del self.entries[:-self.KEEP]
                due = time.time() - self._last_write >= self.FLUSH_SECONDS
                if due:
                    self._last_write = time.time()
                    data = list(self.entries)
            if due:
                _atomic_write_json(LOGBUF_PATH, data, indent=0)
        except Exception:
            pass        # ein Protokoll darf nie den Aufrufer mitreissen

    def flush_now(self) -> None:
        """Sofort auf die Platte — beim Beenden und vor dem Ausliefern."""
        try:
            with self._lock:
                data = list(self.entries)
                self._last_write = time.time()
            _atomic_write_json(LOGBUF_PATH, data, indent=0)
        except Exception:
            pass

    def load(self):
        """Beim Start den letzten Stand zurückholen."""
        try:
            with open(LOGBUF_PATH, encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                with self._lock:
                    self.entries = [e for e in data if isinstance(e, dict)][-self.KEEP:]
        except Exception:
            pass

    def snapshot(self) -> list:
        with self._lock:
            return list(self.entries)

    def clear(self) -> None:
        with self._lock:
            self.entries = []
        try:
            _atomic_write_json(LOGBUF_PATH, [], indent=0)
        except Exception:
            pass


admin_log_buffer = _AdminLogHandler()
logging.getLogger().addHandler(admin_log_buffer)
USESSIONS_PATH = _DATA + '/user_sessions.json'
DM_PATH       = _DATA + '/dm.json'          # Mitglieder-Direktnachrichten (Text verschlüsselt)
DMKEY_PATH    = _DATA + '/dm.key'           # Fernet-Schlüssel für die DM-Verschlüsselung
TWOFA_PATH    = _DATA + '/admin_2fa.json'   # TOTP-Secret + Backup-Codes (Admin-2FA)
# Admin-Login ohne Home Assistant: Benutzername + Passwort-Hash. Liegt bewusst
# im gemounteten Datenordner, damit man die Datei bei vergessenem Passwort per
# SSH löschen kann — beim nächsten Start erzeugt MyPage ein neues Passwort und
# schreibt es ins Protokoll. Kommt aus demselben Grund NICHT ins Backup.
ADMIN_LOGIN_PATH = _DATA + '/admin_login.json'
# Grundlage der Vorschau-Links. Wird der Wert erneuert, sind alle bisher
# ausgegebenen Links sofort ungueltig — das ist der Widerruf.
PREVIEW_PATH = _DATA + '/preview.json'
SECRETKEY_PATH = _DATA + '/secret.key'      # Flask SECRET_KEY (signiert das trust2fa-Cookie)
POLLS_PATH    = _DATA + '/polls.json'       # Umfrage-Stimmen (getrennt von site.json)
# Reiseblog getrennt von site.json: eine Zwei-Wochen-Reise mit Erlebnissen,
# Essen und Fotos sind schnell hundert Kilobyte, und site.json wird bei jedem
# Admin-Speichern komplett neu geschrieben und beim Aufräumen komplett
# durchsucht. Getrennt bleibt beides schnell und ein Fehler beim Schreiben
# kostet nicht die ganze Seitenkonfiguration.
TRAVEL_PATH   = _DATA + '/travel.json'
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
# Logo-Werkstatt: je Satz ein Unterordner mit allen erzeugten Größen. Bewusst
# NICHT unter uploads/ — dort wird alles zu WebP mit höchstens 1600 px, und ein
# KI-Bild bekäme über den `-ai`-Marker die Kennzeichnung „KI generiert"
# eingebrannt. Beides macht ein Logo unbrauchbar. Zweiter Grund: der Ordner liegt
# im Add-on-Konfigurationsordner und ist damit direkt über den Share erreichbar —
# \\<host>\addon_configs\XXX_mypage\logos\<name>\icon.png lässt sich ohne Umweg
# ins Add-on-Repository kopieren.
LOGOS_DIR = Path(_DATA) / 'logos'
LOGOS_DIR.mkdir(parents=True, exist_ok=True)
LOGO_SLUG_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,40}$')
LOGO_FILE_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,60}\.(?:png|ico|txt)$')
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


# Netz des Home-Assistant-Supervisors. Aus diesem Netz — und nur daher —
# kommen echte Ingress-Anfragen; der Supervisor selbst sitzt auf 172.30.32.2.
INGRESS_NET_DEFAULT = '172.30.32.0/23'


def _ingress_nets() -> list:
    """Vertrauenswürdige Absendernetze für Ingress.

    Abweichende Aufbauten (HA Supervised in einem eigenen Docker-Netz) lassen
    sich über die Option `ingress_trust_net` nachziehen, ohne dass es eine neue
    Fassung braucht. Ein unbrauchbarer Eintrag wird still übergangen: eine
    vertippte Zeile in den Optionen darf hier nicht dazu führen, dass plötzlich
    jedes Netz als Supervisor gilt.
    """
    nets = [ipaddress.ip_network(INGRESS_NET_DEFAULT)]
    try:
        extra = (load_config().get('ingress_trust_net') or '').strip()
    except Exception:      # noqa: BLE001 — vor dem ersten Laden der Optionen
        extra = ''
    for raw in extra.replace(',', ' ').split():
        try:
            nets.append(ipaddress.ip_network(raw, strict=False))
        except ValueError:
            pass
    return nets


def _ingress_peer(addr: str) -> bool:
    """Kommt die Verbindung tatsächlich vom Supervisor?"""
    try:
        ip = ipaddress.ip_address((addr or '').strip())
    except ValueError:
        return False
    return any(ip in net for net in _ingress_nets())


class _PeerMiddleware:
    """Hält die echte Gegenstelle fest, bevor ProxyFix zugreift.

    ProxyFix ersetzt REMOTE_ADDR durch den letzten Eintrag aus
    X-Forwarded-For — richtig für die Anzeige, unbrauchbar für jede
    Sicherheitsentscheidung, denn die Kette schreibt der Absender. Wer den
    Port direkt erreicht, steht hier unverfälscht.
    """
    def __init__(self, wsgi_app):
        self._app = wsgi_app

    def __call__(self, environ, start_response):
        environ['mypage.peer'] = environ.get('REMOTE_ADDR', '')
        return self._app(environ, start_response)


class _IngressMiddleware:
    """Liest X-Ingress-Path vom HA Supervisor und setzt SCRIPT_NAME,
    damit url_for() hinter dem Ingress-Proxy korrekte URLs erzeugt.

    **Sicherheitskritisch.** Hinter dem Ingress übernimmt Home Assistant die
    Anmeldung, MyPage lässt eine solche Anfrage deshalb ohne eigene Sitzung
    durch (`_is_ingress`). Bis 0.11.28 genügte dafür die Kopfzeile allein — und
    die kann jeder mitschicken, der Port 17761 erreicht. Ein `curl` mit
    `X-Ingress-Path: /x` bekam damit vollen Admin-Zugriff ohne Anmeldung.

    Maßgeblich ist deshalb die **Absenderadresse**, nicht die Kopfzeile: Hier,
    vor ProxyFix, steht in REMOTE_ADDR noch der echte Gegenüber; die
    X-Forwarded-For-Kette wird erst danach ausgewertet und ist damit für diese
    Entscheidung wirkungslos. Passt die Adresse nicht, gilt die Anfrage als
    gewöhnlicher Zugriff auf Port 17761 — dann greift der normale Login. Ein
    Fehlurteil führt also zu „bitte anmelden", nie zu „darf alles".
    """
    def __init__(self, wsgi_app):
        self._app = wsgi_app

    def __call__(self, environ, start_response):
        prefix = environ.get('HTTP_X_INGRESS_PATH', '').rstrip('/')
        trusted = bool(prefix) and _ingress_peer(environ.get('REMOTE_ADDR', ''))
        environ['mypage.ingress'] = trusted
        if trusted:
            environ['SCRIPT_NAME'] = prefix
            path = environ.get('PATH_INFO', '')
            if path.startswith(prefix):
                environ['PATH_INFO'] = path[len(prefix):] or '/'
        elif prefix:
            _log_ingress_reject(environ.get('REMOTE_ADDR', ''))
        return self._app(environ, start_response)


_ingress_warned: dict = {}


def _log_ingress_reject(addr: str) -> None:
    """Abgewiesene Ingress-Kopfzeile melden — je Adresse höchstens stündlich.

    Zwei Fälle sehen gleich aus und beide gehören ins Protokoll: ein Aufbau, in
    dem der Supervisor aus einem anderen Netz kommt (dann fehlt die Option
    `ingress_trust_net`), und jemand, der die Anmeldung umgehen wollte.
    """
    now = time.time()
    if now - _ingress_warned.get(addr, 0) < 3600:
        return
    _ingress_warned[addr] = now
    log.warning("Ingress-Kopfzeile von %s abgewiesen — nicht aus dem "
                "Supervisor-Netz (%s). Bei abweichendem Aufbau die Option "
                "ingress_trust_net setzen.", addr or '?', INGRESS_NET_DEFAULT)


admin_app.wsgi_app  = _PeerMiddleware(
    _IngressMiddleware(ProxyFix(admin_app.wsgi_app, x_for=1, x_proto=1, x_host=1)))
public_app.wsgi_app = _PeerMiddleware(
    ProxyFix(public_app.wsgi_app, x_for=1, x_proto=1, x_host=1))

# ── State ─────────────────────────────────────────────────────────────────────

_config_cache: dict | None = None
_config_mtime: float = 0.0
_merged_cache: dict | None = None
_merged_stamp: tuple | None = None
sessions: dict[str, float] = {}

_site_lock  = threading.Lock()
_stats_lock = threading.Lock()
_msg_lock   = threading.Lock()
_users_lock = threading.Lock()
_comments_lock = threading.Lock()
_audit_lock = threading.Lock()
_dm_lock    = threading.Lock()
_2fa_lock   = threading.Lock()
_admin_login_lock = threading.Lock()
_subs_lock = threading.Lock()
_slot_lock  = threading.Lock()
_game_lock  = threading.Lock()
_polls_lock = threading.Lock()
_travel_lock = threading.Lock()
_ai_drafts_lock = threading.Lock()
_ai_prompts_lock = threading.Lock()
_uploads_meta_lock = threading.Lock()

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
# Zweiter Zähler auf die echte Gegenstelle. Die Sperre oben zählt je gemeldeter
# Besucheradresse; hinter einem Proxy stammt die aus einer Kopfzeile, und wer
# sie pro Versuch weiterdreht, läuft nie in die Sperre. Die Verbindung selbst
# lässt sich nicht weiterdrehen. Die Schwelle liegt höher, weil hinter einem
# Proxy alle Anmeldungen dieselbe Gegenstelle haben: Ein Vertipper des
# Betreibers darf niemanden aussperren, vierzig Versuche in zehn Minuten schon.
_failed_peers: dict[str, list[float]] = defaultdict(list)
_blocked_peers: dict[str, float] = {}
RATE_LIMIT_MAX    = 5
RATE_LIMIT_WINDOW = 10 * 60
RATE_LIMIT_BLOCK  = 15 * 60
RATE_LIMIT_PEER_MAX = 20


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
        # Bis zu zwei Handlungsaufrufe im Kopfbereich. Die Sozial-Knöpfe
        # darunter führen von der Seite weg — hier steht, was der Besucher
        # **auf** der Seite tun soll.
        'cta': [],
    },
    'projects': [],
    'design': {
        'accent': '#58a6ff', 'mode': 'dark', 'layout': 'cards',
        # Kopfbereich: nebeneinander (bisher), zentriert oder mit Bannerbild.
        # `avatar_shape` entscheidet über den Zuschnitt — ein Vereinslogo im
        # Querformat verlor im runden Rahmen links und rechts alles.
        'hero_layout': 'side', 'avatar_shape': 'circle', 'hero_image': '',
        # Wer ist das hier? Bis 0.11.41 stand in den strukturierten Daten immer
        # „Person" — für einen Verein oder ein Restaurant schlicht falsch.
        'entity_type': 'person',
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
        # Sichtbarkeit auf der WEBSITE. Die Reiter im Admin bleiben immer da:
        # sonst liesse sich nichts vorbereiten, bevor der Bereich online geht.
        'travel_enabled': False,
        'forms_enabled': True,
        # Blog, Bibliothek und Projekte waren immer da — deshalb hier AN als
        # Standard. Aus heisst: keine Startseite, keine Navigation, eigene
        # Adressen antworten mit 404, nichts in Sitemap, Feed und Suche. Die
        # Admin-Reiter bleiben stehen, damit man den Bereich vorbereiten kann,
        # bevor er online geht.
        'blog_enabled': True,
        'library_enabled': True,
        'projects_enabled': True,
        # RSS-Feed: Sprache fest wählen statt am Browser des Abrufers hängen zu
        # lassen (siehe _feed_lang). Blog und Reiseblog stehen immer drin,
        # Projekte und Bibliothek nur auf Wunsch — sie ändern sich selten und
        # würden den Feed sonst mit Altbestand fluten.
        # Sprache, die eine Adresse ohne ?lang= und ohne Cookie ausliefert.
        # 'auto' = wie früher nach Accept-Language; siehe detect_language.
        'default_lang': 'de',
        'feed_lang': 'de',
        'feed_projects': False,
        'feed_library': False,
        'registration_enabled': False,
        'registration_quota_mb': 500,
        'newsletter_enabled': False,
        'weekly_review': False,
        'visit_archive': False,
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
        'ai_address': 'sie',
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
        # Frei gewählte Überschrift je Abschnitt: {'<key>': {'de': …, 'en': …}}.
        # Leer heißt „Standardüberschrift aus den Locales" — so heißt „Angebote"
        # beim Restaurant „Speisekarte" und beim Verein „Was wir tun", ohne dass
        # ein Modul umbenannt wird. Löst die alten `timeline_title_*` ab, die
        # `_migrate_section_titles()` beim Laden übernimmt.
        'section_titles': {},
        'news': [],
        'links': [],
        'faq': [],
        'services': [],
        'testimonials': [],
        # Kennzahlen (Zahl + Bezeichnung) und Partnerlogos: zwei wiederkehrende
        # Listen, die sich als Freitext jedes Mal von Hand nachbauen ließen — und
        # dabei jedes Mal anders aussähen.
        'facts': [],
        'partners': [],
        # Videos laufen erst auf Klick (dieselbe Mechanik wie im Beitrag), und
        # Downloads liegen in derselben Ablage wie die Bibliothek-PDFs.
        'videos': [],
        'downloads': [],
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
        'news', 'countdown', 'tips', 'freetext', 'poll', 'blog', 'services', 'projects', 'skills', 'facts',
        'testimonials', 'photos', 'videos', 'library', 'downloads', 'travel', 'forms', 'team',
        'timeline', 'events', 'partners', 'links', 'faq', 'location',
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

# Abschnitte mit eigener Titelzeile im Inhalt: Countdown und Freitext haben
# bereits eigene Titelfelder, eine zweite Überschrift wäre dort eine Falle.
SECTION_TITLE_KEYS = [k for k in SECTION_KEYS if k not in ('countdown', 'freetext')]


def section_title(sections: dict, key: str, lang: str) -> str:
    """Frei gewählte Überschrift eines Abschnitts, leer wenn keine gesetzt ist."""
    entry = ((sections or {}).get('section_titles') or {}).get(key) or {}
    if not isinstance(entry, dict):
        return ''
    if lang == 'en':
        return (entry.get('en') or entry.get('de') or '').strip()
    return (entry.get('de') or entry.get('en') or '').strip()


def _migrate_section_titles(data: dict) -> None:
    """Alte `timeline_title_de/en` in die gemeinsame Ablage übernehmen.

    Nur im Speicher: geschrieben wird es beim nächsten Speichern der Seite. Die
    alten Felder bleiben unangetastet — ginge die Übernahme schief, steht der
    Wert weiterhin dort, statt still zu verschwinden.
    """
    sec = data.get('sections')
    if not isinstance(sec, dict):
        return
    titles = sec.get('section_titles')
    if not isinstance(titles, dict):
        titles = {}
        sec['section_titles'] = titles
    if 'timeline' in titles:
        return
    de = (sec.get('timeline_title_de') or '').strip()
    en = (sec.get('timeline_title_en') or '').strip()
    if de or en:
        titles['timeline'] = {'de': de, 'en': en}


# ── Alternativtexte der Bilder ────────────────────────────────────────────────
#
# Ein Bild ohne Alternativtext ist für Screenreader und Suchmaschinen nicht da.
# Die Texte hängen an der Datei, nicht am Beitrag: dasselbe Bild kann in Beitrag,
# Projekt und Bibliothek stecken und beschreibt dabei immer dasselbe.
#
# WICHTIG: `uploads_meta.json` gehört NICHT in `_reference_blob()`. Sonst gälte
# jede Datei mit Alternativtext als benutzt und „Speicher aufräumen" fände nie
# wieder eine Waise.

# In der Datei stehen zwei getrennte Karten, beide nach Dateiname:
#   `alts`  — Alternativtexte je Sprache
#   `files` — Herkunftsname und Etiketten für die Medienverwaltung
# Wer eine dritte hinzufügt, muss sie in `_uploads_meta_forget()` mit
# aufräumen, sonst bleiben Einträge zu längst gelöschten Dateien liegen.

# ── Zustandsanzeige ───────────────────────────────────────────────────────────
#
# `app.py` schreibt an über hundert Stellen Warnungen ins Log, und niemand liest
# ein Add-on-Log. Ein abgelaufener GitHub-Token, ein stiller Mailversand, ein
# ausgefallenes Backup — alles unsichtbar, bis es jemandem auffällt.
#
# Instrumentiert wird bewusst NICHT jede der Log-Stellen, sondern die Handvoll,
# bei der ein Ausfall dem Betreiber wirklich etwas kostet. Jede meldet über
# `health_note()` ihre letzte Störung; ein Erfolg löscht den Eintrag wieder.

_health_lock = threading.Lock()

HEALTH_KEEP = 20        # mehr Bereiche gibt es nicht


def health_note(key: str, msg: str = '', *, ok: bool = False) -> None:
    """Störung eines Bereichs festhalten — oder mit `ok=True` als behoben löschen.

    Darf nie etwas auslösen: die Aufrufer stecken in Hintergrundschleifen und im
    Mailversand, und eine kaputte Zustandsdatei wäre der schlechteste Grund,
    einen Newsletter scheitern zu lassen.
    """
    try:
        with _health_lock:
            try:
                with open(HEALTH_PATH, encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = {}
            if not isinstance(data, dict):
                data = {}
            if ok:
                if data.pop(key, None) is None:
                    return          # war nichts gemeldet: keine Schreiblast
            else:
                prev = data.get(key) or {}
                data[key] = {'ts': int(time.time()), 'msg': str(msg)[:300],
                             'n': int(prev.get('n', 0)) + 1,
                             'since': prev.get('since') or int(time.time())}
            for k in sorted(data, key=lambda k: (data[k] or {}).get('ts', 0))[:-HEALTH_KEEP]:
                del data[k]
            _atomic_write_json(HEALTH_PATH, data, indent=2)
    except Exception as e:      # niemals den Aufrufer mitreißen
        log.debug("Zustand '%s' konnte nicht festgehalten werden: %s", key, e)


def health_notes() -> dict:
    try:
        with _health_lock:
            with open(HEALTH_PATH, encoding='utf-8') as f:
                data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _uploads_meta_read_locked() -> dict:
    """Ganze Datei — nur aufrufen, wer `_uploads_meta_lock` schon hält."""
    try:
        with open(UPLOADS_META_PATH, encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        _quarantine_corrupt(UPLOADS_META_PATH, e)
        return {}
    return data if isinstance(data, dict) else {}


def _uploads_meta_update(change) -> bool:
    """Lesen, ändern, schreiben — am Stück unter dem Schloss.

    Nur so bleiben die beiden Karten unabhängig voneinander änderbar: wer die
    Datei erst lädt, dann ändert und dann speichert, überschreibt zwischendurch
    Geschriebenes der jeweils anderen Karte.
    """
    with _uploads_meta_lock:
        data = _uploads_meta_read_locked()
        change(data)
        try:
            _atomic_write_json(UPLOADS_META_PATH, data, indent=2)
            return True
        except Exception as e:
            log.error("uploads_meta.json konnte nicht gespeichert werden: %s", e)
            return False


def _uploads_meta_map(key: str) -> dict:
    with _uploads_meta_lock:
        part = _uploads_meta_read_locked().get(key)
    return ({k: v for k, v in part.items() if isinstance(v, dict)}
            if isinstance(part, dict) else {})


def _uploads_meta_load() -> dict:
    """Alternativtexte: Dateiname -> {'de': …, 'en': …}."""
    return _uploads_meta_map('alts')


def _uploads_meta_save(alts: dict) -> bool:
    return _uploads_meta_update(lambda d: d.update({'alts': alts}))


def _uploads_files_load() -> dict:
    """Verwaltungsangaben: Dateiname -> {'orig': …, 'tags': [...]}."""
    return _uploads_meta_map('files')


def _uploads_files_save(files: dict) -> bool:
    return _uploads_meta_update(lambda d: d.update({'files': files}))


UPLOAD_TAG_MAX = 8
UPLOAD_TAGS_LEN = 30


def _upload_tags_clean(raw) -> list:
    """Etiketten säubern: getrimmt, ohne Doppelte, begrenzt in Zahl und Länge."""
    if isinstance(raw, str):
        raw = raw.split(',')
    seen, out = set(), []
    for t in (raw or []):
        t = _clean_str(t, UPLOAD_TAGS_LEN).strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out[:UPLOAD_TAG_MAX]


UPLOAD_FOLDER_LEN = 40


def _upload_folder_clean(raw) -> str:
    """Ordnername säubern — eine Ebene, kein Pfad.

    Der Ordner ist reine Anzeige im Admin; im Dateisystem wandert nichts. Die
    Schrägstriche fliegen trotzdem raus: sie legten eine Verschachtelung nahe,
    die es nicht gibt, und ließen den Namen wie einen Pfad aussehen.
    """
    return _clean_str(str(raw or '').replace('/', ' ').replace('\\', ' '),
                      UPLOAD_FOLDER_LEN).strip()


def _uploads_file_meta_set(name: str, orig: str | None = None,
                           tags: list | None = None,
                           folder: str | None = None) -> bool:
    """Herkunftsname, Etiketten und/oder Ordner einer Datei setzen.

    `None` heißt „unverändert lassen"; eine leere Liste bzw. ein leerer Text
    löscht den jeweiligen Wert. Ein Eintrag ohne Inhalt wird entfernt statt leer
    gespeichert — sonst sammelt die Ablage Karteileichen für jede je angefasste
    Datei.
    """
    def change(data: dict) -> None:
        files = data.get('files')
        if not isinstance(files, dict):
            files = {}
        entry = dict(files.get(name) or {})
        if orig is not None:
            entry['orig'] = _clean_str(orig, 120)
        if tags is not None:
            entry['tags'] = _upload_tags_clean(tags)
        if folder is not None:
            entry['folder'] = _upload_folder_clean(folder)
        entry = {k: v for k, v in entry.items() if v}
        if entry:
            files[name] = entry
        else:
            files.pop(name, None)
        data['files'] = files
    return _uploads_meta_update(change)


def _uploads_meta_forget(names) -> None:
    """Einträge gelöschter Dateien mitnehmen — sonst wächst die Ablage ewig."""
    names = {n for n in names if n}
    if not names:
        return

    def change(data: dict) -> None:
        for key in ('alts', 'files'):
            part = data.get(key)
            if isinstance(part, dict):
                data[key] = {k: v for k, v in part.items() if k not in names}
    _uploads_meta_update(change)


def _req_lang() -> str:
    """Sprache der laufenden Anfrage, leer außerhalb eines Anfragekontexts
    (statischer Export, Hintergrundaufgaben)."""
    try:
        return detect_language(request)
    except Exception:
        return ''


def alt_for(url: str, lang: str = '', fallback: str = '') -> str:
    """Alternativtext zu einer Upload-Adresse.

    Fehlt die gewünschte Sprache, gilt die andere: ein deutscher Text ist für
    einen Screenreader immer noch besser als gar keiner. Erst danach greift der
    Rückfall, den die Vorlage mitgibt (meist der Titel).
    """
    name = (url or '').strip().rsplit('/', 1)[-1]
    entry = _uploads_meta_load().get(name) or {}
    lang = lang or _req_lang() or 'de'
    other = 'en' if lang == 'de' else 'de'
    return (entry.get(lang) or entry.get(other) or fallback or '').strip()


# Markdown erzeugt für `![](…)` ein leeres alt. Genau die werden nachgefüllt —
# ein selbst geschriebener Text bleibt unangetastet.
_IMG_TAG_RE = re.compile(r'<img\b[^>]*>', re.I)
_IMG_SRC_RE = re.compile(r'src="([^"]*)"', re.I)


def _fill_img_alts(html: str, lang: str) -> str:
    if 'alt=""' not in html:
        return html

    def one(m):
        tag = m.group(0)
        src = _IMG_SRC_RE.search(tag)
        if 'alt=""' not in tag or not src:
            return tag
        alt = alt_for(src.group(1), lang)
        return tag.replace('alt=""', 'alt="' + html_mod.escape(alt, quote=True) + '"', 1) if alt else tag

    return _IMG_TAG_RE.sub(one, html)


def render_md(text: str, lang: str = '') -> str:
    """Markdown → HTML (Inhalte stammen ausschließlich vom Admin)."""
    out = md_lib.markdown(text or '', extensions=['nl2br', 'sane_lists', 'tables', 'fenced_code'])
    return _fill_img_alts(out, lang or _req_lang())


# Tags, die `render_md` erzeugen kann. Bewusst eine Liste statt `<[^>]+>`: der
# offene Ausdruck frisst auch spitze Klammern, die als Text gemeint sind — aus
# „Platzhalter <Name> einsetzen" wurde „Platzhalter  einsetzen".
_HTML_TAG_RE = re.compile(
    r'</?(?:p|br|hr|h[1-6]|a|em|strong|b|i|u|s|del|ins|sup|sub|small|mark|code|pre|kbd'
    r'|blockquote|ul|ol|li|dl|dt|dd|img|figure|figcaption|table|thead|tbody|tfoot'
    r'|tr|th|td|caption|span|div|hgroup|section|article)\b[^>]*>', re.I)


def _plain_excerpt(s: str, limit: int = 155) -> str:
    """HTML/Markdown-Text in einen kurzen Klartext-Auszug wandeln.

    `unescape` gehört zwingend dazu: nach dem Entfernen der Tags stehen im Text
    noch die Entities, die der Markdown-Schritt gesetzt hat (`&amp;`). Wer das
    Ergebnis anschließend nochmal maskiert — Jinja in der Meta-Description, der
    Feed beim Zusammenbauen des XML — machte daraus `&amp;amp;`, und im Reader
    stand wörtlich „&amp;". Einmal zurückwandeln, danach einmal maskieren.
    """
    txt = html_mod.unescape(re.sub(r'\s+', ' ', _HTML_TAG_RE.sub(' ', s or '')).strip())
    return re.sub(r'\s+', ' ', txt).strip()[:limit].rstrip()


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
public_app.jinja_env.globals['alt_for'] = alt_for

# Admin-App rendert öffentliche Templates (z. B. Blog-Vorschau) — dieselben Globals bereitstellen
admin_app.jinja_env.globals['alt_for'] = alt_for
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


def load_options() -> dict:
    """Rohe Add-on-Optionen (Home Assistant schreibt sie, Standalone mountet sie)."""
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


def load_config() -> dict:
    """Wirksame Einstellungen: Standardwerte < options.json < settings.json.

    options.json liefert nur noch den Login-Notzugang (username/password/
    session_hours) und – solange nicht migriert – die alten Werte. Alles, was
    der Admin in der Oberfläche pflegt, steht in settings.json und gewinnt.
    """
    global _merged_cache, _merged_stamp
    opts = load_options()
    try:
        s_mtime = os.path.getmtime(SETTINGS_PATH)
    except OSError:
        s_mtime = -1.0
    stamp = (_config_mtime, s_mtime)
    if _merged_cache is None or stamp != _merged_stamp:
        merged = {k: (list(spec[1]) if isinstance(spec[1], list) else spec[1])
                  for k, spec in settings_store.FIELDS.items()}
        merged.update(opts)
        merged.update(settings_store.load())
        _merged_cache, _merged_stamp = merged, stamp
    return _merged_cache


def _settings_changed() -> None:
    """Zusammengeführte Sicht verwerfen — nach Speichern oder Restore."""
    global _merged_cache, _merged_stamp
    _merged_cache, _merged_stamp = None, None


# ── Admin-Login ohne Home Assistant ───────────────────────────────────────────
# Unter Home Assistant stehen Benutzername und Passwort in den Add-on-Optionen —
# daran ändert sich nichts. Ohne Supervisor (Docker, Dockge) gäbe es dafür keine
# Oberfläche, deshalb erzeugt MyPage beim ersten Start selbst ein Passwort,
# schreibt es ins Protokoll und legt nur den Hash ab. Ändern geht danach im
# Admin-Panel; wer es vergisst, löscht admin_login.json und startet neu.

ADMIN_PW_MIN_LEN = 12
# Ohne 0/O und 1/l/I: das Passwort wird aus dem Protokoll abgetippt, und
# verwechselte Zeichen kosten dort mehr als die zwei Bit Entropie.
_PW_UPPER = 'ABCDEFGHJKLMNPQRSTUVWXYZ'
_PW_LOWER = 'abcdefghijkmnopqrstuvwxyz'
_PW_DIGIT = '23456789'
_PW_ALPHABET = _PW_UPPER + _PW_LOWER + _PW_DIGIT
_GEN_PW_LEN = 16


def _gen_admin_password() -> str:
    """Zufälliges Passwort mit garantiert Groß-, Kleinbuchstaben und Ziffern."""
    while True:
        pw = ''.join(secrets.choice(_PW_ALPHABET) for _ in range(_GEN_PW_LEN))
        if (any(c in _PW_UPPER for c in pw) and any(c in _PW_LOWER for c in pw)
                and any(c in _PW_DIGIT for c in pw)):
            return pw


def password_policy_error(pw: str) -> str | None:
    """None = in Ordnung, sonst der Übersetzungsschlüssel des Problems."""
    pw = pw or ''
    if len(pw) < ADMIN_PW_MIN_LEN:
        return 'pw_too_short'
    if not any(c.isupper() for c in pw):
        return 'pw_no_upper'
    if not any(c.islower() for c in pw):
        return 'pw_no_lower'
    if not any(c.isdigit() for c in pw):
        return 'pw_no_digit'
    return None


def load_admin_login() -> dict:
    with _admin_login_lock:
        try:
            with open(ADMIN_LOGIN_PATH, encoding='utf-8') as f:
                d = json.load(f)
                return d if isinstance(d, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception as e:
            # Kaputte Datei beiseitelegen: der nächste Start erzeugt ein neues
            # Passwort, statt dass die Anmeldung dauerhaft klemmt.
            _quarantine_corrupt(ADMIN_LOGIN_PATH, e)
            return {}


def save_admin_login(data: dict) -> None:
    with _admin_login_lock:
        _atomic_write_json(ADMIN_LOGIN_PATH, data, indent=2, mode=0o600)


def ensure_admin_login() -> str | None:
    """Beim Start aufrufen. Liefert das Klartext-Passwort, wenn es neu erzeugt wurde.

    Unter Home Assistant passiert nichts — dort gilt weiterhin options.json.
    """
    if ON_SUPERVISOR:
        return None
    d = load_admin_login()
    if d.get('pw_hash'):
        return None
    # Bestandsinstallationen: wer bisher options.json gemountet hat, soll sich
    # nach dem Update mit demselben Passwort anmelden können. Übernommen wird es
    # gehasht, danach ist die Datei überflüssig.
    opts = load_options()
    old_pw = str(opts.get('password') or '')
    if old_pw and old_pw != 'changeme123':
        save_admin_login({'username': str(opts.get('username') or 'admin'),
                          'pw_hash': generate_password_hash(old_pw),
                          'initial': False, 'created': int(time.time()),
                          'from_options': True})
        log.info("Admin-Zugang aus options.json übernommen und in %s gehasht "
                 "abgelegt — die Datei wird nicht mehr gebraucht", ADMIN_LOGIN_PATH)
        return None
    pw = _gen_admin_password()
    save_admin_login({'username': 'admin', 'pw_hash': generate_password_hash(pw),
                      'initial': True, 'created': int(time.time())})
    return pw


def admin_username() -> str:
    if ON_SUPERVISOR:
        return str(load_config().get('username', 'admin'))
    return str(load_admin_login().get('username') or 'admin')


def admin_password_ok(pwd: str) -> bool:
    """Passwortprüfung für Anmeldung und alle Stellen, die es erneut abfragen."""
    if ON_SUPERVISOR:
        return secrets.compare_digest(str(pwd or ''),
                                      str(load_config().get('password', '')))
    h = str(load_admin_login().get('pw_hash') or '')
    if not h:
        return False
    return check_password_hash(h, str(pwd or ''))


def admin_login_is_initial() -> bool:
    """True, solange noch das erzeugte Startpasswort gilt."""
    return not ON_SUPERVISOR and bool(load_admin_login().get('initial'))


def set_admin_credentials(username: str, password: str) -> None:
    d = load_admin_login()
    d['username'] = username or 'admin'
    d['pw_hash'] = generate_password_hash(password)
    d['initial'] = False
    d['changed'] = int(time.time())
    save_admin_login(d)


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
    _migrate_section_titles(data)
    return data


# ── Versionsstand von site.json (Revisionen) ────────────────────────
# Vor jedem Schreiben wandert der bisherige Stand nach revisions/. Damit ist ein
# versehentlich geleertes Feld oder ein zerschossener Text zurückholbar, ohne
# ein ganzes Backup einzuspielen — die Revision enthält ausschließlich
# site.json, also Seiteninhalte. Mitglieder, Nachrichten, Reiseblog und
# Statistik liegen in eigenen Dateien und bleiben von einer Rückkehr unberührt.
REVISIONS_DIR = Path(_DATA) / 'revisions'
REVISION_KEEP_DEFAULT = 20
_REVISION_RE = re.compile(r'^site-(\d{8}-\d{6})\.json$')
# Ein Admin-Speichern löst je nach Reiter mehrere save_site()-Aufrufe aus, und
# wer länger an einer Seite arbeitet, speichert im Minutentakt. Ohne
# Zusammenfassen bestünde die Liste aus Ständen, die Sekunden auseinander
# liegen, und der brauchbare Stand von gestern wäre längst rausrotiert.
# Gesichert wird immer der Stand VOR der Änderung — der erste Schnappschuss
# einer solchen Serie ist deshalb der richtige.
REVISION_COALESCE = 90        # Sekunden
# Diese Schlüssel ändern sich durch bloßes Besuchen der Seite: der Slot-Jackpot
# zählt bei jedem Dreh hoch, die Tipp-Statistik bei der ersten Anzeige des
# Tages. Eine Revision nur dafür wäre Rauschen und würde echte Änderungen
# aus der Liste drängen.
REVISION_IGNORE = {'slot_jackpot', 'tips_stats'}


def _revision_keep() -> int:
    try:
        return max(0, int(load_config().get('revision_keep', REVISION_KEEP_DEFAULT) or 0))
    except (TypeError, ValueError):
        return REVISION_KEEP_DEFAULT


def _site_changed_keys(old: dict, new: dict) -> list:
    """Geänderte Abschnitte auf oberster Ebene — ohne die flüchtigen Zähler."""
    keys = set(old) | set(new)
    out = [k for k in keys - REVISION_IGNORE
           if json.dumps(old.get(k), sort_keys=True, ensure_ascii=False)
           != json.dumps(new.get(k), sort_keys=True, ensure_ascii=False)]
    return sorted(out)


def list_revisions() -> list:
    """Vorhandene Revisionen, neueste zuerst. Namen tragen den Zeitpunkt."""
    try:
        files = [f for f in REVISIONS_DIR.iterdir()
                 if f.is_file() and _REVISION_RE.match(f.name)]
    except OSError:
        return []
    out = []
    for f in sorted(files, key=lambda x: x.name, reverse=True):
        try:
            out.append({'name': f.name, 'size': f.stat().st_size, 'ts': f.name[5:20]})
        except OSError:
            continue
    return out


def _rotate_revisions(keep: int) -> None:
    for old in list_revisions()[keep:]:
        try:
            (REVISIONS_DIR / old['name']).unlink()
        except OSError as e:
            log.warning("Alte Revision %s konnte nicht entfernt werden: %s", old['name'], e)


def _snapshot_site(new_data: dict | None = None, *, force: bool = False) -> None:
    """Aktuellen Stand von site.json nach revisions/ sichern.

    Wird aus save_site() heraus aufgerufen und läuft dort bereits unter
    `_site_lock`. Fehler bleiben folgenlos: eine fehlende Revision darf das
    Speichern selbst niemals verhindern.
    """
    keep = _revision_keep()
    if keep <= 0:
        return
    try:
        with open(SITE_PATH, encoding='utf-8') as f:
            raw = f.read()
    except OSError:
        return                     # noch keine site.json — nichts zu sichern
    if new_data is not None:
        try:
            old = json.loads(raw)
        except ValueError:
            old = None
        # Beschädigte site.json immer sichern: sie ist gleich überschrieben.
        if old is not None and not _site_changed_keys(old, new_data):
            return
    existing = list_revisions()
    if not force and existing:
        try:
            age = time.time() - (REVISIONS_DIR / existing[0]['name']).stat().st_mtime
            if age < REVISION_COALESCE:
                return
        except OSError:
            pass
    REVISIONS_DIR.mkdir(parents=True, exist_ok=True)
    name = 'site-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.json'
    tmp = REVISIONS_DIR / (name + '.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(raw)
    os.replace(tmp, REVISIONS_DIR / name)
    _rotate_revisions(keep)


def save_site(data: dict) -> None:
    with _site_lock:
        try:
            _snapshot_site(data)
        except Exception as e:
            log.warning("Revision konnte nicht angelegt werden: %s", e)
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
        msg['Subject']    = subject
        msg['From']       = sender
        msg['To']         = to
        msg['Date']       = formatdate(localtime=True)
        msg['Message-ID'] = make_msgid(domain=host)
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
        health_note('smtp', ok=True)
    except Exception as e:
        log.error("E-Mail senden fehlgeschlagen: %s", e)
        health_note('smtp', str(e)[:200])


def _email_html(title: str, lines: list[str]) -> str:
    body = ''.join(f'<p style="margin:4px 0">{l}</p>' for l in lines)
    return (
        '<div style="font-family:sans-serif;max-width:480px;padding:20px;'
        'background:#0d1117;color:#c9d1d9;border-radius:8px">'
        f'<h3 style="margin:0 0 12px;color:#58a6ff">{title}</h3>'
        f'{body}</div>'
    )


def _cookie_secure() -> bool:
    """`Secure` setzen, wenn die Anfrage über HTTPS kam.

    Ohne das Flag schickt der Browser das Sitzungs-Token auch über eine
    unverschlüsselte Verbindung — ein einziger versehentlicher http-Aufruf gibt
    es damit im Klartext preis. Fest auf True lässt es sich nicht setzen: Im
    Heimnetz läuft der Admin oft über http, und ein `Secure`-Cookie käme dort
    nie zurück. `is_secure` stammt hinter einem Proxy aus X-Forwarded-Proto —
    fälscht das jemand auf einer http-Verbindung, sperrt er nur sich selbst aus.
    """
    try:
        return bool(request.is_secure)
    except Exception:      # noqa: BLE001 — ausserhalb eines Anfragekontexts
        return False


def invalidate_admin_sessions(keep: str | None = None) -> int:
    """Alle Admin-Sitzungen bis auf `keep` beenden. Liefert die Anzahl.

    Nach einem Passwortwechsel: eine mitgelesene oder geklaute Sitzung soll den
    Wechsel nicht überleben. Die eigene bleibt, sonst fliegt man selbst raus.
    """
    tokens = [t for t in sessions if t != keep]
    for t in tokens:
        del sessions[t]
    if tokens:
        save_sessions()
    return len(tokens)


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


def _peer_addr(req) -> str:
    """Die tatsächliche Gegenstelle der Verbindung (vor ProxyFix)."""
    return (req.environ.get('mypage.peer') or req.remote_addr or '').strip()


def _trusted_proxy_nets() -> list:
    """Netze, deren Weiterleitungs-Kopfzeilen geglaubt werden.

    Leer (Standard): alle privaten Adressen gelten als Zwischenglied — dort
    steht in jedem realen Aufbau der Reverse Proxy, der Cloudflare-Tunnel oder
    das Docker-Gateway. Ist die Option gesetzt, zählen ausschließlich die
    genannten Netze; damit lässt sich auch das eigene LAN ausschließen.
    """
    out = []
    try:
        raw = (load_config().get('trusted_proxies') or '').strip()
    except Exception:      # noqa: BLE001 — vor dem ersten Laden der Optionen
        raw = ''
    for part in raw.replace(',', ' ').split():
        try:
            out.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            pass
    return out


def _proxy_headers_trusted(req) -> bool:
    """Darf man den Weiterleitungs-Kopfzeilen dieser Verbindung glauben?"""
    try:
        ip = ipaddress.ip_address(_peer_addr(req))
    except ValueError:
        return False
    nets = _trusted_proxy_nets()
    if nets:
        return any(ip in n for n in nets)
    return bool(ip.is_private or ip.is_loopback or ip.is_link_local)


def get_client_ip(req) -> str:
    """Beste verfügbare Besucher-IP.

    Hinter Cloudflare Tunnel / Reverse Proxy ist `remote_addr` die Adresse des
    letzten Zwischenglieds — im HA-Setup das Docker-Bridge-Gateway (172.30.32.1),
    für alle Besucher dieselbe. Deshalb zuerst die Kopfzeilen auswerten, in denen
    die echte Adresse steht, und dabei die erste **öffentliche** nehmen: die
    Zwischenglieder hängen ihre eigenen (privaten) Adressen an die Kette an.

    **Nur von einem Zwischenglied.** Bis 0.11.29 wurden die Kopfzeilen von jedem
    Absender übernommen. Wer den Port direkt erreichte, konnte sich damit jede
    beliebige Adresse geben — und weil die Login-Sperre je Adresse zählt, war
    sie durch Weiterdrehen der Kopfzeile wirkungslos: zwölf Fehlversuche mit
    zwölf erfundenen Adressen lösten keine Sperre aus. Bei direkter Verbindung
    zählt deshalb ausschließlich die echte Gegenstelle.
    """
    if _proxy_headers_trusted(req):
        for header in ('CF-Connecting-IP', 'True-Client-IP', 'X-Real-IP'):
            value = (req.headers.get(header) or '').strip()
            if _is_public_ip(value):
                return value
        for part in (req.headers.get('X-Forwarded-For') or '').split(','):
            if _is_public_ip(part):
                return part.strip()
        return req.remote_addr or 'unknown'
    return _peer_addr(req) or 'unknown'


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
    health_note('client_ip', f"{ip} — Kopfzeilen: {', '.join(seen) or 'keine'}")


def _clear_ip_warning() -> None:
    global _last_ip_warning
    if _last_ip_warning:
        _last_ip_warning = 0.0
        health_note('client_ip', ok=True)


# ── Brute-Force-Schutz ────────────────────────────────────────────────────────

def is_rate_limited(ip: str, peer: str = '') -> bool:
    now = time.time()
    for key, blocked in ((ip, _blocked_ips), (peer, _blocked_peers)):
        if key and key in blocked:
            if now < blocked[key]:
                return True
            del blocked[key]
    _failed_attempts[ip] = [t for t in _failed_attempts[ip] if now - t < RATE_LIMIT_WINDOW]
    return False


def record_failed_attempt(ip: str, peer: str = '') -> None:
    now = time.time()
    _failed_login_times.append(now)
    if peer:
        _failed_peers[peer] = [t for t in _failed_peers[peer]
                               if now - t < RATE_LIMIT_WINDOW] + [now]
        if len(_failed_peers[peer]) >= RATE_LIMIT_PEER_MAX:
            _blocked_peers[peer] = now + RATE_LIMIT_BLOCK
            log.warning("Verbindung von %s für %d Minuten gesperrt "
                        "(%d Fehlversuche, gemeldete Adressen wechselnd)",
                        peer, RATE_LIMIT_BLOCK // 60, len(_failed_peers[peer]))
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


def clear_failed_attempts(ip: str, peer: str = '') -> None:
    _failed_attempts.pop(ip, None)
    _blocked_ips.pop(ip, None)
    if peer:
        _failed_peers.pop(peer, None)
        _blocked_peers.pop(peer, None)


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


# ── Vorschau-Sitzung ──────────────────────────────────────────────────────────
# Der Wartungsmodus liefert jede oeffentliche Seite als 503 aus, und ein
# abgeschaltetes Modul antwortet mit 404. Zum Aufbauen einer Seite braucht man
# aber genau den echten Blick darauf — mit Navigation und Unterseiten, nicht nur
# den Vorschaurahmen der Startseite. Ein signierter Link setzt dafuer einen
# Cookie: Wer ihn hat, sieht die Seite, alle anderen weiterhin die Wartungsseite.
#
# Der Link ist absichtlich teilbar (Vorstand, Kunde, Partner) — deshalb laeuft er
# ab, traegt noindex und laesst sich mit einem Knopf vollstaendig zurueckziehen.

PREVIEW_COOKIE = 'mypage_preview'
PREVIEW_PARAM = 'vorschau'
PREVIEW_HOURS = (1, 8, 168)      # 1 Stunde, 8 Stunden, 7 Tage
_preview_lock = threading.Lock()


def _preview_nonce() -> str:
    """Zufallswert, der in den Signatur-Salt eingeht. Erneuern = alles widerrufen."""
    with _preview_lock:
        try:
            with open(PREVIEW_PATH, encoding='utf-8') as f:
                n = (json.load(f) or {}).get('nonce')
            if isinstance(n, str) and n:
                return n
        except (OSError, ValueError):
            pass
        n = secrets.token_hex(8)
        try:
            _atomic_write_json(PREVIEW_PATH, {'nonce': n}, mode=0o600)
        except Exception as e:      # noqa: BLE001 — ohne Datei gilt der Wert nur bis zum Neustart
            log.warning("Vorschau-Grundlage konnte nicht gespeichert werden: %s", e)
        return n


def preview_revoke() -> None:
    with _preview_lock:
        _atomic_write_json(PREVIEW_PATH, {'nonce': secrets.token_hex(8)}, mode=0o600)


def _preview_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(str(admin_app.config.get('SECRET_KEY', '')),
                                  salt='preview:' + _preview_nonce())


def preview_token(hours: int) -> str:
    """Signierter Token. Die Laufzeit steht mit drin, damit sie beim Lesen gilt."""
    return _preview_serializer().dumps({'h': int(hours)})


def preview_token_hours(token: str) -> int | None:
    """Restlaufzeit-Grundlage in Stunden, wenn der Token gueltig ist — sonst None."""
    if not token:
        return None
    try:
        data = _preview_serializer().loads(token, max_age=168 * 3600)
    except (BadSignature, SignatureExpired, ValueError):
        return None
    hours = int((data or {}).get('h') or 0)
    if hours not in PREVIEW_HOURS:
        return None
    # Zweiter Durchlauf mit der eigenen Laufzeit: `max_age` oben ist nur die
    # Obergrenze, gelten soll die im Token vermerkte Dauer.
    try:
        _preview_serializer().loads(token, max_age=hours * 3600)
    except (BadSignature, SignatureExpired):
        return None
    return hours


def preview_active() -> bool:
    """Laeuft die aktuelle Anfrage in einer Vorschau-Sitzung?"""
    try:
        return preview_token_hours(request.cookies.get(PREVIEW_COOKIE, '')) is not None
    except Exception:      # noqa: BLE001 — ausserhalb eines Anfragekontexts
        return False


def maintenance_active(site: dict) -> bool:
    """Wartungsmodus fuer diese Anfrage — in der Vorschau ist er aufgehoben."""
    return bool(site['design'].get('maintenance')) and not preview_active()


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


SITE_LANGS = ('de', 'en')


def site_default_lang(site: dict | None = None) -> str:
    """Sprache, die eine Adresse ohne weitere Angabe ausliefert.

    'auto' bedeutet: wie früher nach `Accept-Language` entscheiden.
    """
    d = (site if site is not None else load_site())['design']
    v = (d.get('default_lang') or '').strip().lower()
    return v if v in SITE_LANGS + ('auto',) else 'de'


def detect_language(req) -> str:
    """Sprache dieser Anfrage: `?lang=` → Cookie → Standardsprache der Seite.

    `Accept-Language` entscheidet **nicht** mehr mit, außer die Standardsprache
    steht ausdrücklich auf „automatisch". Grund: dieselbe Adresse lieferte je
    nach Kopfzeile eine andere Seite. Googlebot crawlt ohne diese Kopfzeile und
    bekam dadurch auf einer deutschen Seite durchgehend die englische Fassung —
    Titel, Beschreibung und `<html lang>` inbegriffen. Zugleich ist eine feste
    Zuordnung „Adresse → Sprache" die Voraussetzung dafür, dass `canonical` und
    `hreflang` überhaupt etwas Wahres aussagen können.

    Das Ergebnis hängt an der Anfrage und wird dort gemerkt: `detect_language`
    wird je Anfrage mehrfach aufgerufen, und `load_site()` liest jedes Mal die
    Datei.
    """
    if has_request_context() and req is request:
        cached = getattr(g, 'mypage_lang', None)
        if cached:
            return cached
    q = (req.args.get('lang') or '').strip().lower()
    cookie = req.cookies.get('lang', '')
    if q in SITE_LANGS:
        lang = q
    elif cookie in SITE_LANGS:
        lang = cookie
    else:
        default = site_default_lang()
        if has_request_context() and req is request:
            g.mypage_lang_auto = (default == 'auto')
        if default == 'auto':
            accept = req.headers.get('Accept-Language', '')
            lang = 'de' if accept.lower().startswith('de') else 'en'
        else:
            lang = default
    if has_request_context() and req is request:
        g.mypage_lang = lang
    return lang


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
    """Wie viele Monatsdateien das Besucher-Archiv behält (0 = unbegrenzt).

    Standard 1: das Archiv enthält ungekürzte IP-Adressen, und die meisten
    Datenschutzerklärungen sagen für Zugriffsdaten eine Frist von 30 Tagen zu.
    Ein Monat trifft das am ehesten. Wer länger auswerten will, dreht die
    Option bewusst hoch — verboten wird es nicht.
    """
    raw = load_config().get('visit_file_keep')
    if raw is None or raw == '':
        return 1
    try:
        return max(0, min(120, int(raw)))
    except (TypeError, ValueError):
        return 1


def visit_archive_on() -> bool:
    """Ist das dauerhafte Besucher-Archiv aktiv?

    Zwei Wege führen dahin: die Add-on-Option `visit_file_log` und der Schalter
    im Explorer-Reiter. Die Option gehört Home Assistant und lässt sich aus der
    App heraus nicht setzen — deshalb der zweite, app-eigene Schalter in
    site.json. Wer die Option gesetzt hat, merkt vom zweiten nichts.
    """
    if load_config().get('visit_file_log'):
        return True
    return bool(load_site()['design'].get('visit_archive'))


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
    if not visit_archive_on():
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


# ---------------------------------------------------------------------------
# Länder-Zuordnung ohne Fremd-API
#
# Statt jede Besucher-IP bei einem Dienst nachzufragen (Tageslimit, Datenschutz)
# hält das Add-on eine eigene Tabelle: IP-Bereich → Ländercode. Erste Wahl ist
# die frei herunterladbare DB-IP-Lite-Liste, Rückfallebene sind die Delegations-
# dateien der fünf Regional Internet Registries — dieselben Rohdaten, aus denen
# NPMplus seine Ländersperre baut.
#
# Der Unterschied ist die Genauigkeit: die Registries führen das Land der
# Zuteilung (Telekom-Bereiche stehen dort auch mal auf GB), DB-IP führt den
# tatsächlichen Standort. Deshalb erst DB-IP, und die Registries nur, wenn der
# Download ausfällt.
#
# Die Tabelle liegt unter /config/geoip und wird wöchentlich erneuert; ein
# Neustart lädt nichts nach. Es verlässt keine Besucher-IP das Add-on.
# ---------------------------------------------------------------------------
GEOIP_DIR     = Path(_DATA) / 'geoip'
GEOIP_CACHE   = GEOIP_DIR / 'ranges.tsv.gz'
GEOIP_STAMP   = GEOIP_DIR / 'archive.stamp'
GEOIP_MAX_AGE = 7 * 86400
GEOIP_DBIP    = 'https://download.db-ip.com/free/dbip-country-lite-{:%Y-%m}.csv.gz'
GEOIP_RIR = (
    'https://ftp.apnic.net/stats/apnic/delegated-apnic-extended-latest',
    'https://ftp.ripe.net/pub/stats/ripencc/delegated-ripencc-extended-latest',
    'https://ftp.arin.net/pub/stats/arin/delegated-arin-extended-latest',
    'https://ftp.lacnic.net/pub/stats/lacnic/delegated-lacnic-extended-latest',
    'https://ftp.afrinic.net/pub/stats/afrinic/delegated-afrinic-extended-latest',
)


def _geo_empty() -> dict:
    """Leere Nachschlagetabellen, getrennt nach Adressfamilie.

    IPv4-Adressen passen in 64-Bit-Zahlen und liegen als `array` im Speicher,
    ein Achtel dessen, was eine Liste bräuchte. IPv6-Adressen sind dafür zu
    groß, stehen aber als 16-Byte-Blöcke in Netzreihenfolge in einem einzigen
    Puffer — und der vergleicht sich Byte für Byte genauso wie die Zahlen.
    """
    return {
        4: {'starts': array('Q'),  'ends': array('Q'),  'codes': [], 'pool': {}},
        6: {'starts': bytearray(), 'ends': bytearray(), 'codes': [], 'pool': {}},
    }


# Wird beim Aktualisieren komplett ersetzt und nie an Ort und Stelle geändert —
# deshalb brauchen die Leser kein Lock.
_geo_tables: dict = _geo_empty()


def _geo_enabled() -> bool:
    return bool(load_config().get('geoip_offline', True))


def _cf_country(req) -> str:
    c = (req.headers.get('CF-IPCountry') or '').strip().upper()
    return c if len(c) == 2 and c.isalpha() and c != 'XX' else ''


def _lang_country(req) -> str:
    m = re.search(r'[a-zA-Z]{2,3}-([A-Za-z]{2})\b', req.headers.get('Accept-Language') or '')
    return m.group(1).upper() if m else ''


def _guess_country(req) -> str:
    """Besucherland: Cloudflare-Header > lokale Tabelle > Accept-Language-Näherung."""
    return (_cf_country(req)
            or (_geo_country(get_client_ip(req)) if _geo_enabled() else '')
            or _lang_country(req))


def _blob_bisect(blob: bytes, key: bytes) -> int:
    """`bisect_right` über einen Puffer aus aneinandergereihten 16-Byte-Schlüsseln."""
    lo, hi = 0, len(blob) >> 4
    while lo < hi:
        mid = (lo + hi) >> 1
        if blob[mid << 4:(mid + 1) << 4] <= key:
            lo = mid + 1
        else:
            hi = mid
    return lo


def _geo_country(ip: str) -> str:
    """Ländercode einer IP aus der lokalen Tabelle ('' = privat oder unbekannt)."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ''
    if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
        return ''
    fam = _geo_tables[addr.version]
    codes = fam['codes']
    if not codes:
        return ''
    # Letzter Bereich, der nicht hinter der IP anfängt. Passt sein Ende nicht,
    # liegt die IP in einer Lücke (nicht zugeteilt oder nicht zugeordnet).
    if addr.version == 4:
        num = int(addr)
        i = bisect.bisect_right(fam['starts'], num) - 1
        return codes[i] if i >= 0 and num <= fam['ends'][i] else ''
    key = addr.packed
    i = _blob_bisect(fam['starts'], key) - 1
    return codes[i] if i >= 0 and key <= bytes(fam['ends'][i << 4:(i + 1) << 4]) else ''


def _geo_append(tables: dict, version: int, start: int, end: int, cc: str) -> None:
    """Einen Bereich anhängen. Die Quelle muss je Familie aufsteigend liefern."""
    fam = tables[version]
    if version == 4:
        fam['starts'].append(start)
        fam['ends'].append(end)
    else:
        fam['starts'] += start.to_bytes(16, 'big')
        fam['ends'] += end.to_bytes(16, 'big')
    fam['codes'].append(fam['pool'].setdefault(cc, cc))   # jeden Code nur einmal halten


def _geo_rows(tables: dict):
    """Alle Bereiche wieder als (version, start, ende, code) ausgeben."""
    for version in (4, 6):
        fam = tables[version]
        for i, cc in enumerate(fam['codes']):
            if version == 4:
                yield 4, fam['starts'][i], fam['ends'][i], cc
            else:
                yield (6,
                       int.from_bytes(fam['starts'][i << 4:(i + 1) << 4], 'big'),
                       int.from_bytes(fam['ends'][i << 4:(i + 1) << 4], 'big'), cc)


def _geo_count(tables: dict) -> tuple[int, int]:
    return len(tables[4]['codes']), len(tables[6]['codes'])


def _geo_fetch_dbip(tables: dict) -> str:
    """DB-IP-Lite einlesen (CSV: start,ende,land — je Familie bereits sortiert).

    Am Monatsanfang steht die neue Datei nicht immer sofort bereit, deshalb der
    Griff zum Vormonat.
    """
    today = date.today()
    months = [today.replace(day=1)]
    months.append((months[0] - timedelta(days=1)).replace(day=1))
    last_err: Exception | None = None
    for month in months:
        url = GEOIP_DBIP.format(month)
        try:
            with http.get(url, timeout=180, stream=True) as r:
                r.raise_for_status()
                r.raw.decode_content = True
                prev = {4: -1, 6: -1}
                with gzip.open(r.raw, 'rt', encoding='utf-8', errors='replace') as fh:
                    for line in fh:
                        f = line.rstrip('\n').split(',')
                        if len(f) != 3:
                            continue
                        cc = f[2].strip().upper()
                        # 'ZZ' ist DB-IPs Platzhalter für unbekannt/reserviert
                        if len(cc) != 2 or not cc.isalpha() or cc == 'ZZ':
                            continue
                        try:
                            start = ipaddress.ip_address(f[0])
                            end   = ipaddress.ip_address(f[1])
                        except ValueError:
                            continue
                        v = start.version
                        if v != end.version or int(start) <= prev[v]:
                            raise ValueError('Datei ist nicht aufsteigend sortiert')
                        prev[v] = int(end)
                        _geo_append(tables, v, int(start), int(end), cc)
            return f'dbip {month:%Y-%m}'
        except Exception as e:
            last_err = e
            log.warning("GeoIP: DB-IP %s nicht nutzbar (%s)", f'{month:%Y-%m}', e)
            tables.update(_geo_empty())   # Halbe Datei nicht stehen lassen
    raise RuntimeError(f'DB-IP nicht verfügbar ({last_err})')


def _geo_fetch_rir(tables: dict) -> str:
    """Rückfallebene: Delegationsdateien registry|cc|typ|start|wert|datum|status|…"""
    rows: list[tuple[int, int, int, str]] = []
    ok = 0
    for url in GEOIP_RIR:
        host = urlsplit(url).netloc
        before = len(rows)
        try:
            with http.get(url, timeout=180, stream=True) as r:
                r.raise_for_status()
                # Die Registries schicken text/plain ohne Zeichensatz — ohne diese
                # Zeile gibt iter_lines() Bytes zurück und der Parser läuft ins Leere.
                r.encoding = 'utf-8'
                for line in r.iter_lines(decode_unicode=True):
                    if not line or line[0] == '#':
                        continue
                    f = line.split('|')
                    if len(f) < 7 or f[2] not in ('ipv4', 'ipv6'):
                        continue
                    cc = f[1].strip().upper()
                    # '*' steht in den Summenzeilen am Dateianfang; 'available'
                    # und 'reserved' gehören keinem Land.
                    if len(cc) != 2 or not cc.isalpha() or f[6] not in ('allocated', 'assigned'):
                        continue
                    try:
                        if f[2] == 'ipv4':
                            # Bei IPv4 zählt das Feld Adressen statt Präfixlängen —
                            # und die Zahl ist nicht immer eine Zweierpotenz.
                            start, size = int(ipaddress.IPv4Address(f[3])), int(f[4])
                            if size <= 0:
                                continue
                            rows.append((4, start, start + size - 1, cc))
                        else:
                            prefix = int(f[4])
                            if not 0 <= prefix <= 128:
                                continue
                            start = int(ipaddress.IPv6Address(f[3]))
                            rows.append((6, start, start + (1 << (128 - prefix)) - 1, cc))
                    except ValueError:
                        continue
            ok += 1
            log.info("GeoIP: %s → %d Bereiche", host, len(rows) - before)
        except Exception as e:
            log.warning("GeoIP: %s nicht erreichbar (%s)", host, e)
    # Eine fehlende Registry würde einen ganzen Kontinent unsichtbar machen und
    # dessen Besucher stillschweigend als unbekannt festschreiben.
    if ok < len(GEOIP_RIR):
        raise RuntimeError(f'nur {ok} von {len(GEOIP_RIR)} Registries erreichbar')
    rows.sort()
    for version, start, end, cc in rows:
        _geo_append(tables, version, start, end, cc)
    return 'rir'


def _geo_download() -> tuple[dict, str]:
    tables = _geo_empty()
    try:
        return tables, _geo_fetch_dbip(tables)
    except Exception as e:
        log.warning("GeoIP: DB-IP fällt aus (%s) — weiche auf die Registries aus", e)
    tables = _geo_empty()
    return tables, _geo_fetch_rir(tables)


def _geo_save(tables: dict, source: str) -> None:
    GEOIP_DIR.mkdir(parents=True, exist_ok=True)
    tmp = GEOIP_CACHE.with_suffix('.tmp')
    with gzip.open(tmp, 'wt', encoding='ascii') as fh:
        fh.write(f'#{source}\n')
        for version, start, end, cc in _geo_rows(tables):
            fh.write(f'{version}\t{start}\t{end}\t{cc}\n')
    tmp.replace(GEOIP_CACHE)


def _geo_load_cache() -> tuple[dict, str]:
    tables = _geo_empty()
    source = 'unbekannt'
    with gzip.open(GEOIP_CACHE, 'rt', encoding='ascii') as fh:
        for line in fh:
            if line[:1] == '#':
                source = line[1:].strip()
                continue
            f = line.rstrip('\n').split('\t')
            if len(f) == 4:
                _geo_append(tables, int(f[0]), int(f[1]), int(f[2]), f[3])
    return tables, source


def _geo_refresh() -> bool:
    """Tabelle bereitstellen: Zwischenspeicher benutzen, wöchentlich erneuern."""
    global _geo_tables
    loaded = bool(_geo_tables[4]['codes'])
    try:
        age = time.time() - GEOIP_CACHE.stat().st_mtime
    except OSError:
        age = None
    if not loaded and age is not None:
        try:
            tables, source = _geo_load_cache()
            _geo_tables = tables
            loaded = True
            log.info("GeoIP: %d IPv4- und %d IPv6-Bereiche aus %s geladen (%d Tage alt)",
                     *_geo_count(tables), source, int(age // 86400))
        except Exception as e:
            log.warning("GeoIP: Zwischenspeicher unlesbar (%s) — wird neu geholt", e)
            age = None
    if age is None or age >= GEOIP_MAX_AGE:
        try:
            tables, source = _geo_download()
            _geo_save(tables, source)
            _geo_tables = tables
            loaded = True
            log.info("GeoIP: Tabelle aus %s erneuert — %d IPv4- und %d IPv6-Bereiche",
                     source, *_geo_count(tables))
        except Exception as e:
            # Die alte Tabelle bleibt in Betrieb, der nächste Durchlauf probiert es erneut.
            log.warning("GeoIP: Aktualisierung fehlgeschlagen (%s)", e)
    return loaded


def _geo_backfill_log() -> int:
    """Fehlende Länder im Besucher-Log nachtragen — offline, also ohne Limit."""
    stats = load_stats()
    filled = 0
    for v in stats.get('log', []):
        if v.get('country'):
            continue
        code = _geo_country(v.get('ip') or '')
        if code:
            v['country'] = code
            filled += 1
    if filled:
        save_stats(stats)
    return filled


def _geo_backfill_archive() -> int:
    """Dasselbe für die Monatsdateien des Besucher-Archivs.

    Läuft nur, wenn die Tabelle seit dem letzten Durchlauf erneuert wurde — die
    CSVs jede Stunde durchzugehen wäre reine Plattenarbeit ohne neues Ergebnis.
    """
    if not VISITS_DIR.is_dir():
        return 0
    try:
        current = str(int(GEOIP_CACHE.stat().st_mtime))
    except OSError:
        return 0
    try:
        if GEOIP_STAMP.read_text(encoding='ascii').strip() == current:
            return 0
    except OSError:
        pass
    filled = 0
    with _visit_file_lock:
        for path in sorted(VISITS_DIR.glob('visits-*.csv')):
            try:
                with path.open('r', encoding='utf-8-sig', newline='') as fh:
                    rows = list(csv.DictReader(fh, delimiter=';'))
                hits = 0
                for row in rows:
                    if row.get('land'):
                        continue
                    code = _geo_country((row.get('ip') or '').strip())
                    if code:
                        row['land'] = code
                        hits += 1
                if not hits:
                    continue
                tmp = path.with_suffix('.tmp')
                with tmp.open('w', encoding='utf-8-sig', newline='') as fh:
                    w = csv.DictWriter(fh, fieldnames=VISIT_CSV_COLUMNS, delimiter=';',
                                       extrasaction='ignore')
                    w.writeheader()
                    for row in rows:
                        w.writerow({k: (row.get(k) or '') for k in VISIT_CSV_COLUMNS})
                tmp.replace(path)
                filled += hits
            except (OSError, csv.Error) as e:
                log.warning("GeoIP: Archivdatei %s nicht ergänzt (%s)", path.name, e)
    try:
        GEOIP_DIR.mkdir(parents=True, exist_ok=True)
        GEOIP_STAMP.write_text(current, encoding='ascii')
    except OSError:
        pass
    return filled


def _geoip_worker() -> None:
    """Tabelle aktuell halten und fehlende Länder nachtragen (stündlich)."""
    while True:
        try:
            if _geo_enabled() and _geo_refresh():
                filled = _geo_backfill_log()
                archived = _geo_backfill_archive()
                if filled or archived:
                    log.info("GeoIP: %d Log-Einträge und %d Archivzeilen ergänzt",
                             filled, archived)
        except Exception as e:
            log.warning("GeoIP-Worker-Fehler: %s", e)
        time.sleep(3600)


# ── Datenvolumen ──────────────────────────────────────────────────────────────
#
# Waitress liefert jedes Byte selbst aus, also lässt es sich an der WSGI-Schnitt-
# stelle mitzählen: eine Hülle um die öffentliche App zählt mit, was hinausgeht,
# und schreibt die Tagessumme einmal pro Minute nach stats.json. Pro Anfrage zu
# schreiben hieße ein Schreibzugriff je Bild.
#
# Gezählt wird, was MyPage ausliefert — nicht, was auf der Leitung liegt: ein
# vorgelagerter Reverse Proxy packt selbst (gzip) und legt TLS obendrauf. Für
# die echte Leitungslast sind dessen Protokolle die richtige Quelle.
TRAFFIC_FLUSH_SECONDS = 60
_traffic_lock = threading.Lock()
_traffic_pending: dict = {}          # Tag → {'out': n, 'in': n, 'out_bot': n, 'in_bot': n}


def human_size(n: int) -> str:
    """Bytes lesbar machen — 1024er-Schritte, wie im Dateibereich."""
    value = float(n or 0)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if value < 1024 or unit == 'GB':
            return f'{value:.1f} {unit}' if unit != 'B' else f'{int(value)} B'
        value /= 1024
    return f'{value:.1f} GB'


def _traffic_add(day: str, field: str, value: int) -> None:
    if value <= 0:
        return
    with _traffic_lock:
        fields = _traffic_pending.setdefault(day, {})
        fields[field] = fields.get(field, 0) + value


class _TrafficStream:
    """Zählt Antworten ohne angekündigte Länge erst beim Ausliefern.

    Gebucht wird im `close()`, das der Server auch bei abgebrochener Verbindung
    aufruft — ein zur Hälfte geladenes Video zählt damit zur Hälfte.
    """

    def __init__(self, inner, day: str, field: str, head: int):
        self.inner, self.day, self.field, self.sent = inner, day, field, head

    def __iter__(self):
        for chunk in self.inner:
            self.sent += len(chunk)
            yield chunk

    def close(self) -> None:
        _traffic_add(self.day, self.field, self.sent)
        self.sent = 0
        close = getattr(self.inner, 'close', None)
        if close is not None:
            close()


class TrafficMeter:
    """WSGI-Hülle um die öffentliche App, die das Datenvolumen mitzählt."""

    def __init__(self, app):
        self.app = app
        self.config = app.config      # `_serve` liest daraus das Upload-Limit

    def __call__(self, environ, start_response):
        ua = environ.get('HTTP_USER_AGENT') or ''
        # Dieselbe Erkennung wie im Besucher-Log, damit sich die Zahlen decken.
        field = '_bot' if (not ua) or any(b in ua.lower() for b in _BOT_UA) else ''
        day = date.today().isoformat()
        try:
            _traffic_add(day, 'in' + field, int(environ.get('CONTENT_LENGTH') or 0))
        except ValueError:
            pass
        info = {'head': 0, 'len': None, 'body': True}

        def _start(status, headers, exc_info=None):
            # Die Kopfzeilen zählen mit: bei kleinen Antworten machen sie den
            # Löwenanteil aus, und auf der Leitung stehen sie ebenfalls.
            head = len('HTTP/1.1 ') + len(status) + 4      # Statuszeile + Leerzeile
            length = None
            for name, value in headers:
                head += len(name) + len(value) + 4         # ": " und Zeilenende
                if name.lower() == 'content-length':
                    try:
                        length = int(value)
                    except ValueError:
                        length = None
            info.update(head=head, len=length,
                        # HEAD und "nicht verändert" kündigen eine Länge an,
                        # schicken aber keinen Rumpf.
                        body=(environ.get('REQUEST_METHOD') != 'HEAD'
                              and not status.startswith('304')))
            return start_response(status, headers, exc_info)

        result = self.app(environ, _start)
        if not info['body']:
            _traffic_add(day, 'out' + field, info['head'])
            return result
        if info['len'] is not None:
            # Länge steht fest — sofort buchen und die Antwort unangetastet
            # weiterreichen, damit Waitress große Dateien direkt ausliefern kann.
            _traffic_add(day, 'out' + field, info['head'] + info['len'])
            return result
        return _TrafficStream(result, day, 'out' + field, info['head'])


def _traffic_flush() -> None:
    """Gesammelte Bytes in die Tagesstatistik übernehmen."""
    with _traffic_lock:
        if not _traffic_pending:
            return
        pending = dict(_traffic_pending)
        _traffic_pending.clear()
    stats = load_stats()
    days = stats.setdefault('days', {})
    for day, fields in pending.items():
        entry = days.setdefault(day, {'views': 0, 'uniques': 0})
        for name, value in fields.items():
            entry['traffic_' + name] = entry.get('traffic_' + name, 0) + value
            stats['traffic_' + name] = stats.get('traffic_' + name, 0) + value
    save_stats(stats)


def _traffic_worker() -> None:
    while True:
        time.sleep(TRAFFIC_FLUSH_SECONDS)
        try:
            _traffic_flush()
        except Exception as e:
            log.warning("Datenvolumen konnte nicht gespeichert werden: %s", e)


def traffic_totals(stats: dict) -> dict:
    """Volumen gesamt, heute und über die letzten 30 Tage (Bytes)."""
    today = stats.get('days', {}).get(date.today().isoformat(), {})
    last30 = sorted(stats.get('days', {}).items(), reverse=True)[:30]
    out = {'total_out': stats.get('traffic_out', 0),
           'total_in':  stats.get('traffic_in', 0),
           'today_out': today.get('traffic_out', 0),
           'today_bot': today.get('traffic_out_bot', 0),
           'days_out':  sum(d.get('traffic_out', 0) for _, d in last30),
           'days_bot':  sum(d.get('traffic_out_bot', 0) for _, d in last30)}
    return out


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
    if preview_active():
        return  # eigener Blick beim Aufbauen der Seite
    ua = req.headers.get('User-Agent') or ''
    ip = get_client_ip(req)
    # Rechenzentrums-Adressen zählen unabhängig von der Browserkennung als Bot:
    # Scanner geben sich als „Safari · iOS" aus und rutschen sonst als echter
    # Besucher durch (ein Aufruf, keine Verweildauer).
    is_bot = ((not ua) or any(b in ua.lower() for b in _BOT_UA)
              or vx.is_datacenter_ip(ip))
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
        # Kommt wieder eine echte Adresse an, ist der Proxy repariert — die
        # Meldung gehört weg. Nur dann anfassen, wenn überhaupt eine steht:
        # sonst läge bei jedem Seitenaufruf ein Dateizugriff auf dem Weg.
        _clear_ip_warning()
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


NOTFOUND_MAX_PATHS = 200      # so viele verschiedene Pfade werden gemerkt
NOTFOUND_IPS_MAX = 5          # so viele verschiedene Adressen je Pfad


# Pfade, die es auf dieser Website nie gab und nie geben wird: Sonden auf
# fremde Software. `.php` und `wp-` suchen WordPress, `.env`, `.git/` und
# `.ssh` suchen ausgeplauderte Zugangsdaten, `asset-manifest.json` und
# `/api/graphql` fragen ab, ob hinter der Adresse eine React-App mit
# Schnittstelle steckt. Erkannt wird am Pfad, nicht an der Browserkennung:
# Die faelscht jeder Scanner, den Pfad braucht er echt.
_PROBE_PARTS = ('/wp-', '/wordpress', 'xmlrpc.php', '/.env', '/.git', '/.ssh',
                '/.aws', '/vendor/', '/phpmyadmin', '/pma/', '/cgi-bin/',
                '/asset-manifest.json', '/api/graphql', '/graphql',
                '/config.json', '/telescope/', '/actuator/', '/solr/',
                '/owa/', '/autodiscover/', '/wp-json',
                # Ausgabeordner der ueblichen JavaScript-Baukaesten. MyPage legt
                # nichts davon an: Eigene Dateien liegen unter /static, /uploads
                # und /fonts.
                '/dist/', '/assets/', '/build/', '/node_modules/',
                '/package.json', '/composer.json', '/server-status')

# Verrutschte Sicherungen und Editorreste — hier gibt es sie nicht, gesucht
# werden sie trotzdem. `.zip` steht bewusst nicht dabei: Eine Mitgliederdatei
# darf so heissen, und die liegt unter einer echten Adresse.
_PROBE_SUFFIXES = ('.php', '.asp', '.aspx', '.jsp', '.cgi',
                   '.sql', '.bak', '.old', '.swp', '.tar.gz')

# Namen, unter denen Scanner eine vergessene Kopie der Website vermuten: die
# alte Fassung, ein Abzug vor dem Umbau, die Baustelle daneben. Geprüft wird nur
# der **ganze** Pfad aus einem einzigen Stück — `/bak` ist die Sonde,
# `/seite/bak-in-der-mitte` eine ganz normale Adresse. Bewusst nicht dabei:
# Namen, die MyPage selbst vergibt (`blog`, `projekte`, `uploads`), sonst würde
# ein eigener kaputter Verweis als Sonde durchgehen und aus der Liste fallen.
_PROBE_NAMES = frozenset((
    'bak', 'bac', 'bk', 'back', 'backup', 'backups', 'bkp',
    'old', 'olds', 'oldsite', 'old-site', 'alt', 'archiv', 'archive',
    'site', 'sites', 'sito', 'sitio', 'sitios', 'website',
    'www', 'www2', 'wwwroot', 'web', 'webroot', 'public_html',
    'new', 'newsite', 'temp', 'tmp', 'test', 'testing', 'dev', 'develop',
    'staging', 'stage', 'beta', 'demo', 'live', 'main', 'home', 'index',
    'shop', 'store', 'cms', 'portal', 'dump', 'db', 'database', 'sql',
))
_PROBE_YEAR_RE = re.compile(r'^/(19|20)\d{2}/?$')


def _is_probe(path: str) -> bool:
    """Sucht der Aufruf fremde Software statt einer Seite von hier?"""
    p = (path or '').lower()
    # Alles, was mit einem Punkt beginnt: /.env, /.git/config, /.ssh/id_rsa,
    # /.DS_Store — und Kuriositaeten wie /.bod/.ll/. Eine Adresse dieser Form
    # vergibt MyPage nirgends, /.well-known beantwortet der Proxy davor.
    if p.startswith('/.'):
        return True
    # Ein manifest.json in irgendeinem Unterordner sucht den Ausgabeordner
    # eines fremden Baukastens. Das eigene liegt genau auf /manifest.json.
    if p.endswith('/manifest.json') and p != '/manifest.json':
        return True
    # `/bak`, `/old-site`, `/staging` — und `/2021`, weil die Jahreszahl
    # derselben Vermutung folgt: hier liege die Seite von damals noch herum.
    if p.strip('/') in _PROBE_NAMES or _PROBE_YEAR_RE.match(p):
        return True
    return p.endswith(_PROBE_SUFFIXES) or any(part in p for part in _PROBE_PARTS)


def record_notfound(req) -> None:
    """Einen ins Leere laufenden Aufruf festhalten — nach Pfad gebündelt.

    Getrennt vom Besucher-Log, weil ein 404 kein Besuch ist: Er sagt nichts über
    Reichweite, sondern über kaputte Verweise. Gebündelt statt Zeile für Zeile,
    weil der erste Scanner sonst mit `/wp-login.php` die Ablage füllt — bei
    tausend Versuchen steht dann ein Eintrag mit Zähler tausend statt tausend
    Einträgen.

    Anders als `count_visit()` wird **unabhängig von der Adresse** aufgezeichnet:
    Ein kaputter Verweis, der aus dem eigenen Heimnetz angeklickt wird, ist
    derselbe kaputte Verweis. Hier zählt der Pfad, nicht der Besucher.
    """
    if req.headers.get('X-MyPage-Export'):
        return
    path = (req.path or '/')[:120]
    ua = req.headers.get('User-Agent') or ''
    ref = (req.headers.get('Referer') or '')[:300]
    stats = load_stats()
    nf = stats.setdefault('notfound', {})
    e = nf.get(path) or {'n': 0, 'first': int(time.time())}
    e['n'] = e.get('n', 0) + 1
    e['last'] = int(time.time())
    ip = get_client_ip(req)
    # Wie beim Besucherzähler zählt eine Rechenzentrums-Adresse als Bot, egal was
    # in der Browserkennung steht: Ein Scanner gibt sich als „Safari · iOS" aus,
    # aus einem Serverraum surft aber niemand. Bis 0.11.39 sah diese Liste nur
    # die Kennung — und blendete den Scan deshalb trotz gesetztem Haken nicht aus.
    e['bot'] = bool((not ua) or any(b in ua.lower() for b in _BOT_UA)
                    or vx.is_datacenter_ip(ip))
    probe = _is_probe(path)
    # Woher kam der Aufruf? Bei einem eigenen kaputten Verweis ist die Adresse
    # gleichgültig, bei einer Sonde ist sie das Einzige, womit sich etwas
    # anfangen lässt — sperren kann man nur eine Adresse, keinen Pfad.
    # Gespeichert werden höchstens NOTFOUND_IPS_MAX verschiedene, neueste
    # zuerst; nur öffentliche. Das eigene Heimnetz und die internen Aufrufe von
    # Home Assistant sagen nichts, füllen aber die Liste.
    if _is_public_ip(ip):
        ips = [a for a in (e.get('ips') or []) if a != ip]
        e['ips'] = [ip] + ips[:NOTFOUND_IPS_MAX - 1]
        e['cc'] = _guess_country(req)
    if ref:
        e['ref'] = ref
        # Ein Verweis von der eigenen Adresse heißt: der kaputte Link steht auf
        # der eigenen Website. Das ist der Fall, der wirklich zählt — fremde
        # Verweise und Scanner kann man nicht reparieren, eigene schon.
        #
        # Bei einer Sonde gilt das nicht: Den Referer setzt der Scanner selbst,
        # und er trägt gern die angegriffene Adresse ein. Ohne diese Ausnahme
        # trug `/api/graphql` die Marke „eigener Link" und stand damit ganz
        # oben in der Liste — eine gefälschte Kopfzeile hätte den Scan über
        # jeden echten kaputten Verweis gehoben.
        # Zeigt der Verweis auf **genau die** Adresse, die gerade abgerufen wird,
        # ist er gefälscht: Eine Seite, die es nicht gibt, kann keinen Link auf
        # sich selbst tragen. Genau so trat ein Scanner auf, der `/Blog`,
        # `/BACKUP` und `/2021` durchprobierte und jedes Mal die eigene Adresse
        # als Verweisgeber eintrug — jede Zeile trug die Marke „eigener Link".
        e['internal'] = (_same_site_ref(ref) and not probe
                         and not _ref_is_self(ref, req))
    nf[path] = e
    # Begrenzen: die am längsten nicht mehr gesehenen Pfade fliegen zuerst raus.
    if len(nf) > NOTFOUND_MAX_PATHS:
        for k in sorted(nf, key=lambda k: nf[k].get('last', 0))[:len(nf) - NOTFOUND_MAX_PATHS]:
            del nf[k]
    stats['notfound'] = nf
    save_stats(stats)


def _ref_is_self(ref: str, req) -> bool:
    """Verweist die Kopfzeile auf die gerade abgerufene Adresse selbst?"""
    try:
        r = urlparse(ref)
    except ValueError:
        return False
    return (r.path or '/').rstrip('/') == (req.path or '/').rstrip('/')


def _same_site_ref(ref: str) -> bool:
    """Zeigt der Verweisgeber auf die eigene Website?

    Verglichen wird der **ganze** Hostname, nie ein Teilstück: `gizmonet.de.bad.tld`
    darf nicht als eigene Adresse durchgehen.
    """
    try:
        host = urlparse(ref).hostname or ''
    except ValueError:
        return False
    own = set()
    for cand in (load_site()['design'].get('public_url') or '', request.host_url):
        try:
            h = urlparse(cand).hostname
        except ValueError:
            h = None
        if h:
            own.add(h.lower())
    return host.lower() in own


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


def _visit_path_labels(site: dict, paths) -> dict:
    """Sprechende Titel für die Pfade aus dem Besucher-Archiv.

    Im Explorer steht sonst überall `/blog/a1b2c3` statt des Beitragstitels.
    Nachgeschlagen wird nur, was in der Antwort auch vorkommt — bei ein paar
    hundert Pfaden je Abruf ist das billiger als eine Tabelle über alles.
    Pfade ohne eigenen Titel (Startseite, Übersichten) fehlen bewusst in der
    Antwort; die Oberfläche zeigt dann den Pfad.
    """
    labels = {}
    posts = projects = pages = lib = None
    trips = None
    for path in paths:
        title = ''
        if path.startswith('/blog/'):
            if posts is None:
                posts = {p.get('id'): p for p in site.get('posts', [])}
            po = posts.get(path.split('/blog/', 1)[1].split('/')[0])
            title = (po.get('title_de') or po.get('title_en')) if po else ''
        elif path.startswith('/p/'):
            if projects is None:
                projects = {p.get('id'): p for p in site.get('projects', [])}
            pr = projects.get(path.split('/p/', 1)[1].split('/')[0])
            title = pr.get('title') if pr else ''
        elif path.startswith('/seite/'):
            if pages is None:
                pages = {p.get('slug'): p for p in site.get('pages', [])}
            pg = pages.get(path.split('/seite/', 1)[1].split('/')[0])
            title = (pg.get('title_de') or pg.get('title_en')) if pg else ''
        elif path.startswith('/bibliothek/'):
            if lib is None:
                lib = {e.get('slug'): e for e in _lib_public_entries(site)}
            en = lib.get(path.split('/bibliothek/', 1)[1].split('/')[0])
            title = (en.get('title_de') or en.get('title_en')) if en else ''
        elif path.startswith('/reiseblog/'):
            if trips is None:
                trips = _trav_public_trips(site)
            parts = path.split('/reiseblog/', 1)[1].split('/')
            trip = next((x for x in trips if x['slug'] == parts[0]), None)
            tname = (trip.get('name') or trip.get('destination') or '') if trip else ''
            if trip and len(parts) > 1 and parts[1]:
                day = next((d for d in _trav_public_days(trip)
                            if d.get('slug') == parts[1]), None)
                art = (day.get('article') or {}) if day else {}
                dtitle = ((art.get('de') or {}).get('title')
                          or (art.get('en') or {}).get('title') or '')
                title = f'{tname} — {dtitle}' if dtitle else ''
            elif trip:
                title = tname
        if title:
            labels[path] = title
    return labels


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


# ── Gesamt-Speicherlimit ──────────────────────────────────────────────────────
# Bewusst NICHT im Admin-Panel einstellbar: Ein Limit, das der Inhalts-Admin
# selbst hochdrehen kann, ist keins. Es kommt vom Betreiber — per Umgebungs-
# variable in der compose.yaml oder als Add-on-Option unter Home Assistant.
# 0 (oder nicht gesetzt) heisst unbegrenzt, damit bestehende Installationen ihr
# Verhalten nicht aendern.
#
# Gezaehlt wird alles unter dem Datenordner: Bilder, Bibliothek-PDFs, Logos,
# Mitglieder-Dateien, Anhaenge, Spielstaende, Sicherungen. Liegen die Mitglieder-
# Dateien auf einer SMB-Freigabe, stehen sie ausserhalb dieses Ordners und
# zaehlen damit von selbst nicht mit.

STORAGE_RESCAN_S = 300          # Drift ausgleichen, ohne bei jedem Upload zu zaehlen
_storage_lock = threading.Lock()
_storage_bytes = 0
_storage_stamp = 0.0


def storage_limit_bytes() -> int:
    """Gesamtlimit in Bytes, 0 = unbegrenzt."""
    raw = os.environ.get('MYPAGE_STORAGE_MAX_MB')
    if raw is None or str(raw).strip() == '':
        # load_options() statt load_config(): Was in settings.json steht, pflegt
        # der Admin selbst — genau das soll hier nicht greifen.
        raw = load_options().get('storage_max_mb')
    try:
        mb = int(raw or 0)
    except (TypeError, ValueError):
        mb = 0
    return max(0, mb) * 1048576


def _scan_storage_bytes() -> int:
    total = 0
    for root, _dirs, files in os.walk(_DATA):
        for name in files:
            try:
                total += os.stat(os.path.join(root, name)).st_size
            except OSError:      # waehrend des Zaehlens geloescht — nicht schlimm
                pass
    return total


def storage_used_bytes(refresh: bool = False) -> int:
    """Belegter Platz im Datenordner, gepuffert.

    Der Wert wird nach jedem Schreiben fortgeschrieben (`storage_note_delta`)
    und alle `STORAGE_RESCAN_S` neu gezaehlt. Ohne Puffer laege bei jedem Upload
    ein vollstaendiger Durchlauf ueber alle Dateien im Anfragepfad.
    """
    global _storage_bytes, _storage_stamp
    with _storage_lock:
        if refresh or not _storage_stamp or time.time() - _storage_stamp > STORAGE_RESCAN_S:
            _storage_bytes = _scan_storage_bytes()
            _storage_stamp = time.time()
        return _storage_bytes


def storage_note_delta(n: int) -> None:
    """Bekannte Aenderung einrechnen (positiv beim Schreiben, negativ beim Loeschen)."""
    global _storage_bytes
    with _storage_lock:
        _storage_bytes = max(0, _storage_bytes + int(n))


def storage_room_bytes() -> int | None:
    """Verbleibender Platz bis zum Limit. None = kein Limit gesetzt."""
    limit = storage_limit_bytes()
    if not limit:
        return None
    return max(0, limit - storage_used_bytes())


def storage_would_exceed(extra: int) -> bool:
    room = storage_room_bytes()
    return room is not None and int(extra or 0) > room


# Woraus sich der belegte Platz zusammensetzt. Die Reihenfolge ist die der
# Anzeige; Beschriftungen holt die Oberflaeche ueber `storage_grp_<key>` aus den
# Uebersetzungen, damit hier kein deutscher Text im Code steht.
STORAGE_GROUPS = ('uploads', 'docs', 'logos', 'users', 'member_avatars', 'dm_files',
                  'autobackup', 'revisions', 'games', 'visits', 'wm_cache', 'ai_tmp',
                  'geoip')


def _dir_bytes(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.stat(os.path.join(root, name)).st_size
            except OSError:
                pass
    return total


def storage_breakdown() -> dict:
    """Belegter Platz je Ordner plus Gesamtwerte — Grundlage der Anzeige im Admin.

    `rest` faengt alles ab, was direkt im Datenordner liegt (site.json, stats,
    Schluessel …). So ergibt die Summe der Zeilen immer den Gesamtwert, statt
    dass ein Teil unerklaert fehlt.
    """
    groups = []
    counted = 0
    for key in STORAGE_GROUPS:
        d = Path(_DATA) / key
        if key == 'users' and SMB_MOUNTED:
            continue          # liegt auf der Freigabe, zaehlt nicht mit
        if not d.is_dir():
            continue
        size = _dir_bytes(d)
        counted += size
        if size:
            groups.append({'key': key, 'bytes': size})
    total = storage_used_bytes(refresh=True)
    rest = max(0, total - counted)
    if rest:
        groups.append({'key': 'rest', 'bytes': rest})
    groups.sort(key=lambda g: g['bytes'], reverse=True)
    limit = storage_limit_bytes()
    return {'groups': groups, 'total': total, 'limit': limit,
            'pct': (total * 100 // limit) if limit else 0,
            'disk_free': int((_health_dir_free_mb(_DATA) or 0) * 1048576),
            'smb': SMB_MOUNTED}


def _storage_worker() -> None:
    """Zaehlt im Hintergrund nach, damit der gepufferte Wert nicht wegdriftet."""
    while True:
        time.sleep(STORAGE_RESCAN_S)
        try:
            storage_used_bytes(refresh=True)
        except Exception as e:
            log.warning("Speicherstand konnte nicht ermittelt werden: %s", e)


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
    vol = traffic_totals(stats)
    sensors = [
        ('mypage_views_total',    stats.get('total', 0), 'MyPage Aufrufe gesamt',  'mdi:counter',       'Aufrufe'),
        ('mypage_visitors_total', total_uniques(stats),  'MyPage Besucher gesamt', 'mdi:account-group', 'Besucher'),
        ('mypage_views_today',    today['views'],        'MyPage Aufrufe heute',   'mdi:eye',           'Aufrufe'),
        ('mypage_visitors_today', today['uniques'],      'MyPage Besucher heute',  'mdi:account',       'Besucher'),
        ('mypage_traffic_today',  round(vol['today_out'] / 1048576, 1), 'MyPage Datenvolumen heute', 'mdi:swap-vertical', 'MB'),
        ('mypage_traffic_total',  round(vol['total_out'] / 1048576, 1), 'MyPage Datenvolumen gesamt', 'mdi:database-arrow-up', 'MB'),
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

    def _sum(a: int, b: int) -> tuple[int, int, int]:
        v = u = vol = 0
        for i in range(a, b):
            d = days.get((today - timedelta(days=i)).isoformat())
            if d:
                v += d.get('views', 0)
                u += d.get('uniques', 0)
                # Bots zählen beim Volumen mit — sie belasten die Leitung genauso
                vol += d.get('traffic_out', 0) + d.get('traffic_out_bot', 0)
        return v, u, vol

    views, uniques, traffic = _sum(0, 7)        # letzte 7 Tage (heute … −6)
    prev_views, _, prev_traffic = _sum(7, 14)   # Vorwoche
    cutoff = int(time.time()) - 7 * 86400
    log_week = [v for v in stats.get('log', []) if v.get('ts', 0) >= cutoff]
    pages = top_pages(load_site(), log_week, limit=1)
    cutoff_day = (today - timedelta(days=7)).isoformat()
    new_members = sum(1 for u in load_users() if (u.get('created') or '') >= cutoff_day)
    new_messages = sum(1 for m in load_messages() if m.get('ts', 0) >= cutoff)
    trend = round((views - prev_views) / prev_views * 100) if prev_views else None
    vol_trend = round((traffic - prev_traffic) / prev_traffic * 100) if prev_traffic else None
    return {'views': views, 'uniques': uniques, 'trend': trend,
            'traffic': traffic, 'traffic_trend': vol_trend,
            'top_page': (pages[0] if pages else None),
            'new_members': new_members, 'new_messages': new_messages}


def _weekly_github_token_line() -> str:
    """Zeile zum GitHub-Token für den Wochenrückblick ('' = kein Token gesetzt)."""
    t = check_github_token(force=True)
    if t['state'] == 'missing':
        return ''
    if t['state'] == 'invalid':
        return 'GitHub-Token: ⚠ ungültig oder abgelaufen — bitte erneuern'
    if t['state'] != 'ok':
        return 'GitHub-Token: Prüfung fehlgeschlagen (GitHub nicht erreichbar)'
    if not t.get('expires'):
        return 'GitHub-Token: gültig (kein Ablaufdatum)'
    days, date_txt = t.get('days'), t['expires'][:10]
    if days is None:
        return f'GitHub-Token: gültig bis {date_txt}'
    if days < 0:
        return f'GitHub-Token: ⚠ seit {date_txt} abgelaufen — bitte erneuern'
    if days <= 30:
        return f'GitHub-Token: ⚠ läuft in {days} Tagen ab ({date_txt}) — bitte erneuern'
    return f'GitHub-Token: gültig bis {date_txt} (noch {days} Tage)'


def _send_weekly_review() -> None:
    """Verschickt den Wochenrückblick als HA-Benachrichtigung und (falls SMTP
    konfiguriert) als E-Mail an die Admin-Adresse. Texte bewusst auf Deutsch —
    konsistent zu den übrigen HA-Benachrichtigungen."""
    s = _weekly_summary()

    def _trend(value) -> str:
        if value is None:
            return '—'
        arrow = '▲' if value > 0 else ('▼' if value < 0 else '■')
        return f'{arrow} {abs(value)} % ggü. Vorwoche'

    trend_txt = _trend(s['trend'])
    tp = s['top_page']
    top_txt = (f"{tp.get('title') or tp.get('path')} ({tp['count']})") if tp else '—'
    lines = [
        f"Aufrufe: {s['views']}  ({trend_txt})",
        f"Eindeutige Besucher: {s['uniques']}",
        f"Datenvolumen: {human_size(s['traffic'])}  ({_trend(s['traffic_trend'])})",
        f"Top-Seite: {top_txt}",
        f"Neue Mitglieder: {s['new_members']}",
        f"Neue Nachrichten: {s['new_messages']}",
    ]
    gh_line = _weekly_github_token_line()
    if gh_line:
        lines.append(gh_line)
    notify_ha('📊 MyPage: Wochenrückblick', '\n'.join(lines),
              notification_id='mypage_weekly_review')
    if smtp_configured():
        title = (load_site()['design'].get('site_title') or 'MyPage')
        html = _email_html(f'📊 Wochenrückblick — {title}', lines)
        send_email(f'📊 Wochenrückblick — {title}', html)
    log.info("Wochenrückblick verschickt (Aufrufe %d, Besucher %d, Volumen %s)",
             s['views'], s['uniques'], human_size(s['traffic']))


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


BLOG_PAGE_SIZE = 10           # Beiträge je Seite in der Blog-Übersicht
BLOG_PAGER_WINDOW = 2         # Wie viele Nummern links und rechts der aktuellen


def _page_arg() -> int:
    """Seitenzahl aus `?seite=`, mindestens 1.

    Alles Unbrauchbare wird zu 1 statt zu einem Fehler: eine von Hand
    verbogene Adresse soll die Übersicht zeigen, nicht eine Fehlerseite.
    """
    try:
        return max(1, int(request.args.get('seite') or 1))
    except (TypeError, ValueError):
        return 1


def _blog_page_url(page: int, query: str = '', tag: str = '') -> str:
    """Adresse einer Blog-Seite mit erhaltenem Filter.

    Suche und Schlagwort müssen mitwandern — sonst springt das Blättern in der
    gefilterten Liste zurück auf den vollen Bestand.
    """
    args = []
    if tag:
        args.append(('tag', tag))
    if query:
        args.append(('q', query))
    if page > 1:
        args.append(('seite', str(page)))
    return '/blog' + ('?' + urlencode(args) if args else '')


def blog_pager(posts: list, page: int, query: str = '', tag: str = '') -> dict:
    """Ausschnitt und Blätterleiste für die Blog-Übersicht.

    Die Nummernliste zeigt immer die erste und die letzte Seite sowie ein
    Fenster um die aktuelle; dazwischen steht eine Auslassung. Ohne das wächst
    die Leiste bei hundert Seiten über den Bildschirm hinaus.

    Wichtig: Sitemap und Feed führen weiterhin **alle** Beiträge. Wer dort
    dieselbe Begrenzung einbaut, nimmt dem Suchindex den halben Bestand.
    """
    total = len(posts)
    pages = max(1, (total + BLOG_PAGE_SIZE - 1) // BLOG_PAGE_SIZE)
    page = min(max(1, page), pages)
    start = (page - 1) * BLOG_PAGE_SIZE
    items: list = []
    if pages > 1:
        shown = {1, pages} | {n for n in range(page - BLOG_PAGER_WINDOW,
                                               page + BLOG_PAGER_WINDOW + 1)
                              if 1 <= n <= pages}
        last = 0
        for n in sorted(shown):
            if n - last > 1:
                items.append({'gap': True})
            items.append({'gap': False, 'n': n, 'current': n == page,
                          'url': _blog_page_url(n, query, tag)})
            last = n
    return {
        'posts': posts[start:start + BLOG_PAGE_SIZE],
        # `offset` braucht die Vorlage für die Positionsnummern im ItemList:
        # der erste Beitrag auf Seite 3 ist der einundzwanzigste, nicht der erste.
        'page': page, 'pages': pages, 'total': total, 'items': items, 'offset': start,
        'prev_url': _blog_page_url(page - 1, query, tag) if page > 1 else '',
        'next_url': _blog_page_url(page + 1, query, tag) if page < pages else '',
    }


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


def site_search(site: dict, query: str, loc, viewer_is_member: bool,
                lang: str = 'de') -> list:
    """Seitenweite Volltextsuche über Beiträge, Projekte, Seiten, Bibliothek und
    Reiseblog. Liefert eine Liste {kind, title, title_html, url, snippet, locked}.

    `lang` braucht nur der Reiseblog: dessen Texte liegen im Artikel-Objekt und
    nicht in `<feld>_de`/`<feld>_en`, `loc` greift dort also nicht.
    """
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

    for p in projects_public(site):
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

    for trip in _trav_public_trips(site):
        # Die Reise-Seite ist mit dem Rückblick selbst ein Text und nicht mehr
        # nur ein Inhaltsverzeichnis — also gehört sie in die Suche.
        rc = _trav_recap(trip, lang)
        if rc.get('body'):
            consider('travel', rc.get('title') or trip.get('name') or '',
                     f"/reiseblog/{trip['slug']}",
                     ' '.join([rc.get('teaser') or '', rc.get('body') or '',
                               ' '.join((trip.get('recap') or {}).get('tags') or []),
                               trip.get('destination') or '']),
                     trip.get('members_only'))
        for d in _trav_public_days(trip):
            art = _trav_article(d, lang)
            body = ' '.join([art.get('teaser') or '', art.get('body') or '',
                             ' '.join((d.get('article') or {}).get('tags') or []),
                             d.get('location') or '', trip.get('destination') or ''])
            consider('travel', art.get('title') or '',
                     f"/reiseblog/{trip['slug']}/{d.get('slug', '')}",
                     body, trip.get('members_only'))

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


def blog_public(site: dict) -> bool:
    """Ist der Blog fuer die Website freigegeben? (Admin-Reiter bleibt davon unberuehrt.)

    In einer Vorschau-Sitzung gilt er als freigegeben — sonst liesse sich ein
    Bereich nicht aufbauen, ohne ihn zwischendurch fuer alle einzuschalten.
    """
    return site['design'].get('blog_enabled', True) is not False or preview_active()


def library_public(site: dict) -> bool:
    return site['design'].get('library_enabled', True) is not False or preview_active()


def projects_public(site: dict) -> list:
    """Sichtbare Projekte — leer, solange der Bereich nicht freigegeben ist."""
    if site['design'].get('projects_enabled', True) is False and not preview_active():
        return []
    return [p for p in site.get('projects', []) if project_visible(p)]


def sorted_posts(site: dict, public_only: bool = False) -> list:
    posts = sorted(site.get('posts', []), key=lambda p: p.get('date', ''), reverse=True)
    if not public_only:
        return posts
    return [p for p in posts if post_visible(p)] if blog_public(site) else []


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
            # Letzter Push als Datum des Projekts — ohne das steht ein Projekt
            # im Feed ohne <pubDate> und der Leser sortiert es irgendwohin
            'pushed':      (repo.get('pushed_at') or '')[:10],
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


_gh_token_cache: dict = {'ts': 0.0, 'data': None}


def check_github_token(force: bool = False) -> dict:
    """Prüft den konfigurierten Token gegen GET /user (5 Minuten gecacht)."""
    if (not force and _gh_token_cache['data'] is not None
            and time.time() - _gh_token_cache['ts'] < 300):
        return _gh_token_cache['data']

    token = (load_config().get('github_token') or '').strip()
    if not token:
        res = {'state': 'missing'}
    else:
        try:
            r = http.get(f'{GITHUB_API}/user', headers=_gh_headers(), timeout=10)
            if r.status_code == 200:
                res = {'state': 'ok', 'user': (r.json() or {}).get('login', '')}
                expires = r.headers.get(
                    'GitHub-Authentication-Token-Expiration', '').strip()
                if expires:
                    res['expires'] = expires
                    try:
                        exp = datetime.strptime(expires[:19], '%Y-%m-%d %H:%M:%S')
                        res['days'] = (exp.replace(tzinfo=timezone.utc)
                                       - datetime.now(timezone.utc)).days
                    except ValueError:
                        log.warning("Unbekanntes Token-Ablaufformat")
                for key, hdr in (('rate_limit', 'X-RateLimit-Limit'),
                                 ('rate_remaining', 'X-RateLimit-Remaining')):
                    try:
                        res[key] = int(r.headers.get(hdr, ''))
                    except ValueError:
                        pass
            else:
                res = {'state': 'invalid'}
        except http.exceptions.RequestException:
            log.warning("GitHub-Token-Prüfung fehlgeschlagen")
            res = {'state': 'error'}

    _gh_token_cache.update(ts=time.time(), data=res)
    return res


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
                if r.status_code in (401, 403):
                    log.warning("Sterne-Update abgelehnt (HTTP %d) — GitHub-Token "
                                "prüfen (Admin → System)", r.status_code)
                    health_note('github', f'HTTP {r.status_code}')
                    break
                if r.status_code == 200:
                    health_note('github', ok=True)
                    data = r.json()
                    new_stars = data.get('stargazers_count', p.get('stars', 0))
                    if new_stars != p.get('stars'):
                        p['stars'] = new_stars
                        changed = True
                    # Beim selben Durchlauf das Push-Datum nachziehen: es liefert
                    # dem Feed das <pubDate> und füllt sich so auch für Projekte,
                    # die vor dieser Version importiert wurden
                    pushed = (data.get('pushed_at') or '')[:10]
                    if pushed and pushed != p.get('repo_pushed'):
                        p['repo_pushed'] = pushed
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
    p['repo_pushed']    = _clean_str(raw.get('repo_pushed'), 10)
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


def _unique_slug(wish: str, taken: set, fallback: str,
                 reserved: set | None = None) -> tuple[str, bool]:
    """Eindeutigen Slug bestimmen — und melden, ob er von der Eingabe abweicht.

    Das zweite Rückgabestück ist der eigentliche Zweck: Wer „rhodos" eintippt
    und stillschweigend „rhodos-2" bekommt, sucht seine Seite später an der
    falschen Adresse. Die Oberfläche sagt es deshalb hinterher an.

    Angehängt wird ab 2, weil der vorhandene Eintrag der erste ist.
    """
    reserved = reserved or set()
    base = wish
    if not base or base in reserved:
        return fallback, bool(wish)
    slug, n = base, 2
    while slug in taken or slug in reserved:
        slug = f'{base}-{n}'
        n += 1
    return slug, slug != base


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


def _page_slug(site: dict, raw: dict, page_id: str) -> tuple[str, bool]:
    """Eindeutigen, gültigen Slug ermitteln (aus Eingabe oder Titel abgeleitet)."""
    wish = _slugify(raw.get('slug') or raw.get('title_de') or raw.get('title_en') or '')
    taken = {p['slug'] for p in site.get('pages', []) if p.get('id') != page_id}
    return _unique_slug(wish, taken, 'seite-' + page_id[:6], RESERVED_SLUGS)


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

# Darstellung des Bibliothek-Anrisses auf der Startseite. Alle Varianten nutzen
# dasselbe Karten-Markup, nur die CSS-Klasse am Rail unterscheidet sich —
# siehe „Layout-Varianten der Bibliothek" in templates/public.html.
LIB_LAYOUTS = {'carousel', 'overlay', 'list', 'mini', 'collapsed'}


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
    if lib.get('layout') not in LIB_LAYOUTS:
        lib['layout'] = 'carousel'
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


def _lib_entry_slug(site: dict, raw: dict, entry_id: str) -> tuple[str, bool]:
    wish = _slugify(raw.get('slug') or raw.get('title_de') or raw.get('title_en') or '')
    taken = {e.get('slug') for e in _library(site).get('entries', []) if e.get('id') != entry_id}
    return _unique_slug(wish, taken, 'eintrag-' + entry_id[:6])


def _find_lib_entry(site: dict, slug: str) -> dict | None:
    if not library_public(site):
        return None
    return next((e for e in _library(site).get('entries', []) if e.get('slug') == slug), None)


def _lib_public_entries(site: dict) -> list:
    """Veröffentlichte Einträge (Mitglieder-only bleibt gelistet, nur der Text ist gesperrt).

    Leer, solange die Bibliothek in den Einstellungen nicht für die Website
    freigegeben ist — der Admin-Reiter bleibt davon unberührt.
    """
    if not library_public(site):
        return []
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
_LIB_PDF_LAYOUT = 4

_PDF_TABLE_RE = re.compile(r'(<table\b[^>]*>)(.*?)</table>', re.I | re.S)


def _pdf_mark_tables(html: str) -> str:
    """Hängt jeder Tabelle ihre Spaltenzahl als Klasse an (`t-c6`).

    Das PDF-CSS setzt `table-layout: fixed`, sonst laufen breite Tabellen über
    den Seitenrand hinaus und werden abgeschnitten. Feste Spaltenbreiten teilen
    die Seite aber gleichmäßig auf — ab fünf Spalten wird der Text darin
    unlesbar schmal, wenn die Schrift nicht mitschrumpft. CSS kann Spalten
    nicht zählen, also passiert das hier.
    """
    def repl(m):
        tag, inner = m.group(1), m.group(2)
        rows = re.findall(r'<tr\b.*?</tr>', inner, re.I | re.S)
        n = max((len(re.findall(r'<t[hd]\b', r, re.I)) for r in rows), default=1)
        n = min(max(n, 1), 9)
        if re.search(r'\bclass\s*=', tag, re.I):
            return m.group(0)
        return f'{tag[:-1]} class="t-c{n}">{inner}</table>'

    return _PDF_TABLE_RE.sub(repl, html)


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
    # Zwei Regeln im Stylesheet unten sind nicht offensichtlich:
    # `table-layout: fixed` ist Pflicht — bei `auto` bemisst WeasyPrint die
    # Spalten am Inhalt und schiebt breite Tabellen über den Seitenrand, der
    # Überhang wird abgeschnitten. Und `page-break-inside: avoid` gehört auf
    # die Zeile, nicht auf die Tabelle: eine Tabelle, die länger als eine Seite
    # ist, wandert sonst komplett auf die nächste und lässt den Rest der vorigen
    # Seite leer. `word-break: break-word` gibt es nicht — WeasyPrint verwirft
    # es mit einer Warnung; `overflow-wrap: anywhere` ist die gültige Form.
    return f"""<!DOCTYPE html><html lang="{escape(lang)}"><head><meta charset="utf-8">
<title>{escape(loc(entry, 'title'))}</title><style>
@page {{ size: A4; margin: 20mm 18mm 18mm;
  @bottom-center {{ content: "{escape(page_label)} " counter(page) " / " counter(pages);
                    font-size: 9pt; color: #666; }} }}
body {{ font-family: "DejaVu Sans", sans-serif; font-size: 10.5pt; line-height: 1.55; color: #111;
        hyphens: auto; }}
h1.doc-title {{ font-size: 20pt; margin: 0 0 2mm; color: {escape(accent)}; }}
.doc-sub {{ font-size: 9pt; color: #666; margin-bottom: 8mm;
            border-bottom: 1px solid #ddd; padding-bottom: 3mm; }}
h1, h2, h3 {{ line-height: 1.25; margin: 6mm 0 2mm; page-break-after: avoid; }}
h2 {{ font-size: 14pt; }} h3 {{ font-size: 12pt; }}
p {{ margin: 0 0 3mm; orphans: 2; widows: 2; }} ul, ol {{ margin: 0 0 3mm 6mm; }}
li {{ orphans: 2; widows: 2; }}
img {{ max-width: 100%; }}
a {{ overflow-wrap: anywhere; }}
blockquote {{ border-left: 2pt solid {escape(accent)}; margin: 3mm 0; padding: 0 4mm; color: #444; }}
pre {{ background: #f4f4f4; padding: 3mm; border-radius: 2mm; white-space: pre-wrap;
       font-family: "DejaVu Sans Mono", monospace; font-size: 9pt; }}
code {{ font-family: "DejaVu Sans Mono", monospace; font-size: 9pt; }}
table {{ border-collapse: collapse; width: 100%; margin: 3mm 0; table-layout: fixed; }}
thead {{ display: table-header-group; }}
tr {{ page-break-inside: avoid; }}
th, td {{ border: 0.5pt solid #bbb; padding: 1.5mm 2mm; text-align: left; font-size: 9.5pt;
          vertical-align: top; overflow-wrap: anywhere; }}
th {{ background: #f0f0f0; }}
table.t-c4 th, table.t-c4 td {{ font-size: 8.5pt; padding: 1.2mm 1.5mm; }}
table.t-c5 th, table.t-c5 td {{ font-size: 8pt; padding: 1mm 1.2mm; line-height: 1.4; }}
table.t-c6 th, table.t-c6 td, table.t-c7 th, table.t-c7 td,
table.t-c8 th, table.t-c8 td, table.t-c9 th, table.t-c9 td
  {{ font-size: 7pt; padding: 0.8mm 1mm; line-height: 1.3; }}
hr {{ border: none; border-top: 0.5pt solid #ccc; margin: 5mm 0; }}
</style></head><body>
<h1 class="doc-title">{escape(loc(entry, 'title'))}</h1>
{f'<div class="doc-sub">{escape(subtitle)}</div>' if subtitle else ''}
{_pdf_mark_tables(_overlay_html_images(render_md(loc(entry, 'body'))))}
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


def _form_slug(site: dict, raw: dict, form_id: str) -> tuple[str, bool]:
    wish = _slugify(raw.get('slug') or raw.get('title_de') or raw.get('title_en') or '')
    taken = {f['slug'] for f in site.get('forms', []) if f.get('id') != form_id}
    return _unique_slug(wish, taken, 'formular-' + form_id[:6])


def _public_forms(site: dict) -> list:
    """Formulare, die öffentlich erreichbar sind.

    Der Schalter unter Design → Module steuert die Website als Ganzes, der
    Schalter am Formular das einzelne Formular. Beides muss zusammenkommen.
    """
    if not site['design'].get('forms_enabled', True) and not preview_active():
        return []
    return [f for f in site.get('forms', []) if f.get('enabled') and f.get('slug')]


def _nav_forms(site: dict, loc) -> list:
    """Aktive Formulare mit gesetztem Navi-Schalter."""
    out = []
    for f in _public_forms(site):
        if f.get('nav'):
            label = loc(f, 'title')
            if label:
                out.append({'href': '/formular/' + f['slug'], 'label': label})
    return out


def _nav_links(site: dict, loc, t: dict | None = None, with_library: bool = True,
               with_travel: bool = True, with_forms: bool = True) -> list:
    """Navi-Einträge für Bibliothek, Reiseblog, eigene Seiten und Formulare.

    Auf der Startseite stecken Bibliothek, Reiseblog und Formulare bereits als
    Abschnitt in der Sektions-Navigation (Anker `#library`, `#reiseblog`,
    `#formulare`) — dort jeweils mit `False`, sonst stünden sie doppelt in der
    Leiste. Auf den Unterseiten sind es die einzigen Wege zurück.
    """
    lib = _nav_library(site, loc, t or {}) if with_library else []
    trav = _nav_travel(site, loc, t or {}) if with_travel else []
    forms = _nav_forms(site, loc) if with_forms else []
    return lib + trav + _nav_pages(site, loc) + forms


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
    """Läuft die Anfrage über den HA-Ingress (dann hat HA schon angemeldet)?

    Die Entscheidung fällt in `_IngressMiddleware` anhand der Absenderadresse
    und steht als Merker in der Umgebung. Bewusst nicht mehr über
    `request.script_root`: den setzt eine Kopfzeile, die jeder mitschicken kann.
    """
    return bool(request.environ.get('mypage.ingress'))


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
        clear_failed_attempts(ip, _peer_addr(request))
        hours = int(cfg.get('session_hours', 24))
        token = create_session(hours)
        log_audit('admin_login')
        resp = make_response(redirect(url_for('admin_index')))
        resp.set_cookie('session', token, httponly=True, samesite='Lax',
                        secure=_cookie_secure(), max_age=hours * 3600)
        resp.delete_cookie('pre2fa')
        return resp

    def _grant_session_trusted(ip):
        resp = _grant_session(ip)
        if request.form.get('remember_device'):
            token = create_trusted_session()
            if token:
                cookie_value = _trusted_cookie_serializer().dumps(token)
                resp.set_cookie('trust2fa', cookie_value, httponly=True, samesite='Lax',
                                 secure=_cookie_secure(),
                                 max_age=TRUSTED_DEVICE_DAYS * 86400)
        return resp

    if request.method == 'POST':
        ip = get_client_ip(request)
        peer = _peer_addr(request)
        if is_rate_limited(ip, peer):
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
            record_failed_attempt(ip, peer)
            log_audit('admin_login_2fa_failed')
            error = t.get('error_2fa_code', 'Ungültiger Code.')
            step = 'code'
        else:
            # Schritt 1: Benutzername + Passwort
            uname = request.form.get('username', '')
            pwd   = request.form.get('password', '')
            if (secrets.compare_digest(uname, admin_username())
                    and admin_password_ok(pwd)):
                if twofa_enabled() and not is_trusted_session_valid(request.cookies.get('trust2fa')):
                    pre = _pending_2fa_new()
                    resp = make_response(render_template('login.html', t=t, lang=lang,
                                                         error=None, step='code'))
                    resp.set_cookie('pre2fa', pre, httponly=True, samesite='Lax',
                                    secure=_cookie_secure(), max_age=PENDING_2FA_TTL)
                    return resp
                return _grant_session(ip)
            record_failed_attempt(ip, peer)
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
    account = admin_username()
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


# Regeln wie bei den Mitgliedern: sichtbare Zeichen, keine Leerzeichen.
_ADMIN_USER_RE = re.compile(r'^[A-Za-z0-9._@-]{3,64}$')


@admin_app.route('/api/preview-link', methods=['POST'])
def api_preview_link():
    """Vorschau-Link erzeugen. Zeigt die echte Seite trotz Wartungsmodus."""
    err = _api_auth()
    if err:
        return err
    hours = int((request.get_json(silent=True) or {}).get('hours') or 0)
    if hours not in PREVIEW_HOURS:
        return jsonify({'error': 'bad_hours'}), 400
    site = load_site()
    # Die eingetragene oeffentliche Adresse zuerst: Der Link soll auf die Seite
    # zeigen, wie Besucher sie erreichen — nicht auf den Admin-Host.
    base = (site['design'].get('public_url') or '').rstrip('/')
    if not base:
        host = (request.host or '').split(':')[0]
        base = f'{request.scheme}://{host}:{PUBLIC_PORT}'
    token = preview_token(hours)
    log_audit('preview_link', f'{hours} h')
    return jsonify({'url': f'{base}/?{PREVIEW_PARAM}={token}',
                    'hours': hours,
                    'expires': int(time.time()) + hours * 3600,
                    'public_url_set': bool(site['design'].get('public_url'))})


@admin_app.route('/api/preview-link/revoke', methods=['POST'])
def api_preview_revoke():
    """Alle ausgegebenen Vorschau-Links auf einen Schlag ungültig machen."""
    err = _api_auth()
    if err:
        return err
    preview_revoke()
    log_audit('preview_revoke')
    log.info("Vorschau-Links zurückgezogen")
    return jsonify({'ok': True})


@admin_app.route('/api/diskuse')
def api_diskuse():
    """Belegter Platz je Ordner. Reine Anzeige — das Limit selbst ist hier nicht
    zu ändern, es kommt aus der Add-on-Konfiguration bzw. der compose.yaml."""
    err = _api_auth()
    if err:
        return err
    return jsonify(storage_breakdown())


@admin_app.route('/api/admin-login')
def api_admin_login_state():
    err = _api_auth()
    if err:
        return err
    return jsonify({'on_ha': ON_SUPERVISOR,
                    'username': admin_username(),
                    'initial': admin_login_is_initial(),
                    'twofa': twofa_enabled(),
                    'min_len': ADMIN_PW_MIN_LEN})


@admin_app.route('/api/admin-login', methods=['POST'])
def api_admin_login_change():
    """Benutzername und Passwort des Admins ändern (nur ohne Home Assistant).

    Verlangt das aktuelle Passwort — und bei aktiver 2FA zusätzlich einen Code.
    Sonst könnte eine offene Sitzung an einem unbeaufsichtigten Rechner den
    Zugang übernehmen. Danach fliegen alle übrigen Sitzungen raus.
    """
    err = _api_auth()
    if err:
        return err
    if ON_SUPERVISOR:
        return jsonify({'error': 'on_ha'}), 400
    body = request.get_json(silent=True) or {}
    if (gate := _key_gate_check(body.get('current'), body.get('code'),
                                'admin_password_denied')):
        return gate
    new = str(body.get('new') or '')
    if (perr := password_policy_error(new)):
        return jsonify({'error': perr}), 400
    uname = _clean_str(body.get('username'), 64) or admin_username()
    if not _ADMIN_USER_RE.match(uname):
        return jsonify({'error': 'bad_username'}), 400
    set_admin_credentials(uname, new)
    ended = invalidate_admin_sessions(request.cookies.get('session'))
    log_audit('admin_password_changed', uname)
    log.info("Admin-Zugang geändert (Benutzer '%s') — %d weitere Sitzung(en) beendet",
             uname, ended)
    return jsonify({'ok': True, 'username': uname, 'sessions_ended': ended})


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
    return render_template('admin.html', t=t, lang=lang, ingress=_is_ingress(),
                           on_ha=ON_SUPERVISOR)


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
    if isinstance(raw.get('cta'), list):
        prof['cta'] = [{
            'label_de': _clean_str(e.get('label_de'), 40),
            'label_en': _clean_str(e.get('label_en'), 40),
            'url':      _clean_str(e.get('url'), 300),
        } for e in raw['cta'][:2]
            if isinstance(e, dict)
            and (_clean_str(e.get('label_de'), 40) or _clean_str(e.get('label_en'), 40))
            # Ziel darf eine Sprungmarke, eine eigene Adresse oder eine fremde
            # Seite sein — aber nichts, was der Browser als Skript ausführt.
            and _clean_str(e.get('url'), 300).startswith(('#', '/', 'http://', 'https://', 'mailto:'))]
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
    if raw.get('entity_type') in ('person', 'organization', 'localbusiness'):
        d['entity_type'] = raw['entity_type']
    if raw.get('hero_layout') in ('side', 'center', 'banner'):
        d['hero_layout'] = raw['hero_layout']
    if raw.get('avatar_shape') in ('circle', 'rounded', 'free'):
        d['avatar_shape'] = raw['avatar_shape']
    if 'hero_image' in raw:
        d['hero_image'] = _clean_str(raw['hero_image'], 500)
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
                 'dm_ha_notify', 'directory_enabled', 'search_enabled', 'weekly_review',
                 'travel_enabled', 'forms_enabled', 'feed_projects', 'feed_library',
                 'blog_enabled', 'library_enabled', 'projects_enabled',
                 'visit_archive'):
        if flag in raw:
            d[flag] = bool(raw[flag])
    if 'default_lang' in raw:
        dl = _clean_str(raw['default_lang'], 4).lower()
        d['default_lang'] = dl if dl in ('de', 'en', 'auto') else 'de'
    if 'feed_lang' in raw:
        fl = _clean_str(raw['feed_lang'], 2).lower()
        d['feed_lang'] = fl if fl in ('de', 'en') else 'de'
    if 'ai_address' in raw:
        a = _clean_str(raw['ai_address'], 4).lower()
        d['ai_address'] = a if a in AI_ADDRESS_FORMS else 'sie'
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
    if isinstance(raw.get('section_titles'), dict):
        # Nur bekannte Abschnitte, und leere Paare fliegen raus: sonst wächst die
        # Ablage mit jedem Speichern um leere Einträge für alle 20 Module.
        titles = {}
        for key, val in raw['section_titles'].items():
            if key not in SECTION_TITLE_KEYS or not isinstance(val, dict):
                continue
            de = _clean_str(val.get('de'), 60)
            en = _clean_str(val.get('en'), 60)
            if de or en:
                titles[key] = {'de': de, 'en': en}
        sec['section_titles'] = titles
        # Der Werdegang wird ab hier aus der gemeinsamen Ablage bedient. Die alten
        # Felder mitzuziehen hält site.json widerspruchsfrei, falls doch noch
        # etwas daraus liest.
        tl = titles.get('timeline') or {}
        sec['timeline_title_de'], sec['timeline_title_en'] = tl.get('de', ''), tl.get('en', '')
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
    if isinstance(raw.get('facts'), list):
        # Die Zahl bleibt Text: „500+", „24/7" und „~3 Mio." sind genauso
        # gemeint wie eine glatte Zahl, und gerechnet wird damit nirgends.
        sec['facts'] = [{
            'value':    _clean_str(e.get('value'), 20),
            'label_de': _clean_str(e.get('label_de'), 60),
            'label_en': _clean_str(e.get('label_en'), 60),
            'icon':     _clean_str(e.get('icon'), 8),
        } for e in raw['facts'][:12]
            if isinstance(e, dict) and _clean_str(e.get('value'), 20)]
    if isinstance(raw.get('partners'), list):
        sec['partners'] = [{
            'name': _clean_str(e.get('name'), 80),
            'logo': _clean_str(e.get('logo'), 500),
            'url':  _clean_str(e.get('url'), 500) if _clean_str(e.get('url'), 500).startswith(('http://', 'https://')) else '',
        } for e in raw['partners'][:40]
            if isinstance(e, dict) and _clean_str(e.get('name'), 80)]
    if isinstance(raw.get('videos'), list):
        # Nur was `parse_video()` erkennt: eine beliebige Adresse als iframe zu
        # laden hieße, jeder fremden Seite den Rahmen zu öffnen.
        sec['videos'] = [{
            'url':      _clean_str(e.get('url'), 500),
            'title_de': _clean_str(e.get('title_de'), 160),
            'title_en': _clean_str(e.get('title_en'), 160),
            'desc_de':  _clean_str(e.get('desc_de'), 500),
            'desc_en':  _clean_str(e.get('desc_en'), 500),
        } for e in raw['videos'][:20]
            if isinstance(e, dict) and parse_video(_clean_str(e.get('url'), 500))[1]]
    if isinstance(raw.get('downloads'), list):
        # Der Dateiname muss dem Muster der Ablage entsprechen (UUID + Endung),
        # sonst zeigt ein selbst gesetzter Eintrag später auf eine fremde Datei.
        sec['downloads'] = [{
            'file':     _clean_str(e.get('file'), 80),
            'title_de': _clean_str(e.get('title_de'), 160),
            'title_en': _clean_str(e.get('title_en'), 160),
            'desc_de':  _clean_str(e.get('desc_de'), 400),
            'desc_en':  _clean_str(e.get('desc_en'), 400),
        } for e in raw['downloads'][:60]
            if isinstance(e, dict) and _DOC_FILE_RE.match(_clean_str(e.get('file'), 80) or '')
            and (_clean_str(e.get('title_de'), 160) or _clean_str(e.get('title_en'), 160))]
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
        # settings.json kommt mit, settings.key bewusst NICHT: so stehen Tokens
        # und Passwörter im Backup nur verschlüsselt, und wer das Zip in die
        # Hände bekommt, kann sie nicht lesen. Preis: nach einem Restore auf
        # einer frischen Installation (ohne alten Schlüssel) müssen die
        # geheimen Felder einmal neu eingetragen werden.
        for name in ('site.json', 'stats.json', 'messages.json', 'users.json',
                     'comments.json', 'audit.json', 'subscribers.json',
                     'dm.json', 'dm.key', 'admin_2fa.json', 'secret.key',
                     'ai_usage.json', 'travel.json', 'ai_drafts.json',
                     'ai_prompts.json', 'uploads_meta.json', 'settings.json'):
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
        # Logo-Sätze (logos/<slug>/<datei>) — anders als die KI-Entwürfe sind das
        # fertige Arbeitsergebnisse, die niemand ein zweites Mal erzeugen will
        if LOGOS_DIR.is_dir():
            for d in sorted(LOGOS_DIR.iterdir()):
                if not d.is_dir() or not LOGO_SLUG_RE.match(d.name):
                    continue
                for f in sorted(d.iterdir()):
                    if f.is_file() and LOGO_FILE_RE.match(f.name):
                        z.write(f, f'logos/{d.name}/{f.name}')


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
        health_note('backup', str(e)[:200])
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return None
    log.info("Automatisches Backup erstellt: %s (%.1f MB)",
             target.name, target.stat().st_size / 1048576)
    health_note('backup', ok=True)
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
            room = storage_room_bytes()
            if keep > 0 and room is not None and room <= 0:
                # Voll: die vorhandenen Sicherungen ausduennen statt eine weitere
                # anzulegen. Sie sind das Erste, was Platz freigibt, ohne dass
                # Inhalte verloren gehen.
                _rotate_auto_backups(max(1, keep - 1))
                log.warning("Speicherlimit erreicht — kein neues automatisches Backup, "
                            "Aufbewahrung vorübergehend auf %d Datei(en) verkürzt", max(1, keep - 1))
            elif keep > 0:
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


# ── Revisionen: früheren Stand der Seiteninhalte ansehen und zurückholen ────

def _revision_path(name: str) -> Path | None:
    """Pfad zu einer Revision — nur exakt passende Namen, sonst None."""
    if not _REVISION_RE.match(name or ''):
        return None
    return safe_under(REVISIONS_DIR, name)


@admin_app.route('/api/revisions')
def api_revisions_list():
    err = _api_auth()
    if err:
        return err
    keep = _revision_keep()
    revs = list_revisions()
    # Was sich geändert hat, wird beim Auflisten aus den Dateien selbst
    # ermittelt: jede Revision gegen ihre Vorgängerin, die neueste gegen den
    # aktuellen Stand. Eine mitgeführte Indexdatei wäre schneller, könnte aber
    # von den Dateien abweichen — und dann zeigt die Liste Unsinn an.
    def read(name: str):
        try:
            with open(REVISIONS_DIR / name, encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    newer = None
    try:
        with open(SITE_PATH, encoding='utf-8') as f:
            newer = json.load(f)
    except (OSError, ValueError):
        pass
    for r in revs:
        older = read(r['name'])
        r['changed'] = (_site_changed_keys(older, newer)
                        if older is not None and newer is not None else [])
        newer = older if older is not None else newer
    return jsonify({'revisions': revs, 'keep': keep})


@admin_app.route('/api/revisions/<name>')
def api_revision_download(name: str):
    err = _api_auth()
    if err:
        return err
    f = _revision_path(name)
    if f is None or not f.is_file():
        return jsonify({'error': 'not found'}), 404
    return send_file(f, mimetype='application/json', as_attachment=True,
                     download_name=f.name)


@admin_app.route('/api/revisions/<name>/restore', methods=['POST'])
def api_revision_restore(name: str):
    err = _api_auth()
    if err:
        return err
    f = _revision_path(name)
    if f is None or not f.is_file():
        return jsonify({'error': 'not found'}), 404
    try:
        with open(f, encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError) as e:
        log.warning("Revision %s ist nicht lesbar: %s", name, e)
        return jsonify({'error': 'unreadable'}), 400
    if not isinstance(data, dict):
        return jsonify({'error': 'unreadable'}), 400
    # Der Stand vor der Rückkehr wird selbst zur Revision — sonst wäre ein
    # versehentlich zurückgeholter Stand nicht mehr rückgängig zu machen.
    # `force`, weil das Zusammenfassen sonst genau hier zuschlägt: wer eben
    # gespeichert hat und dann zurückholt, liegt innerhalb des Zeitfensters.
    with _site_lock:
        try:
            _snapshot_site(force=True)
        except Exception as e:
            log.warning("Stand vor der Rückkehr konnte nicht gesichert werden: %s", e)
        try:
            _atomic_write_json(SITE_PATH, data, indent=2)
        except Exception as e:
            log.warning("Revision %s konnte nicht eingespielt werden: %s", name, e)
            return jsonify({'error': 'restore failed'}), 500
    log_audit('revision_restore', name)
    return jsonify({'ok': True})


@admin_app.route('/api/revisions/<name>', methods=['DELETE'])
def api_revision_delete(name: str):
    err = _api_auth()
    if err:
        return err
    f = _revision_path(name)
    if f is None or not f.is_file():
        return jsonify({'error': 'not found'}), 404
    try:
        f.unlink()
    except OSError:
        log.warning("Revision '%s' konnte nicht gelöscht werden", f.name)
        return jsonify({'error': 'delete failed'}), 500
    log_audit('revision_delete', f.name)
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
                              'admin_2fa.json', 'ai_usage.json', 'travel.json',
                              'ai_drafts.json', 'ai_prompts.json',
                              'uploads_meta.json', 'settings.json'):
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
                elif member.startswith('logos/'):
                    # Einzige Stelle mit Unterordner im Backup: logos/<slug>/<datei>.
                    # Beide Teile einzeln prüfen, damit aus dem Zip kein Pfad
                    # entstehen kann, der LOGOS_DIR verlässt.
                    parts = member.split('/')
                    if len(parts) != 3 or not LOGO_SLUG_RE.match(parts[1]):
                        continue
                    if not LOGO_FILE_RE.match(parts[2]):
                        continue
                    sub = safe_under(LOGOS_DIR, parts[1])
                    if sub is None:
                        continue
                    sub.mkdir(parents=True, exist_ok=True)
                    target = safe_under(sub, parts[2])
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
    settings_store.reset_cache()  # settings.json kann aus dem Backup stammen
    _settings_changed()
    log_audit('restore', f'{restored} Datei(en)')
    log.info("Backup wiederhergestellt: %d Datei(en)", restored)
    return jsonify({'ok': True, 'restored': restored})


# Obergrenze je Rechtstext. Eine ausführliche Datenschutzerklärung aus einem
# Generator liegt schnell bei 30 000–60 000 Zeichen; die frühere Grenze von
# 20 000 hat solche Texte mitten im Satz abgeschnitten, ohne es zu sagen.
LEGAL_TEXT_MAX = 150_000


@admin_app.route('/api/legal', methods=['POST'])
def api_legal():
    err = _api_auth()
    if err:
        return err
    raw = request.get_json(silent=True) or {}
    site = load_site()
    legal = site['legal']
    cut = False
    for k in ('impressum_de', 'impressum_en', 'privacy_de', 'privacy_en'):
        if k in raw:
            legal[k] = _clean_str(raw[k], LEGAL_TEXT_MAX)
            cut = cut or len(str(raw[k] or '')) > LEGAL_TEXT_MAX
    save_site(site)
    log_audit('settings_legal')
    # Stilles Abschneiden wäre hier besonders unangenehm: eine gekürzte
    # Datenschutzerklärung sieht vollständig aus und ist es nicht.
    return jsonify({'ok': True, 'truncated': cut, 'max': LEGAL_TEXT_MAX})


# Rechtstexte kommen von Generatoren wie e-Recht24 als PDF. Abtippen ist mühsam
# und verliert jede Auszeichnung — deshalb hier der Weg über die Datei. Gespeichert
# wird nichts: die Antwort geht in die Vorschau, übernommen wird erst mit „Speichern".
LEGAL_PDF_MAX_BYTES = 20 * 1024 * 1024


@admin_app.route('/api/legal/import-pdf', methods=['POST'])
def api_legal_import_pdf():
    err = _api_auth()
    if err:
        return err
    f = request.files.get('file')
    if f is None or not f.filename:
        return jsonify({'error': 'no_file'}), 400
    if not f.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'not_pdf'}), 400
    data = f.read(LEGAL_PDF_MAX_BYTES + 1)
    if len(data) > LEGAL_PDF_MAX_BYTES:
        return jsonify({'error': 'too_large'}), 413
    if not data.startswith(b'%PDF'):
        return jsonify({'error': 'not_pdf'}), 400
    try:
        res = pdfimport.extract(data)
    except ValueError as e:
        # Nur die eigenen, bekannten Kennungen zurückgeben — nie den Text einer
        # Ausnahme, der könnte Pfade oder Dateiinhalte enthalten. Der Ausnahme-
        # text dient dabei ausschließlich als Schlüssel; hinausgegeben wird der
        # feste Wert aus dieser Zuordnung, nie die Zeichenkette selbst.
        code = {'no_text': 'no_text',
                'too_many_pages': 'too_many_pages'}.get(str(e), 'unreadable')
        return jsonify({'error': code}), 400
    except Exception:
        log.warning("PDF-Import fehlgeschlagen (%s)", f.filename[:80], exc_info=True)
        return jsonify({'error': 'unreadable'}), 400
    # Vorschau mit derselben Funktion rendern, die auch die öffentliche Seite
    # benutzt — was hier steht, steht später genauso auf der Website.
    res['html'] = render_md(res['markdown'])
    log_audit('legal_import_pdf')
    return jsonify(res)


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
    page['slug'], slug_changed = _page_slug(site, raw, page['id'])
    site.setdefault('pages', []).append(page)
    save_site(site)
    return jsonify({'ok': True, 'slug': page['slug'], 'slug_changed': slug_changed})


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
    pages[idx]['slug'], slug_changed = _page_slug(site, raw, pid)
    save_site(site)
    return jsonify({'ok': True, 'slug': pages[idx]['slug'], 'slug_changed': slug_changed})


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
# Überarbeiten statt neu schreiben: der vorhandene Text geht mit in die Anfrage
# zurück. Sonst bliebe nur „nochmal erzeugen", und das wirft die Handarbeit weg.
AI_TEXT_ACTIONS = ('shorter', 'longer', 'polish', 'custom')
AI_TEXT_NOTE_MAX = 500
# Der ganze Beitrag geht in die Anfrage für die SEO-Beschreibung. Der Deckel
# ist grosszügig, aber nicht offen: ein versehentlich eingefügtes Buch soll
# nicht Token für Token bei Google landen.
AI_SEO_TEXT_MAX = 12_000
AI_INSTRUCTIONS_MAX = 800           # Dauervorgaben, hängen an jedem Textlauf
AI_DRAFTS_MAX = 200                 # ältester Entwurf fliegt raus, wenn voll
AI_PROMPTS_MAX = 100                # dasselbe für die Prompt-Bibliothek
UPLOAD_ALT_MAX = 300                # Alternativtext je Sprache; 125 sind empfohlen
# Ein gespeichertes Vorlagenbild ist eine eigene Upload-Adresse und nichts
# anderes — der Wert landet im Browser in einem <img src> und in einer Anfrage.
_UPLOAD_PATH_RE = re.compile(r'^/uploads/[A-Za-z0-9._-]+$')
AI_DRAFT_TEXT_MAX = 60_000          # ein „langer" Artikel liegt bei ~6 kB
AI_TRANSLATE_PROVIDERS = ('mymemory', 'gemini')
# Interner Fehlercode -> Code fuer das Frontend. `model_missing` ist der Fall,
# der eine eigene Meldung braucht: nicht kaputt, sondern falsch eingestellt.
_AI_ERRORS = {'refused': 'ai_refused', 'empty': 'ai_empty',
              'model_missing': 'ai_model_missing'}

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


# Dauervorgaben des Admins („duzen", „keine Emojis", Eigennamen). Sie gehören in
# die Systemanweisung, nicht in den Auftrag: dort gelten sie für jeden Lauf und
# überleben auch das Überarbeiten.
def _ai_instructions() -> str:
    return _clean_str(_ai_settings().get('instructions'), AI_INSTRUCTIONS_MAX)


# Anrede der KI-Texte. Sie steht im Design und nicht bei den KI-Einstellungen:
# es ist eine Frage des Tonfalls der Website, nicht eine des Modells.
AI_ADDRESS_FORMS = ('sie', 'du')


def _ai_address_note(site: dict | None = None) -> str:
    """Anredezeile fuer jeden KI-Text — haengt an jedem System-Prompt.

    Ohne sie siezt Gemini auf Deutsch von sich aus, auch wenn die uebrige
    Website durchweg duzt.
    """
    d = (site or load_site()).get('design', {})
    form = d.get('ai_address') if d.get('ai_address') in AI_ADDRESS_FORMS else 'sie'
    if form == 'du':
        return ("\n\nAnrede: Sprich den Leser mit „du“ an (klein geschrieben), locker "
                "und direkt — keine Höflichkeitsform, kein „Sie“. Englische Fassungen "
                "bleiben beim neutralen „you“.")
    return ("\n\nAnrede: Sprich den Leser mit „Sie“ an, höflich und sachlich. "
            "Englische Fassungen bleiben beim neutralen „you“.")


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


def _resp_text(resp) -> str:
    """Textteile einer Antwort zusammenfassen.

    Liefert Gemini statt eines Bildes eine Erklärung, steht sie genau hier. Sie
    wegzuwerfen war der Grund, warum ein Fehlschlag nur „fehlgeschlagen" hiess.
    """
    out = []
    for part in (getattr(resp, 'parts', None) or []):
        text = (getattr(part, 'text', '') or '').strip()
        if text:
            out.append(text)
    return ' '.join(out)[:400]


def _gemini_generate_image(prompt: str, *, model: str = '', ratio: str = '',
                           ref: tuple[bytes, str] | None = None
                           ) -> tuple[bytes | None, str, str, str]:
    """Erzeugt ein Bild über Gemini.

    Zurück: (Bilddaten, MIME-Typ, Fehlercode, Erläuterung). Die Erläuterung ist
    das, was Gemini selbst dazu geschrieben hat — bei einer Absage steht dort
    der Grund, und der hilft mehr als jede eigene Vermutung.

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
        finish = cands[0].finish_reason if cands else None
        reason = getattr(finish, 'name', None) or (str(finish) if finish else '')
        if finish in _GEMINI_IMAGE_REFUSALS:
            log.info("Gemini hat die Bildanfrage abgelehnt: %s", finish)
            _ai_usage_record(model, resp)
            return None, '', 'refused', _resp_text(resp) or reason
        for part in (resp.parts or []):
            if part.inline_data is not None and part.inline_data.data:
                _ai_usage_record(model, resp, images=1)
                return (part.inline_data.data,
                        part.inline_data.mime_type or 'image/png', '', '')
        _ai_usage_record(model, resp)
    except genai_errors.APIError as e:
        # Bewusst nur der Statuscode: die Meldung des SDK kann die vollständige
        # Anfrage-URL samt API-Key enthalten, die hat im Add-on-Log nichts zu suchen.
        code = getattr(e, 'code', None)
        log.warning("Gemini-Bildanfrage fehlgeschlagen (%s): Status %s",
                    model, code or type(e).__name__)
        # 404 heißt hier nicht „Ausfall", sondern „diesen Modellnamen gibt es
        # nicht (mehr)". Ohne eigene Meldung sucht der Nutzer den Fehler bei sich.
        return None, '', ('model_missing' if code == 404 else 'failed'), f'HTTP {code}' if code else ''
    except Exception as e:
        # Absichtlich breit: SDK-interne Fehler dürfen nicht als HTML-Fehlerseite
        # beim Frontend landen, das ausschließlich JSON erwartet.
        log.error("Gemini-Bildanfrage (%s) unerwartet fehlgeschlagen: %s: %s",
                  model, type(e).__name__, e)
        return None, '', 'failed', type(e).__name__
    # 200, aber kein Bild: Grund und Erlaeuterung sind hier die einzige Auskunft.
    # Frueher ging beides verloren und der Nutzer sah nur "fehlgeschlagen".
    note = _resp_text(resp)
    block = getattr(getattr(resp, 'prompt_feedback', None), 'block_reason', None)
    log.warning("Gemini-Antwort (%s) enthielt kein Bild — finish_reason=%s block_reason=%s%s",
                model, reason or '?', block or '-', (': ' + note) if note else '')
    return None, '', 'empty', note or ' / '.join(
        x for x in (reason, getattr(block, 'name', None) or (str(block) if block else '')) if x)


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
    data, _mime, code, detail = _gemini_generate_image(prompt)
    if code:
        return jsonify({'error': _AI_ERRORS.get(code, 'ai_failed'), 'detail': detail,
                        'model': _gemini_image_model()}), 502
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
        'instructions': _ai_instructions(),
        'image_used': img_used, 'image_max': AI_IMAGE_MAX_PER_HOUR,
        'text_used': txt_used, 'text_max': AI_TEXT_MAX_PER_HOUR,
        'max_images': AI_STUDIO_MAX_IMAGES,
        # Der Logo-Designer rechnet auch ohne Schlüssel — für den Weg über ein
        # eigenes Bild braucht er nur Pillow
        'logo': _HAS_PIL,
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
    # Leerer Text ist eine gültige Angabe: er löscht die Dauervorgaben wieder
    if 'instructions' in raw:
        ai['instructions'] = _clean_str(raw.get('instructions'), AI_INSTRUCTIONS_MAX)
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
    images, last, last_detail = [], 'failed', ''
    for _ in range(count):
        data, mime, code, detail = _gemini_generate_image(prompt, model=model,
                                                          ratio=ratio, ref=ref)
        if code:
            last, last_detail = code, detail
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
        return jsonify({'error': _AI_ERRORS.get(last, 'ai_failed'),
                        'detail': last_detail, 'model': model}), 502
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


# ── Logo-Designer ─────────────────────────────────────────────────────────────
#
# Ein Logo ist kein Titelbild. Es braucht exakte Pixelmaße statt eines
# Seitenverhältnisses, PNG statt WebP, meist einen freigestellten Hintergrund —
# und auf keinen Fall ein eingebranntes „KI generiert". Deshalb eine eigene
# Ablage (LOGOS_DIR) und eine eigene Aufbereitung, statt `_store_upload_image`
# zu verbiegen: dessen Zusagen (WebP, 1600 px, Kennzeichnung) sind für Uploads
# richtig und für Logos genau verkehrt.
#
# Gemini liefert nur Seitenverhältnisse. Die Maße rechnet darum diese Datei:
# einmal quadratisch erzeugen, dann je Ziel freistellen, zuschneiden, einpassen.
# Derselbe Weg steht auch ohne KI offen — ein vorhandenes Bild hochladen und nur
# die Größen erzeugen lassen.

# Zielformate je Vorlage: (Dateiname, Breite, Höhe, Rand). Der Rand ist ein
# Anteil der kürzeren Kante; 0 heißt randlos, wie es Icons brauchen.
LOGO_PRESETS: dict[str, tuple] = {
    # Home-Assistant-Add-on: icon.png quadratisch, logo.png im Breitformat
    'ha':      (('icon.png', 256, 256, 0.0), ('logo.png', 250, 100, 0.06)),
    # Progressive Web App (manifest.json) und iOS-Startbildschirm
    'pwa':     (('icon-192.png', 192, 192, 0.0), ('icon-512.png', 512, 512, 0.0),
                ('apple-touch-icon.png', 180, 180, 0.08)),
    'favicon': (('favicon.ico', 0, 0, 0.0), ('favicon-32.png', 32, 32, 0.0)),
    # Vorschaubild für geteilte Links — hier gehört Luft um das Motiv
    'social':  (('og-image.png', 1200, 630, 0.22),),
}
LOGO_ICO_SIZES = ((16, 16), (32, 32), (48, 48))
LOGO_SOURCE_MAX = 1024      # Kantenlänge der abgelegten source.png
LOGO_CUSTOM_MIN = 16
LOGO_CUSTOM_MAX = 4096
LOGO_SETS_MAX = 200
LOGO_IMPORT_MAX_BYTES = 16 * 1024 * 1024
LOGO_CUT_TOLERANCE_MAX = 90
LOGO_CUT_SCAN_MAX = 512     # Kantenlänge, auf der die Randsuche läuft
# Ohne diesen Zusatz liefert Gemini gern einen Farbverlauf oder eine gemalte
# Szene als Grund — beides lässt sich nicht freistellen.
LOGO_BG_HINT = ('The logo sits centered on a plain, uniform, pure white '
                'background. No shadow, no gradient, no frame, no border, '
                'no additional text or caption outside the logo itself.')
# Der Wert wird nicht zurückgemeldet, sondern in die PNG-Textfelder geschrieben:
# ein Logo trägt keine sichtbare Kennzeichnung (die wäre der Zweck zuwider), aber
# in der Datei soll nachlesbar bleiben, woher es stammt.
LOGO_PNG_SOFTWARE = 'MyPage Logo-Designer'
# Alpha-Umsetzung der Randsuche: 0 (kein Hintergrund) → 255 deckend, 1 → 0
_LOGO_ALPHA_TABLE = bytes([255] + [0] * 255)


def _logo_bg_color(img) -> tuple:
    """Farbe, die als Hintergrund gilt — der zweitkleinste der vier Eckwerte.

    Median statt „linke obere Ecke": ein einzelnes verirrtes Eckpixel (die KI
    setzt gern eine Signatur dorthin) würde sonst die ganze Maske verschieben.
    """
    w, h = img.size
    corners = [img.getpixel(p)[:3]
               for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
    return tuple(sorted(c[i] for c in corners)[1] for i in range(3))


def _logo_edge_mask(like):
    """Vom Rand aus erreichbare Flächen einer Kandidatenmaske (255 = erreichbar).

    Läuft auf einer verkleinerten Fassung: die Frage lautet nur „hängt dieser
    Fleck am Bildrand?", und dafür reichen ein paar hundert Pixel. Eine
    Breitensuche über 1024² wäre in reinem Python sekundenlang, `ImageDraw.
    floodfill` müsste zudem für jeden Randpunkt einzeln starten.
    """
    w, h = like.size
    scale = min(1.0, LOGO_CUT_SCAN_MAX / max(w, h))
    sw, sh = max(1, int(w * scale)), max(1, int(h * scale))
    small = like.resize((sw, sh), Image.NEAREST).tobytes()
    seen = bytearray(sw * sh)
    stack = [x for x in range(sw)] + [(sh - 1) * sw + x for x in range(sw)]
    stack += [y * sw for y in range(sh)] + [y * sw + sw - 1 for y in range(sh)]
    total = sw * sh
    while stack:
        i = stack.pop()
        if seen[i] or not small[i]:
            continue
        seen[i] = 1
        x = i % sw
        if x:
            stack.append(i - 1)
        if x < sw - 1:
            stack.append(i + 1)
        if i >= sw:
            stack.append(i - sw)
        if i + sw < total:
            stack.append(i + sw)
    reach = Image.frombytes('L', (sw, sh), bytes(seen).translate(
        bytes([0] + [255] * 255)))
    # Bilinear zurück: die weiche Kante schadet nicht, weil gleich noch mit der
    # scharfen Maske in voller Auflösung multipliziert wird
    return reach.resize((w, h), Image.BILINEAR)


def _logo_cutout(img, tolerance: int):
    """Randverbundenen Hintergrund transparent machen.

    Bewusst nur vom Rand aus: geschlossene helle Flächen im Motiv — das Auge
    eines Maskottchens, die Fläche in einem „O" — sollen bleiben, was sie sind.

    Die Kante wird leicht weichgezeichnet. Die KI liefert kantengeglättete
    Ränder; eine harte Maske schneidet mitten durch die Übergangspixel und
    hinterlässt eine Treppe samt hellem Saum.
    """
    img = img.convert('RGBA')
    w, h = img.size
    ref = Image.new('RGB', (w, h), _logo_bg_color(img))
    diff = ImageChops.difference(img.convert('RGB'), ref).convert('L')
    like = diff.point(lambda v: 255 if v <= tolerance else 0)
    bg = ImageChops.multiply(like, _logo_edge_mask(like))
    alpha = ImageChops.invert(bg).filter(ImageFilter.GaussianBlur(0.7))
    # Der alte Alphakanal zählt mit: ein bereits freigestelltes PNG soll nicht
    # plötzlich wieder deckend werden
    img.putalpha(ImageChops.multiply(img.getchannel('A'), alpha))
    return img


def _logo_trim_box(img):
    """Zuschnitt auf das Motiv. Bei RGBA über den Alphakanal — `getbbox()` sähe
    sonst die (noch weißen) Farbwerte der durchsichtigen Pixel und fände nichts."""
    return (img.getchannel('A').getbbox() if img.mode == 'RGBA' else img.getbbox())


def _logo_fit(img, w: int, h: int, pad: float):
    """Motiv auf w×h einpassen, mittig, mit durchsichtigem Grund.

    Erst zuschneiden, dann einpassen: ohne den Zuschnitt bestimmt der zufällige
    Leerraum der KI-Vorlage die Größe, und dasselbe Motiv wäre in jedem Format
    unterschiedlich groß.
    """
    box = _logo_trim_box(img)
    src = img.crop(box) if box else img
    m = int(min(w, h) * pad)
    inner = (max(1, w - 2 * m), max(1, h - 2 * m))
    fitted = ImageOps.contain(src, inner, Image.LANCZOS)
    out = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    out.paste(fitted, ((w - fitted.width) // 2, (h - fitted.height) // 2), fitted)
    return out


def _logo_pnginfo(meta: dict):
    """Herkunft in die PNG-Textfelder schreiben.

    Ein Logo mit sichtbarem Wasserzeichen wäre wertlos, verschweigen wollen wir
    die Herkunft trotzdem nicht — sie steht in der Datei und in prompt.txt.
    """
    info = PngImagePlugin.PngInfo()
    info.add_text('Software', LOGO_PNG_SOFTWARE)
    info.add_text('Creation Time', datetime.now(timezone.utc).isoformat(timespec='seconds'))
    if meta.get('model'):
        info.add_text('Source', 'Google Gemini ' + meta['model'])
    if meta.get('prompt'):
        info.add_text('Description', meta['prompt'][:800])
    return info


def _logo_targets(presets: list, custom: tuple | None) -> list:
    """Gewählte Vorlagen zu einer Liste von Zielformaten auflösen."""
    out = []
    for key in presets:
        out.extend(LOGO_PRESETS.get(key) or ())
    if custom:
        cw, ch = custom
        out.append((f'custom-{cw}x{ch}.png', cw, ch, 0.0))
    # Reihenfolge erhalten, Doppelte (Vorlagen überschneiden sich) entfernen
    seen, uniq = set(), []
    for t in out:
        if t[0] not in seen:
            seen.add(t[0])
            uniq.append(t)
    return uniq


def _logo_render(src_bytes: bytes, slug: str, targets: list, *, cutout: bool,
                 tolerance: int, meta: dict) -> list:
    """Einen Logo-Satz erzeugen. Zurück: die geschriebenen Dateinamen.

    Wirft bei kaputten Bilddaten oder unschreibbarem Ordner — die Aufrufer
    machen daraus eine Meldung, hier bleibt der Fehler roh.
    """
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(src_bytes)))
    img = img.convert('RGBA')
    img.thumbnail((LOGO_SOURCE_MAX, LOGO_SOURCE_MAX), Image.LANCZOS)
    if cutout:
        img = _logo_cutout(img, tolerance)
    target_dir = safe_under(LOGOS_DIR, slug)
    if target_dir is None:
        raise ValueError('bad slug')
    target_dir.mkdir(parents=True, exist_ok=True)
    info = _logo_pnginfo(meta)
    written = []
    src_path = safe_under(target_dir, 'source.png')
    if src_path is not None:
        img.save(src_path, 'PNG', pnginfo=info, optimize=True)
        written.append('source.png')
    for name, w, h, pad in targets:
        p = safe_under(target_dir, name)
        if p is None:
            continue
        if name.endswith('.ico'):
            # ICO trägt mehrere Auflösungen in einer Datei; Pillow leitet sie aus
            # der übergebenen Vorlage ab, die dafür groß genug sein muss
            _logo_fit(img, 256, 256, 0.0).save(p, 'ICO', sizes=list(LOGO_ICO_SIZES))
        else:
            _logo_fit(img, w, h, pad).save(p, 'PNG', pnginfo=info, optimize=True)
        written.append(name)
    note = safe_under(target_dir, 'prompt.txt')
    if note is not None:
        lines = [
            f"Erzeugt: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"Herkunft: {meta.get('origin') or 'unbekannt'}",
            f"Modell:   {meta.get('model') or '—'}",
            f"Freigestellt: {'ja, Toleranz ' + str(tolerance) if cutout else 'nein'}",
            f"Dateien:  {', '.join(written)}",
            '',
            meta.get('prompt') or '',
        ]
        note.write_text('\n'.join(lines), encoding='utf-8')
        written.append('prompt.txt')
    log.info("Logo-Satz „%s“ erzeugt: %s", slug, ', '.join(written))
    return written


def _logo_dir(slug: str) -> Path | None:
    if not LOGO_SLUG_RE.match(slug or ''):
        return None
    p = safe_under(LOGOS_DIR, slug)
    return p if (p is not None and p.is_dir()) else None


def _logo_files(d: Path) -> list:
    """Dateien eines Satzes mit Maßen — die Maße stehen sonst nur im Dateinamen,
    und beim Import eigener Bilder auch dort nicht."""
    out = []
    try:
        entries = sorted(d.iterdir(), key=lambda p: p.name)
    except OSError:
        return out
    for f in entries:
        if not f.is_file() or not LOGO_FILE_RE.match(f.name):
            continue
        item = {'name': f.name, 'size': f.stat().st_size, 'w': 0, 'h': 0}
        if f.suffix.lower() in ('.png', '.ico'):
            try:
                with Image.open(f) as im:
                    item['w'], item['h'] = im.size
            except Exception:
                pass
        out.append(item)
    return out


def _logo_sets() -> list:
    """Alle Sätze, neueste zuerst."""
    out = []
    try:
        dirs = [d for d in LOGOS_DIR.iterdir()
                if d.is_dir() and LOGO_SLUG_RE.match(d.name)]
    except OSError:
        return out
    for d in dirs:
        try:
            ts = d.stat().st_mtime
        except OSError:
            continue
        out.append({'slug': d.name, 'ts': int(ts), 'files': _logo_files(d)})
    out.sort(key=lambda s: s['ts'], reverse=True)
    return out


def _logo_read_params(raw: dict) -> tuple:
    """Die geteilten Felder von „speichern" und „neu rechnen" prüfen."""
    slug = _clean_str(raw.get('slug'), 41).lower()
    presets = [p for p in (raw.get('presets') or []) if p in LOGO_PRESETS]
    custom = None
    try:
        cw, ch = int(raw.get('custom_w') or 0), int(raw.get('custom_h') or 0)
        if LOGO_CUSTOM_MIN <= cw <= LOGO_CUSTOM_MAX and LOGO_CUSTOM_MIN <= ch <= LOGO_CUSTOM_MAX:
            custom = (cw, ch)
    except (TypeError, ValueError):
        custom = None
    try:
        tol = max(0, min(LOGO_CUT_TOLERANCE_MAX, int(raw.get('tolerance') or 12)))
    except (TypeError, ValueError):
        tol = 12
    return slug, presets, custom, bool(raw.get('cutout')), tol


@admin_app.route('/api/ai/logo', methods=['POST'])
def api_ai_logo():
    """Logo-Entwürfe erzeugen. Legt wie das Bild-Studio nur in AI_TMP_DIR ab."""
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
    try:
        count = max(1, min(AI_STUDIO_MAX_IMAGES, int(raw.get('count') or 1)))
    except (TypeError, ValueError):
        count = 1
    ref = _ai_ref_image(raw.get('ref') or '') if raw.get('ref') else None
    if raw.get('ref') and ref is None:
        return jsonify({'error': 'bad_ref'}), 400
    # Der Hintergrund-Hinweis geht immer mit, nicht nur beim Freistellen: ein
    # ruhiger Grund ist auch für ein deckendes Icon die bessere Vorlage.
    full = prompt + ' ' + LOGO_BG_HINT
    if not _ai_rate_take(_ai_image_times, AI_IMAGE_MAX_PER_HOUR, count):
        return jsonify({'error': 'rate_limited'}), 429
    _ai_tmp_sweep()
    images, last, last_detail = [], 'failed', ''
    for _ in range(count):
        # Quadratisch erzeugen: alle Zielformate entstehen daraus durch
        # Zuschnitt, und ein 16:9-Entwurf hätte für icon.png zu wenig Höhe
        data, mime, code, detail = _gemini_generate_image(full, model=model,
                                                          ratio='1:1', ref=ref)
        if code:
            last, last_detail = code, detail
            continue
        tid = uuid.uuid4().hex
        target = safe_under(AI_TMP_DIR, tid + '.img')
        if target is None:
            continue
        try:
            target.write_bytes(data)
        except OSError as e:
            log.warning("Logo-Entwurf konnte nicht zwischengespeichert werden: %s", e)
            continue
        _ai_tmp[tid] = {'mime': mime, 'ts': time.time(), 'prompt': prompt,
                        'model': model}
        images.append({'id': tid, 'url': 'api/ai/studio/preview/' + tid})
    if not images:
        return jsonify({'error': _AI_ERRORS.get(last, 'ai_failed'),
                        'detail': last_detail, 'model': model}), 502
    log.info("Logo-Designer: %d Entwurf/Entwürfe erzeugt (%s%s)",
             len(images), model, ', mit Vorlage' if ref else '')
    return jsonify({'ok': True, 'images': images})


@admin_app.route('/api/ai/logo/keep', methods=['POST'])
def api_ai_logo_keep():
    """Einen Entwurf als Logo-Satz ablegen."""
    err = _api_auth()
    if err:
        return err
    raw = request.get_json(silent=True) or {}
    slug, presets, custom, cutout, tol = _logo_read_params(raw)
    if not LOGO_SLUG_RE.match(slug):
        return jsonify({'error': 'bad_slug'}), 400
    targets = _logo_targets(presets, custom)
    if not targets:
        return jsonify({'error': 'no_targets'}), 400
    if len(_logo_sets()) >= LOGO_SETS_MAX and not _logo_dir(slug):
        return jsonify({'error': 'too_many'}), 400
    tid = _clean_str(raw.get('id'), 40)
    p = _ai_tmp_file(tid)
    if p is None:
        return jsonify({'error': 'not_found'}), 404
    meta = _ai_tmp.get(tid) or {}
    try:
        written = _logo_render(p.read_bytes(), slug, targets, cutout=cutout,
                               tolerance=tol,
                               meta={'prompt': meta.get('prompt'),
                                     'model': meta.get('model'),
                                     'origin': 'KI (Google Gemini)'})
    except Exception as e:
        log.warning("Logo-Satz „%s“ konnte nicht erzeugt werden: %s: %s",
                    slug, type(e).__name__, e)
        return jsonify({'error': 'render_failed'}), 502
    try:
        p.unlink()
    except OSError:
        pass
    _ai_tmp.pop(tid, None)
    log_audit('logo_create', slug)
    return jsonify({'ok': True, 'slug': slug, 'files': written})


@admin_app.route('/api/logos/import', methods=['POST'])
def api_logos_import():
    """Vorhandenes Bild in einen Logo-Satz verwandeln — ohne KI.

    Damit lassen sich auch die fehlenden Größen zu einem längst gezeichneten
    Icon nachziehen; dafür braucht es keinen API-Schlüssel.
    """
    err = _api_auth()
    if err:
        return err
    if not _HAS_PIL:
        return jsonify({'error': 'no_pil'}), 400
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'error': 'no file'}), 400
    if Path(f.filename).suffix.lower() not in ALLOWED_UPLOAD_EXT:
        return jsonify({'error': 'file type not allowed'}), 400
    raw = request.form
    slug, presets, custom, cutout, tol = _logo_read_params({
        'slug': raw.get('slug'), 'presets': raw.getlist('presets'),
        'custom_w': raw.get('custom_w'), 'custom_h': raw.get('custom_h'),
        'cutout': raw.get('cutout') == '1', 'tolerance': raw.get('tolerance'),
    })
    if not LOGO_SLUG_RE.match(slug):
        return jsonify({'error': 'bad_slug'}), 400
    targets = _logo_targets(presets, custom)
    if not targets:
        return jsonify({'error': 'no_targets'}), 400
    if len(_logo_sets()) >= LOGO_SETS_MAX and not _logo_dir(slug):
        return jsonify({'error': 'too_many'}), 400
    data = f.read(LOGO_IMPORT_MAX_BYTES + 1)
    if len(data) > LOGO_IMPORT_MAX_BYTES:
        return jsonify({'error': 'too_large'}), 400
    try:
        written = _logo_render(data, slug, targets, cutout=cutout, tolerance=tol,
                               meta={'origin': 'Eigenes Bild: '
                                     + secure_filename(f.filename)})
    except Exception as e:
        log.warning("Logo-Satz „%s“ aus eigenem Bild fehlgeschlagen: %s: %s",
                    slug, type(e).__name__, e)
        return jsonify({'error': 'render_failed'}), 502
    log_audit('logo_import', slug)
    return jsonify({'ok': True, 'slug': slug, 'files': written})


@admin_app.route('/api/logos/render', methods=['POST'])
def api_logos_render():
    """Weitere Größen aus der abgelegten source.png nachziehen — ohne neuen
    KI-Aufruf, denn die Vorlage liegt ja schon da."""
    err = _api_auth()
    if err:
        return err
    raw = request.get_json(silent=True) or {}
    slug, presets, custom, cutout, tol = _logo_read_params(raw)
    d = _logo_dir(slug)
    if d is None:
        return jsonify({'error': 'not_found'}), 404
    src = safe_under(d, 'source.png')
    if src is None or not src.is_file():
        return jsonify({'error': 'no_source'}), 404
    targets = _logo_targets(presets, custom)
    if not targets:
        return jsonify({'error': 'no_targets'}), 400
    try:
        written = _logo_render(src.read_bytes(), slug, targets, cutout=cutout,
                               tolerance=tol, meta={'origin': 'Neu gerechnet aus source.png'})
    except Exception as e:
        log.warning("Logo-Satz „%s“ konnte nicht neu gerechnet werden: %s: %s",
                    slug, type(e).__name__, e)
        return jsonify({'error': 'render_failed'}), 502
    return jsonify({'ok': True, 'slug': slug, 'files': written})


@admin_app.route('/api/logos')
def api_logos_list():
    err = _api_auth()
    if err:
        return err
    return jsonify({'sets': _logo_sets(), 'presets': list(LOGO_PRESETS),
                    'available': _HAS_PIL,
                    'path': str(LOGOS_DIR)})


@admin_app.route('/api/logos/<slug>/<name>')
def api_logos_file(slug: str, name: str):
    """Einzelne Datei ansehen oder herunterladen (`?dl=1`)."""
    err = _api_auth()
    if err:
        return err
    d = _logo_dir(slug)
    if d is None or not LOGO_FILE_RE.match(name or ''):
        return jsonify({'error': 'not_found'}), 404
    p = safe_under(d, name)
    if p is None or not p.is_file():
        return jsonify({'error': 'not_found'}), 404
    resp = send_file(p, as_attachment=bool(request.args.get('dl')),
                     download_name=name)
    # Ein neu gerechneter Satz behält seine Dateinamen — ohne das hier zeigte
    # der Browser nach „neu rechnen" weiter die alte Fassung
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@admin_app.route('/api/logos/<slug>.zip')
def api_logos_zip(slug: str):
    """Ganzer Satz als ZIP — für den Weg an einen Rechner ohne Share-Zugriff."""
    err = _api_auth()
    if err:
        return err
    d = _logo_dir(slug)
    if d is None:
        return jsonify({'error': 'not_found'}), 404
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for item in _logo_files(d):
            p = safe_under(d, item['name'])
            if p is not None and p.is_file():
                z.write(p, slug + '/' + item['name'])
    buf.seek(0)
    return send_file(buf, mimetype='application/zip', as_attachment=True,
                     download_name=slug + '-logo.zip')


@admin_app.route('/api/logos/delete', methods=['POST'])
def api_logos_delete():
    err = _api_auth()
    if err:
        return err
    slug = _clean_str((request.get_json(silent=True) or {}).get('slug'), 41).lower()
    d = _logo_dir(slug)
    if d is None:
        return jsonify({'error': 'not_found'}), 404
    # Gezielt die eigenen Dateien löschen statt rmtree: liegt dort etwas
    # Fremdes, bleibt es liegen und der Ordner damit bestehen
    for item in _logo_files(d):
        p = safe_under(d, item['name'])
        if p is not None and p.is_file():
            try:
                p.unlink()
            except OSError:
                pass
    try:
        d.rmdir()
    except OSError:
        pass
    log_audit('logo_delete', slug)
    log.info("Logo-Satz „%s“ gelöscht", slug)
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


_AI_TEXT_ACTION_DE = {
    'shorter': ('Kürze den Text deutlich — etwa auf die Hälfte — ohne eine Kernaussage '
                'zu verlieren. Lieber ganze Nebenschauplätze streichen als überall Wörter.'),
    'longer':  ('Baue den Text aus — etwa auf das Anderthalbfache — mit Beispielen, '
                'Begründungen und Details. Keine Wiederholungen, keine Füllsätze.'),
    'polish':  ('Feinschliff: Stil, Rhythmus und Übergänge verbessern, Wiederholungen '
                'und Floskeln entfernen. Inhalt und Umfang bleiben, wie sie sind.'),
    'custom':  'Setze den folgenden Änderungswunsch um, sonst bleibt alles erhalten.',
}
_AI_LANG_DE = {'de': 'Deutsch', 'en': 'Englisch'}


def _ai_lang_line(langs: list[str], mode: str) -> str:
    """Sprachanweisung — bei zwei Sprachen entscheidet `mode` über den Weg."""
    if len(langs) < 2:
        return "Sprache der Ausgabe: " + ("Deutsch." if langs[0] == 'de' else "Englisch.")
    if mode == 'translate':
        return ("Schreibe zuerst die deutsche Fassung. Die englische Fassung ist deren "
                "treue Übersetzung mit gleicher Gliederung und gleicher Länge.")
    return ("Schreibe die deutsche und die englische Fassung jeweils eigenständig "
            "und idiomatisch — die englische ist keine Wort-für-Wort-Übersetzung.")


def _ai_revise_parts(*, kind: str, tone: str, topic: str, action: str, note: str,
                     source: dict, langs: list[str], lang_line: str) -> list[str]:
    """Auftrag fürs Überarbeiten — der vorhandene Text geht vollständig mit.

    Zurück kommt trotzdem die volle Fassung je Sprache, kein Änderungsprotokoll:
    das Formular ersetzt seine Felder damit, und ein Diff könnte es nicht.
    """
    parts = [
        "Überarbeite den vorhandenen Text. Gib je Sprache die vollständige neue "
        "Fassung zurück — Titel, SEO-Beschreibung, Fließtext und Schlagwörter. "
        "Keine Auflistung der Änderungen, kein Kommentar dazu.",
        f"Gewünscht ist {_AI_TEXT_KIND_DE.get(kind, _AI_TEXT_KIND_DE['blog'])}.",
        _AI_TEXT_ACTION_DE.get(action, _AI_TEXT_ACTION_DE['polish']),
    ]
    if note:
        parts.append(f"Änderungswunsch:\n{note}")
    parts.append(f"Tonfall: {_AI_TEXT_TONE_DE.get(tone, _AI_TEXT_TONE_DE['sachlich'])}.")
    parts.append(lang_line)
    if topic:
        parts.append(f"Ursprüngliches Thema und Stichpunkte:\n{topic}")
    for lg in langs:
        d = source.get(lg) or {}
        parts.append(
            f"Vorhandene Fassung ({_AI_LANG_DE.get(lg, lg)}):\n"
            f"Titel: {d.get('title', '')}\n"
            f"SEO-Beschreibung: {d.get('meta', '')}\n"
            f"Text:\n{d.get('text', '')}"
        )
    return parts


def _gemini_image_alt(ref: tuple[bytes, str], *, model: str
                      ) -> tuple[dict | None, str, str]:
    """Alternativtext zu einem Bild — deutsch und englisch in einem Aufruf.

    Bewusst knapp gehalten: ein Alternativtext beschreibt, was zu sehen ist, und
    ist keine Bildunterschrift. Zu lange Texte sind für Screenreader schlimmer
    als zu kurze.
    """
    sys = ("Du schreibst Alternativtexte (alt-Attribute) für Bilder einer Website. "
           "Beschreibe sachlich, was zu sehen ist — höchstens 125 Zeichen je Sprache, "
           "ein Satz ohne Punkt am Ende. Keine Einleitung wie 'Bild von' oder 'Foto zeigt', "
           "keine Vermutungen über Namen, Orte oder Marken, keine Deutung der Stimmung. "
           "Steht Text im Bild und trägt er die Aussage, gib ihn wieder.")
    schema = genai_types.Schema(
        type=genai_types.Type.OBJECT,
        properties={'de': genai_types.Schema(type=genai_types.Type.STRING),
                    'en': genai_types.Schema(type=genai_types.Type.STRING)},
        required=['de', 'en'],
    )
    try:
        client = _gemini_client()
        resp = client.models.generate_content(
            model=model,
            contents=[genai_types.Part.from_bytes(data=ref[0], mime_type=ref[1]),
                      'Schreibe den Alternativtext auf Deutsch (de) und auf Englisch (en).'],
            config=genai_types.GenerateContentConfig(
                system_instruction=sys,
                response_mime_type='application/json',
                response_schema=schema,
                http_options=genai_types.HttpOptions(timeout=GEMINI_TEXT_TIMEOUT_MS),
            ),
        )
        _ai_usage_record(model, resp)
        cands = resp.candidates or []
        finish = cands[0].finish_reason if cands else None
        reason = getattr(finish, 'name', None) or (str(finish) if finish else '')
        if finish in _GEMINI_TEXT_REFUSALS:
            log.info("Gemini hat den Alternativtext abgelehnt: %s", finish)
            return None, 'refused', reason
        data = json.loads(resp.text or '')
        if not isinstance(data, dict):
            return None, 'empty', reason
    except genai_errors.APIError as e:
        code = getattr(e, 'code', None)
        log.warning("Alternativtext fehlgeschlagen (%s): Status %s", model, code or type(e).__name__)
        return (None, ('model_missing' if code == 404 else 'failed'),
                f'HTTP {code}' if code else '')
    except Exception as e:
        log.error("Alternativtext (%s) unerwartet fehlgeschlagen: %s", model, type(e).__name__)
        return None, 'failed', type(e).__name__
    out = {lg: _clean_str(data.get(lg), UPLOAD_ALT_MAX) for lg in ('de', 'en')}
    if not (out['de'] or out['en']):
        return None, 'empty', reason
    return out, '', ''


_AI_SEO_LANG_DE = {'de': 'Deutsch', 'en': 'Englisch'}


def _gemini_seo_desc(*, text: str, title: str, lang: str, model: str
                     ) -> tuple[str | None, str, str]:
    """Eine SEO-Beschreibung aus dem fertigen Beitragstext.

    Bewusst ein eigener Aufruf statt `_gemini_generate_text(kind='seo')`: dort
    entsteht ein Text aus einem Thema, hier fasst das Modell einen vorhandenen
    zusammen. Und es geht immer nur eine Sprache — die Vorschau fragt für die
    Sprache, die dort gerade gewählt ist.
    """
    sys = (
        "Du schreibst die SEO-Beschreibung (meta description) für eine Seite. "
        "Ein bis zwei Sätze, 120 bis 155 Zeichen — kürzer verschenkt Platz, "
        "länger schneidet Google ab. Der wichtigste Begriff steht früh, der Satz "
        "ist aktiv formuliert und sagt, was der Leser auf der Seite bekommt. "
        "Kein Markdown, keine Anführungszeichen, keine Aufzählung, kein "
        "Punkt-Punkt-Punkt, keine Wiederholung des Titels und nichts, was nicht "
        "im Text steht — keine erfundenen Zahlen, Orte oder Versprechen."
    )
    extra = _ai_instructions()
    if extra:
        sys += ("\n\nZusätzliche Vorgaben für diese Website, die immer gelten "
                "(sie ändern nichts an der Antwortform):\n" + extra)
    sys += _ai_address_note()
    parts = [f"Sprache der Beschreibung: {_AI_SEO_LANG_DE.get(lang, 'Deutsch')}."]
    if title:
        parts.append("Titel der Seite:\n" + title)
    parts.append("Text der Seite (Markdown):\n" + text)
    schema = genai_types.Schema(
        type=genai_types.Type.OBJECT,
        properties={'desc': genai_types.Schema(type=genai_types.Type.STRING)},
        required=['desc'],
    )
    try:
        client = _gemini_client()
        resp = client.models.generate_content(
            model=model, contents=['\n\n'.join(parts)],
            config=genai_types.GenerateContentConfig(
                system_instruction=sys,
                response_mime_type='application/json',
                response_schema=schema,
                http_options=genai_types.HttpOptions(timeout=GEMINI_TEXT_TIMEOUT_MS),
            ),
        )
        _ai_usage_record(model, resp)
        cands = resp.candidates or []
        finish = cands[0].finish_reason if cands else None
        reason = getattr(finish, 'name', None) or (str(finish) if finish else '')
        if finish in _GEMINI_TEXT_REFUSALS:
            log.info("Gemini hat die SEO-Beschreibung abgelehnt: %s", finish)
            return None, 'refused', reason
        data = json.loads(resp.text or '')
        if not isinstance(data, dict):
            return None, 'empty', reason
    except genai_errors.APIError as e:
        # Nur der Statuscode: die SDK-Meldung kann die Anfrage-URL samt Key enthalten
        code = getattr(e, 'code', None)
        log.warning("SEO-Beschreibung fehlgeschlagen (%s): Status %s",
                    model, code or type(e).__name__)
        return (None, ('model_missing' if code == 404 else 'failed'),
                f'HTTP {code}' if code else '')
    except (ValueError, TypeError) as e:
        log.warning("SEO-Antwort (%s) war kein gültiges JSON: %s", model, type(e).__name__)
        return None, 'empty', type(e).__name__
    except Exception as e:
        log.error("SEO-Beschreibung (%s) unerwartet fehlgeschlagen: %s", model, type(e).__name__)
        return None, 'failed', type(e).__name__
    out = _clean_str(data.get('desc'), 300)
    if not out:
        return None, 'empty', reason
    return out, '', ''


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
                          langs: list[str], mode: str, model: str,
                          action: str = '', note: str = '',
                          source: dict | None = None
                          ) -> tuple[dict | None, str, str]:
    """Erzeugt Titel, SEO-Beschreibung, Fließtext und Schlagwörter je Sprache.

    Mit `action` (und dem vorhandenen Text in `source`) wird stattdessen
    überarbeitet — dieselbe Antwortform, damit das Formular beide Wege gleich
    behandeln kann.

    Zurück: (Ergebnis, Fehlercode, Erläuterung) — dieselben Codes wie bei den
    Bildern. Die Erläuterung ist Googles Abbruchgrund im Klartext; ohne sie
    steht im Admin nur „fehlgeschlagen" und niemand weiß, woran es lag.
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
    extra = _ai_instructions()
    if extra:
        sys += ("\n\nZusätzliche Vorgaben für diese Website, die immer gelten "
                "(sie ändern nichts an der Antwortform):\n" + extra)
    sys += _ai_address_note()
    if action:
        parts = _ai_revise_parts(kind=kind, tone=tone, topic=topic, action=action,
                                 note=note, source=source or {}, langs=langs,
                                 lang_line=_ai_lang_line(langs, mode))
    else:
        parts = [
            f"Gewünscht ist {_AI_TEXT_KIND_DE.get(kind, _AI_TEXT_KIND_DE['blog'])}.",
            f"Thema und Stichpunkte:\n{topic}",
            f"Tonfall: {_AI_TEXT_TONE_DE.get(tone, _AI_TEXT_TONE_DE['sachlich'])}.",
            f"Zielumfang: rund {words} Wörter je Sprache.",
            _ai_lang_line(langs, mode),
        ]
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
        finish = cands[0].finish_reason if cands else None
        reason = getattr(finish, 'name', None) or (str(finish) if finish else '')
        if finish in _GEMINI_TEXT_REFUSALS:
            log.info("Gemini hat die Textanfrage abgelehnt: %s", finish)
            return None, 'refused', reason
        data = json.loads(resp.text or '')
        if not isinstance(data, dict):
            log.warning("Gemini-Textantwort (%s) ohne verwertbaren Inhalt — finish_reason=%s",
                        model, reason or '?')
            return None, 'empty', reason
    except genai_errors.APIError as e:
        # Nur der Statuscode: die SDK-Meldung kann die Anfrage-URL samt Key enthalten
        code = getattr(e, 'code', None)
        log.warning("Gemini-Textanfrage fehlgeschlagen (%s): Status %s",
                    model, code or type(e).__name__)
        return (None, ('model_missing' if code == 404 else 'failed'),
                f'HTTP {code}' if code else '')
    except (ValueError, TypeError) as e:
        log.warning("Gemini-Textantwort (%s) war kein gültiges JSON: %s", model, type(e).__name__)
        return None, 'empty', type(e).__name__
    except Exception as e:
        log.error("Gemini-Textanfrage (%s) unerwartet fehlgeschlagen: %s: %s",
                  model, type(e).__name__, e)
        return None, 'failed', type(e).__name__
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
        return None, 'empty', reason
    return out, '', ''


@admin_app.route('/api/ai/text', methods=['POST'])
def api_ai_text():
    err = _api_auth()
    if err:
        return err
    if not gemini_text_enabled():
        return jsonify({'error': 'no_api_key'}), 400
    raw = request.get_json(silent=True) or {}
    topic = _clean_str(raw.get('topic'), AI_TEXT_TOPIC_MAX)
    action = raw.get('action') if raw.get('action') in AI_TEXT_ACTIONS else ''
    note = _clean_str(raw.get('note'), AI_TEXT_NOTE_MAX)
    # Beim Überarbeiten ist der vorhandene Text der Auftrag; ein Thema darf dann
    # fehlen. Ohne beides gäbe es nichts zu tun.
    if not action and len(topic) < 3:
        return jsonify({'error': 'invalid'}), 400
    if action == 'custom' and not note:
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
    source = {}
    if action:
        raw_src = raw.get('source') if isinstance(raw.get('source'), dict) else {}
        for lg in langs:
            source[lg] = _ai_draft_lang(raw_src.get(lg))
        if not any(d['text'] or d['title'] for d in source.values()):
            return jsonify({'error': 'invalid'}), 400
    if not _ai_rate_take(_ai_text_times, AI_TEXT_MAX_PER_HOUR):
        return jsonify({'error': 'rate_limited'}), 429
    data, code, detail = _gemini_generate_text(topic=topic, kind=kind, tone=tone,
                                               length=length, langs=langs, mode=mode,
                                               model=model, action=action, note=note,
                                               source=source)
    if code:
        return jsonify({'error': _AI_ERRORS.get(code, 'ai_failed'),
                        'detail': detail, 'model': model}), 502
    log.info("KI-Text %s (%s, %s, %s)", 'überarbeitet' if action else 'erzeugt',
             model, kind, '+'.join(langs))
    return jsonify({'ok': True, 'result': data})


@admin_app.route('/api/ai/seo', methods=['POST'])
def api_ai_seo():
    """SEO-Beschreibung aus einem vorhandenen Text — für den Knopf an der Vorschau."""
    err = _api_auth()
    if err:
        return err
    if not gemini_text_enabled():
        return jsonify({'error': 'no_api_key'}), 400
    raw = request.get_json(silent=True) or {}
    lang = 'en' if raw.get('lang') == 'en' else 'de'
    # Zwei Wege in dieselbe Anfrage: der Dialog schickt seinen (noch nicht
    # gespeicherten) Text mit, die SEO-Übersicht nur Art und Id — dort liegt der
    # Text längst auf der Platte und müsste sonst erst in den Browser wandern.
    kind = raw.get('kind') if raw.get('kind') in SEO_KINDS else ''
    if kind:
        site = load_site()
        obj = _seo_find(site, kind, _clean_str(raw.get('id'), 40))
        if obj is None:
            return jsonify({'error': 'not_found'}), 404
        text, title = _seo_source(site, kind, obj, lang)
        text, title = text[:AI_SEO_TEXT_MAX], title[:200]
    else:
        text = _clean_str(raw.get('text'), AI_SEO_TEXT_MAX)
        title = _clean_str(raw.get('title'), 200)
    # Aus zwei Wörtern lässt sich nichts zusammenfassen; der Titel allein reicht
    # nur, wenn es sonst nichts gibt — dann bleibt es eine Umschreibung.
    if len(text) < 40 and len(title) < 3:
        return jsonify({'error': 'invalid'}), 400
    model = _ai_model_or(raw.get('model'), _gemini_text_model())
    if not _ai_rate_take(_ai_text_times, AI_TEXT_MAX_PER_HOUR):
        return jsonify({'error': 'rate_limited'}), 429
    desc, code, detail = _gemini_seo_desc(text=text, title=title, lang=lang, model=model)
    if code:
        return jsonify({'error': _AI_ERRORS.get(code, 'ai_failed'),
                        'detail': detail, 'model': model}), 502
    log.info("SEO-Beschreibung erzeugt (%s, %s)", model, lang)
    return jsonify({'ok': True, 'desc': desc})


# ── SEO-Übersicht ─────────────────────────────────────────────────────────────
#
# Die SEO-Beschreibung steht bisher nur im Dialog des jeweiligen Inhalts. Wer
# wissen will, wo überhaupt eine fehlt, müsste jeden Beitrag einzeln aufmachen.
# Diese Liste sammelt alles mit eigenem SEO-Feld an einer Stelle — mit dem Text,
# den die Seite heute ausliefert, damit sichtbar wird, was ein leeres Feld
# bedeutet: nicht „keine Beschreibung", sondern „irgendein Textanfang".

SEO_KINDS = ('home', 'post', 'page', 'library')
# Feld mit dem Fließtext je Art. Die Startseite fällt aus der Reihe: ihr
# SEO-Feld steht im Design, der Text dazu im Profil.
_SEO_TEXT_FIELD = {'post': 'text', 'page': 'body', 'library': 'body'}


def _seo_meta_field(kind: str, lang: str) -> str:
    return ('meta_description_' if kind == 'home' else 'meta_') + lang


def _seo_objects(site: dict) -> list[tuple[str, str, dict]]:
    """(Art, Id, Objekt) für alles mit eigenem SEO-Feld — eine Quelle für
    Übersicht, Speichern und KI-Knopf."""
    out: list[tuple[str, str, dict]] = [('home', '', site['design'])]
    # Abgeschaltete Bereiche bleiben draussen: Ihre Adressen antworten mit 404,
    # eine SEO-Zeile dafuer waere Arbeit an einer Seite, die es nicht gibt.
    if blog_public(site):
        out += [('post', p.get('id', ''), p) for p in site.get('posts', [])]
    out += [('page', p.get('id', ''), p) for p in site.get('pages', [])]
    if library_public(site):
        out += [('library', e.get('id', ''), e) for e in _library(site).get('entries', [])]
    return out


def _seo_find(site: dict, kind: str, ident: str) -> dict | None:
    for k, i, obj in _seo_objects(site):
        if k == kind and (kind == 'home' or i == ident):
            return obj
    return None


def _seo_source(site: dict, kind: str, obj: dict, lang: str) -> tuple[str, str]:
    """(Markdown, Titel) als Vorlage für die KI — leere Sprache greift auf die andere."""
    loc = _loc_factory(lang)
    if kind == 'home':
        return loc(site['profile'], 'bio'), (site['design'].get('site_title')
                                             or site['profile'].get('name') or '')
    return loc(obj, _SEO_TEXT_FIELD[kind]), loc(obj, 'title')


def _seo_effective(site: dict, kind: str, obj: dict, lang: str) -> str:
    """Was heute im Quelltext der Seite steht — dieselbe Kette wie in den
    öffentlichen Routen. Steht sie hier anders, ist die Übersicht wertlos."""
    loc = _loc_factory(lang)
    if kind == 'home':
        return _site_meta(site, loc)
    if kind == 'library':
        return (loc(obj, 'meta') or loc(obj, 'summary')
                or _plain_excerpt(render_md(loc(obj, 'body'))) or _site_meta(site, loc))
    field = _SEO_TEXT_FIELD[kind]
    return (loc(obj, 'meta') or _plain_excerpt(render_md(loc(obj, field)))
            or _site_meta(site, loc))


def _seo_row(site: dict, kind: str, ident: str, obj: dict) -> dict:
    if kind == 'home':
        label, url, visible = (site['design'].get('site_title')
                               or site['profile'].get('name') or 'Start'), '/', True
    elif kind == 'post':
        label = obj.get('title_de') or obj.get('title_en') or ident
        url, visible = '/blog/' + ident, post_visible(obj)
    elif kind == 'page':
        label = obj.get('title_de') or obj.get('title_en') or obj.get('slug', '')
        url, visible = '/seite/' + obj.get('slug', ''), bool(obj.get('visible'))
    else:
        label = obj.get('title_de') or obj.get('title_en') or obj.get('slug', '')
        url, visible = '/bibliothek/' + obj.get('slug', ''), bool(obj.get('visible'))
    row = {'kind': kind, 'id': ident, 'label': label, 'url': url, 'visible': visible}
    for lg in ('de', 'en'):
        row['meta_' + lg] = obj.get(_seo_meta_field(kind, lg), '')
        row['eff_' + lg] = _seo_effective(site, kind, obj, lg)
        # Ohne Text kann auch die KI nichts zusammenfassen — der Knopf bleibt dann aus
        row['src_' + lg] = bool(_seo_source(site, kind, obj, lg)[0])
    return row


@admin_app.route('/api/seo/list')
def api_seo_list():
    err = _api_auth()
    if err:
        return err
    site = load_site()
    return jsonify({'items': [_seo_row(site, k, i, o) for k, i, o in _seo_objects(site)]})


@admin_app.route('/api/seo/list', methods=['POST'])
def api_seo_save():
    """Nur die SEO-Felder schreiben — geänderte Zeilen kommen einzeln herein.

    Bewusst kein `_normalize_*`: die Übersicht kennt nur zwei Felder, und ein
    Normalisierer würde alles andere aus einem unvollständigen Datensatz neu
    bauen und dabei löschen.
    """
    err = _api_auth()
    if err:
        return err
    items = (request.get_json(silent=True) or {}).get('items')
    if not isinstance(items, list):
        return jsonify({'error': 'invalid'}), 400
    site = load_site()
    changed, pinged = 0, []
    for raw in items[:500]:
        if not isinstance(raw, dict):
            continue
        kind = raw.get('kind') if raw.get('kind') in SEO_KINDS else ''
        obj = _seo_find(site, kind, _clean_str(raw.get('id'), 40)) if kind else None
        if obj is None:
            continue
        for lg in ('de', 'en'):
            if ('meta_' + lg) not in raw:
                continue   # nicht mitgeschickt heißt „unverändert", nicht „leeren"
            field = _seo_meta_field(kind, lg)
            val = _clean_str(raw.get('meta_' + lg), 300)
            if obj.get(field, '') != val:
                obj[field] = val
                changed += 1
                if kind == 'post':
                    pinged.append(obj)
    if not changed:
        return jsonify({'ok': True, 'count': 0})
    save_site(site)
    for post in {p['id']: p for p in pinged}.values():
        _indexnow_ping_post(site, post)
    log.info("SEO-Beschreibungen geändert: %s Feld(er)", changed)
    return jsonify({'ok': True, 'count': changed})


# ── Entwürfe des Text-Studios ─────────────────────────────────────────────────
#
# Ein erzeugter Text lebte bisher nur im Formular: Tabwechsel, Neuladen oder ein
# zweiter Durchgang haben ihn verworfen. Entwürfe liegen deshalb in einer eigenen
# Datei — nicht in site.json, die bei jedem Admin-Speichern komplett neu
# geschrieben wird, und nicht als unveröffentlichter Blogbeitrag, denn ein
# Entwurf kann auch für ein Projekt oder eine SEO-Beschreibung gedacht sein.
# Mitgespeichert werden auch die Eingaben (Thema, Textart, Tonfall …), damit ein
# geladener Entwurf ohne Abtippen neu erzeugt werden kann.

def _ai_drafts_load() -> list[dict]:
    with _ai_drafts_lock:
        try:
            with open(AI_DRAFTS_PATH, encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            return []
        except Exception as e:
            _quarantine_corrupt(AI_DRAFTS_PATH, e)
            return []
    drafts = data.get('drafts') if isinstance(data, dict) else None
    return [d for d in drafts if isinstance(d, dict)] if isinstance(drafts, list) else []


def _ai_drafts_save(drafts: list[dict]) -> bool:
    with _ai_drafts_lock:
        try:
            _atomic_write_json(AI_DRAFTS_PATH, {'drafts': drafts}, indent=2)
            return True
        except Exception as e:
            log.error("ai_drafts.json konnte nicht gespeichert werden: %s", e)
            return False


def _ai_draft_lang(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    return {'title': _clean_str(raw.get('title'), 300),
            'meta':  _clean_str(raw.get('meta'), 300),
            'text':  _clean_str(raw.get('text'), AI_DRAFT_TEXT_MAX)}


def _ai_draft_from(raw: dict, existing: dict | None = None) -> dict:
    now = int(datetime.now(timezone.utc).timestamp())
    d = existing or {'id': uuid.uuid4().hex[:12], 'ts': now}
    wanted = raw.get('langs')
    langs = [lg for lg in ('de', 'en') if isinstance(wanted, list) and lg in wanted] or ['de']
    d['updated'] = now
    d['name']   = _clean_str(raw.get('name'), 120)
    d['topic']  = _clean_str(raw.get('topic'), AI_TEXT_TOPIC_MAX)
    d['kind']   = raw.get('kind') if raw.get('kind') in AI_TEXT_KINDS else 'blog'
    d['tone']   = raw.get('tone') if raw.get('tone') in AI_TEXT_TONES else 'sachlich'
    d['length'] = raw.get('length') if raw.get('length') in AI_TEXT_LENGTHS else 'mittel'
    d['mode']   = 'translate' if raw.get('mode') == 'translate' else 'native'
    d['langs']  = langs
    d['tags']   = _clean_str(raw.get('tags'), 500)
    d['de'] = _ai_draft_lang(raw.get('de'))
    d['en'] = _ai_draft_lang(raw.get('en'))
    # Ohne Namen wäre die Liste eine Reihe leerer Zeilen — Titel, sonst Thema
    if not d['name']:
        d['name'] = (d['de']['title'] or d['en']['title'] or d['topic']
                     or datetime.now().strftime('%Y-%m-%d %H:%M'))[:120]
    return d


def _ai_draft_row(d: dict) -> dict:
    """Zeile für die Liste — ohne Fließtext, der kann sechsstellig sein."""
    return {'id': d.get('id', ''), 'name': d.get('name', ''),
            'kind': d.get('kind', 'blog'), 'langs': d.get('langs', ['de']),
            'ts': d.get('ts', 0), 'updated': d.get('updated', 0),
            'chars': len(d.get('de', {}).get('text', '')) + len(d.get('en', {}).get('text', ''))}


@admin_app.route('/api/ai/drafts')
def api_ai_drafts():
    err = _api_auth()
    if err:
        return err
    drafts = sorted(_ai_drafts_load(), key=lambda d: d.get('updated', 0), reverse=True)
    return jsonify({'drafts': [_ai_draft_row(d) for d in drafts], 'max': AI_DRAFTS_MAX})


@admin_app.route('/api/ai/drafts/<did>')
def api_ai_draft_get(did):
    err = _api_auth()
    if err:
        return err
    d = next((x for x in _ai_drafts_load() if x.get('id') == did), None)
    if not d:
        return jsonify({'error': 'not_found'}), 404
    return jsonify({'ok': True, 'draft': d})


@admin_app.route('/api/ai/drafts', methods=['POST'])
def api_ai_draft_save():
    err = _api_auth()
    if err:
        return err
    raw = request.get_json(silent=True) or {}
    drafts = _ai_drafts_load()
    did = _clean_str(raw.get('id'), 32)
    existing = next((x for x in drafts if x.get('id') == did), None) if did else None
    d = _ai_draft_from(raw, existing)
    if not (d['de']['text'] or d['en']['text'] or d['de']['title'] or d['en']['title']):
        return jsonify({'error': 'empty'}), 400
    if existing is None:
        drafts.append(d)
        # Ältestes zuerst weg. Die Grenze schützt die Datei davor, mit jedem
        # Durchgang ungebremst zu wachsen — gespeichert wird ja per Knopfdruck.
        if len(drafts) > AI_DRAFTS_MAX:
            drafts = sorted(drafts, key=lambda x: x.get('updated', 0),
                            reverse=True)[:AI_DRAFTS_MAX]
    if not _ai_drafts_save(drafts):
        return jsonify({'error': 'save_failed'}), 500
    log.info("KI-Entwurf gespeichert (%s)", d['id'])
    return jsonify({'ok': True, 'id': d['id'], 'name': d['name']})


@admin_app.route('/api/ai/drafts/<did>', methods=['DELETE'])
def api_ai_draft_delete(did):
    err = _api_auth()
    if err:
        return err
    drafts = _ai_drafts_load()
    rest = [d for d in drafts if d.get('id') != did]
    if len(rest) == len(drafts):
        return jsonify({'error': 'not_found'}), 404
    if not _ai_drafts_save(rest):
        return jsonify({'error': 'save_failed'}), 500
    return jsonify({'ok': True})


# ── Prompt-Bibliothek des Bild-Studios ────────────────────────────────────────
#
# Dasselbe Muster wie die Text-Entwürfe, nur kleiner: ein guter Prompt ist Arbeit
# und war nach dem Neuladen weg. Die Einträge bleiben klein genug, dass die Liste
# sie vollständig ausliefert — es gibt also keinen zweiten Aufruf zum Laden.
# Achtung: das Vorlagenbild ist eine Upload-Adresse, deshalb liest
# `_reference_blob()` diese Datei mit, sonst räumt „Speicher aufräumen" sie weg.

def _ai_prompts_load() -> list[dict]:
    with _ai_prompts_lock:
        try:
            with open(AI_PROMPTS_PATH, encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            return []
        except Exception as e:
            _quarantine_corrupt(AI_PROMPTS_PATH, e)
            return []
    items = data.get('prompts') if isinstance(data, dict) else None
    return [p for p in items if isinstance(p, dict)] if isinstance(items, list) else []


def _ai_prompts_save(items: list[dict]) -> bool:
    with _ai_prompts_lock:
        try:
            _atomic_write_json(AI_PROMPTS_PATH, {'prompts': items}, indent=2)
            return True
        except Exception as e:
            log.error("ai_prompts.json konnte nicht gespeichert werden: %s", e)
            return False


def _ai_prompt_from(raw: dict, existing: dict | None = None) -> dict:
    now = int(datetime.now(timezone.utc).timestamp())
    p = existing or {'id': uuid.uuid4().hex[:12], 'ts': now}
    p['updated'] = now
    p['name']   = _clean_str(raw.get('name'), 120)
    p['prompt'] = _clean_str(raw.get('prompt'), AI_IMAGE_PROMPT_MAX)
    p['ratio']  = raw.get('ratio') if raw.get('ratio') in GEMINI_IMAGE_RATIOS else ''
    try:
        p['count'] = max(1, min(AI_STUDIO_MAX_IMAGES, int(raw.get('count') or 1)))
    except (TypeError, ValueError):
        p['count'] = 1
    # Nur eigene Uploads, gleiche Form wie im Studio — der Wert landet später in
    # einem <img src> und in einer Anfrage
    ref = _clean_str(raw.get('ref'), 200)
    p['ref'] = ref if _UPLOAD_PATH_RE.match(ref) else ''
    if not p['name']:
        p['name'] = p['prompt'][:60] or datetime.now().strftime('%Y-%m-%d %H:%M')
    return p


@admin_app.route('/api/ai/prompts')
def api_ai_prompts():
    err = _api_auth()
    if err:
        return err
    items = sorted(_ai_prompts_load(), key=lambda p: p.get('updated', 0), reverse=True)
    return jsonify({'prompts': items, 'max': AI_PROMPTS_MAX})


@admin_app.route('/api/ai/prompts', methods=['POST'])
def api_ai_prompt_save():
    err = _api_auth()
    if err:
        return err
    raw = request.get_json(silent=True) or {}
    items = _ai_prompts_load()
    pid = _clean_str(raw.get('id'), 32)
    existing = next((x for x in items if x.get('id') == pid), None) if pid else None
    p = _ai_prompt_from(raw, existing)
    if len(p['prompt']) < 3:
        return jsonify({'error': 'empty'}), 400
    if existing is None:
        items.append(p)
        if len(items) > AI_PROMPTS_MAX:
            items = sorted(items, key=lambda x: x.get('updated', 0),
                           reverse=True)[:AI_PROMPTS_MAX]
    if not _ai_prompts_save(items):
        return jsonify({'error': 'save_failed'}), 500
    log.info("Bild-Prompt gespeichert (%s)", p['id'])
    return jsonify({'ok': True, 'id': p['id'], 'name': p['name']})


@admin_app.route('/api/ai/prompts/<pid>', methods=['DELETE'])
def api_ai_prompt_delete(pid):
    err = _api_auth()
    if err:
        return err
    items = _ai_prompts_load()
    rest = [p for p in items if p.get('id') != pid]
    if len(rest) == len(items):
        return jsonify({'error': 'not_found'}), 404
    if not _ai_prompts_save(rest):
        return jsonify({'error': 'save_failed'}), 500
    return jsonify({'ok': True})


# ── Reiseblog ─────────────────────────────────────────────────────────────────
#
# Unterwegs entsteht kein fertiger Text, sondern ein paar Stichpunkte. Aus denen
# baut `travelblog.build_prompt` einen Prompt, und daraus schreibt das Modell den
# Tagesbericht. Rohdaten und Artikel bleiben getrennt gespeichert: eine Korrektur
# am Text darf nicht verlorengehen, nur weil später eine Ausgabe nachgetragen wird.

def load_travel() -> dict:
    with _travel_lock:
        try:
            with open(TRAVEL_PATH, encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            return {'trips': []}
        except Exception as e:
            _quarantine_corrupt(TRAVEL_PATH, e)
            return {'trips': []}
    if not isinstance(data.get('trips'), list):
        data['trips'] = []
    return data


def save_travel(data: dict) -> bool:
    """Speichert und sagt, ob es geklappt hat.

    Ein verschluckter Schreibfehler ist hier besonders teuer: die Oberfläche
    meldete „Gespeichert", der Dialog schloss sich, und der eingetippte Tag war
    weg. Der Rückgabewert zwingt die Routen, das Scheitern zu melden.
    """
    with _travel_lock:
        try:
            _atomic_write_json(TRAVEL_PATH, data, indent=2)
            return True
        except Exception as e:
            log.error("travel.json konnte nicht gespeichert werden: %s", e)
            return False


def _saved(ok: bool, payload: dict | None = None):
    if not ok:
        return jsonify({'error': 'save_failed'}), 500
    return jsonify({'ok': True, **(payload or {})})


def _trip(data: dict, tid: str) -> dict | None:
    return next((t for t in data['trips'] if t.get('id') == tid), None)


def _day(trip: dict, did: str) -> dict | None:
    return next((d for d in trip.get('days', []) if d.get('id') == did), None)


def _trav_slug(wish: str, fallback: str, taken: set) -> str:
    """Eindeutiger Slug aus Wunsch oder Notnagel, Dubletten mit -2, -3, …"""
    base = _slugify(wish) or fallback
    slug, n = base, 2
    while slug in taken:
        slug = f'{base}-{n}'
        n += 1
    return slug


def _trav_trip_slug(data: dict, trip: dict, tid: str) -> str:
    """Adresse der Reise. Ein einmal vergebener Slug bleibt, auch wenn die Reise
    später umbenannt wird — sonst führt jeder geteilte Link ins Leere."""
    taken = {t.get('slug') for t in data['trips'] if t.get('id') != tid and t.get('slug')}
    return _trav_slug(trip.get('slug') or trip.get('name') or '', 'reise-' + tid[:6], taken)


def _trav_day_slug(trip: dict, day: dict, did: str) -> str:
    """Adresse des Tages, standardmäßig `tag-3`.

    Bewusst ohne Ort im Slug: der Ort wird beim Nachtragen gern noch korrigiert,
    die Tagesnummer nicht. Eindeutig muss der Slug nur innerhalb der Reise sein.
    """
    taken = {d.get('slug') for d in trip.get('days', []) if d.get('id') != did and d.get('slug')}
    return _trav_slug(day.get('slug') or f"tag-{day.get('day_number') or 1}",
                      'tag-' + did[:6], taken)


@admin_app.route('/api/travel')
def api_travel_get():
    err = _api_auth()
    if err:
        return err
    return jsonify(load_travel())


@admin_app.route('/api/travel/options')
def api_travel_options():
    """Auswahllisten aus einer Hand — sonst müssten sie im JavaScript ein
    zweites Mal stehen und liefen mit der Zeit auseinander."""
    err = _api_auth()
    if err:
        return err
    return jsonify({
        'weather_conditions': list(tb.WEATHER_CONDITIONS),
        'wind_strengths': list(tb.WIND_STRENGTHS),
        'experience_types': list(tb.EXPERIENCE_TYPES),
        'recommendations': list(tb.RECOMMENDATIONS),
        'transports': list(tb.TRANSPORTS),
        'meal_types': list(tb.MEAL_TYPES),
        'moment_categories': list(tb.MOMENT_CATEGORIES),
        'expense_categories': list(tb.EXPENSE_CATEGORIES),
        'currencies': list(tb.CURRENCIES),
        'writing_styles': list(tb.WRITING_STYLES),
        'perspectives': list(tb.PERSPECTIVES),
        'lengths': list(tb.LENGTHS),
        # Ohne Home Assistant gibt es die Wetter-Übernahme nicht — die
        # Oberfläche blendet die Knöpfe dann ganz aus, statt sie ins Leere
        # zeigen zu lassen.
        'on_ha': bool(SUPERVISOR_TOKEN),
    })


@admin_app.route('/api/travel/trips', methods=['POST'])
def api_travel_trip_create():
    err = _api_auth()
    if err:
        return err
    data = load_travel()
    if len(data['trips']) >= tb.MAX_TRIPS:
        return jsonify({'error': 'too many'}), 400
    trip = tb.normalize_trip(request.get_json(silent=True) or {})
    if not trip['name']:
        return jsonify({'error': 'name required'}), 400
    trip['id'] = uuid.uuid4().hex[:12]
    trip['slug'] = _trav_trip_slug(data, trip, trip['id'])
    data['trips'].insert(0, trip)
    return _saved(save_travel(data), {'id': trip['id']})


@admin_app.route('/api/travel/trips/<tid>', methods=['PUT', 'DELETE'])
def api_travel_trip(tid: str):
    err = _api_auth()
    if err:
        return err
    data = load_travel()
    trip = _trip(data, tid)
    if trip is None:
        return jsonify({'error': 'not_found'}), 404
    if request.method == 'DELETE':
        data['trips'] = [t for t in data['trips'] if t.get('id') != tid]
        ok = save_travel(data)
        if ok:
            log_audit('travel_trip_delete', trip.get('name', ''))
        return _saved(ok)
    merged = tb.normalize_trip(request.get_json(silent=True) or {}, trip)
    merged['id'] = tid
    merged['slug'] = _trav_trip_slug(data, merged, tid)
    data['trips'] = [merged if t.get('id') == tid else t for t in data['trips']]
    return _saved(save_travel(data))


@admin_app.route('/api/travel/trips/<tid>/days', methods=['POST'])
def api_travel_day_create(tid: str):
    err = _api_auth()
    if err:
        return err
    data = load_travel()
    trip = _trip(data, tid)
    if trip is None:
        return jsonify({'error': 'not_found'}), 404
    if len(trip.get('days', [])) >= tb.MAX_DAYS:
        return jsonify({'error': 'too many'}), 400
    day = tb.normalize_day(request.get_json(silent=True) or {})
    day['id'] = uuid.uuid4().hex[:12]
    day['slug'] = _trav_day_slug(trip, day, day['id'])
    trip.setdefault('days', []).append(day)
    trip['days'].sort(key=lambda d: (d.get('day_number') or 0, d.get('date') or ''))
    return _saved(save_travel(data), {'id': day['id']})


@admin_app.route('/api/travel/trips/<tid>/days/<did>', methods=['PUT', 'DELETE'])
def api_travel_day(tid: str, did: str):
    err = _api_auth()
    if err:
        return err
    data = load_travel()
    trip = _trip(data, tid)
    day = _day(trip, did) if trip else None
    if day is None:
        return jsonify({'error': 'not_found'}), 404
    if request.method == 'DELETE':
        trip['days'] = [d for d in trip['days'] if d.get('id') != did]
        ok = save_travel(data)
        if ok:
            log_audit('travel_day_delete', f"{trip.get('name', '')} #{day.get('day_number')}")
        return _saved(ok)
    merged = tb.normalize_day(request.get_json(silent=True) or {}, day)
    merged['id'] = did
    merged['slug'] = _trav_day_slug(trip, merged, did)
    trip['days'] = [merged if d.get('id') == did else d for d in trip['days']]
    trip['days'].sort(key=lambda d: (d.get('day_number') or 0, d.get('date') or ''))
    return _saved(save_travel(data))


def _travel_article_schema(langs: list[str], photos: int):
    """Antwortformat: je Sprache Titel, Anriss und Text, dazu Schlagwörter und
    eine Bildunterschrift je Fotohinweis."""
    per_lang = genai_types.Schema(
        type=genai_types.Type.OBJECT,
        properties={
            'title':  genai_types.Schema(type=genai_types.Type.STRING),
            'teaser': genai_types.Schema(type=genai_types.Type.STRING),
            'body':   genai_types.Schema(type=genai_types.Type.STRING),
        },
        required=['title', 'teaser', 'body'],
    )
    props = {lg: per_lang for lg in langs}
    props['tags'] = genai_types.Schema(
        type=genai_types.Type.ARRAY,
        items=genai_types.Schema(type=genai_types.Type.STRING))
    if photos:
        props['captions'] = genai_types.Schema(
            type=genai_types.Type.ARRAY,
            items=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={lg: genai_types.Schema(type=genai_types.Type.STRING)
                            for lg in langs},
                required=list(langs)))
    return genai_types.Schema(type=genai_types.Type.OBJECT, properties=props,
                              required=list(langs) + ['tags'])


# ── Wetter aus Home Assistant ─────────────────────────────────────────────────
#
# Das Wetter von Hand einzutippen ist unterwegs die lästigste Stelle des
# Formulars — und das Add-on läuft in Home Assistant, das den Wert kennt. Es
# gilt aber eine Einschränkung, die nicht wegzudiskutieren ist: eine
# Wetter-Entität misst dort, wo sie eingerichtet wurde, meist also zu Hause.
# Für eine Reise nach Kreta muss in HA eine Entität für das Reiseziel
# angelegt werden. Deshalb wird die Entität je Reise gewählt und nichts
# automatisch geraten.
#
# Ohne Supervisor-Token (MyPage unter Docker, ohne HA) gibt es diese Funktion
# nicht: dann fehlen die Knöpfe in der Oberfläche ganz, statt eine Meldung
# anzubieten, aus der niemand einen Ausweg hat.

_HA_STATES = 'http://supervisor/core/api/states'
_HA_HISTORY = 'http://supervisor/core/api/history/period'
_HA_ENTITY_RE = re.compile(r'^weather\.[a-z0-9_]{1,64}$')

# Home Assistant kennt mehr Zustände als das Formular Auswahlpunkte hat. Was
# sich nicht sinnvoll zuordnen lässt, bleibt bewusst leer — ein falsch geratenes
# Wetter wäre schlimmer als ein leeres Feld, das nachfragt.
_HA_CONDITIONS = {
    'sunny': 'sonnig', 'clear-night': 'sonnig',
    'partlycloudy': 'leicht bewölkt',
    'cloudy': 'bewölkt',
    'fog': 'neblig',
    'rainy': 'regnerisch', 'pouring': 'regnerisch', 'snowy-rainy': 'regnerisch',
    'snowy': 'Schneefall',
    'hail': 'stürmisch', 'lightning': 'stürmisch', 'lightning-rainy': 'stürmisch',
    'windy': 'stürmisch', 'windy-variant': 'stürmisch',
    'exceptional': 'wechselhaft',
}


def _ha_wind_label(speed, unit: str) -> str:
    """Windgeschwindigkeit zur Stufe des Formulars. Grenzen nach Beaufort:
    bis 5 km/h windstill, bis 19 leicht (Bft 1–3), bis 38 mäßig (4–5),
    bis 61 stark (6–7), darüber sehr stark (ab 8)."""
    try:
        kmh = float(speed)
    except (TypeError, ValueError):
        return ''
    unit = (unit or 'km/h').lower()
    if unit in ('m/s', 'ms'):
        kmh *= 3.6
    elif unit in ('mph', 'mi/h'):
        kmh *= 1.609344
    elif unit in ('kn', 'knots'):
        kmh *= 1.852
    for limit, label in ((6, 'windstill'), (20, 'leicht'), (39, 'mäßig'), (62, 'stark')):
        if kmh < limit:
            return label
    return 'sehr stark'


def _ha_weather_from_state(state: dict) -> dict:
    """Ein HA-Zustandsobjekt in die Felder des Wetter-Schritts übersetzen."""
    attrs = state.get('attributes') or {}
    temp = attrs.get('temperature')
    if temp is not None and str(attrs.get('temperature_unit') or '°C').strip() == '°F':
        try:
            temp = round((float(temp) - 32) * 5 / 9, 1)
        except (TypeError, ValueError):
            temp = None
    try:
        temp = round(float(temp), 1) if temp is not None else None
    except (TypeError, ValueError):
        temp = None
    return {
        'condition': _HA_CONDITIONS.get(state.get('state') or '', ''),
        'raw_condition': _clean_str(state.get('state'), 40),
        'temperature': temp,
        'wind': _ha_wind_label(attrs.get('wind_speed'),
                               attrs.get('wind_speed_unit') or 'km/h'),
        'at': _clean_str(state.get('last_changed'), 40),
    }


@admin_app.route('/api/travel/ha/weather-entities')
def api_travel_ha_entities():
    """Wetter-Entitäten zur Auswahl im Reise-Dialog."""
    err = _api_auth()
    if err:
        return err
    if not SUPERVISOR_TOKEN:
        return jsonify({'on_ha': False, 'entities': []})
    try:
        r = http.get(_HA_STATES, timeout=10,
                     headers={'Authorization': f'Bearer {SUPERVISOR_TOKEN}'})
        r.raise_for_status()
        states = r.json()
    except Exception as e:
        log.warning("HA-Wetterentitäten nicht abrufbar: %s: %s", type(e).__name__, e)
        return jsonify({'on_ha': True, 'entities': [], 'error': 'ha_failed'}), 502
    out = []
    for st in states if isinstance(states, list) else []:
        eid = st.get('entity_id') or ''
        if _HA_ENTITY_RE.match(eid):
            out.append({'id': eid,
                        'name': _clean_str((st.get('attributes') or {}).get('friendly_name')
                                           or eid, 120)})
    out.sort(key=lambda x: x['name'].lower())
    return jsonify({'on_ha': True, 'entities': out})


@admin_app.route('/api/travel/ha/weather')
def api_travel_ha_weather():
    """Wetter zu einem Reisetag. Für heute der aktuelle Zustand, für ein
    vergangenes Datum der Verlauf aus dem Recorder — dessen Aufbewahrung ist
    begrenzt (Standard zehn Tage), weiter zurück gibt es schlicht nichts."""
    err = _api_auth()
    if err:
        return err
    if not SUPERVISOR_TOKEN:
        return jsonify({'error': 'not_on_ha'}), 400
    entity = request.args.get('entity', '')
    if not _HA_ENTITY_RE.match(entity):
        return jsonify({'error': 'invalid'}), 400
    day = request.args.get('date', '')
    try:
        wanted = date.fromisoformat(day)
    except ValueError:
        return jsonify({'error': 'invalid'}), 400
    today = datetime.now().astimezone().date()
    if wanted > today:
        return jsonify({'error': 'future'}), 400
    headers = {'Authorization': f'Bearer {SUPERVISOR_TOKEN}'}
    try:
        if wanted == today:
            r = http.get(f'{_HA_STATES}/{entity}', timeout=10, headers=headers)
            if r.status_code == 404:
                return jsonify({'error': 'no_entity'}), 404
            r.raise_for_status()
            return jsonify({'ok': True, 'source': 'now'} | _ha_weather_from_state(r.json()))
        tz = datetime.now().astimezone().tzinfo
        start = datetime.combine(wanted, dtime(0, 0), tz)
        end = datetime.combine(wanted, dtime(23, 59, 59), tz)
        r = http.get(f'{_HA_HISTORY}/{start.isoformat()}', timeout=20, headers=headers,
                     params={'filter_entity_id': entity, 'end_time': end.isoformat()})
        r.raise_for_status()
        series = r.json()
    except Exception as e:
        log.warning("HA-Wetter (%s) nicht abrufbar: %s: %s", entity, type(e).__name__, e)
        return jsonify({'error': 'ha_failed'}), 502
    rows = (series[0] if isinstance(series, list) and series
            and isinstance(series[0], list) else [])
    # Der Zustand um die Mittagszeit beschreibt einen Reisetag besser als der um
    # Mitternacht — und besser als ein Durchschnitt, den es als Wetterlage
    # ohnehin nicht gibt („teils sonnig, teils Gewitter" ist keine Auswahl).
    noon = datetime.combine(wanted, dtime(13, 0), tz)
    best, best_gap = None, None
    for st in rows:
        if not isinstance(st, dict) or st.get('state') in (None, 'unknown', 'unavailable'):
            continue
        stamp = st.get('last_changed') or st.get('last_updated') or ''
        try:
            when = datetime.fromisoformat(stamp)
        except ValueError:
            continue
        gap = abs((when - noon).total_seconds())
        if best_gap is None or gap < best_gap:
            best, best_gap = st, gap
    if best is None:
        return jsonify({'error': 'no_history'}), 404
    return jsonify({'ok': True, 'source': 'history'} | _ha_weather_from_state(best))


def _travel_article_call(*, prompt: str, system: str, langs: list[str],
                         photos: int, model: str) -> tuple[dict | None, dict, int]:
    """Ein Reisebericht-Lauf. Erzeugen und Überarbeiten unterscheiden sich nur in
    Prompt und Systemanweisung — der Rest bis hin zur Fehlerbehandlung ist gleich,
    und zweimal derselbe Block wäre zweimal zu pflegen."""
    try:
        client = _gemini_client()
        resp = client.models.generate_content(
            model=model, contents=[prompt],
            config=genai_types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type='application/json',
                response_schema=_travel_article_schema(langs, photos),
                http_options=genai_types.HttpOptions(timeout=GEMINI_TEXT_TIMEOUT_MS),
            ),
        )
        _ai_usage_record(model, resp)
        cands = resp.candidates or []
        finish = cands[0].finish_reason if cands else None
        reason = getattr(finish, 'name', None) or (str(finish) if finish else '')
        if finish in _GEMINI_TEXT_REFUSALS:
            return None, {'error': 'ai_refused', 'detail': reason}, 502
        raw = json.loads(resp.text or '')
        if not isinstance(raw, dict):
            return None, {'error': 'ai_empty', 'detail': reason}, 502
    except genai_errors.APIError as e:
        code = getattr(e, 'code', None)
        log.warning("Reisebericht fehlgeschlagen (%s): Status %s", model, code)
        return None, {'error': 'ai_model_missing' if code == 404 else 'ai_failed',
                      'detail': f'HTTP {code}' if code else '', 'model': model}, 502
    except Exception as e:
        log.error("Reisebericht (%s) unerwartet fehlgeschlagen: %s: %s",
                  model, type(e).__name__, e)
        return None, {'error': 'ai_failed', 'detail': type(e).__name__, 'model': model}, 502
    return tb.normalize_article(raw), {}, 200


@admin_app.route('/api/travel/trips/<tid>/days/<did>/generate', methods=['POST'])
def api_travel_generate(tid: str, did: str):
    err = _api_auth()
    if err:
        return err
    if not gemini_text_enabled():
        return jsonify({'error': 'no_api_key'}), 400
    data = load_travel()
    trip = _trip(data, tid)
    day = _day(trip, did) if trip else None
    if day is None:
        return jsonify({'error': 'not_found'}), 404
    langs = (trip.get('settings') or {}).get('langs') or ['de']
    # Vortage nach Tagesnummer, damit der Kontext stimmt, auch wenn ein Tag
    # nachträglich eingeschoben wurde
    previous = [d for d in trip.get('days', [])
                if (d.get('day_number') or 0) < (day.get('day_number') or 0)]
    prompt = tb.build_prompt(trip, day, previous)
    photo_notes = [p for p in (day.get('photos') or []) if p.get('photo_note')]
    if not _ai_rate_take(_ai_text_times, AI_TEXT_MAX_PER_HOUR):
        return jsonify({'error': 'rate_limited'}), 429
    model = _gemini_text_model()
    article, err, status = _travel_article_call(
        prompt=prompt, system=tb.SYSTEM_PROMPT + _ai_address_note(), langs=langs,
        photos=len(photo_notes), model=model)
    if article is None:
        return jsonify(err), status
    log.info("Reisebericht erzeugt: %s Tag %s (%s, %s)", trip.get('name'),
             day.get('day_number'), model, '+'.join(langs))
    return jsonify({'ok': True, 'article': article, 'prompt': prompt})


@admin_app.route('/api/travel/trips/<tid>/days/<did>/revise', methods=['POST'])
def api_travel_revise(tid: str, did: str):
    """Vorhandenen Bericht überarbeiten statt neu erzeugen.

    Der Text kommt aus dem Formular, nicht aus der gespeicherten Fassung: der
    Wizard speichert vor dem Aufruf zwar, aber der Nutzer soll auch eine gerade
    von Hand geänderte Zeile mitgeben können, ohne sie vorher zu sichern.
    """
    err = _api_auth()
    if err:
        return err
    if not gemini_text_enabled():
        return jsonify({'error': 'no_api_key'}), 400
    raw = request.get_json(silent=True) or {}
    action = raw.get('action') if raw.get('action') in tb.REVISE_ACTIONS else ''
    note = _clean_str(raw.get('note'), tb.REVISE_NOTE_MAX)
    if not action or (action == 'custom' and not note):
        return jsonify({'error': 'invalid'}), 400
    data = load_travel()
    trip = _trip(data, tid)
    day = _day(trip, did) if trip else None
    if day is None:
        return jsonify({'error': 'not_found'}), 404
    trip_langs = (trip.get('settings') or {}).get('langs') or ['de']
    wanted = raw.get('langs')
    langs = [lg for lg in trip_langs
             if isinstance(wanted, list) and lg in wanted] or trip_langs
    article = tb.normalize_article(raw.get('article')
                                   if isinstance(raw.get('article'), dict)
                                   else (day.get('article') or {}))
    # Ohne Text gibt es nichts zu überarbeiten — und ein leerer Auftrag käme als
    # frei erfundener Bericht zurück, genau das, was der Systemprompt verbietet.
    if not any((article.get(lg) or {}).get('body') for lg in langs):
        return jsonify({'error': 'no_article'}), 400
    if not _ai_rate_take(_ai_text_times, AI_TEXT_MAX_PER_HOUR):
        return jsonify({'error': 'rate_limited'}), 429
    photo_notes = [p for p in (day.get('photos') or []) if p.get('photo_note')]
    prompt = tb.build_revise_prompt(
        trip, article, langs, action, note,
        data_block=tb.build_prompt(trip, day, include_style=False),
        photo_notes=[p['photo_note'] for p in photo_notes])
    model = _gemini_text_model()
    fresh, err, status = _travel_article_call(
        prompt=prompt, system=tb.REVISE_SYSTEM_PROMPT + _ai_address_note(), langs=langs,
        photos=len(photo_notes), model=model)
    if fresh is None:
        return jsonify(err), status
    # Nur die angeforderten Sprachen ersetzen: wer allein die englische Fassung
    # überarbeiten lässt, darf die deutsche nicht verlieren.
    for lg in ('de', 'en'):
        if lg not in langs:
            fresh[lg] = article.get(lg) or {'title': '', 'teaser': '', 'body': ''}
    if not fresh.get('captions'):
        fresh['captions'] = article.get('captions') or []
    log.info("Reisebericht überarbeitet (%s): %s Tag %s (%s, %s)", action,
             trip.get('name'), day.get('day_number'), model, '+'.join(langs))
    return jsonify({'ok': True, 'article': fresh, 'prompt': prompt})


# ── Ort zu Koordinaten ────────────────────────────────────────────────────────
#
# Ein Foto liefert GPS, das Formular will einen Ortsnamen. Dazwischen steht ein
# Dienst, der beides verbindet — hier Nominatim von OpenStreetMap, weil er ohne
# Schlüssel auskommt. Die Anfrage passiert deshalb NUR auf Knopfdruck: die
# Koordinaten eines privaten Fotos ungefragt an einen fremden Server zu schicken
# wäre das Gegenteil dessen, was der EXIF-Auswurf beim Upload bezweckt.

NOMINATIM_URL = 'https://nominatim.openstreetmap.org/reverse'
# Nominatim verlangt eine Kennung mit Kontaktweg, sonst sperrt es die Anfragen
NOMINATIM_UA = 'MyPage-Addon (https://github.com/LuckyTriple7/HA-AddOns)'


@admin_app.route('/api/travel/geocode')
def api_travel_geocode():
    err = _api_auth()
    if err:
        return err
    try:
        lat = float(request.args.get('lat', ''))
        lon = float(request.args.get('lon', ''))
    except ValueError:
        return jsonify({'error': 'invalid'}), 400
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return jsonify({'error': 'invalid'}), 400
    try:
        r = http.get(NOMINATIM_URL, timeout=15,
                     params={'format': 'jsonv2', 'lat': f'{lat:.6f}', 'lon': f'{lon:.6f}',
                             'zoom': '12', 'accept-language': 'de'},
                     # Nominatim verlangt eine Kennung, sonst sperrt es
                     headers={'User-Agent': NOMINATIM_UA})
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.warning("Nominatim nicht erreichbar: %s: %s", type(e).__name__, e)
        return jsonify({'error': 'geo_failed'}), 502
    addr = data.get('address') if isinstance(data, dict) else {}
    addr = addr if isinstance(addr, dict) else {}
    place = next((addr[k] for k in ('city', 'town', 'village', 'municipality',
                                    'county', 'state') if addr.get(k)), '')
    if not place:
        return jsonify({'error': 'no_place'}), 404
    return jsonify({'ok': True, 'place': _clean_str(place, 120),
                    'country': _clean_str(addr.get('country'), 80)})


# ── Reise-Rückblick ───────────────────────────────────────────────────────────
#
# Der Text über die ganze Reise, der auf der Reise-Seite über der Tagesliste
# steht. Er entsteht aus den fertigen Tagesberichten und wird getrennt
# freigegeben: ein Rückblick, der halb fertig im Netz steht, wäre schlimmer als
# gar keiner.

def _travel_recap_schema(langs: list[str]):
    per_lang = genai_types.Schema(
        type=genai_types.Type.OBJECT,
        properties={'title':  genai_types.Schema(type=genai_types.Type.STRING),
                    'teaser': genai_types.Schema(type=genai_types.Type.STRING),
                    'body':   genai_types.Schema(type=genai_types.Type.STRING)},
        required=['title', 'teaser', 'body'])
    props = {lg: per_lang for lg in langs}
    props['tags'] = genai_types.Schema(
        type=genai_types.Type.ARRAY,
        items=genai_types.Schema(type=genai_types.Type.STRING))
    return genai_types.Schema(type=genai_types.Type.OBJECT, properties=props,
                              required=list(langs) + ['tags'])


def _travel_recap_call(*, prompt: str, system: str, langs: list[str], model: str
                       ) -> tuple[dict | None, dict, int]:
    """Wie `_travel_article_call`, nur mit dem Schema ohne Bildunterschriften."""
    try:
        client = _gemini_client()
        resp = client.models.generate_content(
            model=model, contents=[prompt],
            config=genai_types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type='application/json',
                response_schema=_travel_recap_schema(langs),
                http_options=genai_types.HttpOptions(timeout=GEMINI_TEXT_TIMEOUT_MS),
            ),
        )
        _ai_usage_record(model, resp)
        cands = resp.candidates or []
        finish = cands[0].finish_reason if cands else None
        reason = getattr(finish, 'name', None) or (str(finish) if finish else '')
        if finish in _GEMINI_TEXT_REFUSALS:
            return None, {'error': 'ai_refused', 'detail': reason}, 502
        raw = json.loads(resp.text or '')
        if not isinstance(raw, dict):
            return None, {'error': 'ai_empty', 'detail': reason}, 502
    except genai_errors.APIError as e:
        code = getattr(e, 'code', None)
        log.warning("Reise-Rückblick fehlgeschlagen (%s): Status %s", model, code)
        return None, {'error': 'ai_model_missing' if code == 404 else 'ai_failed',
                      'detail': f'HTTP {code}' if code else '', 'model': model}, 502
    except Exception as e:
        log.error("Reise-Rückblick (%s) unerwartet fehlgeschlagen: %s: %s",
                  model, type(e).__name__, e)
        return None, {'error': 'ai_failed', 'detail': type(e).__name__, 'model': model}, 502
    return tb.normalize_recap(raw), {}, 200


def _recap_days(trip: dict) -> list:
    """Tage mit fertigem Bericht, nach Reisetag sortiert. Ein Tag ohne Text
    trägt nichts bei — seine Rohdaten stünden im Rückblick unvermittelt neben
    den erzählten Tagen."""
    return sorted([d for d in (trip.get('days') or [])
                   if any(((d.get('article') or {}).get(lg) or {}).get('body')
                          for lg in ('de', 'en'))],
                  key=lambda d: d.get('day_number') or 0)


@admin_app.route('/api/travel/trips/<tid>/recap', methods=['POST', 'PUT'])
def api_travel_recap(tid: str):
    """POST erzeugt den Rückblick, PUT speichert ihn samt Freigabe."""
    err = _api_auth()
    if err:
        return err
    data = load_travel()
    trip = _trip(data, tid)
    if trip is None:
        return jsonify({'error': 'not_found'}), 404
    raw = request.get_json(silent=True) or {}

    if request.method == 'PUT':
        trip['recap'] = tb.normalize_recap(raw.get('recap'))
        trip['recap_published'] = bool(raw.get('recap_published'))
        return _saved(save_travel(data))

    if not gemini_text_enabled():
        return jsonify({'error': 'no_api_key'}), 400
    days = _recap_days(trip)
    if not days:
        return jsonify({'error': 'no_days'}), 400
    langs = (trip.get('settings') or {}).get('langs') or ['de']
    if not _ai_rate_take(_ai_text_times, AI_TEXT_MAX_PER_HOUR):
        return jsonify({'error': 'rate_limited'}), 429
    prompt = tb.build_recap_prompt(trip, days)
    model = _gemini_text_model()
    recap, err, status = _travel_recap_call(
        prompt=prompt, system=tb.RECAP_SYSTEM_PROMPT + _ai_address_note(),
        langs=langs, model=model)
    if recap is None:
        return jsonify(err), status
    log.info("Reise-Rückblick erzeugt: %s (%s Tage, %s, %s)", trip.get('name'),
             len(days), model, '+'.join(langs))
    return jsonify({'ok': True, 'recap': recap, 'prompt': prompt})


@admin_app.route('/api/travel/trips/<tid>/recap/revise', methods=['POST'])
def api_travel_recap_revise(tid: str):
    """Rückblick überarbeiten — derselbe Werkzeugkasten wie beim Tagesbericht."""
    err = _api_auth()
    if err:
        return err
    if not gemini_text_enabled():
        return jsonify({'error': 'no_api_key'}), 400
    raw = request.get_json(silent=True) or {}
    action = raw.get('action') if raw.get('action') in tb.REVISE_ACTIONS else ''
    note = _clean_str(raw.get('note'), tb.REVISE_NOTE_MAX)
    if not action or (action == 'custom' and not note):
        return jsonify({'error': 'invalid'}), 400
    data = load_travel()
    trip = _trip(data, tid)
    if trip is None:
        return jsonify({'error': 'not_found'}), 404
    trip_langs = (trip.get('settings') or {}).get('langs') or ['de']
    wanted = raw.get('langs')
    langs = [lg for lg in trip_langs
             if isinstance(wanted, list) and lg in wanted] or trip_langs
    recap = tb.normalize_recap(raw.get('recap') if isinstance(raw.get('recap'), dict)
                               else (trip.get('recap') or {}))
    if not any((recap.get(lg) or {}).get('body') for lg in langs):
        return jsonify({'error': 'no_article'}), 400
    if not _ai_rate_take(_ai_text_times, AI_TEXT_MAX_PER_HOUR):
        return jsonify({'error': 'rate_limited'}), 429
    prompt = tb.build_revise_prompt(
        trip, recap, langs, action, note, recap=True,
        data_block=tb.build_recap_prompt(trip, _recap_days(trip)))
    model = _gemini_text_model()
    fresh, err, status = _travel_recap_call(
        prompt=prompt, system=tb.RECAP_SYSTEM_PROMPT + _ai_address_note(),
        langs=langs, model=model)
    if fresh is None:
        return jsonify(err), status
    for lg in ('de', 'en'):
        if lg not in langs:
            fresh[lg] = recap.get(lg) or {'title': '', 'teaser': '', 'body': ''}
    log.info("Reise-Rückblick überarbeitet (%s): %s (%s, %s)", action,
             trip.get('name'), model, '+'.join(langs))
    return jsonify({'ok': True, 'recap': fresh, 'prompt': prompt})


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
        # Bewusst ohne die Dienstnamen: sie stammen aus der Antwort auf eine
        # Anfrage, die den Abrechnungs-Schlüssel trägt, und alles daraus gilt
        # als schutzbedürftig (CodeQL py/clear-text-logging-sensitive-data).
        # Verloren geht nichts — die Namen stehen unten im Ergebnis unter
        # `services` und damit im Admin.
        log.info("Preiskatalog: %d Dienste gelesen, %d passen",
                 len(services), len(matched))
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
        # Der Preiskatalog wird mit dem Abrechnungs-Schlüssel abgefragt; alles,
        # was aus dieser Antwort stammt, gehört nicht in eine Logdatei, die im
        # Supportfall weitergereicht wird. Das gilt auch für `code`: er entsteht
        # in `_billing_error` durch Nachschlagen mit einem Schlüssel aus Googles
        # Antwort. Deshalb wird hier **kein** Wert übergeben, sondern die Meldung
        # ausgewählt — was im Log landet, ist damit nachweislich fester Text.
        # (Zwei sanftere Fassungen — Nachschlagen im Wörterbuch, Holen aus einer
        # Konstantenliste — hat CodeQL beide weiterhin bemängelt; die Markierung
        # überlebt jeden Umweg, der den Wert noch anfasst.)
        # Der Admin bekommt Code und Klartextgrund unverändert in der Antwort.
        if code == 'billing_disabled':
            log.info("Preiskatalog abgelehnt: Abrechnung im Google-Projekt nicht aktiviert")
        elif code == 'key_rejected':
            log.info("Preiskatalog abgelehnt: Schlüssel zurückgewiesen")
        elif code == 'service_not_found':
            log.info("Preiskatalog abgelehnt: kein passender Dienst im Katalog")
        else:
            log.info("Preiskatalog abgelehnt")
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
    lay = _clean_str(raw.get('layout'), 20)
    lib['layout'] = lay if lay in LIB_LAYOUTS else 'carousel'
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
    entry['slug'], slug_changed = _lib_entry_slug(site, raw, entry['id'])
    lib['entries'].append(entry)
    pdf_state = _library_apply_pdf(site, entry)
    save_site(site)
    return jsonify({'ok': True, 'slug': entry['slug'], 'pdf': pdf_state,
                    'slug_changed': slug_changed})


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
    entries[idx]['slug'], slug_changed = _lib_entry_slug(site, raw, eid)
    pdf_state = _library_apply_pdf(site, entries[idx])
    save_site(site)
    return jsonify({'ok': True, 'slug': entries[idx]['slug'], 'pdf': pdf_state,
                    'slug_changed': slug_changed})


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
    # Eine Kopie soll eine neue Adresse bekommen — die Abweichung ist hier
    # der Zweck und keine Meldung wert.
    copy['slug'] = _lib_entry_slug(site, {'slug': src.get('slug', '')}, copy['id'])[0]
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


@admin_app.route('/api/upload-doc', methods=['POST'])
@admin_app.route('/api/library/upload-doc', methods=['POST'])
def api_library_upload_doc():
    """PDF-Upload für Bibliothek und Download-Abschnitt (getrennt von /api/upload
    für Bilder). Beide legen in derselben Ablage ab; der ältere Pfad bleibt, damit
    eine offene Oberfläche nach dem Update weiterarbeitet."""
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
    form['slug'], slug_changed = _form_slug(site, raw, form['id'])
    site.setdefault('forms', []).append(form)
    save_site(site)
    return jsonify({'ok': True, 'slug': form['slug'], 'slug_changed': slug_changed})


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
    forms[idx]['slug'], slug_changed = _form_slug(site, raw, fid)
    save_site(site)
    return jsonify({'ok': True, 'slug': forms[idx]['slug'], 'slug_changed': slug_changed})


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


@admin_app.route('/api/settings')
def api_settings_get():
    """Wirksame Einstellungen für die Oberfläche — geheime Felder nur als Ja/Nein."""
    err = _api_auth()
    if err:
        return err
    data = settings_store.public_view(load_config())
    data['smb_live'] = SMB_MOUNTED
    data['on_ha'] = bool(SUPERVISOR_TOKEN)
    return jsonify(data)


@admin_app.route('/api/settings', methods=['POST'])
def api_settings_save():
    err = _api_auth()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    values = body.get('values')
    clear = body.get('clear') or []
    if not isinstance(values, dict) or not isinstance(clear, list):
        return jsonify({'error': 'invalid'}), 400
    clear = [k for k in clear if isinstance(k, str) and k in settings_store.FIELDS]
    try:
        changed = settings_store.save(values, clear)
    except OSError as e:
        log.warning("Einstellungen konnten nicht geschrieben werden: %s", e)
        return jsonify({'error': 'write failed'}), 500
    _settings_changed()
    restart = False
    if changed:
        cfg = load_config()
        # Alles sofort wirksam machen, was ohne Neustart geht — sonst wundert
        # sich der Admin, warum die gerade gespeicherte Zahl nichts tut.
        if 'user_upload_max_mb' in changed:
            mb = max(1, min(4096, int(cfg.get('user_upload_max_mb') or 200)))
            public_app.config['MAX_CONTENT_LENGTH'] = mb * 1024 * 1024
        if 'visit_bot_nets' in changed:
            vx.set_extra_bot_nets(cfg.get('visit_bot_nets') or [])
        if any(k in settings_store.SMB_KEYS for k in changed):
            if SMB_MOUNTED:
                # Remount kann Sekunden dauern — Antwort nicht blockieren
                threading.Thread(target=remount_smb, daemon=True).start()
            else:
                restart = True   # Mountpunkt fehlt, den legt erst run.sh an
        # Nur die Feldnamen ins Protokoll, niemals die Werte
        log_audit('settings_update', ', '.join(sorted(changed))[:200])
    return jsonify({'ok': True, 'changed': sorted(changed), 'restart': restart})


# Schlüssel-Export ist die einzige Stelle, an der ein Geheimnis das Add-on
# verlässt. Deshalb: Admin-Passwort (und 2FA, falls aktiv) erneut abfragen,
# Fehlversuche bremsen und jeden Vorgang ins Audit-Log schreiben.
_key_gate: dict = {'fails': 0, 'until': 0.0}
_KEY_GATE_MAX = 5
_KEY_GATE_LOCK_S = 300


def _key_gate_check(password: str, code: str,
                    audit: str = 'settings_key_denied') -> tuple | None:
    """None = freigegeben, sonst die fertige Fehlerantwort.

    Gemeinsame Sperre für alle Stellen, die das Admin-Passwort erneut abfragen
    (Schlüssel-Export/-Import, Passwortwechsel): fünf Fehlversuche, dann fünf
    Minuten zu. `audit` benennt den Vorgang im Protokoll.
    """
    now = time.time()
    if _key_gate['until'] > now:
        return jsonify({'error': 'locked',
                        'retry_after': int(_key_gate['until'] - now)}), 429
    ok = admin_password_ok(password)
    if ok and twofa_enabled():
        ok = totp_verify(load_2fa().get('secret', ''), code or '') or backup_code_consume(code or '')
    if not ok:
        _key_gate['fails'] += 1
        if _key_gate['fails'] >= _KEY_GATE_MAX:
            _key_gate['until'] = now + _KEY_GATE_LOCK_S
            _key_gate['fails'] = 0
        log_audit(audit)
        return jsonify({'error': 'auth'}), 403
    _key_gate['fails'] = 0
    return None


def _key_error(exc: ValueError):
    """Fehlercode der Schlüssel-Funktionen in eine feste Antwort übersetzen.

    Bewusst eine Kette fester Zeichenketten statt `str(exc)`: aus einer
    Ausnahme darf nie Text nach außen gehen (CodeQL: information exposure
    through an exception). Der Code der Ausnahme wird nur verglichen, geantwortet
    wird ausschließlich mit hier stehenden Literalen.
    """
    code = exc.args[0] if exc.args else ''
    if code == 'passphrase_short':
        return jsonify({'error': 'passphrase_short'}), 400
    if code == 'wrong_passphrase':
        return jsonify({'error': 'wrong_passphrase'}), 400
    if code == 'invalid_file':
        return jsonify({'error': 'invalid_file'}), 400
    if code == 'no_key':
        return jsonify({'error': 'no_key'}), 400
    if code == 'exists':
        return jsonify({'error': 'exists'}), 400
    if code == 'crypto_unavailable':
        return jsonify({'error': 'crypto_unavailable'}), 400
    return jsonify({'error': 'invalid'}), 400


@admin_app.route('/api/settings/key', methods=['GET'])
def api_settings_key_state():
    err = _api_auth()
    if err:
        return err
    return jsonify({'key': settings_store.key_exists(),
                    'min_len': settings_store.KEY_PASSPHRASE_MIN,
                    'twofa': twofa_enabled()})


@admin_app.route('/api/settings/key/export', methods=['POST'])
def api_settings_key_export():
    err = _api_auth()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    if (gate := _key_gate_check(body.get('password'), body.get('code'))):
        return gate
    try:
        data = settings_store.export_key(str(body.get('passphrase') or ''))
    except ValueError as e:
        return _key_error(e)
    log_audit('settings_key_export')
    return Response(data, mimetype='application/json', headers={
        'Content-Disposition': 'attachment; filename="mypage-settings-key.json"',
        'Cache-Control': 'no-store'})


@admin_app.route('/api/settings/key/import', methods=['POST'])
def api_settings_key_import():
    err = _api_auth()
    if err:
        return err
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'error': 'no file'}), 400
    if (gate := _key_gate_check(request.form.get('password'), request.form.get('code'))):
        return gate
    data = f.read(64 * 1024)   # die Exportdatei ist wenige hundert Byte groß
    try:
        readable = settings_store.import_key(
            data, request.form.get('passphrase') or '',
            overwrite=request.form.get('overwrite') == '1')
    except ValueError as e:
        return _key_error(e)
    except OSError as e:
        log.warning("Schlüssel konnte nicht geschrieben werden: %s", e)
        return jsonify({'error': 'write failed'}), 500
    _settings_changed()
    log_audit('settings_key_import', f'{readable} Feld(er) lesbar')
    return jsonify({'ok': True, 'readable': readable})


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


@admin_app.route('/api/preview')
def api_preview():
    """Die öffentliche Startseite als HTML für den Vorschau-Rahmen.

    Ein Rahmen, der die öffentliche Adresse direkt lädt, scheitert an zwei
    Stellen, die MyPage nicht in der Hand hat: Reverse Proxies setzen
    `X-Frame-Options` (Klickjacking-Schutz, der so bleiben soll), und über den
    Ingress läuft der Admin unter der Adresse von Home Assistant — Port 17760
    ist dort nicht zwingend erreichbar, bei HTTPS lädt der Browser eine
    http-Seite im Rahmen ohnehin nicht.

    Deshalb rendert der Admin die Seite selbst (derselbe Prozess, kein Netz)
    und reicht sie als `srcdoc` weiter: gleiche Herkunft, damit greift keine
    der beiden Sperren. `X-MyPage-Export` verhindert wie beim statischen
    Export, dass der Besucherzähler den eigenen Blick mitzählt.

    Das eingefügte `<base>` sorgt dafür, dass Bilder und Schriften trotzdem
    von der echten Seite kommen. Bei HTTPS muss die Basis ebenfalls HTTPS
    sein, sonst blockiert der Browser sie als gemischten Inhalt — dann taugt
    nur die eingetragene öffentliche URL. Sonst reicht der Nachbarport.
    """
    err = _api_auth()
    if err:
        return err
    base = (load_site()['design'].get('public_url') or '').rstrip('/')
    host = (request.host or '').split(':')[0]
    port_base = f'http://{host}:{PUBLIC_PORT}'
    if request.scheme == 'https':
        base = base if base.startswith('https://') else ''
    else:
        base = base or port_base
    client = public_app.test_client()
    r = client.get('/', headers={'Accept-Language': request.headers.get('Accept-Language', 'de'),
                                 'X-MyPage-Export': '1'})
    if r.status_code != 200:
        return jsonify({'error': 'render_failed', 'status': r.status_code}), 502
    html = r.get_data(as_text=True)
    # target="_blank" gehört dazu: im Rahmen geklickte Links liefen sonst genau
    # in die X-Frame-Options-Sperre, wegen der die Vorschau hier gerendert wird.
    tag = f'<base href="{escape(base)}/" target="_blank">' if base else ''
    if tag:
        i = html.lower().find('<head>')
        html = (html[:i + 6] + tag + html[i + 6:]) if i >= 0 else tag + html
    return jsonify({'html': html, 'base': base})


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
    for p in projects_public(site):
        if _has_detail(p):
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
    # Dateien des Download-Abschnitts gehören in den Export: sonst zeigt die
    # exportierte Seite auf Adressen, die es außerhalb des Add-ons nicht gibt.
    if 'downloads' not in set(site.get('hidden_sections') or []) \
            and 'downloads' not in set(site.get('members_sections') or []):
        for d in (site.get('sections') or {}).get('downloads') or []:
            fn = d.get('file') or ''
            if _DOC_FILE_RE.match(fn):
                pages[f'download/{fn}'] = f'/download/{fn}'
    trav_trips = _trav_public_trips(site)
    if trav_trips:
        pages['reiseblog/index.html'] = '/reiseblog'
        for tr in trav_trips:
            pages[f"reiseblog/{tr['slug']}/index.html"] = f"/reiseblog/{tr['slug']}"
            for d in _trav_public_days(tr):
                pages[f"reiseblog/{tr['slug']}/{d['slug']}/index.html"] = \
                    f"/reiseblog/{tr['slug']}/{d['slug']}"
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


def _exif_facts(img) -> dict:
    """Aufnahmedatum und GPS aus dem EXIF-Block, bevor er verworfen wird.

    Nur für den Reiseblog gedacht: dort spart es das Abtippen von Datum und Ort.
    Gespeichert wird davon **nichts** — die Werte gehen einmal an den Browser des
    Admins zurück, der sie ins Formular übernimmt. Die abgelegte Bilddatei bleibt
    wie bisher metadatenfrei (siehe `_store_upload_image`).
    """
    try:
        exif = img.getexif()
    except Exception:
        return {}
    out = {}
    try:
        # DateTimeOriginal steht im Exif-IFD, nicht im Haupt-IFD
        taken = (exif.get_ifd(0x8769) or {}).get(36867) or exif.get(306) or ''
        if isinstance(taken, str) and len(taken) >= 10:
            iso = taken[:10].replace(':', '-')
            date.fromisoformat(iso)          # wirft, wenn es kein Datum ist
            out['taken'] = iso
    except Exception:
        pass
    try:
        gps = exif.get_ifd(0x8825) or {}

        def _deg(value, ref: str):
            d, m, sec = (float(x) for x in value)
            dec = d + m / 60 + sec / 3600
            return round(-dec if ref in ('S', 'W') else dec, 6)

        if gps.get(2) and gps.get(4):
            lat = _deg(gps[2], str(gps.get(1) or 'N'))
            lon = _deg(gps[4], str(gps.get(3) or 'E'))
            if -90 <= lat <= 90 and -180 <= lon <= 180 and (lat or lon):
                out['lat'], out['lon'] = lat, lon
    except Exception:
        pass
    return out


def _store_upload_image(src, *, max_side: int = 1600, quality: int = 82,
                        ai: bool = False, meta: dict | None = None,
                        name: str | None = None) -> str | None:
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
    # Was der Reiseblog gebrauchen kann, vor dem Verwerfen herauslesen. Der
    # Aufrufer entscheidet, ob er danach fragt; ohne `meta` ändert sich nichts.
    if meta is not None:
        meta.update(_exif_facts(img))
    # EXIF-Orientierung anwenden (sonst erscheinen Handy-Hochkant-Fotos gedreht)
    # und damit zugleich Metadaten verwerfen (GPS/Kamera) — Datenschutz.
    img = ImageOps.exif_transpose(img)
    img.thumbnail((max_side, max_side))
    if img.mode not in ('RGB', 'RGBA'):
        img = img.convert('RGBA' if 'A' in img.getbands() else 'RGB')
    # `name` setzt nur das Ersetzen: dann behält die Datei ihren Namen, damit
    # jede Einbindung weiter zeigt, wohin sie zeigte. Die `-ai`-Kennzeichnung
    # steckt im Namen und bleibt dadurch erhalten — sie darf beim Austausch des
    # Inhalts nicht verlorengehen.
    name = name or (uuid.uuid4().hex + (AI_IMAGE_SUFFIX if ai else '') + '.webp')
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
            meta: dict = {}
            name = _store_upload_image(f.stream, meta=meta)
            if name:
                # Der Herkunftsname ist das Einzige, woran ein Mensch die Datei
                # später wiedererkennt — abgelegt wird sie unter einer UUID.
                # Nur der Name, nicht der Pfad: der verriete das Verzeichnis des
                # Hochladenden.
                _uploads_file_meta_set(name, orig=Path(f.filename).name)
                # `exif` geht nur an den Browser zurück, der die Datei gerade
                # hochgeladen hat — abgelegt wird davon nichts.
                return jsonify({'ok': True, 'url': '/uploads/' + name, 'exif': meta})
        except Exception as e:
            log.warning("Bild-Optimierung fehlgeschlagen, speichere Original: %s", e)
        f.stream.seek(0)
    # ext stammt aus dem Dateinamen, ist aber gegen ALLOWED_UPLOAD_EXT geprüft
    name = uuid.uuid4().hex + ext
    target = safe_under(UPLOADS_DIR, name)
    if target is None:
        abort(400)
    f.save(target)
    _uploads_file_meta_set(name, orig=Path(f.filename).name)
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
    site = load_site()
    blob = _reference_blob(site)
    alts = _uploads_meta_load()
    fmeta = _uploads_files_load()
    usage = _upload_usage(site)
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
        a = alts.get(f.name) or {}
        m = fmeta.get(f.name) or {}
        u = usage.get(f.name) or {}
        files.append({'url': '/uploads/' + f.name, 'size': st.st_size,
                      'mtime': int(st.st_mtime), 'used': f.name in blob,
                      'alt_de': a.get('de', ''), 'alt_en': a.get('en', ''),
                      'orig': m.get('orig', ''), 'tags': m.get('tags') or [],
                      'folder': m.get('folder', ''),
                      'places': u.get('places') or [], 'place_count': u.get('n', 0),
                      # Marker steckt im Dateinamen (siehe _store_upload_image) —
                      # damit lässt sich die Galerie auf KI-Bilder eingrenzen
                      'ai': f.stem.endswith(AI_IMAGE_SUFFIX)})
    files.sort(key=lambda x: x['mtime'], reverse=True)
    return jsonify({'files': files[:UPLOADS_LIST_MAX], 'total': len(files),
                    'tags': sorted({t for m in fmeta.values()
                                    for t in (m.get('tags') or [])},
                                   key=str.lower),
                    # Aus der ganzen Ablage, nicht nur aus den gezeigten
                    # Kacheln: sonst verschwände ein Ordner aus der Leiste,
                    # sobald seine Bilder jenseits der Kachelgrenze liegen.
                    'folders': sorted({m.get('folder') for m in fmeta.values()
                                       if m.get('folder')}, key=str.lower)})


@admin_app.route('/api/docs/list')
def api_docs_list():
    """Vorhandene Bibliothek-PDFs für den Datei-Browser im Tab System."""
    err = _api_auth()
    if err:
        return err
    blob = _reference_blob(load_site())
    files = []
    for f in DOCS_DIR.iterdir():
        if not f.is_file() or not _DOC_FILE_RE.match(f.name):
            continue
        try:
            st = f.stat()
        except OSError:
            continue
        files.append({'name': f.name, 'size': st.st_size,
                      'mtime': int(st.st_mtime), 'used': f.name in blob})
    files.sort(key=lambda x: x['mtime'], reverse=True)
    return jsonify({'files': files[:UPLOADS_LIST_MAX], 'total': len(files)})


@admin_app.route('/api/docs/file/<name>')
def api_docs_file(name: str):
    """Ein PDF zur Ansicht im Admin — bewusst inline, anders als öffentlich.

    Die öffentliche Bibliothek-Route liefert PDFs ausschließlich als Download
    (siehe library_entry_pdf): dort ist die Datei für jeden Besucher erreichbar,
    und ein PDF darf im Browser Skript ausführen. Hier hinter dem Login sieht sie
    nur, wer sie selbst hochgeladen hat — trotzdem `sandbox` und `nosniff`, damit
    ein präpariertes PDF nicht auf die Admin-Sitzung zugreifen kann.
    """
    err = _api_auth()
    if err:
        return err
    if not _DOC_FILE_RE.match(name or ''):
        return jsonify({'error': 'invalid'}), 400
    target = safe_under(DOCS_DIR, name)
    if target is None or not target.is_file():
        return jsonify({'error': 'not_found'}), 404
    resp = send_file(target, mimetype='application/pdf')
    resp.headers['Content-Disposition'] = 'inline; filename="dokument.pdf"'
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['Content-Security-Policy'] = 'sandbox'
    return resp


@admin_app.route('/api/docs/delete', methods=['POST'])
def api_docs_delete():
    """Ein einzelnes PDF löschen. Eingebundene bleiben tabu — dieselbe Regel wie
    bei den Bildern, sonst zeigt ein Bibliothek-Eintrag ins Leere."""
    err = _api_auth()
    if err:
        return err
    name = Path(_clean_str((request.get_json(silent=True) or {}).get('name'), 120)).name
    if not _DOC_FILE_RE.match(name):
        return jsonify({'error': 'invalid'}), 400
    p = safe_under(DOCS_DIR, name)
    if p is None or not p.is_file():
        return jsonify({'error': 'not_found'}), 404
    if name in _reference_blob(load_site()):
        return jsonify({'error': 'in_use'}), 409
    try:
        p.unlink()
    except OSError as e:
        log.warning("PDF '%s' konnte nicht gelöscht werden: %s", name, e)
        return jsonify({'error': 'delete_failed'}), 500
    log_audit('doc_delete', name)
    return jsonify({'ok': True})


def _reference_blob(site: dict) -> str:
    """Der Text, in dem nach Dateinamen gesucht wird.

    Enthält site.json, travel.json UND die Prompt-Bibliothek. Ohne den
    Reiseblog-Teil hielte das Aufräumen jedes Reisefoto für verwaist und löschte
    es beim nächsten Klick — derselbe Grund, aus dem der Löschschutz im
    Datei-Browser hier mitliest. Dieselbe Falle gilt für das Vorlagenbild eines
    gespeicherten Prompts.
    """
    return (json.dumps(site, ensure_ascii=False)
            + json.dumps(load_travel(), ensure_ascii=False)
            + json.dumps(_ai_prompts_load(), ensure_ascii=False))


# Dateinamen der Uploads sind UUIDs mit fester Endung — dieselbe Annahme, auf
# der schon der Vorkommen-Scan des Aufräumens beruht.
_UPLOAD_NAME_RE = re.compile(r'[0-9a-f]{8,32}(?:-ai)?\.[a-z0-9]{2,5}', re.I)


def _usage_entities(site: dict) -> list:
    """(Art, Bezeichnung, Adresse, Teilbaum) für jeden Ort mit Bildern.

    Grundlage der Spalte „verwendet in" in der Medienverwaltung. Bewusst
    grobkörnig: ein Beitrag ist ein Ort, nicht jedes einzelne Feld darin.
    Fehlt hier ein Bereich, sagt die Verwaltung „nirgends verwendet", obwohl das
    Bild eingebunden ist — deshalb gehört jede neue Ablage mit Bildern hier
    hinein. Der Löschschutz hängt weiterhin an `_reference_blob()` und nicht an
    dieser Liste, damit ein Vergessen hier kein Bild kostet.

    Die Bezeichnung darf leer bleiben; die Oberfläche setzt dann den übersetzten
    Namen der Art ein. Hier einen deutschen Rückfalltext einzusetzen, hieße ihn
    auch im englischen Admin zu zeigen.
    """
    def title(obj):
        return (obj.get('title_de') or obj.get('title_en') or obj.get('name')
                or obj.get('label_de') or obj.get('label_en') or '')

    out = [('home', '', '/', {'profile': site.get('profile'),
                              'design': site.get('design'),
                              'sections': site.get('sections')})]
    out += [('post', title(p), '/blog/' + p.get('id', ''), p)
            for p in site.get('posts', [])]
    out += [('page', title(p), '/seite/' + (p.get('slug') or ''), p)
            for p in site.get('pages', [])]
    out += [('project', title(p), '/p/' + p.get('id', ''), p)
            for p in site.get('projects', [])]
    out += [('album', title(a), '', a) for a in site.get('albums', [])]
    out += [('library', title(e), '/bibliothek/' + (e.get('slug') or ''), e)
            for e in _library(site).get('entries', [])]
    for trip in (load_travel().get('trips') or []):
        base = trip.get('name') or trip.get('destination') or ''
        slug = trip.get('slug') or ''
        for day in (trip.get('days') or []):
            art = (day.get('article') or {}).get('de') or {}
            day_title = art.get('title') or f"#{day.get('number') or ''}"
            url = f"/reiseblog/{slug}/{day.get('slug')}" if slug and day.get('slug') else ''
            out.append(('travel', ' — '.join(x for x in (base, day_title) if x), url, day))
    return out


USAGE_PLACES_MAX = 5      # mehr zeigt die Oberfläche ohnehin nicht


def _upload_usage(site: dict) -> dict:
    """Dateiname -> {'n': Anzahl Orte, 'places': die ersten paar davon}.

    Ein Durchgang je Ort statt einer Suche je Datei: bei dreihundert Bildern und
    zweihundert Orten wären das sonst sechzigtausend Textsuchen.
    """
    usage: dict[str, dict] = {}
    for kind, label, url, obj in _usage_entities(site):
        if not obj:
            continue
        for name in set(_UPLOAD_NAME_RE.findall(json.dumps(obj, ensure_ascii=False))):
            hit = usage.setdefault(name, {'n': 0, 'places': []})
            hit['n'] += 1
            if len(hit['places']) < USAGE_PLACES_MAX:
                hit['places'].append({'kind': kind, 'label': _clean_str(label, 80),
                                      'url': url})
    return usage


def _unused_in(directory: Path, site: dict):
    """Dateien in `directory`, die nirgends mehr referenziert sind.

    Dateinamen sind durchweg eindeutige UUIDs, daher ist ein Vorkommen-Scan über
    den JSON-Text sicher und deckt jede Fundstelle ab, ohne die Struktur zu kennen.
    """
    blob = _reference_blob(site)
    orphans, total = [], 0
    for f in directory.iterdir():
        if f.is_file() and f.name not in blob:
            orphans.append(f)
            total += f.stat().st_size
    return orphans, total


def _wm_cache_forget(name: str) -> int:
    """Zwischengespeicherte Fassungen eines Bildes wegwerfen.

    Nötig, sobald sich der Inhalt unter gleichem Namen ändert (Ersetzen) oder
    die Datei verschwindet. Ohne das liefert die Auslieferung weiter das alte
    Bild mit eingebranntem Text aus, und niemand fände heraus, warum.
    """
    stem = Path(name).stem
    if not stem:
        return 0
    gone = 0
    # Vorsilbe von Hand vergleichen statt über ein Muster: der Stamm ist zwar
    # eine UUID, aber ein Muster mit Sonderzeichen darin würde stillschweigend
    # etwas anderes treffen.
    prefix = stem + '-'
    for f in [x for x in WM_CACHE_DIR.iterdir()
              if x.is_file() and x.name.startswith(prefix) and x.suffix == '.webp']:
        try:
            f.unlink()
            gone += 1
        except OSError as e:
            log.warning("Cache-Datei %s konnte nicht gelöscht werden: %s", f.name, e)
    return gone


def _unused_wm_cache():
    """Cache-Dateien ohne zugehörigen Upload — (Liste, Bytes).

    Der Name ist `<stamm des bildes>-<schlüssel>.webp`; gibt es zum Stamm kein
    Bild mehr, ist die Datei nicht wiederherstellbar zuzuordnen und wird nie
    wieder ausgeliefert. Dieselbe Regel sammelt die Dateien aus der Zeit vor
    dieser Namensgebung ein: deren Stamm gehört zu keinem Upload.

    Der Cache ist reine Ableitung — er steht in keiner Backup-Liste und rechnet
    sich beim nächsten Abruf neu. Zu viel zu löschen kostet daher nichts außer
    einmal Rechenzeit; zu wenig zu löschen lässt das Verzeichnis wachsen.
    """
    stems = {f.stem for f in UPLOADS_DIR.iterdir() if f.is_file()}
    orphans, total = [], 0
    for f in WM_CACHE_DIR.glob('*.webp'):
        if f.name.rsplit('-', 1)[0] in stems:
            continue
        orphans.append(f)
        try:
            total += f.stat().st_size
        except OSError:
            pass
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
    removed, gone = 0, []
    for f in orphans:
        try:
            f.unlink()
            removed += 1
            gone.append(f.name)
        except OSError as e:
            log.warning("Aufräumen: %s konnte nicht gelöscht werden: %s", f.name, e)
    _uploads_meta_forget(gone)
    if removed:
        log_audit(audit_tag, f'{removed} Datei(en)')
    return jsonify({'ok': True, 'removed': removed, 'freed_mb': round(total / 1048576, 1)})


def _public_urls(site: dict) -> list:
    """Alle öffentlich erreichbaren Pfade mit lesbarer Bezeichnung.

    Grundlage der Zielauswahl bei den Weiterleitungen: Ein Pfad wie
    `/blog/3061752ccc9f` ist von Hand nicht zu tippen und aus dem Kopf schon gar
    nicht. Dieselben Quellen wie die Sitemap, nur mit Titel statt Datum.
    """
    loc = _loc_factory(site_default_lang(site) if site_default_lang(site) != 'auto' else 'de')
    out = [{'url': '/', 'kind': 'home',
            'label': site['design'].get('site_title') or site['profile'].get('name') or '/'}]
    out += [{'url': '/seite/' + p['slug'], 'kind': 'page', 'label': loc(p, 'title')}
            for p in site.get('pages', []) if p.get('visible') and p.get('slug')]
    posts = sorted_posts(site, public_only=True)
    if posts:
        out.append({'url': '/blog', 'kind': 'blog', 'label': 'Blog'})
        out += [{'url': '/blog/' + p['id'], 'kind': 'post', 'label': loc(p, 'title')}
                for p in posts]
    lib = _lib_public_entries(site)
    if lib:
        out.append({'url': '/bibliothek', 'kind': 'library', 'label': _library_label(site, loc, {})})
        out += [{'url': '/bibliothek/' + e['slug'], 'kind': 'library', 'label': loc(e, 'title')}
                for e in lib if e.get('slug')]
    for tr in _trav_public_trips(site):
        out.append({'url': '/reiseblog/' + tr['slug'], 'kind': 'travel',
                    'label': tr.get('name') or tr.get('destination') or tr['slug']})
        for d in _trav_public_days(tr):
            art = (d.get('article') or {}).get('de') or {}
            out.append({'url': f"/reiseblog/{tr['slug']}/{d['slug']}", 'kind': 'travel',
                        'label': art.get('title') or d.get('slug', '')})
    out += [{'url': '/p/' + p['id'], 'kind': 'project', 'label': p.get('title') or p['id']}
            for p in projects_public(site) if _has_detail(p)]
    out += [{'url': '/formular/' + f['slug'], 'kind': 'form', 'label': loc(f, 'title')}
            for f in _public_forms(site) if f.get('slug')]
    return out


# Die Prüfungen der Zustandsanzeige. Absichtlich eine überschaubare Liste: Sie
# soll das melden, was den Betrieb kostet, und nicht jede Einstellung
# kommentieren. Wer eine hinzufügt, gibt ihr eine eigene `id` — die Oberfläche
# holt Beschriftung und Rat über `health_<id>_label` / `health_<id>_hint` aus
# den Übersetzungen, damit hier kein deutscher Text im Code landet.

def _health_dir_free_mb(path: str) -> float | None:
    try:
        return shutil.disk_usage(path).free / 1048576
    except OSError:
        return None


def _health_newest_backup() -> tuple[str, int] | None:
    """(Name, Alter in Tagen) des jüngsten automatischen Backups."""
    try:
        files = [f for f in BACKUPS_DIR.iterdir()
                 if f.is_file() and f.suffix == '.zip']
    except OSError:
        return None
    if not files:
        return None
    newest = max(files, key=lambda f: f.stat().st_mtime)
    age = int((time.time() - newest.stat().st_mtime) // 86400)
    return newest.name, age


def health_checks() -> list:
    """Zustand als Liste von Prüfungen: `level` ist ok, warn, err oder off."""
    site = load_site()
    cfg = load_config()
    notes = health_notes()
    out = []

    def add(cid, level, detail='', note_key=None):
        n = notes.get(note_key or cid)
        # Eine festgehaltene Störung schlägt „nicht eingerichtet": Wenn der
        # Mailversand gescheitert ist, war er offensichtlich eingerichtet — und
        # die Einstellung kann seither entfernt worden sein, ohne dass das den
        # Fehlschlag ungeschehen macht. Ihn hier zu verschlucken hieße, die
        # Anzeige genau dann schweigen zu lassen, wenn sie etwas zu sagen hat.
        if n and level == 'off':
            level = 'err'
        row = {'id': cid, 'level': level, 'detail': detail}
        if n:
            row['since'] = n.get('since') or n.get('ts')
            row['count'] = n.get('n', 1)
            row['msg'] = n.get('msg', '')
        out.append(row)

    # Öffentliche Adresse — ohne sie zeigen Sitemap, Feed und kanonische
    # Adressen auf die interne Adresse und sind damit wertlos.
    add('public_url', 'ok' if (site['design'].get('public_url') or '').strip() else 'warn')

    # Besucher-IP: kommt die echte Adresse durch den Proxy?
    add('client_ip', 'err' if 'client_ip' in notes else 'ok')

    # Automatisches Backup
    keep = int(cfg.get('auto_backup_keep', AUTO_BACKUP_KEEP_DEFAULT) or 0)
    newest = _health_newest_backup()
    if not keep:
        add('backup', 'off')
    elif 'backup' in notes:
        add('backup', 'err')
    elif newest is None:
        add('backup', 'warn')
    else:
        name, age = newest
        add('backup', 'ok' if age <= 1 else 'warn', f'{name} ({age} d)')

    # Speicherplatz im Datenordner
    free = _health_dir_free_mb(_DATA)
    if free is None:
        add('disk', 'warn')
    else:
        add('disk', 'err' if free < 200 else 'warn' if free < 1000 else 'ok',
            f'{free / 1024:.1f} GB')

    # Gesamt-Speicherlimit des Betreibers (0 = keins gesetzt)
    limit = storage_limit_bytes()
    if not limit:
        add('storage', 'off')
    else:
        used = storage_used_bytes()
        pct = used * 100 // limit
        add('storage', 'err' if pct >= 100 else 'warn' if pct >= 80 else 'ok',
            f'{used / 1048576:.0f} / {limit // 1048576} MB ({pct} %)')

    # Mailversand
    if not (cfg.get('smtp_host') or '').strip():
        add('smtp', 'off')
    else:
        add('smtp', 'err' if 'smtp' in notes else 'ok')

    # GitHub-Token (nur wenn überhaupt Projekte verknüpft sind)
    linked = any(p.get('repo_full_name') for p in site.get('projects', []))
    if not linked:
        add('github', 'off')
    else:
        add('github', 'err' if 'github' in notes else 'ok')

    # KI-Schlüssel
    add('ai', 'ok' if (cfg.get('gemini_api_key') or '').strip() else 'off')

    # Bildverarbeitung und PDF-Erzeugung
    add('pillow', 'ok' if _HAS_PIL else 'err')
    lib_pdf = any((e.get('pdf_mode') or '') == 'generated'
                  for e in _library(site).get('entries', []))
    add('weasy', 'off' if not lib_pdf else ('ok' if _HAS_WEASY else 'err'))

    # Länderdaten der Statistik
    try:
        age = int((time.time() - GEOIP_CACHE.stat().st_mtime) // 86400)
        add('geoip', 'warn' if age > 60 else 'ok', f'{age} d')
    except OSError:
        add('geoip', 'off')

    # Indexierung — kein Fehler, aber der häufigste Grund für „Google findet
    # mich nicht", und ohne Anzeige fällt es niemandem auf.
    add('indexing', 'ok' if site['design'].get('allow_indexing') else 'off')
    return out


def health_counts() -> dict:
    """Zahlen für die zugeklappten Bereiche im Reiter System.

    Dort lädt seit 0.11.26 jeder Bereich seinen Inhalt erst beim Aufklappen.
    Ohne diese Zahlen wäre der Reiter zwar aufgeräumt, aber blind: dass vierzig
    Fassungen liegen oder drei Alternativtexte fehlen, sähe man erst nach dem
    Öffnen. Ein Aufruf füllt alle Kopfzeilen; jede Zählung ist ein Verzeichnis-
    oder ein JSON-Lesevorgang — keine baut einen Index auf.
    """
    def count_dir(path: Path, ok) -> int:
        try:
            return sum(1 for f in path.iterdir() if f.is_file() and ok(f))
        except OSError:
            return 0

    alts = _uploads_meta_load()
    images = alts_missing = 0
    try:
        for f in UPLOADS_DIR.iterdir():
            if not f.is_file() or f.suffix.lower() not in ALLOWED_UPLOAD_EXT:
                continue
            images += 1
            a = alts.get(f.name) or {}
            if not (a.get('de') or a.get('en')):
                alts_missing += 1
    except OSError:
        pass

    rows = admin_log_buffer.snapshot()
    nf = [(k, e) for k, e in (load_stats().get('notfound') or {}).items()
          if isinstance(e, dict)]
    return {
        'log_errors': sum(r.get('n', 1) for r in rows
                          if r.get('level') in ('ERROR', 'CRITICAL')),
        'log_warnings': sum(r.get('n', 1) for r in rows
                            if r.get('level') == 'WARNING'),
        'audit': len(load_audit()),
        'revisions': len(list_revisions()),
        'backups': count_dir(BACKUPS_DIR, lambda f: f.suffix == '.zip'),
        'images': images,
        'alts_missing': alts_missing,
        'docs': count_dir(DOCS_DIR, lambda f: bool(_DOC_FILE_RE.match(f.name))),
        # Zwei Zahlen, weil die Liste Bots ausblenden kann: ohne die zweite
        # stünde in der Kopfzeile eine 0, während unten dreißig Zeilen warten.
        'notfound': sum(1 for k, e in nf if not e.get('bot') and not _is_probe(k)),
        'notfound_all': len(nf),
    }


@admin_app.route('/api/log')
def api_log():
    """Die letzten Warnungen und Fehler des laufenden Add-ons.

    Bewusst erst ab Stufe „Warnung": Auf INFO meldet jeder Start ein Dutzend
    Zeilen Routine, die den Puffer füllen und nichts erklären. Wer das ganze
    Protokoll braucht, findet es in Home Assistant unter Add-on → Protokoll.
    """
    err = _api_auth()
    if err:
        return err
    admin_log_buffer.flush_now()
    rows = list(reversed(admin_log_buffer.snapshot()))
    return jsonify({'rows': rows,
                    'errors': sum(r.get('n', 1) for r in rows
                                  if r.get('level') in ('ERROR', 'CRITICAL')),
                    'warnings': sum(r.get('n', 1) for r in rows
                                    if r.get('level') == 'WARNING')})


@admin_app.route('/api/log/clear', methods=['POST'])
def api_log_clear():
    err = _api_auth()
    if err:
        return err
    admin_log_buffer.clear()
    log_audit('log_clear')
    return jsonify({'ok': True})


@admin_app.route('/api/health')
def api_health():
    err = _api_auth()
    if err:
        return err
    rows = health_checks()
    rank = {'err': 0, 'warn': 1, 'ok': 2, 'off': 3}
    rows.sort(key=lambda r: rank.get(r['level'], 9))
    return jsonify({'checks': rows,
                    'bad': sum(1 for r in rows if r['level'] in ('err', 'warn')),
                    'counts': health_counts()})


@admin_app.route('/api/site/urls')
def api_site_urls():
    """Zielauswahl für Weiterleitungen."""
    err = _api_auth()
    if err:
        return err
    return jsonify({'urls': _public_urls(load_site())})


@admin_app.route('/api/stats/notfound')
def api_stats_notfound():
    """Ins Leere laufende Aufrufe, häufigste zuerst.

    Bots werden gekennzeichnet, aber nicht verschluckt: Wer sie stillschweigend
    filtert, verliert genau die Zeile, die er sucht, wenn die Erkennung daneben
    liegt. Ausblenden entscheidet die Oberfläche.
    """
    err = _api_auth()
    if err:
        return err
    nf = load_stats().get('notfound') or {}
    # `probe` wird beim Ausliefern aus dem Pfad bestimmt, nicht aus dem
    # gespeicherten Eintrag: So sind auch die Zeilen eingestuft, die vor dieser
    # Fassung aufgelaufen sind, und eine erweiterte Musterliste wirkt rückwirkend.
    rows = [{'path': p, 'n': e.get('n', 0), 'last': e.get('last', 0),
             'first': e.get('first', 0), 'ref': e.get('ref', ''),
             'probe': _is_probe(p),
             'internal': bool(e.get('internal')) and not _is_probe(p),
             'bot': bool(e.get('bot')),
             'ips': list(e.get('ips') or []), 'cc': e.get('cc', '')}
            for p, e in nf.items() if isinstance(e, dict)]
    # Eigene kaputte Verweise zuerst, Sonden zuletzt, dazwischen nach
    # Häufigkeit: die Liste soll oben das zeigen, was sich reparieren lässt.
    rows.sort(key=lambda r: (r['probe'], not r['internal'], -r['n'], -r['last']))
    return jsonify({'rows': rows, 'total': sum(r['n'] for r in rows)})


@admin_app.route('/api/stats/notfound/clear', methods=['POST'])
def api_stats_notfound_clear():
    """Eine Zeile oder die ganze Liste vergessen.

    Nötig, weil eine erledigte Fundstelle sonst für immer oben steht — die
    Zählung läuft ja weiter, auch wenn die Weiterleitung längst greift.
    """
    err = _api_auth()
    if err:
        return err
    path = _clean_str((request.get_json(silent=True) or {}).get('path'), 120)
    stats = load_stats()
    nf = stats.get('notfound') or {}
    if path:
        removed = 1 if nf.pop(path, None) is not None else 0
    else:
        removed = len(nf)
        nf = {}
    stats['notfound'] = nf
    save_stats(stats)
    log_audit('notfound_clear', path or f'alle ({removed})')
    return jsonify({'ok': True, 'removed': removed})


@admin_app.route('/api/uploads/unused')
def api_uploads_unused():
    err = _api_auth()
    if err:
        return err
    orphans, total = _unused_uploads(load_site())
    cache_files, cache_bytes = _unused_wm_cache()
    return jsonify({'count': len(orphans), 'cache_count': len(cache_files),
                    'size_mb': round((total + cache_bytes) / 1048576, 1)})


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
    if name in _reference_blob(load_site()):
        return jsonify({'error': 'in_use'}), 409
    try:
        p.unlink()
    except OSError as e:
        log.warning("Bild '%s' konnte nicht gelöscht werden: %s", name, e)
        return jsonify({'error': 'delete_failed'}), 500
    _uploads_meta_forget([name])
    _wm_cache_forget(name)
    log_audit('upload_delete', name)
    return jsonify({'ok': True})


@admin_app.route('/api/uploads/meta', methods=['POST'])
def api_uploads_meta():
    """Herkunftsname und Etiketten einer Datei setzen.

    Beides dient allein dem Wiederfinden — abgelegt bleibt die Datei unter
    ihrer UUID. Ein Umbenennen im Dateisystem käme nicht in Frage: der Name
    steht in jeder Einbindung und in bereits veröffentlichten Seiten.
    """
    err = _api_auth()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    name = Path(_clean_str(body.get('name'), 120)).name
    if Path(name).suffix.lower() not in ALLOWED_UPLOAD_EXT:
        return jsonify({'error': 'invalid'}), 400
    p = safe_under(UPLOADS_DIR, name)
    if p is None or not p.is_file():
        return jsonify({'error': 'not_found'}), 404
    orig = body.get('orig')
    tags = body.get('tags')
    folder = body.get('folder')
    if not _uploads_file_meta_set(name,
                                  orig=None if orig is None else _clean_str(orig, 120),
                                  tags=None if tags is None else tags,
                                  folder=None if folder is None else folder):
        return jsonify({'error': 'save_failed'}), 500
    m = _uploads_files_load().get(name) or {}
    return jsonify({'ok': True, 'orig': m.get('orig', ''), 'tags': m.get('tags') or [],
                    'folder': m.get('folder', '')})


@admin_app.route('/api/uploads/folder', methods=['POST'])
def api_uploads_folder():
    """Mehrere Dateien in einen Ordner legen (oder aus allen herausnehmen).

    Sammelweise, weil es einzeln niemand täte: einen gewachsenen Bestand über
    je einen Dialog zu sortieren, dauert länger als das Suchen, das der Ordner
    ersparen soll. Ein leerer Zielname bedeutet „unsortiert".

    Der Ordner ist eine Angabe in `uploads_meta.json` und sonst nichts. Im
    Dateisystem wandert keine Datei, weil ihr Name in jeder Einbindung und in
    bereits veröffentlichten Adressen steht.
    """
    err = _api_auth()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    folder = _upload_folder_clean(body.get('folder'))
    names = body.get('names')
    if not isinstance(names, list) or not names:
        return jsonify({'error': 'invalid'}), 400
    moved, missing = 0, 0
    for raw in names[:UPLOADS_LIST_MAX]:
        name = Path(_clean_str(raw, 120)).name
        if Path(name).suffix.lower() not in ALLOWED_UPLOAD_EXT:
            missing += 1
            continue
        p = safe_under(UPLOADS_DIR, name)
        if p is None or not p.is_file():
            missing += 1
            continue
        if _uploads_file_meta_set(name, folder=folder):
            moved += 1
    log_audit('upload_folder', f'{moved} Datei(en) → {folder or "—"}')
    return jsonify({'ok': True, 'moved': moved, 'missing': missing,
                    'folder': folder})


@admin_app.route('/api/uploads/replace', methods=['POST'])
def api_uploads_replace():
    """Inhalt einer vorhandenen Datei austauschen, Name bleibt.

    Der Sinn der ganzen Sache: jede Einbindung — in Beiträgen, Seiten, Alben,
    im Reiseblog, in bereits veröffentlichten Adressen — zeigt danach ohne
    Zutun auf das neue Bild. Ein Löschen samt Neu-Hochladen kann das nicht.

    Zwei Grenzen sind bewusst eng gezogen:

    * Nur `.webp` lässt sich ersetzen. `_store_upload_image()` schreibt immer
      WebP; in eine `.png` geschrieben, lieferte die Datei danach WebP-Daten
      unter falscher Endung aus.
    * Die `-ai`-Kennzeichnung steckt im Dateinamen und bleibt deshalb erhalten.
      Ein KI-Bild bleibt gekennzeichnet, auch wenn ein Foto hineinwandert —
      die vorsichtige Richtung. Umgekehrt lässt sich ein gewöhnliches Bild
      nicht durch ein KI-Bild ersetzen, ohne die Kennzeichnung zu verlieren;
      dafür ist der normale Weg über das KI-Studio zu gehen.
    """
    err = _api_auth()
    if err:
        return err
    name = Path(_clean_str(request.form.get('name'), 120)).name
    target = safe_under(UPLOADS_DIR, name)
    if target is None or not target.is_file():
        return jsonify({'error': 'not_found'}), 404
    if Path(name).suffix.lower() != '.webp':
        return jsonify({'error': 'not_webp'}), 400
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'error': 'no file'}), 400
    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXT or ext == '.gif':
        return jsonify({'error': 'file type not allowed'}), 400
    if not _HAS_PIL:
        return jsonify({'error': 'no_pillow'}), 400
    try:
        written = _store_upload_image(f.stream, name=name)
    except Exception as e:
        log.warning("Ersetzen von %s fehlgeschlagen: %s", name, e)
        return jsonify({'error': 'convert_failed'}), 400
    if not written:
        return jsonify({'error': 'convert_failed'}), 400
    # Ohne das liefert die Auslieferung weiter die Fassung mit eingebranntem
    # Text zum alten Bild aus.
    _wm_cache_forget(name)
    _uploads_file_meta_set(name, orig=Path(f.filename).name)
    log_audit('upload_replace', name)
    try:
        mtime = int(target.stat().st_mtime)
    except OSError:
        mtime = int(time.time())
    return jsonify({'ok': True, 'url': '/uploads/' + name, 'mtime': mtime})


@admin_app.route('/api/uploads/alts', methods=['POST'])
def api_uploads_alts():
    """Alternativtexte in einem Rutsch speichern.

    Der Editor schickt nur die geänderten Zeilen; ein leerer Text löscht den
    Eintrag, damit die Ablage nicht mit leeren Feldern zuwächst.
    """
    err = _api_auth()
    if err:
        return err
    raw = (request.get_json(silent=True) or {}).get('alts')
    if not isinstance(raw, dict):
        return jsonify({'error': 'invalid'}), 400
    alts = _uploads_meta_load()
    for key, val in list(raw.items())[:UPLOADS_LIST_MAX]:
        name = Path(_clean_str(key, 120)).name
        if not name or Path(name).suffix.lower() not in ALLOWED_UPLOAD_EXT:
            continue
        val = val if isinstance(val, dict) else {}
        entry = {lg: _clean_str(val.get(lg), UPLOAD_ALT_MAX) for lg in ('de', 'en')}
        if entry['de'] or entry['en']:
            alts[name] = entry
        else:
            alts.pop(name, None)
    if not _uploads_meta_save(alts):
        return jsonify({'error': 'save_failed'}), 500
    return jsonify({'ok': True, 'count': len(alts)})


@admin_app.route('/api/ai/alt', methods=['POST'])
def api_ai_alt():
    """Alternativtext aus dem Bild selbst — dieselbe Anfrage liefert DE und EN."""
    err = _api_auth()
    if err:
        return err
    if not gemini_text_enabled():
        return jsonify({'error': 'no_api_key'}), 400
    name = Path(_clean_str((request.get_json(silent=True) or {}).get('name'), 120)).name
    ref = _ai_ref_image('/uploads/' + name) if name else None
    if ref is None:
        return jsonify({'error': 'bad_ref'}), 400
    model = _ai_model_or((request.get_json(silent=True) or {}).get('model'), _gemini_text_model())
    if not _ai_rate_take(_ai_text_times, AI_TEXT_MAX_PER_HOUR):
        return jsonify({'error': 'rate_limited'}), 429
    data, code, detail = _gemini_image_alt(ref, model=model)
    if code:
        return jsonify({'error': _AI_ERRORS.get(code, 'ai_failed'),
                        'detail': detail, 'model': model}), 502
    log.info("Alternativtext erzeugt (%s)", model)
    return jsonify({'ok': True, 'alt': data})


@admin_app.route('/api/uploads/cleanup', methods=['POST'])
def api_uploads_cleanup():
    """Verwaiste Bilder löschen — und dabei den Bild-Zwischenspeicher mit.

    Der Cache wird sonst nie kleiner: er entsteht beim Ausliefern und überlebt
    das Bild, zu dem er gehört. Er ist reine Ableitung und in keinem Backup,
    also ist ein zu großzügiges Aufräumen folgenlos.
    """
    # Die Prüfung fehlte bis 0.11.28 als einzige unter 314 Routen — ein POST
    # ohne Anmeldung löschte damit Dateien.
    err = _api_auth()
    if err:
        return err
    orphans, total = _unused_uploads(load_site())
    resp = _cleanup_dir(orphans, total, 'uploads_cleanup')
    cache_files, cache_bytes = _unused_wm_cache()
    gone = 0
    for f in cache_files:
        try:
            f.unlink()
            gone += 1
        except OSError as e:
            log.warning("Cache-Datei %s konnte nicht gelöscht werden: %s", f.name, e)
    if gone:
        log_audit('wm_cache_cleanup', f'{gone} Datei(en)')
        data = resp.get_json()
        data['cache_removed'] = gone
        data['freed_mb'] = round((total + cache_bytes) / 1048576, 1)
        return jsonify(data)
    return resp


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


@admin_app.route('/api/github/token')
def api_github_token():
    err = _api_auth()
    if err:
        return err
    force = request.args.get('force') == '1'
    return jsonify(check_github_token(force=force))


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
            'repo_pushed':    repo.get('pushed', ''),
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
        'traffic':   traffic_totals(stats),
    })


# ── Besucher-Explorer ─────────────────────────────────────────────────────────
#
# Wertet das dauerhafte CSV-Archiv aus (`visits/visits-JJJJ-MM.csv`). Die Logik
# steckt in visitexplorer.py, hier steht nur das Drumherum: Rechte prüfen,
# Monat auf Gültigkeit prüfen, Ergebnis deckeln.
#
# Nie Rohzeilen ausliefern — ein Monat kann sechsstellig viele haben. Raus
# gehen Auswertungen, höchstens VISIT_SESSIONS_MAX Sitzungs-Kurzfassungen und
# die Schrittliste genau der Sitzung, die der Admin öffnet.

VISIT_SESSIONS_MAX = 300
_VISIT_MONTH_RE = re.compile(r'^\d{4}-(?:0[1-9]|1[0-2])$')


def _visit_month_path(month: str):
    """Pfad zur Monatsdatei — None, wenn der Monat nicht stimmt oder sie fehlt.

    Der Dateiname wird hier selbst gebaut; aus der Anfrage kommt nur das
    Monatskürzel, und das muss vorher durch den regulären Ausdruck.
    """
    if not _VISIT_MONTH_RE.match(month or ''):
        return None
    p = safe_under(VISITS_DIR, f'visits-{month}.csv')
    return p if p is not None and p.is_file() else None


def _visit_months() -> list:
    """Vorhandene Monate, neueste zuerst."""
    try:
        names = [f.name for f in VISITS_DIR.iterdir()
                 if f.is_file() and _VISIT_FILE_RE.match(f.name)]
    except OSError:
        return []
    return sorted((n[7:14] for n in names), reverse=True)


def _visit_rows(month: str, with_bots: bool):
    """Geparste Zeilen eines Monats, wahlweise ohne Bots. `(rows, meta)`."""
    path = _visit_month_path(month)
    if path is None:
        return None, None
    try:
        rows, meta = vx.cache_get(path, month)
    except OSError:
        return None, None
    if not with_bots:
        # Die Netzprüfung läuft zusätzlich zur `bot`-Spalte, damit auch schon
        # archivierte Zeilen sauber werden: die Spalte wurde beim Schreiben
        # gesetzt, die Netzliste kam später dazu.
        rows = [r for r in rows
                if not r[vx.BOT] and not vx.is_datacenter_ip(r[vx.IP])]
    return rows, meta


def _visit_sessions(rows, with_bots: bool) -> tuple:
    """Sitzungen bauen, ohne Bot-Schalter die Scanner aussortieren.

    Zwei Filter greifen nacheinander: die `bot`-Spalte samt Netzprüfung schon
    beim Lesen der Zeilen (`_visit_rows`), und hier die Verhaltensprüfung —
    ein Aufruf, kein Referrer, keine Sprache. Die zweite fängt genau das, wofür
    keine Netzliste reicht: Scanner aus Mobilfunk- und Endkundennetzen.
    """
    sessions = vx.build_sessions(rows)
    if with_bots:
        return sessions, 0
    return vx.drop_scanners(sessions)


def _visit_args():
    """Monat und Bot-Schalter aus der Anfrage."""
    month = _clean_str(request.args.get('month'), 7)
    return month, request.args.get('bots') == '1'


@admin_app.route('/api/visits/months')
def api_visits_months():
    err = _api_auth()
    if err:
        return err
    by_option = bool(load_config().get('visit_file_log'))
    by_site = bool(load_site()['design'].get('visit_archive'))
    months = _visit_months()
    return jsonify({
        'enabled': by_option or by_site,
        # Woher der Schalter kommt — nur bei 'site' darf der Admin ihn umlegen,
        # die Add-on-Option gehört Home Assistant.
        'source':  'option' if by_option else ('site' if by_site else 'off'),
        'months':  months,
        'current': months[0] if months else '',
    })


@admin_app.route('/api/visits/overview')
def api_visits_overview():
    err = _api_auth()
    if err:
        return err
    month, with_bots = _visit_args()
    rows, meta = _visit_rows(month, with_bots)
    if rows is None:
        return jsonify({'error': 'not_found'}), 404
    sessions, scanners = _visit_sessions(rows, with_bots)
    site = load_site()
    paths = vx.all_paths(sessions)
    return jsonify({
        'month':     month,
        'rows':      meta['rows'],
        'skipped':   meta['skipped'],
        'truncated': meta['truncated'],
        'scanners':  scanners,
        'cards':     vx.summary(sessions),
        **vx.path_analytics(sessions),
        'heatmap':   vx.heatmap(rows),
        'daily':     vx.daily(sessions),
        'returning': vx.returning(sessions),
        'labels':    _visit_path_labels(site, paths),
    })


@admin_app.route('/api/visits/sessions')
def api_visits_sessions():
    err = _api_auth()
    if err:
        return err
    month, with_bots = _visit_args()
    rows, meta = _visit_rows(month, with_bots)
    if rows is None:
        return jsonify({'error': 'not_found'}), 404
    sessions, scanners = _visit_sessions(rows, with_bots)
    day = _clean_str(request.args.get('day'), 10)
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', day or ''):
        sessions = [s for s in sessions
                    if datetime.fromtimestamp(s['start']).strftime('%Y-%m-%d') == day]
    total = len(sessions)
    shown = sessions[:VISIT_SESSIONS_MAX]
    return jsonify({
        'sessions':  vx.strip_steps(shown),
        'total':     total,
        'scanners':  scanners,
        'truncated': total > len(shown),
        'labels':    _visit_path_labels(load_site(), vx.all_paths(shown)),
    })


@admin_app.route('/api/visits/session/<sid>')
def api_visits_session(sid: str):
    err = _api_auth()
    if err:
        return err
    month, with_bots = _visit_args()
    rows, _meta = _visit_rows(month, with_bots)
    if rows is None:
        return jsonify({'error': 'not_found'}), 404
    hit = next((s for s in vx.build_sessions(rows) if s['id'] == sid), None)
    if hit is None:
        return jsonify({'error': 'not_found'}), 404
    hit = dict(hit)
    hit['steps'] = hit['steps'][:500]
    hit['labels'] = _visit_path_labels(load_site(), {s['path'] for s in hit['steps']})
    return jsonify(hit)


@admin_app.route('/uploads/<path:filename>')
def admin_uploads(filename: str):
    err = _api_auth()
    if err:
        return err
    return send_from_directory(UPLOADS_DIR, filename, max_age=86400)


# ── Öffentliche Routen ────────────────────────────────────────────────────────

# ── Sprache und kanonische Adressen ───────────────────────────────────────────
#
# Eine Adresse, zwei Sprachen — das ging bisher ohne jede Auskunft darüber nach
# außen. Für Suchmaschinen war die Seite dadurch nicht einzuordnen, und jeder
# Zwischenspeicher durfte eine der beiden Fassungen für alle festhalten.

def _seo_urls(lang: str) -> dict:
    """Kanonische Adresse und Sprachvarianten der gerade gerenderten Seite.

    Filter- und Suchparameter (`?tag=`, `?q=`, `?nl=`) fallen bewusst weg: sie
    zeigen Ausschnitte desselben Bestandes, und jeden als eigene Seite zu melden
    verteilt genau die Signale, die die Hauptseite braucht.

    Steht die Standardsprache auf „automatisch", trägt die nackte Adresse keine
    feste Sprache. Dann ist sie für beide Fassungen die kanonische, und nur die
    `hreflang`-Angaben benennen die eindeutigen Adressen.
    """
    # Ausnahme von der Regel oben: in der Blog-Übersicht bleibt `?seite=` stehen.
    # Seite 2 zeigt andere Beiträge als Seite 1 — wer sie auf Seite 1
    # kanonisiert, nimmt Google alles ab dem elften Beitrag aus dem Index.
    # Nur dort und nur ohne Filter: an jeder anderen Adresse ist der Parameter
    # wirkungslos und würde nur eine zweite kanonische Fassung derselben Seite
    # erfinden. Und Seite 2 einer Schlagwort-Auswahl zeigt etwas anderes als
    # Seite 2 des vollen Bestandes — gefilterte Ansichten bleiben deshalb bei
    # der Regel oben und kanonisieren auf `/blog`.
    paged = (request.endpoint == 'blog_index'
             and not (request.args.get('q') or request.args.get('tag')))
    page = _page_arg() if paged else 1
    base = _base_url() + request.path + (f'?seite={page}' if page > 1 else '')
    sep = '&' if page > 1 else '?'
    default = site_default_lang()
    alts = [(lg, base if lg == default else f'{base}{sep}lang={lg}') for lg in SITE_LANGS]
    canonical = base if (default == 'auto' or lang == default) else f'{base}{sep}lang={lang}'
    return {'canonical_url': canonical, 'hreflang_urls': alts + [('x-default', base)]}


# Eine Stelle fuer alle Uploads: geprueft wird die angekuendigte Laenge, bevor
# Flask den Rumpf ueberhaupt einliest. Das trifft jeden Weg, auf dem Dateien
# hereinkommen (Bilder, PDFs, Logos, Avatare, Anhaenge, Mitglieder-Dateien,
# Restore) — auch kuenftige, ohne dass man daran denken muss. Anfragen ohne
# Datei laufen woanders und bleiben unberuehrt, damit sich bei vollem Speicher
# weiterhin aufraeumen, loeschen und bedienen laesst.
def _storage_guard():
    if request.method not in ('POST', 'PUT', 'PATCH'):
        return None
    if not (request.content_type or '').startswith('multipart/form-data'):
        return None
    if not storage_would_exceed(request.content_length or 0):
        return None
    # Zweite Meinung mit frisch gezaehltem Stand: Geloeschtes wird im Puffer
    # nicht mitgefuehrt, sonst wuerde nach dem Aufraeumen bis zu fuenf Minuten
    # lang weiter abgewiesen.
    storage_used_bytes(refresh=True)
    if not storage_would_exceed(request.content_length or 0):
        return None
    limit_mb = storage_limit_bytes() // 1048576
    log.warning("Upload abgewiesen: Speicherlimit von %d MB erreicht (%s)",
                limit_mb, request.path)
    # Der Mitgliederbereich arbeitet mit Formularen und Weiterleitungen, der
    # Admin mit JSON — eine JSON-Antwort im Browser waere dort eine leere Seite.
    if request.path.startswith('/bereich'):
        return redirect('/bereich?msg=storage')
    return jsonify({'error': 'storage_full', 'limit_mb': limit_mb,
                    'used_mb': storage_used_bytes() // 1048576}), 413


def _storage_after(resp):
    """Angenommene Uploads gleich einrechnen, statt auf den naechsten Durchlauf
    zu warten. Gezaehlt wird die angekuendigte Laenge — etwas mehr als die Datei
    am Ende belegt, und in dieser Richtung ist die Schaetzung die richtige."""
    try:
        if (request.method in ('POST', 'PUT', 'PATCH')
                and (request.content_type or '').startswith('multipart/form-data')
                and resp.status_code < 400):
            storage_note_delta(request.content_length or 0)
    except Exception:      # noqa: BLE001 — Buchhaltung darf keine Antwort kippen
        pass
    return resp


public_app.before_request(_storage_guard)
admin_app.before_request(_storage_guard)
public_app.after_request(_storage_after)
admin_app.after_request(_storage_after)


# ------------------------------------------------------------------ Sicherheits-Kopfzeilen
#
# Der Browser folgt allem, was im ausgelieferten HTML steht: ein eingeschleustes
# `<script src="https://fremd/…">` ladet er ohne Rueckfrage. Die Kopfzeilen hier
# sagen ihm vorher, was ueberhaupt erlaubt ist — zweite Verteidigungslinie hinter
# sauberem Inhalt. Die erste bleibt noetig: `render_md` reicht rohes HTML durch,
# und `fetch_github_readme` holt fremdes Markdown auf die Projektseite.
#
# `'unsafe-inline'` steht bewusst drin. Die Vorlagen arbeiten mit rund 660
# `onclick`-Attributen und mehreren hundert `style="…"`; ein Nonce deckt nur
# <script>-Bloecke ab, keine Attribute. Ohne Umbau waere eine strengere Regel
# einfach eine kaputte Oberflaeche. Was trotzdem greift: fremde Skript-Quellen,
# <object>, ein umgebogenes <base>, Formulare nach draussen, fremdes Einbetten.
_CSP_COMMON = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    # Bilder und Medien duerfen von aussen kommen: Beitraege binden fremde
    # Adressen ein, und `http:` steht dabei, weil MyPage im LAN selbst ohne TLS
    # laeuft — ein Bild vom NAS soll nicht am Kopfzeilen-Schutz scheitern.
    "img-src 'self' data: http: https:; "
    "media-src 'self' https:; "
    "object-src 'none'; form-action 'self'"
)

# Oeffentlich: die beiden Video-Hosts aus `parse_video` duerfen eingebettet
# werden, umgekehrt darf die Seite nirgends eingebettet werden (Klickjacking).
CSP_PUBLIC = (_CSP_COMMON + "; font-src 'self'; connect-src 'self'; "
              "manifest-src 'self'; base-uri 'none'; "
              "frame-src https://www.youtube-nocookie.com https://player.vimeo.com; "
              "frame-ancestors 'none'")

# Nur Schema, Name und Port — alles andere kaeme aus einem Eingabefeld direkt in
# eine Kopfzeile. Ein Zeilenumbruch darin waere eine zweite, frei erfundene
# Kopfzeile.
_ORIGIN_RE = re.compile(r'^https?://[A-Za-z0-9.\-]{1,253}(:\d{1,5})?$')
_preview_origin_cache: tuple = (None, ())


def _preview_origins() -> tuple:
    """Herkunft der oeffentlichen Seite, wie sie die Design-Vorschau einsetzt.

    Die Vorschau rendert die oeffentliche Startseite im Admin und reicht sie als
    `srcdoc` weiter (siehe `api_preview`). Ein `srcdoc`-Rahmen erbt die Regel des
    Elterndokuments — also diese hier. Weil in das HTML ein `<base>` auf die
    echte Adresse eingefuegt wird, kommen Schriften und Bilder darin vom
    Nachbarport und nicht von der Admin-Adresse: ohne diese Ausnahme zeigte die
    Vorschau ab „Durchsetzen" eine Seite ohne Schrift und ohne Bilder, und das
    ist genau das, was man dort beurteilen will.

    Gleiche Herleitung wie in `api_preview`, damit beide nicht auseinanderlaufen.
    Zwischengespeichert ueber die Aenderungszeit von site.json — sonst laege bei
    jeder Antwort ein vollstaendiges Lesen der Datei davor.
    """
    global _preview_origin_cache
    try:
        mtime = os.path.getmtime(SITE_PATH)
    except OSError:
        mtime = -1.0
    host = (request.host or '').split(':')[0]
    key = (mtime, host, request.scheme)
    if _preview_origin_cache[0] == key:
        return _preview_origin_cache[1]
    pub = (load_site()['design'].get('public_url') or '').rstrip('/')
    if not _ORIGIN_RE.match(pub):
        pub = ''
    if request.scheme == 'https':
        # Bei HTTPS taugt nur die eingetragene HTTPS-Adresse: eine http-Quelle
        # blockt der Browser ohnehin als gemischten Inhalt.
        out = [pub] if pub.startswith('https://') else []
    else:
        out = [pub or f'http://{host}:{PUBLIC_PORT}']
    origins = tuple(o for o in out if o)
    _preview_origin_cache = (key, origins)
    return origins


def _csp_admin() -> str:
    """Regel fuer das Admin-Panel — bewusst OHNE `frame-ancestors` und ohne
    `X-Frame-Options`: Ueber den HA-Ingress laeuft das Panel in einem iframe von
    Home Assistant, eine Sperre hier liesse das Panel weiss.

    `frame-src 'self'` deckt den Vorschaurahmen ab, die Herkunft der
    oeffentlichen Seite kommt aus `_preview_origins()`.
    """
    extra = ' '.join(_preview_origins())
    src = ("'self' " + extra) if extra else "'self'"
    return (_CSP_COMMON + f"; font-src {src}; connect-src {src}; "
            f"manifest-src {src}; base-uri {src}; frame-src 'self'")

# Faehigkeiten, die MyPage nicht braucht, gar nicht erst zulassen. Die vier
# Video-Eintraege nennen die Embed-Hosts, sonst fehlt im eingebetteten Video der
# Vollbild-Knopf. `clipboard-write` bleibt fuer die Kopier-Knoepfe.
PERMISSIONS_POLICY = (
    # Nur Namen, die Browser auch kennen — ein unbekannter (etwa
    # `ambient-light-sensor`, in Chrome hinter einem Flag) wird zwar nur
    # uebersprungen, schreibt aber bei jedem Seitenaufruf eine Fehlermeldung
    # in die Konsole, in der spaeter die echten Treffer untergehen.
    "accelerometer=(), camera=(), display-capture=(), "
    "geolocation=(), gyroscope=(), magnetometer=(), microphone=(), midi=(), "
    "payment=(), publickey-credentials-get=(), screen-wake-lock=(), serial=(), "
    "usb=(), xr-spatial-tracking=(), clipboard-write=(self), "
    'autoplay=(self "https://www.youtube-nocookie.com" "https://player.vimeo.com"), '
    'encrypted-media=(self "https://www.youtube-nocookie.com" "https://player.vimeo.com"), '
    'fullscreen=(self "https://www.youtube-nocookie.com" "https://player.vimeo.com"), '
    'picture-in-picture=(self "https://www.youtube-nocookie.com" "https://player.vimeo.com")'
)


def _security_headers(resp, csp: str):
    """CSP, Permissions-Policy und die zwei kleinen Kopfzeilen an jede Antwort.

    `setdefault` statt Zuweisung: Routen, die es besser wissen, behalten ihre
    eigene Angabe — die PDF-Auslieferung setzt `Content-Security-Policy: sandbox`,
    und das ist strenger als alles hier.

    Der Modus kommt aus den Einstellungen und steht ab Werk auf `report`: Die
    Regel wird mitgeschickt, blockiert aber nichts, sondern meldet in der Konsole,
    was sie blockiert *haette*. So faellt ein Fehlalarm auf, bevor er als weisse
    Seite auffaellt.
    """
    mode = str(load_config().get('csp_mode') or 'report')
    resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
    resp.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    resp.headers.setdefault('Permissions-Policy', PERMISSIONS_POLICY)
    if mode == 'off':
        return resp
    name = ('Content-Security-Policy' if mode == 'on'
            else 'Content-Security-Policy-Report-Only')
    resp.headers.setdefault(name, csp)
    return resp


public_app.after_request(lambda r: _security_headers(r, CSP_PUBLIC))
admin_app.after_request(lambda r: _security_headers(r, _csp_admin()))


# Einstieg in die Vorschau: ?vorschau=<token> an einer beliebigen oeffentlichen
# Adresse. Der Token wandert in einen Cookie und aus der Adresse heraus — sonst
# steht er im Verlauf, im Referrer und in jedem geteilten Screenshot.
def _preview_entry():
    token = request.args.get(PREVIEW_PARAM)
    if not token:
        return None
    hours = preview_token_hours(token)
    args = {k: v for k, v in request.args.items(multi=True) if k != PREVIEW_PARAM}
    # Ueber _safe_next, obwohl der Pfad vom Server geparst kommt: Ein Aufruf von
    # `//fremde-seite.de/?vorschau=…` ergibt einen Pfad, der mit zwei Schraegstrichen
    # beginnt — als `Location` waere das eine protokollrelative Adresse und damit
    # eine Weiterleitung nach draussen.
    target = _safe_next(request.path + ('?' + urlencode(args, doseq=True) if args else ''))
    resp = redirect(target)
    if hours is None:
        # Abgelaufen oder zurueckgezogen: Cookie weg, Seite verhaelt sich wieder
        # wie fuer jeden anderen Besucher.
        resp.delete_cookie(PREVIEW_COOKIE)
        log.info("Vorschau-Link abgelehnt (abgelaufen oder zurückgezogen)")
        return resp
    resp.set_cookie(PREVIEW_COOKIE, token, httponly=True, samesite='Lax',
                    secure=_cookie_secure(), max_age=hours * 3600)
    log.info("Vorschau-Sitzung begonnen (%d h)", hours)
    return resp


public_app.before_request(_preview_entry)


@public_app.route('/vorschau-ende')
def preview_end():
    resp = redirect('/')
    resp.delete_cookie(PREVIEW_COOKIE)
    return resp


@public_app.after_request
def _preview_marks(resp):
    """Balken und noindex, solange die Vorschau laeuft.

    Der Balken kommt hier statt in die Vorlagen: Es sind zwanzig oeffentliche
    Seiten, und vergessen wuerde man genau die, auf der man sich dann wundert.
    """
    if not preview_active():
        return resp
    # Auch wenn der Link irgendwo aufgeschnappt wird: nichts davon gehoert in
    # einen Suchindex.
    resp.headers['X-Robots-Tag'] = 'noindex, nofollow'
    if resp.mimetype != 'text/html' or resp.direct_passthrough:
        return resp
    try:
        html = resp.get_data(as_text=True)
    except (RuntimeError, UnicodeDecodeError):
        return resp
    if '</body>' not in html:
        return resp
    t = load_translations(detect_language(request))
    bar = (
        '<div style="position:fixed;left:0;right:0;bottom:0;z-index:99999;'
        'background:#d29922;color:#1c1c1c;font:600 13px/1.4 system-ui,sans-serif;'
        'padding:8px 14px;display:flex;gap:12px;align-items:center;'
        'justify-content:center;flex-wrap:wrap">'
        f'<span>{html_mod.escape(t.get("preview_bar", ""))}</span>'
        '<a href="/vorschau-ende" style="color:#1c1c1c;text-decoration:underline">'
        f'{html_mod.escape(t.get("preview_bar_end", ""))}</a></div>'
    )
    resp.set_data(html.replace('</body>', bar + '</body>', 1))
    return resp


@public_app.context_processor
def _inject_seo():
    return _seo_urls(detect_language(request))


@public_app.after_request
def _lang_headers(resp):
    """`Content-Language` und `Vary` an jede ausgelieferte Seite.

    Ohne `Vary` darf jeder Zwischenspeicher — nginx, Cloudflare, ein
    Firmen-Proxy — die erste Fassung, die durch ihn hindurchgeht, für alle
    festhalten. Bei zwei Sprachen auf derselben Adresse heißt das: kommt der
    Suchmaschinen-Roboter zuerst, sehen danach auch die Besucher dessen Fassung.
    """
    if resp.mimetype != 'text/html':
        return resp
    lang = getattr(g, 'mypage_lang', None)
    if lang:
        resp.headers['Content-Language'] = lang
    resp.vary.add('Cookie')
    if getattr(g, 'mypage_lang_auto', False):
        resp.vary.add('Accept-Language')
    return resp


@public_app.after_request
def _cache_headers(resp):
    """ETag und `Cache-Control` an die oeffentlichen Seiten.

    Gespart wird damit die **Uebertragung**, nicht das Rendern: die Seite wird
    weiterhin bei jeder Anfrage gebaut, aber wenn dabei Byte fuer Byte dasselbe
    herauskommt wie beim letzten Mal, geht statt einiger hundert Kilobyte ein
    leeres 304 zurueck. Der Fingerabdruck stammt deshalb aus dem fertigen Rumpf
    und nicht aus Aenderungszeiten der Ablagen — jede kuenstliche Kennzahl
    muesste bei jedem neuen Feld nachgezogen werden und liefert beim ersten
    Vergessen veraltete Seiten aus.

    `max-age=0, must-revalidate` heisst: ein vorgeschalteter Proxy darf die
    Seite behalten, muss sie aber vor jeder Auslieferung rueckfragen. Damit ist
    ein frisch gespeicherter Beitrag sofort draussen — eine Haltezeit groesser
    als null waere genau der Fall, in dem der Betreiber seine eigene Aenderung
    nicht sieht und an der falschen Stelle sucht.

    Angemeldete Mitglieder bekommen `private, no-store` und keinen ETag: ihre
    Seiten koennen geschuetzten Inhalt tragen, und der darf in keinem
    gemeinsamen Zwischenspeicher landen. Geprueft wird dafuer nur, ob ueberhaupt
    ein Sitzungs-Cookie mitkommt — ein abgelaufenes Cookie fuehrt dann zur
    vorsichtigeren Antwort, was die richtige Richtung ist, und erspart den
    Griff in die Benutzerdatei bei jedem Gast.
    """
    if request.method not in ('GET', 'HEAD'):
        return resp
    if resp.status_code != 200 or resp.mimetype != 'text/html':
        return resp
    # Wer schon selbst etwas gesetzt hat, weiss es besser (etwa `no-store` an
    # den Auslieferrouten fuer Dateien).
    if resp.direct_passthrough or resp.headers.get('Cache-Control'):
        return resp
    # Vorschau wie eine Mitglieder-Sitzung behandeln: Die Seite zeigt dort Dinge,
    # die fuer alle anderen gesperrt sind. Landete sie in einem gemeinsamen
    # Zwischenspeicher, bekaeme sie der naechste Besucher zu sehen.
    if request.cookies.get('usession') or request.cookies.get(PREVIEW_COOKIE):
        resp.headers['Cache-Control'] = 'private, no-store'
        return resp
    resp.headers['Cache-Control'] = 'public, max-age=0, must-revalidate'
    resp.set_etag(hashlib.sha256(resp.get_data()).hexdigest()[:32])
    return resp.make_conditional(request)


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
    # Datei, alte Stände werden dadurch nie ausgeliefert. Der Stamm des
    # Bildnamens steht davor, damit `_wm_cache_forget()` die Fassungen eines
    # Bildes wiederfindet — aus dem Hash allein lässt sich der Bezug nicht
    # zurückrechnen.
    key = hashlib.sha256((text + '|' + safe).encode()).hexdigest()[:24]
    cached = WM_CACHE_DIR / f'{Path(safe).stem}-{key}.webp'
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


@public_app.template_filter('abs_url')
def _abs_url(u: str) -> str:
    """Pfad zur vollen Adresse machen — für alles, was außerhalb der Seite gelesen wird.

    Open Graph landet bei WhatsApp, Discord, Slack und X, und die holen das Bild
    von ihren eigenen Servern. Ein Pfad wie „/uploads/foo.webp" hat dort keinen
    Bezugspunkt mehr: die Vorschau bleibt leer. Bereits vollständige Adressen und
    eingebettete Daten bleiben unangetastet.
    """
    u = (u or '').strip()
    if not u or u.startswith(('http://', 'https://', '//', 'data:')):
        return u
    return _base_url() + ('' if u.startswith('/') else '/') + u


# ── Öffentliche Vorlagen im Admin ─────────────────────────────────────────────
# Die Vorschau-Routen (/preview/blog, /preview/page, …) rendern dieselben
# Vorlagen wie die öffentliche Seite. Filter und Kontext hängen aber an
# `public_app`; die eigene Jinja-Umgebung von `admin_app` kennt sie nicht. Ohne
# diese Übernahme bricht jede Vorschau mit „no filter named 'abs_url'" ab
# (Fehler 500), und die gewählte Schrift fehlt, weil `font_family` leer bleibt.
admin_app.jinja_env.filters['abs_url'] = _abs_url
admin_app.context_processor(_inject_font)
admin_app.context_processor(_inject_banner)
admin_app.context_processor(_inject_seo)


def _public_url_list(site: dict, base: str) -> list:
    """Alle öffentlich indexierbaren URLs (Startseite, Projekte, Blog, Bibliothek).

    Grundlage für den IndexNow-Ping — was hier fehlt, wird Bing/Yandex nie gemeldet.
    """
    urls = [base + '/']
    urls += [f"{base}/seite/{p['slug']}" for p in site.get('pages', []) if p.get('visible')]
    urls += [f"{base}/p/{p['id']}" for p in projects_public(site) if _has_detail(p)]
    posts = sorted_posts(site, public_only=True)
    if posts:
        urls.append(base + '/blog')
        urls += [f"{base}/blog/{p['id']}" for p in posts]
    lib_entries = _lib_public_entries(site)
    if lib_entries:
        urls.append(base + '/bibliothek')
        urls += [f"{base}/bibliothek/{e['slug']}" for e in lib_entries]
    trav_trips = _trav_public_trips(site)
    if trav_trips:
        urls.append(base + '/reiseblog')
        for tr in trav_trips:
            urls.append(f"{base}/reiseblog/{tr['slug']}")
            urls += [f"{base}/reiseblog/{tr['slug']}/{d['slug']}"
                     for d in _trav_public_days(tr)]
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
    if base.startswith(('http://', 'https://')) and post_visible(post) and blog_public(site):
        indexnow_submit([base + '/', base + '/blog', f"{base}/blog/{post['id']}"])


def _indexnow_ping_project(site: dict, proj: dict) -> None:
    base = (site['design'].get('public_url') or '').rstrip('/')
    if (base.startswith(('http://', 'https://')) and _has_detail(proj)
            and proj in projects_public(site)):
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
    if maintenance_active(site):
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
    """Spielregeln aus dem mitgelieferten Markdown, mit Rückfall auf Deutsch.

    `lang` stammt über `detect_language` aus der Anfrage — seit `?lang=` dort
    mitzählt, sogar direkt aus der Adresszeile. Deshalb wird der Wert nicht
    weitergereicht, sondern auf eines von zwei Literalen zurückgeführt: er baut
    einen Dateinamen, und ein durchgereichter Anfragewert in einem Pfad ist
    genau das, was CodeQL zu Recht als `py/path-injection` meldet. `safe_under`
    kommt als zweiter Riegel dazu; `game` setzen ausschließlich die Aufrufer als
    feste Zeichenkette.
    """
    code = 'en' if lang == 'en' else 'de'
    path = safe_under(Path(_BASE), f'game_{game}_rules_{code}.md')
    if path is None or not path.is_file():
        path = safe_under(Path(_BASE), f'game_{game}_rules_de.md')
    if path is None or not path.is_file():
        return ''
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
    if maintenance_active(site):
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
    if maintenance_active(site):
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
    if maintenance_active(site):
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
    if maintenance_active(site):
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
    if maintenance_active(site):
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
    if maintenance_active(site):
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
    if maintenance_active(site):
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
    if maintenance_active(site):
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
    if maintenance_active(site):
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
    trav_trips = _trav_public_trips(site)
    if trav_trips:
        entries.append((base + '/reiseblog', ''))
        for tr in trav_trips:
            entries.append((f"{base}/reiseblog/{tr['slug']}", ''))
            entries += [(f"{base}/reiseblog/{tr['slug']}/{d['slug']}",
                         d['date'] if _valid_date(d.get('date')) else '')
                        for d in _trav_public_days(tr)]
    entries += [(f"{base}/p/{p['id']}", '') for p in projects_public(site)
                if _has_detail(p)]
    if posts:
        entries.append((base + '/blog', newest))
        entries += [(f"{base}/blog/{p['id']}", p['date'] if _valid_date(p.get('date')) else '')
                    for p in posts]
    # Sprachvarianten mitmelden. Jede Adresse liefert beide Fassungen, die
    # englische unter `?lang=en` — in der Sitemap stand davon bisher nichts, und
    # eine Adresse, die nirgends genannt wird, findet ein Roboter allenfalls
    # zufällig. `xhtml:link` benennt die Fassungen an derselben Stelle, an der
    # die Seite ohnehin gemeldet wird.
    default = site_default_lang(site)

    def _alts(loc: str) -> str:
        out = ''
        for lg in SITE_LANGS:
            href = loc if lg == default else f'{loc}?lang={lg}'
            out += f'    <xhtml:link rel="alternate" hreflang="{lg}" href="{html_mod.escape(href)}"/>\n'
        out += f'    <xhtml:link rel="alternate" hreflang="x-default" href="{html_mod.escape(loc)}"/>\n'
        return out

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += ('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
            ' xmlns:xhtml="http://www.w3.org/1999/xhtml">\n')
    for loc, lastmod in entries:
        xml += f'  <url>\n    <loc>{html_mod.escape(loc)}</loc>\n'
        if lastmod:
            xml += f'    <lastmod>{lastmod}</lastmod>\n'
        xml += _alts(loc)
        xml += '  </url>\n'
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


# ── RSS-Feed ──────────────────────────────────────────────────────────────────
#
# Der Feed ist die einzige Schnittstelle, über die andere Programme neue Inhalte
# mitbekommen: Feed-Leser, Home Assistants `feedreader` und jeder
# Automatisierungsdienst, der „neuer Eintrag → irgendwohin weiterreichen"
# anbietet. Deshalb steht hier alles drin, was ein solcher Dienst braucht —
# Volltext, Bildadresse und Schlagwörter — und nicht nur Titel plus drei Zeilen.

FEED_MAX_ITEMS = 50
FEED_TEASER_MAX = 400
FEED_TTL_MIN = 60
_FEED_MIME = {'.webp': 'image/webp', '.png': 'image/png', '.jpg': 'image/jpeg',
              '.jpeg': 'image/jpeg', '.gif': 'image/gif'}
# Mittags statt um Mitternacht: `00:00:00 +0000` ist für jeden Leser westlich von
# Greenwich noch der Vortag, ein Beitrag vom 7. stünde in den USA unter dem 6.
FEED_HOUR = 12
_FEED_ABS_RE = re.compile(r'\b(src|href)="/([^"/][^"]*)"', re.I)


def _feed_lang(site: dict) -> str:
    """Sprache des Feeds. `?lang=` schlägt die Konfiguration, der Browser zählt nie.

    Ein Feed-Leser holt dieselbe Adresse für alle seine Nutzer und schickt dabei
    meist gar kein `Accept-Language`. Hinge die Sprache daran, lieferte derselbe
    URL mal Deutsch und mal Englisch — und der erste Zwischenspeicher friert eine
    der beiden Fassungen für alle ein.
    """
    q = (request.args.get('lang') or '').strip().lower()
    if q in ('de', 'en'):
        return q
    cfg = (site['design'].get('feed_lang') or '').strip().lower()
    return cfg if cfg in ('de', 'en') else 'de'


def _feed_cut(text: str, limit: int = FEED_TEASER_MAX) -> str:
    """Auf `limit` kürzen, aber an der letzten Wortgrenze davor statt mittendrin."""
    txt = (text or '').strip()
    if len(txt) <= limit:
        return txt
    cut = txt[:limit]
    sp = cut.rfind(' ')
    return (cut[:sp] if sp > limit // 2 else cut).rstrip(' ,;:-–') + ' …'


# Ein importiertes README enthält Links wie `filebox/` oder `docs/README.md` —
# relativ zum Repository gemeint. Auf der Projektseite lösen sie sich gegen
# `/p/<id>` auf, im Feed-Leser gegen dessen eigene Adresse: beides führt ins
# Leere. Deshalb werden sie auf das Repository umgebogen. `HEAD` steht bei
# GitHub für den Standard-Branch, der Name muss also nicht bekannt sein.
_MD_REL_HREF_RE = re.compile(
    r'(<a\b[^>]*?\bhref=")(?!https?://|mailto:|data:|#|/|\?)([^"]+)(")', re.I)
_MD_REL_SRC_RE = re.compile(
    r'(<img\b[^>]*?\bsrc=")(?!https?://|mailto:|data:|#|/|\?)([^"]+)(")', re.I)


def _repo_abs_links(html: str, repo_url: str) -> str:
    """Relative Links eines GitHub-READMEs auf das Repository umbiegen."""
    url = (repo_url or '').strip().rstrip('/')
    if not html or not url:
        return html or ''
    # Hostname vergleichen, nicht `startswith` — `evil.com/x?y=github.com` wäre
    # sonst ein gültiges Ziel (siehe CodeQL-Muster für URL-Prüfungen)
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    if host != 'github.com' or len(parsed.path.strip('/').split('/')) != 2:
        return html

    def fix(m, kind):
        path = m.group(2).lstrip('./').lstrip('/')
        if not path:
            return m.group(0)
        if kind == 'img':
            target = f'{url}/raw/HEAD/{path}'
        else:
            target = f'{url}/{"tree" if path.endswith("/") else "blob"}/HEAD/{path}'
        return f'{m.group(1)}{target}{m.group(3)}'

    html = _MD_REL_HREF_RE.sub(lambda m: fix(m, 'a'), html)
    return _MD_REL_SRC_RE.sub(lambda m: fix(m, 'img'), html)


def _feed_abs(html: str, base: str) -> str:
    """Absolute Adressen im Volltext. Ein Feed-Leser kennt den Kontext der Seite
    nicht — `/uploads/x.webp` zeigt bei ihm ins Leere."""
    return _FEED_ABS_RE.sub(lambda m: f'{m.group(1)}="{base}/{m.group(2)}"', html or '')


def _feed_media(url: str, base: str) -> tuple:
    """(Adresse, MIME-Typ, Größe) eines Bildes für `<enclosure>`.

    Nur eigene Uploads: RSS verlangt eine Längenangabe, und die ließe sich für
    ein fremdes Bild nur durch Abholen ermitteln — ein Abruf auf Zuruf
    gespeicherter Daten (SSRF) und obendrein langsam.

    Die Adresse zeigt bewusst auf `/uploads/`: diese Route brennt KI-erzeugten
    Bildern die Kennzeichnung ein. Die Größe ist dann eine Schätzung, weil die
    Auslieferung neu kodiert — RSS behandelt `length` ohnehin als Hinweis.
    """
    name = (url or '').strip()
    if not name.startswith('/uploads/'):
        return ('', '', 0)
    name = name.removeprefix('/uploads/')
    p = safe_under(UPLOADS_DIR, name)
    if p is None or not p.is_file():
        return ('', '', 0)
    try:
        size = p.stat().st_size
    except OSError:
        return ('', '', 0)
    return (f'{base}/uploads/{name}',
            _FEED_MIME.get(p.suffix.lower(), 'application/octet-stream'), size)


def _feed_items(site: dict, lang: str, t: dict, loc, base: str) -> list:
    """Alle Feed-Einträge aus Blog, Reiseblog und (auf Wunsch) Projekten und
    Bibliothek.

    Mitglieder-only-Inhalte kommen mit Titel und Adresse vor, aber ohne Text und
    ohne Bild. Sie ganz zu verschweigen wäre auch falsch — auf der Website stehen
    sie ja ebenfalls in der Liste, nur gesperrt. Der alte Feed prüfte die Sperre
    gar nicht und lieferte 300 Zeichen des Textes an jeden.
    """
    d = site['design']
    locked_note = t.get('feed_members_only') or 'Nur für Mitglieder.'
    untitled = t.get('feed_untitled') or '—'
    items = []

    def add(*, title, link, date_iso, summary, body, tags, image, locked):
        items.append({
            'title': (title or '').strip() or untitled,
            'link': link,
            'date': date_iso or '',
            'summary': locked_note if locked else _feed_cut(summary),
            'body': '' if locked else (body or ''),
            'tags': [x for x in (tags or []) if x][:8],
            'image': '' if locked else (image or ''),
            'locked': locked,
        })

    for p in sorted_posts(site, public_only=True):
        locked = bool(p.get('members_only'))
        body = '' if locked else _overlay_html_images(render_md(loc(p, 'text')))
        add(title=loc(p, 'title'), link=f"{base}/blog/{p['id']}",
            date_iso=p.get('date'),
            summary=loc(p, 'meta') or _plain_excerpt(body, 100000),
            body=body, tags=p.get('tags'), image=p.get('image'), locked=locked)

    # Reiseblog: hängt am Modulschalter, sonst stünden Tage im Feed, die die
    # Website gar nicht ausliefert
    if d.get('travel_enabled'):
        data = load_travel()
        for trip in _trav_public_trips(site, data):
            locked = bool(trip.get('members_only'))
            for day in _trav_public_days(trip):
                art = _trav_article(day, lang)
                body = ('' if locked else
                        _overlay_html_images(render_md(art.get('body') or '')))
                photo = next((ph.get('url') for ph in (day.get('photos') or [])
                              if ph.get('url')), '')
                # Der Tagestitel allein („Ankunft") sagt im Feed-Leser nichts —
                # dort stehen die Einträge ohne den Zusammenhang der Reise
                head = ' · '.join(x for x in (trip.get('name'), art.get('title')) if x)
                add(title=head,
                    link=f"{base}/reiseblog/{trip['slug']}/{day['slug']}",
                    date_iso=day.get('date'),
                    summary=art.get('teaser') or _plain_excerpt(body, 100000),
                    body=body, tags=(day.get('article') or {}).get('tags'),
                    image=photo, locked=locked)

    if d.get('feed_projects'):
        for p in projects_public(site):
            # Ohne Detailseite gäbe es keine Adresse, auf die der Eintrag zeigen
            # könnte — ein Feed-Eintrag ohne Ziel ist wertlos
            if not _has_detail(p):
                continue
            body = _repo_abs_links(_overlay_html_images(render_md(loc(p, 'long'))),
                                   p.get('repo_url', ''))
            add(title=p.get('title'), link=f"{base}/p/{p['id']}",
                # Letzter Push des Repositories; von Hand angelegte Projekte
                # haben keinen und bleiben ohne Datum
                date_iso=p.get('repo_pushed') or '',
                summary=loc(p, 'desc') or _plain_excerpt(body, 100000),
                body=body, tags=p.get('tags'), image=p.get('image'), locked=False)

    if d.get('feed_library'):
        for e in _lib_public_entries(site):
            locked = bool(e.get('members_only'))
            body = '' if locked else _overlay_html_images(render_md(loc(e, 'body')))
            add(title=loc(e, 'title'), link=f"{base}/bibliothek/{e.get('slug', '')}",
                date_iso=e.get('updated'),
                summary=loc(e, 'meta') or loc(e, 'summary') or _plain_excerpt(body, 100000),
                body=body, tags=e.get('tags'), image=e.get('image'), locked=locked)

    # Neueste zuerst; Einträge ohne Datum (Projekte) landen dadurch hinten
    items.sort(key=lambda i: i['date'], reverse=True)
    return items[:FEED_MAX_ITEMS]


def _feed_pubdate(date_iso: str, seq: int) -> str:
    """`YYYY-MM-DD` → RFC-822. `seq` verschiebt gleiche Daten um je eine Minute.

    Ohne den Versatz tragen alle Einträge eines Tages denselben Zeitstempel, und
    die Reihenfolge im Leser wird zufällig. Die Minute ist keine erfundene
    Uhrzeit, sondern die Position im Feed — anders lässt sich „selber Tag, diese
    Reihenfolge" in RSS nicht ausdrücken.
    """
    try:
        base = datetime.strptime(date_iso, '%Y-%m-%d').replace(
            hour=FEED_HOUR, tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return ''
    return (base - timedelta(minutes=seq)).strftime('%a, %d %b %Y %H:%M:%S +0000')


@public_app.route('/feed.xml')
def rss_feed():
    site = load_site()
    lang = _feed_lang(site)
    t = load_translations(lang)
    loc = _loc_factory(lang)
    base = _base_url()
    d = site['design']
    esc = html_mod.escape
    items = _feed_items(site, lang, t, loc, base)

    author = site['profile'].get('name') or ''
    body = ''
    seen_dates: dict[str, int] = {}
    for it in items:
        seq = seen_dates[it['date']] = seen_dates.get(it['date'], -1) + 1
        pub = _feed_pubdate(it['date'], seq)
        img_url, img_type, img_len = _feed_media(it['image'], base)
        body += (f'    <item>\n'
                 f'      <title>{esc(it["title"])}</title>\n'
                 f'      <link>{esc(it["link"])}</link>\n'
                 f'      <guid isPermaLink="true">{esc(it["link"])}</guid>\n'
                 + (f'      <pubDate>{pub}</pubDate>\n' if pub else '')
                 + f'      <description>{esc(it["summary"])}</description>\n'
                 + (f'      <dc:creator>{esc(author)}</dc:creator>\n' if author else '')
                 + ''.join(f'      <category>{esc(tag)}</category>\n' for tag in it['tags'])
                 + (f'      <enclosure url="{esc(img_url)}" type="{img_type}" '
                    f'length="{img_len}"/>\n' if img_url else '')
                 # CDATA statt Maskieren: der Volltext ist HTML und soll es
                 # bleiben. `]]>` kann darin nicht vorkommen — `render_md`
                 # erzeugt es nicht und Markdown-Quelltext wird escaped —,
                 # sicherheitshalber wird es trotzdem aufgetrennt.
                 + (f'      <content:encoded><![CDATA['
                    f'{_feed_abs(it["body"], base).replace("]]>", "]]]]><![CDATA[>")}'
                    f']]></content:encoded>\n' if it['body'] else '')
                 + f'    </item>\n')

    title = d.get('site_title') or site['profile'].get('name') or 'MyPage'
    desc = loc(site['profile'], 'tagline') or title
    self_url = f'{base}/feed.xml' + (f'?lang={lang}' if request.args.get('lang') else '')
    # Kanal-Logo: das Profilbild, sonst das Favicon — beides nur, wenn es ein
    # eigener Upload ist (siehe _feed_media)
    logo, _lt, _ll = _feed_media(site['profile'].get('avatar') or d.get('favicon') or '', base)
    built = max((it['date'] for it in items if it['date']), default='')
    head = (f'    <title>{esc(title)}</title>\n'
            f'    <link>{esc(base)}/blog</link>\n'
            f'    <description>{esc(desc)}</description>\n'
            f'    <language>{lang}</language>\n'
            f'    <generator>MyPage</generator>\n'
            f'    <ttl>{FEED_TTL_MIN}</ttl>\n'
            f'    <atom:link href="{esc(self_url)}" rel="self" type="application/rss+xml"/>\n'
            + (f'    <lastBuildDate>{_feed_pubdate(built, 0)}</lastBuildDate>\n'
               if built else '')
            # Kein <managingEditor>: RSS verlangt dort eine E-Mail-Adresse, und die
            # Website zeigt sie bewusst nur zerlegt (Schutz vor Adress-Sammlern).
            # atom:author und dc:creator nennen den Namen ohne Adresse.
            + (f'    <atom:author><atom:name>{esc(author)}</atom:name></atom:author>\n'
               if author else '')
            + (f'    <image>\n      <url>{esc(logo)}</url>\n'
               f'      <title>{esc(title)}</title>\n'
               f'      <link>{esc(base)}/</link>\n    </image>\n' if logo else ''))

    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"'
           ' xmlns:content="http://purl.org/rss/1.0/modules/content/"'
           ' xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
           '  <channel>\n'
           f'{head}{body}'
           '  </channel>\n</rss>\n')

    # Kein 404 mehr, wenn nichts da ist: ein leerer, gültiger Feed heißt „noch
    # nichts veröffentlicht", ein 404 heißt für den Leser „kaputt" — und manche
    # tragen einen so gemeldeten Feed dauerhaft aus.
    resp = make_response(xml)
    resp.headers['Content-Type'] = 'application/rss+xml; charset=utf-8'
    resp.set_etag(hashlib.sha256(xml.encode('utf-8')).hexdigest()[:32])
    resp.headers['Cache-Control'] = f'public, max-age={FEED_TTL_MIN * 60}'
    # make_conditional beantwortet If-None-Match/If-Modified-Since mit 304 —
    # der Feed wird im Minutentakt abgefragt und ändert sich fast nie
    return resp.make_conditional(request)


@public_app.errorhandler(404)
def not_found(_e):
    site = load_site()
    # Eingerichtete Weiterleitung? Greift nur für nicht (mehr) existierende Pfade.
    rd = _find_redirect(site, request.path)
    if rd:
        # rd['to'] stammt aus der gespeicherten Konfiguration (Admin), nicht aus der Anfrage
        return redirect(rd['to'], code=301 if rd.get('permanent', True) else 302)
    # Erst hier festhalten: Ein Pfad mit eingerichteter Weiterleitung ist kein
    # Fehler mehr, und ihn weiter zu melden hieße, eine erledigte Sache jeden
    # Tag aufs Neue auf die Liste zu setzen.
    try:
        record_notfound(request)
    except Exception as e:      # eine Fehlerseite darf an nichts scheitern
        log.warning("404 konnte nicht festgehalten werden: %s", e)
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
    if maintenance_active(site):
        return _maintenance_page(site, lang)
    t = load_translations(lang)
    stats = load_stats()
    legal = site.get('legal', {})
    loc = _loc_factory(lang)
    email = site['profile'].get('email', '')
    email_parts = email.split('@', 1) if '@' in email else None
    projects = [dict(p, has_detail=_has_detail(p)) for p in projects_public(site)]
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
    # Reiseblog: die jüngsten Reisen als Kacheln, „alle anzeigen" führt auf die
    # Übersicht. Reihenfolge wie im Admin — die neueste Reise steht dort oben.
    travel_trips = [_trav_trip_view(tr, lang) for tr in _trav_public_trips(site)[:6]]
    # Formulare: Titel und Einleitung als Anriss, der Rest steht auf der Seite
    # selbst. Ohne Titel gäbe es nichts anzuklicken, also fliegen sie raus.
    form_cards = [{'slug': f['slug'], 'title': loc(f, 'title'),
                   'intro': _plain_excerpt(render_md(loc(f, 'intro')))}
                  for f in _public_forms(site) if loc(f, 'title')]

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
        'facts':        ('fakten',       'facts_heading',        bool(sections.get('facts'))),
        'videos':       ('videos',       'videos_heading',       bool(sections.get('videos'))),
        'downloads':    ('downloads',    'downloads_heading',    bool(sections.get('downloads'))),
        'partners':     ('partner',      'partners_heading',     bool(sections.get('partners'))),
        'testimonials': ('testimonials', 'testimonials_heading', bool(sections.get('testimonials'))),
        'photos':       ('photos',       'albums_heading',       bool(albums)),
        'library':      ('library',      'library_heading',      bool(library_entries)),
        'team':         ('team',         'team_heading',         bool(sections.get('team'))),
        'timeline':     ('timeline',     'timeline_heading',     bool(sections.get('timeline'))),
        'events':       ('events',       'events_heading',       bool(sections.get('events'))),
        'links':        ('links',        'links_heading',        bool(sections.get('links'))),
        'faq':          ('faq',          'faq_heading',          bool(sections.get('faq'))),
        'location':     ('standort',     'location_heading',     loc_present),
        # Der Reiseblog erscheint, sobald er freigegeben ist UND mindestens ein
        # Tag veroeffentlicht wurde -- sonst waere die Sprungmarke ein Verweis
        # ins Leere. Beides steckt schon in `travel_trips`.
        'travel':       ('reiseblog',    'trav_trips_heading',   bool(travel_trips)),
        'forms':        ('formulare',    'forms_heading',        bool(form_cards)),
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

    # Frei konfigurierbare Überschriften je Abschnitt (leer = Standard aus den Locales)
    sec_titles = {k: section_title(sections, k, lang) for k in SECTION_TITLE_KEYS}
    # Der Werdegang hatte sein eigenes Feld, bevor es das für alle gab.
    timeline_title = sec_titles.get('timeline') or loc(sections, 'timeline_title')
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
                if sec_titles.get(key):
                    label = sec_titles[key]
                elif key == 'timeline' and timeline_title:
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
        trav_in_nav = 'travel' in section_order and section_defs['travel'][2]
        # Steht der Formular-Abschnitt schon als Sprungmarke in der Leiste,
        # entfallen die einzelnen Formular-Links: sonst stünde dort erst
        # „Formulare" und daneben nochmal jedes einzelne Formular.
        forms_in_nav = 'forms' in section_order and section_defs['forms'][2]
        nav_items += _nav_links(site, loc, t, with_library=not lib_in_nav,
                                with_travel=not trav_in_nav,
                                with_forms=not forms_in_nav)

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
                           library_layout=_library(site).get('layout', 'carousel'),
                           travel_trips=travel_trips,
                           form_cards=form_cards,
                           countdown_title=countdown_title,
                           newsletter_open=newsletter_open() and not static_export,
                           nl=_clean_str(request.args.get('nl'), 20),
                           nav_items=nav_items,
                           section_order=section_order,
                           sec_titles=sec_titles,
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
    if maintenance_active(site):
        return _maintenance_page(site, lang)
    all_posts = sorted_posts(site, public_only=True)
    if not all_posts:
        abort(404)
    query = _clean_str(request.args.get('q'), 80)
    tag = _clean_str(request.args.get('tag'), 30)
    page = _page_arg()
    pager = blog_pager(filter_posts(all_posts, query, tag), page, query, tag)
    # Eine Seitenzahl jenseits des Bestandes ist keine Seite. Ohne 404 gäbe es
    # unendlich viele Adressen, die alle dasselbe letzte Dutzend zeigen — der
    # Suchmaschine wäre der Bestand damit beliebig groß.
    if page > pager['pages']:
        abort(404)
    count_visit(request)
    t = load_translations(lang)
    loc = _loc_factory(lang)
    return render_template('blog.html', t=t, lang=lang, site=site, loc=loc,
                           posts=pager['posts'], pager=pager, tags=all_post_tags(site),
                           query=query, active_tag=tag,
                           newsletter_open=newsletter_open(),
                           nl=_clean_str(request.args.get('nl'), 20),
                           meta_desc=_site_meta(site, loc),
                           year=datetime.now(timezone.utc).year)


@public_app.route('/suche')
def site_search_page():
    lang = detect_language(request)
    site = load_site()
    if maintenance_active(site):
        return _maintenance_page(site, lang)
    if not site['design'].get('search_enabled'):
        abort(404)
    query = _clean_str(request.args.get('q'), 80)
    loc = _loc_factory(lang)
    member = current_member(request)
    results = site_search(site, query, loc, member is not None, lang) if query else []
    count_visit(request)
    t = load_translations(lang)
    kind_labels = {
        'blog':    t.get('search_kind_blog', 'Blog'),
        'project': t.get('search_kind_project', 'Projekt'),
        'page':    t.get('search_kind_page', 'Seite'),
        'library': _library_label(site, loc, t),
        'travel':  t.get('trav_trips_heading', 'Reiseblog'),
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
    if maintenance_active(site):
        return _maintenance_page(site, lang)
    post = _visible_post(site, pid)
    if post is None:
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
    if not blog_public(site):
        return None
    post = next((p for p in site.get('posts', []) if p.get('id') == pid), None)
    return post if post is not None and post_visible(post) else None


@public_app.route('/api/poll/vote', methods=['POST'])
def api_poll_vote():
    """Stimme zur Startseiten-Umfrage abgeben (Mitglied per Konto, Gast per Cookie).
    Erneutes Abstimmen ändert die eigene Stimme."""
    site = load_site()
    if maintenance_active(site):
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
    if maintenance_active(site) or not site['design'].get('comments_enabled'):
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
    if maintenance_active(site) or not site['design'].get('comments_enabled'):
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
    if maintenance_active(site):
        return _maintenance_page(site, lang)
    proj = next((p for p in projects_public(site) if p.get('id') == pid), None)
    if proj is None or not _has_detail(proj):
        abort(404)
    count_visit(request)
    t = load_translations(lang)
    loc = _loc_factory(lang)
    long_html = _repo_abs_links(render_md(loc(proj, 'long')), proj.get('repo_url', ''))
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
        # Liegen die Mitglieder-Dateien auf dem Server selbst, gilt zusaetzlich
        # das Gesamtlimit des Betreibers. Angezeigt wird das kleinere von beidem
        # — sonst versprechen wir Platz, den es gar nicht gibt.
        if not SMB_MOUNTED:
            room = storage_room_bytes()
            if room is not None:
                quota = min(quota, used + room)
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
    if maintenance_active(site):
        return _maintenance_page(site, detect_language(request))
    return _member_page(current_member(request), request.args.get('msg', ''))


@public_app.route('/bereich/login', methods=['POST'])
def member_login():
    ip = get_client_ip(request)
    peer = _peer_addr(request)
    email = (request.form.get('email') or '').strip().lower()
    if is_rate_limited(ip, peer):
        log.warning("Mitglieder-Login GESPERRT: '%s' von %s (zu viele Fehlversuche)",
                    email or '?', ip)
        return redirect('/bereich?msg=locked')
    password = request.form.get('password') or ''
    user = next((u for u in load_users() if u['email'] == email), None)
    if user is None or not check_password_hash(user['pw_hash'], password):
        record_failed_attempt(ip, peer)
        log.warning("Mitglieder-Login FEHLGESCHLAGEN: '%s' von %s", email or '?', ip)
        return redirect('/bereich?msg=credentials')
    clear_failed_attempts(ip, peer)
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
                    secure=_cookie_secure(), max_age=USER_SESSION_HOURS * 3600)
    log.info("Mitglieder-Login ERFOLGREICH: '%s' von %s", email, ip)
    return resp


@public_app.route('/bereich/forgot', methods=['GET', 'POST'])
def member_forgot():
    site = load_site()
    if maintenance_active(site):
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
    if maintenance_active(site):
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
    if maintenance_active(site):
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
    if maintenance_active(site):
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
    if maintenance_active(site) or not site['design'].get('contact_enabled'):
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
    if maintenance_active(site):
        return _maintenance_page(site, lang)
    form = next((f for f in _public_forms(site) if f['slug'] == slug), None)
    if form is None:
        abort(404)
    count_visit(request)
    return _render_form(form, site, lang, ok=bool(request.args.get('ok')))


@public_app.route('/formular/<slug>', methods=['POST'])
def custom_form_submit(slug: str):
    lang = detect_language(request)
    site = load_site()
    if maintenance_active(site):
        return _maintenance_page(site, lang)
    form = next((f for f in _public_forms(site) if f['slug'] == slug), None)
    if form is None:
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
    if maintenance_active(site):
        return _maintenance_page(site, lang)
    t = load_translations(lang)
    text = _loc_factory(lang)(site.get('legal', {}), kind)
    if not text.strip():
        abort(404)
    # Rechtstexte durchlaufen dieselbe Markdown-Ausgabe wie Seiten und Beiträge.
    # Reiner Fließtext bleibt dabei unverändert stehen (`nl2br` erhält die
    # Umbrüche), gegliederter Text bekommt endlich seine Überschriften.
    body_html = render_md(text, lang)
    # Bringt der Text seine eigene Hauptüberschrift mit — etwa aus einem
    # Generator-PDF —, würde die Überschrift des Templates sie doppeln.
    own_title = body_html.lstrip().startswith('<h1')
    title = t.get('legal_' + kind, kind)
    # Das Template erwartet Schriftangaben — ohne sie standen die Rechtsseiten
    # als einzige der Website in der Systemschrift statt in der eingestellten.
    font_family, font_faces = font_css(site['design'])
    return render_template('legal.html', t=t, lang=lang, site=site,
                           title=title, body_html=body_html, own_title=own_title,
                           font_family=font_family, font_faces=font_faces,
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
    if maintenance_active(site):
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
    if maintenance_active(site):
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
    if maintenance_active(site):
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
    if maintenance_active(site):
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


@public_app.route('/download/<name>')
def public_download(name: str):
    """Datei aus dem Download-Abschnitt — immer als Anhang, nie inline.

    Ausgeliefert wird ausschließlich, was im Abschnitt selbst steht: der Name
    muss in `sections.downloads` vorkommen. Ohne diese Liste wäre die Route ein
    offener Zugriff auf die ganze Dokumentenablage, in der auch die PDFs
    gesperrter Bibliothek-Einträge liegen.
    """
    site = load_site()
    if maintenance_active(site):
        abort(404)
    if not _DOC_FILE_RE.match(name or ''):
        abort(404)
    entry = next((d for d in (site.get('sections') or {}).get('downloads') or []
                  if d.get('file') == name), None)
    if entry is None:
        abort(404)
    if 'downloads' in set(site.get('hidden_sections') or []):
        abort(404)
    if 'downloads' in set(site.get('members_sections') or []) and not is_member(request):
        abort(404)
    target = safe_under(DOCS_DIR, name)
    if target is None or not target.is_file():
        abort(404)
    loc = _loc_factory(detect_language(request))
    fname = (_slugify(loc(entry, 'title')) or 'download') + Path(name).suffix
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


# ── Reiseblog (öffentlich) ────────────────────────────────────────────────────
#
# Aufbau wie die Bibliothek — Übersicht, dann Detail —, nur mit einer Ebene mehr:
# ein Reisetag ohne seine Reise hat keinen Zusammenhang. Daher /reiseblog,
# /reiseblog/<reise> und /reiseblog/<reise>/<tag>.
#
# Sichtbar ist ein Tag nur, wenn er freigegeben ist UND einen Artikel hat. Der
# Schalter allein genügt nicht: unterwegs wird ständig zwischengespeichert, und
# eine freigegebene Seite ohne Text wäre eine leere Seite mit Datum.

def _trav_article(day: dict, lang: str) -> dict:
    """Artikel in der gewünschten Sprache, sonst in der anderen.

    Eine Reise kann einsprachig geführt sein — dann steht auf der englischen
    Seite der deutsche Bericht. Das ist besser als eine leere Seite.
    """
    art = day.get('article') or {}
    want = art.get(lang) or {}
    if want.get('title') or want.get('body'):
        return want
    other = art.get('en' if lang == 'de' else 'de') or {}
    return other if (other.get('title') or other.get('body')) else want


def _trav_recap(trip: dict, lang: str) -> dict:
    """Freigegebener Rückblick in der gewünschten Sprache, sonst in der anderen.
    Leer, solange die Freigabe fehlt oder kein Text dasteht."""
    if not trip.get('recap_published'):
        return {}
    rc = trip.get('recap') or {}
    want = rc.get(lang) or {}
    if want.get('body'):
        return want
    other = rc.get('en' if lang == 'de' else 'de') or {}
    return other if other.get('body') else {}


def _trav_day_public(day: dict) -> bool:
    art = day.get('article') or {}
    return bool(day.get('published') and day.get('slug')
                and any((art.get(lg) or {}).get('title') for lg in ('de', 'en')))


def _trav_public_days(trip: dict) -> list:
    return [d for d in (trip.get('days') or []) if _trav_day_public(d)]


def _trav_public_trips(site: dict, data: dict | None = None) -> list:
    """Reisen mit mindestens einem veröffentlichten Tag.

    Leer, solange der Reiseblog in den Einstellungen nicht für die Website
    freigegeben ist — der Admin-Reiter bleibt davon unberührt.
    """
    if not site['design'].get('travel_enabled') and not preview_active():
        return []
    data = load_travel() if data is None else data
    return [t for t in (data.get('trips') or [])
            if t.get('slug') and _trav_public_days(t)]


def _trav_date(iso: str, lang: str) -> str:
    """Datum zum Anzeigen: deutsch 12.05.2027, sonst unverändert ISO."""
    if lang != 'de' or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', iso or ''):
        return iso or ''
    y, m, d = iso.split('-')
    return f'{d}.{m}.{y}'


def _trav_first_photo(day: dict) -> str:
    return next((p['url'] for p in (day.get('photos') or []) if p.get('url')), '')


def _trav_trip_view(trip: dict, lang: str) -> dict:
    """Reise als Kachel für die Übersicht."""
    days = _trav_public_days(trip)
    lead = _trav_article(days[0], lang) if days else {}
    cover = next((_trav_first_photo(d) for d in days if _trav_first_photo(d)), '')
    return {
        'slug': trip.get('slug', ''),
        'name': trip.get('name') or trip.get('destination') or trip.get('slug', ''),
        'destination': trip.get('destination') or '',
        'day_count': len(days),
        'start': _trav_date(trip.get('travel_start') or '', lang),
        'end': _trav_date(trip.get('travel_end') or '', lang),
        'image': _overlay_url(cover),
        'teaser': (_trav_recap(trip, lang).get('teaser') or lead.get('teaser') or ''),
        'members_only': bool(trip.get('members_only')),
    }


def _trav_day_view(day: dict, lang: str) -> dict:
    """Tag als Kachel für die Reise-Seite."""
    art = _trav_article(day, lang)
    return {
        'slug': day.get('slug', ''),
        'number': day.get('day_number') or 0,
        'date': _trav_date(day.get('date') or '', lang),
        'location': day.get('location') or '',
        'title': art.get('title') or '',
        'teaser': art.get('teaser') or '',
        'image': _overlay_url(_trav_first_photo(day)),
    }


def _trav_gallery(day: dict, lang: str) -> list:
    """Fotos mit Bildunterschrift.

    Die KI-Unterschriften in `article.captions` gehören zu den Fotos MIT
    Hinweis, in genau deren Reihenfolge — Fotos ohne Hinweis hat der Prompt
    übersprungen. Der Zähler läuft deshalb über alle Fotos, hochgezählt wird
    aber nur bei denen mit Hinweis. Wer stumpf über den Index der Fotoliste
    ginge, hängte die Unterschriften ans falsche Bild.
    """
    caps = (day.get('article') or {}).get('captions') or []
    other = 'en' if lang == 'de' else 'de'
    out, k = [], 0
    for p in (day.get('photos') or []):
        ai = {}
        if p.get('photo_note'):
            ai = caps[k] if k < len(caps) else {}
            k += 1
        if not p.get('url'):
            continue
        out.append({'url': _overlay_url(p['url']),
                    'caption': (p.get('caption_' + lang) or ai.get(lang)
                                or p.get('caption_' + other) or ai.get(other) or '')})
    return out


def _trav_opt_label(t: dict, group: str, value: str) -> str:
    """Deutschen Auswahlwert für die Anzeige übersetzen.

    Gespeichert und in den Prompt gereicht wird immer der deutsche Klartext —
    er ist Teil des Prompts und darf sich nicht ändern, sonst schriebe das
    Modell plötzlich über anderes Wetter. Übersetzt wird ausschließlich die
    Anzeige; ohne Eintrag in der Karte bleibt der Wert stehen. Die deutsche
    Karte ist deshalb leer: dort ist der Wert schon die Beschriftung.
    """
    return ((t.get('trav_opt_labels') or {}).get(group) or {}).get(value, value)


def _trav_prices(trip: dict) -> bool:
    """Ob Beträge öffentlich gezeigt werden dürfen — dieselbe Einstellung, die
    schon steuert, ob die KI Preise nennen darf."""
    return (trip.get('settings') or {}).get('include_prices', True) is not False


def _trav_money(amount: float, currency: str, lang: str) -> str:
    """Betrag mit Währung, deutsch mit Komma."""
    text = f'{amount:.2f}'
    if lang == 'de':
        text = text.replace('.', ',')
    return f'{text} {currency}'.strip()


def _trav_facts(day: dict, lang: str, t: dict) -> list:
    """Kurze Faktenzeile über dem Bericht: Datum, Ort, Wetter."""
    facts = [x for x in (_trav_date(day.get('date') or '', lang),
                         day.get('location') or '') if x]
    w = day.get('weather') or {}
    if w.get('mention'):
        wx = ' '.join(x for x in (
            _trav_opt_label(t, 'weather_conditions', w.get('condition') or ''),
            f"{w['temperature']} °C" if w.get('temperature') is not None else '') if x)
        if wx:
            facts.append(wx)
    return facts


def _trav_expenses(day: dict, lang: str, t: dict) -> dict:
    """Ausgaben eines Tages: Zeilen und Summe je Währung.

    Summiert wird getrennt je Währung, nicht umgerechnet — ein geratener
    Wechselkurs wäre eine erfundene Zahl in einem Bericht, der keine enthalten
    soll (dieselbe Regel wie in `travelblog.expense_total`).
    """
    rows = [{'category': _trav_opt_label(t, 'expense_categories', e.get('category') or ''),
             'description': e.get('description') or '',
             'amount': _trav_money(e['amount'], e.get('currency') or 'EUR', lang)}
            for e in (day.get('expenses') or []) if e.get('amount') is not None]
    if not rows:
        return {}
    return {'rows': rows,
            'totals': [_trav_money(v, k, lang)
                       for k, v in sorted(tb.expense_total(day).items())]}


def _trav_trip_totals(trip: dict, lang: str) -> list:
    """Ausgaben der ganzen Reise je Währung — nur aus veröffentlichten Tagen.

    Ein Entwurf darf die öffentliche Summe nicht mitbestimmen: sonst stünde
    unter der Reise ein Betrag, den kein sichtbarer Tag erklärt.
    """
    totals: dict[str, float] = {}
    for d in _trav_public_days(trip):
        for cur, val in tb.expense_total(d).items():
            totals[cur] = round(totals.get(cur, 0) + val, 2)
    return [_trav_money(v, k, lang) for k, v in sorted(totals.items())]


def _nav_travel(site: dict, loc, t: dict) -> list:
    """Navi-Eintrag des Reiseblogs (nur mit veröffentlichten Tagen)."""
    if not _trav_public_trips(site):
        return []
    return [{'href': '/reiseblog', 'label': t.get('trav_trips_heading', 'Reiseblog')}]


def _trav_locked(trip: dict, preview: bool) -> bool:
    """Mitglieder-Sperre gilt für die ganze Reise, nicht je Tag: eine Reise
    halb öffentlich zu zeigen ergäbe eine Geschichte mit Löchern."""
    return bool(trip.get('members_only')) and not preview and not is_member(request)


def _trav_head(site: dict, lang: str):
    """Gemeinsamer Kopf aller Reiseblog-Seiten."""
    t = load_translations(lang)
    loc = _loc_factory(lang)
    font_family, font_faces = font_css(site['design'])
    return t, loc, font_family, font_faces


@public_app.route('/reiseblog')
def travel_index():
    lang = detect_language(request)
    site = load_site()
    if maintenance_active(site):
        return _maintenance_page(site, lang)
    trips = _trav_public_trips(site)
    if not trips:
        abort(404)
    count_visit(request)
    t, loc, font_family, font_faces = _trav_head(site, lang)
    return render_template(
        'travel.html', t=t, lang=lang, site=site, loc=loc,
        heading=t.get('trav_trips_heading', ''),
        trips=[_trav_trip_view(tr, lang) for tr in trips],
        font_family=font_family, font_faces=font_faces,
        nav_items=(_nav_links(site, loc, t, with_travel=False)
                   if site['design'].get('show_nav', True) else []),
        meta_desc=(t.get('trav_public_intro', '') or _site_meta(site, loc)),
        year=datetime.now(timezone.utc).year)


@public_app.route('/reiseblog/<tslug>')
def travel_trip_page(tslug: str):
    lang = detect_language(request)
    site = load_site()
    if maintenance_active(site):
        return _maintenance_page(site, lang)
    trip = next((x for x in _trav_public_trips(site) if x['slug'] == tslug), None)
    if trip is None:
        abort(404)
    count_visit(request)
    t, loc, font_family, font_faces = _trav_head(site, lang)
    view = _trav_trip_view(trip, lang)
    locked = _trav_locked(trip, False)
    # Bei gesperrten Reisen nur der Anriss — derselbe Weg wie beim Tagesbericht.
    recap = _trav_recap(trip, lang)
    recap_full = _overlay_html_images(render_md(recap.get('body') or ''))
    recap_html = (('<p>' + _locked_teaser(recap_full) + '</p>')
                  if (locked and recap_full) else recap_full)
    return render_template(
        'travel_trip.html', t=t, lang=lang, site=site, loc=loc,
        heading=t.get('trav_trips_heading', ''), trip=view,
        days=[_trav_day_view(d, lang) for d in _trav_public_days(trip)],
        locked=locked, recap_title=recap.get('title') or '', recap_html=recap_html,
        recap_tags=((trip.get('recap') or {}).get('tags') or []) if recap else [],
        totals=([] if locked or not _trav_prices(trip)
                else _trav_trip_totals(trip, lang)),
        font_family=font_family, font_faces=font_faces,
        nav_items=(_nav_links(site, loc, t, with_travel=False)
                   if site['design'].get('show_nav', True) else []),
        meta_desc=(view['teaser'] or view['destination'] or _site_meta(site, loc)),
        year=datetime.now(timezone.utc).year)


def _render_travel_day(site: dict, trip: dict, day: dict, lang: str, preview: bool = False):
    t, loc, font_family, font_faces = _trav_head(site, lang)
    art = _trav_article(day, lang)
    # Geblättert wird nur über veröffentlichte Tage. In der Vorschau eines noch
    # nicht freigegebenen Tages steht er nicht in der Liste — dann entfällt die
    # Blätter-Leiste, statt auf Adressen zu zeigen, die es öffentlich nicht gibt.
    days = _trav_public_days(trip)
    idx = next((i for i, d in enumerate(days) if d.get('id') == day.get('id')), -1)
    locked = _trav_locked(trip, preview)
    full_html = _overlay_html_images(render_md(art.get('body') or ''))
    body_html = ('<p>' + _locked_teaser(full_html) + '</p>') if locked else full_html
    return render_template(
        'travel_day.html', t=t, lang=lang, site=site, loc=loc,
        trip=_trav_trip_view(trip, lang), day=_trav_day_view(day, lang),
        heading=t.get('trav_trips_heading', ''),
        title=art.get('title') or f"{t.get('trav_day', 'Tag')} {day.get('day_number')}",
        body_html=body_html, locked=locked,
        members_only=bool(trip.get('members_only')),
        facts=_trav_facts(day, lang, t),
        # „Preise nennen" gilt für den Bericht wie für die Aufstellung darunter.
        # Wer der KI verbietet, über Geld zu schreiben, will es auch nicht als
        # Tabelle auf derselben Seite stehen haben.
        expenses=({} if (locked or not _trav_prices(trip))
                  else _trav_expenses(day, lang, t)),
        gallery=([] if locked else _trav_gallery(day, lang)),
        tags=((day.get('article') or {}).get('tags') or []),
        prev_day=(_trav_day_view(days[idx - 1], lang) if idx > 0 else None),
        next_day=(_trav_day_view(days[idx + 1], lang)
                  if 0 <= idx < len(days) - 1 else None),
        font_family=font_family, font_faces=font_faces,
        nav_items=(_nav_links(site, loc, t, with_travel=False)
                   if site['design'].get('show_nav', True) else []),
        # Bewusst `body_html` (bei gesperrten Reisen der Anriss): der volle Text
        # gehört nicht in die Meta-Description, wenn die Seite gesperrt ist.
        meta_desc=(art.get('teaser') or _plain_excerpt(body_html)
                   or _site_meta(site, loc)),
        year=datetime.now(timezone.utc).year)


@public_app.route('/reiseblog/<tslug>/<dslug>')
def travel_day_page(tslug: str, dslug: str):
    lang = detect_language(request)
    site = load_site()
    if maintenance_active(site):
        return _maintenance_page(site, lang)
    trip = next((x for x in _trav_public_trips(site) if x['slug'] == tslug), None)
    day = next((d for d in _trav_public_days(trip) if d.get('slug') == dslug),
               None) if trip else None
    if day is None:
        abort(404)
    count_visit(request)
    return _render_travel_day(site, trip, day, lang)


@admin_app.route('/preview/travel/<tid>/<did>')
def admin_travel_preview(tid: str, did: str):
    """Tages-Vorschau im Admin — zeigt auch noch nicht freigegebene Tage.

    Ohne sie ließe sich vor dem Freigeben nicht sehen, wie der Bericht mit
    Fotos und Bildunterschriften tatsächlich aussieht.
    """
    err = _auth_required()
    if err:
        return err
    data = load_travel()
    trip = _trip(data, tid)
    day = _day(trip, did) if trip else None
    if day is None:
        abort(404)
    return _render_travel_day(load_site(), trip, day,
                              detect_language(request), preview=True)


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
    _serve(TrafficMeter(public_app), PUBLIC_PORT, threads=8)


def _handle_sigterm(signum, frame) -> None:
    """Sauberer Exit bei SIGTERM (HA-Supervisor-Stop/Update) — ohne eigenen Handler
    würde Python den Default-Handler laufen lassen (exit 143), worüber sich der
    Supervisor beschwert ("should trap SIGTERM ... exit with code 0"). Alle
    Hintergrund-Threads sind daemon=True (siehe unten), ein harter os._exit(0)
    ist daher sicher — Schreibzugriffe laufen über `with open(...) as f:`-Blöcke,
    die beim jeweiligen Abschluss bereits geschlossen/geflusht sind."""
    log.info("SIGTERM empfangen, beende sauber…")
    # Der Protokollpuffer schreibt nur alle paar Sekunden auf die Platte. Ohne
    # diesen letzten Anstoß fehlten nach einem Neustart genau die Meldungen, die
    # kurz davor auflaufen — also die, die den Neustart erklären.
    admin_log_buffer.flush_now()
    os._exit(0)


def _log_admin_login_banner(generated: str | None) -> None:
    """Zugangsdaten beim Start ins Protokoll schreiben (nur ohne Home Assistant).

    Das Startpasswort steht bei JEDEM Start im Protokoll, solange es nicht
    geändert wurde — Docker-Protokolle rotieren, und wer den allerersten Start
    verpasst, müsste sonst gleich wieder die Datei löschen. Nach dem Wechsel im
    Admin-Panel ist hier Ruhe.
    """
    if generated:
        log.warning("=" * 68)
        log.warning("Neue Installation — Admin-Zugang angelegt in %s", ADMIN_LOGIN_PATH)
        log.warning("  Benutzer:  admin")
        log.warning("  Passwort:  %s", generated)
        log.warning("Bitte notieren und im Admin-Panel unter Einstellungen ändern.")
        log.warning("Erscheint das unerwartet, zeigt der Datenordner ins Leere —")
        log.warning("dann Volume prüfen, BEVOR neue Inhalte angelegt werden.")
        log.warning("=" * 68)
        return
    d = load_admin_login()
    if d.get('initial'):
        log.warning("Admin-Zugang steht noch auf dem erzeugten Startpasswort. "
                    "Es steht im Protokoll des ersten Starts; ändern im Admin-Panel "
                    "unter Einstellungen → Zugang. Vergessen? %s löschen und neu starten.",
                    ADMIN_LOGIN_PATH)


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, _handle_sigterm)
    load_sessions()
    load_user_sessions()
    # Einmalig: bisherige Add-on-Optionen in die eigene settings.json übernehmen
    settings_store.migrate(load_options())
    _settings_changed()
    cfg = load_config()
    if ON_SUPERVISOR:
        if cfg.get('password') in ('', 'changeme123'):
            log.warning("Standard-Passwort aktiv — bitte in den Add-on-Optionen ändern!")
    else:
        _log_admin_login_banner(ensure_admin_login())
    upload_max = max(1, min(4096, int(cfg.get('user_upload_max_mb') or 200)))
    public_app.config['MAX_CONTENT_LENGTH'] = upload_max * 1024 * 1024
    extra_nets = cfg.get('visit_bot_nets') or []
    if extra_nets:
        vx.set_extra_bot_nets(extra_nets)
        log.info("Besucherzähler: %d zusätzliche Bot-Netze aus visit_bot_nets",
                 len(extra_nets))

    # Initialer SMB-Mount (run.sh setzt nur noch den Pfad, Zugangsdaten bleiben im Speicher)
    if SMB_MOUNTED and not storage_available():
        if remount_smb():
            log.info("SMB-Share beim Start gemountet")
        else:
            log.warning("SMB-Mount beim Start fehlgeschlagen — Dateibereich offline, "
                        "Watchdog versucht es jede Minute erneut")
    log.info("Mitglieder-Bereich: Speicher unter %s, Upload-Limit %d MB",
             userfiles_root(), upload_max)
    _limit = storage_limit_bytes()
    if _limit:
        log.info("Speicherlimit: %d MB, belegt %d MB",
                 _limit // 1048576, storage_used_bytes(refresh=True) // 1048576)

    # Aufbewahrung des Besucher-Archivs auch beim Start durchsetzen, nicht erst
    # beim nächsten Monatswechsel. Wer die Frist herunterdreht, will die alten
    # Dateien loswerden — und Home Assistant startet das Add-on nach jeder
    # Optionsänderung ohnehin neu, also greift die neue Frist sofort.
    _prune_visit_files()

    # Warnungen des letzten Laufs zurückholen — sonst steht das Protokoll im
    # Admin nach jedem Neustart auf leer, und gerade ein Neustart ist der
    # Zeitpunkt, an dem man wissen will, was vorher los war.
    admin_log_buffer.load()

    threading.Thread(target=_run_public, daemon=True).start()
    threading.Thread(target=refresh_project_stars, daemon=True).start()
    threading.Thread(target=_sensor_worker, daemon=True).start()
    threading.Thread(target=_ha_games_worker, daemon=True).start()
    threading.Thread(target=_geoip_worker, daemon=True).start()
    threading.Thread(target=_traffic_worker, daemon=True).start()
    threading.Thread(target=_smb_watchdog, daemon=True).start()
    threading.Thread(target=_dm_reminder_worker, daemon=True).start()
    threading.Thread(target=_weekly_review_worker, daemon=True).start()
    threading.Thread(target=auto_backup_loop, daemon=True).start()
    threading.Thread(target=_storage_worker, daemon=True).start()

    log.info("MyPage bereit — öffentlich: %d, Admin: %d", PUBLIC_PORT, ADMIN_PORT)
    # Acht Threads wie oeffentlich: Der Admin laedt beim Oeffnen eines Reiters
    # mehrere Endpunkte parallel, und bei vier Threads meldete Waitress dann
    # "Task queue depth is 3" — die Anfragen warteten aufeinander. Ein
    # wartender Thread kostet praktisch nur Speicher.
    _serve(admin_app, ADMIN_PORT, threads=8)
