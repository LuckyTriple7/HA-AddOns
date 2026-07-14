"""Tests für die Kalender-Trend-Historie (`calendar_history`, `_store_calendar_snapshot`,
`_calendar_moves`/`_calendar_top_moves`/`_calendar_date_history`) sowie den TTL-Fix in
`_check_cheaper_date`. Kein Netz nötig: `fetch_calendar` wird gemonkeypatcht."""
import importlib
import io
import json
import time
import zipfile

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
    mod.init_db()
    return mod


def _add_offer(m, url, return_date="2027-03-15"):
    now = int(time.time())
    with m.db() as con:
        con.execute(
            "INSERT INTO offers (url, hotel, region, country, return_date, created) "
            "VALUES (?,?,?,?,?,?)",
            (url, "Test-Hotel", "Kanaren", "Spanien", return_date, now))
        return con.execute("SELECT id FROM offers WHERE url=?", (url,)).fetchone()["id"]


def _cal(days, **extra):
    out = {"ok": True, "currency": "EUR", "window_start": days[0][0],
           "window_end": days[-1][0], "duration": 7,
           "days": [{"date": d, "price": p} for d, p in days],
           "tracked_date": days[0][0], "tracked_price": days[0][1],
           "cheapest_date": days[0][0], "cheapest_price": days[0][1]}
    out.update(extra)
    return out


def test_first_calendar_fetch_writes_baseline_no_moves(m):
    oid = _add_offer(m, "https://example.invalid/a?duration=7")
    cal = _cal([("2027-05-01", 500), ("2027-05-02", 520), ("2027-05-03", 480)])
    with m.db() as con:
        m._store_calendar_snapshot(con, oid, cal)
        rows = con.execute("SELECT * FROM calendar_history WHERE offer_id=?", (oid,)).fetchall()
        moves = m._calendar_moves(con, oid)
    assert len(rows) == 3               # Baseline: jeder Tag einmal
    assert moves == {}                  # kein zweiter Datenpunkt -> keine Bewegung berechenbar


def test_store_calendar_snapshot_returns_empty_on_baseline_and_real_changes_only(m):
    """Rückgabewert dient der Benachrichtigung: Baseline (kein Vorwert) und neu ins
    Fenster gerutschte Tage (kein Vorwert für GENAU dieses Datum) zaehlen NICHT als
    'echte Aenderung' -- nur ein tatsaechlich anderer Preis fuer ein zuvor bekanntes
    Datum."""
    oid = _add_offer(m, "https://example.invalid/z?duration=7")
    with m.db() as con:
        changed1 = m._store_calendar_snapshot(
            con, oid, _cal([("2027-05-01", 500), ("2027-05-02", 520)]))
        assert changed1 == []   # reine Baseline

        changed2 = m._store_calendar_snapshot(
            con, oid, _cal([("2027-05-01", 500), ("2027-05-02", 560)]))
        assert changed2 == ["2027-05-02"]   # echte Preisaenderung

        # 05-03 ist neu im Fenster (kein Vorwert) -> keine "Aenderung"
        changed3 = m._store_calendar_snapshot(
            con, oid, _cal([("2027-05-01", 500), ("2027-05-02", 560), ("2027-05-03", 400)]))
        assert changed3 == []


def test_store_calendar_snapshot_heals_missing_baseline(m):
    """calendar_cache aus einer Version VOR calendar_history (< 0.43.11): die Historie
    ist leer, der alte Preis steht nur im Cache. Ändert sich ein Tag, muss der Vorwert
    aus dem Cache rückdatiert nachgetragen werden — sonst hätte der Tag nur eine
    History-Zeile, _calendar_moves() fände kein Delta und der min_diff-Filter würde
    die Änderung verschlucken (keine Benachrichtigung, kein Trend-Badge)."""
    oid = _add_offer(m, "https://example.invalid/heal?duration=7")
    old_ts = int(time.time()) - 86400
    with m.db() as con:
        # Cache "von früher" direkt setzen, ohne History (wie vor dem Feature)
        con.execute("INSERT OR REPLACE INTO calendar_cache (offer_id, ts, data) VALUES (?,?,?)",
                    (oid, old_ts, json.dumps(_cal([("2027-05-01", 1999), ("2027-05-02", 1800)]))))
        changed = m._store_calendar_snapshot(
            con, oid, _cal([("2027-05-01", 2026), ("2027-05-02", 1800)]))
        moves = m._calendar_moves(con, oid)
        rows = con.execute(
            "SELECT travel_date, ts, price FROM calendar_history WHERE offer_id=? "
            "ORDER BY travel_date, ts", (oid,)).fetchall()
    assert changed == ["2027-05-01"]
    # geheilter Tag: Vorwert (rückdatiert auf Cache-ts) + neuer Preis; 05-02 unverändert -> keine Zeile
    assert [(r["travel_date"], r["price"]) for r in rows] == [
        ("2027-05-01", 1999), ("2027-05-01", 2026)]
    assert rows[0]["ts"] == old_ts
    assert moves["2027-05-01"]["delta"] == 27


def test_unchanged_price_writes_no_new_row(m):
    oid = _add_offer(m, "https://example.invalid/b?duration=7")
    cal = _cal([("2027-05-01", 500), ("2027-05-02", 520)])
    with m.db() as con:
        m._store_calendar_snapshot(con, oid, cal)
        m._store_calendar_snapshot(con, oid, cal)  # identischer zweiter Abruf
        n = con.execute("SELECT COUNT(*) c FROM calendar_history WHERE offer_id=?",
                        (oid,)).fetchone()["c"]
    assert n == 2   # keine neuen Zeilen, Delta-Encoding greift


def test_changed_day_writes_delta_row_and_move(m):
    oid = _add_offer(m, "https://example.invalid/c?duration=7")
    cal1 = _cal([("2027-05-01", 500), ("2027-05-02", 520)])
    cal2 = _cal([("2027-05-01", 500), ("2027-05-02", 560)])   # nur 05-02 geändert
    with m.db() as con:
        m._store_calendar_snapshot(con, oid, cal1)
        m._store_calendar_snapshot(con, oid, cal2)
        n = con.execute("SELECT COUNT(*) c FROM calendar_history WHERE offer_id=?",
                        (oid,)).fetchone()["c"]
        moves = m._calendar_moves(con, oid)
    assert n == 3   # 2 Baseline + 1 geänderter Tag
    assert set(moves) == {"2027-05-02"}
    assert moves["2027-05-02"]["price"] == 560
    assert moves["2027-05-02"]["prev_price"] == 520
    assert moves["2027-05-02"]["delta"] == 40


def test_calendar_top_moves_sorted_by_abs_delta(m):
    oid = _add_offer(m, "https://example.invalid/d?duration=7")
    cal1 = _cal([("2027-05-01", 500), ("2027-05-02", 500), ("2027-05-03", 500)])
    cal2 = _cal([("2027-05-01", 510), ("2027-05-02", 450), ("2027-05-03", 500)])
    with m.db() as con:
        m._store_calendar_snapshot(con, oid, cal1)
        m._store_calendar_snapshot(con, oid, cal2)
        moves = m._calendar_moves(con, oid)
        top = m._calendar_top_moves(moves, limit=1)
    assert len(top) == 1
    assert top[0]["date"] == "2027-05-02"   # |-50| > |+10|


def test_calendar_date_history_returns_full_series(m):
    oid = _add_offer(m, "https://example.invalid/e?duration=7")
    with m.db() as con:
        for price in (500, 520, 480):
            m._store_calendar_snapshot(con, oid, _cal([("2027-05-01", price)]))
        points = m._calendar_date_history(con, oid, "2027-05-01")
    assert [p["price"] for p in points] == [500, 520, 480]


def test_check_cheaper_date_skips_fetch_within_ttl(m, monkeypatch):
    oid = _add_offer(m, "https://example.invalid/f?duration=7")
    cal = _cal([("2027-03-08", 400)], tracked_date="2027-03-15", tracked_price=500,
                cheapest_date="2027-03-08", cheapest_price=400)
    with m.db() as con:
        con.execute("INSERT OR REPLACE INTO calendar_cache (offer_id, ts, data) VALUES (?,?,?)",
                    (oid, int(time.time()), json.dumps(cal)))
    calls = []
    monkeypatch.setattr(m, "fetch_calendar", lambda *a, **k: calls.append(1) or None)
    notified = []
    monkeypatch.setattr(m, "_notify_ha", lambda *a, **k: notified.append(1))
    monkeypatch.setattr(m, "_notify_telegram", lambda *a, **k: None)
    offer = {"id": oid, "url": "https://example.invalid/f?duration=7", "label": "", "hotel": ""}
    m._check_cheaper_date(offer, 500)
    assert calls == []          # frischer Cache -> kein fetch_calendar-Aufruf
    assert notified == [1]      # Benachrichtigungslogik laeuft trotzdem aus dem Cache


def test_check_cheaper_date_refetches_after_ttl_expiry(m, monkeypatch):
    oid = _add_offer(m, "https://example.invalid/g?duration=7")
    old_cal = _cal([("2027-03-08", 450)])
    stale_ts = int(time.time()) - m._CALENDAR_FRESH_SECONDS - 1
    with m.db() as con:
        con.execute("INSERT OR REPLACE INTO calendar_cache (offer_id, ts, data) VALUES (?,?,?)",
                    (oid, stale_ts, json.dumps(old_cal)))
    new_cal = _cal([("2027-03-08", 400)], tracked_date="2027-03-15", tracked_price=500,
                    cheapest_date="2027-03-08", cheapest_price=400)
    calls = []
    monkeypatch.setattr(m, "fetch_calendar", lambda *a, **k: calls.append(1) or new_cal)
    monkeypatch.setattr(m, "_notify_ha", lambda *a, **k: None)
    monkeypatch.setattr(m, "_notify_telegram", lambda *a, **k: None)
    offer = {"id": oid, "url": "https://example.invalid/g?duration=7", "label": "", "hotel": ""}
    m._check_cheaper_date(offer, 500)
    assert calls == [1]   # abgelaufener Cache -> fetch_calendar wird aufgerufen
    with m.db() as con:
        row = con.execute("SELECT data FROM calendar_cache WHERE offer_id=?", (oid,)).fetchone()
        n_hist = con.execute("SELECT COUNT(*) c FROM calendar_history WHERE offer_id=?",
                             (oid,)).fetchone()["c"]
    assert json.loads(row["data"])["cheapest_price"] == 400
    # 2 Zeilen: Baseline-Heilung traegt den Vorwert (450) aus dem alten Cache nach,
    # dazu der neue Preis (400) -- so ist das Delta sofort in _calendar_moves sichtbar.
    assert n_hist == 2


def test_check_cheaper_date_first_call_has_no_cache_and_fetches(m, monkeypatch):
    oid = _add_offer(m, "https://example.invalid/h?duration=7")
    cal = _cal([("2027-03-08", 400)])
    calls = []
    monkeypatch.setattr(m, "fetch_calendar", lambda *a, **k: calls.append(1) or cal)
    monkeypatch.setattr(m, "_notify_ha", lambda *a, **k: None)
    monkeypatch.setattr(m, "_notify_telegram", lambda *a, **k: None)
    offer = {"id": oid, "url": "https://example.invalid/h?duration=7", "label": "", "hotel": ""}
    m._check_cheaper_date(offer, 500)
    assert calls == [1]
    with m.db() as con:
        assert con.execute("SELECT 1 FROM calendar_cache WHERE offer_id=?",
                           (oid,)).fetchone() is not None


def test_maybe_refresh_calendars_daily(m, monkeypatch):
    """Täglicher Kalender-Auto-Refresh: nur aktive Angebote mit Kalender älter
    24h, älteste zuerst; pausierte/frische bleiben unangetastet; abschaltbar."""
    old = _add_offer(m, "https://example.invalid/da?duration=7")
    fresh = _add_offer(m, "https://example.invalid/db?duration=7")
    paused = _add_offer(m, "https://example.invalid/dc?duration=7")
    now = int(time.time())
    with m.db() as con:
        con.execute("INSERT INTO calendar_cache (offer_id, ts, data) VALUES (?,?,?)",
                    (old, now - 90000, "{}"))       # >24h alt
        con.execute("INSERT INTO calendar_cache (offer_id, ts, data) VALUES (?,?,?)",
                    (fresh, now - 3600, "{}"))      # frisch
        con.execute("INSERT INTO calendar_cache (offer_id, ts, data) VALUES (?,?,?)",
                    (paused, now - 90000, "{}"))
        con.execute("UPDATE offers SET paused=1 WHERE id=?", (paused,))
    runs = []
    monkeypatch.setattr(m, "_run_calendar", lambda oid: runs.append(oid))
    m._maybe_refresh_calendars()
    assert runs == [old]

    runs.clear()
    monkeypatch.setattr(m, "load_config", lambda: {"calendar_daily_refresh": False})
    m._maybe_refresh_calendars()
    assert runs == []


def test_delete_offer_removes_calendar_history(m):
    oid = _add_offer(m, "https://example.invalid/i?duration=7")
    with m.db() as con:
        m._store_calendar_snapshot(con, oid, _cal([("2027-05-01", 500)]))
        m._store_calendar_snapshot(con, oid, _cal([("2027-05-01", 520)]))
    c = m.app.test_client()
    r = c.delete(f"/api/offers/{oid}", headers=ING)
    assert r.status_code == 200
    with m.db() as con:
        n = con.execute("SELECT COUNT(*) c FROM calendar_history WHERE offer_id=?",
                        (oid,)).fetchone()["c"]
    assert n == 0


def test_reset_offer_removes_calendar_history(m):
    oid = _add_offer(m, "https://example.invalid/j?duration=7")
    with m.db() as con:
        m._store_calendar_snapshot(con, oid, _cal([("2027-05-01", 500)]))
        m._store_calendar_snapshot(con, oid, _cal([("2027-05-01", 520)]))
    c = m.app.test_client()
    r = c.post(f"/api/reset/{oid}", headers=ING)
    assert r.status_code == 200
    with m.db() as con:
        n = con.execute("SELECT COUNT(*) c FROM calendar_history WHERE offer_id=?",
                        (oid,)).fetchone()["c"]
    assert n == 0


def test_api_calendar_day_route_returns_points(m):
    oid = _add_offer(m, "https://example.invalid/k?duration=7")
    with m.db() as con:
        m._store_calendar_snapshot(con, oid, _cal([("2027-05-01", 500)]))
        m._store_calendar_snapshot(con, oid, _cal([("2027-05-01", 520)]))
    c = m.app.test_client()
    r = c.get(f"/api/calendar/{oid}/day/2027-05-01", headers=ING)
    assert r.status_code == 200
    d = r.get_json()
    assert d["date"] == "2027-05-01"
    assert [p["price"] for p in d["points"]] == [500, 520]


def test_api_calendar_day_route_validates_date_format(m):
    oid = _add_offer(m, "https://example.invalid/l?duration=7")
    c = m.app.test_client()
    r = c.get(f"/api/calendar/{oid}/day/not-a-date", headers=ING)
    assert r.status_code == 400
    r2 = c.get("/api/calendar/999999/day/2027-05-01", headers=ING)
    assert r2.status_code == 404


def test_calendar_payload_includes_moves_and_top_moves(m):
    oid = _add_offer(m, "https://example.invalid/n?duration=7")
    with m.db() as con:
        m._store_calendar_snapshot(con, oid, _cal([("2027-05-01", 500), ("2027-05-02", 500)]))
        m._store_calendar_snapshot(con, oid, _cal([("2027-05-01", 500), ("2027-05-02", 560)]))
    out = m._calendar_payload(oid)
    assert out["status"] == "done"
    assert set(out["moves"]) == {"2027-05-02"}
    assert out["top_moves"][0]["date"] == "2027-05-02"


def test_backup_zip_contains_calendar_history_per_offer(m):
    oid = _add_offer(m, "https://example.invalid/o?duration=7")
    with m.db() as con:
        m._store_calendar_snapshot(con, oid, _cal([("2027-05-01", 500)]))
        m._store_calendar_snapshot(con, oid, _cal([("2027-05-01", 520)]))
    c = m.app.test_client()
    b = c.get("/api/backup", headers=ING)
    assert b.status_code == 200
    data = json.loads(zipfile.ZipFile(io.BytesIO(b.data)).read("data.json"))
    offer = next(o for o in data["offers"] if o["url"] == "https://example.invalid/o?duration=7")
    assert len(offer["calendar_history"]) == 2
    assert [h["price"] for h in offer["calendar_history"]] == [500, 520]


def test_restore_reimports_calendar_history(m):
    url = "https://www.tui.com/x/1/offer/?duration=7"   # muss echte tui.com-URL sein (_valid_tui_url)
    oid = _add_offer(m, url)
    with m.db() as con:
        m._store_calendar_snapshot(con, oid, _cal([("2027-05-01", 500)]))
        m._store_calendar_snapshot(con, oid, _cal([("2027-05-01", 520)]))
    c = m.app.test_client()
    b = c.get("/api/backup", headers=ING)

    with m.db() as con:
        con.execute("DELETE FROM offers")   # simuliert Restore auf frischem System
        con.execute("DELETE FROM calendar_history")

    rr = c.post("/api/restore", headers=ING,
                data={"file": (io.BytesIO(b.data), "backup.zip")},
                content_type="multipart/form-data")
    assert rr.status_code == 200
    with m.db() as con:
        new_oid = con.execute(
            "SELECT id FROM offers WHERE url=?", (url,)).fetchone()["id"]
        rows = con.execute("SELECT price FROM calendar_history WHERE offer_id=? ORDER BY ts",
                           (new_oid,)).fetchall()
    assert [r["price"] for r in rows] == [500, 520]


def test_calendar_alert_set_after_move_and_cleared_on_view(m):
    """Der 'Kalender'-Button soll aufleuchten, sobald sich seit dem letzten Öffnen
    ein Preis im Kalender geändert hat, und wieder erlöschen, sobald der Kalender
    angesehen wurde (GET /api/calendar/<id> mit status=done markiert als gesehen)."""
    oid = _add_offer(m, "https://example.invalid/q?duration=7")
    with m.db() as con:
        m._store_calendar_snapshot(con, oid, _cal([("2027-05-01", 500)]))
    offers = m._collect_offers()
    assert next(o for o in offers if o["id"] == oid)["calendar_alert"] is False

    with m.db() as con:
        m._store_calendar_snapshot(con, oid, _cal([("2027-05-01", 540)]))   # Preis geändert
    offers = m._collect_offers()
    assert next(o for o in offers if o["id"] == oid)["calendar_alert"] is True

    c = m.app.test_client()
    r = c.get(f"/api/calendar/{oid}", headers=ING)
    assert r.status_code == 200
    assert r.get_json()["status"] == "done"

    offers = m._collect_offers()
    assert next(o for o in offers if o["id"] == oid)["calendar_alert"] is False   # gesehen -> erloschen
