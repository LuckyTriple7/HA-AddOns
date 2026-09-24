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


def test_analyse_nennt_speicherhalter(m, monkeypatch):
    """Belegt oder zerstückelt, und wer hält es — ohne das bleibt nur Raten."""
    m._test_ballast = [('x' * 1024) + str(i) for i in range(3000)]   # ~3 MB, je eigener String
    monkeypatch.setattr(m, '_require_api', lambda: None)
    d = m.app.test_client().get('/api/memory/analyze').get_json()
    names = [h['name'] for h in d['holders']]
    assert 'app._test_ballast' in names
    assert d['types'] and d['gc_objects'] > 0
    assert 'malloc' in d and 'pymalloc' in d


def test_run_sh_nutzt_glibc_malloc():
    """pymalloc hielt nach einer Spitze 401 MB frei, aber unerreichbar für den Trim."""
    from pathlib import Path
    run = (Path(__file__).resolve().parent.parent / 'run.sh').read_text(encoding='utf-8')
    assert 'export PYTHONMALLOC=malloc' in run


def test_speicherspitze_einer_anfrage_steht_im_log(m, monkeypatch, caplog):
    import logging
    werte = iter([100.0, 250.0])
    monkeypatch.setattr(m, '_rss_mb', lambda: next(werte, 250.0))
    with caplog.at_level(logging.INFO):
        m.app.test_client().get('/health')
    assert any('Anfrage GET /health: +150 MB' in r.getMessage() for r in caplog.records)
