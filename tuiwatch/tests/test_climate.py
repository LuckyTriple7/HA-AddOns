"""Tests für die Klimatabelle je Reiseziel.

Kernpunkt: die Tabelle wird EINMAL je Ziel von der KI erzeugt und dauerhaft
gespeichert (Klima-Normalwerte ändern sich nicht). Jeder weitere Abruf muss ohne
KI-Aufruf auskommen — sonst würde die Suchmaske bei jedem Suchlauf Geld verbrennen.
"""
import importlib
import json

import pytest

pytest.importorskip("flask")

CLIMATE = {
    "months": [{"monat": i, "temp_tag": 20 + i, "temp_nacht": 12 + i, "wasser": 18 + i,
                "sonnenstunden": 6, "regentage": 3, "hinweis": ""} for i in range(1, 13)],
    "beste_monate": [4, 5, 10],
    "zusammenfassung": "Ganzjährig mild.",
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


@pytest.fixture
def client(m, monkeypatch):
    monkeypatch.setattr(m, "_auth_ok", lambda req: True)
    monkeypatch.setattr(m, "load_config", lambda: {"anthropic_api_key": "sk-test",
                                                   "anthropic_model": "claude-haiku-4-5"})
    m.app.config["TESTING"] = True
    return m.app.test_client()


@pytest.fixture
def ai(m, monkeypatch):
    """`_ai_request` abfangen — zählt die Aufrufe und liefert das Schema-JSON."""
    calls = []

    def _fake(api_key, model, prompt, **kw):
        calls.append(dict(kw, prompt=prompt))
        return json.dumps(CLIMATE), {"input_tokens": 10, "output_tokens": 20}, None

    monkeypatch.setattr(m, "_ai_request", _fake)
    return calls


def test_get_without_stored_table_costs_nothing(client, ai):
    """Die Suchmaske fragt hier bei jedem Suchlauf an — der GET darf nie die KI rufen."""
    d = client.get("/api/climate/128").get_json()
    assert d == {"found": False, "giata": 128}
    assert not ai


def test_first_post_generates_and_stores(client, m, ai):
    d = client.post("/api/ai/climate", json={"giata": 128, "label": "Gran Canaria"}).get_json()
    assert d["found"] is True and d["cached"] is False
    assert len(d["data"]["months"]) == 12
    assert len(ai) == 1 and ai[0]["use_web_search"] is True
    with m.db() as con:
        row = con.execute("SELECT label FROM climate WHERE giata=128").fetchone()
    assert row["label"] == "Gran Canaria"


def test_second_post_uses_the_stored_table(client, ai):
    client.post("/api/ai/climate", json={"giata": 128, "label": "Gran Canaria"})
    d = client.post("/api/ai/climate", json={"giata": 128, "label": "Gran Canaria"}).get_json()
    assert d["cached"] is True
    assert len(ai) == 1          # kein zweiter KI-Aufruf


def test_refresh_forces_a_new_call(client, ai):
    client.post("/api/ai/climate", json={"giata": 128, "label": "Gran Canaria"})
    d = client.post("/api/ai/climate",
                    json={"giata": 128, "label": "Gran Canaria", "refresh": True}).get_json()
    assert d["cached"] is False and len(ai) == 2


def test_get_after_generation_is_served_from_db(client, ai):
    client.post("/api/ai/climate", json={"giata": 128, "label": "Gran Canaria"})
    d = client.get("/api/climate/128").get_json()
    assert d["found"] is True and d["label"] == "Gran Canaria"
    assert len(d["data"]["months"]) == 12
    assert len(ai) == 1


def test_incomplete_answer_is_rejected(client, m, monkeypatch):
    """Eine Tabelle mit Lücken wäre in der UI schlechter als gar keine — und sie
    dürfte sich nicht dauerhaft festsetzen."""
    monkeypatch.setattr(m, "_ai_request", lambda *a, **k: (
        json.dumps({"months": CLIMATE["months"][:5], "beste_monate": [], "zusammenfassung": ""}),
        {"input_tokens": 1, "output_tokens": 1}, None))
    r = client.post("/api/ai/climate", json={"giata": 99, "label": "X"})
    assert r.status_code == 502 and r.get_json()["error"] == "ai_empty"
    with m.db() as con:
        assert con.execute("SELECT 1 FROM climate WHERE giata=99").fetchone() is None


def test_list_is_empty_at_first(client, ai):
    assert client.get("/api/climate").get_json() == {"items": []}
    assert not ai


def test_list_shows_stored_destinations(client, ai):
    """Zugriff von der Hauptseite: dort gibt es keinen Ziel-Picker, also braucht es
    die Liste der bereits gespeicherten Tabellen."""
    client.post("/api/ai/climate", json={"giata": 128, "label": "Gran Canaria"})
    client.post("/api/ai/climate", json={"giata": 127, "label": "Fuerteventura"})
    items = client.get("/api/climate").get_json()["items"]
    assert [i["label"] for i in items] == ["Fuerteventura", "Gran Canaria"]   # alphabetisch
    assert all("ts" in i and "giata" in i for i in items)
    # Die Monatsdaten gehören nicht in die Liste — die wäre sonst unnötig groß.
    assert all("data" not in i for i in items)


def test_delete_removes_it(client, ai):
    client.post("/api/ai/climate", json={"giata": 128, "label": "Gran Canaria"})
    assert client.delete("/api/climate/128").get_json()["deleted"] == 1
    assert client.get("/api/climate/128").get_json()["found"] is False


def test_post_without_label_and_without_stored_table(client, ai):
    assert client.post("/api/ai/climate", json={"giata": 1}).get_json()["error"] == "no_dest"
    assert not ai


def test_prompt_asks_for_twelve_months_and_water(client, ai):
    client.post("/api/ai/climate", json={"giata": 128, "label": "Gran Canaria"})
    p = ai[0]["prompt"]
    assert "zwölf Monate" in p and "Wassertemperatur" in p
    assert "Sonnenstunden" in p and "Regentage" in p
    assert "Klima-Normalwerte" in p        # keine Wettervorhersage
    assert "Gran Canaria" in p


# ── Prompt-Vorschau ───────────────────────────────────────────────────────────
# Die Option `ai_prompt_preview` lässt Routen statt der Daten erst den fertigen
# Prompt zurückgeben. Live führte das zu einem stillen Totalausfall: das Frontend
# rief die Route mit nacktem fetch auf, bekam HTTP 200 mit {prompt_preview:…} und
# zeigte eine leere Tabelle — ohne Fehler, ohne Log-Eintrag, weil gar kein
# KI-Aufruf stattfand.

@pytest.fixture
def preview(m, monkeypatch):
    monkeypatch.setattr(m, "load_config", lambda: {
        "anthropic_api_key": "sk-test", "anthropic_model": "claude-haiku-4-5",
        "ai_prompt_preview": True})


def test_preview_returns_the_prompt_instead_of_data(client, preview, ai):
    d = client.post("/api/ai/climate", json={"giata": 128, "label": "Gran Canaria"}).get_json()
    assert "prompt_preview" in d and "data" not in d
    assert not ai          # kein KI-Aufruf vor der Bestätigung


def test_confirmed_prompt_runs_through(client, preview, ai):
    d = client.post("/api/ai/climate", json={"giata": 128, "label": "Gran Canaria",
                                             "_prompt_confirmed": True}).get_json()
    assert d["found"] is True and len(d["data"]["months"]) == 12
    assert len(ai) == 1


def test_stored_table_is_served_even_with_preview_on(client, preview, ai):
    """Erst speichern, dann bei aktiver Vorschau erneut anfragen: die gespeicherte
    Tabelle kommt direkt zurück — eine Vorschau für einen Aufruf, der gar nicht
    stattfindet, wäre sinnlos."""
    client.post("/api/ai/climate", json={"giata": 128, "label": "Gran Canaria",
                                         "_prompt_confirmed": True})
    d = client.post("/api/ai/climate", json={"giata": 128, "label": "Gran Canaria"}).get_json()
    assert d["cached"] is True and "prompt_preview" not in d


# ── E-Mail ────────────────────────────────────────────────────────────────────

def test_email_sends_the_stored_table(client, m, ai, monkeypatch):
    client.post("/api/ai/climate", json={"giata": 128, "label": "Gran Canaria"})
    monkeypatch.setattr(m, "smtp_configured", lambda: True)
    sent = []
    monkeypatch.setattr(m, "send_email", lambda s, h, t: sent.append((s, h, t)))
    r = client.post("/api/climate/128/email", json={"to": "a@b.de", "months": [4]})
    assert r.status_code == 200 and r.get_json()["sent"] is True
    subject, html, to = sent[0]
    assert to == "a@b.de" and "Gran Canaria" in subject
    assert "Januar" in html and "Dezember" in html
    assert "Ganzjährig mild." in html
    assert len(ai) == 1          # Versand kostet keinen KI-Aufruf


def test_email_without_stored_table_is_404(client, m, monkeypatch):
    monkeypatch.setattr(m, "smtp_configured", lambda: True)
    monkeypatch.setattr(m, "send_email", lambda s, h, t: None)
    r = client.post("/api/climate/777/email", json={"to": "a@b.de"})
    assert r.status_code == 404


def test_email_needs_smtp(client, m, ai, monkeypatch):
    client.post("/api/ai/climate", json={"giata": 128, "label": "Gran Canaria"})
    monkeypatch.setattr(m, "smtp_configured", lambda: False)
    r = client.post("/api/climate/128/email", json={"to": "a@b.de"})
    assert r.status_code == 400 and r.get_json()["error"] == "smtp_not_configured"


def test_climate_html_marks_best_and_selected_months():
    email_search = importlib.import_module("email_search")
    html = email_search.climate_html("Gran Canaria", CLIMATE, months_hl=[5])
    assert "★" in html                       # beste Monate markiert
    assert "dein Reisezeitraum" in html      # Hervorhebung erklärt
    assert "<script>" not in html


def test_climate_html_escapes_the_label():
    email_search = importlib.import_module("email_search")
    html = email_search.climate_html("<script>x</script>", CLIMATE)
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_requires_auth(m):
    m.app.config["TESTING"] = True
    c = m.app.test_client()
    assert c.get("/api/climate/128").status_code == 401
    assert c.post("/api/ai/climate", json={"giata": 1, "label": "X"}).status_code == 401
    assert c.post("/api/climate/128/email", json={"to": "a@b.de"}).status_code == 401
