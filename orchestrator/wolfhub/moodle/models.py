import re
from pathlib import PurePosixPath
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


def identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", value):
        raise ValueError("Expected a course/item identifier")
    return value


def relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or any(p in {"", ".", ".."} for p in value.split("/")) or "\\" in value:
        raise ValueError("Unsafe file path")
    return value


def web_url(value: str) -> str:
    url = urlsplit(value)
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise ValueError("Expected an HTTPS URL without credentials")
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TaskParams(StrictModel):
    course: str
    item: str | None = None
    canvas_course_id: str | None = None

    @field_validator("canvas_course_id")
    @classmethod
    def canvas_id(cls, value):
        if value is not None and not re.fullmatch(r"[0-9]+", value):
            raise ValueError("Expected a numeric Canvas course ID")
        return value

    _ids = field_validator("course", "item")(lambda v: identifier(v) if v is not None else v)


class ManifestFile(StrictModel):
    path: str
    url: str
    role: Literal["starter", "tests"] | None = None
    agent_path: str | None = None

    _path = field_validator("path")(relative_path)

    @field_validator("url")
    @classmethod
    def safe_url(cls, value):
        if value.startswith("/course/"):
            relative_path(value[1:])
            return value
        return web_url(value)


class ManifestItem(StrictModel):
    id: str
    type: Literal["assignment", "doc", "announcement"]
    title: str = Field(min_length=1, max_length=1000)
    version: int = Field(ge=1)
    published_at: str | None = None
    due: str | None = None
    description: str = Field(default="", max_length=200000)
    files: list[ManifestFile] = Field(max_length=100)

    _id = field_validator("id")(identifier)

    @field_validator("due", "published_at")
    @classmethod
    def timestamp(cls, value):
        if value is not None:
            from datetime import datetime
            if datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is None:
                raise ValueError("Timestamp must include a timezone")
        return value


class Manifest(StrictModel):
    course: str
    title: str = Field(min_length=1)
    source: Literal["moodle", "canvas"]
    sample: bool = False
    items: list[ManifestItem] = Field(max_length=500)

    _course = field_validator("course")(identifier)

class AgentResult(StrictModel):
    status: Literal["running", "needs_human", "done", "error"]
    steps: list[str] = Field(max_length=100)
    result: dict | None = None


def validate_result(data, kind, course):
    result = AgentResult.model_validate(data)
    if result.status == "done":
        if kind == "list_assignments":
            manifest = Manifest.model_validate(result.result)
            if manifest.course != course or len({i.id for i in manifest.items}) != len(manifest.items):
                raise ValueError("Manifest course mismatch or duplicate items")
        else:
            if not result.result or set(result.result) != {"moodle_url"}:
                raise ValueError("Result must contain only moodle_url")
            web_url(result.result["moodle_url"])
    return result
