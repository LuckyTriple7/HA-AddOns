"""Flugzeiten-Wächter (flight_watch.py): gebuchte Flüge gegen den Flugplan des
Heimatflughafens. Kein Netz — die Flugpläne werden gemonkeypatcht."""
import importlib
import json
import time
from datetime import date, timedelta

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


@pytest.fixture
def fw(m):
    import flight_watch
    return flight_watch


def _de(d: date) -> str:
    return d.strftime("%d.%m.%Y")


DEP = date.today() + timedelta(days=20)
RET = DEP + timedelta(days=10)


def _add_trip(m, fluege, code="T1"):
    with m.db() as con:
        con.execute(
            "INSERT INTO trips (booking_code, destination, start_date, end_date, data, created) "
            "VALUES (?,?,?,?,?,?)",
            (code, "Gran Canaria", DEP.isoformat(), RET.isoformat(),
             json.dumps({"fluege": fluege}), int(time.time())))
        return con.execute("SELECT id FROM trips WHERE booking_code=?", (code,)).fetchone()["id"]


HIN = {"typ": "Hinflug", "datum": _de(DEP), "abflug_zeit": "06:45", "ankunft_zeit": "10:50",
       "von": "Stuttgart (STR)", "nach": "Gran Canaria (LPA)", "flugnummer": "TUIfly X32168"}
RUECK = {"typ": "Rückflug", "datum": _de(RET), "abflug_zeit": "22:30", "ankunft_zeit": "03:40",
         "von": "Gran Canaria (LPA)", "nach": "Stuttgart (STR)", "flugnummer": "TUIfly X32169"}


def _row(direction, fno, other, dep, arr, days="täglich", till=None):
    return {"dir": direction, "key": None, "fno": fno, "other": other,
            "departure": dep, "arrival": arr, "weekdays_short": days,
            "date_from": (DEP - timedelta(days=60)).isoformat(),
            "date_till": (till or RET + timedelta(days=60)).isoformat()}


def _plan(monkeypatch, fw, rows):
    """Saisonplan STR ersetzen — gleiche Normalisierung wie im Modul."""
    def fake(airport):
        return [{"dir": r["dir"], "key": fw.parse_flight_no(r["fno"]), "other": r["other"],
                 "time": fw._hhmm(r["departure"] if r["dir"] == "departure" else r["arrival"]),
                 "days": fw._days(r["weekdays_short"]), "from": r["date_from"],
                 "till": r["date_till"]} for r in rows]
    monkeypatch.setattr(fw, "_seasonal_rows", fake)


def _sink(m, monkeypatch):
    sent = []
    monkeypatch.setattr(m, "_notify_ha", lambda title, msg, tag, muted=False: sent.append((title, msg)))
    monkeypatch.setattr(m, "_notify_telegram", lambda text, muted=False: None)
    return sent


def _status(m, tid):
    with m.db() as con:
        return {r["idx"]: dict(r) for r in con.execute(
            "SELECT * FROM trip_flight_checks WHERE trip_id=?", (tid,)).fetchall()}


def test_parse_flight_no(fw):
    assert fw.parse_flight_no("TUIfly X32168") == ("X3", 2168)
    assert fw.parse_flight_no("X3 2168") == ("X3", 2168)
    assert fw.parse_flight_no("Eurowings EW2648") == ("EW", 2648)
    assert fw.parse_flight_no("FR 0985") == ("FR", 985)
    assert fw.parse_flight_no("") is None


def test_unchanged_flights_are_ok_without_message(m, fw, monkeypatch):
    tid = _add_trip(m, [HIN, RUECK])
    _plan(monkeypatch, fw, [_row("departure", "X3 2168", "LPA", "06:45", "10:50"),
                            _row("arrival", "X3 2169", "LPA", "22:30", "03:40")])
    sent = _sink(m, monkeypatch)
    assert fw.check_trips() == 2
    st = _status(m, tid)
    assert st[0]["status"] == "ok" and st[1]["status"] == "ok"
    assert sent == []


def test_changed_time_notifies_once_then_all_clear(m, fw, monkeypatch):
    tid = _add_trip(m, [HIN])
    _plan(monkeypatch, fw, [_row("departure", "X3 2168", "LPA", "07:30", "11:35")])
    sent = _sink(m, monkeypatch)
    fw.check_trips()
    fw.check_trips()
    assert len(sent) == 1
    assert "Flugzeit geändert" in sent[0][0]
    assert "07:30" in sent[0][1] and "06:45" in sent[0][1]
    assert _status(m, tid)[0]["plan_time"] == "07:30"

    _plan(monkeypatch, fw, [_row("departure", "X3 2168", "LPA", "06:45", "10:50")])
    fw.check_trips()
    assert len(sent) == 2 and "wieder wie gebucht" in sent[1][0]


def test_missing_flight_needs_two_checks_and_names_alternatives(m, fw, monkeypatch):
    tid = _add_trip(m, [HIN])
    _plan(monkeypatch, fw, [_row("departure", "X3 2170", "LPA", "08:15", "12:20")])
    sent = _sink(m, monkeypatch)
    fw.check_trips()
    assert sent == [] and _status(m, tid)[0]["status"] == "missing"
    fw.check_trips()
    assert len(sent) == 1 and "nicht mehr im Flugplan" in sent[0][0]
    assert "X3 2170 08:15" in sent[0][1]


def test_date_beyond_published_plan_is_pending(m, fw, monkeypatch):
    tid = _add_trip(m, [HIN])
    _plan(monkeypatch, fw, [_row("departure", "X3 2170", "LPA", "08:15", "12:20",
                                 till=DEP - timedelta(days=5))])
    sent = _sink(m, monkeypatch)
    fw.check_trips()
    fw.check_trips()
    assert _status(m, tid)[0]["status"] == "pending"
    assert sent == []


def test_fra_arrival_matches_next_day_and_codeshare(m, fw, monkeypatch):
    rueck = dict(RUECK, nach="Frankfurt (FRA)", flugnummer="Condor DE1773")
    tid = _add_trip(m, [rueck])
    import fra_flights_client as F
    calls = []

    def fake(q, ft, df, dt, limit=300, verbose=False):
        calls.append((q, ft, df, dt))
        nxt = (RET + timedelta(days=1)).isoformat()
        return {"rows": [{"date": nxt, "time": "03:40", "flight_no": "AS 8965",
                          "codeshares": ["DE 1773"]}], "truncated": False}
    monkeypatch.setattr(F, "search_flights", fake)
    _sink(m, monkeypatch)
    fw.check_trips()
    assert calls and calls[0][:2] == ("LPA", "arrivals")
    assert _status(m, tid)[0]["status"] == "ok"


def test_unsupported_airport_and_past_flights(m, fw, monkeypatch):
    past = dict(HIN, datum=_de(date.today() - timedelta(days=1)))
    other = dict(HIN, von="Düsseldorf (DUS)")
    tid = _add_trip(m, [past, other])
    _plan(monkeypatch, fw, [])
    _sink(m, monkeypatch)
    assert fw.check_trips() == 1
    st = _status(m, tid)
    assert 0 not in st and st[1]["status"] == "unsupported"


def test_setting_off_skips_everything(m, fw, monkeypatch):
    _add_trip(m, [HIN])
    called = []
    monkeypatch.setattr(fw, "check_trips", lambda *a, **k: called.append(1) or 0)
    monkeypatch.setattr(m, "load_config", lambda: {"notify_flight_changes": False})
    fw.maybe_check_flights()
    assert called == []
    monkeypatch.setattr(m, "load_config", lambda: {})
    fw.maybe_check_flights()           # neue, ungeprüfte Reise → sofort
    assert called == [1]


def test_trip_detail_and_manual_check(m, fw, monkeypatch):
    tid = _add_trip(m, [HIN])
    _plan(monkeypatch, fw, [_row("departure", "X3 2168", "LPA", "07:30", "11:35")])
    _sink(m, monkeypatch)
    c = m.app.test_client()
    r = c.post(f"/api/trips/{tid}/flights/check", headers=ING)
    assert r.status_code == 200
    assert r.get_json()["flight_checks"][0]["status"] == "changed"
    d = c.get(f"/api/trips/{tid}", headers=ING).get_json()
    assert d["flight_checks"][0]["plan_time"] == "07:30"

    # Neu-Import mit anderer Flugnummer: der alte Stand gehört nicht mehr dazu
    with m.db() as con:
        con.execute("UPDATE trips SET data=? WHERE id=?",
                    (json.dumps({"fluege": [dict(HIN, flugnummer="TUIfly X32170")]}), tid))
    d = c.get(f"/api/trips/{tid}", headers=ING).get_json()
    assert d["flight_checks"] == []


def test_deleting_trip_removes_checks(m, fw, monkeypatch):
    tid = _add_trip(m, [HIN])
    _plan(monkeypatch, fw, [_row("departure", "X3 2168", "LPA", "06:45", "10:50")])
    _sink(m, monkeypatch)
    fw.check_trips()
    c = m.app.test_client()
    assert c.delete(f"/api/trips/{tid}", headers=ING).status_code == 200
    assert _status(m, tid) == {}
