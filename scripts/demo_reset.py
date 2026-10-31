#!/usr/bin/env python3
"""Restore both demo boxes and the sample course to a rehearsable state."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "orchestrator"))
sys.path.insert(0, str(ROOT / "scripts"))

from seed import push_student  # noqa: E402
from wolfhub.boxes import get_client  # noqa: E402
from wolfhub.registry import Registry  # noqa: E402

LOCAL_DEFAULTS = {
    "alex": "http://127.0.0.1:8101",
    "sam": "http://127.0.0.1:8102",
}
STUDENTS = {"alex": "Alex Rivera", "sam": "Sam Chen"}


def reset_course() -> str:
    base = os.environ.get("ORCH_URL", "http://127.0.0.1:8000").rstrip("/")
    try:
        response = httpx.post(f"{base}/api/instructor/reset-course", timeout=2.0)
        response.raise_for_status()
        return "orchestrator API"
    except httpx.HTTPError:
        from wolfhub.course import reset_course as reset_course_route

        reset_course_route()
        return "local course reset function (orchestrator unavailable)"


def reset_box(client, registry: Registry, student: str, backend: str) -> str:
    record = registry.get(student)
    if record and record.get("box_id") and record.get("backend") == backend:
        box_id = record["box_id"]
    else:
        box_id = client.ensure(student, STUDENTS[student])
        registry.set(student, STUDENTS[student], box_id, backend)
    client.call(box_id, {"v": 1, "type": "reset"})
    client.call(
        box_id,
        {"v": 1, "type": "init", "student_id": student, "name": STUDENTS[student]},
    )
    return box_id


def sync_and_wait(client, box_id: str, timeout: float = 120.0) -> dict:
    started = client.call(box_id, {"v": 1, "type": "sync"})
    job_id = started["job_id"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = client.call(box_id, {"v": 1, "type": "get_sync", "job_id": job_id})
        job = result["job"]
        if job["status"] != "running":
            if job["status"] != "done":
                raise RuntimeError(f"Initial sync failed: {job.get('errors', [])}")
            if job.get("errors"):
                raise RuntimeError(f"Initial sync had errors: {job['errors']}")
            return job
        time.sleep(0.5)
    raise TimeoutError(f"Initial sync {job_id} did not finish within {timeout:.0f}s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("local", "maritime"))
    args = parser.parse_args()
    backend = (args.backend or os.environ.get("BOX_BACKEND", "maritime")).lower()
    if backend not in {"local", "maritime"}:
        raise ValueError(f"Unsupported backend: {backend}")
    os.environ["BOX_BACKEND"] = backend
    if backend == "local" and not os.environ.get("LOCAL_BOXES"):
        os.environ["LOCAL_BOXES"] = ",".join(
            f"{student}={url}" for student, url in LOCAL_DEFAULTS.items()
        )

    client = get_client()
    registry = Registry()
    box_ids = {
        student: reset_box(client, registry, student, backend) for student in STUDENTS
    }
    course_reset = reset_course()
    seeded = push_student("alex", backend)
    jobs = {student: sync_and_wait(client, box_ids[student]) for student in STUDENTS}
    print(
        "Demo reset complete: "
        f"backend={backend}, course={course_reset}, alex_files={seeded}, "
        + ", ".join(
            f"{student}_sync={len(job['new'])} new/{job['unchanged']} unchanged"
            for student, job in jobs.items()
        )
    )


if __name__ == "__main__":
    main()
