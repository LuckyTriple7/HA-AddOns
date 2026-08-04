"""Guard: die YAML-Dateien des Add-ons müssen parsebar sein und jede Option muss in
beiden Sprachen beschrieben sein.

Hintergrund (v0.60.3, live): in `translations/de.yaml` stand in einer
doppelt-gequoteten Beschreibung ein ASCII-Anführungszeichen (`„heute + X Tage"`).
Das beendet den YAML-String mitten im Satz, die Datei war unparsebar — und Home
Assistant zeigte daraufhin **kommentarlos die englische Übersetzung** an. Kein
Fehler, kein Log-Eintrag, nur plötzlich englische Einstellungen. Genau diese
stille Regression fängt dieser Test ab.
"""
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
LOCALES = ("de", "en")


def _load(rel: str):
    try:
        return yaml.safe_load((ROOT / rel).read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        pytest.fail(f"{rel} ist kein gültiges YAML: {exc}")


@pytest.mark.parametrize("rel", ["config.yaml"] + [f"translations/{l}.yaml" for l in LOCALES])
def test_yaml_parses(rel):
    assert _load(rel), f"{rel} ist leer"


def test_every_option_is_translated():
    """Jede Option aus config.yaml braucht Name und Beschreibung in beiden Sprachen —
    sonst zeigt HA den nackten Schlüssel an."""
    options = set((_load("config.yaml").get("options") or {}).keys())
    for loc in LOCALES:
        tr = (_load(f"translations/{loc}.yaml").get("configuration") or {})
        missing = sorted(options - set(tr))
        assert not missing, f"translations/{loc}.yaml: keine Übersetzung für {missing}"
        incomplete = sorted(k for k in options
                            if not (tr[k] or {}).get("name")
                            or not (tr[k] or {}).get("description"))
        assert not incomplete, f"translations/{loc}.yaml: name/description fehlt bei {incomplete}"
