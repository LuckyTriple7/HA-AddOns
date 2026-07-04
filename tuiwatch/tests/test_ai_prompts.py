"""Tests für die editierbaren KI-Prompt-Vorlagen (Reiseberater + Hotelvergleich):
Fakten/Instruktionen-Split, Sicherheitsklauseln bleiben immer fix, Persistenz über
/api/ai/prompt-settings.
"""
import importlib

import pytest

pytest.importorskip("flask")

ING = {"X-Ingress-Path": "/test"}


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


def test_prompt_instructions_default_when_nothing_saved(app_mod):
    assert app_mod._prompt_instructions("advisor", "DEFAULT") == "DEFAULT"


def test_prompt_instructions_uses_custom_when_enabled(app_mod):
    app_mod._meta_set("custom_prompt_advisor_enabled", "1")
    app_mod._meta_set("custom_prompt_advisor_text", "MEIN TEXT")
    assert app_mod._prompt_instructions("advisor", "DEFAULT") == "MEIN TEXT"


def test_prompt_instructions_falls_back_when_enabled_but_empty(app_mod):
    app_mod._meta_set("custom_prompt_advisor_enabled", "1")
    app_mod._meta_set("custom_prompt_advisor_text", "   ")
    assert app_mod._prompt_instructions("advisor", "DEFAULT") == "DEFAULT"


def test_prompt_instructions_ignores_custom_when_disabled(app_mod):
    app_mod._meta_set("custom_prompt_advisor_enabled", "0")
    app_mod._meta_set("custom_prompt_advisor_text", "MEIN TEXT")
    assert app_mod._prompt_instructions("advisor", "DEFAULT") == "DEFAULT"


def test_advisor_prompt_keeps_safety_clauses_with_custom_instructions(app_mod):
    app_mod._meta_set("custom_prompt_advisor_enabled", "1")
    app_mod._meta_set("custom_prompt_advisor_text", "Nur diese eine Anweisung.")
    profile = {"region": "Europa", "excluded_countries": ["Türkei"],
               "travel_type": ["Pauschalreise (TUI)"]}
    prompt = app_mod._advisor_prompt(profile)
    assert "Ziel-Region: Europa" in prompt
    assert "Türkei" in prompt  # Länder-Ausschluss-Klausel weiterhin drin
    assert "TUI" in prompt  # Pauschalreise-Klausel weiterhin drin
    assert "Reisewarnung" in prompt  # Reisewarnungs-Check immer drin
    assert "Nur diese eine Anweisung." in prompt  # Custom-Text wird verwendet
    assert prompt.index("Nur diese eine Anweisung.") > prompt.index("Reisewarnung")
    assert prompt.rstrip().endswith(app_mod._ADVISOR_SAFETY_TRAILER.strip())


def test_advisor_prompt_uses_default_instructions_when_disabled(app_mod):
    profile = {"region": "Deutschland"}
    prompt = app_mod._advisor_prompt(profile)
    assert "Windverhältnisse" in prompt
    assert "Sal" in prompt and "Boa Vista" in prompt


def test_compare_prompt_contains_facts_and_instructions(app_mod):
    hotels = [{"name": "Hotel A", "location": "Fuerteventura"},
              {"name": "Hotel B", "location": "Gran Canaria"}]
    instructions = app_mod._prompt_instructions("compare", app_mod._DEFAULT_COMPARE_INSTRUCTIONS)
    prompt = app_mod._compare_prompt(hotels, instructions)
    assert "Hotel A" in prompt and "Hotel B" in prompt
    assert "Preis-Leistung" in prompt


def test_prompt_settings_get_default(app_mod):
    c = app_mod.app.test_client()
    r = c.get("/api/ai/prompt-settings", headers=ING)
    assert r.status_code == 200
    data = r.get_json()
    assert set(data.keys()) == {"advisor", "compare"}
    assert data["advisor"]["enabled"] is False
    assert data["advisor"]["text"] == ""
    assert "Windverhältnisse" in data["advisor"]["default"]


def test_prompt_settings_post_and_get_roundtrip(app_mod):
    c = app_mod.app.test_client()
    r = c.post("/api/ai/prompt-settings", headers=ING, json={
        "advisor": {"enabled": True, "text": "Mein Reiseberater-Prompt"},
    })
    assert r.status_code == 200
    r = c.get("/api/ai/prompt-settings", headers=ING)
    data = r.get_json()
    assert data["advisor"]["enabled"] is True
    assert data["advisor"]["text"] == "Mein Reiseberater-Prompt"
    # compare wurde nicht mitgeschickt -> bleibt unverändert (disabled/leer)
    assert data["compare"]["enabled"] is False


def test_prompt_settings_text_capped_at_max_len(app_mod):
    c = app_mod.app.test_client()
    long_text = "x" * 5000
    c.post("/api/ai/prompt-settings", headers=ING, json={
        "advisor": {"enabled": True, "text": long_text},
    })
    r = c.get("/api/ai/prompt-settings", headers=ING)
    assert len(r.get_json()["advisor"]["text"]) == app_mod._CUSTOM_PROMPT_MAX_LEN
