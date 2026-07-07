"""Tests für den KI-Kalender-Analyse-Button (Preise/Preisänderungen zusammenfassen,
günstige/teure Monate empfehlen). `_ai_request` wird direkt gemockt — kein echter
Anthropic/Gemini-Aufruf nötig. Markdown-Antwort (kein Structured Output), daher ohne
Websuche und ohne Gemini-Sonderfall."""
import importlib
import json
import time

import pytest

pytest.importorskip("flask")

ING = {"X-Ingress-Path": "/test"}

_OUTLOOK_TEXT = ("## Günstige Monate\n- Mai 2027: ca. 500 €\n\n"
                 "## Teure Monate\n- Dezember 2027: ca. 900 €\n\n"
                 "## Empfehlung\nJetzt für Mai buchen.")


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


def _add_offer(m, url, hotel="Test-Hotel", return_date="2027-05-15"):
    now = int(time.time())
    with m.db() as con:
        con.execute(
            "INSERT INTO offers (url, hotel, region, country, return_date, created) "
            "VALUES (?,?,?,?,?,?)", (url, hotel, "Kanaren", "Spanien", return_date, now))
        return con.execute("SELECT id FROM offers WHERE url=?", (url,)).fetchone()["id"]


def _cal(days, **extra):
    out = {"ok": True, "currency": "EUR", "window_start": days[0][0],
           "window_end": days[-1][0], "duration": 7,
           "days": [{"date": d, "price": p} for d, p in days],
           "tracked_date": days[0][0], "tracked_price": days[0][1],
           "cheapest_date": days[0][0], "cheapest_price": days[0][1]}
    out.update(extra)
    return out


def _mock_ai_ok(m, monkeypatch, text=_OUTLOOK_TEXT, calls=None, use_web_search_seen=None):
    calls = calls if calls is not None else []

    def fake(api_key, model, prompt, *, max_tokens, log_ctx, use_web_search=True, output_schema=None):
        calls.append(1)
        if use_web_search_seen is not None:
            use_web_search_seen.append(use_web_search)
        return text, {"input_tokens": 100, "output_tokens": 50,
                      "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}, None

    monkeypatch.setattr(m, "_ai_request", fake)
    monkeypatch.setattr(m, "_run_calendar", lambda *a, **k: None)  # kein Netz
    return calls


# ── _calendar_outlook_facts ───────────────────────────────────────────────────────

def test_calendar_outlook_facts_none_for_missing_offer(m):
    with m.db() as con:
        assert m._calendar_outlook_facts(con, 999) is None


def test_calendar_outlook_facts_none_without_calendar(m):
    oid = _add_offer(m, "https://example.invalid/a?duration=7")
    with m.db() as con:
        assert m._calendar_outlook_facts(con, oid) is None


def test_calendar_outlook_facts_works_with_few_months(m):
    """Anders als _calendar_seasonal_summary: keine Mindestschwelle, auch 1-2 Monate
    liefern schon ein Ergebnis."""
    oid = _add_offer(m, "https://example.invalid/b?duration=7", hotel="Strandhotel Sonne")
    with m.db() as con:
        m._store_calendar_snapshot(con, oid, _cal(
            [("2027-05-01", 500), ("2027-05-02", 520), ("2027-06-01", 700)]))
        facts = m._calendar_outlook_facts(con, oid)
    assert facts["hotel"] == "Strandhotel Sonne"
    assert facts["monthly"] == [("2027-05", 510, 2), ("2027-06", 700, 1)]
    assert facts["moves"] == []   # erster Abruf, keine Bewegung


def test_calendar_outlook_facts_includes_moves(m):
    oid = _add_offer(m, "https://example.invalid/c?duration=7")
    with m.db() as con:
        m._store_calendar_snapshot(con, oid, _cal([("2027-05-01", 500)]))
        m._store_calendar_snapshot(con, oid, _cal([("2027-05-01", 560)]))
        facts = m._calendar_outlook_facts(con, oid)
    assert len(facts["moves"]) == 1
    assert facts["moves"][0]["date"] == "2027-05-01"
    assert facts["moves"][0]["delta"] == 60


# ── Prompt-Inhalt ──────────────────────────────────────────────────────────────────

def test_calendar_outlook_prompt_contains_hotel_and_months():
    import app as m
    facts = {"hotel": "Riu Funana", "duration": 7, "tracked_date": "2027-05-03",
             "tracked_price": 515, "cheapest_date": "2027-05-01", "cheapest_price": 500,
             "monthly": [("2027-05", 510, 2), ("2027-06", 700, 1)], "moves": []}
    p = m._calendar_outlook_prompt(facts)
    assert "Riu Funana" in p
    assert "Mai 2027" in p and "Juni 2027" in p
    assert "keine Preisänderungen" in p


def test_calendar_outlook_prompt_lists_moves():
    import app as m
    facts = {"hotel": "Riu Funana", "duration": 7, "tracked_date": None,
             "tracked_price": None, "cheapest_date": None, "cheapest_price": None,
             "monthly": [("2027-05", 510, 2)],
             "moves": [{"date": "2027-05-01", "price": 560, "prev_price": 500,
                        "delta": 60, "ts": 1}]}
    p = m._calendar_outlook_prompt(facts)
    assert "500" in p and "560" in p and "gestiegen" in p


# ── Route ────────────────────────────────────────────────────────────────────────

def test_calendar_outlook_requires_api_key(m):
    oid = _add_offer(m, "https://example.invalid/d?duration=7")
    c = m.app.test_client()
    r = c.post(f"/api/ai/calendar-outlook/{oid}", headers=ING)
    assert r.status_code == 400 and r.get_json()["error"] == "no_api_key"


def test_calendar_outlook_not_found(m):
    _write_options(m, anthropic_api_key="k")
    c = m.app.test_client()
    r = c.post("/api/ai/calendar-outlook/999999", headers=ING)
    assert r.status_code == 404


def test_calendar_outlook_no_data_without_calendar(m, monkeypatch):
    _write_options(m, anthropic_api_key="k")
    oid = _add_offer(m, "https://example.invalid/e?duration=7")
    monkeypatch.setattr(m, "_run_calendar", lambda *a, **k: None)   # kein Netz
    c = m.app.test_client()
    r = c.post(f"/api/ai/calendar-outlook/{oid}", headers=ING)
    assert r.status_code == 400 and r.get_json()["error"] == "no_data"


def test_calendar_outlook_success_caches_and_saves_history(m, monkeypatch):
    _write_options(m, anthropic_api_key="k")
    oid = _add_offer(m, "https://example.invalid/f?duration=7")
    with m.db() as con:
        m._store_calendar_snapshot(con, oid, _cal([("2027-05-01", 500), ("2027-06-01", 700)]))
    calls = _mock_ai_ok(m, monkeypatch)
    c = m.app.test_client()

    r1 = c.post(f"/api/ai/calendar-outlook/{oid}", headers=ING)
    assert r1.status_code == 200
    d1 = r1.get_json()
    assert d1["summary"] == _OUTLOOK_TEXT and d1["cached"] is False
    assert len(calls) == 1

    r2 = c.post(f"/api/ai/calendar-outlook/{oid}", headers=ING)
    assert r2.status_code == 200 and r2.get_json()["cached"] is True
    assert len(calls) == 1   # kein zweiter KI-Aufruf

    with m.db() as con:
        row = con.execute(
            "SELECT kind, summary FROM ai_analyses WHERE kind='calendar_outlook'").fetchone()
    assert row is not None and row["summary"] == _OUTLOOK_TEXT


def test_calendar_outlook_uses_no_web_search(m, monkeypatch):
    """Markdown-Ergebnis aus rein lokalen Daten -- keine Websuche noetig, das umgeht
    zugleich die Gemini-Einschraenkung (Structured Output + Websuche kombiniert)."""
    _write_options(m, anthropic_api_key="k")
    oid = _add_offer(m, "https://example.invalid/g?duration=7")
    with m.db() as con:
        m._store_calendar_snapshot(con, oid, _cal([("2027-05-01", 500)]))
    seen = []
    _mock_ai_ok(m, monkeypatch, use_web_search_seen=seen)
    c = m.app.test_client()
    r = c.post(f"/api/ai/calendar-outlook/{oid}", headers=ING)
    assert r.status_code == 200
    assert seen == [False]


def test_existing_ai_call_sites_still_use_web_search_by_default(m, monkeypatch):
    """Regression: _ai_call() default fuer use_web_search muss True bleiben, damit
    Hotel-Fazit/Frage/TripPilot/Vergleich weiter mit Websuche laufen."""
    seen = []

    def fake(api_key, model, prompt, *, max_tokens, log_ctx, use_web_search=True, output_schema=None):
        seen.append(use_web_search)
        return "Text", {"input_tokens": 1, "output_tokens": 1,
                        "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}, None

    monkeypatch.setattr(m, "_ai_request", fake)
    text, usage, err = m._ai_call("k", "claude-opus-4-8", "prompt", max_tokens=10, log_ctx="x")
    assert err is None
    assert seen == [True]
