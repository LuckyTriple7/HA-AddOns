#!/usr/bin/env python3
"""TUI-Angebotspreis per Headless-Chromium auslesen.

Die TUI-Angebotsseite rendert Preise erst per JavaScript; ein statischer Abruf
liefert nichts. Wir laden die Seite mit Playwright/Chromium, klicken den
Cookie-Consent weg und lesen die **erste (= günstigste) Angebotskarte**
(`div.offer-card__content`) aus — das ist der konkrete, buchbare Preis
("Günstigster Preis") inkl. Flugdetails. Optional wird "Verfügbarkeit prüfen"
geklickt, um Verfügbarkeit + bestätigten Gesamtpreis zu erfassen.

Lokal nutzt Playwright sein gebündeltes Chromium; im Add-on-Container wird das
System-Chromium über die Umgebungsvariable CHROMIUM_PATH gesetzt.

Details zur Wartung bei TUI-Layout-Änderungen: siehe SCRAPING.md.
"""
import os
import re
import time
from urllib.parse import unquote, urlparse

from playwright.sync_api import sync_playwright

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

CONSENT_SELECTORS = [
    "#cmm-accept-all",
    "button[data-testid='uc-accept-all-button']",
    "#onetrust-accept-btn-handler",
    "button:has-text('Alle akzeptieren')",
    "button:has-text('Akzeptieren')",
    "button:has-text('Zustimmen')",
]

BEST_OFFER_SELECTOR = "div.tui-hotel-best-offer"   # nur als Lade-Signal
OFFER_CARD_SELECTOR = "div.offer-card__content"    # konkrete Angebote (aufst. sortiert)
HOTEL_NAME_SELECTOR = "h1.tui-hotel-name__title"

_PRICE_RE = re.compile(r"pro Person\s*([\d.\s]+(?:,\d{2})?)\s*€", re.IGNORECASE)
_OLDPRICE_RE = re.compile(r"(\d{1,2})\s*%\s*([\d.\s]+(?:,\d{2})?)\s*€")  # "- 7% 2.129 €"
_TOTAL_RE = re.compile(r"Gesamtpreis\s*([\d.\s]+(?:,\d{2})?)\s*€", re.IGNORECASE)
_AIRPORT_RE = re.compile(r"^.+\([A-Z]{3}\)$")
_ROOMCODE_RE = re.compile(r"\([A-Z]{2,}\d+[A-Z0-9]*\)")          # z. B. (DZX1)
_FLIGHTLINE_RE = re.compile(r"\d{1,2}\.\d{2}\.\d{4},?\s*\d{1,2}:\d{2}")
_NIGHTS_RE = re.compile(r"\d+\s*Nächte")
_TRAVELLERS_RE = re.compile(r"\d+\s*(Erwachsene[r]?|Kind|Kinder)")
BOARD_TYPES = ("Alles Inklusive", "All Inclusive", "Vollpension", "Halbpension",
               "Frühstück", "Übernachtung", "Ohne Verpflegung")


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


def _to_amount(raw: str) -> float | None:
    s = (raw or '').strip().replace(" ", "").replace("\xa0", "")
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _parse_flights(lines: list[str]) -> tuple[str, list[str]]:
    """Liest Abflughafen + bis zu zwei Flug-Legs aus den Kartenzeilen.
    Rückgabe: (abflughafen, [hin, rück]) als lesbare Strings."""
    airport = ''
    for ln in lines[:4]:
        if _AIRPORT_RE.match(ln):
            airport = ln
            break
    legs: list[str] = []
    for i, ln in enumerate(lines):
        if _FLIGHTLINE_RE.search(ln):
            datetime_txt = re.sub(r"\s+", " ", ln).strip()
            airline, stops = '', ''
            for nxt in lines[i + 1:i + 4]:
                if nxt in ('Direktflug',) or 'Stopp' in nxt or 'Umstieg' in nxt or 'Zwischenstopp' in nxt:
                    stops = nxt
                elif not airline and nxt not in BOARD_TYPES and not _FLIGHTLINE_RE.search(nxt) \
                        and 'Flugdetails' not in nxt:
                    airline = nxt
            parts = [datetime_txt] + [x for x in (airline, stops) if x]
            legs.append(" · ".join(parts))
        if len(legs) >= 2:
            break
    return airport, legs


def _parse_card(text: str) -> dict:
    """Extrahiert Preis/Flug/Zimmer-Daten aus dem Text einer Angebotskarte."""
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines() if ln.strip()]
    out: dict = {}

    m = _PRICE_RE.search(text)
    out['price'] = _to_amount(m.group(1)) if m else None
    om = _OLDPRICE_RE.search(text)
    if om:
        out['discount'] = int(om.group(1))
        out['old_price'] = _to_amount(om.group(2))

    # Zimmer = Zeile mit Zimmer-Code (DZX1), nicht der Flughafen
    for ln in lines:
        if _ROOMCODE_RE.search(ln) and not _AIRPORT_RE.match(ln):
            out['room'] = ln
            break
    for ln in lines:
        for b in BOARD_TYPES:
            if ln.startswith(b):
                out['board'] = ln
                break
        if out.get('board'):
            break
    nm = _NIGHTS_RE.search(text)
    out['nights'] = nm.group(0).strip() if nm else ''
    tm = _TRAVELLERS_RE.search(text)
    out['travellers'] = tm.group(0).strip() if tm else ''

    airport, legs = _parse_flights(lines)
    out['dep_airport'] = airport
    out['flight_out'] = legs[0] if len(legs) > 0 else ''
    out['flight_ret'] = legs[1] if len(legs) > 1 else ''
    return out


def fetch_price(url: str, *, timeout_ms: int = 60000, check_availability: bool = True,
                verbose: bool = False) -> dict:
    """Liest den konkreten 'Günstigster Preis' einer TUI-Angebots-URL.

    Rückgabe (immer dict, nie Exception nach außen):
        ok, price, currency, old_price, discount, hotel, room, board, nights,
        travellers, dep_airport, flight_out, flight_ret, details,
        available (bool|None), total_price, note
    """
    r = {"ok": False, "price": None, "currency": "EUR", "old_price": None,
         "discount": None, "hotel": "", "room": "", "board": "", "nights": "",
         "travellers": "", "dep_airport": "", "flight_out": "", "flight_ret": "",
         "details": "", "available": None, "total_price": None, "note": ""}
    chromium_path = os.environ.get("CHROMIUM_PATH") or None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=chromium_path,
                                        args=["--no-sandbox", "--disable-dev-shm-usage"])
            ctx = browser.new_context(locale="de-DE", user_agent=USER_AGENT,
                                      viewport={"width": 1366, "height": 2200})
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

                try:
                    page.wait_for_selector(BEST_OFFER_SELECTOR, timeout=30000)
                except Exception:
                    pass
                try:
                    page.wait_for_selector(OFFER_CARD_SELECTOR, timeout=20000)
                except Exception:
                    pass
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass

                # Hotelname
                name_el = page.query_selector(HOTEL_NAME_SELECTOR)
                r["hotel"] = (name_el.inner_text().strip() if name_el else '') or hotel_from_url(url)

                # Erste Angebotskarte mit Preis (= günstigste, da aufsteigend sortiert)
                card = None
                for el in page.query_selector_all(OFFER_CARD_SELECTOR):
                    try:
                        t = el.inner_text() or ""
                    except Exception:
                        continue
                    if "pro Person" in t and "€" in t:
                        card = el
                        break
                if not card:
                    r["note"] = "Keine Angebotskarte gefunden (Layout geändert oder kein Angebot)"
                    return r

                parsed = _parse_card(card.inner_text())
                r.update({k: parsed.get(k, r[k]) for k in
                          ("price", "old_price", "discount", "room", "board",
                           "nights", "travellers", "dep_airport", "flight_out", "flight_ret")})
                if r["price"] is None:
                    r["note"] = "Preis ('pro Person …') nicht erkannt"
                    return r

                # Lesbare Kurzbeschreibung
                r["details"] = " · ".join(x for x in (
                    r["nights"], r["travellers"], r["room"], r["board"],
                    (f"ab {r['dep_airport']}" if r['dep_airport'] else "")) if x)

                # Verfügbarkeit prüfen (optional)
                if check_availability:
                    try:
                        avail_btn = card.query_selector("button:has-text('Verfügbarkeit')")
                        if avail_btn:
                            avail_btn.click()
                            # auf Ergebnis warten
                            deadline = time.time() + 25
                            while time.time() < deadline:
                                ct = card.inner_text() or ""
                                if "verfügbar" in ct.lower() or "Gesamtpreis" in ct \
                                        or "nicht verfügbar" in ct.lower():
                                    break
                                time.sleep(1)
                            ct = card.inner_text() or ""
                            if "nicht verfügbar" in ct.lower():
                                r["available"] = False
                            elif "verfügbar" in ct.lower() or "Gesamtpreis" in ct:
                                r["available"] = True
                            tm = _TOTAL_RE.search(ct)
                            if tm:
                                r["total_price"] = _to_amount(tm.group(1))
                            if verbose:
                                print(f"[scraper] Verfügbarkeit={r['available']} total={r['total_price']}")
                    except Exception as e:
                        if verbose:
                            print(f"[scraper] Verfügbarkeitsprüfung fehlgeschlagen: {e}")

                r["ok"] = True
                return r
            finally:
                browser.close()
    except Exception as e:  # pragma: no cover
        r["note"] = f"{type(e).__name__}: {e}"[:200]
        return r


if __name__ == "__main__":
    import json
    import sys
    test_url = sys.argv[1] if len(sys.argv) > 1 else (
        "https://www.tui.com/pauschalreisen/suchen/angebote/Riu-Papayas/2781/offer/"
        "?startDate=2027-05-01&endDate=2027-05-30&duration=10&travellers=1"
        "&searchScope=PACKAGE&showTotalPrice=0&regionGiataIds=128"
        "&departureAirports=STR&earlyBird=0&sortOffersAsc=1"
        "&sortOffersField=campaignOffers&roomTypeOpCodes=DZX1")
    print(json.dumps(fetch_price(test_url, verbose=True), ensure_ascii=False, indent=2))
