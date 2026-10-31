"""RateMyProfessor lookup with caching, live GraphQL queries, and sample fallback."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx

RMP_GRAPHQL_URL = "https://www.ratemyprofessors.com/graphql"
RMP_HEADERS = {
    "Authorization": "Basic dGVzdDp0ZXN0",
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/json",
}
RMP_QUERY = (
    "query($t:String!,$s:ID!){newSearch{teachers(query:{text:$t,schoolID:$s})"
    "{edges{node{firstName lastName department avgRating avgDifficulty numRatings "
    "wouldTakeAgainPercent legacyId}}}}}"
)
DEFAULT_SCHOOL_ID = "U2Nob29sLTY4NQ=="  # NC State
CACHE_FILE = "rmp_cache.json"
CACHE_TTL = 86400  # 24 hours
PER_CALL_TIMEOUT = 3.0
BATCH_BUDGET = 6.0

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


class Rating(dict):
    """Rating dictionary that also supports numeric comparisons with float/int."""

    def __float__(self) -> float:
        return float(self.get("rating", 0.0))

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, (int, float)):
            return self.get("rating") == other
        return super().__eq__(other)


def _normalize_name(name: str) -> str:
    """Strip academic titles like Dr. / Prof. / Professor."""
    return re.sub(
        r"^(?:Dr\.|Prof\.|Professor)\s+", "", name.strip(), flags=re.IGNORECASE
    ).strip()


def _is_offline_or_ollama() -> bool:
    """Check if gemma is in offline or ollama mode."""
    try:
        from wolfbox import gemma

        mode = gemma.mode()
        if mode == "ollama":
            return True
        st = gemma.status()
        if st.get("active_backend") == "ollama":
            return True
        if mode != "fake" and not st.get("online", False):
            return True
        return False
    except Exception:
        return False


def _load_sample_ratings() -> tuple[dict[str, dict], dict[str, dict]]:
    sample_file = DATA_DIR / "ratings_sample.json"
    if not sample_file.exists():
        return {}, {}
    try:
        with open(sample_file, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if "ratings" in raw and isinstance(raw["ratings"], dict):
            raw_map = raw["ratings"]
        else:
            raw_map = {k: v for k, v in raw.items() if isinstance(v, dict)}

        norm_map = {_normalize_name(k).lower(): v for k, v in raw_map.items()}
        return raw_map, norm_map
    except Exception:
        return {}, {}


def get_ratings(names: list[str], store: Any = None) -> dict[str, Rating | None]:
    """Retrieve ratings for a list of instructor names.

    Order:
      1. Per-student cache in store (rmp_cache.json, 24h TTL)
      2. If RMP_LIVE=1 and gemma not in offline/ollama mode: live GraphQL lookup
         (hard 3s timeout per call, 6s budget for whole batch)
      3. Fallback to ratings_sample.json
      4. Missing -> None (never raise)
    """
    result: dict[str, Rating | None] = {}
    if not names:
        return result

    # 1. Load cache from store
    cache: dict[str, dict] = {}
    if store is not None and hasattr(store, "read_json"):
        try:
            cache = store.read_json(CACHE_FILE, {}) or {}
        except Exception:
            cache = {}

    now = time.time()
    cache_dirty = False

    # 2. Sample ratings
    sample_map, sample_map_norm = _load_sample_ratings()

    # 3. Live config
    live_allowed = (os.environ.get("RMP_LIVE") == "1") and not _is_offline_or_ollama()
    school_id = os.environ.get("RMP_SCHOOL_ID", DEFAULT_SCHOOL_ID)
    batch_start = time.monotonic()

    for name in names:
        if not name or not isinstance(name, str):
            result[name] = None
            continue

        # A. Check cache
        if name in cache:
            entry = cache[name]
            cached_at = entry.get("cached_at", 0)
            if now - cached_at < CACHE_TTL:
                data = dict(entry.get("rating", {}))
                data["source"] = "cache"
                result[name] = Rating(data)
                continue

        # B. Live GraphQL lookup
        live_found = False
        if live_allowed:
            elapsed = time.monotonic() - batch_start
            remaining_budget = BATCH_BUDGET - elapsed
            if remaining_budget > 0:
                call_timeout = min(PER_CALL_TIMEOUT, remaining_budget)
                try:
                    cleaned_name = _normalize_name(name)
                    payload = {
                        "query": RMP_QUERY,
                        "variables": {"t": cleaned_name, "s": school_id},
                    }
                    resp = httpx.post(
                        RMP_GRAPHQL_URL,
                        json=payload,
                        headers=RMP_HEADERS,
                        timeout=call_timeout,
                    )
                    if resp.status_code == 200:
                        body = resp.json()
                        edges = (
                            body.get("data", {})
                            .get("newSearch", {})
                            .get("teachers", {})
                            .get("edges", [])
                        )
                        matched_node = None
                        target_clean = cleaned_name.lower()
                        for edge in edges:
                            node = edge.get("node", {})
                            fn = node.get("firstName", "").strip()
                            ln = node.get("lastName", "").strip()
                            node_full = f"{fn} {ln}".strip().lower()
                            if (
                                node_full == name.lower()
                                or node_full == target_clean
                                or (
                                    ln
                                    and target_clean.endswith(ln.lower())
                                    and (not fn or fn.lower() in target_clean)
                                )
                            ):
                                matched_node = node
                                break

                        if matched_node is not None:
                            legacy_id = matched_node.get("legacyId")
                            url = (
                                f"https://www.ratemyprofessors.com/professor/{legacy_id}"
                                if legacy_id
                                else None
                            )
                            wta = matched_node.get("wouldTakeAgainPercent")
                            wta_val = (
                                float(wta)
                                if (wta is not None and float(wta) >= 0)
                                else None
                            )
                            rating_val = float(matched_node.get("avgRating", 0.0))
                            diff_val = float(matched_node.get("avgDifficulty", 0.0))
                            num_val = int(matched_node.get("numRatings", 0))

                            live_rating = Rating({
                                "rating": rating_val,
                                "difficulty": diff_val,
                                "num_ratings": num_val,
                                "would_take_again": wta_val,
                                "source": "rmp",
                                "url": url,
                            })
                            result[name] = live_rating
                            cache[name] = {"cached_at": now, "rating": dict(live_rating)}
                            cache_dirty = True
                            live_found = True
                except Exception:
                    # Timeout or network error -> fall back to sample
                    pass

        if live_found:
            continue

        # C. Sample fallback
        sample_entry = sample_map.get(name)
        if not sample_entry:
            sample_entry = sample_map_norm.get(_normalize_name(name).lower())

        if sample_entry:
            wta = sample_entry.get("would_take_again")
            result[name] = Rating({
                "rating": float(sample_entry.get("rating", 0.0)),
                "difficulty": float(sample_entry.get("difficulty", 0.0)),
                "num_ratings": int(sample_entry.get("num_ratings", 0)),
                "would_take_again": float(wta) if wta is not None else None,
                "source": "sample",
            })
        else:
            result[name] = None

    # Save cache if updated
    if cache_dirty and store is not None and hasattr(store, "write_json"):
        try:
            store.write_json(CACHE_FILE, cache)
        except Exception:
            pass

    return result
