#!/usr/bin/env python3
"""Lokales Alarm-Archiv — SQLite unter /data.

CrowdSec räumt seine Datenbank nach einigen Wochen auf; was dort verschwindet,
ist über die LAPI nicht mehr zu holen. Dieses Archiv schreibt jede Erkennung
einmal mit und beantwortet danach alle Fragen nach der Vergangenheit selbst:
Verlauf, Karte, Alarmliste, Historie einer Adresse. Der aktuelle Zustand —
aktive Sperren, Bouncer, Metriken — kommt weiterhin live aus der LAPI, denn
dort gehört er hin.

Vollständig aufgenommen werden nur Erkennungen. Eine
Blocklisten-Synchronisierung ist ein einzelner Alarm mit fünfstelliger
Entscheidungszahl ohne Ortsbezug — von ihr bleiben nur Kennung und Zeitpunkt,
genug für den zweiten Balken im Verlauf. Alles andere an ihr wäre ein Datensatz
ohne Aussage und in der Summe der Grund, warum die Datei wächst.
"""

import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1

# Ein Datensatz ist rund 200 Bytes. Die Grenze steht als Zeilenzahl und nicht in
# Megabyte, weil sich danach die Abfragen richten und nicht die Dateigröße.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    id            INTEGER PRIMARY KEY,
    created_at    TEXT    NOT NULL,
    created_ts    INTEGER NOT NULL,
    scenario      TEXT    NOT NULL DEFAULT '',
    message       TEXT    NOT NULL DEFAULT '',
    value         TEXT    NOT NULL DEFAULT '',
    scope         TEXT    NOT NULL DEFAULT '',
    country       TEXT    NOT NULL DEFAULT '',
    as_name       TEXT    NOT NULL DEFAULT '',
    lat           REAL,
    lon           REAL,
    events_count  INTEGER NOT NULL DEFAULT 0,
    decision_count INTEGER NOT NULL DEFAULT 0,
    simulated     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS alerts_ts ON alerts(created_ts);
CREATE INDEX IF NOT EXISTS alerts_value ON alerts(value, created_ts);
CREATE INDEX IF NOT EXISTS alerts_scenario ON alerts(scenario);
-- Von einer Blocklisten-Synchronisierung bleibt nur ihre Kennung und ihr Tag.
-- Das genuegt fuer den zweiten Balken im Verlauf und kostet dreissig Bytes,
-- waehrend der Alarm selbst zehntausende Entscheidungen mitbrächte.
CREATE TABLE IF NOT EXISTS syncs (
    id         INTEGER PRIMARY KEY,
    created_ts INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS syncs_ts ON syncs(created_ts);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def _parse_ts(stamp) -> int | None:
    """Zeitstempel der LAPI in Sekunden seit 1970. Unlesbares gibt None — ein
    Alarm ohne verwertbare Zeit gehört nicht in ein Archiv, das nach Zeit
    sortiert."""
    text = str(stamp or '').strip()
    if not text:
        return None
    text = text.replace('Z', '+00:00').replace('z', '+00:00')
    if 'T' not in text and ' ' in text:
        text = text.replace(' ', 'T', 1)
    # CrowdSec haengt gelegentlich mehr als sechs Nachkommastellen an, damit
    # kommt fromisoformat vor Python 3.11 nicht zurecht.
    if '.' in text:
        head, _, tail = text.partition('.')
        digits = ''
        while tail and tail[0].isdigit():
            digits, tail = digits + tail[0], tail[1:]
        text = head + '.' + (digits[:6] or '0') + tail
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _coord(raw):
    """0/0 schreibt CrowdSec, wenn das GeoIP-Enrichment nichts gefunden hat.
    Dieselbe Lesart wie in der Karte: das ist kein Ort, das ist eine Lücke."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value != value or abs(value) > 180:
        return None
    return value


def row_from_alert(alert: dict) -> tuple | None:
    """Ein LAPI-Alarm als Archivzeile, oder None wenn er nicht taugt."""
    if not isinstance(alert, dict):
        return None
    try:
        ident = int(alert.get('id'))
    except (TypeError, ValueError):
        return None
    stamp = alert.get('created_at') or alert.get('start_at') or ''
    ts = _parse_ts(stamp)
    if ts is None:
        return None
    src = alert.get('source') or {}
    lat, lon = _coord(src.get('latitude')), _coord(src.get('longitude'))
    if lat == 0 and lon == 0:
        lat = lon = None
    return (
        ident,
        str(stamp),
        ts,
        str(alert.get('scenario') or '')[:200],
        str(alert.get('message') or '')[:500],
        str(src.get('value') or src.get('ip') or '')[:64],
        str(src.get('scope') or '')[:32],
        str(src.get('cn') or '')[:8],
        str(src.get('as_name') or '')[:120],
        lat, lon,
        int(alert.get('events_count') or 0),
        len(alert.get('decisions') or []),
        1 if alert.get('simulated') else 0,
    )


_INSERT = """INSERT OR IGNORE INTO alerts
    (id, created_at, created_ts, scenario, message, value, scope, country,
     as_name, lat, lon, events_count, decision_count, simulated)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""

_COLS = ('id', 'created_at', 'scenario', 'message', 'value', 'country',
         'as_name', 'events_count', 'decision_count', 'simulated')


class Archive:
    """Dünne Hülle um eine SQLite-Datei. Jeder Thread bekommt seine eigene
    Verbindung — Flask bedient mehrere gleichzeitig, und der Füll-Thread läuft
    daneben. Geschrieben wird nur an einer Stelle, gelesen überall."""

    def __init__(self, path: str):
        self.path = path
        self._local = threading.local()
        self._write_lock = threading.Lock()
        self._broken = ''

    # -- Verbindung ----------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        con = getattr(self._local, 'con', None)
        if con is not None:
            return con
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        # WAL, damit der Füll-Thread schreiben kann, während die Oberfläche
        # liest. Ohne das sperrt jeder Schreibvorgang die ganze Datei.
        con.execute('PRAGMA journal_mode=WAL')
        con.execute('PRAGMA synchronous=NORMAL')
        con.execute('PRAGMA busy_timeout=10000')
        self._local.con = con
        return con

    def open(self) -> bool:
        """Datei anlegen und Schema sicherstellen. Schlägt das fehl, bleibt das
        Archiv aus und die Endpunkte holen ihre Antworten wie bisher aus der
        LAPI — ein kaputtes Archiv darf die Oberfläche nicht mitnehmen."""
        if self._broken:
            return False
        try:
            folder = os.path.dirname(self.path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            con = self._connect()
            with self._write_lock:
                con.executescript(_SCHEMA)
                con.execute('INSERT OR REPLACE INTO meta VALUES (?,?)',
                            ('schema_version', str(SCHEMA_VERSION)))
                con.commit()
            return True
        except (sqlite3.Error, OSError) as e:
            self._broken = type(e).__name__
            log.warning('alert archive unavailable (%s) — falling back to the LAPI',
                        self._broken)
            return False

    def available(self) -> bool:
        return not self._broken

    # -- Schreiben -----------------------------------------------------------

    def ingest(self, alerts) -> int:
        """Erkennungen aufnehmen. Doppelte fallen über die Alarm-ID weg, das
        Archiv darf also beliebig oft dieselbe Zeitspanne abholen."""
        rows = [r for r in (row_from_alert(a) for a in alerts) if r]
        if not rows:
            return 0
        try:
            con = self._connect()
            with self._write_lock:
                before = con.total_changes
                con.executemany(_INSERT, rows)
                con.commit()
                return con.total_changes - before
        except sqlite3.Error as e:
            log.warning('alert archive write failed: %s', type(e).__name__)
            return 0

    def ingest_syncs(self, alerts) -> int:
        """Blocklisten-Synchronisierungen, nur mit Kennung und Zeitpunkt."""
        rows = []
        for alert in alerts:
            if not isinstance(alert, dict):
                continue
            try:
                ident = int(alert.get('id'))
            except (TypeError, ValueError):
                continue
            ts = _parse_ts(alert.get('created_at') or alert.get('start_at') or '')
            if ts is not None:
                rows.append((ident, ts))
        if not rows:
            return 0
        try:
            con = self._connect()
            with self._write_lock:
                before = con.total_changes
                con.executemany('INSERT OR IGNORE INTO syncs VALUES (?,?)', rows)
                con.commit()
                return con.total_changes - before
        except sqlite3.Error:
            return 0

    def prune(self, days: int) -> int:
        """Alles älter als ``days`` Tage entfernen. ``0`` heißt: nichts wegwerfen."""
        if days <= 0:
            return 0
        cutoff = int(time.time()) - days * 86400
        try:
            con = self._connect()
            with self._write_lock:
                cur = con.execute('DELETE FROM alerts WHERE created_ts < ?', (cutoff,))
                gone = cur.rowcount or 0
                con.execute('DELETE FROM syncs WHERE created_ts < ?', (cutoff,))
                con.commit()
                return gone
        except sqlite3.Error as e:
            log.warning('alert archive prune failed: %s', type(e).__name__)
            return 0

    def set_meta(self, key: str, value: str) -> None:
        try:
            con = self._connect()
            with self._write_lock:
                con.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (key, str(value)))
                con.commit()
        except sqlite3.Error:
            pass

    def get_meta(self, key: str) -> str:
        try:
            row = self._connect().execute(
                'SELECT value FROM meta WHERE key = ?', (key,)).fetchone()
        except sqlite3.Error:
            return ''
        return row['value'] if row else ''

    # -- Lesen ---------------------------------------------------------------

    def newest_ts(self) -> int:
        try:
            row = self._connect().execute(
                'SELECT MAX(created_ts) AS t FROM alerts').fetchone()
        except sqlite3.Error:
            return 0
        return int(row['t'] or 0)

    def stats(self) -> dict:
        """Was im Archiv steht — Grundlage für die Anzeige in den Einstellungen."""
        out = {'available': self.available(), 'rows': 0, 'syncs': 0, 'oldest': '',
               'newest': '', 'bytes': 0, 'last_sync': self.get_meta('last_sync')}
        if not self.available():
            return out
        try:
            row = self._connect().execute(
                'SELECT COUNT(*) AS n, MIN(created_ts) AS lo, MAX(created_ts) AS hi '
                'FROM alerts').fetchone()
            out['syncs'] = int(self._connect().execute(
                'SELECT COUNT(*) AS n FROM syncs').fetchone()['n'] or 0)
            out['rows'] = int(row['n'] or 0)
            for key, ts in (('oldest', row['lo']), ('newest', row['hi'])):
                if ts:
                    out[key] = datetime.fromtimestamp(int(ts), timezone.utc).isoformat()
        except sqlite3.Error:
            return out
        # Die WAL-Datei zählt mit, sonst sieht ein frisch gefülltes Archiv
        # kleiner aus, als es auf der Platte ist.
        for suffix in ('', '-wal'):
            try:
                out['bytes'] += os.path.getsize(self.path + suffix)
            except OSError:
                pass
        return out

    def history(self, days: int) -> tuple:
        """Erkennungen und Listenabgleiche je Tag. Der Schlüssel ist das Datum
        in UTC, damit er zu dem passt, was die Alarmliste anzeigt."""
        cutoff = int(time.time()) - days * 86400
        out = []
        for table in ('alerts', 'syncs'):
            try:
                rows = self._connect().execute(
                    "SELECT strftime('%Y-%m-%d', created_ts, 'unixepoch') AS day, "
                    'COUNT(*) AS n FROM ' + table + ' WHERE created_ts >= ? '
                    'GROUP BY day', (cutoff,)).fetchall()
            except sqlite3.Error:
                rows = []
            out.append({r['day']: int(r['n']) for r in rows})
        return out[0], out[1]

    def points(self, since_ts: int, limit: int) -> tuple:
        """Adressen mit Koordinaten, nach Zahl der Erkennungen. Gibt die Liste
        und die Gesamtzahl verorteter Adressen zurück, damit der Aufrufer
        „gekürzt" ehrlich beantworten kann."""
        try:
            con = self._connect()
            total = con.execute(
                'SELECT COUNT(DISTINCT value) AS n FROM alerts '
                'WHERE created_ts >= ? AND lat IS NOT NULL', (since_ts,)).fetchone()
            rows = con.execute(
                'SELECT value, COUNT(*) AS n, MAX(created_ts) AS last, '
                '       AVG(lat) AS lat, AVG(lon) AS lon, '
                '       MAX(country) AS country, MAX(as_name) AS as_name '
                'FROM alerts WHERE created_ts >= ? AND lat IS NOT NULL '
                'GROUP BY value ORDER BY n DESC, value LIMIT ?',
                (since_ts, limit)).fetchall()
        except sqlite3.Error:
            return [], 0
        out = []
        for r in rows:
            out.append({'value': r['value'], 'lat': round(r['lat'], 3),
                        'lon': round(r['lon'], 3), 'country': r['country'] or '',
                        'as_name': r['as_name'] or '', 'count': int(r['n']),
                        'scenario': self._top_scenario(r['value'], since_ts)})
        return out, int(total['n'] or 0)

    def _top_scenario(self, value: str, since_ts: int) -> str:
        try:
            row = self._connect().execute(
                'SELECT scenario, COUNT(*) AS n FROM alerts '
                'WHERE value = ? AND created_ts >= ? AND scenario <> "" '
                'GROUP BY scenario ORDER BY n DESC LIMIT 1',
                (value, since_ts)).fetchone()
        except sqlite3.Error:
            return ''
        return row['scenario'] if row else ''

    def count_since(self, since_ts: int) -> int:
        try:
            row = self._connect().execute(
                'SELECT COUNT(*) AS n FROM alerts WHERE created_ts >= ?',
                (since_ts,)).fetchone()
        except sqlite3.Error:
            return 0
        return int(row['n'] or 0)

    def search(self, since_ts: int = 0, needle: str = '', value: str = '',
               scenario: str = '', simulated=None, limit: int = 5000) -> list:
        """Alarme als Wörterbücher, neueste zuerst.

        Der Freitext läuft über dieselben Felder wie die Suche auf der
        LAPI-Seite. LIKE bekommt seine Sonderzeichen maskiert, sonst würde ein
        eingegebenes ``%`` alles finden."""
        where = ['created_ts >= ?']
        args: list = [int(since_ts)]
        if value:
            where.append('value = ?')
            args.append(value)
        if scenario:
            where.append('scenario = ?')
            args.append(scenario)
        if simulated is not None:
            where.append('simulated = ?')
            args.append(1 if simulated else 0)
        if needle:
            pattern = '%' + needle.lower().replace('\\', '\\\\') \
                                          .replace('%', '\\%').replace('_', '\\_') + '%'
            where.append("(LOWER(value) LIKE ? ESCAPE '\\' OR "
                         "LOWER(scenario) LIKE ? ESCAPE '\\' OR "
                         "LOWER(country) LIKE ? ESCAPE '\\' OR "
                         "LOWER(as_name) LIKE ? ESCAPE '\\')")
            args.extend([pattern] * 4)
        args.append(max(1, int(limit)))
        sql = ('SELECT ' + ', '.join(_COLS) + ' FROM alerts WHERE '
               + ' AND '.join(where) + ' ORDER BY created_ts DESC, id DESC LIMIT ?')
        try:
            rows = self._connect().execute(sql, args).fetchall()
        except sqlite3.Error as e:
            log.warning('alert archive read failed: %s', type(e).__name__)
            return []
        return [dict(r) for r in rows]

    def close(self) -> None:
        con = getattr(self._local, 'con', None)
        if con is not None:
            try:
                con.close()
            except sqlite3.Error:
                pass
            self._local.con = None
