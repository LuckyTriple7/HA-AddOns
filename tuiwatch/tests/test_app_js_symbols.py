"""Statische Prüfung von `static/app.js` auf benutzte, aber nicht deklarierte
Konstanten.

Anlass: beim Umbau der KI-Anzeige wurde der Block mit `AI_JOB_MAX_WAIT_MS` und
`AI_JOB_POLL_MS` versehentlich mit herausgeschnitten. Beide wurden weiter benutzt.
Ergebnis war ein `ReferenceError` bei **jedem** KI-Aufruf — sofortiger Fehler im
Fenster, nichts im Server-Log, weil serverseitig gar nichts schiefging. Genau die
Sorte Fehler, die weder `node --check` noch ein Python-Test bemerkt hätte.

Deshalb hier eine bewusst enge Prüfung: nur SCREAMING_CASE-Konstanten mit
bekanntem Präfix. Die sind im Modulkopf deklariert und über die ganze Datei
verstreut in Gebrauch — ein Muster, bei dem so ein Schnitt leicht passiert.
"""
import re
from pathlib import Path

import pytest

APP_JS = Path(__file__).resolve().parent.parent / "static" / "app.js"

# Präfixe der Konstanten, die hier geprüft werden. Bewusst eng gehalten: eine
# vollständige JS-Scope-Analyse ist mit einem Regex nicht zu haben, und ein Test,
# der falsch anschlägt, wird schnell abgeschaltet.
_PREFIXES = ("AI_", "PROMPTCFG_")
_NAME = r"(?:" + "|".join(p + "[A-Z0-9_]+" for p in _PREFIXES) + r")"


@pytest.fixture(scope="module")
def src():
    if not APP_JS.is_file():
        pytest.skip("static/app.js nicht gefunden")
    return APP_JS.read_text(encoding="utf-8")


def test_every_used_constant_is_declared(src):
    used = set(re.findall(r"\b(" + _NAME + r")\b", src))
    declared = set(re.findall(r"\b(?:const|let|var)\s+(" + _NAME + r")\b", src))
    missing = sorted(used - declared)
    assert not missing, (
        "In app.js benutzt, aber nirgends deklariert: " + ", ".join(missing)
        + " — das wirft zur Laufzeit einen ReferenceError, sichtbar nur im Browser."
    )


def test_no_constant_is_declared_twice(src):
    """Eine zweite Deklaration mit `const` im selben Scope ist ein harter
    SyntaxError — beim Zusammenführen von Blöcken leicht passiert."""
    declared = re.findall(r"\b(?:const|let)\s+(" + _NAME + r")\b", src)
    doppelt = sorted({n for n in declared if declared.count(n) > 1})
    assert not doppelt, "Mehrfach deklariert: " + ", ".join(doppelt)
