import json
import shutil
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from wolfhub import course


def test_publish_and_reset_endpoints_are_idempotent_and_restore(tmp_path, monkeypatch):
    site = tmp_path / "course_site"
    shutil.copytree(course.SITE_DIR, site)
    monkeypatch.setattr(course, "SITE_DIR", site)
    app = FastAPI()
    app.include_router(course.router)
    client = TestClient(app)

    published = client.post("/api/instructor/publish", json={"item": "hw5"})
    assert published.status_code == 200
    assert published.json()["published"] == "hw5"
    assert "hw5" in published.json()["items"]
    assert client.post("/api/instructor/publish", json={"item": "hw5"}).json()["items"].count("hw5") == 1

    updated = client.post("/api/instructor/publish", json={"item": "hw4-v2"})
    assert updated.status_code == 200
    assert json.loads((site / "csc116/course.json").read_text())["items"]

    reset = client.post("/api/instructor/reset-course")
    assert reset.status_code == 200
    assert (site / "csc116/course.json").read_bytes() == (site / "csc116/course.original.json").read_bytes()
