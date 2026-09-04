"""DNS-Momentaufnahmen und deren Vergleich.

Der Sinn ist nicht, DNS noch einmal abzufragen -- das kann der DNS-Reiter
laengst --, sondern die Frage zu beantworten: *was hat sich seit letzter
Woche geaendert?* Bei einem Umzug, nach einem Eingriff des Providers oder
wenn eine Mail-Zustellung ploetzlich scheitert, ist genau das die Frage, auf
die man sonst keine Antwort hat, weil niemand den vorherigen Stand notiert
hat.

Gespeichert wird als eine Zeile pro Aufnahme mit den Datensaetzen als JSON --
Zonen sind klein, und ein eigenes Tabellenschema pro Record-Typ waere
Aufwand ohne Gewinn.
"""

import json
import os
import sqlite3
import threading
import time

# Apex plus die zwei Namen, an denen sich in der Praxis am haeufigsten etwas
# unbemerkt aendert: www (Umzug) und _dmarc (Mail-Richtlinie).
APEX_TYPES = ('A', 'AAAA', 'MX', 'NS', 'TXT', 'SOA', 'CAA', 'DS')
EXTRA_NAMES = (
    ('www', ('A', 'AAAA', 'CNAME')),
    ('_dmarc', ('TXT',)),
)

MAX_PER_DOMAIN = 30
MAX_TOTAL = 500

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    domain  TEXT    NOT NULL,
    ts      INTEGER NOT NULL,
    label   TEXT    NOT NULL DEFAULT '',
    data    TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_domain ON snapshots(domain, ts DESC);
"""


class SnapshotError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class SnapshotStore:
    """Wie MonitorStore: eine Verbindung pro Thread, Schreibzugriffe unter
    einem Schloss, ein kaputter Speicher legt die Anwendung nicht lahm."""

    def __init__(self, path: str):
        self.path = path
        self._local = threading.local()
        self._write_lock = threading.Lock()
        self._broken = ''

    def _connect(self) -> sqlite3.Connection:
        con = getattr(self._local, 'con', None)
        if con is not None:
            return con
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA journal_mode=WAL')
        con.execute('PRAGMA synchronous=NORMAL')
        con.execute('PRAGMA busy_timeout=10000')
        self._local.con = con
        return con

    def open(self) -> bool:
        try:
            folder = os.path.dirname(self.path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            with self._write_lock:
                self._connect().executescript(_SCHEMA)
            return True
        except (sqlite3.Error, OSError) as e:
            self._broken = type(e).__name__
            return False

    @property
    def broken(self) -> str:
        return self._broken

    def add(self, domain: str, records: list, label: str = '') -> dict:
        with self._write_lock:
            con = self._connect()
            cur = con.execute(
                'INSERT INTO snapshots (domain, ts, label, data)'
                ' VALUES (?, ?, ?, ?)',
                (domain, int(time.time()), label[:80], json.dumps(records)))
            new_id = cur.lastrowid
            # Aufraeumen sofort statt per Wartungsjob: die Grenze ist klein
            # genug, dass das nichts kostet.
            con.execute(
                'DELETE FROM snapshots WHERE domain = ? AND id NOT IN ('
                ' SELECT id FROM snapshots WHERE domain = ?'
                ' ORDER BY ts DESC LIMIT ?)',
                (domain, domain, MAX_PER_DOMAIN))
            con.execute(
                'DELETE FROM snapshots WHERE id NOT IN ('
                ' SELECT id FROM snapshots ORDER BY ts DESC LIMIT ?)',
                (MAX_TOTAL,))
            con.commit()
        return self.get(new_id)

    def get(self, snapshot_id: int) -> dict:
        row = self._connect().execute(
            'SELECT * FROM snapshots WHERE id = ?', (snapshot_id,)).fetchone()
        if row is None:
            raise SnapshotError('snapshot_not_found')
        return {'id': row['id'], 'domain': row['domain'], 'ts': row['ts'],
                'label': row['label'], 'records': json.loads(row['data'])}

    def list(self, domain: str = '') -> list:
        # Ein fester Abfragetext mit "(? IS NULL OR ...)" statt einer
        # zusammengebauten WHERE-Klausel -- CodeQL beanstandet das Muster
        # selbst dann, wenn nur Platzhalter eingesetzt werden.
        rows = self._connect().execute(
            'SELECT id, domain, ts, label, data FROM snapshots'
            ' WHERE (? = "" OR domain = ?) ORDER BY ts DESC LIMIT 200',
            (domain, domain)).fetchall()
        out = []
        for row in rows:
            records = json.loads(row['data'])
            out.append({'id': row['id'], 'domain': row['domain'],
                        'ts': row['ts'], 'label': row['label'],
                        'entries': len(records),
                        'records_total': sum(len(r['records']) for r in records)})
        return out

    def delete(self, snapshot_id: int) -> None:
        with self._write_lock:
            con = self._connect()
            cur = con.execute('DELETE FROM snapshots WHERE id = ?', (snapshot_id,))
            con.commit()
        if cur.rowcount == 0:
            raise SnapshotError('snapshot_not_found')


# ── Aufnehmen und Vergleichen ────────────────────────────────────────────────


def capture(ctx, domain: str) -> list:
    """[{'name': ..., 'type': ..., 'records': [...], 'ttl': n, 'error': ''}]

    Ein einzelner fehlgeschlagener Typ wird als Zeile mit Fehlercode
    vermerkt, nicht geworfen -- sonst verhindert ein zickiger Resolver die
    ganze Aufnahme.
    """
    from netcore import ProbeError, clean_domain, query

    domain = clean_domain(domain)
    wanted = [(domain, rrtype) for rrtype in APEX_TYPES]
    for prefix, types in EXTRA_NAMES:
        wanted.extend((f'{prefix}.{domain}', rrtype) for rrtype in types)

    out = []
    for name, rrtype in wanted:
        entry = {'name': name, 'type': rrtype, 'records': [], 'ttl': 0,
                 'error': ''}
        try:
            answer = query(ctx, name, rrtype)
            entry['records'] = sorted(answer.records)
            entry['ttl'] = answer.ttl
        except ProbeError as e:
            entry['error'] = e.code
        out.append(entry)
    return out


def _key(entry: dict) -> tuple:
    return (entry['name'], entry['type'])


def compare(before: list, after: list) -> dict:
    """Was ist dazugekommen, was ist weg, was hat sich geaendert.

    Verglichen werden die Datensaetze selbst, nicht die TTL: eine TTL, die
    von 3600 auf 3599 gelaufen ist, ist keine Aenderung, die jemanden
    interessiert.
    """
    old = {_key(e): e for e in before}
    new = {_key(e): e for e in after}
    changes = []
    for key in sorted(set(old) | set(new)):
        old_records = old.get(key, {}).get('records', [])
        new_records = new.get(key, {}).get('records', [])
        if old_records == new_records:
            continue
        changes.append({
            'name': key[0], 'type': key[1],
            'removed': [r for r in old_records if r not in new_records],
            'added': [r for r in new_records if r not in old_records],
            'before': old_records, 'after': new_records,
        })
    return {'changed': changes, 'unchanged': len(set(old) & set(new)) - len(changes),
            'identical': not changes}
