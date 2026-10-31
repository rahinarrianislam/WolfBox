import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from wolfhub.aggregate import heatmap
from wolfhub.boxes import BoxError, BoxUnavailable, get_client
from wolfhub.registry import Registry


ROOT = Path(__file__).resolve().parents[1]


class StudentRequest(BaseModel):
    id: str
    name: str


class SubmitRequest(BaseModel):
    code: str
    assignment: str | None = None


class AskRequest(BaseModel):
    text: str


class PrefsRequest(BaseModel):
    text: str


class SolveRequest(BaseModel):
    full_sections: list[str] | None = None


def create_app(box_client=None, registry=None) -> FastAPI:
    app = FastAPI()
    app.state.box_client = box_client or get_client()
    app.state.registry = registry or Registry()

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return JSONResponse(status_code=exc.status_code, content={"error": message})

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def student(student_id: str) -> dict:
        record = app.state.registry.get(student_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Unknown student")
        return record

    def call(student_id: str, kind: str, payload: dict | None = None) -> dict:
        record = student(student_id)
        if not record.get("box_id"):
            raise HTTPException(status_code=503, detail="Student box is not provisioned")
        envelope = {"v": 1, "type": kind, **(payload or {})}
        try:
            result = app.state.box_client.call(record["box_id"], envelope)
        except BoxError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except BoxUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Box unavailable: {exc}") from exc
        if result.get("ok") is False:
            raise HTTPException(status_code=502, detail=str(result.get("error", "Box request failed")))
        return {key: value for key, value in result.items() if key != "ok"}

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/students")
    def list_students():
        return app.state.registry.list()

    @app.post("/api/students")
    def create_student(body: StudentRequest):
        backend = os.getenv("BOX_BACKEND", "local").lower()
        try:
            box_id = app.state.box_client.ensure(body.id, body.name)
            app.state.registry.set(body.id, body.name, box_id, backend)
            result = app.state.box_client.call(
                box_id,
                {"v": 1, "type": "init", "student_id": body.id, "name": body.name},
            )
            if result.get("ok") is False:
                raise BoxError(str(result.get("error", "Box request failed")))
        except BoxError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except BoxUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Box unavailable: {exc}") from exc
        return {"id": body.id, "name": body.name, "box_id": box_id, "backend": backend}

    @app.get("/api/students/{student_id}/state")
    def get_state(student_id: str, assignment: str | None = None):
        payload = {"assignment": assignment} if assignment else {}
        return call(student_id, "get_state", payload)

    @app.post("/api/students/{student_id}/submit")
    def submit(student_id: str, body: SubmitRequest, assignment: str | None = Query(default=None)):
        assignment = assignment or body.assignment or "hw4"
        return call(student_id, "submit_code", {"files": {f"{assignment}.py": body.code}, "assignment": assignment})

    @app.get("/api/students/{student_id}/runs/{run_id}")
    def get_run(student_id: str, run_id: str, assignment: str | None = None):
        payload = {"run_id": run_id}
        if assignment:
            payload["assignment"] = assignment
        return call(student_id, "get_run", payload)

    @app.get("/api/students/{student_id}/runs")
    def list_runs(student_id: str, assignment: str | None = None):
        payload = {"assignment": assignment} if assignment else {}
        return call(student_id, "list_runs", payload)

    @app.post("/api/students/{student_id}/ask")
    def ask(student_id: str, body: AskRequest):
        return call(student_id, "ask", {"text": body.text})

    @app.get("/api/students/{student_id}/ta-summary")
    def ta_summary(student_id: str, assignment: str | None = None):
        payload = {"assignment": assignment} if assignment else {}
        return call(student_id, "ta_summary", payload)

    @app.get("/api/students/{student_id}/plan")
    def plan_get(student_id: str):
        return call(student_id, "plan_get")

    @app.post("/api/students/{student_id}/plan/prefs")
    def plan_set_prefs(student_id: str, body: PrefsRequest):
        return call(student_id, "plan_set_prefs", {"text": body.text})

    @app.post("/api/students/{student_id}/plan/solve")
    def plan_solve(student_id: str, body: SolveRequest):
        payload = {"full_sections": body.full_sections} if body.full_sections is not None else {}
        return call(student_id, "plan_solve", payload)

    @app.post("/api/students/{student_id}/sync")
    def sync(student_id: str):
        return call(student_id, "sync")

    @app.get("/api/students/{student_id}/sync/{job_id}")
    def get_sync(student_id: str, job_id: str):
        return call(student_id, "get_sync", {"job_id": job_id})

    @app.get("/api/students/{student_id}/docs")
    def list_docs(student_id: str, course: str | None = None):
        payload = {"course": course} if course else {}
        return call(student_id, "list_docs", payload)

    @app.get("/api/students/{student_id}/docs/{doc_id:path}")
    def get_doc(student_id: str, doc_id: str):
        return call(student_id, "get_doc", {"doc_id": doc_id})

    @app.get("/api/students/{student_id}/deadlines")
    def deadlines(student_id: str):
        return call(student_id, "deadlines")

    @app.get("/api/students/{student_id}/assignments")
    def list_assignments(student_id: str):
        return call(student_id, "list_assignments")

    @app.get("/api/instructor/heatmap")
    def instructor_heatmap():
        return heatmap(app.state.registry.list(), app.state.box_client)

    try:
        from wolfhub.course import router as course_router

        app.include_router(course_router)
    except ImportError:
        pass

    try:
        from wolfhub.delegate import router as delegate_router

        app.include_router(delegate_router)
    except ImportError:
        pass

    course_dir = ROOT / "course_site"
    static_dir = ROOT / "static"
    course_dir.mkdir(parents=True, exist_ok=True)
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/course", StaticFiles(directory=course_dir), name="course")
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    return app


app = create_app()
