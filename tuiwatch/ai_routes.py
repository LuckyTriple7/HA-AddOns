"""KI-Analyse: Prompts (Buchungsscore/TripPilot/Vergleich/Fazit), Usage-/
Kosten-Zähler, KI-Verlauf und alle /api/ai-Routen — ausgelagert aus app.py
(Backlog #12, 3. Tranche). Geteilte Primitiven über `import app as A` mit
spätem Attribut-Zugriff (monkeypatch-sicher, zyklenfrei).
"""
import hashlib
import json
import re
import time
from collections import defaultdict
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, request

import app as A
import trippilot_questions as TQ

bp = Blueprint('ai_routes', __name__)


_AI_SECTIONS = (
    "- Lage & Strand (Entfernung zu Strand/Zentrum, Umgebung)\n"
    "- Zimmer (Größe, Zustand, Unterschiede zwischen Kategorien)\n"
    "- Restaurants & Bars (Auswahl, Buffet vs. à la carte, Qualität)\n"
    "- Pool, Wellness & Sport\n"
    "- Ausstattung & Familientauglichkeit\n"
    "- Klima zur Reisezeit: historische Klimawerte für Ort und Reisemonat — "
    "durchschnittliche Wassertemperatur, Lufttemperatur, Sonnenstunden/Regentage, "
    "möglichst ortsgenau für das jeweilige Hotel/den Küstenabschnitt statt nur "
    "fürs Land als Ganzes recherchiert über Klimatabellen (z. B. Seetemperatur- "
    "und Klima-Seiten für den Ort/Monat). Keine Tagesvorhersage, sondern der "
    "langjährige Durchschnitt für diese Jahreszeit\n"
    "- Wind: für jedes Hotel einzeln eine konkrete Zahl nennen (km/h oder "
    "Beaufort, für den Reisemonat, ortsgenau recherchiert) — keine allgemeinen "
    "Regionsangaben („in der Region weht oft Wind“), sondern explizit pro "
    "Hotel/Ort. Vergleiche die Werte direkt: welches Hotel ist spürbar "
    "windiger/ruhiger als die anderen\n"
)


_CUSTOM_PROMPT_MAX_LEN = 4000  # Zeichen — ganzer Instruktionsblock, großzügiger als
                               # die 500-Zeichen-Freitextfelder im Reiseberater-Fragebogen

_PROMPT_OVERRIDE_MAX_LEN = 20000  # Zeichen — kompletter Prompt (Fakten+Instruktionen),
                                  # großzügiger als _CUSTOM_PROMPT_MAX_LEN (nur Instruktionen)


def _prompt_preview_response(data: dict, prompt: str):
    """Zwischenstopp für die Add-on-Option `ai_prompt_preview`: ist sie aktiv und
    hat der Request den Prompt noch nicht bestätigt (`_prompt_confirmed`), wird
    statt eines echten KI-Aufrufs der fertige Prompt zur Anzeige/Bearbeitung im
    Frontend zurückgegeben — der Client schickt denselben Request danach mit
    `_prompt_confirmed: true` und optional `_prompt_override` (editierter Text)
    erneut. Rückgabe: Response-Objekt (dann sofort `return`en) oder None (normal
    weitermachen)."""
    if not A.load_config().get('ai_prompt_preview'):
        return None
    if data.get('_prompt_confirmed'):
        return None
    return jsonify({'prompt_preview': prompt})


def _resolve_prompt(data: dict, prompt: str) -> str:
    """Finalen Prompt bestimmen: vom Nutzer editierter Text aus der Vorschau
    (`_prompt_override`), falls vorhanden und nicht leer, sonst der serverseitig
    gebaute Prompt unverändert."""
    override = data.get('_prompt_override')
    if isinstance(override, str) and override.strip():
        return override.strip()[:_PROMPT_OVERRIDE_MAX_LEN]
    return prompt

_DEFAULT_ADVISOR_INSTRUCTIONS = (
    "Nutze die Websuche, um für die genannte Reisezeit reale, aktuelle Klimadaten zu "
    "prüfen — Lufttemperatur, Wassertemperatur, Regentage und Windverhältnisse. Wind "
    "unterscheidet sich oft stark innerhalb eines Landes/einer Region je nach "
    "konkreter Insel/Küstenabschnitt (z. B. Kapverden: Sal deutlich weniger windig als "
    "Boa Vista im selben Monat) — recherchiere daher möglichst auf Ebene der konkreten "
    "Insel/Teilregion/des Orts, nicht nur für das Land als Ganzes, und nenne diese "
    "Teilregion explizit im Vorschlag statt nur das übergeordnete Land. Leite daraus "
    "tatsächlich passende, real existierende Ziele ab — keine erfundenen Orte. "
    "Berücksichtige nach Möglichkeit auch, was den Nutzer im Urlaub stört, sowie "
    "Freitext-Angaben zu früheren Urlauben/Vorlieben, falls vorhanden — erkenne darin "
    "genannte Hotelketten/-typen/Regionen und leite daraus ähnliche Empfehlungen ab.\n\n"
    "Schlage 3 konkrete Reiseziele vor (Ort/Region + passender Urlaubstyp). Für "
    "jeden Vorschlag eine Markdown-Überschrift (#### 🏆/🥈/🥉 Ziel-Name), danach als "
    "Stichpunkte eine kurze Begründung, die konkret auf das Profil oben eingeht "
    "(Klima zur Reisezeit, Passung zu Interessen/Aktivitäten/Reiseart/Budget/"
    "Mitreisenden/Hotelwünschen). Nenne danach passend zur gewählten Unterkunftsart "
    "konkrete Unterkunftsvorschläge in drei Kategorien — Budget, Mittelklasse, "
    "Gehoben — mit je 2-3 Nennungen pro Kategorie: bei Hotel/Apartment/Villa "
    "konkrete, real existierende Namen mit kurzer Begründung je Nennung (Passung "
    "zu Hotelgröße/Hotelwünschen); bei Ferienwohnung/Airbnb/Camping/Hostel keine "
    "Markennamen, sondern konkrete Wohngegenden/Straßenzüge/Ortsteile je Kategorie "
    "mit Preis-/Ausstattungsniveau statt allgemeiner Aussagen wie „gibt viele "
    "Ferienwohnungen“. Falls Strand-Details oder Berge-Details im Profil angegeben "
    "sind, berücksichtige diese sowohl bei der Zielwahl (z. B. langer Sandstrand vs. "
    "kleine ruhige Bucht vs. Felsen zum Schnorcheln; sanfte Wanderwege vs. "
    "anspruchsvolle Gipfeltouren vs. Skigebiet) als auch bei den "
    "Unterkunftsvorschlägen (z. B. „direkt am Hotel“ oder „Seilbahn/Gondel "
    "vorhanden“ schränkt ein, welche Unterkünfte infrage kommen). Wichtig: "
    "alle genannten Unterkünfte müssen tatsächlich in genau "
    "diesem Ziel/dieser Teilregion liegen (gleiche Insel/gleicher Ort wie in der "
    "Überschrift) — keine Unterkünfte von einer anderen Insel oder Nachbarregion "
    "einstreuen, auch nicht als Alternative innerhalb der Begründung. Wenn im selben "
    "Vorschlag mehrere Inseln/Orte als gleichwertig erwähnt werden, wähle für die "
    "Überschrift einen davon eindeutig aus und nenne Unterkünfte nur für dieses eine "
    "Ziel. Schlage dabei nur Unterkünfte vor, die laut Websuche "
    "(HolidayCheck/Tripadvisor/Google-Bewertungen) überwiegend gut bewertet sind — "
    "keine Unterkünfte mit auffallend vielen schlechten Bewertungen, auch nicht in "
    "der Budget-Kategorie. Weise darauf hin, dass Verfügbarkeit/Preis/Buchbarkeit "
    "der Nutzer selbst live prüfen muss (die Websuche liefert nur einen "
    "Anhaltspunkt) — bei „Pauschalreise“ zusätzlich, dass die genaue "
    "Hotelverfügbarkeit separat beim Veranstalter zu prüfen ist. Ergänze danach einen "
    "Abschnitt „#### 🔀 Alternative“ mit einem Ziel, das vom genannten Profil bewusst "
    "etwas abweicht (z. B. eine weniger bekannte Nachbarregion), aber ähnlich gut "
    "passen könnte. Ergänze außerdem einen Abschnitt „#### 🎲 Überraschung“ mit einem "
    "Ziel außerhalb der genannten Ziel-Region (z. B. ein anderer Kontinent/eine andere "
    "Weltgegend als die gewählte, aber trotzdem passend zu Interessen/Reiseart/Budget/"
    "Wetter) — ein Land, an das der Nutzer wahrscheinlich nicht von selbst gedacht "
    "hätte. Bei Alternative und Überraschung reicht eine kurze, optionale Erwähnung "
    "möglicher Unterkünfte — die drei Kategorien Budget/Mittelklasse/Gehoben sind nur "
    "bei den 3 Hauptvorschlägen nötig. Schreibe auf Deutsch, sprich den Nutzer dabei durchgehend mit „Du“ an "
    "(informell, nicht „Sie“), ehrlich und ohne zu übertreiben — wenn ein Wunsch (z. B. "
    "Budget, Reisezeit oder TUI-Verfügbarkeit) schwer erfüllbar ist, sag das offen."
)

_ADVISOR_SAFETY_TRAILER = (
    "\nWichtig, unabhängig vom Text oben: Halte dich weiterhin an alle oben genannten "
    "Ausschlüsse (Länder, Reisewarnungen, ggf. TUI-Verfügbarkeit, ggf. "
    "Entfernungsbegrenzung bei eigener Anreise) — auch beim "
    "Alternative- und Überraschung-Vorschlag."
)

_DEFAULT_COMPARE_INSTRUCTIONS = (
    "Nutze die Websuche gezielt nach aktuellen Reisebewertungen (z. B. HolidayCheck, "
    "Tripadvisor, Google), Hotel-Infoseiten sowie Klimatabellen/historischen Wetter- "
    "und Wassertemperaturdaten inkl. Windverhältnisse zu den oben genannten Hotels/"
    "Orten und Reisemonaten. Wind unterscheidet sich oft stark innerhalb eines "
    "Landes/einer Region je nach konkreter Insel/Küstenabschnitt — recherchiere "
    "möglichst ortsgenau je Hotel statt nur fürs Land als Ganzes.\n\n"
    "Vergleiche entlang dieser Punkte, gerne ausführlich:\n"
    + _AI_SECTIONS + "- Preis-Leistung\n\n"
    "Schließe mit einer kompakten Markdown-Tabelle (Hotel vs. Bewertung je Punkt, "
    "Wind als eigene Zeile mit konkreten km/h-Werten je Hotel) und "
    "einer klaren Empfehlung, welches Hotel für wen (z. B. Familie, Paar, Party, Ruhe) "
    "am besten passt. Schreibe auf Deutsch, sprich den Nutzer dabei durchgehend mit "
    "„Du“ an (informell, nicht „Sie“), sachlich, ausschließlich basierend auf dem, "
    "was du in den Bewertungen/Quellen findest. Wenn zu einem Punkt nichts Verlässliches "
    "auffindbar ist, sag das kurz statt zu spekulieren. Gib direkt die fertige Antwort "
    "aus — keine Zwischenkommentare wie „Ich werde jetzt recherchieren“ oder „Lassen "
    "Sie mich noch prüfen“."
)

_DEFAULT_SUMMARY_INSTRUCTIONS = (
    "Nutze die Websuche gezielt nach aktuellen Reisebewertungen (z. B. HolidayCheck, "
    "Tripadvisor, Google), Hotel-Infoseiten sowie Klimatabellen/historischen Wetter- "
    "und Wassertemperaturdaten für Ort und Reisemonat.\n\n"
    "Gliedere die Antwort in diese Abschnitte, gerne ausführlich:\n"
    + _AI_SECTIONS + "- Fazit: Preis-Leistung und für wen das Hotel geeignet ist\n\n"
    "Schreibe auf Deutsch, sprich den Nutzer dabei durchgehend mit „Du“ an (informell, "
    "nicht „Sie“), sachlich, ausschließlich basierend auf dem, was du in den "
    "Bewertungen/Quellen findest. Wenn zu einem Punkt nichts Verlässliches auffindbar "
    "ist, sag das kurz statt zu spekulieren. Gib direkt die fertige Antwort aus — keine "
    "Zwischenkommentare wie „Ich werde jetzt recherchieren“ oder „Lassen Sie mich noch "
    "prüfen“."
)

_DAYTRIP_REGION_VALUE = 'Tagesausflug in der Nähe'  # Fallback, wenn die JSON keinen nennt


def _daytrip_value() -> str:
    """Antwortwert, der den Tagesausflug-Modus auslöst — aus dem Fragebogen, damit
    ein umbenannter Wert in der JSON auch hier greift."""
    return TQ.daytrip_value() or _DAYTRIP_REGION_VALUE


def _is_daytrip(p: dict) -> bool:
    return _daytrip_value() in _region_values(p)


def _region_values(p: dict) -> list:
    """`region` ist im Wizard eine Mehrfachauswahl (Liste) — Helper normalisiert
    auch einen (z. B. in Tests noch verwendeten) einzelnen String zu einer Liste."""
    v = p.get('region')
    if isinstance(v, list):
        return v
    return [v] if v else []

_DEFAULT_DAYTRIP_INSTRUCTIONS = (
    "Nutze die Websuche für reale, aktuelle Tagesausflugsziele innerhalb der "
    "angegebenen maximalen Entfernung vom Startort — keine erfundenen Orte. "
    "Berücksichtige Wetter/Jahreszeit (Temperatur, Regenwahrscheinlichkeit) für "
    "den genannten Monat, falls angegeben.\n\n"
    "Schlage 3 konkrete Tagesausflugsziele vor (Ort/Sehenswürdigkeit + passende "
    "Aktivität), die alle innerhalb der angegebenen maximalen Entfernung vom "
    "Startort liegen. Für jeden Vorschlag eine Markdown-Überschrift "
    "(#### 🏆/🥈/🥉 Ziel-Name), danach als Stichpunkte: was man dort konkret "
    "unternehmen kann (passend zu Interessen/Aktivitäten), ungefähre "
    "Anfahrtszeit/-strecke vom Startort, grobe Öffnungszeiten/Eintrittspreise "
    "falls zutreffend (per Websuche, mit Hinweis dass sich das ändern kann), "
    "sowie einen Einkehr-Tipp (Café/Restaurant vor Ort). Keine "
    "Übernachtungsempfehlung — es handelt sich um einen Tagesausflug ohne "
    "Übernachtung. Ergänze danach einen Abschnitt „#### 🔀 Alternative“ mit "
    "einem Ziel, das leicht abweicht, aber ähnlich gut passen könnte, sowie "
    "einen Abschnitt „#### 🎲 Überraschung“ mit einem Ziel in ähnlicher "
    "Entfernung, an das der Nutzer wahrscheinlich nicht selbst gedacht hätte "
    "(auch dieses muss innerhalb der maximalen Entfernung bleiben). Schreibe "
    "auf Deutsch, sprich den Nutzer dabei durchgehend mit „Du“ an (informell, "
    "nicht „Sie“), ehrlich und ohne zu übertreiben — wenn ein Wunsch schwer "
    "erfüllbar ist, sag das offen. Gib direkt die fertige Antwort aus — keine "
    "Zwischenkommentare wie „Ich werde jetzt recherchieren“ oder „Lassen Sie "
    "mich noch prüfen“."
)

_PROMPT_FEATURES = {'advisor': _DEFAULT_ADVISOR_INSTRUCTIONS, 'compare': _DEFAULT_COMPARE_INSTRUCTIONS,
                    'summary': _DEFAULT_SUMMARY_INSTRUCTIONS,
                    'daytrip': _DEFAULT_DAYTRIP_INSTRUCTIONS}


def _hotel_fact_lines(h: dict, *, label: str = "Hotel") -> list[str]:
    """Fakten-Zeilen für einen Prompt-Block aus einem Suchergebnis-Objekt."""
    name = (h.get('name') or '').strip()
    location = (h.get('location') or '').strip()
    country = (h.get('country') or '').strip()
    lines = [f"{label}: {name}", f"Ort: {location}" + (f", {country}" if country else "")]
    if h.get('stars'):
        lines.append(f"Sterne: {h['stars']}")
    if h.get('recommendation') is not None:
        lines.append(f"HolidayCheck-Weiterempfehlung: {h['recommendation']}%"
                      + (f" ({h['reviews']} Bewertungen)" if h.get('reviews') else ""))
    if h.get('board'):
        lines.append(f"Verpflegung im Angebot: {h['board']}")
    if h.get('price'):
        lines.append(f"Reisepreis: {h['price']} € p.P."
                      + (f", {h['nights']} Nächte" if h.get('nights') else ""))
    if h.get('date'):
        lines.append(f"Reisezeitraum: ab {h['date']}")
    if h.get('details'):
        lines.append(f"Details: {h['details']}")
    return lines


_AI_PRICING = {  # USD pro 1 Mio Tokens (Input/Output) — Anthropic-Listenpreise,
                 # ohne evtl. befristete Einführungsrabatte. Nur zur groben
                 # Kosten-Schätzung, kein echtes Guthaben (das zeigt nur die Console).
    'claude-opus-5':    {'input': 5.0,  'output': 25.0},
    'claude-opus-4-8':  {'input': 5.0,  'output': 25.0},
    'claude-sonnet-5':  {'input': 3.0,  'output': 15.0},
    'claude-haiku-4-5': {'input': 1.0,  'output': 5.0},
    'claude-fable-5':   {'input': 10.0, 'output': 50.0},
    # Gemini-Listenpreise (Google AI, Stand August 2026). gemini-2.5-flash wird laut
    # ai.google.dev/gemini-api/docs/deprecations am 16.10.2026 abgeschaltet
    # (Ersatz lt. Google: gemini-3.6-flash) — bis dahin funktioniert es noch,
    # danach aus _GEMINI_MODELS/config.yaml-Schema entfernen.
    'gemini-3.1-pro':   {'input': 2.0,  'output': 12.0},
    'gemini-3.6-flash': {'input': 1.5,  'output': 7.5},
    'gemini-3.5-flash': {'input': 1.5,  'output': 9.0},
    'gemini-2.5-flash': {'input': 0.3,  'output': 2.5},
    # Perplexity-Listenpreise (docs.perplexity.ai, Stand Juli 2026). Die
    # zusätzliche Request-Gebühr (siehe _AI_PERPLEXITY_REQUEST_FEE) ist HIER
    # bewusst nicht mit drin — sie wird separat pro Aufruf addiert, weil sie
    # nicht pro Token, sondern pauschal je Anfrage anfällt.
    'sonar':                {'input': 1.0, 'output': 1.0},
    'sonar-pro':             {'input': 3.0, 'output': 15.0},
    'sonar-reasoning-pro':   {'input': 2.0, 'output': 8.0},
    'sonar-deep-research':   {'input': 2.0, 'output': 8.0},
}

# USD pro 1000 Anfragen, gestaffelt nach `search_context_size` (siehe
# ai_client.py::_ai_request_perplexity) — wir fragen dort immer 'low' an (die
# günstigste Stufe), daher hier ebenfalls nur die 'low'-Preise. Sonar Deep
# Research hat keine Kontext-Stufen, sondern eine feste Gebühr je 1000
# Suchanfragen; wird hier gleich behandelt. In USD pro Aufruf (bereits /1000).
_AI_PERPLEXITY_REQUEST_FEE = {
    'sonar':                0.005,
    'sonar-pro':             0.006,
    'sonar-reasoning-pro':   0.006,
    'sonar-deep-research':   0.005,
}


def _ai_call_cost(model: str, usage: dict) -> float:
    """Geschätzte Kosten (USD) für genau diesen einen Aufruf."""
    price = _AI_PRICING.get(model, _AI_PRICING['claude-opus-5'])
    cost = usage.get('input_tokens', 0) / 1_000_000 * price['input']
    cost += usage.get('output_tokens', 0) / 1_000_000 * price['output']
    cost += usage.get('cache_read_input_tokens', 0) / 1_000_000 * price['input'] * 0.1
    cost += usage.get('cache_creation_input_tokens', 0) / 1_000_000 * price['input'] * 1.25
    cost += _AI_PERPLEXITY_REQUEST_FEE.get(model, 0.0)
    return round(cost, 4)


def _ai_usage_calc(models: dict) -> dict:
    """Verrechnet ein {model: counters}-Dict zu Aufrufen/Tokens/geschätzten
    Kosten (USD), je Modell mit eigenem Preis (siehe _AI_PRICING) plus — bei
    Perplexity — der pauschalen Request-Gebühr je Aufruf (siehe
    _AI_PERPLEXITY_REQUEST_FEE)."""
    cost = 0.0
    calls = input_tokens = output_tokens = 0
    for model, t in models.items():
        price = _AI_PRICING.get(model, _AI_PRICING['claude-opus-5'])
        n_calls = t.get('calls', 0)
        cost += t.get('input_tokens', 0) / 1_000_000 * price['input']
        cost += t.get('output_tokens', 0) / 1_000_000 * price['output']
        cost += t.get('cache_read_input_tokens', 0) / 1_000_000 * price['input'] * 0.1
        cost += t.get('cache_creation_input_tokens', 0) / 1_000_000 * price['input'] * 1.25
        cost += n_calls * _AI_PERPLEXITY_REQUEST_FEE.get(model, 0.0)
        calls += n_calls
        input_tokens += t.get('input_tokens', 0)
        output_tokens += t.get('output_tokens', 0)
    return {'calls': calls, 'input_tokens': input_tokens, 'output_tokens': output_tokens,
            'estimated_usd': round(cost, 4)}


def _ai_usage_period_calc(meta_key: str, id_field: str, current_id: str) -> dict:
    """Liest einen periodischen Zähler-Bucket (Tag/Monat) aus `meta` — bei
    abgelaufener Periode (anderes Datum/Monat als `current_id`) gilt er als leer,
    ohne die gespeicherten Daten selbst zu löschen (das passiert erst beim
    nächsten `_record_ai_usage`-Aufruf für die neue Periode)."""
    try:
        stored = json.loads(A._meta_get(meta_key) or '{}')
    except (TypeError, ValueError):
        stored = {}
    models = (stored.get('models') or {}) if stored.get(id_field) == current_id else {}
    return _ai_usage_calc(models)


def _ai_usage_totals() -> dict:
    """Aufsummierte Token-Nutzung + geschätzte Kosten (USD): gesamt (seit je),
    heute und diesen Monat — je Modell separat verrechnet."""
    try:
        totals = json.loads(A._meta_get('ai_usage_totals') or '{}')
    except (TypeError, ValueError):
        totals = {}
    result = _ai_usage_calc(totals)
    result['today'] = _ai_usage_period_calc('ai_usage_today', 'date', time.strftime('%Y-%m-%d'))
    result['month'] = _ai_usage_period_calc('ai_usage_month', 'month', time.strftime('%Y-%m'))
    return result


def _record_ai_usage_bucket(meta_key: str, id_field: str | None, current_id: str | None,
                            model: str, usage: dict) -> None:
    """Addiert einen KI-Aufruf zu einem Zähler-Bucket in `meta`. Für periodische
    Buckets (id_field gesetzt, z. B. 'date'/'month') wird bei Periodenwechsel auf
    0 zurückgesetzt statt unbegrenzt zu wachsen; für den Gesamt-Bucket (id_field
    None) bleibt das bisherige flache {model: counters}-Format erhalten."""
    try:
        stored = json.loads(A._meta_get(meta_key) or '{}')
    except (TypeError, ValueError):
        stored = {}
    if id_field:
        if stored.get(id_field) != current_id:
            stored = {id_field: current_id, 'models': {}}
        models = stored.setdefault('models', {})
    else:
        models = stored
    t = models.setdefault(model, {'input_tokens': 0, 'output_tokens': 0,
                                   'cache_creation_input_tokens': 0,
                                   'cache_read_input_tokens': 0, 'calls': 0})
    for key in ('input_tokens', 'output_tokens', 'cache_creation_input_tokens',
                'cache_read_input_tokens'):
        t[key] += usage.get(key, 0)
    t['calls'] += 1
    A._meta_set(meta_key, json.dumps(stored))


def _record_ai_usage(model: str, usage: dict) -> dict:
    """Nutzung eines frischen KI-Aufrufs zu Gesamt-, Tages- und Monats-Zählern
    addieren und die aktualisierten Gesamtwerte zurückgeben."""
    _record_ai_usage_bucket('ai_usage_totals', None, None, model, usage)
    _record_ai_usage_bucket('ai_usage_today', 'date', time.strftime('%Y-%m-%d'), model, usage)
    _record_ai_usage_bucket('ai_usage_month', 'month', time.strftime('%Y-%m'), model, usage)
    return _ai_usage_totals()


_AI_HISTORY_MAX = 300  # ältere Einträge werden beim Speichern verworfen


def _save_ai_analysis(kind: str, title: str, model: str, text: str, usage: dict,
                      prompt: str = '', offer_id: int | None = None) -> int:
    """Fertiges KI-Fazit/-Vergleich dauerhaft ablegen, damit es später über den
    KI-Verlauf wieder einsehbar (und per E-Mail versendbar) ist — unabhängig vom
    24h-Cache. `prompt` (optional) speichert den exakten Prompt-Text mit, damit der
    Eintrag später über /api/ai/history/<id>/repeat mit einer (ggf. anderen) KI
    wiederholt werden kann — leer bei Aufrufern, die (noch) keinen Prompt mitgeben.
    `offer_id` (optional) verknüpft den Eintrag mit einem Angebot — Basis für den
    Buchungsscore-Verlauf. Gibt die neue Zeilen-ID zurück."""
    if len(title) > 300:
        A.log.warning("KI-Verlauf-Titel gekürzt (%d → 300 Zeichen): %s…", len(title), title[:60])
    with A.db() as con:
        cur = con.execute('INSERT INTO ai_analyses (kind, title, model, summary, usage, ts, '
                          'prompt, offer_id) VALUES (?,?,?,?,?,?,?,?)',
                          (kind, title[:300], model, text, json.dumps(usage or {}), int(time.time()),
                           prompt, offer_id))
        aid = cur.lastrowid
        con.execute('DELETE FROM ai_analyses WHERE id NOT IN '
                    '(SELECT id FROM ai_analyses ORDER BY id DESC LIMIT ?)', (_AI_HISTORY_MAX,))
    return aid


def _booking_score_history(offer_id: int, limit: int = 20) -> list[dict]:
    """Score-Verlauf eines Angebots aus ai_analyses (kind=booking_score, per
    offer_id verknüpft — Einträge vor 0.49.0 haben keine Verknüpfung). Älteste
    zuerst, für Delta-Anzeige und Mini-Chart im Score-Modal."""
    with A.db() as con:
        rows = con.execute(
            'SELECT ts, summary FROM ai_analyses WHERE kind=? AND offer_id=? '
            # id als Tiebreaker: zwei Scores in derselben Sekunde blieben sonst
            # in instabiler Reihenfolge (ts ist nur sekundengenau)
            'ORDER BY ts DESC, id DESC LIMIT ?', ('booking_score', offer_id, limit)).fetchall()
    out = []
    for r in rows:
        res = A._json_loads_safe(r['summary'], {}) if r['summary'] else {}
        if isinstance(res, dict) and isinstance(res.get('score'), int):
            out.append({'ts': r['ts'], 'score': res['score'],
                        'empfehlung': res.get('empfehlung')})
    return list(reversed(out))


_AI_PROVIDERS = ('anthropic', 'gemini', 'perplexity')  # feste Reihenfolge — bestimmt
                                                        # u. a. den Fallback, wenn der
                                                        # gewählte Provider ungültig/
                                                        # nicht konfiguriert ist
_AI_PROVIDER_KEY_FIELDS = {'anthropic': 'anthropic_api_key', 'gemini': 'gemini_api_key',
                          'perplexity': 'perplexity_api_key'}


def _configured_ai_providers(cfg: dict) -> list[str]:
    """Provider mit hinterlegtem API-Key, in fester Anzeige-/Fallback-Reihenfolge."""
    return [p for p in _AI_PROVIDERS if (cfg.get(_AI_PROVIDER_KEY_FIELDS[p]) or '').strip()]


def _provider_for_model(model: str) -> str:
    """Umkehrung von `_ai_config_for`: welcher Provider bedient dieses Modell —
    für Folgefragen (`/api/ai/history/<id>/followup`), die mit demselben Modell
    weiterlaufen müssen, das die ursprüngliche Antwort gegeben hat (nicht
    zwangsläufig der gerade aktive Standard-Provider)."""
    if model in A._GEMINI_MODELS:
        return 'gemini'
    if model in A._PERPLEXITY_MODELS:
        return 'perplexity'
    return 'anthropic'


def _ai_active_provider(cfg: dict | None = None) -> str:
    """Welcher Provider ('anthropic'/'gemini'/'perplexity') gerade aktiv ist. Ist
    nur ein API-Key hinterlegt, gilt automatisch dieser (verhindert die Falle,
    dass z. B. `gemini_api_key` gesetzt, aber `ai_provider` noch auf 'anthropic'
    steht, und die KI-Features fälschlich inaktiv bleiben). Sind mehrere Keys
    gesetzt, entscheidet der zuletzt per Footer-Umschalter gewählte Provider
    (`meta` Key `ai_provider_active`), sonst der Add-on-Standard `ai_provider`
    — beide nur gültig, wenn sie auch tatsächlich konfiguriert sind, sonst
    Fallback auf den ersten konfigurierten Provider in `_AI_PROVIDERS`-Reihenfolge."""
    cfg = cfg or A.load_config()
    configured = _configured_ai_providers(cfg)
    if len(configured) > 1:
        active = A._meta_get('ai_provider_active')
        if active not in configured:
            active = cfg.get('ai_provider')
            if active not in configured:
                active = configured[0]
        return active
    if configured:
        return configured[0]
    return cfg.get('ai_provider') or 'anthropic'


def _ai_config_for(provider: str) -> tuple[str, str]:
    """(api_key, model) aus den Add-on-Optionen für einen bestimmten Provider —
    model fällt jeweils auf das Flaggschiff-Modell zurück, falls leer oder
    ungültig. `A._ai_request()` erkennt anhand des Modellnamens (siehe
    `A._AI_MODELS`/`A._GEMINI_MODELS`/`A._PERPLEXITY_MODELS`), welchen Provider
    es ansprechen muss. Auch für /api/ai/history/<id>/repeat nutzbar, wo der
    Nutzer die KI unabhängig vom gerade aktiven Provider wählt."""
    cfg = A.load_config()
    if provider == 'gemini':
        api_key = (cfg.get('gemini_api_key') or '').strip()
        model = cfg.get('gemini_model') or 'gemini-3.1-pro'
        if model not in A._GEMINI_MODELS:
            model = 'gemini-3.1-pro'
        return api_key, model
    if provider == 'perplexity':
        api_key = (cfg.get('perplexity_api_key') or '').strip()
        model = cfg.get('perplexity_model') or 'sonar-pro'
        if model not in A._PERPLEXITY_MODELS:
            model = 'sonar-pro'
        return api_key, model
    api_key = (cfg.get('anthropic_api_key') or '').strip()
    model = cfg.get('anthropic_model') or 'claude-opus-5'
    if model not in A._AI_MODELS:
        model = 'claude-opus-5'
    return api_key, model


def _ai_config():
    """(api_key, model) für den gerade aktiven Provider (siehe
    `_ai_active_provider`) — Kurzform von `_ai_config_for`."""
    return _ai_config_for(_ai_active_provider())


_AI_TAG_VOCAB = [
    "Familie", "Strand", "Party & Nachtleben", "Ruhe & Erholung", "Wellness & Spa",
    "Sport & Aktiv", "Luxus", "Budget", "Alleinreisende", "Kultur & Sightseeing",
    "Adults Only", "Golf",
]
_AI_TAG_SCHEMA = {
    "type": "object",
    "properties": {"tags": {"type": "array", "items": {"type": "string"}}},
    "required": ["tags"], "additionalProperties": False,
}


def _ai_auto_tags(h: dict, api_key: str, model: str) -> list | None:
    """2-4 passende Schlagworte aus einer festen Liste für ein Angebot vergeben
    (structured output, kein Websuche nötig). None bei jedem Fehler."""
    prompt = (
        "Vergib 2 bis 4 passende Schlagworte für folgendes Hotel/Reise-Angebot, "
        "ausschließlich aus dieser Liste (exakten Wortlaut übernehmen):\n"
        + ", ".join(_AI_TAG_VOCAB) + "\n\n"
        + "\n".join(_hotel_fact_lines(h)) + "\n\n"
        "Wähle nur Schlagworte, die durch die Fakten wirklich gestützt sind (z. B. "
        "'Familie' nur bei Hinweisen auf Kinderclub/Familienhotel, 'Party & "
        "Nachtleben' nur bei entsprechender Lage/Ausstattung). Lieber weniger, aber "
        "treffende Tags als geraten."
    )
    text, usage, code = A._ai_request(api_key, model, prompt, max_tokens=300,
                                    log_ctx="Auto-Tags", use_web_search=False,
                                    output_schema=_AI_TAG_SCHEMA)
    if code or not text:
        return None
    try:
        tags = [t for t in json.loads(text).get('tags', []) if t in _AI_TAG_VOCAB][:4]
    except (ValueError, AttributeError):
        return None
    usage['estimated_usd'] = _ai_call_cost(model, usage)
    _record_ai_usage(model, usage)
    return tags


@bp.route('/api/ai/auto-tags', methods=['POST'])
def api_ai_auto_tags():
    """Vergibt automatisch Tags für 1..N ausgewählte Angebote (Sammelaktion) —
    ergänzt bestehende Tags, überschreibt sie nicht."""
    if (err := A._require_api()):
        return err
    api_key, model = _ai_config()
    if not api_key:
        return jsonify({'error': 'no_api_key',
                        'note': 'Kein Anthropic API-Key in den Add-on-Einstellungen hinterlegt'}), 400
    data = request.get_json(silent=True) or {}
    ids = data.get('ids')
    if not isinstance(ids, list) or not ids:
        return jsonify({'error': 'invalid'}), 400
    want = {int(i) for i in ids if str(i).isdigit()}
    offers_by_id = {o['id']: o for o in A._collect_offers() if o['id'] in want}
    results = {}
    for oid, o in offers_by_id.items():
        h = {'name': o.get('label') or o.get('hotel'), 'location': o.get('location'),
             'country': o.get('country'), 'stars': o.get('stars'),
             'recommendation': o.get('recommendation'), 'reviews': o.get('rating_count'),
             'price': o.get('price'), 'details': o.get('details')}
        tags = _ai_auto_tags(h, api_key, model)
        if tags is None:
            continue
        merged = list(dict.fromkeys((o.get('tags') or []) + tags))
        with A.db() as con:
            con.execute('UPDATE offers SET tags=? WHERE id=?',
                        (json.dumps(merged, ensure_ascii=False), oid))
        results[oid] = merged
    return jsonify({'results': results})


_BOOKING_SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer"},
        "empfehlung": {"type": "string", "enum": ["jetzt_buchen", "beobachten", "warten"]},
        "vertrauen": {"type": "integer"},
        "erwartung_7_tage": {"type": "string", "enum": ["steigend", "fallend", "gleich"]},
        "erwartung_30_tage": {"type": "string", "enum": ["steigend", "fallend", "gleich"]},
        "begruendung": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "typ": {"type": "string", "enum": ["daten", "annahme"]},
                },
                "required": ["text", "typ"], "additionalProperties": False,
            },
        },
    },
    "required": ["score", "empfehlung", "vertrauen", "erwartung_7_tage",
                 "erwartung_30_tage", "begruendung"],
    "additionalProperties": False,
}

_BOOKING_SCORE_INSTRUCTIONS = (
    "Score 0-100: 0 = auf keinen Fall jetzt buchen, 100 = sehr guter Buchungszeitpunkt.\n"
    "Berücksichtige u. a. Preisentwicklung, Änderungsgeschwindigkeit, Abstand zu "
    "Tiefst-/Höchstpreis, Saison, Tage bis Abflug, Wochentag, deutsche Schulferien "
    "(grob, aus deinem Wissen), sowie ggf. per Websuche gefundene aktuelle Nachrichten "
    "oder besondere Ereignisse zum Reiseziel/Veranstalter.\n"
    "Wichtig zur Gewichtung: die Saisonalität aus dem Preiskalender (falls angegeben) "
    "zeigt nur, welcher Reisemonat für DIESES Hotel relativ zu anderen Monaten "
    "günstiger/teurer ist — das ist KEINE Vorhersage, wie sich der Preis für genau "
    "diesen Termin bis zum Abflug noch entwickelt, und rechtfertigt für sich allein "
    "kein 'jetzt buchen'. Je länger die Vorlaufzeit (Tage bis Abreise), desto weniger "
    "Gewicht sollte diese saisonale Einordnung bekommen und desto mehr zählen "
    "Preistrend/Markttrend als Signal für JETZT. Bei langer Vorlaufzeit gilt zusätzlich "
    "die allgemeine Erfahrung, dass Frühbucher bei Pauschalreisen meist im Vorteil sind "
    "(Preise tendieren dazu, näher am Abflug bei sinkender Verfügbarkeit zu steigen) — "
    "das spricht eher FÜR ein frühes Buchen, auch wenn der aktuelle Reisemonat laut "
    "Kalender nur durchschnittlich und nicht der günstigste ist. Nutze die volle "
    "Monatsliste (falls angegeben) für den direkten Vergleich zweier beliebiger "
    "Reisemonate — verlasse dich NICHT nur auf günstigsten/teuersten Monat, wenn der "
    "Zielmonat oder Vergleichsmonat keiner der beiden Extreme ist. Monate mit wenigen "
    "Terminen (z. B. nur 1-2, etwa bei wöchentlichem statt täglichem Flugrhythmus) "
    "sind ein schwächeres Signal als gut belegte Monate — werte sie trotzdem als "
    "typ='daten', aber vorsichtiger.\n"
    "Der Vorjahresvergleich (falls angegeben) ist ein stärkeres Signal als die reine "
    "Saisonalität: er zeigt echte Kalenderpreise für denselben Reisemonat ein Jahr "
    "früher, der bei langer Vorlaufzeit oft schon näher am eigenen Abflug liegt. Der "
    "Vergleich ist bewusst MONATSBEZOGEN (Ø-Preis über den ganzen Monat) — erwarte "
    "KEINE taggenaue Übereinstimmung mit dem exakten Reisedatum und bewerte das Fehlen "
    "einer taggenauen Entsprechung NICHT als fehlendes/unsicheres Signal oder Grund, "
    "'vertrauen' zu senken; die Monatsebene ist die vorgesehene und für sich genommen "
    "ausreichende Vergleichsbasis und zählt als typ='daten'. Interpretiere ihn aber "
    "vorsichtig, nicht als reines Nachfragesignal: Pauschalreisen "
    "werden ohnehin Jahr für Jahr etwas teurer (allgemeine Preissteigerung, grob "
    "einstelliger Prozentbereich p. a. aus deinem Wissen) — ziehe diesen Sockel gedanklich "
    "ab, bevor du den Rest als Nachfrage-/Knappheitssignal wertest. Zusätzlich liegt der "
    "Vorjahresmonat näher am Abflug als der Zielmonat, was laut obiger Frühbucher-Logik "
    "für sich allein schon einen Aufschlag erklären kann — die beiden Effekte lassen sich "
    "aus den Zahlen allein nicht sauber trennen, werte den Vergleich daher als groben "
    "Hinweis, nicht als exakten Prozentwert. Ist die Abweichung deutlich größer als plausible "
    "Inflation + Vorlaufzeit-Effekt erklären würden, prüfe per Websuche, ob politische, "
    "wirtschaftliche oder sonstige aktuelle Ereignisse (z. B. Währung, Treibstoffkosten, "
    "Sicherheitslage, Kapazitätsänderungen von Airline/Veranstalter) am Reiseziel eine "
    "Erklärung liefern, und nenne sie in der Begründung (typ='annahme', falls per Websuche "
    "gefunden). Nach dieser Einordnung: bleibt ein klarer Aufschlag, spricht das für frühes "
    "Buchen; liegt der Zielmonat auf/unter dem Vorjahreswert, eher für Beobachten/Warten. "
    "Gewichte das Gesamtsignal ähnlich stark wie den eigenen Preistrend.\n"
    "Die Preisbewegungen im Preiskalender (falls angegeben) sind echte beobachtete "
    "Änderungen je Abreisetag dieses Hotels/Zimmers: Steigen viele Termine auf breiter "
    "Front, ist Warten riskant (spricht für JETZT buchen); fallen viele, kann Warten "
    "sich lohnen. Gewichte dieses Signal ähnlich stark wie den eigenen Preistrend.\n"
    "Kennzeichne JEDEN Punkt in der Begründung mit typ='daten' (aus den oben gelieferten "
    "Zahlen ableitbar — dazu zählt auch die Saisonalität aus dem Preiskalender, falls "
    "angegeben: das sind echte abgefragte Preise, keine Schätzung) oder typ='annahme' "
    "(dein allgemeines Wissen, Saison-Erfahrung oder Websuche-Ergebnis, ohne harte "
    "Zahlen aus diesem Angebot). Senke 'vertrauen', wenn viele Punkte 'annahme' statt "
    "'daten' sind. Erfinde keine konkreten Preise oder Ereignisse, die du nicht "
    "wirklich gefunden hast."
)


def _calendar_seasonal_summary(cal: dict) -> dict | None:
    """Grobe Saisonalität aus einem bereits abgerufenen Preiskalender dieses Hotels/
    Zimmers (`calendar_cache`, siehe `A._run_calendar`) — echte Daten (tatsächlich
    abgefragte Preise je Abreisetag über ~18 Monate), keine Schätzung. None, wenn
    noch kein Kalender abgerufen wurde oder zu wenige Tage für eine Monatsaufteilung
    vorliegen. Löst selbst KEINEN neuen (teuren) Kalender-Abruf aus."""
    days = cal.get('days') or []
    if len(days) < 30:
        return None
    by_month: dict[str, list] = defaultdict(list)
    for d in days:
        by_month[d['date'][:7]].append(d['price'])
    # Für Angebote mit wöchentlichem statt täglichem Abflugrhythmus (z. B. nur
    # Sonntagsflüge) hat ein Monat oft nur 2-4 Termine insgesamt — die Schwelle
    # >= 3 gilt daher nur für Günstigster/Teuerster-Monat (Ausreißer-Schutz bei
    # der Extremwert-Auswahl), NICHT für die volle Monatsliste unten, sonst
    # fehlen ganze Monate (inkl. evtl. des Zielmonats) komplett aus dem Prompt.
    monthly = {m: round(sum(p) / len(p)) for m, p in by_month.items() if len(p) >= 3}
    if len(monthly) < 3:
        return None
    cheapest_month = min(monthly, key=monthly.get)
    priciest_month = max(monthly, key=monthly.get)
    result = {
        'cheapest_month': cheapest_month, 'cheapest_month_avg': monthly[cheapest_month],
        'priciest_month': priciest_month, 'priciest_month_avg': monthly[priciest_month],
        'tracked_price': cal.get('tracked_price'), 'tracked_date': cal.get('tracked_date'),
        'overall_cheapest_price': cal.get('cheapest_price'),
        'overall_cheapest_date': cal.get('cheapest_date'),
        # Volle Monatsliste (alle Monate mit mind. 1 Termin, nicht nur die zwei
        # Extreme) — sonst sieht die KI z. B. nicht, dass zwei mittlere Monate
        # 200 € auseinanderliegen, wenn keiner von beiden zufällig der
        # günstigste/teuerste im ganzen Kalender ist. Tage-Anzahl mitgeben,
        # damit die KI dünn belegte Monate (wenig Termine) vorsichtiger
        # gewichtet als gut belegte.
        'monthly': sorted((m, round(sum(p) / len(p)), len(p)) for m, p in by_month.items()),
    }
    # Vorjahresvergleich: der Kalender deckt heute bis weit über den Zieltermin hinaus
    # ab (siehe fetch_calendar) — bei >12 Monaten Vorlauf liegt der Zielmonat des
    # Vorjahres (z. B. Sept. 2026 für einen Zieltermin Sept. 2027) oft schon mit im
    # Fenster und ist DEUTLICH näher am eigenen Abflug als der Zieltermin selbst.
    # Das ist ein echtes Signal, wie sich diese Saison preislich entwickelt, statt nur
    # OB der Zielmonat an sich (über alle Jahre gemittelt) günstig/teuer ist.
    tracked_ym = (cal.get('tracked_date') or '')[:7]
    if tracked_ym and tracked_ym in monthly:
        result['target_month'] = tracked_ym
        result['target_month_avg'] = monthly[tracked_ym]
        try:
            prior_ym = f"{int(tracked_ym[:4]) - 1:04d}-{tracked_ym[5:7]}"
        except ValueError:
            prior_ym = None
        if prior_ym and prior_ym in monthly:
            result['prior_year_month'] = prior_ym
            result['prior_year_month_avg'] = monthly[prior_ym]
    return result


def _offer_booking_facts(con, offer_id: int) -> dict | None:
    """Fakten für den KI-Buchungsscore eines einzelnen Angebots: aktueller Preis,
    Preisspanne, eigener Trend (`A._trend_for`), Markttrend/-index seiner Destination
    (`A._market_trend`/`A._market_index`) sowie — falls bereits abgerufen — die
    Saisonalität aus dem gespeicherten Preiskalender dieses Hotels/Zimmers
    (`_calendar_seasonal_summary`). None, wenn das Angebot noch nie erfolgreich
    geprüft wurde (kein Preis vorhanden)."""
    o = con.execute('SELECT * FROM offers WHERE id=?', (offer_id,)).fetchone()
    if not o:
        return None
    last = con.execute(
        'SELECT * FROM price_history WHERE offer_id=? AND ok=1 AND price IS NOT NULL '
        'ORDER BY ts DESC LIMIT 1', (offer_id,)).fetchone()
    if not last:
        return None
    stats = con.execute(
        'SELECT MIN(price) mn, MAX(price) mx, COUNT(*) c FROM price_history '
        'WHERE offer_id=? AND ok=1 AND price IS NOT NULL', (offer_id,)).fetchone()
    region = o['region'] or ''
    seasonal = None
    cal_row = con.execute('SELECT data FROM calendar_cache WHERE offer_id=?', (offer_id,)).fetchone()
    if cal_row:
        try:
            seasonal = _calendar_seasonal_summary(json.loads(cal_row['data']))
        except (ValueError, TypeError):
            seasonal = None
    # Abreisedatum + Tage bis Abreise selbst berechnen (nicht der KI überlassen) —
    # live beobachtet: ohne explizites "heutiges Datum" im Prompt verschätzte sich
    # die KI bei der Vorlaufzeit um Jahre (hielt "2027" fälschlich für ~3 Jahre
    # entfernt statt gut 1 Jahr).
    nights = A.duration_from_url(o['url'])
    departure_date, departure_days = '', None
    if o['return_date']:
        try:
            ret = date.fromisoformat(o['return_date'][:10])
            dep = ret - timedelta(days=nights) if nights else ret
            departure_date = dep.isoformat()
            departure_days = (dep - date.today()).days
        except ValueError:
            pass
    return {
        'hotel': o['label'] or o['hotel'] or f"Angebot #{offer_id}",
        'details': o['details'] or '', 'region': region, 'country': o['country'] or '',
        'stars': o['stars'], 'rating': o['rating'], 'rating_count': o['rating_count'],
        'recommendation': o['recommendation'], 'return_date': o['return_date'] or '',
        'departure_date': departure_date, 'departure_days': departure_days,
        'target_price': o['target_price'], 'booked_price': o['booked_price'],
        'price': last['price'], 'min_price': stats['mn'], 'max_price': stats['mx'],
        'samples': stats['c'],
        'own_trend': A._trend_for(con, offer_id),
        'region_trend': A._market_trend(con, region=region) if region else None,
        'region_index': A._market_index(con, region=region) if region else None,
        'seasonal': seasonal,
        # Größte Kalender-Bewegungen (calendar_history) wie bei der KI-Kalenderanalyse:
        # breite Anstiege über viele Reisetermine = Warten riskant, breite Rückgänge =
        # Warten kann sich lohnen — direktes Signal für "jetzt buchen oder warten?".
        'calendar_moves': A._calendar_top_moves(A._calendar_moves(con, offer_id), limit=8),
    }


def _calendar_outlook_facts(con, offer_id: int) -> dict | None:
    """Fakten für die KI-Kalenderanalyse: Monatsdurchschnitte (schwellenfrei, auch bei
    wenig Daten — anders als `_calendar_seasonal_summary`, das für den Buchungsscore
    harte Mindestschwellen braucht) + größte Bewegungen aus calendar_history. None
    ohne abgerufenen Kalender."""
    o = con.execute('SELECT label, hotel FROM offers WHERE id=?', (offer_id,)).fetchone()
    if not o:
        return None
    cal_row = con.execute('SELECT data FROM calendar_cache WHERE offer_id=?', (offer_id,)).fetchone()
    if not cal_row:
        return None
    try:
        cal = json.loads(cal_row['data'])
    except (ValueError, TypeError):
        return None
    days = cal.get('days') or []
    if not days:
        return None
    by_month: dict[str, list] = defaultdict(list)
    for d in days:
        by_month[d['date'][:7]].append(d['price'])
    monthly = sorted((m, round(sum(p) / len(p)), len(p)) for m, p in by_month.items())
    moves = A._calendar_top_moves(A._calendar_moves(con, offer_id), limit=8)
    return {
        'hotel': o['label'] or o['hotel'] or f"Angebot #{offer_id}",
        'duration': cal.get('duration'),
        'tracked_date': cal.get('tracked_date'), 'tracked_price': cal.get('tracked_price'),
        'cheapest_date': cal.get('cheapest_date'), 'cheapest_price': cal.get('cheapest_price'),
        'monthly': monthly, 'moves': moves,
    }


_CALENDAR_OUTLOOK_INSTRUCTIONS = (
    "Fasse die Preisentwicklung im Kalender kurz zusammen und gib eine Empfehlung, "
    "wann eine Buchung günstig bzw. teuer ist. Gliedere die Antwort so:\n"
    "- Kurzer Absatz (2-3 Sätze) zum allgemeinen Preisniveau, und falls Daten vorhanden "
    "zu auffälligen Preisänderungen.\n"
    "- Abschnitt \"Günstige Monate\" als Liste (Monat + ca. Preis).\n"
    "- Abschnitt \"Teure Monate\" als Liste (Monat + ca. Preis).\n"
    "- Abschnitt \"Empfehlung\": 1-2 Sätze konkrete Handlungsempfehlung.\n\n"
    "Nutze ausschließlich die unten gelieferten Daten — keine Websuche, keine erfundenen "
    "Zahlen. Schreibe auf Deutsch, sprich den Nutzer mit „Du“ an, fasse dich kurz "
    "(insgesamt max. ~180 Wörter). Gib direkt die fertige Antwort aus, kein Vorspann."
)


def _calendar_outlook_prompt(facts: dict) -> str:
    lines = [f"Heutiges Datum: {date.today().isoformat()}", f"Hotel: {facts['hotel']}"]
    if facts.get('duration'):
        lines.append(f"Reisedauer: {facts['duration']} Nächte")
    if facts.get('tracked_date'):
        lines.append(f"Preis im aktuell gewählten Reisezeitraum: {facts['tracked_price']} € "
                      f"(am {facts['tracked_date']})")
    if facts.get('cheapest_date'):
        lines.append(f"Günstigster Einzeltermin im gesamten Kalender: "
                      f"{facts['cheapest_price']} € (am {facts['cheapest_date']})")
    lines.append("Monatsdurchschnittspreise im Kalender (Ø-Preis, Anzahl Tage mit Daten):")
    for m, avg, n in facts['monthly']:
        lines.append(f"- {A._month_name_de(m)}: Ø {avg} € ({n} Tage)")
    if facts['moves']:
        lines.append("Größte Preisänderungen seit dem jeweils letzten bekannten Wert "
                      "für dieses Reisedatum:")
        for mv in facts['moves']:
            arrow = "gestiegen" if mv['delta'] > 0 else "gefallen"
            lines.append(f"- {mv['date']}: {mv['prev_price']} € -> {mv['price']} € "
                         f"({arrow} um {abs(mv['delta'])} €)")
    else:
        lines.append("Bisher wurden noch keine Preisänderungen im Kalender aufgezeichnet.")
    return ("Du bist ein Reisepreis-Analyst. Analysiere den Preiskalender dieser "
            "Pauschalreise.\n\n" + "\n".join(lines) + "\n\n" + _CALENDAR_OUTLOOK_INSTRUCTIONS)


def _booking_score_prompt(facts: dict) -> str:
    """Baut den Buchungsscore-Prompt für ein einzelnes Angebot aus dessen eigenen
    (bereits vorgerechneten) Fakten — keine rohen Preislisten, damit die KI nicht
    selbst (fehleranfällig) einen Trend aus Rohdaten ableiten muss."""
    lines = [f"Heutiges Datum: {date.today().isoformat()}", f"Hotel: {facts['hotel']}"]
    if facts['details']:
        lines.append(f"Details: {facts['details']}")
    if facts['region'] or facts['country']:
        lines.append(f"Reiseziel: {facts['region']}"
                      + (f", {facts['country']}" if facts['country'] else ''))
    if facts['stars']:
        lines.append(f"Sterne: {facts['stars']}")
    if facts['rating'] is not None:
        lines.append(f"Bewertung: {facts['rating']}"
                      + (f" ({facts['rating_count']} Bewertungen)" if facts['rating_count'] else ''))
    if facts['recommendation'] is not None:
        lines.append(f"Weiterempfehlung: {facts['recommendation']}%")
    lines.append(f"Aktueller Preis: {facts['price']:.0f} €")
    if facts['min_price'] is not None and facts['max_price'] is not None:
        lines.append(f"Bisher beobachteter Preisbereich: {facts['min_price']:.0f} – "
                      f"{facts['max_price']:.0f} € ({facts['samples']} Messpunkte)")
    if facts['return_date']:
        lines.append(f"Rückreisedatum: {facts['return_date']}")
    if facts.get('departure_date'):
        dd = facts.get('departure_days')
        extra = (f" — das sind {dd} Tage bzw. rund {dd / 30.44:.1f} Monate bis Abreise, "
                 f"ausgehend vom heutigen Datum oben" if dd is not None else '')
        lines.append(f"Geschätztes Abreisedatum: {facts['departure_date']}{extra}")
    if facts['target_price']:
        lines.append(f"Wunschpreis des Nutzers: {facts['target_price']:.0f} €")
    if facts['booked_price']:
        lines.append(f"Bereits gebuchter Vergleichspreis: {facts['booked_price']:.0f} €")
    t = facts['own_trend']
    if t:
        lines.append(f"Eigener Preistrend (letzte Messpunkte dieses Angebots): "
                      f"{t['dir']} ({t['pct']:+.1f} %)")
    rt = facts['region_trend']
    if rt:
        lines.append(f"Markttrend der Destination (14 Tage, alle getrackten Angebote): "
                      f"{rt['dir']} ({rt['pct']:+.1f} %, {rt['n']} Datenpunkte)")
    ri = facts['region_index']
    if ri:
        lines.append(f"Markt-Index der Destination seit Aufzeichnungsbeginn: "
                      f"{ri['index']} ({ri['pct']:+.1f} %, {ri['n']} Datenpunkte)")
    s = facts['seasonal']
    if s:
        lines.append(
            f"Saisonalität aus dem gespeicherten Preiskalender dieses Hotels/Zimmers "
            f"(echte abgefragte Preise je Abreisetag, ~18 Monate): günstigster Monat "
            f"{s['cheapest_month']} (Ø {s['cheapest_month_avg']} €), teuerster Monat "
            f"{s['priciest_month']} (Ø {s['priciest_month_avg']} €)"
            + (f"; günstigster Einzeltermin im Kalender {s['overall_cheapest_date']} "
               f"({s['overall_cheapest_price']} €)" if s.get('overall_cheapest_date') else '')
            + (f"; Preis im aktuell gewählten Reisezeitraum laut Kalender "
               f"{s['tracked_price']} € (am {s['tracked_date']})" if s.get('tracked_price') else ''))
        if s.get('monthly'):
            lines.append("Monatsdurchschnittspreise im Kalender (Ø-Preis, Anzahl Termine — "
                          "alle Monate, für direkten Vergleich beliebiger Reisemonate "
                          "untereinander, nicht nur der beiden Extreme oben):")
            for m, avg, n in s['monthly']:
                lines.append(f"- {A._month_name_de(m)}: Ø {avg} € ({n} Termine)")
        if s.get('prior_year_month_avg'):
            yoy_pct = ((s['target_month_avg'] - s['prior_year_month_avg'])
                       / s['prior_year_month_avg'] * 100)
            lines.append(
                f"Vorjahresvergleich (echte Kalenderdaten, gleicher Reisemonat ein Jahr "
                f"früher — der liegt bei so langer Vorlaufzeit oft schon näher am eigenen "
                f"Abflug und zeigt, wie sich diese Saison preislich entwickelt): "
                f"{A._month_name_de(s['prior_year_month'])} lag im Schnitt bei "
                f"{s['prior_year_month_avg']} €, {A._month_name_de(s['target_month'])} "
                f"(Zielmonat) aktuell im Schnitt bei {s['target_month_avg']} € "
                f"({yoy_pct:+.1f} %).")
    mv = facts.get('calendar_moves') or []
    if mv:
        ups = sum(1 for m in mv if m['delta'] > 0)
        lines.append(f"Größte Preisbewegungen im Preiskalender dieses Hotels/Zimmers "
                      f"(je Abreisetag, seit dem jeweils letzten bekannten Wert; "
                      f"{ups} von {len(mv)} gestiegen):")
        for m in mv:
            arrow = "gestiegen" if m['delta'] > 0 else "gefallen"
            lines.append(f"- Abreise {m['date']}: {m['prev_price']} € -> {m['price']} € "
                         f"({arrow} um {abs(m['delta'])} €)")
    return ("Du bist ein Reisepreis-Analyst. Bewerte den aktuellen Preis dieser "
            "Pauschalreise und berechne einen Buchungsscore.\n\n" + "\n".join(lines)
            + "\n\n" + _BOOKING_SCORE_INSTRUCTIONS)


def _region_outlook_prompt(region: str, trend: dict | None, index: dict | None) -> str:
    """Buchungsscore-Prompt für eine ganze Destination (kein bestimmtes Hotel) — nur
    aus dem regionalen Markttrend/-index, ohne Angebots-Details."""
    lines = [f"Heutiges Datum: {date.today().isoformat()}", f"Reiseziel: {region}"]
    if trend:
        lines.append(f"Markttrend (14 Tage, alle aktuell getrackten Angebote dieser "
                      f"Destination): {trend['dir']} ({trend['pct']:+.1f} %, "
                      f"{trend['n']} Datenpunkte)")
    if index:
        lines.append(f"Markt-Index seit Aufzeichnungsbeginn: {index['index']} "
                      f"({index['pct']:+.1f} %, {index['n']} Datenpunkte)")
    return ("Du bist ein Reisepreis-Analyst. Schätze allgemein ein, ob jetzt ein guter "
            "Zeitpunkt ist, eine Pauschalreise in dieses Reiseziel zu buchen — "
            "unabhängig von einem bestimmten Hotel.\n\n" + "\n".join(lines)
            + "\n\n" + _BOOKING_SCORE_INSTRUCTIONS)


def _hotel_summary_prompt(hotel: dict, instructions: str) -> str:
    """Baut den KI-Fazit-Prompt: feste Hotel-Fakten + (ggf. vom Nutzer angepasste)
    Instruktionen."""
    facts = ("Erstelle eine ausführliche, ehrliche Einschätzung zu folgendem Hotel:\n\n"
             + "\n".join(_hotel_fact_lines(hotel)))
    return facts + "\n\n" + instructions


@bp.route('/api/ai/hotel-summary', methods=['POST'])
def api_ai_hotel_summary():
    """Ausführliche KI-Einschätzung zu einem Hotel aus den Suchergebnissen (Lage,
    Zimmer, Gastronomie, Pool, Ausstattung, Fazit) — Claude durchsucht dafür live
    das Web nach Bewertungen. Gecacht je Hotel (giataId), um wiederholte teure
    Abrufe beim erneuten Öffnen zu vermeiden."""
    if (err := A._require_api()):
        return err
    api_key, model = _ai_config()
    if not api_key:
        return jsonify({'error': 'no_api_key',
                        'note': 'Kein Anthropic API-Key in den Add-on-Einstellungen hinterlegt'}), 400
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'invalid'}), 400
    instructions = A._prompt_instructions('summary', _DEFAULT_SUMMARY_INSTRUCTIONS)
    instr_hash = hashlib.sha1(instructions.encode('utf-8')).hexdigest()[:10]
    giata = data.get('giata')
    cache_key = f'{instr_hash}:' + (str(giata) if giata else name.lower())
    with A._ai_cache_lock:
        cached = A._ai_summary_cache.get(cache_key)
    if cached and time.time() - cached['ts'] < A._AI_SUMMARY_TTL:
        return jsonify({'summary': cached['summary'], 'usage': cached.get('usage'),
                        'totals': _ai_usage_totals(), 'id': cached.get('id'), 'cached': True})

    prompt = _hotel_summary_prompt(data, instructions)
    if (preview := _prompt_preview_response(data, prompt)):
        return preview
    prompt = _resolve_prompt(data, prompt)
    text, usage, err = A._ai_call(api_key, model, prompt, max_tokens=4096, log_ctx=name)
    if err:
        return err
    usage['estimated_usd'] = _ai_call_cost(model, usage)
    totals = _record_ai_usage(model, usage)
    aid = _save_ai_analysis('single', name, model, text, usage, prompt)
    with A._ai_cache_lock:
        A._ai_summary_cache[cache_key] = {'summary': text, 'usage': usage, 'id': aid, 'ts': time.time()}
    return jsonify({'summary': text, 'usage': usage, 'totals': totals, 'id': aid, 'cached': False})


def _ai_score_request(prompt: str, model: str, api_key: str, log_ctx: str):
    """Ruft die KI mit dem Buchungsscore-Schema + Websuche auf und parst das Ergebnis.
    Rückgabe: (result_dict, usage, None) oder (None, None, (jsonify(...), status))."""
    # 2048 statt 1024: mit Websuche zählt auch der Zwischentext des Modells (zwischen
    # den Suchaufrufen) zum Output-Budget — bei 1024 wurde das Structured-Output-JSON
    # live abgeschnitten (stop_reason=max_tokens, beide Provider 200 OK, UI nur
    # "fehlgeschlagen"). Gemini bekommt zusätzlich die Thinking-Reserve obendrauf.
    text, usage, code = A._ai_request(api_key, model, prompt, max_tokens=2048,
                                    log_ctx=log_ctx, use_web_search=True,
                                    output_schema=_BOOKING_SCORE_SCHEMA)
    if code == 'failed':
        return None, None, (jsonify({'error': 'ai_failed'}), 502)
    if code == 'refused':
        return None, None, (jsonify({'error': 'ai_refused'}), 502)
    if code == 'empty' or not text:
        return None, None, (jsonify({'error': 'ai_empty'}), 502)
    try:
        result = json.loads(text)
    except ValueError:
        A.log.warning("Buchungsscore (%s): KI-Antwort kein gültiges JSON "
                    "(%d Zeichen): %.200s", log_ctx, len(text), text)
        return None, None, (jsonify({'error': 'ai_empty'}), 502)
    return result, usage, None


@bp.route('/api/ai/calendar-outlook/<int:offer_id>', methods=['POST'])
def api_ai_calendar_outlook(offer_id: int):
    """KI-Zusammenfassung des Preiskalenders eines Angebots (günstige/teure Monate,
    Preisänderungen) — reiner Markdown-Fließtext, keine Websuche (nur lokale
    Kalenderdaten), daher ohne Sonderfall für Claude/Gemini nutzbar. 6h gecacht."""
    if (err := A._require_api()):
        return err
    api_key, model = _ai_config()
    if not api_key:
        return jsonify({'error': 'no_api_key',
                        'note': 'Kein Anthropic API-Key in den Add-on-Einstellungen hinterlegt'}), 400
    data = request.get_json(silent=True) or {}
    cached = A._calendar_outlook_cache.get(offer_id)
    if cached and time.time() - cached['ts'] < A._BOOKING_SCORE_TTL:
        return jsonify({'summary': cached['summary'], 'usage': cached.get('usage'),
                        'totals': _ai_usage_totals(), 'id': cached.get('id'), 'cached': True})
    with A.db() as con:
        if not con.execute('SELECT 1 FROM offers WHERE id=?', (offer_id,)).fetchone():
            return jsonify({'error': 'not_found'}), 404
        cal_row = con.execute('SELECT ts FROM calendar_cache WHERE offer_id=?', (offer_id,)).fetchone()
    if not cal_row or time.time() - cal_row['ts'] >= A._CALENDAR_FRESH_SECONDS:
        A._run_calendar(offer_id)   # wie im Buchungsscore: fehlenden/alten Kalender einmalig auffrischen
    with A.db() as con:
        facts = _calendar_outlook_facts(con, offer_id)
    if facts is None:
        return jsonify({'error': 'no_data'}), 400
    prompt = _calendar_outlook_prompt(facts)
    if (preview := _prompt_preview_response(data, prompt)):
        return preview
    prompt = _resolve_prompt(data, prompt)
    text, usage, err = A._ai_call(api_key, model, prompt, max_tokens=700,
                                log_ctx=facts['hotel'], use_web_search=False)
    if err:
        return err
    usage['estimated_usd'] = _ai_call_cost(model, usage)
    totals = _record_ai_usage(model, usage)
    aid = _save_ai_analysis('calendar_outlook', facts['hotel'], model, text, usage, prompt)
    A._calendar_outlook_cache[offer_id] = {'summary': text, 'usage': usage, 'id': aid, 'ts': time.time()}
    return jsonify({'summary': text, 'usage': usage, 'totals': totals, 'id': aid, 'cached': False})


@bp.route('/api/ai/booking-score/<int:offer_id>', methods=['POST'])
def api_ai_booking_score(offer_id: int):
    """KI-Buchungsscore für ein einzelnes getracktes Angebot — auf Anfrage (kostet
    Websuche-Aufrufe), 6h je Angebot gecacht."""
    if (err := A._require_api()):
        return err
    api_key, model = _ai_config()
    if not api_key:
        return jsonify({'error': 'no_api_key',
                        'note': 'Kein Anthropic API-Key in den Add-on-Einstellungen hinterlegt'}), 400
    data = request.get_json(silent=True) or {}
    with A._ai_cache_lock:
        cached = A._booking_score_cache.get(offer_id)
    if cached and time.time() - cached['ts'] < A._BOOKING_SCORE_TTL:
        return jsonify({'result': cached['result'], 'usage': cached['usage'],
                        'totals': _ai_usage_totals(), 'id': cached.get('id'), 'cached': True,
                        'history': _booking_score_history(offer_id)})
    with A.db() as con:
        facts = _offer_booking_facts(con, offer_id)
    if facts is None:
        return jsonify({'error': 'no_price'}), 400
    with A.db() as con:
        cal_row = con.execute('SELECT ts FROM calendar_cache WHERE offer_id=?', (offer_id,)).fetchone()
    if not cal_row or time.time() - cal_row['ts'] >= A._CALENDAR_FRESH_SECONDS:
        # Fehlender/veralteter Preiskalender wird für den Buchungsscore vorher
        # aufgefrischt (synchron, nur für Angebote mit Preis — sonst lohnt sich der
        # Abruf nicht) — nicht bei jedem Aufruf, nur wenn er fehlt oder älter als
        # A._CALENDAR_FRESH_SECONDS ist. Facts danach neu laden, damit die frische
        # Saisonalität im Prompt landet.
        A._run_calendar(offer_id)
        with A.db() as con:
            facts = _offer_booking_facts(con, offer_id)
    prompt = _booking_score_prompt(facts)
    if (preview := _prompt_preview_response(data, prompt)):
        return preview
    prompt = _resolve_prompt(data, prompt)
    result, usage, err = _ai_score_request(prompt, model, api_key, facts['hotel'])
    if err:
        return err
    usage['estimated_usd'] = _ai_call_cost(model, usage)
    totals = _record_ai_usage(model, usage)
    aid = _save_ai_analysis('booking_score', facts['hotel'], model,
                            json.dumps(result, ensure_ascii=False), usage, prompt,
                            offer_id=offer_id)
    with A._ai_cache_lock:
        A._booking_score_cache[offer_id] = {'result': result, 'usage': usage, 'id': aid, 'ts': time.time()}
    return jsonify({'result': result, 'usage': usage, 'totals': totals, 'id': aid, 'cached': False,
                    'history': _booking_score_history(offer_id)})


@bp.route('/api/ai/region-outlook', methods=['POST'])
def api_ai_region_outlook():
    """KI-Einschätzung für eine ganze Destination (kein bestimmtes Hotel) aus deren
    Markttrend/-index — auf Anfrage, 6h je Region gecacht."""
    if (err := A._require_api()):
        return err
    api_key, model = _ai_config()
    if not api_key:
        return jsonify({'error': 'no_api_key',
                        'note': 'Kein Anthropic API-Key in den Add-on-Einstellungen hinterlegt'}), 400
    data = request.get_json(silent=True) or {}
    region = (data.get('region') or '').strip()
    if not region:
        return jsonify({'error': 'invalid'}), 400
    cached = A._region_outlook_cache.get(region)
    if cached and time.time() - cached['ts'] < A._BOOKING_SCORE_TTL:
        return jsonify({'result': cached['result'], 'usage': cached['usage'],
                        'totals': _ai_usage_totals(), 'id': cached.get('id'), 'cached': True})
    with A.db() as con:
        trend = A._market_trend(con, region=region)
        index = A._market_index(con, region=region)
    if trend is None and index is None:
        return jsonify({'error': 'no_data'}), 400
    prompt = _region_outlook_prompt(region, trend, index)
    if (preview := _prompt_preview_response(data, prompt)):
        return preview
    prompt = _resolve_prompt(data, prompt)
    result, usage, err = _ai_score_request(prompt, model, api_key, region)
    if err:
        return err
    usage['estimated_usd'] = _ai_call_cost(model, usage)
    totals = _record_ai_usage(model, usage)
    aid = _save_ai_analysis('region_outlook', region, model,
                            json.dumps(result, ensure_ascii=False), usage, prompt)
    A._region_outlook_cache[region] = {'result': result, 'usage': usage, 'id': aid, 'ts': time.time()}
    return jsonify({'result': result, 'usage': usage, 'totals': totals, 'id': aid, 'cached': False})


_BOARD_LABELS = {'AI': 'All Inclusive', 'VP': 'Vollpension', 'HP': 'Halbpension',
                 'BB': 'Frühstück', 'OV': 'ohne Verpflegung'}

# ── Klimatabelle je Reiseziel ─────────────────────────────────────────────────
# Strukturiert statt Fließtext: als JSON lässt sich die Tabelle sortiert rendern,
# der Reisemonat hervorheben und später weiterverwenden (z. B. im Reisezeit-Check).
# Ein Markdown-Block wäre nur einmal lesbar und nicht auswertbar.
_CLIMATE_SCHEMA = {
    "type": "object",
    "properties": {
        "months": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "monat": {"type": "integer"},
                    "temp_tag": {"type": "number"},
                    "temp_nacht": {"type": "number"},
                    "wasser": {"type": "number"},
                    "sonnenstunden": {"type": "number"},
                    "regentage": {"type": "integer"},
                    "hinweis": {"type": "string"},
                },
                "required": ["monat", "temp_tag", "temp_nacht", "wasser",
                             "sonnenstunden", "regentage", "hinweis"],
                "additionalProperties": False,
            },
        },
        "beste_monate": {"type": "array", "items": {"type": "integer"}},
        "zusammenfassung": {"type": "string"},
    },
    "required": ["months", "beste_monate", "zusammenfassung"],
    "additionalProperties": False,
}


def _climate_prompt(label: str) -> str:
    return (
        f"Stelle mir das Klima für {label} als Jahresübersicht zusammen — für alle "
        "zwölf Monate, Januar (1) bis Dezember (12), jeder Monat genau einmal.\n\n"
        "Je Monat: durchschnittliche Tageshöchsttemperatur und Nachttemperatur in °C, "
        "durchschnittliche Wassertemperatur in °C, Sonnenstunden pro Tag, Regentage "
        "im Monat. Dazu ein kurzer Hinweis (höchstens acht Wörter) für Besonderes wie "
        "Regenzeit, Hurrikansaison, Passatwind, Hitze oder Hochsaison — sonst leer "
        "lassen.\n\n"
        "Nenne außerdem die aus Wetter-Sicht besten Reisemonate und eine "
        "Zusammenfassung in zwei bis drei Sätzen (Klimatyp, Regenzeit, "
        "Badesaison).\n\n"
        "Nutze langjährige Klima-Normalwerte (Klimamittel), keine Vorhersage für ein "
        "einzelnes Jahr. Suche die Werte im Web und stütze dich auf gängige "
        "Klimatabellen. Wo für das Ziel keine Wassertemperatur sinnvoll ist "
        "(Binnenland), trage 0 ein und schreibe es in den Hinweis."
    )


def _linkify_citations_in_place(result: dict, urls: list | None) -> None:
    """Perplexity setzt Quellen-Marker wie „[7][11]" auch in die Textfelder einer
    strukturierten Antwort. Dort können sie beim Abruf nicht verlinkt werden (das
    würde den JSON-String zerstören), also passiert es hier nach dem Parsen — sonst
    bliebe im Klima-Fenster toter Text stehen. Bei den anderen Anbietern ist `urls`
    leer und die Funktion tut nichts."""
    if not urls:
        return
    from ai_client import _perplexity_linkify_citations
    data = {'citations': urls}
    if isinstance(result.get('zusammenfassung'), str):
        result['zusammenfassung'] = _perplexity_linkify_citations(
            result['zusammenfassung'], data)
    for m in (result.get('months') or []):
        if isinstance(m, dict) and isinstance(m.get('hinweis'), str):
            m['hinweis'] = _perplexity_linkify_citations(m['hinweis'], data)


def _climate_load(giata: int):
    with A.db() as con:
        row = con.execute('SELECT label, ts, model, data FROM climate WHERE giata=?',
                          (giata,)).fetchone()
    if not row:
        return None
    try:
        data = json.loads(row['data'])
    except ValueError:
        return None
    return {'giata': giata, 'label': row['label'], 'ts': row['ts'],
            'model': row['model'], 'data': data}


@bp.route('/api/climate', methods=['GET'])
def api_climate_list():
    """Alle gespeicherten Klimatabellen (ohne die Monatsdaten) — für den Zugriff von
    der Hauptseite aus, wo kein Reiseziel aus der Suchmaske vorliegt."""
    if (err := A._require_api()):
        return err
    with A.db() as con:
        rows = con.execute('SELECT giata, label, ts FROM climate '
                           'ORDER BY label COLLATE NOCASE').fetchall()
    return jsonify({'items': [dict(r) for r in rows]})


@bp.route('/api/climate/<int:giata>', methods=['GET'])
def api_climate_get(giata: int):
    """Gespeicherte Klimatabelle eines Reiseziels — **ohne** KI-Aufruf. Die Suchmaske
    fragt hier bei jedem Suchlauf an; das muss kostenlos sein. Fehlt die Tabelle,
    kommt `{'found': False}` und der Client entscheidet, ob er sie erzeugen lässt."""
    if (err := A._require_api()):
        return err
    got = _climate_load(giata)
    if not got:
        return jsonify({'found': False, 'giata': giata})
    return jsonify(dict(got, found=True))


@bp.route('/api/ai/climate', methods=['POST'])
def api_ai_climate():
    """Klimatabelle für ein Reiseziel per KI erzeugen und dauerhaft speichern.

    Liegt sie schon vor, wird sie unverändert zurückgegeben — Klima-Normalwerte
    ändern sich nicht, ein erneuter Aufruf wäre reine Geldverbrennung. `refresh: true`
    erzwingt eine Neuberechnung (Knopf im Klima-Fenster)."""
    if (err := A._require_api()):
        return err
    data = request.get_json(silent=True) or {}
    try:
        giata = int(data.get('giata'))
    except (TypeError, ValueError):
        return jsonify({'error': 'no_dest'}), 400
    label = (data.get('label') or '').strip()
    if not data.get('refresh'):
        if (got := _climate_load(giata)):
            return jsonify(dict(got, found=True, cached=True))
    if not label:
        return jsonify({'error': 'no_dest'}), 400
    api_key, model = _ai_config()
    if not api_key:
        return jsonify({'error': 'no_api_key',
                        'note': 'Kein Anthropic API-Key in den Add-on-Einstellungen hinterlegt'}), 400
    prompt = _climate_prompt(label)
    if (preview := _prompt_preview_response(data, prompt)):
        return preview
    prompt = _resolve_prompt(data, prompt)
    text, usage, code = A._ai_request(api_key, model, prompt, max_tokens=3000,
                                      log_ctx=f"Klimatabelle {label}",
                                      use_web_search=True, output_schema=_CLIMATE_SCHEMA)
    if code == 'failed':
        return jsonify({'error': 'ai_failed'}), 502
    if code == 'refused':
        return jsonify({'error': 'ai_refused'}), 502
    if code == 'empty' or not text:
        return jsonify({'error': 'ai_empty'}), 502
    try:
        result = json.loads(text)
    except ValueError:
        A.log.warning("Klimatabelle %s: KI-Antwort kein gültiges JSON (%d Zeichen): %.200s",
                      label, len(text), text)
        return jsonify({'error': 'ai_empty'}), 502
    months = [m for m in (result.get('months') or []) if isinstance(m, dict)]
    if len(months) < 12:
        A.log.warning("Klimatabelle %s: nur %d Monate geliefert", label, len(months))
        return jsonify({'error': 'ai_empty'}), 502
    _linkify_citations_in_place(result, (usage or {}).pop('citation_urls', None))
    usage['estimated_usd'] = _ai_call_cost(model, usage)
    totals = _record_ai_usage(model, usage)
    ts = int(time.time())
    with A.db() as con:
        con.execute('INSERT OR REPLACE INTO climate (giata, label, ts, model, data) '
                    'VALUES (?,?,?,?,?)',
                    (giata, label, ts, model, json.dumps(result, ensure_ascii=False)))
    A.log.info("Klimatabelle für %s (%s) gespeichert", label, giata)
    return jsonify({'found': True, 'cached': False, 'giata': giata, 'label': label,
                    'ts': ts, 'model': model, 'data': result,
                    'usage': usage, 'totals': totals})


@bp.route('/api/climate/<int:giata>/email', methods=['POST'])
def api_climate_email(giata: int):
    """Gespeicherte Klimatabelle per E-Mail verschicken. Kein KI-Aufruf — verschickt
    wird ausschließlich, was schon in der Datenbank liegt."""
    if (err := A._require_api()):
        return err
    if not A.smtp_configured():
        return jsonify({'error': 'smtp_not_configured'}), 400
    data = request.get_json(silent=True) or {}
    to = (data.get('to') or A.load_config().get('smtp_to') or '').strip()
    if not to:
        return jsonify({'error': 'no_recipient'}), 400
    got = _climate_load(giata)
    if not got:
        return jsonify({'error': 'not_found'}), 404
    months_hl = [int(m) for m in (data.get('months') or []) if str(m).isdigit()]
    import email_search
    html = email_search.climate_html(got['label'], got['data'], months_hl=months_hl)
    try:
        A.send_email(f"TUIWatch – Klima {got['label']}", html, to)
    except Exception as e:
        A.log.error("Klima-E-Mail fehlgeschlagen: %s", e)
        return jsonify({'error': 'send_failed'}), 502
    A.log.info("Klimatabelle %s an %s gesendet", got['label'], to)
    return jsonify({'sent': True, 'to': to})


@bp.route('/api/climate/<int:giata>', methods=['DELETE'])
def api_climate_delete(giata: int):
    """Gespeicherte Klimatabelle verwerfen (der nächste Abruf erzeugt sie neu)."""
    if (err := A._require_api()):
        return err
    with A.db() as con:
        n = con.execute('DELETE FROM climate WHERE giata=?', (giata,)).rowcount
    return jsonify({'deleted': n})


# ── Reiseführer je Reiseziel ──────────────────────────────────────────────────
# Dieselbe Bauart wie die Klimatabelle: einmal je Ziel von der KI erzeugt, dauerhaft
# gespeichert, Auffrischen nur auf Knopfdruck. Ein Reiseführer ist der teuerste
# Einzelaufruf im Add-on (dreizehn Abschnitte, zwanzig Vokabeln) — ihn bei jedem
# Öffnen neu zu erzeugen wäre nicht vertretbar.
#
# Bewusst eine generische Abschnittsstruktur statt vierzehn benannter Felder: die
# Abschnitte sind inhaltlich völlig verschieden (Vokabelliste, Notrufnummern,
# Verhaltensregeln), ein Schema mit festen Feldern je Abschnitt wäre riesig und
# müsste bei jeder Prompt-Änderung mitgezogen werden. `label` bleibt leer, wo ein
# Punkt keine Bezeichnung hat (Don't Dos, Insider-Tipps).
_GUIDE_SCHEMA = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "titel": {"type": "string"},
                    "einleitung": {"type": "string"},
                    "punkte": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "text": {"type": "string"},
                                "volatil": {"type": "boolean"},
                            },
                            "required": ["label", "text", "volatil"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["titel", "einleitung", "punkte"],
                "additionalProperties": False,
            },
        },
        "zusammenfassung": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["sections", "zusammenfassung"],
    "additionalProperties": False,
}

_GUIDE_SECTIONS = (
    ("Allgemeine Informationen",
     "Land; Hauptstadt (falls relevant); Sprache(n); Währung; aktueller Wechselkurs "
     "zum Euro; Zeitzone; Flugzeit ab Deutschland; Landesvorwahl; Steckdosen-Typ und "
     "Netzspannung"),
    ("Einreise",
     "Benötigte Dokumente; Visum erforderlich?; Gültigkeitsanforderungen für den "
     "Reisepass; Zollbestimmungen; besondere Einreisehinweise"),
    ("Klima",
     "Beste Reisezeit; Temperaturen nach Jahreszeit; Wassertemperaturen; Regenzeit; "
     "Windverhältnisse; UV-Index"),
    ("Gesundheit",
     "Trinkwasser; empfohlene Impfungen; Mücken; Apotheken; medizinische Versorgung"),
    ("Geld",
     "Kartenzahlung üblich?; Bargeld sinnvoll?; Geldautomaten; Trinkgeld-Empfehlungen; "
     "Preisniveau im Vergleich zu Deutschland"),
    ("Mobilität",
     "Mietwagen sinnvoll?; öffentliche Verkehrsmittel; Taxi; Uber/Bolt vorhanden?; "
     "Verkehrsregeln"),
    ("Internet & Kommunikation", "Mobilfunknetz; eSIM verfügbar?; WLAN; Roaming"),
    ("Sicherheit",
     "Allgemeine Sicherheitslage; typische Betrugsmaschen; Gegenden, die man meiden "
     "sollte; Verhalten bei Notfällen"),
    ("Kultur & Etikette",
     "Begrüßung; Kleidung; Fotografieren; religiöse Besonderheiten; Verhalten in "
     "Restaurants; Umgang mit Einheimischen"),
    ("Don't Dos",
     "Mindestens 10 Dinge, die Touristen möglichst vermeiden sollten, jeweils mit "
     "kurzer Begründung. `label` bleibt leer, die Begründung gehört in `text`."),
    ("Insider-Tipps",
     "10 Tipps, die viele Reiseführer nicht erwähnen; typische regionale "
     "Spezialitäten; lokale Getränke; Souvenirs; schöne Aussichtspunkte; weniger "
     "bekannte Ausflugsziele"),
    ("Praktische Informationen",
     "Notrufnummern; Öffnungszeiten; Feiertage; Stromausfälle häufig?; "
     "Leitungswasser; Sonnenuntergang je nach Jahreszeit"),
    ("Nützliche Wörter",
     "Genau 20 wichtige Wörter und Redewendungen. `label` = Wort in der Landessprache, "
     "`text` = deutsche Übersetzung (bei Bedarf mit Aussprachehilfe)."),
)


def _guide_prompt(label: str) -> str:
    secs = '\n'.join(f"{i}. {t}\n   {d}" for i, (t, d) in enumerate(_GUIDE_SECTIONS, 1))
    return (
        "Du bist ein erfahrener Reiseberater.\n\n"
        f"Erstelle für das Reiseziel „{label}\" einen kompakten, aber informativen "
        "Reiseführer.\n\n"
        "Liefere genau die folgenden dreizehn Abschnitte in dieser Reihenfolge und mit "
        "genau diesen Titeln. `einleitung` ist ein einleitender Satz (darf leer "
        "bleiben), `punkte` sind die Einzelangaben: `label` die Bezeichnung, `text` "
        "die Angabe.\n\n"
        f"{secs}\n\n"
        "Dazu `zusammenfassung`: höchstens 15 Stichpunkte mit allen wichtigen "
        "Informationen.\n\n"
        "Setze `volatil` auf true bei allem, was sich kurzfristig ändern kann — "
        "Einreisebestimmungen, Wechselkurs, Preise, Impfvorgaben, Sicherheitslage. "
        "Sonst false. Suche aktuelle Informationen im Web."
    )


def _guide_linkify_in_place(result: dict, urls: list | None) -> None:
    """Wie `_linkify_citations_in_place`, nur für die Reiseführer-Struktur — sonst
    stünden Perplexitys Quellen-Marker („[7]") als toter Text in jedem Abschnitt."""
    if not urls:
        return
    from ai_client import _perplexity_linkify_citations
    data = {'citations': urls}

    def lk(s):
        return _perplexity_linkify_citations(s, data) if isinstance(s, str) else s

    result['zusammenfassung'] = [lk(s) for s in (result.get('zusammenfassung') or [])]
    for sec in (result.get('sections') or []):
        if not isinstance(sec, dict):
            continue
        sec['einleitung'] = lk(sec.get('einleitung'))
        for p in (sec.get('punkte') or []):
            if isinstance(p, dict):
                p['text'] = lk(p.get('text'))


def _guide_load(giata: int):
    with A.db() as con:
        row = con.execute('SELECT label, ts, model, data FROM guide WHERE giata=?',
                          (giata,)).fetchone()
    if not row:
        return None
    try:
        data = json.loads(row['data'])
    except ValueError:
        return None
    return {'giata': giata, 'label': row['label'], 'ts': row['ts'],
            'model': row['model'], 'data': data}


@bp.route('/api/guide', methods=['GET'])
def api_guide_list():
    """Alle gespeicherten Reiseführer (ohne Inhalt) — für die Übersicht."""
    if (err := A._require_api()):
        return err
    with A.db() as con:
        rows = con.execute('SELECT giata, label, ts FROM guide '
                           'ORDER BY label COLLATE NOCASE').fetchall()
    return jsonify({'items': [dict(r) for r in rows]})


@bp.route('/api/guide/<int:giata>', methods=['GET'])
def api_guide_get(giata: int):
    """Gespeicherter Reiseführer — **ohne** KI-Aufruf. Die zum Ziel gespeicherte
    Klimatabelle kommt mit, sie wird im selben Fenster angezeigt."""
    if (err := A._require_api()):
        return err
    got = _guide_load(giata)
    if not got:
        return jsonify({'found': False, 'giata': giata})
    return jsonify(dict(got, found=True, climate=(_climate_load(giata) or {}).get('data')))


@bp.route('/api/ai/guide', methods=['POST'])
def api_ai_guide():
    """Reiseführer per KI erzeugen und dauerhaft speichern. Liegt er vor, kommt er
    unverändert zurück; `refresh: true` erzwingt eine Neuerstellung."""
    if (err := A._require_api()):
        return err
    data = request.get_json(silent=True) or {}
    try:
        giata = int(data.get('giata'))
    except (TypeError, ValueError):
        return jsonify({'error': 'no_dest'}), 400
    label = (data.get('label') or '').strip()
    if not data.get('refresh'):
        if (got := _guide_load(giata)):
            return jsonify(dict(got, found=True, cached=True,
                                climate=(_climate_load(giata) or {}).get('data')))
    if not label:
        return jsonify({'error': 'no_dest'}), 400
    api_key, model = _ai_config()
    if not api_key:
        return jsonify({'error': 'no_api_key',
                        'note': 'Kein KI-API-Key in den Add-on-Einstellungen hinterlegt'}), 400
    prompt = _guide_prompt(label)
    if (preview := _prompt_preview_response(data, prompt)):
        return preview
    prompt = _resolve_prompt(data, prompt)
    # 12000 statt der 3000 der Klimatabelle: dreizehn Abschnitte plus zwanzig Vokabeln
    # sprengen jedes kleinere Budget, und eine abgeschnittene Antwort ist kein
    # gültiges JSON — der Aufruf wäre komplett verloren.
    text, usage, code = A._ai_request(api_key, model, prompt, max_tokens=12000,
                                      log_ctx=f"Reiseführer {label}",
                                      use_web_search=True, output_schema=_GUIDE_SCHEMA)
    if code == 'failed':
        return jsonify({'error': 'ai_failed'}), 502
    if code == 'refused':
        return jsonify({'error': 'ai_refused'}), 502
    if code == 'empty' or not text:
        return jsonify({'error': 'ai_empty'}), 502
    try:
        result = json.loads(text)
    except ValueError:
        A.log.warning("Reiseführer %s: KI-Antwort kein gültiges JSON (%d Zeichen): %.200s",
                      label, len(text), text)
        return jsonify({'error': 'ai_empty'}), 502
    sections = [s for s in (result.get('sections') or []) if isinstance(s, dict)]
    if len(sections) < 5:
        A.log.warning("Reiseführer %s: nur %d Abschnitte geliefert", label, len(sections))
        return jsonify({'error': 'ai_empty'}), 502
    _guide_linkify_in_place(result, (usage or {}).pop('citation_urls', None))
    usage['estimated_usd'] = _ai_call_cost(model, usage)
    totals = _record_ai_usage(model, usage)
    ts = int(time.time())
    with A.db() as con:
        con.execute('INSERT OR REPLACE INTO guide (giata, label, ts, model, data) '
                    'VALUES (?,?,?,?,?)',
                    (giata, label, ts, model, json.dumps(result, ensure_ascii=False)))
    A.log.info("Reiseführer für %s (%s) gespeichert — %d Abschnitte", label, giata,
               len(sections))
    return jsonify({'found': True, 'cached': False, 'giata': giata, 'label': label,
                    'ts': ts, 'model': model, 'data': result,
                    'climate': (_climate_load(giata) or {}).get('data'),
                    'usage': usage, 'totals': totals})


@bp.route('/api/guide/<int:giata>/email', methods=['POST'])
def api_guide_email(giata: int):
    """Gespeicherten Reiseführer per E-Mail verschicken — inklusive Klimatabelle,
    sofern eine gespeichert ist. Kein KI-Aufruf."""
    if (err := A._require_api()):
        return err
    if not A.smtp_configured():
        return jsonify({'error': 'smtp_not_configured'}), 400
    data = request.get_json(silent=True) or {}
    to = (data.get('to') or A.load_config().get('smtp_to') or '').strip()
    if not to:
        return jsonify({'error': 'no_recipient'}), 400
    got = _guide_load(giata)
    if not got:
        return jsonify({'error': 'not_found'}), 404
    import email_search
    html = email_search.guide_html(got['label'], got['data'],
                                   climate=(_climate_load(giata) or {}).get('data'))
    try:
        A.send_email(f"TUIWatch – Reiseführer {got['label']}", html, to)
    except Exception as e:
        A.log.error("Reiseführer-E-Mail fehlgeschlagen: %s", e)
        return jsonify({'error': 'send_failed'}), 502
    A.log.info("Reiseführer %s an %s gesendet", got['label'], to)
    return jsonify({'sent': True, 'to': to})


@bp.route('/api/guide/<int:giata>', methods=['DELETE'])
def api_guide_delete(giata: int):
    """Gespeicherten Reiseführer verwerfen (der nächste Abruf erzeugt ihn neu)."""
    if (err := A._require_api()):
        return err
    with A.db() as con:
        n = con.execute('DELETE FROM guide WHERE giata=?', (giata,)).rowcount
    return jsonify({'deleted': n})


def _search_advice_prompt(d: dict) -> str:
    """Prompt für den Reisezeit-Check aus der Suchmaske: taugt der gewählte Zeitraum
    für dieses Ziel, wie liegt er preislich, und was wären ähnliche Alternativen.

    Die Suchmaske weiß nichts über Klima oder Saison — genau deshalb ist das eine
    KI-Frage. Mitgegeben werden nur die Eckdaten der Suche und, falls schon gesucht
    wurde, eine kurze Preisstatistik der Treffer: ohne die könnte die KI zum
    Preisniveau nur allgemein herumraten, mit ihr kann sie den konkreten Zeitraum
    einordnen."""
    dest = (d.get('dest') or '').strip() or 'das gewählte Reiseziel'
    start, end = (d.get('start') or '').strip(), (d.get('end') or '').strip()
    lines = [f"Reiseziel: {dest}"]
    if start and end:
        lines.append(f"Gewünschter Reisezeitraum: {start} bis {end}")
    elif start:
        lines.append(f"Gewünschter Reisebeginn: {start}")
    if d.get('duration'):
        lines.append(f"Reisedauer: {d['duration']}"
                     + (" (exakt dieser Zeitraum)" if d.get('exact') else " Nächte"))
    if d.get('travellers'):
        lines.append(f"Reisende: {d['travellers']}")
    if (d.get('airport_label') or d.get('airport')):
        lines.append(f"Abflughafen: {d.get('airport_label') or d.get('airport')}")
    boards = [_BOARD_LABELS.get(str(b), str(b)) for b in (d.get('boards') or [])]
    if boards:
        lines.append("Verpflegung: " + ", ".join(boards))
    if d.get('min_stars'):
        lines.append(f"Mindestens {d['min_stars']} Sterne")
    if d.get('min_recommend'):
        lines.append(f"Mindestens {d['min_recommend']} % Weiterempfehlung")
    if d.get('direct'):
        lines.append("Nur Direktflüge")
    if d.get('adults_only'):
        lines.append("Nur Erwachsenenhotels")
    stats = d.get('results') or {}
    if stats.get('count'):
        s = [f"{stats['count']} Treffer"]
        if stats.get('total'):
            s.append(f"von {stats['total']} in der Region")
        if stats.get('min_price'):
            s.append(f"günstigster {A._eur(stats['min_price'])} p. P.")
        if stats.get('median_price'):
            s.append(f"Median {A._eur(stats['median_price'])}")
        if stats.get('max_price'):
            s.append(f"teuerster {A._eur(stats['max_price'])}")
        lines.append("Aktuelle Suchtreffer: " + ", ".join(s))
    return (
        "Ich plane folgende Reise und habe sie so in meiner Suchmaske stehen:\n\n"
        + "\n".join(f"- {x}" for x in lines) + "\n\n"
        "Bitte prüfe das und antworte auf Deutsch, sprich mich durchgehend mit „Du“ "
        "an (informell, nicht „Sie“). Gliedere die Antwort mit diesen Überschriften:\n\n"
        "**1. Reisezeit** — Taugt der gewählte Zeitraum für dieses Ziel? Gehe auf "
        "Regen-/Trockenzeit, Temperaturen (Luft und Wasser), Luftfeuchtigkeit, Wind "
        "sowie Hurrikan-/Monsun-/Zyklonsaison ein, soweit für das Ziel relevant. "
        "Nenne konkrete Werte statt Allgemeinplätzen.\n"
        "**2. Saison und Preisniveau** — Ist der Zeitraum Haupt-, Neben- oder "
        "Zwischensaison? Welche Monate sind an diesem Ziel erfahrungsgemäß die "
        "Schnäppchenmonate, und wie viel günstiger sind sie grob gegenüber der "
        "Hauptsaison? Achte auf Schulferien und Feiertage in Deutschland sowie auf "
        "lokale Feiertage/Großereignisse, die Preise oder Verfügbarkeit treiben.\n"
        "**3. Besserer Zeitraum?** — Falls ein anderer Termin für dasselbe Ziel "
        "deutlich mehr fürs Geld böte oder wetterseitig klar besser wäre, nenne ihn "
        "konkret (Monat, gern mit Kalenderwoche) und sag, was er bringt. Passt der "
        "gewählte Zeitraum schon gut, sag das ebenso klar, statt um jeden Preis eine "
        "Alternative zu konstruieren.\n"
        "**4. Ähnliche Ziele** — Nenne 2 bis 4 Alternativziele mit vergleichbarem "
        "Charakter (Flugzeit ab dem genannten Abflughafen, Klima zur gewählten Zeit, "
        "Preisniveau, Art des Urlaubs) und schreibe je Ziel einen Satz, worin es sich "
        "vom Wunschziel unterscheidet — Vor- UND Nachteil.\n\n"
        "Nutze die Websuche für alles Saison-, Wetter- und Preisabhängige. Sag klar, "
        "worauf sich deine Angaben stützen; wo du unsicher bist, sag es offen statt "
        "zu spekulieren. Keine Hotelempfehlungen — es geht um Zeitraum und Ziel."
    )


@bp.route('/api/ai/search-advice', methods=['POST'])
def api_ai_search_advice():
    """Reisezeit-Check direkt aus der Suchmaske: Klima/Saison zum gewählten Zeitraum,
    Schnäppchenmonate und ähnliche Alternativziele. Die Eckdaten kommen vom Frontend
    (Maskenstand plus optional eine Preisstatistik der aktuellen Treffer), nicht aus
    der DB — die Suche wird ja nicht persistiert."""
    if (err := A._require_api()):
        return err
    api_key, model = _ai_config()
    if not api_key:
        return jsonify({'error': 'no_api_key',
                        'note': 'Kein Anthropic API-Key in den Add-on-Einstellungen hinterlegt'}), 400
    data = request.get_json(silent=True) or {}
    dest = (data.get('dest') or '').strip()
    if not dest:
        return jsonify({'error': 'no_dest'}), 400
    prompt = _search_advice_prompt(data)
    if (preview := _prompt_preview_response(data, prompt)):
        return preview
    prompt = _resolve_prompt(data, prompt)
    text, usage, err = A._ai_call(api_key, model, prompt, max_tokens=2500,
                                  log_ctx="Reisezeit-Check")
    if err:
        return err
    usage['estimated_usd'] = _ai_call_cost(model, usage)
    totals = _record_ai_usage(model, usage)
    title = dest + (f" ({data['start']}–{data['end']})"
                    if data.get('start') and data.get('end') else '')
    aid = _save_ai_analysis('search_advice', title, model, text, usage, prompt)
    return jsonify({'summary': text, 'usage': usage, 'totals': totals, 'id': aid,
                    'cached': False})


def _ai_ask_general(question: str, data: dict, api_key: str, model: str):
    """Allgemeine Reisefrage — zu Regionen, Ländern, Reisezeiten, Einreise,
    Verkehrsmitteln, allem was (noch) nicht im Portfolio steckt.

    Anders als die Portfolio-Frage bekommt die KI hier keine Angebotsliste,
    sondern muss auf Websuche und Allgemeinwissen zurückgreifen. Die Betonung im
    Prompt liegt deshalb auf Aktualität und auf dem offenen Eingeständnis von
    Unsicherheit: Einreiseregeln, Preise und Öffnungszeiten ändern sich, und eine
    selbstbewusst formulierte veraltete Auskunft wäre hier schädlicher als ein
    ehrliches „das solltest du kurz vor der Reise gegenprüfen"."""
    home = (A.load_config().get('trippilot_home_location') or '').strip()
    prompt = (
        f"Allgemeine Reisefrage: {question}\n\n"
        + (f"Mein Heimatort ist {home} — nutze das für Fragen zu Anreise, Flugzeit "
           "oder Entfernung.\n\n" if home else "")
        + "Beantworte die Frage auf Deutsch, sprich mich durchgehend mit „Du“ an "
        "(informell, nicht „Sie“). Nutze die Websuche für alles, was sich ändern "
        "kann — Einreise- und Visabestimmungen, Impfempfehlungen, Feiertage, "
        "Wetter- und Klimadaten der Saison, Preisniveau, aktuelle Lage vor Ort. "
        "Sag klar dazu, worauf sich deine Angabe stützt und wie aktuell sie ist; "
        "bei Regeln, die sich häufig ändern (Einreise, Gesundheit), weise darauf "
        "hin, dass sie kurz vor Reiseantritt gegenzuprüfen sind. Wenn du etwas "
        "nicht verlässlich weißt, sag das offen, statt zu spekulieren. "
        "Antworte strukturiert und knapp — Überschriften und Aufzählungen statt "
        "langer Fließtexte. Es geht ausdrücklich NICHT um meine bereits "
        "getrackten Angebote; empfiehl keine konkreten Hotelbuchungen, es sei "
        "denn, ich frage danach."
    )
    if (preview := _prompt_preview_response(data, prompt)):
        return preview
    prompt = _resolve_prompt(data, prompt)
    text, usage, err = A._ai_call(api_key, model, prompt, max_tokens=1800,
                                  log_ctx="Allgemeine Reisefrage")
    if err:
        return err
    usage['estimated_usd'] = _ai_call_cost(model, usage)
    totals = _record_ai_usage(model, usage)
    aid = _save_ai_analysis('ask_general', question, model, text, usage, prompt)
    return jsonify({'summary': text, 'usage': usage, 'totals': totals, 'id': aid,
                    'cached': False})


@bp.route('/api/ai/ask', methods=['POST'])
def api_ai_ask():
    """Freitext-Frage. Zwei Ausprägungen über `scope`:

    * `portfolio` (Standard) — Frage über die aktuell getrackten Angebote: Preis,
      Ort, Sterne/Weiterempfehlung, Trend, Wunschpreis, Tags werden mitgeschickt.
    * `general` — allgemeine Reisefrage ohne Portfolio-Bezug (Region, Land,
      Reisezeit, Einreise, Verkehrsmittel …). Bewusst OHNE die Angebotsliste: sie
      wäre für solche Fragen nur Ballast, würde Tokens kosten und die Antwort
      unnötig auf die eigenen Hotels lenken. Braucht deshalb auch keine Angebote —
      die Frage lässt sich mit leerem Portfolio genauso stellen."""
    if (err := A._require_api()):
        return err
    api_key, model = _ai_config()
    if not api_key:
        return jsonify({'error': 'no_api_key',
                        'note': 'Kein Anthropic API-Key in den Add-on-Einstellungen hinterlegt'}), 400
    data = request.get_json(silent=True) or {}
    question = (data.get('question') or '').strip()
    if not question:
        return jsonify({'error': 'invalid'}), 400
    if (data.get('scope') or 'portfolio') == 'general':
        return _ai_ask_general(question, data, api_key, model)
    offers = [o for o in A._collect_offers() if not o.get('archived')]
    if not offers:
        return jsonify({'error': 'no_offers'}), 400

    def nm(o):
        return o.get('label') or o.get('hotel') or f"Angebot #{o['id']}"

    lines = []
    for o in offers:
        parts = [nm(o)]
        if o.get('location'):
            parts.append(o['location'])
        if o.get('stars'):
            parts.append(f"{o['stars']}★")
        if o.get('recommendation') is not None:
            parts.append(f"{o['recommendation']}% Weiterempfehlung")
        if o.get('price') is not None:
            parts.append(f"{A._eur(o['price'])} p.P.")
        if o.get('delta'):
            parts.append(f"Δ letzte Prüfung {A._eur(o['delta'])}")
        if o.get('target_price'):
            parts.append(f"Wunschpreis {A._eur(o['target_price'])}")
        if o.get('return_date'):
            parts.append(f"Rückreise {o['return_date']}")
        if o.get('tags'):
            parts.append("Tags: " + ", ".join(o['tags']))
        lines.append("- " + " · ".join(str(p) for p in parts))

    prompt = (
        "Hier ist mein aktuelles Portfolio getrackter Reisen/Hotels bei TUIWatch:\n\n"
        + "\n".join(lines) + "\n\n"
        f"Frage dazu: {question}\n\n"
        "Antworte auf Deutsch, sprich den Nutzer dabei durchgehend mit „Du“ an "
        "(informell, nicht „Sie“), konkret. Für alles, was die obigen Daten "
        "bereits enthalten (Preis, Ort, Sterne, Trend, Wunschpreis, Tags), nenne "
        "die betroffenen Hotels beim Namen und stütze dich ausschließlich auf "
        "diese Daten — erfinde hier nichts dazu. Betrifft die Frage etwas, das "
        "die Daten nicht abdecken (z. B. Klima/Wetter zur Reisezeit, "
        "Sehenswürdigkeiten, aktuelle Ereignisse am Ort), nutze die Websuche und "
        "beantworte es trotzdem, statt nur auf fehlende Daten zu verweisen. Wenn "
        "auch die Websuche keine verlässliche Antwort liefert, sag das offen "
        "statt zu spekulieren."
    )
    if (preview := _prompt_preview_response(data, prompt)):
        return preview
    prompt = _resolve_prompt(data, prompt)
    text, usage, err = A._ai_call(api_key, model, prompt, max_tokens=1500, log_ctx="Portfolio-Frage")
    if err:
        return err
    usage['estimated_usd'] = _ai_call_cost(model, usage)
    totals = _record_ai_usage(model, usage)
    aid = _save_ai_analysis('ask', question, model, text, usage, prompt)
    return jsonify({'summary': text, 'usage': usage, 'totals': totals, 'id': aid, 'cached': False})


@bp.route('/api/ai/prompt-settings', methods=['GET', 'POST'])
def api_ai_prompt_settings():
    """Eigene KI-Prompt-Vorlagen für Reiseberater/Hotelvergleich einsehen/speichern.
    GET liefert je Feature Default-Text + gespeicherten Custom-Text + Enabled-Flag;
    POST speichert je Feature unabhängig (toleriert Teil-Updates)."""
    if (err := A._require_api()):
        return err
    if request.method == 'GET':
        return jsonify({
            feature: {
                'default': default,
                'enabled': A._meta_get(f'custom_prompt_{feature}_enabled') == '1',
                'text': A._meta_get(f'custom_prompt_{feature}_text') or '',
            }
            for feature, default in _PROMPT_FEATURES.items()
        })
    data = request.get_json(silent=True) or {}
    for feature in _PROMPT_FEATURES:
        fdata = data.get(feature)
        if not isinstance(fdata, dict):
            continue
        text = (fdata.get('text') or '').strip()[:_CUSTOM_PROMPT_MAX_LEN]
        A._meta_set(f'custom_prompt_{feature}_enabled', '1' if fdata.get('enabled') else '0')
        A._meta_set(f'custom_prompt_{feature}_text', text)
    return jsonify({'saved': True})


@bp.route('/api/ai/provider', methods=['GET', 'POST'])
def api_ai_provider():
    """Status/Umschalter für den aktiven KI-Anbieter. GET liefert, welcher
    Provider gerade aktiv ist und ob überhaupt umgeschaltet werden kann (nur
    möglich, wenn mindestens 2 der 3 API-Keys hinterlegt sind — sonst bestimmt
    automatisch der eine vorhandene Key den Provider, siehe
    `_ai_active_provider`). POST wechselt den aktiven Provider (nur erlaubt,
    wenn der Ziel-Provider auch konfiguriert ist) und persistiert die Wahl in
    `meta`. `both_configured` bleibt aus Kompatibilitätsgründen erhalten
    (bedeutet jetzt „mind. 2 von 3 konfiguriert"); `configured_providers` ist
    die neue, vollständige Liste fürs Frontend."""
    if (err := A._require_api()):
        return err
    cfg = A.load_config()
    configured = _configured_ai_providers(cfg)
    multi = len(configured) > 1
    if request.method == 'POST':
        provider = (request.get_json(silent=True) or {}).get('provider')
        if provider not in _AI_PROVIDERS:
            return jsonify({'error': 'invalid_provider'}), 400
        if not multi or provider not in configured:
            return jsonify({'error': 'not_both_configured'}), 400
        A._meta_set('ai_provider_active', provider)
    return jsonify({'active': _ai_active_provider(cfg), 'both_configured': multi,
                    'configured_providers': configured,
                    'anthropic_configured': 'anthropic' in configured,
                    'gemini_configured': 'gemini' in configured,
                    'perplexity_configured': 'perplexity' in configured})


# Felder/Labels/Typen kommen aus derselben JSON wie der Wizard im Frontend
# (trippilot_questions) — sonst würde eine dort ergänzte Frage beim Absenden
# still verworfen. Absichtlich Funktionen statt Modul-Konstanten: die Datei ist
# zur Laufzeit editierbar, ein einmal gelesenes Tupel wäre sofort veraltet.
# Reihenfolge der Fragen = Reihenfolge der Profilzeilen im Prompt.
_advisor_fields = TQ.fields              # Mehrfachauswahl -> Liste (max. 15 x 40 Zeichen)
_advisor_list_fields = TQ.list_fields    # Freitext        -> max. 500 Zeichen
_advisor_text_fields = TQ.text_fields    # Einfachauswahl  -> max. 60 Zeichen
_advisor_labels = TQ.labels

_ADVISOR_VALUE_MAXLEN = 40
_ADVISOR_LIST_MAXLEN = 15
_ADVISOR_TEXT_MAXLEN = 500
_ADVISOR_CHOICE_MAXLEN = 60


def _advisor_prompt(p: dict, prev_dna: dict | None = None) -> str:
    """Baut den Reiseberater-Prompt aus dem kompletten Profil (Region/Interessen/
    Reiseart/Budget/Reisezeit/Wetter/Aktivitäten/Unterkunft/Hotelwünsche/Flug/
    Abneigungen/Freitext) — freie KI-Empfehlung, nicht auf eigene Angebote
    beschränkt, mit Websuche für reale/aktuelle Klimadaten. `prev_dna` (optional)
    ist das aus früheren Anfragen gespeicherte Reise-DNA-Profil (Zusatzkontext).
    Ist `region` der Tagesausflug-Wert des Fragebogens, wird stattdessen ein
    Tagesausflug ohne Übernachtung geplant (eigener Instruktionstext, keine
    TUI/Unterkunfts-Klauseln, keine Reise-DNA)."""
    is_daytrip = _is_daytrip(p)
    labels = _advisor_labels()
    lines = ["Ein Nutzer sucht per Reiseberater-Fragebogen sein nächstes Urlaubsziel. "
             "Sein Profil:\n"]
    for key in _advisor_fields():
        val = p.get(key)
        if isinstance(val, list):
            val = ", ".join(str(v).strip() for v in val if str(v).strip())
        if val:
            lines.append(f"- {labels.get(key, key)}: {val}")
    if not is_daytrip and _profile_has(p, 'travel_type',
                                       _semantic('package_tour', _DEFAULT_PACKAGE_TOUR)):
        lines.append(
            "\nWichtig: Der Nutzer will eine Pauschalreise (Flug + Hotel) buchen. "
            "Empfehle Ziele/Regionen, die gängige Veranstalter (z. B. TUI, DER "
            "Touristik, FTI) im Programm haben — grob per Websuche plausibilisieren, "
            "aber keine übertrieben strikte Einzelprüfung verlangen."
        )
    if not is_daytrip and (p.get('excluded_countries') or p.get('excluded_countries_other')):
        lines.append(
            "\nWichtig: Schlage unter keinen Umständen Ziele in den oben unter "
            "„Kommt nicht in Frage“/„Weitere ausgeschlossene Länder“ genannten "
            "Ländern/Regionen vor — auch nicht als Alternative."
        )
    if not is_daytrip and _profile_has(p, 'arrival_mode',
                                       _semantic('self_arrival', _DEFAULT_SELF_ARRIVAL)):
        transport = p.get('arrival_mode')
        lines.append(
            "\nWichtig: Der Nutzer reist eigenständig mit "
            f"{transport} an, nicht mit dem Flugzeug. Schlage "
            "ausschließlich Ziele vor, die vom angegebenen Startort aus "
            "innerhalb der angegebenen maximalen Entfernung/Fahrzeit realistisch "
            "erreichbar sind (Fahrstrecke/-zeit per Websuche grob abschätzen) — "
            "das gilt auch für den 🔀 Alternative-Vorschlag. Der Abschnitt "
            "🎲 Überraschung darf in diesem Fall KEIN anderes Land/keinen "
            "anderen Kontinent vorschlagen, sondern muss ebenfalls innerhalb "
            "der Fahrdistanz bleiben — wähle stattdessen ein Ziel in "
            "Reichweite, an das der Nutzer wahrscheinlich nicht selbst gedacht "
            "hätte. Bei „Pauschalreise“ gemeinsam mit eigener Anreise "
            "weise darauf hin, dass viele Pauschalreisen einen Flug "
            "beinhalten und das Angebot an reinen Fahr-Pauschalreisen "
            "eingeschränkter sein kann."
        )
    if prev_dna and not is_daytrip:
        dna_line = ", ".join(f"{label} {value}%" for label, value in prev_dna.items())
        lines.append(
            f"\nZusatzkontext aus früheren Reiseberater-Anfragen dieses Nutzers "
            f"(Reise-DNA, grobe Tendenz, nicht überbewerten): {dna_line}."
        )
    if not is_daytrip:
        lines.append(
            "\nUnabhängig von den Angaben oben: Prüfe für jedes in Betracht gezogene "
            "Land per Websuche, ob aktuell eine Reisewarnung oder ein Sicherheitshinweis "
            "des Auswärtigen Amts (oder vergleichbare offizielle Warnung) besteht, und "
            "schlage solche Länder nicht vor, außer der Nutzer hat sie oben ausdrücklich "
            "gewünscht (z. B. als Ziel-Region genannt)."
        )
    if is_daytrip:
        lines.append("\n" + A._prompt_instructions('daytrip', _DEFAULT_DAYTRIP_INSTRUCTIONS))
    else:
        lines.append("\n" + A._prompt_instructions('advisor', _DEFAULT_ADVISOR_INSTRUCTIONS))
    lines.append(_ADVISOR_SAFETY_TRAILER)
    return "\n".join(lines)


# Welche Antwortwerte welche Bedeutung tragen, steht im `semantics`-Block der
# Fragen-JSON — sonst wäre jede Umbenennung einer Option ein stiller Ausfall
# (Reise-DNA auf Sockelwert, Prompt-Klauseln futsch). Diese Vorgaben greifen
# nur, solange eine Datei ohne `semantics`-Block im Einsatz ist.
_DEFAULT_PACKAGE_TOUR = ('Pauschalreise',)
_DEFAULT_SELF_ARRIVAL = ('Auto', 'Bus', 'Bahn')
_DEFAULT_DNA = {
    '🌴 Strand': {'interests': ['🌴 Strand'],
                 'hotel_wishes': ['direkte Strandlage', 'Sandstrand', 'Hausriff'],
                 'sea': ['28°C+ (tropisch warm)', '24–27°C (angenehm warm)'],
                 'beach_detail': ['Feinsandig', 'Weitläufig, kilometerlang', 'Direkt am Hotel']},
    '🏛️ Kultur': {'interests': ['🏛️ Kultur'], 'activities': ['Museen', 'Fotografieren']},
    '🎉 Nachtleben': {'interests': ['🎉 Nachtleben']},
    '⛰️ Aktiv': {'interests': ['🚶 Wandern', '🚴 Radfahren', '⛰️ Berge'],
                'activities': ['Wandern', 'Mountainbike', 'Skifahren', 'Surfen', 'Golf',
                               'Reiten', 'Segeln', 'Klettern', 'Tennis', 'Kajak/SUP'],
                'berge_detail': ['Anspruchsvolle Gipfeltouren', 'Skigebiet (Winter)']},
    '🍹 Entspannung': {'interests': ['🍹 Entspannung'], 'hotel_wishes': ['Spa', 'Ruhe']},
    '🍽️ Kulinarik': {'interests': ['🍽️ Essen'], 'activities': ['Kulinarik', 'Wein']},
    '👨‍👩‍👧 Familie': {'interests': ['👨‍👩‍👧 Familie'], 'companions': ['Familie'],
                    'hotel_wishes': ['Familienhotel', 'Kinderpool', 'Rutschen']},
    '💰 Preisbewusst': {'budget': ['bis 500 €', '500–1000 €']},
}


def _semantic(name: str, default):
    val = TQ.semantics().get(name)
    return val if val else default


def _profile_has(p: dict, key: str, vals) -> bool:
    """Trifft einer der Werte auf die (Einzel- oder Mehrfach-)Antwort zu?"""
    v = p.get(key)
    if isinstance(v, list):
        return any(x in v for x in vals)
    return v in vals


def _advisor_dna_scores(p: dict) -> dict:
    """Deterministisches Reise-DNA-Profil aus den Fragebogen-Antworten (kein
    zusätzlicher KI-Call) — je Kategorie ein grober 0-100-Score. Jede Frage
    liefert höchstens ein Signal, egal wie viele ihrer Werte passen."""
    dna = _semantic('dna', None) or _DEFAULT_DNA
    scores = {}
    for label, groups in dna.items():
        if not isinstance(groups, dict):
            continue
        hits = sum(1 for key, vals in groups.items()
                   if isinstance(vals, list) and _profile_has(p, key, vals))
        scores[label] = min(100, 15 + 35 * hits)
    return scores


def _advisor_dna_update(new_scores: dict) -> dict:
    """Verschmilzt neue DNA-Werte mit dem gespeicherten Profil (gleitender
    Mittelwert) und persistiert sie in `meta`, damit sich das Profil über
    mehrere Reiseberater-Anfragen hinweg stabilisiert statt bei jedem Aufruf
    komplett neu zu sein."""
    try:
        prev = json.loads(A._meta_get('travel_dna') or '{}')
    except (TypeError, ValueError):
        prev = {}
    prev_scores = prev.get('scores') or {}
    merged = {label: val if label not in prev_scores else round((prev_scores[label] + val) / 2)
              for label, val in new_scores.items()}
    A._meta_set('travel_dna', json.dumps(
        {'scores': merged, 'count': (prev.get('count') or 0) + 1, 'updated_ts': int(time.time())},
        ensure_ascii=False))
    return merged


def _advisor_dna_table(scores: dict) -> str:
    rows = "\n".join(f"| {label} | {value}% |" for label, value in scores.items())
    return f"\n\n#### 🧬 Deine Reise-DNA\n| Kategorie | Ausprägung |\n|---|---|\n{rows}\n"


@bp.route('/api/trippilot/questions')
def api_trippilot_questions():
    """Fragebogen für den TripPilot-Wizard. `source` sagt, ob die Nutzerdatei
    unter /config/trippilot greift oder die Auslieferungsversion; `errors` sind
    Probleme in einer fehlerhaften Nutzerdatei, damit die Oberfläche sie
    anzeigen kann statt sie nur ins Log zu schreiben."""
    if (err := A._require_api()):
        return err
    q = TQ.load()
    return jsonify({'steps': q['steps'], 'daytrip_value': _daytrip_value(),
                    'source': q['source'], 'errors': q['errors'],
                    'path': TQ.QUESTIONS_PATH})


@bp.route('/api/ai/travel-advisor', methods=['POST'])
def api_ai_travel_advisor():
    """KI-Reiseberater: aus einem kurzen Profil (Region, Interessen, Reiseart,
    Budget, Reisezeit, Wetterwünsche) schlägt Claude 3 passende Ziele vor — freie
    Empfehlung aus KI-Wissen + Websuche, unabhängig vom eigenen Angebots-Portfolio."""
    if (err := A._require_api()):
        return err
    api_key, model = _ai_config()
    if not api_key:
        return jsonify({'error': 'no_api_key',
                        'note': 'Kein Anthropic API-Key in den Add-on-Einstellungen hinterlegt'}), 400
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({'error': 'invalid'}), 400
    profile = {}
    list_fields, text_fields = _advisor_list_fields(), _advisor_text_fields()
    for key in _advisor_fields():
        val = data.get(key)
        if key in list_fields:
            if isinstance(val, list):
                profile[key] = [str(v).strip()[:_ADVISOR_VALUE_MAXLEN]
                                for v in val if str(v).strip()][:_ADVISOR_LIST_MAXLEN]
        elif key in text_fields:
            if isinstance(val, str) and val.strip():
                profile[key] = val.strip()[:_ADVISOR_TEXT_MAXLEN]
        elif isinstance(val, str) and val.strip():
            profile[key] = val.strip()[:_ADVISOR_CHOICE_MAXLEN]
    if not any(profile.values()):
        return jsonify({'error': 'invalid'}), 400

    try:
        prev_dna = (json.loads(A._meta_get('travel_dna') or '{}')).get('scores') or {}
    except (TypeError, ValueError):
        prev_dna = {}
    prompt = _advisor_prompt(profile, prev_dna)
    if (preview := _prompt_preview_response(data, prompt)):
        return preview
    prompt = _resolve_prompt(data, prompt)
    title = ', '.join(_region_values(profile)) or 'TripPilot'
    if profile.get('month'):
        title += ' · ' + profile['month']
    if profile.get('interests'):
        title += ' · ' + ', '.join(profile['interests'][:3])
    text, usage, err = A._ai_call(api_key, model, prompt, max_tokens=3072, log_ctx='TripPilot')
    if err:
        return err
    dna = {}
    if not _is_daytrip(profile):
        dna = _advisor_dna_update(_advisor_dna_scores(profile))
        text += _advisor_dna_table(dna)
    usage['estimated_usd'] = _ai_call_cost(model, usage)
    totals = _record_ai_usage(model, usage)
    aid = _save_ai_analysis('advisor', title, model, text, usage, prompt)
    return jsonify({'summary': text, 'usage': usage, 'totals': totals, 'id': aid, 'dna': dna,
                    'cached': False})


def _compare_prompt(hotels: list[dict], instructions: str) -> str:
    """Baut den Hotelvergleichs-Prompt: feste Hotel-Fakten-Blöcke + (ggf. vom
    Nutzer angepasste) Instruktionen."""
    blocks = ["\n".join(_hotel_fact_lines(h, label=f"Hotel {i}"))
              for i, h in enumerate(hotels, 1)]
    facts = ("Vergleiche ausführlich die folgenden Hotels für eine Reiseentscheidung:\n\n"
             + "\n\n".join(blocks))
    return facts + "\n\n" + instructions


@bp.route('/api/ai/hotel-compare', methods=['POST'])
def api_ai_hotel_compare():
    """Vergleicht 2–5 Hotels aus den Suchergebnissen in einem KI-Aufruf: gleiche
    Kriterien wie beim Einzel-Fazit, plus Vergleichstabelle und Empfehlung, welches
    Hotel für wen (Familie, Paar, Ruhe, …) am besten passt."""
    if (err := A._require_api()):
        return err
    api_key, model = _ai_config()
    if not api_key:
        return jsonify({'error': 'no_api_key',
                        'note': 'Kein Anthropic API-Key in den Add-on-Einstellungen hinterlegt'}), 400
    data = request.get_json(silent=True) or {}
    hotels = [h for h in (data.get('hotels') or [])
              if isinstance(h, dict) and (h.get('name') or '').strip()][:5]
    if len(hotels) < 2:
        return jsonify({'error': 'invalid'}), 400

    instructions = A._prompt_instructions('compare', _DEFAULT_COMPARE_INSTRUCTIONS)
    instr_hash = hashlib.sha1(instructions.encode('utf-8')).hexdigest()[:10]
    cache_key = (f'cmp:{instr_hash}:'
                 + '|'.join(sorted(str(h.get('giata') or (h.get('name') or '').lower())
                                   for h in hotels)))
    with A._ai_cache_lock:
        cached = A._ai_summary_cache.get(cache_key)
    if cached and time.time() - cached['ts'] < A._AI_SUMMARY_TTL:
        return jsonify({'summary': cached['summary'], 'usage': cached.get('usage'),
                        'totals': _ai_usage_totals(), 'id': cached.get('id'), 'cached': True})

    prompt = _compare_prompt(hotels, instructions)
    if (preview := _prompt_preview_response(data, prompt)):
        return preview
    prompt = _resolve_prompt(data, prompt)
    text, usage, err = A._ai_call(api_key, model, prompt, max_tokens=6144,
                                log_ctx=f"Vergleich {len(hotels)} Hotels")
    if err:
        return err
    usage['estimated_usd'] = _ai_call_cost(model, usage)
    totals = _record_ai_usage(model, usage)
    title = ' · '.join(h.get('name', '') for h in hotels)
    aid = _save_ai_analysis('compare', title, model, text, usage, prompt)
    with A._ai_cache_lock:
        A._ai_summary_cache[cache_key] = {'summary': text, 'usage': usage, 'id': aid, 'ts': time.time()}
    return jsonify({'summary': text, 'usage': usage, 'totals': totals, 'id': aid, 'cached': False})


def _ai_md_to_html(text: str) -> str:
    """Sehr einfacher Markdown→HTML-Renderer fürs E-Mail-Layout (Überschriften,
    Listen, Tabellen, **fett**) — spiegelt die JS-Variante `aiMdLite` im Frontend."""
    def esc(s):
        return A._esc_html(s)

    def inline(s):
        # [n](url) -> anklickbare Zitat-Nummer (Perplexity), vor **bold** wie im
        # JS-Pendant aiInline — sonst stört Fettdruck rund um eine Zitat-Klammer
        # die Link-Erkennung.
        s = re.sub(r'\[(\d+)\]\((https?://[^\s")]+)\)',
                   r'<a href="\2" style="color:#0b65d8;text-decoration:none">[\1]</a>', s)
        return re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s)

    def row(l):
        return [inline(c.strip()) for c in l.strip().strip('|').split('|')]

    lines = esc(text).split('\n')
    html, in_list, i = [], False, 0

    def close_list():
        nonlocal in_list
        if in_list:
            html.append('</ul>')
            in_list = False

    while i < len(lines):
        line = lines[i].strip()
        if not line:
            close_list()
            i += 1
            continue
        if line.startswith('|') and i + 1 < len(lines) \
                and re.match(r'^\|?[\s:|-]+\|?$', lines[i + 1].strip()):
            close_list()
            header = row(line)
            body_rows, j = [], i + 2
            while j < len(lines) and lines[j].strip().startswith('|'):
                body_rows.append(row(lines[j]))
                j += 1
            html.append('<table style="width:100%;border-collapse:collapse;'
                        'margin:8px 0 16px;font-size:13px"><thead><tr>'
                        + ''.join(f'<th style="text-align:left;padding:6px 8px;'
                                 f'border-bottom:1px solid #ddd;color:#777">{c}</th>'
                                 for c in header)
                        + '</tr></thead><tbody>'
                        + ''.join('<tr>' + ''.join(
                            f'<td style="padding:6px 8px;border-bottom:1px solid #eee">{c}</td>'
                            for c in r) + '</tr>' for r in body_rows)
                        + '</tbody></table>')
            i = j
            continue
        h = re.match(r'^#{1,4}\s+(.*)', line)
        b = re.match(r'^[-*]\s+(.*)', line)
        if h:
            close_list()
            html.append(f'<h3 style="margin:18px 0 6px;color:#10243e;font-size:15px">'
                        f'{inline(h.group(1))}</h3>')
        elif b:
            if not in_list:
                html.append('<ul style="margin:0;padding-left:18px;color:#333;font-size:14px">')
                in_list = True
            html.append(f'<li style="margin:4px 0">{inline(b.group(1))}</li>')
        else:
            close_list()
            html.append(f'<p style="margin:0 0 10px;color:#333;font-size:14px;'
                        f'line-height:1.45">{inline(line)}</p>')
        i += 1
    close_list()
    return ''.join(html)


@bp.route('/api/ai/email', methods=['POST'])
def api_ai_email():
    """Eine gespeicherte KI-Analyse (Fazit oder Vergleich, per ID aus `ai_analyses`)
    als HTML-Mail versenden — funktioniert für frische wie für Verlaufs-Ergebnisse,
    da beide immer eine ID haben. Empfänger optional aus dem Nextcloud-Adressbuch
    (bestehender `/api/contacts`-Autocomplete im UI)."""
    if (err := A._require_api()):
        return err
    if not A.smtp_configured():
        return jsonify({'error': 'smtp_not_configured'}), 400
    data = request.get_json(silent=True) or {}
    to = (data.get('to') or A.load_config().get('smtp_to') or '').strip()
    if not to:
        return jsonify({'error': 'no_recipient'}), 400
    aid = data.get('id')
    with A.db() as con:
        row = con.execute('SELECT * FROM ai_analyses WHERE id=?', (aid,)).fetchone() if aid else None
    if not row:
        return jsonify({'error': 'not_found'}), 404
    kind_label = 'KI-Vergleich' if row['kind'] == 'compare' else 'KI-Fazit'
    subject = f"TUIWatch — {kind_label}: {row['title']}"[:200]
    html = (
        '<div style="font-family:system-ui,Arial,sans-serif;max-width:640px;margin:0 auto">'
        f'<h2 style="color:#10243e">🤖 {kind_label}</h2>'
        f'<p style="color:#555;font-size:13px">{A._esc_html(row["title"])}</p>'
        + _ai_md_to_html(row['summary'])
        + '</div>'
    )
    try:
        A.send_email(subject, html, to)
    except Exception as e:
        A.log.error("KI-Analyse-E-Mail fehlgeschlagen: %s", e)
        return jsonify({'error': 'send_failed'}), 502
    A.log.info("KI-Analyse #%s per E-Mail an %s gesendet", aid, to)
    return jsonify({'sent': True, 'to': to})


@bp.route('/api/ai/history', methods=['GET'])
def api_ai_history():
    """Liste bisheriger KI-Fazits/-Vergleiche (neueste zuerst) für den KI-Verlauf."""
    if (err := A._require_api()):
        return err
    with A.db() as con:
        rows = con.execute(
            'SELECT id, kind, title, model, ts, substr(summary,1,160) AS preview, '
            "CASE WHEN prompt!='' THEN 1 ELSE 0 END AS has_prompt "
            'FROM ai_analyses ORDER BY id DESC LIMIT ?', (_AI_HISTORY_MAX,)).fetchall()
    return jsonify({'items': [dict(r) for r in rows]})


@bp.route('/api/ai/history/<int:aid>', methods=['GET'])
def api_ai_history_get(aid: int):
    """Vollständigen gespeicherten Analyse-Eintrag laden (fürs erneute Anzeigen)."""
    if (err := A._require_api()):
        return err
    with A.db() as con:
        row = con.execute('SELECT * FROM ai_analyses WHERE id=?', (aid,)).fetchone()
    if not row:
        return jsonify({'error': 'not_found'}), 404
    d = dict(row)
    try:
        d['usage'] = json.loads(d.get('usage') or '{}')
    except (TypeError, ValueError):
        d['usage'] = {}
    return jsonify(d)


@bp.route('/api/ai/history/<int:aid>', methods=['DELETE'])
def api_ai_history_delete(aid: int):
    if (err := A._require_api()):
        return err
    with A.db() as con:
        con.execute('DELETE FROM ai_analyses WHERE id=?', (aid,))
    # Buchungsscore/Region-Ausblick/Fazit-Zusammenfassungen werden bis zu 6h im
    # Prozess-Speicher gecacht (unabhängig von ai_analyses) — ohne Invalidierung
    # hier würde ein erneuter Klick nach dem Löschen aus dem KI-Verlauf denselben,
    # eigentlich gelöschten Stand aus dem Cache wieder anzeigen.
    with A._ai_cache_lock:
        for cache in (A._booking_score_cache, A._region_outlook_cache, A._ai_summary_cache):
            for key in [k for k, v in cache.items() if v.get('id') == aid]:
                del cache[key]
    return jsonify({'ok': True})


# max_tokens/use_web_search je Markdown-Kind (1:1 aus den jeweiligen Original-Routen
# übernommen) — für api_ai_history_repeat unten. booking_score/region_outlook sind
# NICHT hier drin, die laufen strukturiert über _ai_score_request (eigenes, festes
# max_tokens=1024/use_web_search=True).
_AI_RETRY_MARKDOWN_CONFIG = {
    'single': {'max_tokens': 4096, 'use_web_search': True},
    'calendar_outlook': {'max_tokens': 700, 'use_web_search': False},
    'ask': {'max_tokens': 1500, 'use_web_search': True},
    'ask_general': {'max_tokens': 1800, 'use_web_search': True},
    'search_advice': {'max_tokens': 2500, 'use_web_search': True},
    'advisor': {'max_tokens': 3072, 'use_web_search': True},
    'compare': {'max_tokens': 6144, 'use_web_search': True},
}


@bp.route('/api/ai/history/<int:aid>/repeat', methods=['POST'])
def api_ai_history_repeat(aid: int):
    """Wiederholt einen gespeicherten KI-Verlaufseintrag mit gewähltem Provider —
    schickt den eingefrorenen Prompt erneut, speichert das Ergebnis als NEUEN
    Verlaufseintrag (Original bleibt unverändert erhalten). Bei kind='advisor'
    (TripPilot) fehlt in der Wiederholung die angehängte Reise-DNA-Tabelle — die wird
    deterministisch aus dem Fragebogen-Zustand berechnet, der hier nicht gespeichert
    ist, nur der fertige Prompt-Text."""
    if (err := A._require_api()):
        return err
    data = request.get_json(silent=True) or {}
    provider = data.get('provider')
    if provider not in _AI_PROVIDERS:
        return jsonify({'error': 'invalid_provider'}), 400
    with A.db() as con:
        row = con.execute('SELECT kind, title, prompt FROM ai_analyses WHERE id=?',
                          (aid,)).fetchone()
    if not row:
        return jsonify({'error': 'not_found'}), 404
    if not row['prompt']:
        return jsonify({'error': 'no_prompt',
                        'note': 'Dieser Eintrag wurde vor der Wiederholen-Funktion gespeichert.'}), 400
    api_key, model = _ai_config_for(provider)
    if not api_key:
        return jsonify({'error': 'no_api_key'}), 400
    kind, title, prompt = row['kind'], row['title'], row['prompt']
    if (preview := _prompt_preview_response(data, prompt)):
        return preview
    prompt = _resolve_prompt(data, prompt)
    if kind in ('booking_score', 'region_outlook'):
        result, usage, err = _ai_score_request(prompt, model, api_key, title)
        if err:
            return err
        text = json.dumps(result, ensure_ascii=False)
    else:
        rcfg = _AI_RETRY_MARKDOWN_CONFIG.get(kind, {'max_tokens': 2048, 'use_web_search': True})
        result = None
        text, usage, err = A._ai_call(api_key, model, prompt, max_tokens=rcfg['max_tokens'],
                                    log_ctx=title, use_web_search=rcfg['use_web_search'])
        if err:
            return err
    usage['estimated_usd'] = _ai_call_cost(model, usage)
    totals = _record_ai_usage(model, usage)
    new_id = _save_ai_analysis(kind, title, model, text, usage, prompt)
    out = {'usage': usage, 'totals': totals, 'id': new_id}
    out.update({'result': result} if result is not None else {'summary': text})
    return jsonify(out)


_AI_FOLLOWUP_MAX_LEN = 2000  # Zeichen — Freitext-Folgefrage, großzügiger als übliche Formfelder
_AI_FOLLOWUP_UNSUPPORTED_KINDS = ('booking_score', 'region_outlook')  # strukturiertes JSON,
                                                                       # keine Konversation


def _ai_followup_messages(row) -> list[dict]:
    """Turn-Historie für eine Folgefrage: bereits gespeicherte Konversation
    (`conversation`-Spalte, JSON-Array) fortsetzen — bei Einträgen ohne bisherige
    Folgefrage wird sie einmalig aus dem eingefrorenen `prompt`+`summary` der
    Erstantwort rekonstruiert (die beiden existieren für jeden Eintrag mit
    `has_prompt`, die Konversation selbst erst ab der ersten Folgefrage)."""
    try:
        conv = json.loads(row['conversation'] or '[]')
    except (TypeError, ValueError):
        conv = []
    if not isinstance(conv, list) or not conv:
        conv = [{"role": "user", "content": row['prompt']},
                {"role": "assistant", "content": row['summary']}]
    return conv


@bp.route('/api/ai/history/<int:aid>/followup', methods=['POST'])
def api_ai_history_followup(aid: int):
    """Stellt eine Folgefrage zu einem bestehenden KI-Verlaufseintrag — echte
    Konversation (bisheriger Prompt + Antwort(en) + neue Frage), anders als
    „🔁 Wiederholen“, das nur denselben alten Prompt erneut verschickt.
    Ergänzt den bestehenden Eintrag um die neue Runde (statt einen neuen Eintrag
    anzulegen, damit der KI-Verlauf nicht mit einem Eintrag pro Folgefrage
    zumüllt) und antwortet mit demselben Modell/Provider, das die ursprüngliche
    Antwort gegeben hat (nicht zwangsläufig der aktuell aktive Standard-
    Provider) — funktioniert bei allen 3 Anbietern (Claude/Gemini/Perplexity
    unterstützen alle Mehrfach-Turn-Konversationen, siehe
    `ai_client.py::_ai_request_messages`). Nicht bei strukturierten Ergebnissen
    (Buchungsscore/Region-Ausblick — reines JSON statt Fließtext, siehe
    `_AI_FOLLOWUP_UNSUPPORTED_KINDS`)."""
    if (err := A._require_api()):
        return err
    data = request.get_json(silent=True) or {}
    question = (data.get('question') or '').strip()
    if not question or len(question) > _AI_FOLLOWUP_MAX_LEN:
        return jsonify({'error': 'invalid'}), 400
    with A.db() as con:
        row = con.execute('SELECT kind, title, model, prompt, summary, conversation '
                          'FROM ai_analyses WHERE id=?', (aid,)).fetchone()
    if not row:
        return jsonify({'error': 'not_found'}), 404
    if row['kind'] in _AI_FOLLOWUP_UNSUPPORTED_KINDS:
        return jsonify({'error': 'unsupported_kind'}), 400
    if not row['prompt'] or not row['summary']:
        return jsonify({'error': 'no_prompt',
                        'note': 'Dieser Eintrag hat keine gespeicherte Konversation.'}), 400
    model = row['model']
    api_key, _default_model = _ai_config_for(_provider_for_model(model))
    if not api_key:
        return jsonify({'error': 'no_api_key'}), 400
    if (preview := _prompt_preview_response(data, question)):
        return preview
    question = _resolve_prompt(data, question)
    messages = _ai_followup_messages(row)
    messages.append({"role": "user", "content": question})
    rcfg = _AI_RETRY_MARKDOWN_CONFIG.get(row['kind'], {'max_tokens': 2048, 'use_web_search': True})
    text, usage, err = A._ai_call_messages(api_key, model, messages, max_tokens=rcfg['max_tokens'],
                                         log_ctx=row['title'], use_web_search=rcfg['use_web_search'])
    if err:
        return err
    messages.append({"role": "assistant", "content": text})
    usage['estimated_usd'] = _ai_call_cost(model, usage)
    totals = _record_ai_usage(model, usage)
    with A.db() as con:
        con.execute('UPDATE ai_analyses SET summary=?, usage=?, conversation=?, ts=? WHERE id=?',
                    (text, json.dumps(usage), json.dumps(messages, ensure_ascii=False),
                     int(time.time()), aid))
    return jsonify({'summary': text, 'usage': usage, 'totals': totals, 'id': aid})


_dest_cache: dict = {}     # parent → {parentName, items}
_airports_cache: list = []  # einmalig geladen
_contacts_cache: list = []  # Nextcloud-Adressbuch, gecacht bis ?refresh=1

