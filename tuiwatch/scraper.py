#!/usr/bin/env python3
"""TUI-Angebotspreis per Headless-Chromium auslesen.

Die TUI-Angebotsseite rendert Preise erst per JavaScript; ein statischer Abruf
liefert nichts. Wir laden die Seite daher mit Playwright/Chromium, klicken den
Cookie-Consent weg und lesen die "Dein Angebot"-Box (div.tui-hotel-best-offer)
aus — das ist das Angebot, das exakt zu den Suchparametern der URL passt
(alles darunter sind Alternativen).

Lokal nutzt Playwright sein gebündeltes Chromium; im Add-on-Container wird das
System-Chromium über die Umgebungsvariable CHROMIUM_PATH gesetzt.
"""
import os
import re
import time
from urllib.parse import unquote, urlparse

from playwright.sync_api import sync_playwright

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# Reihenfolge = Priorität; erster sichtbarer Treffer gewinnt.
CONSENT_SELECTORS = [
    "#cmm-accept-all",
    "button[data-testid='uc-accept-all-button']",
    "#onetrust-accept-btn-handler",
    "button:has-text('Alle akzeptieren')",
    "button:has-text('Akzeptieren')",
    "button:has-text('Zustimmen')",
]

BEST_OFFER_SELECTOR = "div.tui-hotel-best-offer"
HOTEL_NAME_SELECTOR = "h1.tui-hotel-name__title"


def hotel_from_url(url: str) -> str:
    """Fallback-Hotelname aus der URL: …/angebote/Riu-Papayas/2781/… → 'Riu Papayas'."""
    try:
        parts = [p for p in urlparse(url).path.split('/') if p]
        if 'angebote' in parts:
            seg = parts[parts.index('angebote') + 1]
            name = unquote(seg).replace('-', ' ').strip()
            return name if name and not name.isdigit() else ''
    except Exception:
        pass
    return ''

# "pro Person ab 1.933 €" → 1933   (deutsches Format: . = Tausender, , = Dezimal)
_FINAL_RE = re.compile(r"ab\s*([\d.\s]+(?:,\d{2})?)\s*€", re.IGNORECASE)
_ANY_PRICE_RE = re.compile(r"([\d.\s]+(?:,\d{2})?)\s*€")
_DISCOUNT_RE = re.compile(r"-\s*(\d{1,2})\s*%")


def _to_amount(raw: str) -> float | None:
    """'1.933' / '1.933,50' → float. Punkt = Tausender, Komma = Dezimal."""
    s = raw.strip().replace(" ", "").replace("\xa0", "")
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def fetch_price(url: str, *, timeout_ms: int = 60000, verbose: bool = False) -> dict:
    """Liest den 'Dein Angebot'-Preis einer TUI-Angebots-URL.

    Rückgabe (immer ein dict, nie Exception nach außen):
        ok:        bool
        price:     float | None   – Endpreis pro Person (z. B. 1933.0)
        currency:  str            – 'EUR'
        old_price: float | None   – durchgestrichener Vergleichspreis
        discount:  int | None     – Rabatt in % (z. B. 7)
        details:   str            – Reise-Eckdaten (Nächte, Termin, Belegung …)
        note:      str            – Fehler-/Statushinweis
    """
    result = {"ok": False, "price": None, "currency": "EUR", "hotel": "",
              "old_price": None, "discount": None, "details": "", "note": ""}
    chromium_path = os.environ.get("CHROMIUM_PATH") or None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=chromium_path,
                                        args=["--no-sandbox", "--disable-dev-shm-usage"])
            ctx = browser.new_context(locale="de-DE", user_agent=USER_AGENT,
                                      viewport={"width": 1366, "height": 1800})
            page = ctx.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                time.sleep(2)
                for sel in CONSENT_SELECTORS:
                    try:
                        el = page.query_selector(sel)
                        if el and el.is_visible():
                            el.click()
                            if verbose:
                                print(f"[scraper] Consent geklickt: {sel}")
                            break
                    except Exception:
                        pass

                # Auf die Angebots-Box warten
                try:
                    page.wait_for_selector(BEST_OFFER_SELECTOR, timeout=30000)
                except Exception:
                    pass
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass

                # Hotelname (Überschrift oben); Fallback aus der URL
                name_el = page.query_selector(HOTEL_NAME_SELECTOR)
                if name_el:
                    result["hotel"] = (name_el.inner_text() or "").strip()
                if not result["hotel"]:
                    result["hotel"] = hotel_from_url(url)

                box = page.query_selector(BEST_OFFER_SELECTOR)
                if not box:
                    result["note"] = "Angebots-Box nicht gefunden (Layout geändert oder kein Angebot)"
                    return result

                text = box.inner_text() or ""
                m = _FINAL_RE.search(text)
                if not m:
                    result["note"] = "Endpreis ('pro Person ab …') nicht erkannt"
                    return result
                result["price"] = _to_amount(m.group(1))

                # Alter Preis = erster €-Betrag vor dem Endpreis
                head = text[:m.start()]
                old_hits = _ANY_PRICE_RE.findall(head)
                if old_hits:
                    result["old_price"] = _to_amount(old_hits[-1])
                dm = _DISCOUNT_RE.search(text)
                if dm:
                    result["discount"] = int(dm.group(1))

                # Reise-Eckdaten = die Zeilen zwischen Überschrift und Preisblock
                lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
                detail_lines = [ln for ln in lines
                                if "€" not in ln and "%" not in ln
                                and not ln.lower().startswith("dein angebot")]
                result["details"] = " · ".join(detail_lines[:6])

                result["ok"] = result["price"] is not None
                if not result["ok"]:
                    result["note"] = "Preis konnte nicht in Zahl umgewandelt werden"
                return result
            finally:
                browser.close()
    except Exception as e:  # pragma: no cover - Netz/Browser-Fehler
        result["note"] = f"{type(e).__name__}: {e}"[:200]
        return result


if __name__ == "__main__":
    import json
    import sys
    test_url = sys.argv[1] if len(sys.argv) > 1 else (
        "https://www.tui.com/pauschalreisen/suchen/angebote/Riu-Papayas/2781/offer/"
        "?startDate=2027-05-01&endDate=2027-05-30&duration=10&travellers=1"
        "&searchScope=PACKAGE&showTotalPrice=0&regionGiataIds=128"
        "&departureAirports=STR&earlyBird=0&sortOffersAsc=1"
        "&sortOffersField=campaignOffers&roomTypeOpCodes=DZX1"
    )
    print(json.dumps(fetch_price(test_url, verbose=True), ensure_ascii=False, indent=2))
