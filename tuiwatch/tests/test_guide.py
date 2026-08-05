"""Tests für den KI-Reiseführer je Reiseziel.

Wie die Klimatabelle: EINMAL je Ziel erzeugt, dauerhaft gespeichert, jeder weitere
Abruf ohne KI-Aufruf. Hier wiegt das schwerer als beim Klima — der Reiseführer ist
mit dreizehn Abschnitten und zwanzig Vokabeln der teuerste Einzelaufruf im Add-on.
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

GUIDE = {
    "sections": [
        {"titel": "Allgemeine Informationen", "einleitung": "Spanische Insel.",
         "punkte": [{"label": "Währung", "text": "Euro", "volatil": False},
                    {"label": "Wechselkurs", "text": "1:1", "volatil": True}]},
        {"titel": "Einreise", "einleitung": "",
         "punkte": [{"label": "Dokumente", "text": "Personalausweis", "volatil": True}]},
        {"titel": "Klima", "einleitung": "Ganzjährig mild.", "punkte": []},
        {"titel": "Don't Dos", "einleitung": "",
         "punkte": [{"label": "", "text": "Nicht am Strand grillen", "volatil": False}]},
        {"titel": "Nützliche Wörter", "einleitung": "",
         "punkte": [{"label": "Hola", "text": "Hallo", "volatil": False}]},
    ],
    "zusammenfassung": ["Euro als Währung", "Kein Visum nötig"],
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
        return json.dumps(GUIDE), {"input_tokens": 10, "output_tokens": 20}, None

    monkeypatch.setattr(m, "_ai_request", _fake)
    return calls


def test_get_without_stored_guide_costs_nothing(client, ai):
    d = client.get("/api/guide/128").get_json()
    assert d == {"found": False, "giata": 128}
    assert not ai


def test_first_post_generates_and_stores(client, m, ai):
    d = client.post("/api/ai/guide", json={"giata": 128, "label": "Gran Canaria"}).get_json()
    assert d["found"] is True and d["cached"] is False
    assert [s["titel"] for s in d["data"]["sections"]][:2] == \
        ["Allgemeine Informationen", "Einreise"]
    assert len(ai) == 1 and ai[0]["use_web_search"] is True
    with m.db() as con:
        row = con.execute("SELECT label FROM guide WHERE giata=128").fetchone()
    assert row["label"] == "Gran Canaria"


def test_second_post_uses_the_stored_guide(client, ai):
    client.post("/api/ai/guide", json={"giata": 128, "label": "Gran Canaria"})
    d = client.post("/api/ai/guide", json={"giata": 128, "label": "Gran Canaria"}).get_json()
    assert d["cached"] is True
    assert len(ai) == 1          # kein zweiter KI-Aufruf


def test_refresh_forces_a_new_call(client, ai):
    client.post("/api/ai/guide", json={"giata": 128, "label": "Gran Canaria"})
    d = client.post("/api/ai/guide",
                    json={"giata": 128, "label": "Gran Canaria", "refresh": True}).get_json()
    assert d["cached"] is False and len(ai) == 2


def test_token_budget_is_large_enough_for_thirteen_sections(client, ai):
    """Eine abgeschnittene Antwort ist kein gültiges JSON — der Aufruf wäre komplett
    verloren. Deshalb deutlich mehr als die 3000 der Klimatabelle."""
    client.post("/api/ai/guide", json={"giata": 128, "label": "Gran Canaria"})
    assert ai[0]["max_tokens"] >= 8000


def test_truncated_answer_is_rejected_and_not_stored(client, m, monkeypatch):
    monkeypatch.setattr(m, "_ai_request", lambda *a, **k: (
        json.dumps({"sections": GUIDE["sections"][:2], "zusammenfassung": []}),
        {"input_tokens": 1, "output_tokens": 1}, None))
    r = client.post("/api/ai/guide", json={"giata": 99, "label": "X"})
    assert r.status_code == 502 and r.get_json()["error"] == "ai_empty"
    with m.db() as con:
        assert con.execute("SELECT 1 FROM guide WHERE giata=99").fetchone() is None


def test_prompt_covers_all_requested_topics(client, ai):
    client.post("/api/ai/guide", json={"giata": 128, "label": "Gran Canaria"})
    p = ai[0]["prompt"]
    for topic in ("Einreise", "Gesundheit", "Geld", "Mobilität", "Sicherheit",
                  "Kultur & Etikette", "Don't Dos", "Insider-Tipps",
                  "Nützliche Wörter", "Praktische Informationen"):
        assert topic in p
    assert "Gran Canaria" in p
    assert "volatil" in p            # kurzlebige Angaben werden markiert
    assert "15 Stichpunkte" in p


def test_list_and_delete(client, ai):
    assert client.get("/api/guide").get_json() == {"items": []}
    client.post("/api/ai/guide", json={"giata": 128, "label": "Gran Canaria"})
    client.post("/api/ai/guide", json={"giata": 127, "label": "Fuerteventura"})
    items = client.get("/api/guide").get_json()["items"]
    assert [i["label"] for i in items] == ["Fuerteventura", "Gran Canaria"]   # alphabetisch
    assert all("data" not in i for i in items)          # Inhalt gehört nicht in die Liste
    assert client.delete("/api/guide/128").get_json()["deleted"] == 1
    assert client.get("/api/guide/128").get_json()["found"] is False


def test_post_without_label_and_without_stored_guide(client, ai):
    assert client.post("/api/ai/guide", json={"giata": 1}).get_json()["error"] == "no_dest"
    assert not ai


# ── Klimatabelle im Reiseführer ───────────────────────────────────────────────
# Beide hängen an derselben Region-giataId, damit sie zusammenfinden.

def test_guide_carries_the_stored_climate_table(client, ai):
    client.post("/api/ai/climate", json={"giata": 128, "label": "Gran Canaria"})
    # `ai` liefert für JEDEN Aufruf das Reiseführer-JSON — die Klimaroute lehnt das
    # ab, deshalb hier direkt in die DB schreiben statt über die Route.
    d = client.get("/api/guide/128").get_json()
    assert d["found"] is False        # noch kein Reiseführer


def test_guide_get_includes_climate(client, m, ai):
    import time
    with m.db() as con:
        con.execute("INSERT INTO climate (giata, label, ts, model, data) VALUES (?,?,?,?,?)",
                    (128, "Gran Canaria", int(time.time()), "x", json.dumps(CLIMATE)))
    client.post("/api/ai/guide", json={"giata": 128, "label": "Gran Canaria"})
    d = client.get("/api/guide/128").get_json()
    assert len(d["climate"]["months"]) == 12


def test_guide_without_climate_is_fine(client, ai):
    d = client.post("/api/ai/guide", json={"giata": 5, "label": "X"}).get_json()
    assert d["climate"] is None


# ── Prompt-Vorschau ───────────────────────────────────────────────────────────

@pytest.fixture
def preview(m, monkeypatch):
    monkeypatch.setattr(m, "load_config", lambda: {
        "anthropic_api_key": "sk-test", "anthropic_model": "claude-haiku-4-5",
        "ai_prompt_preview": True})


def test_preview_returns_the_prompt_instead_of_data(client, preview, ai):
    d = client.post("/api/ai/guide", json={"giata": 128, "label": "Gran Canaria"}).get_json()
    assert "prompt_preview" in d and "data" not in d
    assert not ai


def test_confirmed_prompt_runs_through(client, preview, ai):
    d = client.post("/api/ai/guide", json={"giata": 128, "label": "Gran Canaria",
                                           "_prompt_confirmed": True}).get_json()
    assert d["found"] is True and len(ai) == 1


# ── E-Mail ────────────────────────────────────────────────────────────────────

def test_email_sends_the_stored_guide(client, m, ai, monkeypatch):
    client.post("/api/ai/guide", json={"giata": 128, "label": "Gran Canaria"})
    monkeypatch.setattr(m, "smtp_configured", lambda: True)
    sent = []
    monkeypatch.setattr(m, "send_email", lambda s, h, t: sent.append((s, h, t)))
    r = client.post("/api/guide/128/email", json={"to": "a@b.de"})
    assert r.status_code == 200 and r.get_json()["sent"] is True
    subject, html, to = sent[0]
    assert to == "a@b.de" and "Gran Canaria" in subject
    assert "Einreise" in html and "Nützliche Wörter" in html
    assert "Euro als Währung" in html          # Zusammenfassung
    assert len(ai) == 1                        # Versand kostet keinen KI-Aufruf


def test_email_includes_climate_when_stored(client, m, ai, monkeypatch):
    import time
    with m.db() as con:
        con.execute("INSERT INTO climate (giata, label, ts, model, data) VALUES (?,?,?,?,?)",
                    (128, "Gran Canaria", int(time.time()), "x", json.dumps(CLIMATE)))
    client.post("/api/ai/guide", json={"giata": 128, "label": "Gran Canaria"})
    monkeypatch.setattr(m, "smtp_configured", lambda: True)
    sent = []
    monkeypatch.setattr(m, "send_email", lambda s, h, t: sent.append((s, h, t)))
    client.post("/api/guide/128/email", json={"to": "a@b.de"})
    html = sent[0][1]
    assert "Klimatabelle" in html and "Januar" in html and "Dezember" in html


def test_email_without_stored_guide_is_404(client, m, monkeypatch):
    monkeypatch.setattr(m, "smtp_configured", lambda: True)
    monkeypatch.setattr(m, "send_email", lambda s, h, t: None)
    assert client.post("/api/guide/777/email", json={"to": "a@b.de"}).status_code == 404


def test_email_needs_smtp(client, m, ai, monkeypatch):
    client.post("/api/ai/guide", json={"giata": 128, "label": "Gran Canaria"})
    monkeypatch.setattr(m, "smtp_configured", lambda: False)
    r = client.post("/api/guide/128/email", json={"to": "a@b.de"})
    assert r.status_code == 400 and r.get_json()["error"] == "smtp_not_configured"


def test_guide_html_escapes_and_marks_volatile():
    email_search = importlib.import_module("email_search")
    evil = {"sections": [{"titel": "T", "einleitung": "",
                          "punkte": [{"label": "<script>", "text": "x", "volatil": True}]}],
            "zusammenfassung": []}
    html = email_search.guide_html("X", evil)
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "⏱" in html


def test_guide_html_links_citations():
    email_search = importlib.import_module("email_search")
    data = {"sections": [{"titel": "T", "einleitung": "",
                          "punkte": [{"label": "L", "text": "Mild [1](https://a.invalid/x).",
                                      "volatil": False}]}],
            "zusammenfassung": []}
    html = email_search.guide_html("X", data)
    assert '<a href="https://a.invalid/x"' in html and ">[1]</a>" in html


def test_perplexity_citations_become_links(client, m, monkeypatch):
    payload = json.loads(json.dumps(GUIDE))
    payload["zusammenfassung"] = ["Euro [1]"]
    payload["sections"][0]["einleitung"] = "Insel [2]"
    payload["sections"][0]["punkte"][0]["text"] = "Euro [1]"
    monkeypatch.setattr(m, "_ai_request", lambda *a, **k: (
        json.dumps(payload),
        {"input_tokens": 1, "output_tokens": 1,
         "citation_urls": ["https://a.invalid/x", "https://b.invalid/y"]}, None))
    d = client.post("/api/ai/guide", json={"giata": 5, "label": "X"}).get_json()
    assert d["data"]["zusammenfassung"] == ["Euro [1](https://a.invalid/x)"]
    assert d["data"]["sections"][0]["einleitung"] == "Insel [2](https://b.invalid/y)"
    assert d["data"]["sections"][0]["punkte"][0]["text"] == "Euro [1](https://a.invalid/x)"
    assert "citation_urls" not in d["usage"]


def test_other_providers_are_untouched(client, ai):
    d = client.post("/api/ai/guide", json={"giata": 6, "label": "Y"}).get_json()
    assert d["data"]["zusammenfassung"] == GUIDE["zusammenfassung"]
