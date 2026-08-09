"""Tests für den Benachrichtigungs-Verlauf (notify_log + /api/notifications),
das Fehler-Panel (/api/errors, _warn_buffer) und den KI-Feld-Vorschlag
(/api/trips/<id>/fields/suggest). Kein Netz: http.post/_ai_request gemonkeypatcht."""
import importlib
import io
import json

import pytest

pytest.importorskip("flask")

ING = {"X-Ingress-Path": "/test"}


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
    mod.TRIPS_DIR = str(tmp_path / "trips")
    mod.init_db()
    return mod


def _write_options(m, **opts):
    with open(m.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(opts, f)


def test_notify_telegram_logged_in_history(m, monkeypatch):
    _write_options(m, telegram_bot_token="tok", telegram_chat_id="42")
    monkeypatch.setattr(m.http, "post", lambda *a, **k: None)
    m._notify_telegram("Preis gefallen: 1.999 €")
    c = m.app.test_client()
    d = c.get("/api/notifications", headers=ING).get_json()
    assert len(d["items"]) == 1
    it = d["items"][0]
    assert it["channel"] == "telegram" and it["ok"] == 1
    assert "1.999" in it["message"]


def test_notify_ha_extra_service(m, monkeypatch):
    """ha_notify_service: zusätzliche notify.*-Dienste (Komma-Liste, Präfix optional)."""
    _write_options(m, ha_notify_service="notify.mobile_app_handy, tv")
    monkeypatch.setattr(m, "SUPERVISOR_TOKEN", "tok")
    calls = []
    monkeypatch.setattr(m.http, "post", lambda url, **k: calls.append(url))
    m._notify_ha("Titel", "Text", "test")
    assert any(u.endswith("/services/persistent_notification/create") for u in calls)
    assert any(u.endswith("/services/notify/mobile_app_handy") for u in calls)
    assert any(u.endswith("/services/notify/tv") for u in calls)


def test_notify_ha_no_extra_service_by_default(m, monkeypatch):
    _write_options(m)
    monkeypatch.setattr(m, "SUPERVISOR_TOKEN", "tok")
    calls = []
    monkeypatch.setattr(m.http, "post", lambda url, **k: calls.append(url))
    m._notify_ha("Titel", "Text", "test")
    assert len(calls) == 1  # nur persistent_notification


def test_notify_failure_logged_as_not_ok(m, monkeypatch):
    _write_options(m, telegram_bot_token="tok", telegram_chat_id="42")
    def boom(*a, **k):
        raise OSError("offline")
    monkeypatch.setattr(m.http, "post", boom)
    m._notify_telegram("Test")
    d = m.app.test_client().get("/api/notifications", headers=ING).get_json()
    assert d["items"][0]["ok"] == 0


def test_notify_log_pruned_to_500(m, monkeypatch):
    for i in range(510):
        m._log_notification("ha", f"T{i}", "msg", "tag", True)
    with m.db() as con:
        n = con.execute("SELECT COUNT(*) c FROM notify_log").fetchone()["c"]
    assert n == 500


def test_errors_endpoint_returns_recent_warnings(m):
    m.log.warning("Testwarnung: Kalender kaputt")
    d = m.app.test_client().get("/api/errors", headers=ING).get_json()
    msgs = [it["msg"] for it in d["items"]]
    assert any("Testwarnung: Kalender kaputt" in s for s in msgs)
    assert all(it["level"] in ("WARNING", "ERROR") for it in d["items"])


def test_fields_suggest_returns_ai_values_without_saving(m, monkeypatch):
    _write_options(m, anthropic_api_key="sk-test")
    fake = {"buchungsnummer": "12345678", "buchungsdatum": "01.02.2026",
            "reiseziel": "Teststrand", "hotel": {"name": "Test Hotel"},
            "reisezeitraum": {"von": "01.05.2026", "bis": "08.05.2026"},
            "naechte": 7, "verpflegung": "AI", "gesamtpreis": "1.000,00",
            "reisende": [{}], "fluege": [], "extras": [], "rabatte": [],
            "sonderwuensche": [], "anzahlung": {}, "restzahlung": {},
            "zimmertyp": None, "zahlungsart": None}
    monkeypatch.setattr(m, "parse_tui_pdf", lambda f: dict(fake))
    c = m.app.test_client()
    r = c.post("/api/trips/import", headers=ING,
               data={"pdf": (io.BytesIO(b"%PDF-1.4 fake"), "reise.pdf")},
               content_type="multipart/form-data")
    tid = r.get_json()["id"]

    monkeypatch.setattr(m, "extract_pdf_text", lambda f: "PDF-Text")
    monkeypatch.setattr(m, "_ai_request", lambda *a, **k: (
        json.dumps({"buchungsnummer": None, "buchungsdatum": None, "reiseziel": "Kreta",
                     "hotel_name": None, "reisezeitraum_von": None, "reisezeitraum_bis": None,
                     "naechte": None, "verpflegung": None, "gesamtpreis": "2.222,00",
                     "reisende_anzahl": None}),
        {"input_tokens": 10, "output_tokens": 5, "cache_creation_input_tokens": 0,
         "cache_read_input_tokens": 0}, None))
    d = c.post(f"/api/trips/{tid}/fields/suggest", headers=ING).get_json()
    assert d["ok"] is True
    assert d["suggestions"] == {"reiseziel": "Kreta", "gesamtpreis": "2.222,00"}
    # NUR Vorschlag — nichts gespeichert: Reiseziel unverändert, kein Override
    detail = c.get(f"/api/trips/{tid}", headers=ING).get_json()
    assert detail["data"]["reiseziel"] == "Teststrand"
    assert "_manual" not in detail["data"]


def test_backup_includes_packing_template(m):
    import zipfile
    m._meta_set("packing_template", json.dumps({"Kat": ["Item"]}))
    c = m.app.test_client()
    b = c.get("/api/backup", headers=ING)
    data = json.loads(zipfile.ZipFile(io.BytesIO(b.data)).read("data.json"))
    assert json.loads(data["meta"]["packing_template"]) == {"Kat": ["Item"]}
