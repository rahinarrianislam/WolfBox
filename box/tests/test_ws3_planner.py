import json
from pathlib import Path

import pytest
from wolfbox.planner import handlers, prefs, solver
from wolfbox.store import Store

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture
def catalog():
    with open(DATA_DIR / "catalog.json", "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def requirements():
    with open(DATA_DIR / "requirements.json", "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def alex_completed():
    with open(DATA_DIR / "transcript_alex.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        return data["completed"]


def test_prefs_regex_demo_sentence():
    """Verify regex parsing of the demo sentence from the spec."""
    text = "no 8 AMs, I work Tue/Thu after noon, 15 credits max"
    parsed, echo = prefs.parse(text)

    assert parsed["earliest_start"] == "09:00"
    assert len(parsed["blocked"]) == 1
    assert set(parsed["blocked"][0]["days"]) == {"Tue", "Thu"}
    assert parsed["blocked"][0]["start"] == "12:00"
    assert parsed["blocked"][0]["end"] == "23:59"
    assert parsed["max_credits"] == 15
    assert parsed["min_credits"] == 12

    assert "09:00" in echo
    assert "Tue/Thu" in echo
    assert "15 credits" in echo


def test_prefs_regex_various_phrasings():
    """Test various preferences: days off, compact, must take, before 9."""
    text = "nothing before 9, Fridays off, compact, must take CSC 316, 12 credits min, 15 credits max"
    parsed, echo = prefs.parse(text)

    assert parsed["earliest_start"] == "09:00"
    assert "Fri" in parsed["prefer_days_off"]
    assert parsed["prefer_compact"] is True
    assert "CSC 316" in parsed["must_take"]
    assert parsed["min_credits"] == 12
    assert parsed["max_credits"] == 15
    assert "CSC 316" in echo
    assert "Fri" in echo


def test_solver_no_conflicts_and_prereqs(catalog, requirements, alex_completed):
    """Verify that every option has zero time conflicts and all prereqs are met."""
    demo_prefs = {
        "earliest_start": "09:00",
        "blocked": [{"days": ["Tue", "Thu"], "start": "12:00", "end": "23:59"}],
        "min_credits": 12,
        "max_credits": 15,
        "prefer_days_off": [],
        "prefer_compact": False,
        "must_take": [],
    }

    options = solver.solve(catalog, requirements, alex_completed, demo_prefs)
    assert len(options) == 3

    courses_by_code = {c["code"]: c for c in catalog["courses"]}
    completed_set = set(alex_completed)

    for opt in options:
        sections = opt["sections"]
        course_codes = [s["course"] for s in sections]

        # Check prereqs
        for code in course_codes:
            course = courses_by_code[code]
            assert code not in completed_set
            for p in course.get("prereqs", []):
                assert p in completed_set

        # Check pairwise conflicts
        for i in range(len(sections)):
            for j in range(i + 1, len(sections)):
                s1 = sections[i]
                s2 = sections[j]
                shared_days = set(s1["days"]) & set(s2["days"])
                if shared_days:
                    # Times must not overlap
                    overlap = s1["start"] < s2["end"] and s2["start"] < s1["end"]
                    assert not overlap, f"Conflict found between {s1} and {s2}"


def test_solver_hard_prefs_respected(catalog, requirements, alex_completed):
    """Verify that no section starts before earliest_start and none in blocked windows."""
    demo_prefs = {
        "earliest_start": "09:00",
        "blocked": [{"days": ["Tue", "Thu"], "start": "12:00", "end": "23:59"}],
        "min_credits": 12,
        "max_credits": 15,
    }

    options = solver.solve(catalog, requirements, alex_completed, demo_prefs)
    assert len(options) > 0

    for opt in options:
        for s in opt["sections"]:
            # Check earliest start
            assert s["start"] >= "09:00", f"Section starts too early: {s}"

            # Check blocked window
            if any(d in ["Tue", "Thu"] for d in s["days"]):
                # Overlap test with 12:00-23:59
                overlaps_blocked = s["start"] < "23:59" and "12:00" < s["end"]
                assert not overlaps_blocked, f"Section in blocked window: {s}"


def test_solver_distinct_course_sets_and_max_three(
    catalog, requirements, alex_completed
):
    """Verify <= 3 options and all returned options have distinct course sets."""
    demo_prefs = {
        "earliest_start": "09:00",
        "blocked": [{"days": ["Tue", "Thu"], "start": "12:00", "end": "23:59"}],
        "min_credits": 12,
        "max_credits": 15,
    }

    options = solver.solve(catalog, requirements, alex_completed, demo_prefs)
    assert 1 <= len(options) <= 3

    seen_sets = set()
    for opt in options:
        c_set = frozenset(s["course"] for s in opt["sections"])
        assert c_set not in seen_sets, f"Duplicate course set in options: {c_set}"
        seen_sets.add(c_set)


def test_solver_deterministic(catalog, requirements, alex_completed):
    """Verify two runs with the same parameters return identical results."""
    demo_prefs = {
        "earliest_start": "09:00",
        "blocked": [{"days": ["Tue", "Thu"], "start": "12:00", "end": "23:59"}],
        "min_credits": 12,
        "max_credits": 15,
    }

    run1 = solver.solve(catalog, requirements, alex_completed, demo_prefs)
    run2 = solver.solve(catalog, requirements, alex_completed, demo_prefs)

    assert run1 == run2


def test_solver_full_sections_excluded(catalog, requirements, alex_completed):
    """Verify that sections marked in full_sections are excluded from all options."""
    demo_prefs = {
        "earliest_start": "09:00",
        "blocked": [{"days": ["Tue", "Thu"], "start": "12:00", "end": "23:59"}],
        "min_credits": 12,
        "max_credits": 15,
    }

    initial_options = solver.solve(catalog, requirements, alex_completed, demo_prefs)
    assert len(initial_options) > 0

    first_sec_id = initial_options[0]["sections"][0]["section_id"]
    new_options = solver.solve(
        catalog,
        requirements,
        alex_completed,
        demo_prefs,
        full_sections=[first_sec_id],
    )

    for opt in new_options:
        sec_ids = [s["section_id"] for s in opt["sections"]]
        assert first_sec_id not in sec_ids


def test_handlers_end_to_end(tmp_path, alex_completed):
    """Test plan_get, plan_set_prefs, and plan_solve handlers using Store."""
    store = Store(tmp_path)

    # 1. Initialize plan with completed courses
    store.save_plan({"completed": alex_completed})

    # 2. plan_get before prefs
    res_get1 = handlers.handle_plan_get(store, {})
    assert "plan" in res_get1
    assert "remaining" in res_get1
    assert "options" in res_get1
    assert res_get1["options"] == []
    assert len(res_get1["remaining"]) == 4

    # Check remaining details
    csc_core = next(r for r in res_get1["remaining"] if r["id"] == "CSC_CORE")
    assert csc_core["completed"] == 2  # CSC 116, CSC 216
    assert csc_core["remaining"] == 2  # 4 - 2

    # 3. plan_set_prefs
    demo_text = "no 8 AMs, I work Tue/Thu after noon, 15 credits max"
    res_prefs = handlers.handle_plan_set_prefs(store, {"text": demo_text})
    assert "prefs" in res_prefs
    assert "echo" in res_prefs
    assert res_prefs["prefs"]["earliest_start"] == "09:00"

    # Verify plan was updated in store
    plan = store.load_plan()
    assert plan["prefs_text"] == demo_text
    assert plan["prefs"]["max_credits"] == 15

    # 4. plan_solve
    res_solve = handlers.handle_plan_solve(store, {})
    assert "options" in res_solve
    options = res_solve["options"]
    assert len(options) == 3

    for opt in options:
        assert opt["credits"] <= 15
        assert len(opt["explanation"]) > 0
        assert len(opt["explanation"].split()) <= 50

    # 5. plan_get after solve returns stored options
    res_get2 = handlers.handle_plan_get(store, {})
    assert len(res_get2["options"]) == 3
    assert res_get2["options"] == options


def test_handlers_default_completed_when_missing(tmp_path):
    """Verify handlers fall back to default completed courses ['CSC 116', 'MA 141'] if missing."""
    store = Store(tmp_path)
    # Empty plan
    res_get = handlers.handle_plan_get(store, {})
    assert res_get["plan"] == {}
    assert len(res_get["remaining"]) == 4

    res_solve = handlers.handle_plan_solve(store, {})
    assert "options" in res_solve
    assert len(res_solve["options"]) > 0


def test_solver_must_take(catalog, requirements, alex_completed):
    """Verify that options must include specified must_take courses."""
    prefs_with_must_take = {
        "must_take": ["CSC 316"],
        "min_credits": 12,
        "max_credits": 15,
    }
    options = solver.solve(catalog, requirements, alex_completed, prefs_with_must_take)
    assert len(options) > 0
    for opt in options:
        courses = [s["course"] for s in opt["sections"]]
        assert "CSC 316" in courses


def test_solver_must_take_ineligible(catalog, requirements, alex_completed):
    """If a must_take course is impossible/ineligible, solver should return empty list."""
    prefs_ineligible = {
        "must_take": ["NONEXISTENT 999"],
    }
    options = solver.solve(catalog, requirements, alex_completed, prefs_ineligible)
    assert options == []


def test_handlers_registry():
    """Verify HANDLERS dict has required keys matching router expectation."""
    assert "plan_get" in handlers.HANDLERS
    assert "plan_set_prefs" in handlers.HANDLERS
    assert "plan_solve" in handlers.HANDLERS
    for fn in handlers.HANDLERS.values():
        assert callable(fn)
