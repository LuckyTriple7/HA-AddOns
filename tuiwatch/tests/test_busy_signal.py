"""Tests für das Hintergrund-Signal (Logo färbt sich, solange etwas läuft).

Deckt `busy`/`busy_labels` und die Auslieferung über GET /api/offers ab.
"""
import importlib

import pytest

pytest.importorskip("flask")

ING = {"X-Ingress-Path": "/test"}


@pytest.fixture
def m(tmp_path, monkeypatch):
    monkeypatch.setenv("TUIWATCH_DATA", str(tmp_path))
    monkeypatch.setenv("TUIWATCH_BASE", str(tmp_path))
    try:
        mod = importlib.import_module("app")
    except Exception as exc:
        pytest.skip(f"app nicht importierbar: {exc}")
    importlib.reload(mod)
    mod.DB_PATH = str(tmp_path / "tuiwatch.db")
    mod.init_db()
    mod._busy.clear()
    mod._checking.clear()
    return mod


def test_busy_label_kommt_und_geht(m):
    assert m.busy_labels() == []
    with m.busy("Suchabos"):
        assert m.busy_labels() == ["Suchabos"]
    assert m.busy_labels() == []


def test_busy_zaehlt_verschachtelt(m):
    """Dasselbe Label doppelt (Poller + Oberfläche) darf beim ersten Ende nicht
    verschwinden — sonst erlischt das Signal, während noch etwas läuft."""
    with m.busy("Preiskalender"):
        with m.busy("Preiskalender"):
            assert m.busy_labels() == ["Preiskalender"]
        assert m.busy_labels() == ["Preiskalender"]
    assert m.busy_labels() == []


def test_busy_raeumt_bei_fehler_auf(m):
    with pytest.raises(RuntimeError):
        with m.busy("Backup"):
            raise RuntimeError("kaputt")
    assert m.busy_labels() == []


def test_laufende_preis_checks_aus_checking(m):
    """Einzel-Checks (auch aus der Oberfläche) melden sich über `_checking`."""
    m._checking.update({1})
    assert m.busy_labels() == ["Preis-Check"]
    m._checking.update({2, 3})
    assert m.busy_labels() == ["Preis-Checks (3)"]


def test_poller_label_verdraengt_das_abgeleitete(m):
    """Läuft der Poller-Block, soll nicht zusätzlich ein zweites Preis-Label
    im Tooltip stehen."""
    m._checking.update({1, 2})
    with m.busy("Preis-Checks (7)"):
        assert m.busy_labels() == ["Preis-Checks (7)"]


def test_api_offers_liefert_busy(m):
    c = m.app.test_client()
    assert c.get("/api/offers", headers=ING).get_json()["busy"] == []
    with m.busy("Selbsttest"):
        assert c.get("/api/offers", headers=ING).get_json()["busy"] == ["Selbsttest"]
