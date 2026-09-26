"""Flugzeiten-Wächter für gebuchte Reisen („Meine Reisen").

Der PDF-Import kennt je Flug Datum, Strecke, Uhrzeit und Flugnummer. Vier
Flughäfen liest TUIWatch ohnehin schon (STR, FRA, MUC, FKB — siehe die
`*_flights_client.py`). Einmal am Tag gleicht dieses Modul die kommenden Flüge
gegen den Plan des jeweiligen Heimatflughafens ab und meldet:

- **geänderte Uhrzeit** — Abflug (Hinflug) bzw. Ankunft (Rückflug) am
  Heimatflughafen weicht von der gebuchten Zeit ab;
- **Flug nicht mehr im Plan** — der Plan deckt das Datum ab, führt die
  Flugnummer an dem Tag aber nicht mehr. Erst beim zweiten Abgleich in Folge,
  damit ein einzelner Parser-Aussetzer (MUC kommt aus einem PDF) keinen
  Fehlalarm auslöst. Gleichzeitig nennt die Meldung, was am selben Tag auf der
  Strecke fliegt — oft hat TUI nur die Nummer getauscht;
- **Entwarnung**, wenn ein gemeldeter Flug wieder wie gebucht im Plan steht.

Verglichen wird immer nur die Zeit am Heimatflughafen: nur die steht in jedem
der vier Pläne in derselben Zeitzone wie in der Buchung. Liegt das Datum jenseits
des veröffentlichten Plans (Sommerflüge im Winter), heißt der Zustand
`pending` und es gibt keine Meldung. Die Quelle ist der Flughafen, nicht TUI —
die Meldung sagt das dazu.
"""
import json
import logging
import re
import time
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify

import app as A

log = logging.getLogger('tuiwatch')

bp = Blueprint('flight_watch', __name__)

WATCH_INTERVAL = 86400        # regulärer Abgleich 1×/Tag
MISSING_CONFIRM = 2           # „nicht im Plan" erst nach so vielen Abgleichen in Folge
HOME_AIRPORTS = ('STR', 'FRA', 'MUC', 'FKB')

_IATA_RE = re.compile(r'\(([A-Z]{3})\)')
_FNO_RE = re.compile(r'([A-Z0-9]{2})\s*0*(\d{1,4})[A-Z]?')
_WEEKDAYS = ('Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So')


def init_db(con) -> None:
    """Letzter Abgleich je Flug einer Reise — wird aus `app.init_db` gerufen.
    `flight` hält Datum|Flugnummer|Zeit der Buchung fest: ändert sich der Flug
    durch einen Neu-Import, beginnt der Zustand von vorn."""
    con.execute('''CREATE TABLE IF NOT EXISTS trip_flight_checks (
        trip_id      INTEGER NOT NULL,
        idx          INTEGER NOT NULL,
        flight       TEXT NOT NULL,
        status       TEXT NOT NULL,
        airport      TEXT NOT NULL DEFAULT '',
        plan_time    TEXT NOT NULL DEFAULT '',
        note         TEXT NOT NULL DEFAULT '',
        miss_streak  INTEGER NOT NULL DEFAULT 0,
        notified_sig TEXT NOT NULL DEFAULT '',
        checked_ts   INTEGER NOT NULL,
        PRIMARY KEY (trip_id, idx),
        FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE
    )''')


# ── Normalisieren ───────────────────────────────────────────────────────────────

def parse_flight_no(text: str) -> tuple[str, int] | None:
    """'TUIfly X32168' / 'X3 2168' / 'EW2648' → ('X3', 2168). Airline-Codes sind
    zweistellig (IATA), deshalb ist 'X32168' eindeutig zerlegbar."""
    parts = (text or '').strip().split()
    if not parts:
        return None
    for cand in (''.join(parts[-2:]) if len(parts) >= 2 else '', parts[-1]):
        m = _FNO_RE.fullmatch(cand.upper()) if cand else None
        if m:
            return m.group(1), int(m.group(2))
    return None


def _iata(text: str) -> str:
    m = _IATA_RE.search(text or '')
    return m.group(1) if m else ''


def _hhmm(t: str) -> str:
    m = re.match(r'(\d{1,2}):(\d{2})', (t or '').strip())
    return f'{int(m.group(1)):02d}:{m.group(2)}' if m else ''


def _days(short: str) -> set[int]:
    """'Mo, Do' / 'MoDo' / 'täglich' → {0, 3}. Leer/'–' → alle Tage (unbekannt
    heißt: nicht am Wochentag scheitern lassen)."""
    s = short or ''
    if 'täglich' in s:
        return set(range(7))
    found = {i for i, d in enumerate(_WEEKDAYS) if d in s}
    return found or set(range(7))


def trip_flights(data: dict) -> list[dict]:
    """Die prüfbaren Flüge einer Reise: je Flug Heimatflughafen, Richtung und die
    gebuchte Zeit dort. Flüge ohne unterstützten Flughafen tauchen mit
    `home=''` auf (Zustand `unsupported`)."""
    out = []
    for idx, f in enumerate(data.get('fluege') or []):
        d = A._iso_date(f.get('datum'))
        key = parse_flight_no(f.get('flugnummer'))
        von, nach = _iata(f.get('von')), _iata(f.get('nach'))
        if von in HOME_AIRPORTS:
            home, other, direction, booked = von, nach, 'departure', f.get('abflug_zeit')
        elif nach in HOME_AIRPORTS:
            home, other, direction, booked = nach, von, 'arrival', f.get('ankunft_zeit')
        else:
            home, other, direction, booked = '', '', '', ''
        out.append({'idx': idx, 'date': d, 'key': key, 'home': home, 'other': other,
                    'direction': direction, 'booked': _hhmm(booked),
                    'typ': f.get('typ') or 'Flug', 'datum': f.get('datum') or '',
                    'label': f"{key[0]} {key[1]}" if key else (f.get('flugnummer') or '')})
    return out


# ── Flugpläne ───────────────────────────────────────────────────────────────────

def _seasonal_rows(airport: str) -> list[dict] | None:
    """Saisonplan (STR/MUC/FKB) auf eine gemeinsame Form gebracht:
    {dir, key, other, time, days, from, till}. `time` ist die Zeit am
    Heimatflughafen (Abflug bzw. Ankunft). None bei Abruffehler."""
    if airport == 'STR':
        import str_flights_client as S
        raw = S.search_connections('')
        if raw is None:
            return None
        rows = [{'dir': 'departure' if r['type'] == 'Departure' else 'arrival',
                 'fno': f"{r['airline_code']} {re.sub(r'[^0-9]', '', r['flight_no'])}",
                 **r} for r in raw]
    elif airport == 'MUC':
        import muc_flights_client as M
        res = M.search('', limit=10 ** 6)
        if res is None:
            return None
        rows = [{'dir': r['direction'], 'fno': r['flight_no'], **r} for r in res['rows']]
    elif airport == 'FKB':
        import fkb_flights_client as F
        res = F.search('', limit=10 ** 6)
        if res is None:
            return None
        rows = [{'dir': r['direction'], 'fno': r['flight_no'], **r} for r in res['rows']]
    else:
        return None
    out = []
    for r in rows:
        out.append({'dir': r['dir'], 'key': parse_flight_no(r['fno']),
                    'other': r.get('airport_code') or '',
                    'time': _hhmm(r['departure'] if r['dir'] == 'departure' else r['arrival']),
                    'days': _days(r.get('weekdays_short')),
                    'from': r.get('date_from') or '', 'till': r.get('date_till') or ''})
    return out


def _seasonal_on(rows: list[dict], direction: str, day: str) -> list[dict]:
    wd = date.fromisoformat(day).weekday()
    return [r for r in rows if r['dir'] == direction and wd in r['days']
            and (not r['from'] or r['from'] <= day) and (not r['till'] or day <= r['till'])]


def _check_seasonal(fl: dict, rows: list[dict]) -> dict:
    covered = max((r['till'] for r in rows if r['till']), default='') >= fl['date']
    days = _candidate_days(fl)
    hits = [r for d in days for r in _seasonal_on(rows, fl['direction'], d)
            if r['key'] == fl['key']]
    alts = [r for r in _seasonal_on(rows, fl['direction'], fl['date'])
            if r['other'] == fl['other'] and r['key'] != fl['key']]
    return _verdict(fl, [h['time'] for h in hits], covered,
                    [f"{a['key'][0]} {a['key'][1]} {a['time']}" for a in alts if a['key']])


def _check_fra(fl: dict, cache: dict) -> dict | None:
    """FRA kennt Einzelflüge je Datum statt Saisonstrecken. Abgedeckt ist ein
    Datum, sobald der Plan auf der Strecke Flüge an diesem Tag oder später führt
    — sonst ist die Strecke dort (noch) nicht veröffentlicht."""
    import fra_flights_client as F
    days = _candidate_days(fl)
    ft = 'departures' if fl['direction'] == 'departure' else 'arrivals'
    ck = (fl['other'], ft, days[0][:7], days[-1][:7])
    if ck not in cache:
        cache[ck] = F.search_flights(fl['other'], ft, days[0][:7], days[-1][:7], limit=1000)
    res = cache[ck]
    if res is None:
        return None
    rows = res.get('rows') or []

    def keys(r):
        return {parse_flight_no(x) for x in [r.get('flight_no')] + (r.get('codeshares') or [])}

    hits = [r['time'] for r in rows if r.get('date') in days and fl['key'] in keys(r)]
    covered = bool(res.get('truncated')) or any((r.get('date') or '') >= fl['date'] for r in rows)
    alts = [f"{r['flight_no']} {r['time']}" for r in rows
            if r.get('date') == fl['date'] and fl['key'] not in keys(r)]
    return _verdict(fl, [_hhmm(h) for h in hits], covered, alts)


def _candidate_days(fl: dict) -> list[str]:
    """Ankünfte am Heimatflughafen dürfen einen Tag später liegen (Nachtflug
    zurück) — je nach Plan steht der Flug unter dem Abflug- oder Ankunftstag."""
    if fl['direction'] == 'arrival':
        nxt = (date.fromisoformat(fl['date']) + timedelta(days=1)).isoformat()
        return [fl['date'], nxt]
    return [fl['date']]


def _verdict(fl: dict, hit_times: list[str], covered: bool, alts: list[str]) -> dict:
    if hit_times:
        if not fl['booked'] or fl['booked'] in hit_times:   # ohne gebuchte Zeit: nur Existenz
            return {'status': 'ok', 'plan_time': fl['booked'] or hit_times[0], 'note': ''}
        return {'status': 'changed', 'plan_time': hit_times[0], 'note': ''}
    if not covered:
        return {'status': 'pending', 'plan_time': '', 'note': ''}
    return {'status': 'missing', 'plan_time': '', 'note': ', '.join(sorted(set(alts))[:5])}


# ── Abgleich + Meldung ─────────────────────────────────────────────────────────

def _flight_sig(fl: dict) -> str:
    return f"{fl['date']}|{fl['label']}|{fl['booked']}"


def _upcoming_trips(con, trip_id: int | None = None):
    today = date.today().isoformat()
    return con.execute(
        'SELECT id, destination, hotel, title, data FROM trips '
        'WHERE COALESCE(end_date, start_date) >= ? AND (? IS NULL OR id=?) ORDER BY start_date',
        (today, trip_id, trip_id)).fetchall()


def check_trips(trip_id: int | None = None) -> int:
    """Gleicht die kommenden Flüge ab (alle Reisen oder nur `trip_id`), schreibt den
    Zustand und verschickt fällige Meldungen. Gibt die Zahl geprüfter Flüge zurück."""
    today = date.today().isoformat()
    with A.db() as con:
        trips = _upcoming_trips(con, trip_id)
    plans: dict[str, list | None] = {}
    fra_cache: dict = {}
    checked = 0
    for t in trips:
        data = A._json_loads_safe(t['data'], {})
        name = t['destination'] or t['hotel'] or t['title'] or f"Reise #{t['id']}"
        for fl in trip_flights(data):
            if not fl['date'] or fl['date'] < today:
                continue
            if not (fl['home'] and fl['key']):
                res = {'status': 'unsupported', 'plan_time': '', 'note': ''}
            elif fl['home'] == 'FRA':
                res = _check_fra(fl, fra_cache)
            else:
                if fl['home'] not in plans:
                    plans[fl['home']] = _seasonal_rows(fl['home'])
                rows = plans[fl['home']]
                res = _check_seasonal(fl, rows) if rows else None
            if res is None:
                res = {'status': 'error', 'plan_time': '', 'note': ''}
            _store_and_notify(t['id'], name, fl, res)
            checked += 1
    return checked


def _store_and_notify(trip_id: int, name: str, fl: dict, res: dict) -> None:
    sig = _flight_sig(fl)
    with A.db() as con:
        prev = con.execute('SELECT flight, miss_streak, notified_sig FROM trip_flight_checks '
                           'WHERE trip_id=? AND idx=?', (trip_id, fl['idx'])).fetchone()
    same = prev is not None and prev['flight'] == sig
    streak = (prev['miss_streak'] if same else 0)
    notified = (prev['notified_sig'] if same else '')
    status = res['status']
    if status == 'missing':
        streak += 1
    elif status != 'error':
        streak = 0

    alert = ''
    if status == 'changed':
        alert = f"changed|{res['plan_time']}"
    elif status == 'missing' and streak >= MISSING_CONFIRM:
        alert = 'missing'
    elif status == 'missing' and notified == 'missing':
        alert = 'missing'          # bleibt gemeldet, solange er fehlt

    new_notified = notified
    if status == 'error' or (status == 'missing' and not alert):
        pass                        # Zustand offen — nichts melden, nichts zurücknehmen
    elif alert and alert != notified:
        _send(name, fl, res, alert)
        new_notified = alert
    elif not alert and notified and status == 'ok':
        _send(name, fl, res, 'ok')
        new_notified = ''
    elif not alert:
        new_notified = ''

    with A.db() as con:
        con.execute(
            'INSERT OR REPLACE INTO trip_flight_checks (trip_id, idx, flight, status, airport, '
            'plan_time, note, miss_streak, notified_sig, checked_ts) VALUES (?,?,?,?,?,?,?,?,?,?)',
            (trip_id, fl['idx'], sig, status, fl['home'], res['plan_time'], res['note'],
             streak, new_notified, int(time.time())))


def _send(name: str, fl: dict, res: dict, kind: str) -> None:
    where = 'Abflug' if fl['direction'] == 'departure' else 'Ankunft'
    head = f"{fl['typ']} am {fl['datum']} ({fl['label']})"
    src = f"Quelle: Flugplan des Flughafens {fl['home']}, nicht TUI — im Zweifel bei TUI nachsehen."
    if kind.startswith('changed'):
        title = f"✈️ Flugzeit geändert: {name}"
        body = (f"{head}: {where} {fl['home']} jetzt {res['plan_time']} Uhr "
                f"statt {fl['booked']} Uhr.")
    elif kind == 'missing':
        title = f"✈️ Flug nicht mehr im Flugplan: {name}"
        body = f"{head} steht nicht mehr im Flugplan {fl['home']}."
        if res['note']:
            body += f" Am selben Tag auf der Strecke: {res['note']}."
    else:
        title = f"✈️ Flug wieder wie gebucht: {name}"
        body = f"{head}: {where} {fl['home']} wieder {fl['booked']} Uhr laut Flugplan."
    log.info("%s — %s", title, body)
    tag = f"flight_{fl['idx']}_{re.sub(r'[^0-9A-Za-z]', '', fl['label'])}_{fl['date']}"
    A._notify_ha(title, f"{body}\n{src}", tag)
    A._notify_telegram(f"<b>{A._esc_html(title)}</b>\n{A._esc_html(body)}\n"
                       f"<i>{A._esc_html(src)}</i>")


def _unchecked_exist() -> bool:
    """Gibt es kommende Flüge ohne Abgleich (neu importierte Reise)? Dann wartet
    der nächste Abgleich nicht bis morgen."""
    today = date.today().isoformat()
    with A.db() as con:
        trips = _upcoming_trips(con)
        done = {(r['trip_id'], r['idx']): r['flight'] for r in con.execute(
            'SELECT trip_id, idx, flight FROM trip_flight_checks').fetchall()}
    for t in trips:
        for fl in trip_flights(A._json_loads_safe(t['data'], {})):
            if fl['date'] and fl['date'] >= today and done.get((t['id'], fl['idx'])) != _flight_sig(fl):
                return True
    return False


def maybe_check_flights() -> None:
    """Poller-Schritt: 1×/Tag, und sofort, sobald eine neue Reise ungeprüft ist."""
    if not A.load_config().get('notify_flight_changes', True):
        return
    try:
        last = int(A._meta_get('flight_watch_ts', 0) or 0)
    except ValueError:
        last = 0
    if time.time() - last < WATCH_INTERVAL and not _unchecked_exist():
        return
    n = check_trips()
    A._meta_set('flight_watch_ts', int(time.time()))
    if n:
        log.info("Flugzeiten-Abgleich: %d Flug/Flüge geprüft", n)


def flight_checks_for(con, trip_id: int) -> list[dict]:
    """Zustand je Flug für die Detailansicht (nur zum aktuell gebuchten Flug
    passende Zeilen — ein veralteter Stand nach Neu-Import bleibt unsichtbar)."""
    row = con.execute('SELECT data FROM trips WHERE id=?', (trip_id,)).fetchone()
    if not row:
        return []
    sigs = {fl['idx']: _flight_sig(fl) for fl in trip_flights(A._json_loads_safe(row['data'], {}))}
    out = []
    for r in con.execute('SELECT * FROM trip_flight_checks WHERE trip_id=? ORDER BY idx',
                         (trip_id,)).fetchall():
        if sigs.get(r['idx']) == r['flight']:
            out.append({'idx': r['idx'], 'status': r['status'], 'airport': r['airport'],
                        'plan_time': r['plan_time'], 'note': r['note'],
                        'checked': datetime.fromtimestamp(r['checked_ts']).isoformat()})
    return out


@bp.route('/api/trips/<int:tid>/flights/check', methods=['POST'])
def api_trip_flights_check(tid):
    """„Flugplan prüfen" in der Reise-Detailansicht — sofortiger Abgleich einer Reise."""
    if (err := A._require_api()):
        return err
    try:
        check_trips(tid)
    except Exception as e:
        log.error("Flugzeiten-Abgleich Reise #%d fehlgeschlagen: %s", tid, type(e).__name__)
        return jsonify({'error': 'check_failed'}), 502
    with A.db() as con:
        return jsonify({'flight_checks': flight_checks_for(con, tid)})
