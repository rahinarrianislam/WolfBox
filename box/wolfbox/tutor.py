"""History-aware tutoring, using only the shared Store contract.

WS1 calls on_run_complete from its background worker and merges HANDLERS.
Model failures always leave a usable hint, answer, summary, or nudge draft.
"""

from __future__ import annotations

import copy
import difflib
from datetime import UTC, datetime

from . import gemma

TAGS = gemma.TAGS
CHAT_TIMEOUT = 23.0
BACKGROUND_TIMEOUT = 20.0
FALLBACK_HINT = "Trace the failing test's input through your code one step at a time. What does your code do at the boundary or with an empty input?"


def _call(fn, timeout=BACKGROUND_TIMEOUT):
    def invoke():
        with gemma.time_budget(timeout):
            result = fn()
            return result, gemma.last_llm()

    return gemma._bounded(invoke, timeout)


def _code(store, assignment, run=None):
    if run:
        run_id = run["run_id"]
        for rel in (
            f"snapshots/{run_id}/{assignment}.py",
            f"snapshots/{run_id}/{assignment}/{assignment}.py",
        ):
            text = store.read_text(rel)
            if text is not None:
                return text
    return store.read_text(f"repo/{assignment}/{assignment}.py", "") or ""


def _assignment(store, requested=None):
    if requested is not None:
        if (
            not isinstance(requested, str)
            or not requested
            or "/" in requested
            or "\\" in requested
            or requested in {".", ".."}
        ):
            raise ValueError("Invalid assignment")
        return requested
    # Synced metadata wins over an older run from a previously due assignment.
    dated = []
    courses = store.path("courses")
    for path in courses.glob("*/docs/*/meta.json"):
        meta = store.read_json(str(path.relative_to(store.data_dir)), {}) or {}
        workspace = meta.get("workspace")
        if not workspace or not list(store.path(workspace).glob("test_*.py")):
            continue
        for deadline in meta.get("deadlines", []):
            try:
                due = datetime.fromisoformat(deadline["due"])
                if due.tzinfo is None:
                    due = due.replace(tzinfo=UTC)
                dated.append((due, store.path(workspace).name))
            except (KeyError, TypeError, ValueError):
                continue
    if dated:
        now = datetime.now(UTC)
        already_due = [item for item in dated if item[0] <= now]
        return _assignment(store, (max(already_due) if already_due else min(dated))[1])
    runs = store.list_runs(limit=1)
    if runs:
        return _assignment(store, runs[0].get("assignment", "hw4"))
    repo = store.path("repo")
    candidates = (
        sorted(
            p.name for p in repo.iterdir() if p.is_dir() and list(p.glob("test_*.py"))
        )
        if repo.exists()
        else []
    )
    return candidates[-1] if candidates else "hw4"


def on_run_complete(store, run) -> None:
    run.update(tags=[], related_past=[], hint=None, hint_status="ready")
    try:
        if not run.get("failed"):
            return
        assignment = _assignment(store, run.get("assignment", "hw4"))
        code = _code(store, assignment, run)
        tags, _ = _call(lambda: gemma.classify(code, run["failed"]))
        tags = list(dict.fromkeys(tag for tag in tags if tag in TAGS))
        run["tags"] = tags
        profile = store.load_profile()
        history = copy.deepcopy(profile)
        # Cite past assignments first: "this looks like your hw2 bug" is the product.
        for tag, items in list(history.get("examples", {}).items()):
            other = [e for e in items if e.get("assignment") != assignment]
            history["examples"][tag] = other or items
        examples = profile.setdefault("examples", {})
        counts = profile.setdefault("mistake_counts", {})
        # Match old history before the current run becomes one of the examples.
        run["related_past"] = [
            {
                "run_id": example["run_id"],
                "assignment": example["assignment"],
                "tag": tag,
            }
            for tag in tags
            for example in history.get("examples", {}).get(tag, [])[-2:]
            if example.get("run_id")
            and example.get("assignment")
            and example["run_id"] != run["run_id"]
        ]
        note = "; ".join(
            f"{failure.get('test', 'test')} failed" for failure in run["failed"]
        )[:200]
        for tag in tags:
            counts[tag] = counts.get(tag, 0) + 1
            # One example per assignment, so retries don't evict older assignments.
            kept = [e for e in examples.get(tag, []) if e.get("assignment") != assignment]
            examples[tag] = (
                kept + [{"run_id": run["run_id"], "assignment": assignment, "note": note}]
            )[-5:]
        store.save_profile(profile)
        run["hint"], run["llm"] = _call(
            lambda: gemma.hint(code, run["failed"], tags, history)
        )
    except Exception:  # noqa: BLE001 - every model failure gets a usable fallback
        run["hint"] = FALLBACK_HINT
        run["llm"] = {"backend": "fallback", "model": "canned"}
    finally:
        store.save_run(run)


def nudge_draft(store, nudge, last_run) -> str:
    try:
        draft, _ = _call(
            lambda: gemma.nudge_draft(
                nudge.get("reason", "Repeated test failures"), last_run
            ),
            timeout=CHAT_TIMEOUT,
        )
        return draft
    except Exception:  # noqa: BLE001 - every model failure gets a usable fallback
        assignment = (last_run or {}).get("assignment", "my assignment")
        return f"Hi! I'm stuck on {assignment} after repeated failing tests. Could we trace one failing input together in office hours?"


def ask(store, payload):
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("ask requires nonempty text")
    # The deadline covers context reads, generation, validation, and its retry.
    try:
        with gemma.time_budget(CHAT_TIMEOUT):
            assignment = _assignment(store, payload.get("assignment"))
            runs = store.list_runs(limit=1, assignment=assignment)
            last = runs[0] if runs else None
            code = _code(store, assignment)
            profile = store.load_profile()
            reply, _ = _call(
                lambda: gemma.answer(text, code, last, profile), timeout=CHAT_TIMEOUT
            )
            return {"reply": reply}
    except Exception:  # noqa: BLE001 - every model failure gets a usable fallback
        return {"reply": FALLBACK_HINT}


def _recent_with_diffs(store, assignment):
    runs = store.list_runs(limit=10, assignment=assignment)
    for index, run in enumerate(runs[:-1]):
        current = _code(store, assignment, run)
        previous = _code(store, assignment, runs[index + 1])
        diff = difflib.unified_diff(
            previous.splitlines(),
            current.splitlines(),
            fromfile=runs[index + 1]["run_id"],
            tofile=run["run_id"],
            lineterm="",
        )
        run["code_diff"] = "\n".join(diff)[:2000]
    return runs


def _fallback_summary(profile, runs, assignment):
    last = runs[0] if runs else {}
    tests = (
        ", ".join(failure.get("test", "unknown") for failure in last.get("failed", []))
        or "none recorded"
    )
    patterns = (
        ", ".join(
            f"{tag} ({count})"
            for tag, count in sorted(
                profile.get("mistake_counts", {}).items(),
                key=lambda pair: pair[1],
                reverse=True,
            )[:3]
        )
        or "no recorded patterns"
    )
    text = (
        f"### Where they are\n{assignment}; failing tests: {tests}.\n"
        f"### What they tried\n{len(runs)} recent recorded attempts; review their test results and code changes together.\n"
        f"### Patterns\n{patterns}.\n### Suggested opener\nWhat should happen on the smallest failing input?"
    )
    return " ".join(text.split()[:200]) if len(text.split()) > 200 else text


def ta_summary(store, payload):
    assignment = _assignment(store, payload.get("assignment"))
    runs = store.list_runs(limit=1, assignment=assignment)
    key = runs[0]["run_id"] if runs else f"no-runs:{assignment}"
    cache = store.read_json("ta_summary_cache.json", {}) or {}
    if key in cache:
        return {"markdown": cache[key]}
    profile = store.load_profile()
    try:
        with gemma.time_budget(CHAT_TIMEOUT):
            recent = _recent_with_diffs(store, assignment)
            code = _code(store, assignment)
            markdown, _ = _call(
                lambda: gemma.ta_summary(profile, recent, code), timeout=CHAT_TIMEOUT
            )
    except Exception:  # noqa: BLE001 - every model failure gets a usable fallback
        markdown = _fallback_summary(
            profile, store.list_runs(limit=10, assignment=assignment), assignment
        )
    cache[key] = markdown
    store.write_json("ta_summary_cache.json", cache)
    return {"markdown": markdown}


HANDLERS = {"ask": ask, "ta_summary": ta_summary}
