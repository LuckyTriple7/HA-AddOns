"""Ohne Internet pausiert der Poller, statt in Timeouts zu laufen.

Fiel die Leitung aus, lief bisher jeder Schritt in seine eigenen Timeouts, jedes
fällige Angebot zweimal, und im Verlauf stand am Ende ein Fehlversuch, der nichts
über den Preis aussagt. `_net_ok()` prüft einmal je Runde und protokolliert
Ausfall und Rückkehr je einmal — nicht bei jedem Durchlauf neu.
"""
import importlib

import pytest

pytest.importorskip("flask")


@pytest.fixture
def m(tmp_path, monkeypatch):
    monkeypatch.setenv("TUIWATCH_DATA", str(tmp_path))
    monkeypatch.setenv("TUIWATCH_BASE", str(tmp_path))
    try:
        mod = importlib.import_module("app")
    except Exception as exc:
        pytest.skip(f"app nicht importierbar: {exc}")
    importlib.reload(mod)
    mod._net_state.update(online=True, since=0.0, logged=0.0)
    return mod


def test_ausfall_und_rueckkehr_je_einmal_im_log(m, monkeypatch, caplog):
    import scraper
    monkeypatch.setattr(scraper, "internet_reachable", lambda *a, **k: False)
    with caplog.at_level("WARNING", logger="tuiwatch"):
        assert m._net_ok() is False
        assert m._net_ok() is False          # zweite Runde: keine neue Zeile
    assert sum("Keine Internetverbindung" in r.message for r in caplog.records) == 1

    caplog.clear()
    monkeypatch.setattr(scraper, "internet_reachable", lambda *a, **k: True)
    with caplog.at_level("INFO", logger="tuiwatch"):
        assert m._net_ok() is True
        assert m._net_ok() is True
    assert sum("wieder da" in r.message for r in caplog.records) == 1


def test_zustand_merkt_sich_den_ausfall(m, monkeypatch):
    import scraper
    monkeypatch.setattr(scraper, "internet_reachable", lambda *a, **k: False)
    m._net_ok()
    assert m._net_state["online"] is False and m._net_state["since"] > 0
    monkeypatch.setattr(scraper, "internet_reachable", lambda *a, **k: True)
    m._net_ok()
    assert m._net_state["online"] is True and m._net_state["since"] == 0.0


def test_reaper_fasst_nichts_an_waehrend_ein_abruf_laeuft(m, monkeypatch):
    """Solange ein Fallback-Abruf läuft, gehören die Chromium-Prozesse dazu —
    sie zu beenden würde genau den Abruf abschießen, auf dessen Ergebnis wir warten."""
    import scraper
    monkeypatch.setattr(scraper, "browser_busy", lambda: True)
    monkeypatch.setattr(m, "_chromium_leftovers",
                        lambda: [(1234, 500.0)])   # dürfte nicht abgefragt werden
    assert m._reap_orphan_chromium() == 0


def test_reaper_findet_ohne_marker_nichts(m):
    """Läuft kein Fallback-Browser, ist die Liste leer — fremde Prozesse im selben
    Namensraum (Testlauf, Entwicklungsrechner) tragen unseren Marker nicht."""
    assert m._chromium_leftovers() == []
    assert m._reap_orphan_chromium() == 0
