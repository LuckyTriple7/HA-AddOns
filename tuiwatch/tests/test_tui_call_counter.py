"""Tests für den TUI-API-Aufrufzähler im Footer (`GET /api/tui-calls`).

Zählt wird über scraper._get/_post (Wrapper um requests.get/post, siehe
scraper.py) → app._record_tui_call() → meta-Key 'tui_call_count' mit
Tages-Schlüssel, der beim Datumswechsel den alten Stand verwirft (kein
Cronjob nötig, gleiches Muster wie die KI-Nutzungs-Buckets in ai_routes.py).
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
    mod.DB_PATH = str(tmp_path / "tuiwatch.db")
    mod.init_db()
    return mod


@pytest.fixture
def client(m, monkeypatch):
    monkeypatch.setattr(m, "_auth_ok", lambda req: True)
    m.app.config["TESTING"] = True
    return m.app.test_client()


def test_counter_starts_at_zero(m, client):
    r = client.get("/api/tui-calls")
    assert r.status_code == 200
    assert r.get_json()["count"] == 0


def test_record_tui_call_increments(m):
    assert m._record_tui_call() == 1
    assert m._record_tui_call() == 2
    assert m._tui_call_count_today() == 2


def test_route_reflects_recorded_calls(m, client):
    m._record_tui_call()
    m._record_tui_call()
    m._record_tui_call()
    d = client.get("/api/tui-calls").get_json()
    assert d["count"] == 3


def test_resets_on_a_new_day(m, monkeypatch):
    m._record_tui_call()
    m._record_tui_call()
    assert m._tui_call_count_today() == 2
    monkeypatch.setattr(m.time, "strftime", lambda fmt: "2099-01-01")
    assert m._tui_call_count_today() == 0
    # Der erste Aufruf am neuen Tag startet wieder bei 1, statt weiterzuzählen
    assert m._record_tui_call() == 1


def test_scraper_get_and_post_increment_the_counter(m, monkeypatch):
    """End-to-End: scraper._get/_post (statt requests.get/post direkt) sind der
    einzige Weg, wie TUI-API-Aufrufe im Code ausgelöst werden — siehe die
    projektweite Ersetzung in scraper.py."""
    scraper = importlib.import_module("scraper")

    class _FakeResp:
        status_code = 200

        def json(self):
            return {}

    monkeypatch.setattr(scraper.requests, "get", lambda *a, **k: _FakeResp())
    monkeypatch.setattr(scraper.requests, "post", lambda *a, **k: _FakeResp())

    scraper._get("https://example.invalid")
    scraper._get("https://example.invalid")
    scraper._post("https://example.invalid")

    assert m._tui_call_count_today() == 3


def test_scraper_count_call_never_raises_without_a_configured_db(monkeypatch):
    """`_count_call` importiert app.py lazy und schluckt Fehler — ein fehlendes
    DB-Setup (z. B. in den reinen Parsing-Tests) darf den eigentlichen
    TUI-Aufruf nie zum Absturz bringen."""
    scraper = importlib.import_module("scraper")
    scraper._count_call()  # darf nicht werfen, unabhängig vom DB-Zustand
