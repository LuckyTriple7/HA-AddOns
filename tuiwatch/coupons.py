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
# Linux-UA, konsistent zur tatsächlichen Container-Umgebung (ein Windows-UA auf einem
# Linux-Headless-Browser ist selbst ein Bot-Signal, weil er den Client Hints widerspricht).
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
CONSENT_SELECTORS = [
    "button:has-text('Zustimmen')", "button:has-text('Alle akzeptieren')",
    "button:has-text('Akzeptieren')", "#cmm-accept-all",
    "#onetrust-accept-btn-handler",
]
# Tarnung gegen simple Headless-Erkennung (navigator.webdriver etc.)
_STEALTH_JS = (
    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
    "Object.defineProperty(navigator,'languages',{get:()=>['de-DE','de']});"
    "Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3]});"
)


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


def _accept_consent(page, verbose, timeout=15):
    """Cookie-/Consent-Dialog wegklicken — pollt bis zu `timeout` s, da der Dialog
    verzögert erscheint."""
    end = time.time() + timeout
    while time.time() < end:
        for sel in CONSENT_SELECTORS:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    el.click(timeout=4000)
                    if verbose:
                        log.info("Coupon-Login: Consent akzeptiert (%s)", sel)
                    time.sleep(1)
                    return True
            except Exception:
                pass
        time.sleep(0.5)
    return False


def _click_text(page, texts):
    # Button kann kurz `disabled` sein → ein paar Anläufe, nur aktive/sichtbare klicken.
    for _ in range(20):
        for t in texts:
            try:
                btn = page.query_selector(f"button:has-text('{t}')")
                if btn and btn.is_visible() and btn.is_enabled():
                    btn.click(timeout=5000)
                    return True
            except Exception:
                pass
        try:
            btn = page.query_selector("button[type=submit]")
            if btn and btn.is_visible() and btn.is_enabled():
                btn.click(timeout=5000)
                return True
        except Exception:
            pass
        time.sleep(0.5)
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
            browser = p.chromium.launch(
                headless=True, executable_path=chromium_path,
                args=["--no-sandbox", "--disable-dev-shm-usage",
                      "--disable-blink-features=AutomationControlled"])
            ctx = browser.new_context(locale="de-DE", user_agent=USER_AGENT,
                                      viewport={"width": 1366, "height": 1600})
            try:
                ctx.add_init_script(_STEALTH_JS)
            except Exception:
                pass
            page = ctx.new_page()
            page.on("response", on_response)

            def _save_debug():
                if debug_png:
                    try:
                        page.screenshot(path=debug_png, full_page=True)
                    except Exception:
                        pass

            def _email_step():
                # Feld ist `type=text`, kommt doppelt vor und ist anfangs `disabled`
                # (erst nach Hydration aktiv) → nur das AKTIVE, sichtbare Feld nehmen.
                email = page.wait_for_selector(
                    "input#email:not([disabled]), input[name='email']:not([disabled]), "
                    "input[type='email']:not([disabled]), "
                    "input[autocomplete='username']:not([disabled])",
                    state="visible", timeout=45000)
                email.click()
                email.fill(user)
                if not _click_text(page, ["Weiter", "Continue"]):
                    try:
                        email.press("Enter")
                    except Exception:
                        pass

            try:
                page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
                time.sleep(2)
                _accept_consent(page, verbose)         # Cookie-Dialog VOR der Eingabe weg
                # Schritt 1 + 2: E-Mail → Passwort. Der Bot-Schutz (Captcha) kann beim
                # ersten „Weiter" fehlschlagen („…Captcha schiefgelaufen, Seite neu laden…").
                # → bis zu 2× neu laden und erneut versuchen.
                pw = None
                for attempt in range(3):
                    _email_step()
                    try:
                        pw = page.wait_for_selector("input[type=password]:not([disabled])",
                                                    state="visible", timeout=20000)
                        break
                    except Exception:
                        pass
                    body = ""
                    try:
                        body = (page.inner_text("body") or "").lower()
                    except Exception:
                        pass
                    if "captcha" in body and attempt < 2:
                        if verbose:
                            log.info("Coupon-Login: Captcha-Fehler → Seite neu laden (Versuch %d)", attempt + 2)
                        page.reload(wait_until="domcontentloaded", timeout=60000)
                        time.sleep(2)
                        _accept_consent(page, verbose)
                        continue
                    break
                if pw is None:
                    _save_debug()
                    body = ""
                    try:
                        body = (page.inner_text("body") or "").lower()
                    except Exception:
                        pass
                    if "captcha" in body:
                        return {"ok": False, "error": "Login vom TUI-Bot-Schutz (Captcha) "
                                "blockiert — automatischer Login ist hier leider nicht möglich. "
                                "Siehe Debug-Screenshot."}
                    return {"ok": False, "error": "Nach der E-Mail kam kein Passwort-Feld "
                            "(evtl. Consent-Banner oder unbekanntes Konto). "
                            "Siehe Debug-Screenshot."}
                pw.click()
                pw.fill(password)
                if not _click_text(page, ["Anmelden", "Einloggen", "Login"]):
                    try:
                        pw.press("Enter")
                    except Exception:
                        pass
                try:
                    page.wait_for_load_state("networkidle", timeout=30000)
                except Exception:
                    pass
                time.sleep(2)
                # Coupon-Seite laden → löst getAccountCoupons aus
                page.goto(COUPONS_URL, wait_until="domcontentloaded", timeout=60000)
                for _ in range(50):                    # bis zu ~25 s auf die API-Antwort warten
                    if "data" in captured:
                        break
                    time.sleep(0.5)
                if "data" not in captured:
                    _save_debug()
                    if page.query_selector("input[type=password]"):
                        return {"ok": False, "error": "Login nicht möglich — Passwort-Feld "
                                "noch aktiv (falsche Daten oder Bot-Schutz/Captcha). "
                                "Siehe Debug-Screenshot."}
                    return {"ok": False, "error": "Coupon-Daten nicht empfangen "
                            "(Session/Seite unerwartet). Siehe Debug-Screenshot."}
                coupons = parse_coupons(captured["data"])
                if verbose:
                    log.info("Coupon-Abruf: %d Coupons empfangen", len(coupons))
                return {"ok": True, "coupons": coupons}
            except Exception as e:
                _save_debug()
                if verbose:
                    log.warning("Coupon-Abruf-Fehler: %s: %s", type(e).__name__, e)
                return {"ok": False, "error": f"{type(e).__name__}: {e} (Debug-Screenshot verfügbar)"}
            finally:
                try:
                    browser.close()
                except Exception:
                    pass
    except Exception as e:
        if verbose:
            log.warning("Coupon-Abruf-Fehler (Browser): %s: %s", type(e).__name__, e)
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
