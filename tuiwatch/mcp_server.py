"""MCP-Server (Model Context Protocol) für TUIWatch — ab 0.119.0.

Ein Endpunkt `/mcp` im normalen Webserver, Transport „Streamable HTTP“ in der
einfachsten Form: jede Anfrage ist ein JSON-RPC-POST, die Antwort kommt als
`application/json` (die Spezifikation erlaubt das statt eines SSE-Streams).
Zustandslos, keine Sitzungs-ID, kein GET-Stream — genug für LiteLLM
(`transport: http`), Claude Desktop/Code und andere Clients.

Absicherung, bewusst getrennt vom Login der Oberfläche:
- Schalter `enable_mcp` (Standard aus); aus = der Endpunkt antwortet mit 404.
- Eigenes Token `mcp_token` (verschlüsselt gespeichert, mindestens 16 Zeichen),
  als `Authorization: Bearer …` oder `X-API-Key: …`. Fehlversuche laufen in
  dieselbe Sperre wie der Login.
- Browser-Anfragen von fremden Seiten (Origin ≠ eigener Host) werden abgelehnt.
- Standardmäßig nur lesende Werkzeuge; Aktionen (prüfen, Wunschpreis,
  pausieren) nur mit `mcp_allow_actions`.
"""
from __future__ import annotations

import json
import secrets
from datetime import date, datetime
from urllib.parse import urlparse

from flask import Blueprint, Response, jsonify, request

import app as A

bp = Blueprint('mcp_server', __name__)

PROTOCOL_VERSIONS = ('2025-06-18', '2025-03-26', '2024-11-05')
MAX_BODY = 256 * 1024
MIN_TOKEN_LEN = 16

INSTRUCTIONS = (
    "TUIWatch verfolgt Preise von TUI-Reiseangeboten und verwaltet gebuchte Reisen. "
    "Preise sind pro Person in Euro, total_price ist der Gesamtpreis aller Reisenden. "
    "Zuerst list_offers aufrufen, Details und Preisverlauf dann mit get_offer. "
    "Gebuchte Reisen („Meine Reisen“) mit list_trips und get_trip. "
    "Bei Fragen zu fehlenden Preisen zuerst get_problems und get_api_status.")


# ── Hilfen ────────────────────────────────────────────────────────────────────

def _iso(ts) -> str | None:
    try:
        return datetime.fromtimestamp(int(ts)).isoformat(timespec='minutes') if ts else None
    except (TypeError, ValueError, OSError):
        return None


def _offer_summary(o: dict) -> dict:
    return {
        'id': o['id'],
        'name': o.get('label') or o.get('hotel') or f"Angebot #{o['id']}",
        'hotel': o.get('hotel') or '',
        'location': o.get('location') or '', 'region': o.get('region') or '',
        'country': o.get('country') or '',
        'details': o.get('details') or '', 'nights': o.get('nights'),
        'return_date': o.get('return_date') or '',
        'travellers': o.get('travellers_count'),
        'departure_airport': o.get('dep_airport') or '',
        'price_per_person': o.get('price'), 'total_price': o.get('total_price'),
        'available': o.get('available'),
        'target_price': o.get('target_price'), 'booked_price': o.get('booked_price'),
        'min_price': o.get('min_price'), 'max_price': o.get('max_price'),
        'avg30_price': o.get('avg30_price'), 'delta_last_check': o.get('delta'),
        'trend': o.get('trend'),
        'paused': o.get('paused'), 'archived': o.get('archived'),
        'history_only': o.get('history_only'),
        'last_checked': _iso(o.get('last_ts')), 'last_check_ok': o.get('ok'),
        'tags': o.get('tags') or [], 'url': o.get('url'),
    }


def _find_offer(offer_id) -> dict | None:
    try:
        oid = int(offer_id)
    except (TypeError, ValueError):
        return None
    return next((o for o in A._collect_offers() if o['id'] == oid), None)


def _price_history(offer_id: int, points: int) -> list:
    with A.db() as con:
        rows = con.execute(
            'SELECT ts, price FROM price_history WHERE offer_id=? AND ok=1 '
            'AND price IS NOT NULL ORDER BY ts', (offer_id,)).fetchall()
    if len(rows) > points:
        step = len(rows) / points
        picked = [rows[int(i * step)] for i in range(points - 1)] + [rows[-1]]
    else:
        picked = rows
    return [{'time': _iso(r['ts']), 'price': r['price']} for r in picked]


class ToolError(Exception):
    """Fehler, den das Modell sehen soll (isError im Ergebnis, kein Protokollfehler)."""


# ── Werkzeuge ─────────────────────────────────────────────────────────────────

def t_list_offers(args: dict):
    inc_arch = bool(args.get('include_archived', False))
    offers = [o for o in A._collect_offers() if inc_arch or not o.get('archived')]
    return {'count': len(offers), 'offers': [_offer_summary(o) for o in offers]}


def t_get_offer(args: dict):
    o = _find_offer(args.get('offer_id'))
    if not o:
        raise ToolError('Angebot nicht gefunden')
    points = max(5, min(int(args.get('history_points') or 60), 500))
    out = _offer_summary(o)
    out.update({
        'room': o.get('room') or '', 'cancellation': o.get('cancellation'),
        'stars': o.get('stars'), 'rating': o.get('rating'),
        'rating_count': o.get('rating_count'),
        'flight_outbound': o.get('flight_out') or '', 'flight_return': o.get('flight_ret') or '',
        'old_price': o.get('old_price'), 'discount': o.get('discount'),
        'last_booked': o.get('last_booked') or '',
        'final_payment_date': o.get('final_payment_date') or '',
        'note': o.get('note') or '',
        'price_history': _price_history(o['id'], points),
    })
    return out


# Datenschutz: an das KI-Modell gehen nur Reisedaten, nichts zu Personen. Keine
# Namen, keine Geburtsdaten, keine Sonderwünsche (Freitext) und keine
# Buchungsnummer (mit Namen zusammen der Schlüssel zur Buchung bei TUI).
# Deshalb eine Liste ERLAUBTER Felder statt einer Sperrliste — ein neues
# Parser-Feld gelangt so nicht versehentlich nach außen.
_TRIPS_COLS = ('SELECT id, booking_date, title, destination, hotel, start_date, '
               'end_date, nights, travellers, total_price, package_price, meal FROM trips ')
_TRIP_DETAIL_KEYS = ('buchungsdatum', 'reisezeitraum', 'naechte', 'reiseziel', 'zimmertyp',
                     'verpflegung', 'gesamtpreis', 'paketpreis', 'paketpreis_netto',
                     'extras_summe', 'rabatte_summe', 'preis_pro_nacht', 'preis_pro_person_nacht',
                     'preis_pro_nacht_paket', 'preis_pro_person_nacht_paket', 'rabatte',
                     'zahlungsart', 'anzahlung', 'restzahlung')
_FLIGHT_KEYS = ('datum', 'typ', 'abflug_zeit', 'ankunft_zeit', 'dauer', 'von', 'nach',
                'flugnummer')
_EXTRA_KEYS = ('typ', 'code', 'teilnehmer', 'anzahl', 'gewicht', 'plaetze', 'preis')


def _pick(d, keys) -> dict:
    return {k: d[k] for k in keys if isinstance(d, dict) and k in d}


def _trip_details(data: dict) -> dict:
    """Aus dem geparsten TUI-PDF nur die freigegebenen Felder (siehe oben)."""
    out = _pick(data, _TRIP_DETAIL_KEYS)
    hotel = data.get('hotel')
    if isinstance(hotel, dict):
        out['hotel'] = _pick(hotel, ('name', 'code'))
    out['fluege'] = [_pick(f, _FLIGHT_KEYS) for f in (data.get('fluege') or [])
                     if isinstance(f, dict)]
    out['extras'] = [_pick(e, _EXTRA_KEYS) for e in (data.get('extras') or [])
                     if isinstance(e, dict)]
    # Reisende nur als Anzahl und Preis je Person — ohne Namen und Geburtsdatum
    reisende = [x for x in (data.get('reisende') or []) if isinstance(x, dict)]
    out['reisende_anzahl'] = len(reisende) or None
    out['preis_je_reisendem'] = [x.get('preis') for x in reisende if x.get('preis')]
    return out
_TRIPS_UPCOMING_SQL = (_TRIPS_COLS + 'WHERE end_date >= ? OR end_date IS NULL '
                       'ORDER BY start_date ASC LIMIT ?')
_TRIPS_ALL_SQL = _TRIPS_COLS + 'ORDER BY start_date DESC LIMIT ?'


def t_list_trips(args: dict):
    """„Meine Reisen“: bevorstehende (Standard) oder alle gebuchten Reisen."""
    include_past = bool(args.get('include_past', False))
    limit = max(1, min(int(args.get('limit') or 50), 200))
    today = date.today().isoformat()
    # Zwei feste Abfragen statt eines per Bedingung zusammengesetzten Texts (CodeQL)
    sql = _TRIPS_ALL_SQL if include_past else _TRIPS_UPCOMING_SQL
    with A.db() as con:
        rows = con.execute(sql, (today, limit) if not include_past else (limit,)).fetchall()
    trips = []
    for t in (dict(x) for x in rows):
        if t.get('start_date'):
            try:
                t['days_until'] = (date.fromisoformat(t['start_date']) - date.today()).days
            except ValueError:
                pass
        t['own_share'] = (round((t['total_price'] or 0) / (t['travellers'] or 1), 2)
                          if t.get('total_price') else None)
        trips.append(t)
    return {'count': len(trips),
            'nights_sum': sum(t.get('nights') or 0 for t in trips),
            'total_sum': round(sum(t.get('total_price') or 0 for t in trips), 2),
            'own_sum': round(sum(t.get('own_share') or 0 for t in trips), 2),
            'trips': trips}


def t_get_trip(args: dict):
    """Alle Daten einer gebuchten Reise: aus dem TUI-PDF erkannte Felder (Flüge,
    Hotel, Reisende, Zahlungen …), Flugzeiten-Abgleich, offene Packliste."""
    try:
        tid = int(args.get('trip_id'))
    except (TypeError, ValueError):
        raise ToolError('trip_id fehlt oder ist keine Zahl')
    with A.db() as con:
        row = con.execute('SELECT * FROM trips WHERE id=?', (tid,)).fetchone()
        if not row:
            raise ToolError('Reise nicht gefunden')
        packing = con.execute(
            'SELECT category, label, checked FROM trip_packing_items WHERE trip_id=? '
            'ORDER BY id', (tid,)).fetchall()
        atts = con.execute('SELECT orig_name FROM trip_attachments WHERE trip_id=? '
                           'ORDER BY id', (tid,)).fetchall()
        checks = A.flight_watch.flight_checks_for(con, tid)
    trip = {k: row[k] for k in ('id', 'booking_date', 'title', 'destination',
                                'hotel', 'start_date', 'end_date', 'nights', 'travellers',
                                'total_price', 'package_price', 'net_per_night', 'meal')}
    trip['details'] = _trip_details(A._json_loads_safe(row['data'] or '{}', {}))
    trip['flight_schedule_checks'] = checks
    open_items = [f"{p['category']}: {p['label']}" for p in packing if not p['checked']]
    trip['packing'] = {'total': len(packing), 'open': len(open_items),
                       'open_items': open_items[:100]}
    trip['attachments'] = [a['orig_name'] for a in atts]
    return trip


def t_next_trip(args: dict):
    return {'next_trip': A._next_trip()}


def t_get_status(args: dict):
    offers = A._collect_offers()
    last = max((o.get('last_ts') or 0 for o in offers), default=0)
    return {'version': A.APP_VERSION,
            'active_offers': sum(1 for o in offers if not o.get('archived') and not o.get('paused')),
            'paused_offers': sum(1 for o in offers if o.get('paused') and not o.get('archived')),
            'archived_offers': sum(1 for o in offers if o.get('archived')),
            'last_price_check': _iso(last),
            'running_tasks': A.busy_labels()}


def t_get_problems(args: dict):
    """Offene Störungen (Angebot nicht verfügbar, Abruf-Fehler in Folge …)."""
    import issues
    with A.db() as con:
        rows = con.execute('SELECT * FROM issues ORDER BY muted, streak DESC, '
                           'last_ts DESC').fetchall()
        items = [issues._row(r, con) for r in rows]
    return {'summary': issues.summary(), 'problems': [
        {'kind': i['kind_label'], 'title': i['title'], 'detail': i['detail'],
         'severity': i['severity'], 'failures_in_a_row': i['streak'],
         'since': _iso(i['first_ts']), 'last': _iso(i['last_ts']),
         'muted': bool(i['muted'])} for i in items]}


def t_get_api_status(args: dict):
    """Letzter Selbsttest der TUI-Schnittstellen (ohne neuen anzustoßen)."""
    with A._health_lock:
        st = dict(A._health_state)
    return {'ok': st.get('ok'), 'checked': _iso(st.get('ts')), 'running': bool(st.get('running')),
            'checks': [{'name': c.get('name'), 'ok': c.get('ok'), 'critical': c.get('critical'),
                        'note': c.get('note') or c.get('detail') or ''}
                       for c in (st.get('checks') or []) if isinstance(c, dict)]}


_FLIGHT_ROWS_MAX = 80


def t_search_flights(args: dict):
    """Abflüge zu einem Ziel an den eingeschalteten Flughäfen (Flugpläne)."""
    import all_flights_routes
    q = str(args.get('destination') or '').strip()
    if len(q) < 2:
        raise ToolError('destination: mindestens 2 Zeichen (Stadt, Land oder IATA-Code)')
    out = all_flights_routes.search_all(q, str(args.get('date_from') or '').strip(),
                                        str(args.get('date_till') or '').strip())
    if out is None:
        raise ToolError('Kein Flugplan eingeschaltet (Einstellungen → Zusatzmodule)')
    names = {'str': 'Stuttgart', 'fra': 'Frankfurt', 'muc': 'München', 'fkb': 'Karlsruhe/Baden-Baden'}
    result = {}
    for k, v in out.items():
        rows = (v or {}).get('rows') or []
        result[names.get(k, k)] = ({'error': True} if (v or {}).get('error')
                                   else {'count': len(rows), 'flights': rows[:_FLIGHT_ROWS_MAX],
                                         'truncated': len(rows) > _FLIGHT_ROWS_MAX})
    return result


def t_list_flight_destinations(args: dict):
    import all_flights_routes
    out = all_flights_routes.destinations_all()
    if out is None:
        raise ToolError('Kein Flugplan eingeschaltet (Einstellungen → Zusatzmodule)')
    q = str(args.get('filter') or '').strip().lower()
    if q:
        out = [d for d in out if q in (d.get('name') or '').lower()
               or q in (d.get('country') or '').lower() or q == (d.get('code') or '').lower()]
    return {'count': len(out), 'destinations': out[:300]}


# Kommentare zu öffentlichen Links tragen Name und IP des Schreibenden — keine
# Personendaten an das KI-Modell, diese Meldungen fallen deshalb ganz heraus.
_NOTIFY_HIDDEN_TAGS = ('share_comment',)


def t_get_notifications(args: dict):
    limit = max(1, min(int(args.get('limit') or 30), 200))
    with A.db() as con:
        rows = con.execute(
            'SELECT ts, channel, title, message, tag, ok FROM notify_log '
            'ORDER BY id DESC LIMIT 400').fetchall()
    items = []
    seen = set()
    for r in rows:
        if (r['tag'] or '') in _NOTIFY_HIDDEN_TAGS or (r['tag'] or '').startswith('share_comment'):
            continue
        key = (r['ts'], r['title'], r['message'])       # HA + Telegram = eine Meldung
        if key in seen:
            continue
        seen.add(key)
        items.append({'time': _iso(r['ts']), 'title': r['title'] or '', 'message': r['message'] or ''})
        if len(items) >= limit:
            break
    return {'notifications': items}


def t_get_price_calendar(args: dict):
    import price_calendar
    o = _find_offer(args.get('offer_id'))
    if not o:
        raise ToolError('Angebot nicht gefunden')
    cal = price_calendar._calendar_payload(o['id'])
    if cal.get('status') != 'done':
        return {'offer_id': o['id'], 'status': cal.get('status'),
                'hint': 'Noch kein Preiskalender abgerufen (in der Oberfläche starten).'}
    days = [{'date': d.get('date'), 'price': d.get('price')}
            for d in (cal.get('days') or []) if d.get('date')]
    keep = ('cheapest_date', 'cheapest_price', 'priciest_date', 'priciest_price')
    return {'offer_id': o['id'], 'fetched': _iso(cal.get('ts')),
            **{k: cal.get(k) for k in keep if k in cal},
            'current_price_per_person': o.get('price'), 'days': days[:200]}


def t_get_market_trend(args: dict):
    data = A.market_trend_payload()
    region = str(args.get('region') or '').strip().lower()
    if region:
        data['by_region'] = [r for r in data.get('by_region') or []
                             if region in str(r.get('region') or '').lower()]
    return data


def t_get_promo_codes(args: dict):
    return A._aktionscodes_payload()


def t_check_offer(args: dict):
    o = _find_offer(args.get('offer_id'))
    if not o:
        raise ToolError('Angebot nicht gefunden')
    if o.get('archived'):
        raise ToolError('Archivierte Angebote lassen sich nicht mehr prüfen')
    A._spawn(A.check_offer, o['id'])
    A.log.info("MCP: Preis-Check für Angebot #%d angestoßen", o['id'])
    return {'started': True, 'offer_id': o['id'],
            'hint': 'Der Check läuft im Hintergrund; das Ergebnis in ~1 Minute mit get_offer abfragen.'}


def t_set_target_price(args: dict):
    o = _find_offer(args.get('offer_id'))
    if not o:
        raise ToolError('Angebot nicht gefunden')
    raw = args.get('price')
    try:
        price = float(raw) if raw not in (None, '', 0) else None
    except (TypeError, ValueError):
        raise ToolError('price muss eine Zahl sein (oder null zum Entfernen)')
    if price is not None and not (1 <= price <= 100000):
        raise ToolError('price außerhalb des sinnvollen Bereichs')
    with A.db() as con:
        con.execute('UPDATE offers SET target_price=? WHERE id=?', (price, o['id']))
    A.log.info("MCP: Wunschpreis #%d %s", o['id'],
               f"gesetzt: {price:.0f} €" if price else "entfernt")
    if price:
        A._log_event(o['id'], 'target', f"Wunschpreis {A._eur(price)}")
    return {'offer_id': o['id'], 'target_price': price}


def t_pause_offer(args: dict):
    o = _find_offer(args.get('offer_id'))
    if not o:
        raise ToolError('Angebot nicht gefunden')
    paused = bool(args.get('paused', True))
    with A.db() as con:
        con.execute('UPDATE offers SET paused=? WHERE id=?', (1 if paused else 0, o['id']))
    A.log.info("MCP: Angebot #%d %s", o['id'], "pausiert" if paused else "fortgesetzt")
    A._spawn(A.push_ha_sensors)
    return {'offer_id': o['id'], 'paused': paused}


_ID = {'type': 'integer', 'description': 'ID des Angebots (aus list_offers)'}
TOOLS = [
    {'name': 'list_offers', 'handler': t_list_offers, 'write': False,
     'description': 'Alle verfolgten TUI-Angebote mit aktuellem Preis, Wunschpreis, '
                    'Tiefst-/Höchstpreis, Trend und Status.',
     'inputSchema': {'type': 'object', 'properties': {
         'include_archived': {'type': 'boolean', 'description': 'Archivierte (vergangene) Angebote mitliefern', 'default': False}},
         'additionalProperties': False}},
    {'name': 'get_offer', 'handler': t_get_offer, 'write': False,
     'description': 'Details eines Angebots inklusive Flügen, Zimmer, Bewertung und Preisverlauf.',
     'inputSchema': {'type': 'object', 'properties': {
         'offer_id': _ID,
         'history_points': {'type': 'integer', 'description': 'Max. Punkte im Preisverlauf (5-500)', 'default': 60}},
         'required': ['offer_id'], 'additionalProperties': False}},
    {'name': 'list_trips', 'handler': t_list_trips, 'write': False,
     'description': 'Gebuchte Reisen aus „Meine Reisen“ (Ziel, Hotel, Zeitraum, Preis, Reisende, '
                    'Tage bis Abreise) mit Summen. Standard: nur laufende und kommende Reisen.',
     'inputSchema': {'type': 'object', 'properties': {
         'include_past': {'type': 'boolean', 'description': 'Auch vergangene Reisen', 'default': False},
         'limit': {'type': 'integer', 'default': 50}}, 'additionalProperties': False}},
    {'name': 'get_trip', 'handler': t_get_trip, 'write': False,
     'description': 'Daten einer gebuchten Reise: Flüge mit Zeiten, Hotel, Zimmer, Verpflegung, '
                    'Anzahl Reisende und Preise, Zahlungen/Fristen, Abgleich mit dem Flughafen-Flugplan, '
                    'offene Punkte der Packliste. Enthält keine Personendaten.',
     'inputSchema': {'type': 'object', 'properties': {
         'trip_id': {'type': 'integer', 'description': 'ID der Reise (aus list_trips)'}},
         'required': ['trip_id'], 'additionalProperties': False}},
    {'name': 'next_trip', 'handler': t_next_trip, 'write': False,
     'description': 'Die nächste gebuchte Reise mit Abflugzeitpunkt.',
     'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
    {'name': 'get_status', 'handler': t_get_status, 'write': False,
     'description': 'Zustand von TUIWatch: Version, Anzahl Angebote, letzte Preisprüfung, laufende Aufgaben.',
     'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
    {'name': 'get_problems', 'handler': t_get_problems, 'write': False,
     'description': 'Offene Störungen: Angebot nicht mehr verfügbar, Abruf schlägt wiederholt fehl, '
                    'Messreihe oder Suchabo gestört — mit Schwere, Anzahl Fehlversuche und Zeitraum.',
     'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
    {'name': 'get_api_status', 'handler': t_get_api_status, 'write': False,
     'description': 'Letzter Selbsttest der TUI-Schnittstellen: erreichbar ja/nein, welche Einzelprüfung '
                    'scheitert, wann geprüft. Erklärt z. B., warum keine neuen Preise kommen.',
     'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
    {'name': 'search_flights', 'handler': t_search_flights, 'write': False,
     'description': 'Abflüge zu einem Ziel laut Flugplan der eingeschalteten Heimatflughäfen '
                    '(Stuttgart, Frankfurt, München, Karlsruhe) mit Wochentagen, Zeiten, Airline.',
     'inputSchema': {'type': 'object', 'properties': {
         'destination': {'type': 'string', 'description': 'Ziel: Stadt, Land oder IATA-Code, z. B. Heraklion oder HER'},
         'date_from': {'type': 'string', 'description': 'Optional, JJJJ-MM-TT'},
         'date_till': {'type': 'string', 'description': 'Optional, JJJJ-MM-TT'}},
         'required': ['destination'], 'additionalProperties': False}},
    {'name': 'list_flight_destinations', 'handler': t_list_flight_destinations, 'write': False,
     'description': 'Alle Ziele, die ab den eingeschalteten Heimatflughäfen angeflogen werden.',
     'inputSchema': {'type': 'object', 'properties': {
         'filter': {'type': 'string', 'description': 'Optional: Teil von Name/Land oder IATA-Code'}},
         'additionalProperties': False}},
    {'name': 'get_notifications', 'handler': t_get_notifications, 'write': False,
     'description': 'Zuletzt gesendete Benachrichtigungen: Preisänderungen, Wunschpreis erreicht, '
                    'günstigerer Termin, Flugzeiten geändert usw., neueste zuerst.',
     'inputSchema': {'type': 'object', 'properties': {
         'limit': {'type': 'integer', 'default': 30}}, 'additionalProperties': False}},
    {'name': 'get_price_calendar', 'handler': t_get_price_calendar, 'write': False,
     'description': 'Preiskalender eines Angebots: Preis pro Person je Abreisetag rund um den '
                    'gebuchten Termin, günstigster und teuerster Tag.',
     'inputSchema': {'type': 'object', 'properties': {'offer_id': _ID},
                     'required': ['offer_id'], 'additionalProperties': False}},
    {'name': 'get_market_trend', 'handler': t_get_market_trend, 'write': False,
     'description': 'Markttrend (14 Tage) und Preisindex, global und je Region, dazu Preisbarometer '
                    'mit Buchungsampel (jetzt buchen oder warten).',
     'inputSchema': {'type': 'object', 'properties': {
         'region': {'type': 'string', 'description': 'Optional: nur Regionen, die das enthalten'}},
         'additionalProperties': False}},
    {'name': 'get_promo_codes', 'handler': t_get_promo_codes, 'write': False,
     'description': 'Aktuelle TUI-Aktionscodes (Gutscheine) mit Wert und Bedingungen.',
     'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
    {'name': 'check_offer', 'handler': t_check_offer, 'write': True,
     'description': 'Preis eines Angebots jetzt neu abfragen (läuft im Hintergrund).',
     'inputSchema': {'type': 'object', 'properties': {'offer_id': _ID},
                     'required': ['offer_id'], 'additionalProperties': False}},
    {'name': 'set_target_price', 'handler': t_set_target_price, 'write': True,
     'description': 'Wunschpreis (pro Person, Euro) setzen; null entfernt ihn. Bei Erreichen meldet TUIWatch sich.',
     'inputSchema': {'type': 'object', 'properties': {
         'offer_id': _ID, 'price': {'type': ['number', 'null']}},
         'required': ['offer_id', 'price'], 'additionalProperties': False}},
    {'name': 'pause_offer', 'handler': t_pause_offer, 'write': True,
     'description': 'Angebot pausieren (keine Preisprüfungen mehr) oder mit paused=false fortsetzen.',
     'inputSchema': {'type': 'object', 'properties': {
         'offer_id': _ID, 'paused': {'type': 'boolean', 'default': True}},
         'required': ['offer_id'], 'additionalProperties': False}},
]


def _actions_allowed() -> bool:
    return bool(A.load_config().get('mcp_allow_actions', False))


def _visible_tools() -> list:
    allow = _actions_allowed()
    return [t for t in TOOLS if allow or not t['write']]


# ── JSON-RPC ──────────────────────────────────────────────────────────────────

def _err(mid, code: int, message: str) -> dict:
    return {'jsonrpc': '2.0', 'id': mid, 'error': {'code': code, 'message': message}}


def _ok(mid, result: dict) -> dict:
    return {'jsonrpc': '2.0', 'id': mid, 'result': result}


def _handle(msg) -> dict | None:
    """Eine JSON-RPC-Nachricht. None = Benachrichtigung, keine Antwort."""
    if not isinstance(msg, dict) or msg.get('jsonrpc') != '2.0' or 'method' not in msg:
        return _err(msg.get('id') if isinstance(msg, dict) else None, -32600, 'Invalid Request')
    mid = msg.get('id')
    method = msg.get('method')
    params = msg.get('params') or {}
    if mid is None:                               # Benachrichtigung (initialized, cancelled …)
        return None
    if not isinstance(params, dict):
        return _err(mid, -32602, 'Invalid params')
    if method == 'initialize':
        asked = params.get('protocolVersion')
        client = params.get('clientInfo') if isinstance(params.get('clientInfo'), dict) else {}
        A.log.info("MCP: Verbindung von %s (%s)", A.log_safe(A.get_client_ip(request)),
                   A.log_safe(client.get('name') or '?', 60))
        return _ok(mid, {
            'protocolVersion': asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
            'capabilities': {'tools': {'listChanged': False}},
            'serverInfo': {'name': 'tuiwatch', 'title': 'TUIWatch', 'version': A.APP_VERSION},
            'instructions': INSTRUCTIONS})
    if method == 'ping':
        return _ok(mid, {})
    if method == 'tools/list':
        return _ok(mid, {'tools': [
            {'name': t['name'], 'description': t['description'],
             'inputSchema': t['inputSchema'],
             'annotations': {'readOnlyHint': not t['write']}}
            for t in _visible_tools()]})
    if method == 'tools/call':
        name = params.get('name')
        args = params.get('arguments') or {}
        tool = next((t for t in _visible_tools() if t['name'] == name), None)
        if tool is None or not isinstance(args, dict):
            return _err(mid, -32602, 'Unknown tool or invalid arguments')
        # Nur Zahlen/Wahrheitswerte als Argumente ins Log, kein Freitext
        shown = ', '.join(f'{k}={v}' for k, v in args.items()
                          if isinstance(k, str) and k.isidentifier()
                          and (v is None or isinstance(v, (bool, int, float))))
        A.log.info("MCP: %s(%s) von %s", tool['name'], shown, A.log_safe(A.get_client_ip(request)))
        try:
            data = tool['handler'](args)
        except ToolError as e:
            # Feste Texte aus diesem Modul, keine fremden Ausnahmen
            return _ok(mid, {'content': [{'type': 'text', 'text': e.args[0]}], 'isError': True})
        except Exception as e:                   # noqa: BLE001
            A.log.warning("MCP-Werkzeug %s fehlgeschlagen: %s", name, type(e).__name__)
            return _ok(mid, {'content': [{'type': 'text', 'text': 'Interner Fehler'}],
                             'isError': True})
        return _ok(mid, {'content': [{'type': 'text',
                                      'text': json.dumps(data, ensure_ascii=False, default=str)}],
                         'structuredContent': data})
    return _err(mid, -32601, 'Method not found')


# ── HTTP ──────────────────────────────────────────────────────────────────────

def _auth_error():
    cfg = A.load_config()
    if not cfg.get('enable_mcp', False):
        return Response('Not Found', 404)
    token = str(cfg.get('mcp_token') or '').strip()
    if len(token) < MIN_TOKEN_LEN:
        return jsonify({'error': 'mcp_token_missing'}), 503
    origin = request.headers.get('Origin')
    if origin and urlparse(origin).netloc != request.host:
        return jsonify({'error': 'forbidden_origin'}), 403
    ip = A.get_client_ip(request)
    auth = request.headers.get('Authorization') or ''
    given = auth[7:].strip() if auth.lower().startswith('bearer ') else \
        (request.headers.get('X-API-Key') or '').strip()
    # Gültiges Token zuerst und unabhängig von einer IP-Sperre annehmen: die Sperre
    # soll Raten bremsen, und ein zufälliges 64-Zeichen-Token ist nicht zu raten.
    # Andersherum sperrte jeder mit derselben Absender-IP (z. B. ein anderer
    # Container im selben Docker-Netz) den echten Client gleich mit aus.
    if given and secrets.compare_digest(given, token):
        return None
    if A.is_rate_limited(ip):
        A.log.warning("MCP: Anfrage von gesperrter IP %s abgewiesen (zu viele falsche Tokens)",
                      A.log_safe(ip))
        return jsonify({'error': 'rate_limited'}), 429
    if given:
        # Nur ein FALSCHES Token zählt als Fehlversuch. Ganz ohne Token ist es
        # eher ein Erreichbarkeits- oder Health-Check als ein Rateversuch.
        A.record_failed_attempt(ip)
        A.log.warning("MCP: Anfrage mit falschem Token abgelehnt (IP %s)", A.log_safe(ip))
    else:
        A.log.info("MCP: Anfrage ohne Token abgelehnt (IP %s)", A.log_safe(ip))
    resp = jsonify({'error': 'unauthorized'})
    resp.status_code = 401
    resp.headers['WWW-Authenticate'] = 'Bearer'
    return resp


@bp.route('/api/mcp/status', methods=['GET'])
def api_mcp_status():
    """Für den Einstellungsdialog: an/aus und ob ein Token gesetzt ist (nie das Token)."""
    if (err := A._require_api()):
        return err
    cfg = A.load_config()
    return jsonify({'enabled': bool(cfg.get('enable_mcp', False)),
                    'token_set': len(str(cfg.get('mcp_token') or '')) >= MIN_TOKEN_LEN,
                    'actions': bool(cfg.get('mcp_allow_actions', False))})


@bp.route('/api/mcp/token', methods=['POST'])
def api_mcp_token():
    """Neues Token erzeugen, sofort (verschlüsselt) speichern und genau diese eine
    Mal zurückgeben. Ein vorhandenes Token wird damit ungültig. Schaltet den
    MCP-Server gleich mit ein — wer ein Token erzeugt, will ihn nutzen."""
    if (err := A._require_api()):
        return err
    if not A.settings_store.crypto_ready():
        return jsonify({'error': 'crypto_unavailable'}), 400
    token = secrets.token_hex(32)
    try:
        A.settings_store.save({'mcp_token': token, 'enable_mcp': True})
    except OSError:
        return jsonify({'error': 'write_failed'}), 500
    A._settings_changed()
    A.log.info("MCP: neues Token erzeugt, das bisherige ist ungültig")
    return jsonify({'token': token})


@bp.route('/mcp', methods=['POST', 'GET', 'DELETE'])
def mcp_endpoint():
    if (err := _auth_error()):
        return err
    if request.method != 'POST':
        # Kein serverseitiger SSE-Stream, keine Sitzungen (zustandsloser Server)
        return Response(status=405, headers={'Allow': 'POST'})
    if (request.content_length or 0) > MAX_BODY:
        return jsonify(_err(None, -32600, 'Request too large')), 413
    try:
        body = json.loads(request.get_data(cache=False, as_text=True) or 'null')
    except ValueError:
        return jsonify(_err(None, -32700, 'Parse error')), 400
    if isinstance(body, list):                    # Batch (Protokoll 2025-03-26)
        replies = [r for r in (_handle(m) for m in body[:50]) if r is not None]
        return (jsonify(replies), 200) if replies else Response(status=202)
    reply = _handle(body)
    return (jsonify(reply), 200) if reply is not None else Response(status=202)
