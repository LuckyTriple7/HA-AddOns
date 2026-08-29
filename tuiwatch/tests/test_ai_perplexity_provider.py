"""Tests für Perplexity als dritten KI-Anbieter: `_ai_config()`/`_ai_config_for()`
lesen die Perplexity-Optionen korrekt, `_ai_request()` dispatcht anhand des
Modellnamens an `_ai_request_perplexity`, das Usage-Mapping (Tokens,
Websuchen-Anzahl aus `usage.tool_calls_details.web_search`) stimmt, und
`_ai_active_provider()`/`/api/ai/provider` funktionieren mit 3 statt 2 möglichen
Providern. Kein echter API-Key nötig (Fake-`requests.post`, gemocktes Modul ist
dasselbe Objekt wie in app.py — siehe ai_client.py-Docstring).

Antwortformat ist die Agent API (`/v1/agent`): typisiertes `output`-Array statt
`choices`, Quellen im `search_results`-Schritt statt in Top-Level-`citations`.
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


def _sources(*urls, start_id=1):
    """`search_results`-Treffer wie die Agent API sie liefert (1-basierte `id`)."""
    return [{"id": start_id + i, "url": u, "title": f"Quelle {start_id + i}"}
            for i, u in enumerate(urls)]


def _agent_payload(text="Antwort", status="completed", input_tokens=100,
                   output_tokens=50, web_searches=0, results=None,
                   extra_steps=(), cost=None):
    """Agent-API-Antwort: `output` ist ein Array typisierter Schritte, der Text
    steckt als `output_text`-Teil im `message`-Schritt."""
    output = [{"type": "message", "role": "assistant", "status": "completed",
               "content": [{"type": "output_text", "text": text, "annotations": []}]}]
    if results is not None:
        output.append({"type": "search_results", "results": results})
    output.extend(extra_steps)
    usage = {"input_tokens": input_tokens, "output_tokens": output_tokens,
             "total_tokens": input_tokens + output_tokens,
             "tool_calls_details": {"web_search": web_searches}}
    if cost is not None:
        usage["cost"] = cost
    return {
        "id": "resp_test", "object": "response", "status": status,
        "model": "preset-low", "output": output, "usage": usage,
    }


def _patch_requests(monkeypatch, response, captured=None):
    captured = captured if captured is not None else []

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return response

    monkeypatch.setattr(requests, "post", fake_post)
    return captured


def test_ai_config_reads_perplexity_options(app_mod):
    _write_options(app_mod, ai_provider="perplexity", perplexity_api_key="p-key",
                   perplexity_model="pplx-fast")
    api_key, model = app_mod._ai_config()
    assert api_key == "p-key"
    assert model == "pplx-fast"


def test_ai_config_falls_back_to_flagship_on_invalid_perplexity_model(app_mod):
    _write_options(app_mod, ai_provider="perplexity", perplexity_api_key="p-key",
                   perplexity_model="not-a-real-model")
    _api_key, model = app_mod._ai_config()
    assert model == "pplx-low"


def test_ai_config_for_perplexity_explicit(app_mod):
    _write_options(app_mod, perplexity_api_key="p-key")
    api_key, model = app_mod._ai_config_for("perplexity")
    assert api_key == "p-key"
    assert model == "pplx-low"


def test_ai_request_dispatches_perplexity_by_model_name(app_mod, monkeypatch):
    captured = _patch_requests(monkeypatch, _FakeResponse(payload=_agent_payload()))
    text, usage, err = app_mod._ai_request("p-key", "pplx-low", "Prompt",
                                           max_tokens=200, log_ctx="Test")
    assert err is None
    assert text == "Antwort"
    assert captured[0]["url"].endswith("/v1/agent")
    # Gesendet wird das Preset ohne unser `pplx-`-Präfix; die Sonar-Modelle
    # existieren in der Agent API nicht mehr.
    assert captured[0]["json"]["preset"] == "low"
    assert "model" not in captured[0]["json"]
    assert captured[0]["headers"]["Authorization"] == "Bearer p-key"


def test_perplexity_pins_low_search_context_size(app_mod, monkeypatch):
    """Muss explizit gesetzt werden — sonst weicht die tatsächlich abgerechnete
    Request-Gebühr vom in _AI_PERPLEXITY_REQUEST_FEE hinterlegten Wert ab."""
    captured = _patch_requests(monkeypatch, _FakeResponse(payload=_agent_payload()))
    app_mod._ai_request("p-key", "pplx-low", "Prompt", max_tokens=200, log_ctx="Test")
    assert captured[0]["json"]["tools"] == [{"type": "web_search",
                                             "search_context_size": "low"}]


def test_perplexity_prompt_becomes_input_message(app_mod, monkeypatch):
    """Agent API nimmt `input` statt `messages`, je Eintrag mit `type: message`."""
    captured = _patch_requests(monkeypatch, _FakeResponse(payload=_agent_payload()))
    app_mod._ai_request("p-key", "pplx-low", "Prompt", max_tokens=200, log_ctx="Test")
    assert captured[0]["json"]["input"] == [
        {"type": "message", "role": "user", "content": "Prompt"}]
    assert captured[0]["json"]["max_output_tokens"] == 200
    assert "messages" not in captured[0]["json"]
    assert "max_tokens" not in captured[0]["json"]


def test_perplexity_always_searches_regardless_of_the_flag(app_mod, monkeypatch):
    """`use_web_search=False` hat bei Perplexity keine Wirkung: ein Preset bringt
    die Websuche mit, und Tools werden je Werkzeug zusammengeführt statt ersetzt —
    das Weglassen nimmt sie dem Preset also nicht. Ein Schalter dafür ist nicht
    dokumentiert. Festgehalten, damit die Kostenrechnung nicht von einer
    Ersparnis ausgeht, die es nicht gibt."""
    captured = _patch_requests(monkeypatch, _FakeResponse(payload=_agent_payload()))
    app_mod._ai_request("p-key", "pplx-low", "Prompt", max_tokens=200, log_ctx="Test",
                        use_web_search=False)
    assert captured[0]["json"]["tools"] == [{"type": "web_search",
                                             "search_context_size": "low"}]


def test_old_sonar_choice_is_lifted_to_its_preset(app_mod):
    """Bestehende Konfigurationen dürfen ihre eingestellte Gründlichkeit nicht
    verlieren, nur weil die Sonar-Namen weg sind."""
    _write_options(app_mod, ai_provider="perplexity", perplexity_api_key="p-key",
                   perplexity_model="sonar-deep-research")
    _api_key, model = app_mod._ai_config()
    assert model == "pplx-high"


def test_perplexity_truncation_is_logged(app_mod, monkeypatch, caplog):
    """`status: incomplete` ersetzt Sonars `finish_reason: length`."""
    _patch_requests(monkeypatch, _FakeResponse(payload=_agent_payload(status="incomplete")))
    with caplog.at_level("WARNING"):
        text, _usage, err = app_mod._ai_request("p-key", "pplx-low", "Prompt",
                                                max_tokens=200, log_ctx="Test")
    assert err is None and text == "Antwort"
    assert "abgeschnitten" in " ".join(r.getMessage() for r in caplog.records)


def test_perplexity_starts_a_background_run(app_mod, monkeypatch):
    """Der Lauf wird im Hintergrund gestartet, statt eine Verbindung minutenlang
    offen zu halten — sonst schneidet irgendein Zeitlimit dazwischen die
    Recherche ab, fuer die wir bereits bezahlt haben."""
    captured = _patch_requests(monkeypatch, _FakeResponse(payload=_agent_payload()))
    app_mod._ai_request("p-key", "pplx-low", "Prompt", max_tokens=200, log_ctx="Test")
    assert captured[0]["json"]["background"] is True


def test_perplexity_single_request_timeout_is_short(app_mod, monkeypatch):
    """Die einzelne HTTP-Anfrage darf knapp sein: im Hintergrund-Modus antwortet
    die API sofort. Die Wartezeit steckt zwischen den Abfragen, nicht in einer
    offenen Verbindung — deshalb ist `perplexity_timeout` hier NICHT das
    Socket-Limit."""
    _write_options(app_mod, perplexity_api_key="p-key", perplexity_timeout=600)
    captured = _patch_requests(monkeypatch, _FakeResponse(payload=_agent_payload()))
    app_mod._ai_request("p-key", "pplx-low", "Prompt", max_tokens=200, log_ctx="Test")
    assert captured[0]["timeout"] == 30


def test_perplexity_total_wait_defaults_to_five_minutes(app_mod):
    ai_client = importlib.import_module("ai_client")
    assert ai_client._perplexity_timeout() == 300


def test_perplexity_total_wait_is_configurable_and_clamped(app_mod):
    ai_client = importlib.import_module("ai_client")
    _write_options(app_mod, perplexity_api_key="p-key", perplexity_timeout=600)
    assert ai_client._perplexity_timeout() == 600
    _write_options(app_mod, perplexity_api_key="p-key", perplexity_timeout=99999)
    assert ai_client._perplexity_timeout() == 900


def test_perplexity_polls_until_the_run_is_done(app_mod, monkeypatch):
    """Antwortet der Start mit einem Zwischenstatus, wird das Ergebnis ueber
    GET /v1/agent/<id> abgeholt statt aufgegeben."""
    import requests as rq
    monkeypatch.setattr(ai_client_mod(), "_PERPLEXITY_POLL_INTERVAL", 0)
    monkeypatch.setattr(rq, "post", lambda *a, **kw: _FakeResponse(
        payload={"id": "run_1", "status": "in_progress", "output": []}))
    gets = []

    def fake_get(url, headers=None, timeout=None):
        gets.append(url)
        status = "in_progress" if len(gets) < 3 else "completed"
        payload = _agent_payload() if status == "completed" else {"id": "run_1",
                                                                  "status": status}
        return _FakeResponse(payload=payload)

    monkeypatch.setattr(rq, "get", fake_get)
    text, _usage, err = app_mod._ai_request("p-key", "pplx-high", "Prompt",
                                            max_tokens=200, log_ctx="Test")
    assert err is None and text == "Antwort"
    assert gets and gets[0].endswith("/v1/agent/run_1")


def test_perplexity_gives_up_after_the_total_wait(app_mod, monkeypatch):
    """Laeuft der Lauf ewig, muss die Gesamtfrist greifen — sonst haengt der
    Aufruf unbegrenzt."""
    import requests as rq
    _write_options(app_mod, perplexity_api_key="p-key", perplexity_timeout=60)
    monkeypatch.setattr(ai_client_mod(), "_PERPLEXITY_POLL_INTERVAL", 0)
    monkeypatch.setattr(ai_client_mod(), "_perplexity_timeout", lambda: 0)
    monkeypatch.setattr(rq, "post", lambda *a, **kw: _FakeResponse(
        payload={"id": "run_1", "status": "queued", "output": []}))
    monkeypatch.setattr(rq, "get", lambda *a, **kw: _FakeResponse(
        payload={"id": "run_1", "status": "in_progress"}))
    _text, _usage, err = app_mod._ai_request("p-key", "pplx-high", "Prompt",
                                             max_tokens=200, log_ctx="Test")
    assert err == "failed"


def test_perplexity_usage_mapping(app_mod, monkeypatch):
    _patch_requests(monkeypatch, _FakeResponse(payload=_agent_payload(
        input_tokens=1573, output_tokens=239, web_searches=3)))
    _text, usage, _err = app_mod._ai_request("p-key", "pplx-low", "Prompt",
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
                               _FakeResponse(payload=_agent_payload(text='{"tags": ["a"]}')))
    text, _usage, err = app_mod._ai_request("p-key", "pplx-fast", "Prompt", max_tokens=200,
                                            log_ctx="Test", output_schema=schema)
    assert err is None
    assert text == '{"tags": ["a"]}'
    assert captured[0]["json"]["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "tuiwatch_result", "schema": schema}}


def test_perplexity_empty_text_returns_empty_code(app_mod, monkeypatch):
    _patch_requests(monkeypatch, _FakeResponse(payload=_agent_payload(text="")))
    _text, _usage, err = app_mod._ai_request("p-key", "pplx-fast", "Prompt",
                                             max_tokens=200, log_ctx="Test")
    assert err == "empty"


def test_perplexity_http_error_returns_failed_code(app_mod, monkeypatch):
    response = _FakeResponse(status_code=401,
                             raise_exc=requests.HTTPError("401 Unauthorized"))
    _patch_requests(monkeypatch, response)
    _text, _usage, err = app_mod._ai_request("bad-key", "pplx-fast", "Prompt",
                                             max_tokens=200, log_ctx="Test")
    assert err == "failed"


def test_perplexity_http_error_logs_the_response_body(app_mod, monkeypatch, caplog):
    """Ein 400 sagt fuer sich genommen nur „Bad Request" — welches Feld die API
    beanstandet, steht allein im Antwortkoerper. Ohne ihn im Log ist der Fehler
    nicht diagnostizierbar."""
    err_resp = _FakeResponse(status_code=400)
    err_resp.text = '{"error": {"message": "unknown field: preset"}}'
    exc = requests.HTTPError("400 Client Error: Bad Request")
    exc.response = err_resp
    _patch_requests(monkeypatch, _FakeResponse(status_code=400, raise_exc=exc))
    with caplog.at_level("WARNING"):
        _text, _usage, code = app_mod._ai_request("p-key", "pplx-low", "Prompt",
                                                  max_tokens=200, log_ctx="Test")
    assert code == "failed"
    assert "unknown field: preset" in " ".join(r.getMessage() for r in caplog.records)


def test_perplexity_error_without_a_body_still_logs(app_mod, monkeypatch, caplog):
    """Verbindungsfehler haben gar keine Antwort — das darf beim Loggen nicht
    seinerseits krachen."""
    def fake_post(*a, **kw):
        raise requests.ConnectionError("keine Verbindung")
    monkeypatch.setattr(requests, "post", fake_post)
    with caplog.at_level("WARNING"):
        _text, _usage, code = app_mod._ai_request("p-key", "pplx-fast", "Prompt",
                                                  max_tokens=200, log_ctx="Test")
    assert code == "failed"
    assert "keine Verbindung" in " ".join(r.getMessage() for r in caplog.records)


def test_perplexity_connection_error_returns_failed_code(app_mod, monkeypatch):
    def fake_post(*a, **kw):
        raise requests.ConnectionError("boom")
    monkeypatch.setattr(requests, "post", fake_post)
    _text, _usage, err = app_mod._ai_request("p-key", "pplx-fast", "Prompt",
                                             max_tokens=200, log_ctx="Test")
    assert err == "failed"


def test_perplexity_malformed_response_returns_failed_not_uncaught(app_mod, monkeypatch):
    """Regression analog zum Gemini-Fall: eine unerwartete Antwortstruktur darf nicht
    mit einer unbehandelten Exception bis zu Flask durchschlagen."""
    _patch_requests(monkeypatch, _FakeResponse(payload={"unexpected": "shape"}))
    text, usage, err = app_mod._ai_request("p-key", "pplx-fast", "Prompt",
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


def ai_client_mod():
    return importlib.import_module("ai_client")


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
    _patch_requests(monkeypatch, _FakeResponse(payload=_agent_payload(
        text="Traumhafter Strand.[1][3]",
        results=_sources("https://a.example/1", "https://b.example/2",
                         "https://c.example/3"))))
    text, _usage, err = app_mod._ai_request("p-key", "pplx-low", "Prompt",
                                            max_tokens=200, log_ctx="Test")
    assert err is None
    assert text == "Traumhafter Strand.[1](https://a.example/1)[3](https://c.example/3)"


def test_perplexity_falls_back_to_result_order_without_ids(app_mod, monkeypatch):
    """Ohne `id` am Treffer bleibt nur die Reihenfolge — dann zaehlen die Marker
    positionsbasiert, wie frueher gegen die nackte `citations`-Liste."""
    _patch_requests(monkeypatch, _FakeResponse(payload=_agent_payload(
        text="Klares Wasser.[2]",
        results=[{"url": "https://x.example"}, {"url": "https://y.example"}])))
    text, _usage, _err = app_mod._ai_request("p-key", "pplx-fast", "Prompt",
                                             max_tokens=200, log_ctx="Test")
    assert text == "Klares Wasser.[2](https://y.example)"


def test_perplexity_leaves_unmatched_citation_number_unchanged(app_mod, monkeypatch):
    _patch_requests(monkeypatch, _FakeResponse(payload=_agent_payload(
        text="Siehe [9].", results=_sources("https://x.example"))))
    text, _usage, _err = app_mod._ai_request("p-key", "pplx-fast", "Prompt",
                                             max_tokens=200, log_ctx="Test")
    assert text == "Siehe [9]."


def test_perplexity_no_citations_text_unchanged(app_mod, monkeypatch):
    _patch_requests(monkeypatch, _FakeResponse(payload=_agent_payload(text="Kein Zitat hier.")))
    text, _usage, _err = app_mod._ai_request("p-key", "pplx-fast", "Prompt",
                                             max_tokens=200, log_ctx="Test")
    assert text == "Kein Zitat hier."


def test_perplexity_skips_linkify_for_structured_output(app_mod, monkeypatch):
    """Bei Structured Output ist `text` ein JSON-String für einen Parser —
    Markdown-Link-Syntax darf hier nicht eingefügt werden, auch wenn das Modell
    (untypisch) Zitat-Marker im JSON-Text unterbringt."""
    schema = {"type": "object", "properties": {"score": {"type": "integer"}},
              "required": ["score"], "additionalProperties": False}
    _patch_requests(monkeypatch, _FakeResponse(payload=_agent_payload(
        text='{"score": 1}', results=_sources("https://x.example"))))
    text, _usage, _err = app_mod._ai_request("p-key", "pplx-fast", "Prompt", max_tokens=200,
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
    assert app_mod._ai_call_cost("pplx-low", usage) == pytest.approx(0.0025)


def test_ai_call_cost_perplexity_adds_fee_on_top_of_tokens(app_mod):
    usage = {"input_tokens": 1_000_000, "output_tokens": 0,
             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    # pplx-fast: $0.20/1M input + $0.0025 Suchgebühr
    assert app_mod._ai_call_cost("pplx-fast", usage) == pytest.approx(0.2025)


def test_ai_call_cost_no_request_fee_for_claude(app_mod):
    usage = {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0,
             "cache_read_input_tokens": 0}
    assert app_mod._ai_call_cost("claude-opus-4-8", usage) == 0.0


def test_ai_usage_calc_multiplies_perplexity_fee_by_calls(app_mod):
    models = {"pplx-low": {"input_tokens": 0, "output_tokens": 0,
                            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
                            "calls": 3}}
    result = app_mod._ai_usage_calc(models)
    assert result["estimated_usd"] == pytest.approx(0.0075)  # 3 × 0.0025


# -- Echte Kosten aus der Agent API statt Schaetzung ------------------------

def test_perplexity_reports_real_cost_in_usage(app_mod, monkeypatch):
    """Die Agent API rechnet den Aufruf selbst ab; `total_cost` deckt Token- UND
    Tool-/Suchkosten ab und ersetzt damit unsere Schaetzung."""
    _patch_requests(monkeypatch, _FakeResponse(payload=_agent_payload(cost={
        "currency": "USD", "input_cost": 0.00409, "output_cost": 0.01316,
        "cache_read_cost": 0.00045, "tool_calls_cost": 0.0025, "total_cost": 0.0202})))
    _text, usage, err = app_mod._ai_request("p-key", "pplx-low", "Prompt",
                                            max_tokens=200, log_ctx="Test")
    assert err is None
    assert usage["cost_usd"] == pytest.approx(0.0202)
    assert app_mod._ai_call_cost("pplx-low", usage) == pytest.approx(0.0202)


def test_perplexity_without_cost_block_falls_back_to_estimate(app_mod, monkeypatch):
    """Perplexity garantiert das Feld nirgends fuer jedes Modell — fehlt es, muss
    die alte Schaetzung greifen statt eine Luecke zu hinterlassen."""
    _patch_requests(monkeypatch, _FakeResponse(payload=_agent_payload(
        input_tokens=1_000_000, output_tokens=0)))
    _text, usage, _err = app_mod._ai_request("p-key", "pplx-fast", "Prompt",
                                             max_tokens=200, log_ctx="Test")
    assert "cost_usd" not in usage
    assert app_mod._ai_call_cost("pplx-fast", usage) == pytest.approx(0.2025)


def test_perplexity_ignores_cost_in_other_currency(app_mod, monkeypatch):
    """Die gesamte Kostenanzeige ist in USD — eine fremde Waehrung ungeprueft zu
    uebernehmen waere schlicht ein falscher Betrag."""
    _patch_requests(monkeypatch, _FakeResponse(payload=_agent_payload(
        cost={"currency": "EUR", "total_cost": 0.5})))
    _text, usage, _err = app_mod._ai_request("p-key", "pplx-low", "Prompt",
                                             max_tokens=200, log_ctx="Test")
    assert "cost_usd" not in usage


def test_perplexity_ignores_unusable_total_cost(app_mod, monkeypatch):
    _patch_requests(monkeypatch, _FakeResponse(payload=_agent_payload(
        cost={"currency": "USD", "total_cost": None})))
    _text, usage, _err = app_mod._ai_request("p-key", "pplx-low", "Prompt",
                                             max_tokens=200, log_ctx="Test")
    assert "cost_usd" not in usage


def test_ai_call_cost_prefers_reported_over_estimate(app_mod):
    """Gemeldete Kosten sind die echte Zahl — die Schaetzung darf nicht zusaetzlich
    obendrauf kommen, auch nicht die pauschale Request-Gebuehr."""
    usage = {"input_tokens": 1_000_000, "output_tokens": 0,
             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
             "cost_usd": 0.0202}
    assert app_mod._ai_call_cost("pplx-fast", usage) == pytest.approx(0.0202)


def test_usage_bucket_records_the_settled_share(app_mod):
    """Der Bucket merkt sich, welche Aufrufe und Tokens schon abgerechnet sind —
    ohne das wuerden sie in _ai_usage_calc ein zweites Mal geschaetzt."""
    app_mod._record_ai_usage("pplx-low", {
        "input_tokens": 1000, "output_tokens": 200,
        "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
        "cost_usd": 0.02})
    stored = json.loads(app_mod._meta_get("ai_usage_totals"))["pplx-low"]
    assert stored["calls"] == 1 and stored["cost_calls"] == 1
    assert stored["cost_usd"] == pytest.approx(0.02)
    assert stored["cost_input_tokens"] == 1000
    assert stored["cost_output_tokens"] == 200


def test_usage_calc_uses_real_cost_for_settled_calls(app_mod):
    models = {"pplx-low": {"input_tokens": 1000, "output_tokens": 200,
                            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
                            "calls": 1, "cost_usd": 0.02, "cost_calls": 1,
                            "cost_input_tokens": 1000, "cost_output_tokens": 200,
                            "cost_cache_creation_input_tokens": 0,
                            "cost_cache_read_input_tokens": 0}}
    # Nur die gemeldeten 0.02 — keine Token-Schaetzung, keine Request-Gebuehr.
    assert app_mod._ai_usage_calc(models)["estimated_usd"] == pytest.approx(0.02)


def test_usage_calc_mixes_settled_and_estimated_calls(app_mod):
    """Ein ueber die Umstellung hinweg gewachsener Zaehler enthaelt beides. Der
    abgerechnete Teil zaehlt echt, der Rest wird weiter geschaetzt."""
    models = {"pplx-fast": {"input_tokens": 1_000_000 + 500, "output_tokens": 0,
                        "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
                        "calls": 2, "cost_usd": 0.01, "cost_calls": 1,
                        "cost_input_tokens": 500, "cost_output_tokens": 0,
                        "cost_cache_creation_input_tokens": 0,
                        "cost_cache_read_input_tokens": 0}}
    # 0.01 echt + Schaetzung fuer den Rest (1M input = $0.20 + 0.0025 Gebuehr).
    assert app_mod._ai_usage_calc(models)["estimated_usd"] == pytest.approx(0.2125)


def test_usage_calc_unchanged_for_legacy_buckets(app_mod):
    """Buckets von vor der Umstellung haben keine cost_*-Felder — sie muessen sich
    exakt wie bisher verhalten."""
    models = {"pplx-low": {"input_tokens": 1_000_000, "output_tokens": 1_000_000,
                            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
                            "calls": 1}}
    # $0.20 input + $1.20 output + 0.0025 Gebuehr
    assert app_mod._ai_usage_calc(models)["estimated_usd"] == pytest.approx(1.4025)


def test_history_repeat_accepts_perplexity_provider(app_mod, monkeypatch):
    _write_options(app_mod, perplexity_api_key="p-key")
    with app_mod.db() as con:
        con.execute("INSERT INTO ai_analyses (kind, title, model, summary, usage, ts, prompt) "
                    "VALUES (?,?,?,?,?,?,?)",
                    ("single", "Test", "pplx-low", "alt", "{}", 0, "Alter Prompt"))
    _patch_requests(monkeypatch, _FakeResponse(payload=_agent_payload(text="Neue Antwort")))
    c = app_mod.app.test_client()
    r = c.post("/api/ai/history/1/repeat", headers=ING, json={"provider": "perplexity"})
    assert r.status_code == 200
    assert r.get_json()["summary"] == "Neue Antwort"


def test_perplexity_merges_search_results_across_steps(app_mod, monkeypatch):
    """Eine mehrstufige Recherche legt mehrere `search_results`-Schritte ins
    `output`-Array — die Marker zaehlen gegen alle zusammen, nicht nur den ersten."""
    _patch_requests(monkeypatch, _FakeResponse(payload=_agent_payload(
        text="Vergleich.[1][3]",
        results=_sources("https://schritt1.example/1"),
        extra_steps=[{"type": "search_results",
                      "results": _sources("https://schritt2.example/2",
                                          "https://schritt2.example/3", start_id=2)}])))
    text, _usage, _err = app_mod._ai_request("p-key", "pplx-low", "Prompt",
                                             max_tokens=200, log_ctx="Test")
    assert text == ("Vergleich.[1](https://schritt1.example/1)"
                    "[3](https://schritt2.example/3)")


def test_perplexity_aligns_on_ids_not_position(app_mod, monkeypatch):
    """Die Marker verweisen auf die `id` des Treffers. Klafft eine Luecke, darf die
    Nummerierung nicht verrutschen — sonst zeigte `[3]` auf die falsche Quelle."""
    _patch_requests(monkeypatch, _FakeResponse(payload=_agent_payload(
        text="Luecke.[1][2][3]",
        results=[{"id": 1, "url": "https://eins.example"},
                 {"id": 3, "url": "https://drei.example"}])))
    text, _usage, _err = app_mod._ai_request("p-key", "pplx-low", "Prompt",
                                             max_tokens=200, log_ctx="Test")
    assert text == "Luecke.[1](https://eins.example)[2][3](https://drei.example)"


def test_perplexity_logs_how_many_markers_stayed_unlinked(app_mod, monkeypatch, caplog):
    """Ohne diese Zeile im Log wäre nicht zu unterscheiden, ob die Verlinkung
    kaputt ist oder die gelieferte Quellenliste schlicht zu kurz war."""
    _patch_requests(monkeypatch, _FakeResponse(payload=_agent_payload(
        text="Nightlife.[9][58][74]",
        results=_sources(*[f"https://x.example/{i}" for i in range(10)]))))
    with caplog.at_level("INFO"):
        text, _usage, _err = app_mod._ai_request("p-key", "pplx-fast", "Prompt",
                                                 max_tokens=200, log_ctx="Regionen-Vergleich")
    assert "[58]" in text and "[74]" in text, "unauflösbare Marker bleiben unverändert"
    msg = " ".join(r.getMessage() for r in caplog.records)
    assert "2 Zitat-Nummern ohne Quelle" in msg and "höchste: 74" in msg


def test_perplexity_structured_output_passes_the_source_list(app_mod, monkeypatch):
    """Bei Structured Output werden die URLs nur durchgereicht (verlinkt wird erst
    nach dem Parsen) — dieselbe Ausrichtung an den IDs muss auch dort gelten."""
    schema = {"type": "object", "properties": {"score": {"type": "integer"}},
              "required": ["score"], "additionalProperties": False}
    _patch_requests(monkeypatch, _FakeResponse(payload=_agent_payload(
        text='{"score": 1}',
        results=_sources("https://a.example", "https://b.example"))))
    _text, usage, _err = app_mod._ai_request("p-key", "pplx-fast", "Prompt", max_tokens=200,
                                             log_ctx="Test", output_schema=schema)
    assert usage["citation_urls"] == ["https://a.example", "https://b.example"]


def test_perplexity_strips_cite_markers(app_mod, monkeypatch):
    """Die Agent API schreibt Quellenverweise als `cite[36][web:AP2Q...]` mitten in
    den Text. Die Kennung hinter `web:` ist eine opake ID, die sich gegen unsere
    positionsbasierte Quellenliste nicht aufloesen laesst — der ganze Marker muss
    weg, sonst steht er als Zeichensalat in der Antwort."""
    _patch_requests(monkeypatch, _FakeResponse(payload=_agent_payload(
        text="Acht Sonnenstunden. cite[36][web:AP2QHPgnj4BqitwjUF7EcRM3]",
        results=_sources("https://a.example", "https://b.example"))))
    text, _usage, _err = app_mod._ai_request("p-key", "pplx-low", "Prompt",
                                             max_tokens=200, log_ctx="Test")
    assert text == "Acht Sonnenstunden."


def test_perplexity_strips_cite_without_a_number(app_mod, monkeypatch):
    """Ohne fuehrende Zahl darf kein einsames „cite" zurueckbleiben."""
    _patch_requests(monkeypatch, _FakeResponse(payload=_agent_payload(
        text="Badeunfaelle moeglich. cite[web:AP2QHPgnj4][web:blomINkUrk]",
        results=_sources("https://a.example"))))
    text, _usage, _err = app_mod._ai_request("p-key", "pplx-low", "Prompt",
                                             max_tokens=200, log_ctx="Test")
    assert text == "Badeunfaelle moeglich."
    assert "cite" not in text and "web:" not in text


def test_perplexity_keeps_a_resolvable_number_inside_a_cite_marker(app_mod, monkeypatch):
    """Steckt im Marker eine Nummer, die zur Quellenliste passt, wird sie verlinkt
    statt mit weggeworfen."""
    _patch_requests(monkeypatch, _FakeResponse(payload=_agent_payload(
        text="Klar belegt cite[1][web:xyz] soweit.",
        results=_sources("https://a.example", "https://b.example"))))
    text, _usage, _err = app_mod._ai_request("p-key", "pplx-low", "Prompt",
                                             max_tokens=200, log_ctx="Test")
    assert text == "Klar belegt [1](https://a.example) soweit."


def test_region_compare_budget_grows_with_the_number_of_targets(app_mod):
    """Feste 8192 Tokens reichten nicht: bei fuenf Zielen brach die Auswertung nach
    dem dritten ab (8350 Output-Tokens gemeldet). Je Ziel neun Kriterien in
    Fliesstext, dazu Tabelle und Fazit."""
    ai_routes = importlib.import_module("ai_routes")
    assert ai_routes._region_compare_max_tokens(2) < ai_routes._region_compare_max_tokens(5)
    assert ai_routes._region_compare_max_tokens(5) > 20000
    assert ai_routes._region_compare_max_tokens(99) <= 40000


def test_truncated_answers_are_flagged(app_mod, monkeypatch):
    """`status: incomplete` heisst abgeschnitten. Ohne Kennzeichen haelt man die
    Antwort fuer vollstaendig — sie hoert einfach mittendrin auf."""
    _patch_requests(monkeypatch, _FakeResponse(payload=_agent_payload(status="incomplete")))
    _text, usage, err = app_mod._ai_request("p-key", "pplx-low", "Prompt",
                                            max_tokens=200, log_ctx="Test")
    assert err is None
    assert usage["truncated"] is True


def test_complete_answers_are_not_flagged(app_mod, monkeypatch):
    _patch_requests(monkeypatch, _FakeResponse(payload=_agent_payload()))
    _text, usage, _err = app_mod._ai_request("p-key", "pplx-low", "Prompt",
                                             max_tokens=200, log_ctx="Test")
    assert "truncated" not in usage
