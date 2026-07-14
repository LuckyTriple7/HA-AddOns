"""Tests für Perplexity als dritten KI-Anbieter: `_ai_config()`/`_ai_config_for()`
lesen die Perplexity-Optionen korrekt, `_ai_request()` dispatcht anhand des
Modellnamens an `_ai_request_perplexity`, das Usage-Mapping (Tokens,
Websuchen-Anzahl aus `num_search_queries`) stimmt, und `_ai_active_provider()`/
`/api/ai/provider` funktionieren mit 3 statt 2 möglichen Providern. Kein echter
API-Key nötig (Fake-`requests.post`, gemocktes Modul ist dasselbe Objekt wie in
app.py — siehe ai_client.py-Docstring).
"""
import importlib
import json

import pytest
import requests

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


def _write_options(app_mod, **opts):
    with open(app_mod.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(opts, f)


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, raise_exc=None):
        self.status_code = status_code
        self._payload = payload or {}
        self._raise_exc = raise_exc

    def raise_for_status(self):
        if self._raise_exc:
            raise self._raise_exc

    def json(self):
        return self._payload


def _chat_payload(text="Antwort", finish_reason="stop", prompt_tokens=100,
                  completion_tokens=50, num_search_queries=0, citations=None,
                  search_results=None):
    payload = {
        "choices": [{"message": {"content": text}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                  "num_search_queries": num_search_queries},
    }
    if citations is not None:
        payload["citations"] = citations
    if search_results is not None:
        payload["search_results"] = search_results
    return payload


def _patch_requests(monkeypatch, response, captured=None):
    captured = captured if captured is not None else []

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return response

    monkeypatch.setattr(requests, "post", fake_post)
    return captured


def test_ai_config_reads_perplexity_options(app_mod):
    _write_options(app_mod, ai_provider="perplexity", perplexity_api_key="p-key",
                   perplexity_model="sonar")
    api_key, model = app_mod._ai_config()
    assert api_key == "p-key"
    assert model == "sonar"


def test_ai_config_falls_back_to_flagship_on_invalid_perplexity_model(app_mod):
    _write_options(app_mod, ai_provider="perplexity", perplexity_api_key="p-key",
                   perplexity_model="not-a-real-model")
    _api_key, model = app_mod._ai_config()
    assert model == "sonar-pro"


def test_ai_config_for_perplexity_explicit(app_mod):
    _write_options(app_mod, perplexity_api_key="p-key")
    api_key, model = app_mod._ai_config_for("perplexity")
    assert api_key == "p-key"
    assert model == "sonar-pro"


def test_ai_request_dispatches_perplexity_by_model_name(app_mod, monkeypatch):
    captured = _patch_requests(monkeypatch, _FakeResponse(payload=_chat_payload()))
    text, usage, err = app_mod._ai_request("p-key", "sonar-pro", "Prompt",
                                           max_tokens=200, log_ctx="Test")
    assert err is None
    assert text == "Antwort"
    assert captured[0]["json"]["model"] == "sonar-pro"
    assert captured[0]["headers"]["Authorization"] == "Bearer p-key"


def test_perplexity_pins_low_search_context_size(app_mod, monkeypatch):
    """Muss explizit gesetzt werden — sonst weicht die tatsächlich abgerechnete
    Request-Gebühr vom in _AI_PERPLEXITY_REQUEST_FEE hinterlegten Wert ab."""
    captured = _patch_requests(monkeypatch, _FakeResponse(payload=_chat_payload()))
    app_mod._ai_request("p-key", "sonar-pro", "Prompt", max_tokens=200, log_ctx="Test")
    assert captured[0]["json"]["web_search_options"] == {"search_context_size": "low"}


def test_perplexity_usage_mapping(app_mod, monkeypatch):
    _patch_requests(monkeypatch, _FakeResponse(payload=_chat_payload(
        prompt_tokens=1573, completion_tokens=239, num_search_queries=3)))
    _text, usage, _err = app_mod._ai_request("p-key", "sonar-pro", "Prompt",
                                             max_tokens=200, log_ctx="Test")
    assert usage["input_tokens"] == 1573
    assert usage["output_tokens"] == 239
    assert usage["web_search_requests"] == 3
    assert usage["cache_creation_input_tokens"] == 0
    assert usage["cache_read_input_tokens"] == 0


def test_perplexity_output_schema_passed_through(app_mod, monkeypatch):
    schema = {"type": "object", "properties": {"tags": {"type": "array",
              "items": {"type": "string"}}}, "required": ["tags"],
              "additionalProperties": False}
    captured = _patch_requests(monkeypatch,
                               _FakeResponse(payload=_chat_payload(text='{"tags": ["a"]}')))
    text, _usage, err = app_mod._ai_request("p-key", "sonar", "Prompt", max_tokens=200,
                                            log_ctx="Test", output_schema=schema)
    assert err is None
    assert text == '{"tags": ["a"]}'
    assert captured[0]["json"]["response_format"] == {"type": "json_schema",
                                                        "json_schema": {"schema": schema}}


def test_perplexity_empty_text_returns_empty_code(app_mod, monkeypatch):
    _patch_requests(monkeypatch, _FakeResponse(payload=_chat_payload(text="")))
    _text, _usage, err = app_mod._ai_request("p-key", "sonar", "Prompt",
                                             max_tokens=200, log_ctx="Test")
    assert err == "empty"


def test_perplexity_http_error_returns_failed_code(app_mod, monkeypatch):
    response = _FakeResponse(status_code=401,
                             raise_exc=requests.HTTPError("401 Unauthorized"))
    _patch_requests(monkeypatch, response)
    _text, _usage, err = app_mod._ai_request("bad-key", "sonar", "Prompt",
                                             max_tokens=200, log_ctx="Test")
    assert err == "failed"


def test_perplexity_connection_error_returns_failed_code(app_mod, monkeypatch):
    def fake_post(*a, **kw):
        raise requests.ConnectionError("boom")
    monkeypatch.setattr(requests, "post", fake_post)
    _text, _usage, err = app_mod._ai_request("p-key", "sonar", "Prompt",
                                             max_tokens=200, log_ctx="Test")
    assert err == "failed"


def test_perplexity_malformed_response_returns_failed_not_uncaught(app_mod, monkeypatch):
    """Regression analog zum Gemini-Fall: eine unerwartete Antwortstruktur darf nicht
    mit einer unbehandelten Exception bis zu Flask durchschlagen."""
    _patch_requests(monkeypatch, _FakeResponse(payload={"unexpected": "shape"}))
    text, usage, err = app_mod._ai_request("p-key", "sonar", "Prompt",
                                           max_tokens=200, log_ctx="Test")
    assert err == "failed"
    assert text is None and usage is None


def test_anthropic_dispatch_unaffected_by_perplexity(app_mod, monkeypatch):
    """Regressionsschutz: Claude-Modelle landen weiterhin bei _ai_request_anthropic,
    nicht bei der neuen Perplexity-Variante."""
    called = []
    monkeypatch.setattr(app_mod, "_ai_request_anthropic",
                        lambda *a, **kw: (called.append((a, kw)) or ("ok", {}, None)))
    text, _usage, err = app_mod._ai_request("a-key", "claude-sonnet-5", "Prompt",
                                            max_tokens=200, log_ctx="Test")
    assert text == "ok"
    assert err is None
    assert len(called) == 1


ING = {"X-Ingress-Path": "/test"}


def test_active_provider_only_perplexity_key_set(app_mod):
    _write_options(app_mod, perplexity_api_key="p-key")
    assert app_mod._ai_active_provider() == "perplexity"


def test_active_provider_three_keys_uses_config_default(app_mod):
    _write_options(app_mod, anthropic_api_key="a-key", gemini_api_key="g-key",
                   perplexity_api_key="p-key", ai_provider="perplexity")
    assert app_mod._ai_active_provider() == "perplexity"


def test_active_provider_three_keys_uses_meta_override(app_mod):
    _write_options(app_mod, anthropic_api_key="a-key", gemini_api_key="g-key",
                   perplexity_api_key="p-key", ai_provider="anthropic")
    app_mod._meta_set("ai_provider_active", "perplexity")
    assert app_mod._ai_active_provider() == "perplexity"


def test_active_provider_falls_back_when_meta_provider_no_longer_configured(app_mod):
    """Meta sagt 'perplexity', aber der Key wurde inzwischen entfernt — darf nicht
    auf einen nicht konfigurierten Provider zeigen, sondern auf einen echten Fallback."""
    _write_options(app_mod, anthropic_api_key="a-key", gemini_api_key="g-key")
    app_mod._meta_set("ai_provider_active", "perplexity")
    assert app_mod._ai_active_provider() in ("anthropic", "gemini")


def test_provider_route_get_reports_perplexity_configured(app_mod):
    _write_options(app_mod, anthropic_api_key="a-key", perplexity_api_key="p-key")
    c = app_mod.app.test_client()
    r = c.get("/api/ai/provider", headers=ING)
    assert r.status_code == 200
    data = r.get_json()
    assert data["both_configured"] is True
    assert data["perplexity_configured"] is True
    assert data["gemini_configured"] is False
    assert set(data["configured_providers"]) == {"anthropic", "perplexity"}


def test_provider_route_post_switches_to_perplexity(app_mod):
    _write_options(app_mod, anthropic_api_key="a-key", perplexity_api_key="p-key")
    c = app_mod.app.test_client()
    r = c.post("/api/ai/provider", headers=ING, json={"provider": "perplexity"})
    assert r.status_code == 200
    assert r.get_json()["active"] == "perplexity"
    assert app_mod._ai_active_provider() == "perplexity"


def test_provider_route_post_rejects_configured_provider_missing_key(app_mod):
    """perplexity ist ein gültiger Provider-Name, aber ohne Key hier nicht wählbar."""
    _write_options(app_mod, anthropic_api_key="a-key", gemini_api_key="g-key")
    c = app_mod.app.test_client()
    r = c.post("/api/ai/provider", headers=ING, json={"provider": "perplexity"})
    assert r.status_code == 400


# ── Zitat-Verlinkung ([n] -> [n](url)) ──────────────────────────────────────

def test_perplexity_linkifies_citations_from_search_results(app_mod, monkeypatch):
    _patch_requests(monkeypatch, _FakeResponse(payload=_chat_payload(
        text="Traumhafter Strand.[1][3]",
        search_results=[{"url": "https://a.example/1"}, {"url": "https://b.example/2"},
                        {"url": "https://c.example/3"}])))
    text, _usage, err = app_mod._ai_request("p-key", "sonar-pro", "Prompt",
                                            max_tokens=200, log_ctx="Test")
    assert err is None
    assert text == "Traumhafter Strand.[1](https://a.example/1)[3](https://c.example/3)"


def test_perplexity_linkifies_citations_from_bare_citations_list(app_mod, monkeypatch):
    """Fallback, falls die Antwort kein `search_results` liefert (ältere/leichtere
    Sonar-Antworten haben nur die schlichte `citations`-URL-Liste)."""
    _patch_requests(monkeypatch, _FakeResponse(payload=_chat_payload(
        text="Klares Wasser.[2]", citations=["https://x.example", "https://y.example"])))
    text, _usage, _err = app_mod._ai_request("p-key", "sonar", "Prompt",
                                             max_tokens=200, log_ctx="Test")
    assert text == "Klares Wasser.[2](https://y.example)"


def test_perplexity_leaves_unmatched_citation_number_unchanged(app_mod, monkeypatch):
    _patch_requests(monkeypatch, _FakeResponse(payload=_chat_payload(
        text="Siehe [9].", citations=["https://x.example"])))
    text, _usage, _err = app_mod._ai_request("p-key", "sonar", "Prompt",
                                             max_tokens=200, log_ctx="Test")
    assert text == "Siehe [9]."


def test_perplexity_no_citations_text_unchanged(app_mod, monkeypatch):
    _patch_requests(monkeypatch, _FakeResponse(payload=_chat_payload(text="Kein Zitat hier.")))
    text, _usage, _err = app_mod._ai_request("p-key", "sonar", "Prompt",
                                             max_tokens=200, log_ctx="Test")
    assert text == "Kein Zitat hier."


def test_perplexity_skips_linkify_for_structured_output(app_mod, monkeypatch):
    """Bei Structured Output ist `text` ein JSON-String für einen Parser —
    Markdown-Link-Syntax darf hier nicht eingefügt werden, auch wenn das Modell
    (untypisch) Zitat-Marker im JSON-Text unterbringt."""
    schema = {"type": "object", "properties": {"score": {"type": "integer"}},
              "required": ["score"], "additionalProperties": False}
    _patch_requests(monkeypatch, _FakeResponse(payload=_chat_payload(
        text='{"score": 1}', citations=["https://x.example"])))
    text, _usage, _err = app_mod._ai_request("p-key", "sonar", "Prompt", max_tokens=200,
                                             log_ctx="Test", output_schema=schema)
    assert text == '{"score": 1}'


def test_ai_md_to_html_renders_citation_link(app_mod):
    html = app_mod._ai_md_to_html("Traumhaft.[1](https://a.example/page?x=1&y=2)")
    assert '<a href="https://a.example/page?x=1&amp;y=2"' in html
    assert '>[1]</a>' in html


# ── Kostenschätzung inkl. Request-Gebühr ────────────────────────────────────

def test_ai_call_cost_includes_perplexity_request_fee(app_mod):
    usage = {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0,
             "cache_read_input_tokens": 0}
    assert app_mod._ai_call_cost("sonar-pro", usage) == pytest.approx(0.006)


def test_ai_call_cost_perplexity_adds_fee_on_top_of_tokens(app_mod):
    usage = {"input_tokens": 1_000_000, "output_tokens": 0,
             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    # sonar: $1/1M input + $0.005 Request-Gebühr
    assert app_mod._ai_call_cost("sonar", usage) == pytest.approx(1.005)


def test_ai_call_cost_no_request_fee_for_claude(app_mod):
    usage = {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0,
             "cache_read_input_tokens": 0}
    assert app_mod._ai_call_cost("claude-opus-4-8", usage) == 0.0


def test_ai_usage_calc_multiplies_perplexity_fee_by_calls(app_mod):
    models = {"sonar-pro": {"input_tokens": 0, "output_tokens": 0,
                            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
                            "calls": 3}}
    result = app_mod._ai_usage_calc(models)
    assert result["estimated_usd"] == pytest.approx(0.018)  # 3 × 0.006


def test_history_repeat_accepts_perplexity_provider(app_mod, monkeypatch):
    _write_options(app_mod, perplexity_api_key="p-key")
    with app_mod.db() as con:
        con.execute("INSERT INTO ai_analyses (kind, title, model, summary, usage, ts, prompt) "
                    "VALUES (?,?,?,?,?,?,?)",
                    ("single", "Test", "sonar-pro", "alt", "{}", 0, "Alter Prompt"))
    _patch_requests(monkeypatch, _FakeResponse(payload=_chat_payload(text="Neue Antwort")))
    c = app_mod.app.test_client()
    r = c.post("/api/ai/history/1/repeat", headers=ING, json={"provider": "perplexity"})
    assert r.status_code == 200
    assert r.get_json()["summary"] == "Neue Antwort"
