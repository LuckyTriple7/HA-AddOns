"""Guard: app.py muss auch als SKRIPT starten (`python3 app.py`, wie run.sh im
Add-on) — nicht nur als importiertes Modul (wie unter pytest).

Hintergrund (v0.48.2, live): als Skript heißt das Modul '__main__'; `import app`
in den Blueprint-Modulen führte app.py dadurch ein zweites Mal aus →
Zirkular-Crash bei register_blueprint. Alle 307 Tests waren grün, weil pytest
app als Modul 'app' importiert. Dieser Test startet den echten Skript-Pfad als
Subprozess und wartet auf /health."""
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("flask")
requests = pytest.importorskip("requests")

ROOT = Path(__file__).resolve().parent.parent
PORT = 17982


def test_app_starts_as_script(tmp_path):
    env = dict(os.environ, TUIWATCH_DATA=str(tmp_path), TUIWATCH_BASE=str(ROOT),
               TUIWATCH_PORT=str(PORT))
    proc = subprocess.Popen([sys.executable, str(ROOT / "app.py")], env=env,
                            cwd=str(ROOT), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            if proc.poll() is not None:   # Prozess tot -> Crash beim Start
                out = proc.stdout.read()
                pytest.fail(f"app.py als Skript gestorben (exit {proc.returncode}):\n{out[-2000:]}")
            try:
                r = requests.get(f"http://127.0.0.1:{PORT}/health", timeout=2)
                assert r.status_code == 200
                return
            except requests.RequestException:
                time.sleep(0.5)
        pytest.fail("app.py als Skript: /health nicht erreichbar (30s Timeout)")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
