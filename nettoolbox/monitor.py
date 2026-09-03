"""Scheduled monitoring: re-run a probe against a target on its own interval,
keep a history, and notify by email and/or Telegram on a state change.

SQLite under /data, same shape as crowdpanel's alert archive: every thread
gets its own connection (Flask serves several requests at once, the worker
runs alongside them), WAL so a write does not lock out the readers, one write
lock so two threads never commit at once.
"""

import logging
import smtplib
import socket
import sqlite3
import threading
import time
from email.mime.text import MIMEText

import requests

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1

# Which probe a monitor can run, and which parameter key that probe expects
# its target under (probes.py's own registry uses different key names per
# probe — 'target' for tls, 'ip' for blacklist, 'domain' for mail_health).
MONITOR_PROBES = {
    'tls': 'target',
    'blacklist': 'ip',
    'mail_health': 'domain',
}

HISTORY_KEEP = 200  # rows per monitor

_SCHEMA = """
CREATE TABLE IF NOT EXISTS monitors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    probe           TEXT    NOT NULL,
    target          TEXT    NOT NULL,
    interval_hours  INTEGER NOT NULL DEFAULT 6,
    enabled         INTEGER NOT NULL DEFAULT 1,
    notify_email    INTEGER NOT NULL DEFAULT 1,
    notify_telegram INTEGER NOT NULL DEFAULT 1,
    created_ts      INTEGER NOT NULL,
    last_run_ts     INTEGER,
    last_level      TEXT    NOT NULL DEFAULT '',
    last_summary    TEXT    NOT NULL DEFAULT '',
    last_error      TEXT    NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS monitor_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    monitor_id INTEGER NOT NULL,
    ts         INTEGER NOT NULL,
    level      TEXT    NOT NULL,
    summary    TEXT    NOT NULL DEFAULT '',
    notified   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS monitor_history_mid ON monitor_history(monitor_id, ts);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

_LEVEL_RANK = {'ok': 0, 'info': 1, 'warn': 2, 'fail': 3}


class MonitorError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class MonitorStore:
    """Thin wrapper around the monitors SQLite file."""

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
            import os
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
            log.warning("monitor store unavailable (%s) — monitoring disabled",
                        self._broken)
            return False

    def available(self) -> bool:
        return not self._broken

    # -- CRUD ------------------------------------------------------------

    def list_monitors(self) -> list:
        rows = self._connect().execute(
            'SELECT * FROM monitors ORDER BY id').fetchall()
        return [dict(r) for r in rows]

    def get_monitor(self, monitor_id: int) -> dict:
        row = self._connect().execute(
            'SELECT * FROM monitors WHERE id = ?', (monitor_id,)).fetchone()
        if row is None:
            raise MonitorError('monitor_not_found')
        return dict(row)

    def create_monitor(self, name: str, probe: str, target: str,
                       interval_hours: int, notify_email: bool,
                       notify_telegram: bool, enabled: bool = True) -> int:
        if probe not in MONITOR_PROBES:
            raise MonitorError('bad_probe')
        with self._write_lock:
            con = self._connect()
            cur = con.execute(
                """INSERT INTO monitors
                   (name, probe, target, interval_hours, enabled,
                    notify_email, notify_telegram, created_ts)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (name[:120], probe, target[:253], max(1, int(interval_hours)),
                 1 if enabled else 0, 1 if notify_email else 0,
                 1 if notify_telegram else 0, int(time.time())))
            con.commit()
            return cur.lastrowid

    def update_monitor(self, monitor_id: int, **fields) -> None:
        self.get_monitor(monitor_id)  # 404s if missing
        allowed = ('name', 'probe', 'target', 'interval_hours', 'enabled',
                  'notify_email', 'notify_telegram')
        sets, values = [], []
        for key in allowed:
            if key not in fields:
                continue
            value = fields[key]
            if key in ('enabled', 'notify_email', 'notify_telegram'):
                value = 1 if value else 0
            elif key == 'interval_hours':
                value = max(1, int(value))
            elif key == 'name':
                value = str(value)[:120]
            elif key == 'target':
                value = str(value)[:253]
            elif key == 'probe' and value not in MONITOR_PROBES:
                raise MonitorError('bad_probe')
            sets.append(f'{key} = ?')
            values.append(value)
        if not sets:
            return
        values.append(monitor_id)
        with self._write_lock:
            con = self._connect()
            con.execute(f"UPDATE monitors SET {', '.join(sets)} WHERE id = ?", values)
            con.commit()

    def delete_monitor(self, monitor_id: int) -> None:
        with self._write_lock:
            con = self._connect()
            con.execute('DELETE FROM monitors WHERE id = ?', (monitor_id,))
            con.execute('DELETE FROM monitor_history WHERE monitor_id = ?', (monitor_id,))
            con.commit()

    # -- History -----------------------------------------------------------

    def history(self, monitor_id: int, limit: int = 50) -> list:
        rows = self._connect().execute(
            """SELECT * FROM monitor_history WHERE monitor_id = ?
               ORDER BY ts DESC LIMIT ?""", (monitor_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def record_run(self, monitor_id: int, level: str, summary: str,
                   notified: bool) -> None:
        now = int(time.time())
        with self._write_lock:
            con = self._connect()
            con.execute(
                """INSERT INTO monitor_history (monitor_id, ts, level, summary, notified)
                   VALUES (?,?,?,?,?)""",
                (monitor_id, now, level, summary[:500], 1 if notified else 0))
            con.execute(
                """UPDATE monitors SET last_run_ts = ?, last_level = ?,
                   last_summary = ?, last_error = '' WHERE id = ?""",
                (now, level, summary[:500], monitor_id))
            # Keep only the newest HISTORY_KEEP rows per monitor -- this is a
            # health log, not an audit trail; unbounded growth serves nobody.
            con.execute(
                """DELETE FROM monitor_history WHERE monitor_id = ? AND id NOT IN
                   (SELECT id FROM monitor_history WHERE monitor_id = ?
                    ORDER BY ts DESC LIMIT ?)""",
                (monitor_id, monitor_id, HISTORY_KEEP))
            con.commit()

    def record_error(self, monitor_id: int, error: str) -> None:
        now = int(time.time())
        with self._write_lock:
            con = self._connect()
            con.execute(
                'UPDATE monitors SET last_run_ts = ?, last_error = ? WHERE id = ?',
                (now, error[:300], monitor_id))
            con.commit()

    def due_monitors(self, now_ts: int) -> list:
        rows = self._connect().execute(
            'SELECT * FROM monitors WHERE enabled = 1').fetchall()
        due = []
        for row in rows:
            m = dict(row)
            last = m['last_run_ts'] or 0
            if now_ts - last >= m['interval_hours'] * 3600:
                due.append(m)
        return due


# ── Summaries ────────────────────────────────────────────────────────────────
# Short, fixed-language (German) one-liners for notifications. Not the same
# text the UI shows -- that is translated client-side from finding codes; a
# notification has to stand on its own without that JS layer, so it is kept
# short and probe-specific rather than trying to mirror every finding.


def summarize(probe: str, result: dict) -> str:
    level = (result.get('level') or 'ok').upper()
    if probe == 'tls':
        days = result.get('days_left')
        if not result.get('trusted'):
            return f"{level}: Zertifikatskette nicht vertrauenswürdig ({result.get('verify_error') or '?'})"
        if days is not None:
            return f"{level}: Zertifikat noch {days} Tage gültig"
        return f"{level}: Details nicht verfügbar"
    if probe == 'blacklist':
        listed = result.get('listed_count', 0)
        if listed:
            names = ', '.join(r['label'] for r in result.get('rows', []) if r.get('listed'))
            return f"{level}: auf {listed} Sperrliste(n) gelistet — {names}"
        return f"{level}: auf keiner Sperrliste gelistet"
    if probe == 'mail_health':
        return f"{level}: Punktestand {result.get('score', '?')}/100"
    return level


# ── Notifications ─────────────────────────────────────────────────────────────


def send_email(cfg: dict, subject: str, body: str) -> tuple:
    host = str(cfg.get('smtp_host') or '').strip()
    to = str(cfg.get('smtp_to') or '').strip()
    if not host or not to:
        return False, 'not_configured'
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = subject
    msg['From'] = str(cfg.get('smtp_from') or cfg.get('smtp_user') or 'nettoolbox@localhost')
    msg['To'] = to
    port = int(cfg.get('smtp_port') or 587)
    try:
        server = smtplib.SMTP(host, port, timeout=15)
        try:
            if cfg.get('smtp_tls', True):
                server.starttls()
            user = str(cfg.get('smtp_user') or '')
            if user:
                server.login(user, str(cfg.get('smtp_password') or ''))
            server.sendmail(msg['From'], [to], msg.as_string())
        finally:
            server.quit()
        return True, ''
    except (smtplib.SMTPException, OSError) as e:
        # Full detail (host, port, server banner text) goes to the log only --
        # callers (including the settings-test API, which echoes this to the
        # browser) get a short category code, never str(e). A raw exception
        # can carry internal hostnames or auth-server responses.
        log.warning("monitor email notification failed: %s", e)
        if isinstance(e, smtplib.SMTPAuthenticationError):
            return False, 'auth_failed'
        if isinstance(e, smtplib.SMTPRecipientsRefused):
            return False, 'recipient_refused'
        if isinstance(e, (socket.timeout, TimeoutError)):
            return False, 'timeout'
        return False, 'connection_failed'


def send_telegram(cfg: dict, text: str) -> tuple:
    token = str(cfg.get('telegram_bot_token') or '').strip()
    chat_id = str(cfg.get('telegram_chat_id') or '').strip()
    if not token or not chat_id:
        return False, 'not_configured'
    try:
        resp = requests.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            json={'chat_id': chat_id, 'text': text}, timeout=10)
        if resp.status_code != 200:
            return False, f'http_{resp.status_code}'
        return True, ''
    except requests.RequestException as e:
        log.warning("monitor telegram notification failed: %s", e)
        if isinstance(e, requests.Timeout):
            return False, 'timeout'
        return False, 'connection_failed'


def notify(cfg: dict, monitor: dict, level: str, summary: str) -> bool:
    """Sends on every call -- the caller decides whether a state change (or a
    reminder) warrants one; this only knows how to deliver, not when to."""
    subject = f"[NetToolbox] {monitor['name']}: {level.upper()}"
    body = (f"{monitor['name']} ({monitor['probe']}: {monitor['target']})\n\n"
           f"{summary}\n\n-- NetToolbox")
    sent_any = False
    if monitor.get('notify_email'):
        ok, err = send_email(cfg, subject, body)
        sent_any = sent_any or ok
        if not ok and err != 'not_configured':
            log.warning("monitor %s: email notification failed: %s", monitor['id'], err)
    if monitor.get('notify_telegram'):
        ok, err = send_telegram(cfg, f"{subject}\n{summary}")
        sent_any = sent_any or ok
        if not ok and err != 'not_configured':
            log.warning("monitor %s: telegram notification failed: %s", monitor['id'], err)
    return sent_any


# ── Running a single monitor ──────────────────────────────────────────────────


def run_monitor(store: MonitorStore, monitor: dict, ctx, notify_cfg: dict) -> dict:
    """Runs the monitor's probe once, records history, notifies on a level
    change. Raises nothing -- a probe failure is itself recorded, not thrown,
    so the worker loop never has to special-case one bad monitor."""
    import probes as probes_module
    param_key = MONITOR_PROBES.get(monitor['probe'])
    if param_key is None:
        store.record_error(monitor['id'], 'bad_probe')
        return {'ok': False, 'error': 'bad_probe'}

    try:
        result = probes_module.run(monitor['probe'], {param_key: monitor['target']}, ctx)
    except Exception as e:
        code = getattr(e, 'code', type(e).__name__)
        store.record_error(monitor['id'], str(code))
        return {'ok': False, 'error': str(code)}

    level = result.get('level', 'ok')
    summary = summarize(monitor['probe'], result)
    previous_level = monitor.get('last_level') or ''
    changed = previous_level != '' and previous_level != level
    # First run: only a hard failure is worth an immediate alert. 'info' is
    # routine (a single MX, a missing BIMI logo — completely normal) and
    # would otherwise fire the moment anyone adds a monitor; the baseline is
    # set silently instead and only *changes* from it get reported after.
    should_notify = changed or (previous_level == '' and level == 'fail')
    notified = False
    if should_notify:
        notified = notify(notify_cfg, monitor, level, summary)
    store.record_run(monitor['id'], level, summary, notified)
    return {'ok': True, 'level': level, 'summary': summary, 'notified': notified}


def worker_loop(store: MonitorStore, ctx_factory, notify_cfg_factory,
                poll_seconds: int = 60, stop_event: threading.Event = None) -> None:
    """Runs forever (or until stop_event is set) checking for due monitors."""
    while stop_event is None or not stop_event.is_set():
        try:
            if store.available():
                now = int(time.time())
                for m in store.due_monitors(now):
                    try:
                        run_monitor(store, m, ctx_factory(), notify_cfg_factory())
                    except Exception:
                        log.exception("monitor %s failed to run", m.get('id'))
        except Exception:
            log.exception("monitor worker iteration failed")
        time.sleep(poll_seconds)
