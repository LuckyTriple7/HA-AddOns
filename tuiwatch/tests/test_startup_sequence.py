"""Start-Jobs laufen nacheinander, Dauer-Threads erst danach (0.117.6)."""
import importlib
import threading

import pytest

pytest.importorskip("flask")

ING = {"X-Ingress-Path": "/test"}


@pytest.fixture
def m(tmp_path, monkeypatch):
    monkeypatch.setenv("TUIWATCH_DATA", str(tmp_path))
    monkeypatch.setenv("TUIWATCH_BASE", str(tmp_path))
    try:
        mod = importlib.import_module("app")
    except Exception as exc:                     # pragma: no cover
        pytest.skip(f"app nicht importierbar: {exc}")
    importlib.reload(mod)
    monkeypatch.setattr(mod, "_trim_once", lambda auto=True: 0.0)
    return mod


def test_jobs_run_one_after_another_then_workers(m, monkeypatch):
    log, running = [], []

    def job(name, fail=False):
        def fn():
            running.append(name)
            assert len(running) == 1, "zwei Start-Jobs gleichzeitig"
            log.append(name)
            running.pop()
            if fail:
                raise RuntimeError("x")
        return fn
    monkeypatch.setattr(m, "_startup_jobs", lambda: [
        ("A", job("A"), True), ("B", job("B", fail=True), True),
        ("C", job("C"), False), ("D", job("D"), True)])
    started = threading.Event()

    def worker():
        log.append("worker")
        started.set()
    m._startup_sequence((worker,))
    assert started.wait(2)
    assert log == ["A", "B", "D", "worker"]
    states = [j["state"] for j in m._startup_state["jobs"]]
    assert states == ["done", "error", "skip", "done"]
    assert m._startup_state["active"] is False


def test_startup_endpoint(m):
    m._startup_state.update(active=True, jobs=[
        {"label": "Reiseziel-Index", "state": "run", "secs": None, "since": 0}])
    d = m.app.test_client().get("/api/startup", headers=ING).get_json()
    assert d["active"] is True and d["jobs"][0]["label"] == "Reiseziel-Index"
    assert m.app.test_client().get("/api/startup").status_code == 401
