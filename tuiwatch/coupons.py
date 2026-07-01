"""MyTUI-Coupon-Abruf über den eingeloggten Bereich (my.tui.com).

Der Login ist durch einen Bot-Schutz (SAP-Gigya-Captcha) abgesichert; ein reiner
Server-Login per `requests` wird davon blockiert. Daher meldet sich TUIWatch in einem
echten Headless-Browser (Playwright) an — der Gigya-WebSDK löst den (meist unsichtbaren)
Captcha im Browser-Kontext. Nach dem Login lädt die myTUI-SPA die Coupons über die
JSON-API `…/coupons/getAccountCoupons`; wir fangen genau diese Antwort ab und werten sie
aus (kein Nachbauen von Token/Headern nötig).

Die eigentliche Auswertung (`parse_coupons`) ist rein und ohne Browser testbar.
"""
import logging
import os
import time

log = logging.getLogger("tuiwatch")

LOGIN_URL = "https://my.tui.com/n/"
COUPONS_URL = "https://my.tui.com/n/my-benefits/coupons"
COUPON_API_MARK = "getAccountCoupons"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
CONSENT_SELECTORS = [
    "#cmm-accept-all", "#onetrust-accept-btn-handler",
    "button:has-text('Alle akzeptieren')", "button:has-text('Akzeptieren')",
    "button:has-text('Zustimmen')",
]


def parse_coupons(data) -> list:
    """Aus der getAccountCoupons-JSON-Antwort die relevanten Felder ziehen.
    Toleriert Array oder Objekt mit `coupons`/`data`-Liste."""
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("coupons") or data.get("data") or data.get("items") or []
    else:
        items = []
    out = []
    for c in items:
        if not isinstance(c, dict):
            continue
        tpl = c.get("template") or {}
        cid = c.get("couponId") or c.get("id") or tpl.get("mastercodehash")
        if not cid:
            continue
        out.append({
            "id": str(cid),
            "title": (tpl.get("claim") or c.get("name") or "Coupon").strip(),
            "saving": tpl.get("saving"),
            "start": c.get("startDate") or "",
            "end": c.get("endDate") or "",
        })
    return out


def _consent(page, verbose):
    for sel in CONSENT_SELECTORS:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                if verbose:
                    log.info("Coupon-Login: Consent geklickt (%s)", sel)
                time.sleep(1)
                return
        except Exception:
            pass


def _click_text(page, texts):
    for t in texts:
        try:
            btn = page.query_selector(f"button:has-text('{t}')")
            if btn and btn.is_visible():
                btn.click()
                return True
        except Exception:
            pass
    # Fallback: sichtbaren Submit-Button klicken
    try:
        btn = page.query_selector("button[type=submit]")
        if btn and btn.is_visible():
            btn.click()
            return True
    except Exception:
        pass
    return False


def fetch_coupons(user: str, password: str, *, verbose: bool = False,
                  debug_png: str | None = None) -> dict:
    """Loggt sich ein und liest die aktuellen MyTUI-Coupons.
    Rückgabe: {'ok': True, 'coupons': [...]} oder {'ok': False, 'error': '…'}."""
    if not (user and password):
        return {"ok": False, "error": "Keine Zugangsdaten gesetzt (tui_user/tui_pass)."}
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        return {"ok": False, "error": f"Playwright nicht verfügbar: {e}"}

    chromium_path = os.environ.get("CHROMIUM_PATH") or None
    captured: dict = {}

    def on_response(resp):
        try:
            if COUPON_API_MARK in resp.url and resp.status == 200:
                captured["data"] = resp.json()
        except Exception:
            pass

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=chromium_path,
                                        args=["--no-sandbox", "--disable-dev-shm-usage"])
            ctx = browser.new_context(locale="de-DE", user_agent=USER_AGENT,
                                      viewport={"width": 1366, "height": 1600})
            page = ctx.new_page()
            page.on("response", on_response)
            try:
                page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
                time.sleep(2)
                _consent(page, verbose)
                # Schritt 1: E-Mail eingeben → „Weiter"
                email = page.wait_for_selector(
                    "input[type=email], input[name*='mail' i], input[autocomplete='username']",
                    timeout=30000)
                email.fill(user)
                _click_text(page, ["Weiter", "Continue"])
                time.sleep(2)
                # Schritt 2: Passwort → „Anmelden"
                pw = page.wait_for_selector("input[type=password]", timeout=30000)
                pw.fill(password)
                _click_text(page, ["Anmelden", "Einloggen", "Login"])
                try:
                    page.wait_for_load_state("networkidle", timeout=30000)
                except Exception:
                    pass
                time.sleep(2)
                # Coupon-Seite laden → löst getAccountCoupons aus
                page.goto(COUPONS_URL, wait_until="domcontentloaded", timeout=60000)
                for _ in range(40):                    # bis zu ~20 s auf die API-Antwort warten
                    if "data" in captured:
                        break
                    time.sleep(0.5)
                if "data" not in captured:
                    if debug_png:
                        try:
                            page.screenshot(path=debug_png, full_page=True)
                        except Exception:
                            pass
                    if page.query_selector("input[type=password]"):
                        return {"ok": False, "error": "Login nicht möglich — Passwort-Feld "
                                "noch aktiv (falsche Daten oder Bot-Schutz/Captcha)."}
                    return {"ok": False, "error": "Coupon-Daten nicht empfangen "
                            "(Session/Seite unerwartet)."}
                coupons = parse_coupons(captured["data"])
                if verbose:
                    log.info("Coupon-Abruf: %d Coupons empfangen", len(coupons))
                return {"ok": True, "coupons": coupons}
            finally:
                try:
                    browser.close()
                except Exception:
                    pass
    except Exception as e:
        if verbose:
            log.warning("Coupon-Abruf-Fehler: %s: %s", type(e).__name__, e)
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
