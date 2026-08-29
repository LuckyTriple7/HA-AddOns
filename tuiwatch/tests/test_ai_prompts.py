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
               "travel_type": ["Pauschalreise"]}
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


def test_advisor_prompt_includes_beach_detail_when_set(app_mod):
    profile = {"region": "Europa", "interests": ["🌴 Strand"],
               "beach_detail": ["Feinsandig", "Direkt am Hotel"]}
    prompt = app_mod._advisor_prompt(profile)
    assert "Strand-Details: Feinsandig, Direkt am Hotel" in prompt


def test_advisor_prompt_includes_arrival_distance_clause_for_own_arrival(app_mod):
    profile = {"region": "Europa", "arrival_mode": "Auto",
               "home_location": "70173 Stuttgart", "max_distance": "bis 400 km"}
    prompt = app_mod._advisor_prompt(profile)
    assert "Startort eigene Anreise: 70173 Stuttgart" in prompt
    assert "Max. Entfernung eigene Anreise: bis 400 km" in prompt
    assert "eigenständig mit Auto an" in prompt
    assert "🎲 Überraschung darf in diesem Fall KEIN anderes Land" in prompt


def test_advisor_prompt_omits_arrival_distance_clause_for_flight(app_mod):
    profile = {"region": "Europa", "arrival_mode": "Flugzeug"}
    prompt = app_mod._advisor_prompt(profile)
    assert "eigenständig mit" not in prompt


def test_advisor_prompt_uses_daytrip_instructions(app_mod):
    profile = {"region": app_mod._DAYTRIP_REGION_VALUE,
               "home_location": "70173 Stuttgart", "max_distance": "bis 100 km",
               "duration_daytrip": "Ganzer Tag"}
    prompt = app_mod._advisor_prompt(profile)
    assert "Tagesausflugsziele" in prompt
    assert "Startort eigene Anreise: 70173 Stuttgart" in prompt
    assert "Verfügbare Zeit: Ganzer Tag" in prompt
    assert "Unterkunftsvorschläge" not in prompt
    assert "die TUI tatsächlich im Programm hat" not in prompt
    assert "TUI-Pauschalreisen einen Flug" not in prompt
    assert "ob aktuell eine Reisewarnung" not in prompt


def test_advisor_prompt_daytrip_includes_perfect_daytrip_freetext(app_mod):
    """Neues Freitext-Feld des Tagesausflug-Wizards muss im Prompt ankommen."""
    profile = {"region": app_mod._DAYTRIP_REGION_VALUE, "home_location": "Köln",
               "perfect_daytrip": "Viel Natur, wenig Trubel, gutes Café am Ziel"}
    prompt = app_mod._advisor_prompt(profile)
    assert "Perfekter Ausflug laut Nutzer (Freitext): Viel Natur, wenig Trubel, gutes Café am Ziel" in prompt


def test_advisor_prompt_vacation_still_checks_reisewarnung(app_mod):
    profile = {"region": "Europa"}
    prompt = app_mod._advisor_prompt(profile)
    assert "ob aktuell eine Reisewarnung" in prompt


def test_region_is_multi_select_list(app_mod):
    """`region` ist im Wizard jetzt eine Mehrfachauswahl (Liste) -
    mehrere Regionen gleichzeitig muessen im Prompt ankommen."""
    profile = {"region": ["Balearen", "Griechische Inseln"]}
    prompt = app_mod._advisor_prompt(profile)
    assert "Ziel-Region: Balearen, Griechische Inseln" in prompt


def test_region_list_containing_daytrip_triggers_daytrip_mode(app_mod):
    profile = {"region": [app_mod._DAYTRIP_REGION_VALUE],
               "home_location": "Köln", "max_distance": "bis 100 km"}
    prompt = app_mod._advisor_prompt(profile)
    assert "Tagesausflugsziele" in prompt


def test_region_values_helper_normalizes_scalar_and_list(app_mod):
    assert app_mod._region_values({"region": "Europa"}) == ["Europa"]
    assert app_mod._region_values({"region": ["Europa", "Italien"]}) == ["Europa", "Italien"]
    assert app_mod._region_values({}) == []


def test_advisor_prompt_daytrip_ignores_dna_context(app_mod):
    profile = {"region": app_mod._DAYTRIP_REGION_VALUE, "home_location": "Köln"}
    prompt = app_mod._advisor_prompt(profile, prev_dna={"🌴 Strand": 50})
    assert "Reise-DNA" not in prompt


def test_compare_prompt_contains_facts_and_instructions(app_mod):
    hotels = [{"name": "Hotel A", "location": "Fuerteventura"},
              {"name": "Hotel B", "location": "Gran Canaria"}]
    instructions = app_mod._prompt_instructions("compare", app_mod._DEFAULT_COMPARE_INSTRUCTIONS)
    prompt = app_mod._compare_prompt(hotels, instructions)
    assert "Hotel A" in prompt and "Hotel B" in prompt
    assert "Preis-Leistung" in prompt


def test_summary_prompt_contains_facts_and_instructions(app_mod):
    hotel = {"name": "Hotel C", "location": "Antalya"}
    instructions = app_mod._prompt_instructions("summary", app_mod._DEFAULT_SUMMARY_INSTRUCTIONS)
    prompt = app_mod._hotel_summary_prompt(hotel, instructions)
    assert "Hotel C" in prompt
    assert "Fazit" in prompt


# Alle anpassbaren Vorlagen. Klimatabelle und Reiseführer kamen später dazu —
# ihre Prompts waren vorher fest verdrahtet und nur im Code änderbar.
_FEATURES = {"advisor", "compare", "summary", "daytrip", "region_compare",
             "climate", "guide"}


def test_prompt_settings_includes_summary_feature(app_mod):
    c = app_mod.app.test_client()
    data = c.get("/api/ai/prompt-settings", headers=ING).get_json()
    assert set(data.keys()) == _FEATURES
    assert "Fazit" in data["summary"]["default"]


def test_prompt_settings_get_default(app_mod):
    c = app_mod.app.test_client()
    r = c.get("/api/ai/prompt-settings", headers=ING)
    assert r.status_code == 200
    data = r.get_json()
    assert set(data.keys()) == _FEATURES
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
    long_text = "x" * (app_mod._CUSTOM_PROMPT_MAX_LEN + 1000)
    c.post("/api/ai/prompt-settings", headers=ING, json={
        "advisor": {"enabled": True, "text": long_text},
    })
    r = c.get("/api/ai/prompt-settings", headers=ING)
    assert len(r.get_json()["advisor"]["text"]) == app_mod._CUSTOM_PROMPT_MAX_LEN


def test_guide_and_climate_are_editable(app_mod):
    """Beide waren fest im Code verdrahtet. Ihr Standardtext muss im Dialog
    ankommen, sonst steht dort ein leeres Feld statt der Vorlage."""
    c = app_mod.app.test_client()
    data = c.get("/api/ai/prompt-settings", headers=ING).get_json()
    assert "Abschnitte" in data["guide"]["default"]
    assert "LGBTQ-Reisende" in data["guide"]["default"]
    assert "Informationsfreiheit" in data["guide"]["default"]
    assert "Klima-Normalwerte" in data["climate"]["default"]


def test_a_custom_guide_prompt_reaches_the_request(app_mod, monkeypatch):
    """Nur gespeicherte Vorlagen nützen nichts — sie müssen auch im Prompt landen."""
    c = app_mod.app.test_client()
    c.post("/api/ai/prompt-settings", headers=ING, json={
        "guide": {"enabled": True, "text": "NUR EIN ABSCHNITT: Wetter."}})
    ai_routes = importlib.import_module("ai_routes")
    prompt = ai_routes._guide_prompt("Kreta")
    assert "NUR EIN ABSCHNITT" in prompt
    assert "Kreta" in prompt, "das Reiseziel bleibt fest, es steht nicht in der Vorlage"


def test_the_long_region_compare_default_is_not_truncated_on_save(app_mod):
    """Der Standardtext ist ueber 10000 Zeichen lang. Waere das Limit zu knapp,
    schnitte das Speichern still ab und der Nutzer merkte es erst an der Antwort."""
    c = app_mod.app.test_client()
    default = c.get("/api/ai/prompt-settings", headers=ING).get_json()["region_compare"]["default"]
    assert len(default) > 6000, "Testvoraussetzung: Vorlage laenger als das alte Limit"
    c.post("/api/ai/prompt-settings", headers=ING, json={
        "region_compare": {"enabled": True, "text": default}})
    back = c.get("/api/ai/prompt-settings", headers=ING).get_json()["region_compare"]["text"]
    assert back == default.strip()
