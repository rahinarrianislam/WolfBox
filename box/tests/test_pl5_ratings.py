"""Tests for RateMyProfessor integration, ratings module, solver rating rules, and prefs."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
import httpx
import pytest

from wolfbox.planner import handlers, prefs, ratings, solver
from wolfbox.store import Store


def test_sample_fallback_known_and_unknown():
    res = ratings.get_ratings(["Dr. Ada Park", "Dr. Elena Rostova", "Ghost Professor"])
    assert res["Dr. Ada Park"] is not None
    assert res["Dr. Ada Park"]["rating"] == 4.8
    assert res["Dr. Ada Park"]["source"] == "sample"
    assert res["Dr. Ada Park"]["num_ratings"] > 0
    assert res["Dr. Ada Park"]["would_take_again"] is not None

    assert res["Dr. Elena Rostova"] is not None
    assert res["Dr. Elena Rostova"]["rating"] == 4.7
    assert res["Dr. Elena Rostova"]["source"] == "sample"

    # Missing professor -> None, never raises
    assert res["Ghost Professor"] is None


def test_cache_hit_and_ttl(tmp_path):
    store = Store(str(tmp_path))
    now = time.time()
    initial_cache = {
        "Dr. Cached": {
            "cached_at": now - 3600,  # 1 hour old (fresh)
            "rating": {
                "rating": 4.7,
                "difficulty": 2.2,
                "num_ratings": 30,
                "would_take_again": 90.0,
                "source": "rmp",
                "url": "https://www.ratemyprofessors.com/professor/999",
            },
        },
        "Dr. Expired": {
            "cached_at": now - 90000,  # 25 hours old (> 24h TTL)
            "rating": {
                "rating": 2.0,
                "difficulty": 4.5,
                "num_ratings": 5,
                "would_take_again": 20.0,
                "source": "rmp",
            },
        },
    }
    store.write_json("rmp_cache.json", initial_cache)

    res = ratings.get_ratings(["Dr. Cached", "Dr. Expired"], store)
    assert res["Dr. Cached"] is not None
    assert res["Dr. Cached"]["source"] == "cache"
    assert res["Dr. Cached"]["rating"] == 4.7
    assert res["Dr. Cached"]["url"] == "https://www.ratemyprofessors.com/professor/999"

    # Expired should not use cache; Dr. Expired not in sample -> None
    assert res["Dr. Expired"] is None


def test_live_lookup_parsing_from_canned_graphql(monkeypatch, tmp_path):
    store = Store(str(tmp_path))
    monkeypatch.setenv("RMP_LIVE", "1")

    canned_response = {
        "data": {
            "newSearch": {
                "teachers": {
                    "edges": [
                        {
                            "node": {
                                "firstName": "Ada",
                                "lastName": "Park",
                                "department": "Computer Science",
                                "avgRating": 4.95,
                                "avgDifficulty": 2.1,
                                "numRatings": 88,
                                "wouldTakeAgainPercent": 96.0,
                                "legacyId": "1234567",
                            }
                        }
                    ]
                }
            }
        }
    }

    class MockResponse:
        status_code = 200

        def json(self):
            return canned_response

    def mock_post(url, json=None, headers=None, timeout=None):
        return MockResponse()

    monkeypatch.setattr(httpx, "post", mock_post)

    res = ratings.get_ratings(["Dr. Ada Park"], store)
    assert res["Dr. Ada Park"] is not None
    assert res["Dr. Ada Park"]["rating"] == 4.95
    assert res["Dr. Ada Park"]["source"] == "rmp"
    assert (
        res["Dr. Ada Park"]["url"]
        == "https://www.ratemyprofessors.com/professor/1234567"
    )

    # Check that it was saved to cache
    saved_cache = store.read_json("rmp_cache.json")
    assert "Dr. Ada Park" in saved_cache
    assert saved_cache["Dr. Ada Park"]["rating"]["rating"] == 4.95


def test_timeout_falls_back_to_sample(monkeypatch, tmp_path):
    store = Store(str(tmp_path))
    monkeypatch.setenv("RMP_LIVE", "1")

    def mock_timeout(url, json=None, headers=None, timeout=None):
        raise httpx.TimeoutException("Read timed out")

    monkeypatch.setattr(httpx, "post", mock_timeout)

    # Must not raise, falls back to sample
    res = ratings.get_ratings(["Dr. Ada Park"], store)
    assert res["Dr. Ada Park"] is not None
    assert res["Dr. Ada Park"]["rating"] == 4.8
    assert res["Dr. Ada Park"]["source"] == "sample"


def test_min_rating_filter():
    mock_catalog = [
        {
            "code": "CSC 216",
            "name": "Software Development",
            "credits": 3,
            "prereqs": [],
            "satisfies": ["major_core"],
            "sections": [
                {
                    "id": "CSC216-001",
                    "days": ["Mon", "Wed"],
                    "start": "10:00",
                    "end": "11:15",
                    "instructor": "Dr. Bad Prof",
                },
                {
                    "id": "CSC216-002",
                    "days": ["Tue", "Thu"],
                    "start": "10:00",
                    "end": "11:15",
                    "instructor": "Dr. Good Prof",
                },
                {
                    "id": "CSC216-003",
                    "days": ["Mon", "Wed"],
                    "start": "14:00",
                    "end": "15:15",
                    "instructor": "Dr. Unrated Prof",
                },
            ],
        },
        {
            "code": "ENG 101",
            "name": "Academic Writing",
            "credits": 9,  # Inflate so total credits meet min 12
            "prereqs": [],
            "satisfies": ["general_ed"],
            "sections": [
                {
                    "id": "ENG101-001",
                    "days": ["Fri"],
                    "start": "09:00",
                    "end": "12:00",
                    "instructor": "Dr. English",
                }
            ],
        },
    ]
    mock_reqs = [
        {"id": "major_core", "name": "Major Core", "courses_needed": 1},
        {"id": "general_ed", "name": "General Ed", "courses_needed": 1},
    ]

    mock_ratings = {
        "Dr. Bad Prof": {"rating": 2.2, "source": "sample"},
        "Dr. Good Prof": {"rating": 4.6, "source": "sample"},
        "Dr. English": {"rating": 4.0, "source": "sample"},
    }

    # Filter with min_rating = 3.5
    options = solver.solve(
        catalog=mock_catalog,
        requirements=mock_reqs,
        completed=[],
        prefs={"min_credits": 12, "max_credits": 15, "min_rating": 3.5},
        ratings=mock_ratings,
    )

    assert len(options) > 0
    # No option should contain CSC216-001 (bad prof with 2.2)
    for opt in options:
        sec_ids = [s["section_id"] for s in opt["sections"]]
        assert "CSC216-001" not in sec_ids
        # CSC216-002 (4.6) or CSC216-003 (unrated) can appear
        assert any(sid in ("CSC216-002", "CSC216-003") for sid in sec_ids)


def test_ratings_change_ranking():
    # Two sections of elective courses, one with high rated prof, one with low rated prof
    mock_catalog = [
        {
            "code": "CSC 226",
            "name": "Discrete Math",
            "credits": 12,
            "prereqs": [],
            "satisfies": ["math"],
            "sections": [
                {
                    "id": "CSC226-001",
                    "days": ["Mon", "Wed"],
                    "start": "10:00",
                    "end": "11:15",
                    "instructor": "Dr. Stellar",
                }
            ],
        },
        {
            "code": "ST 370",
            "name": "Probability & Statistics",
            "credits": 12,
            "prereqs": [],
            "satisfies": ["math"],
            "sections": [
                {
                    "id": "ST370-001",
                    "days": ["Mon", "Wed"],
                    "start": "10:00",
                    "end": "11:15",
                    "instructor": "Dr. Mediocre",
                }
            ],
        },
    ]
    mock_reqs = [{"id": "math", "name": "Math Requirement", "courses_needed": 1}]

    # When ratings are provided: Dr. Stellar (4.9) vs Dr. Mediocre (2.5)
    mock_ratings = {
        "Dr. Stellar": {"rating": 4.9, "source": "sample"},
        "Dr. Mediocre": {"rating": 2.5, "source": "sample"},
    }

    options = solver.solve(
        catalog=mock_catalog,
        requirements=mock_reqs,
        completed=[],
        prefs={"min_credits": 12, "max_credits": 15, "prefer_high_rated": True},
        ratings=mock_ratings,
    )

    assert len(options) == 2
    # The top option should be CSC 226 (Dr. Stellar)
    assert options[0]["sections"][0]["course"] == "CSC 226"
    assert options[0]["sections"][0]["instructor"] == "Dr. Stellar"
    assert options[0]["sections"][0]["rating"]["rating"] == 4.9
    assert options[0]["avg_rating"] == 4.9
    assert options[0]["score"] > options[1]["score"]


def test_solver_unchanged_when_ratings_none():
    data_dir = Path(__file__).resolve().parents[1] / "data"
    with open(data_dir / "catalog.json") as f:
        cat = json.load(f)
    with open(data_dir / "requirements.json") as f:
        reqs = json.load(f)

    # Solve without ratings
    options = solver.solve(
        catalog=cat,
        requirements=reqs,
        completed=["CSC 116", "MA 141"],
        prefs={"prefer_compact": True},
        ratings=None,
    )

    assert len(options) <= 3
    for opt in options:
        assert opt["avg_rating"] is None
        for s in opt["sections"]:
            assert "instructor" in s
            assert s["rating"] is None


def test_prefs_parsing_regex_phrases():
    # 1. Rating threshold
    p, echo = prefs.parse("I need rating above 4 and 15 credits max")
    assert p["min_rating"] == 4.0
    assert p["prefer_high_rated"] is True
    assert "Min rating 4.0" in echo

    # 2. Stars threshold
    p2, echo2 = prefs.parse("at least 3.5 stars, good professors, Fridays off")
    assert p2["min_rating"] == 3.5
    assert p2["prefer_high_rated"] is True
    assert "Fri" in p2["prefer_days_off"]

    # 3. Explicit high rated
    p3, echo3 = prefs.parse("avoid bad profs and minimize gaps")
    assert p3["prefer_high_rated"] is True
    assert p3["prefer_compact"] is True
    assert "Prefer highly rated professors" in echo3

    # 4. Ignore ratings
    p4, echo4 = prefs.parse("ignore professor ratings, no 8 AMs")
    assert p4["prefer_high_rated"] is False
    assert p4["earliest_start"] == "09:00"


def test_handlers_plan_solve_and_get_integration(tmp_path):
    store = Store(str(tmp_path))

    # Initial plan_get
    res_get = handlers.handle_plan_get(store, {})
    assert "plan" in res_get
    assert "remaining" in res_get
    assert res_get["options"] == []

    # plan_set_prefs
    res_prefs = handlers.handle_plan_set_prefs(
        store, {"text": "good professors, rating above 3.5"}
    )
    assert res_prefs["prefs"]["prefer_high_rated"] is True
    assert res_prefs["prefs"]["min_rating"] == 3.5

    # plan_solve
    res_solve = handlers.handle_plan_solve(store, {})
    assert len(res_solve["options"]) > 0
    top_opt = res_solve["options"][0]
    assert top_opt["avg_rating"] is not None
    assert top_opt["avg_rating"] >= 3.5
    for s in top_opt["sections"]:
        assert s.get("instructor") is not None
        if s.get("rating"):
            assert s["rating"]["rating"] >= 3.5

    # Subsequent plan_get retrieves enriched options
    res_get_after = handlers.handle_plan_get(store, {})
    assert len(res_get_after["options"]) > 0
    assert res_get_after["options"][0]["avg_rating"] is not None
