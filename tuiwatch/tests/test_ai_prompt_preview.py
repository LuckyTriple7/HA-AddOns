"""Tests für die Option `ai_prompt_preview`: ist sie aktiv, liefert eine
interaktive KI-Route beim ersten Aufruf statt eines echten KI-Aufrufs nur den
fertigen Prompt zur Anzeige (`{'prompt_preview': ...}`) zurück. Erst ein
zweiter Aufruf mit `_prompt_confirmed: true` (optional `_prompt_override` mit
editiertem Text) löst den echten KI-Aufruf aus. Ist die Option aus (Standard),
verhält sich jede Route wie zuvor — ein einziger Aufruf, sofort das Ergebnis.
"""
import importlib
import json
import time

import pytest

pytest.importorskip("flask")

ING = {"X-Ingress-Path": "/test"}

_SCORE_RESULT = {
    "score": 72, "empfehlung": "beobachten", "vertrauen": 60,
    "erwartung_7_tage": "gleich", "erwartung_30_tage": "steigend",
    "begruendung": [{"text": "Preis nahe historischem Tief", "typ": "daten"}],
}


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


def _write_options(m, **opts):
    with open(m.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(opts, f)


def _mock_ai_request(m, monkeypatch, result=None, calls=None):
    """Ersetzt `_ai_request` durch einen Fake, der jeden Aufruf (inkl. Prompt)
    in `calls` protokolliert — für structured Output (Buchungsscore/Region-
    Ausblick) UND reinen Markdown-Text nutzbar."""
    calls = calls if calls is not None else []

    def fake(api_key, model, prompt, *, max_tokens, log_ctx, use_web_search=True,
              output_schema=None):
        calls.append({"prompt": prompt, "output_schema": output_schema})
        if output_schema is not None:
            text = json.dumps(result or _SCORE_RESULT)
        else:
            text = result if isinstance(result, str) else "KI-Antwort als Fließtext."
        return text, {"input_tokens": 100, "output_tokens": 50,
                      "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
                      "web_search_requests": 0}, None

    monkeypatch.setattr(m, "_ai_request", fake)
    monkeypatch.setattr(m, "_run_calendar", lambda *a, **k: None)  # kein Netz
    return calls


def _mock_ai_request_messages(m, monkeypatch, text="Vertiefte Antwort.", calls=None):
    calls = calls if calls is not None else []

    def fake(api_key, model, messages, *, max_tokens, log_ctx, use_web_search=True):
        # Kopie speichern — der Aufrufer hängt der Original-Liste danach die
        # Assistant-Antwort an, ein reiner Verweis würde die Assertion verfälschen.
        calls.append({"messages": list(messages)})
        return text, {"input_tokens": 20, "output_tokens": 10,
                      "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
                      "web_search_requests": 0}, None

    monkeypatch.setattr(m, "_ai_request_messages", fake)
    return calls


def _add_offer(m, url, price=1500, region="Kanaren", country="Spanien",
               return_date="2027-03-15"):
    now = int(time.time())
    with m.db() as con:
        con.execute(
            "INSERT INTO offers (url, hotel, region, country, return_date, created) "
            "VALUES (?,?,?,?,?,?)", (url, "Test-Hotel", region, country, return_date, now))
        oid = con.execute("SELECT id FROM offers WHERE url=?", (url,)).fetchone()["id"]
        con.execute("INSERT INTO price_history (offer_id, ts, price, ok) VALUES (?,?,?,1)",
                    (oid, now, price))
    return oid


def _insert_history(m, kind="single", title="Testhotel", model="claude-haiku-4-5",
                    summary="Alte Antwort", prompt="Alter Prompt-Text", conversation=""):
    with m.db() as con:
        cur = con.execute(
            "INSERT INTO ai_analyses (kind, title, model, summary, usage, ts, prompt, conversation) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (kind, title, model, summary, "{}", int(time.time()), prompt, conversation))
        return cur.lastrowid


# ── Option aus (Standard) ────────────────────────────────────────────────────

def test_preview_off_calls_ai_directly(m, monkeypatch):
    oid = _add_offer(m, "https://example.invalid/off?duration=7")
    _write_options(m, anthropic_api_key="sk-test")   # ai_prompt_preview fehlt -> False
    calls = _mock_ai_request(m, monkeypatch)
    c = m.app.test_client()
    r = c.post(f"/api/ai/booking-score/{oid}", headers=ING)
    d = r.get_json()
    assert r.status_code == 200
    assert "prompt_preview" not in d
    assert d["result"]["score"] == 72
    assert len(calls) == 1


# ── Option an: Buchungsscore (structured output) ────────────────────────────

def test_preview_on_returns_prompt_without_calling_ai(m, monkeypatch):
    oid = _add_offer(m, "https://example.invalid/on?duration=7")
    _write_options(m, anthropic_api_key="sk-test", ai_prompt_preview=True)
    calls = _mock_ai_request(m, monkeypatch)
    c = m.app.test_client()
    r = c.post(f"/api/ai/booking-score/{oid}", headers=ING)
    d = r.get_json()
    assert r.status_code == 200
    assert "prompt_preview" in d and d["prompt_preview"]
    assert "Test-Hotel" in d["prompt_preview"]
    assert calls == []   # kein echter KI-Aufruf ausgelöst


def test_preview_confirmed_with_override_sends_edited_prompt(m, monkeypatch):
    oid = _add_offer(m, "https://example.invalid/ov?duration=7")
    _write_options(m, anthropic_api_key="sk-test", ai_prompt_preview=True)
    calls = _mock_ai_request(m, monkeypatch)
    c = m.app.test_client()
    r = c.post(f"/api/ai/booking-score/{oid}", headers=ING,
               json={"_prompt_confirmed": True, "_prompt_override": "Mein editierter Prompt"})
    d = r.get_json()
    assert r.status_code == 200
    assert len(calls) == 1
    assert calls[0]["prompt"] == "Mein editierter Prompt"
    assert d["result"]["score"] == 72


def test_preview_confirmed_without_override_uses_built_prompt(m, monkeypatch):
    """Bestätigt ohne Override (Nutzer hat nichts geändert) -> der serverseitig
    gebaute Prompt geht unverändert raus, nicht leer/anders."""
    oid = _add_offer(m, "https://example.invalid/noov?duration=7")
    _write_options(m, anthropic_api_key="sk-test", ai_prompt_preview=True)
    calls = _mock_ai_request(m, monkeypatch)
    c = m.app.test_client()
    r = c.post(f"/api/ai/booking-score/{oid}", headers=ING,
               json={"_prompt_confirmed": True})
    assert r.status_code == 200
    assert len(calls) == 1
    assert "Test-Hotel" in calls[0]["prompt"]


def test_preview_cache_hit_skips_preview(m, monkeypatch):
    """Ein gecachtes Ergebnis (24h) braucht keinen frischen KI-Aufruf -> auch
    keine Prompt-Vorschau, unabhängig von der Option."""
    oid = _add_offer(m, "https://example.invalid/cache?duration=7")
    _write_options(m, anthropic_api_key="sk-test", ai_prompt_preview=True)
    _mock_ai_request(m, monkeypatch)
    c = m.app.test_client()
    c.post(f"/api/ai/booking-score/{oid}", headers=ING,
          json={"_prompt_confirmed": True})   # füllt den Cache
    r2 = c.post(f"/api/ai/booking-score/{oid}", headers=ING)
    d2 = r2.get_json()
    assert d2.get("cached") is True
    assert "prompt_preview" not in d2


# ── Option an: KI-Fazit (reiner Markdown-Text statt structured output) ─────

def test_hotel_summary_preview_roundtrip(m, monkeypatch):
    _write_options(m, anthropic_api_key="sk-test", ai_prompt_preview=True)
    calls = _mock_ai_request(m, monkeypatch, result="Ausführliches Fazit.")
    c = m.app.test_client()
    body = {"name": "Strandhotel Sonne", "location": "Palma", "country": "Spanien"}
    r1 = c.post("/api/ai/hotel-summary", headers=ING, json=body)
    d1 = r1.get_json()
    assert "prompt_preview" in d1
    assert calls == []

    body2 = dict(body, _prompt_confirmed=True, _prompt_override="Kurzer eigener Prompt")
    r2 = c.post("/api/ai/hotel-summary", headers=ING, json=body2)
    d2 = r2.get_json()
    assert r2.status_code == 200
    assert d2["summary"] == "Ausführliches Fazit."
    assert len(calls) == 1
    assert calls[0]["prompt"] == "Kurzer eigener Prompt"


# ── Option an: Folgefrage (Konversation, eigener Vorschau-Pfad im Frontend) ─

def test_history_followup_preview_roundtrip(m, monkeypatch):
    aid = _insert_history(m, kind="single", prompt="Ursprünglicher Prompt",
                          summary="Ursprüngliche Antwort")
    _write_options(m, anthropic_api_key="sk-test", ai_prompt_preview=True)
    calls = _mock_ai_request_messages(m, monkeypatch)
    c = m.app.test_client()

    r1 = c.post(f"/api/ai/history/{aid}/followup", headers=ING, json={"question": "Und im Winter?"})
    d1 = r1.get_json()
    assert "prompt_preview" in d1
    assert d1["prompt_preview"] == "Und im Winter?"
    assert calls == []

    r2 = c.post(f"/api/ai/history/{aid}/followup", headers=ING,
               json={"question": "Und im Winter?", "_prompt_confirmed": True,
                     "_prompt_override": "Und speziell im Dezember?"})
    d2 = r2.get_json()
    assert r2.status_code == 200
    assert len(calls) == 1
    assert calls[0]["messages"][-1] == {"role": "user", "content": "Und speziell im Dezember?"}


# ── Option an: Verlauf-Wiederholen (bereits eingefrorener Prompt) ──────────

def test_history_repeat_preview_roundtrip(m, monkeypatch):
    aid = _insert_history(m, kind="single", prompt="Eingefrorener Prompt",
                          summary="Alte Antwort")
    _write_options(m, anthropic_api_key="sk-test", ai_prompt_preview=True)
    calls = _mock_ai_request(m, monkeypatch, result="Neue Antwort.")
    c = m.app.test_client()

    r1 = c.post(f"/api/ai/history/{aid}/repeat", headers=ING, json={"provider": "anthropic"})
    d1 = r1.get_json()
    assert "prompt_preview" in d1
    assert d1["prompt_preview"] == "Eingefrorener Prompt"
    assert calls == []

    r2 = c.post(f"/api/ai/history/{aid}/repeat", headers=ING,
               json={"provider": "anthropic", "_prompt_confirmed": True,
                     "_prompt_override": "Angepasster Wiederholungs-Prompt"})
    d2 = r2.get_json()
    assert r2.status_code == 200
    assert len(calls) == 1
    assert calls[0]["prompt"] == "Angepasster Wiederholungs-Prompt"
    assert d2["summary"] == "Neue Antwort."
