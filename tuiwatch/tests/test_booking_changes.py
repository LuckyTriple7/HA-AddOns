"""Tests für den Buchungsdetails-Vergleich (_check_booking_changes):
Flugzeiten-/Klassen-Änderung und Errata-Änderung melden, Erstbefüllung still."""
import importlib
import json
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
    mod.TRIPS_DIR = str(tmp_path / "trips")
    mod.init_db()
    mod._ha, mod._tg = [], []
    monkeypatch.setattr(mod, "_notify_ha", lambda t, msg, tag, muted=False: mod._ha.append(msg))
    monkeypatch.setattr(mod, "_notify_telegram", lambda t, muted=False: mod._tg.append(t))
    return mod


SEG_OLD = {"out": [{"dep": "STR", "arr": "RHO", "start": "2026-10-19T06:55",
                    "end": "2026-10-19T11:00", "airline": "X3", "number": "4706",
                    "cls": "Y", "fare": ""}],
           "ret": [{"dep": "RHO", "arr": "STR", "start": "2026-10-28T11:05",
                    "end": "2026-10-28T13:15", "airline": "X3", "number": "4707",
                    "cls": "Y", "fare": ""}]}


def _mk_offer(m, **cols):
    with m.db() as con:
        cur = con.execute("INSERT INTO offers (url, hotel, created) VALUES (?,?,?)",
                          ("https://www.tui.com/x", "Hotel X", int(time.time())))
        oid = cur.lastrowid
        for k, v in cols.items():
            con.execute(f"UPDATE offers SET {k}=? WHERE id=?", (v, oid))
        return dict(con.execute("SELECT * FROM offers WHERE id=?", (oid,)).fetchone())


def test_first_fill_is_silent_but_stored(m):
    offer = _mk_offer(m)
    m._check_booking_changes(offer, {"flight_segments": SEG_OLD,
                                     "errata": ["Hinweis A"],
                                     "hotel_supplier": "DBH/MTS",
                                     "flight_flags": {"charter": True, "seat": True, "svc": True}})
    assert m._ha == [] and m._tg == []
    with m.db() as con:
        row = dict(con.execute("SELECT * FROM offers WHERE id=?", (offer["id"],)).fetchone())
    assert json.loads(row["flight_segments"])["out"][0]["number"] == "4706"
    assert json.loads(row["errata"]) == ["Hinweis A"]
    assert row["hotel_supplier"] == "DBH/MTS"
    assert json.loads(row["flight_flags"])["charter"] is True


def test_flight_time_change_notifies_once(m):
    offer = _mk_offer(m, flight_segments=json.dumps(SEG_OLD, ensure_ascii=False, sort_keys=True))
    new = json.loads(json.dumps(SEG_OLD))
    new["out"][0]["start"] = "2026-10-19T14:30"   # Hinflug verschoben
    new["out"][0]["number"] = "4712"
    m._check_booking_changes(offer, {"flight_segments": new})
    assert len(m._ha) == 1
    assert "Hinflug geändert" in m._ha[0]
    assert "06:55" in m._ha[0] and "14:30" in m._ha[0]
    # Verlauf-Marker protokolliert
    with m.db() as con:
        ev = con.execute("SELECT type, text FROM offer_events WHERE offer_id=?",
                         (offer["id"],)).fetchall()
    assert ev and ev[0]["type"] == "booking"
    # zweiter Lauf mit identischem (gespeichertem) Stand → still
    with m.db() as con:
        offer2 = dict(con.execute("SELECT * FROM offers WHERE id=?", (offer["id"],)).fetchone())
    m._check_booking_changes(offer2, {"flight_segments": new})
    assert len(m._ha) == 1


def test_class_change_and_errata_change(m):
    offer = _mk_offer(m, flight_segments=json.dumps(SEG_OLD, ensure_ascii=False, sort_keys=True),
                      errata=json.dumps(["Hinweis A"], ensure_ascii=False))
    new = json.loads(json.dumps(SEG_OLD))
    new["ret"][0]["cls"] = "K"                    # nur Buchungsklasse wechselt
    m._check_booking_changes(offer, {"flight_segments": new,
                                     "errata": ["Hinweis A", "Neuer Hinweis B"]})
    assert len(m._ha) == 1
    assert "Rückflug geändert" in m._ha[0] and "Kl. K" in m._ha[0]
    assert "Errata" in m._ha[0]


def test_option_off_suppresses_notification(m, monkeypatch):
    monkeypatch.setattr(m, "load_config", lambda: {"notify_booking_changes": False})
    offer = _mk_offer(m, flight_segments=json.dumps(SEG_OLD, ensure_ascii=False, sort_keys=True))
    new = json.loads(json.dumps(SEG_OLD))
    new["out"][0]["start"] = "2026-10-19T20:00"
    m._check_booking_changes(offer, {"flight_segments": new})
    assert m._ha == []
    # gespeichert wird trotzdem
    with m.db() as con:
        row = con.execute("SELECT flight_segments FROM offers WHERE id=?",
                          (offer["id"],)).fetchone()
    assert "20:00" in row["flight_segments"]
