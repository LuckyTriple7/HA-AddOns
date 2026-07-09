"""Tests für Gemini als zweiten KI-Anbieter: `_ai_config()` liest die
Gemini-Optionen korrekt, `_ai_request()` dispatcht anhand des Modellnamens
an `_ai_request_gemini`, und das Usage-Mapping (Tokens, Websuchen-Anzahl aus
Grounding-Metadata) stimmt. Kein echter API-Key nötig (Fake-Client).
"""
import importlib
import json
from types import SimpleNamespace

import pytest

pytest.importorskip("flask")
pytest.importorskip("google.genai")

from google.genai import errors as genai_errors  # noqa: E402
from google.genai import types as genai_types  # noqa: E402


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


class _FakeCandidate:
    def __init__(self, finish_reason=genai_types.FinishReason.STOP, web_search_queries=None):
        self.finish_reason = finish_reason
        self.grounding_metadata = SimpleNamespace(web_search_queries=web_search_queries or [])


class _FakeResponse:
    def __init__(self, text="Antwort", finish_reason=genai_types.FinishReason.STOP,
                web_search_queries=None, prompt_tokens=100, output_tokens=50,
                cached_tokens=0):
        self.text = text
        self.candidates = [_FakeCandidate(finish_reason, web_search_queries)]
        self.usage_metadata = SimpleNamespace(
            prompt_token_count=prompt_tokens, candidates_token_count=output_tokens,
            cached_content_token_count=cached_tokens,
        )


class _FakeModels:
    def __init__(self, response, captured):
        self._response = response
        self._captured = captured

    def generate_content(self, **kwargs):
        self._captured.append(kwargs)
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class _FakeClient:
    def __init__(self, response, captured, **_kwargs):
        self.models = _FakeModels(response, captured)


def _patch_genai(app_mod, monkeypatch, response):
    captured = []
    monkeypatch.setattr(app_mod.genai, "Client",
                        lambda **kw: _FakeClient(response, captured, **kw))
    return captured


def test_ai_config_reads_gemini_options(app_mod):
    _write_options(app_mod, ai_provider="gemini", gemini_api_key="g-key",
                   gemini_model="gemini-3.5-flash")
    api_key, model = app_mod._ai_config()
    assert api_key == "g-key"
    assert model == "gemini-3.5-flash"


def test_ai_config_falls_back_to_flagship_on_invalid_gemini_model(app_mod):
    _write_options(app_mod, ai_provider="gemini", gemini_api_key="g-key",
                   gemini_model="not-a-real-model")
    _api_key, model = app_mod._ai_config()
    assert model == "gemini-3.1-pro"


def test_ai_config_defaults_to_anthropic(app_mod):
    api_key, model = app_mod._ai_config()
    assert model == "claude-opus-4-8"
    assert api_key == ""


def test_ai_request_dispatches_gemini_by_model_name(app_mod, monkeypatch):
    captured = _patch_genai(app_mod, monkeypatch, _FakeResponse())
    text, usage, err = app_mod._ai_request("g-key", "gemini-3.1-pro", "Prompt",
                                           max_tokens=200, log_ctx="Test")
    assert err is None
    assert text == "Antwort"
    assert captured[0]["model"] == "gemini-3.1-pro"


def test_gemini_usage_mapping(app_mod, monkeypatch):
    _patch_genai(app_mod, monkeypatch, _FakeResponse(
        prompt_tokens=1234, output_tokens=567, cached_tokens=89,
        web_search_queries=["a", "b", "c"]))
    _text, usage, _err = app_mod._ai_request("g-key", "gemini-3.1-pro", "Prompt",
                                             max_tokens=200, log_ctx="Test")
    assert usage["input_tokens"] == 1234
    assert usage["output_tokens"] == 567
    assert usage["cache_read_input_tokens"] == 89
    assert usage["cache_creation_input_tokens"] == 0
    assert usage["web_search_requests"] == 3


def test_gemini_web_search_tool_added_when_enabled(app_mod, monkeypatch):
    captured = _patch_genai(app_mod, monkeypatch, _FakeResponse())
    app_mod._ai_request("g-key", "gemini-3.1-pro", "Prompt", max_tokens=200,
                        log_ctx="Test", use_web_search=True)
    assert captured[0]["config"].tools is not None


def test_gemini_no_tools_when_web_search_disabled(app_mod, monkeypatch):
    captured = _patch_genai(app_mod, monkeypatch, _FakeResponse())
    app_mod._ai_request("g-key", "gemini-3.1-pro", "Prompt", max_tokens=200,
                        log_ctx="Test", use_web_search=False)
    assert captured[0]["config"].tools is None


def test_gemini_output_schema_passed_through(app_mod, monkeypatch):
    schema = {"type": "object", "properties": {"tags": {"type": "array",
              "items": {"type": "string"}}}, "required": ["tags"],
              "additionalProperties": False}
    captured = _patch_genai(app_mod, monkeypatch, _FakeResponse(text='{"tags": ["a"]}'))
    text, _usage, err = app_mod._ai_request("g-key", "gemini-2.5-flash", "Prompt",
                                            max_tokens=200, log_ctx="Test",
                                            use_web_search=False, output_schema=schema)
    assert err is None
    assert text == '{"tags": ["a"]}'
    assert captured[0]["config"].response_mime_type == "application/json"
    # additionalProperties wird entfernt - Gemini lehnt das Feld live mit
    # 400 INVALID_ARGUMENT ab ("Unknown name additional_properties")
    assert "additionalProperties" not in captured[0]["config"].response_schema
    assert captured[0]["config"].response_schema["required"] == ["tags"]


def test_gemini_web_search_dropped_when_combined_with_output_schema(app_mod, monkeypatch):
    """Regression: Gemini lehnt Tool-Use zusammen mit response_mime_type=application/json
    live mit 400 INVALID_ARGUMENT ab ("Tool use with a response mime type ... is
    unsupported"). Bei beidem gleichzeitig muss das Schema gewinnen (Aufrufer brauchen
    parsebares JSON) und die Websuche für diesen Aufruf stillschweigend entfallen."""
    schema = {"type": "object", "properties": {"score": {"type": "integer"}},
              "required": ["score"], "additionalProperties": False}
    captured = _patch_genai(app_mod, monkeypatch, _FakeResponse(text='{"score": 50}'))
    text, _usage, err = app_mod._ai_request("g-key", "gemini-2.5-flash", "Prompt",
                                            max_tokens=200, log_ctx="Test",
                                            use_web_search=True, output_schema=schema)
    assert err is None
    assert text == '{"score": 50}'
    assert captured[0]["config"].tools is None            # Websuche entfallen
    assert captured[0]["config"].response_mime_type == "application/json"  # Schema bleibt


def test_gemini_unexpected_exception_returns_failed_not_uncaught(app_mod, monkeypatch):
    """Regression: live beobachtet — Google antwortete mit 200 OK, aber danach kam beim
    Frontend nur eine generische Fehlermeldung an (nicht JSON-parsebar). Ursache: nur
    `genai_errors.APIError` wurde gefangen; ein anderer SDK-interner Fehler (z. B. im
    Automatic-Function-Calling-Loop bei aktivierter Websuche) schlug bis nach oben
    durch. Muss jetzt als sauberes ('failed') zurückkommen, nicht crashen."""
    _patch_genai(app_mod, monkeypatch, RuntimeError("boom, irgendein SDK-interner Fehler"))
    text, usage, err = app_mod._ai_request("g-key", "gemini-3.1-pro", "Prompt",
                                           max_tokens=200, log_ctx="Test")
    assert err == "failed"
    assert text is None and usage is None


def test_gemini_sanitize_schema_strips_additional_properties_nested(app_mod):
    schema = {"type": "object", "additionalProperties": False,
              "properties": {"inner": {"type": "object", "additional_properties": False,
                                       "properties": {"x": {"type": "string"}}}}}
    cleaned = app_mod._gemini_sanitize_schema(schema)
    assert "additionalProperties" not in cleaned
    assert "additional_properties" not in cleaned["properties"]["inner"]
    assert cleaned["properties"]["inner"]["properties"]["x"]["type"] == "string"


def test_gemini_max_output_tokens_reserves_thinking_budget(app_mod, monkeypatch):
    """Thinking-Tokens teilen sich bei Gemini das Budget mit max_output_tokens
    — bei knappen Werten (Auto-Tags: 300, Wochenüberblick: 500) frisst Thinking
    die eigentliche Antwort leer/abgeschnitten, ohne dass ein Fehler auftritt.
    Reserve muss draufgeschlagen werden, sonst reproduziert sich der Bug."""
    captured = _patch_genai(app_mod, monkeypatch, _FakeResponse())
    app_mod._ai_request("g-key", "gemini-3.1-pro", "Prompt", max_tokens=300,
                        log_ctx="Test")
    sent = captured[0]["config"].max_output_tokens
    assert sent >= 300 + app_mod._GEMINI_THINKING_TOKEN_RESERVE


def test_gemini_refusal_detected(app_mod, monkeypatch):
    _patch_genai(app_mod, monkeypatch,
                _FakeResponse(finish_reason=genai_types.FinishReason.SAFETY))
    _text, _usage, err = app_mod._ai_request("g-key", "gemini-3.1-pro", "Prompt",
                                             max_tokens=200, log_ctx="Test")
    assert err == "refused"


def test_gemini_empty_text_returns_empty_code(app_mod, monkeypatch):
    _patch_genai(app_mod, monkeypatch, _FakeResponse(text=""))
    _text, _usage, err = app_mod._ai_request("g-key", "gemini-3.1-pro", "Prompt",
                                             max_tokens=200, log_ctx="Test")
    assert err == "empty"


def test_gemini_api_error_returns_failed_code(app_mod, monkeypatch):
    error = genai_errors.APIError(500, {"message": "boom"})
    _patch_genai(app_mod, monkeypatch, error)
    _text, _usage, err = app_mod._ai_request("g-key", "gemini-3.1-pro", "Prompt",
                                             max_tokens=200, log_ctx="Test")
    assert err == "failed"


def test_anthropic_dispatch_unaffected(app_mod, monkeypatch):
    """Regressionsschutz: Claude-Modelle landen weiterhin bei _ai_request_anthropic,
    nicht bei der neuen Gemini-Variante."""
    called = []
    monkeypatch.setattr(app_mod, "_ai_request_anthropic",
                        lambda *a, **kw: (called.append((a, kw)) or ("ok", {}, None)))
    text, _usage, err = app_mod._ai_request("a-key", "claude-sonnet-5", "Prompt",
                                            max_tokens=200, log_ctx="Test")
    assert text == "ok"
    assert err is None
    assert len(called) == 1


ING = {"X-Ingress-Path": "/test"}


def test_active_provider_defaults_to_anthropic_when_nothing_configured(app_mod):
    assert app_mod._ai_active_provider() == "anthropic"


def test_active_provider_only_gemini_key_set(app_mod):
    _write_options(app_mod, gemini_api_key="g-key")
    assert app_mod._ai_active_provider() == "gemini"


def test_active_provider_only_anthropic_key_set(app_mod):
    _write_options(app_mod, anthropic_api_key="a-key")
    assert app_mod._ai_active_provider() == "anthropic"


def test_active_provider_both_keys_uses_config_default(app_mod):
    _write_options(app_mod, anthropic_api_key="a-key", gemini_api_key="g-key",
                   ai_provider="gemini")
    assert app_mod._ai_active_provider() == "gemini"


def test_active_provider_both_keys_uses_meta_override(app_mod):
    _write_options(app_mod, anthropic_api_key="a-key", gemini_api_key="g-key",
                   ai_provider="anthropic")
    app_mod._meta_set("ai_provider_active", "gemini")
    assert app_mod._ai_active_provider() == "gemini"


def test_provider_route_get_reports_both_configured(app_mod):
    _write_options(app_mod, anthropic_api_key="a-key", gemini_api_key="g-key")
    c = app_mod.app.test_client()
    r = c.get("/api/ai/provider", headers=ING)
    assert r.status_code == 200
    data = r.get_json()
    assert data["both_configured"] is True
    assert data["anthropic_configured"] is True
    assert data["gemini_configured"] is True


def test_provider_route_post_switches_when_both_configured(app_mod):
    _write_options(app_mod, anthropic_api_key="a-key", gemini_api_key="g-key")
    c = app_mod.app.test_client()
    r = c.post("/api/ai/provider", headers=ING, json={"provider": "gemini"})
    assert r.status_code == 200
    assert r.get_json()["active"] == "gemini"
    assert app_mod._ai_active_provider() == "gemini"


def test_provider_route_post_rejected_when_only_one_configured(app_mod):
    _write_options(app_mod, anthropic_api_key="a-key")
    c = app_mod.app.test_client()
    r = c.post("/api/ai/provider", headers=ING, json={"provider": "gemini"})
    assert r.status_code == 400


def test_provider_route_post_rejects_invalid_provider(app_mod):
    _write_options(app_mod, anthropic_api_key="a-key", gemini_api_key="g-key")
    c = app_mod.app.test_client()
    r = c.post("/api/ai/provider", headers=ING, json={"provider": "openai"})
    assert r.status_code == 400
