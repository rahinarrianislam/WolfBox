"""FastAPI APIRouter for Moodle delegation via OpenClaw / Maritime."""
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from wolfhub.moodle.models import identifier


def instructor_only(request: Request):
    """Fails closed (503) if auth is missing/unconfigured, else verifies instructor role."""
    auth = sys.modules.get("wolfhub.auth")
    if auth is None:
        try:
            import wolfhub.auth as auth
        except ImportError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Instructor authentication unavailable",
            )
    if hasattr(auth, "require_instructor"):
        return auth.require_instructor(request)
    if hasattr(auth, "require_role"):
        dep = auth.require_role("instructor")
        try:
            return dep(request)
        except TypeError:
            return dep()
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Instructor authentication unavailable",
    )


def instructor_dependency():
    """Factory returning a FastAPI dependency callable."""
    auth = sys.modules.get("wolfhub.auth")
    if auth is None:
        try:
            import wolfhub.auth as auth
        except ImportError:
            pass
    if auth is not None:
        if hasattr(auth, "require_role"):
            return auth.require_role("instructor")
        if hasattr(auth, "require_instructor"):
            return auth.require_instructor

    def fail_closed(request: Request):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Instructor authentication unavailable",
        )

    return fail_closed


router = APIRouter(dependencies=[Depends(instructor_only)])


def get_delegate(request: Request):
    delegate = getattr(request.app.state, "moodle_delegate", None)
    if delegate is None:
        from wolfhub.moodle.agent import MoodleDelegate

        site_dir = Path(__file__).resolve().parents[1] / "course_site"
        delegate = MoodleDelegate(site_dir=site_dir)
        request.app.state.moodle_delegate = delegate
    return delegate


class DelegateMoodleRequest(BaseModel):
    course: str
    item: Optional[str] = None


@router.post("/api/delegate/moodle/{kind}", status_code=status.HTTP_202_ACCEPTED)
def delegate_moodle(kind: str, body: DelegateMoodleRequest, request: Request):
    allowed_kinds = {"list_assignments", "publish_assignment", "open_course"}
    if kind not in allowed_kinds:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown delegation task kind '{kind}'",
        )
    delegate = get_delegate(request)
    try:
        task_id = delegate.start_task(kind, body.model_dump())
        return {"task_id": task_id}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/api/delegate/tasks/{task_id}")
def get_task(task_id: str, request: Request):
    delegate = get_delegate(request)
    task = delegate.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.get("/api/delegate/tasks")
def list_tasks(request: Request):
    delegate = get_delegate(request)
    return delegate.list_tasks()
