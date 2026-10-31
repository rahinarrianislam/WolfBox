"""NC State public class search. No credentials, browser, or LLM required."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from html.parser import HTMLParser

import httpx

BASE_URL = "https://webappprd.acs.ncsu.edu/php/coursecat/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; WolfBox public schedule planner)"}
SOURCE = "ncsu-public-class-search"


@dataclass
class _Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)

    def text(self):
        return " ".join(
            " ".join(
                c.text() if isinstance(c, _Node) else c for c in self.children
            ).split()
        )

    def find(self, tag):
        for child in self.children:
            if isinstance(child, _Node):
                if child.tag == tag:
                    yield child
                yield from child.find(tag)


class _HTML(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = _Node("root")
        self.stack = [self.root]
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in {
            "br",
            "img",
            "hr",
            "input",
            "meta",
            "link",
            "wbr",
            "area",
            "base",
            "embed",
            "param",
            "source",
            "track",
            "col",
        }:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse_course(html: str, code: str) -> dict | None:
    """Parse only the requested course and timed sections from a saved/live response.

    shortcut: prerequisite expressions are flattened; for an OR expression any
    listed course qualifies, including mixed AND/OR, until a full requisite parser is needed.
    """
    course = next(
        (
            n
            for n in _HTML(html).root.find("section")
            if n.attrs.get("id") == code.replace(" ", "-")
        ),
        None,
    )
    if course is None:
        return None
    title = next(course.find("small"), None)
    units = re.search(r"Units:\s*(\d+(?:\.\d+)?)", course.text())
    if title is None or units is None:
        raise ValueError(f"{code}: missing title or units")
    prereq_text = " ".join(
        p.text()
        for p in course.find("p")
        if re.match(r"Prerequisites?\s*:", p.text(), re.IGNORECASE)
    )
    prereqs = list(dict.fromkeys(re.findall(r"\b[A-Z]{1,4}\s+\d{3}\b", prereq_text)))
    rows = [list(row.find("td")) for row in course.find("tr")]
    rows = [cells for cells in rows if len(cells) >= 7]
    has_lecture = any(cells[1].text().lower() == "lec" for cells in rows)
    sections = []
    for cells in rows:
        if has_lecture and cells[1].text().lower() != "lec":
            continue
        times = re.findall(r"\b\d{1,2}:\d{2}\s*[AP]M\b", cells[4].text(), re.IGNORECASE)
        days = []
        for li in cells[4].find("li"):
            if "meet" in li.attrs.get("class", "").split():
                for abbr in li.find("abbr"):
                    day = abbr.attrs.get("title", "").split(" - ")[0][:3]
                    if day in {"Mon", "Tue", "Wed", "Thu", "Fri"} and day not in days:
                        days.append(day)
        if len(times) != 2 or not days:
            continue  # TBA/asynchronous and multi-meeting rows cannot be represented safely.
        availability = cells[3].text()
        seat_match = re.search(r"(\d+)\s*/\s*(\d+)", availability)
        status_match = re.search(
            r"\b(Open|Closed|Reserved|Wait\s*list(?:ed)?)\b",
            availability,
            re.IGNORECASE,
        )
        if not seat_match or not status_match:
            raise ValueError(f"{code}: unrecognized availability: {availability}")
        status = status_match.group(1).lower()
        # Reserved seats require eligibility checks this hackathon planner cannot make.
        status = (
            "Closed"
            if status == "reserved"
            else ("Waitlist" if status.startswith("wait") else status.capitalize())
        )
        instructor = cells[6].text()
        if "," in instructor:
            last, first = instructor.split(",", 1)
            instructor = f"{first.strip()} {last.strip()}"
        sections.append(
            {
                "id": code.replace(" ", "") + "-" + cells[0].text(),
                "days": days,
                "start": datetime.strptime(times[0].upper(), "%I:%M %p").strftime(
                    "%H:%M"
                ),
                "end": datetime.strptime(times[1].upper(), "%I:%M %p").strftime(
                    "%H:%M"
                ),
                "instructor": instructor,
                "seats": {
                    "open": int(seat_match.group(1)),
                    "capacity": int(seat_match.group(2)),
                },
                "status": status,
            }
        )
    return {
        "code": code,
        "title": title.text(),
        "credits": float(units.group(1)),
        "prereqs": prereqs,
        "prereqs_any": len(prereqs) > 1
        and bool(re.search(r"\bor\s+(?:\[\s*)?[A-Z]{1,4}\s+\d{3}\b", prereq_text)),
        "sections": sections,
    }


@lru_cache(maxsize=8)
def subjects(term: str) -> dict[str, str]:
    response = httpx.post(
        BASE_URL + "subjects.php", data={"strm": term}, headers=HEADERS, timeout=5
    )
    response.raise_for_status()
    return {s.split(" - ")[0]: s for s in json.loads(response.json()["subj_js"])}


def fetch_course(code: str, term: str) -> dict | None:
    if not re.fullmatch(r"[A-Z]{1,4} \d{3}", code) or not re.fullmatch(r"\d{4}", term):
        raise ValueError("expected a course like CSC 316 and a four-digit term")
    subject, number = code.split()
    subject_name = subjects(term).get(subject)
    if subject_name is None:
        return None
    response = httpx.post(
        BASE_URL + "search.php",
        data={
            "term": term,
            "subject": subject_name,
            "course-inequality": "=",
            "course-number": number,
            "current_strm": term,
        },
        headers=HEADERS,
        timeout=5,
    )
    response.raise_for_status()
    body = response.json()
    if body.get("error"):
        raise ValueError(f"{code}: public search returned an error")
    return parse_course(body["html"], code)
