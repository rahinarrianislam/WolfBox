"""Moodle delegation agent using OpenClaw on Maritime."""
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
        mode: Optional[str] = None,
    ):
        self.site_dir = Path(site_dir) if site_dir else Path(__file__).resolve().parents[2] / "course_site"
        self.fake_delay = float(fake_delay)
        self.moodle_url = (moodle_url or os.getenv("MOODLE_URL", "https://school.moodledemo.net")).rstrip("/")
        self.api_key = api_key or os.getenv("MARITIME_API_KEY")
        
        explicit_mode = os.getenv("MOODLE_DELEGATE") or mode
        if explicit_mode:
            if explicit_mode not in {"fake", "real"}:
                raise ValueError(f"Unknown MOODLE_DELEGATE mode '{explicit_mode}'")
            self.mode = explicit_mode
        else:
            # Explicit fake mode only; default to real mode.
            # Real mode requires MARITIME_API_KEY when tasks execute.
            self.mode = "real"

        self.tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._client = None
        self._agent = None

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
                if isinstance(ag, dict) and ag.get("name") == "wolfbox-moodle":
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

    def resume_task(self, task_id: str, token: Optional[str] = None) -> Dict[str, Any]:
        """Concrete resume flow for tasks waiting for human authentication."""
        with self._lock:
            task = self.tasks.get(task_id)
            if task is None:
                raise KeyError(f"Task {task_id} not found")
            if task.get("status") != "needs_human":
                raise ValueError(
                    f"Task {task_id} is not waiting for human input (status: {task.get('status')})"
                )
            if not token:
                task["status"] = "error"
                task["steps"].append(
                    "Resume failed: institutional Moodle requires web-service token; "
                    "interactive browser takeover is unsupported without desktop integration."
                )
                return task

            task["ws_token"] = token
            task["status"] = "queued"
            task["steps"].append("Credentials provided; resuming task.")

        worker = threading.Thread(target=self._run_task, args=(task_id,), daemon=True)
        worker.start()
        return self.get_task(task_id)

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            task = self.tasks.get(task_id)
            return {k: v for k, v in task.items() if k != "ws_token"} if task else None

    def list_tasks(self) -> List[Dict[str, Any]]:
        with self._lock:
            return sorted(
                [{k: v for k, v in t.items() if k != "ws_token"} for t in self.tasks.values()],
                key=lambda t: t.get("created_at", ""),
                reverse=True,
            )

    def _run_task(self, task_id: str) -> None:
        task = self.tasks[task_id]
        task["status"] = "running"
        try:
            mode = os.getenv("MOODLE_DELEGATE", task.get("mode")) or self.mode
            task["mode"] = mode
            if mode == "fake":
                self._run_fake(task_id)
            elif mode == "real":
                self._run_real(task_id)
            else:
                raise ValueError(f"Unknown delegate mode: {mode}")
        except Exception as e:
            task["status"] = "error"
            task["steps"].append(f"Task failed: {e}")

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

    def _load_staged_assignment(self, course: str, item: str) -> Dict[str, Any]:
        """Load metadata and files from staged assignment directory."""
        course_dir = Path(self.site_dir) / course
        staged_dir = course_dir / "staged"
        items_json_path = staged_dir / "items.json"

        item_data = None
        if items_json_path.exists():
            try:
                staged_items = json.loads(items_json_path.read_text(encoding="utf-8"))
                item_data = staged_items.get(item)
            except Exception:
                pass

        title = item_data.get("title", item) if item_data else item
        due = item_data.get("due") if item_data else None

        loaded_files = []
        item_folder = staged_dir / item

        if item_data and "files" in item_data:
            for f in item_data["files"]:
                rel_path = f.get("path")
                f_path = staged_dir / rel_path if (staged_dir / rel_path).exists() else item_folder / Path(rel_path).name
                if f_path.exists() and f_path.is_file():
                    try:
                        content = f_path.read_text(encoding="utf-8")
                    except UnicodeDecodeError:
                        content = f"<binary file: {f_path.stat().st_size} bytes>"
                    loaded_files.append({"path": rel_path, "filename": f_path.name, "content": content})
        elif item_folder.exists() and item_folder.is_dir():
            for f_path in sorted(item_folder.rglob("*")):
                if f_path.is_file() and not f_path.name.startswith("."):
                    rel = str(f_path.relative_to(staged_dir))
                    try:
                        content = f_path.read_text(encoding="utf-8")
                    except UnicodeDecodeError:
                        content = f"<binary file: {f_path.stat().st_size} bytes>"
                    loaded_files.append({"path": rel, "filename": f_path.name, "content": content})

        if not item_data and not loaded_files:
            raise FileNotFoundError(f"Staged assignment '{item}' not found in course '{course}'")

        description = ""
        for f in loaded_files:
            if f["filename"].lower() == "readme.md":
                description = f["content"]
                break
        if not description and item_data:
            description = item_data.get("description", "")

        return {
            "item": item,
            "title": title,
            "due": due,
            "description": description,
            "files": loaded_files,
        }

    def _run_real(self, task_id: str) -> None:
        task = self.tasks[task_id]
        kind = task["kind"]
        course = task["course"]

        if not self.api_key:
            raise ValueError(
                "MARITIME_API_KEY must be configured for real mode; "
                "set MOODLE_DELEGATE=fake for explicit simulation"
            )

        task["steps"].append("Ensuring OpenClaw agent on Maritime")
        agent = self.ensure_agent()
        agent_id = (
            agent.get("id")
            if isinstance(agent, dict) and agent.get("id")
            else (
                self._agent.get("id")
                if isinstance(self._agent, dict) and self._agent.get("id")
                else "wolfbox-moodle"
            )
        )

        task["steps"].append(
            "Maritime OpenClaw runs in headless container; desktop attachment unsupported, omitting watch/takeover links."
        )
        task["watch_url"] = None
        task["takeover_url"] = None

        host = urlsplit(self.moodle_url).hostname or ""
        is_demo = host in DEMO_HOSTS
        token = task.get("ws_token") or os.getenv("MOODLE_WS_TOKEN")

        if not is_demo and not token:
            task["status"] = "needs_human"
            task["steps"].append(
                "Institutional Moodle requires authentication token. Provide token to resume."
            )
            return

        if kind == "open_course":
            prompt = (
                f"Navigate to {self.moodle_url}, open course '{course}', and verify the course session is accessible. "
                f"Return JSON strictly adhering to this format:\n"
                f'{{"status": "done", "steps": ["navigated to course", "verified session"], '
                f'"result": {{"moodle_url": "<verified_https_course_url>"}}}}'
            )
            task["steps"].append("Instructing OpenClaw agent to open course")
            chat_res = self.client.agents.chat(agent_id, prompt)
            if not isinstance(chat_res, dict):
                raise RuntimeError("Invalid response from OpenClaw agent")
            if chat_res.get("error"):
                raise RuntimeError(f"OpenClaw agent error: {chat_res['error']}")
            response_text = chat_res.get("response")
            if not response_text:
                raise RuntimeError("OpenClaw agent returned empty response")
            task["steps"].append("Validating OpenClaw open_course response")
            parsed = json.loads(response_text)
            validated = validate_result(parsed, kind, course)
            if validated.status != "done":
                raise RuntimeError(f"Agent did not open course: status is {validated.status}")
            res_url = validated.result.get("moodle_url")
            if not res_url:
                raise ValueError("Agent result missing moodle_url")
            res_host = urlsplit(res_url).hostname
            expected_host = urlsplit(self.moodle_url).hostname
            if res_host != expected_host:
                raise ValueError(
                    f"Returned URL hostname '{res_host}' does not match expected Moodle host '{expected_host}'"
                )
            task["result"] = validated.result
            task["status"] = "done"
            task["steps"].append(f"Course '{course}' opened and verified at {res_url}")

        elif kind == "publish_assignment":
            item = task["params"].get("item")
            if not item:
                raise ValueError("item is required for publish_assignment")
            staged = self._load_staged_assignment(course, item)
            task["steps"].append(f"Loaded staged assignment '{item}' with {len(staged['files'])} files")

            files_block = "\n\n".join(
                f"File: {f['filename']} (path: {f['path']})\n```\n{f['content']}\n```"
                for f in staged["files"]
            )

            prompt = (
                f"Navigate to {self.moodle_url}, open course '{course}', and create a new assignment.\n"
                f"Title: {staged['title']}\n"
                f"Due Date: {staged['due'] or 'None'}\n"
                f"Description / Instructions:\n{staged['description']}\n\n"
                f"Assignment Files to Upload / Configure:\n{files_block}\n\n"
                f"Publish the assignment on Moodle and verify it is visible to students. "
                f"Return JSON strictly adhering to this format:\n"
                f'{{"status": "done", "steps": ["created assignment", "uploaded files", "verified publish"], '
                f'"result": {{"moodle_url": "<verified_https_url_to_assignment>"}}}}'
            )
            task["steps"].append("Instructing OpenClaw agent to publish assignment")
            chat_res = self.client.agents.chat(agent_id, prompt)
            if not isinstance(chat_res, dict):
                raise RuntimeError("Invalid response from OpenClaw agent")
            if chat_res.get("error"):
                raise RuntimeError(f"OpenClaw agent error: {chat_res['error']}")
            response_text = chat_res.get("response")
            if not response_text:
                raise RuntimeError("OpenClaw agent returned empty response")
            task["steps"].append("Validating OpenClaw publish response")
            parsed = json.loads(response_text)
            validated = validate_result(parsed, kind, course)
            if validated.status != "done":
                raise RuntimeError(f"Agent did not complete publish: status is {validated.status}")
            res_url = validated.result.get("moodle_url")
            if not res_url:
                raise ValueError("Agent result missing moodle_url")
            res_host = urlsplit(res_url).hostname
            expected_host = urlsplit(self.moodle_url).hostname
            if res_host != expected_host:
                raise ValueError(
                    f"Returned URL hostname '{res_host}' does not match expected Moodle host '{expected_host}'"
                )
            task["result"] = validated.result
            task["status"] = "done"
            task["steps"].append(f"Assignment '{item}' published and verified at {res_url}")

        elif kind == "list_assignments":
            task["steps"].append("Querying Moodle assignments and resources")
            try:
                rest = MoodleRest(self.moodle_url, token=token)
                manifest = rest.import_course(course, course, self.site_dir, task_id)
                task["result"] = manifest
                task["status"] = "done"
                task["steps"].append(
                    f"Imported {len(manifest.get('items', []))} items via Moodle REST API"
                )
                return
            except Exception as rest_err:
                task["steps"].append(f"Moodle REST API unavailable ({rest_err}), falling back to OpenClaw")

            prompt = (
                f"Navigate to {self.moodle_url}, find course '{course}', list all assignments and "
                f"resources with their due dates, descriptions, and file URLs. Format as JSON."
            )
            task["steps"].append("Instructing OpenClaw agent to crawl course")
            chat_res = self.client.agents.chat(agent_id, prompt)
            if not isinstance(chat_res, dict):
                raise RuntimeError("Invalid response from OpenClaw agent")
            if chat_res.get("error"):
                raise RuntimeError(f"OpenClaw agent error: {chat_res['error']}")
            response_text = chat_res.get("response")
            if not response_text:
                raise RuntimeError("OpenClaw agent returned empty response")
            task["steps"].append("Processing OpenClaw response")
            parsed = json.loads(response_text)
            validated = validate_result(parsed, kind, course)
            if validated.status != "done":
                raise RuntimeError(f"Agent did not list assignments: status is {validated.status}")
            saved = save_manifest(validated.result, self.site_dir, task_id)
            task["result"] = saved
            task["status"] = "done"
            task["steps"].append(f"Successfully saved {len(saved.get('items', []))} items")
