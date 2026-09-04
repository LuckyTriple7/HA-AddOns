"""Atomares Schreiben von Dateien — schreibt nie direkt ins Ziel.

Hintergrund: der SIGTERM-Handler beendet den Prozess hart (`os._exit(0)`, siehe
`app._handle_sigterm`), und HA OS kann jederzeit neu starten. Ein `open(path,'w')`
kürzt die Zieldatei sofort auf 0 Bytes — wird der Prozess dazwischen beendet,
steht dort Müll oder nichts mehr. Bei `settings.key` hieße das: alle
verschlüsselten Zugangsdaten sind unwiederbringlich weg.

Deshalb überall dasselbe Muster: in eine Temp-Datei im *selben* Verzeichnis
schreiben, fsync, dann per `os.replace` einhängen. `os.replace` ist auf einem
POSIX-Dateisystem atomar — das Ziel enthält danach entweder komplett den alten
oder komplett den neuen Stand, nie einen halben. Ein harter Kill mitten im
Schreiben hinterlässt höchstens eine verwaiste `.tmp-*.new`-Datei.

Temp-Namen sind eindeutig (mkstemp), damit zwei gleichzeitig schreibende Threads
sich nicht gegenseitig die halbfertige Temp-Datei überschreiben.
"""
from __future__ import annotations

import json
import os
import tempfile


def _fsync_dir(path: str) -> None:
    """Verzeichniseintrag selbst dauerhaft machen — sonst kann `os.replace` nach
    einem Stromausfall noch fehlen, obwohl die Daten schon geschrieben waren.
    Unter Windows (nur Entwicklung/Tests) gibt es das nicht, daher tolerant."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def write_bytes(path: str, data: bytes, *, mode: int | None = None) -> None:
    """Schreibt `data` atomar nach `path`. `mode` z. B. 0o600 für Schlüsseldateien
    (mkstemp legt ohnehin mit 0600 an, das Ziel erbt die Temp-Rechte)."""
    path = os.fspath(path)
    d = os.path.dirname(os.path.abspath(path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.tmp-', suffix='.new')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            try:
                os.chmod(tmp, mode)
            except OSError:
                pass
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    _fsync_dir(d)


def write_text(path: str, text: str, *, encoding: str = 'utf-8',
               mode: int | None = None) -> None:
    write_bytes(path, text.encode(encoding), mode=mode)


def write_json(path: str, obj, *, mode: int | None = None, **dump_kw) -> None:
    """`dump_kw` wird an `json.dumps` durchgereicht (indent, ensure_ascii, …)."""
    write_text(path, json.dumps(obj, **dump_kw), mode=mode)
