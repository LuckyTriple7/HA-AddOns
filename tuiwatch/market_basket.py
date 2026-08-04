"""Markttrend aus einem täglichen Warenkorb je gespeicherter Suche.

Der bisherige Markttrend (`price_moves` in app.py) misst nur die Preisbewegung der
GETRACKTEN Angebote — je Reiseziel oft nur ein, zwei Hotels. Dieses Modul erweitert
ihn um eine deutlich breitere Basis: einmal pro Tag läuft **genau die gespeicherte
Suche** des Nutzers noch einmal, und alle ihre Treffer werden als Warenkorb-Snapshot
abgelegt. Der Trend entsteht aus dem Vergleich aufeinanderfolgender Snapshots.

**Ein Warenkorb je gespeicherter Suche**, nicht je Region — mit deren echten
Reiseterminen, Dauer, Verpflegungs-, Sterne- und Flughafenfiltern. Zwei Suchen für
dasselbe Ziel mit verschiedenen Terminen ergeben zwei getrennte Warenkörbe; das sind
schlicht verschiedene Märkte. Ein früherer Entwurf suchte stattdessen mit konstanter
Vorlaufzeit („heute + 91 Tage") — statistisch sauber, praktisch aber wertlos: wer
seinen Urlaub im Mai plant, dem hilft die Preisbewegung eines täglich weiterwandernden
Termins nicht bei der Frage, ob er JETZT buchen soll. Die konstante Vorlaufzeit ist
nur noch Rückfallebene für Warenkörbe ohne eigenes Datum (siehe `_offer_targets`).

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
  ein Preissprung ohne Marktsignal. Solche Paare werden übersprungen. Das Abreise-
  **datum** ist dagegen ausdrücklich KEIN Match-Kriterium: bei einer Suche über einen
  Zeitraum (z. B. ganzer Mai) ist der günstigste Termin innerhalb des Fensters genau
  die Zahl, um die es geht — wandert er, ist das die gesuchte Information.
* **Verkettung erst auf Tagesebene.** `A._compound_pct` verkettet ALLE übergebenen
  Werte — die hunderten Hotel-Deltas eines Tages direkt hineinzugeben ergäbe Unsinn.
  Deshalb wird pro Warenkorb und Tag EIN Median abgelegt (`basket_moves`) und erst
  diese Tageswerte werden über die Zeit verkettet.

Abgeholt wird jede Suche vollständig (siehe `_fetch_basket`) — ein fester Seiten-Deckel
hätte wegen der Preis-aufsteigenden Sortierung stets nur die günstigsten N Hotels
erfasst, deren Randbelegung täglich wechselt und den Median verfälscht hätte.
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

BASKET_LEAD_DAYS_DEFAULT = 91   # nur Rückfallebene, siehe _offer_targets
BASKET_NIGHTS = 7               # dito: Dauer, wenn kein eigener Wert ermittelbar ist
BASKET_TRAVELLERS = 2
BASKET_PAGE_SIZE = 50           # entspricht resultsPerPage der Such-API
BASKET_MAX_PAGES = 20           # Reißleine (1000 Hotels); normal endet die Schleife an `total`
BASKET_MAX_REGIONS_DEFAULT = 20  # Deckel für die tägliche API-Last (Option, siehe _max_regions)
BASKET_MIN_MATCHED = 10         # Obergrenze der Mindestbreite, siehe _min_matched
BASKET_MIN_MATCHED_FLOOR = 5    # darunter ist ein Median nicht mehr aussagekräftig
BASKET_MIN_MATCHED_SHARE = 0.6  # Anteil des Warenkorbs, der wiederauftauchen muss
BASKET_MIN_DAYS = 2             # weniger Tagesbewegungen → kein Trend
BASKET_MAX_GAP_DAYS = 7         # größere Lücke (Add-on aus) → Kette neu beginnen
BASKET_RETENTION_DAYS = 120     # Snapshots älter als das werden verworfen

_run_lock = threading.Lock()
_running = False
# Fortschritt des laufenden Warenkorb-Laufs für die UI. Ein Lauf dauert je nach Anzahl
# der Suchen und Treffer eine Weile; ohne diesen Zwischenstand sähe der Nutzer nach dem
# Klick minutenlang nichts. Bewusst ein einfaches dict statt einer Tabelle — der Wert
# ist rein flüchtig und nach einem Neustart bedeutungslos.
_progress: dict = {'done': 0, 'total': 0, 'current': '', 'hotels': 0}


def _set_progress(**kw) -> None:
    _progress.update(kw)


# ── Schema ─────────────────────────────────────────────────────────────────────

def init_basket_db(con) -> None:
    """Tabellen anlegen — wird aus `app.init_db` aufgerufen.
    `basket_snapshots` ist die Rohdatenhaltung (wird nach `BASKET_RETENTION_DAYS`
    beschnitten), `basket_moves` das verdichtete Ergebnis (eine Zeile je Warenkorb
    und Tag, bleibt dauerhaft — winzig und die Grundlage des Index).

    `basket` ist der Schlüssel eines Warenkorbs: der Name der gespeicherten Suche
    bzw. „<Region> (Abreise TT.MM.JJJJ)" bei Warenkörben aus getrackten Angeboten.

    Migration: die erste Fassung (v0.60.x) schlüsselte nach Region und suchte mit
    konstanter Vorlaufzeit statt mit den echten Reiseterminen. Diese Datenpunkte
    haben eine andere Preisbasis und dürfen nicht mit den neuen verkettet werden —
    die alten Tabellen werden daher einmalig verworfen."""
    cols = {r['name'] for r in con.execute('PRAGMA table_info(basket_snapshots)').fetchall()}
    if cols and 'basket' not in cols:
        con.execute('DROP TABLE IF EXISTS basket_snapshots')
        con.execute('DROP TABLE IF EXISTS basket_moves')
        A.log.info("Warenkorb: Daten der Regions-Fassung verworfen — der Warenkorb "
                   "richtet sich jetzt nach den Terminen der gespeicherten Suchen")
    con.execute('''CREATE TABLE IF NOT EXISTS basket_snapshots (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        ts           INTEGER NOT NULL,
        day          TEXT NOT NULL,
        basket       TEXT NOT NULL DEFAULT '',
        region_giata INTEGER,
        giata        TEXT NOT NULL,
        price        REAL NOT NULL,
        board        TEXT DEFAULT '',
        nights       INTEGER,
        dep_date     TEXT DEFAULT ''
    )''')
    con.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_basket_snap '
                'ON basket_snapshots(basket, day, giata)')
    con.execute('''CREATE TABLE IF NOT EXISTS basket_moves (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        ts         INTEGER NOT NULL,
        day        TEXT NOT NULL,
        basket     TEXT NOT NULL DEFAULT '',
        prev_day   TEXT NOT NULL DEFAULT '',
        gap_days   INTEGER DEFAULT 1,
        pct_median REAL NOT NULL,
        n_matched  INTEGER NOT NULL,
        n_total    INTEGER NOT NULL
    )''')
    con.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_basket_move '
                'ON basket_moves(basket, day)')
    # Angebots-Warenkörbe hießen kurzzeitig „<Region> (Abreise TT.MM.JJJJ)" — ein
    # Warenkorb je Einzeltermin. Seit der Monatsbündelung gibt es zu diesen
    # Schlüsseln keinen Warenkorb mehr; ihre Snapshots blieben sonst als
    # Karteileichen liegen und stünden bis zum Ablauf der Aufbewahrung in der UI
    # unter „sammelt noch".
    if not con.execute(
            "SELECT 1 FROM meta WHERE key='basket_offer_keys_bundled'").fetchone():
        n = con.execute(
            "DELETE FROM basket_snapshots WHERE basket LIKE '% (Abreise %'").rowcount
        con.execute("DELETE FROM basket_moves WHERE basket LIKE '% (Abreise %'")
        con.execute("INSERT OR REPLACE INTO meta (key, value) "
                    "VALUES ('basket_offer_keys_bundled','1')")
        if n:
            A.log.info("Warenkorb: %d Snapshots der Einzeltermin-Fassung verworfen "
                       "(Angebots-Warenkörbe laufen jetzt je Monat)", n)


# ── Konfiguration ──────────────────────────────────────────────────────────────

def _enabled() -> bool:
    return bool(A.load_config().get('market_basket_enabled', True))


def _lead_days() -> int:
    """Vorlaufzeit in Tagen für die Rückfallebene, auf 14…365 begrenzt. Greift NUR
    für Warenkörbe ohne eigenen Reisetermin (siehe `_offer_targets`) — gespeicherte
    Suchen bringen ihr Datum selbst mit."""
    try:
        v = int(A.load_config().get('market_basket_lead_days', BASKET_LEAD_DAYS_DEFAULT))
    except (TypeError, ValueError):
        return BASKET_LEAD_DAYS_DEFAULT
    return max(14, min(365, v))


def _max_regions() -> int:
    """Obergrenze für die täglich abgefragten Warenkörbe, auf 1…50 begrenzt.
    Der Deckel ist reiner Lastschutz: ein Warenkorb kostet je 50 Hotels einen
    API-Aufruf pro Tag (typisch 1–6), der Standard also grob 100 Requests täglich —
    Kleingeld gegenüber dem normalen Poller."""
    try:
        v = int(A.load_config().get('market_basket_max_regions', BASKET_MAX_REGIONS_DEFAULT))
    except (TypeError, ValueError):
        return BASKET_MAX_REGIONS_DEFAULT
    return max(1, min(50, v))


def _period(p: dict) -> str:
    """Reisezeitraum eines Payloads als Klartext für UI und Log."""
    vom, bis = (p.get('vom') or '').strip(), (p.get('bis') or '').strip()

    def _de(s):
        try:
            return date.fromisoformat(s[:10]).strftime('%d.%m.%Y')
        except ValueError:
            return s
    if vom and bis and vom != bis:
        return f"{_de(vom)} – {_de(bis)}"
    return _de(vom or bis) if (vom or bis) else ''


def _expired(p: dict) -> bool:
    """True, wenn der Reisezeitraum der Suche komplett in der Vergangenheit liegt —
    dann gibt es nichts mehr zu beobachten und die Suche liefert ohnehin nichts."""
    end = (p.get('bis') or p.get('vom') or '').strip()
    if not end:
        return False
    try:
        return date.fromisoformat(end[:10]) < date.today()
    except ValueError:
        return False


def _basket_targets() -> list:
    """Die täglich abzufragenden Warenkörbe. Jeder trägt seinen kompletten
    Such-Payload — also die echten Reisetermine des Nutzers, nicht ein künstlich
    berechnetes Datum.

    Quelle 1 sind die **gespeicherten Suchen** (Schlüssel = ihr Name; das ist die
    vom Nutzer selbst kuratierte Liste „was mich interessiert" samt Terminen und
    Filtern). Quelle 2 sind die Regionen der **getrackten Angebote**, für die kein
    Suchabo existiert. Abgelaufene Zeiträume fallen raus. Gedeckelt auf
    `_max_regions()`; wird abgeschnitten, sagt es das Log — sonst würde eine neu
    angelegte Suche stillschweigend nie im Warenkorb landen."""
    limit = _max_regions()
    out, seen = [], set()
    with A.db() as con:
        rows = con.execute('SELECT name, payload FROM saved_searches ORDER BY id').fetchall()
    for r in rows:
        try:
            payload = json.loads(r['payload']) or {}
            giata = int((payload.get('dest') or {}).get('giata'))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if _expired(payload):
            A.log.debug("Warenkorb: Suche „%s“ übersprungen (Reisezeitraum vorbei)", r['name'])
            continue
        key = (r['name'] or '').strip() or f"Suche {giata}"
        if key in seen:
            continue
        seen.add(key)
        out.append({'key': key, 'giata': giata, 'payload': payload,
                    'period': _period(payload), 'source': 'search'})
    out += _offer_targets(seen)
    if len(out) > limit:
        A.log.warning("Warenkorb: %d Warenkörbe gefunden, aber nur %d erlaubt — nicht "
                      "berücksichtigt: %s (Option market_basket_max_regions erhöhen)",
                      len(out), limit, ", ".join(t['key'] for t in out[limit:]))
    return out[:limit]


_MONTHS_DE = ('Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli',
              'August', 'September', 'Oktober', 'November', 'Dezember')


def _month_window(dep: date, nights: int) -> tuple[date, date]:
    """Suchfenster für den Abreisemonat von `dep`: (früheste Abreise, späteste
    Rückreise). Ab heute gerechnet — ein bereits laufender Monat beginnt beim
    Warenkorb heute, nicht rückwirkend.

    Das Ende ist Monatsletzter **plus Reisedauer**, weil `endDate` bei der Such-API
    die späteste Rückreise meint. Ohne den Aufschlag fielen genau die Abreisen am
    Monatsende heraus (im Log: Abreise 31.05. mit 11 Nächten endet am 11.06.)."""
    first = max(dep.replace(day=1), date.today())
    nxt = (dep.replace(day=28) + timedelta(days=4)).replace(day=1)
    return first, nxt - timedelta(days=1) + timedelta(days=nights)


def _offer_targets(seen: set) -> list:
    """Warenkörbe aus den getrackten Angeboten — für Reiseziele, zu denen es keine
    gespeicherte Suche gibt. Der Reisetermin kommt aus dem Angebot selbst (Abreise
    = Rückreisedatum minus Dauer aus der URL); nur wenn dort nichts steht, greift
    ersatzweise die konstante Vorlaufzeit `market_basket_lead_days`.

    Gebündelt wird je **Region, Abreisemonat und Dauer**, nicht je Einzeltermin.
    Fünf getrackte Gran-Canaria-Angebote mit Abreise am 3., 7., 31. Mai sowie 7. und
    14. Juni ergaben sonst fünf Warenkörbe à ~220 Hotels und fünf Ergebnisseiten —
    25 Abrufe täglich für praktisch denselben Markt. Als Zeitraum dient der ganze
    Monat; die Suche liefert je Hotel den günstigsten Termin darin, was für einen
    Markttrend genau die richtige Zahl ist. Die Dauer bleibt im Schlüssel, weil eine
    Woche und zwei Wochen unterschiedliche Preisniveaus haben.

    Die Zuordnung Hotel→Region geht über die Breadcrumb-API (ein Aufruf je Hotel)
    und wird dauerhaft in `meta` gecacht — Hotels wechseln die Region nicht."""
    try:
        cache = json.loads(A._meta_get('basket_region_map') or '{}')
    except (TypeError, json.JSONDecodeError):
        cache = {}
    with A.db() as con:
        offers = con.execute(
            'SELECT url, region, return_date FROM offers '
            'WHERE COALESCE(archived,0)=0 ORDER BY id').fetchall()
    out, dirty, grouped = [], False, set()
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
        if not rg:
            continue
        nights = A.duration_from_url(o['url']) or BASKET_NIGHTS
        dep = _offer_departure(o['return_date'], nights)
        if dep < date.today():
            continue
        group = (int(rg), dep.year, dep.month, nights)
        if group in grouped:
            continue
        grouped.add(group)
        label = (o['region'] or '').strip() or str(rg)
        vom, bis = _month_window(dep, nights)
        key = f"{label} ({_MONTHS_DE[dep.month - 1]} {dep.year}, {nights} Nächte)"
        if key in seen:
            continue
        seen.add(key)
        payload = {'dest': {'giata': int(rg), 'label': label},
                   'vom': vom.isoformat(), 'bis': bis.isoformat(),
                   'dur': nights, 'trav': BASKET_TRAVELLERS}
        # Angezeigt wird der Abreise-Bereich, nicht das Suchfenster — dessen Ende ist
        # um die Reisedauer verschoben (Rückreise-Rand) und läse sich sonst falsch.
        last_dep = bis - timedelta(days=nights)
        out.append({'key': key, 'giata': int(rg), 'payload': payload, 'source': 'offer',
                    'period': f"Abreise {vom.strftime('%d.%m.')} – "
                              f"{last_dep.strftime('%d.%m.%Y')}"})
    if dirty:
        A._meta_set('basket_region_map', json.dumps(cache))
    return out


def _offer_departure(return_date: str, nights: int) -> date:
    """Abreisedatum eines Angebots: Rückreise minus Dauer. Fehlt das Rückreisedatum
    oder ist es unlesbar, bleibt nur die konstante Vorlaufzeit als Näherung."""
    try:
        return date.fromisoformat((return_date or '')[:10]) - timedelta(days=nights)
    except ValueError:
        return date.today() + timedelta(days=_lead_days())


# ── Snapshot holen und ablegen ─────────────────────────────────────────────────

def _fetch_basket(payload: dict) -> list:
    """Die gespeicherte Suche ausführen — mit ihren echten Reiseterminen, ihrer
    Dauer und ihren Filtern (`watch._search_from_fav_payload`, dieselbe Funktion,
    die auch das Suchabo nutzt). Über die Tage bleiben die Parameter identisch,
    genau deshalb sind die Snapshots vergleichbar.

    Geholt wird die Suche **vollständig** (bis `total` erreicht ist), nicht nur die
    erste Seite. Grund: die Such-API sortiert nach Preis aufsteigend — ein fester
    Seiten-Deckel würde stets die *günstigsten* N Hotels erfassen, und Hotels an
    dieser Grenze wandern täglich rein und raus. Genau diese wechselnde Randbelegung
    würde der Median als Preisbewegung missverstehen. `BASKET_MAX_PAGES` ist nur eine
    Reißleine gegen ein unerwartet riesiges Suchergebnis."""
    import watch  # spät: watch importiert seinerseits app, das hier gerade lädt
    out, seen = [], set()
    total = None
    for page in range(BASKET_MAX_PAGES):
        res = watch._search_from_fav_payload(payload, offset=page * BASKET_PAGE_SIZE)
        if not (res and res.get('ok')):
            break
        if total is None:
            total = res.get('total')
        rows = res.get('results') or []
        for r in rows:
            g = str(r.get('giata') or '')
            if not g or g in seen or r.get('price') is None:
                continue
            seen.add(g)
            out.append(r)
        # Abbruch, sobald die gemeldete Gesamttrefferzahl abgearbeitet ist. Die
        # Seitengröße selbst taugt nicht als alleiniges Abbruchsignal: die Nachfilter
        # (Sterne/Weiterempfehlung) können eine volle Seite auf wenige Treffer
        # eindampfen, ohne dass die Suche zu Ende wäre.
        if total is not None and (page + 1) * BASKET_PAGE_SIZE >= total:
            break
        if not rows:
            break
    else:
        A.log.warning("Warenkorb nach %d Seiten abgebrochen (gemeldet: %s Treffer) — "
                      "Warenkorb ist unvollständig", BASKET_MAX_PAGES, total)
    return out


def _store_snapshot(con, basket: str, region_giata: int, day: str, ts: int, rows: list) -> None:
    """Snapshot des Tages ersetzen (ein manueller Zweitlauf am selben Tag soll den
    ersten überschreiben, nicht danebenliegen)."""
    con.execute('DELETE FROM basket_snapshots WHERE basket=? AND day=?', (basket, day))
    con.executemany(
        'INSERT INTO basket_snapshots (ts, day, basket, region_giata, giata, price, '
        'board, nights, dep_date) VALUES (?,?,?,?,?,?,?,?,?)',
        [(ts, day, basket, region_giata, str(r.get('giata')), float(r['price']),
          r.get('board') or '', r.get('nights'), r.get('date') or '') for r in rows])


def _compute_move(con, basket: str, day: str) -> dict | None:
    """Tagesbewegung eines Warenkorbs aus dem Vergleich mit dem letzten vorhandenen
    Snapshot. Rückgabe None, wenn es keinen Vorgänger gibt, die Lücke zu groß ist
    oder zu wenige Hotels in beiden Snapshots stehen."""
    prev = con.execute(
        'SELECT DISTINCT day FROM basket_snapshots WHERE basket=? AND day<? '
        'ORDER BY day DESC LIMIT 1', (basket, day)).fetchone()
    if not prev:
        return None
    prev_day = prev['day']
    try:
        gap = (date.fromisoformat(day) - date.fromisoformat(prev_day)).days
    except ValueError:
        return None
    if gap > BASKET_MAX_GAP_DAYS:
        A.log.info("Warenkorb „%s“: %d Tage Lücke seit %s — Kette beginnt neu",
                   basket, gap, prev_day)
        return None

    def _snap(d):
        return {r['giata']: r for r in con.execute(
            'SELECT giata, price, board, nights FROM basket_snapshots '
            'WHERE basket=? AND day=?', (basket, d)).fetchall()}

    cur, old = _snap(day), _snap(prev_day)
    pcts = []
    for g, c in cur.items():
        o = old.get(g)
        if not o or not o['price']:
            continue
        # Zimmerkategorie ist unsichtbar, Verpflegung/Dauer aber nicht — ein Wechsel
        # dort ist ein anderer Angebotstyp, kein Marktsignal. Das Abreisedatum wird
        # bewusst NICHT verglichen: wandert der günstigste Termin innerhalb des
        # gesuchten Zeitraums, ist genau das die gesuchte Information.
        if (o['board'] or '') != (c['board'] or '') or o['nights'] != c['nights']:
            continue
        pcts.append((c['price'] - o['price']) / o['price'] * 100)
    # Mindestbreite an der KLEINEREN der beiden Snapshot-Größen messen: schrumpft der
    # Warenkorb (Saisonende, Hotels ausgebucht), soll die Schwelle mitschrumpfen und
    # nicht am größeren Vortag hängen bleiben.
    need = _min_matched(min(len(cur), len(old)))
    if len(pcts) < need:
        A.log.info("Warenkorb „%s“: nur %d von %d vergleichbaren Hotels (min. %d) — "
                   "Tag verworfen", basket, len(pcts), min(len(cur), len(old)), need)
        return None
    med = statistics.median(pcts)
    con.execute(
        'INSERT OR REPLACE INTO basket_moves (ts, day, basket, prev_day, gap_days, '
        'pct_median, n_matched, n_total) VALUES (?,?,?,?,?,?,?,?)',
        (int(time.time()), day, basket, prev_day, gap, med, len(pcts), len(cur)))
    return {'day': day, 'prev_day': prev_day, 'gap_days': gap,
            'pct_median': round(med, 2), 'n_matched': len(pcts), 'n_total': len(cur)}


def _min_matched(basket_size: int) -> int:
    """Wie viele Hotel-Paare ein Tag mindestens braucht, um gezählt zu werden.

    Eine feste Zahl (10) war für stark gefilterte Suchen zu streng: wer „nur All
    Inclusive, Direktflug ab STR, Lage 10" sucht, bekommt vielleicht 12 Treffer —
    ein einziger Verpflegungswechsel bei zweien reicht dann, und der Tag fällt
    dauerhaft durch. Deshalb relativ zur Warenkorbgröße (60 %), nach oben durch
    BASKET_MIN_MATCHED gedeckelt (große Warenkörbe bleiben streng) und nach unten
    durch BASKET_MIN_MATCHED_FLOOR — unter fünf Werten ist ein Median beliebig."""
    return max(BASKET_MIN_MATCHED_FLOOR,
               min(BASKET_MIN_MATCHED, int(basket_size * BASKET_MIN_MATCHED_SHARE)))


def _prune(con) -> None:
    """Alte Snapshots wegwerfen — die verdichteten `basket_moves` bleiben, der Index
    seit Aufzeichnungsbeginn überlebt das Beschneiden also."""
    cutoff = (date.today() - timedelta(days=BASKET_RETENTION_DAYS)).isoformat()
    con.execute('DELETE FROM basket_snapshots WHERE day<?', (cutoff,))


def run_basket(target: dict) -> dict:
    """Einen Warenkorb komplett durchlaufen: Suche ausführen, Snapshot ablegen,
    Tagesbewegung berechnen. Rückgabe für Log/API."""
    key = target['key']
    rows = _fetch_basket(target['payload'])
    if not rows:
        A.log.warning("Warenkorb „%s“ (%s): Suche lieferte keine Treffer",
                      key, target.get('period') or '?')
        return {'basket': key, 'hotels': 0, 'move': None}
    ts = int(time.time())
    day = datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
    with A.db() as con:
        _store_snapshot(con, key, target.get('giata'), day, ts, rows)
        move = _compute_move(con, key, day)
        _prune(con)
    A.log.info("Warenkorb „%s“ (%s): %d Hotels erfasst%s", key,
               target.get('period') or '?', len(rows),
               (f", Tagesbewegung {move['pct_median']:+.2f} % aus {move['n_matched']} Hotels"
                if move else " (noch keine Tagesbewegung)"))
    return {'basket': key, 'hotels': len(rows), 'move': move}


def run_baskets(*, force: bool = False) -> list:
    """Alle Warenkörbe abarbeiten, jeden höchstens 1×/Tag (`force` umgeht das für den
    manuellen Anstoß aus der UI). Ein Lauf gleichzeitig — der Poll-Worker und ein
    UI-Klick dürfen sich nicht überlappen."""
    global _running
    with _run_lock:
        if _running:
            return []
        _running = True
    try:
        day = datetime.now().strftime('%Y-%m-%d')
        targets = _basket_targets()
        if not force:
            # Schon erledigte Warenkörbe vorab aussortieren, damit der Fortschritt
            # die tatsächlich anstehende Arbeit zeigt und nicht bei „3 von 8"
            # stehenbleibt, weil fünf übersprungen wurden.
            with A.db() as con:
                targets = [t for t in targets if not con.execute(
                    'SELECT 1 FROM basket_snapshots WHERE basket=? AND day=? LIMIT 1',
                    (t['key'], day)).fetchone()]
        _set_progress(done=0, total=len(targets), current='', hotels=0)
        out = []
        for target in targets:
            _set_progress(current=target['key'])
            try:
                res = run_basket(target)
                out.append(res)
                _set_progress(hotels=_progress['hotels'] + res['hotels'])
            except Exception as e:
                A.log.error("Warenkorb „%s“ fehlgeschlagen: %s: %s",
                            target['key'], type(e).__name__, e)
            _set_progress(done=_progress['done'] + 1)
        _set_progress(current='')
        return out
    finally:
        _running = False


def maybe_run_baskets() -> None:
    """Aufhänger für den Poll-Worker (analog `_maybe_refresh_calendars`)."""
    if not _enabled():
        return
    run_baskets()


# ── Auswertung ─────────────────────────────────────────────────────────────────

def _moves_query(basket: str | None, cutoff_day: str | None) -> tuple[str, list]:
    """Fester Query-Text mit `(? IS NULL OR …)`-Paaren statt laufzeitabhängiger
    String-Verkettung — gleiche Begründung wie bei `A._market_moves_query`: CodeQL
    stuft dynamisch zusammengebautes SQL pauschal als riskant ein."""
    q = ('SELECT day, basket, pct_median, n_matched FROM basket_moves '
         'WHERE (? IS NULL OR day>=?) AND (? IS NULL OR basket=?) ORDER BY day ASC')
    return q, [cutoff_day, cutoff_day, basket, basket]


def _daily_series(con, basket: str | None, cutoff_day: str | None) -> list:
    """Tageswerte als [(tag, prozent, hotelzahl)]. Über alle Warenkörbe hinweg
    (basket None) werden deren Mediane eines Tages nach Hotelzahl gewichtet
    gemittelt — ein Warenkorb mit 200 Hotels soll den Gesamtwert stärker prägen als
    einer mit 15."""
    q, params = _moves_query(basket, cutoff_day)
    by_day: dict[str, list] = defaultdict(list)
    for r in con.execute(q, params).fetchall():
        by_day[r['day']].append((r['pct_median'], max(1, r['n_matched'])))
    out = []
    for day in sorted(by_day):
        vals = by_day[day]
        total = sum(n for _, n in vals)
        out.append((day, sum(p * n for p, n in vals) / total, total))
    return out


def basket_trend(con, *, basket: str | None = None, window_days: int = 14) -> dict | None:
    """Warenkorb-Trend über ein rollierendes Fenster. Gleiche Rückgabeform wie
    `A._market_trend` (dir/pct/days/n), damit UI und Sensor beide Quellen ohne
    Sonderfälle anzeigen können; `hotels` nennt zusätzlich die Breite der Basis."""
    cutoff = (date.today() - timedelta(days=window_days)).isoformat()
    series = _daily_series(con, basket, cutoff)
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


def basket_index(con, *, basket: str | None = None) -> dict | None:
    """Warenkorb-Index seit Aufzeichnungsbeginn (Basis 100), analog `A._market_index` —
    fängt langsame Bewegungen ab, die aus dem 14-Tage-Fenster herausfallen."""
    series = _daily_series(con, basket, None)
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
    """Kompletter Warenkorb-Stand für API und HA-Sensor. `by_region` heißt aus
    Kompatibilitätsgründen weiter so (UI und Sensor-Attribute), enthält aber je einen
    Warenkorb — also eine gespeicherte Suche samt Reisezeitraum."""
    targets = _basket_targets()   # nur EINMAL — kann Breadcrumb-Abrufe auslösen
    periods = {t['key']: t.get('period') or '' for t in targets}
    with A.db() as con:
        keys = [r['basket'] for r in con.execute(
            "SELECT DISTINCT basket FROM basket_moves WHERE basket!=''").fetchall()]
        glob = {'trend': basket_trend(con), 'index': basket_index(con)}
        by_region = []
        for k in sorted(keys):
            t, i = basket_trend(con, basket=k), basket_index(con, basket=k)
            if t or i:
                by_region.append({'region': k, 'period': periods.get(k, ''),
                                  'trend': t, 'index': i})
        last = con.execute('SELECT MAX(day) d FROM basket_snapshots').fetchone()
        pending = [r['basket'] for r in con.execute(
            "SELECT DISTINCT basket FROM basket_snapshots WHERE basket NOT IN "
            "(SELECT basket FROM basket_moves)").fetchall()]
    return {'enabled': _enabled(), 'global': glob, 'by_region': by_region,
            'last_day': (last['d'] if last else None) or '',
            'baskets': [{'key': t['key'], 'period': t.get('period') or '',
                         'source': t.get('source')} for t in targets],
            'pending': sorted(pending), 'running': _running,
            'progress': dict(_progress)}


# ── Routen ─────────────────────────────────────────────────────────────────────

@bp.route('/api/market-basket')
def api_market_basket():
    """Warenkorb-Markttrend: global und je gespeicherter Suche, plus Status (letzter
    Lauf, Warenkörbe ohne verwertbare Bewegung)."""
    if (err := A._require_api()):
        return err
    return jsonify(basket_payload())


@bp.route('/api/market-basket/progress')
def api_market_basket_progress():
    """Schlanker Endpunkt allein für den Fortschrittsbalken — die UI fragt ihn
    sekündlich ab, während ein Lauf läuft. Bewusst OHNE `basket_payload()`: das
    ermittelt die Warenkörbe neu und liest die komplette Auswertung, viel zu teuer
    für eine Abfrage im Sekundentakt."""
    if (err := A._require_api()):
        return err
    return jsonify({'running': _running, 'progress': dict(_progress)})


@bp.route('/api/market-basket/run', methods=['POST'])
def api_market_basket_run():
    """Warenkorb-Lauf sofort anstoßen. Läuft im Hintergrund (mehrere Warenkörbe ×
    mehrere Suchseiten dauern länger als ein sinnvolles Request-Timeout) — die UI
    fragt danach `/api/market-basket` erneut ab."""
    if (err := A._require_api()):
        return err
    if _running:
        return jsonify({'started': False, 'note': 'läuft bereits'})
    targets = _basket_targets()
    if not targets:
        return jsonify({'started': False, 'note': 'keine gespeicherte Suche mit Ziel'})
    A._spawn(lambda: run_baskets(force=True))
    return jsonify({'started': True, 'regions': [t['key'] for t in targets]})


@bp.route('/api/market-basket/region', methods=['DELETE'])
def api_market_basket_region_delete():
    """Daten EINES Warenkorbs löschen (Snapshots und Bewegungen) — Neustart der
    Aufzeichnung, z. B. nachdem sich die Suchparameter geändert haben."""
    if (err := A._require_api()):
        return err
    region = ((request.get_json(silent=True) or {}).get('region') or '').strip()
    if not region:
        return jsonify({'error': 'invalid'}), 400
    with A.db() as con:
        snaps = con.execute('DELETE FROM basket_snapshots WHERE basket=?', (region,)).rowcount
        moves = con.execute('DELETE FROM basket_moves WHERE basket=?', (region,)).rowcount
    A.log.info("Warenkorb-Daten für „%s“ gelöscht: %d Snapshots, %d Tagesbewegungen",
               region, snaps, moves)
    return jsonify({'region': region, 'snapshots': snaps, 'moves': moves})
