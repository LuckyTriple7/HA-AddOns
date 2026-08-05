"""Preiskalender (Snapshot, Trend-Historie, Bewegungen, Routen) — ausgelagert
aus app.py (Backlog #12, 2. Tranche). Geteilte Primitiven (db, log,
fetch_calendar, Notify, A._calendar_state/-lock) über `import app as A`
mit spätem Attribut-Zugriff — Test-Monkeypatches auf dem app-Namespace
(m.fetch_calendar, m._notify_ha, ...) bleiben wirksam.
"""
import json
import re
import time
from collections import defaultdict

from flask import Blueprint, jsonify

import app as A

bp = Blueprint('price_calendar', __name__)


# ── Preiskalender (on-demand, gespeichert) ──────────────────────────────────────

def _store_calendar_snapshot(con, offer_id: int, cal: dict) -> list[str]:
    """Speichert einen frisch abgerufenen Preiskalender: überschreibt wie bisher den
    kompletten Snapshot in `calendar_cache` (unverändert für UI/Buchungsscore) UND
    schreibt Delta-codierte Zeilen in `calendar_history` — nur für Tage, deren Preis
    sich seit dem letzten bekannten Wert für dieses (offer_id, travel_date) geändert
    hat (oder die zum ersten Mal beobachtet werden). Verglichen wird gegen den noch
    nicht überschriebenen VORHERIGEN calendar_cache-Snapshot, kein Zusatz-Read der
    (potenziell großen) Trend-Tabelle nötig.

    Rückgabe: Liste der Reisedaten mit einer ECHTEN Preisänderung (Tag war vorher schon
    mit einem Preis bekannt, jetzt anders) — für Benachrichtigungen. Schließt bewusst
    Tage aus, die nur neu ins Kalenderfenster gerutscht sind (kein Vorwert vorhanden,
    z.B. globaler Erstabruf) — dafür gibt es keinen sinnvollen Vergleichswert, also
    keine "Preisänderung"."""
    ts = int(time.time())
    prev_row = con.execute('SELECT ts, data FROM calendar_cache WHERE offer_id=?',
                           (offer_id,)).fetchone()
    prev_prices: dict = {}
    if prev_row:
        try:
            prev_prices = {d['date']: d['price']
                           for d in json.loads(prev_row['data']).get('days', [])}
        except (ValueError, TypeError, KeyError):
            prev_prices = {}
    con.execute('INSERT OR REPLACE INTO calendar_cache (offer_id, ts, data) VALUES (?,?,?)',
                (offer_id, ts, json.dumps(cal)))
    days = cal.get('days', [])
    real_changed = [d['date'] for d in days
                    if d['date'] in prev_prices and prev_prices[d['date']] != d['price']]
    if real_changed:
        # Baseline-Heilung: stammt der vorherige Snapshot aus einer Zeit VOR der
        # calendar_history-Tabelle (Cache < 0.43.11) oder wurde die Historie geleert,
        # fehlt für einen jetzt geänderten Tag der Vorwert in der Historie — dann
        # hätte er nur EINE Zeile (den neuen Preis), _calendar_moves() (braucht >=2)
        # fände kein Delta und der calendar_trend_min_diff-Filter würde die Änderung
        # verschlucken. Der Vorwert steht aber noch im alten Cache: hier als
        # rückdatierte Zeile nachtragen, damit Delta/Trend/Alarm funktionieren.
        have = {r['travel_date'] for r in con.execute(
            'SELECT DISTINCT travel_date FROM calendar_history WHERE offer_id=?',
            (offer_id,)).fetchall()}
        prev_ts = min(prev_row['ts'], ts - 1)
        baseline = [(offer_id, d, prev_ts, prev_prices[d])
                    for d in real_changed if d not in have]
        if baseline:
            con.executemany(
                'INSERT INTO calendar_history (offer_id, travel_date, ts, price) VALUES (?,?,?,?)',
                baseline)
    changed = [(offer_id, d['date'], ts, d['price']) for d in days
               if prev_prices.get(d['date']) != d['price']]
    if changed:
        con.executemany(
            'INSERT INTO calendar_history (offer_id, travel_date, ts, price) VALUES (?,?,?,?)',
            changed)
    return real_changed


_MONTH_NAMES_DE = ('Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August',
                    'September', 'Oktober', 'November', 'Dezember')


def _month_name_de(ym: str) -> str:
    """'2027-05' -> 'Mai 2027'."""
    y, m = ym.split('-')
    return f"{_MONTH_NAMES_DE[int(m) - 1]} {y}"


def _format_month_list_de(months: list[str]) -> str:
    names = [_month_name_de(m) for m in months]
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " und " + names[-1]


def _check_calendar_trend_alert(offer_id: int, changed_dates: list[str]) -> None:
    """Meldet Preisänderungen im Kalender für bereits bekannte Reisedaten — bewusst
    grob (Hotelname + Monat(e), kein Datum/Preis, siehe _store_calendar_snapshot für
    die Definition von 'echte Änderung'). Gated durch notify_calendar_trend, und
    gefiltert auf Tage mit einer Bewegung >= calendar_trend_min_diff (€) — winzige
    Änderungen (z. B. 10 € bei 2000+ € Reisepreis) sollen nicht benachrichtigen.
    Die Storage-Seite (calendar_history/Trend-Ansicht) bleibt davon unberührt und
    zeigt weiterhin JEDE Änderung, unabhängig von dieser Schwelle."""
    if not changed_dates:
        return
    cfg = A.load_config()
    if not cfg.get('notify_calendar_trend', True):
        return
    min_diff = max(0, int(cfg.get('calendar_trend_min_diff', 20) or 0))
    with A.db() as con:
        offer = con.execute('SELECT label, hotel, url, notify_calendar_muted FROM offers WHERE id=?',
                            (offer_id,)).fetchone()
        moves = _calendar_moves(con, offer_id)   # auch fürs Detail-Log unten gebraucht
    if not offer:
        return
    if min_diff > 0:
        changed_dates = [d for d in changed_dates
                         if abs(moves.get(d, {}).get('delta', 0)) >= min_diff]
        if not changed_dates:
            return
    months = sorted({d[:7] for d in changed_dates})
    month_str = _format_month_list_de(months)
    name = offer['label'] or offer['hotel'] or f"Angebot #{offer_id}"
    A.log.info("📅 Kalenderpreise geändert (#%d %s): %d Tag(e) in %s → Benachrichtigung",
             offer_id, name, len(changed_dates), month_str)
    if A._verbose():
        # Nur bei aktiviertem "Ausführliches Logging" — Nachricht/HA-Notify bleiben
        # bewusst grob (kein Datum/Preis), aber fürs Debuggen (z. B. Diskrepanz
        # zwischen Meldung und dem, was später im Kalender/calendar_history zu
        # sehen ist) hilft die genaue Aufschlüsselung ungemein. missing = Daten,
        # die _store_calendar_snapshot als "geändert" einstufte, aber die JETZT
        # (gleicher DB-Request) _calendar_moves() nicht mehr als 2-Punkt-Historie
        # findet — sollte eigentlich nie vorkommen, ist aber genau das Symptom,
        # falls calendar_history zwischenzeitlich geleert wurde/wird.
        found = sorted(d for d in changed_dates if d in moves)
        missing = sorted(d for d in changed_dates if d not in moves)
        details = "; ".join(
            f"{d}: {moves[d]['prev_price']}→{moves[d]['price']} €"
            f" ({'+' if moves[d]['delta']>0 else ''}{moves[d]['delta']} €)" for d in found)
        A.log.info("📅 Kalender-Details (#%d %s): %s%s", offer_id, name,
                 details or "(keine)",
                 f" | OHNE Historie-Treffer: {', '.join(missing)}" if missing else "")
    muted = bool(offer['notify_calendar_muted'])
    A._notify_ha(f"📅 Kalenderpreise geändert: {name}",
               f"{name}\nPreisänderungen im Preiskalender für {month_str}.\n{offer['url']}",
               f"caltrend_{offer_id}", muted=muted)
    A._notify_telegram(f"📅 <b>Kalenderpreise geändert</b>\n{name}\n{month_str}\n{offer['url']}", muted=muted)


def _run_calendar(offer_id: int) -> None:
    """Liest den Preiskalender (Preis je Abreisetag) und speichert ihn in der DB."""
    try:
        with A.db() as con:
            offer = con.execute('SELECT url FROM offers WHERE id=?', (offer_id,)).fetchone()
        if not offer:
            with A._calendar_lock:
                A._calendar_state[offer_id] = {'status': 'error', 'note': 'Angebot nicht gefunden'}
            return
        res = A.fetch_calendar(offer['url'], verbose=A._verbose())
        if not res or not res.get('ok'):
            A.log.warning("Preiskalender #%d: keine Daten/nicht abrufbar", offer_id)
            with A._calendar_lock:
                A._calendar_state[offer_id] = {'status': 'error', 'note': 'Preiskalender nicht abrufbar'}
            return
        with A.db() as con:
            changed = _store_calendar_snapshot(con, offer_id, res)
        _check_calendar_trend_alert(offer_id, changed)
        with A._calendar_lock:
            A._calendar_state.pop(offer_id, None)
        A.log.info("Preiskalender #%d: %d Tage, günstigster %s (%s €)", offer_id,
                 len(res.get('days', [])), res.get('cheapest_date'), res.get('cheapest_price'))
    except Exception as e:
        A.log.error("Preiskalender #%d Fehler: %s", offer_id, e)
        with A._calendar_lock:
            A._calendar_state[offer_id] = {'status': 'error', 'note': 'Preiskalender fehlgeschlagen'}


def _calendar_moves(con, offer_id: int) -> dict[str, dict]:
    """Letzte bekannte Preisbewegung je Reisedatum aus calendar_history: für jedes
    Datum werden nur die zwei jüngsten bekannten Preise verglichen (Tage ohne
    Änderung erzeugen ja keine neue Zeile, siehe _store_calendar_snapshot). Rückgabe:
    {travel_date: {price, prev_price, delta, ts}} — nur für Daten mit >=2 bekannten
    Preisen."""
    rows = con.execute(
        'SELECT travel_date, ts, price FROM calendar_history WHERE offer_id=? '
        'ORDER BY travel_date, ts', (offer_id,)).fetchall()
    by_date: dict[str, list] = defaultdict(list)
    for r in rows:
        by_date[r['travel_date']].append((r['ts'], r['price']))
    moves = {}
    for d, pts in by_date.items():
        if len(pts) < 2:
            continue
        (_, prev_price), (last_ts, last_price) = pts[-2], pts[-1]
        moves[d] = {'price': last_price, 'prev_price': prev_price,
                    'delta': last_price - prev_price, 'ts': last_ts}
    return moves


def _calendar_top_moves(moves: dict, limit: int = 12) -> list[dict]:
    """Größte Bewegungen (nach Betrag) aus _calendar_moves(), für die 'Größte
    Bewegungen seit letztem Abruf'-Liste."""
    return sorted(
        ({'date': d, **v} for d, v in moves.items()),
        key=lambda m: abs(m['delta']), reverse=True)[:limit]


def _calendar_date_history(con, offer_id: int, travel_date: str) -> list[dict]:
    """Preisverlauf EINES Reisedatums über alle Snapshots — Datenquelle für den
    Mini-Zeitreihen-Chart bei Klick auf einen Kalendertag."""
    return [dict(r) for r in con.execute(
        'SELECT ts, price FROM calendar_history WHERE offer_id=? AND travel_date=? '
        'ORDER BY ts', (offer_id, travel_date)).fetchall()]


def _calendar_moves_since(con, offer_id: int, since_ts: int) -> list[str]:
    """Monate mit echter Preisänderung (nicht Erstsichtung) seit `since_ts` — für den
    Wochenüberblick. 'Echt' = es existiert eine FRÜHERE calendar_history-Zeile für
    dasselbe Reisedatum (sonst ist der Tag nur neu ins Kalenderfenster gerutscht).
    Vergleich über `id` statt `ts`: `ts` ist nur sekundengenau, zwei Snapshots
    innerhalb derselben Sekunde (schnelles "Neu abfragen") wären mit `ts<ts` sonst
    nicht als "frühere Zeile" erkennbar — `id` (AUTOINCREMENT) bleibt strikt
    monoton in Einfügereihenfolge."""
    rows = con.execute(
        'SELECT DISTINCT ch.travel_date FROM calendar_history ch WHERE ch.offer_id=? '
        'AND ch.ts>=? AND EXISTS (SELECT 1 FROM calendar_history p WHERE '
        'p.offer_id=ch.offer_id AND p.travel_date=ch.travel_date AND p.id<ch.id)',
        (offer_id, since_ts)).fetchall()
    return sorted({r['travel_date'][:7] for r in rows})


def _calendar_payload(offer_id: int) -> dict:
    with A._calendar_lock:
        st = dict(A._calendar_state.get(offer_id) or {})
    if st.get('status') == 'running':
        return {'status': 'running'}
    with A.db() as con:
        row = con.execute('SELECT ts, data FROM calendar_cache WHERE offer_id=?',
                          (offer_id,)).fetchone()
        moves = _calendar_moves(con, offer_id) if row else {}
    if row:
        out = A._json_loads_safe(row['data'], {})
        out['status'] = 'done'
        out['ts'] = row['ts']
        out['moves'] = moves
        out['top_moves'] = _calendar_top_moves(moves)
        # Der teuerste Termin kam erst später dazu (v0.67.0). Für Snapshots, die
        # davor abgerufen wurden, hier aus den Tagesdaten nachrechnen — sonst müsste
        # der Nutzer jeden Kalender neu abrufen, nur um die Spanne zu sehen.
        if 'priciest_date' not in out:
            prices = {d['date']: d['price'] for d in (out.get('days') or [])
                      if d.get('price') is not None}
            if prices:
                xd = max(prices, key=prices.get)
                out['priciest_date'], out['priciest_price'] = xd, prices[xd]
    else:
        out = {'status': 'idle'}
    if st.get('status') == 'error':
        out['error'] = st.get('note', 'Preiskalender fehlgeschlagen')
    return out


@bp.route('/api/calendar/<int:offer_id>', methods=['POST'])
def api_calendar_start(offer_id: int):
    if (err := A._require_api()):
        return err
    with A._calendar_lock:
        if A._calendar_state.get(offer_id, {}).get('status') == 'running':
            return jsonify({'started': True, 'already': True})
    with A.db() as con:
        exists = con.execute('SELECT 1 FROM offers WHERE id=?', (offer_id,)).fetchone()
    if not exists:
        return jsonify({'error': 'not_found'}), 404
    with A._calendar_lock:
        A._calendar_state[offer_id] = {'status': 'running'}
    A.log.info("Preiskalender-Abruf gestartet: Angebot #%d", offer_id)
    A._spawn(_run_calendar, offer_id)
    return jsonify({'started': True})


@bp.route('/api/calendar/<int:offer_id>', methods=['GET'])
def api_calendar_get(offer_id: int):
    if (err := A._require_api()):
        return err
    payload = _calendar_payload(offer_id)
    if payload.get('status') == 'done':
        # Angezeigt -> Trend-Blinken auf dem "Kalender"-Button erlischt bis zur
        # naechsten Preisaenderung (siehe calendar_alert in _collect_offers()).
        with A.db() as con:
            con.execute('UPDATE offers SET calendar_seen_ts=? WHERE id=?',
                        (int(time.time()), offer_id))
    return jsonify(payload)


@bp.route('/api/calendar/<int:offer_id>/day/<travel_date>', methods=['GET'])
def api_calendar_day_history(offer_id: int, travel_date: str):
    """Preisverlauf eines einzelnen Reisedatums über alle Kalender-Snapshots — für
    den Mini-Chart bei Klick auf einen Kalendertag."""
    if (err := A._require_api()):
        return err
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', travel_date or ''):
        return jsonify({'error': 'bad_date'}), 400
    with A.db() as con:
        if not con.execute('SELECT 1 FROM offers WHERE id=?', (offer_id,)).fetchone():
            return jsonify({'error': 'not_found'}), 404
        points = _calendar_date_history(con, offer_id, travel_date)
    return jsonify({'date': travel_date, 'points': points})

