"""WolfBox's Maritime-compatible HTTP entry point."""

import json
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from wolfbox import gemma, protocol, router
from wolfbox.store import Store


class ChatRequest(BaseModel):
    message: str
    source: str


def _warmup():
    try:
        if hasattr(gemma, "warmup"):
            gemma.warmup()
    except Exception:
        pass


def create_app():
    @asynccontextmanager
    async def lifespan(app):
        app.state.store = Store(os.environ.get("DATA_DIR", "/data"))
        router.ensure_template(app.state.store)
        threading.Thread(target=_warmup, daemon=True).start()
        yield

    app = FastAPI(lifespan=lifespan)

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/chat")
    def chat(body: ChatRequest):
        try:
            response = router.dispatch(app.state.store, protocol.parse(body.message))
        except Exception as exc:
            response = protocol.error(str(exc))
        return {"response": json.dumps(response)}

    @app.get("/schedules")
    def schedules():
        return [
            {"id": "sync", "cron": "*/15 * * * *", "prompt": '{"v":1,"type":"sync"}'},
            {
                "id": "catalog",
                "cron": "0 */6 * * *",
                "prompt": '{"v":1,"type":"plan_refresh"}',
            },
        ]

    return app


app = create_app()
