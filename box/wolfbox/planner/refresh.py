"""Background public-catalog refresh, persisted in the student's Store."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

from wolfbox.planner import ncsu
from wolfbox.store import Store, now_iso

SAMPLE_CATALOG = Path(__file__).resolve().parents[2] / "data" / "catalog.json"


def run_refresh(store, catalog=None, fetcher=None, term=None, job_id=None):
    term = term or os.environ.get("NCSU_TERM", "2271")
    job_id = job_id or "c_" + uuid.uuid4().hex[:12]
    job = {
        "job_id": job_id,
        "status": "running",
        "term": term,
        "started": now_iso(),
        "finished": None,
        "courses_found": 0,
        "sections_found": 0,
        "missing": [],
        "errors": [],
    }
    store.write_json(f"planner_jobs/{job_id}.json", job)
    try:
        catalog = (
            catalog if catalog is not None else json.loads(SAMPLE_CATALOG.read_text())
        )
        get = fetcher or ncsu.fetch_course
        courses = []
        for i, sample in enumerate(catalog["courses"]):
            if i and fetcher is None:
                time.sleep(0.25)
            try:
                live = get(sample["code"], term)
            except Exception as exc:  # noqa: BLE001 - Persist background failures for polling.
                job["errors"].append({"course": sample["code"], "error": str(exc)})
                live = None
            if live is not None:
                job["courses_found"] += 1
                job["sections_found"] += len(live["sections"])
            else:
                job["missing"].append(sample["code"])
            courses.append(
                {
                    **sample,
                    **(live or {}),
                    "satisfies": sample.get("satisfies", []),
                    "sections": live["sections"] if live else [],
                }
            )
        # A failed fetch must not replace the last good snapshot with empty sections.
        if job["errors"]:
            job["status"] = "error"
        else:
            store.write_json(
                "catalog_ncsu.json",
                {
                    "source": ncsu.SOURCE,
                    "term": term,
                    "fetched_at": now_iso(),
                    "sample": False,
                    "courses": courses,
                },
            )
            job["status"] = "done"
    except Exception as exc:  # noqa: BLE001 - Persist background failures for polling.
        job["status"] = "error"
        job["errors"].append({"course": "catalog", "error": str(exc)})
    job["finished"] = now_iso()
    store.write_json(f"planner_jobs/{job_id}.json", job)
    return job


def start_refresh(store, catalog):
    job_id = "c_" + uuid.uuid4().hex[:12]
    store.write_json(
        f"planner_jobs/{job_id}.json",
        {
            "job_id": job_id,
            "status": "running",
            "started": now_iso(),
            "finished": None,
            "errors": [],
        },
    )
    threading.Thread(
        target=run_refresh,
        args=(store,),
        kwargs={"catalog": catalog, "job_id": job_id},
        name="catalog-" + job_id,
        daemon=True,
    ).start()
    return {"job_id": job_id, "status": "running"}


def get_status(store, job_id):
    if not isinstance(job_id, str) or not re.fullmatch(r"c_[a-f0-9]{12}", job_id):
        raise ValueError("invalid catalog job_id")
    job = store.read_json(f"planner_jobs/{job_id}.json")
    if job is None:
        raise ValueError("unknown catalog job_id")
    return {"job": job}


def main():
    store = Store(os.environ.get("DATA_DIR", "/data"))
    job = run_refresh(store)
    print(json.dumps(job, indent=2))
    return 0 if job["status"] == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
