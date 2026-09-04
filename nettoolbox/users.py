"""Benutzerkonten für die Anmeldung außerhalb von Home Assistant.

Bis 0.1.43 gab es genau ein Konto: Benutzername und Kennwort aus den Add-on-
Optionen. Das reicht, solange nur der Betreiber selbst prüft, und hört genau
dann auf zu reichen, wenn jemand anderes mitbenutzen soll -- ohne die
Einstellungen zu sehen, ohne unbegrenzt fremde Server abzufragen und ohne dass
sich zwei Leute ein Kennwort teilen.

Das Konto aus den Optionen bleibt bestehen und ist immer Administrator. Es ist
der Weg zurück, wenn hier alles verriegelt ist: die Add-on-Optionen kann nur
ändern, wer ohnehin schon Home Assistant bedient. Die Konten dieser Datei
kommen zusätzlich dazu.

Kennwörter liegen als werkzeug-Hash (scrypt) in der Datenbank, nie im Klartext.
Das Startkennwort erfährt der Betreiber genau einmal -- beim Anlegen, per Mail
an den neuen Benutzer und, falls kein SMTP eingerichtet ist, in der Antwort an
die Oberfläche.
"""

import os
import re
import secrets
import sqlite3
import threading
import time

from werkzeug.security import check_password_hash, generate_password_hash

# Der Betreiber ist als Konto nicht in dieser Datenbank -- er kommt aus den
# Add-on-Optionen und trägt deshalb eine ID, die SQLite nie vergibt.
OPTIONS_ADMIN_ID = 0

USERNAME_SHAPE = re.compile(r'^[A-Za-z0-9._-]{3,32}$')
# Absichtlich grob: eine Adresse endgültig zu prüfen kann nur der Mailversand
# selbst. Hier geht es darum, offensichtlichen Unsinn und Kopfzeilen-
# Schmuggel (Zeilenumbrüche, Kommas) abzuweisen.
EMAIL_SHAPE = re.compile(r'^[^@\s,;:<>"]{1,64}@[A-Za-z0-9.-]{1,180}\.[A-Za-z]{2,24}$')

PASSWORD_MIN = 10
PASSWORD_MAX = 200

# Ohne 0/O und 1/l/I: das Startkennwort wird abgetippt oder vorgelesen.
_ALPHABET = 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
INITIAL_LENGTH = 14

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL COLLATE NOCASE UNIQUE,
    email         TEXT    NOT NULL DEFAULT '',
    pw_hash       TEXT    NOT NULL,
    is_admin      INTEGER NOT NULL DEFAULT 0,
    blocked       INTEGER NOT NULL DEFAULT 0,
    must_change   INTEGER NOT NULL DEFAULT 1,
    modules       TEXT    NOT NULL DEFAULT '*',
    daily_quota   INTEGER NOT NULL DEFAULT 0,
    created_ts    INTEGER NOT NULL,
    last_login_ts INTEGER NOT NULL DEFAULT 0,
    note          TEXT    NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS usage (
    uid  INTEGER NOT NULL,
    day  TEXT    NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (uid, day)
);
CREATE TABLE IF NOT EXISTS activity (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    uid    INTEGER NOT NULL,
    ts     INTEGER NOT NULL,
    probe  TEXT    NOT NULL,
    target TEXT    NOT NULL DEFAULT '',
    level  TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_activity_uid ON activity(uid, ts DESC);
"""

# Wie viele Zeilen je Konto aufgehoben werden. Das Protokoll beantwortet die
# Frage "was hat wer geprüft", nicht "was war 2024" -- unbegrenztes Wachstum
# in einer Add-on-Datenbank wäre nur eine Zeitbombe.
ACTIVITY_PER_USER = 500


class UserError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def new_password() -> str:
    return ''.join(secrets.choice(_ALPHABET) for _ in range(INITIAL_LENGTH))


def check_password_rules(password: str, username: str = '') -> None:
    """Wenige, dafür ernst gemeinte Regeln. Zeichenklassen-Zwang erzeugt
    erfahrungsgemäß "Passwort1!" und nicht mehr Sicherheit -- Länge tut das."""
    password = password or ''
    if len(password) < PASSWORD_MIN or len(password) > PASSWORD_MAX:
        raise UserError('weak_password')
    if username and password.lower() == username.lower():
        raise UserError('weak_password')


def clean_username(raw) -> str:
    name = str(raw or '').strip()
    if not USERNAME_SHAPE.match(name):
        raise UserError('bad_username')
    return name


def clean_email(raw) -> str:
    """Leer ist erlaubt: dann gibt es keine Willkommensmail und der Betreiber
    gibt das Startkennwort selbst weiter."""
    mail = str(raw or '').strip()
    if not mail:
        return ''
    if len(mail) > 254 or not EMAIL_SHAPE.match(mail):
        raise UserError('bad_email')
    return mail


class UserStore:
    """Wie MonitorStore und SnapshotStore: eine Verbindung je Thread,
    Schreibzugriffe unter einem Schloss, ein kaputter Speicher legt die
    Anwendung nicht lahm -- dann bleibt eben nur das Konto aus den Optionen."""

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

    def available(self) -> bool:
        return not self._broken

    # ── Lesen ────────────────────────────────────────────────────────────────

    @staticmethod
    def _view(row) -> dict:
        """Was die Oberfläche zu sehen bekommt -- ohne Hash."""
        return {'id': row['id'], 'username': row['username'],
                'email': row['email'], 'is_admin': bool(row['is_admin']),
                'blocked': bool(row['blocked']),
                'must_change': bool(row['must_change']),
                'modules': row['modules'], 'daily_quota': row['daily_quota'],
                'created_ts': row['created_ts'],
                'last_login_ts': row['last_login_ts'], 'note': row['note']}

    def list(self) -> list:
        rows = self._connect().execute(
            'SELECT * FROM users ORDER BY username COLLATE NOCASE').fetchall()
        return [self._view(row) for row in rows]

    def get(self, user_id: int) -> dict:
        row = self._connect().execute(
            'SELECT * FROM users WHERE id = ?', (int(user_id),)).fetchone()
        if row is None:
            raise UserError('user_not_found')
        return self._view(row)

    def by_name(self, username: str):
        return self._connect().execute(
            'SELECT * FROM users WHERE username = ? COLLATE NOCASE',
            (str(username or ''),)).fetchone()

    def verify(self, username: str, password: str):
        """Gibt den Benutzer zurück, wenn das Kennwort stimmt, sonst None.

        Auch ein unbekannter Name kostet einen Hash-Durchlauf: sonst verrät
        die Antwortzeit, welche Namen es gibt.
        """
        try:
            row = self.by_name(username)
        except sqlite3.Error as e:
            # Ein kaputter Speicher darf nicht als "Kennwort stimmt" enden.
            self._broken = type(e).__name__
            return None
        stored = row['pw_hash'] if row is not None else generate_password_hash(
            'nettoolbox-dummy')
        ok = check_password_hash(stored, str(password or ''))
        if row is None or not ok or row['blocked']:
            return None
        return self._view(row)

    # ── Schreiben ────────────────────────────────────────────────────────────

    def create(self, username: str, email: str, is_admin: bool,
               note: str = '') -> tuple:
        """Legt das Konto mit einem erzeugten Startkennwort an. Gibt
        (Benutzer, Startkennwort) zurück -- das Kennwort ist danach nirgends
        mehr abrufbar."""
        username = clean_username(username)
        email = clean_email(email)
        password = new_password()
        with self._write_lock:
            con = self._connect()
            if self.by_name(username) is not None:
                raise UserError('user_exists')
            try:
                cur = con.execute(
                    'INSERT INTO users (username, email, pw_hash, is_admin,'
                    ' must_change, created_ts, note)'
                    ' VALUES (?, ?, ?, ?, 1, ?, ?)',
                    (username, email, generate_password_hash(password),
                     1 if is_admin else 0, int(time.time()),
                     str(note or '')[:200]))
            except sqlite3.IntegrityError:
                raise UserError('user_exists')
            con.commit()
            new_id = cur.lastrowid
        return self.get(new_id), password

    def update(self, user_id: int, fields: dict) -> dict:
        """Ändert Stammdaten. Das Kennwort läuft nie hier durch."""
        user = self.get(user_id)
        sets, values = [], []
        if 'email' in fields:
            sets.append('email = ?')
            values.append(clean_email(fields['email']))
        if 'note' in fields:
            sets.append('note = ?')
            values.append(str(fields['note'] or '')[:200])
        # Kein "letzter Betreiber"-Schutz: das Konto aus den Add-on-Optionen
        # ist immer vorhanden und immer Betreiber, ausgesperrt werden kann
        # sich hier also niemand.
        if 'blocked' in fields:
            sets.append('blocked = ?')
            values.append(1 if fields['blocked'] else 0)
        if 'is_admin' in fields:
            sets.append('is_admin = ?')
            values.append(1 if fields['is_admin'] else 0)
        if 'modules' in fields:
            sets.append('modules = ?')
            values.append(str(fields['modules'] or '*')[:2000])
        if 'daily_quota' in fields:
            try:
                quota = max(0, min(10000, int(fields['daily_quota'])))
            except (TypeError, ValueError):
                raise UserError('bad_quota')
            sets.append('daily_quota = ?')
            values.append(quota)
        if not sets:
            return user
        # Die Feldnamen stammen ausschließlich aus den Literalen oben, nie aus
        # der Anfrage; eingesetzt werden nur Platzhalter.
        with self._write_lock:
            con = self._connect()
            con.execute('UPDATE users SET ' + ', '.join(sets) + ' WHERE id = ?',
                        tuple(values) + (int(user_id),))
            con.commit()
        return self.get(user_id)

    def set_password(self, user_id: int, password: str,
                     must_change: bool = False) -> None:
        user = self.get(user_id)
        check_password_rules(password, user['username'])
        with self._write_lock:
            con = self._connect()
            con.execute(
                'UPDATE users SET pw_hash = ?, must_change = ? WHERE id = ?',
                (generate_password_hash(password),
                 1 if must_change else 0, int(user_id)))
            con.commit()

    def reset_password(self, user_id: int) -> tuple:
        """Neues Startkennwort, das beim nächsten Anmelden gewechselt werden
        muss. Gibt (Benutzer, Kennwort) zurück."""
        user = self.get(user_id)
        password = new_password()
        with self._write_lock:
            con = self._connect()
            con.execute(
                'UPDATE users SET pw_hash = ?, must_change = 1 WHERE id = ?',
                (generate_password_hash(password), int(user_id)))
            con.commit()
        return user, password

    def delete(self, user_id: int) -> dict:
        user = self.get(user_id)
        with self._write_lock:
            con = self._connect()
            con.execute('DELETE FROM users WHERE id = ?', (int(user_id),))
            # Verbrauch und Protokoll gehen mit -- von einem gelöschten Konto
            # bleibt sonst eine Spur zurück, die niemand mehr zuordnen kann.
            con.execute('DELETE FROM usage WHERE uid = ?', (int(user_id),))
            con.execute('DELETE FROM activity WHERE uid = ?', (int(user_id),))
            con.commit()
        return user

    # ── Tageskontingent ──────────────────────────────────────────────────────

    def usage_today(self, user_id: int, day: str) -> int:
        try:
            row = self._connect().execute(
                'SELECT used FROM usage WHERE uid = ? AND day = ?',
                (int(user_id), str(day))).fetchone()
        except sqlite3.Error:
            return 0
        return int(row['used']) if row else 0

    def spend(self, user_id: int, day: str, limit: int) -> bool:
        """Eine Abfrage abbuchen. False = Kontingent aufgebraucht.

        Zählen und Prüfen stecken bewusst in einer Anweisung unter dem
        Schreibschloss: zwei gleichzeitige Prüfungen dürfen sich nicht beide
        die letzte freie Abfrage nehmen.
        """
        if limit <= 0:
            return True
        with self._write_lock:
            try:
                con = self._connect()
                cur = con.execute(
                    'INSERT INTO usage (uid, day, used) VALUES (?, ?, 1)'
                    ' ON CONFLICT(uid, day) DO UPDATE SET used = used + 1'
                    ' WHERE used < ?', (int(user_id), str(day), int(limit)))
                con.commit()
            except sqlite3.Error:
                # Lieber durchlassen als den Dienst verweigern: das Kontingent
                # ist eine Bremse, keine Sicherheitsgrenze.
                return True
        return cur.rowcount > 0

    def forget_day(self, user_id: int, day: str) -> None:
        """Kontingent eines Kontos für heute zurücksetzen."""
        with self._write_lock:
            con = self._connect()
            con.execute('DELETE FROM usage WHERE uid = ? AND day = ?',
                        (int(user_id), str(day)))
            con.commit()

    # ── Protokoll ────────────────────────────────────────────────────────────

    def log_activity(self, user_id: int, probe: str, target: str,
                     level: str) -> None:
        """Wer hat was geprüft. Fehlschläge sind kein Grund, die Prüfung
        selbst scheitern zu lassen."""
        try:
            with self._write_lock:
                con = self._connect()
                con.execute(
                    'INSERT INTO activity (uid, ts, probe, target, level)'
                    ' VALUES (?, ?, ?, ?, ?)',
                    (int(user_id), int(time.time()), str(probe)[:40],
                     str(target or '')[:253], str(level or '')[:16]))
                con.execute(
                    'DELETE FROM activity WHERE uid = ? AND id NOT IN ('
                    ' SELECT id FROM activity WHERE uid = ?'
                    ' ORDER BY ts DESC, id DESC LIMIT ?)',
                    (int(user_id), int(user_id), ACTIVITY_PER_USER))
                con.commit()
        except sqlite3.Error:
            pass

    def activity(self, user_id: int, limit: int = 200) -> list:
        rows = self._connect().execute(
            'SELECT ts, probe, target, level FROM activity WHERE uid = ?'
            ' ORDER BY ts DESC, id DESC LIMIT ?',
            (int(user_id), max(1, min(1000, int(limit))))).fetchall()
        return [{'ts': r['ts'], 'probe': r['probe'], 'target': r['target'],
                 'level': r['level']} for r in rows]

    def forget_user(self, user_id: int) -> None:
        """Verbrauch und Protokoll eines Kontos entfernen -- gehört zum
        Löschen, sonst bliebe von einem gelöschten Konto eine Spur zurück."""
        with self._write_lock:
            con = self._connect()
            con.execute('DELETE FROM usage WHERE uid = ?', (int(user_id),))
            con.execute('DELETE FROM activity WHERE uid = ?', (int(user_id),))
            con.commit()

    def touch_login(self, user_id: int) -> None:
        try:
            with self._write_lock:
                con = self._connect()
                con.execute('UPDATE users SET last_login_ts = ? WHERE id = ?',
                            (int(time.time()), int(user_id)))
                con.commit()
        except sqlite3.Error:
            pass  # eine verpasste Zeitangabe ist kein Grund, die Anmeldung zu verweigern
