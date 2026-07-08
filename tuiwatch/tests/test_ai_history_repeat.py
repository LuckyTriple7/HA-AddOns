"""Tests fuer "KI-Verlauf wiederholen" (POST /api/ai/history/<id>/repeat):
gespeicherter Prompt wird mit gewaehltem Provider (Claude/Gemini) erneut
verschickt, Ergebnis landet als NEUER ai_analyses-Eintrag. `_ai_request` wird
direkt gemockt - kein echter Anthropic/Gemini-Aufruf noetig."""
import importlib
import json

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
    return mod


def _write_options(m, **opts):
    with open(m.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(opts, f)


def _insert_history(m, kind="ask", title="Testfrage", model="claude-haiku-4-5",
                    summary="Alte Antwort", prompt="Alter Prompt-Text", ts=1000):
    with m.db() as con:
        cur = con.execute(
            "INSERT INTO ai_analyses (kind, title, model, summary, usage, ts, prompt) "
            "VALUES (?,?,?,?,?,?,?)",
            (kind, title, model, summary, "{}", ts, prompt))
        return cur.lastrowid


def _mock_ai_text(m, monkeypatch, text="Neue Antwort", calls=None):
    calls = calls if calls is not None else []

    def fake(api_key, model, prompt, *, max_tokens, log_ctx, use_web_search=True, output_schema=None):
        calls.append({"api_key": api_key, "model": model, "prompt": prompt,
                      "use_web_search": use_web_search, "output_schema": output_schema})
        return text, {"input_tokens": 10, "output_tokens": 5,
                      "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}, None

    monkeypatch.setattr(m, "_ai_request", fake)
    return calls


# ── Migration + _save_ai_analysis ──────────────────────────────────────────────

def test_migration_adds_prompt_column(m):
    cols = {r["name"] for r in m.db().execute("PRAGMA table_info(ai_analyses)").fetchall()}
    assert "prompt" in cols


def test_save_ai_analysis_persists_prompt(m):
    aid = m._save_ai_analysis("ask", "Titel", "claude-haiku-4-5", "Text", {}, "Mein Prompt")
    with m.db() as con:
        row = con.execute("SELECT prompt FROM ai_analyses WHERE id=?", (aid,)).fetchone()
    assert row["prompt"] == "Mein Prompt"


def test_save_ai_analysis_prompt_defaults_empty(m):
    aid = m._save_ai_analysis("ask", "Titel", "claude-haiku-4-5", "Text", {})
    with m.db() as con:
        row = con.execute("SELECT prompt FROM ai_analyses WHERE id=?", (aid,)).fetchone()
    assert row["prompt"] == ""


# ── _ai_config_for ──────────────────────────────────────────────────────────────

def test_ai_config_for_ignores_active_provider(m):
    _write_options(m, anthropic_api_key="ak", anthropic_model="claude-sonnet-5",
                   gemini_api_key="gk", gemini_model="gemini-3.5-flash", ai_provider="gemini")
    m._meta_set("ai_provider_active", "gemini")   # "aktiver" Provider ist gemini
    assert m._ai_config_for("anthropic") == ("ak", "claude-sonnet-5")
    assert m._ai_config_for("gemini") == ("gk", "gemini-3.5-flash")


def test_ai_config_for_empty_key_when_not_configured(m):
    _write_options(m, anthropic_api_key="ak")
    api_key, _ = m._ai_config_for("gemini")
    assert api_key == ""


# ── Verlaufsliste: has_prompt ────────────────────────────────────────────────────

def test_history_list_has_prompt_flag(m):
    with_prompt = _insert_history(m, title="Mit Prompt", prompt="etwas")
    without_prompt = _insert_history(m, title="Ohne Prompt", prompt="")
    c = m.app.test_client()
    items = {it["id"]: it for it in c.get("/api/ai/history", headers=ING).get_json()["items"]}
    assert items[with_prompt]["has_prompt"] == 1
    assert items[without_prompt]["has_prompt"] == 0


# ── Route /api/ai/history/<id>/repeat ────────────────────────────────────────────

def test_repeat_markdown_kind_creates_new_entry(m, monkeypatch):
    _write_options(m, anthropic_api_key="ak", anthropic_model="claude-sonnet-5")
    calls = _mock_ai_text(m, monkeypatch, text="Frisch generiert")
    old_id = _insert_history(m, kind="ask", title="Frage", prompt="Der alte Prompt")
    c = m.app.test_client()

    r = c.post(f"/api/ai/history/{old_id}/repeat", headers=ING, json={"provider": "anthropic"})
    assert r.status_code == 200
    d = r.get_json()
    assert d["summary"] == "Frisch generiert"
    assert "result" not in d
    assert len(calls) == 1
    assert calls[0]["prompt"] == "Der alte Prompt"
    assert calls[0]["use_web_search"] is True   # 'ask' Default laut _AI_RETRY_MARKDOWN_CONFIG

    with m.db() as con:
        rows = con.execute("SELECT id, kind, title, summary, prompt FROM ai_analyses ORDER BY id").fetchall()
    assert len(rows) == 2   # Original bleibt, neuer Eintrag kommt dazu
    assert rows[0]["id"] == old_id and rows[0]["summary"] == "Alte Antwort"
    new_row = rows[1]
    assert new_row["id"] == d["id"] != old_id
    assert new_row["kind"] == "ask" and new_row["title"] == "Frage"
    assert new_row["summary"] == "Frisch generiert"
    assert new_row["prompt"] == "Der alte Prompt"


def test_repeat_calendar_outlook_uses_no_web_search(m, monkeypatch):
    _write_options(m, anthropic_api_key="ak")
    calls = _mock_ai_text(m, monkeypatch)
    old_id = _insert_history(m, kind="calendar_outlook", title="Hotel X", prompt="Kalenderprompt")
    c = m.app.test_client()
    r = c.post(f"/api/ai/history/{old_id}/repeat", headers=ING, json={"provider": "anthropic"})
    assert r.status_code == 200
    assert calls[0]["use_web_search"] is False


def test_repeat_structured_kind_creates_new_entry(m, monkeypatch):
    _write_options(m, gemini_api_key="gk", gemini_model="gemini-3.1-pro")
    result = {"score": 72, "empfehlung": "jetzt_buchen", "vertrauen": 80,
              "erwartung_7_tage": "steigend", "erwartung_30_tage": "gleich",
              "begruendung": [{"typ": "daten", "text": "Preis stabil"}]}
    calls = _mock_ai_text(m, monkeypatch, text=json.dumps(result, ensure_ascii=False))
    old_id = _insert_history(m, kind="booking_score", title="Hotel Y",
                             summary=json.dumps({"score": 10}), prompt="Score-Prompt")
    c = m.app.test_client()

    r = c.post(f"/api/ai/history/{old_id}/repeat", headers=ING, json={"provider": "gemini"})
    assert r.status_code == 200
    d = r.get_json()
    assert d["result"] == result
    assert "summary" not in d
    assert calls[0]["output_schema"] == m._BOOKING_SCORE_SCHEMA
    assert calls[0]["use_web_search"] is True

    with m.db() as con:
        n = con.execute("SELECT COUNT(*) c FROM ai_analyses").fetchone()["c"]
    assert n == 2


def test_repeat_invalid_provider(m):
    old_id = _insert_history(m)
    c = m.app.test_client()
    r = c.post(f"/api/ai/history/{old_id}/repeat", headers=ING, json={"provider": "chatgpt"})
    assert r.status_code == 400 and r.get_json()["error"] == "invalid_provider"


def test_repeat_not_found(m):
    c = m.app.test_client()
    r = c.post("/api/ai/history/9999/repeat", headers=ING, json={"provider": "anthropic"})
    assert r.status_code == 404


def test_repeat_no_prompt_on_legacy_entry(m):
    old_id = _insert_history(m, prompt="")
    _write_options(m, anthropic_api_key="ak")
    c = m.app.test_client()
    r = c.post(f"/api/ai/history/{old_id}/repeat", headers=ING, json={"provider": "anthropic"})
    assert r.status_code == 400 and r.get_json()["error"] == "no_prompt"


def test_repeat_no_api_key_for_chosen_provider(m):
    _write_options(m, anthropic_api_key="ak")   # nur Anthropic konfiguriert
    old_id = _insert_history(m)
    c = m.app.test_client()
    r = c.post(f"/api/ai/history/{old_id}/repeat", headers=ING, json={"provider": "gemini"})
    assert r.status_code == 400 and r.get_json()["error"] == "no_api_key"


def test_repeat_propagates_ai_failure(m, monkeypatch):
    _write_options(m, anthropic_api_key="ak")

    def fake_fail(api_key, model, prompt, *, max_tokens, log_ctx, use_web_search=True, output_schema=None):
        return None, None, "failed"

    monkeypatch.setattr(m, "_ai_request", fake_fail)
    old_id = _insert_history(m)
    c = m.app.test_client()
    r = c.post(f"/api/ai/history/{old_id}/repeat", headers=ING, json={"provider": "anthropic"})
    assert r.status_code == 502 and r.get_json()["error"] == "ai_failed"
    with m.db() as con:
        n = con.execute("SELECT COUNT(*) c FROM ai_analyses").fetchone()["c"]
    assert n == 1   # kein neuer Eintrag bei Fehler


# ── Backup Export/Import ─────────────────────────────────────────────────────────

def test_backup_export_includes_prompt(m):
    _insert_history(m, title="Mit Prompt", prompt="der prompt text")
    c = m.app.test_client()
    import io
    import zipfile
    b = c.get("/api/backup", headers=ING)
    data = json.loads(zipfile.ZipFile(io.BytesIO(b.data)).read("data.json"))
    assert data["ai_analyses"][0]["prompt"] == "der prompt text"


def test_backup_import_missing_prompt_key_defaults_empty(m):
    c = m.app.test_client()
    payload = {"tuiwatch_backup": 4, "ai_analyses": [
        {"kind": "ask", "title": "Alt-Backup ohne prompt", "model": "claude-haiku-4-5",
         "summary": "alte Antwort", "usage": "{}", "ts": 500},
    ]}
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("data.json", json.dumps(payload))
    buf.seek(0)
    r = c.post("/api/restore", headers=ING,
              data={"file": (buf, "old-backup.zip")}, content_type="multipart/form-data")
    assert r.status_code == 200
    with m.db() as con:
        row = con.execute("SELECT prompt FROM ai_analyses WHERE title=?",
                          ("Alt-Backup ohne prompt",)).fetchone()
    assert row["prompt"] == ""   # nicht NULL, nicht Crash
