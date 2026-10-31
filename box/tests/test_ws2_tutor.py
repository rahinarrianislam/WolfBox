"""Tutor behavior through the shared Store, independent of WS1's router/runner."""

import json
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wolfbox import gemma
from wolfbox.store import Store


@pytest.fixture
def tutor(monkeypatch):
    monkeypatch.setenv("GEMMA_BACKEND", "fake")
    monkeypatch.delenv("GEMMA_FAKE", raising=False)
    from wolfbox import tutor

    return tutor


@pytest.fixture
def store(tmp_path):
    store = Store(tmp_path)
    store.write_text("repo/hw4/hw4.py", "def last(xs):\n    return xs[len(xs)]\n")
    return store


def failure(run_id="r4", assignment="hw4"):
    return {
        "run_id": run_id,
        "ts": "2026-10-31T12:00:00Z",
        "assignment": assignment,
        "status": "done",
        "passed": [],
        "failed": [{"test": "test_last_index", "message": "IndexError"}],
        "hint_status": "pending",
    }


def seed(store):
    store.save_profile(
        {
            "student_id": "alex",
            "name": "Alex",
            "mistake_counts": {"off_by_one": 4},
            "examples": {
                "off_by_one": [
                    {
                        "run_id": "r2",
                        "assignment": "hw2",
                        "note": "range(len(xs)+1) indexed past end",
                    }
                ]
            },
        }
    )


def test_seeded_tutor_cites_past_before_updating_profile(tutor, store):
    seed(store)
    run = failure()
    tutor.on_run_complete(store, run)
    saved = store.get_run("r4")
    assert "hw2" in saved["hint"]
    assert saved["hint"].endswith("?")
    assert len(saved["hint"].split()) <= 80
    assert saved["tags"] == ["off_by_one"]
    assert saved["hint_status"] == "ready"
    assert saved["llm"] == {"backend": "fake", "model": "fake"}
    assert saved["related_past"] == [
        {"run_id": "r2", "assignment": "hw2", "tag": "off_by_one"}
    ]
    profile = store.load_profile()
    assert profile["mistake_counts"]["off_by_one"] == 5
    assert profile["examples"]["off_by_one"][-1]["run_id"] == "r4"


def test_fresh_tutor_gives_generic_hint(tutor, store):
    tutor.on_run_complete(store, failure())
    run = store.get_run("r4")
    assert "hw2" not in run["hint"]
    assert "hw4" not in run["hint"]
    assert run["hint"].endswith("?")
    assert run["related_past"] == []
    assert store.load_profile()["mistake_counts"] == {"off_by_one": 1}


def test_profile_keeps_five_examples_and_filters_tags(tutor, store, monkeypatch):
    monkeypatch.setattr(
        gemma, "classify", lambda *a: ["off_by_one", "invented", "off_by_one"]
    )
    for i in range(7):
        tutor.on_run_complete(store, failure(f"r{i}"))
    profile = store.load_profile()
    assert profile["mistake_counts"] == {"off_by_one": 7}
    assert [e["run_id"] for e in profile["examples"]["off_by_one"]] == ["r6"]  # one per assignment
    assert store.get_run("r6")["tags"] == ["off_by_one"]


def test_all_pass_still_saves_run(tutor, store):
    run = failure()
    run["failed"] = []
    run["passed"] = ["test_last_index"]
    tutor.on_run_complete(store, run)
    saved = store.get_run("r4")
    assert saved["tags"] == []
    assert saved["hint"] is None
    assert saved["hint_status"] == "ready"
    assert store.load_profile() == {}


@pytest.mark.parametrize("broken_task", ["classify", "hint"])
def test_run_is_saved_with_fallback_when_gemma_fails(
    tutor, store, monkeypatch, broken_task
):
    def unavailable(*args):
        raise TimeoutError("offline")

    monkeypatch.setattr(gemma, broken_task, unavailable)
    tutor.on_run_complete(store, failure())
    saved = store.get_run("r4")
    assert saved["hint"].endswith("?")
    assert len(saved["hint"].split()) <= 80
    assert saved["llm"]["backend"] == "fallback"
    assert saved["hint_status"] == "ready"


def test_ask_uses_code_and_history(tutor, store):
    seed(store)
    tutor.on_run_complete(store, failure())
    response = tutor.HANDLERS["ask"](store, {"text": "Why is the last index failing?"})
    assert "hw2" in response["reply"]
    assert response["reply"].endswith("?")
    assert "ok" not in response


def test_ta_summary_cache_invalidates_for_new_run(tutor, store, monkeypatch):
    tutor.on_run_complete(store, failure())
    first = tutor.HANDLERS["ta_summary"](store, {})
    assert "Where they are" in first["markdown"]

    def unavailable(*args):
        raise AssertionError("cached summary should avoid model call")

    monkeypatch.setattr(gemma, "ta_summary", unavailable)
    assert tutor.HANDLERS["ta_summary"](store, {}) == first
    cache = store.read_json("ta_summary_cache.json")
    assert "r4" in json.dumps(cache)
    store.save_run(failure("r5"))
    second = tutor.HANDLERS["ta_summary"](store, {})
    assert second["markdown"] != first["markdown"]
    assert len(second["markdown"].split()) <= 200


def test_assignment_specific_summary_and_code(tutor, store, monkeypatch):
    store.save_run(failure("r4", "hw4"))
    store.save_run(failure("r5", "hw5"))
    seen = []

    def summary(profile, runs, code):
        seen.append((runs, code))
        return "Where they are: hw4\nWhat they tried: last index\nPatterns: boundaries\nSuggested opener: Which index?"

    monkeypatch.setattr(gemma, "ta_summary", summary)
    tutor.HANDLERS["ta_summary"](store, {"assignment": "hw4"})
    assert all(run["assignment"] == "hw4" for run in seen[0][0])
    assert "return xs[len(xs)]" in seen[0][1]


def test_ask_timeout_returns_fallback_promptly(tutor, store, monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(tutor, "CHAT_TIMEOUT", 0.05, raising=False)
    monkeypatch.setattr(gemma, "answer", lambda *a: (release.wait(2), "late?")[1])
    start = time.monotonic()
    try:
        reply = tutor.HANDLERS["ask"](store, {"text": "why?"})["reply"]
        assert time.monotonic() - start < 0.5
        assert reply.endswith("?")
        assert "late" not in reply
    finally:
        release.set()


def test_nudge_has_fallback(tutor, store, monkeypatch):
    def unavailable(*args):
        raise ConnectionError("offline")

    monkeypatch.setattr(gemma, "nudge_draft", unavailable)
    draft = tutor.nudge_draft(
        store, {"reason": "test_last_index failed 5 runs"}, failure()
    )
    assert "hw4" in draft
    assert len(draft.split()) <= 60


def test_default_assignment_uses_latest_due_workspace(tutor, store, monkeypatch):
    store.save_run(failure("r4", "hw4"))
    store.write_text("repo/hw4/test_hw4.py", "")
    store.write_text("repo/hw5/test_hw5.py", "")
    store.write_text("repo/hw5/hw5.py", "# current hw5 code")
    store.write_json(
        "courses/csc116/docs/hw4/meta.json",
        {
            "type": "assignment",
            "workspace": "repo/hw4",
            "deadlines": [{"due": "2026-10-20T23:59:00Z"}],
        },
    )
    store.write_json(
        "courses/csc116/docs/hw5/meta.json",
        {
            "type": "assignment",
            "workspace": "repo/hw5",
            "deadlines": [{"due": "2026-10-30T23:59:00Z"}],
        },
    )
    observed = []
    monkeypatch.setattr(
        gemma,
        "answer",
        lambda question, code, last, history: (
            observed.append((code, last)) or "What happens?"
        ),
    )
    tutor.HANDLERS["ask"](store, {"text": "What next?"})
    assert observed == [("# current hw5 code", None)]


def test_ta_summary_includes_snapshot_diffs(tutor, store, monkeypatch):
    store.save_run(failure("r4"))
    store.save_run(failure("r5"))
    store.write_text("snapshots/r4/hw4.py", "return xs[len(xs)]")
    store.write_text("snapshots/r5/hw4.py", "return xs[-1]")
    observed = []

    def summarize(profile, runs, code):
        observed.extend(runs)
        return "Where they are\nWhat they tried\nPatterns\nSuggested opener"

    monkeypatch.setattr(gemma, "ta_summary", summarize)
    tutor.HANDLERS["ta_summary"](store, {})
    assert "-return xs[len(xs)]" in observed[0]["code_diff"]
    assert "+return xs[-1]" in observed[0]["code_diff"]


def test_empty_ask_rejected(tutor, store):
    with pytest.raises(ValueError):
        tutor.HANDLERS["ask"](store, {"text": " "})
