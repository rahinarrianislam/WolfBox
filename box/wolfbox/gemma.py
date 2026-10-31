"""INTERFACE STUB committed by the orchestrator. WS2 replaces this file with the real implementation
(gemini / ollama / auto / fake backends, IMPLEMENTATION.md §6) but MUST keep these names and signatures:

    TAGS: list[str]
    mode() -> str                                     # "auto"|"gemini"|"ollama"|"fake" (GEMMA_FAKE=1 => "fake")
    status() -> dict                                  # LlmStatus {mode, active_backend, model, online}
    _generate(system, user, json_mode=False, timeout=20.0) -> tuple[str, str, str]   # (text, backend, model); raises on failure
    last_llm() -> dict                                # {"backend","model"} of the most recent successful call
    classify(code, failures) -> list[str]
    hint(code, failures, tags, history) -> str
    answer(question, code, last_run, history) -> str
    ta_summary(profile, recent_runs, code) -> str
    nudge_draft(reason, last_run) -> str
    summarize_doc(title, text) -> str
    extract_deadlines(title, text, manifest_due) -> list[dict]
    change_note(title, old_text, new_text) -> str

Every task fn returns validated output or raises; callers catch and use a canned fallback.
In fake mode, _generate returns "" for unknown prompts (and "{}" when json_mode) - callers needing structured
output in fake mode (planner prefs) must have their own deterministic fallback.
"""

from __future__ import annotations

import os

TAGS = ["off_by_one", "empty_input", "none_handling", "mutation_aliasing", "wrong_return", "type_confusion", "infinite_loop", "other"]


def mode() -> str:
    if os.environ.get("GEMMA_FAKE") == "1":
        return "fake"
    return os.environ.get("GEMMA_BACKEND", "auto")


def status() -> dict:
    return {"mode": mode(), "active_backend": "fake", "model": "fake", "online": False}


def last_llm() -> dict:
    return {"backend": "fake", "model": "fake"}


def _generate(system: str, user: str, json_mode: bool = False, timeout: float = 20.0) -> tuple[str, str, str]:
    return ("{}" if json_mode else ""), "fake", "fake"


def classify(code, failures):
    return ["other"] if failures else []


def hint(code, failures, tags, history):
    return "Look closely at the failing test's input. What does your code do at the boundary?"


def answer(question, code, last_run, history):
    return "What does the failing test expect, and what does your code return for that input?"


def ta_summary(profile, recent_runs, code):
    return "**Where they are:** (stub)"


def nudge_draft(reason, last_run):
    return f"Hi! I'm stuck: {reason}. Could we go over it in office hours?"


def summarize_doc(title, text):
    return f"{title}: (summary stub)"


def extract_deadlines(title, text, manifest_due):
    return [{"what": f"{title} due", "due": manifest_due}] if manifest_due else []


def change_note(title, old_text, new_text):
    return f"{title} was updated."
