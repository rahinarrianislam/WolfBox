import os
from fastapi.testclient import TestClient

from wolfhub.main import create_app
from wolfhub.registry import Registry


class FakeBoxClient:
    def __init__(self):
        self.calls = []

    def ensure(self, student_id, name):
        return f"box:{student_id}"

    def call(self, box_id, envelope):
        self.calls.append((box_id, envelope))
        return {"ok": True, "echo": envelope["type"], "payload": envelope}


def client(tmp_path):
    boxes = FakeBoxClient()
    app = create_app(boxes, Registry(tmp_path / "students.json"))
    with TestClient(app) as test_client:
        yield test_client, boxes


def test_student_registration_is_idempotent(tmp_path):
    test_client, boxes = next(client(tmp_path))
    first = test_client.post("/api/students", json={"id": "alex", "name": "Alex Rivera"})
    second = test_client.post("/api/students", json={"id": "alex", "name": "Alex Rivera"})
    assert first.status_code == second.status_code == 200
    assert first.json()["box_id"] == second.json()["box_id"] == "box:alex"
    assert len([call for call in boxes.calls if call[1]["type"] == "init"]) == 2
    expected_backend = os.getenv("BOX_BACKEND", "maritime").lower()
    assert test_client.get("/api/students").json()[0] == {
        "id": "alex", "name": "Alex Rivera", "box_id": "box:alex", "backend": expected_backend
    }


def test_registry_round_trips_students_json(tmp_path):
    path = tmp_path / "nested" / "students.json"
    registry = Registry(path)
    registry.set("alex", "Alex Rivera", "box:alex", "local")
    assert Registry(path).get("alex") == {
        "name": "Alex Rivera", "box_id": "box:alex", "backend": "local"
    }


def test_routes_map_to_box_envelopes_and_strip_ok(tmp_path):
    test_client, boxes = next(client(tmp_path))
    test_client.post("/api/students", json={"id": "alex", "name": "Alex Rivera"})
    cases = [
        ("GET", "/api/students", None, None),
        ("GET", "/api/students/alex/state?assignment=hw5", None, ("get_state", {"assignment": "hw5"})),
        ("POST", "/api/students/alex/submit?assignment=hw5", {"code": "print(1)"}, ("submit_code", {"files": {"hw5.py": "print(1)"}, "assignment": "hw5"})),
        ("GET", "/api/students/alex/runs/run-1?assignment=hw5", None, ("get_run", {"run_id": "run-1", "assignment": "hw5"})),
        ("GET", "/api/students/alex/runs?assignment=hw5", None, ("list_runs", {"assignment": "hw5"})),
        ("POST", "/api/students/alex/ask", {"text": "why?"}, ("ask", {"text": "why?"})),
        ("GET", "/api/students/alex/ta-summary?assignment=hw5", None, ("ta_summary", {"assignment": "hw5"})),
        ("GET", "/api/students/alex/plan", None, ("plan_get", {})),
        ("POST", "/api/students/alex/plan/prefs", {"text": "no 8 AMs"}, ("plan_set_prefs", {"text": "no 8 AMs"})),
        ("POST", "/api/students/alex/plan/solve", {"full_sections": ["CSC316-001"]}, ("plan_solve", {"full_sections": ["CSC316-001"]})),
        ("POST", "/api/students/alex/sync", {}, ("sync", {})),
        ("GET", "/api/students/alex/sync/job-1", None, ("get_sync", {"job_id": "job-1"})),
        ("GET", "/api/students/alex/docs?course=csc116", None, ("list_docs", {"course": "csc116"})),
        ("GET", "/api/students/alex/docs/csc116%2Fhw4", None, ("get_doc", {"doc_id": "csc116/hw4"})),
        ("GET", "/api/students/alex/deadlines", None, ("deadlines", {})),
        ("GET", "/api/students/alex/assignments", None, ("list_assignments", {})),
    ]
    for method, path, body, expected in cases[1:]:
        response = test_client.request(method, path, json=body)
        assert response.status_code == 200, response.text
        assert "ok" not in response.json()
        assert response.json()["echo"] == expected[0]
        assert boxes.calls[-1][1] == {"v": 1, "type": expected[0], **expected[1]}
    assert cases[0][1] == "/api/students"


def test_box_error_maps_to_502(tmp_path):
    test_client, boxes = next(client(tmp_path))
    test_client.post("/api/students", json={"id": "alex", "name": "Alex Rivera"})

    def fail(box_id, envelope):
        return {"ok": False, "error": "invalid submission"}

    boxes.call = fail
    response = test_client.get("/api/students/alex/state")
    assert response.status_code == 502
    assert response.json() == {"error": "invalid submission"}


def test_box_connection_error_maps_to_503(tmp_path):
    test_client, boxes = next(client(tmp_path))
    test_client.post("/api/students", json={"id": "alex", "name": "Alex Rivera"})

    def fail(box_id, envelope):
        raise ConnectionError("refused")

    boxes.call = fail
    response = test_client.get("/api/students/alex/state")
    assert response.status_code == 503
    assert response.json() == {"error": "Box unavailable: refused"}


def test_heatmap_anonymizes_students_and_skips_errors(tmp_path):
    test_client, boxes = next(client(tmp_path))
    test_client.post("/api/students", json={"id": "alex", "name": "Alex Rivera"})
    test_client.post("/api/students", json={"id": "sam", "name": "Sam Chen"})

    def data(box_id, envelope):
        if box_id == "box:sam":
            return {"ok": False, "error": "offline"}
        if envelope["type"] == "get_state":
            return {"ok": True, "profile": {"mistake_counts": {"off_by_one": 3}}}
        return {"ok": True, "runs": [{"failed": [{"test": "test_last_index"}], "tags": ["off_by_one"]}]}

    boxes.call = data
    response = test_client.get("/api/instructor/heatmap")
    assert response.status_code == 200
    assert response.json() == {
        "students": ["Student 1"],
        "mistake_tags": {"off_by_one": 3},
        "failing_tests": {"test_last_index": 1},
    }


def test_health_endpoint():
    response = TestClient(create_app()).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_config_and_maritime_key_upload(tmp_path, monkeypatch):
    test_client, _ = next(client(tmp_path))
    monkeypatch.delenv("MARITIME_API_KEY", raising=False)
    monkeypatch.delenv("BOX_BACKEND", raising=False)

    cfg = test_client.get("/api/config").json()
    assert cfg["backend"] == "maritime"
    assert cfg["has_maritime_key"] is False

    # Empty key rejected
    bad = test_client.post("/api/config/maritime-key", json={"key": "   "})
    assert bad.status_code == 400

    # Valid key uploaded
    res = test_client.post("/api/config/maritime-key", json={"key": "mrt_secret_token_12345"})
    assert res.status_code == 200
    assert res.json()["has_maritime_key"] is True
    assert res.json()["backend"] == "maritime"
    assert os.environ.get("MARITIME_API_KEY") == "mrt_secret_token_12345"

    # Confirmed in get config
    cfg_after = test_client.get("/api/config").json()
    assert cfg_after["has_maritime_key"] is True
    assert cfg_after["maritime_key_preview"] == "mrt_...2345"
