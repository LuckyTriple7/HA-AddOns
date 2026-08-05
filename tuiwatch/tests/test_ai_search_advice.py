"""Tests für den Reisezeit-Check aus der Suchmaske (`POST /api/ai/search-advice`).

Die Suchmaske weiß nichts über Klima, Saison oder Preisniveau — genau dafür ist die
Route da. Geprüft wird vor allem, dass alle Eckdaten der Maske im Prompt landen: was
dort fehlt, kann die KI nicht berücksichtigen, und das fällt in der Antwort nicht auf.
"""
import importlib

import pytest

pytest.importorskip("flask")


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


@pytest.fixture
def client(m, monkeypatch):
    monkeypatch.setattr(m, "_auth_ok", lambda req: True)
    monkeypatch.setattr(m, "load_config", lambda: {"anthropic_api_key": "sk-test",
                                                   "anthropic_model": "claude-haiku-4-5"})
    m.app.config["TESTING"] = True
    return m.app.test_client()


@pytest.fixture
def calls(m, monkeypatch):
    seen = []

    def _fake(api_key, model, prompt, **kw):
        seen.append(dict(kw, prompt=prompt))
        return "Antworttext", {"input_tokens": 10, "output_tokens": 20}, None

    monkeypatch.setattr(m, "_ai_call", _fake)
    return seen


BASE = {"dest": "Mauritius", "start": "2027-01-01", "end": "2027-03-31",
        "duration": 14, "travellers": 1, "airport": "STR",
        "airport_label": "Stuttgart (STR)"}


def test_needs_a_destination(client, calls):
    assert client.post("/api/ai/search-advice", json={}).get_json()["error"] == "no_dest"
    assert not calls


def test_prompt_carries_the_mask(client, calls):
    client.post("/api/ai/search-advice", json=dict(
        BASE, boards=["AI"], min_stars=4, min_recommend=80, direct=True))
    p = calls[-1]["prompt"]
    assert "Mauritius" in p
    assert "2027-01-01 bis 2027-03-31" in p
    assert "14" in p and "Reisende: 1" in p
    assert "Stuttgart (STR)" in p
    assert "All Inclusive" in p          # Code AI wird ausgeschrieben
    assert "4 Sterne" in p and "80 % Weiterempfehlung" in p
    assert "Nur Direktflüge" in p


def test_prompt_asks_for_all_four_topics(client, calls):
    """Regenzeit/Temperaturen, Saison & Schnäppchenmonate, besserer Zeitraum,
    ähnliche Ziele — das war die Anforderung an diesen Check."""
    client.post("/api/ai/search-advice", json=BASE)
    p = calls[-1]["prompt"]
    for topic in ("Regen-/Trockenzeit", "Temperaturen", "Hauptsaison",
                  "Schnäppchenmonate", "Besserer Zeitraum", "Ähnliche Ziele"):
        assert topic in p, topic


def test_price_stats_are_included_when_results_exist(client, calls):
    """Ohne Preisspanne könnte die KI zum Preisniveau nur allgemein raten."""
    client.post("/api/ai/search-advice", json=dict(
        BASE, results={"count": 32, "total": 71, "min_price": 1529,
                       "median_price": 2100, "max_price": 4300}))
    p = calls[-1]["prompt"]
    assert "32 Treffer" in p and "von 71 in der Region" in p
    assert "1.529" in p and "4.300" in p


def test_without_results_no_price_section(client, calls):
    client.post("/api/ai/search-advice", json=BASE)
    assert "Aktuelle Suchtreffer" not in calls[-1]["prompt"]


def test_exact_duration_is_marked_as_such(client, calls):
    client.post("/api/ai/search-advice", json=dict(BASE, exact=True))
    assert "exakt dieser Zeitraum" in calls[-1]["prompt"]


def test_result_lands_in_history_with_dates_in_the_title(client, m, calls):
    client.post("/api/ai/search-advice", json=BASE)
    with m.db() as con:
        row = con.execute("SELECT kind, title FROM ai_analyses ORDER BY id DESC").fetchone()
    assert row["kind"] == "search_advice"
    assert row["title"] == "Mauritius (2027-01-01–2027-03-31)"


def test_history_repeat_knows_the_new_kind():
    ai_routes = importlib.import_module("ai_routes")
    assert ai_routes._AI_RETRY_MARKDOWN_CONFIG["search_advice"]["use_web_search"] is True


def test_requires_auth(m, monkeypatch):
    monkeypatch.setattr(m, "_auth_ok", lambda req: False)
    m.app.config["TESTING"] = True
    r = m.app.test_client().post("/api/ai/search-advice", json=BASE)
    assert r.status_code == 401


def test_without_api_key(m, monkeypatch):
    monkeypatch.setattr(m, "_auth_ok", lambda req: True)
    monkeypatch.setattr(m, "load_config", lambda: {})
    m.app.config["TESTING"] = True
    r = m.app.test_client().post("/api/ai/search-advice", json=BASE)
    assert r.status_code == 400 and r.get_json()["error"] == "no_api_key"
