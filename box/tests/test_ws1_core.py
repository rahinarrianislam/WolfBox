import importlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from wolfbox.store import Store


def module(name):
    try:
        return importlib.import_module(f"wolfbox.{name}")
    except ImportError:
        pytest.fail(f"WS1 module {name} must exist")


def test_store_atomic_history_and_student_isolation(tmp_path):
    store = Store(tmp_path / "alex")
    store.save_profile({"student_id": "alex"})
    assert Store(tmp_path / "alex").load_profile()["student_id"] == "alex"
    assert Store(tmp_path / "sam").load_profile() == {}
    for rid, assignment in [("r_1", "hw4"), ("r_2", "hw5")]:
        store.save_run(
            {
                "run_id": rid,
                "ts": "2026-10-31T12:00:00Z",
                "assignment": assignment,
                "status": "running",
            }
        )
    store.save_run(
        {
            "run_id": "r_1",
            "ts": "2026-10-31T12:00:00Z",
            "assignment": "hw4",
            "status": "done",
        }
    )
    assert len(store.read_text("runs.jsonl").splitlines()) == 2
    assert store.get_run("r_1")["status"] == "done"
    assert [r["run_id"] for r in store.list_runs()] == ["r_2", "r_1"]
    assert [r["run_id"] for r in store.list_runs(assignment="hw4")] == ["r_1"]
    with pytest.raises(ValueError):
        store.write_text("../escape", "no")
    (store.data_dir / "link").symlink_to(tmp_path / "sam", target_is_directory=True)
    with pytest.raises(ValueError):
        store.write_text("link/escape", "no")


def test_protocol_plain_text_and_invalid_envelopes():
    protocol = module("protocol")
    assert protocol.parse("Why?") == {"type": "ask", "text": "Why?"}
    assert protocol.parse('{"v":1,"type":"init","name":"Alex"}')["name"] == "Alex"
    for raw in ["[]", "null", '"hello"', "{}", '{"v":2,"type":"init"}', '{"type":4}']:
        with pytest.raises(ValueError):
            protocol.parse(raw)
    assert protocol.success({"created": True}) == {"ok": True, "created": True}
    assert protocol.error("bad") == {"ok": False, "error": "bad"}


def test_nudge_consecutive_time_and_resets():
    compute = module("nudge").compute
    now = datetime(2026, 10, 31, 12, tzinfo=UTC)

    def run(minutes, failed=True):
        return {
            "ts": (now - timedelta(minutes=minutes)).isoformat(),
            "status": "done",
            "failed": [{"test": "test_last_index"}] if failed else [],
        }

    streak = [run(i) for i in range(5)]
    assert compute(streak, now, 30)["active"]
    assert "5" in compute(list(reversed(streak)), now, 30)["reason"]
    assert compute([run(31), run(2)], now, 30)["active"]
    assert not compute([run(31), run(3, False), run(2)], now, 30)["active"]
    assert not compute([run(31), run(0, False)], now, 30)["active"]
    assert not compute([run(2)], now, 30)["active"]
    assert compute([], now, 30) == {"active": False, "reason": None}


def test_router_init_state_seed_reset_and_assignments(tmp_path, monkeypatch):
    dispatch = module("router").dispatch
    store = Store(tmp_path)
    assert dispatch(store, {"type": "init", "student_id": "alex", "name": "Alex"}) == {
        "ok": True,
        "created": True,
    }
    store.write_text("repo/hw4/hw4.py", "# student's edits")
    assert not dispatch(store, {"type": "init", "student_id": "sam", "name": "Sam"})[
        "created"
    ]
    state = dispatch(store, {"type": "get_state"})
    assert state["student_id"] == "alex"
    assert state["code"] == "# student's edits"
    assert state["assignment"] == "hw4"
    assert state["nudge"] == {"active": False, "reason": None}
    assert state["llm"]["active_backend"] == "fake"
    assignments = dispatch(store, {"type": "list_assignments"})["assignments"]
    assert assignments == [
        {
            "id": "hw4",
            "title": "HW4: list utilities",
            "due": None,
            "has_tests": True,
            "source": "template",
        }
    ]
    assert not dispatch(store, {"type": "seed", "files": {"x": "x"}})["ok"]
    assert not dispatch(store, {"type": "reset"})["ok"]
    monkeypatch.setenv("ALLOW_SEED", "1")
    assert not dispatch(store, {"type": "seed", "files": {"../x": "x"}})["ok"]
    assert (
        dispatch(store, {"type": "seed", "files": {"extra.txt": "hi"}})["written"] == 1
    )
    assert dispatch(store, {"type": "reset"})["ok"]
    assert not store.path("extra.txt").exists()
    assert store.load_profile()["name"] == "Alex"
    assert "last_n" in store.read_text("repo/hw4/hw4.py")
    assert not dispatch(store, {"type": "unknown"})["ok"]


def test_synced_metadata_and_default_assignment(tmp_path):
    dispatch = module("router").dispatch
    store = Store(tmp_path)
    for assignment, due in [
        ("hw5", "2026-11-01T00:00:00Z"),
        ("hw6", "2026-11-06T00:00:00Z"),
    ]:
        store.write_text(f"repo/{assignment}/{assignment}.py", "# code")
        store.write_text(f"repo/{assignment}/test_{assignment}.py", "")
        store.write_json(
            f"courses/csc116/docs/{assignment}/meta.json",
            {"title": assignment.upper(), "deadlines": [{"due": due}]},
        )
    state = dispatch(store, {"type": "get_state"})
    assert state["assignment"] == "hw6"
    items = dispatch(store, {"type": "list_assignments"})["assignments"]
    assert items[0]["source"] == "sync"
    assert items[0]["title"] == "HW5"
    assert items[0]["due"] == "2026-11-01T00:00:00Z"


@pytest.mark.parametrize(
    "fixture,failed", [("hw4_buggy.py", ["test_last_index"]), ("hw4_correct.py", [])]
)
def test_runner_real_pytest_and_snapshot(tmp_path, fixture, failed):
    dispatch = module("router").dispatch
    runner = module("runner")
    store = Store(tmp_path)
    dispatch(store, {"type": "init", "student_id": "alex", "name": "Alex"})
    source = (Path(__file__).parent / "fixtures" / fixture).read_text()
    result = dispatch(store, {"type": "submit_code", "files": {"hw4.py": source}})
    assert result["ok"] and result["status"] == "running"
    runner.wait(result["run_id"], timeout=25)
    run = store.get_run(result["run_id"])
    assert run["status"] == "done", run
    assert [f["test"] for f in run["failed"]] == failed
    assert len(run["passed"]) == 6 - len(failed)
    assert all(len(f["message"]) <= 400 for f in run["failed"])
    assert run["hint_status"] in {"failed", "ready"}
    assert run["duration_ms"] > 0
    assert store.read_text(f"snapshots/{run['run_id']}/hw4.py") == source
    assert set(run) == {
        "run_id",
        "ts",
        "assignment",
        "status",
        "passed",
        "failed",
        "duration_ms",
        "tags",
        "hint",
        "hint_status",
        "related_past",
        "llm",
    }
    assert (
        dispatch(store, {"type": "get_run", "run_id": run["run_id"]})["run"]["run_id"]
        == run["run_id"]
    )
    assert "code" not in dispatch(store, {"type": "list_runs"})["runs"][0]


def test_app_chat_round_trip(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = module("main").create_app()
    with TestClient(app) as client:
        assert client.get("/health").json() == {"ok": True}
        assert tmp_path.joinpath("repo/hw4/hw4.py").exists()

        def chat(payload):
            response = client.post(
                "/chat", json={"message": json.dumps(payload), "source": "test"}
            )
            assert response.status_code == 200
            assert isinstance(response.json()["response"], str)
            return json.loads(response.json()["response"])

        assert chat({"type": "init", "student_id": "alex", "name": "Alex"})["created"]
        src = (
            Path(__file__).with_name("fixtures").joinpath("hw4_correct.py").read_text()
        )
        result = chat({"type": "submit_code", "files": {"hw4.py": src}})
        import time

        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            run = chat({"type": "get_run", "run_id": result["run_id"]})["run"]
            if run["status"] != "running" and run["hint_status"] != "pending":
                break
            time.sleep(0.02)
        assert run["status"] == "done" and len(run["passed"]) == 6
        assert not chat({"type": "missing"})["ok"]
        assert not chat([])["ok"]
        assert client.get("/schedules").json() == [
            {"id": "sync", "cron": "*/15 * * * *", "prompt": '{"v":1,"type":"sync"}'}
        ]


def test_runner_reaps_completed_jobs(tmp_path):
    runner = module("runner")
    store = Store(tmp_path)
    store.write_text("repo/tiny/test_tiny.py", "def test_ok():\n    assert True\n")
    result = runner.submit_code(store, {"tiny.py": "x = 1"}, "tiny")
    # Use the actual worker to observe API-only callers that never call wait().
    thread, _ = runner._jobs[result["run_id"]]
    thread.join(25)
    assert not thread.is_alive()
    assert result["run_id"] not in runner._jobs
    runner.wait(result["run_id"], timeout=1)


@pytest.mark.parametrize(
    "code,timeout,expected",
    [
        ("import time\ndef test_slow():\n    time.sleep(10)\n", 0.3, "timed out"),
        ("import os\ndef test_crash():\n    os._exit(3)\n", 20, "exited 3"),
        ("def test_bad(:\n    pass\n", 20, "exited 2"),
    ],
)
def test_runner_timeout_crash_and_collection_error(
    tmp_path, monkeypatch, code, timeout, expected
):
    runner = module("runner")
    monkeypatch.setattr(runner, "TIMEOUT_SECONDS", timeout)
    store = Store(tmp_path)
    store.write_text("repo/tiny/test_tiny.py", code)
    result = runner.submit_code(store, {"tiny.py": "x = 1"}, "tiny")
    runner.wait(result["run_id"], timeout=25)
    run = store.get_run(result["run_id"])
    assert run["status"] == "error"
    assert expected in run["failed"][-1]["message"]
    assert run["hint_status"] in {"failed", "ready"}


def test_runner_snapshots_isolate_back_to_back_submissions(tmp_path):
    runner = module("runner")
    store = Store(tmp_path)
    store.write_text(
        "repo/tiny/test_tiny.py",
        "import time\nfrom tiny import answer\ndef test_answer():\n    time.sleep(0.2)\n    assert answer() == 42\n",
    )
    one = runner.submit_code(
        store, {"tiny.py": "def answer():\n    return 42\n"}, "tiny"
    )
    two = runner.submit_code(
        store, {"tiny.py": "def answer():\n    return 0\n"}, "tiny"
    )
    for result in (one, two):
        runner.wait(result["run_id"], timeout=25)
    assert store.get_run(one["run_id"])["passed"] == ["test_answer"]
    assert store.get_run(two["run_id"])["failed"][0]["test"] == "test_answer"


def test_submit_rejects_escaping_paths_before_writing_anything(tmp_path):
    runner = module("runner")
    store = Store(tmp_path)
    store.write_text("repo/tiny/tiny.py", "original")
    for path in ["../other.py", "/tmp/outside.py", "../../profile.json"]:
        with pytest.raises(ValueError):
            runner.submit_code(store, {"tiny.py": "changed", path: "escaped"}, "tiny")
        assert store.read_text("repo/tiny/tiny.py") == "original"


def test_lazy_feature_handlers_and_tutor_hooks(tmp_path, monkeypatch):
    import sys
    import types

    router = module("router")
    runner = module("runner")
    store = Store(tmp_path)
    router.init(store, {"student_id": "alex", "name": "Alex"})
    assert not router.dispatch(store, {"type": "late_handler"})["ok"]
    tutor = types.ModuleType("wolfbox.tutor")
    tutor.HANDLERS = {
        "late_handler": lambda store, payload: {
            "student": store.load_profile()["student_id"]
        }
    }

    def complete(store, run):
        run["hint"] = "Check the boundary. What index is last?"
        run["hint_status"] = "ready"
        store.save_run(run)

    tutor.on_run_complete = complete
    monkeypatch.setitem(sys.modules, "wolfbox.tutor", tutor)
    assert router.dispatch(store, {"type": "late_handler"}) == {
        "ok": True,
        "student": "alex",
    }
    store.write_text("repo/tiny/test_tiny.py", "def test_ok():\n    assert True\n")
    run_id = runner.submit_code(store, {"tiny.py": ""}, "tiny")["run_id"]
    runner.wait(run_id, timeout=25)
    assert store.get_run(run_id)["hint"].endswith("?")

    def broken(store, run):
        raise RuntimeError("tutor unavailable")

    tutor.on_run_complete = broken
    store.write_text("repo/tiny/test_tiny.py", "def test_bad():\n    assert False\n")
    run_id = runner.submit_code(store, {"tiny.py": ""}, "tiny")["run_id"]
    runner.wait(run_id, timeout=25)
    assert store.get_run(run_id)["hint_status"] == "failed"


def test_nudge_draft_and_llm_fallbacks(tmp_path, monkeypatch):
    import sys
    import types

    router = module("router")
    store = Store(tmp_path)
    router.init(store, {"student_id": "alex", "name": "Alex"})
    for i in range(5):
        store.save_run(
            {
                "run_id": f"r_{i}",
                "assignment": "hw4",
                "status": "done",
                "ts": f"2026-10-31T12:0{i}:00Z",
                "failed": [{"test": "test_last_index"}],
            }
        )
    tutor = types.ModuleType("wolfbox.tutor")
    tutor.HANDLERS = {}
    tutor.nudge_draft = lambda store, nudge, run: "Tutor draft"
    monkeypatch.setitem(sys.modules, "wolfbox.tutor", tutor)
    assert router.get_state(store, {})["nudge"]["draft"] == "Tutor draft"
    del tutor.nudge_draft
    assert "stuck" in router.get_state(store, {})["nudge"]["draft"]

    def broken(*args):
        raise RuntimeError("model offline")

    monkeypatch.setattr(router.gemma, "nudge_draft", broken)
    monkeypatch.setattr(router.gemma, "status", broken)
    state = router.get_state(store, {})
    assert state["nudge"]["draft"]
    assert state["llm"] == {
        "mode": "fake",
        "active_backend": "fake",
        "model": "fake",
        "online": False,
    }


def test_store_orders_runs_submitted_within_one_second(tmp_path, monkeypatch):
    import wolfbox.store as storage

    clock = iter(
        [
            datetime(2026, 10, 31, 12, 0, 0, 1, UTC),
            datetime(2026, 10, 31, 12, 0, 0, 2, UTC),
        ]
    )

    class Clock(datetime):
        @staticmethod
        def now(tz):
            return next(clock)

    monkeypatch.setattr(storage, "datetime", Clock)
    store = Store(tmp_path)
    for run_id in ["r_z", "r_a"]:
        store.save_run({"run_id": run_id, "ts": storage.now_iso(), "assignment": "hw4"})
    assert [run["run_id"] for run in store.list_runs()] == ["r_a", "r_z"]


def test_store_orders_seeded_and_fractional_timestamps(tmp_path):
    store = Store(tmp_path)
    store.save_run(
        {"run_id": "r_old", "ts": "2026-10-31T12:00:00Z", "assignment": "hw4"}
    )
    store.save_run(
        {"run_id": "r_new", "ts": "2026-10-31T12:00:00.000001Z", "assignment": "hw4"}
    )
    assert [run["run_id"] for run in store.list_runs()] == ["r_new", "r_old"]


def test_get_state_nudge_draft_has_a_response_deadline(tmp_path, monkeypatch):
    import sys
    import threading
    import time
    import types

    router = module("router")
    store = Store(tmp_path)
    router.init(store, {"student_id": "alex", "name": "Alex"})
    for i in range(5):
        store.save_run(
            {
                "run_id": f"r_{i}",
                "assignment": "hw4",
                "status": "done",
                "ts": f"2026-10-31T12:0{i}:00Z",
                "failed": [{"test": "test_last_index"}],
            }
        )
    released = threading.Event()
    tutor = types.ModuleType("wolfbox.tutor")
    tutor.HANDLERS = {}

    def slow_draft(*args):
        released.wait(2)
        return "Delayed draft"

    tutor.nudge_draft = slow_draft
    monkeypatch.setitem(sys.modules, "wolfbox.tutor", tutor)
    monkeypatch.setattr(router, "NUDGE_TIMEOUT_SECONDS", 0.03, raising=False)
    started = time.monotonic()
    try:
        state = router.get_state(store, {})
        assert time.monotonic() - started < 0.5
        assert state["nudge"]["active"] and state["nudge"]["draft"]
    finally:
        released.set()


def test_reset_waits_for_active_run_to_finish(tmp_path, monkeypatch):
    router = module("router")
    runner = module("runner")
    store = Store(tmp_path)
    router.init(store, {"student_id": "alex", "name": "Alex"})
    monkeypatch.setenv("ALLOW_SEED", "1")
    store.write_text(
        "repo/tiny/test_tiny.py",
        "import time\ndef test_ok():\n    time.sleep(0.1)\n    assert True\n",
    )
    run_id = runner.submit_code(store, {"tiny.py": ""}, "tiny")["run_id"]
    assert not router.dispatch(store, {"type": "reset"})["ok"]
    assert store.get_run(run_id) is not None
    runner.wait(run_id, timeout=25)
    assert router.dispatch(store, {"type": "reset"})["ok"]
    assert store.get_run(run_id) is None
    assert store.load_profile()["student_id"] == "alex"
