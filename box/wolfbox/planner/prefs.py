"""Parse student natural language preferences and explain generated schedules."""

from __future__ import annotations

import json
import re
from typing import Any

from wolfbox import gemma

VALID_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
DAY_NORM_MAP = {
    "mon": "Mon",
    "monday": "Mon",
    "mondays": "Mon",
    "tue": "Tue",
    "tues": "Tue",
    "tuesday": "Tue",
    "tuesdays": "Tue",
    "wed": "Wed",
    "wednesday": "Wed",
    "wednesdays": "Wed",
    "thu": "Thu",
    "thur": "Thu",
    "thurs": "Thu",
    "thursday": "Thu",
    "thursdays": "Thu",
    "fri": "Fri",
    "friday": "Fri",
    "fridays": "Fri",
}


def _normalize_time(t: str | None) -> str | None:
    if not t or not isinstance(t, str):
        return None
    t = t.strip()
    m = re.match(r"^(\d{1,2}):(\d{2})$", t)
    if m:
        h, mn = int(m.group(1)), int(m.group(2))
        return f"{h:02d}:{mn:02d}"
    m_hour = re.match(r"^(\d{1,2})\s*(am|pm)?$", t, re.IGNORECASE)
    if m_hour:
        h = int(m_hour.group(1))
        ampm = (m_hour.group(2) or "").lower()
        if ampm == "pm" and h < 12:
            h += 12
        elif ampm == "am" and h == 12:
            h = 0
        return f"{h:02d}:00"
    return None


def _normalize_day(d: str) -> str | None:
    if not isinstance(d, str):
        return None
    return DAY_NORM_MAP.get(d.strip().lower())


def _build_echo(prefs: dict) -> str:
    """Produce a concise one-line restatement of the parsed preferences."""
    parts = []
    if prefs.get("earliest_start"):
        parts.append(f"No classes before {prefs['earliest_start']}")
    if prefs.get("blocked"):
        for b in prefs["blocked"]:
            days_str = "/".join(b.get("days", []))
            start = b.get("start", "")
            end = b.get("end", "")
            if start == "12:00" and end == "23:59":
                parts.append(f"{days_str} afternoons blocked")
            elif start == "00:00" and end == "12:00":
                parts.append(f"{days_str} mornings blocked")
            else:
                parts.append(f"Blocked {days_str} {start}–{end}")
    min_c = prefs.get("min_credits", 12)
    max_c = prefs.get("max_credits", 15)
    if min_c and max_c:
        if min_c == max_c:
            parts.append(f"{max_c} credits")
        else:
            parts.append(f"{min_c}–{max_c} credits")
    elif max_c:
        parts.append(f"Max {max_c} credits")
    elif min_c:
        parts.append(f"Min {min_c} credits")

    if prefs.get("prefer_days_off"):
        days_str = ", ".join(prefs["prefer_days_off"])
        parts.append(f"Prefer {days_str} off")
    if prefs.get("prefer_compact"):
        parts.append("Compact schedule")
    if prefs.get("must_take"):
        courses_str = ", ".join(prefs["must_take"])
        parts.append(f"Must take {courses_str}")

    if not parts:
        return "Standard schedule (12–15 credits)."
    return "; ".join(parts) + "."


def _regex_parse(text: str) -> dict[str, Any]:
    """Deterministic regex fallback parser for preferences."""
    prefs: dict[str, Any] = {
        "earliest_start": None,
        "blocked": [],
        "min_credits": 12,
        "max_credits": 15,
        "prefer_days_off": [],
        "prefer_compact": False,
        "must_take": [],
    }

    if not text:
        return prefs

    # 1. Earliest start: "no 8 AMs", "nothing before 9", "nothing before 9am"
    if re.search(r"\bno\s+8(?::00)?\s*(?:am|a\.m\.|ams)?\b", text, re.IGNORECASE):
        prefs["earliest_start"] = "09:00"
    else:
        m_early = re.search(
            r"\b(?:nothing|no\s+classes?)\s+before\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
            text,
            re.IGNORECASE,
        )
        if m_early:
            hour = int(m_early.group(1))
            ampm = (m_early.group(3) or "").lower()
            if ampm == "pm" and hour < 12:
                hour += 12
            mins = int(m_early.group(2) or 0)
            prefs["earliest_start"] = f"{hour:02d}:{mins:02d}"

    # 2. Blocked windows: e.g. "I work Tue/Thu after noon", "Tue/Thu afternoons"
    # Detect Tue/Thu afternoon
    if re.search(
        r"\b(?:tue(?:s)?(?:\s*/\s*|\s+and\s+)thu(?:rs)?(?:days?)?)\b",
        text,
        re.IGNORECASE,
    ):
        if re.search(
            r"\b(?:after\s+noon|afternoons?(?:\s+off)?|after\s+12(?::00)?(?:\s*pm)?)\b",
            text,
            re.IGNORECASE,
        ):
            prefs["blocked"].append(
                {"days": ["Tue", "Thu"], "start": "12:00", "end": "23:59"}
            )
        elif re.search(
            r"\b(?:mornings?(?:\s+off)?|before\s+noon|before\s+12(?::00)?(?:\s*pm)?)\b",
            text,
            re.IGNORECASE,
        ):
            prefs["blocked"].append(
                {"days": ["Tue", "Thu"], "start": "00:00", "end": "12:00"}
            )

    # 3. Credits: "15 credits max", "max 15 credits", "min 12 credits", "12 credits min"
    m_max = re.search(
        r"(?:max(?:imum)?\s*(\d+)\s*credits?|(\d+)\s*(?:credits?|cr)\s*max(?:imum)?|no\s+more\s+than\s+(\d+)\s*credits?|at\s+most\s+(\d+)\s*credits?)",
        text,
        re.IGNORECASE,
    )
    if m_max:
        val = next(g for g in m_max.groups() if g is not None)
        prefs["max_credits"] = int(val)

    m_min = re.search(
        r"(?:min(?:imum)?\s*(\d+)\s*credits?|(\d+)\s*(?:credits?|cr)\s*min(?:imum)?|at\s+least\s+(\d+)\s*credits?)",
        text,
        re.IGNORECASE,
    )
    if m_min:
        val = next(g for g in m_min.groups() if g is not None)
        prefs["min_credits"] = int(val)

    # 4. Prefer days off: "Fridays off", "prefer Fridays off", "no Friday"
    m_off = re.search(
        r"\b(?:prefer\s+)?(mon|tue|wed|thu|fri)(?:day|days)?s?\s+off\b",
        text,
        re.IGNORECASE,
    )
    if m_off:
        day_norm = _normalize_day(m_off.group(1))
        if day_norm and day_norm not in prefs["prefer_days_off"]:
            prefs["prefer_days_off"].append(day_norm)
    else:
        m_no_day = re.search(
            r"\bno\s+(mon|tue|wed|thu|fri)(?:day|days)?s?\b", text, re.IGNORECASE
        )
        if m_no_day:
            day_norm = _normalize_day(m_no_day.group(1))
            # Don't confuse "no 8 AMs" or "no Tue/Thu afternoons" with whole day off
            if day_norm and day_norm not in prefs["prefer_days_off"]:
                # Only if not already part of blocked window
                already_blocked = any(
                    day_norm in b.get("days", []) for b in prefs["blocked"]
                )
                if not already_blocked:
                    prefs["prefer_days_off"].append(day_norm)

    # 5. Must take: "must take CSC 316", "need CSC 316"
    m_must = re.findall(
        r"(?:must\s+take|need|require)\s+([A-Za-z]{2,4}\s*\d{3})", text, re.IGNORECASE
    )
    for c in m_must:
        # Normalize code with single space: "CSC 316"
        parts = re.split(r"\s+", c.strip())
        if len(parts) == 2:
            code_norm = f"{parts[0].upper()} {parts[1]}"
        else:
            m_split = re.match(r"^([A-Za-z]{2,4})(\d{3})$", c.strip())
            code_norm = (
                f"{m_split.group(1).upper()} {m_split.group(2)}"
                if m_split
                else c.upper()
            )
        if code_norm not in prefs["must_take"]:
            prefs["must_take"].append(code_norm)

    # 6. Prefer compact: "compact", "prefer compact", "minimize gaps", "no gaps"
    if re.search(r"\b(?:compact|minimize\s+gaps|no\s+gaps)\b", text, re.IGNORECASE):
        prefs["prefer_compact"] = True

    return prefs


def parse(text: str) -> tuple[dict[str, Any], str]:
    """Parse text into Prefs dict and an echo string."""
    if gemma.mode() != "fake":
        system_prompt = (
            "You are a course scheduling preference parser. Extract the student's constraints "
            "into JSON matching the exact schema:\n"
            "{\n"
            '  "earliest_start": "HH:MM" or null,\n'
            '  "blocked": [{"days": ["Mon"|"Tue"|"Wed"|"Thu"|"Fri"], "start": "HH:MM", "end": "HH:MM"}],\n'
            '  "min_credits": int,\n'
            '  "max_credits": int,\n'
            '  "prefer_days_off": ["Mon"|"Tue"|"Wed"|"Thu"|"Fri"],\n'
            '  "prefer_compact": bool,\n'
            '  "must_take": ["COURSE CODE"]\n'
            "}\n"
            "Output only JSON without backticks."
        )
        try:
            raw_text, _, _ = gemma._generate(
                system_prompt, text, json_mode=True, timeout=10.0
            )
            data = json.loads(raw_text)
            if isinstance(data, dict) and data:
                # Strictly validate and drop unknown keys
                clean_prefs: dict[str, Any] = {
                    "earliest_start": _normalize_time(data.get("earliest_start")),
                    "blocked": [],
                    "min_credits": int(data.get("min_credits", 12)),
                    "max_credits": int(data.get("max_credits", 15)),
                    "prefer_days_off": [],
                    "prefer_compact": bool(data.get("prefer_compact", False)),
                    "must_take": [],
                }
                for b in data.get("blocked", []):
                    if isinstance(b, dict):
                        b_days = [
                            _normalize_day(d)
                            for d in b.get("days", [])
                            if _normalize_day(d)
                        ]
                        b_start = _normalize_time(b.get("start", "00:00")) or "00:00"
                        b_end = _normalize_time(b.get("end", "23:59")) or "23:59"
                        if b_days:
                            clean_prefs["blocked"].append(
                                {"days": b_days, "start": b_start, "end": b_end}
                            )

                for d in data.get("prefer_days_off", []):
                    nd = _normalize_day(d)
                    if nd and nd not in clean_prefs["prefer_days_off"]:
                        clean_prefs["prefer_days_off"].append(nd)

                for mt in data.get("must_take", []):
                    if isinstance(mt, str) and mt.strip():
                        clean_prefs["must_take"].append(mt.strip().upper())

                echo = _build_echo(clean_prefs)
                return clean_prefs, echo
        except Exception:  # noqa: BLE001, S110
            pass

    # Fallback to deterministic regex parser
    prefs = _regex_parse(text)
    echo = _build_echo(prefs)
    return prefs, echo


def _template_explain(opt: dict, prefs: dict) -> str:
    courses = sorted({s["course"] for s in opt.get("sections", [])})
    credits = opt.get("credits", 0)
    all_days = set()
    for s in opt.get("sections", []):
        all_days.update(s.get("days", []))

    notes = []
    if "Fri" not in all_days:
        notes.append("Fridays off")
    if prefs.get("blocked"):
        notes.append("respects your blocked work hours")
    if prefs.get("earliest_start"):
        notes.append(f"no classes before {prefs['earliest_start']}")

    notes_str = f" with {', '.join(notes)}" if notes else ""
    reqs = opt.get("satisfies", [])
    req_str = f" Satisfies {', '.join(reqs)}." if reqs else ""
    return f"{credits} credits across {len(courses)} courses ({', '.join(courses)}){notes_str}.{req_str}"


def explain(options: list[dict], prefs: dict) -> list[str]:
    """Generate explanations (<= 50 words each) for the options."""
    if gemma.mode() != "fake":
        try:
            exps = []
            for opt in options:
                courses = sorted({s["course"] for s in opt.get("sections", [])})
                prompt = (
                    f"Write a concise explanation (under 40 words) for this schedule option.\n"
                    f"Courses: {courses}\n"
                    f"Credits: {opt.get('credits')}\n"
                    f"Preferences: {prefs}\n"
                    f"Do not invent any sections or courses."
                )
                text, _, _ = gemma._generate(
                    "You are a concise academic advisor. Limit response to <= 40 words.",
                    prompt,
                    timeout=5.0,
                )
                text = text.strip()
                if text and len(text.split()) <= 50:
                    exps.append(text)
                else:
                    exps.append(_template_explain(opt, prefs))
            if len(exps) == len(options):
                return exps
        except Exception:  # noqa: BLE001, S110
            pass

    return [_template_explain(opt, prefs) for opt in options]
