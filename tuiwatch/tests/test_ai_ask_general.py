"""Tests für die allgemeine Reisefrage (`/api/ai/ask` mit `scope=general`).

Kernunterschied zur Portfolio-Frage: die Angebotsliste wird NICHT mitgeschickt
(wäre für „wann ist die beste Reisezeit für Sri Lanka" nur Ballast und würde die
Antwort auf die eigenen Hotels lenken), und die Frage funktioniert deshalb auch
mit leerem Portfolio.
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
        return "Antworttext", {"input_tokens": 10, "output_tokens": 20}, None

    monkeypatch.setattr(m, "_ai_call", _fake)
    return seen


def _ask(client, question, **extra):
    return client.post("/api/ai/ask", json=dict(question=question, **extra))


def test_general_question_works_without_any_offers(m, client, calls):
    """Portfolio-Frage verlangt Angebote, die allgemeine Reisefrage nicht."""
    assert _ask(client, "Beste Reisezeit Sri Lanka?").get_json()["error"] == "no_offers"
    r = _ask(client, "Beste Reisezeit Sri Lanka?", scope="general")
    assert r.status_code == 200 and r.get_json()["summary"] == "Antworttext"


def test_general_prompt_omits_the_portfolio(m, client, calls, monkeypatch):
    """Auch mit getrackten Angeboten darf die Angebotsliste nicht im Prompt landen."""
    with m.db() as con:
        con.execute("INSERT INTO offers (url, hotel, label, created) VALUES (?,?,?,?)",
                    ("https://x.invalid/angebote/H/1/", "Riu Papayas", "Mein Hotel", 0))
    _ask(client, "Wie komme ich nach Sri Lanka?", scope="general")
    prompt = calls[-1]["prompt"]
    assert "Riu Papayas" not in prompt and "Mein Hotel" not in prompt
    assert "NICHT um meine bereits getrackten Angebote" in prompt
    assert "Allgemeine Reisefrage" in prompt


def test_general_prompt_uses_home_location(m, client, calls, monkeypatch):
    """Der hinterlegte Heimatort hilft bei Anreise-/Entfernungsfragen."""
    monkeypatch.setattr(m, "load_config", lambda: {
        "anthropic_api_key": "sk-test", "anthropic_model": "claude-haiku-4-5",
        "trippilot_home_location": "Stuttgart"})
    _ask(client, "Wie lange fliegt man?", scope="general")
    assert "Stuttgart" in calls[-1]["prompt"]


def test_general_answer_lands_in_history_under_its_own_kind(m, client, calls):
    _ask(client, "Visum für Vietnam?", scope="general")
    with m.db() as con:
        row = con.execute("SELECT kind, title FROM ai_analyses ORDER BY id DESC").fetchone()
    assert row["kind"] == "ask_general" and row["title"] == "Visum für Vietnam?"


def test_unknown_scope_falls_back_to_portfolio(m, client, calls):
    """Ein unbekannter Wert darf nicht versehentlich die allgemeine Frage auslösen."""
    assert _ask(client, "Was?", scope="quatsch").get_json()["error"] == "no_offers"


def test_empty_question_is_rejected(m, client, calls):
    assert _ask(client, "   ", scope="general").status_code == 400


def test_history_repeat_knows_the_new_kind(m):
    """Ohne Eintrag in _AI_RETRY_MARKDOWN_CONFIG ließe sich eine Reisefrage im
    KI-Verlauf nicht mit einem anderen Anbieter wiederholen."""
    ai_routes = importlib.import_module("ai_routes")
    assert "ask_general" in ai_routes._AI_RETRY_MARKDOWN_CONFIG
    assert ai_routes._AI_RETRY_MARKDOWN_CONFIG["ask_general"]["use_web_search"] is True
