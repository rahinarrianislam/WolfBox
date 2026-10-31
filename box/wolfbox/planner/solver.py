"""Deterministic course schedule solver (pure, no Gemma dependencies)."""

from __future__ import annotations

import itertools
from typing import Any


def _time_to_mins(t_str: str) -> int:
    parts = t_str.split(":")
    return int(parts[0]) * 60 + int(parts[1])


def _normalize_days(days: list[str] | str) -> list[str]:
    if isinstance(days, list):
        return [d.capitalize()[:3] if len(d) > 3 else d for d in days]
    # Handle string format like "MWF" or "TR"
    res = []
    d = days.upper()
    if "M" in d:
        res.append("Mon")
    if "T" in d and ("TH" in d or "R" in d):
        res.append("Tue")
        res.append("Thu")
    elif "T" in d:
        res.append("Tue")
    if "W" in d:
        res.append("Wed")
    if "R" in d and "Thu" not in res:
        res.append("Thu")
    if "F" in d:
        res.append("Fri")
    return res


def _sections_conflict(s1: dict, s2: dict) -> bool:
    s1_days = set(_normalize_days(s1.get("days", [])))
    s2_days = set(_normalize_days(s2.get("days", [])))
    if not (s1_days & s2_days):
        return False
    s1_start = s1.get("start", "00:00")
    s1_end = s1.get("end", "23:59")
    s2_start = s2.get("start", "00:00")
    s2_end = s2.get("end", "23:59")
    return s1_start < s2_end and s2_start < s1_end


def solve(
    catalog: dict | list,
    requirements: dict | list,
    completed: list[str] | set[str],
    prefs: dict | None = None,
    full_sections: list[str] | None = None,
    ratings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Pure, deterministic solver for conflict-free college course schedules.

    Returns top <= 3 options with distinct course sets.
    """
    if prefs is None:
        prefs = {}
    if full_sections is None:
        full_sections = []

    full_sec_set = set(full_sections)
    completed_set = {c.strip() for c in (completed or [])}

    # Parse catalog
    if isinstance(catalog, dict):
        raw_courses = catalog.get("courses", [])
    elif isinstance(catalog, list):
        raw_courses = catalog
    else:
        raw_courses = []

    # Parse requirements
    if isinstance(requirements, dict):
        raw_reqs = requirements.get("requirements", [])
    elif isinstance(requirements, list):
        raw_reqs = requirements
    else:
        raw_reqs = []

    # Prefs defaults
    min_credits = prefs.get("min_credits")
    if min_credits is None:
        min_credits = 12
    max_credits = prefs.get("max_credits")
    if max_credits is None:
        max_credits = 15

    earliest_start = prefs.get("earliest_start")
    blocked_windows = prefs.get("blocked", []) or []
    prefer_days_off = [
        _normalize_days([d])[0] for d in prefs.get("prefer_days_off", []) or []
    ]
    prefer_compact = bool(prefs.get("prefer_compact", False))
    must_take = [
        c.strip() for c in (prefs.get("must_take", []) or []) if c and c.strip()
    ]
    prefer_high_rated = bool(prefs.get("prefer_high_rated", True))
    min_rating = prefs.get("min_rating")
    if min_rating is not None:
        try:
            min_rating = float(min_rating)
        except (TypeError, ValueError):
            min_rating = None

    # Calculate unfulfilled requirements
    # Requirement needed count:
    req_needed: dict[str, int] = {}
    req_names: dict[str, str] = {}
    for r in raw_reqs:
        r_id = r["id"]
        req_names[r_id] = r.get("name", r_id)
        courses_needed = r.get("courses_needed", 0)
        # Count completed courses that satisfy this requirement
        completed_in_req = sum(
            1
            for c in raw_courses
            if c["code"] in completed_set and r_id in c.get("satisfies", [])
        )
        remaining_needed = max(0, courses_needed - completed_in_req)
        req_needed[r_id] = remaining_needed

    # 1. Eligible courses: prerequisites met, course not completed
    eligible_courses: dict[str, dict] = {}
    for c in raw_courses:
        code = c["code"].strip()
        if code in completed_set:
            continue
        prereqs = c.get("prereqs", [])
        prereqs_met = any if c.get("prereqs_any") else all
        if not prereqs or prereqs_met(p.strip() in completed_set for p in prereqs):
            eligible_courses[code] = c

    # Check must_take: all must be in eligible_courses
    for m in must_take:
        if m not in eligible_courses:
            return []

    # 2. Filter sections for each eligible course by hard constraints
    valid_sections_by_course: dict[str, list[dict]] = {}
    for code, course in eligible_courses.items():
        valid_secs = []
        for sec in course.get("sections", []):
            sec_id = sec.get("id", "")
            if (
                sec_id in full_sec_set
                or sec.get("status") in {"Closed", "Waitlist"}
                or (sec.get("seats") is not None and sec["seats"].get("open", 0) <= 0)
            ):
                continue

            sec_start = sec.get("start", "00:00")
            sec_end = sec.get("end", "23:59")

            # Check earliest_start
            if earliest_start and sec_start < earliest_start:
                continue

            # Check blocked windows
            sec_days = set(_normalize_days(sec.get("days", [])))
            blocked_conflict = False
            for b in blocked_windows:
                b_days = set(_normalize_days(b.get("days", [])))
                if sec_days & b_days:
                    b_start = b.get("start", "00:00")
                    b_end = b.get("end", "23:59")
                    if sec_start < b_end and b_start < sec_end:
                        blocked_conflict = True
                        break
            if blocked_conflict:
                continue

            # Check min_rating: unrated sections pass
            if min_rating is not None and ratings:
                sec_inst = sec.get("instructor")
                r_info = ratings.get(sec_inst)
                r_val = None
                if isinstance(r_info, dict):
                    r_val = r_info.get("rating")
                elif isinstance(r_info, (int, float)):
                    r_val = float(r_info)
                if r_val is not None and r_val < min_rating:
                    continue

            valid_secs.append(sec)

        if valid_secs:
            valid_sections_by_course[code] = valid_secs

    # If any must_take course has 0 valid sections, impossible
    for m in must_take:
        if not valid_sections_by_course.get(m):
            return []

    # Candidate courses are eligible courses with at least 1 valid section
    candidate_codes = sorted(valid_sections_by_course.keys())

    # 3. Enumerate course subsets within [min_credits, max_credits] that contain must_take
    valid_combos = []
    # Cap combinations to avoid slow explosion
    max_k = min(len(candidate_codes), 7)
    for k in range(1, max_k + 1):
        for combo in itertools.combinations(candidate_codes, k):
            if must_take and not all(m in combo for m in must_take):
                continue
            tot_credits = sum(eligible_courses[c]["credits"] for c in combo)
            if min_credits <= tot_credits <= max_credits:
                valid_combos.append(combo)

    # Sort combos by heuristic requirement coverage so we evaluate promising course sets first
    def combo_heuristic(combo):
        tot_c = sum(eligible_courses[c]["credits"] for c in combo)
        req_hits = sum(
            1
            for c in combo
            for r in eligible_courses[c].get("satisfies", [])
            if req_needed.get(r, 0) > 0
        )
        return (-req_hits, -tot_c, combo)

    valid_combos.sort(key=combo_heuristic)
    valid_combos = valid_combos[:150]  # bounded enumeration

    # 4. For each course set, find conflict-free section combination and score it
    options_by_course_set: dict[tuple[str, ...], dict] = {}

    for combo in valid_combos:
        # Sections for each course in combo
        sec_lists = [valid_sections_by_course[c] for c in combo]

        best_option = None
        best_score = -1.0

        # Enumerate section assignments for this combo
        for sec_choice in itertools.product(*sec_lists):
            # Check pairwise conflicts
            conflict = False
            for i in range(len(sec_choice)):
                for j in range(i + 1, len(sec_choice)):
                    if _sections_conflict(sec_choice[i], sec_choice[j]):
                        conflict = True
                        break
                if conflict:
                    break
            if conflict:
                continue

            # Compute score
            # A) Requirement coverage
            total_courses = len(combo)
            useful_courses = sum(
                1
                for c in combo
                if any(
                    req_needed.get(r, 0) > 0
                    for r in eligible_courses[c].get("satisfies", [])
                )
            )
            req_score = (useful_courses / total_courses) if total_courses > 0 else 1.0

            # B) Prefer days off
            if prefer_days_off:
                active_days = set()
                for sec in sec_choice:
                    active_days.update(_normalize_days(sec.get("days", [])))
                free_count = sum(1 for d in prefer_days_off if d not in active_days)
                days_off_score = free_count / len(prefer_days_off)
            else:
                days_off_score = 1.0

            # C) Prefer compact
            if prefer_compact:
                # Calculate total gap minutes across all days
                day_sections: dict[str, list[dict]] = {}
                for sec in sec_choice:
                    for d in _normalize_days(sec.get("days", [])):
                        day_sections.setdefault(d, []).append(sec)

                total_gap_mins = 0
                for d, secs in day_sections.items():
                    sorted_secs = sorted(secs, key=lambda s: s.get("start", "00:00"))
                    for idx in range(len(sorted_secs) - 1):
                        curr_end = _time_to_mins(sorted_secs[idx].get("end", "00:00"))
                        next_start = _time_to_mins(
                            sorted_secs[idx + 1].get("start", "00:00")
                        )
                        if next_start > curr_end:
                            total_gap_mins += next_start - curr_end
                compact_score = 1.0 / (1.0 + total_gap_mins / 60.0)
            else:
                compact_score = 1.0

            # Compute rating score and option avg rating
            sec_ratings = []
            for sec in sec_choice:
                inst = sec.get("instructor")
                r_info = ratings.get(inst) if ratings else None
                sec_ratings.append(r_info)

            numeric_ratings = []
            for r in sec_ratings:
                if isinstance(r, dict):
                    v = r.get("rating")
                    if isinstance(v, (int, float)):
                        numeric_ratings.append(float(v))
                elif isinstance(r, (int, float)):
                    numeric_ratings.append(float(r))

            if numeric_ratings:
                opt_avg_rating = sum(numeric_ratings) / len(numeric_ratings)
            else:
                opt_avg_rating = None

            if ratings is not None and prefer_high_rated:
                rating_score = (opt_avg_rating / 5.0) if opt_avg_rating is not None else 0.6
                raw_score = 0.40 * req_score + 0.25 * days_off_score + 0.15 * compact_score + 0.20 * rating_score
            else:
                raw_score = 0.50 * req_score + 0.30 * days_off_score + 0.20 * compact_score

            if raw_score > best_score:
                best_score = raw_score
                # Build satisfied reqs list
                satisfies_set = set()
                for c in combo:
                    satisfies_set.update(eligible_courses[c].get("satisfies", []))

                formatted_sections = [
                    {
                        "course": combo[idx],
                        "section_id": sec_choice[idx]["id"],
                        "days": _normalize_days(sec_choice[idx].get("days", [])),
                        "start": sec_choice[idx].get("start", ""),
                        "end": sec_choice[idx].get("end", ""),
                        "instructor": sec_choice[idx].get("instructor"),
                        "rating": sec_ratings[idx],
                        **(
                            {
                                "seats": sec_choice[idx]["seats"],
                                "status": sec_choice[idx].get("status"),
                            }
                            if "seats" in sec_choice[idx]
                            else {}
                        ),
                    }
                    for idx in range(len(combo))
                ]
                # Sort sections deterministically by course code
                formatted_sections.sort(key=lambda s: s["course"])

                tot_credits = sum(eligible_courses[c]["credits"] for c in combo)
                best_option = {
                    "sections": formatted_sections,
                    "credits": tot_credits,
                    "score": round(raw_score, 2),
                    "satisfies": sorted(satisfies_set),
                    "explanation": "",
                    "avg_rating": round(opt_avg_rating, 2) if opt_avg_rating is not None else None,
                    "_raw_score": raw_score,
                }

        if best_option is not None:
            options_by_course_set[combo] = best_option

    # 5. Sort options by score descending, then credits descending, then course codes
    sorted_options = sorted(
        options_by_course_set.values(),
        key=lambda opt: (
            -opt["_raw_score"],
            -opt["credits"],
            [s["course"] for s in opt["sections"]],
        ),
    )

    # Clean internal _raw_score
    result = []
    for opt in sorted_options[:3]:
        opt.pop("_raw_score", None)
        result.append(opt)

    return result
