import json
from pathlib import Path, PurePosixPath

from .models import Manifest, identifier


def save_manifest(data, site_dir, task_id, job_dir=None, download=None):
    manifest = Manifest.model_validate(data).model_dump(exclude_none=True)
    identifier(task_id)
    course_dir = Path(site_dir) / manifest["course"]
    for item in manifest["items"]:
        seen = set()
        for file in item["files"]:
            if file["path"] in seen:
                raise ValueError("Duplicate file path")
            seen.add(file["path"])
            agent_path = file.pop("agent_path", None)
            if agent_path:
                root = PurePosixPath(job_dir or "/invalid") / "exports"
                remote = PurePosixPath(agent_path)
                if ".." in remote.parts or not remote.is_relative_to(root) or not download:
                    raise ValueError("Agent file must be inside this task's exports directory")
                content = download(str(remote))
                if not isinstance(content, bytes) or len(content) > 8 * 1024 * 1024:
                    raise ValueError("Export exceeds the 8 MiB file limit")
                target = course_dir / "moodle" / task_id / file["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                file["url"] = f"/course/{manifest['course']}/moodle/{task_id}/{file['path']}"
        readme = f"{item['id']}/README.md"
        if readme not in seen:
            target = course_dir / "moodle" / task_id / readme
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"# {item['title']}\n\n{item['description']}\n", encoding="utf-8")
            item["files"].append({"path": readme, "url": f"/course/{manifest['course']}/moodle/{task_id}/{readme}"})
    course_dir.mkdir(parents=True, exist_ok=True)
    path = course_dir / "course.moodle.json"
    temporary = course_dir / f".course.moodle.{task_id}.tmp"
    temporary.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return manifest


def course_url(course="csc116", source=None):
    """Use this when configuring COURSE_URL; the mock remains the default."""
    import os
    source = source or os.getenv("COURSE_SOURCE", "mock")
    if source not in {"mock", "moodle"}:
        raise ValueError("COURSE_SOURCE must be mock or moodle")
    filename = "course.moodle.json" if source == "moodle" else "course.json"
    return f"/course/{identifier(course)}/{filename}"
