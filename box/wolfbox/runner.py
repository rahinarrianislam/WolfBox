"""Background pytest jobs, each executing an immutable submission workspace."""

from __future__ import annotations

import importlib
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

from wolfbox.store import Store, now_iso

TIMEOUT_SECONDS = 20
_jobs: dict[str, tuple[threading.Thread, Path]] = {}
_jobs_lock = threading.RLock()


def identifier(value, label="assignment"):
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]*", value
    ):
        raise ValueError(f"invalid {label}")
    return value


def busy(store):
    with _jobs_lock:
        return any(
            thread.is_alive() and root == store.data_dir
            for thread, root in _jobs.values()
        )


def submit_code(store: Store, files: dict, assignment: str = "hw4") -> dict:
    identifier(assignment)
    if not isinstance(files, dict) or not files:
        raise ValueError(
            "files must be a nonempty object of relative paths to source strings"
        )
    workspace = store.path("repo", assignment)
    if not workspace.is_dir():
        raise ValueError(f"unknown assignment: {assignment}")
    destinations = []
    for name, source in files.items():
        if not isinstance(name, str) or not isinstance(source, str):
            raise ValueError("file names and contents must be strings")
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ValueError("file path must stay inside the assignment")
        destination = store.path("repo", assignment, name)
        if workspace not in destination.parents:
            raise ValueError("file path must stay inside the assignment")
        destinations.append((destination, source))
    with _jobs_lock:
        for destination, source in destinations:
            store.write_text(str(destination.relative_to(store.data_dir)), source)
        run_id = f"r_{datetime.now(UTC):%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:4]}"
        while store.path("runs", f"{run_id}.json").exists():
            run_id = f"r_{datetime.now(UTC):%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:4]}"
        snapshot = store.path("snapshots", run_id)
        shutil.copytree(
            workspace,
            snapshot,
            ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"),
        )
        run = {
            "run_id": run_id,
            "ts": now_iso(),
            "assignment": assignment,
            "status": "running",
            "passed": [],
            "failed": [],
            "duration_ms": 0,
            "tags": [],
            "hint": None,
            "hint_status": "pending",
            "related_past": [],
            "llm": None,
        }
        store.save_run(run)
        thread = threading.Thread(target=_job, args=(store, run, snapshot), daemon=True)
        _jobs[run_id] = (thread, store.data_dir)
        thread.start()
    return {"run_id": run_id, "status": "running"}


def _job(store, run, workspace):
    try:
        _execute(store, run, workspace)
    finally:
        with _jobs_lock:
            _jobs.pop(run["run_id"], None)


def _execute(store, run, workspace):
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="wolfbox-pytest-") as temporary:
            report = Path(temporary) / "results.xml"
            env = {
                **os.environ,
                "PYTEST_ADDOPTS": "",
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                "PYTHONPATH": str(workspace),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            # A private config prevents a parent repo's pytest settings changing submissions.
            config = Path(temporary) / "pytest.ini"
            config.write_text("[pytest]\n")
            with tempfile.TemporaryFile() as output:
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        "-q",
                        "-c",
                        str(config),
                        "--junitxml",
                        str(report),
                        "-p",
                        "no:cacheprovider",
                    ],
                    cwd=workspace,
                    env=env,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                try:
                    process.wait(timeout=TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                    raise TimeoutError(f"pytest timed out after {TIMEOUT_SECONDS}s")
                if report.exists():
                    for case in ET.parse(report).iter("testcase"):
                        failure = case.find("failure")
                        if failure is None:
                            failure = case.find("error")
                        if failure is not None:
                            run["failed"].append(
                                {
                                    "test": case.get("name", "pytest"),
                                    "message": (
                                        failure.text
                                        or failure.get("message", "Test failed")
                                    )[-400:],
                                }
                            )
                        elif case.find("skipped") is None:
                            run["passed"].append(case.get("name", "pytest"))
                if process.returncode not in (0, 1) or not (
                    run["passed"] or run["failed"]
                ):
                    output.seek(0, os.SEEK_END)
                    output.seek(max(0, output.tell() - 400))
                    raise RuntimeError(
                        f"pytest exited {process.returncode}: {output.read().decode(errors='replace')}"
                    )
                run["status"] = "done"
    except Exception as exc:
        run["status"] = "error"
        run["failed"].append({"test": "pytest", "message": str(exc)[:400]})
    run["duration_ms"] = max(1, int((time.monotonic() - started) * 1000))
    store.save_run(run)
    try:
        tutor = importlib.import_module("wolfbox.tutor")
        tutor.on_run_complete(store, run)
    except Exception:
        run["hint_status"] = (
            "ready" if run["status"] == "done" and not run["failed"] else "failed"
        )
        store.save_run(run)


def wait(run_id: str, timeout: float = 25):
    """Wait for pytest and the optional tutor hook; raise if still running."""
    with _jobs_lock:
        job = _jobs.get(run_id)
    if job is None:
        return
    thread, _ = job
    thread.join(timeout)
    if thread.is_alive():
        raise TimeoutError(f"run {run_id} did not finish within {timeout}s")
