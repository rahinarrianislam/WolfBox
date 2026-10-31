from collections import Counter


def heatmap(students: list[dict], box_client) -> dict:
    tags = Counter()
    failing_tests = Counter()
    included = []
    for student in students:
        box_id = student.get("box_id")
        if not box_id:
            continue
        try:
            state = box_client.call(box_id, {"v": 1, "type": "get_state"})
            run_data = box_client.call(box_id, {"v": 1, "type": "list_runs"})
            if state.get("ok") is False or run_data.get("ok") is False:
                continue
            runs = run_data.get("runs", [])
        except Exception:
            continue
        included.append(f"Student {len(included) + 1}")
        counts = state.get("profile", {}).get("mistake_counts", {})
        tags.update({key: value for key, value in counts.items() if isinstance(value, int)})
        for run in runs:
            for tag in run.get("tags", []):
                if tag not in counts:
                    tags[tag] += 1
            for failure in run.get("failed", []):
                if failure.get("test"):
                    failing_tests[failure["test"]] += 1
    return {"students": included, "mistake_tags": dict(tags), "failing_tests": dict(failing_tests)}
