"""Hintergrundaufträge für lange KI-Anfragen.

Eine gründliche Perplexity-Stufe recherchiert minutenlang. Hängt die Antwort so
lange in einer offenen HTTP-Verbindung, gibt der Browser (bzw. der Ingress-Proxy
davor) vorher auf — der Nutzer sieht „fehlgeschlagen", während der Server zu Ende
rechnet und das Ergebnis ablegt. Mit `_async: true` kommt stattdessen sofort eine
Auftragsnummer zurück, das Ergebnis wird über `/api/ai/job/<id>` abgeholt.

Wichtig sind hier vor allem die beiden Dinge, die im Thread leicht verloren gehen:
der Request-Körper und die Anmeldung.
"""
import importlib
import json
import time

import pytest

pytest.importorskip("flask")

ING = {"X-Ingress-Path": "/test"}


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
    with open(m.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"ai_provider": "perplexity", "perplexity_api_key": "p-key"}, f)
    return m


def _await_job(client, job_id, tries=100):
    """Auftrag abholen, bis er fertig ist (wie das Frontend, nur schneller)."""
    for _ in range(tries):
        r = client.get(f"/api/ai/job/{job_id}", headers=ING)
        if r.status_code != 202:
            return r
        time.sleep(0.05)
    raise AssertionError("Auftrag wurde nicht fertig")


def test_without_the_flag_the_route_answers_directly(app_mod, monkeypatch):
    """Ältere Frontends schicken `_async` nicht — die müssen unverändert laufen."""
    monkeypatch.setattr(app_mod, "_ai_request",
                        lambda *a, **k: ("Ein Fazit.", {"input_tokens": 1, "output_tokens": 1}, None))
    c = app_mod.app.test_client()
    r = c.post("/api/ai/ask", headers=ING, json={"question": "Wann nach Kreta?", "scope": "general"})
    assert r.status_code == 200
    assert "job" not in r.get_json()


def test_async_returns_a_job_and_then_the_real_answer(app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "_ai_request",
                        lambda *a, **k: ("Ein Fazit.", {"input_tokens": 1, "output_tokens": 1}, None))
    c = app_mod.app.test_client()
    r = c.post("/api/ai/ask", headers=ING,
               json={"question": "Wann nach Kreta?", "scope": "general", "_async": True})
    assert r.status_code == 202
    job = r.get_json()["job"]

    done = _await_job(c, job)
    assert done.status_code == 200
    assert done.get_json()["summary"] == "Ein Fazit."


def test_the_request_body_survives_into_the_thread(app_mod, monkeypatch):
    """Der Thread hat keinen Request-Kontext geerbt — der Körper wird eigens
    nachgebaut. Ginge er verloren, liefe die Route ohne ihre Eingaben."""
    seen = {}

    def fake(_key, _model, prompt, **kw):
        seen["prompt"] = prompt
        return "Fazit.", {"input_tokens": 1, "output_tokens": 1}, None

    monkeypatch.setattr(app_mod, "_ai_request", fake)
    c = app_mod.app.test_client()
    r = c.post("/api/ai/ask", headers=ING,
               json={"question": "Wann auf die Malediven?", "scope": "general", "_async": True})
    _await_job(c, r.get_json()["job"])
    assert "Malediven" in seen["prompt"]


def test_a_failing_route_reports_its_own_error_code(app_mod, monkeypatch):
    """Fehler der Route dürfen nicht zu einem generischen 500 verwaschen —
    das Frontend unterscheidet danach, ob ein Wiederholen sinnvoll ist."""
    monkeypatch.setattr(app_mod, "_ai_request", lambda *a, **k: (None, None, "failed"))
    c = app_mod.app.test_client()
    r = c.post("/api/ai/ask", headers=ING,
               json={"question": "Wann nach Kreta?", "scope": "general", "_async": True})
    done = _await_job(c, r.get_json()["job"])
    assert done.status_code >= 400
    assert "error" in done.get_json()


def test_an_exception_in_the_thread_does_not_hang_the_job(app_mod, monkeypatch):
    """Ohne Auffangnetz bliebe der Auftrag für immer „running" und das Fenster
    drehte sich, bis der Nutzer aufgibt."""
    def boom(*a, **k):
        raise RuntimeError("kaputt")
    monkeypatch.setattr(app_mod, "_ai_request", boom)
    c = app_mod.app.test_client()
    r = c.post("/api/ai/ask", headers=ING,
               json={"question": "Wann nach Kreta?", "scope": "general", "_async": True})
    done = _await_job(c, r.get_json()["job"])
    assert done.status_code == 500
    assert done.get_json()["error"] == "failed"


def test_a_result_is_handed_out_only_once(app_mod, monkeypatch):
    """Nach dem Abholen ist der Auftrag weg — sonst sammelten sich fertige
    Ergebnisse im Speicher an."""
    monkeypatch.setattr(app_mod, "_ai_request",
                        lambda *a, **k: ("Fazit.", {"input_tokens": 1, "output_tokens": 1}, None))
    c = app_mod.app.test_client()
    r = c.post("/api/ai/ask", headers=ING,
               json={"question": "Wann nach Kreta?", "scope": "general", "_async": True})
    job = r.get_json()["job"]
    assert _await_job(c, job).status_code == 200
    assert c.get(f"/api/ai/job/{job}", headers=ING).status_code == 404


def test_unknown_job_is_not_found(app_mod):
    c = app_mod.app.test_client()
    assert c.get("/api/ai/job/gibtsnicht", headers=ING).status_code == 404
