"""KI-Provider-Client (Anthropic + Gemini + Perplexity): Dispatcher, Requests,
Structured Output, Websuche — ausgelagert aus app.py (Backlog #12, 2. Tranche).
Geteilte Primitiven über `import app as A` (spät gebunden, monkeypatch-
sicher); anthropic/genai sind dieselben Modul-Objekte wie in app.py —
Test-Patches auf app_mod.genai.Client wirken daher auch hier. Perplexity hat
kein offizielles Python-SDK — reiner REST-Aufruf über `requests` (bereits
Add-on-Abhängigkeit) gegen die Agent API (`/v1/agent`).
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

_PERPLEXITY_API_URL = "https://api.perplexity.ai/v1/agent"
_PERPLEXITY_CITATION_RE = re.compile(r'\[(\d+)\](?!\()')


def _perplexity_output_text(data: dict):
    """Antworttext aus dem typisierten `output`-Array der Agent API.

    Das rohe JSON hat kein `output_text` — das ist eine Bequemlichkeit der SDKs,
    und wir sprechen die API direkt per `requests` an. Der Text steckt im
    `message`-Schritt, dessen `content` ein Array von Teilen (`output_text`) ist
    und nicht wie bei Sonar ein String; ein blanker String wird trotzdem
    akzeptiert, das kostet nichts und deckt schlichtere Antworten mit ab.

    Rückgabe `None` heißt „kein message-Schritt gefunden" (unerwartete Struktur,
    der Aufrufer meldet 'failed'), `''` heißt „Schritt da, aber leer" ('empty') —
    diese beiden Fälle dürfen nicht zusammenfallen."""
    for item in (data.get('output') or []):
        if not isinstance(item, dict) or item.get('type') != 'message':
            continue
        content = item.get('content')
        if isinstance(content, str):
            return content
        return ''.join(p.get('text') or '' for p in (content or [])
                       if isinstance(p, dict) and p.get('type') in ('output_text', 'text'))
    return None


def _perplexity_citation_urls(data: dict) -> list:
    """Quellenliste einer Agent-API-Antwort, 1-basiert indiziert.

    Die Quellen stehen nicht mehr in den Top-Level-Feldern `search_results`/
    `citations` (so war es bei Sonar), sondern in den `search_results`-Schritten
    des `output`-Arrays. Eine mehrstufige Recherche kann mehrere davon enthalten
    — alle werden zusammengeführt.

    Die Zitat-Marker im Text zählen gegen die `id` eines Treffers, nicht gegen
    seine Position. Solange die IDs lückenlos bei 1 beginnen, ist beides dasselbe;
    fehlt eine ID oder klafft eine Lücke, wird an den IDs ausgerichtet und die
    Lücke bleibt leer (`None`) — ein Link auf die falsche Quelle wäre schlimmer
    als gar keiner. Liefert kein Treffer eine ID, bleibt nur die Reihenfolge."""
    by_id = {}
    positional = []
    for item in (data.get('output') or []):
        if not isinstance(item, dict) or item.get('type') != 'search_results':
            continue
        for r in (item.get('results') or []):
            if not isinstance(r, dict) or not r.get('url'):
                continue
            positional.append(r['url'])
            n = r.get('id')
            if isinstance(n, int) and not isinstance(n, bool) and n >= 1:
                by_id.setdefault(n, r['url'])
    if not by_id:
        return positional
    return [by_id.get(n) for n in range(1, max(by_id) + 1)]


def _perplexity_linkify_citations(text: str, urls: list | None, *, log_ctx: str = '') -> str:
    """Ersetzt Perplexitys nackte Zitat-Marker `[1]`/`[5]` im Fließtext durch
    Markdown-Links `[1](url)` auf die zugehörige Quelle — macht sie im Frontend
    (aiMdLite/aiInline) anklickbar statt als toter Text stehen zu bleiben.
    `urls` ist die 1-basierte Liste aus `_perplexity_citation_urls`; Lücken darin
    (`None`) gelten wie eine fehlende Quelle. `(?!\\()` verhindert
    Doppel-Verlinkung, falls im Text ausnahmsweise schon `[n](url)` steht.

    Zahlen ohne passende Quelle bleiben unverändert stehen — Perplexity nummeriert
    bei vielen Suchanfragen gegen eine größere interne Quellenmenge, als es in der
    Antwort zurückgibt (typisch bei Vergleichen über mehrere Ziele: `[9]` ist
    verlinkt, `[58]` nicht). Geraten wird dort nichts; ein Link auf die falsche
    Quelle wäre schlimmer als gar keiner. Das Ausmaß landet im Log, sonst wäre
    nicht zu unterscheiden, ob die Verlinkung ausfällt oder die Liste zu kurz ist."""
    if not urls:
        return text
    missing = set()

    def _sub(m):
        n = int(m.group(1))
        if 1 <= n <= len(urls) and urls[n - 1]:
            return f'[{n}]({urls[n - 1]})'
        missing.add(n)
        return m.group(0)

    out = _PERPLEXITY_CITATION_RE.sub(_sub, text)
    if missing:
        A.log.info("Perplexity (%s): %d Zitat-Nummern ohne Quelle (höchste: %d, "
                   "geliefert wurden %d) — bleiben unverlinkt",
                   log_ctx or 'KI-Antwort', len(missing), max(missing), len(urls))
    return out


def _ai_request(api_key: str, model: str, prompt: str, *, max_tokens: int,
                log_ctx: str, use_web_search: bool = True, output_schema: dict | None = None):
    """Provider-Dispatcher: leitet anhand des Modellnamens (siehe `_AI_MODELS`/
    `A._GEMINI_MODELS`/`A._PERPLEXITY_MODELS`) an die passende `_ai_request_*`-
    Funktion weiter — alle drei mit identischer Rückgabe-Signatur (text, usage,
    error_code); error_code ist None bei Erfolg, sonst 'failed' / 'refused' /
    'empty'. `usage` = {input_tokens, output_tokens, cache_creation_input_tokens,
    cache_read_input_tokens, web_search_requests}. Mit `output_schema` antwortet
    das Modell als validiertes JSON nach diesem Schema (structured outputs) —
    `text` ist dann der JSON-String. Dispatcht bewusst direkt zu den Einzel-
    Prompt-Funktionen (nicht über `_ai_request_messages`) — Tests/Aufrufer
    patchen teils gezielt `_ai_request_anthropic`/`_ai_request_gemini`/
    `_ai_request_perplexity`, das muss auf diesem Pfad weiterhin greifen."""
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


def _ai_request_messages(api_key: str, model: str, messages: list[dict], *, max_tokens: int,
                         log_ctx: str, use_web_search: bool = True,
                         output_schema: dict | None = None):
    """Wie `_ai_request`, aber mit vollständiger Konversation (`messages` =
    `[{"role": "user"|"assistant", "content": str}, ...]`) statt nur einem
    einzelnen Prompt — für Folgefragen zu einem bestehenden KI-Verlaufseintrag
    (siehe `ai_routes.py::api_ai_history_followup`). Alle drei Provider
    unterstützen Mehrfach-Turn-Konversationen; Rollen-Namen sind provider-
    übergreifend einheitlich 'user'/'assistant' (Gemini erwartet intern 'model'
    statt 'assistant' — die Umbenennung passiert in `_ai_request_gemini_messages`,
    nicht hier, damit Aufrufer sich nicht um Provider-Eigenheiten kümmern müssen)."""
    if model in A._GEMINI_MODELS:
        return A._ai_request_gemini_messages(api_key, model, messages, max_tokens=max_tokens,
                                           log_ctx=log_ctx, use_web_search=use_web_search,
                                           output_schema=output_schema)
    if model in A._PERPLEXITY_MODELS:
        return A._ai_request_perplexity_messages(api_key, model, messages, max_tokens=max_tokens,
                                               log_ctx=log_ctx, use_web_search=use_web_search,
                                               output_schema=output_schema)
    return A._ai_request_anthropic_messages(api_key, model, messages, max_tokens=max_tokens,
                                          log_ctx=log_ctx, use_web_search=use_web_search,
                                          output_schema=output_schema)


def _perplexity_reported_cost(usage_obj: dict, *, log_ctx: str = ''):
    """Tatsaechliche Kosten dieses Aufrufs in USD aus `usage.cost.total_cost`,
    oder `None`, wenn die Antwort keine brauchbare Zahl liefert.

    `total_cost` deckt laut Doku Ein-/Ausgabe-Token, Cache UND Tool-Aufrufe ab
    (im Beispiel dort: 0.00409 + 0.01316 + 0.00045 + 0.0025 = 0.0202) — es ist
    also der volle Aufruf inklusive Suchgebuehr und nicht nur der Token-Anteil.
    Perplexity garantiert das Feld nirgends fuer jedes Modell, deshalb ist es
    optional behandelt statt vorausgesetzt.

    Eine andere Waehrung als USD wird verworfen statt umgerechnet: die gesamte
    Kostenanzeige ist in USD, ein ungepruefter Zahlenwert waere schlicht falsch."""
    cost = usage_obj.get('cost')
    if not isinstance(cost, dict):
        return None
    currency = cost.get('currency')
    if currency is not None and str(currency).upper() != 'USD':
        A.log.warning("Perplexity (%s) meldet Kosten in %s statt USD — "
                      "Schaetzung wird beibehalten", log_ctx or 'KI-Antwort', currency)
        return None
    total = cost.get('total_cost')
    if isinstance(total, bool) or not isinstance(total, (int, float)):
        return None
    if total < 0:
        return None
    return float(total)


def _ai_request_perplexity(api_key: str, model: str, prompt: str, *, max_tokens: int,
                           log_ctx: str, use_web_search: bool = True,
                           output_schema: dict | None = None):
    """Einzel-Prompt-Kurzform von `_ai_request_perplexity_messages` — siehe dort."""
    return _ai_request_perplexity_messages(api_key, model, [{"role": "user", "content": prompt}],
                                          max_tokens=max_tokens, log_ctx=log_ctx,
                                          use_web_search=use_web_search, output_schema=output_schema)


def _ai_request_perplexity_messages(api_key: str, model: str, messages: list[dict], *,
                                    max_tokens: int, log_ctx: str, use_web_search: bool = True,
                                    output_schema: dict | None = None):
    """Perplexity-Variante von `_ai_request_anthropic_messages` — gleiche Rückgabe-
    Signatur (text, usage, error_code), siehe `A._ai_request_messages`. Spricht die
    Agent API (`/v1/agent`) an; die alte Sonar-Chat-Completions-API wird laut
    docs.perplexity.ai nur noch bis 27.09.2026 unterstützt. Die Sonar-Modelle
    selbst bleiben nutzbar, sie heißen dort `perplexity/<name>` — deshalb bleiben
    unsere Modell-IDs (`sonar-pro` …) in den Optionen, der Preistabelle und den
    gespeicherten Nutzungszählern unverändert, das Präfix kommt erst hier dazu.

    Unser rollenbasiertes `messages`-Schema ('user'/'assistant') geht 1:1 ins
    `input`-Array, nur mit `type: message` je Eintrag — keine Umwandlung wie bei
    Gemini. Die Websuche ist anders als bei Sonar kein Automatismus mehr, sondern
    ein Tool, das mitgeschickt werden muss; ohne diesen Eintrag sucht das Modell
    gar nicht. Damit wirkt `use_web_search=False` hier jetzt tatsächlich (bei Sonar
    war der Schalter folgenlos) und spart die Suchgebühr bei den Aufrufen, die
    ohnehin nichts nachschlagen sollen (Auto-Tags, PDF-Fallback, Feld-Vorschläge).

    `search_context_size` wird explizit auf 'low' gepinnt (statt dem API-Default zu
    überlassen) — hält die zusätzliche, gestaffelte Request-Gebühr auf der
    günstigsten Stufe UND macht sie überhaupt erst planbar:
    `ai_routes.py::_AI_PERPLEXITY_REQUEST_FEE` rechnet genau diese Stufe in die
    Kostenanzeige mit ein, ohne dieses Pinning wäre die Gebühr unvorhersehbar
    (API könnte 'medium' o. Ä. als Default nutzen) und die Schätzung stimmt nicht
    mehr. Bei `use_web_search=False` fällt sie gar nicht an, die Schätzung liegt
    dort also einen Zehntelcent zu hoch — bewusst in Kauf genommen, lieber zu
    hoch geschätzt als zu niedrig."""
    payload = {
        "model": f"perplexity/{model}",
        "input": [{"type": "message", "role": m.get("role"), "content": m.get("content")}
                  for m in messages],
        "max_output_tokens": max_tokens,
    }
    if use_web_search:
        payload["tools"] = [{"type": "web_search", "search_context_size": "low"}]
    if output_schema is not None:
        payload["response_format"] = {"type": "json_schema",
                                      "json_schema": {"name": "tuiwatch_result",
                                                      "schema": output_schema}}
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
    if not isinstance(data, dict):
        A.log.error("KI-Antwort (%s) unerwartete Struktur: %s statt Objekt",
                    log_ctx, type(data).__name__)
        return None, None, 'failed'
    status = data.get('status')
    text = _perplexity_output_text(data)
    if text is None:
        # Kein `message`-Schritt im `output`-Array: entweder ein API-Fehler mit
        # status=failed oder eine Struktur, die wir nicht kennen. Beides ist für
        # den Aufrufer dasselbe — nur der Log unterscheidet die Fälle.
        A.log.error("KI-Antwort (%s) ohne message-Schritt: status=%s, error=%s",
                    log_ctx, status, (data.get('error') or {}) if
                    isinstance(data.get('error'), dict) else data.get('error'))
        return None, None, 'failed'
    text = text.strip()
    if status == 'incomplete':
        A.log.warning("KI-Antwort (%s) am Token-Limit abgeschnitten (max_output_tokens, "
                    "%d Zeichen erhalten)", log_ctx, len(text))
    if not text:
        A.log.warning("KI-Antwort (%s) leer: status=%s", log_ctx, status)
        return None, None, 'empty'
    u = data.get('usage') or {}
    tools = u.get('tool_calls_details') or {}
    if output_schema is None:
        # Nur bei Freitext verlinken — bei Structured Output ist `text` ein
        # JSON-String, den ein Aufrufer parst; Markdown-Syntax würde ihn zerstören.
        text = _perplexity_linkify_citations(text, _perplexity_citation_urls(data),
                                             log_ctx=log_ctx)
    # Die Cache-Zähler bleiben bewusst 0: Perplexity meldet gecachte Eingabe-Token
    # in `input_tokens_details`, zählt sie aber bereits in `input_tokens` mit —
    # durchgereicht würden sie in `_ai_call_cost` ein zweites Mal berechnet.
    usage = {'input_tokens': u.get('input_tokens', 0) or 0,
             'output_tokens': u.get('output_tokens', 0) or 0,
             'cache_creation_input_tokens': 0, 'cache_read_input_tokens': 0,
             'web_search_requests': (tools.get('web_search', 0) or 0)
             if isinstance(tools, dict) else 0}
    # Die Agent API rechnet den Aufruf selbst ab und liefert das Ergebnis mit —
    # `total_cost` enthaelt neben den Token- auch die Tool-/Suchkosten. Damit
    # ersetzt eine gemeldete Zahl unsere Schaetzung aus Preistabelle plus
    # pauschaler Request-Gebuehr (siehe `ai_routes.py::_ai_call_cost`). Fehlt das
    # Feld oder ist es unbrauchbar, bleibt es bei der Schaetzung — deshalb hier
    # streng pruefen und im Zweifel gar nichts setzen.
    reported = _perplexity_reported_cost(u, log_ctx=log_ctx)
    if reported is not None:
        usage['cost_usd'] = reported
    # Quellen-URLs durchreichen: bei Structured Output stecken Perplexitys nackte
    # Marker („[7][11]") in den JSON-Strings und lassen sich erst nach dem Parsen
    # verlinken — ohne die Liste bliebe dort toter Text stehen.
    if output_schema is not None:
        srcs = _perplexity_citation_urls(data)
        if srcs:
            usage['citation_urls'] = srcs
    return text, usage, None


def _ai_request_anthropic(api_key: str, model: str, prompt: str, *, max_tokens: int,
                          log_ctx: str, use_web_search: bool = True,
                          output_schema: dict | None = None):
    """Einzel-Prompt-Kurzform von `_ai_request_anthropic_messages` — siehe dort."""
    return _ai_request_anthropic_messages(api_key, model, [{"role": "user", "content": prompt}],
                                         max_tokens=max_tokens, log_ctx=log_ctx,
                                         use_web_search=use_web_search, output_schema=output_schema)


def _ai_request_anthropic_messages(api_key: str, model: str, messages: list[dict], *,
                                   max_tokens: int, log_ctx: str, use_web_search: bool = True,
                                   output_schema: dict | None = None):
    """Reiner Claude-Aufruf ohne Flask-Abhängigkeit (kein jsonify) — nutzbar sowohl
    aus Request-Handlern als auch aus Hintergrund-Threads (z. B. Wochenüberblick),
    die keinen Flask-App-Context haben. Rückgabe-Signatur siehe `A._ai_request_messages`.
    Claudes `messages`-Format entspricht bereits 1:1 unserem provider-übergreifenden
    Rollen-Schema ('user'/'assistant') — keine Umwandlung nötig."""
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
            model=model, max_tokens=max_tokens, messages=messages, **kwargs,
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
    """Einzel-Prompt-Kurzform von `_ai_request_gemini_messages` — siehe dort."""
    return _ai_request_gemini_messages(api_key, model, [{"role": "user", "content": prompt}],
                                      max_tokens=max_tokens, log_ctx=log_ctx,
                                      use_web_search=use_web_search, output_schema=output_schema)


def _ai_request_gemini_messages(api_key: str, model: str, messages: list[dict], *,
                                max_tokens: int, log_ctx: str, use_web_search: bool = True,
                                output_schema: dict | None = None):
    """Gemini-Variante von `_ai_request_anthropic_messages` — gleiche Rückgabe-
    Signatur (text, usage, error_code), siehe `A._ai_request_messages`. Gemini
    erwartet für den Assistenten-Turn intern die Rolle 'model' statt unserem
    provider-übergreifenden 'assistant' — die Umbenennung passiert hier, Aufrufer
    bleiben provider-agnostisch. `output_schema` wird vor der Übergabe als
    `response_schema` von `additionalProperties` bereinigt (siehe
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
    contents = [genai_types.Content(role=('model' if m['role'] == 'assistant' else 'user'),
                                    parts=[genai_types.Part(text=m['content'])])
               for m in messages]
    try:
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=model, contents=contents,
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
    innerhalb eines Request-Handlers laufen. Ruft bewusst direkt `A._ai_request`
    auf (nicht über `_ai_call_messages`) — Tests/Aufrufer patchen teils gezielt
    `_ai_request`, das muss auf diesem Pfad weiterhin greifen."""
    text, usage, code = A._ai_request(api_key, model, prompt, max_tokens=max_tokens,
                                    log_ctx=log_ctx, use_web_search=use_web_search)
    if code == 'failed':
        return None, None, (jsonify({'error': 'ai_failed'}), 502)
    if code == 'refused':
        return None, None, (jsonify({'error': 'ai_refused'}), 502)
    if code == 'empty':
        return None, None, (jsonify({'error': 'ai_empty'}), 502)
    return text, usage, None


def _ai_call_messages(api_key: str, model: str, messages: list[dict], *, max_tokens: int,
                      log_ctx: str, use_web_search: bool = True):
    """Wie `_ai_call`, aber mit vollständiger Konversation statt nur einem Prompt
    — für `/api/ai/history/<id>/followup`."""
    text, usage, code = A._ai_request_messages(api_key, model, messages, max_tokens=max_tokens,
                                             log_ctx=log_ctx, use_web_search=use_web_search)
    if code == 'failed':
        return None, None, (jsonify({'error': 'ai_failed'}), 502)
    if code == 'refused':
        return None, None, (jsonify({'error': 'ai_refused'}), 502)
    if code == 'empty':
        return None, None, (jsonify({'error': 'ai_empty'}), 502)
    return text, usage, None

