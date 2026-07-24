"""Tests für den KI-Buchungsscore (pro Angebot + pro Destination): Fakten-Sammlung,
Prompt-Inhalt, Routen (Cache, Fehlerfälle, KI-Verlauf-Persistenz). `_ai_request` wird
direkt gemockt — kein echter Anthropic/Gemini-Aufruf nötig."""
import importlib
import json
import time

import pytest

pytest.importorskip("flask")

ING = {"X-Ingress-Path": "/test"}

_SCORE_RESULT = {
    "score": 72, "empfehlung": "beobachten", "vertrauen": 60,
    "erwartung_7_tage": "gleich", "erwartung_30_tage": "steigend",
    "begruendung": [{"text": "Preis nahe historischem Tief", "typ": "daten"},
                     {"text": "Nebensaison endet bald", "typ": "annahme"}],
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


def _mock_ai_ok(m, monkeypatch, result=None, calls=None):
    calls = calls if calls is not None else []
    def fake(*a, **k):
        calls.append(1)
        return json.dumps(result or _SCORE_RESULT), {"input_tokens": 100, "output_tokens": 50,
                                                       "cache_creation_input_tokens": 0,
                                                       "cache_read_input_tokens": 0}, None
    monkeypatch.setattr(m, "_ai_request", fake)
    monkeypatch.setattr(m, "_run_calendar", lambda *a, **k: None)  # kein Netz
    return calls


def _add_offer(m, url, price=1000, region="Kanaren", country="Spanien",
               return_date="2027-03-15", with_price=True):
    now = int(time.time())
    with m.db() as con:
        con.execute(
            "INSERT INTO offers (url, hotel, region, country, return_date, created) "
            "VALUES (?,?,?,?,?,?)", (url, "Test-Hotel", region, country, return_date, now))
        oid = con.execute("SELECT id FROM offers WHERE url=?", (url,)).fetchone()["id"]
        if with_price:
            con.execute("INSERT INTO price_history (offer_id, ts, price, ok) VALUES (?,?,?,1)",
                        (oid, now, price))
    return oid


def _seed_moves(m, region, pct_values, days_ago_start=13):
    now = int(time.time())
    with m.db() as con:
        for i, pct in enumerate(pct_values):
            ts = now - (days_ago_start - i) * 86400
            con.execute(
                "INSERT INTO price_moves (ts, region, country, months_out, pct_change) "
                "VALUES (?,?,?,?,?)", (ts, region, "Spanien", 5, pct))


# ── _offer_booking_facts ────────────────────────────────────────────────────────

def test_offer_booking_facts_none_for_missing_offer(m):
    with m.db() as con:
        assert m._offer_booking_facts(con, 999) is None


def test_offer_booking_facts_none_without_price(m):
    oid = _add_offer(m, "https://example.invalid/nb?duration=7", with_price=False)
    with m.db() as con:
        assert m._offer_booking_facts(con, oid) is None


def test_offer_booking_facts_includes_region_trend(m):
    oid = _add_offer(m, "https://example.invalid/a?duration=7", price=1500)
    _seed_moves(m, "Kanaren", [1.0] * 8)
    with m.db() as con:
        facts = m._offer_booking_facts(con, oid)
    assert facts["price"] == 1500
    assert facts["region"] == "Kanaren"
    assert facts["region_trend"]["dir"] == "up"
    assert facts["seasonal"] is None   # kein Kalender abgerufen


def test_offer_booking_facts_computes_departure_from_today(m):
    """Regression: die KI verschätzte sich live um Jahre bei der Vorlaufzeit, weil
    weder das heutige Datum noch eine vorgerechnete Vorlaufzeit im Prompt standen.
    Muss jetzt selbst (nicht von der KI) berechnet werden: Abreise = Rückreise minus
    Reisedauer (aus dem `duration=`-URL-Parameter), Tage bis Abreise ab heute."""
    import datetime
    oid = _add_offer(m, "https://example.invalid/dep?duration=7",
                      return_date="2027-03-15")
    with m.db() as con:
        facts = m._offer_booking_facts(con, oid)
    expected_departure = datetime.date(2027, 3, 15) - datetime.timedelta(days=7)
    expected_days = (expected_departure - datetime.date.today()).days
    assert facts["departure_date"] == expected_departure.isoformat()
    assert facts["departure_days"] == expected_days


def test_booking_score_prompt_includes_todays_date_and_departure(m):
    oid = _add_offer(m, "https://example.invalid/dep2?duration=7",
                      return_date="2027-03-15")
    with m.db() as con:
        facts = m._offer_booking_facts(con, oid)
    p = m._booking_score_prompt(facts)
    import datetime
    assert f"Heutiges Datum: {datetime.date.today().isoformat()}" in p
    assert "Geschätztes Abreisedatum: 2027-03-08" in p
    assert "Tage bzw. rund" in p


def test_offer_booking_facts_includes_seasonal_when_calendar_cached(m):
    oid = _add_offer(m, "https://example.invalid/b?duration=7", price=1200)
    days = []
    for month, price in (("2027-05", 900), ("2027-12", 1600), ("2027-09", 1200)):
        for d in range(1, 21):
            days.append({"date": f"{month}-{d:02d}", "price": price})
    cal = {"ok": True, "days": days, "cheapest_date": "2027-05-05", "cheapest_price": 900,
           "tracked_date": "2027-12-10", "tracked_price": 1600}
    with m.db() as con:
        con.execute("INSERT INTO calendar_cache (offer_id, ts, data) VALUES (?,?,?)",
                    (oid, int(time.time()), json.dumps(cal)))
        facts = m._offer_booking_facts(con, oid)
    assert facts["seasonal"]["cheapest_month"] == "2027-05"
    assert facts["seasonal"]["priciest_month"] == "2027-12"
    assert facts["seasonal"]["cheapest_month_avg"] == 900


def test_offer_booking_facts_seasonal_includes_full_monthly_breakdown(m):
    """Regression: KI wertete zwei nicht-extreme Monate falsch aus (z. B. Sept. 2026
    vs. Feb. 2027 200 € auseinander), weil `seasonal` bisher nur die beiden Extreme
    (günstigster/teuerster Monat) enthielt — Monate dazwischen waren im Prompt gar
    nicht mit Ø-Preis sichtbar."""
    oid = _add_offer(m, "https://example.invalid/mb?duration=7", price=1200)
    days = []
    for month, price in (("2027-05", 900), ("2027-12", 1600), ("2027-09", 1200)):
        for d in range(1, 21):
            days.append({"date": f"{month}-{d:02d}", "price": price})
    cal = {"ok": True, "days": days, "cheapest_date": "2027-05-05", "cheapest_price": 900,
           "tracked_date": "2027-09-10", "tracked_price": 1200}
    with m.db() as con:
        con.execute("INSERT INTO calendar_cache (offer_id, ts, data) VALUES (?,?,?)",
                    (oid, int(time.time()), json.dumps(cal)))
        facts = m._offer_booking_facts(con, oid)
    assert facts["seasonal"]["monthly"] == [("2027-05", 900, 20), ("2027-09", 1200, 20),
                                             ("2027-12", 1600, 20)]
    prompt = m._booking_score_prompt(facts)
    assert "Monatsdurchschnittspreise im Kalender" in prompt
    assert "September 2027: Ø 1200 € (20 Termine)" in prompt
    assert "Mai 2027: Ø 900 € (20 Termine)" in prompt
    assert "Dezember 2027: Ø 1600 € (20 Termine)" in prompt


def test_offer_booking_facts_seasonal_monthly_includes_sparse_months(m):
    """Regression: bei wöchentlichem statt täglichem Flugrhythmus (z. B. nur
    Sonntagsflüge) hat mancher Monat nur 1-2 Termine — die >= 3-Schwelle für
    Günstigster/Teuerster-Monat darf solche Monate nicht komplett aus der vollen
    Monatsliste tilgen, sonst fehlt z. B. der Zielmonat des Nutzers ganz im Prompt."""
    oid = _add_offer(m, "https://example.invalid/sparse?duration=7", price=1200)
    days = []
    for month, price in (("2027-05", 900), ("2027-12", 1600), ("2027-09", 1200)):
        for d in range(1, 21):
            days.append({"date": f"{month}-{d:02d}", "price": price})
    # Nov. 2027: nur 2 Termine (z. B. wöchentlicher Flugrhythmus) -> unter der
    # >= 3-Schwelle für Extremwerte, muss aber trotzdem in der vollen Liste stehen.
    days.append({"date": "2027-11-07", "price": 1686})
    days.append({"date": "2027-11-21", "price": 1686})
    cal = {"ok": True, "days": days, "cheapest_date": "2027-05-05", "cheapest_price": 900,
           "tracked_date": "2027-09-10", "tracked_price": 1200}
    with m.db() as con:
        con.execute("INSERT INTO calendar_cache (offer_id, ts, data) VALUES (?,?,?)",
                    (oid, int(time.time()), json.dumps(cal)))
        facts = m._offer_booking_facts(con, oid)
    monthly = dict((mo, (avg, n)) for mo, avg, n in facts["seasonal"]["monthly"])
    assert monthly["2027-11"] == (1686, 2)
    prompt = m._booking_score_prompt(facts)
    assert "November 2027: Ø 1686 € (2 Termine)" in prompt


def test_offer_booking_facts_includes_prior_year_month_comparison(m):
    """Regression: bei langer Vorlaufzeit (z. B. Zieltermin Sept. 2027) deckt der
    Kalender ab heute bis weit über den Zieltermin hinaus ab (fetch_calendar) — der
    gleiche Reisemonat ein Jahr früher (Sept. 2026) liegt dann oft schon mit im
    Fenster und damit näher am eigenen Abflug. Dieser Vorjahresvergleich wurde bisher
    für den Buchungsscore nicht ausgewertet."""
    oid = _add_offer(m, "https://example.invalid/yoy?duration=7", price=1900)
    days = []
    for month, price in (("2026-09", 1500), ("2027-01", 1000), ("2027-05", 900),
                          ("2027-09", 1900)):
        for d in range(1, 21):
            days.append({"date": f"{month}-{d:02d}", "price": price})
    cal = {"ok": True, "days": days, "cheapest_date": "2027-05-05", "cheapest_price": 900,
           "tracked_date": "2027-09-10", "tracked_price": 1900}
    with m.db() as con:
        con.execute("INSERT INTO calendar_cache (offer_id, ts, data) VALUES (?,?,?)",
                    (oid, int(time.time()), json.dumps(cal)))
        facts = m._offer_booking_facts(con, oid)
    s = facts["seasonal"]
    assert s["target_month"] == "2027-09"
    assert s["target_month_avg"] == 1900
    assert s["prior_year_month"] == "2026-09"
    assert s["prior_year_month_avg"] == 1500
    prompt = m._booking_score_prompt(facts)
    assert "Vorjahresvergleich" in prompt
    assert "September 2026" in prompt
    assert "1500" in prompt or "1.500" in prompt


def test_offer_booking_facts_includes_calendar_moves(m):
    """Kalender-Bewegungen (calendar_history) gehören in die Buchungsscore-Fakten —
    breite Anstiege/Rückgänge über viele Reisetermine sind ein direktes
    'jetzt buchen oder warten?'-Signal (wie bei der KI-Kalenderanalyse)."""
    oid = _add_offer(m, "https://example.invalid/cm?duration=7", price=1200)
    cal1 = {"ok": True, "days": [{"date": "2027-05-01", "price": 1999},
                                  {"date": "2027-05-02", "price": 1800}]}
    cal2 = {"ok": True, "days": [{"date": "2027-05-01", "price": 2026},
                                  {"date": "2027-05-02", "price": 1800}]}
    with m.db() as con:
        m._store_calendar_snapshot(con, oid, cal1)
        m._store_calendar_snapshot(con, oid, cal2)
        facts = m._offer_booking_facts(con, oid)
    assert len(facts["calendar_moves"]) == 1
    assert facts["calendar_moves"][0]["date"] == "2027-05-01"
    assert facts["calendar_moves"][0]["delta"] == 27


def test_booking_score_prompt_includes_calendar_moves():
    facts = {"hotel": "Riu Funana", "details": "", "region": "", "country": "",
             "stars": None, "rating": None, "rating_count": None,
             "recommendation": None, "return_date": "",
             "target_price": None, "booked_price": None, "price": 1849,
             "min_price": None, "max_price": None, "samples": 1,
             "own_trend": None, "region_trend": None, "region_index": None,
             "seasonal": None,
             "calendar_moves": [
                 {"date": "2027-05-01", "price": 2026, "prev_price": 1999,
                  "delta": 27, "ts": 0},
                 {"date": "2027-06-14", "price": 1971, "prev_price": 1990,
                  "delta": -19, "ts": 0}]}
    import app as m
    p = m._booking_score_prompt(facts)
    assert "Größte Preisbewegungen im Preiskalender" in p
    assert "1 von 2 gestiegen" in p
    assert "Abreise 2027-05-01: 1999 € -> 2026 € (gestiegen um 27 €)" in p
    assert "Abreise 2027-06-14: 1990 € -> 1971 € (gefallen um 19 €)" in p


def test_booking_score_history_grows_and_reports_delta(m, monkeypatch):
    """Score-Verlauf: jeder frische Score landet per offer_id in ai_analyses;
    die Route liefert `history` (älteste zuerst) — Basis für Delta + Sparkline."""
    oid = _add_offer(m, "https://example.invalid/hist?duration=7", price=1500)
    _write_options(m, anthropic_api_key="sk-test")
    c = m.app.test_client()

    _mock_ai_ok(m, monkeypatch, result=dict(_SCORE_RESULT, score=72))
    r1 = c.post(f"/api/ai/booking-score/{oid}", headers=ING).get_json()
    assert [h["score"] for h in r1["history"]] == [72]

    with m._ai_cache_lock:
        m._booking_score_cache.pop(oid, None)   # 24h-Cache umgehen -> zweite Messung
    _mock_ai_ok(m, monkeypatch, result=dict(_SCORE_RESULT, score=65))
    r2 = c.post(f"/api/ai/booking-score/{oid}", headers=ING).get_json()
    assert [h["score"] for h in r2["history"]] == [72, 65]
    assert r2["history"][-1]["empfehlung"] == "beobachten"

    # Cache-Antwort enthält den Verlauf ebenfalls
    r3 = c.post(f"/api/ai/booking-score/{oid}", headers=ING).get_json()
    assert r3["cached"] is True
    assert [h["score"] for h in r3["history"]] == [72, 65]


def test_booking_score_invalid_json_returns_ai_empty_and_logs(m, monkeypatch, caplog):
    """Abgeschnittenes Structured-Output-JSON (z. B. stop_reason=max_tokens) darf
    nicht still scheitern: 502 ai_empty + WARNING mit Text-Ausschnitt im Log."""
    import logging
    oid = _add_offer(m, "https://example.invalid/tj?duration=7", price=1500)
    _write_options(m, anthropic_api_key="sk-test")
    monkeypatch.setattr(m, "_run_calendar", lambda *a, **k: None)
    monkeypatch.setattr(m, "_ai_request", lambda *a, **k: (
        '{"score": 72, "empfehlung": "beob', {"input_tokens": 1, "output_tokens": 1,
        "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}, None))
    c = m.app.test_client()
    with caplog.at_level(logging.WARNING):
        r = c.post(f"/api/ai/booking-score/{oid}", headers=ING)
    assert r.status_code == 502
    assert r.get_json()["error"] == "ai_empty"
    assert any("kein gültiges JSON" in rec.message for rec in caplog.records)


# ── Prompt-Inhalt ────────────────────────────────────────────────────────────────

def test_booking_score_prompt_contains_facts():
    facts = {"hotel": "Riu Funana", "details": "7 Nächte", "region": "Kap Verde",
             "country": "", "stars": 4, "rating": None, "rating_count": None,
             "recommendation": None, "return_date": "2027-01-09",
             "target_price": None, "booked_price": None, "price": 1849,
             "min_price": 1789, "max_price": 2369, "samples": 10,
             "own_trend": {"dir": "up", "pct": 3.2},
             "region_trend": {"dir": "flat", "pct": 0.5, "n": 12},
             "region_index": {"index": 105.0, "pct": 5.0, "n": 40},
             "seasonal": None}
    import app as m
    p = m._booking_score_prompt(facts)
    assert "Riu Funana" in p and "1849" in p and "Kap Verde" in p
    assert "1789" in p and "2369" in p
    assert "typ='daten'" in p and "typ='annahme'" in p


def test_region_outlook_prompt_contains_region_and_trend():
    import app as m
    p = m._region_outlook_prompt("Balearen", {"dir": "down", "pct": -4.2, "n": 20}, None)
    assert "Balearen" in p and "-4.2" in p


# ── Routen ───────────────────────────────────────────────────────────────────────

def test_booking_score_requires_api_key(m):
    oid = _add_offer(m, "https://example.invalid/c?duration=7")
    c = m.app.test_client()
    r = c.post(f"/api/ai/booking-score/{oid}", headers=ING)
    assert r.status_code == 400 and r.get_json()["error"] == "no_api_key"


def test_booking_score_no_price_yet(m):
    _write_options(m, anthropic_api_key="k")
    oid = _add_offer(m, "https://example.invalid/d?duration=7", with_price=False)
    c = m.app.test_client()
    r = c.post(f"/api/ai/booking-score/{oid}", headers=ING)
    assert r.status_code == 400 and r.get_json()["error"] == "no_price"


def test_booking_score_success_caches_and_saves_history(m, monkeypatch):
    _write_options(m, anthropic_api_key="k")
    oid = _add_offer(m, "https://example.invalid/e?duration=7", price=1500)
    calls = _mock_ai_ok(m, monkeypatch)
    c = m.app.test_client()

    r1 = c.post(f"/api/ai/booking-score/{oid}", headers=ING)
    assert r1.status_code == 200
    d1 = r1.get_json()
    assert d1["result"]["score"] == 72 and d1["cached"] is False
    assert len(calls) == 1

    r2 = c.post(f"/api/ai/booking-score/{oid}", headers=ING)
    assert r2.status_code == 200 and r2.get_json()["cached"] is True
    assert len(calls) == 1   # kein zweiter KI-Aufruf

    with m.db() as con:
        row = con.execute("SELECT kind, summary FROM ai_analyses WHERE kind='booking_score'").fetchone()
    assert row is not None
    assert json.loads(row["summary"])["score"] == 72


def test_booking_score_refreshes_missing_calendar(m, monkeypatch):
    """Fehlt der Preiskalender komplett, wird er vor dem Score einmalig aufgefrischt."""
    _write_options(m, anthropic_api_key="k")
    oid = _add_offer(m, "https://example.invalid/cal1?duration=7", price=1500)
    _mock_ai_ok(m, monkeypatch)
    calendar_calls = []
    monkeypatch.setattr(m, "_run_calendar", lambda oid_: calendar_calls.append(oid_))
    c = m.app.test_client()
    r = c.post(f"/api/ai/booking-score/{oid}", headers=ING)
    assert r.status_code == 200
    assert calendar_calls == [oid]


def test_booking_score_skips_refresh_when_calendar_fresh(m, monkeypatch):
    """Ist der Kalender noch frisch (< 7 Tage alt), wird er NICHT erneut abgerufen."""
    _write_options(m, anthropic_api_key="k")
    oid = _add_offer(m, "https://example.invalid/cal2?duration=7", price=1500)
    with m.db() as con:
        con.execute("INSERT INTO calendar_cache (offer_id, ts, data) VALUES (?,?,?)",
                    (oid, int(time.time()) - 3600, json.dumps({"ok": True, "days": []})))
    _mock_ai_ok(m, monkeypatch)
    calendar_calls = []
    monkeypatch.setattr(m, "_run_calendar", lambda oid_: calendar_calls.append(oid_))
    c = m.app.test_client()
    r = c.post(f"/api/ai/booking-score/{oid}", headers=ING)
    assert r.status_code == 200
    assert calendar_calls == []


def test_booking_score_refreshes_stale_calendar(m, monkeypatch):
    """Kalender ist da, aber älter als 7 Tage -> wird trotzdem aufgefrischt."""
    _write_options(m, anthropic_api_key="k")
    oid = _add_offer(m, "https://example.invalid/cal3?duration=7", price=1500)
    with m.db() as con:
        con.execute("INSERT INTO calendar_cache (offer_id, ts, data) VALUES (?,?,?)",
                    (oid, int(time.time()) - 8 * 86400, json.dumps({"ok": True, "days": []})))
    _mock_ai_ok(m, monkeypatch)
    calendar_calls = []
    monkeypatch.setattr(m, "_run_calendar", lambda oid_: calendar_calls.append(oid_))
    c = m.app.test_client()
    r = c.post(f"/api/ai/booking-score/{oid}", headers=ING)
    assert r.status_code == 200
    assert calendar_calls == [oid]


def test_booking_score_no_price_skips_calendar_refresh(m, monkeypatch):
    """Ohne Preis lohnt sich kein Kalender-Abruf -> darf gar nicht erst versucht werden."""
    _write_options(m, anthropic_api_key="k")
    oid = _add_offer(m, "https://example.invalid/cal4?duration=7", with_price=False)
    calendar_calls = []
    monkeypatch.setattr(m, "_run_calendar", lambda oid_: calendar_calls.append(oid_))
    c = m.app.test_client()
    r = c.post(f"/api/ai/booking-score/{oid}", headers=ING)
    assert r.status_code == 400 and r.get_json()["error"] == "no_price"
    assert calendar_calls == []


def test_region_outlook_requires_region(m):
    _write_options(m, anthropic_api_key="k")
    c = m.app.test_client()
    r = c.post("/api/ai/region-outlook", headers=ING, json={})
    assert r.status_code == 400 and r.get_json()["error"] == "invalid"


def test_region_outlook_no_data(m):
    _write_options(m, anthropic_api_key="k")
    c = m.app.test_client()
    r = c.post("/api/ai/region-outlook", headers=ING, json={"region": "Unbekannt"})
    assert r.status_code == 400 and r.get_json()["error"] == "no_data"


def test_region_outlook_success_caches_and_saves_history(m, monkeypatch):
    _write_options(m, anthropic_api_key="k")
    _seed_moves(m, "Balearen", [-1.0] * 8)
    calls = _mock_ai_ok(m, monkeypatch)
    c = m.app.test_client()

    r1 = c.post("/api/ai/region-outlook", headers=ING, json={"region": "Balearen"})
    assert r1.status_code == 200 and r1.get_json()["cached"] is False
    assert len(calls) == 1

    r2 = c.post("/api/ai/region-outlook", headers=ING, json={"region": "Balearen"})
    assert r2.status_code == 200 and r2.get_json()["cached"] is True
    assert len(calls) == 1

    with m.db() as con:
        row = con.execute("SELECT kind, title FROM ai_analyses WHERE kind='region_outlook'").fetchone()
    assert row is not None and row["title"] == "Balearen"
