"""WS2 backend and output contracts, without external inference services."""

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wolfbox import gemma


@pytest.fixture(autouse=True)
def fake_env(monkeypatch):
    monkeypatch.delenv("GEMMA_FAKE", raising=False)
    monkeypatch.setenv("GEMMA_BACKEND", "fake")
    if hasattr(gemma, "_reset_state"):
        gemma._reset_state()


@pytest.fixture
def ollama_server(monkeypatch):
    requests = []
    replies = [(200, {"message": {"content": "A local reply?"}})]

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append(
                json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            )
            status, body = replies.pop(0) if len(replies) > 1 else replies[0]
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("OLLAMA_URL", f"http://127.0.0.1:{server.server_port}")
    try:
        yield requests, replies
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def test_fake_classifies_failures_and_reads_env_at_call_time(monkeypatch):
    assert gemma.classify("", [{"test": "test_last_index", "message": ""}]) == [
        "off_by_one"
    ]
    assert gemma.classify("", [{"test": "test_empty", "message": "None"}]) == [
        "empty_input",
        "none_handling",
    ]
    assert gemma.classify("", []) == []
    monkeypatch.setenv("GEMMA_BACKEND", "ollama")
    monkeypatch.setenv("GEMMA_FAKE", "1")
    assert gemma.mode() == "fake"
    assert gemma._generate("unknown", "", json_mode=True) == ("{}", "fake", "fake")


def test_fake_tasks_and_manifest_deadline_precedence():
    due = "2026-11-06T23:59:00-05:00"
    assert gemma.summarize_doc("Syllabus", "Read before class.\nBring questions.")
    assert len(gemma.summarize_doc("Syllabus", "Read before class.").splitlines()) <= 3
    assert gemma.extract_deadlines("HW4", "Due tomorrow", due)[0]["due"] == due
    assert gemma.extract_deadlines("Notes", "No due date", None) == []
    assert gemma.change_note("HW4", "old rule", "new rule")
    assert len(gemma.nudge_draft("five failures", {"assignment": "hw4"}).split()) <= 60
    assert gemma.answer("Why?", "", {}, {}).endswith("?")
    summary = gemma.ta_summary({}, [], "")
    for heading in (
        "Where they are",
        "What they tried",
        "Patterns",
        "Suggested opener",
    ):
        assert heading in summary
    assert len(summary.split()) <= 200


def test_auto_falls_back_and_opens_circuit(monkeypatch, ollama_server):
    monkeypatch.setenv("GEMMA_BACKEND", "auto")
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")
    attempts = []

    def unreachable(*args):
        attempts.append(True)
        raise httpx.ConnectError("unreachable")

    monkeypatch.setattr(gemma, "_gemini", unreachable, raising=False)
    assert gemma._generate("system", "same prompt")[1] == "ollama"
    assert gemma._generate("system", "same prompt")[1] == "ollama"
    assert len(attempts) == 1
    assert gemma.status()["active_backend"] == "ollama"
    assert gemma.status()["online"] is False
    assert gemma.last_llm()["backend"] == "ollama"
    payload = ollama_server[0][0]
    assert payload["messages"] == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "same prompt"},
    ]
    assert payload["keep_alive"] == "30m"
    assert payload["think"] is False
    assert payload["stream"] is False


def test_auto_does_not_fall_back_on_4xx(monkeypatch, ollama_server):
    monkeypatch.setenv("GEMMA_BACKEND", "auto")
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")

    def bad_key(*args):
        response = httpx.Response(
            401, request=httpx.Request("POST", "https://example.test")
        )
        raise httpx.HTTPStatusError(
            "bad key", request=response.request, response=response
        )

    monkeypatch.setattr(gemma, "_gemini", bad_key, raising=False)
    with pytest.raises(httpx.HTTPStatusError):
        gemma._generate("system", "user")
    assert ollama_server[0] == []
    assert gemma.status()["active_backend"] == "gemini"


def test_ollama_retries_rejected_think_flag(monkeypatch, ollama_server):
    monkeypatch.setenv("GEMMA_BACKEND", "ollama")
    requests, replies = ollama_server
    replies[:] = [
        (400, {"error": "think is unsupported"}),
        (200, {"message": {"content": '{"tags":["off_by_one"]}'}}),
    ]
    assert gemma.classify("", [{"test": "last"}]) == ["off_by_one"]
    assert requests[0]["format"] == "json"
    assert "think" not in requests[1]


@pytest.mark.parametrize("task", ["hint", "answer"])
def test_socratic_postcheck_rejects_long_code_and_retries(monkeypatch, task):
    calls = []

    def unsafe(*args, **kwargs):
        calls.append(True)
        return "```python\na=1\nb=2\nc=3\nd=4\n```\nWhat next?", "fake", "fake"

    monkeypatch.setattr(gemma, "_generate", unsafe)
    with pytest.raises(ValueError):
        if task == "hint":
            gemma.hint("", [], [], {})
        else:
            gemma.answer("solve", "", {}, {})
    assert len(calls) == 2


def test_socratic_output_caps_words_and_requires_question(monkeypatch):
    monkeypatch.setattr(
        gemma, "_generate", lambda *a, **k: ("word " * 100 + "Why?", "fake", "fake")
    )
    result = gemma.hint("", [], [], {})
    assert len(result.split()) <= 80
    assert result.endswith("?")
    monkeypatch.setattr(
        gemma, "_generate", lambda *a, **k: ("Here is the answer.", "fake", "fake")
    )
    with pytest.raises(ValueError):
        gemma.hint("", [], [], {})


def test_overall_timeout_does_not_wait_for_stuck_backend(monkeypatch):
    monkeypatch.setenv("GEMMA_BACKEND", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")
    release = threading.Event()
    monkeypatch.setattr(
        gemma, "_gemini", lambda *a: (release.wait(2), "late")[1], raising=False
    )
    start = time.monotonic()
    try:
        with pytest.raises(TimeoutError):
            gemma._generate("s", "u", timeout=0.05)
        assert time.monotonic() - start < 0.5
    finally:
        release.set()


def test_history_in_prompt_is_capped(monkeypatch):
    seen = []
    monkeypatch.setattr(
        gemma,
        "_generate",
        lambda system, user, **k: (
            seen.append(json.loads(user)) or "Like hw4, what happens?",
            "fake",
            "fake",
        ),
    )
    profile = {
        "mistake_counts": {
            "other": 1,
            "empty_input": 4,
            "off_by_one": 8,
            "none_handling": 2,
        },
        "examples": {
            tag: [{"assignment": f"hw{i}", "note": "note"} for i in range(5)]
            for tag in ["other", "empty_input", "off_by_one", "none_handling"]
        },
    }
    gemma.hint("", [], ["off_by_one"], profile)
    history = seen[0]["history"]
    assert set(history["mistake_counts"]) == {
        "off_by_one",
        "empty_input",
        "none_handling",
    }
    assert all(len(examples) <= 2 for examples in history["examples"].values())


def test_auto_missing_key_and_5xx_fall_back_then_recover(monkeypatch, ollama_server):
    monkeypatch.setenv("GEMMA_BACKEND", "auto")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert gemma._generate("s", "u")[1] == "ollama"
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")
    assert gemma.status()["online"] is False
    gemma._reset_state()
    response = httpx.Response(
        503, request=httpx.Request("POST", "https://example.test")
    )

    def server_error(*args):
        raise httpx.HTTPStatusError(
            "service down", request=response.request, response=response
        )

    monkeypatch.setattr(gemma, "_gemini", server_error)
    assert gemma._generate("s", "u")[1] == "ollama"
    assert gemma._circuit_until > time.monotonic()
    monkeypatch.setattr(gemma, "_circuit_until", time.monotonic() - 1)
    monkeypatch.setattr(gemma, "_gemini", lambda *a: "Cloud reply?")
    assert gemma._generate("s", "u")[1] == "gemini"
    assert gemma.status()["online"] is True


def test_gemini_sdk_thinking_retry_and_transport_timeouts(monkeypatch):
    from google import genai

    original_client = genai.Client
    requests = []

    def transport(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                400,
                json={
                    "error": {
                        "code": 400,
                        "message": "thinking_config unsupported",
                        "status": "INVALID_ARGUMENT",
                    }
                },
            )
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [{"text": "Try the boundary?"}],
                        },
                        "finishReason": "STOP",
                    }
                ]
            },
        )

    def client(**kwargs):
        kwargs["http_options"].client_args["transport"] = httpx.MockTransport(transport)
        return original_client(**kwargs)

    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")
    monkeypatch.setattr(genai, "Client", client)
    assert (
        gemma._gemini("Socratic tutor", "test input", False, 20) == "Try the boundary?"
    )
    assert requests[0].extensions["timeout"]["connect"] <= 3
    assert requests[0].extensions["timeout"]["read"] == 20
    first = json.loads(requests[0].content)
    second = json.loads(requests[1].content)
    thinking = first["generationConfig"]["thinkingConfig"]
    assert thinking.get("thinkingBudget", thinking.get("thinking_budget")) == 0
    assert "thinkingConfig" not in second["generationConfig"]


@pytest.mark.parametrize(
    "task,reply",
    [
        ("classify", '{"tags":"off_by_one"}'),
        ("classify", '{"tags":[1]}'),
        ("extract_deadlines", '{"deadlines":[{"what":"HW4","due":"tomorrow"}]}'),
        (
            "extract_deadlines",
            '{"deadlines":[{"what":"HW4","due":"2026-11-06T12:00:00Z","source_doc":8}]}',
        ),
        ("summarize_doc", "one\ntwo\nthree\nfour"),
        ("ta_summary", "No required sections"),
        ("nudge_draft", ""),
        ("change_note", ""),
    ],
)
def test_tasks_reject_malformed_outputs(monkeypatch, task, reply):
    monkeypatch.setattr(gemma, "_generate", lambda *a, **k: (reply, "fake", "fake"))
    args = {
        "classify": ("", []),
        "extract_deadlines": ("HW4", "", None),
        "summarize_doc": ("Title", "Text"),
        "ta_summary": ({}, [], ""),
        "nudge_draft": ("reason", {}),
        "change_note": ("Title", "old", "new"),
    }
    with pytest.raises(ValueError):
        getattr(gemma, task)(*args[task])


def test_invalid_hint_can_retry_to_valid_reply(monkeypatch):
    outputs = iter(["Here is the solution.", "Which boundary fails?"])
    monkeypatch.setattr(
        gemma, "_generate", lambda *a, **k: (next(outputs), "fake", "fake")
    )
    assert gemma.hint("", [], [], {}) == "Which boundary fails?"


def test_document_inputs_and_diff_are_bounded(monkeypatch):
    seen = []

    def generate(system, user, **kwargs):
        seen.append(json.loads(user))
        return "A short summary.", "fake", "fake"

    monkeypatch.setattr(gemma, "_generate", generate)
    gemma.summarize_doc("Title", "x" * 10000)
    assert len(seen[-1]["text"]) <= 6000
    gemma.change_note("Title", "first\nold", "first\nnew")
    assert "-old" in seen[-1]["diff"] and "+new" in seen[-1]["diff"]
    assert len(seen[-1]["diff"]) <= 6000


def test_hint_retries_then_rejects_missing_matching_citation(monkeypatch):
    profile = {
        "mistake_counts": {"off_by_one": 4},
        "examples": {"off_by_one": [{"assignment": "hw2", "note": "loop bound"}]},
    }
    monkeypatch.setattr(
        gemma, "_generate", lambda *a, **k: ("Which index fails?", "fake", "fake")
    )
    with pytest.raises(ValueError):
        gemma.hint("", [], ["off_by_one"], profile)


def test_socratic_truncation_preserves_final_question(monkeypatch):
    reply = "A detail. " * 50 + "What happens on the final index?"
    monkeypatch.setattr(gemma, "_generate", lambda *a, **k: (reply, "fake", "fake"))
    result = gemma.hint("", [], [], {})
    assert result.endswith("What happens on the final index?")
    assert len(result.split()) <= 80


def test_warmup_is_nonblocking_and_swallows_errors(monkeypatch):
    monkeypatch.setenv("GEMMA_BACKEND", "auto")
    entered = threading.Event()
    release = threading.Event()

    def unavailable(*args):
        entered.set()
        release.wait(1)
        raise ConnectionError("offline")

    monkeypatch.setattr(gemma, "_ollama", unavailable)
    start = time.monotonic()
    try:
        gemma.warmup()
        assert time.monotonic() - start < 0.5
        assert entered.wait(0.5)
    finally:
        release.set()


def test_ollama_retries_plain_text_think_error(monkeypatch):
    monkeypatch.setenv("GEMMA_BACKEND", "ollama")
    replies = iter(
        [
            httpx.Response(
                400,
                text="think unsupported",
                request=httpx.Request("POST", "http://localhost/api/chat"),
            ),
            httpx.Response(
                200,
                json={"message": {"content": "A local hint?"}},
                request=httpx.Request("POST", "http://localhost/api/chat"),
            ),
        ]
    )
    monkeypatch.setattr(httpx, "post", lambda *a, **k: next(replies))
    assert gemma._generate("s", "u")[0] == "A local hint?"
