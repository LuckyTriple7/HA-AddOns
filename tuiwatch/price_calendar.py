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
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify

import app as A

bp = Blueprint('price_calendar', __name__)


# ── Monatstrend: Schema ────────────────────────────────────────────────────────
# Der Preiskalender liefert eine ganz andere Grundgesamtheit als das Preisbarometer:
# dort viele Hotels für EINEN Termin, hier EIN Hotel/Zimmer für 400–700 Reisetage.
# Das Zusammensetzungsproblem, das im Barometer die Matched Pairs erzwingt, gibt es
# hier nicht — die Menge der Reisetage ist fest. Deshalb darf (und soll) hier ein
# echter wertgewichteter Monatsindex gerechnet werden statt eines Medians:
#
#     pct_Monat = (Σ p_neu − Σ p_alt) / Σ p_alt · 100
#
# summiert über alle Reisetage des Monats, die in BEIDEN Snapshots einen Preis hatten.
# Der entscheidende Punkt steckt im Nenner: `calendar_history` ist delta-codiert
# (eine Zeile nur bei Änderung, siehe `_store_calendar_snapshot`). Wer nur die
# geänderten Tage betrachtet, misst deshalb ausschließlich Tage, an denen sich etwas
# bewegt hat, und der Index läuft massiv davon. Unveränderte Tage zählen hier mit
# ihrem Preis in den Nenner und mit 0 in den Zähler — genau die richtige Dämpfung.

CAL_MONTH_MAX_PCT = 60.0    # Tagessprünge darüber sind Artefakte (Zimmerkategorie/
                            # Verfügbarkeit), kein Marktsignal — fliegen raus
CAL_MONTH_MIN_DAYS = 2      # weniger Beobachtungstage → kein Trend
CAL_MONTH_WINDOW = 14       # Tage im rollierenden Trendfenster, wie beim Markttrend


def init_month_db(con) -> None:
    """Tabelle für die verdichtete Monatsbewegung — wird aus `app.init_db` gerufen.
    Eine Zeile je (Angebot, Beobachtungstag, Reisemonat); bei ~18 Monaten also rund
    18 Zeilen pro Kalenderabruf. Bleibt dauerhaft: sie ist winzig gegenüber
    `calendar_history` und trägt den Index seit Aufzeichnungsbeginn."""
    con.execute('''CREATE TABLE IF NOT EXISTS calendar_month_moves (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        offer_id  INTEGER NOT NULL,
        ts        INTEGER NOT NULL,
        day       TEXT NOT NULL,
        month     TEXT NOT NULL,
        pct       REAL NOT NULL,
        n_days    INTEGER NOT NULL,
        n_changed INTEGER NOT NULL,
        sum_prev  REAL NOT NULL,
        FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE CASCADE
    )''')
    con.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_calmonth '
                'ON calendar_month_moves(offer_id, day, month)')
    _backfill_month_moves(con)


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
    # Monatsbewegung mitschreiben, solange beide Preistabellen noch hier vorliegen.
    _store_month_moves(con, offer_id, ts,
                       prev_prices, {d['date']: d['price'] for d in days})
    return real_changed


def _month_aggregate(prev_prices: dict, new_prices: dict, obs_day: str) -> dict:
    """Wertgewichtete Preisbewegung je Reisemonat zwischen zwei Snapshots.

    `prev_prices`/`new_prices`: {Reisedatum: Preis}. Gezählt werden nur Reisetage mit
    Preis in BEIDEN Snapshots (neu hinzugekommene haben keinen Vergleichswert,
    herausgefallene keinen aktuellen) und die am Beobachtungstag noch in der Zukunft
    liegen. Einzelsprünge über `CAL_MONTH_MAX_PCT` werden verworfen — solche Sprünge
    sind ein anderer Zimmertyp oder eine Verfügbarkeitslücke, kein Preissignal.

    Rückgabe {Monat: (pct, n_days, n_changed, sum_prev)}. `n_days` ist die Zahl der
    verglichenen Reisetage — der Nenner, nicht die Zahl der Änderungen."""
    agg: dict[str, list] = defaultdict(lambda: [0.0, 0, 0, 0.0])   # num, n, changed, den
    for d, new in new_prices.items():
        old = prev_prices.get(d)
        if old is None or not old or new is None or d < obs_day:
            continue
        if abs((new - old) / old * 100) > CAL_MONTH_MAX_PCT:
            continue
        a = agg[d[:7]]
        a[0] += new - old
        a[1] += 1
        a[2] += 1 if new != old else 0
        a[3] += old
    return {m: (round(num / den * 100, 4), n, ch, round(den, 2))
            for m, (num, n, ch, den) in agg.items() if den}


def _store_month_moves(con, offer_id: int, ts: int, prev_prices: dict,
                       new_prices: dict) -> int:
    """Monatsbewegungen eines Kalenderabrufs ablegen. Wird direkt aus
    `_store_calendar_snapshot` gefüttert, das beide Preistabellen ohnehin schon in
    der Hand hat — kein zusätzlicher Read der großen `calendar_history`.

    Ein zweiter Abruf am selben Tag ERSETZT den Tageswert nicht, sondern verkettet
    ihn mit dem vorhandenen: die Gesamtbewegung des Tages ist das Produkt seiner
    Einzelschritte. Würde die zweite Zeile die erste überschreiben, ginge der erste
    Schritt verloren und die Kette meldete zu wenig Bewegung. Ein identisch
    wiederholter Abruf ist dabei unschädlich — er liefert 0 % und ändert nichts."""
    if not prev_prices:
        return 0                     # Erstabruf ist reine Baseline, keine Bewegung
    day = datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
    agg = _month_aggregate(prev_prices, new_prices, day)
    if not agg:
        return 0
    have = {r['month']: r for r in con.execute(
        'SELECT month, pct, n_changed FROM calendar_month_moves '
        'WHERE offer_id=? AND day=?', (offer_id, day)).fetchall()}
    rows = []
    for mth, (pct, n, ch, den) in agg.items():
        old = have.get(mth)
        if old:
            pct = round(((1 + old['pct'] / 100) * (1 + pct / 100) - 1) * 100, 4)
            ch += old['n_changed']
        rows.append((offer_id, ts, day, mth, pct, n, ch, den))
    con.executemany(
        'INSERT OR REPLACE INTO calendar_month_moves (offer_id, ts, day, month, '
        'pct, n_days, n_changed, sum_prev) VALUES (?,?,?,?,?,?,?,?)', rows)
    return len(rows)


def _backfill_month_moves(con) -> None:
    """Monatsbewegungen einmalig aus der vorhandenen `calendar_history` nachrechnen.

    Die Historie ist delta-codiert, enthält aber durch Fortschreiben (carry-forward)
    die vollständige Preismatrix: der zuletzt bekannte Preis eines Reisetages gilt bis
    zur nächsten Änderungszeile. Damit lässt sich jeder frühere Abruf rekonstruieren.

    Eine Unschärfe bleibt: Abrufe, bei denen sich KEIN einziger Reisetag geändert hat,
    hinterlassen keine Zeile und sind darum unsichtbar. Sie hätten 0 % beigetragen,
    verändern die verkettete Kurve also nicht — nur die gezählte Zahl der
    Beobachtungstage fällt etwas zu niedrig aus.

    Läuft genau einmal (`meta`-Flag)."""
    if con.execute("SELECT 1 FROM meta WHERE key='calendar_month_backfill'").fetchone():
        return
    offers = [r['offer_id'] for r in con.execute(
        'SELECT DISTINCT offer_id FROM calendar_history').fetchall()]
    n_rows = 0
    for offer_id in offers:
        by_ts: dict[int, dict] = defaultdict(dict)
        for r in con.execute('SELECT travel_date, ts, price FROM calendar_history '
                             'WHERE offer_id=? ORDER BY ts', (offer_id,)).fetchall():
            by_ts[r['ts']][r['travel_date']] = r['price']
        state: dict = {}
        for ts in sorted(by_ts):
            changed = by_ts[ts]
            day = datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
            # Der Snapshot dieses Abrufs: fortgeschriebener Stand plus die Änderungen.
            # Reisetage, die inzwischen in der Vergangenheit liegen, fallen in
            # `_month_aggregate` über den `d < obs_day`-Filter heraus.
            new_prices = {**state, **changed}
            rows = [(offer_id, ts, day, m, pct, n, ch, den) for m, (pct, n, ch, den)
                    in _month_aggregate(state, new_prices, day).items()]
            if rows:
                con.executemany(
                    'INSERT OR REPLACE INTO calendar_month_moves (offer_id, ts, day, '
                    'month, pct, n_days, n_changed, sum_prev) VALUES (?,?,?,?,?,?,?,?)',
                    rows)
                n_rows += len(rows)
            state = new_prices
    con.execute("INSERT OR REPLACE INTO meta (key, value) "
                "VALUES ('calendar_month_backfill','1')")
    if n_rows:
        A.log.info("Kalender-Monatstrend: %d Monatsbewegungen aus der vorhandenen "
                   "Kalenderhistorie nachgerechnet (%d Angebote)", n_rows, len(offers))


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


# ── Monatstrend: Auswertung ────────────────────────────────────────────────────

def _month_moves_query(offer_id: int, month: str | None,
                       cutoff_day: str | None) -> tuple[str, list]:
    """Fester Query-Text mit `(? IS NULL OR …)`-Paaren statt laufzeitabhängiger
    String-Verkettung — gleiche Begründung wie bei `A._market_moves_query`."""
    q = ('SELECT day, month, pct, n_days, n_changed FROM calendar_month_moves '
         'WHERE offer_id=? AND (? IS NULL OR month=?) AND (? IS NULL OR day>=?) '
         'ORDER BY day ASC')
    return q, [offer_id, month, month, cutoff_day, cutoff_day]


def _month_series(con, offer_id: int, month: str,
                  cutoff_day: str | None = None) -> list:
    """Tageswerte eines Reisemonats als [(Beobachtungstag, Prozent, Reisetage)].
    Enthält bewusst auch die 0-%-Tage: ein Tag ohne Preisänderung ist ein
    beobachteter, ruhiger Tag — kein fehlender."""
    q, params = _month_moves_query(offer_id, month, cutoff_day)
    return [(r['day'], r['pct'], r['n_days']) for r in con.execute(q, params).fetchall()]


def month_trend(con, offer_id: int, month: str,
                window_days: int = CAL_MONTH_WINDOW) -> dict | None:
    """Rollierender Trend eines Reisemonats — gleiche Rückgabeform wie
    `A._market_trend` (dir/pct/days/n), damit die UI dieselben Badges nutzen kann."""
    cutoff = (date.today() - timedelta(days=window_days)).isoformat()
    series = _month_series(con, offer_id, month, cutoff)
    if len(series) < CAL_MONTH_MIN_DAYS:
        return None
    deadband = A._market_trend_threshold()
    cum = A._compound_pct([p for _, p, _ in series])
    direction = 'down' if cum <= -deadband else ('up' if cum >= deadband else 'flat')
    # Streak: seit wie vielen Tagen nichts GEGENLÄUFIGES passiert ist. Anders als beim
    # Markttrend zählen ruhige Tage (0 %) hier mit, statt die Serie zu beenden — im
    # Kalender ist 0 % der Normalfall (die meisten Reisetage ändern sich an den
    # meisten Tagen nicht). Mit der strengen Zählweise des Barometers stünde hier fast
    # immer „seit 1 Tag", was nichts aussagt.
    streak = 0
    for _, p, _n in reversed(series):
        same = ((direction == 'up' and p >= 0) or (direction == 'down' and p <= 0)
                or (direction == 'flat' and abs(p) < deadband))
        if not same:
            break
        streak += 1
    return {'dir': direction, 'pct': round(cum, 1), 'days': streak,
            'n': len(series), 'hotels': series[-1][2]}


def month_index(con, offer_id: int, month: str) -> dict | None:
    """Index eines Reisemonats seit Aufzeichnungsbeginn (Basis 100), analog
    `A._market_index` — fängt langsame Bewegungen außerhalb des 14-Tage-Fensters."""
    series = _month_series(con, offer_id, month)
    if len(series) < CAL_MONTH_MIN_DAYS:
        return None
    pct = A._compound_pct([p for _, p, _ in series])
    try:
        since = int(datetime.fromisoformat(series[0][0]).timestamp())
    except ValueError:
        since = int(time.time())
    return {'index': round(100 + pct, 1), 'pct': round(pct, 1),
            'since': since, 'n': len(series)}


def month_payload(offer_id: int) -> dict:
    """Monatsübersicht eines Angebots: je Reisemonat der aktuelle Durchschnittspreis
    aus dem gespeicherten Snapshot plus Trend und Index aus der Bewegungshistorie.

    Preisniveau und Bewegung kommen bewusst aus verschiedenen Quellen: das Niveau ist
    eine Momentaufnahme (`calendar_cache`), die Bewegung die verkettete Historie
    (`calendar_month_moves`)."""
    with A.db() as con:
        row = con.execute('SELECT ts, data FROM calendar_cache WHERE offer_id=?',
                          (offer_id,)).fetchone()
        if not row:
            return {'offer_id': offer_id, 'months': [], 'note': 'kein Kalender abgerufen'}
        try:
            days = json.loads(row['data']).get('days', [])
        except (ValueError, TypeError):
            days = []
        by_month: dict[str, list] = defaultdict(list)
        today = date.today().isoformat()
        for d in days:
            if d.get('price') is not None and (d.get('date') or '') >= today:
                by_month[d['date'][:7]].append(d['price'])
        obs = con.execute(
            'SELECT COUNT(DISTINCT day) c FROM calendar_month_moves WHERE offer_id=?',
            (offer_id,)).fetchone()['c']
        out = []
        for m in sorted(by_month):
            prices = by_month[m]
            out.append({
                'month': m, 'label': _month_name_de(m),
                'avg': round(sum(prices) / len(prices)), 'min': min(prices),
                'max': max(prices), 'dates': len(prices),
                'trend': month_trend(con, offer_id, m),
                'index': month_index(con, offer_id, m),
            })
    return {'offer_id': offer_id, 'months': out, 'observations': obs,
            'ts': row['ts'], 'min_days': CAL_MONTH_MIN_DAYS,
            'window_days': CAL_MONTH_WINDOW}


@bp.route('/api/calendar/<int:offer_id>/months', methods=['GET'])
def api_calendar_months(offer_id: int):
    """Monatsübersicht: Preisniveau je Reisemonat plus dessen Bewegung über die Zeit.

    Andere Frage als der Markttrend: der beschreibt den Markt (viele Hotels, ein
    Termin), dieser hier ein einzelnes Hotel/Zimmer über alle seine Reisetermine.
    Weicht ein Monat vom Markttrend ab, wird dort typischerweise das Kontingent
    knapp — ein Signal, das keine der beiden Quellen allein liefert."""
    if (err := A._require_api()):
        return err
    with A.db() as con:
        if not con.execute('SELECT 1 FROM offers WHERE id=?', (offer_id,)).fetchone():
            return jsonify({'error': 'not_found'}), 404
    return jsonify(month_payload(offer_id))


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

