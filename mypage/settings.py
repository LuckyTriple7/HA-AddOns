"""Einstellungen aus der Oberfläche — settings.json statt Add-on-Optionen.

Bis Version 0.10.46 kamen alle Einstellungen aus `/data/options.json`, also aus
der Home-Assistant-Konfiguration. Das hatte zwei Nachteile: ohne Home Assistant
(Standalone unter Docker) gab es dafür keine Oberfläche, und Tokens sowie
Passwörter lagen im Klartext in jedem Backup.

Dieses Modul hält die Einstellungen stattdessen in `settings.json` im Datenordner
und verschlüsselt die geheimen Felder mit einem eigenen Fernet-Schlüssel
(`settings.key`, wie `dm.key` bei den Direktnachrichten). In der HA-Konfiguration
bleiben nur noch Benutzername, Passwort und Sitzungsdauer — der Notzugang, falls
man sich über die Oberfläche aussperrt.

Vorrang beim Lesen: Standardwerte < options.json < settings.json.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading

log = logging.getLogger('mypage')

try:
    from cryptography.fernet import Fernet, InvalidToken
    _HAS_CRYPTO = True
except Exception:  # Bibliothek fehlt → geheime Felder bleiben ungesetzt
    _HAS_CRYPTO = False

# Präfix der verschlüsselten Werte in settings.json. Ein Wert ohne Präfix ist
# Klartext (z. B. aus einer von Hand bearbeiteten Datei) und wird beim nächsten
# Speichern automatisch verschlüsselt.
ENC_PREFIX = 'enc:'

# Diese Felder verwaltet weiterhin Home Assistant über die Add-on-Optionen.
# Sie dürfen niemals in settings.json landen, sonst wäre der Notzugang weg.
LOCKED_KEYS = ('username', 'password', 'session_hours')

# Feldbeschreibung: key -> (typ, standard, extra)
#   str    extra = Maximallänge
#   int    extra = (min, max)
#   bool   extra = None
#   list   extra = (Maximalzahl, Regex je Eintrag)
#   choice extra = Tupel erlaubter Werte
FIELDS: dict = {
    # Benachrichtigungen
    'ha_notify':          ('bool',   True,  None),
    'telegram_bot_token': ('str',    '',    200),
    'telegram_chat_id':   ('str',    '',    64),
    # Mailversand
    'smtp_host':          ('str',    '',    200),
    'smtp_port':          ('int',    587,   (1, 65535)),
    'smtp_user':          ('str',    '',    200),
    'smtp_password':      ('str',    '',    200),
    'smtp_from':          ('str',    '',    200),
    'smtp_to':            ('str',    '',    400),
    'smtp_tls':           ('bool',   True,  None),
    # Dienste
    'github_token':       ('str',    '',    200),
    'translate_email':    ('str',    '',    200),
    # Besucherzähler und Statistik
    'visit_log_max':      ('int',    500,   (50, 10000)),
    'visit_file_log':     ('bool',   False, None),
    'visit_file_keep':    ('int',    1,     (0, 120)),
    'visit_bot_nets':     ('list',   [],    (100, r'^[0-9a-fA-F:.]{2,45}(/\d{1,3})?$')),
    'user_journal_max':   ('int',    100,   (20, 1000)),
    'geoip_offline':      ('bool',   True,  None),
    # Mitgliederbereich und Backup
    'user_upload_max_mb': ('int',    200,   (1, 4096)),
    'auto_backup_keep':   ('int',    7,     (0, 60)),
    # SMB-Speicher für Mitglieder-Dateien
    'smb_server':         ('str',    '',    200),
    'smb_share':          ('str',    '',    200),
    'smb_user':           ('str',    '',    200),
    'smb_password':       ('str',    '',    200),
    # KI (Google Gemini)
    'gemini_api_key':     ('str',    '',    200),
    'gemini_billing_key': ('str',    '',    200),
    'gemini_image_model': ('choice', 'gemini-3.1-flash-image',
                           ('gemini-3.1-flash-image', 'gemini-3.1-flash-lite-image',
                            'gemini-3-pro-image', 'gemini-2.5-flash-image')),
    'gemini_image_ratio': ('choice', '16:9',
                           ('16:9', '3:2', '4:3', '1:1', '3:4', '2:3', '9:16', '21:9')),
}

# Verschlüsselt gespeichert und nie an den Browser zurückgegeben.
SECRET_KEYS = frozenset({
    'telegram_bot_token', 'smtp_password', 'github_token',
    'smb_password', 'gemini_api_key', 'gemini_billing_key',
})

# SMB-Felder: greifen sofort, wenn der Mountpunkt schon existiert (Remount).
# War beim Start kein SMB konfiguriert, fehlt der Mountpunkt — dann meldet die
# Oberfläche, dass ein Neustart des Add-ons nötig ist.
SMB_KEYS = frozenset({'smb_server', 'smb_share', 'smb_user', 'smb_password'})

_lock = threading.Lock()
_path = ''
_key_path = ''
_fernet = None
_cache: dict = {}
_cache_mtime = -1.0


def init(data_dir: str) -> None:
    """Pfade festlegen. Muss einmal beim Start aufgerufen werden."""
    global _path, _key_path
    _path = os.path.join(data_dir, 'settings.json')
    _key_path = os.path.join(data_dir, 'settings.key')


def path() -> str:
    return _path


def reset_cache() -> None:
    """Cache und Schlüssel verwerfen — nach einem Restore kann beides neu sein."""
    global _cache, _cache_mtime, _fernet
    with _lock:
        _cache, _cache_mtime, _fernet = {}, -1.0, None


def _get_fernet():
    global _fernet
    if _fernet is not None:
        return _fernet
    if not _HAS_CRYPTO or not _key_path:
        return None
    try:
        if os.path.exists(_key_path):
            with open(_key_path, 'rb') as f:
                key = f.read().strip()
        else:
            key = Fernet.generate_key()
            with open(_key_path, 'wb') as f:
                f.write(key)
            try:
                os.chmod(_key_path, 0o600)
            except OSError:
                pass
            log.info("Schlüssel für die Einstellungen neu erzeugt")
        _fernet = Fernet(key)
        return _fernet
    except Exception as e:
        log.warning("Schlüssel für die Einstellungen nicht nutzbar: %s", e)
        return None


def _encrypt(value: str) -> str:
    if not value:
        return ''
    f = _get_fernet()
    if f is None:
        # Ohne Verschlüsselung lieber gar nicht speichern, als den Token im
        # Klartext in den Datenordner (und damit ins Backup) zu schreiben.
        log.warning("Geheimes Feld nicht gespeichert — Verschlüsselung nicht verfügbar")
        return ''
    return ENC_PREFIX + f.encrypt(value.encode('utf-8')).decode('ascii')


def _decrypt(value: str) -> str:
    if not isinstance(value, str) or not value.startswith(ENC_PREFIX):
        return value if isinstance(value, str) else ''
    f = _get_fernet()
    if f is None:
        return ''
    try:
        return f.decrypt(value[len(ENC_PREFIX):].encode('ascii')).decode('utf-8')
    except (InvalidToken, ValueError):
        # Passiert, wenn settings.json aus einem Backup kommt, settings.key aber
        # nicht — dann ist der Wert verloren und muss neu eingetragen werden.
        log.warning("Geheimes Feld konnte nicht entschlüsselt werden (falscher Schlüssel?)")
        return ''


def _read_raw() -> dict:
    """settings.json roh lesen (Geheimes noch verschlüsselt), mit mtime-Cache."""
    global _cache, _cache_mtime
    if not _path:
        return {}
    try:
        mtime = os.path.getmtime(_path)
    except OSError:
        return {}
    if mtime != _cache_mtime:
        try:
            with open(_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            _cache = data if isinstance(data, dict) else {}
            _cache_mtime = mtime
        except Exception as e:
            log.warning("settings.json nicht lesbar: %s", e)
            return _cache or {}
    return _cache


def load() -> dict:
    """Alle gesetzten Einstellungen, geheime Felder entschlüsselt."""
    out = {}
    for key, value in _read_raw().items():
        if key not in FIELDS:
            continue
        out[key] = _decrypt(value) if key in SECRET_KEYS else value
    return out


def exists() -> bool:
    return bool(_path) and os.path.exists(_path)


def coerce(key: str, value):
    """Einen Wert auf den Typ des Feldes bringen. None = ungültig, ignorieren."""
    spec = FIELDS.get(key)
    if spec is None:
        return None
    kind, default, extra = spec
    if kind == 'bool':
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ('1', 'true', 'yes', 'on')
        return bool(value)
    if kind == 'int':
        try:
            n = int(str(value).strip())
        except (TypeError, ValueError):
            return None
        lo, hi = extra
        return max(lo, min(hi, n))
    if kind == 'choice':
        v = str(value or '').strip()
        return v if v in extra else default
    if kind == 'list':
        if isinstance(value, str):
            value = [p for p in re.split(r'[\s,;]+', value) if p]
        if not isinstance(value, list):
            return None
        limit, pattern = extra
        rx = re.compile(pattern)
        return [str(v).strip() for v in value[:limit] if rx.match(str(v).strip())]
    v = str(value if value is not None else '').strip()
    return v[:extra]


def save(values: dict, clear=()) -> list:
    """Einstellungen schreiben. Gibt die tatsächlich geänderten Schlüssel zurück.

    `values` enthält nur Felder, die der Benutzer angefasst hat; geheime Felder
    ohne neuen Wert bleiben unverändert. `clear` leert einzelne Felder gezielt.
    """
    with _lock:
        raw = dict(_read_raw())
        changed = []
        for key in clear or ():
            if key in FIELDS and raw.get(key) not in (None, '', []):
                raw[key] = '' if FIELDS[key][0] in ('str', 'choice') else FIELDS[key][1]
                changed.append(key)
        for key, value in (values or {}).items():
            if key not in FIELDS or key in LOCKED_KEYS:
                continue
            new = coerce(key, value)
            if new is None:
                continue
            if key in SECRET_KEYS:
                if new == '':
                    continue          # leeres Feld heißt „unverändert lassen"
                new = _encrypt(new)
                if not new:
                    continue          # Verschlüsselung nicht möglich
            if raw.get(key) != new:
                raw[key] = new
                changed.append(key)
        if not changed:
            return []
        _write(raw)   # OSError meldet der Aufrufer als Fehler an die Oberfläche
        return changed


def _write(raw: dict) -> None:
    global _cache, _cache_mtime
    tmp = _path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(raw, f, indent=2, ensure_ascii=False)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, _path)
    _cache = raw
    try:
        _cache_mtime = os.path.getmtime(_path)
    except OSError:
        _cache_mtime = -1.0


def migrate(options: dict) -> bool:
    """Beim ersten Start die bisherigen Add-on-Optionen übernehmen.

    Läuft nur, solange settings.json fehlt. Geheime Felder werden dabei
    verschlüsselt — der Klartext bleibt in options.json stehen, bis Home
    Assistant die Optionen mit einer späteren Version aus dem Schema wirft.
    """
    if exists() or not isinstance(options, dict):
        return False
    seed = {}
    for key, value in options.items():
        if key in FIELDS and key not in LOCKED_KEYS and value not in (None, ''):
            seed[key] = value
    with _lock:
        raw = {}
        for key, value in seed.items():
            new = coerce(key, value)
            if new is None:
                continue
            raw[key] = _encrypt(new) if key in SECRET_KEYS else new
        try:
            _write(raw)
        except OSError as e:
            # Ein nicht beschreibbarer Datenordner darf den Start nicht kosten:
            # ohne settings.json gelten weiter die Werte aus options.json.
            log.warning("settings.json konnte nicht angelegt werden: %s", e)
            return False
    log.info("Einstellungen aus den Add-on-Optionen übernommen: %d Feld(er) "
             "in settings.json (geheime Felder verschlüsselt)", len(raw))
    return True


def public_view(effective: dict) -> dict:
    """Ansicht für die Oberfläche — geheime Felder nur als „gesetzt: ja/nein"."""
    out, secrets_set = {}, {}
    for key, (kind, default, _extra) in FIELDS.items():
        if key in SECRET_KEYS:
            secrets_set[key] = bool(str(effective.get(key) or '').strip())
            continue
        value = effective.get(key, default)
        out[key] = default if value is None else value
    return {'values': out, 'secrets': secrets_set,
            'crypto': _HAS_CRYPTO and _get_fernet() is not None}
