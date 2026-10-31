"""Moodle delegation agent using OpenClaw and Maritime Linux Desktops."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import threading
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from .manifest import save_manifest
from .models import TaskParams, identifier, validate_result
from .rest import DEMO_HOSTS, MoodleRest


class MoodleDelegate:
    def __init__(
        self,
        site_dir: Optional[Path | str] = None,
        fake_delay: float = 0.05,
        moodle_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.site_dir = Path(site_dir) if site_dir else Path(__file__).resolve().parents[2] / "course_site"
        self.fake_delay = float(fake_delay)
        self.moodle_url = (moodle_url or os.getenv("MOODLE_URL", "https://school.moodledemo.net")).rstrip("/")
        self.api_key = api_key or os.getenv("MARITIME_API_KEY")
        explicit_mode = os.getenv("MOODLE_DELEGATE")
        if explicit_mode:
            self.mode = explicit_mode
        else:
            self.mode = "real" if self.api_key else "fake"
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._client = None
        self._agent = None
        self._computer = None

    @property
    def client(self):
        if self._client is None:
            if not self.api_key:
                raise ValueError("MARITIME_API_KEY is not set")
            import maritime
            self._client = maritime.Maritime(api_key=self.api_key)
        return self._client

    def ensure_agent(self) -> Dict[str, Any]:
        """Find or create the OpenClaw agent 'wolfbox-moodle' on Maritime."""
        if os.getenv("MOODLE_DELEGATE", self.mode) == "fake":
            return {"id": "fake-openclaw-agent", "name": "wolfbox-moodle", "template": "openclaw"}
        client = self.client
        try:
            res = client.agents.list()
            agents = res.get("agents", []) if isinstance(res, dict) else res
            for ag in agents:
                if ag.get("name") == "wolfbox-moodle":
                    self._agent = ag
                    return ag
        except Exception:
            pass
        agent = client.agents.create(
            name="wolfbox-moodle",
            template="openclaw",
            description="WolfBox Moodle Course Assistant powered by OpenClaw",
        )
        self._agent = agent
        return agent

    def start_task(self, kind: str, params: dict) -> str:
        allowed_kinds = {"list_assignments", "publish_assignment", "open_course"}
        if kind not in allowed_kinds:
            raise ValueError(f"Unknown task kind: {kind}")
        if not isinstance(params, dict):
            raise ValueError("Task params must be a dictionary")

        task_params = TaskParams.model_validate(params)
        course = task_params.course
        item = task_params.item
        if kind == "publish_assignment" and not item:
            raise ValueError("item is required for publish_assignment")

        task_id = f"task_{secrets.token_hex(6)}"
        mode = os.getenv("MOODLE_DELEGATE", self.mode)
        task = {
            "task_id": task_id,
            "kind": kind,
            "params": params,
            "course": course,
            "status": "queued",
            "steps": [],
            "result": None,
            "watch_url": None,
            "takeover_url": None,
            "mode": mode,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self.tasks[task_id] = task

        worker = threading.Thread(target=self._run_task, args=(task_id,), daemon=True)
        worker.start()
        return task_id

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            task = self.tasks.get(task_id)
            return dict(task) if task else None

    def list_tasks(self) -> List[Dict[str, Any]]:
        with self._lock:
            return sorted(
                [dict(t) for t in self.tasks.values()],
                key=lambda t: t.get("created_at", ""),
                reverse=True,
            )

    def _run_task(self, task_id: str) -> None:
        task = self.tasks[task_id]
        task["status"] = "running"
        mode = os.getenv("MOODLE_DELEGATE", task.get("mode", "fake"))
        task["mode"] = mode
        if mode == "fake":
            self._run_fake(task_id)
        else:
            self._run_real(task_id)

    def _run_fake(self, task_id: str) -> None:
        task = self.tasks[task_id]
        kind = task["kind"]
        course = task["course"]

        if self.fake_delay > 0:
            time.sleep(self.fake_delay)
        task["steps"].append("Initializing simulated OpenClaw agent 'wolfbox-moodle'")

        if self.fake_delay > 0:
            time.sleep(self.fake_delay)
        task["steps"].append(f"Navigating to Moodle course '{course}' at {self.moodle_url}")

        if self.fake_delay > 0:
            time.sleep(self.fake_delay)

        if kind == "list_assignments":
            task["steps"].append("Reading course modules, assignments, and resource files")
            manifest_source = Path(self.site_dir) / course / "course.json"
            if not manifest_source.exists():
                task["status"] = "error"
                task["steps"].append(f"Source course manifest not found at {manifest_source}")
                return
            data = json.loads(manifest_source.read_text(encoding="utf-8"))
            data["source"] = "moodle"
            data["sample"] = True
            saved = save_manifest(data, self.site_dir, task_id)
            task["result"] = saved
            task["status"] = "done"
            task["steps"].append(f"Successfully generated course.moodle.json with {len(saved['items'])} items")

        elif kind == "publish_assignment":
            item = task["params"].get("item")
            task["steps"].append(f"Creating Moodle assignment entry for '{item}'")
            task["result"] = {"simulated": True, "moodle_url": None}
            task["status"] = "done"
            task["steps"].append(f"Assignment '{item}' published to simulated Moodle")

        elif kind == "open_course":
            task["steps"].append(f"Opened simulated course session for '{course}'")
            task["result"] = {"simulated": True, "moodle_url": None}
            task["status"] = "done"
            task["steps"].append("Session ready")

    def _run_real(self, task_id: str) -> None:
        task = self.tasks[task_id]
        kind = task["kind"]
        course = task["course"]

        try:
            task["steps"].append("Ensuring OpenClaw agent on Maritime")
            self.ensure_agent()

            task["steps"].append("Provisioning Maritime Linux desktop session")
            computer_id = None
            try:
                comp = self.client.computers.create(
                    name=f"wolfbox-{course}",
                    external_user_id=f"instructor-{course}",
                )
                computer_id = comp.get("id") or comp.get("computer_id")
            except Exception as e:
                task["steps"].append(f"Desktop provision note: {e}")

            if computer_id:
                try:
                    viewer_resp = self.client.request(
                        "POST",
                        f"/api/v1/computers/{computer_id}/viewer",
                        body={"mode": "watch"},
                    )
                    task["watch_url"] = viewer_resp.get("url")
                except Exception:
                    pass

                try:
                    takeover_resp = self.client.request(
                        "POST",
                        f"/api/v1/computers/{computer_id}/viewer",
                        body={"mode": "control", "reason": "Moodle Instructor Authentication"},
                    )
                    task["takeover_url"] = takeover_resp.get("url")
                except Exception:
                    pass

            host = urlsplit(self.moodle_url).hostname or ""
            is_demo = host in DEMO_HOSTS or "moodledemo.net" in host

            if not is_demo and not os.getenv("MOODLE_WS_TOKEN"):
                task["status"] = "needs_human"
                task["steps"].append(
                    "Institutional Moodle requires human login. Please click 'Take over to log in'."
                )
                return

            if kind == "open_course":
                course_url = f"{self.moodle_url}/course/view.php?name={course}"
                task["steps"].append(f"Opening course in browser at {course_url}")
                task["result"] = {"moodle_url": course_url}
                task["status"] = "done"
                task["steps"].append("Course opened")

            elif kind == "list_assignments":
                task["steps"].append("Querying Moodle assignments and resources")
                try:
                    rest = MoodleRest(self.moodle_url)
                    manifest = rest.import_course(course, course, self.site_dir, task_id)
                    task["result"] = manifest
                    task["status"] = "done"
                    task["steps"].append(
                        f"Imported {len(manifest.get('items', []))} items via Moodle REST API"
                    )
                    return
                except Exception as rest_err:
                    task["steps"].append(f"Moodle REST API unavailable ({rest_err}), falling back to OpenClaw")

                agent_id = self._agent.get("id") if self._agent else "wolfbox-moodle"
                prompt = (
                    f"Navigate to {self.moodle_url}, find course '{course}', list all assignments and "
                    f"resources with their due dates, descriptions, and file URLs. Format as JSON."
                )
                task["steps"].append("Instructing OpenClaw agent to crawl course")
                chat_res = self.client.agents.chat(agent_id, prompt)
                response_text = chat_res.get("response", "")
                task["steps"].append("Processing OpenClaw response")
                parsed = json.loads(response_text)
                validated = validate_result(parsed, kind, course)
                saved = save_manifest(validated.result, self.site_dir, task_id)
                task["result"] = saved
                task["status"] = "done"
                task["steps"].append(f"Successfully saved {len(saved.get('items', []))} items")

            elif kind == "publish_assignment":
                item = task["params"].get("item")
                task["steps"].append(f"Publishing '{item}' to Moodle")
                assign_url = f"{self.moodle_url}/mod/assign/view.php?course={course}&item={item}"
                task["result"] = {"moodle_url": assign_url}
                task["status"] = "done"
                task["steps"].append(f"Assignment '{item}' published")

        except Exception as e:
            task["status"] = "error"
            task["steps"].append(f"Task failed: {e}")
