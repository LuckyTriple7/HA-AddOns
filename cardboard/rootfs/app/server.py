import asyncio
import hashlib
import json
import logging
import re
import sqlite3
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app        = FastAPI()
admin_app  = FastAPI()
ingress_app = FastAPI()

_ha_status_cache: dict = {"reachable": False, "version": None, "since": None, "checked_at": None}

DATA_DIR = Path("/data")
CONFIG_DIR = Path("/config/addons_config/cardboard")
OPTIONS_FILE = DATA_DIR / "options.json"
STATIC_DIR = Path("/app/static")
DB_PATH = DATA_DIR / "cardboard.db"
COOKIE_NAME       = "cb_session"
ADMIN_COOKIE_NAME = "cb_admin"
ADMIN_SESSION_AGE = 4 * 3600  # 4 Stunden


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


def get_serializer() -> URLSafeTimedSerializer:
    opts = load_options()
    secret = (opts.get("ha_token") or "cardboard-fallback-secret")[:50]
    return URLSafeTimedSerializer(secret)


def safe_child(base: Path, *parts: str) -> Path | None:
    """Gibt einen Pfad nur zurück wenn er innerhalb von base liegt (verhindert Path Traversal)."""
    try:
        resolved = base.joinpath(*parts).resolve()
        if resolved.is_relative_to(base.resolve()):
            return resolved
    except Exception:
        pass
    return None


# ── Admin auth ────────────────────────────────────────────────────────────────

def admin_password_set() -> bool:
    return bool((load_options().get("admin_password") or "").strip())


def get_admin_serializer() -> URLSafeTimedSerializer:
    opts = load_options()
    secret = ((opts.get("ha_token") or "cardboard-admin-secret") + "-admin")[:60]
    return URLSafeTimedSerializer(secret)


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
    """Ingress oder LAN-Zugang ohne Passwort = automatisch eingeloggt."""
    if not admin_password_set():
        return is_private_ip(request) or _is_ingress(request)
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
                ip_address  TEXT
            )
        """)
        conn.commit()


def db_log_login(username: str, success: bool, ip: str | None):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO login_events (timestamp, username, success, ip_address) VALUES (?, ?, ?, ?)",
            (datetime.utcnow().isoformat(timespec="seconds"), username, int(success), ip),
        )
        conn.commit()


# ── Auth helpers ──────────────────────────────────────────────────────────────

def is_https(request: Request) -> bool:
    return (
        request.url.scheme == "https"
        or request.headers.get("x-forwarded-proto", "").lower() == "https"
    )


def check_password(plain: str, stored: str) -> bool:
    """Unterstützt SHA-256-Hashes (64 Hex-Zeichen) und Klartext-Passwörter."""
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


# ── Main app ──────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return RedirectResponse("/view")


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
        ha_url   = (opts.get("ha_url") or "http://homeassistant.local:8123").rstrip("/")
        ha_token = opts.get("ha_token") or ""
        uptime_entity = (opts.get("uptime_sensor") or "sensor.uptime").strip()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{ha_url}/api/config",
                    headers={"Authorization": f"Bearer {ha_token}"},
                )
                if resp.status_code == 200:
                    version = resp.json().get("version", "")
                    since = None
                    try:
                        up = await client.get(
                            f"{ha_url}/api/states/{uptime_entity}",
                            headers={"Authorization": f"Bearer {ha_token}"},
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
    ha_url   = (opts.get("ha_url") or "http://homeassistant.local:8123").rstrip("/")
    ha_token = opts.get("ha_token") or ""
    timestamp = datetime.utcnow().strftime("%d.%m.%Y %H:%M:%S")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{ha_url}/api/services/persistent_notification/create",
                headers={"Authorization": f"Bearer {ha_token}"},
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
    ip = client_ip(request)

    users = load_users()
    user = next((u for u in users if (u.get("username") or "").lower() == username), None)

    if not user or not check_password(password, user.get("password", "")):
        db_log_login(username or "?", False, ip)
        log.warning("Login fehlgeschlagen: user='%s' ip='%s'", username or "?", ip or "?")
        asyncio.create_task(_notify_failed_login(username or "?", ip))
        return RedirectResponse("/login?error=1", status_code=303)

    db_log_login(username, True, ip)
    log.info("Login erfolgreich: user='%s' ip='%s'", username, ip or "?")
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

    user["password"] = hashlib.sha256(new_pw.encode()).hexdigest()
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

    return {
        "username":         username,
        "display_name":     display_name,
        "lang":             lang,
        "refresh_interval": opts.get("refresh_interval", 30),
        "card_count":       min(len(templates), 3),
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

    ha_url = (opts.get("ha_url") or "http://homeassistant.local:8123").rstrip("/")
    ha_token = opts.get("ha_token") or ""
    templates = (user.get("templates") or [])[:3]

    cards = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for entry in templates:
            tpl_name, title = parse_template_entry(entry)
            tpl_path = safe_child(CONFIG_DIR / username, tpl_name)
            if not tpl_path or not tpl_path.exists():
                cards.append({"title": title, "content": f"⚠️ Template nicht gefunden: `{tpl_name}`"})
                continue

            content = tpl_path.read_text(encoding="utf-8")
            try:
                resp = await client.post(
                    f"{ha_url}/api/template",
                    headers={
                        "Authorization": f"Bearer {ha_token}",
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
            except Exception as e:
                log.exception("Fehler beim Rendern von %s", tpl_name)
                cards.append({"title": title, "content": f"⚠️ Verbindungsfehler: {e}"})

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

    opts = load_options()
    ha_url   = (opts.get("ha_url") or "http://homeassistant.local:8123").rstrip("/")
    ha_token = opts.get("ha_token") or ""

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{ha_url}/api/",
                headers={"Authorization": f"Bearer {ha_token}"},
            )
        ha_ok  = resp.status_code == 200
        ha_msg = "ok" if ha_ok else f"HTTP {resp.status_code}"
    except Exception as e:
        ha_ok  = False
        ha_msg = str(e)

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
        return RedirectResponse("/admin/login?error=1", status_code=303)
    token = get_admin_serializer().dumps({"admin": True})
    response = RedirectResponse("/admin/", status_code=303)
    response.set_cookie(ADMIN_COOKIE_NAME, token, max_age=ADMIN_SESSION_AGE, httponly=True, samesite="lax")
    return response


@ingress_app.get("/admin/logout")
async def ingress_admin_logout():
    response = RedirectResponse("/admin/login", status_code=303)
    response.delete_cookie(ADMIN_COOKIE_NAME)
    return response


@ingress_app.get("/admin/", response_class=HTMLResponse)
async def ingress_admin_panel(request: Request):
    if not admin_panel_allowed(request):
        return _admin_login_redirect()
    return _serve_admin_html("admin.html")


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


# ── Admin business logic (shared) ────────────────────────────────────────────

def _admin_list_users():
    users = load_users()
    result = []
    for u in users:
        uname = (u.get("username") or "").lower()
        templates = u.get("templates") or []
        result.append({
            "username":       uname,
            "display_name":   u.get("display_name") or "",
            "lang":           u.get("lang") or "de",
            "template_count": len(templates),
            "force_pw_change": bool(u.get("force_pw_change")),
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

    pw_hash = hashlib.sha256(password.encode()).hexdigest()
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

    user_dir = CONFIG_DIR / username
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

    user["password"] = hashlib.sha256(new_pw.encode()).hexdigest()
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
    log.info("CardBoard startet — Web-UI: %s  Admin-API: %s  Ingress: %s", port, admin_port, ingress_port)

    async def serve():
        cfg_main    = uvicorn.Config(app,         host="0.0.0.0", port=port,         log_level="info")
        cfg_admin   = uvicorn.Config(admin_app,   host="0.0.0.0", port=admin_port,   log_level="info")
        cfg_ingress = uvicorn.Config(ingress_app, host="0.0.0.0", port=ingress_port, log_level="info")
        await asyncio.gather(
            uvicorn.Server(cfg_main).serve(),
            uvicorn.Server(cfg_admin).serve(),
            uvicorn.Server(cfg_ingress).serve(),
        )

    asyncio.run(serve())
