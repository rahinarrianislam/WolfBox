import json
import os
from pathlib import Path


DEFAULT_STUDENTS = {
    "alex": {"name": "Alex Rivera", "box_id": None, "backend": None},
    "sam": {"name": "Sam Chen", "box_id": None, "backend": None},
}


class Registry:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.getenv("REGISTRY_PATH", "./students.json"))
        self.students = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            return json.loads(self.path.read_text())
        return {student_id: dict(value) for student_id, value in DEFAULT_STUDENTS.items()}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.students, indent=2) + "\n")

    def get(self, student_id: str) -> dict | None:
        return self.students.get(student_id)

    def set(self, student_id: str, name: str, box_id: str, backend: str) -> dict:
        entry = {"name": name, "box_id": box_id, "backend": backend}
        selected = self.students.get(student_id, {}).get("canvas_course_id")
        if selected:
            entry["canvas_course_id"] = selected
        self.students[student_id] = entry
        self._save()
        return entry

    def select_canvas_course(self, student_id: str, course_id: str):
        self.students[student_id]["canvas_course_id"] = course_id
        self._save()

    def list(self) -> list[dict]:
        return [dict(id=student_id, **entry) for student_id, entry in self.students.items()]
