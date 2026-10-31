import shutil
from pathlib import Path

from wolfbox.store import Store
from wolfbox import gemma
from wolfbox.sync.jobs import run_sync
from wolfbox.sync.handlers import deadlines, get_doc, get_sync, list_assignments, list_docs
from wolfhub.course import publish_item


SITE = Path(__file__).resolve().parents[2] / "orchestrator" / "course_site" / "csc116"


def local_fetch(url, site=SITE):
    path = site / url.split("/course/csc116/", 1)[1]
    return path.read_bytes()


def test_sync_indexes_published_course_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMMA_BACKEND", "fake")
    store = Store(tmp_path)

    first = run_sync(store, "http://sample/course/csc116/course.json", fetcher=local_fetch)

    assert first["new"] == [f"csc116/{doc}" for doc in ["syllabus", "lecture-05", "lecture-06", "hw2", "hw3", "hw4", "announce-01"]]
    assert len(store.read_json("courses/csc116/deadlines.json", [])) >= 3
    assert all((tmp_path / "repo" / hw).is_dir() for hw in ("hw2", "hw3", "hw4"))
    assert "Functions sample course notes" in (tmp_path / "courses/csc116/docs/lecture-05/text.md").read_text()

    second = run_sync(store, "http://sample/course/csc116/course.json", fetcher=local_fetch)

    assert second["new"] == []
    assert second["changed"] == []
    assert second["unchanged"] == 7
    assert get_sync(store, {"job_id": first["job_id"]})["job"]["status"] == "done"
    assert len(list_docs(store, {})["docs"]) == 7
    assert get_doc(store, {"doc_id": "csc116/hw4"})["doc"]["workspace"] == "repo/hw4"
    assert len(deadlines(store, {"days": 14})["deadlines"]) >= 3
    assert {a["id"] for a in list_assignments(store, {})["assignments"]} == {"hw2", "hw3", "hw4"}


def test_sync_published_changes_preserve_student_starter(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMMA_BACKEND", "fake")
    store = Store(tmp_path)
    site_root = tmp_path / "site"
    site = site_root / "csc116"
    shutil.copytree(SITE, site)
    def fetch(url):
        return local_fetch(url, site)

    run_sync(store, "http://sample/course/csc116/course.json", fetcher=fetch)
    (tmp_path / "repo/hw4/hw4.py").write_text("# student's edits\n")
    publish_item(site_root, "hw5")
    publish_item(site_root, "hw4-v2")

    result = run_sync(store, "http://sample/course/csc116/course.json", fetcher=fetch)

    assert result["new"] == ["csc116/hw5"]
    assert result["changed"] == ["csc116/hw4"]
    assert store.read_json("courses/csc116/docs/hw4/meta.json")["change_note"]
    assert (tmp_path / "repo/hw4/hw4.py").read_text() == "# student's edits\n"
    assert (tmp_path / "repo/hw4/hw4.py.new").exists()
    assert "preserved" in store.read_json("courses/csc116/docs/hw4/meta.json")["workspace_note"]


def test_gemma_failures_do_not_abort_sync(tmp_path, monkeypatch):
    monkeypatch.setattr(gemma, "summarize_doc", lambda *_: (_ for _ in ()).throw(RuntimeError("offline")))
    monkeypatch.setattr(gemma, "extract_deadlines", lambda *_: (_ for _ in ()).throw(RuntimeError("offline")))
    monkeypatch.setattr(gemma, "last_llm", lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    store = Store(tmp_path)

    result = run_sync(store, "http://sample/course/csc116/course.json", fetcher=local_fetch)

    assert result["status"] == "done"
    assert result["errors"] == []
    hw4 = store.read_json("courses/csc116/docs/hw4/meta.json")
    assert hw4["summary"] is None
    assert hw4["due"] == "2026-11-09T23:59:00-05:00"
    assert hw4["deadlines"][0]["due"] == hw4["due"]
