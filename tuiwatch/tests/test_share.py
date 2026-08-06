"""Tests für die öffentlichen Angebots-Links (share_routes.py).

Schwerpunkt Sicherheit: die öffentliche App darf ausschließlich `/s/<token>`
kennen, und im Schnappschuss darf nichts landen, was nicht ausdrücklich in der
Whitelist steht (TUI-URL, Buchungscode, PDF-Link, Wunschpreis …). Beides würde
sonst über einen weitergegebenen Link nach draußen sickern.
"""
import importlib
import json
import time
from pathlib import Path

import pytest

pytest.importorskip("flask")

ROOT = Path(__file__).resolve().parent.parent

CLIMATE = {
    "months": [{"monat": i, "temp_tag": 20 + i, "temp_nacht": 12, "wasser": 18,
                "sonnenstunden": 6, "regentage": 3, "hinweis": ""} for i in range(1, 13)],
    "beste_monate": [5, 6],
    "zusammenfassung": "Ganzjährig mild.",
}
GUIDE = {
    "sections": [{"titel": "Einreise", "einleitung": "Kurz und knapp.",
                  "punkte": [{"label": "Pass", "text": "Noch 6 Monate gültig",
                              "volatil": True}]}],
    "zusammenfassung": ["Personalausweis reicht"],
}
# Angebots-URL mit Region-giataId: Klima/Reiseführer hängen an der Region, nicht
# am Hotel — ohne die Region würde der Schnappschuss beides stumm weglassen.
OFFER_URL = ("https://www.tui.com/pauschalreisen/angebote/Hotel-Sonne/4711/"
             "?regionGiataIds=555")


@pytest.fixture
def m(tmp_path, monkeypatch):
    monkeypatch.setenv("TUIWATCH_DATA", str(tmp_path))
    monkeypatch.setenv("TUIWATCH_BASE", str(ROOT))   # Templates/Assets liegen im Repo
    try:
        mod = importlib.import_module("app")
    except Exception as exc:
        pytest.skip(f"app nicht importierbar: {exc}")
    importlib.reload(mod)
    mod.DB_PATH = str(tmp_path / "tuiwatch.db")
    mod.init_db()
    return mod


@pytest.fixture
def sr(m):
    import share_routes
    importlib.reload(share_routes)
    return share_routes


@pytest.fixture
def offer_id(m):
    now = int(time.time())
    with m.db() as con:
        cur = con.execute(
            "INSERT INTO offers (url, label, hotel, details, room, board, location, "
            "country, stars, rating, rating_count, travellers_count, return_date, "
            "image_url, booking_code, pdf_url, target_price, booked_price, created) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (OFFER_URL, "Testangebot", "Hotel Sonne", "7 Nächte ab 12.09.2026",
             "Doppelzimmer", "All Inclusive", "Playa", "Spanien", 4.0, 5.4, 220, 2,
             "2026-09-19", "https://img.example/h.jpg", "GEHEIM123",
             "https://tui.example/geheim.pdf", 999.0, 1234.0, now))
        oid = cur.lastrowid
        con.execute("INSERT INTO price_history (offer_id, ts, price, ok) VALUES (?,?,?,1)",
                    (oid, now - 86400, 1999.0))
        con.execute("INSERT INTO price_history (offer_id, ts, price, ok) VALUES (?,?,?,1)",
                    (oid, now, 1899.0))
        con.execute("INSERT INTO climate (giata, label, ts, model, data) VALUES (555,?,?,?,?)",
                    ("Mallorca", now, "m", json.dumps(CLIMATE)))
        con.execute("INSERT INTO guide (giata, label, ts, model, data) VALUES (555,?,?,?,?)",
                    ("Mallorca", now, "m", json.dumps(GUIDE)))
        con.execute("INSERT INTO ai_analyses (kind, title, model, summary, ts) "
                    "VALUES ('advisor','Kanaren','m','## Vorschlag\n- **Teneriffa**',?)",
                    (now,))
    return oid


@pytest.fixture
def admin(m, monkeypatch):
    monkeypatch.setattr(m, "_auth_ok", lambda req: True)
    m.app.config["TESTING"] = True
    return m.app.test_client()


@pytest.fixture
def public(sr):
    sr.share_app.config["TESTING"] = True
    return sr.share_app.test_client()


def _create(admin, offer_id, **kw):
    body = {"offer_ids": [offer_id], "title": "Unsere Auswahl", "note": "Schau mal"}
    body.update(kw)
    r = admin.post("/api/shares", json=body)
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()


# ── Schnappschuss ─────────────────────────────────────────────────────────────

def test_payload_only_contains_whitelisted_fields(m, sr, admin, offer_id):
    """Der Schnappschuss darf keine Felder enthalten, die nicht in _OFFER_FIELDS
    stehen — sonst wandert eine neue Angebots-Spalte automatisch nach draußen."""
    tok = _create(admin, offer_id)["token"]
    with m.db() as con:
        payload = json.loads(con.execute("SELECT payload FROM shares WHERE token=?",
                                         (tok,)).fetchone()["payload"])
    item = payload["offers"][0]
    allowed = set(sr._OFFER_FIELDS) | set(sr._LIVE_FIELDS) | {"history", "spark", "id"}
    assert set(item) <= allowed
    for forbidden in ("pdf_url", "booking_code", "room_booking_code",
                      "target_price", "booked_price"):
        assert forbidden not in item


def test_public_page_leaks_nothing_sensitive(public, admin, offer_id):
    tok = _create(admin, offer_id, include={"climate": True})["token"]
    body = public.get("/s/" + tok).get_data(as_text=True)
    assert "Testangebot" in body and "Mallorca" in body
    for secret in ("GEHEIM123", "geheim.pdf", "999", "1234"):
        assert secret not in body


def test_price_and_availability_are_live(m, public, admin, offer_id):
    """Preis und Verfügbarkeit sollen dem aktuellen Stand folgen — sonst zeigt ein
    weitergegebener Link Wochen später einen Fantasiepreis."""
    tok = _create(admin, offer_id)["token"]
    assert "1.899" in public.get("/s/" + tok).get_data(as_text=True)
    with m.db() as con:
        con.execute("INSERT INTO price_history (offer_id, ts, price, ok, available) "
                    "VALUES (?,?,?,1,0)", (offer_id, int(time.time()) + 60, 4444.0))
    body = public.get("/s/" + tok).get_data(as_text=True)
    assert "4.444" in body and "1.899" not in body
    assert "nicht mehr verfügbar" in body


def test_description_stays_frozen(m, public, admin, offer_id):
    """Nur Preis/Verfügbarkeit sind live — Beschreibung bleibt der Stand vom Erzeugen."""
    tok = _create(admin, offer_id)["token"]
    with m.db() as con:
        con.execute("UPDATE offers SET label='Umbenannt', room='Suite' WHERE id=?",
                    (offer_id,))
    body = public.get("/s/" + tok).get_data(as_text=True)
    assert "Testangebot" in body and "Umbenannt" not in body


def test_deleted_offer_keeps_last_known_state(m, public, admin, offer_id):
    tok = _create(admin, offer_id)["token"]
    with m.db() as con:
        con.execute("DELETE FROM offers WHERE id=?", (offer_id,))
    body = public.get("/s/" + tok).get_data(as_text=True)
    assert "Testangebot" in body and "1.899" in body
    assert "Letzter bekannter Stand" in body


def test_links_to_tui_and_holidaycheck(public, admin, offer_id):
    body = public.get("/s/" + _create(admin, offer_id)["token"]).get_data(as_text=True)
    assert OFFER_URL.replace("&", "&amp;") in body or OFFER_URL in body
    assert "site%3Aholidaycheck.de" in body


def test_only_tui_urls_are_linked(m, sr):
    """Die Angebots-URL landet als Link auf einer öffentlichen Seite — alles außer
    tui.com per https bleibt draußen."""
    assert sr._tui_link({"url": "https://www.tui.com/x"})
    assert not sr._tui_link({"url": "http://www.tui.com/x"})
    assert not sr._tui_link({"url": "https://evil.example/tui.com"})
    assert not sr._tui_link({"url": "javascript:alert(1)"})
    assert not sr._tui_link({"url": ""})


def test_extras_only_when_requested(public, admin, offer_id):
    plain = public.get("/s/" + _create(admin, offer_id)["token"]).get_data(as_text=True)
    assert "Klima" not in plain and "Reiseführer" not in plain

    full = _create(admin, offer_id, include={"climate": True, "guide": True,
                                             "history": True, "advisor": True},
                   advisor_id=1)
    body = public.get("/s/" + full["token"]).get_data(as_text=True)
    assert "Klima" in body and "Reiseführer" in body and "Reiseberater" in body
    assert "Preisverlauf" in body  # SVG-Sparkline


def test_create_requires_existing_offers(admin):
    assert admin.post("/api/shares", json={"offer_ids": [9999]}).status_code == 400
    assert admin.post("/api/shares", json={"offer_ids": []}).status_code == 400


# ── Gültigkeit / Widerruf ─────────────────────────────────────────────────────

def test_unknown_token_is_404(public):
    assert public.get("/s/" + "x" * 20).status_code == 404
    assert public.get("/s/kurz").status_code == 404


def test_expired_token_is_410(m, public, admin, offer_id):
    tok = _create(admin, offer_id)["token"]
    with m.db() as con:
        con.execute("UPDATE shares SET expires_ts=? WHERE token=?",
                    (int(time.time()) - 10, tok))
    assert public.get("/s/" + tok).status_code == 410


def test_revoked_token_is_404(public, admin, offer_id):
    tok = _create(admin, offer_id)["token"]
    assert admin.delete("/api/shares/" + tok).status_code == 200
    assert public.get("/s/" + tok).status_code == 404


def test_views_are_counted(public, admin, offer_id):
    tok = _create(admin, offer_id)["token"]
    public.get("/s/" + tok)
    public.get("/s/" + tok)
    item = admin.get("/api/shares").get_json()["items"][0]
    assert item["token"] == tok and item["views"] == 2


def test_edit_keeps_token_and_swaps_offers(m, public, admin, offer_id):
    """Angebot austauschen, ohne dass Empfänger einen neuen Link brauchen."""
    tok = _create(admin, offer_id)["token"]
    public.get("/s/" + tok)          # ein Aufruf, muss erhalten bleiben
    with m.db() as con:
        second = con.execute(
            "INSERT INTO offers (url, label, hotel, created) VALUES "
            "('https://www.tui.com/pauschalreisen/angebote/Zweites/4712/','Zweitangebot',"
            "'Hotel Zwei',?)", (int(time.time()),)).lastrowid

    r = admin.patch("/api/shares/" + tok, json={"offer_ids": [second]})
    assert r.status_code == 200 and r.get_json()["token"] == tok

    body = public.get("/s/" + tok).get_data(as_text=True)
    assert "Zweitangebot" in body and "Testangebot" not in body
    item = admin.get("/api/shares").get_json()["items"][0]
    assert item["token"] == tok and item["views"] == 2


def test_edit_detail_prefills_current_state(admin, offer_id):
    created = _create(admin, offer_id, include={"climate": True, "history": True},
                      title="Titel", note="Notiz")
    d = admin.get("/api/shares/" + created["token"]).get_json()
    assert d["offer_ids"] == [offer_id]
    assert d["title"] == "Titel" and d["note"] == "Notiz"
    assert d["include"]["climate"] is True and d["include"]["history"] is True
    assert d["include"]["guide"] is False
    assert 1 <= d["days"] <= 31


def test_edit_keeps_creation_date(m, admin, offer_id):
    tok = _create(admin, offer_id)["token"]
    with m.db() as con:
        con.execute("UPDATE shares SET created_ts=? WHERE token=?", (1000, tok))
    admin.patch("/api/shares/" + tok, json={"offer_ids": [offer_id]})
    with m.db() as con:
        row = con.execute("SELECT created_ts, payload FROM shares WHERE token=?",
                          (tok,)).fetchone()
    assert row["created_ts"] == 1000
    assert json.loads(row["payload"])["created"] == 1000


def test_edit_rejects_empty_selection(admin, offer_id):
    tok = _create(admin, offer_id)["token"]
    assert admin.patch("/api/shares/" + tok, json={"offer_ids": []}).status_code == 400
    assert admin.patch("/api/shares/" + tok,
                       json={"offer_ids": [9999]}).status_code == 400


def test_destinations_report_missing_extras(m, admin, offer_id):
    """Grundlage für die Rückfrage „Klimatabelle fehlt — jetzt erstellen?"."""
    d = admin.post("/api/shares/destinations", json={"offer_ids": [offer_id]}).get_json()
    assert d["items"] == [{"giata": 555, "label": "Spanien", "has_climate": True,
                           "has_guide": True}]
    with m.db() as con:
        con.execute("DELETE FROM climate WHERE giata=555")
    d = admin.post("/api/shares/destinations", json={"offer_ids": [offer_id]}).get_json()
    assert d["items"][0]["has_climate"] is False
    assert d["items"][0]["has_guide"] is True


def test_destinations_needs_auth(m):
    m.app.config["TESTING"] = True
    assert m.app.test_client().post("/api/shares/destinations",
                                    json={"offer_ids": [1]}).status_code == 401


def test_detail_of_unknown_token_is_404(admin):
    assert admin.get("/api/shares/" + "x" * 20).status_code == 404


def test_patch_extends_validity(admin, offer_id):
    created = _create(admin, offer_id, days=1)
    r = admin.patch("/api/shares/" + created["token"], json={"days": 60})
    assert r.status_code == 200
    assert r.get_json()["expires_ts"] > created["expires_ts"]


# ── Abschottung der öffentlichen App ──────────────────────────────────────────

@pytest.mark.parametrize("path", ["/", "/login", "/api/offers", "/api/shares",
                                  "/static/app.js", "/a/app.js", "/icon-192.png"])
def test_public_app_serves_nothing_else(public, path):
    """Die öffentliche App kennt weder die Oberfläche noch irgendeine API — ein
    versehentlich dort registrierter Blueprint fliegt hier auf."""
    assert public.get(path).status_code == 404


def test_public_assets_are_whitelisted(public):
    for name in ("share.css", "share.js", "aimd.js"):
        assert public.get("/a/" + name).status_code == 200
    assert public.get("/robots.txt").get_data(as_text=True).startswith("User-agent")


def test_security_headers(public, admin, offer_id):
    r = public.get("/s/" + _create(admin, offer_id)["token"])
    assert r.headers["X-Robots-Tag"] == "noindex, nofollow"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]


def test_admin_routes_need_auth(m, offer_id):
    """Ohne Session ist die Verwaltung dicht (echte _auth_ok-Prüfung, kein Ingress)."""
    m.app.config["TESTING"] = True
    c = m.app.test_client()
    assert c.get("/api/shares").status_code == 401
    assert c.post("/api/shares", json={"offer_ids": [offer_id]}).status_code == 401
    assert c.delete("/api/shares/abcdefgh").status_code == 401


def test_token_has_enough_entropy(admin, offer_id):
    tok = _create(admin, offer_id)["token"]
    assert len(tok) >= 16
    assert len({_create(admin, offer_id)["token"] for _ in range(5)}) == 5


def test_cleanup_removes_long_expired(m, sr, admin, offer_id):
    tok = _create(admin, offer_id)["token"]
    with m.db() as con:
        con.execute("UPDATE shares SET expires_ts=? WHERE token=?",
                    (int(time.time()) - 30 * 86400, tok))
    assert sr.cleanup_expired() == 1
    with m.db() as con:
        assert con.execute("SELECT COUNT(*) c FROM shares").fetchone()["c"] == 0
