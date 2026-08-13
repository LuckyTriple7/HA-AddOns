"""Markttrend aus einem täglichen Preisbarometer je gespeicherter Suche.

Der bisherige Markttrend (`price_moves` in app.py) misst nur die Preisbewegung der
GETRACKTEN Angebote — je Reiseziel oft nur ein, zwei Hotels. Dieses Modul erweitert
ihn um eine deutlich breitere Basis: einmal pro Tag läuft **genau die gespeicherte
Suche** des Nutzers noch einmal, und alle ihre Treffer werden als Barometer-Snapshot
abgelegt. Der Trend entsteht aus dem Vergleich aufeinanderfolgender Snapshots.

**Eine Messreihe je gespeicherter Suche**, nicht je Region — mit deren echten
Reiseterminen, Dauer, Verpflegungs-, Sterne- und Flughafenfiltern. Zwei Suchen für
dasselbe Ziel mit verschiedenen Terminen ergeben zwei getrennte Messreihen; das sind
schlicht verschiedene Märkte. Ein früherer Entwurf suchte stattdessen mit konstanter
Vorlaufzeit („heute + 91 Tage") — statistisch sauber, praktisch aber wertlos: wer
seinen Urlaub im Mai plant, dem hilft die Preisbewegung eines täglich weiterwandernden
Termins nicht bei der Frage, ob er JETZT buchen soll. Die konstante Vorlaufzeit ist
nur noch Rückfallebene für Messreihen ohne eigenes Datum (siehe `_offer_targets`).

Warum es so und nicht anders gerechnet wird:

* **Matched Pairs statt Durchschnittsvergleich.** Die Messreihe ändert sich täglich
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
  Deshalb wird pro Messreihe und Tag EIN Median abgelegt (`basket_moves`) und erst
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
BASKET_MIN_MATCHED_SHARE = 0.6  # Anteil der Messreihe, der wiederauftauchen muss
BASKET_MIN_DAYS = 2             # weniger Tagesbewegungen → kein Trend
BASKET_MAX_GAP_DAYS = 7         # größere Lücke (Add-on aus) → Kette neu beginnen
BASKET_RETENTION_DAYS = 120     # Snapshots älter als das werden verworfen

_run_lock = threading.Lock()
_running = False
# Fortschritt des laufenden Barometer-Laufs für die UI. Ein Lauf dauert je nach Anzahl
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
    beschnitten), `basket_moves` das verdichtete Ergebnis (eine Zeile je Messreihe
    und Tag, bleibt dauerhaft — winzig und die Grundlage des Index).

    `basket` ist der Schlüssel einer Messreihe: der Name der gespeicherten Suche
    bzw. „<Region> (Abreise TT.MM.JJJJ)" bei Messreihenn aus getrackten Angeboten.

    Migration: die erste Fassung (v0.60.x) schlüsselte nach Region und suchte mit
    konstanter Vorlaufzeit statt mit den echten Reiseterminen. Diese Datenpunkte
    haben eine andere Preisbasis und dürfen nicht mit den neuen verkettet werden —
    die alten Tabellen werden daher einmalig verworfen."""
    cols = {r['name'] for r in con.execute('PRAGMA table_info(basket_snapshots)').fetchall()}
    if cols and 'basket' not in cols:
        con.execute('DROP TABLE IF EXISTS basket_snapshots')
        con.execute('DROP TABLE IF EXISTS basket_moves')
        A.log.info("Preisbarometer: Daten der Regions-Fassung verworfen — die Messreihe "
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
    # Vorlaufzeit (Tage bis Abreise) je Tagesbewegung — zweite Dimension neben der
    # Zeitachse, Grundlage der Booking-Kurve. Bewusst auf `basket_moves` und nicht
    # nur in `basket_snapshots`: die Snapshots werden nach BASKET_RETENTION_DAYS
    # geworfen, die Kurve reicht aber bis 180+ Tage Vorlauf zurück.
    mcols = {r['name'] for r in con.execute('PRAGMA table_info(basket_moves)').fetchall()}
    if 'days_to_dep' not in mcols:
        con.execute('ALTER TABLE basket_moves ADD COLUMN days_to_dep INTEGER')
    # Preisniveau je Messreihe und Tag, verdichtet auf fünf Zahlen. Rein informativ
    # („was kostet dieser Markt gerade") — die Trendrechnung läuft weiter über die
    # Matched Pairs, weil rohe Perzentile die wechselnde Hotel-Zusammensetzung
    # messen würden, nicht den Preis. Überlebt den Snapshot-Prune.
    con.execute('''CREATE TABLE IF NOT EXISTS basket_levels (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        ts          INTEGER NOT NULL,
        day         TEXT NOT NULL,
        basket      TEXT NOT NULL DEFAULT '',
        days_to_dep INTEGER,
        n_hotels    INTEGER NOT NULL,
        p25         REAL,
        p50         REAL,
        p75         REAL
    )''')
    con.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_basket_level '
                'ON basket_levels(basket, day)')
    # Angebots-Messreihen hießen kurzzeitig „<Region> (Abreise TT.MM.JJJJ)" — ein
    # Preisbarometer je Einzeltermin. Seit der Monatsbündelung gibt es zu diesen
    # Schlüsseln keine Messreihe mehr; ihre Snapshots blieben sonst als
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
            A.log.info("Preisbarometer: %d Snapshots der Einzeltermin-Fassung verworfen "
                       "(Angebots-Messreihen laufen jetzt je Monat)", n)
    _backfill_booking(con)


def _backfill_booking(con) -> None:
    """Einmalig `days_to_dep` und `basket_levels` aus den noch vorhandenen Snapshots
    nachtragen — sonst startet die Booking-Kurve bei null, obwohl die Rohdaten der
    letzten `BASKET_RETENTION_DAYS` Tage schon auf Platte liegen.

    Der Vorlauf wird hier über ALLE Hotels des Tages gemittelt, nicht nur über die
    gematchten Paare wie im Live-Pfad (`_compute_move`) — der Vorgänger-Snapshot kann
    längst geprunt sein. Der Unterschied ist praktisch null: `dep_date` ist eine
    Eigenschaft des Suchfensters, nicht des einzelnen Hotels.

    Läuft genau einmal (`meta`-Flag). Tage, deren Snapshots bereits weg sind, bleiben
    dauerhaft ohne Vorlauf und fallen aus der Kurve — richtig so, geraten wird nicht."""
    if con.execute("SELECT 1 FROM meta WHERE key='basket_booking_backfill'").fetchone():
        return
    moves = con.execute(
        'SELECT basket, day FROM basket_moves WHERE days_to_dep IS NULL').fetchall()
    n_moves = 0
    for r in moves:
        dte = _median_dte(con, r['basket'], r['day'])
        if dte is None:
            continue
        con.execute('UPDATE basket_moves SET days_to_dep=? WHERE basket=? AND day=?',
                    (dte, r['basket'], r['day']))
        n_moves += 1
    days = con.execute(
        'SELECT DISTINCT basket, day FROM basket_snapshots WHERE basket!=\'\'').fetchall()
    n_lv = 0
    for r in days:
        rows = con.execute(
            'SELECT price, dep_date FROM basket_snapshots WHERE basket=? AND day=?',
            (r['basket'], r['day'])).fetchall()
        ts = con.execute('SELECT MIN(ts) t FROM basket_snapshots WHERE basket=? AND day=?',
                         (r['basket'], r['day'])).fetchone()['t'] or int(time.time())
        if _store_levels(con, r['basket'], r['day'], int(ts),
                         [{'price': x['price'], 'date': x['dep_date']} for x in rows]):
            n_lv += 1
    con.execute("INSERT OR REPLACE INTO meta (key, value) "
                "VALUES ('basket_booking_backfill','1')")
    if n_moves or n_lv:
        A.log.info("Booking-Kurve: %d Tagesbewegungen mit Vorlaufzeit ergänzt, "
                   "%d Preisniveaus nachgetragen", n_moves, n_lv)


# ── Konfiguration ──────────────────────────────────────────────────────────────

def _enabled() -> bool:
    return bool(A.load_config().get('market_basket_enabled', True))


def _lead_days() -> int:
    """Vorlaufzeit in Tagen für die Rückfallebene, auf 14…365 begrenzt. Greift NUR
    für Messreihen ohne eigenen Reisetermin (siehe `_offer_targets`) — gespeicherte
    Suchen bringen ihr Datum selbst mit."""
    try:
        v = int(A.load_config().get('market_basket_lead_days', BASKET_LEAD_DAYS_DEFAULT))
    except (TypeError, ValueError):
        return BASKET_LEAD_DAYS_DEFAULT
    return max(14, min(365, v))


def _max_regions() -> int:
    """Obergrenze für die täglich abgefragten Messreihen, auf 1…50 begrenzt.
    Der Deckel ist reiner Lastschutz: eine Messreihe kostet je 50 Hotels einen
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
    """Die täglich abzufragenden Messreihen. Jeder trägt seinen kompletten
    Such-Payload — also die echten Reisetermine des Nutzers, nicht ein künstlich
    berechnetes Datum.

    Quelle 1 sind die **gespeicherten Suchen** (Schlüssel = ihr Name; das ist die
    vom Nutzer selbst kuratierte Liste „was mich interessiert" samt Terminen und
    Filtern). Quelle 2 sind die Regionen der **getrackten Angebote**, für die kein
    Suchabo existiert. Abgelaufene Zeiträume fallen raus. Gedeckelt auf
    `_max_regions()`; wird abgeschnitten, sagt es das Log — sonst würde eine neu
    angelegte Suche stillschweigend nie im Preisbarometer landen."""
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
            A.log.debug("Preisbarometer: Suche „%s“ übersprungen (Reisezeitraum vorbei)", r['name'])
            continue
        key = (r['name'] or '').strip() or f"Suche {giata}"
        if key in seen:
            continue
        seen.add(key)
        out.append({'key': key, 'giata': giata, 'payload': payload,
                    'period': _period(payload), 'source': 'search'})
    out += _offer_targets(seen)
    if len(out) > limit:
        A.log.warning("Preisbarometer: %d Messreihen gefunden, aber nur %d erlaubt — nicht "
                      "berücksichtigt: %s (Option market_basket_max_regions erhöhen)",
                      len(out), limit, ", ".join(t['key'] for t in out[limit:]))
    return out[:limit]


_MONTHS_DE = ('Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli',
              'August', 'September', 'Oktober', 'November', 'Dezember')


def _month_window(dep: date, nights: int) -> tuple[date, date]:
    """Suchfenster für den Abreisemonat von `dep`: (früheste Abreise, späteste
    Rückreise). Ab heute gerechnet — ein bereits laufender Monat beginnt beim
    Preisbarometer heute, nicht rückwirkend.

    Das Ende ist Monatsletzter **plus Reisedauer**, weil `endDate` bei der Such-API
    die späteste Rückreise meint. Ohne den Aufschlag fielen genau die Abreisen am
    Monatsende heraus (im Log: Abreise 31.05. mit 11 Nächten endet am 11.06.)."""
    first = max(dep.replace(day=1), date.today())
    nxt = (dep.replace(day=28) + timedelta(days=4)).replace(day=1)
    return first, nxt - timedelta(days=1) + timedelta(days=nights)


def _offer_targets(seen: set) -> list:
    """Messreihen aus den getrackten Angeboten — für Reiseziele, zu denen es keine
    gespeicherte Suche gibt. Der Reisetermin kommt aus dem Angebot selbst (Abreise
    = Rückreisedatum minus Dauer aus der URL); nur wenn dort nichts steht, greift
    ersatzweise die konstante Vorlaufzeit `market_basket_lead_days`.

    Gebündelt wird je **Region, Abreisemonat und Dauer**, nicht je Einzeltermin.
    Fünf getrackte Gran-Canaria-Angebote mit Abreise am 3., 7., 31. Mai sowie 7. und
    14. Juni ergaben sonst fünf Messreihen à ~220 Hotels und fünf Ergebnisseiten —
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
                A.log.debug("Preisbarometer: Region zu Hotel %s nicht ermittelbar: %s", hotel_giata, e)
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
        A.log.warning("Preisbarometer nach %d Seiten abgebrochen (gemeldet: %s Treffer) — "
                      "Preisbarometer ist unvollständig", BASKET_MAX_PAGES, total)
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


def _days_to_dep(dep_date: str, day: str) -> int | None:
    """Vorlaufzeit in Tagen: Abreisetag minus Snapshot-Tag. None bei fehlendem oder
    unlesbarem Datum. Negative Werte (Abreise liegt hinter dem Snapshot) gibt es nur
    bei kaputten Daten und werden verworfen."""
    try:
        d = (date.fromisoformat((dep_date or '')[:10]) - date.fromisoformat(day)).days
    except ValueError:
        return None
    return d if d >= 0 else None


def _median_dte(con, basket: str, day: str) -> int | None:
    """Repräsentative Vorlaufzeit einer Messreihe an einem Tag: Median über die
    Abreisedaten des Snapshots. Median, weil Monatsfenster-Suchen (`_month_window`)
    je Hotel den günstigsten Termin im ganzen Monat liefern — die Einzelwerte
    streuen also über bis zu 30 Tage."""
    rows = con.execute('SELECT dep_date FROM basket_snapshots WHERE basket=? AND day=?',
                       (basket, day)).fetchall()
    vals = [d for d in (_days_to_dep(r['dep_date'], day) for r in rows) if d is not None]
    return int(round(statistics.median(vals))) if vals else None


def _store_levels(con, basket: str, day: str, ts: int, rows: list) -> bool:
    """Preisniveau des Tages verdichten (P25/Median/P75 über alle Hotelpreise des
    Snapshots) und in `basket_levels` ablegen. Fünf Zahlen je Messreihe und Tag,
    die den Snapshot-Prune überleben — Grundlage der €-Kontextanzeige.

    Ausdrücklich NICHT die Trendbasis: über die Tage wechselt die Hotelauswahl, rohe
    Perzentile würden diese Zusammensetzung messen. Dafür bleiben die Matched Pairs
    in `_compute_move` zuständig. Rückgabe True, wenn eine Zeile geschrieben wurde."""
    prices = sorted(float(r['price']) for r in rows if r.get('price') is not None)
    if not prices:
        return False
    # `statistics.quantiles` braucht mindestens zwei Werte; bei einem einzigen Hotel
    # sind alle drei Perzentile schlicht dieser Preis.
    if len(prices) >= 2:
        q = statistics.quantiles(prices, n=4, method='inclusive')
        p25, p50, p75 = q[0], q[1], q[2]
    else:
        p25 = p50 = p75 = prices[0]
    dtes = [d for d in (_days_to_dep(r.get('date') or '', day) for r in rows) if d is not None]
    con.execute(
        'INSERT OR REPLACE INTO basket_levels (ts, day, basket, days_to_dep, n_hotels, '
        'p25, p50, p75) VALUES (?,?,?,?,?,?,?,?)',
        (ts, day, basket, int(round(statistics.median(dtes))) if dtes else None,
         len(prices), round(p25, 2), round(p50, 2), round(p75, 2)))
    return True


def _compute_move(con, basket: str, day: str) -> dict | None:
    """Tagesbewegung einer Messreihe aus dem Vergleich mit dem letzten vorhandenen
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
        A.log.info("Messreihe „%s“: %d Tage Lücke seit %s — Kette beginnt neu",
                   basket, gap, prev_day)
        return None

    def _snap(d):
        return {r['giata']: r for r in con.execute(
            'SELECT giata, price, board, nights, dep_date FROM basket_snapshots '
            'WHERE basket=? AND day=?', (basket, d)).fetchall()}

    cur, old = _snap(day), _snap(prev_day)
    pcts, dtes = [], []
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
        # Vorlaufzeit derselben Grundgesamtheit, aus der auch der Median stammt —
        # so beschreibt sie genau die Hotels, die diese Bewegung erzeugt haben.
        dte = _days_to_dep(c['dep_date'], day)
        if dte is not None:
            dtes.append(dte)
    # Mindestbreite an der KLEINEREN der beiden Snapshot-Größen messen: schrumpft der
    # Preisbarometer (Saisonende, Hotels ausgebucht), soll die Schwelle mitschrumpfen und
    # nicht am größeren Vortag hängen bleiben.
    need = _min_matched(min(len(cur), len(old)))
    if len(pcts) < need:
        A.log.info("Messreihe „%s“: nur %d von %d vergleichbaren Hotels (min. %d) — "
                   "Tag verworfen", basket, len(pcts), min(len(cur), len(old)), need)
        return None
    med = statistics.median(pcts)
    dte = int(round(statistics.median(dtes))) if dtes else None
    con.execute(
        'INSERT OR REPLACE INTO basket_moves (ts, day, basket, prev_day, gap_days, '
        'pct_median, n_matched, n_total, days_to_dep) VALUES (?,?,?,?,?,?,?,?,?)',
        (int(time.time()), day, basket, prev_day, gap, med, len(pcts), len(cur), dte))
    return {'day': day, 'prev_day': prev_day, 'gap_days': gap,
            'pct_median': round(med, 2), 'n_matched': len(pcts), 'n_total': len(cur),
            'days_to_dep': dte}


def _min_matched(basket_size: int) -> int:
    """Wie viele Hotel-Paare ein Tag mindestens braucht, um gezählt zu werden.

    Eine feste Zahl (10) war für stark gefilterte Suchen zu streng: wer „nur All
    Inclusive, Direktflug ab STR, Lage 10" sucht, bekommt vielleicht 12 Treffer —
    ein einziger Verpflegungswechsel bei zweien reicht dann, und der Tag fällt
    dauerhaft durch. Deshalb relativ zur Messreihengröße (60 %), nach oben durch
    BASKET_MIN_MATCHED gedeckelt (große Messreihen bleiben streng) und nach unten
    durch BASKET_MIN_MATCHED_FLOOR — unter fünf Werten ist ein Median beliebig."""
    return max(BASKET_MIN_MATCHED_FLOOR,
               min(BASKET_MIN_MATCHED, int(basket_size * BASKET_MIN_MATCHED_SHARE)))


def _prune(con) -> None:
    """Alte Snapshots wegwerfen — die verdichteten `basket_moves` bleiben, der Index
    seit Aufzeichnungsbeginn überlebt das Beschneiden also."""
    cutoff = (date.today() - timedelta(days=BASKET_RETENTION_DAYS)).isoformat()
    con.execute('DELETE FROM basket_snapshots WHERE day<?', (cutoff,))


def run_basket(target: dict) -> dict:
    """Einen Preisbarometer komplett durchlaufen: Suche ausführen, Snapshot ablegen,
    Tagesbewegung berechnen. Rückgabe für Log/API."""
    key = target['key']
    rows = _fetch_basket(target['payload'])
    if not rows:
        A.log.warning("Messreihe „%s“ (%s): Suche lieferte keine Treffer",
                      key, target.get('period') or '?')
        return {'basket': key, 'hotels': 0, 'move': None}
    ts = int(time.time())
    day = datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
    with A.db() as con:
        _store_snapshot(con, key, target.get('giata'), day, ts, rows)
        _store_levels(con, key, day, ts, rows)
        move = _compute_move(con, key, day)
        _prune(con)
    _invalidate_curve()
    A.log.info("Messreihe „%s“ (%s): %d Hotels erfasst%s", key,
               target.get('period') or '?', len(rows),
               (f", Tagesbewegung {move['pct_median']:+.2f} % aus {move['n_matched']} Hotels"
                if move else " (noch keine Tagesbewegung)"))
    return {'basket': key, 'hotels': len(rows), 'move': move}


def run_baskets(*, force: bool = False) -> list:
    """Alle Messreihen abarbeiten, jeden höchstens 1×/Tag (`force` umgeht das für den
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
            # Schon erledigte Messreihen vorab aussortieren, damit der Fortschritt
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
                A.log.error("Messreihe „%s“ fehlgeschlagen: %s: %s",
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


def schedule_info() -> dict:
    """Wann steht das Preisbarometer das nächste Mal an? Für die Zeitplan-Übersicht
    (Rechtsklick aufs Logo). `next`: 0 = beim nächsten Poll-Durchlauf, sonst Zeitstempel;
    `disabled` = im Add-on abgeschaltet."""
    if not _enabled():
        return {'next': None, 'disabled': True, 'note': 'in den Add-on-Optionen abgeschaltet'}
    day = datetime.now().strftime('%Y-%m-%d')
    targets = _basket_targets()
    if not targets:
        return {'next': None, 'note': 'keine Messreihen (gespeicherte Suchen/Regionen)'}
    with A.db() as con:
        open_n = sum(1 for t in targets if not con.execute(
            'SELECT 1 FROM basket_snapshots WHERE basket=? AND day=? LIMIT 1',
            (t['key'], day)).fetchone())
    if open_n:
        return {'next': 0, 'note': f'{open_n} von {len(targets)} Messreihen heute offen'}
    tomorrow = (datetime.now() + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return {'next': int(tomorrow.timestamp()),
            'note': f'{len(targets)} Messreihen heute erledigt'}


# ── Auswertung ─────────────────────────────────────────────────────────────────

def _moves_query(basket: str | None, cutoff_day: str | None) -> tuple[str, list]:
    """Fester Query-Text mit `(? IS NULL OR …)`-Paaren statt laufzeitabhängiger
    String-Verkettung — gleiche Begründung wie bei `A._market_moves_query`: CodeQL
    stuft dynamisch zusammengebautes SQL pauschal als riskant ein."""
    q = ('SELECT day, basket, pct_median, n_matched FROM basket_moves '
         'WHERE (? IS NULL OR day>=?) AND (? IS NULL OR basket=?) ORDER BY day ASC')
    return q, [cutoff_day, cutoff_day, basket, basket]


def _daily_series(con, basket: str | None, cutoff_day: str | None) -> list:
    """Tageswerte als [(tag, prozent, hotelzahl)]. Über alle Messreihen hinweg
    (basket None) werden deren Mediane eines Tages nach Hotelzahl gewichtet
    gemittelt — eine Messreihe mit 200 Hotels soll den Gesamtwert stärker prägen als
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
    """Preisbarometer-Trend über ein rollierendes Fenster. Gleiche Rückgabeform wie
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
    """Preisbarometer-Index seit Aufzeichnungsbeginn (Basis 100), analog `A._market_index` —
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


# ── Booking-Kurve: wie sich Preise über die Vorlaufzeit bewegen ────────────────
# Der Trend oben beantwortet „was passiert gerade?". Dieser Abschnitt beantwortet
# „ist jetzt ein guter Zeitpunkt zu buchen?" — eine andere Frage mit anderer Mathematik.
#
# Grundgedanke: jede Tagesbewegung trägt seit dieser Fassung ihre Vorlaufzeit
# (`days_to_dep`). Sortiert man alle Bewegungen ALLER Messreihen nach Vorlauf statt
# nach Kalendertag, entsteht die typische Preiskurve des Marktes: wie viel Prozent
# pro Tag bewegen sich Preise, wenn noch 120 Tage bis zur Abreise sind, und wie viel
# in der letzten Woche davor.
#
# Gepoolt wird global über alle Messreihen. Das ist zulässig, weil Prozentwerte
# dimensionslos sind — eine 900-€-Woche Mallorca und eine 3000-€-Fernreise sind in
# „% pro Tag" direkt vergleichbar, in Euro wären sie es nicht. Und es ist nötig:
# eine einzelne Messreihe durchläuft die Kurve nur einmal und liefert je Bucket
# eine Handvoll Punkte.

# (lo, hi, Beschriftung) — hi None = offen nach oben. Grenzen bewusst wie in der
# Reisebranche üblich: der Abstand wird kürzer, je näher die Abreise rückt, weil
# dort auch die Preisbewegung schneller wird.
BOOKING_BUCKETS = (
    (181, None, 'ab 181 Tage'),
    (121, 180, '180–121 Tage'),
    (91, 120, '120–91 Tage'),
    (61, 90, '90–61 Tage'),
    (31, 60, '60–31 Tage'),
    (8, 30, '30–8 Tage'),
    (0, 7, 'unter 8 Tage'),
)
BOOKING_OPEN_WIDTH = 60          # Rechenbreite des offenen Buckets (nur für die Anzeige)
BOOKING_CURVE_MIN_SAMPLES = 8    # weniger Punkte → kein Bucket-Wert, es wird nichts geraten
BOOKING_CURVE_MIN_SERIES = 2     # aus einer einzigen Messreihe ist es keine Marktkurve
BOOKING_POSITION_MIN_DAYS = 7    # Perzentilrang braucht eine Mindesthistorie
BOOKING_MIN_COVERAGE = 0.5       # Anteil der Resttage, den die Kurve abdecken muss
BOOKING_CURVE_TTL = 300          # s; die Kurve ändert sich höchstens 1×/Tag
BOOKING_LASTMINUTE_DAYS = 14     # darunter nie „warten" empfehlen
BOOKING_GREEN = 0.35             # Score-Schwellen der Ampel
BOOKING_RED = -0.35
# Gewichte der drei Ampel-Komponenten. Die erwartete Restbewegung wiegt am
# schwersten, weil sie als Einzige nach vorn schaut; der aktuelle 14-Tage-Trend am
# leichtesten, weil eine ruhige Woche wenig über die kommenden Monate sagt.
BOOKING_WEIGHTS = {'expected': 0.40, 'position': 0.35, 'trend': 0.25}
BOOKING_MIN_WEIGHT = 0.5         # weniger verfügbares Gewicht → gar keine Ampel

_curve_cache: dict = {'ts': 0.0, 'data': None}
_signal_cache: dict = {'ts': 0.0, 'data': None}


def _invalidate_curve() -> None:
    """Cache nach einem Barometer-Lauf verwerfen — sonst zeigte die UI direkt nach
    dem manuellen Anstoß bis zu `BOOKING_CURVE_TTL` Sekunden die alte Kurve."""
    _curve_cache.update(ts=0.0, data=None)
    _signal_cache.update(ts=0.0, data=None)


def _booking_enabled() -> bool:
    return _enabled() and bool(A.load_config().get('booking_window_enabled', True))


def _bucket_index(dte: int) -> int | None:
    for i, (lo, hi, _label) in enumerate(BOOKING_BUCKETS):
        if dte >= lo and (hi is None or dte <= hi):
            return i
    return None


def _bucket_width(lo: int, hi: int | None) -> int:
    return BOOKING_OPEN_WIDTH if hi is None else (hi - lo + 1)


def booking_curve(con) -> list:
    """Die Preiskurve über die Vorlaufzeit, ein Eintrag je Bucket.

    Je Tagesbewegung wird auf **Prozent pro Tag** normiert (`pct_median / gap_days`).
    Ohne diese Normierung wäre ein Wert aus einer 4-Tage-Lücke (Add-on war aus) mit
    einem echten Tagesschritt gleichgewichtet und würde die Kurve nach außen ziehen.
    Die Verkettung in `_daily_series` braucht diese Korrektur nicht — dort ist die
    Lücke als ein Kettenglied ja korrekt —, hier schon, weil eine Rate entsteht.

    Je Bucket der **Median** der Tagesraten, nicht ein gewichtetes Mittel: gepoolt
    stehen hier Messreihen sehr verschiedener Größe nebeneinander, und einzelne
    Ausreißertage (Aktionscode-Woche, Kontingentwechsel) würden ein Mittel
    dominieren. Die Tageswerte selbst sind bereits Mediane.

    Buckets unter `BOOKING_CURVE_MIN_SAMPLES` Punkten liefern `rate=None` — eine
    Kurve wird nicht erfunden. `thin` markiert Buckets, die zwar genug Punkte haben,
    aber aus weniger als `BOOKING_CURVE_MIN_SERIES` Messreihen stammen; die stehen
    in der UI mit Warnhinweis da statt stillschweigend als Marktaussage."""
    now = time.time()
    if _curve_cache['data'] is not None and now - _curve_cache['ts'] < BOOKING_CURVE_TTL:
        return _curve_cache['data']
    rows = con.execute(
        'SELECT basket, pct_median, gap_days, days_to_dep FROM basket_moves '
        'WHERE days_to_dep IS NOT NULL').fetchall()
    rates: dict[int, list] = defaultdict(list)
    series: dict[int, set] = defaultdict(set)
    for r in rows:
        i = _bucket_index(int(r['days_to_dep']))
        if i is None:
            continue
        rates[i].append(r['pct_median'] / max(1, r['gap_days'] or 1))
        series[i].add(r['basket'])
    out = []
    for i, (lo, hi, label) in enumerate(BOOKING_BUCKETS):
        vals, n_series = rates.get(i, []), len(series.get(i, ()))
        enough = len(vals) >= BOOKING_CURVE_MIN_SAMPLES
        rate = statistics.median(vals) if enough else None
        width = _bucket_width(lo, hi)
        out.append({
            'lo': lo, 'hi': hi, 'label': label, 'width': width,
            'rate': round(rate, 4) if rate is not None else None,
            # Was der ganze Bucket bewegt, wenn man ihn durchläuft — die Zahl, die
            # man in Reise-Ratgebern liest („90–61 Tage vor Abreise: −7 %").
            'pct': round(((1 + rate / 100) ** width - 1) * 100, 1) if rate is not None else None,
            'n': len(vals), 'n_series': n_series,
            'thin': bool(enough and n_series < BOOKING_CURVE_MIN_SERIES),
        })
    _curve_cache.update(ts=now, data=out)
    return out


def expected_remaining(curve: list, days_to_dep: int | None) -> dict | None:
    """Erwartete Preisbewegung von heute bis zur Abreise, aus der Kurve hochgerechnet.

    Die verbleibenden `D` Tage werden auf die Buckets aufgeteilt (an Tag mit Vorlauf
    ℓ gilt die Rate des Buckets, in dem ℓ liegt) und deren Tagesraten
    zinseszins-verkettet:

        E = (Π_b (1 + r_b/100)^{d_b} − 1) · 100

    Buckets ohne Datenlage zählen als Faktor 1 (neutral), gehen aber nicht als
    abgedeckt in `coverage` ein. Deckt die Kurve weniger als `BOOKING_MIN_COVERAGE`
    der Resttage ab, gibt es keine Aussage — lieber nichts sagen als eine Prognose,
    die zur Hälfte aus Annahmen besteht.

    Vorzeichen: E > 0 heißt „Preise steigen voraussichtlich" → jetzt buchen."""
    if not days_to_dep or days_to_dep <= 0:
        return None
    factor, covered = 1.0, 0
    for b in curve:
        # Resttage, deren Vorlauf in diesen Bucket fällt: ℓ läuft von D bis 1 herunter.
        hi = min(b['hi'] if b['hi'] is not None else days_to_dep, days_to_dep)
        overlap = max(0, hi - max(b['lo'], 1) + 1)
        if not overlap or b['rate'] is None:
            continue
        factor *= (1 + b['rate'] / 100) ** overlap
        covered += overlap
    coverage = covered / days_to_dep
    if coverage < BOOKING_MIN_COVERAGE:
        return None
    return {'pct': round((factor - 1) * 100, 1), 'coverage': round(coverage, 2),
            'days': days_to_dep}


def basket_position(con, basket: str) -> dict | None:
    """Wo steht der heutige Preis im bisher beobachteten Verlauf dieser Messreihe?

    Gerechnet wird auf dem **verketteten Index** `L_d = 100 · Π(1 + m_k/100)`, nicht
    auf den rohen Medianpreisen aus `basket_levels`. Grund ist derselbe, aus dem die
    Tagesbewegung Matched Pairs benutzt: die Hotelauswahl wechselt täglich, ein roher
    Medianpreis misst deshalb zu einem guten Teil die Zusammensetzung. Der verkettete
    Index ist davon per Konstruktion frei.

    `rank` = Anteil der bisherigen Tage, an denen es gleich teuer oder günstiger war.
    0 heißt „so günstig wie noch nie beobachtet", 100 „Höchststand"."""
    series = _daily_series(con, basket, None)
    if len(series) < BOOKING_POSITION_MIN_DAYS:
        return None
    idx, level = [], 100.0
    for _day, pct, _n in series:
        level *= (1 + pct / 100)
        idx.append(level)
    cur = idx[-1]
    rank = sum(1 for v in idx if v <= cur) / len(idx) * 100
    return {'rank': round(rank, 1), 'n': len(idx), 'index': round(cur, 1),
            'min': round(min(idx), 1), 'max': round(max(idx), 1)}


def _current_dte(con, basket: str) -> int | None:
    """Heutiger Vorlauf einer Messreihe: der zuletzt erfasste Wert, um die seither
    vergangenen Tage verringert. Ohne diese Korrektur zeigte eine Messreihe, deren
    letzter Lauf drei Tage her ist, einen zu großen Vorlauf — und damit eine zu
    optimistische Restbewegung."""
    r = con.execute(
        'SELECT day, days_to_dep FROM basket_moves WHERE basket=? AND days_to_dep IS NOT NULL '
        'ORDER BY day DESC LIMIT 1', (basket,)).fetchone()
    if not r:
        r = con.execute(
            'SELECT day, days_to_dep FROM basket_levels WHERE basket=? AND days_to_dep IS NOT NULL '
            'ORDER BY day DESC LIMIT 1', (basket,)).fetchone()
    if not r:
        return None
    try:
        elapsed = (date.today() - date.fromisoformat(r['day'])).days
    except ValueError:
        return None
    return max(0, int(r['days_to_dep']) - max(0, elapsed))


def _clip(v: float) -> float:
    return max(-1.0, min(1.0, v))


def booking_signal(con, basket: str, curve: list | None = None,
                   active: set | None = None) -> dict | None:
    """Die Ampel einer Messreihe: 🟢 buchen / 🟡 neutral / 🔴 warten.

    Bewusst deterministisch und aufschlüsselbar (kein LLM) — jede Komponente wird mit
    Rohwert und Datenbasis zurückgegeben, sonst wäre der Score eine Blackbox, der man
    eine Buchungsentscheidung nicht anvertrauen will.

        T = clip(−pct14 / 5)      fallende Preise = guter Moment
        P = clip((50 − rank)/50)  günstig im eigenen Verlauf = guter Moment
        E = clip(exp_pct / 10)    erwarteter Anstieg = jetzt buchen
        S = (0.25·T + 0.35·P + 0.40·E) / Σ verfügbarer Gewichte

    Fehlende Komponenten fallen heraus und die übrigen Gewichte werden renormiert;
    bleibt weniger als `BOOKING_MIN_WEIGHT` übrig, gibt es keine Ampel. Unter
    `BOOKING_LASTMINUTE_DAYS` Tagen Vorlauf wird nie 🔴 gezeigt — es gibt nichts mehr
    zu warten, und das Risiko ist dort einseitig (ausgebucht statt teurer)."""
    if curve is None:
        curve = booking_curve(con)
    if active is None:
        active = _active_keys(con)
    dte = _current_dte(con, basket)
    if basket not in active:
        # Abgeschlossene Messreihe: Empfehlung sofort aus, nicht erst wenn der Trend
        # nach 14 Tagen aus dem Fenster fällt.
        return {'basket': basket, 'days_to_dep': dte, 'components': {}, 'closed': True,
                'ampel': None, 'score': None,
                'note': 'Messreihe abgeschlossen — kein laufender Reisezeitraum mehr'}
    trend = basket_trend(con, basket=basket)
    pos = basket_position(con, basket)
    exp = expected_remaining(curve, dte)
    comps, total = {}, 0.0
    score = 0.0
    if trend:
        v = _clip(-trend['pct'] / 5)
        comps['trend'] = {'value': round(v, 2), 'pct': trend['pct'], 'dir': trend['dir'],
                          'weight': BOOKING_WEIGHTS['trend'], 'n': trend['n']}
        score += v * BOOKING_WEIGHTS['trend']
        total += BOOKING_WEIGHTS['trend']
    if pos:
        v = _clip((50 - pos['rank']) / 50)
        comps['position'] = {'value': round(v, 2), 'rank': pos['rank'], 'n': pos['n'],
                             'index': pos['index'], 'weight': BOOKING_WEIGHTS['position']}
        score += v * BOOKING_WEIGHTS['position']
        total += BOOKING_WEIGHTS['position']
    if exp:
        v = _clip(exp['pct'] / 10)
        comps['expected'] = {'value': round(v, 2), 'pct': exp['pct'],
                             'coverage': exp['coverage'],
                             'weight': BOOKING_WEIGHTS['expected']}
        score += v * BOOKING_WEIGHTS['expected']
        total += BOOKING_WEIGHTS['expected']
    out = {'basket': basket, 'days_to_dep': dte, 'components': comps, 'closed': False,
           'ampel': None, 'score': None, 'note': ''}
    if total < BOOKING_MIN_WEIGHT:
        out['note'] = ('zu wenig Daten für eine Empfehlung'
                       if comps else 'sammelt noch Daten')
        return out
    s = score / total
    ampel = 'green' if s >= BOOKING_GREEN else ('red' if s <= BOOKING_RED else 'yellow')
    if ampel == 'red' and dte is not None and dte < BOOKING_LASTMINUTE_DAYS:
        ampel = 'yellow'
        out['note'] = (f'weniger als {BOOKING_LASTMINUTE_DAYS} Tage bis zur Abreise — '
                       'Warten bringt hier nichts mehr')
    out.update(ampel=ampel, score=round(s, 2))
    return out


def booking_payload() -> dict:
    """Kurve plus Ampel je Messreihe — für die Route, das UI und den HA-Sensor."""
    if not _booking_enabled():
        return {'enabled': False, 'curve': [], 'signals': []}
    with A.db() as con:
        curve = booking_curve(con)
        active = _active_keys(con)
        keys = [r['basket'] for r in con.execute(
            "SELECT DISTINCT basket FROM basket_moves WHERE basket!=''").fetchall()]
        signals = [s for s in (booking_signal(con, k, curve, active) for k in sorted(keys)) if s]
    covered = sum(1 for b in curve if b['rate'] is not None)
    return {'enabled': True, 'curve': curve, 'signals': signals,
            'buckets_ready': covered, 'buckets_total': len(curve)}


def _signal_map(con) -> dict:
    """Ampeln je Messreihen-Schlüssel, gecacht. `_collect_offers` wird alle 5 s
    gepollt — ohne Cache liefe je Angebot und Poll die komplette Trend-/Positions-
    Rechnung. Der TTL ist unkritisch: die Zahlen ändern sich 1×/Tag."""
    now = time.time()
    if _signal_cache['data'] is not None and now - _signal_cache['ts'] < BOOKING_CURVE_TTL:
        return _signal_cache['data']
    curve = booking_curve(con)
    active = _active_keys(con)
    keys = [r['basket'] for r in con.execute(
        "SELECT DISTINCT basket FROM basket_moves WHERE basket!=''").fetchall()]
    data = {}
    for k in keys:
        s = booking_signal(con, k, curve, active)
        if s and s.get('ampel'):
            data[k] = s
    _signal_cache.update(ts=now, data=data)
    return data


def basket_key_for_offer(con, url: str, region: str, return_date: str) -> str | None:
    """Zu welcher Messreihe gehört ein getracktes Angebot?

    Läuft ausdrücklich **ohne Netz**: die Region kommt nur aus dem bereits
    aufgebauten `meta`-Cache `basket_region_map`, nie über einen Breadcrumb-Abruf.
    Diese Funktion hängt an `_collect_offers` und damit am 5-Sekunden-Poll der
    Oberfläche — ein HTTP-Aufruf pro Angebot und Poll wäre dort fatal. Hotels, die
    noch nicht im Cache stehen, bekommen beim nächsten Barometer-Lauf einen Eintrag
    und danach auch eine Ampel.

    Zuerst wird eine gespeicherte Suche gesucht, deren Ziel und Reisezeitraum zum
    Angebot passen (deren Messreihe ist die genauere), sonst greift der
    Angebots-Schlüssel aus `_offer_targets`."""
    hotel_giata = A._giata_from_url(url)
    if not hotel_giata:
        return None
    try:
        cache = json.loads(A._meta_get('basket_region_map') or '{}')
    except (TypeError, json.JSONDecodeError):
        return None
    rg = cache.get(hotel_giata)
    if not rg:
        return None
    nights = A.duration_from_url(url) or BASKET_NIGHTS
    dep = _offer_departure(return_date, nights)
    for r in con.execute('SELECT name, payload FROM saved_searches ORDER BY id').fetchall():
        try:
            payload = json.loads(r['payload']) or {}
            if int((payload.get('dest') or {}).get('giata')) != int(rg):
                continue
            vom = date.fromisoformat((payload.get('vom') or '')[:10])
            bis = date.fromisoformat((payload.get('bis') or payload.get('vom') or '')[:10])
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if vom <= dep <= bis:
            return (r['name'] or '').strip() or f"Suche {int(rg)}"
    label = (region or '').strip() or str(rg)
    return f"{label} ({_MONTHS_DE[dep.month - 1]} {dep.year}, {nights} Nächte)"


def _active_keys(con) -> set:
    """Schlüssel der Messreihen, die noch eine lebende Quelle haben.

    Alles andere ist **abgeschlossen**: der Reisezeitraum ist vorbei, oder die
    gespeicherte Suche wurde gelöscht bzw. umbenannt (der Schlüssel ist ihr Name).
    Solche Reihen bekommen keine Ampel mehr — sonst stünde bis zu 14 Tage nach
    Ablauf noch „guter Buchungszeitpunkt" an einer Reise, die niemand mehr buchen
    kann. Ihr Index und ihr Beitrag zur Booking-Kurve bleiben dagegen erhalten:
    abgelaufene Reisen sind genau die, die ein Vorlauf-Fenster komplett durchlaufen
    haben.

    Bewusst OHNE Netzzugriff, denn diese Funktion hängt über `_signal_map` am
    5-Sekunden-Poll der Angebotsliste: die gespeicherten Suchen kommen aus der DB,
    die Angebots-Messreihen über `basket_key_for_offer` (nur `meta`-Cache). Deshalb
    hier eine eigene, schlanke Ermittlung statt `_basket_targets()`, das für
    unbekannte Hotels Breadcrumb-Abrufe auslösen würde. Dass beide Wege denselben
    Schlüssel bilden, sichert `test_active_keys_match_targets` ab."""
    keys = set()
    for r in con.execute('SELECT name, payload FROM saved_searches ORDER BY id').fetchall():
        try:
            payload = json.loads(r['payload']) or {}
            giata = int((payload.get('dest') or {}).get('giata'))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if _expired(payload):
            continue
        keys.add((r['name'] or '').strip() or f"Suche {giata}")
    for o in con.execute('SELECT url, region, return_date FROM offers '
                         'WHERE COALESCE(archived,0)=0').fetchall():
        try:
            k = basket_key_for_offer(con, o['url'], o['region'], o['return_date'])
        except Exception:
            continue
        if k:
            keys.add(k)
    return keys


def offer_signals(con, offers: list) -> dict:
    """Ampel je Angebots-ID für die Kachelansicht. `offers` sind die Zeilen aus
    `offers`; zurück kommt nur, wofür es auch wirklich eine Ampel gibt."""
    if not _booking_enabled():
        return {}
    try:
        signals = _signal_map(con)
    except Exception as e:      # eine kaputte Messreihe darf die Angebotsliste nicht kippen
        A.log.debug("Booking-Ampel für die Angebotsliste nicht ermittelbar: %s", e)
        return {}
    if not signals:
        return {}
    out = {}
    for o in offers:
        try:
            key = basket_key_for_offer(con, o['url'], o['region'], o['return_date'])
        except Exception:
            continue
        s = signals.get(key or '')
        if s:
            out[o['id']] = {'ampel': s['ampel'], 'score': s['score'],
                            'days_to_dep': s['days_to_dep'], 'basket': key,
                            'expected_pct': (s['components'].get('expected') or {}).get('pct'),
                            'rank': (s['components'].get('position') or {}).get('rank')}
    return out


def basket_payload() -> dict:
    """Kompletter Barometer-Stand für API und HA-Sensor. `by_region` heißt aus
    Kompatibilitätsgründen weiter so (UI und Sensor-Attribute), enthält aber je einen
    Preisbarometer — also eine gespeicherte Suche samt Reisezeitraum."""
    targets = _basket_targets()   # nur EINMAL — kann Breadcrumb-Abrufe auslösen
    periods = {t['key']: t.get('period') or '' for t in targets}
    booking = _booking_enabled()
    with A.db() as con:
        keys = [r['basket'] for r in con.execute(
            "SELECT DISTINCT basket FROM basket_moves WHERE basket!=''").fetchall()]
        glob = {'trend': basket_trend(con), 'index': basket_index(con)}
        # Kurve EINMAL für alle Messreihen (gepoolt und gecacht) statt je Zeile neu.
        curve = booking_curve(con) if booking else []
        # `_basket_targets()` kennt nur die aktiven Reihen — für die Kennzeichnung der
        # abgeschlossenen wird daraus direkt die Schlüsselmenge gebildet, statt
        # `_active_keys` ein zweites Mal zu rechnen.
        active = {t['key'] for t in targets}
        by_region = []
        for k in sorted(keys):
            t, i = basket_trend(con, basket=k), basket_index(con, basket=k)
            if t or i:
                last = con.execute('SELECT MAX(day) d FROM basket_moves WHERE basket=?',
                                   (k,)).fetchone()
                by_region.append({'region': k, 'period': periods.get(k, ''),
                                  'trend': t, 'index': i,
                                  'closed': k not in active,
                                  'last_day': (last['d'] if last else '') or '',
                                  'signal': booking_signal(con, k, curve, active) if booking else None,
                                  'level': _last_level(con, k)})
        last = con.execute('SELECT MAX(day) d FROM basket_snapshots').fetchone()
        pending = [r['basket'] for r in con.execute(
            "SELECT DISTINCT basket FROM basket_snapshots WHERE basket NOT IN "
            "(SELECT basket FROM basket_moves)").fetchall()]
    return {'enabled': _enabled(), 'global': glob, 'by_region': by_region,
            'last_day': (last['d'] if last else None) or '',
            'baskets': [{'key': t['key'], 'period': t.get('period') or '',
                         'source': t.get('source')} for t in targets],
            'pending': sorted(pending), 'running': _running,
            'progress': dict(_progress),
            'booking': {'enabled': booking, 'curve': curve,
                        'ready': sum(1 for b in curve if b['rate'] is not None),
                        'total': len(curve)}}


def _last_level(con, basket: str) -> dict | None:
    """Letztes bekanntes Preisniveau einer Messreihe (€-Kontext neben dem Index).
    Aus `basket_levels`, überlebt daher den Snapshot-Prune."""
    r = con.execute('SELECT day, n_hotels, p25, p50, p75 FROM basket_levels '
                    'WHERE basket=? ORDER BY day DESC LIMIT 1', (basket,)).fetchone()
    return dict(r) if r else None


# ── Routen ─────────────────────────────────────────────────────────────────────

@bp.route('/api/market-basket')
def api_market_basket():
    """Preisbarometer: global und je gespeicherter Suche, plus Status (letzter
    Lauf, Messreihen ohne verwertbare Bewegung)."""
    if (err := A._require_api()):
        return err
    return jsonify(basket_payload())


@bp.route('/api/booking-window')
def api_booking_window():
    """Booking-Kurve (global über alle Messreihen) plus Ampel je Messreihe — die
    Antwort auf „ist jetzt ein guter Zeitpunkt zu buchen?", im Unterschied zum
    Markttrend („was passiert gerade?")."""
    if (err := A._require_api()):
        return err
    return jsonify(booking_payload())


@bp.route('/api/market-basket/progress')
def api_market_basket_progress():
    """Schlanker Endpunkt allein für den Fortschrittsbalken — die UI fragt ihn
    sekündlich ab, während ein Lauf läuft. Bewusst OHNE `basket_payload()`: das
    ermittelt die Messreihen neu und liest die komplette Auswertung, viel zu teuer
    für eine Abfrage im Sekundentakt."""
    if (err := A._require_api()):
        return err
    return jsonify({'running': _running, 'progress': dict(_progress)})


@bp.route('/api/market-basket/run', methods=['POST'])
def api_market_basket_run():
    """Barometer-Lauf sofort anstoßen. Läuft im Hintergrund (mehrere Messreihen ×
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
    """Daten EINER Messreihe löschen (Snapshots und Bewegungen) — Neustart der
    Aufzeichnung, z. B. nachdem sich die Suchparameter geändert haben."""
    if (err := A._require_api()):
        return err
    region = ((request.get_json(silent=True) or {}).get('region') or '').strip()
    if not region:
        return jsonify({'error': 'invalid'}), 400
    with A.db() as con:
        snaps = con.execute('DELETE FROM basket_snapshots WHERE basket=?', (region,)).rowcount
        moves = con.execute('DELETE FROM basket_moves WHERE basket=?', (region,)).rowcount
        levels = con.execute('DELETE FROM basket_levels WHERE basket=?', (region,)).rowcount
    _invalidate_curve()
    A.log.info("Barometer-Daten für „%s“ gelöscht: %d Snapshots, %d Tagesbewegungen, "
               "%d Preisniveaus", region, snaps, moves, levels)
    return jsonify({'region': region, 'snapshots': snaps, 'moves': moves, 'levels': levels})
