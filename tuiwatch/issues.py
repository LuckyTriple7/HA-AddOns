"""Störungsliste: dauerhafte Leerläufe sammeln, im Kopf melden, gezielt pausieren.

Manche Fehlpfade wiederholen sich täglich, ohne dass je wieder ein Ergebnis kommt:
eine Preisbarometer-Messreihe zu einem Ziel, das gar nicht mehr im Programm ist
(„Suche lieferte keine Treffer"), ein Angebot auf einer toten URL, ein Suchabo mit
kaputter Payload. Jeder dieser Fälle kostet täglich TUI-Aufrufe und landet bisher nur
als WARNING im Log — dort sieht man ihn erst, wenn man danach sucht.

Dieses Modul führt sie in einer Tabelle zusammen (eine Zeile je `kind`+`key`, mit
Serie und Zähler), meldet ihre Zahl über `/api/offers` an den Kopf der Seite und
bietet je Störung genau eine Handlung an: **pausieren**. Was das bedeutet, hängt am
`kind` (siehe `_apply_mute`) — Angebot pausieren, Suchabo abschalten, Messreihe aus
dem Barometer nehmen. Pausierte Störungen bleiben sichtbar (nur ohne Zählung), damit
niemand vergisst, dass da etwas stillgelegt wurde.

Bewusst KEINE Kopie des Log-Puffers (`/api/errors`): der zeigt jede Warnung seit dem
Start, hier stehen nur die wiederkehrenden, abschaltbaren Fälle.
"""
import time

from flask import Blueprint, jsonify, request

import app as A

bp = Blueprint('issues', __name__)

# Ab dieser Serie gilt eine Störung als Fehler (rotes Ausrufezeichen statt gelbem).
# Drei Läufe in Folge ohne Ergebnis sind kein Ausreißer mehr — dieselbe Schwelle
# nutzt der Ausverkauft-Alarm für Angebote (A.ERROR_ALARM_STREAK).
ISSUE_ERROR_STREAK = 3

# Was „pausieren" je Störungsart heißt — auch die Beschriftung im UI kommt daher.
KINDS = {
    'basket': 'Messreihe',
    'offer': 'Angebot',
    'search': 'Suchabo',
}


def init_issues_db(con) -> None:
    """Tabelle anlegen — wird aus `app.init_db` aufgerufen."""
    con.execute('''CREATE TABLE IF NOT EXISTS issues (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        kind     TEXT NOT NULL,
        key      TEXT NOT NULL,
        title    TEXT NOT NULL DEFAULT '',
        detail   TEXT NOT NULL DEFAULT '',
        streak   INTEGER NOT NULL DEFAULT 0,
        total    INTEGER NOT NULL DEFAULT 0,
        first_ts INTEGER NOT NULL,
        last_ts  INTEGER NOT NULL,
        muted    INTEGER NOT NULL DEFAULT 0
    )''')
    con.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_issues_key ON issues(kind, key)')


# ── Melden / Entwarnen ─────────────────────────────────────────────────────────

def report(kind: str, key, title: str, detail: str = '') -> None:
    """Einen Leerlauf melden. Erste Meldung legt die Zeile an, jede weitere zählt
    Serie und Gesamtzahl hoch. Ein bestehendes `muted` bleibt unangetastet — sonst
    würde eine pausierte Störung sich beim nächsten Lauf selbst reaktivieren.

    Absichtlich fehlertolerant: das ist Diagnose-Beiwerk, ein Schreibfehler darf
    weder den Poller noch das Preisbarometer abbrechen."""
    key = str(key)
    now = int(time.time())
    try:
        with A.db() as con:
            row = con.execute('SELECT id FROM issues WHERE kind=? AND key=?',
                              (kind, key)).fetchone()
            if row:
                con.execute('UPDATE issues SET title=?, detail=?, streak=streak+1, '
                            'total=total+1, last_ts=? WHERE id=?',
                            (title, detail, now, row['id']))
            else:
                con.execute('INSERT INTO issues (kind, key, title, detail, streak, total, '
                            'first_ts, last_ts, muted) VALUES (?,?,?,?,1,1,?,?,0)',
                            (kind, key, title, detail, now, now))
    except Exception as e:
        A.log.debug("Störung „%s/%s“ nicht gespeichert: %s: %s", kind, key, type(e).__name__, e)


def clear(kind: str, key) -> None:
    """Entwarnung: die Störung ist von selbst weg (wieder Treffer, wieder ein Preis).
    Die Zeile fällt komplett raus — samt eines gesetzten `muted`, denn wenn wieder
    etwas geliefert wird, war die Pause offensichtlich nicht (mehr) nötig."""
    try:
        with A.db() as con:
            con.execute('DELETE FROM issues WHERE kind=? AND key=?', (kind, str(key)))
    except Exception as e:
        A.log.debug("Störung „%s/%s“ nicht gelöscht: %s: %s", kind, key, type(e).__name__, e)


def muted_keys(kind: str) -> set:
    """Pausierte Schlüssel einer Art — für Aufrufer, die den Leerlauf selbst
    verhindern müssen (das Preisbarometer lässt pausierte Messreihen ganz aus)."""
    try:
        with A.db() as con:
            return {r['key'] for r in con.execute(
                'SELECT key FROM issues WHERE kind=? AND muted=1', (kind,)).fetchall()}
    except Exception:
        return set()


def drop_missing(kind: str, keys) -> None:
    """Störungen aufräumen, deren Bezugsobjekt es nicht mehr gibt (gelöschte Suche,
    entferntes Angebot). Ohne das bliebe eine Messreihe ewig als Störung stehen,
    obwohl sie längst niemand mehr abfragt."""
    keep = {str(k) for k in keys}
    try:
        with A.db() as con:
            rows = con.execute('SELECT id, key FROM issues WHERE kind=?', (kind,)).fetchall()
            for r in rows:
                if r['key'] not in keep:
                    con.execute('DELETE FROM issues WHERE id=?', (r['id'],))
    except Exception as e:
        A.log.debug("Störungen der Art „%s“ nicht aufgeräumt: %s: %s",
                    kind, type(e).__name__, e)


def summary() -> dict:
    """Kurzfassung für den Kopf der Seite: Anzahl der nicht pausierten Störungen und
    die höchste Dringlichkeit darunter (`warn` gelb, `error` rot)."""
    try:
        with A.db() as con:
            rows = con.execute('SELECT streak FROM issues WHERE muted=0').fetchall()
    except Exception:
        return {'n': 0, 'severity': None}
    if not rows:
        return {'n': 0, 'severity': None}
    sev = 'error' if any(r['streak'] >= ISSUE_ERROR_STREAK for r in rows) else 'warn'
    return {'n': len(rows), 'severity': sev}


# ── Pausieren ──────────────────────────────────────────────────────────────────

def _apply_mute(kind: str, key: str, on: bool) -> None:
    """Die eigentliche Wirkung des Pausierens — je Art etwas anderes.

    `basket` braucht hier nichts: `market_basket._basket_targets` fragt `muted_keys`
    selbst ab und lässt die Messreihe dann aus. Bei `offer` und `search` gibt es
    dagegen bereits einen Schalter am Objekt, der genau das tut."""
    if kind == 'offer':
        with A.db() as con:
            con.execute('UPDATE offers SET paused=? WHERE id=?', (1 if on else 0, int(key)))
    elif kind == 'search':
        with A.db() as con:
            con.execute('UPDATE saved_searches SET watch=? WHERE id=?',
                        (0 if on else 1, int(key)))


# ── Routen ─────────────────────────────────────────────────────────────────────

def _row(r) -> dict:
    d = dict(r)
    d['kind_label'] = KINDS.get(d['kind'], d['kind'])
    d['severity'] = 'error' if d['streak'] >= ISSUE_ERROR_STREAK else 'warn'
    return d


@bp.route('/api/issues', methods=['GET'])
def api_issues():
    """Alle Störungen, dringendste zuerst, pausierte ans Ende."""
    if (err := A._require_api()):
        return err
    with A.db() as con:
        rows = con.execute('SELECT * FROM issues ORDER BY muted, streak DESC, '
                           'last_ts DESC').fetchall()
    return jsonify({'items': [_row(r) for r in rows], 'summary': summary()})


@bp.route('/api/issues/<int:iid>/mute', methods=['POST'])
def api_issue_mute(iid: int):
    """Störung pausieren (`{"on": true}`) oder wieder aktivieren (`{"on": false}`).
    Setzt zusätzlich den passenden Schalter am Bezugsobjekt, siehe `_apply_mute`."""
    if (err := A._require_api()):
        return err
    on = bool((request.get_json(silent=True) or {}).get('on', True))
    with A.db() as con:
        row = con.execute('SELECT * FROM issues WHERE id=?', (iid,)).fetchone()
    if not row:
        return jsonify({'error': 'nicht gefunden'}), 404
    try:
        _apply_mute(row['kind'], row['key'], on)
    except Exception as e:
        A.log.warning("Störung #%d konnte nicht %s werden: %s: %s", iid,
                      'pausiert' if on else 'reaktiviert', type(e).__name__, e)
        return jsonify({'error': 'Aktion fehlgeschlagen'}), 500
    with A.db() as con:
        # Beim Reaktivieren die Serie zurücksetzen: sonst stünde die Störung sofort
        # wieder rot da, obwohl der nächste Lauf noch gar nicht stattgefunden hat.
        con.execute('UPDATE issues SET muted=?, streak=CASE WHEN ?=1 THEN streak ELSE 0 END '
                    'WHERE id=?', (1 if on else 0, 1 if on else 0, iid))
    A.log.info("Störung „%s/%s“ %s", row['kind'], row['key'],
               'pausiert' if on else 'wieder aktiviert')
    return jsonify({'ok': True, 'muted': on})


@bp.route('/api/issues/<int:iid>', methods=['DELETE'])
def api_issue_delete(iid: int):
    """Störung ausblenden. Nur den Eintrag — am Bezugsobjekt ändert sich nichts;
    tritt der Leerlauf wieder auf, erscheint die Störung erneut."""
    if (err := A._require_api()):
        return err
    with A.db() as con:
        con.execute('DELETE FROM issues WHERE id=?', (iid,))
    return jsonify({'ok': True})
