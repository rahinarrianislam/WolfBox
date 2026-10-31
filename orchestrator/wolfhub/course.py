import json
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()
SITE_DIR = Path(__file__).resolve().parents[1] / "course_site"


class PublishRequest(BaseModel):
    item: str


def publish_item(site_dir, item):
    manifest_path = Path(site_dir) / "csc116/course.json"
    staged_path = Path(site_dir) / "csc116/staged/items.json"
    manifest = json.loads(manifest_path.read_text())
    staged = json.loads(staged_path.read_text())
    entry = staged.get(item)
    if entry is None:
        raise ValueError("unknown staged item")
    if item == "hw4-v2":
        manifest["items"] = [entry if row["id"] == "hw4" else row for row in manifest["items"]]
    elif not any(row["id"] == entry["id"] for row in manifest["items"]):
        manifest["items"].append(entry)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return {"ok": True, "published": item, "items": [row["id"] for row in manifest["items"]]}


@router.post("/api/instructor/publish")
def publish(request: PublishRequest):
    try:
        return publish_item(SITE_DIR, request.item)
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/instructor/reset-course")
def reset_course():
    source = SITE_DIR / "csc116/course.original.json"
    target = SITE_DIR / "csc116/course.json"
    if not source.exists():
        raise HTTPException(status_code=500, detail="original course manifest is missing")
    shutil.copyfile(source, target)
    return {"ok": True, "reset": True}
