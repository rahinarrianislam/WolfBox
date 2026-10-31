import json
import shutil
import sys
import time
from pathlib import Path
from types import ModuleType

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient


SITE = Path(__file__).resolve().parents[1] / "course_site"


@pytest.fixture
def site(tmp_path):
    shutil.copytree(SITE / "csc116", tmp_path / "csc116")
    shutil.copyfile(tmp_path / "csc116/course.original.json", tmp_path / "csc116/course.json")
    return tmp_path


def finish(delegate, task_id):
    for _ in range(300):
        task = delegate.get_task(task_id)
        if task["status"] in {"done", "error"}:
            return task
        time.sleep(0.01)
    pytest.fail("task did not finish")


def test_fake_import_writes_separate_sync_compatible_manifest(site, monkeypatch):
    from wolfhub.moodle.agent import MoodleDelegate
    from wolfbox.sync.manifest import load_manifest

    monkeypatch.setenv("MOODLE_DELEGATE", "fake")
    original = (site / "csc116/course.json").read_bytes()
    delegate = MoodleDelegate(site_dir=site, fake_delay=0.01)
    task_id = delegate.start_task("list_assignments", {"course": "csc116"})
    task = finish(delegate, task_id)
    assert task["status"] == "done", task
    assert task["mode"] == "fake"
    manifest_path = site / "csc116/course.moodle.json"
    manifest = load_manifest("https://wolfbox.test/course/csc116/course.moodle.json", lambda _: manifest_path.read_bytes())
    assert manifest["source"] == "moodle"
    assert manifest["sample"] is True
    assert len(manifest["items"]) == 7
    assert (site / "csc116/course.json").read_bytes() == original
    assert len(task["steps"]) >= 3
    assert task["watch_url"] is None  # Never invent a live viewer in fake mode.


def test_fake_publish_and_open_are_explicitly_simulated(site, monkeypatch):
    from wolfhub.moodle.agent import MoodleDelegate

    monkeypatch.setenv("MOODLE_DELEGATE", "fake")
    delegate = MoodleDelegate(site_dir=site, fake_delay=0)
    for kind, params in [("open_course", {}), ("publish_assignment", {"item": "hw5"})]:
        task = finish(delegate, delegate.start_task(kind, {"course": "csc116", **params}))
        assert task["status"] == "done"
        assert task["result"]["simulated"] is True
        assert task["result"].get("moodle_url") is None


@pytest.mark.parametrize("kind,params", [("delete_course", {"course": "csc116"}), ("open_course", {"course": "../outside"}), ("publish_assignment", {"course": "csc116", "item": "../../etc/passwd"}), ("publish_assignment", {"course": "csc116"})])
def test_invalid_tasks_rejected_before_work_starts(site, kind, params):
    from wolfhub.moodle.agent import MoodleDelegate

    with pytest.raises(ValueError):
        MoodleDelegate(site_dir=site).start_task(kind, params)


def test_routes_fail_closed_and_support_instructor_hook(site, monkeypatch):
    import wolfhub.delegate as routes
    from wolfhub.moodle.agent import MoodleDelegate

    monkeypatch.setenv("MOODLE_DELEGATE", "fake")
    app = FastAPI()
    app.include_router(routes.router)
    app.state.moodle_delegate = MoodleDelegate(site_dir=site, fake_delay=0)
    client = TestClient(app)
    assert client.get("/api/delegate/tasks").status_code == 503
    assert client.post("/api/delegate/moodle/open_course", json={"course": "csc116"}).status_code == 503

    def instructor(request: Request):
        if request.headers.get("Authorization") != "Bearer instructor-test":
            raise HTTPException(403)

    app.dependency_overrides[routes.instructor_only] = instructor
    assert client.get("/api/delegate/tasks", headers={"Authorization": "Bearer student"}).status_code == 403
    headers = {"Authorization": "Bearer instructor-test"}
    response = client.post("/api/delegate/moodle/list_assignments", json={"course": "csc116"}, headers=headers)
    assert response.status_code == 202
    task_id = response.json()["task_id"]
    finish(app.state.moodle_delegate, task_id)
    task = client.get(f"/api/delegate/tasks/{task_id}", headers=headers).json()
    assert task["status"] == "done"
    assert client.get("/api/delegate/tasks", headers=headers).json()[0]["task_id"] == task_id
    assert client.get("/api/delegate/tasks/missing", headers=headers).status_code == 404
    assert client.post("/api/delegate/moodle/unknown", json={"course": "csc116"}, headers=headers).status_code == 422


def test_auth_factory_uses_real_fastapi_dependency_resolution(monkeypatch):
    from fastapi import Depends, Header
    from wolfhub.delegate import instructor_dependency

    auth = ModuleType("wolfhub.auth")

    def user(authorization: str = Header(default="")):
        return authorization

    def require_role(role):
        def require(identity=Depends(user)):
            if identity != f"Bearer {role}":
                raise HTTPException(403)
        return require

    auth.require_role = require_role
    monkeypatch.setitem(sys.modules, "wolfhub.auth", auth)
    app = FastAPI()

    @app.get("/protected", dependencies=[Depends(instructor_dependency())])
    def protected():
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/protected").status_code == 403
    assert client.get("/protected", headers={"Authorization": "Bearer student"}).status_code == 403
    assert client.get("/protected", headers={"Authorization": "Bearer instructor"}).status_code == 200


def test_strict_results_block_paths_wrong_course_and_fake_success():
    from wolfhub.moodle.models import validate_result

    good = {"status": "done", "steps": ["Read course"], "result": {"course": "csc116", "title": "Test", "source": "moodle", "items": [{"id": "hw1", "type": "assignment", "title": "HW1", "version": 1, "description": "Prompt", "files": []}]}}
    assert validate_result(good, "list_assignments", "csc116").status == "done"
    for mutate in [lambda d: d["result"].update(course="other"), lambda d: d["result"]["items"][0].update(id="../oops"), lambda d: d["result"]["items"][0].update(unexpected=True), lambda d: d.update(status="success")]:
        data = json.loads(json.dumps(good))
        mutate(data)
        with pytest.raises(ValueError):
            validate_result(data, "list_assignments", "csc116")
    with pytest.raises(ValueError):
        validate_result({"status": "done", "steps": [], "result": {}}, "publish_assignment", "csc116")


def test_private_files_are_copied_without_server_fetching_moodle(site):
    from wolfhub.moodle.manifest import save_manifest

    manifest = {"course": "csc116", "title": "Moodle course", "source": "moodle", "items": [{"id": "hw1", "type": "assignment", "title": "HW1", "version": 1, "description": "Real prompt", "files": [{"path": "hw1/starter.py", "url": "https://school.moodledemo.net/pluginfile.php/1/starter.py", "agent_path": "/data/jobs/task1/exports/starter.py", "role": "starter"}]}]}
    def download(path):
        assert path == "/data/jobs/task1/exports/starter.py"
        return b"answer = None\n"
    saved = save_manifest(manifest, site, "task1", "/data/jobs/task1", download)
    file = saved["items"][0]["files"][0]
    assert file["url"] == "/course/csc116/moodle/task1/hw1/starter.py"
    assert "agent_path" not in file
    assert (site / "csc116/moodle/task1/hw1/starter.py").read_bytes() == b"answer = None\n"
    assert any(f["path"] == "hw1/README.md" for f in saved["items"][0]["files"])
    manifest["items"][0]["files"][0]["agent_path"] = "/data/secrets"
    with pytest.raises(ValueError):
        save_manifest(manifest, site, "task1", "/data/jobs/task1", download)


def test_rest_import_converts_assignments_resources_and_authenticated_files(site):
    from wolfhub.moodle.rest import MoodleRest

    def transport(request):
        from urllib.parse import parse_qs
        params = parse_qs(request.content.decode()) if request.method == "POST" else {}
        fn = params.get("wsfunction", [None])[0]
        if fn == "core_course_search_courses":
            return httpx.Response(200, json={"courses": [{"id": 72, "shortname": "Memory", "fullname": "Memory"}]})
        if fn == "core_course_get_contents":
            return httpx.Response(200, json=[{"modules": [{"id": 7, "modname": "assign", "name": "Poem", "description": "<p>Write a poem</p>", "contents": [{"type": "file", "filename": "starter.py", "fileurl": "https://school.moodledemo.net/webservice/pluginfile.php/1/starter.py"}]}]}])
        if fn == "mod_assign_get_assignments":
            return httpx.Response(200, json={"courses": [{"assignments": [{"cmid": 7, "duedate": 1793574000, "intro": "<p>Write a poem</p>"}]}]})
        assert request.url.path == "/webservice/pluginfile.php/1/starter.py"
        assert request.url.params["token"] == "test-token"
        return httpx.Response(200, content=b"# starter\n")

    rest = MoodleRest("https://school.moodledemo.net", token="test-token", client=httpx.Client(transport=httpx.MockTransport(transport)))
    manifest = rest.import_course("csc116", "Memory", site, "task1")
    item = manifest["items"][0]
    assert item["description"] == "Write a poem"
    assert item["due"].endswith("+00:00")
    assert item["files"][0]["url"].startswith("/course/csc116/moodle/task1/")
    assert "test-token" not in json.dumps(manifest)
    assert (site / "csc116/moodle/task1/moodle-7/starter.py").read_bytes() == b"# starter\n"


def test_institutional_credentials_never_used_for_token_login(monkeypatch):
    from wolfhub.moodle.rest import MoodleRest

    monkeypatch.setenv("MOODLE_USERNAME", "real-person")
    monkeypatch.setenv("MOODLE_PASSWORD", "never-send")
    def no_network(request):
        pytest.fail("institutional credentials sent over network")
    with pytest.raises(ValueError, match="token|takeover"):
        MoodleRest("https://moodle.example.edu", client=httpx.Client(transport=httpx.MockTransport(no_network))).authenticate()


def test_no_key_defaults_fail_closed_with_config_error(site, monkeypatch):
    from wolfhub.moodle.agent import MoodleDelegate

    monkeypatch.delenv("MOODLE_DELEGATE", raising=False)
    monkeypatch.delenv("MARITIME_API_KEY", raising=False)
    delegate = MoodleDelegate(site_dir=site, fake_delay=0)
    assert delegate.mode == "real"
    task_id = delegate.start_task("open_course", {"course": "csc116"})
    task = finish(delegate, task_id)
    assert task["status"] == "error"
    assert any("MARITIME_API_KEY must be configured" in step for step in task["steps"])
    assert task["result"] is None


def test_fake_worker_exception_reaches_error_state(site, monkeypatch):
    from wolfhub.moodle.agent import MoodleDelegate

    monkeypatch.setenv("MOODLE_DELEGATE", "fake")
    delegate = MoodleDelegate(site_dir=site, fake_delay=0)

    def explode(*args, **kwargs):
        raise RuntimeError("Simulated crash in worker")

    monkeypatch.setattr(delegate, "_run_fake", explode)
    task_id = delegate.start_task("open_course", {"course": "csc116"})
    task = finish(delegate, task_id)
    assert task["status"] == "error"
    assert any("Simulated crash in worker" in step for step in task["steps"])


def test_demo_host_exact_allowlist(site, monkeypatch):
    from wolfhub.moodle.agent import MoodleDelegate

    monkeypatch.delenv("MOODLE_DELEGATE", raising=False)
    monkeypatch.setenv("MARITIME_API_KEY", "dummy-key")
    delegate = MoodleDelegate(
        site_dir=site,
        moodle_url="https://evil-moodledemo.net",
        fake_delay=0,
    )
    monkeypatch.setattr(delegate, "ensure_agent", lambda: {"id": "ag_123"})
    task_id = delegate.start_task("open_course", {"course": "csc116"})
    time.sleep(0.05)
    task = delegate.get_task(task_id)
    assert task["status"] == "needs_human"
    assert any("Institutional Moodle requires authentication token" in step for step in task["steps"])


def test_desktop_limitation_reported_and_links_omitted(site, monkeypatch):
    from wolfhub.moodle.agent import MoodleDelegate

    monkeypatch.delenv("MOODLE_DELEGATE", raising=False)
    monkeypatch.setenv("MARITIME_API_KEY", "dummy-key")
    delegate = MoodleDelegate(site_dir=site, fake_delay=0)
    monkeypatch.setattr(delegate, "ensure_agent", lambda: {"id": "ag_123"})
    
    fake_client = ModuleType("fake_maritime")
    class Agents:
        def chat(self, agent_id, prompt):
            return {
                "response": json.dumps({
                    "status": "done",
                    "steps": ["navigated"],
                    "result": {"moodle_url": "https://school.moodledemo.net/course/view.php?id=12"}
                })
            }
    fake_client.agents = Agents()
    monkeypatch.setattr(delegate, "_client", fake_client)

    task_id = delegate.start_task("open_course", {"course": "csc116"})
    task = finish(delegate, task_id)
    assert task["status"] == "done"
    assert task["watch_url"] is None
    assert task["takeover_url"] is None
    assert any("desktop attachment unsupported" in step for step in task["steps"])


def test_real_open_course_calls_agent_and_verifies_url(site, monkeypatch):
    from wolfhub.moodle.agent import MoodleDelegate

    monkeypatch.delenv("MOODLE_DELEGATE", raising=False)
    monkeypatch.setenv("MARITIME_API_KEY", "dummy-key")
    delegate = MoodleDelegate(site_dir=site, fake_delay=0)
    monkeypatch.setattr(delegate, "ensure_agent", lambda: {"id": "ag_123"})

    prompts_received = []
    fake_client = ModuleType("fake_maritime")
    class Agents:
        def chat(self, agent_id, prompt):
            prompts_received.append((agent_id, prompt))
            return {
                "response": json.dumps({
                    "status": "done",
                    "steps": ["opened course", "verified session"],
                    "result": {"moodle_url": "https://school.moodledemo.net/course/view.php?id=99"}
                })
            }
    fake_client.agents = Agents()
    monkeypatch.setattr(delegate, "_client", fake_client)

    task_id = delegate.start_task("open_course", {"course": "csc116"})
    task = finish(delegate, task_id)
    assert task["status"] == "done"
    assert len(prompts_received) == 1
    assert prompts_received[0][0] == "ag_123"
    assert "csc116" in prompts_received[0][1]
    assert task["result"]["moodle_url"] == "https://school.moodledemo.net/course/view.php?id=99"


def test_real_publish_assignment_loads_staged_files_and_calls_agent(site, monkeypatch):
    from wolfhub.moodle.agent import MoodleDelegate

    monkeypatch.delenv("MOODLE_DELEGATE", raising=False)
    monkeypatch.setenv("MARITIME_API_KEY", "dummy-key")
    delegate = MoodleDelegate(site_dir=site, fake_delay=0)
    monkeypatch.setattr(delegate, "ensure_agent", lambda: {"id": "ag_123"})

    prompts_received = []
    fake_client = ModuleType("fake_maritime")
    class Agents:
        def chat(self, agent_id, prompt):
            prompts_received.append((agent_id, prompt))
            return {
                "response": json.dumps({
                    "status": "done",
                    "steps": ["created assignment", "uploaded files", "verified publish"],
                    "result": {"moodle_url": "https://school.moodledemo.net/mod/assign/view.php?id=123"}
                })
            }
    fake_client.agents = Agents()
    monkeypatch.setattr(delegate, "_client", fake_client)

    task_id = delegate.start_task("publish_assignment", {"course": "csc116", "item": "hw5"})
    task = finish(delegate, task_id)
    assert task["status"] == "done"
    assert len(prompts_received) == 1
    prompt = prompts_received[0][1]
    assert "HW5: dictionaries" in prompt
    assert "2026-11-13" in prompt
    assert "hw5.py" in prompt
    assert "README.md" in prompt
    assert task["result"]["moodle_url"] == "https://school.moodledemo.net/mod/assign/view.php?id=123"


@pytest.mark.parametrize("bad_response,expected_err", [
    ({"error": "Agent process died"}, "OpenClaw agent error"),
    ({"response": ""}, "empty response"),
    ({"response": "not json"}, "Expecting value"),
    ({"response": json.dumps({"status": "error", "steps": ["login failed"]})}, "Agent did not"),
    ({"response": json.dumps({"status": "done", "steps": [], "result": {"moodle_url": "https://attacker.com/pwn"}})}, "does not match expected Moodle host"),
    ({"response": json.dumps({"status": "done", "steps": [], "result": {"moodle_url": "http://insecure.site"}})}, "Expected an HTTPS URL"),
])
def test_real_failures_never_become_done(site, monkeypatch, bad_response, expected_err):
    from wolfhub.moodle.agent import MoodleDelegate

    monkeypatch.delenv("MOODLE_DELEGATE", raising=False)
    monkeypatch.setenv("MARITIME_API_KEY", "dummy-key")
    delegate = MoodleDelegate(site_dir=site, fake_delay=0)
    monkeypatch.setattr(delegate, "ensure_agent", lambda: {"id": "ag_123"})

    fake_client = ModuleType("fake_maritime")
    class Agents:
        def chat(self, agent_id, prompt):
            return bad_response
    fake_client.agents = Agents()
    monkeypatch.setattr(delegate, "_client", fake_client)

    task_id = delegate.start_task("open_course", {"course": "csc116"})
    task = finish(delegate, task_id)
    assert task["status"] == "error"
    assert task["result"] is None
    assert any(expected_err.lower() in step.lower() for step in task["steps"])


def test_real_publish_missing_staged_item_never_done(site, monkeypatch):
    from wolfhub.moodle.agent import MoodleDelegate

    monkeypatch.delenv("MOODLE_DELEGATE", raising=False)
    monkeypatch.setenv("MARITIME_API_KEY", "dummy-key")
    delegate = MoodleDelegate(site_dir=site, fake_delay=0)
    monkeypatch.setattr(delegate, "ensure_agent", lambda: {"id": "ag_123"})

    task_id = delegate.start_task("publish_assignment", {"course": "csc116", "item": "nonexistent_hw"})
    task = finish(delegate, task_id)
    assert task["status"] == "error"
    assert task["result"] is None
    assert any("not found" in step.lower() for step in task["steps"])


def test_institutional_needs_human_and_concrete_resume_flow(site, monkeypatch):
    import wolfhub.delegate as routes
    from wolfhub.moodle.agent import MoodleDelegate

    monkeypatch.delenv("MOODLE_DELEGATE", raising=False)
    monkeypatch.setenv("MARITIME_API_KEY", "dummy-key")
    delegate = MoodleDelegate(
        site_dir=site,
        moodle_url="https://moodle.ncsu.edu",
        fake_delay=0,
    )
    monkeypatch.setattr(delegate, "ensure_agent", lambda: {"id": "ag_123"})

    task_id = delegate.start_task("list_assignments", {"course": "csc116"})
    time.sleep(0.05)
    task = delegate.get_task(task_id)
    assert task["status"] == "needs_human"

    task_no_token = delegate.resume_task(task_id, token=None)
    assert task_no_token["status"] == "error"
    assert any("interactive browser takeover is unsupported" in s for s in task_no_token["steps"])

    delegate.tasks[task_id]["status"] = "needs_human"

    def mock_import(self, course, name, site_dir, tid):
        return {"course": course, "title": "NCSU", "source": "moodle", "sample": False, "items": []}
    monkeypatch.setattr("wolfhub.moodle.agent.MoodleRest.import_course", mock_import)

    task_resumed = delegate.resume_task(task_id, token="valid-ws-token")
    task_done = finish(delegate, task_id)
    assert task_done["status"] == "done"

    app = FastAPI()
    app.include_router(routes.router)
    app.state.moodle_delegate = delegate
    app.dependency_overrides[routes.instructor_only] = lambda: {"user": "instructor"}
    client = TestClient(app)

    res_404 = client.post("/api/delegate/tasks/missing_task/resume", json={"token": "t"})
    assert res_404.status_code == 404

    res_400 = client.post(f"/api/delegate/tasks/{task_id}/resume", json={"token": "t"})
    assert res_400.status_code == 400


def test_auth_contract_matches_require_instructor(monkeypatch):
    import wolfhub.delegate as routes

    auth = ModuleType("wolfhub.auth")
    def require_instructor(request: Request):
        if request.headers.get("Authorization") != "Bearer valid-inst":
            raise HTTPException(403, detail="instructor role required")
        return {"role": "instructor"}

    auth.require_instructor = require_instructor
    monkeypatch.setitem(sys.modules, "wolfhub.auth", auth)

    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)

    assert client.get("/api/delegate/tasks").status_code == 403
    assert client.get("/api/delegate/tasks", headers={"Authorization": "Bearer invalid"}).status_code == 403
    assert client.get("/api/delegate/tasks", headers={"Authorization": "Bearer valid-inst"}).status_code == 200


def test_task_responses_exclude_resume_credentials(tmp_path):
    from wolfhub.moodle.agent import MoodleDelegate
    delegate = MoodleDelegate(site_dir=tmp_path, mode="fake")
    delegate.tasks["task_private"] = {"task_id": "task_private", "status": "done", "ws_token": "private-token", "created_at": "now"}
    assert "ws_token" not in delegate.get_task("task_private")
    assert "ws_token" not in delegate.list_tasks()[0]
