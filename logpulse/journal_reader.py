#!/usr/bin/env python3
"""journald-Ingest: liest /var/log/journal, klassifiziert Quelle + Log-Level,
persistiert Einträge in SQLite. Läuft als Hintergrund-Thread neben der Flask-App."""
import logging
import re
import time

log = logging.getLogger(__name__)

JOURNAL_PATH = "/var/log/journal"

PRIORITY_TO_LEVEL = {
    0: "CRITICAL", 1: "CRITICAL", 2: "CRITICAL",
    3: "ERROR", 4: "WARNING", 5: "INFO", 6: "INFO", 7: "DEBUG",
}

# Eigene Addons (cardboard, syswatch, gitpulse, ...) loggen im Format "[LEVEL] ..."
BRACKET_LEVEL = re.compile(r'^\[(DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL|OK)\]')
BRACKET_NORMALIZE = {"WARN": "WARNING", "OK": "INFO"}

# HA Core / Supervisor loggen im Python-logging-Standardformat
# "2026-07-08 12:00:00.000 WARNING (MainThread) [homeassistant.core] msg"
HA_STYLE_LEVEL = re.compile(r'^\S+ \S+ (DEBUG|INFO|WARNING|ERROR|CRITICAL)\b')

# Viele Go-Tools (crowdsec, traefik, ...) loggen Logrus/Zerolog-Stil:
# time="..." level=info msg="..." — Docker markiert das per stdout/stderr
# als INFO/ERROR-Priority, unabhängig vom echten Level im Text.
LOGRUS_LEVEL = re.compile(r'\blevel=(debug|info|warn(?:ing)?|error|fatal|panic)\b', re.IGNORECASE)
LOGRUS_NORMALIZE = {
    'DEBUG': 'DEBUG', 'INFO': 'INFO', 'WARN': 'WARNING', 'WARNING': 'WARNING',
    'ERROR': 'ERROR', 'FATAL': 'CRITICAL', 'PANIC': 'CRITICAL',
}

ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')

# Fallback-Level für Folgezeilen ohne erkennbares Prefix (z.B. Tracebacks)
_last_level_by_key: dict[str, str] = {}


def classify_source(entry: dict) -> tuple[str, str | None]:
    container = entry.get("CONTAINER_NAME")
    if container == "homeassistant":
        return "core", container
    if container == "hassio_supervisor":
        return "supervisor", container
    if container:
        return "addon", container
    return "system", None


def derive_level(msg: str, key: str, priority: int) -> str:
    m = BRACKET_LEVEL.match(msg)
    if m:
        lvl = m.group(1)
        lvl = BRACKET_NORMALIZE.get(lvl, lvl)
        _last_level_by_key[key] = lvl
        return lvl
    m = HA_STYLE_LEVEL.match(msg)
    if m:
        lvl = m.group(1)
        _last_level_by_key[key] = lvl
        return lvl
    m = LOGRUS_LEVEL.search(msg)
    if m:
        lvl = LOGRUS_NORMALIZE.get(m.group(1).upper(), 'INFO')
        _last_level_by_key[key] = lvl
        return lvl
    if key in _last_level_by_key:
        return _last_level_by_key[key]
    lvl = PRIORITY_TO_LEVEL.get(priority, "INFO")
    _last_level_by_key[key] = lvl
    return lvl


def _open_reader():
    from systemd import journal
    return journal.Reader(path=JOURNAL_PATH)


def reader_loop(get_conn, db_lock, resolve_addon_name, notify_new, poll_timeout_ms: int = 5000):
    """Läuft endlos im Hintergrund-Thread. Blockiert bei Fehlern kurz und versucht erneut,
    statt den Thread sterben zu lassen (journald kann z.B. während Rotation kurz hakeln)."""
    while True:
        try:
            _reader_loop_once(get_conn, db_lock, resolve_addon_name, notify_new, poll_timeout_ms)
        except Exception:
            log.exception("journal_reader: Ingest-Loop abgebrochen, Neustart in 5s")
            time.sleep(5)


def _reader_loop_once(get_conn, db_lock, resolve_addon_name, notify_new, poll_timeout_ms):
    jr = _open_reader()
    jr.this_boot()

    with db_lock:
        row = get_conn().execute(
            "SELECT cursor FROM log_entries ORDER BY id DESC LIMIT 1"
        ).fetchone()

    if row:
        try:
            jr.seek_cursor(row[0])
            jr.get_next()  # bereits verarbeiteten Eintrag überspringen
        except Exception:
            jr.seek_tail()
    else:
        jr.seek_tail()
        try:
            jr.get_previous()
        except Exception:
            pass

    while True:
        jr.wait(poll_timeout_ms / 1000.0)
        batch = []
        for entry in jr:
            source, container = classify_source(entry)
            raw_msg = entry.get("MESSAGE", "")
            if not isinstance(raw_msg, str):
                raw_msg = str(raw_msg)
            msg = ANSI_RE.sub('', raw_msg)
            priority = int(entry.get("PRIORITY", 6))
            key = container or source
            level = derive_level(msg, key, priority)
            addon_name = resolve_addon_name(container) if source == "addon" else None
            ts_field = entry.get("__REALTIME_TIMESTAMP")
            ts = ts_field.timestamp() if ts_field is not None else time.time()
            batch.append((
                ts, source, container, addon_name,
                entry.get("SYSLOG_IDENTIFIER") or entry.get("_COMM"),
                priority, level, msg, str(entry.get("__CURSOR", "")),
            ))
        if batch:
            with db_lock:
                conn = get_conn()
                conn.executemany(
                    "INSERT OR IGNORE INTO log_entries "
                    "(ts, source, container, addon_name, identifier, priority, level, message, cursor) "
                    "VALUES (?,?,?,?,?,?,?,?,?)", batch)
                conn.commit()
            notify_new()


def retention_loop(get_conn, db_lock, load_config, db_path, interval_seconds: int = 1800):
    import os
    while True:
        try:
            cfg = load_config()
            cutoff = time.time() - int(cfg.get('retention_days', 14)) * 86400
            max_mb = int(cfg.get('max_db_size_mb', 300))
            with db_lock:
                conn = get_conn()
                conn.execute("DELETE FROM log_entries WHERE ts < ?", (cutoff,))
                conn.commit()
                while True:
                    try:
                        size_mb = os.path.getsize(db_path) / (1024 * 1024)
                    except OSError:
                        break
                    if size_mb <= max_mb:
                        break
                    cur = conn.execute(
                        "DELETE FROM log_entries WHERE id IN "
                        "(SELECT id FROM log_entries ORDER BY ts ASC LIMIT 1000)")
                    conn.commit()
                    if cur.rowcount == 0:
                        break
                conn.execute("PRAGMA incremental_vacuum(5000)")
                conn.commit()
        except Exception:
            log.exception("journal_reader: Retention-Durchlauf fehlgeschlagen")
        time.sleep(interval_seconds)
