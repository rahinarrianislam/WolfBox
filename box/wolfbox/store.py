"""All student state lives under data_dir. Never read a global DATA_DIR here (Plan B needs per-student dirs).

SHARED API (WS1 owns this file; other workstreams depend on these method names/signatures):
    Store(data_dir)
    .data_dir: Path
    .path(*parts) -> Path                       # data_dir / parts (no mkdir)
    .read_json(rel, default=None) -> Any
    .write_json(rel, obj) -> None               # atomic, mkdir parents
    .read_text(rel, default=None) / .write_text(rel, text)
    .load_profile() -> dict / .save_profile(dict)
    .load_plan() -> dict / .save_plan(dict)
    .save_run(run: dict) -> None                # writes runs/<id>.json; appends to runs.jsonl on first save
    .get_run(run_id) -> dict | None
    .list_runs(limit=20, assignment=None) -> list[dict]   # newest first
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_lock = threading.RLock()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Store:
    def __init__(self, data_dir: str | os.PathLike):
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def path(self, *parts: str) -> Path:
        p = self.data_dir.joinpath(*parts).resolve()
        if p != self.data_dir and self.data_dir not in p.parents:
            raise ValueError(f"path escapes DATA_DIR: {parts}")
        return p

    def read_text(self, rel: str, default: str | None = None) -> str | None:
        p = self.path(rel)
        return p.read_text() if p.exists() else default

    def write_text(self, rel: str, text: str) -> None:
        p = self.path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".tmp")
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, p)

    def read_json(self, rel: str, default: Any = None) -> Any:
        t = self.read_text(rel)
        if t is None:
            return default
        try:
            return json.loads(t)
        except json.JSONDecodeError:
            return default

    def write_json(self, rel: str, obj: Any) -> None:
        self.write_text(rel, json.dumps(obj, indent=2))

    def load_profile(self) -> dict:
        return self.read_json("profile.json", {}) or {}

    def save_profile(self, profile: dict) -> None:
        profile["updated_at"] = now_iso()
        self.write_json("profile.json", profile)

    def load_plan(self) -> dict:
        return self.read_json("plan.json", {}) or {}

    def save_plan(self, plan: dict) -> None:
        self.write_json("plan.json", plan)

    def save_run(self, run: dict) -> None:
        with _lock:
            rel = f"runs/{run['run_id']}.json"
            first = not self.path(rel).exists()
            self.write_json(rel, run)
            if first:
                with open(self.path("runs.jsonl"), "a") as f:
                    f.write(json.dumps(run) + "\n")

    def get_run(self, run_id: str) -> dict | None:
        return self.read_json(f"runs/{run_id}.json")

    def list_runs(self, limit: int = 20, assignment: str | None = None) -> list[dict]:
        d = self.path("runs")
        if not d.exists():
            return []
        runs = [r for r in (self.read_json(f"runs/{p.name}") for p in d.glob("*.json")) if r]
        if assignment:
            runs = [r for r in runs if r.get("assignment") == assignment]
        runs.sort(key=lambda r: (r.get("ts", ""), r.get("run_id", "")), reverse=True)
        return runs[:limit] if limit else runs
