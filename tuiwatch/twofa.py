"""Zwei-Faktor-Anmeldung (TOTP) für den direkten Login über Port 17794.

Über HA-Ingress greift sie nicht — dort hat Home Assistant bereits angemeldet.
Übernommen aus MyPage (Admin-2FA), angepasst an TUIWatch:

- TOTP nach RFC 6238 mit der Standardbibliothek (6 Stellen, 30 s, ±1 Fenster).
- 10 Backup-Codes, nur als Hash gespeichert, je einmal nutzbar.
- „Gerät merken": zufälliges Token im Cookie; gespeichert wird nur sein
  SHA-256 — eine geleakte twofa.json öffnet also kein gemerktes Gerät.
- Ablage in `<Datenordner>/twofa.json` mit Rechten 0600. Wer sich aussperrt
  (Handy weg, keine Backup-Codes), löscht diese Datei: dann gilt 2FA als aus.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import logging
import os
import secrets
import threading
import time
from urllib.parse import quote

from werkzeug.security import check_password_hash, generate_password_hash

import atomic_io

log = logging.getLogger('tuiwatch')

TOTP_STEP = 30
TOTP_DIGITS = 6
TOTP_WINDOW = 1
BACKUP_CODE_COUNT = 10
PENDING_TTL = 300           # Sekunden zwischen Passwort- und Code-Schritt
TRUST_COOKIE = 'tw_trust2fa'
PENDING_COOKIE = 'tw_pre2fa'

_lock = threading.Lock()
_path = ''
_pending: dict[str, float] = {}     # Token → Ablaufzeit (nur im Speicher)


def init(data_dir: str) -> None:
    global _path
    _path = os.path.join(data_dir, 'twofa.json')
    _pending.clear()


def _load() -> dict:
    with _lock:
        try:
            with open(_path, encoding='utf-8') as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as e:
            # Unlesbar → 2FA gilt als aus. Lieber das als ein ausgesperrter
            # Besitzer; laut loggen, damit es nicht untergeht.
            log.error("twofa.json nicht lesbar (%s) — Zwei-Faktor-Anmeldung ist AUS",
                      type(e).__name__)
            return {}


def _save(d: dict) -> None:
    with _lock:
        atomic_io.write_json(_path, d, mode=0o600, indent=2)


def enabled() -> bool:
    d = _load()
    return bool(d.get('enabled') and d.get('secret'))


def status(days: int) -> dict:
    d = _load()
    now = time.time()
    return {'enabled': bool(d.get('enabled') and d.get('secret')),
            'backup_remaining': len(d.get('backup') or []),
            'trusted_devices': sum(1 for v in (d.get('trusted') or {}).values()
                                   if now - v < days * 86400)}


# ── TOTP ──────────────────────────────────────────────────────────────────────

def new_secret() -> str:
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
    return any(secrets.compare_digest(_totp_at(secret_b32, now + w * TOTP_STEP), code)
               for w in range(-TOTP_WINDOW, TOTP_WINDOW + 1))


def otpauth_uri(secret_b32: str, account: str) -> str:
    issuer = 'TUIWatch'
    label = quote(f'{issuer}:{account}')
    return (f'otpauth://totp/{label}?secret={secret_b32}'
            f'&issuer={quote(issuer)}&digits={TOTP_DIGITS}&period={TOTP_STEP}')


def qr_svg(data: str) -> str:
    """QR-Code als Inline-SVG, lokal erzeugt — das Secret verlässt den Server nicht."""
    try:
        import qrcode
        import qrcode.image.svg as qrsvg
        img = qrcode.make(data, image_factory=qrsvg.SvgPathImage, box_size=9, border=2)
        buf = io.BytesIO()
        img.save(buf)
        return buf.getvalue().decode('utf-8')
    except Exception as e:      # noqa: BLE001 — ohne QR bleibt die manuelle Eingabe
        log.warning("QR-Code konnte nicht erzeugt werden: %s", type(e).__name__)
        return ''


# ── Einrichten / Abschalten ───────────────────────────────────────────────────

def start_setup() -> str:
    """Neues Secret vormerken; aktiv wird es erst nach bestätigtem Code."""
    secret = new_secret()
    d = _load()
    d['pending'] = secret
    _save(d)
    return secret


def confirm_setup(code: str) -> list | None:
    """Vorgemerktes Secret aktivieren. Liefert die Backup-Codes (Klartext, nur
    diese eine Anzeige) oder None bei falschem Code / fehlender Vormerkung."""
    d = _load()
    pending = d.get('pending') or ''
    if not pending or not totp_verify(pending, code):
        return None
    plain = ['-'.join(secrets.token_hex(2) for _ in range(2)) for _ in range(BACKUP_CODE_COUNT)]
    _save({'enabled': True, 'secret': pending,
           'backup': [generate_password_hash(c) for c in plain], 'trusted': {}})
    return plain


def check_code(code: str) -> bool:
    """TOTP- oder Backup-Code des aktiven Secrets. Backup-Codes werden verbraucht."""
    d = _load()
    if totp_verify(d.get('secret') or '', code):
        return True
    code = (code or '').strip().lower()
    if not code:
        return False
    hashes = list(d.get('backup') or [])
    for i, h in enumerate(hashes):
        if check_password_hash(h, code):
            hashes.pop(i)
            d['backup'] = hashes
            _save(d)
            return True
    return False


def disable() -> None:
    _save({'enabled': False})


# ── Zwischenschritt nach dem Passwort ─────────────────────────────────────────

def pending_new() -> str:
    now = time.time()
    for k in [k for k, exp in _pending.items() if exp < now]:
        _pending.pop(k, None)
    token = secrets.token_hex(32)
    _pending[token] = now + PENDING_TTL
    return token


def pending_valid(token: str | None) -> bool:
    exp = _pending.get(token or '')
    if exp is None:
        return False
    if time.time() > exp:
        _pending.pop(token, None)
        return False
    return True


def pending_drop(token: str | None) -> None:
    _pending.pop(token or '', None)


# ── Gemerkte Geräte ───────────────────────────────────────────────────────────

def _h(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


MAX_TRUST_DAYS = 90     # Obergrenze der Einstellung, zugleich Aufräumgrenze


def trust_device() -> str:
    """Neues Geräte-Token anlegen; zurück kommt der Klartext für das Cookie.
    Gespeichert wird der Anlegezeitpunkt, nicht das Ablaufdatum — so gilt eine
    später verkürzte Einstellung sofort auch für schon gemerkte Geräte."""
    token = secrets.token_hex(32)
    d = _load()
    now = time.time()
    trusted = {k: v for k, v in (d.get('trusted') or {}).items()
               if now - v < MAX_TRUST_DAYS * 86400}
    trusted[_h(token)] = now
    d['trusted'] = trusted
    _save(d)
    return token


def device_trusted(token: str | None, days: int) -> bool:
    """Gemerktes Gerät, gemessen an der aktuellen Einstellung `days` (0 = aus)."""
    if not token or days <= 0:
        return False
    created = (_load().get('trusted') or {}).get(_h(token))
    return bool(created) and time.time() - created < days * 86400


def forget_devices() -> None:
    d = _load()
    d['trusted'] = {}
    _save(d)
