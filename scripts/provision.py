#!/usr/bin/env python3
"""Provision Maritime boxes for the WolfBox demo students.

needs WS0 verification: custom-image provisioning and env reload behavior.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "orchestrator"))

from wolfhub.boxes import MaritimeBoxClient  # noqa: E402
from wolfhub.registry import Registry  # noqa: E402


def main() -> None:
    client = MaritimeBoxClient()
    registry = Registry()
    for student_id, name in (("alex", "Alex Rivera"), ("sam", "Sam Chen")):
        box_id = client.ensure(student_id, name)
        result = client.call(box_id, {"v": 1, "type": "init", "student_id": student_id, "name": name})
        if result.get("ok") is False:
            raise RuntimeError(str(result.get("error", "Box initialization failed")))
        registry.set(student_id, name, box_id, "maritime")
        print(f"Provisioned {student_id}: {box_id}")


if __name__ == "__main__":
    main()
