import asyncio
import hashlib
import json
import logging
import os
import re
import secrets
import shutil
import sqlite3
import time
from collections import defaultdict
from datetime import datetime
from ipaddress import ip_address
from pathlib import Path

import httpx
import uvicorn
import yaml
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] [%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S', force=True)
log = logging.getLogger(__name__)

UVICORN_LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {"format": "[%(levelname)s] [%(asctime)s] %(message)s", "datefmt": "%Y-%m-%d %H:%M:%S"},
    },
    "handlers": {
        "default": {"formatter": "default", "class": "logging.StreamHandler", "stream": "ext://sys.stdout"},
    },
    "loggers": {
        "uvicorn":        {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.error":  {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["default"], "level": "INFO", "propagate": False},
    },
}

app        = FastAPI()
admin_app  = FastAPI()
ingress_app = FastAPI()

_ha_status_cache: dict = {"reachable": False, "version": None, "since": None, "checked_at": None}

# ── Rate limiting ─────────────────────────────────────────────────────────────
_failed_attempts: dict[str, list[float]] = defaultdict(list)
_blocked_ips:     dict[str, float]       = {}
RATE_LIMIT_MAX    = 5
RATE_LIMIT_WINDOW = 10 * 60   # 10 min Fenster
RATE_LIMIT_BLOCK  = 15 * 60   # 15 min Sperre


def is_rate_limited(ip: str) -> bool:
    now = time.time()
    if ip in _blocked_ips:
        if now < _blocked_ips[ip]:
            return True
        del _blocked_ips[ip]
    _failed_attempts[ip] = [t for t in _failed_attempts[ip] if now - t < RATE_LIMIT_WINDOW]
    return False


def record_failed_attempt(ip: str):
    now = time.time()
    _failed_attempts[ip].append(now)
    recent = [t for t in _failed_attempts[ip] if now - t < RATE_LIMIT_WINDOW]
    _failed_attempts[ip] = recent
    if len(recent) >= RATE_LIMIT_MAX:
        _blocked_ips[ip] = now + RATE_LIMIT_BLOCK
        log.warning("IP '%s' für %d Minuten gesperrt (zu viele fehlgeschlagene Logins)", ip, RATE_LIMIT_BLOCK // 60)


def clear_failed_attempts(ip: str):
    _failed_attempts.pop(ip, None)
    _blocked_ips.pop(ip, None)


def _is_private_ip_str(ip: str) -> bool:
    try:
        addr = ip_address(ip)
        return addr.is_private or addr.is_loopback
    except ValueError:
        return False


def _admin_get_rate_limits():
    now = time.time()
    to_remove = [ip for ip, until in _blocked_ips.items() if now >= until]
    for ip in to_remove:
        del _blocked_ips[ip]
    blocked = []
    for ip, until in sorted(_blocked_ips.items(), key=lambda x: x[1]):
        remaining = max(0, int(until - now))
        attempts  = len([t for t in _failed_attempts.get(ip, []) if now - t < RATE_LIMIT_WINDOW])
        blocked.append({"ip": ip, "remaining_seconds": remaining, "attempts": attempts})
    return JSONResponse({"blocked": blocked})


async def _admin_unblock_ip(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    ip = (body.get("ip") or "").strip()
    if not ip:
        return JSONResponse({"error": "ip_empty"}, status_code=400)
    clear_failed_attempts(ip)
    log.info("Admin: IP '%s' manuell entsperrt", ip)
    return JSONResponse({"success": True})

DATA_DIR = Path("/data")
CONFIG_DIR = Path("/config/addons_config/cardboard")
OPTIONS_FILE = DATA_DIR / "options.json"
STATIC_DIR = Path("/app/static")
DB_PATH = DATA_DIR / "cardboard.db"
COOKIE_NAME       = "cb_session"
ADMIN_COOKIE_NAME = "cb_admin"
ADMIN_SESSION_AGE = 4 * 3600  # 4 Stunden

# SUPERVISOR_TOKEN wird vom Supervisor automatisch injiziert (homeassistant_api: true) —
# kein manuell eingetragener ha_token mehr nötig. HA-API läuft über den Supervisor-Proxy.
SUPERVISOR_TOKEN    = os.environ.get("SUPERVISOR_TOKEN", "")
HA_API_BASE         = "http://supervisor/core/api"
SESSION_SECRET_FILE = CONFIG_DIR / ".session_secret"


def session_max_age() -> int:
    try:
        days = int(load_options().get("session_lifetime", 7))
        return max(1, days) * 24 * 3600
    except Exception:
        return 7 * 24 * 3600


# ── Config & Users ────────────────────────────────────────────────────────────

def load_options() -> dict:
    with open(OPTIONS_FILE) as f:
        return json.load(f)


def load_users() -> list:
    users_file = CONFIG_DIR / "users.yaml"
    if not users_file.exists():
        return []
    with open(users_file, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("users", []) if data else []


def user_must_change_password(username: str) -> bool:
    users = load_users()
    user = next((u for u in users if (u.get("username") or "").lower() == username), None)
    return bool(user and user.get("force_pw_change"))


def validate_new_password(password: str, opts: dict) -> str | None:
    min_len = max(1, int(opts.get("pw_min_length") or 8))
    if len(password) < min_len:
        return "password_too_short"
    if opts.get("pw_require_special", True):
        if not any(c.isdigit() or not c.isalnum() for c in password):
            return "password_no_special"
    return None


def write_users(yaml_data: dict):
    """Schreibt users.yaml atomar (via tmp-Datei)."""
    users_file = CONFIG_DIR / "users.yaml"
    tmp = users_file.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.dump(yaml_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    tmp.replace(users_file)


_session_secret_cache: str | None = None


def get_session_secret() -> str:
    """Stabiles Signing-Secret für Session-Cookies, persistiert in /config (überlebt
    Neustarts). Früher wurde dafür ha_token genutzt — seit der Umstellung auf den
    Supervisor-Token gibt es keinen manuellen Token mehr."""
    global _session_secret_cache
    if _session_secret_cache:
        return _session_secret_cache
    try:
        s = SESSION_SECRET_FILE.read_text(encoding="utf-8").strip() if SESSION_SECRET_FILE.exists() else ""
        if not s:
            s = secrets.token_hex(32)
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            SESSION_SECRET_FILE.write_text(s, encoding="utf-8")
            try:
                os.chmod(SESSION_SECRET_FILE, 0o600)
            except OSError:
                pass
    except OSError:
        # /config nicht beschreibbar: prozesslokales Secret (Sessions überleben keinen Neustart)
        s = secrets.token_hex(32)
    _session_secret_cache = s
    return s


def get_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_session_secret())


_SAFE_PATH_PART = re.compile(r'^[a-zA-Z0-9_\-][a-zA-Z0-9._\-]{0,254}$')

def safe_child(base: Path, *parts: str) -> Path | None:
    """Gibt einen Pfad nur zurück wenn er innerhalb von base liegt (verhindert Path Traversal)."""
    try:
        # Regex-validate each part before use — CodeQL-recognized sanitizer pattern
        safe_parts = []
        for part in parts:
            m = _SAFE_PATH_PART.match(str(part))
            if not m:
                return None
            safe_parts.append(m.group(0))
        resolved = base.joinpath(*safe_parts).resolve()
        base_resolved = base.resolve()
        if str(resolved).startswith(str(base_resolved) + os.sep) or str(resolved) == str(base_resolved):
            return resolved
    except Exception:
        pass
    return None


# ── Admin auth ────────────────────────────────────────────────────────────────

def admin_password_set() -> bool:
    return bool((load_options().get("admin_password") or "").strip())


def get_admin_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_session_secret() + "-admin")


def get_admin_session(request: Request) -> bool:
    token = request.cookies.get(ADMIN_COOKIE_NAME)
    if not token:
        return False
    try:
        data = get_admin_serializer().loads(token, max_age=ADMIN_SESSION_AGE)
        return data.get("admin") is True
    except (BadSignature, SignatureExpired):
        return False


def admin_panel_allowed(request: Request) -> bool:
    """Über HA-Ingress hat der Supervisor den Benutzer bereits authentifiziert →
    kein Admin-Passwort nötig (wie MyPage). Der Ingress-Port ist nicht im LAN
    erreichbar, daher kann x-ingress-path nicht von außen gefälscht werden.
    Ohne gesetztes Passwort ist auch der LAN-Zugang frei; sonst Passwort-Session."""
    if _is_ingress(request):
        return True
    if not admin_password_set():
        return is_private_ip(request)
    return get_admin_session(request)


def _is_ingress(request: Request) -> bool:
    return request.headers.get("x-ingress-path") is not None


def validate_username(username: str) -> str | None:
    if not username:
        return "username_empty"
    if not re.match(r'^[a-z0-9_\-]{1,32}$', username):
        return "username_invalid"
    return None


# ── Database ──────────────────────────────────────────────────────────────────

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS login_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT    NOT NULL,
                username    TEXT    NOT NULL,
                success     INTEGER NOT NULL,
                ip_address  TEXT,
                user_agent  TEXT
            )
        """)
        try:
            conn.execute("ALTER TABLE login_events ADD COLUMN user_agent TEXT")
        except Exception:
            pass
        conn.commit()


def _parse_user_agent(ua: str) -> str:
    if not ua:
        return "—"
    u = ua.lower()
    if "edg/" in u or "edghtml" in u:
        browser = "Edge"
    elif "opr/" in u or "opera" in u:
        browser = "Opera"
    elif "chrome/" in u:
        m = re.search(r"chrome/(\d+)", u)
        browser = f"Chrome {m.group(1)}" if m else "Chrome"
    elif "firefox/" in u:
        m = re.search(r"firefox/(\d+)", u)
        browser = f"Firefox {m.group(1)}" if m else "Firefox"
    elif "safari/" in u:
        browser = "Safari"
    else:
        browser = "?"
    if "android" in u:
        os = "Android"
    elif "iphone" in u:
        os = "iPhone"
    elif "ipad" in u:
        os = "iPad"
    elif "windows" in u:
        os = "Windows"
    elif "mac os" in u:
        os = "macOS"
    elif "linux" in u:
        os = "Linux"
    else:
        os = "?"
    return f"{browser} · {os}"


def db_log_login(username: str, success: bool, ip: str | None, user_agent: str | None = None):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO login_events (timestamp, username, success, ip_address, user_agent) VALUES (?, ?, ?, ?, ?)",
            (datetime.utcnow().isoformat(timespec="seconds"), username, int(success), ip, user_agent),
        )
        conn.commit()


# ── Auth helpers ──────────────────────────────────────────────────────────────

def is_https(request: Request) -> bool:
    return (
        request.url.scheme == "https"
        or request.headers.get("x-forwarded-proto", "").lower() == "https"
    )


_PBKDF2_ITERS = 260_000

def _hash_password(password: str) -> str:
    """Erstellt einen PBKDF2-HMAC-SHA256-Hash mit zufälligem Salt."""
    salt = os.urandom(16)
    h = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, _PBKDF2_ITERS)
    return f"pbkdf2:{salt.hex()}:{h.hex()}"

def check_password(plain: str, stored: str) -> bool:
    """Unterstützt PBKDF2-Hashes (neu), SHA-256-Hashes (legacy) und Klartext."""
    if stored.startswith('pbkdf2:'):
        try:
            _, salt_hex, hash_hex = stored.split(':', 2)
            salt = bytes.fromhex(salt_hex)
            h = hashlib.pbkdf2_hmac('sha256', plain.encode('utf-8'), salt, _PBKDF2_ITERS)
            return h.hex() == hash_hex
        except Exception:
            return False
    if len(stored) == 64 and all(c in "0123456789abcdefABCDEF" for c in stored):
        return hashlib.sha256(plain.encode()).hexdigest().lower() == stored.lower()
    return plain == stored


def get_current_user(request: Request) -> str | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        data = get_serializer().loads(token, max_age=session_max_age())
        return data.get("username")
    except (BadSignature, SignatureExpired):
        return None


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


# ── PWA Icon Generator ────────────────────────────────────────────────────────

def _generate_icon_png(size: int) -> bytes:
    """Erzeugt ein CardBoard-Icon als PNG (pure stdlib, keine Dependencies)."""
    import struct, zlib

    BG  = bytes([17,  24,  39])   # #111827
    SRF = bytes([31,  41,  55])   # #1f2937
    ACC = bytes([59,  130, 246])  # #3b82f6
    DOC = bytes([229, 231, 235])  # #e5e7eb
    LN  = bytes([55,  65,  81])   # #374151

    px = bytearray(BG * (size * size))

    def set_px(x, y, c):
        if 0 <= x < size and 0 <= y < size:
            i = (y * size + x) * 3
            px[i:i + 3] = c

    def fill_rect(x0, y0, x1, y1, c):
        for y in range(max(0, y0), min(size, y1)):
            xs, xe = max(0, x0), min(size, x1)
            if xe > xs:
                i = (y * size + xs) * 3
                px[i:i + (xe - xs) * 3] = c * (xe - xs)

    def fill_circle(cx, cy, r, c):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if dx * dx + dy * dy <= r * r:
                    set_px(cx + dx, cy + dy, c)

    def rounded_rect(x0, y0, x1, y1, r, c):
        fill_rect(x0 + r, y0, x1 - r, y1, c)
        fill_rect(x0, y0 + r, x1, y1 - r, c)
        fill_circle(x0 + r,     y0 + r,     r, c)
        fill_circle(x1 - r - 1, y0 + r,     r, c)
        fill_circle(x0 + r,     y1 - r - 1, r, c)
        fill_circle(x1 - r - 1, y1 - r - 1, r, c)

    s = size / 512
    rounded_rect(int(32*s),  int(32*s),  int(480*s), int(480*s), int(48*s), SRF)
    rounded_rect(int(128*s), int(152*s), int(384*s), int(424*s), int(16*s), DOC)
    rounded_rect(int(192*s), int(112*s), int(320*s), int(196*s), int(16*s), ACC)
    for y_b in [234, 272, 310]:
        fill_rect(int(160*s), int(y_b*s), int(352*s), int((y_b + 20)*s), LN)
    fill_rect(int(160*s), int(348*s), int(272*s), int(368*s), LN)

    raw = bytearray()
    for y in range(size):
        raw += b'\x00'
        raw += px[y * size * 3:(y + 1) * size * 3]

    def chunk(tag, data):
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', crc)

    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(bytes(raw), 6))
            + chunk(b'IEND', b''))


def init_pwa():
    for size in (192, 512):
        path = STATIC_DIR / f"icon-{size}.png"
        if not path.exists():
            log.info("PWA: Generiere icon-%d.png …", size)
            path.write_bytes(_generate_icon_png(size))


# ── Main app ──────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return RedirectResponse("/view")


@app.get("/sw.js")
async def service_worker():
    content = (STATIC_DIR / "sw.js").read_text(encoding="utf-8")
    return Response(content, media_type="application/javascript")


@app.get("/manifest.json")
async def pwa_manifest():
    content = (STATIC_DIR / "manifest.json").read_text(encoding="utf-8")
    return Response(content, media_type="application/manifest+json")


@app.get("/api/public/config")
async def public_config():
    """Öffentlicher Endpunkt für die Login-Seite — kein Auth erforderlich."""
    opts = load_options()
    return {"login_message": opts.get("login_message") or ""}


@app.get("/api/public/ha-status")
async def public_ha_status():
    """HA-Erreichbarkeit und Version — kein Auth erforderlich, Cache 30 s."""
    global _ha_status_cache
    now = datetime.utcnow()
    last_check = _ha_status_cache.get("checked_at")
    if last_check is None or (now - last_check).total_seconds() > 30:
        opts = load_options()
        uptime_entity = (opts.get("uptime_sensor") or "sensor.uptime").strip()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{HA_API_BASE}/config",
                    headers={"Authorization": f"Bearer {SUPERVISOR_TOKEN}"},
                )
                if resp.status_code == 200:
                    version = resp.json().get("version", "")
                    since = None
                    try:
                        up = await client.get(
                            f"{HA_API_BASE}/states/{uptime_entity}",
                            headers={"Authorization": f"Bearer {SUPERVISOR_TOKEN}"},
                        )
                        if up.status_code == 200:
                            state = up.json().get("state", "")
                            if state and state not in ("unavailable", "unknown", ""):
                                since = state
                    except Exception:
                        pass
                    _ha_status_cache.update({"reachable": True, "version": version, "since": since, "checked_at": now})
                else:
                    _ha_status_cache.update({"reachable": False, "checked_at": now})
        except Exception:
            _ha_status_cache.update({"reachable": False, "checked_at": now})
    return {
        "reachable":    _ha_status_cache.get("reachable", False),
        "version":      _ha_status_cache.get("version"),
        "online_since": _ha_status_cache.get("since"),
    }


async def _notify_failed_login(username: str, ip: str | None):
    opts = load_options()
    if not opts.get("notify_failed_login", True):
        return
    timestamp = datetime.utcnow().strftime("%d.%m.%Y %H:%M:%S")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{HA_API_BASE}/services/persistent_notification/create",
                headers={"Authorization": f"Bearer {SUPERVISOR_TOKEN}"},
                json={
                    "title": "⚠️ CardBoard: Login fehlgeschlagen",
                    "message": f"Benutzer: **{username}**\nIP: {ip or 'unbekannt'}\nZeit: {timestamp} UTC",
                    "notification_id": "cardboard_failed_login",
                },
            )
    except Exception:
        log.debug("HA-Benachrichtigung für fehlgeschlagenen Login konnte nicht gesendet werden")


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return (STATIC_DIR / "login.html").read_text(encoding="utf-8")


@app.post("/login")
async def do_login(request: Request):
    form = await request.form()
    username = (form.get("username") or "").strip().lower()
    password = form.get("password") or ""
    ip = client_ip(request) or "unknown"
    ua = request.headers.get("user-agent") or ""

    if is_rate_limited(ip) and not _is_private_ip_str(ip):
        log.warning("Login blockiert (Rate Limit): ip='%s'", ip)
        return RedirectResponse("/login?error=locked", status_code=303)

    users = load_users()
    user = next((u for u in users if (u.get("username") or "").lower() == username), None)

    if not user or not check_password(password, user.get("password", "")):
        record_failed_attempt(ip)
        db_log_login(username or "?", False, ip, ua)
        log.warning("Login fehlgeschlagen: user='%s' ip='%s'", username or "?", ip)
        asyncio.create_task(_notify_failed_login(username or "?", ip))
        return RedirectResponse("/login?error=1", status_code=303)

    clear_failed_attempts(ip)
    db_log_login(username, True, ip, ua)
    log.info("Login erfolgreich: user='%s' ip='%s'", username, ip)
    token = get_serializer().dumps({"username": username})
    target = "/change-password?forced=1" if user_must_change_password(username) else "/view"
    response = RedirectResponse(target, status_code=303)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=session_max_age(),
        httponly=True,
        samesite="lax",
        secure=is_https(request),
    )
    return response


@app.get("/logout")
async def logout(request: Request):
    username = get_current_user(request)
    if username:
        log.info("Logout: user='%s'", username)
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


@app.get("/change-password", response_class=HTMLResponse)
async def change_password_page(request: Request):
    if not get_current_user(request):
        return RedirectResponse("/login")
    return (STATIC_DIR / "change_password.html").read_text(encoding="utf-8")


@app.post("/api/change-password")
async def api_change_password(request: Request):
    username = get_current_user(request)
    if not username:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_request"}, status_code=400)

    old_pw  = body.get("old_password", "")
    new_pw  = body.get("new_password", "")
    conf_pw = body.get("confirm_password", "")

    if not new_pw:
        return JSONResponse({"error": "password_empty"}, status_code=400)
    if new_pw != conf_pw:
        return JSONResponse({"error": "passwords_mismatch"}, status_code=400)

    opts = load_options()
    err = validate_new_password(new_pw, opts)
    if err:
        return JSONResponse({"error": err, "pw_min_length": int(opts.get("pw_min_length") or 8)}, status_code=400)

    users_file = CONFIG_DIR / "users.yaml"
    with open(users_file, encoding="utf-8") as f:
        yaml_data = yaml.safe_load(f) or {}

    users = yaml_data.get("users", [])
    user  = next((u for u in users if (u.get("username") or "").lower() == username), None)

    if not user or not check_password(old_pw, user.get("password", "")):
        return JSONResponse({"error": "wrong_password"}, status_code=400)

    user["password"] = _hash_password(new_pw)
    was_forced = bool(user.pop("force_pw_change", False))
    write_users(yaml_data)
    log.info("Passwort für Benutzer '%s' geändert%s", username, " (initiales Passwort)" if was_forced else "")
    return JSONResponse({"success": True, "was_forced": was_forced})


@app.get("/view", response_class=HTMLResponse)
async def view_page(request: Request):
    username = get_current_user(request)
    if not username:
        return RedirectResponse("/login")
    if user_must_change_password(username):
        return RedirectResponse("/change-password?forced=1")
    return (STATIC_DIR / "view.html").read_text(encoding="utf-8")


@app.get("/api/config")
async def api_config(request: Request):
    username = get_current_user(request)
    if not username:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    opts = load_options()
    users = load_users()
    user = next((u for u in users if (u.get("username") or "").lower() == username), None)
    templates = (user or {}).get("templates", [])
    display_name = (user or {}).get("display_name") or username
    lang = (user or {}).get("lang", "de").lower()
    if lang not in ("de", "en"):
        lang = "de"
    max_cards    = max(1, int(opts.get("max_cards") or 3))
    cards_per_row = max(1, min(6, int(opts.get("cards_per_row") or 3)))

    return {
        "username":         username,
        "display_name":     display_name,
        "lang":             lang,
        "refresh_interval": opts.get("refresh_interval", 30),
        "max_cards":        max_cards,
        "cards_per_row":    cards_per_row,
        "card_count":       min(len(templates), max_cards),
        "pw_min_length":     int(opts.get("pw_min_length") or 8),
        "pw_require_special": bool(opts.get("pw_require_special", True)),
        "force_pw_change":   user_must_change_password(username),
    }


def parse_template_entry(entry) -> tuple[str, str | None]:
    """Unterstützt String-Format und Dict-Format mit optionalem Titel."""
    if isinstance(entry, dict):
        return entry.get("file", ""), entry.get("title") or None
    return str(entry), None


@app.get("/api/render")
async def api_render(request: Request):
    username = get_current_user(request)
    if not username:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    opts = load_options()
    users = load_users()
    user = next((u for u in users if (u.get("username") or "").lower() == username), None)

    if not user:
        return JSONResponse({"error": "Benutzer nicht gefunden"}, status_code=404)

    max_cards = max(1, int(opts.get("max_cards") or 3))
    templates = (user.get("templates") or [])[:max_cards]

    cards = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for entry in templates:
            tpl_name, title = parse_template_entry(entry)
            tpl_path = safe_child(CONFIG_DIR, username, tpl_name)
            if not tpl_path or not tpl_path.exists():
                cards.append({"title": title, "content": f"⚠️ Template nicht gefunden: `{tpl_name}`"})
                continue

            content = tpl_path.read_text(encoding="utf-8")
            try:
                resp = await client.post(
                    f"{HA_API_BASE}/template",
                    headers={
                        "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
                        "Content-Type": "application/json",
                    },
                    json={"template": content},
                )
                if resp.status_code == 200:
                    cards.append({"title": title, "content": resp.text})
                else:
                    cards.append({"title": title, "content": f"⚠️ HA Fehler {resp.status_code}:\n```\n{resp.text[:500]}\n```"})
            except httpx.TimeoutException:
                cards.append({"title": title, "content": "⚠️ Zeitüberschreitung beim Abrufen der HA-Daten"})
            except Exception:
                log.exception("Fehler beim Rendern von %s", tpl_name)
                cards.append({"title": title, "content": "⚠️ Verbindungsfehler"})

    return {"cards": cards}


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── Admin app (interner Port, nur LAN) ───────────────────────────────────────

def is_private_ip(request: Request) -> bool:
    """Nur private/Loopback-IPs dürfen die Admin-API nutzen."""
    host = request.client.host if request.client else ""
    try:
        addr = ip_address(host)
        return addr.is_private or addr.is_loopback
    except ValueError:
        return False


def admin_allowed(request: Request) -> bool:
    if is_private_ip(request):
        return True
    ip = request.client.host if request.client else "?"
    log.warning("Admin-API Zugriff verweigert: ip='%s' path='%s'", ip, request.url.path)
    return False


@admin_app.get("/api/admin/stats")
async def admin_stats(request: Request):
    if not admin_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)

    with sqlite3.connect(DB_PATH) as conn:
        total            = conn.execute("SELECT COUNT(*) FROM login_events").fetchone()[0]
        total_success    = conn.execute("SELECT COUNT(*) FROM login_events WHERE success = 1").fetchone()[0]
        total_failed     = conn.execute("SELECT COUNT(*) FROM login_events WHERE success = 0").fetchone()[0]
        last_24h_success = conn.execute(
            "SELECT COUNT(*) FROM login_events WHERE success = 1 AND timestamp >= datetime('now','-24 hours')"
        ).fetchone()[0]
        last_24h_failed  = conn.execute(
            "SELECT COUNT(*) FROM login_events WHERE success = 0 AND timestamp >= datetime('now','-24 hours')"
        ).fetchone()[0]

    return {
        "total_logins":      total,
        "successful_logins": total_success,
        "failed_logins":     total_failed,
        "last_24h": {
            "successful": last_24h_success,
            "failed":     last_24h_failed,
        },
    }


@admin_app.get("/api/admin/logins")
async def admin_logins(
    request: Request,
    status:   str = "all",
    username: str = "",
    limit:    int = 100,
    offset:   int = 0,
):
    """
    status: all | success | failed
    username: Filter auf einen bestimmten Benutzernamen (optional)
    limit: max. 500
    """
    if not admin_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)

    limit = min(max(limit, 1), 500)
    where, params = [], []

    if status == "success":
        where.append("success = 1")
    elif status == "failed":
        where.append("success = 0")

    if username:
        where.append("username = ?")
        params.append(username.lower())

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            f"SELECT timestamp, username, success, ip_address FROM login_events {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        total = conn.execute(
            f"SELECT COUNT(*) FROM login_events {where_sql}", params
        ).fetchone()[0]

    return {
        "total":  total,
        "limit":  limit,
        "offset": offset,
        "events": [
            {"timestamp": r[0], "username": r[1], "success": bool(r[2]), "ip": r[3]}
            for r in rows
        ],
    }


@admin_app.get("/api/admin/health")
async def admin_health(request: Request):
    if not admin_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{HA_API_BASE}/",
                headers={"Authorization": f"Bearer {SUPERVISOR_TOKEN}"},
            )
        ha_ok  = resp.status_code == 200
        ha_msg = "ok" if ha_ok else f"HTTP {resp.status_code}"
    except Exception as e:
        ha_ok  = False
        ha_msg = "connection error"
        log.warning("HA-API nicht erreichbar: %s", e)

    return {
        "status": "ok" if ha_ok else "degraded",
        "ha_api": {"reachable": ha_ok, "message": ha_msg},
    }


# ── Admin Panel (Ingress + Port 17773) ────────────────────────────────────────

ADMIN_STATIC_DIR = Path("/app/static/admin")

def _admin_login_redirect(base_path: str = "") -> RedirectResponse:
    return RedirectResponse(f"{base_path}/admin/login", status_code=303)


def _serve_admin_html(name: str) -> HTMLResponse:
    return HTMLResponse((ADMIN_STATIC_DIR / name).read_text(encoding="utf-8"))


def _ingress_base(request: Request) -> str:
    return request.headers.get("x-ingress-path", "").rstrip("/")


# ── Ingress app (Port 17774, HA Ingress) ─────────────────────────────────────

@ingress_app.get("/")
async def ingress_root():
    return Response(status_code=302, headers={"Location": "admin/"})


@ingress_app.get("/admin/login", response_class=HTMLResponse)
async def ingress_admin_login_page():
    return _serve_admin_html("admin_login.html")


@ingress_app.post("/admin/login")
async def ingress_admin_login(request: Request):
    form = await request.form()
    password = form.get("password") or ""
    opts = load_options()
    expected = (opts.get("admin_password") or "").strip()
    if expected and not check_password(password, expected):
        return Response(status_code=303, headers={"Location": "login?error=1"})
    token = get_admin_serializer().dumps({"admin": True})
    response = Response(status_code=303, headers={"Location": "."})
    response.set_cookie(ADMIN_COOKIE_NAME, token, max_age=ADMIN_SESSION_AGE, httponly=True, samesite="lax")
    return response


@ingress_app.get("/admin/logout")
async def ingress_admin_logout():
    response = Response(status_code=303, headers={"Location": "login"})
    response.delete_cookie(ADMIN_COOKIE_NAME)
    return response


@ingress_app.get("/admin/", response_class=HTMLResponse)
async def ingress_admin_panel(request: Request):
    if not admin_panel_allowed(request):
        return Response(status_code=302, headers={"Location": "login"})
    return _serve_admin_html("admin.html")


@ingress_app.post("/admin/api/preview")
async def ingress_preview(request: Request):
    if not admin_panel_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return await _admin_preview(request)


@ingress_app.get("/admin/api/recent-logins")
async def ingress_admin_recent_logins(request: Request):
    if not admin_panel_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return _admin_recent_logins()


@ingress_app.get("/admin/api/rate-limits")
async def ingress_get_rate_limits(request: Request):
    if not admin_panel_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return _admin_get_rate_limits()


@ingress_app.post("/admin/api/rate-limits/unblock")
async def ingress_unblock_ip(request: Request):
    if not admin_panel_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return await _admin_unblock_ip(request)


@ingress_app.get("/admin/api/pw-config")
async def ingress_admin_pw_config(request: Request):
    if not admin_panel_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    opts = load_options()
    return JSONResponse({"pw_min_length": int(opts.get("pw_min_length") or 8), "pw_require_special": bool(opts.get("pw_require_special", True))})


@ingress_app.get("/admin/api/users")
async def ingress_admin_list_users(request: Request):
    if not admin_panel_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return _admin_list_users()


@ingress_app.post("/admin/api/users")
async def ingress_admin_create_user(request: Request):
    if not admin_panel_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return await _admin_create_user(request)


@ingress_app.put("/admin/api/users/{username}")
async def ingress_admin_update_user(username: str, request: Request):
    if not admin_panel_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return await _admin_update_user(username, request)


@ingress_app.delete("/admin/api/users/{username}")
async def ingress_admin_delete_user(username: str, request: Request):
    if not admin_panel_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return _admin_delete_user(username)


@ingress_app.post("/admin/api/users/{username}/reset-password")
async def ingress_admin_reset_password(username: str, request: Request):
    if not admin_panel_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return await _admin_reset_password(username, request)


ingress_app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ── Admin Panel routes on admin_app (Port 17773) ─────────────────────────────

@admin_app.get("/")
async def admin_root():
    return Response(status_code=302, headers={"Location": "admin/"})


@admin_app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page_direct():
    return _serve_admin_html("admin_login.html")


@admin_app.post("/admin/login")
async def admin_login_direct(request: Request):
    if not admin_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    form = await request.form()
    password = form.get("password") or ""
    opts = load_options()
    expected = (opts.get("admin_password") or "").strip()
    if expected and not check_password(password, expected):
        return RedirectResponse("/admin/login?error=1", status_code=303)
    token = get_admin_serializer().dumps({"admin": True})
    response = RedirectResponse("/admin/", status_code=303)
    response.set_cookie(ADMIN_COOKIE_NAME, token, max_age=ADMIN_SESSION_AGE, httponly=True, samesite="lax")
    return response


@admin_app.get("/admin/logout")
async def admin_logout_direct():
    response = RedirectResponse("/admin/login", status_code=303)
    response.delete_cookie(ADMIN_COOKIE_NAME)
    return response


@admin_app.get("/admin/", response_class=HTMLResponse)
async def admin_panel_direct(request: Request):
    if not admin_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    opts = load_options()
    expected = (opts.get("admin_password") or "").strip()
    if expected and not get_admin_session(request):
        return _admin_login_redirect()
    return _serve_admin_html("admin.html")


@admin_app.post("/admin/api/preview")
async def admin_preview_direct(request: Request):
    if not admin_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return await _admin_preview(request)


@admin_app.get("/admin/api/recent-logins")
async def admin_recent_logins_direct(request: Request):
    if not admin_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return _admin_recent_logins()


@admin_app.get("/admin/api/rate-limits")
async def admin_get_rate_limits(request: Request):
    if not admin_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return _admin_get_rate_limits()


@admin_app.post("/admin/api/rate-limits/unblock")
async def admin_unblock_ip(request: Request):
    if not admin_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return await _admin_unblock_ip(request)


@admin_app.get("/admin/api/pw-config")
async def admin_pw_config_direct(request: Request):
    if not admin_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    opts = load_options()
    return JSONResponse({"pw_min_length": int(opts.get("pw_min_length") or 8), "pw_require_special": bool(opts.get("pw_require_special", True))})


@admin_app.get("/admin/api/users")
async def admin_list_users_direct(request: Request):
    if not admin_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return _admin_list_users()


@admin_app.post("/admin/api/users")
async def admin_create_user_direct(request: Request):
    if not admin_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return await _admin_create_user(request)


@admin_app.put("/admin/api/users/{username}")
async def admin_update_user_direct(username: str, request: Request):
    if not admin_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return await _admin_update_user(username, request)


@admin_app.delete("/admin/api/users/{username}")
async def admin_delete_user_direct(username: str, request: Request):
    if not admin_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return _admin_delete_user(username)


@admin_app.post("/admin/api/users/{username}/reset-password")
async def admin_reset_password_direct(username: str, request: Request):
    if not admin_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return await _admin_reset_password(username, request)


admin_app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static_admin")


# ── Template page routes ─────────────────────────────────────────────────────

@ingress_app.get("/admin/templates/{username}", response_class=HTMLResponse)
async def ingress_templates_page(username: str, request: Request):
    if not admin_panel_allowed(request):
        return Response(status_code=302, headers={"Location": "../login"})
    return _serve_admin_html("admin_templates.html")


@ingress_app.get("/admin/api/users/{username}/logins")
async def ingress_user_logins(username: str, request: Request):
    if not admin_panel_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return _admin_user_logins(username)


@ingress_app.post("/admin/api/users/{username}/templates/reorder")
async def ingress_reorder_templates(username: str, request: Request):
    if not admin_panel_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return await _admin_reorder_templates(username, request)


@ingress_app.get("/admin/api/users/{username}/templates")
async def ingress_list_templates(username: str, request: Request):
    if not admin_panel_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return _admin_get_templates(username)


@ingress_app.get("/admin/api/users/{username}/templates/{filename}")
async def ingress_get_template(username: str, filename: str, request: Request):
    if not admin_panel_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return _admin_get_template_content(username, filename)


@ingress_app.put("/admin/api/users/{username}/templates/{filename}")
async def ingress_save_template(username: str, filename: str, request: Request):
    if not admin_panel_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return await _admin_save_template(username, filename, request)


@ingress_app.delete("/admin/api/users/{username}/templates/{filename}")
async def ingress_delete_template(username: str, filename: str, request: Request):
    if not admin_panel_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return _admin_delete_template(username, filename)


@ingress_app.get("/admin/api/orphaned")
async def ingress_get_orphaned(request: Request):
    if not admin_panel_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return _admin_get_orphaned()


@ingress_app.post("/admin/api/orphaned/cleanup")
async def ingress_cleanup_orphaned(request: Request):
    if not admin_panel_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return await _admin_cleanup_orphaned(request)


@admin_app.get("/admin/templates/{username}", response_class=HTMLResponse)
async def admin_templates_page(username: str, request: Request):
    if not admin_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    opts = load_options()
    if (opts.get("admin_password") or "").strip() and not get_admin_session(request):
        return Response(status_code=302, headers={"Location": "../login"})
    return _serve_admin_html("admin_templates.html")


@admin_app.get("/admin/api/users/{username}/logins")
async def admin_user_logins(username: str, request: Request):
    if not admin_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return _admin_user_logins(username)


@admin_app.post("/admin/api/users/{username}/templates/reorder")
async def admin_reorder_templates(username: str, request: Request):
    if not admin_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return await _admin_reorder_templates(username, request)


@admin_app.get("/admin/api/users/{username}/templates")
async def admin_list_templates(username: str, request: Request):
    if not admin_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return _admin_get_templates(username)


@admin_app.get("/admin/api/users/{username}/templates/{filename}")
async def admin_get_template(username: str, filename: str, request: Request):
    if not admin_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return _admin_get_template_content(username, filename)


@admin_app.put("/admin/api/users/{username}/templates/{filename}")
async def admin_save_template(username: str, filename: str, request: Request):
    if not admin_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return await _admin_save_template(username, filename, request)


@admin_app.delete("/admin/api/users/{username}/templates/{filename}")
async def admin_delete_template(username: str, filename: str, request: Request):
    if not admin_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return _admin_delete_template(username, filename)


@admin_app.get("/admin/api/orphaned")
async def admin_get_orphaned(request: Request):
    if not admin_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return _admin_get_orphaned()


@admin_app.post("/admin/api/orphaned/cleanup")
async def admin_cleanup_orphaned(request: Request):
    if not admin_allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return await _admin_cleanup_orphaned(request)


# ── Admin business logic (shared) ────────────────────────────────────────────

async def _admin_preview(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    content = body.get("template", "")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{HA_API_BASE}/template",
                headers={"Authorization": f"Bearer {SUPERVISOR_TOKEN}", "Content-Type": "application/json"},
                json={"template": content},
            )
        if resp.status_code == 200:
            return JSONResponse({"rendered": resp.text})
        return JSONResponse({"error": f"HA {resp.status_code}", "detail": resp.text[:500]})
    except Exception:
        log.exception("Template-Vorschau Fehler")
        return JSONResponse({"error": "internal error"}, status_code=503)


def _admin_recent_logins():
    with sqlite3.connect(DB_PATH) as conn:
        def last(success: int):
            row = conn.execute(
                "SELECT timestamp, username, ip_address FROM login_events "
                "WHERE success = ? ORDER BY id DESC LIMIT 1", (success,)
            ).fetchone()
            return {"timestamp": row[0], "username": row[1], "ip": row[2]} if row else None
        failed_24h = conn.execute(
            "SELECT COUNT(*) FROM login_events WHERE success = 0 "
            "AND timestamp >= datetime('now', '-24 hours')"
        ).fetchone()[0]
    return JSONResponse({"last_success": last(1), "last_failed": last(0), "failed_24h": failed_24h})


def _admin_user_logins(username: str, limit: int = 50):
    username = username.lower()
    users = load_users()
    if not any((u.get("username") or "").lower() == username for u in users):
        return JSONResponse({"error": "not_found"}, status_code=404)
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT timestamp, success, ip_address, user_agent FROM login_events "
            "WHERE username = ? ORDER BY id DESC LIMIT ?",
            (username, limit),
        ).fetchall()
    return JSONResponse({
        "username": username,
        "events": [{"timestamp": r[0], "success": bool(r[1]), "ip": r[2], "browser": _parse_user_agent(r[3] or "")} for r in rows],
    })


async def _admin_reorder_templates(username: str, request: Request):
    username = username.lower()
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    order = body.get("order")
    if not isinstance(order, list):
        return JSONResponse({"error": "invalid_order"}, status_code=400)
    users_file = CONFIG_DIR / "users.yaml"
    if not users_file.exists():
        return JSONResponse({"error": "not_found"}, status_code=404)
    with open(users_file, encoding="utf-8") as f:
        yaml_data = yaml.safe_load(f) or {}
    users = yaml_data.get("users") or []
    user = next((u for u in users if (u.get("username") or "").lower() == username), None)
    if not user:
        return JSONResponse({"error": "not_found"}, status_code=404)
    normalized = _normalize_templates(user.get("templates"))
    tpl_map = {t["file"]: t for t in normalized}
    reordered = [tpl_map[f] for f in order if f in tpl_map]
    reordered.extend(t for t in normalized if t["file"] not in order)
    user["templates"] = [{"file": t["file"], "title": t["title"]} if t["title"] else t["file"] for t in reordered]
    write_users(yaml_data)
    log.info("Admin: Templates für '%s' umsortiert", username)
    return JSONResponse({"success": True})


def _admin_get_orphaned():
    known = {(u.get("username") or "").lower() for u in load_users()}
    orphaned = []
    if CONFIG_DIR.exists():
        for entry in sorted(CONFIG_DIR.iterdir()):
            if not entry.is_dir():
                continue
            if entry.name.lower() in known:
                continue
            files = sorted(f.name for f in entry.iterdir() if f.is_file() and f.suffix == ".j2")
            total_files = sum(1 for f in entry.iterdir() if f.is_file())
            orphaned.append({"dir": entry.name, "j2_files": files, "total_files": total_files})
    return JSONResponse({"orphaned": orphaned})


async def _admin_cleanup_orphaned(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    dirs = body.get("dirs")
    if not isinstance(dirs, list) or not dirs:
        return JSONResponse({"error": "dirs_empty"}, status_code=400)
    known = {(u.get("username") or "").lower() for u in load_users()}
    deleted, errors = [], []
    for name in dirs:
        name = str(name).strip()
        if not name or name.lower() in known:
            errors.append({"dir": name, "reason": "active_user"})
            continue
        target = safe_child(CONFIG_DIR, name)
        if not target or not target.exists() or not target.is_dir():
            errors.append({"dir": name, "reason": "not_found"})
            continue
        try:
            shutil.rmtree(target)
            log.info("Admin: Verwaistes Verzeichnis '%s' gelöscht", name)
            deleted.append(name)
        except Exception:
            log.exception("Fehler beim Löschen von Verzeichnis '%s'", name)
            errors.append({"dir": name, "reason": "delete failed"})
    return JSONResponse({"deleted": deleted, "errors": errors})


def _normalize_templates(templates: list) -> list:
    result = []
    for e in (templates or []):
        result.append({"file": e.get("file", ""), "title": e.get("title") or ""} if isinstance(e, dict) else {"file": str(e), "title": ""})
    return result


def _admin_get_templates(username: str):
    username = username.lower()
    users = load_users()
    user = next((u for u in users if (u.get("username") or "").lower() == username), None)
    if not user:
        return JSONResponse({"error": "not_found"}, status_code=404)
    result = []
    for t in _normalize_templates(user.get("templates")):
        path = safe_child(CONFIG_DIR, username, t["file"]) if t["file"] else None
        result.append({**t, "exists": bool(path and path.exists())})
    return JSONResponse(result)


def _admin_get_template_content(username: str, filename: str):
    username = username.lower()
    path = safe_child(CONFIG_DIR, username, filename)
    if not path:
        return JSONResponse({"error": "invalid_path"}, status_code=400)
    if not path.exists():
        return JSONResponse({"content": ""})
    return JSONResponse({"content": path.read_text(encoding="utf-8")})


async def _admin_save_template(username: str, filename: str, request: Request):
    username = username.lower()
    if not re.match(r'^[a-zA-Z0-9_\-]+\.j2$', filename):
        return JSONResponse({"error": "invalid_filename"}, status_code=400)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    content = body.get("content", "")
    title   = body.get("title", "")

    path = safe_child(CONFIG_DIR, username, filename)
    if not path:
        return JSONResponse({"error": "invalid_path"}, status_code=400)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    users_file = CONFIG_DIR / "users.yaml"
    if not users_file.exists():
        return JSONResponse({"error": "users_file_missing"}, status_code=500)
    with open(users_file, encoding="utf-8") as f:
        yaml_data = yaml.safe_load(f) or {}
    users = yaml_data.get("users") or []
    user  = next((u for u in users if (u.get("username") or "").lower() == username), None)
    if not user:
        return JSONResponse({"error": "not_found"}, status_code=404)

    normalized = _normalize_templates(user.get("templates"))
    entry = next((t for t in normalized if t["file"] == filename), None)
    if entry:
        entry["title"] = title
    else:
        normalized.append({"file": filename, "title": title})
    user["templates"] = [{"file": t["file"], "title": t["title"]} if t["title"] else t["file"] for t in normalized]
    write_users(yaml_data)
    log.info("Admin: Template '%s' für '%s' gespeichert", filename, username)
    return JSONResponse({"success": True})


def _admin_delete_template(username: str, filename: str):
    username = username.lower()
    path = safe_child(CONFIG_DIR, username, filename)
    if not path:
        return JSONResponse({"error": "invalid_path"}, status_code=400)

    users_file = CONFIG_DIR / "users.yaml"
    if users_file.exists():
        with open(users_file, encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f) or {}
        users = yaml_data.get("users") or []
        user  = next((u for u in users if (u.get("username") or "").lower() == username), None)
        if user:
            normalized = _normalize_templates(user.get("templates"))
            normalized = [t for t in normalized if t["file"] != filename]
            user["templates"] = [{"file": t["file"], "title": t["title"]} if t["title"] else t["file"] for t in normalized]
            write_users(yaml_data)

    if path.exists():
        path.unlink()
    log.info("Admin: Template '%s' für '%s' gelöscht", filename, username)
    return JSONResponse({"success": True})


def _admin_list_users():
    users = load_users()

    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT username, timestamp, ip_address FROM login_events "
            "WHERE success = 1 AND id IN ("
            "  SELECT MAX(id) FROM login_events WHERE success = 1 GROUP BY username"
            ")"
        ).fetchall()
    last_logins = {r[0]: {"ts": r[1], "ip": r[2]} for r in rows}

    result = []
    for u in users:
        uname = (u.get("username") or "").lower()
        ll = last_logins.get(uname)
        result.append({
            "username":        uname,
            "display_name":    u.get("display_name") or "",
            "lang":            u.get("lang") or "de",
            "template_count":  len(u.get("templates") or []),
            "force_pw_change": bool(u.get("force_pw_change")),
            "last_login_at":   ll["ts"] if ll else None,
            "last_login_ip":   ll["ip"] if ll else None,
        })
    return JSONResponse(result)


async def _admin_create_user(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_request"}, status_code=400)

    username     = (body.get("username") or "").strip().lower()
    password     = body.get("password") or ""
    display_name = body.get("display_name") or ""
    lang         = body.get("lang") or "de"

    err = validate_username(username)
    if err:
        return JSONResponse({"error": err}, status_code=400)
    if not password:
        return JSONResponse({"error": "password_empty"}, status_code=400)

    opts = load_options()
    pw_err = validate_new_password(password, opts)
    if pw_err:
        return JSONResponse({"error": pw_err, "pw_min_length": int(opts.get("pw_min_length") or 8)}, status_code=400)

    users_file = CONFIG_DIR / "users.yaml"
    yaml_data  = {}
    if users_file.exists():
        with open(users_file, encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f) or {}
    users = yaml_data.get("users") or []

    if any((u.get("username") or "").lower() == username for u in users):
        return JSONResponse({"error": "username_exists"}, status_code=409)

    pw_hash = _hash_password(password)
    new_user: dict = {
        "username":     username,
        "password":     pw_hash,
        "force_pw_change": True,
    }
    if display_name:
        new_user["display_name"] = display_name
    if lang in ("de", "en"):
        new_user["lang"] = lang
    new_user["templates"] = []

    users.append(new_user)
    yaml_data["users"] = users
    write_users(yaml_data)

    user_dir = safe_child(CONFIG_DIR, username)
    if user_dir:
        user_dir.mkdir(parents=True, exist_ok=True)

    log.info("Admin: Benutzer '%s' erstellt", username)
    return JSONResponse({"success": True, "username": username}, status_code=201)


async def _admin_update_user(username: str, request: Request):
    username = username.lower()
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_request"}, status_code=400)

    users_file = CONFIG_DIR / "users.yaml"
    if not users_file.exists():
        return JSONResponse({"error": "not_found"}, status_code=404)
    with open(users_file, encoding="utf-8") as f:
        yaml_data = yaml.safe_load(f) or {}

    users = yaml_data.get("users") or []
    user  = next((u for u in users if (u.get("username") or "").lower() == username), None)
    if not user:
        return JSONResponse({"error": "not_found"}, status_code=404)

    if "display_name" in body:
        user["display_name"] = body["display_name"]
    if "lang" in body and body["lang"] in ("de", "en"):
        user["lang"] = body["lang"]
    if "force_pw_change" in body:
        if body["force_pw_change"]:
            user["force_pw_change"] = True
        else:
            user.pop("force_pw_change", None)

    write_users(yaml_data)
    log.info("Admin: Benutzer '%s' aktualisiert", username)
    return JSONResponse({"success": True})


def _admin_delete_user(username: str):
    username = username.lower()
    users_file = CONFIG_DIR / "users.yaml"
    if not users_file.exists():
        return JSONResponse({"error": "not_found"}, status_code=404)
    with open(users_file, encoding="utf-8") as f:
        yaml_data = yaml.safe_load(f) or {}

    users = yaml_data.get("users") or []
    new_users = [u for u in users if (u.get("username") or "").lower() != username]
    if len(new_users) == len(users):
        return JSONResponse({"error": "not_found"}, status_code=404)

    yaml_data["users"] = new_users
    write_users(yaml_data)
    log.info("Admin: Benutzer '%s' gelöscht", username)
    return JSONResponse({"success": True})


async def _admin_reset_password(username: str, request: Request):
    username = username.lower()
    try:
        body = await request.json()
    except Exception:
        body = {}

    new_pw = body.get("password") or ""
    if not new_pw:
        return JSONResponse({"error": "password_empty"}, status_code=400)

    opts = load_options()
    pw_err = validate_new_password(new_pw, opts)
    if pw_err:
        return JSONResponse({"error": pw_err, "pw_min_length": int(opts.get("pw_min_length") or 8)}, status_code=400)

    users_file = CONFIG_DIR / "users.yaml"
    if not users_file.exists():
        return JSONResponse({"error": "not_found"}, status_code=404)
    with open(users_file, encoding="utf-8") as f:
        yaml_data = yaml.safe_load(f) or {}

    users = yaml_data.get("users") or []
    user  = next((u for u in users if (u.get("username") or "").lower() == username), None)
    if not user:
        return JSONResponse({"error": "not_found"}, status_code=404)

    user["password"] = _hash_password(new_pw)
    user["force_pw_change"] = True
    write_users(yaml_data)
    log.info("Admin: Passwort für '%s' zurückgesetzt", username)
    return JSONResponse({"success": True})


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port         = 17772
    admin_port   = 17773
    ingress_port = 17774

    init_db()
    init_pwa()
    log.info("CardBoard startet — Web-UI: %s  Admin-API: %s  Ingress: %s", port, admin_port, ingress_port)

    async def serve():
        cfg_main    = uvicorn.Config(app,         host="0.0.0.0", port=port,         log_level="info", log_config=UVICORN_LOG_CONFIG)
        cfg_admin   = uvicorn.Config(admin_app,   host="0.0.0.0", port=admin_port,   log_level="info", log_config=UVICORN_LOG_CONFIG)
        cfg_ingress = uvicorn.Config(ingress_app, host="0.0.0.0", port=ingress_port, log_level="info", log_config=UVICORN_LOG_CONFIG)
        await asyncio.gather(
            uvicorn.Server(cfg_main).serve(),
            uvicorn.Server(cfg_admin).serve(),
            uvicorn.Server(cfg_ingress).serve(),
        )

    asyncio.run(serve())
