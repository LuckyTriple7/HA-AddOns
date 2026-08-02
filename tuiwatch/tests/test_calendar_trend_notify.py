"""Tests für die Benachrichtigung bei Kalender-Preisänderungen (HA/Telegram/Digest):
`_check_calendar_trend_alert`, `_month_name_de`/`_format_month_list_de`,
`_calendar_moves_since`, sowie die neue Digest-Kategorie "Kalenderpreise geändert".
Kein Netz nötig: `fetch_calendar`/`_notify_ha`/`_notify_telegram` werden gemonkeypatcht."""
import importlib
import time

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


def _add_offer(m, url, label="", hotel="Test-Hotel", return_date="2027-05-15"):
    now = int(time.time())
    with m.db() as con:
        con.execute(
            "INSERT INTO offers (url, hotel, label, region, country, return_date, created) "
            "VALUES (?,?,?,?,?,?,?)",
            (url, hotel, label, "Kanaren", "Spanien", return_date, now))
        return con.execute("SELECT id FROM offers WHERE url=?", (url,)).fetchone()["id"]


def _cal(days, **extra):
    out = {"ok": True, "currency": "EUR", "window_start": days[0][0],
           "window_end": days[-1][0], "duration": 7,
           "days": [{"date": d, "price": p} for d, p in days],
           "tracked_date": days[0][0], "tracked_price": days[0][1],
           "cheapest_date": days[0][0], "cheapest_price": days[0][1]}
    out.update(extra)
    return out


def _mock_notify(m, monkeypatch):
    sink = []
    monkeypatch.setattr(m, "_notify_ha", lambda title, msg, tag, muted=False: sink.append(("ha", title, msg, tag)))
    monkeypatch.setattr(m, "_notify_telegram", lambda text, muted=False: sink.append(("tg", text)))
    return sink


def test_month_name_de():
    import app as m
    assert m._month_name_de("2027-05") == "Mai 2027"
    assert m._month_name_de("2027-12") == "Dezember 2027"


def test_format_month_list_de():
    import app as m
    assert m._format_month_list_de(["2027-05"]) == "Mai 2027"
    assert m._format_month_list_de(["2027-05", "2027-06"]) == "Mai 2027 und Juni 2027"
    assert m._format_month_list_de(["2027-05", "2027-06", "2027-08"]) == \
        "Mai 2027, Juni 2027 und August 2027"


def test_calendar_trend_alert_skips_empty_changes(m, monkeypatch):
    oid = _add_offer(m, "https://example.invalid/a?duration=7")
    sink = _mock_notify(m, monkeypatch)
    m._check_calendar_trend_alert(oid, [])
    assert sink == []


def test_calendar_trend_alert_respects_config_flag(m, monkeypatch):
    oid = _add_offer(m, "https://example.invalid/b?duration=7")
    sink = _mock_notify(m, monkeypatch)
    monkeypatch.setattr(m, "load_config", lambda: {"notify_calendar_trend": False})
    m._check_calendar_trend_alert(oid, ["2027-05-02"])
    assert sink == []


def test_calendar_trend_alert_sends_hotel_and_month_only(m, monkeypatch):
    oid = _add_offer(m, "https://example.invalid/c?duration=7", hotel="Strandhotel Sonne")
    sink = _mock_notify(m, monkeypatch)
    # calendar_trend_min_diff:0 = Schwelle aus — dieser Test prüft nur das Nachrichten-
    # format, es werden keine echten calendar_history-Zeilen (mit Delta) angelegt.
    monkeypatch.setattr(m, "load_config", lambda: {"notify_calendar_trend": True,
                                                     "calendar_trend_min_diff": 0})
    m._check_calendar_trend_alert(oid, ["2027-05-02", "2027-06-10"])
    assert len(sink) == 2
    kinds = {e[0] for e in sink}
    assert kinds == {"ha", "tg"}
    for e in sink:
        text = e[2] if e[0] == "ha" else e[1]
        assert "Strandhotel Sonne" in text
        assert "Mai 2027 und Juni 2027" in text
        assert "2027-05-02" not in text and "2027-06-10" not in text   # kein genaues Datum
        assert "€" not in text                                        # kein Preis


def test_calendar_trend_alert_filters_small_moves_below_default_threshold(m, monkeypatch):
    oid = _add_offer(m, "https://example.invalid/g?duration=7", hotel="Kleinpreis-Hotel")
    sink = _mock_notify(m, monkeypatch)
    monkeypatch.setattr(m, "load_config", lambda: {"notify_calendar_trend": True})  # default min_diff 20
    with m.db() as con:
        m._store_calendar_snapshot(con, oid, _cal([("2027-05-01", 2100)]))
        changed = m._store_calendar_snapshot(con, oid, _cal([("2027-05-01", 2110)]))  # nur +10 €
    m._check_calendar_trend_alert(oid, changed)
    assert sink == []


def test_calendar_trend_alert_min_diff_zero_disables_filter(m, monkeypatch):
    oid = _add_offer(m, "https://example.invalid/h?duration=7", hotel="Kleinpreis-Hotel-2")
    sink = _mock_notify(m, monkeypatch)
    monkeypatch.setattr(m, "load_config", lambda: {"notify_calendar_trend": True,
                                                     "calendar_trend_min_diff": 0})
    with m.db() as con:
        m._store_calendar_snapshot(con, oid, _cal([("2027-05-01", 2100)]))
        changed = m._store_calendar_snapshot(con, oid, _cal([("2027-05-01", 2110)]))  # nur +10 €
    m._check_calendar_trend_alert(oid, changed)
    assert len(sink) == 2


def test_calendar_trend_alert_passes_moves_above_threshold(m, monkeypatch):
    oid = _add_offer(m, "https://example.invalid/i?duration=7", hotel="Großpreis-Hotel")
    sink = _mock_notify(m, monkeypatch)
    monkeypatch.setattr(m, "load_config", lambda: {"notify_calendar_trend": True})  # default min_diff 20
    with m.db() as con:
        m._store_calendar_snapshot(con, oid, _cal([("2027-05-01", 2100)]))
        changed = m._store_calendar_snapshot(con, oid, _cal([("2027-05-01", 2150)]))  # +50 €
    m._check_calendar_trend_alert(oid, changed)
    assert len(sink) == 2


def test_run_calendar_notifies_only_on_real_change(m, monkeypatch):
    oid = _add_offer(m, "https://example.invalid/d?duration=7")
    sink = _mock_notify(m, monkeypatch)
    monkeypatch.setattr(m, "load_config", lambda: {"notify_calendar_trend": True})

    monkeypatch.setattr(m, "fetch_calendar", lambda *a, **k: _cal(
        [("2027-05-01", 500), ("2027-05-02", 520)]))
    m._run_calendar(oid)
    assert sink == []   # Baseline, keine Benachrichtigung

    monkeypatch.setattr(m, "fetch_calendar", lambda *a, **k: _cal(
        [("2027-05-01", 500), ("2027-05-02", 560)]))   # 05-02 geändert
    m._run_calendar(oid)
    assert len(sink) == 2   # genau ein Notify-Paar (ha+tg)


def test_calendar_moves_since_excludes_first_sighting(m):
    oid = _add_offer(m, "https://example.invalid/e?duration=7")
    with m.db() as con:
        m._store_calendar_snapshot(con, oid, _cal([("2027-05-01", 500)]))
        old_since = int(time.time()) - 3600
        m._store_calendar_snapshot(con, oid, _cal([("2027-05-01", 540)]))   # echte Änderung
        m._store_calendar_snapshot(con, oid, _cal([("2027-05-01", 540), ("2027-05-02", 400)]))  # neuer Tag
        months = m._calendar_moves_since(con, oid, old_since)
    assert months == ["2027-05"]   # nur die echte Änderung an 05-01, nicht die Erstsichtung von 05-02

    with m.db() as con:
        future_since = int(time.time()) + 3600
        assert m._calendar_moves_since(con, oid, future_since) == []   # außerhalb des Fensters


def test_price_change_triggers_calendar_refresh_and_trend_alert(m, monkeypatch):
    """End-to-End über check_offer: beim ersten Check eines neuen Angebots wird der
    Kalender initial abgerufen (über _check_cheaper_date, kein Cache vorhanden).
    Bewegt sich später der getrackte Preis, wird der Kalender per force_refresh
    sofort neu abgerufen (TTL-Bypass) — inkl. History/Delta und Kalender-Alarm."""
    oid = _add_offer(m, "https://example.invalid/r?duration=7", hotel="Refresh-Hotel")
    sink = _mock_notify(m, monkeypatch)
    monkeypatch.setattr(m, "fetch_hotel_image", lambda url, **k: "")
    monkeypatch.setattr(m, "fetch_price", lambda url, **k: {
        "ok": True, "price": 1999, "region": "Kanaren", "country": "Spanien",
        "return_date": "2027-05-14"})
    cal_calls = []
    cal_holder = {"cal": _cal([("2027-05-03", 1999)])}
    monkeypatch.setattr(m, "fetch_calendar",
                        lambda *a, **k: cal_calls.append(1) or cal_holder["cal"])

    m.check_offer(oid)              # erster Check eines neuen Angebots
    assert cal_calls == [1]         # Kalender wird initial mit abgerufen (kein Cache)

    cal_holder["cal"] = _cal([("2027-05-03", 2026)])
    monkeypatch.setattr(m, "fetch_price", lambda url, **k: {
        "ok": True, "price": 2026, "region": "Kanaren", "country": "Spanien",
        "return_date": "2027-05-14"})
    m.check_offer(oid)              # Preis 1999 -> 2026: Kalender muss nachziehen
    assert cal_calls == [1, 1]      # genau EIN Refresh trotz frischer TTL
    with m.db() as con:
        moves = m._calendar_moves(con, oid)
    assert moves["2027-05-03"]["delta"] == 27
    assert any(e[0] == "ha" and e[3] == f"caltrend_{oid}" for e in sink)   # Kalender-Alarm kam


def test_digest_includes_calendar_moves_section(m, monkeypatch):
    oid = _add_offer(m, "https://example.invalid/f?duration=7", hotel="Berghotel Alpin")
    monkeypatch.setattr(m, "fetch_price", lambda url, **k: {
        "ok": True, "price": 900, "region": "Kanaren", "country": "Spanien",
        "return_date": "2027-05-15"})
    monkeypatch.setattr(m, "fetch_hotel_image", lambda url, **k: "")
    m.check_offer(oid)   # damit das Angebot einen Preis hat (Digest filtert sonst raus)

    with m.db() as con:
        m._store_calendar_snapshot(con, oid, _cal([("2027-05-01", 500)]))
        m._store_calendar_snapshot(con, oid, _cal([("2027-05-01", 540)]))

    digest = m._build_digest()
    assert digest is not None
    assert "Kalenderpreise geändert" in digest["text"]
    assert "Berghotel Alpin" in digest["text"]
    assert "Mai 2027" in digest["text"]
    assert "Kalenderpreise geändert" in digest["html"]
    assert "Berghotel Alpin" in digest["html"]
