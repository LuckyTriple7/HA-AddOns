"""Tests für `atomic_io`: Dateien landen ganz oder gar nicht im Ziel.

Grund für das Modul: der SIGTERM-Handler beendet den Prozess hart (`os._exit(0)`).
Ein direktes `open(path, 'w')` kürzt das Ziel sofort — wird dazwischen abgebrochen,
ist der alte Stand weg. Genau das darf hier nicht passieren.
"""
import json
import os

import pytest

import atomic_io


def _siblings(p):
    return sorted(os.listdir(str(p)))


def test_write_bytes_erzeugt_datei_und_raeumt_temp_auf(tmp_path):
    t = tmp_path / "x.bin"
    atomic_io.write_bytes(str(t), b"hallo")
    assert t.read_bytes() == b"hallo"
    assert _siblings(tmp_path) == ["x.bin"]      # keine .tmp-*.new-Leiche


def test_write_bytes_ersetzt_bestehende_datei(tmp_path):
    t = tmp_path / "x.bin"
    t.write_bytes(b"alt")
    atomic_io.write_bytes(str(t), b"neu")
    assert t.read_bytes() == b"neu"
    assert _siblings(tmp_path) == ["x.bin"]


def test_fehler_beim_schreiben_laesst_alten_stand_stehen(tmp_path, monkeypatch):
    """Kernversprechen: schlägt das Schreiben fehl, ist die Zieldatei unverändert —
    bei `open(path,'w')` wäre sie an dieser Stelle schon auf 0 Bytes gekürzt."""
    t = tmp_path / "settings.json"
    t.write_bytes(b'{"alt": true}')

    real_replace = os.replace

    def boom(src, dst):
        raise OSError("Kein Platz mehr")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        atomic_io.write_bytes(str(t), b'{"neu": true}')
    monkeypatch.setattr(os, "replace", real_replace)

    assert t.read_bytes() == b'{"alt": true}'
    assert _siblings(tmp_path) == ["settings.json"]   # Temp-Datei wurde entfernt


def test_write_text_und_write_json(tmp_path):
    a = tmp_path / "a.txt"
    atomic_io.write_text(str(a), "äöü")
    assert a.read_text(encoding="utf-8") == "äöü"

    b = tmp_path / "b.json"
    atomic_io.write_json(str(b), {"k": "ä"}, ensure_ascii=False, indent=2)
    assert json.loads(b.read_text(encoding="utf-8")) == {"k": "ä"}
    assert "\n" in b.read_text(encoding="utf-8")      # indent kam durch


@pytest.mark.skipif(os.name == "nt", reason="POSIX-Rechte gibt es unter Windows nicht")
def test_mode_wird_gesetzt(tmp_path):
    t = tmp_path / "settings.key"
    atomic_io.write_bytes(str(t), b"geheim", mode=0o600)
    assert oct(os.stat(str(t)).st_mode & 0o777) == "0o600"


def test_schluesseldatei_bleibt_bei_fehler_lesbar(tmp_path, monkeypatch):
    """Der teuerste Einzelfall: ein halb geschriebener `settings.key` macht alle
    verschlüsselten Zugangsdaten unwiederbringlich unlesbar."""
    k = tmp_path / "settings.key"
    k.write_bytes(b"echter-schluessel")
    monkeypatch.setattr(os, "replace", lambda *a: (_ for _ in ()).throw(OSError("boom")))
    with pytest.raises(OSError):
        atomic_io.write_bytes(str(k), b"neuer-schluessel", mode=0o600)
    assert k.read_bytes() == b"echter-schluessel"
