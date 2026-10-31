#!/usr/bin/env python3
"""Load one sample student's DATA_DIR files into their WolfBox."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "orchestrator"))

from wolfhub.boxes import get_client  # noqa: E402
from wolfhub.registry import Registry  # noqa: E402

LOCAL_DEFAULTS = {
    "alex": "http://127.0.0.1:8101",
    "sam": "http://127.0.0.1:8102",
}
NAMES = {"alex": "Alex Rivera", "sam": "Sam Chen"}
MAX_BATCH_CHARS = 256_000


def _student_files(student: str) -> dict[str, str]:
    root = ROOT / "seed" / student
    if not root.is_dir():
        raise ValueError(f"No seed data directory for {student!r}: {root}")
    files = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name in {".gitkeep", "README.md"}:
            continue
        files[path.relative_to(root).as_posix()] = path.read_text(encoding="utf-8")
    return files


def _box_for(student: str, backend: str):
    registry = Registry()
    record = registry.get(student)
    client = get_client()
    if record and record.get("box_id") and record.get("backend") == backend:
        return client, record["box_id"]

    name = NAMES.get(student, student.title())
    box_id = client.ensure(student, name)
    client.call(box_id, {"v": 1, "type": "init", "student_id": student, "name": name})
    registry.set(student, name, box_id, backend)
    return client, box_id


def push_student(student: str, backend: str | None = None) -> int:
    backend = backend or os.environ.get("BOX_BACKEND", "local").lower()
    if backend not in {"local", "maritime"}:
        raise ValueError(f"Unsupported backend: {backend}")
    os.environ["BOX_BACKEND"] = backend
    if backend == "local" and not os.environ.get("LOCAL_BOXES"):
        os.environ["LOCAL_BOXES"] = ",".join(
            f"{key}={url}" for key, url in LOCAL_DEFAULTS.items()
        )

    client, box_id = _box_for(student, backend)
    files = _student_files(student)
    written = 0
    batch: dict[str, str] = {}
    chars = 0
    for path, content in files.items():
        item_chars = len(path) + len(content)
        if batch and chars + item_chars > MAX_BATCH_CHARS:
            result = client.call(box_id, {"v": 1, "type": "seed", "files": batch})
            written += result.get("written", 0)
            batch, chars = {}, 0
        batch[path] = content
        chars += item_chars
    if batch:
        result = client.call(box_id, {"v": 1, "type": "seed", "files": batch})
        written += result.get("written", 0)
    print(json.dumps({"written": written}))
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("student")
    parser.add_argument("--backend", choices=("local", "maritime"))
    args = parser.parse_args()
    push_student(args.student, args.backend)


if __name__ == "__main__":
    main()
