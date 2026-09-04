"""Pytest-Setup: macht das Add-on-Modul `scraper` importierbar (liegt eine Ebene
über diesem tests/-Ordner) und stellt kleine Helfer für die Fixtures bereit."""
import json
import os
import sys

import pytest

# Die API-Tests melden sich wie der HA-Supervisor mit `X-Ingress-Path` an. Seit
# 0.113.7 glaubt app.py diesen Header nur noch, wenn ein SUPERVISOR_TOKEN in der
# Umgebung steht (sonst waere er ausserhalb von HA eine Login-Umgehung) — die
# Testumgebung stellt genau das her. Die Sperre selbst prueft
# tests/test_ingress_trust.py.
os.environ.setdefault("TUIWATCH_TRUST_INGRESS", "1")

HERE = os.path.dirname(__file__)
ROOT = os.path.dirname(HERE)              # …/tuiwatch
FX = os.path.join(HERE, "fixtures")
sys.path.insert(0, ROOT)


def load_fixture(name: str):
    """Lädt eine (echte, reduzierte) TUI-API-Antwort aus tests/fixtures/."""
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f)


class FakeResp:
    """Minimaler requests.Response-Ersatz für die Monkeypatch-Tests."""
    def __init__(self, data, status: int = 200):
        self._data = data
        self.status_code = status

    def json(self):
        return self._data


@pytest.fixture
def fx():
    return load_fixture


@pytest.fixture
def fake_resp():
    return FakeResp
