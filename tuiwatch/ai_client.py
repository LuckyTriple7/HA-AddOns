"""KI-Provider-Client (Anthropic + Gemini + Perplexity): Dispatcher, Requests,
Structured Output, Websuche — ausgelagert aus app.py (Backlog #12, 2. Tranche).
Geteilte Primitiven über `import app as A` (spät gebunden, monkeypatch-
sicher); anthropic/genai sind dieselben Modul-Objekte wie in app.py —
Test-Patches auf app_mod.genai.Client wirken daher auch hier. Perplexity hat
kein offizielles Python-SDK — reiner REST-Aufruf über `requests` (bereits
Add-on-Abhängigkeit), OpenAI-kompatibles Chat-Completions-Schema.
"""
import logging
import re

from flask import jsonify

import anthropic
import requests
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

import app as A

_PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"
_PERPLEXITY_CITATION_RE = re.compile(r'\[(\d+)\](?!\()')


def _perplexity_linkify_citations(text: str, data: dict) -> str:
    """Ersetzt Perplexitys nackte Zitat-Marker `[1]`/`[5]` im Fließtext durch
    Markdown-Links `[1](url)` auf die zugehörige Quelle aus `search_results`
    (bevorzugt) bzw. `citations` — macht sie im Frontend (aiMdLite/aiInline)
    anklickbar statt als toter Text stehen zu bleiben. Nummerierung ist
    1-basiert wie im Original; Zahlen ohne passende Quelle (außerhalb der
    Liste) bleiben unverändert. `(?!\\()` verhindert Doppel-Verlinkung, falls
    im Text ausnahmsweise schon `[n](url)` steht."""
    search_results = data.get('search_results') or []
    urls = [r.get('url') for r in search_results if isinstance(r, dict) and r.get('url')]
    if not urls:
        urls = [u for u in (data.get('citations') or []) if u]
    if not urls:
        return text

    def _sub(m):
        n = int(m.group(1))
        return f'[{n}]({urls[n - 1]})' if 1 <= n <= len(urls) else m.group(0)

    return _PERPLEXITY_CITATION_RE.sub(_sub, text)


def _ai_request(api_key: str, model: str, prompt: str, *, max_tokens: int,
                log_ctx: str, use_web_search: bool = True, output_schema: dict | None = None):
    """Provider-Dispatcher: leitet anhand des Modellnamens (siehe `_AI_MODELS`/
    `A._GEMINI_MODELS`/`A._PERPLEXITY_MODELS`) an die passende `_ai_request_*`-
    Funktion weiter — alle drei mit identischer Rückgabe-Signatur (text, usage,
    error_code); error_code ist None bei Erfolg, sonst 'failed' / 'refused' /
    'empty'. `usage` = {input_tokens, output_tokens, cache_creation_input_tokens,
    cache_read_input_tokens, web_search_requests}. Mit `output_schema` antwortet
    das Modell als validiertes JSON nach diesem Schema (structured outputs) —
    `text` ist dann der JSON-String."""
    if model in A._GEMINI_MODELS:
        return A._ai_request_gemini(api_key, model, prompt, max_tokens=max_tokens,
                                  log_ctx=log_ctx, use_web_search=use_web_search,
                                  output_schema=output_schema)
    if model in A._PERPLEXITY_MODELS:
        return A._ai_request_perplexity(api_key, model, prompt, max_tokens=max_tokens,
                                      log_ctx=log_ctx, use_web_search=use_web_search,
                                      output_schema=output_schema)
    return A._ai_request_anthropic(api_key, model, prompt, max_tokens=max_tokens,
                                 log_ctx=log_ctx, use_web_search=use_web_search,
                                 output_schema=output_schema)


def _ai_request_perplexity(api_key: str, model: str, prompt: str, *, max_tokens: int,
                           log_ctx: str, use_web_search: bool = True,
                           output_schema: dict | None = None):
    """Perplexity-Variante von `_ai_request_anthropic` — gleiche Rückgabe-Signatur
    (text, usage, error_code), siehe `A._ai_request`. Sonar-Modelle durchsuchen das
    Web bei JEDER Anfrage automatisch (kein separates Tool wie bei Claude/Gemini) —
    `use_web_search=False` hat hier keine Wirkung, es gibt keinen Schalter dafür.
    `search_context_size` wird explizit auf 'low' gepinnt (statt dem API-Default zu
    überlassen) — hält die zusätzliche, gestaffelte Request-Gebühr auf der
    günstigsten Stufe UND macht sie überhaupt erst planbar: `ai_routes.py::
    _AI_PERPLEXITY_REQUEST_FEE` rechnet genau diese Stufe in die Kostenanzeige mit
    ein, ohne dieses Pinning wäre die Gebühr unvorhersehbar (API könnte 'medium'
    o. Ä. als Default nutzen) und die Schätzung stimmt nicht mehr."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "web_search_options": {"search_context_size": "low"},
    }
    if output_schema is not None:
        payload["response_format"] = {"type": "json_schema",
                                      "json_schema": {"schema": output_schema}}
    try:
        resp = requests.post(
            _PERPLEXITY_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload, timeout=90,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        A.log.warning("KI-Anfrage fehlgeschlagen (%s): %s", log_ctx, e)
        return None, None, 'failed'
    except ValueError as e:
        A.log.error("KI-Antwort (%s) kein gültiges JSON: %s", log_ctx, e)
        return None, None, 'failed'
    try:
        choice = data["choices"][0]
        text = (choice["message"]["content"] or "").strip()
        finish_reason = choice.get("finish_reason")
        u = data.get("usage") or {}
    except (KeyError, IndexError, TypeError) as e:
        A.log.error("KI-Antwort (%s) unerwartete Struktur: %s: %s", log_ctx, type(e).__name__, e)
        return None, None, 'failed'
    if finish_reason == 'length':
        A.log.warning("KI-Antwort (%s) am Token-Limit abgeschnitten (max_tokens, "
                    "%d Zeichen erhalten)", log_ctx, len(text))
    if not text:
        A.log.warning("KI-Antwort (%s) leer: finish_reason=%s", log_ctx, finish_reason)
        return None, None, 'empty'
    if output_schema is None:
        # Nur bei Freitext verlinken — bei Structured Output ist `text` ein
        # JSON-String, den ein Aufrufer parst; Markdown-Syntax würde ihn zerstören.
        text = _perplexity_linkify_citations(text, data)
    usage = {'input_tokens': u.get('prompt_tokens', 0) or 0,
             'output_tokens': u.get('completion_tokens', 0) or 0,
             'cache_creation_input_tokens': 0, 'cache_read_input_tokens': 0,
             'web_search_requests': u.get('num_search_queries', 0) or 0}
    return text, usage, None


def _ai_request_anthropic(api_key: str, model: str, prompt: str, *, max_tokens: int,
                          log_ctx: str, use_web_search: bool = True,
                          output_schema: dict | None = None):
    """Reiner Claude-Aufruf ohne Flask-Abhängigkeit (kein jsonify) — nutzbar sowohl
    aus Request-Handlern als auch aus Hintergrund-Threads (z. B. Wochenüberblick),
    die keinen Flask-App-Context haben. Rückgabe-Signatur siehe `A._ai_request`."""
    kwargs = {}
    if use_web_search:
        # allowed_callers=["direct"]: Haiku unterstützt kein programmatic tool
        # calling — ohne das Flag lehnt die API web_search auf diesem Modell ab.
        val = A.load_config().get('ai_max_web_searches')
        try:
            max_uses = int(val) if val is not None else 12
        except (TypeError, ValueError):
            max_uses = 12
        max_uses = max(1, min(max_uses, 50))
        kwargs['tools'] = [{"type": "web_search_20260209", "name": "web_search",
                            "allowed_callers": ["direct"], "max_uses": max_uses}]
    if output_schema is not None:
        kwargs['output_config'] = {'format': {'type': 'json_schema', 'schema': output_schema}}
    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=model, max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}], **kwargs,
        )
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
        A.log.warning("KI-Anfrage fehlgeschlagen (%s): %s", log_ctx, e)
        return None, None, 'failed'
    if resp.stop_reason == 'refusal':
        return None, None, 'refused'
    text = "\n\n".join(b.text for b in resp.content if b.type == 'text').strip()
    if resp.stop_reason == 'max_tokens':
        # Antwort abgeschnitten — bei Structured Output ist das JSON dann meist
        # unvollständig und der Aufrufer scheitert still beim Parsen. Loggen,
        # sonst ist der Fehler von außen nicht diagnostizierbar (nur 200 OK im Log).
        A.log.warning("KI-Antwort (%s) am Token-Limit abgeschnitten (max_tokens, "
                    "%d Zeichen erhalten)", log_ctx, len(text))
    if not text:
        A.log.warning("KI-Antwort (%s) leer: stop_reason=%s", log_ctx, resp.stop_reason)
        return None, None, 'empty'
    u = resp.usage
    server_tool_use = getattr(u, 'server_tool_use', None)
    usage = {'input_tokens': u.input_tokens, 'output_tokens': u.output_tokens,
             'cache_creation_input_tokens': getattr(u, 'cache_creation_input_tokens', 0) or 0,
             'cache_read_input_tokens': getattr(u, 'cache_read_input_tokens', 0) or 0,
             'web_search_requests': getattr(server_tool_use, 'web_search_requests', 0) or 0}
    return text, usage, None


_GEMINI_REFUSAL_REASONS = {
    genai_types.FinishReason.SAFETY, genai_types.FinishReason.PROHIBITED_CONTENT,
    genai_types.FinishReason.BLOCKLIST, genai_types.FinishReason.RECITATION,
    genai_types.FinishReason.SPII, genai_types.FinishReason.IMAGE_SAFETY,
    genai_types.FinishReason.IMAGE_PROHIBITED_CONTENT,
}


def _gemini_sanitize_schema(schema):
    """Entfernt `additionalProperties`/`additional_properties` rekursiv aus einem
    JSON-Schema-Dict. Der Python-SDK-Typ `genai.types.Schema` akzeptiert dieses
    Feld zwar lokal (Pydantic-Alias), die echte Gemini-REST-API lehnt es aber mit
    400 INVALID_ARGUMENT ab ("Unknown name additional_properties") — in der
    Praxis per Live-Aufruf bestätigt, nicht nur Doku/SDK-Vermutung."""
    if isinstance(schema, dict):
        return {k: _gemini_sanitize_schema(v) for k, v in schema.items()
                if k not in ('additionalProperties', 'additional_properties')}
    if isinstance(schema, list):
        return [_gemini_sanitize_schema(v) for v in schema]
    return schema


_GEMINI_THINKING_TOKEN_RESERVE = 2048


def _ai_request_gemini(api_key: str, model: str, prompt: str, *, max_tokens: int,
                       log_ctx: str, use_web_search: bool = True,
                       output_schema: dict | None = None):
    """Gemini-Variante von `_ai_request_anthropic` — gleiche Rückgabe-Signatur
    (text, usage, error_code), siehe `A._ai_request`. `output_schema` wird vor der
    Übergabe als `response_schema` von `additionalProperties` bereinigt (siehe
    `_gemini_sanitize_schema`) — Gemini kennt dieses JSON-Schema-Feld nicht.
    Websuche über Google-Search-Grounding — kennt kein `max_uses`-Äquivalent,
    `ai_max_web_searches` wirkt daher nur bei Anthropic.

    `max_output_tokens` teilt sich bei Gemini das Budget mit den intern
    generierten „Thinking"-Tokens (anders als bei Anthropic, wo Thinking hier
    nicht genutzt wird) — bei knappen `max_tokens`-Werten (z. B. 300 für
    Auto-Tags, 500 für den Wochenüberblick) frisst das Thinking das komplette
    Budget auf, sodass die eigentliche Antwort leer oder mitten im Satz
    abgeschnitten zurückkommt, ohne dass ein Fehler auftritt (live beobachtet:
    Auto-Tags ohne Fehler aber ohne Tags, Wochenüberblick-Text bricht ab).
    Reserve draufschlagen, damit für die eigentliche Antwort immer genug
    Budget übrig bleibt.

    Gemini lehnt Tool-Use (Websuche) zusammen mit `response_mime_type: application/json`
    kategorisch ab ("Tool use with a response mime type ... is unsupported", live per
    400 INVALID_ARGUMENT bestätigt) — anders als Anthropic, das beides kombinieren kann.
    Bei gleichzeitiger Anfrage hat das Schema Vorrang (Aufrufer verlassen sich auf
    parsebares JSON), Websuche wird für diesen Aufruf stillschweigend übersprungen."""
    cfg_kwargs = {'max_output_tokens': max_tokens + _GEMINI_THINKING_TOKEN_RESERVE}
    if use_web_search and output_schema is not None:
        A.log.info("Gemini (%s): Websuche + Structured Output nicht kombinierbar — "
                 "Websuche für diesen Aufruf übersprungen", log_ctx)
        use_web_search = False
    if use_web_search:
        cfg_kwargs['tools'] = [genai_types.Tool(google_search=genai_types.GoogleSearch())]
    if output_schema is not None:
        cfg_kwargs['response_mime_type'] = 'application/json'
        cfg_kwargs['response_schema'] = _gemini_sanitize_schema(output_schema)
    try:
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=model, contents=prompt,
            config=genai_types.GenerateContentConfig(**cfg_kwargs),
        )
        candidates = resp.candidates or []
        if candidates and candidates[0].finish_reason in _GEMINI_REFUSAL_REASONS:
            return None, None, 'refused'
        text = (resp.text or '').strip()
        u = resp.usage_metadata
    except genai_errors.APIError as e:
        A.log.warning("KI-Anfrage fehlgeschlagen (%s): %s", log_ctx, e)
        return None, None, 'failed'
    except Exception as e:
        # Absichtlich breit: auch SDK-interne Fehler (z. B. im Automatic-Function-
        # Calling-Loop bei aktivierter Websuche, oder beim Antwort-Parsing) dürfen
        # nicht bis zu Flask unabgefangen durchschlagen — sonst kommt beim Aufrufer
        # eine HTML-Fehlerseite statt JSON an (Frontend meldet dann nur generisch
        # "fehlgeschlagen", live beobachtet: 200 OK von Google, danach Absturz).
        A.log.error("KI-Anfrage (%s) unerwartet fehlgeschlagen: %s: %s",
                 log_ctx, type(e).__name__, e)
        return None, None, 'failed'
    if not text:
        fr = candidates[0].finish_reason if candidates else None
        A.log.warning("KI-Antwort (%s) leer: finish_reason=%s", log_ctx, fr)
        return None, None, 'empty'
    web_searches = 0
    try:
        web_searches = len(candidates[0].grounding_metadata.web_search_queries or [])
    except (AttributeError, IndexError, TypeError):
        pass
    usage = {'input_tokens': (getattr(u, 'prompt_token_count', 0) or 0),
             'output_tokens': (getattr(u, 'candidates_token_count', 0) or 0),
             'cache_creation_input_tokens': 0,
             'cache_read_input_tokens': (getattr(u, 'cached_content_token_count', 0) or 0),
             'web_search_requests': web_searches}
    return text, usage, None


def _ai_call(api_key: str, model: str, prompt: str, *, max_tokens: int, log_ctx: str,
             use_web_search: bool = True):
    """Flask-Route-Wrapper um `A._ai_request`: gleiche Erfolgs-Rückgabe (text, usage,
    None), Fehler als (None, None, (jsonify(...), status)) — für Endpunkte, die
    innerhalb eines Request-Handlers laufen."""
    text, usage, code = A._ai_request(api_key, model, prompt, max_tokens=max_tokens,
                                    log_ctx=log_ctx, use_web_search=use_web_search)
    if code == 'failed':
        return None, None, (jsonify({'error': 'ai_failed'}), 502)
    if code == 'refused':
        return None, None, (jsonify({'error': 'ai_refused'}), 502)
    if code == 'empty':
        return None, None, (jsonify({'error': 'ai_empty'}), 502)
    return text, usage, None

