"""Tests für fra_board_client.py (FRA-Zielliste über das Tagesbord einer
Drittseite, siehe Modul-Docstring für die Herkunft/Grenzen).

Netzwerk wird gemockt; geprüft werden die Eigenheiten, die im echten Betrieb
weh tun: AIRail-Bahnzubringer (Aachen/Berlin/Basel/Hamburg — live im Board
gesehen) im selben Feld wie echte Ziele, das rollierende Fenster (nur der
heutige Tag kommt vom Board, ältere Ziele müssen erhalten bleiben, verjährte
raus) und die Persistenz über Neustarts hinweg.
"""
import json

import pytest

import fra_board_client as fb


@pytest.fixture(autouse=True)
def _reset_state(tmp_path, monkeypatch):
    """Eigener State-Pfad je Test (kein Zugriff auf echtes TUIWATCH_DATA) +
    Modul-State zurücksetzen."""
    monkeypatch.setattr(fb, "_STATE_PATH", str(tmp_path / "fra_board.json"))
    fb._seen = {}
    fb._loaded = False
    fb._last_fetch_ts = 0.0
    yield


def _board(*dests):
    """Board-JSON wie das echte Drittseiten-API: {"data":[{"2": "Ort (CODE)"}]}."""
    return {"data": [{"2": f"{name} ({code})"} for name, code in dests]}


class _Resp:
    def __init__(self, data, status=200):
        self._d, self.status_code = data, status

    def json(self):
        return self._d


def test_dedup_and_filters_airail(monkeypatch):
    """Mehrfachnennungen (Codeshares) dedupliziert; Bahnzubringer (Name
    enthält 'Bahnhof') fliegt nicht wirklich, raus."""
    data = _board(
        ("Palma de Mallorca", "PMI"), ("Palma de Mallorca", "PMI"),
        ("Aachen Hauptbahnhof", "XHJ"), ("Mauritius", "MRU"),
    )
    monkeypatch.setattr(fb.requests, "get", lambda *a, **kw: _Resp(data))
    assert fb.refresh() is True
    dest = fb.list_destinations()
    codes = {d["code"] for d in dest}
    assert codes == {"PMI", "MRU"}
    assert "XHJ" not in codes


def test_rolling_window_keeps_and_expires(monkeypatch):
    """Ein Ziel, das heute nicht im Board steht, bleibt innerhalb des
    Fensters erhalten; nach ROLLING_DAYS ohne erneute Sichtung fliegt es
    raus (könnte eingestellt sein)."""
    monkeypatch.setattr(fb.requests, "get",
                       lambda *a, **kw: _Resp(_board(("Mauritius", "MRU"))))
    fb.refresh()
    assert {d["code"] for d in fb.list_destinations()} == {"MRU"}

    # Anderer Tag, MRU heute nicht im Board — bleibt trotzdem im Fenster
    monkeypatch.setattr(fb.requests, "get",
                       lambda *a, **kw: _Resp(_board(("Palma de Mallorca", "PMI"))))
    fb.refresh()
    assert {d["code"] for d in fb.list_destinations()} == {"MRU", "PMI"}

    # MRU künstlich auf "vor der Fenstergrenze" zurückdatieren -> fliegt beim
    # nächsten Refresh raus
    fb._seen["MRU"]["last_seen"] = "2020-01-01"
    fb.refresh()
    assert {d["code"] for d in fb.list_destinations()} == {"PMI"}


def test_persists_across_reload(monkeypatch, tmp_path):
    """Zustand landet auf Platte und wird beim nächsten Prozess (simuliert
    über _loaded=False + geleerten _seen) wieder eingelesen."""
    monkeypatch.setattr(fb.requests, "get",
                       lambda *a, **kw: _Resp(_board(("Mauritius", "MRU"))))
    fb.refresh()
    assert (tmp_path / "fra_board.json").exists()

    fb._seen = {}
    fb._loaded = False
    fb._ensure_loaded()
    assert "MRU" in fb._seen


def test_list_destinations_none_when_never_loaded(monkeypatch):
    """Kein Cache-Stand + Abruf schlägt fehl -> None (nicht leere Liste),
    analog zu str_/muc_flights_client bei technischem Fehler."""
    def _boom(*a, **kw):
        raise ConnectionError("kein Netz")
    monkeypatch.setattr(fb.requests, "get", _boom)
    assert fb.list_destinations() is None


def test_fail_soft_keeps_old_state_on_fetch_error(monkeypatch):
    """Board schon mal erfolgreich geladen, dann schlägt ein späterer Abruf
    fehl -> alter Stand bleibt bestehen statt leer/None (Fail-Soft, wie bei
    den anderen Flugplan-Clients)."""
    monkeypatch.setattr(fb.requests, "get",
                       lambda *a, **kw: _Resp(_board(("Mauritius", "MRU"))))
    fb.refresh()
    fb._last_fetch_ts = 0.0  # naechster Aufruf gilt wieder als "stale"

    def _boom(*a, **kw):
        raise ConnectionError("kein Netz")
    monkeypatch.setattr(fb.requests, "get", _boom)
    dest = fb.list_destinations()
    assert {d["code"] for d in dest} == {"MRU"}
