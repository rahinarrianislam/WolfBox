import json

import pytest

from wolfhub.boxes import BoxError, LocalBoxClient, parse_local_boxes


def test_local_boxes_parses_mapping():
    assert parse_local_boxes("alex=http://localhost:8101,sam=http://localhost:8102") == {
        "alex": "http://localhost:8101",
        "sam": "http://localhost:8102",
    }


def test_local_client_sends_protocol_envelope_and_returns_inner_json(monkeypatch):
    seen = {}

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"response": json.dumps({"ok": True, "created": True})}

    def post(url, **kwargs):
        seen.update(url=url, **kwargs)
        return Response()

    monkeypatch.setattr("wolfhub.boxes.httpx.post", post)
    result = LocalBoxClient({"alex": "http://localhost:8101"}).call(
        "http://localhost:8101", {"v": 1, "type": "init", "student_id": "alex", "name": "Alex"}
    )
    assert seen["url"] == "http://localhost:8101/chat"
    assert seen["json"] == {
        "message": '{"v": 1, "type": "init", "student_id": "alex", "name": "Alex"}',
        "source": "cli",
    }
    assert result == {"ok": True, "created": True}


def test_local_client_rejects_box_error_envelope(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"response": '{"ok": false, "error": "bad input"}'}

    monkeypatch.setattr("wolfhub.boxes.httpx.post", lambda *args, **kwargs: Response())
    with pytest.raises(BoxError, match="bad input"):
        LocalBoxClient({}).call("http://localhost:8101", {"v": 1, "type": "ask"})
