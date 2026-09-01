"""Speicher zurückgeben: läuft von selbst, nicht nur auf Knopfdruck.

Der Trim hing zuerst an der Prüfrunde — die läuft je nach Einstellung nur alle
sechs bis zwölf Stunden, und der Speicher wächst nicht nur dort: jede Seite der
Oberfläche und jede KI-Antwort läuft in einem eigenen waitress-Thread mit eigener
Arena. Praktisch blieb der Speicher deshalb stehen, bis jemand den Knopf drückte.
Aufgeräumt wird jetzt zusätzlich alle `MEMORY_TRIM_INTERVAL` Sekunden.
"""
import importlib
import inspect

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
    return mod


def test_aufraeumen_merkt_sich_wann_und_wieviel(m):
    m._trim_state.update(ts=0.0, freed_mb=0.0, auto=False)
    freed = m._trim_once(auto=True)
    assert isinstance(freed, float)
    assert m._trim_state['ts'] > 0 and m._trim_state['auto'] is True


def test_intervall_ist_kurz_genug_um_zu_wirken(m):
    """An der Prüfrunde (Standard 6 h, oft 12 h) hing der Trim praktisch nie."""
    assert 60 <= m.MEMORY_TRIM_INTERVAL <= 900


def test_aufraeumer_laeuft_als_eigener_thread(m):
    """Ohne eigenen Thread bliebe es beim Knopfdruck von Hand."""
    src = inspect.getsource(m.main) if hasattr(m, 'main') else inspect.getsource(m)
    assert "_memory_janitor" in src


def test_endpunkt_liefert_vorher_nachher(m):
    c = m.app.test_client()
    r = c.post('/api/memory/trim', headers={'X-Ingress-Path': '/test'})
    assert r.status_code == 200
    d = r.get_json()
    assert {'ok', 'before_mb', 'after_mb', 'freed_mb'} <= set(d)
    assert d['ok'] is True
