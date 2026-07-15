#!/usr/bin/env python3
"""Check24-Preisvergleich (andere Reiseveranstalter) für ein gepinntes Hotel.

Anders als tui.com hat Check24 kein offenes JSON-API: die Angebotsseite ist eine
JS-SPA mit asynchronem Job/Poll-Protokoll (`/suche/json/dynamic/offer` +
`/offersearch/<job>/poll`), deren Antworten die eigentlichen Preis-/Zimmerdaten nur
verschlüsselt (`cryptString`) enthalten — das Entschlüsseln findet clientseitig in
Check24s eigenem JS statt. Wir lassen daher einen echten Headless-Chromium (über
Playwright) die Seite rendern und lesen die fertig entschlüsselten Angebotskarten
aus dem sichtbaren Seitentext, statt das Protokoll selbst nachzubauen.

Details/Beispiele zur Seitenstruktur: siehe SCRAPING_CHECK24.md.
"""
import logging
import re
from urllib.parse import parse_qs, urlencode, urlparse

# playwright wird nur für den eigentlichen Abruf gebraucht und erst dort (lazy)
# importiert, damit dieses Modul auch ohne installiertes playwright importierbar
# bleibt (z. B. für die parse_hotel_link()-Tests) — Konvention aus scraper.py.

from scraper import USER_AGENT, BOARD_TYPES  # keine eigene UA-/Verpflegungsliste duplizieren

log = logging.getLogger("tuiwatch.check24")

CONSENT_REMOVE_JS = (
    "document.querySelectorAll('.c24-cookie-consent-wrapper').forEach(e=>e.remove())"
)

_SOLD_OUT_MARK = "schon weg"
_OFFER_BLOCK_RE = re.compile(r"\d+\s*Tage\s*\|\s*\d+\s*Nächte\s")
_PRICE_RE = re.compile(r"([\d.]+,\d{2})\s*€")
_ROOM_RE = re.compile(r"^1x\s+(.+)$", re.MULTILINE)


def parse_hotel_link(url: str) -> dict | None:
    """hotelId+areaId aus einem eingefügten Check24-Hotel-Link
    (z. B. https://urlaub.check24.de/suche/hotel?...&hotelId=11829&areaId=551&...).
    Beide Parameter sind Pflicht, sonst None (Fail-Soft wie scraper._giata_from_url)."""
    try:
        q = parse_qs(urlparse((url or '').strip()).query)
    except Exception:
        return None
    hotel_id = (q.get('hotelId') or [''])[0]
    area_id = (q.get('areaId') or [''])[0]
    if not hotel_id.isdigit() or not area_id.isdigit():
        return None
    return {'hotel_id': hotel_id, 'area_id': area_id}


def _build_hotel_list_url(hotel_id: str, area_id: str, departure_date: str,
                          return_date: str, airport: str, room_allocation: str) -> str:
    params = {
        'airport': airport or '', 'transportType': 'flight',
        'roomAllocation': room_allocation or 'A',
        'departureDate': departure_date, 'returnDate': return_date, 'days': 'exact',
        'pageArea': 'package', 'areaId': area_id, 'dhs': hotel_id, 'ds': 'h',
        'sorting': 'categoryDistribution', 'offerSort': 'offerRanking',
        'areaSort': 'topregion', 'extendedSearch': '1', 'noRedirect': '1',
        'hotelId': hotel_id,
    }
    return 'https://urlaub.check24.de/suche/hotel?' + urlencode(params)


def _parse_offer_blocks(text: str) -> list[dict]:
    """Zerlegt den sichtbaren Seitentext der Ebene-3-Angebotsseite in einzelne
    Angebotskarten (jede beginnt mit einer Zeile wie „12 Tage | 11 Nächte …“) und
    extrahiert Zimmer/Verpflegung/Preis per Regex — analog zu scraper._parse_card(),
    da Check24 keine stabilen, dokumentierten CSS-Klassen für Angebotskarten bietet."""
    starts = [m.start() for m in _OFFER_BLOCK_RE.finditer(text)]
    blocks = [text[a:b] for a, b in zip(starts, starts[1:] + [len(text)])]
    rows = []
    for block in blocks:
        prices = _PRICE_RE.findall(block)
        if not prices:
            continue
        price = float(prices[-1].replace('.', '').replace(',', '.'))
        room_m = _ROOM_RE.search(block)
        room = room_m.group(1).strip() if room_m else ''
        board = ''
        for b in BOARD_TYPES:
            if b in block:
                board = b
                break
        rows.append({
            'room': room, 'board': board, 'price': price,
            'transfer': 'ohne Hotel-Transfer' not in block and 'Hotel-Transfer' in block,
            'ok': True,
        })
    return rows


def fetch_offers(hotel_id: str, area_id: str, departure_date: str, return_date: str,
                 airport: str, *, room_allocation: str = 'A', room_hint: str = '',
                 board_hint: str = '', verbose: bool = False) -> dict | None:
    """Liefert {'ok': bool, 'rows': [...], 'note': str} oder None bei technischem
    Fehler (Aufrufer wiederholt dann, Konvention wie scraper.fetch_price_api()).
    Jede Zeile: {'room','board','price','transfer','ok'} — Anbietername ist auf der
    Ebene der Angebotskarten nicht als Klartext verfügbar (siehe SCRAPING_CHECK24.md,
    „Offener Punkt“), daher aktuell nicht Teil der Zeile."""
    from playwright.sync_api import sync_playwright
    import os
    import time as _time

    list_url = _build_hotel_list_url(hotel_id, area_id, departure_date, return_date,
                                      airport, room_allocation)
    chromium_path = os.environ.get("CHROMIUM_PATH") or None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=chromium_path,
                                        args=["--no-sandbox", "--disable-dev-shm-usage"])
            ctx = browser.new_context(locale="de-DE", user_agent=USER_AGENT,
                                      viewport={"width": 1280, "height": 1400})
            page = ctx.new_page()
            try:
                page.goto(list_url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(9000)
                try:
                    page.evaluate(CONSENT_REMOVE_JS)
                except Exception:
                    pass
                list_text = page.inner_text("body")
                if _SOLD_OUT_MARK in list_text:
                    if verbose:
                        log.info("Check24: Hotel %s an gewünschten Terminen nicht verfügbar", hotel_id)
                    return {'ok': True, 'rows': [], 'note': 'not_available_exact_dates'}

                try:
                    with page.expect_popup(timeout=8000) as pop_info:
                        page.locator("text=zu den Angeboten").first.click(timeout=8000, force=True)
                    detail = pop_info.value
                except Exception:
                    return {'ok': True, 'rows': [], 'note': 'no_offer_link_found'}

                detail.wait_for_load_state("domcontentloaded", timeout=45000)
                detail.wait_for_timeout(12000)
                try:
                    detail.evaluate(CONSENT_REMOVE_JS)
                except Exception:
                    pass
                offer_text = detail.inner_text("body")
            finally:
                browser.close()
    except Exception as e:
        log.warning("Check24-Abruf fehlgeschlagen (hotelId=%s): %s", hotel_id, e)
        return None

    rows = _parse_offer_blocks(offer_text)
    if board_hint:
        bh = board_hint.strip().lower()
        filtered = [r for r in rows if bh in (r['board'] or '').lower()]
        rows = filtered or rows  # kein Treffer beim Filtern → lieber ungefiltert zeigen als leer
    if room_hint:
        rh = room_hint.strip().lower()
        filtered = [r for r in rows if rh in (r['room'] or '').lower()]
        rows = filtered or rows
    rows.sort(key=lambda r: r['price'])
    if not rows:
        return {'ok': True, 'rows': [], 'note': 'no_offers_parsed'}
    return {'ok': True, 'rows': rows, 'note': ''}
