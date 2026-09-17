from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from pydantic import BaseModel, Field

from app.config import Settings
from app.jobs import arun_hydrate, arun_morning_brief, acatch_up_jobs
from app.media_paths import MediaPathError, safe_media_file
from app.runtime import AppRuntime, build_runtime
from app.serialize import serialize_thread


class MessageIn(BaseModel):
    content: str = Field(min_length=1)


class ResumeIn(BaseModel):
    action: str
    prompt: str | None = None
    params: dict[str, Any] | None = None


class ThreadCreated(BaseModel):
    id: str


class JobRunIn(BaseModel):
    kind: str
    slot: str | None = None
    force: bool = False


def create_app(runtime: AppRuntime | None = None) -> FastAPI:
    runtime = runtime or build_runtime()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        scheduler = None
        if runtime.settings.scheduler_enabled:
            from app.scheduler import start_scheduler

            scheduler = start_scheduler(runtime)
            await acatch_up_jobs(runtime)
        try:
            yield
        finally:
            if scheduler is not None:
                scheduler.shutdown(wait=False)

    app = FastAPI(title="个人超级助理", lifespan=lifespan)
    app.state.runtime = runtime
    app.state.threads = set()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime.settings.cors_origin_list(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def _require_thread(thread_id: str) -> None:
        known = app.state.threads
        if thread_id in known:
            return
        snapshot = runtime.graph.get_state({"configurable": {"thread_id": thread_id}})
        if not snapshot.values and not snapshot.next:
            raise HTTPException(status_code=404, detail="thread not found")
        known.add(thread_id)

    async def _arun(thread_id: str, payload) -> dict[str, Any]:
        config = {"configurable": {"thread_id": thread_id}}
        await runtime.graph.ainvoke(payload, config)
        return serialize_thread(runtime, thread_id)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/config")
    def get_config() -> dict[str, Any]:
        return runtime.settings.public_config()

    @app.post("/v1/threads", response_model=ThreadCreated)
    def create_thread() -> ThreadCreated:
        thread_id = str(uuid.uuid4())
        app.state.threads.add(thread_id)
        return ThreadCreated(id=thread_id)

    @app.get("/v1/threads/{thread_id}")
    def get_thread(thread_id: str) -> dict[str, Any]:
        _require_thread(thread_id)
        return serialize_thread(runtime, thread_id)

    @app.post("/v1/threads/{thread_id}/messages")
    async def post_message(thread_id: str, body: MessageIn) -> dict[str, Any]:
        _require_thread(thread_id)
        current = serialize_thread(runtime, thread_id)
        if current.get("status") == "interrupted":
            raise HTTPException(status_code=409, detail="thread is waiting for review")
        return await _arun(thread_id, {"messages": [HumanMessage(content=body.content)]})

    @app.post("/v1/threads/{thread_id}/resume")
    async def resume_thread(thread_id: str, body: ResumeIn) -> dict[str, Any]:
        _require_thread(thread_id)
        current = serialize_thread(runtime, thread_id)
        if current.get("status") != "interrupted":
            raise HTTPException(status_code=409, detail="thread is not waiting for review")
        decision = {
            "action": body.action,
            "prompt": body.prompt,
            "params": body.params or {},
        }
        return await _arun(thread_id, Command(resume=decision))

    @app.post("/v1/assistant/jobs/run")
    async def run_job(body: JobRunIn) -> dict[str, Any]:
        kind = (body.kind or "").strip()
        if kind == "morning_brief":
            return await arun_morning_brief(runtime, force=body.force)
        if kind == "hydrate":
            if not body.slot:
                raise HTTPException(status_code=400, detail="slot is required for hydrate")
            try:
                return await arun_hydrate(runtime, body.slot, force=body.force)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail="kind must be morning_brief or hydrate")

    @app.get("/v1/media/{kind}/{file_name}")
    def get_media(kind: str, file_name: str):
        try:
            path = safe_media_file(runtime.media_root, kind, file_name)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="media not found") from None
        except MediaPathError:
            raise HTTPException(status_code=400, detail="invalid media path") from None
        media_type = "image/png" if kind == "images" else "video/mp4"
        return FileResponse(path, media_type=media_type)

    return app


def app_from_env() -> FastAPI:
    try:
        settings = Settings()
    except Exception as exc:
        raise RuntimeError(f"invalid settings: {exc}") from exc
    try:
        runtime = build_runtime(settings)
    except MediaPathError as exc:
        raise RuntimeError(str(exc)) from exc
    return create_app(runtime)