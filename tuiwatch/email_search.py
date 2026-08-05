#!/usr/bin/env python3
"""HTML-Mail-Aufbau für Hotelsuchen-Trefferlisten (Region-Suche) — bewusst
getrennt von app.py's `_email_html_offers()` (die getrackten Angebote aus der
DB): Suchtreffer haben eine andere Datenform und kommen frisch vom Frontend
(bereits abgerufene `/api/search`-Ergebnisse, ggf. per Checkbox vorgefiltert),
nicht aus der eigenen DB — app.py soll dafür nicht weiter wachsen."""
from datetime import datetime

import app as A  # später Attributzugriff (A._eur/A.log), zyklenfrei wie in *_routes.py


def _criteria_text(criteria: dict, esc) -> str:
    """Reisendenzahl und Abflughafen für die Kopfzeile. Beides sind Suchparameter
    und stehen in keiner einzelnen Trefferzeile — ohne diese Angabe ließ sich einer
    verschickten Liste nicht ansehen, für wie viele Personen und ab welchem Flughafen
    die Preise gelten (und pro Person ist nicht pro Buchung)."""
    if not isinstance(criteria, dict):
        return ''
    parts = []
    try:
        n = int(criteria.get('travellers') or 0)
    except (TypeError, ValueError):
        n = 0
    if n:
        parts.append('1 Reisender' if n == 1 else f'{n} Reisende')
    # `airport_label` kommt aus dem Auswahlfeld der Suchmaske („Stuttgart (STR)"),
    # `airports` sind die reinen IATA-Codes aus der Such-URL — Klarname bevorzugt.
    label = (criteria.get('airport_label') or '').strip()
    codes = [str(a).strip() for a in (criteria.get('airports') or []) if str(a).strip()]
    if label:
        parts.append(f'ab {label}')
    elif codes:
        parts.append('ab ' + ', '.join(codes))
    return ' · '.join(esc(p) for p in parts)


def html_for_rows(rows: list[dict], *, dest: str = '', criteria: dict | None = None) -> str:
    """Baut eine HTML-Mail aus Suchtreffer-Zeilen (Form wie von `/api/search`
    geliefert: name, location, country, stars, recommendation, reviews, price,
    old_price, discount, board, nights, date, offer_url, ...). `criteria` trägt die
    Suchparameter, die in keiner Zeile stehen (Reisende, Abflughafen) — sie landen in
    der Kopfzeile. Zeilen kommen vom Client, daher werden alle Textfelder escaped
    (kein Vertrauen in Fremddaten für HTML-Ausgabe)."""
    def esc(s):
        return (str(s or '')).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    cards = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        price = A._eur(r.get('price')) if r.get('price') is not None else '–'
        try:
            stars = '★' * int(round(float(r['stars']))) if r.get('stars') else ''
        except (TypeError, ValueError):
            stars = ''
        sub = ''
        if r.get('old_price') and r.get('price') and r['old_price'] > r['price']:
            sub = (f'<span style="text-decoration:line-through;color:#888">{A._eur(r["old_price"])}</span>'
                   + (f' −{esc(r["discount"])}%' if r.get('discount') else ''))
        meta = ' · '.join(esc(x) for x in (
            r.get('board'),
            (f"{r['nights']} Nächte" if r.get('nights') else ''),
            (f"ab {r['date']}" if r.get('date') else ''),
        ) if x)
        rec = ''
        if r.get('recommendation') is not None:
            rec = (f'{esc(r["recommendation"])}% 👍'
                   + (f' ({esc(r["reviews"])})' if r.get('reviews') else ''))
        link = (f'<a href="{esc(r.get("offer_url") or "")}" '
                f'style="color:#0b65d8;text-decoration:none;font-weight:600">Auf tui.com ansehen ↗</a>'
                if r.get('offer_url') else '')
        title = esc(r.get('name') or 'Hotel')
        loc_parts = [x for x in (r.get('location'), r.get('country')) if x]
        cards.append(
            '<tr><td style="padding:0 0 14px">'
            '<table width="100%" cellpadding="0" cellspacing="0" style="background:#fff;'
            'border:1px solid #e2e6ea;border-radius:10px;border-collapse:separate">'
            '<tr><td style="padding:14px 16px">'
            f'<div style="font-size:17px;font-weight:700;color:#10243e">{title} '
            f'<span style="color:#d29922">{stars}</span></div>'
            + (f'<div style="font-size:13px;color:#0b65d8">📍 {esc(", ".join(loc_parts))}</div>' if loc_parts else '')
            + (f'<div style="font-size:13px;color:#555;margin-top:3px">{meta}</div>' if meta else '')
            + (f'<div style="font-size:12px;color:#777;margin-top:3px">{rec}</div>' if rec else '')
            + '<div style="margin-top:10px">'
            f'<span style="font-size:24px;font-weight:800;color:#10243e">{price}</span>'
            ' <span style="font-size:12px;color:#777">pro Person</span></div>'
            + (f'<div style="font-size:13px;color:#777">{sub}</div>' if sub else '')
            + (f'<div style="margin-top:10px;font-size:14px">{link}</div>' if link else '')
            + '</td></tr></table></td></tr>'
        )
    now = datetime.now().strftime('%d.%m.%Y %H:%M')
    crit = _criteria_text(criteria or {}, esc)
    hdr = (f'Hotelsuche{" · " + esc(dest) if dest else ""}'
           + (f' · {crit}' if crit else '') + f' · Stand {now}')
    return (
        '<div style="background:#eef2f8;padding:20px 0;font-family:-apple-system,Segoe UI,Roboto,sans-serif">'
        '<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">'
        '<table width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%">'
        '<tr><td style="padding:0 16px 16px">'
        '<div style="font-size:22px;font-weight:800;color:#0b65d8">✈ TUIWatch</div>'
        f'<div style="font-size:13px;color:#666">{hdr}</div>'
        '</td></tr>'
        f'<tr><td style="padding:0 16px"><table width="100%" cellpadding="0" cellspacing="0">{"".join(cards)}</table></td></tr>'
        '<tr><td style="padding:10px 16px 0;font-size:11px;color:#99a">Generiert von '
        '<a href="https://github.com/LuckyTriple7/HA-AddOns" style="color:#0b65d8;text-decoration:none">TUIWatch</a>'
        ', einer App für Home Assistant · '
        '<a href="https://github.com/LuckyTriple7/HA-AddOns" style="color:#0b65d8;text-decoration:none">github.com/LuckyTriple7/HA-AddOns</a>'
        '</td></tr>'
        '</table></td></tr></table></div>'
    )
