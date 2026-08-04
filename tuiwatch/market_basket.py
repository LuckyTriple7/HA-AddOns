"""Markttrend aus einem täglichen Regions-Warenkorb.

Der bisherige Markttrend (`price_moves` in app.py) misst nur die Preisbewegung der
GETRACKTEN Angebote — je Region oft nur ein, zwei Hotels. Dieses Modul erweitert ihn
um eine deutlich breitere Basis: einmal pro Tag läuft je Region eine normale
Hotelsuche, deren Treffer (bis zu `BASKET_PAGES × 50` Hotels) als Warenkorb-Snapshot
abgelegt werden. Der Trend entsteht aus dem Vergleich aufeinanderfolgender Snapshots.

Warum es so und nicht anders gerechnet wird:

* **Matched Pairs statt Durchschnittsvergleich.** Der Warenkorb ändert sich täglich
  (Hotels sind ausgebucht, neue kommen dazu). Mittelwert-heute gegen Mittelwert-gestern
  würde deshalb vor allem die Zusammensetzung messen, nicht den Preis. Verglichen wird
  daher je Hotel (giataId) gegen SEIN eigenes Vortagesergebnis; nur Hotels, die in
  beiden Snapshots vorkommen, zählen.
* **Median statt Mittelwert** über die Hotel-Deltas. Die Such-API liefert je Hotel das
  günstigste Angebot; dessen Zimmerkategorie steht in keinem Feld und kann wechseln.
  Solche Ausreißer würden einen Mittelwert verzerren, den Median praktisch nicht.
* **Board/Nächte müssen übereinstimmen.** Verpflegung und Dauer sind zwar feste
  Suchparameter, das günstigste Hotelangebot kann trotzdem von HP auf AI springen —
  ein Preissprung ohne Marktsignal. Solche Paare werden übersprungen.
* **Konstante Vorlaufzeit statt konstantem Abreisedatum.** Gesucht wird immer für
  „heute + `market_basket_lead_days`" (Standard 91 = Vielfaches von 7, damit der
  Wochentag konstant bleibt und keine Wochenend-/Wochentag-Preissprünge entstehen).
  Das Abreisedatum wandert dadurch täglich um einen Tag weiter — für alle Hotels
  gleichermaßen, und bei 91 Tagen Vorlauf ist der Saisoneffekt eines einzelnen Tages
  vernachlässigbar. Die Alternative (festes Datum) würde stattdessen die Vorlaufzeit
  täglich schrumpfen lassen und damit den Last-Minute-Effekt mitmessen.
* **Verkettung erst auf Tagesebene.** `A._compound_pct` verkettet ALLE übergebenen
  Werte — die hunderten Hotel-Deltas eines Tages direkt hineinzugeben ergäbe Unsinn.
  Deshalb wird pro Region und Tag EIN Median abgelegt (`basket_moves`) und erst diese
  Tageswerte werden über die Zeit verkettet.

Bekannte Restunschärfe: die Suche sortiert nach Preis aufsteigend, abgeholt werden nur
die ersten `BASKET_PAGES × 50` Hotels. Steigt ein Hotel aus diesem Fenster heraus,
fehlt es im Matching. Mehrere Seiten verdünnen den Effekt, beseitigen ihn aber nicht.
"""
import json
import statistics
import threading
import time
from collections import defaultdict
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, request

import app as A

bp = Blueprint('market_basket', __name__)

BASKET_LEAD_DAYS_DEFAULT = 91   # Vielfaches von 7 → gleicher Wochentag wie gestern
BASKET_NIGHTS = 7
BASKET_TRAVELLERS = 2
BASKET_PAGE_SIZE = 50           # entspricht resultsPerPage der Such-API
BASKET_PAGES = 4                # bis zu 200 Hotels je Region und Tag
BASKET_MAX_REGIONS_DEFAULT = 20  # Deckel für die tägliche API-Last (Option, siehe _max_regions)
BASKET_MIN_MATCHED = 10         # weniger Hotel-Paare → Tag verwerfen (zu dünn)
BASKET_MIN_DAYS = 2             # weniger Tagesbewegungen → kein Trend
BASKET_MAX_GAP_DAYS = 7         # größere Lücke (Add-on aus) → Kette neu beginnen
BASKET_RETENTION_DAYS = 120     # Snapshots älter als das werden verworfen

_run_lock = threading.Lock()
_running = False


# ── Schema ─────────────────────────────────────────────────────────────────────

def init_basket_db(con) -> None:
    """Tabellen anlegen — wird aus `app.init_db` aufgerufen.
    `basket_snapshots` ist die Rohdatenhaltung (wird nach `BASKET_RETENTION_DAYS`
    beschnitten), `basket_moves` das verdichtete Ergebnis (eine Zeile je Region und
    Tag, bleibt dauerhaft — winzig und die Grundlage des Index)."""
    con.execute('''CREATE TABLE IF NOT EXISTS basket_snapshots (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        ts           INTEGER NOT NULL,
        day          TEXT NOT NULL,
        region       TEXT NOT NULL DEFAULT '',
        region_giata INTEGER,
        giata        TEXT NOT NULL,
        price        REAL NOT NULL,
        board        TEXT DEFAULT '',
        nights       INTEGER,
        dep_date     TEXT DEFAULT ''
    )''')
    con.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_basket_snap '
                'ON basket_snapshots(region, day, giata)')
    con.execute('''CREATE TABLE IF NOT EXISTS basket_moves (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        ts         INTEGER NOT NULL,
        day        TEXT NOT NULL,
        region     TEXT NOT NULL DEFAULT '',
        prev_day   TEXT NOT NULL DEFAULT '',
        gap_days   INTEGER DEFAULT 1,
        pct_median REAL NOT NULL,
        n_matched  INTEGER NOT NULL,
        n_total    INTEGER NOT NULL
    )''')
    con.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_basket_move '
                'ON basket_moves(region, day)')


# ── Konfiguration ──────────────────────────────────────────────────────────────

def _enabled() -> bool:
    return bool(A.load_config().get('market_basket_enabled', True))


def _lead_days() -> int:
    """Vorlaufzeit in Tagen, auf 14…365 begrenzt (darunter dominiert Last-Minute,
    darüber liefert die Such-API für viele Regionen noch keine Preise)."""
    try:
        v = int(A.load_config().get('market_basket_lead_days', BASKET_LEAD_DAYS_DEFAULT))
    except (TypeError, ValueError):
        return BASKET_LEAD_DAYS_DEFAULT
    return max(14, min(365, v))


def _max_regions() -> int:
    """Obergrenze für die täglich abgefragten Regionen, auf 1…50 begrenzt.
    Der Deckel ist reiner Lastschutz: eine Region kostet 1–4 API-Aufrufe pro Tag
    (Abbruch, sobald eine Seite weniger als BASKET_PAGE_SIZE Treffer liefert), der
    Standard also höchstens rund 80 Requests täglich — Kleingeld gegenüber dem
    normalen Poller."""
    try:
        v = int(A.load_config().get('market_basket_max_regions', BASKET_MAX_REGIONS_DEFAULT))
    except (TypeError, ValueError):
        return BASKET_MAX_REGIONS_DEFAULT
    return max(1, min(50, v))


def _basket_regions() -> list:
    """Regionen für den Warenkorb, ohne dass der Nutzer giataIds pflegen muss:
    zuerst die Ziele der gespeicherten Suchen (das ist die vom Nutzer selbst
    kuratierte Liste „was mich interessiert"), danach die Regionen der getrackten
    Angebote. Dedupliziert über die Region-giataId, gedeckelt auf `_max_regions()`.
    Wird abgeschnitten, sagt das Log welche Regionen wegfallen — sonst würde eine
    neu angelegte Suche stillschweigend nie im Warenkorb landen."""
    limit = _max_regions()
    out, seen = [], set()
    with A.db() as con:
        rows = con.execute('SELECT payload FROM saved_searches ORDER BY id').fetchall()
    for r in rows:
        try:
            dest = (json.loads(r['payload']) or {}).get('dest') or {}
            giata = int(dest.get('giata'))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if giata in seen:
            continue
        seen.add(giata)
        out.append({'giata': giata, 'label': (dest.get('label') or '').strip() or str(giata)})
    out += _regions_from_offers(seen)
    if len(out) > limit:
        A.log.warning("Warenkorb: %d Regionen gefunden, aber nur %d erlaubt — nicht "
                      "berücksichtigt: %s (Option market_basket_max_regions erhöhen)",
                      len(out), limit, ", ".join(r['label'] for r in out[limit:]))
    return out[:limit]


def _regions_from_offers(seen: set) -> list:
    """Region-giataIds der getrackten Angebote. Die Zuordnung Hotel→Region geht über
    die Breadcrumb-API (ein Aufruf je Hotel), das Ergebnis wird deshalb dauerhaft in
    `meta` gecacht — Hotels wechseln die Region nicht."""
    try:
        cache = json.loads(A._meta_get('basket_region_map') or '{}')
    except (TypeError, json.JSONDecodeError):
        cache = {}
    with A.db() as con:
        offers = con.execute(
            "SELECT url, region FROM offers WHERE COALESCE(archived,0)=0 ORDER BY id").fetchall()
    out, dirty = [], False
    for o in offers:
        hotel_giata = A._giata_from_url(o['url'])
        if not hotel_giata:
            continue
        if hotel_giata not in cache:
            try:
                cache[hotel_giata] = A.region_giata_from_breadcrumb(hotel_giata)
            except Exception as e:
                A.log.debug("Warenkorb: Region zu Hotel %s nicht ermittelbar: %s", hotel_giata, e)
                continue
            dirty = True
        rg = cache.get(hotel_giata)
        if not rg or int(rg) in seen:
            continue
        seen.add(int(rg))
        out.append({'giata': int(rg), 'label': (o['region'] or '').strip() or str(rg)})
    if dirty:
        A._meta_set('basket_region_map', json.dumps(cache))
    return out


# ── Snapshot holen und ablegen ─────────────────────────────────────────────────

def _fetch_basket(region_giata: int) -> list:
    """Eine Region abfragen: feste Suchparameter (ein einziges Abreisedatum, feste
    Dauer und Personenzahl), mehrere Seiten. Feste Parameter sind der Grund, warum
    Verpflegung und Dauer über die Tage stabil bleiben.

    `endDate` ist bei der Such-API die späteste **Rückreise**, nicht die späteste
    Abreise — `start + BASKET_NIGHTS` grenzt die Treffer deshalb auf genau einen
    Abreisetag ein (live verifiziert: 196 Treffer, alle mit demselben `date`).
    `start == end` wäre die naheliegende Schreibweise für „ein Tag", quittiert die
    API aber mit **HTTP 500** — Reisedauer und Zeitfenster widersprechen sich dann."""
    start = date.today() + timedelta(days=_lead_days())
    dep, ret = start.isoformat(), (start + timedelta(days=BASKET_NIGHTS)).isoformat()
    out, seen = [], set()
    for page in range(BASKET_PAGES):
        res = A.fetch_search_params(
            region=region_giata, start=dep, end=ret, duration=BASKET_NIGHTS,
            travellers=BASKET_TRAVELLERS, offset=page * BASKET_PAGE_SIZE,
            verbose=A._verbose())
        if not (res and res.get('ok')):
            break
        rows = res.get('results') or []
        for r in rows:
            g = str(r.get('giata') or '')
            if not g or g in seen or r.get('price') is None:
                continue
            seen.add(g)
            out.append(r)
        if len(rows) < BASKET_PAGE_SIZE:
            break
    return out


def _store_snapshot(con, region: str, region_giata: int, day: str, ts: int, rows: list) -> None:
    """Snapshot des Tages ersetzen (ein manueller Zweitlauf am selben Tag soll den
    ersten überschreiben, nicht danebenliegen)."""
    con.execute('DELETE FROM basket_snapshots WHERE region=? AND day=?', (region, day))
    con.executemany(
        'INSERT INTO basket_snapshots (ts, day, region, region_giata, giata, price, '
        'board, nights, dep_date) VALUES (?,?,?,?,?,?,?,?,?)',
        [(ts, day, region, region_giata, str(r.get('giata')), float(r['price']),
          r.get('board') or '', r.get('nights'), r.get('date') or '') for r in rows])


def _compute_move(con, region: str, day: str) -> dict | None:
    """Tagesbewegung einer Region aus dem Vergleich mit dem letzten vorhandenen
    Snapshot. Rückgabe None, wenn es keinen Vorgänger gibt, die Lücke zu groß ist
    oder zu wenige Hotels in beiden Snapshots stehen."""
    prev = con.execute(
        'SELECT DISTINCT day FROM basket_snapshots WHERE region=? AND day<? '
        'ORDER BY day DESC LIMIT 1', (region, day)).fetchone()
    if not prev:
        return None
    prev_day = prev['day']
    try:
        gap = (date.fromisoformat(day) - date.fromisoformat(prev_day)).days
    except ValueError:
        return None
    if gap > BASKET_MAX_GAP_DAYS:
        A.log.info("Warenkorb „%s“: %d Tage Lücke seit %s — Kette beginnt neu",
                   region, gap, prev_day)
        return None

    def _snap(d):
        return {r['giata']: r for r in con.execute(
            'SELECT giata, price, board, nights FROM basket_snapshots '
            'WHERE region=? AND day=?', (region, d)).fetchall()}

    cur, old = _snap(day), _snap(prev_day)
    pcts = []
    for g, c in cur.items():
        o = old.get(g)
        if not o or not o['price']:
            continue
        # Zimmerkategorie ist unsichtbar, Verpflegung/Dauer aber nicht — ein Wechsel
        # dort ist ein anderer Angebotstyp, kein Marktsignal.
        if (o['board'] or '') != (c['board'] or '') or o['nights'] != c['nights']:
            continue
        pcts.append((c['price'] - o['price']) / o['price'] * 100)
    if len(pcts) < BASKET_MIN_MATCHED:
        A.log.info("Warenkorb „%s“: nur %d vergleichbare Hotels (min. %d) — Tag verworfen",
                   region, len(pcts), BASKET_MIN_MATCHED)
        return None
    med = statistics.median(pcts)
    con.execute(
        'INSERT OR REPLACE INTO basket_moves (ts, day, region, prev_day, gap_days, '
        'pct_median, n_matched, n_total) VALUES (?,?,?,?,?,?,?,?)',
        (int(time.time()), day, region, prev_day, gap, med, len(pcts), len(cur)))
    return {'day': day, 'prev_day': prev_day, 'gap_days': gap,
            'pct_median': round(med, 2), 'n_matched': len(pcts), 'n_total': len(cur)}


def _prune(con) -> None:
    """Alte Snapshots wegwerfen — die verdichteten `basket_moves` bleiben, der Index
    seit Aufzeichnungsbeginn überlebt das Beschneiden also."""
    cutoff = (date.today() - timedelta(days=BASKET_RETENTION_DAYS)).isoformat()
    con.execute('DELETE FROM basket_snapshots WHERE day<?', (cutoff,))


def run_basket_region(region: str, region_giata: int) -> dict:
    """Eine Region komplett durchlaufen: suchen, Snapshot ablegen, Tagesbewegung
    berechnen. Rückgabe für Log/API."""
    rows = _fetch_basket(region_giata)
    if not rows:
        A.log.warning("Warenkorb „%s“ (%s): Suche lieferte keine Treffer", region, region_giata)
        return {'region': region, 'hotels': 0, 'move': None}
    ts = int(time.time())
    day = datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
    with A.db() as con:
        _store_snapshot(con, region, region_giata, day, ts, rows)
        move = _compute_move(con, region, day)
        _prune(con)
    A.log.info("Warenkorb „%s“: %d Hotels erfasst%s", region, len(rows),
               (f", Tagesbewegung {move['pct_median']:+.2f} % aus {move['n_matched']} Hotels"
                if move else " (noch keine Tagesbewegung)"))
    return {'region': region, 'hotels': len(rows), 'move': move}


def run_baskets(*, force: bool = False) -> list:
    """Alle Regionen abarbeiten, je Region höchstens 1×/Tag (`force` umgeht das für
    den manuellen Anstoß aus der UI). Ein Lauf gleichzeitig — der Poll-Worker und ein
    UI-Klick dürfen sich nicht überlappen."""
    global _running
    with _run_lock:
        if _running:
            return []
        _running = True
    try:
        day = datetime.now().strftime('%Y-%m-%d')
        out = []
        for reg in _basket_regions():
            if not force:
                with A.db() as con:
                    done = con.execute(
                        'SELECT 1 FROM basket_snapshots WHERE region=? AND day=? LIMIT 1',
                        (reg['label'], day)).fetchone()
                if done:
                    continue
            try:
                out.append(run_basket_region(reg['label'], reg['giata']))
            except Exception as e:
                A.log.error("Warenkorb „%s“ fehlgeschlagen: %s: %s",
                            reg['label'], type(e).__name__, e)
        return out
    finally:
        _running = False


def maybe_run_baskets() -> None:
    """Aufhänger für den Poll-Worker (analog `_maybe_refresh_calendars`)."""
    if not _enabled():
        return
    run_baskets()


# ── Auswertung ─────────────────────────────────────────────────────────────────

def _moves_query(region: str | None, cutoff_day: str | None) -> tuple[str, list]:
    """Fester Query-Text mit `(? IS NULL OR …)`-Paaren statt laufzeitabhängiger
    String-Verkettung — gleiche Begründung wie bei `A._market_moves_query`: CodeQL
    stuft dynamisch zusammengebautes SQL pauschal als riskant ein."""
    q = ('SELECT day, region, pct_median, n_matched FROM basket_moves '
         'WHERE (? IS NULL OR day>=?) AND (? IS NULL OR region=?) ORDER BY day ASC')
    return q, [cutoff_day, cutoff_day, region, region]


def _daily_series(con, region: str | None, cutoff_day: str | None) -> list:
    """Tageswerte als [(tag, prozent, hotelzahl)]. Über alle Regionen hinweg (region
    None) werden die Regions-Mediane eines Tages nach Hotelzahl gewichtet gemittelt —
    eine Region mit 200 Hotels soll den Gesamtwert stärker prägen als eine mit 15."""
    q, params = _moves_query(region, cutoff_day)
    by_day: dict[str, list] = defaultdict(list)
    for r in con.execute(q, params).fetchall():
        by_day[r['day']].append((r['pct_median'], max(1, r['n_matched'])))
    out = []
    for day in sorted(by_day):
        vals = by_day[day]
        total = sum(n for _, n in vals)
        out.append((day, sum(p * n for p, n in vals) / total, total))
    return out


def basket_trend(con, *, region: str | None = None, window_days: int = 14) -> dict | None:
    """Warenkorb-Trend über ein rollierendes Fenster. Gleiche Rückgabeform wie
    `A._market_trend` (dir/pct/days/n), damit UI und Sensor beide Quellen ohne
    Sonderfälle anzeigen können; `hotels` nennt zusätzlich die Breite der Basis."""
    cutoff = (date.today() - timedelta(days=window_days)).isoformat()
    series = _daily_series(con, region, cutoff)
    if len(series) < BASKET_MIN_DAYS:
        return None
    deadband = A._market_trend_threshold()
    cum = A._compound_pct([p for _, p, _ in series])
    direction = ('down' if cum <= -deadband else ('up' if cum >= deadband else 'flat'))
    streak = 0
    for _, p, _n in reversed(series):
        same = ((direction == 'up' and p > 0) or (direction == 'down' and p < 0)
                or (direction == 'flat' and abs(p) < deadband))
        if not same:
            break
        streak += 1
    return {'dir': direction, 'pct': round(cum, 1), 'days': streak,
            'n': len(series), 'hotels': series[-1][2]}


def basket_index(con, *, region: str | None = None) -> dict | None:
    """Warenkorb-Index seit Aufzeichnungsbeginn (Basis 100), analog `A._market_index` —
    fängt langsame Bewegungen ab, die aus dem 14-Tage-Fenster herausfallen."""
    series = _daily_series(con, region, None)
    if len(series) < BASKET_MIN_DAYS:
        return None
    pct = A._compound_pct([p for _, p, _ in series])
    try:
        since = int(datetime.fromisoformat(series[0][0]).timestamp())
    except ValueError:
        since = int(time.time())
    return {'index': round(100 + pct, 1), 'pct': round(pct, 1),
            'since': since, 'n': len(series)}


def basket_payload() -> dict:
    """Kompletter Warenkorb-Stand für API und HA-Sensor."""
    with A.db() as con:
        regions = [r['region'] for r in con.execute(
            "SELECT DISTINCT region FROM basket_moves WHERE region!=''").fetchall()]
        glob = {'trend': basket_trend(con), 'index': basket_index(con)}
        by_region = []
        for r in sorted(regions):
            t, i = basket_trend(con, region=r), basket_index(con, region=r)
            if t or i:
                by_region.append({'region': r, 'trend': t, 'index': i})
        last = con.execute('SELECT MAX(day) d FROM basket_snapshots').fetchone()
        pending = [r['region'] for r in con.execute(
            "SELECT DISTINCT region FROM basket_snapshots WHERE region NOT IN "
            "(SELECT region FROM basket_moves)").fetchall()]
    return {'enabled': _enabled(), 'global': glob, 'by_region': by_region,
            'last_day': (last['d'] if last else None) or '',
            'lead_days': _lead_days(), 'pending': sorted(pending), 'running': _running}


# ── Routen ─────────────────────────────────────────────────────────────────────

@bp.route('/api/market-basket')
def api_market_basket():
    """Warenkorb-Markttrend: global und je Region, plus Status (letzter Lauf,
    Regionen ohne verwertbare Bewegung, Vorlaufzeit)."""
    if (err := A._require_api()):
        return err
    return jsonify(basket_payload())


@bp.route('/api/market-basket/run', methods=['POST'])
def api_market_basket_run():
    """Warenkorb-Lauf sofort anstoßen. Läuft im Hintergrund (mehrere Regionen ×
    mehrere Suchseiten dauern länger als ein sinnvolles Request-Timeout) — die UI
    fragt danach `/api/market-basket` erneut ab."""
    if (err := A._require_api()):
        return err
    if _running:
        return jsonify({'started': False, 'note': 'läuft bereits'})
    regions = _basket_regions()
    if not regions:
        return jsonify({'started': False, 'note': 'keine Region ermittelbar'})
    A._spawn(lambda: run_baskets(force=True))
    return jsonify({'started': True, 'regions': [r['label'] for r in regions]})


@bp.route('/api/market-basket/region', methods=['DELETE'])
def api_market_basket_region_delete():
    """Warenkorb-Daten EINER Region löschen (Snapshots und Bewegungen) — Neustart der
    Aufzeichnung, z. B. nachdem sich die Suchparameter geändert haben."""
    if (err := A._require_api()):
        return err
    region = ((request.get_json(silent=True) or {}).get('region') or '').strip()
    if not region:
        return jsonify({'error': 'invalid'}), 400
    with A.db() as con:
        snaps = con.execute('DELETE FROM basket_snapshots WHERE region=?', (region,)).rowcount
        moves = con.execute('DELETE FROM basket_moves WHERE region=?', (region,)).rowcount
    A.log.info("Warenkorb-Daten für „%s“ gelöscht: %d Snapshots, %d Tagesbewegungen",
               region, snaps, moves)
    return jsonify({'region': region, 'snapshots': snaps, 'moves': moves})
