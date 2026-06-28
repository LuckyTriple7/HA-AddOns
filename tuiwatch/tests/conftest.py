"""Pytest-Setup: macht das Add-on-Modul `scraper` importierbar (liegt eine Ebene
über diesem tests/-Ordner) und stellt kleine Helfer für die Fixtures bereit."""
import json
import os
import sys

import pytest

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
