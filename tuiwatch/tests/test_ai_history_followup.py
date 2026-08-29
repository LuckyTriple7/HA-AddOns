"""Tests für Folgefragen zu einem KI-Verlaufseintrag (POST
/api/ai/history/<id>/followup): echte Mehrfach-Turn-Konversation (bisheriger
Prompt + Antwort + neue Frage) statt nur denselben alten Prompt erneut wie bei
/repeat. Zwei Ebenen:
1. `_ai_request_messages`/`_ai_call_messages` (ai_client.py) — Dispatch und
   Rollen-Mapping je Provider (Claude/Perplexity: 'user'/'assistant' 1:1;
   Gemini: 'assistant' -> 'model').
2. Der Endpoint selbst — Konversation wird aus prompt+summary rekonstruiert,
   im bestehenden Eintrag fortgeschrieben (kein neuer Verlaufseintrag),
   funktioniert providerübergreifend mit dem Modell des Original-Eintrags.
"""
import importlib
import json
from types import SimpleNamespace

import pytest
import requests

pytest.importorskip("flask")
pytest.importorskip("google.genai")

from google.genai import types as genai_types  # noqa: E402

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


def _write_options(app_mod, **opts):
    with open(app_mod.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(opts, f)


def _insert_history(app_mod, kind="single", title="Testhotel", model="claude-haiku-4-5",
                    summary="Alte Antwort", prompt="Alter Prompt-Text", conversation="", ts=1000):
    with app_mod.db() as con:
        cur = con.execute(
            "INSERT INTO ai_analyses (kind, title, model, summary, usage, ts, prompt, conversation) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (kind, title, model, summary, "{}", ts, prompt, conversation))
        return cur.lastrowid


# ── _ai_request_messages / _ai_call_messages: Provider-Dispatch & Rollen ───────

class _FakeAnthropicUsage:
    input_tokens = 10
    output_tokens = 5
    cache_creation_input_tokens = 0
    cache_read_input_tokens = 0
    server_tool_use = None


class _FakeAnthropicTextBlock:
    type = "text"
    text = "Klar, hier die Vertiefung."


class _FakeAnthropicResponse:
    stop_reason = "end_turn"
    content = [_FakeAnthropicTextBlock()]
    usage = _FakeAnthropicUsage()


class _FakeAnthropicMessages:
    def __init__(self, captured):
        self._captured = captured

    def create(self, **kwargs):
        self._captured.append(kwargs)
        return _FakeAnthropicResponse()


def _patch_anthropic(app_mod, monkeypatch):
    captured = []
    monkeypatch.setattr(app_mod.anthropic, "Anthropic",
                        lambda **kw: SimpleNamespace(messages=_FakeAnthropicMessages(captured)))
    return captured


def test_anthropic_messages_passed_through_unchanged(app_mod, monkeypatch):
    captured = _patch_anthropic(app_mod, monkeypatch)
    messages = [{"role": "user", "content": "Alte Frage"},
                {"role": "assistant", "content": "Alte Antwort"},
                {"role": "user", "content": "Neue Frage"}]
    text, _usage, err = app_mod._ai_request_messages("key", "claude-sonnet-5", messages,
                                                      max_tokens=200, log_ctx="Test")
    assert err is None
    assert text == "Klar, hier die Vertiefung."
    assert captured[0]["messages"] == messages


class _FakeGeminiCandidate:
    def __init__(self, finish_reason=genai_types.FinishReason.STOP):
        self.finish_reason = finish_reason
        self.grounding_metadata = SimpleNamespace(web_search_queries=[])


class _FakeGeminiResponse:
    def __init__(self, text="Klar, hier die Vertiefung."):
        self.text = text
        self.candidates = [_FakeGeminiCandidate()]
        self.usage_metadata = SimpleNamespace(prompt_token_count=10, candidates_token_count=5,
                                              cached_content_token_count=0)


class _FakeGeminiModels:
    def __init__(self, captured):
        self._captured = captured

    def generate_content(self, **kwargs):
        self._captured.append(kwargs)
        return _FakeGeminiResponse()


def _patch_gemini(app_mod, monkeypatch):
    captured = []
    monkeypatch.setattr(app_mod.genai, "Client",
                        lambda **kw: SimpleNamespace(models=_FakeGeminiModels(captured)))
    return captured


def test_gemini_messages_maps_assistant_role_to_model(app_mod, monkeypatch):
    captured = _patch_gemini(app_mod, monkeypatch)
    messages = [{"role": "user", "content": "Alte Frage"},
                {"role": "assistant", "content": "Alte Antwort"},
                {"role": "user", "content": "Neue Frage"}]
    text, _usage, err = app_mod._ai_request_messages("key", "gemini-3.1-pro", messages,
                                                      max_tokens=200, log_ctx="Test")
    assert err is None
    assert text == "Klar, hier die Vertiefung."
    contents = captured[0]["contents"]
    roles = [c.role for c in contents]
    texts = [c.parts[0].text for c in contents]
    assert roles == ["user", "model", "user"]
    assert texts == ["Alte Frage", "Alte Antwort", "Neue Frage"]


class _FakePerplexityResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _patch_perplexity(app_mod, monkeypatch, text="Klar, hier die Vertiefung."):
    captured = []
    payload = {"status": "completed",
               "output": [{"type": "message", "role": "assistant",
                           "content": [{"type": "output_text", "text": text}]}],
               "usage": {"input_tokens": 10, "output_tokens": 5,
                         "tool_calls_details": {"web_search": 0}}}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.append({"url": url, "headers": headers, "json": json})
        return _FakePerplexityResponse(payload)

    monkeypatch.setattr(requests, "post", fake_post)
    return captured


def test_perplexity_messages_passed_through_unchanged(app_mod, monkeypatch):
    captured = _patch_perplexity(app_mod, monkeypatch)
    messages = [{"role": "user", "content": "Alte Frage"},
                {"role": "assistant", "content": "Alte Antwort"},
                {"role": "user", "content": "Neue Frage"}]
    text, _usage, err = app_mod._ai_request_messages("key", "pplx-low", messages,
                                                      max_tokens=200, log_ctx="Test")
    assert err is None
    assert text == "Klar, hier die Vertiefung."
    # Agent API: `input`-Array mit `type: message` je Eintrag; Rollen und Reihen-
    # folge bleiben unveraendert, es kommt nur das Typ-Feld dazu.
    assert captured[0]["json"]["input"] == [dict(m, type="message") for m in messages]


def test_ai_call_messages_wraps_failure_as_jsonify_tuple(app_mod, monkeypatch):
    def fake_post(*a, **kw):
        raise requests.ConnectionError("boom")
    monkeypatch.setattr(requests, "post", fake_post)
    with app_mod.app.app_context():
        text, usage, err = app_mod._ai_call_messages("key", "pplx-fast", [{"role": "user", "content": "Hi"}],
                                                      max_tokens=200, log_ctx="Test")
    assert text is None and usage is None
    resp, status = err
    assert status == 502


# ── /api/ai/history/<id>/followup ───────────────────────────────────────────

def _mock_ai_request_messages(app_mod, monkeypatch, text="Neue Antwort", calls=None):
    calls = calls if calls is not None else []

    def fake(api_key, model, messages, *, max_tokens, log_ctx, use_web_search=True, output_schema=None):
        # Snapshot per Kopie: der Endpoint haengt die Antwort im Anschluss an
        # dieselbe `messages`-Liste an — ohne Kopie wuerde die spaetere Mutation
        # rueckwirkend auch in den hier aufgezeichneten `calls` auftauchen.
        calls.append({"api_key": api_key, "model": model, "messages": list(messages),
                      "use_web_search": use_web_search})
        return text, {"input_tokens": 100_000, "output_tokens": 50_000,
                      "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}, None

    monkeypatch.setattr(app_mod, "_ai_request_messages", fake)
    return calls


def test_followup_404_for_missing_entry(app_mod):
    _write_options(app_mod, anthropic_api_key="a-key")
    c = app_mod.app.test_client()
    r = c.post("/api/ai/history/999/followup", headers=ING, json={"question": "Und Wassersport?"})
    assert r.status_code == 404


def test_followup_400_for_empty_question(app_mod):
    _write_options(app_mod, anthropic_api_key="a-key")
    aid = _insert_history(app_mod)
    c = app_mod.app.test_client()
    r = c.post(f"/api/ai/history/{aid}/followup", headers=ING, json={"question": "  "})
    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid"


def test_followup_400_for_too_long_question(app_mod):
    _write_options(app_mod, anthropic_api_key="a-key")
    aid = _insert_history(app_mod)
    c = app_mod.app.test_client()
    r = c.post(f"/api/ai/history/{aid}/followup", headers=ING, json={"question": "x" * 2001})
    assert r.status_code == 400


@pytest.mark.parametrize("kind", ["booking_score", "region_outlook"])
def test_followup_rejects_structured_kinds(app_mod, kind):
    _write_options(app_mod, anthropic_api_key="a-key")
    aid = _insert_history(app_mod, kind=kind, summary='{"score": 70}')
    c = app_mod.app.test_client()
    r = c.post(f"/api/ai/history/{aid}/followup", headers=ING, json={"question": "Und in 2 Wochen?"})
    assert r.status_code == 400
    assert r.get_json()["error"] == "unsupported_kind"


def test_followup_400_when_entry_has_no_conversation(app_mod):
    _write_options(app_mod, anthropic_api_key="a-key")
    aid = _insert_history(app_mod, prompt="", summary="")
    c = app_mod.app.test_client()
    r = c.post(f"/api/ai/history/{aid}/followup", headers=ING, json={"question": "Und Wassersport?"})
    assert r.status_code == 400
    assert r.get_json()["error"] == "no_prompt"


def test_followup_400_when_provider_key_missing(app_mod):
    _write_options(app_mod)  # kein Key hinterlegt
    aid = _insert_history(app_mod, model="claude-haiku-4-5")
    c = app_mod.app.test_client()
    r = c.post(f"/api/ai/history/{aid}/followup", headers=ING, json={"question": "Und Wassersport?"})
    assert r.status_code == 400
    assert r.get_json()["error"] == "no_api_key"


def test_followup_seeds_conversation_from_prompt_and_summary(app_mod, monkeypatch):
    _write_options(app_mod, anthropic_api_key="a-key")
    aid = _insert_history(app_mod, prompt="Wie ist der Strand?", summary="Traumhaft weiß.")
    calls = _mock_ai_request_messages(app_mod, monkeypatch)
    c = app_mod.app.test_client()
    r = c.post(f"/api/ai/history/{aid}/followup", headers=ING,
              json={"question": "Und das Wasser?"})
    assert r.status_code == 200
    assert calls[0]["messages"] == [
        {"role": "user", "content": "Wie ist der Strand?"},
        {"role": "assistant", "content": "Traumhaft weiß."},
        {"role": "user", "content": "Und das Wasser?"},
    ]
    d = r.get_json()
    assert d["summary"] == "Neue Antwort"
    assert d["id"] == aid


def test_followup_persists_conversation_and_new_summary(app_mod, monkeypatch):
    _write_options(app_mod, anthropic_api_key="a-key")
    aid = _insert_history(app_mod, prompt="Wie ist der Strand?", summary="Traumhaft weiß.")
    _mock_ai_request_messages(app_mod, monkeypatch, text="Kristallklar und warm.")
    c = app_mod.app.test_client()
    c.post(f"/api/ai/history/{aid}/followup", headers=ING, json={"question": "Und das Wasser?"})
    with app_mod.db() as con:
        row = con.execute("SELECT summary, conversation FROM ai_analyses WHERE id=?", (aid,)).fetchone()
    assert row["summary"] == "Kristallklar und warm."
    conv = json.loads(row["conversation"])
    assert conv == [
        {"role": "user", "content": "Wie ist der Strand?"},
        {"role": "assistant", "content": "Traumhaft weiß."},
        {"role": "user", "content": "Und das Wasser?"},
        {"role": "assistant", "content": "Kristallklar und warm."},
    ]


def test_followup_continues_existing_conversation_not_just_first_turn(app_mod, monkeypatch):
    """Zweite Folgefrage muss auf der GESAMTEN bisherigen Konversation aufbauen,
    nicht nur auf dem allerersten Prompt+Antwort-Paar."""
    _write_options(app_mod, anthropic_api_key="a-key")
    existing_conv = json.dumps([
        {"role": "user", "content": "Wie ist der Strand?"},
        {"role": "assistant", "content": "Traumhaft weiß."},
        {"role": "user", "content": "Und das Wasser?"},
        {"role": "assistant", "content": "Kristallklar und warm."},
    ])
    aid = _insert_history(app_mod, prompt="Wie ist der Strand?", summary="Kristallklar und warm.",
                          conversation=existing_conv)
    calls = _mock_ai_request_messages(app_mod, monkeypatch, text="Sehr windig im Winter.")
    c = app_mod.app.test_client()
    c.post(f"/api/ai/history/{aid}/followup", headers=ING, json={"question": "Und der Wind?"})
    assert len(calls[0]["messages"]) == 5
    assert calls[0]["messages"][-1] == {"role": "user", "content": "Und der Wind?"}
    assert calls[0]["messages"][0] == {"role": "user", "content": "Wie ist der Strand?"}


def test_followup_uses_original_entrys_model_not_currently_active_provider(app_mod, monkeypatch):
    """Eintrag wurde ursprünglich mit Gemini beantwortet; aktiver Standard-Provider
    ist inzwischen Anthropic — Folgefrage muss trotzdem bei Gemini bleiben
    (Konversationskontinuität), nicht beim aktuell aktiven Provider landen."""
    _write_options(app_mod, anthropic_api_key="a-key", gemini_api_key="g-key",
                   ai_provider="anthropic")
    aid = _insert_history(app_mod, model="gemini-3.1-pro", prompt="Wie ist der Strand?",
                          summary="Traumhaft weiß.")
    calls = _mock_ai_request_messages(app_mod, monkeypatch)
    c = app_mod.app.test_client()
    c.post(f"/api/ai/history/{aid}/followup", headers=ING, json={"question": "Und das Wasser?"})
    assert calls[0]["api_key"] == "g-key"
    assert calls[0]["model"] == "gemini-3.1-pro"


def test_followup_records_usage_and_cost(app_mod, monkeypatch):
    _write_options(app_mod, anthropic_api_key="a-key")
    aid = _insert_history(app_mod, model="claude-haiku-4-5")
    _mock_ai_request_messages(app_mod, monkeypatch)
    c = app_mod.app.test_client()
    r = c.post(f"/api/ai/history/{aid}/followup", headers=ING, json={"question": "Und Wassersport?"})
    d = r.get_json()
    assert d["usage"]["estimated_usd"] > 0
    assert d["totals"]["calls"] == 1


def test_followup_forwards_ai_backend_error(app_mod, monkeypatch):
    """`_ai_request_messages` gibt bei einem Fehler einen Code-String zurück
    (nicht direkt eine jsonify-Response) — `_ai_call_messages` (der echte,
    ungemockte Wrapper) übersetzt das in die HTTP-Fehlerantwort."""
    _write_options(app_mod, anthropic_api_key="a-key")
    aid = _insert_history(app_mod)

    def fake(*a, **kw):
        return None, None, "failed"

    monkeypatch.setattr(app_mod, "_ai_request_messages", fake)
    c = app_mod.app.test_client()
    r = c.post(f"/api/ai/history/{aid}/followup", headers=ING, json={"question": "Und Wassersport?"})
    assert r.status_code == 502
    assert r.get_json()["error"] == "ai_failed"
