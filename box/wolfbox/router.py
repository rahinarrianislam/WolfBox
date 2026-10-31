"""Envelope type -> handler. WS1 owns this file.

HANDLER CONVENTION (shared): a handler is `fn(store: Store, payload: dict) -> dict`. It returns the inner JSON
WITHOUT "ok"; the router adds {"ok": true}. Raise any exception for {"ok": false, "error": str(e)}.
Each feature module exposes a module-level dict `HANDLERS = {"<type>": fn}`; the router merges:
    wolfbox.router (core: init, get_state, submit_code, get_run, list_runs, list_assignments, seed, reset)
    wolfbox.tutor.HANDLERS            (WS2: ask, ta_summary)
    wolfbox.planner.handlers.HANDLERS (WS3: plan_get, plan_set_prefs, plan_solve)
    wolfbox.sync.handlers.HANDLERS    (WS8: sync, get_sync, list_docs, get_doc, deadlines)
Feature imports are wrapped in try/except ImportError so a missing workstream doesn't break the box.
"""

from __future__ import annotations

import importlib
import os
import shutil
import threading
from datetime import UTC, datetime
from pathlib import Path

from wolfbox import gemma, nudge, protocol, runner
from wolfbox.store import Store

TEMPLATE = Path(__file__).resolve().parents[1] / "assignments" / "hw4"
FEATURE_MODULES = ("wolfbox.tutor", "wolfbox.planner.handlers", "wolfbox.sync.handlers")
NUDGE_TIMEOUT_SECONDS = 20
DEFAULT_NUDGE_DRAFT = (
    "Hi! I'm stuck on this assignment. Could we go over the failing test?"
)


def ensure_template(store: Store):
    """Copy missing template files, preserving students' existing work."""
    for source in TEMPLATE.rglob("*"):
        if source.is_file() and "__pycache__" not in source.parts:
            relative = str(Path("repo/hw4") / source.relative_to(TEMPLATE))
            if not store.path(relative).exists():
                store.write_text(relative, source.read_text())


def init(store, payload):
    student_id, name = payload.get("student_id"), payload.get("name")
    if (
        not isinstance(student_id, str)
        or not student_id
        or not isinstance(name, str)
        or not name
    ):
        raise ValueError("init requires student_id and name")
    created = not store.path("profile.json").exists()
    if created:
        store.save_profile(
            {
                "student_id": student_id,
                "name": name,
                "course": "CSC 116",
                "mistake_counts": {},
                "examples": {},
            }
        )
    ensure_template(store)
    return {"created": created}


def list_assignments(store, payload):
    assignments = []
    repo = store.path("repo")
    for workspace in sorted(repo.iterdir()) if repo.exists() else []:
        if not workspace.is_dir():
            continue
        store.path("repo", workspace.name)
        metadata = None
        for path in sorted(
            store.path("courses").glob(f"*/docs/{workspace.name}/meta.json")
        ):
            metadata = store.read_json(str(path.relative_to(store.data_dir)))
            if metadata is not None:
                break
        readme = store.read_text(f"repo/{workspace.name}/README.md", "")
        title = next(
            (
                line.lstrip("#").strip()
                for line in readme.splitlines()
                if line.startswith("#")
            ),
            workspace.name,
        )
        due = None
        if metadata is not None:
            title = metadata.get("title") or title
            due = metadata.get("due") or next(
                (d["due"] for d in metadata.get("deadlines", []) if d.get("due")), None
            )
        assignments.append(
            {
                "id": workspace.name,
                "title": title,
                "due": due,
                "has_tests": any(workspace.rglob("test_*.py")),
                "source": "sync" if metadata is not None else "template",
            }
        )
    return {"assignments": assignments}


def default_assignment(store, payload):
    assignment = payload.get("assignment")
    if assignment is not None:
        return runner.identifier(assignment)
    if store.path("repo/hw4").is_dir():
        return "hw4"
    assignments = [
        a for a in list_assignments(store, {})["assignments"] if a["has_tests"]
    ]
    if not assignments:
        raise ValueError("no assignment with tests is available")

    def due_key(assignment):
        due = assignment["due"]
        if not due:
            return float("-inf")
        parsed = datetime.fromisoformat(due.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or UTC).timestamp()

    return max(assignments, key=due_key)["id"]


def _nudge_draft(store, current, last_run):
    try:
        tutor = importlib.import_module("wolfbox.tutor")
        draft = tutor.nudge_draft(store, current, last_run)
        if draft:
            return draft
    except Exception:
        pass
    try:
        return gemma.nudge_draft(current["reason"], last_run) or DEFAULT_NUDGE_DRAFT
    except Exception:
        return DEFAULT_NUDGE_DRAFT


def get_state(store, payload):
    assignment = default_assignment(store, payload)
    profile = store.load_profile()
    runs = store.list_runs(limit=0, assignment=assignment)
    last_run = runs[0] if runs else None
    current = nudge.compute(
        runs, datetime.now(UTC), float(os.environ.get("STUCK_MINUTES", "30"))
    )
    if current["active"]:
        drafts = []
        worker = threading.Thread(
            target=lambda: drafts.append(_nudge_draft(store, current, last_run)),
            daemon=True,
        )
        worker.start()
        worker.join(NUDGE_TIMEOUT_SECONDS)
        current["draft"] = drafts[0] if drafts else DEFAULT_NUDGE_DRAFT
    try:
        llm = gemma.status()
    except Exception:
        llm = {
            "mode": "fake",
            "active_backend": "fake",
            "model": "fake",
            "online": False,
        }
    counts = profile.get("mistake_counts", {})
    return {
        "student_id": profile.get("student_id"),
        "name": profile.get("name"),
        "assignment": assignment,
        "code": store.read_text(f"repo/{assignment}/{assignment}.py", ""),
        "last_run": last_run,
        "nudge": current,
        "profile": {
            "mistake_counts": counts,
            "top_tags": sorted(counts, key=lambda tag: (-counts[tag], tag))[:3],
        },
        "llm": llm,
    }


def submit_code(store, payload):
    return runner.submit_code(
        store, payload.get("files"), default_assignment(store, payload)
    )


def get_run(store, payload):
    run_id = runner.identifier(payload.get("run_id"), "run_id")
    run = store.get_run(run_id)
    if run is None:
        raise ValueError(f"unknown run: {run_id}")
    return {"run": run}


def list_runs(store, payload):
    limit = payload.get("limit", 20)
    if type(limit) is not int or limit < 0:
        raise ValueError("limit must be a nonnegative integer")
    # History view: all assignments unless one is asked for (TA page shows hw2/hw3 too).
    assignment = payload.get("assignment")
    return {
        "runs": [
            {k: v for k, v in r.items() if k != "code"}
            for r in store.list_runs(limit=limit, assignment=assignment)
        ]
    }


def _allow_seed():
    if os.environ.get("ALLOW_SEED") != "1":
        raise ValueError("seed and reset require ALLOW_SEED=1")


def seed(store, payload):
    _allow_seed()
    files = payload.get("files")
    if not isinstance(files, dict):
        raise ValueError("files must be an object")
    for path, content in files.items():
        if not isinstance(path, str) or not isinstance(content, str):
            raise ValueError("file names and contents must be strings")
        store.path(path)
    for path, content in files.items():
        store.write_text(path, content)
    return {"written": len(files)}


def reset(store, payload):
    _allow_seed()
    # Do not let an in-flight worker recreate data after reset.
    with runner._jobs_lock:
        if runner.busy(store):
            raise ValueError("wait for active runs to finish before resetting")
        profile = store.load_profile()
        for path in store.data_dir.iterdir():
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
        if profile.get("student_id") and profile.get("name"):
            init(store, profile)
        else:
            ensure_template(store)
    return {}


HANDLERS = {
    "init": init,
    "get_state": get_state,
    "submit_code": submit_code,
    "get_run": get_run,
    "list_runs": list_runs,
    "list_assignments": list_assignments,
    "seed": seed,
    "reset": reset,
}


def dispatch(store: Store, payload: dict) -> dict:
    try:
        handlers = dict(HANDLERS)
        for module_name in FEATURE_MODULES:
            try:
                handlers.update(importlib.import_module(module_name).HANDLERS)
            except ImportError:
                continue
        kind = payload.get("type")
        if kind not in handlers:
            raise ValueError(f"unknown envelope type: {kind}")
        return protocol.success(handlers[kind](store, payload))
    except Exception as exc:
        return protocol.error(str(exc))
