"""Browser-Fallback: Schalter aus den Einstellungen und Netz-Prüfung.

Der Fallback startet ein Headless-Chromium (gemessen 400–740 MB). Er darf deshalb
nur laufen, wenn er eingeschaltet ist UND überhaupt eine Leitung anliegt — ohne
Netz wäre der Speicher für nichts belegt, und zwar bei jedem fälligen Angebot
nacheinander.
"""
import importlib

import pytest

scraper = importlib.import_module("scraper")


@pytest.fixture
def sc(monkeypatch):
    """scraper mit fehlgeschlagener JSON-API und protokolliertem Browser-Aufruf."""
    calls = []
    monkeypatch.setattr(scraper, "fetch_price_api", lambda *a, **k: None)
    monkeypatch.setattr(scraper, "_fetch_price_browser",
                        lambda *a, **k: calls.append(a) or dict(scraper._empty_result(), ok=True))
    monkeypatch.setattr(scraper, "browser_fallback_enabled", lambda: True)
    monkeypatch.setattr(scraper, "internet_reachable", lambda *a, **k: True)
    return scraper, calls


URL = "https://www.tui.com/pauschalreisen/angebot/"


def test_fallback_laeuft_wenn_an_und_netz_da(sc):
    mod, calls = sc
    r = mod.fetch_price(URL)
    assert r["ok"] and len(calls) == 1


def test_fallback_abgeschaltet_startet_keinen_browser(sc, monkeypatch):
    mod, calls = sc
    monkeypatch.setattr(mod, "browser_fallback_enabled", lambda: False)
    r = mod.fetch_price(URL)
    assert calls == []
    assert r["ok"] is False
    assert "abgeschaltet" in r["detail"]


def test_ohne_netz_kein_browser(sc, monkeypatch):
    mod, calls = sc
    monkeypatch.setattr(mod, "internet_reachable", lambda *a, **k: False)
    r = mod.fetch_price(URL)
    assert calls == []
    assert r["ok"] is False
    assert r.get("offline") is True
    assert r["note"] == "Keine Internetverbindung"


def test_netzpruefung_ohne_erreichbares_ziel(monkeypatch):
    """internet_reachable() meldet nur dann True, wenn eines der festen Ziele
    eine Verbindung annimmt — ein OSError je Ziel bedeutet: kein Netz."""
    def boom(*a, **k):
        raise OSError("network unreachable")
    monkeypatch.setattr(scraper.socket, "create_connection", boom)
    assert scraper.internet_reachable(timeout=0.1) is False


def test_option_steht_in_den_einstellungen():
    settings = importlib.import_module("settings")
    typ, default, _extra, group = settings.FIELDS["browser_fallback"][:4]
    assert (typ, default, group) == ("bool", True, "poll")


# ── Hängengebliebene Fallback-Browser ────────────────────────────────────────
# Der Fallback schließt den Browser im `finally`. Bleibt der Aufruf im Netz hängen
# oder stirbt der Thread darunter weg, überlebt Chromium bis zum Neustart — mit
# mehreren hundert MB, die niemand mehr benutzt. Genau das sieht dann aus, als
# bräuchte das Add-on dauerhaft so viel Speicher.

def test_marker_haengt_am_browser_aufruf():
    """Ohne eindeutigen Marker ließe sich unser Chromium nicht von einem fremden
    im selben Namensraum unterscheiden — dann dürfte gar nichts aufgeräumt werden."""
    assert scraper.BROWSER_MARKER.startswith("--")
    import inspect
    src = inspect.getsource(scraper._fetch_price_browser)
    assert "BROWSER_MARKER" in src and "args=[" in src


def test_browser_busy_meldet_laufenden_abruf(monkeypatch):
    assert scraper.browser_busy() is False
    scraper._browser_running += 1
    try:
        assert scraper.browser_busy() is True
    finally:
        scraper._browser_running -= 1
    assert scraper.browser_busy() is False
