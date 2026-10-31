import json
import os
from typing import Protocol

import httpx


class BoxError(Exception):
    """The box received a request but returned an application-level error."""


class BoxUnavailable(Exception):
    """The box could not be reached or returned an invalid transport response."""


class BoxClient(Protocol):
    def ensure(self, student_id: str, name: str) -> str: ...

    def call(self, box_id: str, envelope: dict) -> dict: ...


def parse_local_boxes(value: str | None = None) -> dict[str, str]:
    value = os.getenv("LOCAL_BOXES", "") if value is None else value
    boxes = {}
    for entry in value.split(","):
        if not entry.strip():
            continue
        student_id, sep, url = entry.partition("=")
        if not sep or not student_id.strip() or not url.strip():
            raise ValueError(f"Invalid LOCAL_BOXES entry: {entry!r}")
        boxes[student_id.strip()] = url.strip().rstrip("/")
    return boxes


class LocalBoxClient:
    def __init__(self, boxes: dict[str, str] | None = None):
        self.boxes = parse_local_boxes() if boxes is None else boxes

    def ensure(self, student_id: str, name: str) -> str:
        try:
            return self.boxes[student_id]
        except KeyError as exc:
            raise BoxUnavailable(f"No local box configured for {student_id}") from exc

    def call(self, box_id: str, envelope: dict) -> dict:
        try:
            response = httpx.post(
                f"{box_id.rstrip('/')}/chat",
                json={"message": json.dumps(envelope), "source": "cli"},
                timeout=30.0,
            )
            response.raise_for_status()
            result = response.json()
            inner = json.loads(result["response"])
            if not isinstance(inner, dict):
                raise ValueError("box response must be a JSON object")
        except httpx.HTTPStatusError as exc:
            raise BoxUnavailable(f"Box returned HTTP {exc.response.status_code}") from exc
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
            raise BoxUnavailable(f"Could not communicate with box: {exc}") from exc
        if inner.get("ok") is False:
            raise BoxError(str(inner.get("error", "Box request failed")))
        return inner


class MaritimeBoxClient:
    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from maritime import Maritime

            self._client = Maritime(timeout=30.0, max_retries=0)
        return self._client

    def ensure(self, student_id: str, name: str) -> str:
        # needs WS0 verification: custom-image provisioning via the Python SDK.
        agent = self.client.agents.provision(
            external_id=f"wolfbox-{student_id}",
            name=f"wolfbox-{student_id}",
            template=os.getenv("MARITIME_TEMPLATE", "custom"),
        )
        box_id = agent["id"]
        values = {
            "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY"),
            "ALLOW_SEED": "1",
            "GEMMA_MODEL": os.getenv("GEMMA_MODEL", "gemma-4-26b-a4b-it"),
            "COURSE_URL": os.getenv("COURSE_URL", ""),
        }
        for key, value in values.items():
            if value:
                # needs WS0 verification: set_env/reload_env support for custom agents.
                self.client.agents.set_env(box_id, key, value, secret=key == "GEMINI_API_KEY")
        self.client.agents.reload_env(box_id)
        return box_id

    def call(self, box_id: str, envelope: dict) -> dict:
        try:
            reply = self.client.agents.chat(box_id, json.dumps(envelope))
            inner = json.loads(reply["response"])
            if not isinstance(inner, dict):
                raise ValueError("box response must be a JSON object")
        except (KeyError, ValueError, TypeError) as exc:
            raise BoxUnavailable(f"Invalid Maritime box response: {exc}") from exc
        except Exception as exc:
            raise BoxUnavailable(f"Could not communicate with Maritime box: {exc}") from exc
        if inner.get("ok") is False:
            raise BoxError(str(inner.get("error", "Box request failed")))
        return inner


def get_client() -> BoxClient:
    backend = os.getenv("BOX_BACKEND", "local").lower()
    if backend == "local":
        return LocalBoxClient()
    if backend == "maritime":
        return MaritimeBoxClient()
    raise ValueError(f"Unsupported BOX_BACKEND: {backend}")
