"""Tests für die Konsole im UI (`/api/logs`) und den In-Memory-Log-Puffer.

Der Puffer fasste ursprünglich 200 Zeilen und wurde gar nicht ausgeliefert — ein
einziger Barometer-Lauf schreibt bei vielen gespeicherten Suchen schon über hundert
Zeilen, der interessante Teil war also raus, bevor man nachsehen konnte.
"""
import importlib
import logging

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
    mod.DB_PATH = str(tmp_path / "tuiwatch.db")
    mod.init_db()
    mod._log_buffer.clear()
    mod._warn_buffer.clear()
    return mod


@pytest.fixture
def client(m, monkeypatch):
    monkeypatch.setattr(m, "_auth_ok", lambda req: True)
    m.app.config["TESTING"] = True
    return m.app.test_client()


def _log(m, level, msg):
    logging.getLogger("app").log(getattr(logging, level), msg)


def test_buffer_holds_far_more_than_two_hundred_lines(m):
    assert m._log_buffer.maxlen >= 2000
    for i in range(2500):
        _log(m, "INFO", f"Zeile {i}")
    assert len(m._log_buffer) == m._log_buffer.maxlen
    assert m._log_buffer[-1]["msg"].endswith("Zeile 2499")


def test_logs_endpoint_returns_newest_first(m, client):
    for i in range(3):
        _log(m, "INFO", f"Zeile {i}")
    d = client.get("/api/logs").get_json()
    assert [it["msg"][-1] for it in d["items"]] == ["2", "1", "0"]
    assert d["total"] == 3 and d["capacity"] == m._log_buffer.maxlen


def test_logs_level_filter(m, client):
    _log(m, "INFO", "harmlos")
    _log(m, "WARNING", "achtung")
    _log(m, "ERROR", "kaputt")
    msgs = [it["msg"] for it in client.get("/api/logs?level=WARNING").get_json()["items"]]
    assert any("achtung" in x for x in msgs) and any("kaputt" in x for x in msgs)
    assert not any("harmlos" in x for x in msgs)


def test_logs_text_filter_is_case_insensitive(m, client):
    _log(m, "INFO", "Messreihe „Teneriffa“: 259 Hotels erfasst")
    _log(m, "INFO", "Preis geprüft")
    items = client.get("/api/logs?q=messreihe").get_json()["items"]
    assert len(items) == 1 and "Teneriffa" in items[0]["msg"]


def test_logs_requires_auth(m, monkeypatch):
    monkeypatch.setattr(m, "_auth_ok", lambda req: False)
    m.app.config["TESTING"] = True
    assert m.app.test_client().get("/api/logs").status_code == 401


def test_console_endpoint_returns_only_the_tail(m, client):
    """Das Overlay-Panel pollt alle 2 Sekunden und rendert jedes Mal neu — es darf
    nicht den kompletten 2000-Zeilen-Puffer bekommen."""
    for i in range(800):
        _log(m, "INFO", f"Zeile {i}")
    d = client.get("/api/console").get_json()
    assert len(d["lines"]) == 300 and d["total"] == 800
    assert d["lines"][-1]["msg"].endswith("Zeile 799")     # älteste zuerst
    assert len(client.get("/api/console?limit=500").get_json()["lines"]) == 500
    assert len(client.get("/api/console?limit=1").get_json()["lines"]) == 50   # Boden


def test_warnings_still_land_in_their_own_buffer(m, client):
    _log(m, "INFO", "harmlos")
    _log(m, "ERROR", "kaputt")
    errors = [it["msg"] for it in client.get("/api/errors").get_json()["items"]]
    assert len(errors) == 1 and "kaputt" in errors[0]
