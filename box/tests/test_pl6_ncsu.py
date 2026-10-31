"""Offline public-schedule contracts; every HTTP response is a saved fixture."""

import json
import threading
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from wolfbox.main import create_app
from wolfbox.planner import handlers
from wolfbox.router import dispatch
from wolfbox.store import Store

FIXTURES = Path(__file__).with_name("fixtures")


def parse(name, code):
    from wolfbox.planner.ncsu import parse_course

    return parse_course((FIXTURES / name).read_text(), code)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("RMP_LIVE", "0")
    monkeypatch.setenv("CATALOG_SOURCE", "sample")
    monkeypatch.setenv("GEMMA_BACKEND", "fake")
    original_send = httpx.Client.send

    def reject(client, *args, **kwargs):
        if isinstance(client, TestClient):
            return original_send(client, *args, **kwargs)
        raise AssertionError("network is forbidden in PL6 tests")

    monkeypatch.setattr(httpx.Client, "send", reject)


@pytest.mark.parametrize(
    "name,code,title,count,days,start,end,instructor,seats",
    [
        (
            "ncsu_csc_316.html",
            "CSC 316",
            "Data Structures and Algorithms",
            2,
            ["Mon", "Wed"],
            "11:45",
            "13:00",
            "Jason Tyler King",
            {"open": 84, "capacity": 90},
        ),
        (
            "ncsu_csc_230.html",
            "CSC 230",
            "C and Software Tools",
            2,
            ["Tue", "Thu"],
            "11:45",
            "13:00",
            "David Brian Sturgill",
            {"open": 77, "capacity": 81},
        ),
        (
            "ncsu_ma_305.html",
            "MA 305",
            "Introduction to Linear Algebra and Matrices",
            4,
            ["Tue", "Thu"],
            "08:30",
            "09:45",
            "Zixuan Cang",
            {"open": 83, "capacity": 90},
        ),
        (
            "ncsu_st_370.html",
            "ST 370",
            "Probability and Statistics for Engineers",
            6,
            ["Tue", "Thu"],
            "13:30",
            "14:45",
            "Justin Blaise Post",
            {"open": 89, "capacity": 90},
        ),
    ],
)
def test_saved_courses(name, code, title, count, days, start, end, instructor, seats):
    c = parse(name, code)
    assert (c["code"], c["title"], c["credits"]) == (code, title, 3)
    assert len(c["sections"]) == count
    assert c["sections"][0] == {
        "id": code.replace(" ", "") + "-001",
        "days": days,
        "start": start,
        "end": end,
        "instructor": instructor,
        "seats": seats,
        "status": "Open",
    }


def test_prereqs_only_from_prerequisite_paragraph():
    c = parse("ncsu_csc_316.html", "CSC 316")
    assert c["prereqs"] == ["CSC 216", "CSC 226", "MA 225"]
    assert c["prereqs_any"] is True
    assert parse("ncsu_csc_230.html", "CSC 999") is None


def test_closed_waitlist_tba_and_lecture_filter():
    c = parse("ncsu_edge_cases.html", "CSC 999")
    assert [s["id"] for s in c["sections"]] == ["CSC999-001", "CSC999-002"]
    assert c["sections"][0]["status"] == "Closed"
    assert c["sections"][0]["seats"] == {"open": 0, "capacity": 20}
    assert c["sections"][0]["start"] == "12:00"
    assert c["sections"][1]["status"] == "Waitlist"
    assert c["sections"][1]["start"] == "00:00"
    from wolfbox.planner.ncsu import parse_course

    html = (
        (FIXTURES / "ncsu_edge_cases.html")
        .read_text()
        .replace("<td>Lec</td>", "<td>Rec</td>")
    )
    assert len(parse_course(html, "CSC 999")["sections"]) == 3


def test_fetch_request_uses_subjects_and_saved_response(monkeypatch):
    from wolfbox.planner import ncsu

    ncsu.subjects.cache_clear()

    def send(client, request, **kwargs):
        if request.url.path.endswith("subjects.php"):
            assert request.content == b"strm=2271"
            return httpx.Response(
                200,
                json=json.loads((FIXTURES / "ncsu_subjects.json").read_text()),
                request=request,
            )
        assert request.url.path.endswith("search.php")
        from urllib.parse import parse_qs

        assert parse_qs(request.content.decode()) == {
            "term": ["2271"],
            "subject": ["CSC - Computer Science"],
            "course-inequality": ["="],
            "course-number": ["316"],
            "current_strm": ["2271"],
        }
        assert "Mozilla" in request.headers["user-agent"]
        assert request.extensions["timeout"]["read"] == 5
        return httpx.Response(
            200,
            json={"html": (FIXTURES / "ncsu_csc_316.html").read_text()},
            request=request,
        )

    monkeypatch.setattr(httpx.Client, "send", send)
    assert ncsu.fetch_course("CSC 316", "2271")["sections"][0]["days"] == ["Mon", "Wed"]
    ncsu.subjects.cache_clear()


def test_refresh_writes_live_courses_and_never_invents_missing_sections(tmp_path):
    from wolfbox.planner import refresh

    store = Store(tmp_path)
    sample = {
        "courses": [
            {"code": "CSC 316", "satisfies": ["CORE"], "sections": [{"id": "fake"}]},
            {
                "code": "CSC 999",
                "title": "Absent",
                "satisfies": ["OTHER"],
                "sections": [{"id": "fake"}],
            },
        ]
    }

    def fetch(code, term):
        assert term == "2271"
        return parse("ncsu_csc_316.html", code)

    job = refresh.run_refresh(store, catalog=sample, fetcher=fetch, term="2271")
    assert job["status"] == "done"
    assert (job["courses_found"], job["sections_found"], job["missing"]) == (
        1,
        2,
        ["CSC 999"],
    )
    live = store.read_json("catalog_ncsu.json")
    assert live["source"] == "ncsu-public-class-search"
    assert live["term"] == "2271" and live["fetched_at"] and live["sample"] is False
    assert live["courses"][0]["satisfies"] == ["CORE"]
    assert live["courses"][1]["sections"] == []
    assert store.read_json("planner_jobs/" + job["job_id"] + ".json") == job


def test_failed_refresh_preserves_previous_catalog(tmp_path):
    from wolfbox.planner import refresh

    store = Store(tmp_path)
    store.write_json("catalog_ncsu.json", {"courses": [{"code": "old"}]})

    def fail(*args):
        raise httpx.ConnectError("offline")

    job = refresh.run_refresh(
        store, catalog={"courses": [{"code": "CSC 316", "satisfies": []}]}, fetcher=fail
    )
    assert job["status"] == "error" and job["errors"]
    assert store.read_json("catalog_ncsu.json") == {"courses": [{"code": "old"}]}


def test_refresh_envelopes_run_background_and_poll(tmp_path, monkeypatch):
    from wolfbox.planner import refresh

    release, entered = threading.Event(), threading.Event()

    def fetch(code, term):
        entered.set()
        assert release.wait(5)
        return parse("ncsu_csc_230.html", code)

    monkeypatch.setattr(refresh.ncsu, "fetch_course", fetch)
    monkeypatch.setattr(
        handlers,
        "_load_sample_catalog",
        lambda: {"courses": [{"code": "CSC 230", "satisfies": ["CORE"]}]},
    )
    store = Store(tmp_path)
    try:
        started = dispatch(store, {"type": "plan_refresh"})
        assert started["ok"] and started["status"] == "running"
        assert entered.wait(2)
        status = dispatch(
            store, {"type": "plan_refresh_status", "job_id": started["job_id"]}
        )
        assert status["job"]["status"] == "running"
    finally:
        release.set()
    # Join only the worker belonging to this store (no network or polling).
    for worker in threading.enumerate():
        if worker.name == "catalog-" + started["job_id"]:
            worker.join(5)
    assert (
        dispatch(store, {"type": "plan_refresh_status", "job_id": started["job_id"]})[
            "job"
        ]["status"]
        == "done"
    )
    assert not dispatch(store, {"type": "plan_refresh_status", "job_id": "missing"})[
        "ok"
    ]
    assert not dispatch(store, {"type": "plan_refresh_status", "job_id": "../plan"})[
        "ok"
    ]


def test_live_selection_solver_excludes_full_and_propagates_seats(
    tmp_path, monkeypatch
):
    store = Store(tmp_path)
    c = parse("ncsu_edge_cases.html", "CSC 999")
    open_section = dict(
        c["sections"][0],
        id="CSC999-003",
        status="Open",
        seats={"open": 8, "capacity": 20},
    )
    c["sections"].append(open_section)
    store.write_json(
        "catalog_ncsu.json",
        {
            "source": "ncsu-public-class-search",
            "term": "2271",
            "fetched_at": "2026-10-31T12:00:00Z",
            "sample": False,
            "courses": [c],
        },
    )
    store.save_plan(
        {
            "completed": ["MA 241"],
            "prefs": {"min_credits": 3, "max_credits": 3, "must_take": ["CSC 999"]},
        }
    )
    monkeypatch.setenv("CATALOG_SOURCE", "ncsu")
    options = handlers.handle_plan_solve(store, {})["options"]
    assert len(options) == 1
    assert options[0]["sections"][0]["section_id"] == "CSC999-003"
    assert options[0]["sections"][0]["seats"] == {"open": 8, "capacity": 20}
    assert options[0]["sections"][0]["rating"] is None
    assert handlers.handle_plan_get(store, {})["catalog"] == {
        "source": "ncsu-public-class-search",
        "term": "2271",
        "fetched_at": "2026-10-31T12:00:00Z",
        "sample": False,
    }
    assert (
        handlers.handle_plan_solve(store, {"full_sections": ["CSC999-003"]})["options"]
        == []
    )


def test_sample_default_and_missing_live_fallback(tmp_path, monkeypatch):
    store = Store(tmp_path)
    assert handlers.handle_plan_get(store, {})["catalog"]["sample"] is True
    monkeypatch.setenv("CATALOG_SOURCE", "ncsu")
    assert handlers.handle_plan_get(store, {})["catalog"] == {
        "source": "sample",
        "term": None,
        "fetched_at": None,
        "sample": True,
    }
    assert len(handlers.handle_plan_solve(store, {})["options"]) == 3


def test_schedules_preserve_sync_and_add_catalog(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    # TestClient overrides Client.send, so no outbound HTTP is involved.
    with TestClient(create_app()) as client:
        assert client.get("/schedules").json() == [
            {"id": "sync", "cron": "*/15 * * * *", "prompt": '{"v":1,"type":"sync"}'},
            {
                "id": "catalog",
                "cron": "0 */6 * * *",
                "prompt": '{"v":1,"type":"plan_refresh"}',
            },
        ]


def test_saved_sample_options_are_not_presented_as_live(tmp_path, monkeypatch):
    store = Store(tmp_path)
    assert handlers.handle_plan_solve(store, {})["options"]
    store.write_json(
        "catalog_ncsu.json",
        {
            "source": "ncsu-public-class-search",
            "term": "2271",
            "fetched_at": "2026-10-31T12:00:00Z",
            "sample": False,
            "courses": [],
        },
    )
    monkeypatch.setenv("CATALOG_SOURCE", "ncsu")
    result = handlers.handle_plan_get(store, {})
    assert result["catalog"]["sample"] is False
    assert result["options"] == []


def test_real_reserved_sections_are_not_available_to_solver():
    c = parse("ncsu_csc_116.html", "CSC 116")
    reserved = next(s for s in c["sections"] if s["id"] == "CSC116-002")
    assert reserved["status"] == "Closed"


def test_grade_or_better_does_not_make_and_prereqs_optional():
    from wolfbox.planner.ncsu import parse_course

    html = (
        (FIXTURES / "ncsu_edge_cases.html")
        .read_text()
        .replace("CSC 216 or MA 241.", "CSC 216 with a C or better and MA 241.")
    )
    assert parse_course(html, "CSC 999")["prereqs_any"] is False


def test_saved_live_catalog_yields_three_options_for_alex_demo(tmp_path, monkeypatch):
    store = Store(tmp_path)
    catalog = json.loads((FIXTURES / "ncsu_catalog_2271.json").read_text())
    sample = json.loads((handlers.DATA_DIR / "catalog.json").read_text())
    assert [c["code"] for c in catalog["courses"]] == [
        c["code"] for c in sample["courses"]
    ]
    store.write_json("catalog_ncsu.json", catalog)
    completed = json.loads((handlers.DATA_DIR / "transcript_alex.json").read_text())[
        "completed"
    ]
    store.save_plan({"completed": completed})
    handlers.handle_plan_set_prefs(
        store, {"text": "no 8 AMs, I work Tue/Thu after noon, 15 credits max"}
    )
    monkeypatch.setenv("CATALOG_SOURCE", "ncsu")
    result = handlers.handle_plan_solve(store, {})
    assert result["catalog"]["sample"] is False
    assert len(result["options"]) == 3
    by_id = {s["id"]: s for c in catalog["courses"] for s in c["sections"]}
    assert (
        len({tuple(s["course"] for s in o["sections"]) for o in result["options"]}) == 3
    )
    for option in result["options"]:
        assert 12 <= option["credits"] <= 15
        for section in option["sections"]:
            original = by_id[section["section_id"]]
            assert original["status"] == "Open" and original["seats"]["open"] > 0
            assert section["start"] >= "09:00"
            assert (
                not ({"Tue", "Thu"} & set(section["days"])) or section["end"] <= "12:00"
            )
            assert section["instructor"] == original["instructor"]
            assert section["seats"] == original["seats"]


@pytest.mark.parametrize(
    "status,open_seats", [("Closed", 8), ("Waitlist", 8), ("Open", 0)]
)
def test_unavailable_sections_are_excluded_even_if_status_and_seats_disagree(
    status, open_seats
):
    from wolfbox.planner import solver

    c = parse("ncsu_edge_cases.html", "CSC 999")
    c["sections"] = [
        dict(
            c["sections"][0], status=status, seats={"open": open_seats, "capacity": 20}
        )
    ]
    assert (
        solver.solve(
            {"courses": [c]}, {}, ["MA 241"], {"min_credits": 3, "max_credits": 3}
        )
        == []
    )
