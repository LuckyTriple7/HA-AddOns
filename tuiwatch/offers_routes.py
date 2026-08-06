"""Angebots-, Verlauf-, Vergleichs-, Such-, Reiseziel- und Zimmer-Routen —
ausgelagert aus app.py
(Backlog #12, 3. Tranche). Geteilte Primitiven über `import app as A` mit
spätem Attribut-Zugriff (monkeypatch-sicher, zyklenfrei).
"""
import csv
import io
import json
import os
import sqlite3
import threading
import re
import time
from datetime import date, datetime, timedelta

from urllib.parse import parse_qsl, urlparse

from flask import Blueprint, jsonify, make_response, request

import app as A
import check24_client
import email_search

bp = Blueprint('offers_routes', __name__)


@bp.route('/api/offers', methods=['GET'])
def api_offers():
    if (err := A._require_api()):
        return err
    return jsonify({'offers': A._collect_offers()})


def _normalize_tags(raw) -> list[str]:
    """Trimmt, verwirft Leere und dedupliziert eine Tag-Liste (Reihenfolge bleibt)."""
    if not isinstance(raw, list):
        return []
    seen = set()
    tags = []
    for t in raw:
        t = str(t).strip()
        if t and t not in seen:
            seen.add(t)
            tags.append(t)
    return tags


def _valid_tui_url(url: str) -> bool:
    try:
        p = urlparse(url)
    except Exception:
        return False
    return p.scheme in ('http', 'https') and p.hostname is not None \
        and (p.hostname == 'tui.com' or p.hostname.endswith('.tui.com'))


@bp.route('/api/offers', methods=['POST'])
def api_add_offer():
    if (err := A._require_api()):
        return err
    data = request.get_json(silent=True) or {}
    url = (data.get('url') or '').strip()
    label = (data.get('label') or '').strip()
    if not _valid_tui_url(url):
        return jsonify({'error': 'invalid_url'}), 400
    img = (data.get('image') or '').strip()      # optional: Bild aus der Suche
    if not A._valid_img_url(img):
        img = ''
    history_only = 1 if data.get('history_only') else 0
    tags = _normalize_tags(data.get('tags'))
    tags_json = json.dumps(tags, ensure_ascii=False) if tags else ''
    try:
        with A.db() as con:
            cur = con.execute(
                'INSERT INTO offers (url, label, hotel, details, image_url, history_only, tags, created) '
                'VALUES (?,?,?,?,?,?,?,?)',
                (url, label, A.hotel_from_url(url), '', img, history_only, tags_json, int(time.time())))
            offer_id = cur.lastrowid
    except sqlite3.IntegrityError:
        return jsonify({'error': 'duplicate'}), 409
    A.log.info("Neues Angebot #%d hinzugefügt: %s", offer_id,
             label or A.hotel_from_url(url) or url)
    # start:false (nur vom Zimmerauswahl-Flow in der Suche genutzt) verzögert die
    # erste Prüfung bis zur Zimmerwahl/-bestätigung (POST /api/offers/<id>/start
    # oder POST /api/rooms/<id>) — sonst würde sofort das (u. U. falsche) Zimmer
    # aus dem Such-Ergebnis getrackt, bevor der Nutzer wählen konnte.
    start = data.get('start', True)
    if start:
        A._spawn(A.check_offer, offer_id)  # sofort einmal prüfen
    return jsonify({'id': offer_id, 'started': bool(start)})


@bp.route('/api/offers/<int:offer_id>/start', methods=['POST'])
def api_start_offer(offer_id: int):
    """Startet die erste Prüfung eines mit start:false angelegten Angebots (siehe
    api_add_offer) — z. B. wenn der Nutzer die Zimmerauswahl ohne explizite Wahl
    schließt (dann mit dem ursprünglichen Zimmer aus der Suche getrackt)."""
    if (err := A._require_api()):
        return err
    with A.db() as con:
        if not con.execute('SELECT 1 FROM offers WHERE id=?', (offer_id,)).fetchone():
            return jsonify({'error': 'not_found'}), 404
    A._spawn(A.check_offer, offer_id)
    return jsonify({'started': True})


@bp.route('/api/offers/<int:offer_id>', methods=['DELETE'])
def api_delete_offer(offer_id: int):
    if (err := A._require_api()):
        return err
    with A.db() as con:
        con.execute('DELETE FROM price_history WHERE offer_id=?', (offer_id,))
        con.execute('DELETE FROM compare_cache WHERE offer_id=?', (offer_id,))
        con.execute('DELETE FROM calendar_cache WHERE offer_id=?', (offer_id,))
        con.execute('DELETE FROM calendar_history WHERE offer_id=?', (offer_id,))
        con.execute('DELETE FROM nights_cache WHERE offer_id=?', (offer_id,))
        con.execute('DELETE FROM check24_cache WHERE offer_id=?', (offer_id,))
        con.execute('DELETE FROM cheaper_state WHERE offer_id=?', (offer_id,))
        con.execute('DELETE FROM booked_state WHERE offer_id=?', (offer_id,))
        con.execute('DELETE FROM offer_events WHERE offer_id=?', (offer_id,))
        con.execute('DELETE FROM offers WHERE id=?', (offer_id,))
    A._cheaper_notified.pop(offer_id, None)
    A._fail_notified.discard(offer_id)
    A._vac_notified.discard(offer_id)
    A.log.info("Angebot #%d gelöscht", offer_id)
    A.push_ha_sensors()  # entfernt verwaisten Sensor + nummeriert ggf. neu
    return jsonify({'deleted': offer_id})


@bp.route('/api/offers/<int:offer_id>', methods=['PATCH'])
def api_update_offer(offer_id: int):
    if (err := A._require_api()):
        return err
    data = request.get_json(silent=True) or {}
    events = []  # (type, text) → nach dem A.db-Block protokollieren (Marker im Verlauf)
    with A.db() as con:
        if 'label' in data:
            lbl = (data.get('label') or '').strip()
            con.execute('UPDATE offers SET label=? WHERE id=?', (lbl, offer_id))
            A.log.info("Angebot #%d umbenannt: %s", offer_id, lbl or '(Hotelname)')
        if 'target_price' in data:
            tp = data.get('target_price')
            try:
                tp = float(tp) if tp not in (None, '', 0) else None
            except (TypeError, ValueError):
                tp = None
            con.execute('UPDATE offers SET target_price=? WHERE id=?', (tp, offer_id))
            A.log.info("Wunschpreis #%d %s", offer_id,
                     f"gesetzt: {tp:.0f} €" if tp else "entfernt")
            if tp:
                events.append(('target', f"Wunschpreis {A._eur(tp)}"))
        if 'booked_price' in data:
            bp = data.get('booked_price')
            try:
                bp = float(bp) if bp not in (None, '', 0) else None
            except (TypeError, ValueError):
                bp = None
            con.execute('UPDATE offers SET booked_price=? WHERE id=?', (bp, offer_id))
            if bp is None:  # Buchung zurückgenommen → Alarm-Dedup zurücksetzen
                con.execute('DELETE FROM booked_state WHERE offer_id=?', (offer_id,))
            A.log.info("Gebuchter Preis #%d %s", offer_id,
                     f"gesetzt: {bp:.0f} €" if bp else "entfernt")
            if bp:
                events.append(('booked', f"Gebucht für {A._eur(bp)}"))
        if 'paused' in data:
            con.execute('UPDATE offers SET paused=? WHERE id=?',
                        (1 if data.get('paused') else 0, offer_id))
            A.log.info("Angebot #%d %s", offer_id,
                     "pausiert" if data.get('paused') else "fortgesetzt")
        if 'archived' in data:
            arch = 1 if data.get('archived') else 0
            con.execute('UPDATE offers SET archived=? WHERE id=?', (arch, offer_id))
            A.log.info("Angebot #%d %s", offer_id,
                     "archiviert" if arch else "reaktiviert")
        if 'notify_muted' in data:
            con.execute('UPDATE offers SET notify_muted=? WHERE id=?',
                        (1 if data.get('notify_muted') else 0, offer_id))
            A.log.info("Angebot #%d Benachrichtigungen %s", offer_id,
                     "stummgeschaltet" if data.get('notify_muted') else "aktiviert")
        if 'notify_calendar_muted' in data:
            con.execute('UPDATE offers SET notify_calendar_muted=? WHERE id=?',
                        (1 if data.get('notify_calendar_muted') else 0, offer_id))
            A.log.info("Angebot #%d Kalender-Benachrichtigungen %s", offer_id,
                     "stummgeschaltet" if data.get('notify_calendar_muted') else "aktiviert")
        if 'transfer_included' in data:
            # Manche Hotels (Selbstanreise-Regionen) bieten kein Transfer-Paket — dort
            # liefert die Offer-API bei transferIncluded=true 0 Treffer/Zimmer, obwohl
            # auf tui.com buchbare Angebote existieren. Steht als URL-Parameter fest,
            # wirkt daher automatisch auch auf die reguläre Preisprüfung (nicht nur die
            # Zimmerauswahl).
            ti = bool(data.get('transfer_included'))
            row = con.execute('SELECT url FROM offers WHERE id=?', (offer_id,)).fetchone()
            if not row:
                return jsonify({'error': 'not_found'}), 404
            new_url = A.with_transfer_included(row['url'], ti)
            try:
                con.execute('UPDATE offers SET url=? WHERE id=?', (new_url, offer_id))
            except sqlite3.IntegrityError:
                return jsonify({'error': 'duplicate',
                                'note': 'Dieses Angebot (mit/ohne Transfer) wird bereits verfolgt'}), 409
            A.log.info("Angebot #%d: Transfer %s", offer_id, 'inklusive' if ti else 'ohne')
            events.append(('transfer', f"Transfer {'inklusive' if ti else 'ohne'}"))
        if 'tags' in data:
            tags = _normalize_tags(data.get('tags'))
            con.execute('UPDATE offers SET tags=? WHERE id=?',
                        (json.dumps(tags, ensure_ascii=False), offer_id))
            A.log.info("Angebot #%d Tags gesetzt: %s", offer_id, ', '.join(tags) or '(keine)')
        if 'check24_hotel_id' in data:
            # Normalfall: Klick auf einen Treffer aus der automatischen Hotelsuche
            # (siehe GET /api/check24/search) — hotel_id kommt direkt vom Frontend,
            # kein Link-Parsing nötig.
            hid = str(data.get('check24_hotel_id') or '').strip()
            if not hid:
                con.execute("UPDATE offers SET check24_hotel_id='', check24_link='' WHERE id=?",
                            (offer_id,))
                con.execute('DELETE FROM check24_cache WHERE offer_id=?', (offer_id,))
                A.log.info("Check24-Verknüpfung #%d entfernt", offer_id)
            elif not hid.isdigit():
                return jsonify({'error': 'invalid_check24_hotel_id'}), 400
            else:
                name = (data.get('check24_hotel_name') or '').strip()
                con.execute('UPDATE offers SET check24_hotel_id=?, check24_link=? WHERE id=?',
                            (hid, f'https://urlaub.check24.de/suche/hotel?hotelId={hid}', offer_id))
                con.execute('DELETE FROM check24_cache WHERE offer_id=?', (offer_id,))
                A.log.info("Check24-Hotel #%d verknüpft: hotelId=%s (%s)", offer_id, hid, name)
            with A._check24_lock:
                A._check24_state.pop(offer_id, None)
        elif 'check24_link' in data:
            # Fallback für Power-User: Check24-Link direkt einfügen (falls die
            # automatische Suche das Hotel nicht findet).
            link = (data.get('check24_link') or '').strip()
            if not link:
                con.execute("UPDATE offers SET check24_hotel_id='', check24_link='' WHERE id=?",
                            (offer_id,))
                con.execute('DELETE FROM check24_cache WHERE offer_id=?', (offer_id,))
                A.log.info("Check24-Verknüpfung #%d entfernt", offer_id)
            else:
                parsed = check24_client.parse_hotel_link(link)
                if not parsed:
                    return jsonify({'error': 'invalid_check24_url'}), 400
                con.execute('UPDATE offers SET check24_hotel_id=?, check24_link=? WHERE id=?',
                            (parsed['hotel_id'], link, offer_id))
                con.execute('DELETE FROM check24_cache WHERE offer_id=?', (offer_id,))
                A.log.info("Check24-Hotel #%d verknüpft: hotelId=%s", offer_id, parsed['hotel_id'])
            with A._check24_lock:
                A._check24_state.pop(offer_id, None)
    for t, txt in events:
        A._log_event(offer_id, t, txt)
    if 'archived' in data:
        A.push_ha_sensors()  # Übersicht/Summary-Sensor neu berechnen
    if 'transfer_included' in data:
        A._spawn(A.check_offer, offer_id)
    return jsonify({'id': offer_id, 'ok': True})


@bp.route('/api/history/<int:offer_id>', methods=['GET'])
def api_history(offer_id: int):
    if (err := A._require_api()):
        return err
    with A.db() as con:
        rows = con.execute(
            'SELECT ts, price, old_price, discount, ok, note, '
            'price_hotel, price_flight_out, price_flight_ret, vac_ok FROM price_history '
            'WHERE offer_id=? ORDER BY ts', (offer_id,)).fetchall()
        events = con.execute(
            'SELECT ts, type, text FROM offer_events WHERE offer_id=? ORDER BY ts',
            (offer_id,)).fetchall()
    return jsonify({'history': [dict(r) for r in rows],
                    'events': [dict(e) for e in events]})


@bp.route('/api/history/<int:offer_id>/A.csv', methods=['GET'])
def api_history_csv(offer_id: int):
    if (err := A._require_api()):
        return err
    with A.db() as con:
        offer = con.execute('SELECT hotel, label FROM offers WHERE id=?', (offer_id,)).fetchone()
        rows = con.execute(
            'SELECT ts, price, old_price, discount, available, ok, note, '
            'price_hotel, price_flight_out, price_flight_ret FROM price_history '
            'WHERE offer_id=? ORDER BY ts', (offer_id,)).fetchall()
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=';')
    w.writerow(['Zeitpunkt', 'Preis (EUR)', 'Vergleichspreis (EUR)', 'Rabatt %',
                'Verfuegbar', 'OK', 'Hinweis',
                'Hotel (EUR)', 'Hinflug (EUR)', 'Rueckflug (EUR)'])
    for r in rows:
        avail = '' if r['available'] is None else ('ja' if r['available'] else 'nein')
        w.writerow([datetime.fromtimestamp(r['ts']).strftime('%Y-%m-%d %H:%M:%S'),
                    '' if r['price'] is None else int(round(r['price'])),
                    '' if r['old_price'] is None else int(round(r['old_price'])),
                    r['discount'] if r['discount'] is not None else '',
                    avail, 'ja' if r['ok'] else 'nein', (r['note'] or '').replace('\n', ' '),
                    '' if r['price_hotel'] is None else int(round(r['price_hotel'])),
                    '' if r['price_flight_out'] is None else int(round(r['price_flight_out'])),
                    '' if r['price_flight_ret'] is None else int(round(r['price_flight_ret']))])
    name = A._slug((offer['label'] or offer['hotel']) if offer else '') or f'angebot_{offer_id}'
    resp = make_response('﻿' + buf.getvalue())  # BOM → Umlaute in Excel korrekt
    resp.headers['Content-Type'] = 'text/A.csv; charset=utf-8'
    resp.headers['Content-Disposition'] = f'attachment; filename="tuiwatch_{name}.csv"'
    return resp


@bp.route('/api/check/<int:offer_id>', methods=['POST'])
def api_check_one(offer_id: int):
    if (err := A._require_api()):
        return err
    A.log.info("Manuelle Prüfung angefordert: Angebot #%d", offer_id)
    A._spawn(A.check_offer, offer_id)
    return jsonify({'started': True})


@bp.route('/api/reset/<int:offer_id>', methods=['POST'])
def api_reset_offer(offer_id: int):
    """Setzt ein Angebot zurück: löscht Preisverlauf + Vergleichs-/Kalender-Cache und
    startet eine frische Erstabfrage. Angebot selbst (URL, Name, Wunschpreis) bleibt."""
    if (err := A._require_api()):
        return err
    with A.db() as con:
        if not con.execute('SELECT 1 FROM offers WHERE id=?', (offer_id,)).fetchone():
            return jsonify({'error': 'not_found'}), 404
        con.execute('DELETE FROM price_history WHERE offer_id=?', (offer_id,))
        con.execute('DELETE FROM compare_cache WHERE offer_id=?', (offer_id,))
        con.execute('DELETE FROM calendar_cache WHERE offer_id=?', (offer_id,))
        con.execute('DELETE FROM calendar_history WHERE offer_id=?', (offer_id,))
        con.execute('DELETE FROM nights_cache WHERE offer_id=?', (offer_id,))
        con.execute('DELETE FROM check24_cache WHERE offer_id=?', (offer_id,))
        con.execute('DELETE FROM cheaper_state WHERE offer_id=?', (offer_id,))
        con.execute('DELETE FROM booked_state WHERE offer_id=?', (offer_id,))
        con.execute('DELETE FROM offer_events WHERE offer_id=?', (offer_id,))
    A._log_event(offer_id, 'reset', 'Tracking zurückgesetzt')
    with A._compare_lock:
        A._compare_state.pop(offer_id, None)
    with A._calendar_lock:
        A._calendar_state.pop(offer_id, None)
    with A._nights_lock:
        A._nights_state.pop(offer_id, None)
    with A._check24_lock:
        A._check24_state.pop(offer_id, None)
    A._cheaper_notified.pop(offer_id, None)
    A._fail_notified.discard(offer_id)
    A._vac_notified.discard(offer_id)
    A.log.info("Angebot #%d zurückgesetzt (Verlauf + Caches gelöscht)", offer_id)
    A._spawn(A.check_offer, offer_id)  # frische Erstabfrage
    return jsonify({'reset': offer_id, 'started': True})


@bp.route('/api/check-now', methods=['POST'])
def api_check_now():
    if (err := A._require_api()):
        return err
    if (remaining := A._cooldown_remaining('check_now', 60)):
        return jsonify({'error': 'cooldown', 'retry_after': remaining}), 429
    A._spawn(A.check_all, 'manuell')
    return jsonify({'started': True})


@bp.route('/api/email', methods=['GET', 'POST'])
def api_email():
    if (err := A._require_api()):
        return err
    if request.method == 'GET':  # UI fragt Status/Vorbelegung ab
        return jsonify({'configured': A.smtp_configured(),
                        'default_to': (A.load_config().get('smtp_to') or '').strip()})
    if not A.smtp_configured():
        return jsonify({'error': 'smtp_not_configured'}), 400
    data = request.get_json(silent=True) or {}
    to = (data.get('to') or A.load_config().get('smtp_to') or '').strip()
    if not to:
        return jsonify({'error': 'no_recipient'}), 400
    offers = [o for o in A._collect_offers() if not o.get('archived')]
    # Optional: nur eine Auswahl versenden (Sammelaktion über die Checkboxen)
    ids = data.get('ids')
    if isinstance(ids, list) and ids:
        want = {int(i) for i in ids if str(i).isdigit()}
        offers = [o for o in offers if o['id'] in want]
    if not offers:
        return jsonify({'error': 'no_offers'}), 400
    html = A._email_html_offers(offers)
    subject = f"TUIWatch – {len(offers)} Reisepreise ({datetime.now().strftime('%d.%m.%Y')})"
    try:
        A.send_email(subject, html, to)
    except Exception as e:
        A.log.error("E-Mail-Versand fehlgeschlagen: %s", e)  # Detail nur ins Log
        return jsonify({'error': 'send_failed'}), 502
    A.log.info("Angebots-E-Mail an %s gesendet (%d Angebote)", to, len(offers))
    return jsonify({'sent': True, 'to': to, 'count': len(offers)})


@bp.route('/api/search/email', methods=['POST'])
def api_search_email():
    """Versendet eine Hotelsuchen-Trefferliste per E-Mail — die Zeilen kommen vom
    Frontend (bereits geladene `/api/search`-Ergebnisse, ggf. per Checkbox auf
    eine Auswahl reduziert), nicht aus der DB (Suchtreffer werden nicht
    persistiert)."""
    if (err := A._require_api()):
        return err
    if not A.smtp_configured():
        return jsonify({'error': 'smtp_not_configured'}), 400
    data = request.get_json(silent=True) or {}
    to = (data.get('to') or A.load_config().get('smtp_to') or '').strip()
    if not to:
        return jsonify({'error': 'no_recipient'}), 400
    rows = data.get('results')
    if not isinstance(rows, list) or not rows:
        return jsonify({'error': 'no_results'}), 400
    rows = rows[:100]  # Schutz gegen versehentlich riesige Mails
    crit = data.get('criteria')
    html = email_search.html_for_rows(rows, dest=(data.get('dest') or '').strip(),
                                      criteria=crit if isinstance(crit, dict) else None)
    subject = f"TUIWatch – {len(rows)} Hotel-Treffer ({datetime.now().strftime('%d.%m.%Y')})"
    try:
        A.send_email(subject, html, to)
    except Exception as e:
        A.log.error("Such-Treffer-E-Mail-Versand fehlgeschlagen: %s", e)
        return jsonify({'error': 'send_failed'}), 502
    A.log.info("Such-Treffer-E-Mail an %s gesendet (%d Treffer)", to, len(rows))
    return jsonify({'sent': True, 'to': to, 'count': len(rows)})


_HISTORY_COLS = ('ts', 'price', 'old_price', 'discount', 'available', 'ok', 'note')
_EVENT_COLS = ('ts', 'type', 'text')
# Feste Whitelist der beim Restore einspielbaren Angebots-Spalten (Spaltennamen kommen
# damit NIE aus den Backup-Daten → keine per String gebaute Query aus Nutzerquellen).
_OFFER_RESTORE_COLS = (
    'url', 'label', 'hotel', 'details', 'room', 'board', 'dep_airport', 'flight_out', 'flight_ret',
    'location', 'city', 'region', 'country', 'pdf_url', 'cancellation', 'stars', 'rating',
    'rating_count', 'recommendation', 'total_price', 'travellers_count', 'paused',
    'archived', 'return_date', 'target_price', 'booked_price', 'image_url', 'booking_code',
    'room_booking_code', 'tags', 'check24_hotel_id', 'check24_area_id', 'check24_link', 'created',
)


@bp.route('/api/compare/<int:offer_id>', methods=['POST'])
def api_compare_start(offer_id: int):
    if (err := A._require_api()):
        return err
    with A._compare_lock:
        if A._compare_state.get(offer_id, {}).get('status') == 'running':
            return jsonify({'started': True, 'already': True})
    with A.db() as con:
        o = con.execute('SELECT room, details FROM offers WHERE id=?', (offer_id,)).fetchone()
    if not o:
        return jsonify({'error': 'not_found'}), 404
    if A.is_single_room(f"{o['room']} {o['details']}"):
        return jsonify({'error': 'single_room'}), 409
    with A._compare_lock:
        A._compare_state[offer_id] = {'status': 'running'}
    A.log.info("Pro-Person-Vergleich gestartet: Angebot #%d", offer_id)
    A._spawn(A._run_compare, offer_id)
    return jsonify({'started': True})


@bp.route('/api/compare/<int:offer_id>', methods=['GET'])
def api_compare_get(offer_id: int):
    if (err := A._require_api()):
        return err
    return jsonify(A._compare_payload(offer_id))


@bp.route('/api/nights/<int:offer_id>', methods=['POST'])
def api_nights_start(offer_id: int):
    if (err := A._require_api()):
        return err
    data = request.get_json(silent=True) or {}
    try:
        span = int(data.get('span', 3))
    except (TypeError, ValueError):
        span = 3
    span = max(1, min(A.NIGHTS_SPAN_MAX, span))
    with A._nights_lock:
        if A._nights_state.get(offer_id, {}).get('status') == 'running':
            return jsonify({'started': True, 'already': True})
    with A.db() as con:
        o = con.execute('SELECT id FROM offers WHERE id=?', (offer_id,)).fetchone()
    if not o:
        return jsonify({'error': 'not_found'}), 404
    with A._nights_lock:
        A._nights_state[offer_id] = {'status': 'running'}
    A.log.info("Nächte-Vergleich gestartet: Angebot #%d (±%d)", offer_id, span)
    A._spawn(A._run_nights, offer_id, span)
    return jsonify({'started': True})


@bp.route('/api/nights/<int:offer_id>', methods=['GET'])
def api_nights_get(offer_id: int):
    if (err := A._require_api()):
        return err
    return jsonify(A._nights_payload(offer_id))


def _criteria_from_url(url: str) -> dict:
    """Reisendenzahl und Abflughäfen aus einer TUI-Such-/Angebots-URL. Beide sind
    Suchparameter, keine Ergebnisfelder — in den Treffern selbst stehen sie nicht.
    Die Suchantwort führt sie deshalb als `criteria` mit, damit die UI sie anzeigen
    und die Mail-Ansicht sie in ihre Kopfzeile schreiben kann (ohne dort aus der
    Suchmaske zu raten, die inzwischen ganz andere Werte zeigen kann)."""
    q = dict(parse_qsl(urlparse(url).query, keep_blank_values=True))
    airports = [a.strip() for a in re.split(r'[;,]', q.get('departureAirports', '') or '')
                if a.strip()]
    return {'travellers': A.travellers_from_url(url), 'airports': airports}


@bp.route('/api/search', methods=['POST'])
def api_search():
    """Hotelsuche — entweder über eine eingefügte TUI-Such-/Region-URL oder über ein
    bestehendes Angebot (`offer_id`): dann werden Region (URL bzw. Breadcrumb) und die
    Reiseparameter aus dem Angebot übernommen. Add-on-Filter (Veranstalter TUI,
    Verpflegung) gehen in die Such-Query, danach Nachfilter nach Sternen/Weiterempfehlung/Preis."""
    if (err := A._require_api()):
        return err
    if (remaining := A._cooldown_remaining('search:' + A.get_client_ip(request), 3)):
        return jsonify({'error': 'cooldown', 'retry_after': remaining}), 429
    data = request.get_json(silent=True) or {}
    try:
        offset = max(0, int(data.get('offset') or 0))
    except (TypeError, ValueError):
        offset = 0
    operator_tui = bool(data.get('operator_tui', True))
    direct = bool(data.get('direct'))
    adults_only = bool(data.get('adults_only'))
    transfer_included = bool(data.get('transfer_included'))
    boards = [str(b).strip() for b in (data.get('boards') or []) if str(b).strip()]
    airlines = [str(a).strip() for a in (data.get('airlines') or []) if str(a).strip()]
    location = [int(i) for i in (data.get('location') or []) if str(i).strip().isdigit()]

    def _num(key):
        try:
            return float(data.get(key) or 0)
        except (TypeError, ValueError):
            return 0
    min_stars, min_recommend = _num('min_stars'), _num('min_recommend')
    max_price = _num('max_price')

    region = None
    offer_id = data.get('offer_id')
    search_region = data.get('region')  # Param-Modus aus der Suchmaske
    if offer_id:
        with A.db() as con:
            o = con.execute('SELECT url, label, hotel FROM offers WHERE id=?',
                            (offer_id,)).fetchone()
        if not o:
            return jsonify({'error': 'not_found'}), 404
        url = o['url']
        if 'regionGiataIds=' not in (urlparse(url).query or ''):
            region = A.region_giata_from_breadcrumb(A._giata_from_url(url))
            if not region:
                return jsonify({'error': 'no_region',
                                'note': 'Region zum Angebot nicht ermittelbar'}), 400
        src = f"Angebot #{offer_id} ({o['label'] or o['hotel'] or ''})"
        criteria = _criteria_from_url(url)
        res = A.fetch_search(url, operator_tui=operator_tui, boards=boards, region=region,
                           airlines=airlines, location=location, direct=direct,
                           adults_only=adults_only, transfer_included=transfer_included,
                           offset=offset, verbose=A._verbose())
    elif search_region:
        try:
            region = int(search_region)
        except (TypeError, ValueError):
            return jsonify({'error': 'no_region'}), 400
        airports = [str(a).strip() for a in (data.get('airport') and [data.get('airport')]
                    or data.get('airports') or []) if str(a).strip()]
        # TUIs Such-API antwortet auf Zeiträume in der Vergangenheit mit einem
        # nichtssagenden HTTP 500 statt einem sauberen Fehler — hier vorher abfangen
        # (z. B. stehengebliebenes altes Datum im Suchformular), statt den 500
        # durchzureichen und einen unnötigen API-Call an TUI zu verschwenden.
        start_str, end_str = (data.get('start') or '').strip(), (data.get('end') or '').strip()
        start_date = None
        if start_str:
            try:
                start_date = date.fromisoformat(start_str)
            except ValueError:
                return jsonify({'error': 'invalid_dates', 'note': 'Ungültiges Startdatum'}), 400
            if start_date < date.today():
                return jsonify({'error': 'past_date',
                                'note': 'Startdatum liegt in der Vergangenheit'}), 400
        if end_str:
            try:
                end_date = date.fromisoformat(end_str)
            except ValueError:
                return jsonify({'error': 'invalid_dates', 'note': 'Ungültiges Enddatum'}), 400
            if start_date and end_date < start_date:
                return jsonify({'error': 'invalid_dates',
                                'note': 'Enddatum liegt vor dem Startdatum'}), 400
        A.log.info("Suche: Region %s %s–%s/%sN, %s Reisende, ab %s (TUI=%s, Verpfl.=%s)",
                 region, data.get('start'), data.get('end'), data.get('duration'),
                 data.get('travellers'), ','.join(airports) or '-', operator_tui,
                 ','.join(boards) or '-')
        try:
            _trav = max(1, int(data.get('travellers') or 2))
        except (TypeError, ValueError):
            _trav = 2
        criteria = {'travellers': _trav, 'airports': airports}
        res = A.fetch_search_params(region=region, start=(data.get('start') or '').strip(),
                                  end=(data.get('end') or '').strip(),
                                  duration=data.get('duration'),
                                  travellers=data.get('travellers'), airports=airports,
                                  operator_tui=operator_tui, boards=boards,
                                  airlines=airlines, location=location, direct=direct,
                                  adults_only=adults_only, transfer_included=transfer_included,
                                  offset=offset, verbose=A._verbose())
    else:
        url = (data.get('url') or '').strip()
        if not _valid_tui_url(url):
            return jsonify({'error': 'invalid_url'}), 400
        A.log.info("Suche: %s (TUI=%s, Verpflegung=%s)", url, operator_tui,
                 ','.join(boards) or '-')
        criteria = _criteria_from_url(url)
        res = A.fetch_search(url, operator_tui=operator_tui, boards=boards,
                           airlines=airlines, location=location, direct=direct,
                           adults_only=adults_only, transfer_included=transfer_included,
                           offset=offset, verbose=A._verbose())
    if res is None:
        return jsonify({'error': 'search_failed'}), 502
    if not res.get('ok'):
        return jsonify({'error': 'no_region', 'note': res.get('note', '')}), 400
    # bereits (aktiv) getrackte Hotels (per giataId) markieren — Archiv zählt nicht
    with A.db() as con:
        tracked = {g for g in (A._giata_from_url(r['url'])
                   for r in con.execute(
                       'SELECT url FROM offers WHERE COALESCE(archived,0)=0').fetchall()) if g}
    out = []
    for r in res['results']:
        if min_stars and (r.get('stars') or 0) < min_stars:
            continue
        if min_recommend and (r.get('recommendation') or 0) < min_recommend:
            continue
        if max_price and (r.get('price') is None or r.get('price') > max_price):
            continue
        r['tracked'] = str(r.get('giata')) in tracked
        out.append(r)
    A.log.info("Suche: %d Treffer, %d nach Filter", len(res['results']), len(out))
    return jsonify({'results': out, 'total': res.get('total', len(out)),
                    'matched': len(out), 'criteria': criteria})


# ── Reiseziel-Index (globale Suche über alle Ebenen) ───────────────────────────
# Der Picker lädt je Ebene nach (Land → Region → Insel …). Für eine Suche, die auch
# tief verschachtelte Ziele wie "Kanarische Inseln" (unter Spanien) findet, halten
# wir einen flachen Index des kompletten Baums vor. Der Aufbau ist teuer (~1000+
# API-Aufrufe), daher persistiert in der DB und nur beim Start bzw. manuell erneuert
# — Regionen ändern sich selten.
_DEST_INDEX_TTL = 14 * 86400  # 14 Tage
_dest_index: list = []
_dest_index_ts: int = 0
_dest_index_lock = threading.Lock()
_dest_index_building = False


def _load_dest_index() -> None:
    """Persistierten Reiseziel-Index aus der DB in den Speicher laden."""
    global _dest_index, _dest_index_ts
    raw = A._meta_get('dest_index')
    if raw:
        try:
            _dest_index = json.loads(raw)
            _dest_index_ts = int(A._meta_get('dest_index_ts') or 0)
        except Exception:
            _dest_index = []


def _build_dest_index() -> None:
    """Kompletten Reiseziel-Baum crawlen (teuer!) und persistieren. Läuft im
    Hintergrund; parallele Aufrufe werden zusammengefasst."""
    global _dest_index, _dest_index_ts, _dest_index_building
    with _dest_index_lock:
        if _dest_index_building:
            return
        _dest_index_building = True
    try:
        A.log.info("Reiseziel-Index wird aufgebaut …")
        items = A.build_destination_index()
        if items:
            _dest_index = items
            _dest_index_ts = int(time.time())
            A._meta_set('dest_index', json.dumps(items, ensure_ascii=False))
            A._meta_set('dest_index_ts', _dest_index_ts)
            A.log.info("Reiseziel-Index bereit: %d Einträge", len(items))
        else:
            A.log.warning("Reiseziel-Index leer geblieben (API nicht erreichbar?)")
    finally:
        _dest_index_building = False


def _ensure_dest_index() -> None:
    """Beim Start: Index aus DB laden; wenn leer oder veraltet, neu aufbauen."""
    _load_dest_index()
    if not _dest_index or (int(time.time()) - _dest_index_ts) > _DEST_INDEX_TTL:
        _build_dest_index()


def _search_dest_index(q: str, limit: int = 60) -> list:
    """Treffer im Index (Teilstring im Namen), Präfix-Treffer zuerst."""
    ql = q.lower()
    out = [it for it in _dest_index if ql in (it.get('label') or '').lower()]
    out.sort(key=lambda it: (not (it.get('label') or '').lower().startswith(ql),
                             (it.get('label') or '').lower()))
    return out[:limit]


_offer_dest_cache: dict = {}   # Hotel-giataId → Region-giataId (oder None)


def offer_region_giata(offer_id: int) -> tuple:
    """Region-giataId + Klarname zu einem Angebot — `(None, '')`, wenn unbekannt.

    Klimatabelle und Reiseführer hängen beide an der Region-giataId, das Angebot
    kennt aber nur die Hotel-giataId — die Region steckt in der Breadcrumb-API
    (derselbe Weg wie beim „Region"-Knopf). Die Auflösung ist ein zusätzlicher
    Fremdaufruf und pro Hotel unveränderlich, deshalb im Prozess gemerkt.

    Steht die Region-giataId schon in der Angebots-URL (`regionGiataIds=`), wird
    nichts nachgeschlagen. Auch von share_routes genutzt (Klima/Reiseführer im
    öffentlichen Angebots-Link)."""
    with A.db() as con:
        o = con.execute('SELECT url, region, country FROM offers WHERE id=?',
                        (offer_id,)).fetchone()
    if not o:
        return None, ''
    label = (o['region'] or o['country'] or '').strip()
    region = None
    for val in parse_qsl(urlparse(o['url']).query):
        if val[0] == 'regionGiataIds' and str(val[1]).strip().isdigit():
            region = int(str(val[1]).strip())
            break
    if region is None:
        hotel_giata = A._giata_from_url(o['url'])
        if hotel_giata in _offer_dest_cache:
            region = _offer_dest_cache[hotel_giata]
        else:
            region = A.region_giata_from_breadcrumb(hotel_giata)
            _offer_dest_cache[hotel_giata] = region
    if not region:
        return None, label
    return region, (label or f'Region {region}')


@bp.route('/api/offers/<int:offer_id>/dest', methods=['GET'])
def api_offer_dest(offer_id: int):
    """Reiseziel (Region) zu einem Angebot: Region-giataId + Klarname."""
    if (err := A._require_api()):
        return err
    with A.db() as con:
        if not con.execute('SELECT 1 FROM offers WHERE id=?', (offer_id,)).fetchone():
            return jsonify({'error': 'not_found'}), 404
    region, label = offer_region_giata(offer_id)
    if not region:
        return jsonify({'error': 'no_region',
                        'note': 'Region zum Angebot nicht ermittelbar'}), 400
    return jsonify({'giata': region, 'label': label})


@bp.route('/api/destinations', methods=['GET'])
def api_destinations():
    """Reiseziele für den Picker (Top-Level oder Unterregionen zu ?parent=…)."""
    if (err := A._require_api()):
        return err
    parent = (request.args.get('parent') or '').strip() or None
    if parent not in A._dest_cache:
        d = A.fetch_destinations(parent)
        if d is None:
            return jsonify({'error': 'unavailable'}), 502
        A._dest_cache[parent] = d
    return jsonify(A._dest_cache[parent])


@bp.route('/api/destinations/search', methods=['GET'])
def api_destinations_search():
    """Globale Reiseziel-Suche über alle Ebenen (nutzt den gecachten Index)."""
    if (err := A._require_api()):
        return err
    q = (request.args.get('q') or '').strip()
    if not _dest_index and not _dest_index_building:
        A._spawn(_build_dest_index)  # erster Aufbau on-demand
    if len(q) < 2:
        return jsonify({'items': [], 'building': _dest_index_building,
                        'ready': bool(_dest_index)})
    return jsonify({'items': _search_dest_index(q),
                    'building': _dest_index_building, 'ready': bool(_dest_index),
                    'ts': _dest_index_ts})


@bp.route('/api/destinations/reindex', methods=['POST'])
def api_destinations_reindex():
    """Reiseziel-Index manuell neu aufbauen (Hintergrund)."""
    if (err := A._require_api()):
        return err
    A._spawn(_build_dest_index)
    return jsonify({'ok': True, 'building': True})


@bp.route('/api/airports', methods=['GET'])
def api_airports():
    """Abflughäfen (TUI-Liste, einmalig gecacht)."""
    if (err := A._require_api()):
        return err
    if not A._airports_cache:
        A._airports_cache = A.fetch_airports()
    return jsonify({'airports': A._airports_cache})


@bp.route('/api/contacts', methods=['GET'])
def api_contacts():
    """Nextcloud-Adressbuch (CardDAV), einmalig gecacht — ?refresh=1 erzwingt Neuladen."""
    if (err := A._require_api()):
        return err
    if not A.nc_configured():
        return jsonify({'configured': False, 'contacts': []})
    # Cache lebt weiter als app._contacts_cache (Modul-Attribut statt `global`,
    # Tests lesen/patchen ihn dort)
    if not A._contacts_cache or request.args.get('refresh') == '1':
        cfg = A.load_config()
        A._contacts_cache = A.fetch_contacts(
            cfg.get('nc_addressbook_url', ''), cfg.get('nc_user', ''),
            cfg.get('nc_app_password', ''), verbose=A._verbose())
    return jsonify({'configured': True, 'contacts': A._contacts_cache})


@bp.route('/api/airlines', methods=['GET'])
def api_airlines():
    """Fluggesellschaften für den optionalen Such-Filter (kuratierte Liste)."""
    if (err := A._require_api()):
        return err
    return jsonify({'airlines': A.fetch_airlines()})


@bp.route('/api/rooms/<int:offer_id>', methods=['GET'])
def api_rooms_get(offer_id: int):
    """Wählbare Zimmerkategorien (mit Preis p. P.) für ein Angebot — live abgefragt."""
    if (err := A._require_api()):
        return err
    with A.db() as con:
        o = con.execute('SELECT url FROM offers WHERE id=?', (offer_id,)).fetchone()
    if not o:
        return jsonify({'error': 'not_found'}), 404
    with A._scrape_lock:
        res = A.fetch_rooms(o['url'], verbose=A._verbose())
    if res is None:
        return jsonify({'ok': False, 'note': 'Zimmer konnten nicht geladen werden'}), 502
    res['current'] = A.room_code_from_url(o['url'])
    res['transfer_included'] = A.transfer_included_from_url(o['url'])
    return jsonify(res)


@bp.route('/api/rooms/<int:offer_id>', methods=['POST'])
def api_rooms_set(offer_id: int):
    """Fixiert ein Zimmer (`code`) für das Angebot — danach wird der Preis dieses Zimmers
    verfolgt. Leerer Code = wieder automatisch das günstigste Zimmer."""
    if (err := A._require_api()):
        return err
    data = request.get_json(silent=True) or {}
    code = (data.get('code') or '').strip()
    label = (data.get('label') or '').strip()
    # Zimmercodes von TUI sehen z.B. so aus: DZM1, JSM2, GT06-AI — kurz, alphanumerisch
    # + Bindestrich. Leer = "automatisch günstigstes" bleibt weiterhin erlaubt.
    if code and not re.fullmatch(r'[A-Za-z0-9-]{1,40}', code):
        return jsonify({'error': 'invalid_code'}), 400
    with A.db() as con:
        o = con.execute('SELECT url FROM offers WHERE id=?', (offer_id,)).fetchone()
        if not o:
            return jsonify({'error': 'not_found'}), 404
        new_url = A.with_room_code(o['url'], code)
        try:
            con.execute('UPDATE offers SET url=? WHERE id=?', (new_url, offer_id))
        except sqlite3.IntegrityError:
            return jsonify({'error': 'duplicate',
                            'note': 'Dieses Zimmer wird bereits als eigenes Angebot verfolgt'}), 409
    A.log.info("Angebot #%d: Zimmer %s gewählt", offer_id, code or '(günstigstes)')
    if code:
        A._log_event(offer_id, 'room',
                   f"Zimmer: {label} ({code})" if label else f"Zimmer: {code}")
    else:
        A._log_event(offer_id, 'room', "Zimmer: günstigstes (automatisch)")
    A._spawn(A.check_offer, offer_id)
    return jsonify({'ok': True, 'started': True})

