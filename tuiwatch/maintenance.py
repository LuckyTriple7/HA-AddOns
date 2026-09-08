"""Datenbank-Wartung: Verlaufsdaten verdichten und Speicherplatz zurückgeben
(Backlog #18 und #19).

Zwei getrennte Dinge, die nur zusammen wirken:

* **Verdichten** dünnt alte Verlaufszeilen aus. `price_history` und
  `calendar_history` wachsen unbegrenzt — aufgeräumt wurde bisher nur
  `notify_log` (letzte 500), das Preisbarometer und die KI-Jobs. Bei den
  heutigen Größenordnungen (Nutzerdatenbank rund 25 MB) ist das unkritisch, der
  Pfad ist aber eben unbegrenzt.
* **`VACUUM`** gibt den frei gewordenen Platz ans Dateisystem zurück. SQLite tut
  das von sich aus nie: gelöschte Seiten bleiben in der Datei und werden nur
  intern wiederverwendet. Ohne Verdichten (oder gelöschte Angebote) bringt
  `VACUUM` deshalb so gut wie nichts.

Leitlinie beim Verdichten ist „ausdünnen, nicht wegwerfen": die Aussage des
Verlaufs bleibt erhalten, nur die Auflösung sinkt. Was das im Einzelnen heißt,
steht bei den beiden `_plan_*`-Funktionen — und es ist bewusst so gebaut, dass
die sichtbaren Kennzahlen (niedrigster/höchster Preis, Preisverlauf, Kalender-
Trend) sich dadurch nicht ändern.
"""
import sqlite3
import time
from datetime import date, timedelta

from flask import Blueprint, jsonify, request

import app as A

bp = Blueprint('maintenance', __name__)

# Wie oft im Hintergrund verdichtet wird, wenn die Einstellung gesetzt ist.
# Täglich reicht: es geht um Zeilen, die Monate alt sind.
COMPACT_INTERVAL = 24 * 3600

# Untergrenze für die Einstellung. Alles unter drei Monaten würde Zeilen
# anfassen, die für den 30-Tage-Schnitt und die Trendanzeige noch gebraucht
# werden — die Einstellung soll Altlasten ausdünnen, nicht den laufenden Betrieb.
COMPACT_MIN_MONTHS = 3


def _cutoff_ts(months: int) -> int:
    """Zeitstempel, ab dem verdichtet wird (alles ÄLTERE ist betroffen)."""
    return int(time.time()) - months * 30 * 86400


def _plan_price_history(con, cutoff: int) -> list[int]:
    """Zeilen-IDs aus `price_history`, die beim Verdichten wegfallen.

    Behalten wird je Angebot und Kalendertag:

    * die **erste** und die **letzte** Messung des Tages — sie tragen den Verlauf
      (`_trend_for`, das Preisdiagramm) und die Tagesgrenzen,
    * die **günstigste** und die **teuerste** — sonst würden „niedrigster Preis"
      und „höchster Preis" in der Angebotskarte nachträglich falsch.

    Alles dazwischen ist bei vier bis acht Messungen am Tag Wiederholung: Preise
    ändern sich zwischen zwei Prüfrunden fast nie. Fehlgeschlagene Abrufe
    (`ok=0`) bleiben unangetastet — sie sind selten, und die Störungsliste liest
    genau sie.

    Der Tagesdurchschnitt kann sich durch das Ausdünnen minimal verschieben; das
    ist der einzige Wert, der nicht exakt bleibt (dokumentiert in DOCS.md).
    """
    rows = con.execute(
        'SELECT id, offer_id, ts, price FROM price_history '
        'WHERE ts < ? AND ok=1 AND price IS NOT NULL ORDER BY offer_id, ts',
        (cutoff,)).fetchall()
    per_day: dict = {}
    for r in rows:
        key = (r['offer_id'], time.strftime('%Y-%m-%d', time.localtime(r['ts'])))
        per_day.setdefault(key, []).append((r['id'], r['price']))
    drop: list[int] = []
    for tag in per_day.values():
        if len(tag) <= 4:                     # erste+letzte+min+max deckt das ab
            continue
        keep = {tag[0][0], tag[-1][0],
                min(tag, key=lambda x: x[1])[0], max(tag, key=lambda x: x[1])[0]}
        drop.extend(i for i, _ in tag if i not in keep)
    return drop


def _plan_calendar_history(con, cutoff: int) -> list[int]:
    """Zeilen-IDs aus `calendar_history`, die beim Verdichten wegfallen.

    Behalten wird je Angebot, Reisetag und Kalenderwoche die **letzte**
    Beobachtung — der Stand am Ende dieser Woche. Die Tabelle ist ohnehin
    delta-codiert (eine Zeile nur bei Preisänderung), das Ausdünnen senkt also
    die zeitliche Auflösung alter Beobachtungen von „jede Änderung" auf
    „wöchentlich".

    Wichtig ist die Ausnahme: die **älteste** Zeile eines Reisetags bleibt immer
    stehen. Sie ist die Baseline, und `_calendar_moves()` zählt einen Reisetag
    erst ab zwei bekannten Preisen als bewegt — ohne diese Regel könnten alte
    Termine ihre Bewegung verlieren. Ebenso bleibt die jüngste Zeile: sie ist der
    Preis, den die Vorjahres-Ansicht und die abgereisten Termine anzeigen.
    """
    rows = con.execute(
        'SELECT id, offer_id, travel_date, ts FROM calendar_history '
        'WHERE ts < ? ORDER BY offer_id, travel_date, ts, id', (cutoff,)).fetchall()
    per_date: dict = {}
    for r in rows:
        per_date.setdefault((r['offer_id'], r['travel_date']), []).append((r['id'], r['ts']))
    drop: list[int] = []
    for zeilen in per_date.values():
        if len(zeilen) <= 2:
            continue
        keep = {zeilen[0][0], zeilen[-1][0]}          # Baseline und jüngste
        per_week: dict = {}
        for rid, ts in zeilen:
            woche = date.fromtimestamp(ts).isocalendar()[:2]
            per_week[woche] = rid                     # nach ts sortiert -> letzte gewinnt
        keep.update(per_week.values())
        drop.extend(rid for rid, _ in zeilen if rid not in keep)
    return drop


def compact_history(con, months: int, dry_run: bool = False) -> dict:
    """Verdichtet beide Verlaufstabellen. Gibt zurück, was (weg)fällt.

    `dry_run=True` rechnet nur — das ist der Weg, den die Oberfläche vor dem
    Nachfragen geht: niemand soll „Verdichten" drücken müssen, um zu erfahren,
    was es bringt.
    """
    cutoff = _cutoff_ts(months)
    ph = _plan_price_history(con, cutoff)
    ch = _plan_calendar_history(con, cutoff)
    if not dry_run:
        for tabelle, ids in (('price_history', ph), ('calendar_history', ch)):
            # In Blöcken löschen: eine IN-Liste mit zehntausenden Werten sprengt
            # das SQLite-Limit für Variablen einer Anweisung.
            for i in range(0, len(ids), 500):
                block = ids[i:i + 500]
                con.execute(
                    f'DELETE FROM {tabelle} WHERE id IN ({",".join("?" * len(block))})',
                    block)
    return {'cutoff_ts': cutoff, 'months': months,
            'price_history': len(ph), 'calendar_history': len(ch),
            'total': len(ph) + len(ch), 'dry_run': dry_run}


def vacuum() -> dict:
    """`VACUUM`: schreibt die Datei neu und gibt freie Seiten ans Dateisystem
    zurück. Gibt Größe vorher/nachher in Bytes zurück.

    Läuft bewusst auf einer eigenen Verbindung ohne `with`-Block: `VACUUM` ist in
    einer offenen Transaktion nicht erlaubt, und Pythons Verbindungs-
    Kontextmanager öffnet für schreibende Anweisungen eine.

    Vor dem Messen wird das WAL eingecheckt und abgeschnitten. Sonst verglichen
    sich zwei verschiedene Dinge: frische Löschungen stehen zunächst nur im WAL,
    die Hauptdatei ist noch klein — nach dem VACUUM steckt alles in der
    Hauptdatei, und die Bilanz sähe aus, als wäre die Datenbank gewachsen.
    """
    con = sqlite3.connect(A.DB_PATH, timeout=60)
    try:
        con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        vorher = A.db_file_size()
        con.execute('VACUUM')
        con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    finally:
        con.close()
    nachher = A.db_file_size()
    A.log.info("VACUUM: %.1f -> %.1f MB", vorher / 1048576, nachher / 1048576)
    return {'before': vorher, 'after': nachher, 'freed': max(0, vorher - nachher)}


def _configured_months() -> int:
    """Eingestellte Aufbewahrungsgrenze in Monaten; 0 = Verdichten ist aus."""
    try:
        months = int(A.load_config().get('history_compact_months', 0) or 0)
    except (TypeError, ValueError):
        return 0
    return months if months >= COMPACT_MIN_MONTHS else 0


def compact_worker() -> None:
    """Verdichtet täglich, sofern eingestellt. Ohne Einstellung passiert nichts —
    die Voreinstellung ist aus, Verlaufsdaten wegzuwerfen ist nichts, was ein
    Add-on ungefragt tun sollte."""
    time.sleep(300)                       # erst hochlaufen lassen
    while True:
        try:
            months = _configured_months()
            if months:
                with A.db() as con:
                    res = compact_history(con, months)
                if res['total']:
                    A.log.info("Verlauf verdichtet: %d Zeilen entfernt "
                               "(Preise %d, Kalender %d, älter als %d Monate)",
                               res['total'], res['price_history'],
                               res['calendar_history'], months)
        except Exception as e:
            A.log.warning("Verdichten fehlgeschlagen: %s", type(e).__name__)
        time.sleep(COMPACT_INTERVAL)


# ── Routen ─────────────────────────────────────────────────────────────────────

@bp.route('/api/db/stats', methods=['GET'])
def api_db_stats():
    """Größe der Datei, Zeilen je Verlaufstabelle und der ungenutzte Anteil.

    `freelist_count` × `page_size` ist der Platz, den ein `VACUUM` zurückgäbe —
    ohne diese Zahl wäre der Knopf ein Griff ins Dunkle."""
    if (err := A._require_api()):
        return err
    with A.db() as con:
        seiten = con.execute('PRAGMA page_size').fetchone()[0]
        frei = con.execute('PRAGMA freelist_count').fetchone()[0]
        tabellen = {}
        for t in ('price_history', 'calendar_history', 'calendar_month_moves',
                  'offer_events'):
            tabellen[t] = con.execute(f'SELECT COUNT(*) c FROM {t}').fetchone()['c']
    return jsonify({'bytes': A.db_file_size(), 'reclaimable': seiten * frei,
                    'rows': tabellen, 'compact_months': _configured_months()})


@bp.route('/api/db/compact', methods=['POST'])
def api_db_compact():
    """Verdichten — ohne `apply=true` nur als Vorschau (nichts wird gelöscht)."""
    if (err := A._require_api()):
        return err
    data = request.get_json(silent=True) or {}
    try:
        months = int(data.get('months') or _configured_months() or 12)
    except (TypeError, ValueError):
        return jsonify({'error': 'bad_months'}), 400
    if months < COMPACT_MIN_MONTHS:
        return jsonify({'error': 'too_small', 'min_months': COMPACT_MIN_MONTHS}), 400
    apply = bool(data.get('apply'))
    with A.db() as con:
        res = compact_history(con, months, dry_run=not apply)
    if apply:
        # Beide Werte haengen an Zeilen, die gerade verschwunden sein koennen.
        with A.db() as con:
            A._recalc_last_move_ts(con)
        A._stats_cache_drop()
        A.log.info("Verlauf verdichtet (manuell): %d Zeilen entfernt", res['total'])
    return jsonify(res)


@bp.route('/api/db/vacuum', methods=['POST'])
def api_db_vacuum():
    """Speicherplatz zurückgeben. Dauert bei großen Dateien einen Moment und
    braucht währenddessen kurz den doppelten Platz — deshalb nur auf Knopfdruck,
    nie automatisch."""
    if (err := A._require_api()):
        return err
    try:
        return jsonify(vacuum())
    except sqlite3.Error as e:
        A.log.warning("VACUUM fehlgeschlagen: %s", type(e).__name__)
        return jsonify({'error': 'vacuum_failed'}), 500
