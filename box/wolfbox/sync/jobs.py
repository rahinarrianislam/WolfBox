import threading
import uuid
from datetime import datetime, timezone

from .fetch import fetch
from .manifest import load_manifest
from .process import process_item, start_llm_budget


def run_sync(store, course_url, fetcher=None, job_id=None):
    get = fetcher or fetch
    started = datetime.now(timezone.utc).isoformat()
    job = {"job_id": job_id or "s_" + uuid.uuid4().hex[:12], "status": "running", "started": started,
           "finished": None, "new": [], "changed": [], "unchanged": 0, "errors": []}
    start_llm_budget()
    try:
        manifest = load_manifest(course_url, get)
        course = manifest["course"]
        for item in manifest["items"]:
            try:
                state, _ = process_item(store, course, item, get)
                if state == "unchanged":
                    job["unchanged"] += 1
                else:
                    job[state].append(f"{course}/{item['id']}")
            except Exception as exc:
                job["errors"].append({"item": item.get("id"), "error": str(exc)})
        docs = store.path(f"courses/{course}/docs")
        deadlines = []
        if docs.exists():
            for meta_file in docs.glob("*/meta.json"):
                meta = store.read_json(str(meta_file.relative_to(store.data_dir)), {}) or {}
                deadlines.extend(meta.get("deadlines", []))
        store.write_json(f"courses/{course}/deadlines.json", deadlines)
        job["status"] = "done"
    except Exception as exc:
        job["status"] = "error"
        job["errors"].append({"item": "manifest", "error": str(exc)})
    job["finished"] = datetime.now(timezone.utc).isoformat()
    store.write_json(f"sync_jobs/{job['job_id']}.json", job)
    store.write_json("last_sync.json", job)
    return job


def start_sync(store, course_url):
    job_id = "s_" + uuid.uuid4().hex[:12]
    job = {"job_id": job_id, "status": "running", "started": datetime.now(timezone.utc).isoformat(),
           "finished": None, "new": [], "changed": [], "unchanged": 0, "errors": []}
    store.write_json(f"sync_jobs/{job_id}.json", job)

    def work():
        run_sync(store, course_url, job_id=job_id)

    threading.Thread(target=work, daemon=True).start()
    return {"job_id": job_id, "status": "running"}
