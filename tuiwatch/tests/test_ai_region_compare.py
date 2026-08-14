"""Tests für POST /api/ai/region-compare — Regionen vergleichen (2-5 Ziele + Monat).

`_ai_call` wird gemonkeypatcht (kein Netz); geprüft wird die Route-/Cache-/
Verlaufs-Verdrahtung und der Prompt-Inhalt, nicht die tatsächliche KI-Antwort.
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
    monkeypatch.setattr(m, "load_config", lambda: {"anthropic_api_key": "sk-test",
                                                   "anthropic_model": "claude-haiku-4-5"})
    m.app.config["TESTING"] = True
    return m.app.test_client()


@pytest.fixture
def calls(m, monkeypatch):
    """`_ai_call` abfangen — kein Netz, aber der Prompt bleibt prüfbar."""
    seen = []

    def _fake(api_key, model, prompt, **kw):
        seen.append(dict(kw, prompt=prompt, model=model))
        return "Vergleichstext", {"input_tokens": 10, "output_tokens": 20}, None

    monkeypatch.setattr(m, "_ai_call", _fake)
    return seen


_ROME = {"giata": 1001, "label": "Rom"}
_PALMA = {"giata": 1002, "label": "Palma de Mallorca"}
_KRETA = {"giata": 1003, "label": "Kreta"}


def _cmp(client, regions, month=6):
    return client.post("/api/ai/region-compare", json={"regions": regions, "month": month})


def test_fewer_than_two_regions_rejected(m, client, calls):
    r = _cmp(client, [_ROME])
    assert r.status_code == 400
    assert not calls


def test_more_than_five_regions_truncated(m, client, calls):
    regions = [{"giata": i, "label": f"Ziel {i}"} for i in range(1, 8)]
    r = _cmp(client, regions)
    assert r.status_code == 200
    assert "Ziel 6" not in calls[-1]["prompt"] and "Ziel 7" not in calls[-1]["prompt"]
    assert "Ziel 1" in calls[-1]["prompt"] and "Ziel 5" in calls[-1]["prompt"]


@pytest.mark.parametrize("month", [0, 13, "juni", None])
def test_invalid_month_rejected(m, client, calls, month):
    r = _cmp(client, [_ROME, _PALMA], month=month)
    assert r.status_code == 400
    assert not calls


def test_valid_request_returns_summary_and_saves_history(m, client, calls):
    r = _cmp(client, [_ROME, _PALMA, _KRETA], month=6)
    assert r.status_code == 200
    d = r.get_json()
    assert d["summary"] == "Vergleichstext" and d["cached"] is False
    with m.db() as con:
        row = con.execute("SELECT kind, title FROM ai_analyses ORDER BY id DESC").fetchone()
    assert row["kind"] == "region_compare"
    assert "Rom" in row["title"] and "Kreta" in row["title"]


def test_prompt_names_all_regions_and_the_chosen_month(m, client, calls):
    _cmp(client, [_ROME, _PALMA], month=12)
    prompt = calls[-1]["prompt"]
    assert "Rom" in prompt and "Palma de Mallorca" in prompt
    assert "Dezember" in prompt
    assert "Sicherheit" in prompt and "Preisniveau" in prompt and "Wetter" in prompt


def test_second_identical_call_is_cached_and_skips_ai_call(m, client, calls):
    _cmp(client, [_ROME, _PALMA], month=6)
    assert len(calls) == 1
    r2 = _cmp(client, [_PALMA, _ROME], month=6)  # umgekehrte Reihenfolge → gleicher Key
    assert r2.status_code == 200 and r2.get_json()["cached"] is True
    assert len(calls) == 1  # kein zweiter _ai_call


def test_different_month_is_not_cached_together(m, client, calls):
    _cmp(client, [_ROME, _PALMA], month=6)
    r2 = _cmp(client, [_ROME, _PALMA], month=7)
    assert r2.get_json()["cached"] is False
    assert len(calls) == 2


def test_missing_api_key_returns_no_api_key(m, monkeypatch):
    monkeypatch.setattr(m, "_auth_ok", lambda req: True)
    monkeypatch.setattr(m, "load_config", lambda: {})
    m.app.config["TESTING"] = True
    c = m.app.test_client()
    r = _cmp(c, [_ROME, _PALMA])
    assert r.status_code == 400 and r.get_json()["error"] == "no_api_key"


def test_history_repeat_knows_the_new_kind(m):
    """Ohne Eintrag in _AI_RETRY_MARKDOWN_CONFIG ließe sich ein Regionen-Vergleich
    im KI-Verlauf nicht mit einem anderen Anbieter wiederholen."""
    ai_routes = importlib.import_module("ai_routes")
    assert "region_compare" in ai_routes._AI_RETRY_MARKDOWN_CONFIG
    assert ai_routes._AI_RETRY_MARKDOWN_CONFIG["region_compare"]["use_web_search"] is True


def test_region_compare_supports_followup_questions(m):
    """Freies Markdown wie 'compare' — darf NICHT in
    _AI_FOLLOWUP_UNSUPPORTED_KINDS stehen."""
    ai_routes = importlib.import_module("ai_routes")
    assert "region_compare" not in ai_routes._AI_FOLLOWUP_UNSUPPORTED_KINDS


# — Editierbarer Prompt (Fußzeile „⚙ KI-Prompts“, wie bei Reiseberater/Hotelvergleich) —

def test_region_compare_is_a_registered_prompt_feature(m):
    ai_routes = importlib.import_module("ai_routes")
    assert "region_compare" in ai_routes._PROMPT_FEATURES
    assert ai_routes._PROMPT_FEATURES["region_compare"] == ai_routes._DEFAULT_REGION_COMPARE_INSTRUCTIONS


def test_prompt_settings_lists_region_compare(m, client):
    d = client.get("/api/ai/prompt-settings").get_json()
    assert "region_compare" in d
    assert d["region_compare"]["enabled"] is False
    assert "Wetter im gewählten Monat" in d["region_compare"]["default"]


def test_custom_instructions_are_used_when_enabled(m, client, calls):
    client.post("/api/ai/prompt-settings", json={
        "region_compare": {"enabled": True, "text": "Nur diese eine Anweisung."}})
    _cmp(client, [_ROME, _PALMA], month=6)
    prompt = calls[-1]["prompt"]
    assert "Nur diese eine Anweisung." in prompt
    assert "Wetter im gewählten Monat" not in prompt  # Standardtext wurde ersetzt


def test_custom_instructions_use_their_own_cache_bucket(m, client, calls):
    """Unterschiedlicher Prompt-Text darf nicht denselben Cache-Treffer liefern —
    sonst bekäme man nach einem Speichern eine veraltete Antwort serviert."""
    _cmp(client, [_ROME, _PALMA], month=6)
    assert len(calls) == 1
    client.post("/api/ai/prompt-settings", json={
        "region_compare": {"enabled": True, "text": "Andere Anweisung."}})
    r2 = _cmp(client, [_ROME, _PALMA], month=6)
    assert r2.get_json()["cached"] is False
    assert len(calls) == 2
