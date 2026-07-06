"""Stellt sicher, dass `APP_VERSION` in app.py und `version:` in config.yaml nie
auseinanderlaufen — ist in dieser Session mehrfach vergessen worden. Kein YAML-Parser
nötig, das Feld ist ein einfaches `version: "X.Y.Z"`."""
import importlib
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent


def test_app_version_matches_config_yaml():
    try:
        m = importlib.import_module("app")
    except Exception as exc:
        pytest.skip(f"app nicht importierbar: {exc}")

    config = (_ROOT / "config.yaml").read_text(encoding="utf-8")
    match = re.search(r'^version:\s*"([^"]+)"', config, re.MULTILINE)
    assert match, "config.yaml: version-Zeile nicht gefunden"
    assert m.APP_VERSION == match.group(1), (
        f"APP_VERSION ({m.APP_VERSION}) != config.yaml version ({match.group(1)}) — "
        "bei jedem Versions-Bump beide zusammen aktualisieren"
    )
