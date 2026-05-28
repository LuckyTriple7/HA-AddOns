import asyncio
import hashlib
import json
import logging
import sqlite3
from datetime import datetime
from ipaddress import ip_address
from pathlib import Path

import httpx
import uvicorn
import yaml
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI()
admin_app = FastAPI()

DATA_DIR = Path("/data")
CONFIG_DIR = Path("/config/addons_config/cardboard")
OPTIONS_FILE = DATA_DIR / "options.json"
STATIC_DIR = Path("/app/static")
DB_PATH = DATA_DIR / "cardboard.db"
COOKIE_NAME = "cb_session"
SESSION_MAX_AGE = 7 * 24 * 3600


# ── Config & Users ────────────────────────────────────────────────────────────

def load_options() -> dict:
    with open(OPTIONS_FILE) as f:
        return json.load(f)


def load_users() -> list:
    users_file = CONFIG_DIR / "users.yaml"
    if not users_file.exists():
        return []
    with open(users_file) as f:
        data = yaml.safe_load(f)
    return data.get("users", []) if data else []


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
        data = get_serializer().loads(token, max_age=SESSION_MAX_AGE)
        return data.get("username")
    except (BadSignature, SignatureExpired):
        return None


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# ── Main app ──────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return RedirectResponse("/view")


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
        return RedirectResponse("/login?error=1", status_code=303)

    db_log_login(username, True, ip)
    token = get_serializer().dumps({"username": username})
    response = RedirectResponse("/view", status_code=303)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=is_https(request),
    )
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


@app.get("/view", response_class=HTMLResponse)
async def view_page(request: Request):
    if not get_current_user(request):
        return RedirectResponse("/login")
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
        "username": username,
        "display_name": display_name,
        "lang": lang,
        "refresh_interval": opts.get("refresh_interval", 30),
        "card_count": min(len(templates), 3),
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

    ha_url = (opts.get("ha_url") or "http://homeassistant:8123").rstrip("/")
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


@admin_app.get("/api/admin/stats")
async def admin_stats(request: Request):
    if not is_private_ip(request):
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
    if not is_private_ip(request):
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
    if not is_private_ip(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)

    opts = load_options()
    ha_url   = (opts.get("ha_url") or "http://homeassistant:8123").rstrip("/")
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


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    opts = load_options()
    port       = int(opts.get("port", 17772))
    admin_port = int(opts.get("admin_port", 17773))

    init_db()
    log.info("CardBoard startet — Web-UI: %s  Admin-API: %s", port, admin_port)

    async def serve():
        cfg_main  = uvicorn.Config(app,       host="0.0.0.0", port=port,       log_level="info")
        cfg_admin = uvicorn.Config(admin_app, host="0.0.0.0", port=admin_port, log_level="info")
        await asyncio.gather(
            uvicorn.Server(cfg_main).serve(),
            uvicorn.Server(cfg_admin).serve(),
        )

    asyncio.run(serve())
