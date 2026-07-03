"""Öffentliche TUI-Aktionscodes von https://www.tui.com/aktionscode/ auslesen.

Kein Login, kein Browser, kein Captcha — die Seite liefert die aktiven Codes
server-seitig im HTML (z. B. `ACMYTUI30020260702` = 300 €, Datum 2026-07-02).
`parse_aktionscodes` ist rein und ohne Netz testbar.
"""
import logging
import re

import requests

log = logging.getLogger("tuiwatch")

AKTIONSCODE_URL = "https://www.tui.com/aktionscode/"
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "de-DE,de;q=0.9",
}
# myTUI-Codes: ACMYTUI<Wert><YYYYMMDD> (z. B. ACMYTUI30020260702 → 300 €, 2026-07-02).
# Ohne-Konto-Codes: SAVE<Wert> (z. B. SAVE250, SAVE125).
_CODE_MYTUI_RE = re.compile(r"ACMYTUI(\d+?)(20\d{6})\b")
_CODE_SAVE_RE = re.compile(r"\bSAVE(\d{2,4})\b")
_DATE_RE = r"(\d{2}\.\d{2}\.\d{4})"


def _clean(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or ""))


def parse_aktionscodes(html: str) -> dict:
    """Aktive Aktionscodes + Kontext aus dem HTML ziehen. Rückgabe:
    {codes: [{code, value, kind}], booking_until, travel_period} — je Wert/Art nur einmal."""
    by_key: dict = {}
    for m in _CODE_MYTUI_RE.finditer(html or ""):
        try:
            value = int(m.group(1))
        except ValueError:
            continue
        by_key.setdefault(("mytui", value),
                          {"code": m.group(0), "value": value, "kind": "myTUI"})
    text = _clean(html)
    for m in _CODE_SAVE_RE.finditer(text):
        try:
            value = int(m.group(1))
        except ValueError:
            continue
        by_key.setdefault(("save", value),
                          {"code": m.group(0), "value": value, "kind": "ohne Konto"})
    codes = [by_key[k] for k in sorted(by_key, key=lambda k: (-k[1], k[0]))]

    # Kontext (best effort — fehlt es, bleibt es leer, Codes funktionieren trotzdem)
    booking_until = ""
    mb = re.search(r"(?:Aktionszeitraum|Buchungszeitraum)[^;]*?bis\s*" + _DATE_RE, text, re.I)
    if mb:
        booking_until = mb.group(1)
    travel_period = ""
    mt = re.search(r"Reisezeitraum\s*vom\s*(\d{2}\.\d{2}\.)\s*bis\s*" + _DATE_RE, text, re.I)
    if mt:
        travel_period = f"{mt.group(1)}–{mt.group(2)}"
    return {"codes": codes, "booking_until": booking_until, "travel_period": travel_period}


def fetch_aktionscodes(*, verbose: bool = False) -> dict:
    """Lädt die Aktionscode-Seite und wertet sie aus.
    Rückgabe: {'ok': True, 'codes': [...], 'booking_until': .., 'travel_period': ..}
    oder {'ok': False, 'error': '…'}."""
    try:
        r = requests.get(AKTIONSCODE_URL, headers=_HEADERS, timeout=20)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    if r.status_code != 200:
        return {"ok": False, "error": f"HTTP {r.status_code}"}
    parsed = parse_aktionscodes(r.text)
    if verbose:
        log.info("Aktionscodes: %d gefunden (%s) buchbar_bis=%s",
                 len(parsed["codes"]),
                 ", ".join(f"{c['value']}€" for c in parsed["codes"]) or "keine",
                 parsed["booking_until"] or "-")
    return {"ok": True, **parsed}
