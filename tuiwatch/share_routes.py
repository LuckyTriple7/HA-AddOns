"""Öffentliche Angebots-Seite („Share-Link") — Reisebüro-Stil.

Zwei getrennte Teile in einem Modul:

* `bp` — geschützte Admin-Routen (`/api/shares…`) auf der normalen App: Share
  anlegen, auflisten, verlängern, widerrufen.
* `share_app` — eine **eigene** Flask-App, die in `app.main()` auf einem zweiten
  Port (Standard 17796) lauscht und ausschließlich `/s/<token>` ausliefert. Nur
  dieser Port wird nach außen freigegeben (nginx); der reguläre Port 17794 mit
  Login, API und Ingress bleibt unangetastet.

Sicherheitsprinzip: die öffentliche Seite liest **niemals** die Live-Tabellen,
sondern nur den beim Anlegen eingefrorenen JSON-Snapshot (`shares.payload`), der
aus einer Feld-Whitelist (`_OFFER_FIELDS`) gebaut wird. Damit kann weder ein
anderes Angebot noch eine Buchung durchsickern — auch dann nicht, wenn `offers`
später neue Spalten bekommt. Kein Scrape, kein KI-Aufruf, kein Schreibzugriff
außer dem Aufrufzähler.
"""
import json
import re
import secrets
import time
from collections import defaultdict
from urllib.parse import quote, urlparse

from flask import (Blueprint, Flask, jsonify, make_response, render_template,
                   request, send_file)
from werkzeug.middleware.proxy_fix import ProxyFix

import app as A
import ai_routes
import offers_routes

bp = Blueprint('share_routes', __name__)

# Whitelist der Angebotsfelder, die auf der öffentlichen Seite landen dürfen.
# `url` ist die öffentliche TUI-Angebotsseite (Empfänger sollen dort nachsehen
# können). Bewusst NICHT dabei: pdf_url, booking_code, room_booking_code,
# target_price, booked_price, check24_*, tags, notify_*, paused/archived.
_OFFER_FIELDS = (
    'label', 'hotel', 'details', 'room', 'board', 'nights', 'dep_airport',
    'flight_out', 'flight_ret', 'location', 'city', 'region', 'country',
    'stars', 'rating', 'rating_count', 'recommendation', 'travellers_count',
    'return_date', 'image_url', 'price', 'total_price', 'cancellation', 'url',
)

# Diese Felder werden bei JEDEM Aufruf frisch aus der DB gelesen statt aus dem
# Schnappschuss — ein Link soll den aktuellen Preis und Buchungsstatus zeigen,
# nicht den Stand vom Erzeugen. Der Rest (Beschreibung, Bilder, Klima,
# Reiseführer, Reiseberater) bleibt eingefroren.
_LIVE_FIELDS = ('price', 'total_price', 'available', 'vac_ok', 'last_ts')

_TOKEN_RE = re.compile(r'^[A-Za-z0-9_-]{8,64}$')
_DEFAULT_DAYS = 30
_MAX_DAYS = 365
_MAX_OFFERS = 20          # ein Share bündelt eine Auswahl, keine ganze Datenbank
_HISTORY_POINTS = 60      # Preisverlauf ausgedünnt (Default ohnehin aus)

# Brute-Force-Bremse gegen Token-Raten. Bei 72 Bit Entropie reine
# Rauschunterdrückung, hält aber Scanner aus dem Log.
_fail_hits: dict[str, list[float]] = defaultdict(list)
_FAIL_WINDOW, _FAIL_MAX = 900, 20


# ── Snapshot bauen ────────────────────────────────────────────────────────────

def _price_points(con, offer_id: int) -> list:
    """Preisverlauf als [[ts, preis], …], auf ~`_HISTORY_POINTS` ausgedünnt."""
    rows = con.execute(
        'SELECT ts, price FROM price_history WHERE offer_id=? AND ok=1 '
        'AND price IS NOT NULL ORDER BY ts', (offer_id,)).fetchall()
    if len(rows) > _HISTORY_POINTS:
        step = len(rows) / _HISTORY_POINTS
        picked = [rows[int(i * step)] for i in range(_HISTORY_POINTS)]
        picked[-1] = rows[-1]          # letzter Punkt ist der aktuelle Preis
        rows = picked
    return [[r['ts'], r['price']] for r in rows]


def _build_payload(offer_ids: list, title: str, note: str, include: dict,
                   advisor_id=None) -> dict:
    """Friert die gewählten Angebote samt Zusatzinfos als JSON-Snapshot ein.

    Alle Zusatzdaten (Klima, Reiseführer, Reiseberater) sind bereits gespeicherte
    KI-Ergebnisse — hier wird nichts neu berechnet, es entstehen also keine
    Kosten."""
    wanted = [int(i) for i in offer_ids][:_MAX_OFFERS]
    by_id = {o['id']: o for o in A._collect_offers()}
    need_region = bool(include.get('climate') or include.get('guide'))
    offers, giatas = [], []
    with A.db() as con:
        for oid in wanted:
            o = by_id.get(oid)
            if not o:
                continue
            item = {k: o.get(k) for k in _OFFER_FIELDS}
            # Nur als Schlüssel für den Live-Abgleich beim Anzeigen (siehe
            # _refresh_live) — wird nie gerendert.
            item['id'] = oid
            item['available'] = o.get('available')
            item['vac_ok'] = o.get('vac_ok')
            item['last_ts'] = o.get('last_ts')
            if include.get('history'):
                item['history'] = _price_points(con, oid)
            offers.append(item)
            if need_region:
                # Klima/Reiseführer hängen an der Region-, nicht der Hotel-giataId
                region, _ = offers_routes.offer_region_giata(oid)
                if region and region not in giatas:
                    giatas.append(region)
    payload = {
        'v': 1,
        'title': title,
        'note': note,
        'created': int(time.time()),
        'offers': offers,
    }
    if include.get('climate'):
        payload['climate'] = [c for c in (ai_routes._climate_load(g) for g in giatas) if c]
    if include.get('guide'):
        payload['guide'] = [g for g in (ai_routes._guide_load(x) for x in giatas) if g]
    if include.get('advisor') and advisor_id:
        payload['advisor'] = _advisor_entry(advisor_id)
    return payload


def _advisor_entry(advisor_id):
    """Ein gespeichertes Reiseberater-Ergebnis (`ai_analyses`, kind='advisor')."""
    try:
        aid = int(advisor_id)
    except (TypeError, ValueError):
        return None
    with A.db() as con:
        row = con.execute(
            "SELECT title, summary, ts FROM ai_analyses WHERE id=? AND kind='advisor'",
            (aid,)).fetchone()
    if not row:
        return None
    return {'title': row['title'], 'summary': row['summary'], 'ts': row['ts']}


# ── Admin-API (geschützt, läuft auf der normalen App) ─────────────────────────

def _share_url(token: str) -> str:
    base = (A.load_config().get('public_base_url') or '').strip().rstrip('/')
    return f"{base}/s/{token}" if base else f"/s/{token}"


def _row_to_item(row) -> dict:
    payload = A._json_loads_safe(row['payload'], {}) or {}
    return {
        'token': row['token'], 'title': row['title'], 'note': row['note'],
        'created_ts': row['created_ts'], 'expires_ts': row['expires_ts'],
        'views': row['views'], 'last_view_ts': row['last_view_ts'],
        'offers': len(payload.get('offers') or []),
        'has_climate': bool(payload.get('climate')),
        'has_guide': bool(payload.get('guide')),
        'has_advisor': bool(payload.get('advisor')),
        'url': _share_url(row['token']),
        'expired': row['expires_ts'] < int(time.time()),
    }


@bp.route('/api/shares', methods=['GET'])
def api_shares():
    if (err := A._require_api()):
        return err
    cleanup_expired()
    with A.db() as con:
        rows = con.execute('SELECT * FROM shares ORDER BY created_ts DESC').fetchall()
    cfg = A.load_config()
    return jsonify({'items': [_row_to_item(r) for r in rows],
                    'base_url': (cfg.get('public_base_url') or '').strip(),
                    'enabled': bool(cfg.get('enable_public_share', False))})


@bp.route('/api/shares', methods=['POST'])
def api_share_create():
    if (err := A._require_api()):
        return err
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({'error': 'invalid'}), 400
    ids = data.get('offer_ids')
    if not isinstance(ids, list) or not ids:
        return jsonify({'error': 'no_offers'}), 400
    try:
        ids = [int(i) for i in ids]
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid'}), 400
    include = data.get('include') if isinstance(data.get('include'), dict) else {}
    title = str(data.get('title') or '').strip()[:120]
    note = str(data.get('note') or '').strip()[:2000]
    cfg = A.load_config()
    try:
        days = int(data.get('days') or cfg.get('public_share_days') or _DEFAULT_DAYS)
    except (TypeError, ValueError):
        days = _DEFAULT_DAYS
    days = max(1, min(_MAX_DAYS, days))

    payload = _build_payload(ids, title, note, include, data.get('advisor_id'))
    if not payload['offers']:
        return jsonify({'error': 'no_offers'}), 400
    token = secrets.token_urlsafe(12)
    now = int(time.time())
    with A.db() as con:
        con.execute(
            'INSERT INTO shares (token, title, note, payload, created_ts, expires_ts) '
            'VALUES (?,?,?,?,?,?)',
            (token, title, note, json.dumps(payload, ensure_ascii=False),
             now, now + days * 86400))
    A.log.info("Öffentlicher Share angelegt (%d Angebote, %d Tage gültig)",
               len(payload['offers']), days)
    return jsonify({'token': token, 'url': _share_url(token),
                    'expires_ts': now + days * 86400})


@bp.route('/api/shares/<token>', methods=['PATCH'])
def api_share_patch(token: str):
    """Nur die Gültigkeit verlängern — der Inhalt bleibt bewusst eingefroren."""
    if (err := A._require_api()):
        return err
    if not _TOKEN_RE.match(token):
        return jsonify({'error': 'not_found'}), 404
    data = request.get_json(silent=True) or {}
    try:
        days = int(data.get('days') or _DEFAULT_DAYS)
    except (TypeError, ValueError):
        days = _DEFAULT_DAYS
    days = max(1, min(_MAX_DAYS, days))
    expires = int(time.time()) + days * 86400
    with A.db() as con:
        cur = con.execute('UPDATE shares SET expires_ts=? WHERE token=?', (expires, token))
        if not cur.rowcount:
            return jsonify({'error': 'not_found'}), 404
    return jsonify({'expires_ts': expires})


@bp.route('/api/shares/<token>', methods=['DELETE'])
def api_share_delete(token: str):
    if (err := A._require_api()):
        return err
    if not _TOKEN_RE.match(token):
        return jsonify({'error': 'not_found'}), 404
    with A.db() as con:
        cur = con.execute('DELETE FROM shares WHERE token=?', (token,))
        if not cur.rowcount:
            return jsonify({'error': 'not_found'}), 404
    A.log.info("Öffentlicher Share widerrufen")
    return jsonify({'deleted': True})


def cleanup_expired() -> int:
    """Räumt abgelaufene Shares weg (vom Poller und beim Auflisten aufgerufen)."""
    with A.db() as con:
        cur = con.execute('DELETE FROM shares WHERE expires_ts < ?',
                          (int(time.time()) - 7 * 86400,))
    return cur.rowcount


# ── Öffentliche App (zweiter Port) ────────────────────────────────────────────

share_app = Flask('tuiwatch_share', template_folder=A._BASE + '/templates',
                  static_folder=None)
share_app.wsgi_app = ProxyFix(share_app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Ausschließlich diese Dateien sind öffentlich abrufbar — die Admin-Oberfläche
# (app.js) bleibt draußen, deshalb kein static_folder.
_PUBLIC_ASSETS = {
    'share.css': 'static/share.css',
    'share.js': 'static/share.js',
    'aimd.js': 'static/aimd.js',
    'icon-192.png': 'icon-192.png',
}

_CSP = ("default-src 'self'; img-src 'self' data: https:; "
        "style-src 'self' 'unsafe-inline'; script-src 'self'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


@share_app.template_filter('eur')
def _fmt_eur(value):
    """1234.5 → „1.235 €" (deutsche Tausenderpunkte, ohne Nachkommastellen)."""
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return ''
    return f"{n:,}".replace(',', '.') + ' €'


@share_app.template_filter('dt')
def _fmt_dt(ts):
    """Unix-Zeitstempel → „06.08.2026"."""
    try:
        return time.strftime('%d.%m.%Y', time.localtime(int(ts)))
    except (TypeError, ValueError):
        return ''


@share_app.template_filter('dtm')
def _fmt_dtm(ts):
    """Unix-Zeitstempel → „06.08.2026, 14:32 Uhr" (letzte Preisprüfung)."""
    try:
        return time.strftime('%d.%m.%Y, %H:%M', time.localtime(int(ts))) + ' Uhr'
    except (TypeError, ValueError):
        return ''


@share_app.template_filter('isodate')
def _fmt_isodate(value):
    """„2026-08-13" → „13.08.2026" (unverändert, wenn kein ISO-Datum)."""
    s = str(value or '').strip()
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', s):
        return s
    y, m, d = s.split('-')
    return f"{d}.{m}.{y}"


def _refresh_live(offers: list, with_history: bool) -> None:
    """Aktualisiert Preis und Verfügbarkeit aus der laufenden Datenbank.

    Bewusst eng gefasst: gelesen wird ausschließlich zu den im Schnappschuss
    hinterlegten Angebots-IDs und nur in `_LIVE_FIELDS`. Ein gelöschtes Angebot
    behält seinen letzten bekannten Stand aus dem Schnappschuss (`stale`), damit
    ein weitergegebener Link nicht plötzlich leer ist."""
    ids = [o['id'] for o in offers if o.get('id')]
    if not ids:
        return
    with A.db() as con:
        alive = {r['id'] for r in con.execute(
            'SELECT id FROM offers WHERE id IN (%s)' % ','.join('?' * len(ids)),
            ids).fetchall()}
        for o in offers:
            oid = o.get('id')
            if not oid:
                continue
            if oid not in alive:
                o['stale'] = True
                continue
            row = con.execute(
                'SELECT * FROM price_history WHERE offer_id=? ORDER BY ts DESC LIMIT 1',
                (oid,)).fetchone()
            total = con.execute('SELECT total_price FROM offers WHERE id=?',
                                (oid,)).fetchone()
            if total is not None:
                o['total_price'] = total['total_price']
            if row is None:
                continue
            if row['price'] is not None:
                o['price'] = row['price']
            elif (last_ok := con.execute(
                    'SELECT price FROM price_history WHERE offer_id=? AND ok=1 '
                    'AND price IS NOT NULL ORDER BY ts DESC LIMIT 1',
                    (oid,)).fetchone()):
                o['price'] = last_ok['price']
            o['available'] = None if row['available'] is None else bool(row['available'])
            o['vac_ok'] = None if row['vac_ok'] is None else bool(row['vac_ok'])
            o['last_ts'] = row['ts']
            if with_history:
                o['history'] = _price_points(con, oid)


def _tui_link(o: dict) -> str:
    """Angebots-URL, nur wenn sie wirklich auf tui.com zeigt — der Link steht auf
    einer öffentlichen Seite, da soll kein beliebiges Ziel hin."""
    url = (o.get('url') or '').strip()
    try:
        host = urlparse(url).hostname or ''
    except ValueError:
        return ''
    if urlparse(url).scheme != 'https':
        return ''
    return url if host == 'tui.com' or host.endswith('.tui.com') else ''


def _hc_link(o: dict) -> str:
    """HolidayCheck-Bewertungen über die Google-Seitensuche — dieselbe Mechanik
    wie in der Oberfläche (app.js) und im E-Mail-Versand: HolidayCheck hat keine
    stabile URL je Hotel, die sich aus den Angebotsdaten bilden ließe."""
    if o.get('rating') is None:
        return ''
    name = (o.get('hotel') or o.get('label') or '').strip()
    if not name:
        return ''
    where = (o.get('region') or o.get('country') or '').strip()
    q = f"site:holidaycheck.de {name} {where}".strip()
    return 'https://www.google.com/search?q=' + quote(q)


def _place(o: dict) -> str:
    """Ortszeile ohne Dopplungen — `location` enthält bereits Stadt und Region
    („Playa del Ingles, Gran Canaria"), stumpfes Aneinanderreihen aller vier
    Felder liest sich deshalb wie ein Stotterer."""
    out = []
    for val in (o.get('location'), o.get('city'), o.get('region'), o.get('country')):
        val = (val or '').strip()
        if not val:
            continue
        low = val.lower()
        if any(low in p.lower() for p in out):
            continue
        out = [p for p in out if p.lower() not in low]
        out.append(val)
    return ' · '.join(out)


_NIGHTS_RE = re.compile(r'^\s*(\d+)\s*N[äa]chte?\s+ab\s+([\d.]+)')


def _travel_line(o: dict) -> str:
    """„10 Nächte · 07.05.2027 – 17.05.2027" aus `details` + `return_date`.

    `details` ist eine lange Sammelzeile („… · 1 Erwachsener · Double Room · Alles
    Inklusive · inkl. Flug ab Stuttgart"), deren Bestandteile auf der Seite schon
    in eigenen Feldern stehen — hier interessiert nur der Zeitraum."""
    m = _NIGHTS_RE.match(o.get('details') or '')
    ret = _fmt_isodate(o.get('return_date'))
    if not m:
        return ret
    span = f"{m.group(2)} – {ret}" if ret else f"ab {m.group(2)}"
    return f"{m.group(1)} Nächte · {span}"


_SPARK_W, _SPARK_H = 320, 60


def _spark(points: list) -> dict | None:
    """Preisverlauf als fertiger SVG-Pfad — serverseitig gerechnet, damit die
    öffentliche Seite ohne Chart-Bibliothek und ohne Inline-Script auskommt."""
    pts = [(t, p) for t, p in (points or []) if p is not None]
    if len(pts) < 2:
        return None
    prices = [p for _, p in pts]
    lo, hi = min(prices), max(prices)
    span = (hi - lo) or 1
    step = _SPARK_W / (len(pts) - 1)
    coords = [(round(i * step, 1),
               round(_SPARK_H - 4 - (p - lo) / span * (_SPARK_H - 8), 1))
              for i, (_, p) in enumerate(pts)]
    d = 'M' + ' L'.join(f"{x},{y}" for x, y in coords)
    return {'d': d, 'area': f"{d} L{_SPARK_W},{_SPARK_H} L0,{_SPARK_H} Z",
            'min': lo, 'max': hi, 'first_ts': pts[0][0], 'last_ts': pts[-1][0]}


@share_app.after_request
def _public_headers(resp):
    resp.headers['X-Robots-Tag'] = 'noindex, nofollow'
    resp.headers['X-Frame-Options'] = 'DENY'
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['Referrer-Policy'] = 'no-referrer'
    resp.headers['Content-Security-Policy'] = _CSP
    return resp


def _rate_limited(ip: str) -> bool:
    now = time.time()
    hits = [t for t in _fail_hits[ip] if now - t < _FAIL_WINDOW]
    _fail_hits[ip] = hits
    return len(hits) >= _FAIL_MAX


def _note_fail(ip: str) -> None:
    _fail_hits[ip].append(time.time())


def _error_page(code: int, headline: str, text: str):
    resp = make_response(render_template('share_error.html', headline=headline,
                                         text=text), code)
    return resp


@share_app.route('/s/<token>', methods=['GET'])
def public_share(token: str):
    ip = A.get_client_ip(request)
    if _rate_limited(ip):
        return _error_page(429, 'Zu viele Anfragen',
                           'Bitte später noch einmal versuchen.')
    if not _TOKEN_RE.match(token):
        _note_fail(ip)
        return _error_page(404, 'Nicht gefunden', 'Dieser Link existiert nicht.')
    with A.db() as con:
        row = con.execute('SELECT * FROM shares WHERE token=?', (token,)).fetchone()
        if not row:
            _note_fail(ip)
            return _error_page(404, 'Nicht gefunden',
                               'Dieser Link existiert nicht (mehr).')
        now = int(time.time())
        if row['expires_ts'] < now:
            return _error_page(410, 'Link abgelaufen',
                               'Dieser Link ist nicht mehr gültig. '
                               'Frag einfach nach einem neuen.')
        con.execute('UPDATE shares SET views=views+1, last_view_ts=? WHERE token=?',
                    (now, token))
    payload = A._json_loads_safe(row['payload'], None)
    if not isinstance(payload, dict):
        return _error_page(404, 'Nicht gefunden', 'Dieser Link existiert nicht (mehr).')
    offers = payload.get('offers') or []
    _refresh_live(offers, with_history=any(o.get('history') for o in offers))
    for o in offers:
        o['place'] = _place(o)
        o['travel'] = _travel_line(o)
        o['tui_url'] = _tui_link(o)
        o['hc_url'] = _hc_link(o)
        if o.get('history'):
            o['spark'] = _spark(o['history'])
    return make_response(render_template(
        'share.html', p=payload, offers=payload.get('offers') or [],
        climate=payload.get('climate') or [], guide=payload.get('guide') or [],
        advisor=payload.get('advisor'), expires_ts=row['expires_ts'],
        app_version=A.APP_VERSION))


@share_app.route('/a/<name>', methods=['GET'])
def public_asset(name: str):
    rel = _PUBLIC_ASSETS.get(name)
    if not rel:
        return _error_page(404, 'Nicht gefunden', 'Diese Datei gibt es nicht.')
    return send_file(f"{A._BASE}/{rel}")


@share_app.route('/robots.txt', methods=['GET'])
def public_robots():
    resp = make_response("User-agent: *\nDisallow: /\n")
    resp.headers['Content-Type'] = 'text/plain; charset=utf-8'
    return resp


@share_app.errorhandler(404)
def _public_404(_e):
    return _error_page(404, 'Nicht gefunden', 'Diese Seite gibt es nicht.')


@share_app.errorhandler(405)
def _public_405(_e):
    return _error_page(404, 'Nicht gefunden', 'Diese Seite gibt es nicht.')
