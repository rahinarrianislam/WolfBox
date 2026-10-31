import os
from datetime import datetime, timedelta, timezone

from .jobs import run_sync, start_sync


def sync(store, payload):
    url = payload.get("course_url") or store.read_json("sync_source.json", {}).get("course_url") or os.environ.get("COURSE_URL")
    if not url:
        raise ValueError("course_url is required (or set COURSE_URL)")
    if payload.get("course_url"):
        store.write_json("sync_source.json", {"course_url": url})
    return start_sync(store, url)


def get_sync(store, payload):
    job = store.read_json(f"sync_jobs/{payload['job_id']}.json")
    if not job:
        raise ValueError("sync job not found")
    return {"job": job}


def list_docs(store, payload):
    courses = [payload["course"]] if payload.get("course") else [p.name for p in store.path("courses").glob("*") if p.is_dir()]
    docs = []
    for course in courses:
        root = store.path(f"courses/{course}/docs")
        if root.exists():
            docs.extend(store.read_json(str(p.relative_to(store.data_dir)), {}) for p in root.glob("*/meta.json"))
    return {"docs": [doc for doc in docs if doc]}


def get_doc(store, payload):
    doc_id = payload["doc_id"]
    course, item_id = doc_id.split("/", 1)
    meta = store.read_json(f"courses/{course}/docs/{item_id}/meta.json")
    if not meta:
        raise ValueError("document not found")
    return {"doc": meta, "text": store.read_text(f"courses/{course}/docs/{item_id}/text.md", "")}


def deadlines(store, payload):
    days = max(0, int(payload.get("days", 14)))
    docs = list_docs(store, {})["docs"]
    values = [d for doc in docs for d in doc.get("deadlines", [])]
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days)
    upcoming = []
    for deadline in values:
        try:
            due = datetime.fromisoformat(deadline["due"].replace("Z", "+00:00"))
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
            if now <= due <= end:
                upcoming.append(deadline)
        except (KeyError, ValueError):
            continue
    if not upcoming:
        for deadline in values:
            try:
                due = datetime.fromisoformat(deadline["due"].replace("Z", "+00:00"))
                if due.tzinfo is None:
                    due = due.replace(tzinfo=timezone.utc)
                if due >= now:
                    upcoming.append(deadline)
            except (KeyError, ValueError):
                continue
    upcoming.sort(key=lambda d: d.get("due", ""))
    return {"deadlines": upcoming}


def list_assignments(store, payload):
    assignments = []
    for doc in list_docs(store, payload).get("docs", []):
        if doc.get("type") == "assignment":
            assignments.append({"id": doc["item_id"], "title": doc["title"], "due": next((d.get("due") for d in doc.get("deadlines", [])), None),
                               "has_tests": bool(doc.get("workspace")), "source": "sync"})
    return {"assignments": assignments}


HANDLERS = {"sync": sync, "get_sync": get_sync, "list_docs": list_docs, "get_doc": get_doc, "deadlines": deadlines}
