from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sse_starlette.sse import EventSourceResponse
from langchain_core.messages import HumanMessage
from app.message_metadata import new_message_metadata
from langgraph.types import Command
from pydantic import BaseModel, Field

from app.auth import (
    SESSION_DAYS,
    hash_password,
    hash_token,
    new_session_token,
    validate_password,
    verify_password,
    InvalidPasswordError,
)
from app.avatars import AvatarError, avatar_root, resolve_avatar_file, save_avatar
from app.config import Settings
from app.chat_sse import stream_chat_events
from app.graph import build_invoke_config
from app.knowledge import selected_document_filenames
from app.job_control import JobAccessDenied, cancel_job_run, disable_job, parse_job_uuid
from app.jobs import arun_hydrate, arun_morning_brief, acatch_up_jobs
from app.media_paths import MediaPathError, safe_media_file
from app.plaza import (
    create_agent_instance_for_user,
    ensure_official_thread,
    instance_card,
    require_owned_instance,
    sidebar_payload,
)
from app.repository import (
    CUSTOM_TEMPLATE,
    DOUYIN_OPS_TEMPLATE,
    DuplicateLoginError,
    DuplicateTitleError,
    InvalidTitleError,
    JobRunNotCancellableError,
    NotFoundError,
    RepositoryError,
    UNSET,
    UnsupportedTemplateError,
    UserRecord,
    utcnow,
)
from app.runtime import AppRuntime, build_runtime
from app.serialize import serialize_thread
from app.skill_runtime import build_skill_runtime_context
from app.approvals import APPROVAL_KINDS, APPROVAL_SCOPES, ApprovalScopeError
from app.agent_config_routes import register_agent_config_routes
from app.skill_routes import register_skill_routes
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo


class MessageIn(BaseModel):
    content: str = Field(min_length=1)
    client_message_id: str | None = None


class ResumeIn(BaseModel):
    action: str
    prompt: str | None = None
    params: dict[str, Any] | None = None


class JobRunIn(BaseModel):
    kind: str
    slot: str | None = None
    force: bool = False


class RegisterIn(BaseModel):
    login_name: str
    password: str


class LoginIn(BaseModel):
    login_name: str
    password: str


class AgentInstanceIn(BaseModel):
    template_code: str
    title: str
    intro: str = ""
    avatar: str | None = None


class AgentInstancePatchIn(BaseModel):
    title: str | None = None
    intro: str | None = None
    avatar: str | None = None


class ApprovalRequestIn(BaseModel):
    thread_id: str = Field(min_length=1)
    config_version_id: str = Field(min_length=1)
    approval_kind: str
    resource_code: str = Field(min_length=1, max_length=200)
    approval_scope: str = "once"


class ApprovalDecisionIn(BaseModel):
    approved: bool
    reason: str = Field(default="", max_length=500)


def _serialize_approval(record) -> dict[str, Any]:
    data = dict(record.__dict__)
    for key in ("approval_id", "user_id", "agent_instance_id", "config_version_id", "decided_by"):
        if data.get(key) is not None:
            data[key] = str(data[key])
    for key in ("requested_at", "decided_at", "expires_at", "consumed_at"):
        if data.get(key) is not None:
            data[key] = data[key].isoformat()
    return data


bearer_scheme = HTTPBearer(auto_error=False)


def _http_error(status_code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=detail)


def create_app(runtime: AppRuntime | None = None) -> FastAPI:
    runtime = runtime or build_runtime()
    repo = runtime.business_repo

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

    app = FastAPI(title="运营助手", lifespan=lifespan)
    app.state.runtime = runtime
    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime.settings.cors_origin_list(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def _auth_user(
        request: Request,
        creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    ) -> UserRecord:
        if creds is None or (creds.scheme or "").lower() != "bearer" or not creds.credentials:
            raise _http_error(401, "not authenticated")
        session = repo.get_session_by_token_hash(hash_token(creds.credentials))
        if session is None or session.expires_at <= utcnow():
            raise _http_error(401, "not authenticated")
        user = repo.get_user(session.user_id)
        if user is None:
            raise _http_error(401, "not authenticated")
        if user.status == "disabled":
            raise _http_error(403, "user is disabled")
        request.state.session = session
        request.state.user = user
        return user

    def _parse_instance_id(raw: str) -> UUID:
        try:
            return UUID(str(raw))
        except ValueError as exc:
            raise _http_error(404, "agent instance not found") from exc

    def _owned_instance(user: UserRecord, agent_instance_id: str):
        try:
            return require_owned_instance(repo, user.user_id, _parse_instance_id(agent_instance_id))
        except NotFoundError as exc:
            raise _http_error(404, "agent instance not found") from exc

    def _owned_thread(user: UserRecord, thread_id: str):
        record = repo.get_app_thread(thread_id)
        if record is None or record.user_id != user.user_id:
            raise _http_error(404, "thread not found")
        return record

    async def _arun(thread_id: str, payload) -> EventSourceResponse:
        thread = repo.get_app_thread(thread_id)
        if thread is None:
            raise _http_error(404, "thread not found")
        instance = repo.get_agent_instance(thread.agent_instance_id)
        debug_thread = thread.thread_kind == "debug"
        skill_context = build_skill_runtime_context(
            runtime.skill_service,
            user_id=thread.user_id,
            agent_instance_id=thread.agent_instance_id,
            prefer_draft=debug_thread,
            approvals=runtime.approval_manager,
            thread_id=thread_id,
            config_version_id=None if debug_thread else thread.config_version_id,
        )
        runtime_tool_names = {
            str(getattr(item, "name", ""))
            for item in (runtime.tools or [])
            if getattr(item, "name", "")
        }
        configured_tool_codes = list(skill_context.enabled_tool_codes)
        effective_tool_codes = [code for code in configured_tool_codes if code in runtime_tool_names]
        scope_records = runtime.approval_manager.repository.list_for_scope(
            user_id=thread.user_id, agent_instance_id=thread.agent_instance_id,
            config_version_id=skill_context.config_version_id, thread_id=thread_id,
        )
        tool_records = [item for item in scope_records if item.approval_kind == "tool"]
        if tool_records:
            effective_tool_codes = [
                code for code in effective_tool_codes
                if runtime.approval_manager.ensure(
                    user_id=thread.user_id, agent_instance_id=thread.agent_instance_id,
                    config_version_id=skill_context.config_version_id, thread_id=thread_id,
                    approval_kind="tool", resource_code=code,
                )
            ]
        scoped_graph = runtime.graph_for_tool_codes(
            effective_tool_codes,
            config_version_id=skill_context.config_version_id,
        )
        config = build_invoke_config(
            thread_id=thread_id,
            user_id=thread.user_id,
            agent_instance_id=thread.agent_instance_id,
            allowed_workflow_codes=list(skill_context.workflow_codes),
            assistant_timezone=runtime.settings.assistant_timezone,
            config_version_id=skill_context.config_version_id,
            system_prompt=skill_context.system_prompt,
            skill_instructions=list(skill_context.skill_instructions),
            enabled_tool_codes=effective_tool_codes,
            knowledge_sources=selected_document_filenames(
                repo.list_knowledge_documents(thread.agent_instance_id),
                skill_context.knowledge_document_ids,
            ),
            template_code=instance.template_code if instance else "",
        )
        return EventSourceResponse(
            stream_chat_events(runtime, thread_id, payload, config, graph=scoped_graph),
            media_type="text/event-stream",
            ping=0,
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/config")
    def get_config() -> dict[str, Any]:
        return runtime.settings.public_config()

    @app.get("/v1/agent-types")
    def list_agent_types(user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        del user
        return {"items": [
            {"template_code": DOUYIN_OPS_TEMPLATE, "name": "运营助手", "description": "保留现有抖音运营工作流和 Dify 能力。", "supports_custom_config": False},
            {"template_code": CUSTOM_TEMPLATE, "name": "自定义智能体", "description": "按实例配置提示词、知识库、工具和 Skill。", "supports_custom_config": True},
        ]}

    register_agent_config_routes(app, runtime)
    register_skill_routes(app, runtime)

    @app.post("/v1/agent-instances/{agent_instance_id}/approvals", status_code=201)
    def request_approval(
        agent_instance_id: str, body: ApprovalRequestIn,
        user: UserRecord = Depends(_auth_user),
    ) -> dict[str, Any]:
        instance = _owned_instance(user, agent_instance_id)
        if body.approval_kind not in APPROVAL_KINDS:
            raise _http_error(400, "unsupported approval kind")
        if body.approval_scope not in APPROVAL_SCOPES:
            raise _http_error(400, "unsupported approval scope")
        _owned_thread(user, body.thread_id)
        try:
            config_id = UUID(body.config_version_id)
        except ValueError as exc:
            raise _http_error(400, "invalid config_version_id") from exc
        try:
            config = runtime.skill_service.repository.get_config(config_id)
        except Exception as exc:
            raise _http_error(404, "config version not found") from exc
        if (config.get("user_id") != user.user_id
                or config.get("agent_instance_id") != instance.agent_instance_id):
            raise _http_error(403, "config version forbidden")
        thread = repo.get_app_thread(body.thread_id)
        if thread is None or thread.agent_instance_id != instance.agent_instance_id:
            raise _http_error(403, "thread does not belong to agent instance")
        try:
            record = runtime.approval_manager.require_or_request(
                user_id=user.user_id, agent_instance_id=instance.agent_instance_id,
                config_version_id=config_id, thread_id=body.thread_id,
                approval_kind=body.approval_kind, resource_code=body.resource_code.strip(),
                approval_scope=body.approval_scope,
            )
        except ValueError as exc:
            raise _http_error(400, str(exc)) from exc
        if record is None:
            records = runtime.approval_manager.repository.list_for_scope(
                user_id=user.user_id, agent_instance_id=instance.agent_instance_id,
                config_version_id=config_id, thread_id=body.thread_id,
            )
            record = next(item for item in records
                          if item.approval_kind == body.approval_kind
                          and item.resource_code == body.resource_code.strip())
        return _serialize_approval(record)

    @app.post("/v1/approvals/{approval_id}/decision")
    def decide_approval(
        approval_id: str, body: ApprovalDecisionIn,
        user: UserRecord = Depends(_auth_user),
    ) -> dict[str, Any]:
        try:
            record = runtime.approval_manager.repository.get(UUID(approval_id))
        except (ValueError, AttributeError):
            record = None
        if record is None or record.user_id != user.user_id:
            raise _http_error(404, "approval not found")
        try:
            updated = runtime.approval_manager.repository.decide(
                record.approval_id, user_id=user.user_id,
                approved=body.approved, reason=body.reason,
            )
        except ApprovalScopeError as exc:
            raise _http_error(404, "approval not found") from exc
        return _serialize_approval(updated)

    @app.get("/v1/agent-instances/{agent_instance_id}/approvals")
    def list_approvals(
        agent_instance_id: str, config_version_id: str | None = None,
        thread_id: str | None = None, user: UserRecord = Depends(_auth_user),
    ) -> dict[str, Any]:
        instance = _owned_instance(user, agent_instance_id)
        parsed_config = None
        if config_version_id is not None:
            try:
                parsed_config = UUID(config_version_id)
            except ValueError as exc:
                raise _http_error(400, "invalid config_version_id") from exc
        records = runtime.approval_manager.repository.list_for_agent(
            user_id=user.user_id, agent_instance_id=instance.agent_instance_id,
            config_version_id=parsed_config, thread_id=thread_id,
        )
        return {"items": [_serialize_approval(item) for item in records]}


    @app.post("/v1/auth/register", status_code=201)
    def register(body: RegisterIn) -> dict[str, Any]:
        login_name = (body.login_name or "").strip()
        if not login_name:
            raise _http_error(400, "login_name must not be blank")
        try:
            password = validate_password(body.password)
            user = repo.create_user(login_name, hash_password(password))
        except InvalidPasswordError as exc:
            raise _http_error(400, str(exc)) from exc
        except DuplicateLoginError as exc:
            raise _http_error(409, "login_name already exists") from exc
        except RepositoryError as exc:
            raise _http_error(400, str(exc)) from exc
        return {"user_id": str(user.user_id), "login_name": user.login_name}

    @app.post("/v1/auth/login")
    def login(body: LoginIn) -> dict[str, Any]:
        login_name = (body.login_name or "").strip()
        user = repo.get_user_by_login_name(login_name)
        if user is None or not verify_password(body.password, user.password_hash):
            raise _http_error(401, "invalid credentials")
        if user.status == "disabled":
            raise _http_error(403, "user is disabled")
        token = new_session_token()
        repo.create_session(
            user.user_id,
            hash_token(token),
            utcnow() + timedelta(days=SESSION_DAYS),
        )
        repo.set_user_last_login(user.user_id)
        return {
            "token": token,
            "user_id": str(user.user_id),
            "login_name": user.login_name,
        }

    @app.post("/v1/auth/logout")
    def logout(request: Request, user: UserRecord = Depends(_auth_user)) -> dict[str, bool]:
        session = getattr(request.state, "session", None)
        if session is not None:
            repo.delete_session(session.session_id)
        return {"ok": True}

    @app.get("/v1/me")
    def me(user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        return {
            "user_id": str(user.user_id),
            "login_name": user.login_name,
            "status": user.status,
        }

    @app.get("/v1/agent-instances")
    def list_instances(user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        items = [instance_card(item) for item in repo.list_agent_instances(user.user_id)]
        return {"items": items}

    @app.post("/v1/agent-instances", status_code=201)
    def create_instance(body: AgentInstanceIn, user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        try:
            instance = create_agent_instance_for_user(
                runtime,
                user,
                template_code=body.template_code,
                title=body.title,
                intro=body.intro,
                avatar=body.avatar,
            )
        except InvalidTitleError as exc:
            raise _http_error(400, str(exc)) from exc
        except DuplicateTitleError as exc:
            raise _http_error(409, "title already in use") from exc
        except UnsupportedTemplateError as exc:
            raise _http_error(400, str(exc)) from exc
        except AvatarError as exc:
            raise _http_error(400, str(exc)) from exc
        except RepositoryError as exc:
            raise _http_error(400, str(exc)) from exc
        return instance_card(instance)

    @app.patch("/v1/agent-instances/{agent_instance_id}")
    def patch_instance(
        agent_instance_id: str,
        body: AgentInstancePatchIn,
        user: UserRecord = Depends(_auth_user),
    ) -> dict[str, Any]:
        instance = _owned_instance(user, agent_instance_id)
        avatar_uri = UNSET
        if body.avatar is not None:
            try:
                avatar_uri = save_avatar(avatar_root(runtime.media_root), user.user_id, body.avatar)
            except AvatarError as exc:
                raise _http_error(400, str(exc)) from exc
        try:
            updated = repo.update_agent_instance(
                instance.agent_instance_id,
                user.user_id,
                title=body.title if body.title is not None else UNSET,
                intro=body.intro if body.intro is not None else UNSET,
                avatar_uri=avatar_uri,
            )
        except InvalidTitleError as exc:
            raise _http_error(400, str(exc)) from exc
        except DuplicateTitleError as exc:
            raise _http_error(409, "title already in use") from exc
        except NotFoundError as exc:
            raise _http_error(404, "agent instance not found") from exc
        return instance_card(updated)

    @app.delete("/v1/agent-instances/{agent_instance_id}")
    def delete_instance(
        agent_instance_id: str,
        user: UserRecord = Depends(_auth_user),
    ) -> dict[str, Any]:
        instance = _owned_instance(user, agent_instance_id)
        repo.archive_agent_instance(instance.agent_instance_id)
        return {
            "ok": True,
            "agent_instance_id": str(instance.agent_instance_id),
            "status": "archived",
        }

    @app.post("/v1/agent-instances/{agent_instance_id}/open")
    def open_instance(agent_instance_id: str, user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        instance = _owned_instance(user, agent_instance_id)
        before = instance.updated_at
        thread = ensure_official_thread(runtime, user, instance)
        after = repo.get_agent_instance(instance.agent_instance_id)
        if after is not None and after.updated_at != before:
            raise _http_error(500, "opening a conversation must not update the card")
        return {
            "agent_instance_id": str(instance.agent_instance_id),
            "thread_id": thread.thread_id,
            "config_version_id": str(thread.config_version_id) if thread.config_version_id else None,
            "updated_at": after.updated_at.isoformat() if after else instance.updated_at.isoformat(),
        }

    @app.get("/v1/agent-instances/{agent_instance_id}/sidebar")
    def get_sidebar(agent_instance_id: str, user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        instance = _owned_instance(user, agent_instance_id)
        payload = sidebar_payload(runtime, instance)
        dumped = str(payload)
        if runtime.settings.dify_api_key and runtime.settings.dify_api_key in dumped:
            raise _http_error(500, "sidebar leaked a secret")
        return payload

    @app.get("/v1/agent-instances/{agent_instance_id}/avatar")
    def get_avatar(agent_instance_id: str, user: UserRecord = Depends(_auth_user)):
        instance = _owned_instance(user, agent_instance_id)
        try:
            path = resolve_avatar_file(avatar_root(runtime.media_root), instance.avatar_uri)
        except FileNotFoundError as exc:
            raise _http_error(404, "avatar not found") from exc
        suffix = path.suffix.lower()
        media_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }.get(suffix, "application/octet-stream")
        return FileResponse(path, media_type=media_type)

    @app.post("/v1/threads")
    def create_thread(user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        raise _http_error(400, "use POST /v1/agent-instances/{id}/open")

    @app.get("/v1/threads/{thread_id}")
    def get_thread(thread_id: str, user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        _owned_thread(user, thread_id)
        return serialize_thread(runtime, thread_id)

    @app.post("/v1/threads/{thread_id}/messages")
    async def post_message(
        thread_id: str,
        body: MessageIn,
        user: UserRecord = Depends(_auth_user),
    ) -> EventSourceResponse:
        _owned_thread(user, thread_id)
        current = serialize_thread(runtime, thread_id)
        if current.get("status") == "interrupted":
            raise _http_error(409, "thread is waiting for review")
        metadata = new_message_metadata(
            client_message_id=body.client_message_id,
            created_at=datetime.now(ZoneInfo(runtime.settings.assistant_timezone)),
        )
        message = HumanMessage(
            content=body.content,
            id=metadata["message_id"],
            additional_kwargs={"chat_message": metadata},
        )
        return await _arun(thread_id, {"messages": [message]})

    @app.post("/v1/threads/{thread_id}/resume")
    async def resume_thread(
        thread_id: str,
        body: ResumeIn,
        user: UserRecord = Depends(_auth_user),
    ) -> EventSourceResponse:
        _owned_thread(user, thread_id)
        current = serialize_thread(runtime, thread_id)
        if current.get("status") != "interrupted":
            raise _http_error(409, "thread is not waiting for review")
        pending = current.get("interrupt") or {}
        options = pending.get("options") or []
        if pending.get("type") == "review_media" and not options:
            # Keep legacy persisted HITL payloads safe: media actions are a
            # fixed server-side contract, never an arbitrary client string.
            options = ["approve", "skip", "update", "cancel", "reject"]
        if options and body.action not in options:
            raise _http_error(400, "unsupported resume action for current approval")
        decision = {
            "action": body.action,
            "prompt": body.prompt,
            "params": body.params or {},
        }
        return await _arun(thread_id, Command(resume=decision))

    @app.post("/v1/jobs/{job_id}/disable")
    def disable_owned_job(job_id: str, user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        try:
            job_uuid = parse_job_uuid(job_id, label="job")
            return disable_job(repo, user_id=user.user_id, job_id=job_uuid)
        except JobAccessDenied as exc:
            raise _http_error(403, "job forbidden") from exc
        except NotFoundError as exc:
            raise _http_error(404, "job not found") from exc

    @app.post("/v1/job-runs/{run_id}/cancel")
    def cancel_owned_job_run(run_id: str, user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        try:
            run_uuid = parse_job_uuid(run_id, label="job run")
            return cancel_job_run(repo, user_id=user.user_id, job_run_id=run_uuid)
        except JobAccessDenied as exc:
            raise _http_error(403, "job run forbidden") from exc
        except JobRunNotCancellableError as exc:
            raise _http_error(409, str(exc)) from exc
        except NotFoundError as exc:
            raise _http_error(404, "job run not found") from exc

    @app.post("/v1/assistant/jobs/run")
    async def run_job(body: JobRunIn, user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        kind = (body.kind or "").strip()
        if kind == "morning_brief":
            return await arun_morning_brief(runtime, force=body.force)
        if kind == "hydrate":
            if not body.slot:
                raise _http_error(400, "slot is required for hydrate")
            try:
                return await arun_hydrate(runtime, body.slot, force=body.force)
            except ValueError as exc:
                raise _http_error(400, str(exc)) from exc
        raise _http_error(400, "kind must be morning_brief or hydrate")

    @app.get("/v1/media/{user_id}/{agent_instance_id}/{kind}/{file_name}")
    def get_media(
        user_id: str,
        agent_instance_id: str,
        kind: str,
        file_name: str,
        user: UserRecord = Depends(_auth_user),
    ):
        if str(user.user_id) != str(user_id):
            raise _http_error(404, "media not found")
        try:
            instance_uuid = UUID(str(agent_instance_id))
        except ValueError as exc:
            raise _http_error(404, "media not found") from exc
        try:
            instance = require_owned_instance(repo, user.user_id, instance_uuid)
        except NotFoundError as exc:
            raise _http_error(404, "media not found") from exc
        if str(instance.user_id) != str(user.user_id):
            raise _http_error(403, "media forbidden")
        try:
            path = safe_media_file(
                runtime.media_root,
                kind,
                file_name,
                user_id=str(user.user_id),
                agent_instance_id=str(instance.agent_instance_id),
            )
        except FileNotFoundError:
            raise _http_error(404, "media not found") from None
        except MediaPathError:
            raise _http_error(400, "invalid media path") from None
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
