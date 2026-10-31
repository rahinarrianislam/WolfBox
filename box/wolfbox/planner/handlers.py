"""Handlers for plan_* envelopes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from wolfbox.planner import prefs, ratings, solver
from wolfbox.store import Store

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _load_catalog() -> dict:
    catalog_path = DATA_DIR / "catalog.json"
    if catalog_path.exists():
        with open(catalog_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"courses": []}


def _load_requirements() -> dict:
    req_path = DATA_DIR / "requirements.json"
    if req_path.exists():
        with open(req_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"requirements": []}


def compute_remaining(
    catalog: dict, requirements: dict, completed: list[str] | set[str]
) -> list[dict[str, Any]]:
    """Compute remaining degree requirements given completed courses."""
    completed_set = {c.strip() for c in (completed or [])}
    courses = catalog.get("courses", [])
    raw_reqs = requirements.get("requirements", [])

    results = []
    for req in raw_reqs:
        r_id = req["id"]
        name = req.get("name", r_id)
        courses_needed = req.get("courses_needed", 0)

        # Courses in catalog that satisfy this requirement
        matching_courses = [c for c in courses if r_id in c.get("satisfies", [])]

        completed_count = sum(1 for c in matching_courses if c["code"] in completed_set)
        remaining_count = max(0, courses_needed - completed_count)
        options_codes = sorted(
            [c["code"] for c in matching_courses if c["code"] not in completed_set]
        )

        results.append(
            {
                "id": r_id,
                "name": name,
                "courses_needed": courses_needed,
                "completed": completed_count,
                "remaining": remaining_count,
                "options": options_codes,
            }
        )

    return results


def handle_plan_get(store: Store, payload: dict) -> dict:
    """plan_get {} -> {plan, remaining, options}."""
    plan = store.load_plan()
    completed = plan.get("completed")
    if completed is None:
        completed = ["CSC 116", "MA 141"]

    catalog = _load_catalog()
    requirements = _load_requirements()
    remaining = compute_remaining(catalog, requirements, completed)
    options = plan.get("last_options", []) or []

    if options:
        inst_names = []
        for opt in options:
            for s in opt.get("sections", []):
                inst = s.get("instructor")
                if inst and inst not in inst_names:
                    inst_names.append(inst)
        if inst_names:
            prof_ratings = ratings.get_ratings(inst_names, store)
            for opt in options:
                num_rs = []
                for s in opt.get("sections", []):
                    inst = s.get("instructor")
                    if inst:
                        if "rating" not in s or s["rating"] is None:
                            s["rating"] = prof_ratings.get(inst)
                        r = s.get("rating")
                        if isinstance(r, dict) and isinstance(
                            r.get("rating"), (int, float)
                        ):
                            num_rs.append(r["rating"])
                        elif isinstance(r, (int, float)):
                            num_rs.append(r)
                if ("avg_rating" not in opt or opt["avg_rating"] is None) and num_rs:
                    opt["avg_rating"] = round(sum(num_rs) / len(num_rs), 2)

    return {
        "plan": plan,
        "remaining": remaining,
        "options": options,
    }


def handle_plan_set_prefs(store: Store, payload: dict) -> dict:
    """plan_set_prefs {text} -> {prefs, echo}."""
    text = payload.get("text", "")
    parsed_prefs, echo = prefs.parse(text)

    plan = store.load_plan()
    plan["prefs_text"] = text
    plan["prefs"] = parsed_prefs
    store.save_plan(plan)

    return {
        "prefs": parsed_prefs,
        "echo": echo,
    }


def handle_plan_solve(store: Store, payload: dict) -> dict:
    """plan_solve {full_sections?} -> {options}."""
    full_sections = payload.get("full_sections", []) or []

    plan = store.load_plan()
    completed = plan.get("completed")
    if not completed:
        completed = ["CSC 116", "MA 141"]

    current_prefs = plan.get("prefs") or {}
    catalog = _load_catalog()
    requirements = _load_requirements()

    # Collect instructor names from catalog
    instructors = []
    for c in catalog.get("courses", []):
        for s in c.get("sections", []):
            inst = s.get("instructor")
            if inst and inst not in instructors:
                instructors.append(inst)

    prof_ratings = ratings.get_ratings(instructors, store)

    options = solver.solve(
        catalog=catalog,
        requirements=requirements,
        completed=completed,
        prefs=current_prefs,
        full_sections=full_sections,
        ratings=prof_ratings,
    )

    explanations = prefs.explain(options, current_prefs)
    for opt, exp in zip(options, explanations):
        opt["explanation"] = exp

    plan["last_options"] = options
    store.save_plan(plan)

    return {"options": options}


HANDLERS = {
    "plan_get": handle_plan_get,
    "plan_set_prefs": handle_plan_set_prefs,
    "plan_solve": handle_plan_solve,
}
