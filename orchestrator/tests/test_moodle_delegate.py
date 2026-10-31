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
