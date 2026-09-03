"""In-app settings — settings.json instead of add-on options.

SMTP and Telegram notification channels used to live in the Home Assistant
add-on options only, which meant no UI without Home Assistant (standalone
under Docker) and secrets sitting in plain text in every options.json backup.
This module holds them in settings.json in the data directory instead and
encrypts the secret fields with a Fernet key (settings.key) kept next to it.

Read precedence: defaults < options.json < settings.json. Anything already in
the add-on options keeps working unchanged; the UI simply lets it be
overridden without touching Home Assistant.

Field shape:
    key: (type, default, extra, group, label, hint)
    type  'bool' | 'int' | 'str'
    extra 'int' -> (min, max) · 'str' -> max length · else None
"""

import logging
import os
import threading

log = logging.getLogger(__name__)

try:
    from cryptography.fernet import Fernet, InvalidToken
    _HAS_CRYPTO = True
except Exception:  # library missing -> secret fields simply stay unset
    _HAS_CRYPTO = False

ENC_PREFIX = 'enc:'

GROUPS = (
    ('mail', 'mail'),
    ('telegram', 'telegram'),
)

FIELDS = {
    'smtp_host': ('str', '', 253, 'mail', 'smtp_host', ''),
    'smtp_port': ('int', 587, (1, 65535), 'mail', 'smtp_port', ''),
    'smtp_user': ('str', '', 253, 'mail', 'smtp_user', ''),
    'smtp_password': ('str', '', 500, 'mail', 'smtp_password', ''),
    'smtp_from': ('str', '', 253, 'mail', 'smtp_from', ''),
    'smtp_to': ('str', '', 253, 'mail', 'smtp_to', ''),
    'smtp_tls': ('bool', True, None, 'mail', 'smtp_tls', ''),
    'telegram_bot_token': ('str', '', 200, 'telegram', 'telegram_bot_token', ''),
    'telegram_chat_id': ('str', '', 64, 'telegram', 'telegram_chat_id', ''),
}

SECRET_KEYS = frozenset({'smtp_password', 'telegram_bot_token'})

_lock = threading.Lock()
_path = ''
_key_path = ''
_fernet = None
_cache: dict = {}
_cache_mtime = -1.0


def init(data_dir: str) -> None:
    """Set the file paths. Called once at startup."""
    global _path, _key_path
    _path = os.path.join(data_dir, 'settings.json')
    _key_path = os.path.join(data_dir, 'settings.key')
    reset_cache()


def reset_cache() -> None:
    global _cache, _cache_mtime, _fernet
    with _lock:
        _cache, _cache_mtime, _fernet = {}, -1.0, None


def crypto_available() -> bool:
    return _HAS_CRYPTO


def _get_fernet(create: bool = False):
    """Fernet instance for the key in the data directory.

    create=False (reading/decrypting) deliberately never generates a key --
    otherwise a fresh random key would appear right after a restore, and the
    real key brought back afterwards would look like "a different one" and
    get rejected. Only generated when something actually needs encrypting.
    """
    global _fernet
    if _fernet is not None:
        return _fernet
    if not _HAS_CRYPTO or not _key_path:
        return None
    try:
        if os.path.exists(_key_path):
            with open(_key_path, 'rb') as f:
                key = f.read().strip()
        elif not create:
            return None
        else:
            key = Fernet.generate_key()
            fd = os.open(_key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'wb') as f:
                f.write(key)
            log.info("generated a new key for encrypted settings")
        _fernet = Fernet(key)
        return _fernet
    except Exception as e:
        log.warning("settings encryption key unusable: %s", e)
        return None


def _encrypt(value: str) -> str:
    if not value:
        return ''
    f = _get_fernet(create=True)
    if f is None:
        # Better to not save it at all than write a token in plain text into
        # the data directory (and every backup of it).
        log.warning("secret field not saved — encryption unavailable")
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
        log.warning("secret field could not be decrypted (wrong key?)")
        return ''


def _read_raw() -> dict:
    global _cache, _cache_mtime
    if not _path:
        return {}
    try:
        mtime = os.path.getmtime(_path)
        if mtime != _cache_mtime:
            import json
            with open(_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            _cache = data if isinstance(data, dict) else {}
            _cache_mtime = mtime
    except FileNotFoundError:
        return _cache or {}
    except Exception as e:
        log.warning("settings.json unreadable: %s", e)
        return _cache or {}
    return _cache


def load() -> dict:
    """Every set field, secrets decrypted."""
    out = {}
    for key, value in _read_raw().items():
        if key not in FIELDS:
            continue
        out[key] = _decrypt(value) if key in SECRET_KEYS else value
    return out


def coerce(key: str, value):
    """Bring a value to the field's type. None = invalid, ignore it."""
    spec = FIELDS.get(key)
    if spec is None:
        return None
    kind, default, extra = spec[0], spec[1], spec[2]
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
    v = str(value if value is not None else '').strip()
    return v[:extra]


def save(values: dict) -> list:
    """Write settings. Returns the keys that actually changed.

    `values` holds only the fields the user touched; a secret field left
    empty means "leave unchanged", not "clear it".
    """
    with _lock:
        raw = dict(_read_raw())
        changed = []
        for key, value in (values or {}).items():
            if key not in FIELDS:
                continue
            new = coerce(key, value)
            if new is None:
                continue
            if key in SECRET_KEYS:
                if new == '':
                    continue
                new = _encrypt(new)
                if not new:
                    continue
            if raw.get(key) != new:
                raw[key] = new
                changed.append(key)
        if not changed:
            return []
        _write(raw)
        return changed


def _write(raw: dict) -> None:
    global _cache, _cache_mtime
    import json
    folder = os.path.dirname(_path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = _path + '.tmp'
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(raw, f, indent=2, ensure_ascii=False)
    os.replace(tmp, _path)
    _cache = raw
    try:
        _cache_mtime = os.path.getmtime(_path)
    except OSError:
        _cache_mtime = -1.0


def effective(options_cfg: dict) -> dict:
    """Merge: field defaults < add-on options < settings.json."""
    out = {key: spec[1] for key, spec in FIELDS.items()}
    for key in FIELDS:
        if options_cfg.get(key) not in (None, ''):
            out[key] = options_cfg[key]
    out.update(load())
    return out


def public_view(options_cfg: dict = None) -> dict:
    """What the UI gets back: secrets replaced by whether one is set, never
    the value itself. Non-secret fields fall back to the add-on options, so a
    value set there before this UI existed still shows up as active."""
    options_cfg = options_cfg or {}
    raw = _read_raw()
    out = {}
    for key, spec in FIELDS.items():
        if key in SECRET_KEYS:
            out[key] = ''
            out[key + '_set'] = bool(raw.get(key)) or bool(options_cfg.get(key))
        else:
            if key in raw:
                out[key] = raw[key]
            elif options_cfg.get(key) not in (None, ''):
                out[key] = options_cfg[key]
            else:
                out[key] = spec[1]
    return out
