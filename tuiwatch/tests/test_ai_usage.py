"""Tests für die KI-Kosten-Zähler (gesamt/heute/Monat) — bleiben dauerhaft in
`meta` gespeichert, Tages-/Monatsbucket setzt sich bei Periodenwechsel zurück.
"""
import importlib
import time

import pytest

pytest.importorskip("flask")


@pytest.fixture
def app_mod(tmp_path, monkeypatch):
    monkeypatch.setenv("TUIWATCH_DATA", str(tmp_path))
    monkeypatch.setenv("TUIWATCH_BASE", str(tmp_path))
    try:
        m = importlib.import_module("app")
    except Exception as exc:
        pytest.skip(f"app nicht importierbar: {exc}")
    importlib.reload(m)
    m.DB_PATH = str(tmp_path / "tuiwatch.db")
    m.init_db()
    return m


def _usage(**kw):
    base = {"input_tokens": 1000, "output_tokens": 500,
            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    base.update(kw)
    return base


def test_usage_starts_empty(app_mod):
    totals = app_mod._ai_usage_totals()
    assert totals["calls"] == 0
    assert totals["today"]["calls"] == 0
    assert totals["month"]["calls"] == 0


def test_record_usage_updates_all_three_buckets(app_mod):
    totals = app_mod._record_ai_usage("claude-haiku-4-5", _usage())
    assert totals["calls"] == 1
    assert totals["today"]["calls"] == 1
    assert totals["month"]["calls"] == 1
    assert totals["estimated_usd"] > 0


def test_usage_accumulates_across_calls(app_mod):
    app_mod._record_ai_usage("claude-haiku-4-5", _usage())
    totals = app_mod._record_ai_usage("claude-haiku-4-5", _usage())
    assert totals["calls"] == 2
    assert totals["today"]["calls"] == 2
    assert totals["input_tokens"] == 2000


def test_totals_survive_reimport_like_a_restart(app_mod, tmp_path, monkeypatch):
    app_mod._record_ai_usage("claude-haiku-4-5", _usage())
    monkeypatch.setenv("TUIWATCH_DATA", str(tmp_path))
    monkeypatch.setenv("TUIWATCH_BASE", str(tmp_path))
    m2 = importlib.reload(app_mod)
    m2.DB_PATH = str(tmp_path / "tuiwatch.db")
    totals = m2._ai_usage_totals()
    assert totals["calls"] == 1  # ueberlebt "Neustart" (Modul-Reload, gleiche DB-Datei)


def test_daily_bucket_resets_on_new_day(app_mod):
    app_mod._record_ai_usage("claude-haiku-4-5", _usage())
    assert app_mod._ai_usage_totals()["today"]["calls"] == 1
    # Simuliert Tageswechsel: Bucket auf ein altes Datum manipulieren
    old = app_mod._meta_get("ai_usage_today")
    import json
    data = json.loads(old)
    data["date"] = "2000-01-01"
    app_mod._meta_set("ai_usage_today", json.dumps(data))
    assert app_mod._ai_usage_totals()["today"]["calls"] == 0
    # Gesamt-Zaehler bleibt davon unberuehrt
    assert app_mod._ai_usage_totals()["calls"] == 1


def test_ai_usage_endpoint(app_mod):
    c = app_mod.app.test_client()
    ING = {"X-Ingress-Path": "/test"}
    app_mod._record_ai_usage("claude-haiku-4-5", _usage())
    r = c.get("/api/ai/usage", headers=ING)
    assert r.status_code == 200
    data = r.get_json()
    assert data["calls"] == 1
    assert "today" in data and "month" in data
