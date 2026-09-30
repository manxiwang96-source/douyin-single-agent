from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, ValidationError
from starlette.datastructures import UploadFile

from app.auth import hash_token
from app.knowledge import (
    KnowledgeUploadError,
    MAX_KNOWLEDGE_UPLOAD_BYTES,
    decode_knowledge_upload,
    index_instance_knowledge_text,
    save_knowledge_upload,
    validate_knowledge_upload_filename,
)
from app.plaza import ensure_debug_thread, require_owned_instance
from app.repository import NotFoundError, RepositoryError, UserRecord, utcnow
from app.runtime import AppRuntime
from app.skills import (
    KnowledgeDocumentNotOwnedError,
    UnknownToolCodeError,
    build_prompt_optimize_result,
    prompt_templates,
    validate_draft_knowledge_document_ids,
    validate_draft_tool_codes,
)
from app.tool_catalog import (
    SELECTABLE_TOOL_CATALOG,
    enabled_tool_code_set,
)


class ConfigDraftIn(BaseModel):
    system_prompt: str | None = None
    welcome_message: str | None = None
    example_questions: list[str] | None = None
    enabled_tool_codes: list[str] | None = None
    workflow_codes: list[str] | None = None
    knowledge_document_ids: list[str] | None = None


class KnowledgeDocumentIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    filename: str = Field(min_length=1, max_length=255)
    storage_uri: str = Field(min_length=1, max_length=1000)
    source: str = Field(default="user_upload", pattern="^(seeded_demo|user_upload)$")
    status: str = Field(default="uploaded", pattern="^(uploaded|indexing|ready|failed|archived)$")


class KnowledgeDocumentPatchIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: str | None = Field(default=None, pattern="^(uploaded|indexing|ready|failed|archived)$")


class PromptOptimizeIn(BaseModel):
    prompt: str | None = None


def _serialize_config(config: dict[str, Any]) -> dict[str, Any]:
    data = dict(config)
    for key in ("config_version_id", "user_id", "agent_instance_id"):
        if data.get(key) is not None:
            data[key] = str(data[key])
    for key in ("created_at", "updated_at"):
        if data.get(key) is not None:
            data[key] = data[key].isoformat()
    return data


bearer_scheme = HTTPBearer(auto_error=False)


def _http_error(status_code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=detail)


def register_agent_config_routes(app: FastAPI, runtime: AppRuntime) -> None:
    repo = runtime.business_repo

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

    @app.get("/v1/prompt-templates")
    def list_prompt_templates(user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        del user
        return {"items": [item.__dict__ for item in prompt_templates()]}

    @app.get("/v1/agent-instances/{agent_instance_id}/config")
    def get_agent_config(agent_instance_id: str, user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        _owned_instance(user, agent_instance_id)
        return _serialize_config(runtime.skill_service.ensure_config(user.user_id, _parse_instance_id(agent_instance_id)))

    @app.get("/v1/agent-instances/{agent_instance_id}/config/versions")
    def list_agent_config_versions(agent_instance_id: str, user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        instance = _owned_instance(user, agent_instance_id)
        runtime.skill_service.ensure_config(user.user_id, instance.agent_instance_id)
        return {"items": [_serialize_config(item) for item in runtime.skill_service.list_config_versions(user.user_id, instance.agent_instance_id)]}

    @app.get("/v1/agent-instances/{agent_instance_id}/knowledge")
    def list_agent_knowledge(agent_instance_id: str, user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        instance = _owned_instance(user, agent_instance_id)
        config = runtime.skill_service.ensure_config(user.user_id, instance.agent_instance_id)
        documents = repo.list_knowledge_documents(instance.agent_instance_id)
        return {
            "config_version_id": str(config["config_version_id"]),
            "selected_document_ids": [str(item) for item in (config.get("knowledge_document_ids") or [])],
            "items": [
                {
                    "document_id": str(item.document_id), "title": item.title, "filename": item.filename,
                    "source": item.source, "status": item.status,
                }
                for item in documents
            ],
        }

    def _knowledge_payload(item) -> dict[str, Any]:
        return {
            "document_id": str(item.document_id),
            "title": item.title,
            "filename": item.filename,
            "storage_uri": item.storage_uri,
            "source": item.source,
            "status": item.status,
        }

    def _attach_knowledge_to_draft(user: UserRecord, instance, document_id) -> None:
        draft = runtime.skill_service.ensure_config(user.user_id, instance.agent_instance_id)
        selected = [str(value) for value in (draft.get("knowledge_document_ids") or [])]
        doc_id = str(document_id)
        if doc_id not in selected:
            selected.append(doc_id)
        runtime.skill_service.repository.update_config(
            draft["config_version_id"],
            knowledge_document_ids=selected,
        )

    async def _create_uploaded_knowledge(user: UserRecord, instance, upload: UploadFile, title: str | None) -> dict[str, Any]:
        try:
            filename = validate_knowledge_upload_filename(upload.filename or "")
        except KnowledgeUploadError as exc:
            raise _http_error(400, str(exc)) from exc
        content = await upload.read(MAX_KNOWLEDGE_UPLOAD_BYTES + 1)
        try:
            text = decode_knowledge_upload(content)
        except KnowledgeUploadError as exc:
            raise _http_error(400, str(exc)) from exc
        display_title = (title or "").strip() or Path(filename).stem
        stored_name = f"{uuid4().hex}_{filename}"
        storage_uri = save_knowledge_upload(
            runtime.media_root,
            user_id=user.user_id,
            agent_instance_id=instance.agent_instance_id,
            stored_name=stored_name,
            content=content,
        )
        try:
            item = repo.add_knowledge_document(
                user.user_id,
                instance.agent_instance_id,
                title=display_title,
                filename=filename,
                storage_uri=storage_uri,
                source="user_upload",
                status="uploaded",
            )
        except RepositoryError as exc:
            raise _http_error(400, str(exc)) from exc
        try:
            index_instance_knowledge_text(
                runtime.memory_store,
                user_id=user.user_id,
                agent_instance_id=instance.agent_instance_id,
                text=text,
                source=filename,
                key_prefix=str(item.document_id),
            )
        except Exception as exc:
            item = repo.set_knowledge_document_status(item.document_id, "failed")
            raise _http_error(400, "failed to index knowledge file") from exc
        item = repo.set_knowledge_document_status(item.document_id, "ready")
        _attach_knowledge_to_draft(user, instance, item.document_id)
        return _knowledge_payload(item)

    @app.post("/v1/agent-instances/{agent_instance_id}/knowledge", status_code=201)
    async def create_agent_knowledge(request: Request, agent_instance_id: str, user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        instance = _owned_instance(user, agent_instance_id)
        content_type = (request.headers.get("content-type") or "").lower()
        if "multipart/form-data" in content_type:
            form = await request.form()
            try:
                upload = form.get("file")
                if not isinstance(upload, UploadFile):
                    raise _http_error(400, "knowledge file is required")
                title_value = form.get("title")
                title = None if isinstance(title_value, UploadFile) or title_value is None else str(title_value)
                return await _create_uploaded_knowledge(user, instance, upload, title)
            finally:
                close = getattr(form, "close", None)
                if close is not None:
                    await close()
        try:
            payload = await request.json()
        except Exception as exc:
            raise _http_error(400, "invalid knowledge payload") from exc
        try:
            body = KnowledgeDocumentIn.model_validate(payload)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
        try:
            item = repo.add_knowledge_document(
                user.user_id, instance.agent_instance_id, title=body.title.strip(), filename=body.filename.strip(),
                storage_uri=body.storage_uri.strip(), source=body.source, status=body.status,
            )
        except RepositoryError as exc:
            raise _http_error(400, str(exc)) from exc
        return _knowledge_payload(item)

    @app.patch("/v1/agent-instances/{agent_instance_id}/knowledge/{document_id}")
    def update_agent_knowledge(agent_instance_id: str, document_id: str, body: KnowledgeDocumentPatchIn, user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        instance = _owned_instance(user, agent_instance_id)
        try:
            item = repo.update_knowledge_document(UUID(document_id), user.user_id, instance.agent_instance_id, title=body.title, status=body.status)
        except ValueError as exc:
            raise _http_error(404, "knowledge document not found") from exc
        except RepositoryError as exc:
            raise _http_error(404, str(exc)) from exc
        if item.status == "archived":
            draft = runtime.skill_service.ensure_config(user.user_id, instance.agent_instance_id)
            selected = [str(value) for value in (draft.get("knowledge_document_ids") or []) if str(value) != str(item.document_id)]
            runtime.skill_service.repository.update_config(draft["config_version_id"], knowledge_document_ids=selected)
        return {"document_id": str(item.document_id), "title": item.title, "filename": item.filename, "storage_uri": item.storage_uri, "source": item.source, "status": item.status}

    @app.delete("/v1/agent-instances/{agent_instance_id}/knowledge/{document_id}")
    def delete_agent_knowledge(agent_instance_id: str, document_id: str, user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        instance = _owned_instance(user, agent_instance_id)
        try:
            item = repo.delete_knowledge_document(UUID(document_id), user.user_id, instance.agent_instance_id)
        except ValueError as exc:
            raise _http_error(404, "knowledge document not found") from exc
        except RepositoryError as exc:
            raise _http_error(404, str(exc)) from exc
        draft = runtime.skill_service.ensure_config(user.user_id, instance.agent_instance_id)
        selected = [str(value) for value in (draft.get("knowledge_document_ids") or []) if str(value) != str(item.document_id)]
        runtime.skill_service.repository.update_config(draft["config_version_id"], knowledge_document_ids=selected)
        return {"document_id": str(item.document_id), "status": item.status}

    @app.put("/v1/agent-instances/{agent_instance_id}/config/draft")
    def update_agent_config(
        agent_instance_id: str,
        body: ConfigDraftIn,
        user: UserRecord = Depends(_auth_user),
    ) -> dict[str, Any]:
        _owned_instance(user, agent_instance_id)
        config = runtime.skill_service.ensure_config(user.user_id, _parse_instance_id(agent_instance_id))
        fields = body.model_dump(exclude_none=True)
        if "example_questions" in fields:
            fields["example_questions"] = [str(item)[:200] for item in fields["example_questions"][:10]]
        if "enabled_tool_codes" in fields:
            try:
                fields["enabled_tool_codes"] = validate_draft_tool_codes(fields["enabled_tool_codes"])
            except UnknownToolCodeError as exc:
                raise _http_error(400, str(exc)) from exc
        if "knowledge_document_ids" in fields:
            try:
                fields["knowledge_document_ids"] = validate_draft_knowledge_document_ids(
                    fields["knowledge_document_ids"],
                    allowed_document_ids=[
                        item.document_id
                        for item in repo.list_knowledge_documents(_parse_instance_id(agent_instance_id))
                    ],
                )
            except KnowledgeDocumentNotOwnedError as exc:
                raise _http_error(403, str(exc)) from exc
        updated = runtime.skill_service.repository.update_config(config["config_version_id"], **fields)
        return _serialize_config(updated)

    @app.get("/v1/agent-instances/{agent_instance_id}/tools")
    def list_agent_tools(agent_instance_id: str, user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        instance = _owned_instance(user, agent_instance_id)
        config = runtime.skill_service.ensure_config(user.user_id, instance.agent_instance_id)
        enabled_codes = enabled_tool_code_set(config.get("enabled_tool_codes"))
        items = [
            item.as_dict(enabled=item.built_in or item.tool_code in enabled_codes)
            for item in SELECTABLE_TOOL_CATALOG.items
        ]
        return {"config_version_id": str(config["config_version_id"]), "items": items}

    @app.put("/v1/agent-instances/{agent_instance_id}/config/draft/tools")
    def update_agent_tools(agent_instance_id: str, body: ConfigDraftIn, user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        instance = _owned_instance(user, agent_instance_id)
        if body.enabled_tool_codes is None:
            raise _http_error(400, "enabled_tool_codes is required")
        try:
            requested = validate_draft_tool_codes(body.enabled_tool_codes)
        except UnknownToolCodeError as exc:
            raise _http_error(400, str(exc)) from exc
        config = runtime.skill_service.ensure_config(user.user_id, instance.agent_instance_id)
        updated = runtime.skill_service.repository.update_config(config["config_version_id"], enabled_tool_codes=requested)
        return _serialize_config(updated)

    @app.post("/v1/agent-instances/{agent_instance_id}/config/publish")
    def publish_agent_config(agent_instance_id: str, user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        _owned_instance(user, agent_instance_id)
        try:
            published = runtime.skill_service.repository.publish_config(user.user_id, _parse_instance_id(agent_instance_id))
        except RepositoryError as exc:
            raise _http_error(400, str(exc)) from exc
        return _serialize_config(published)

    @app.post("/v1/agent-instances/{agent_instance_id}/config/draft/prompt/optimize")
    def optimize_agent_prompt(
        agent_instance_id: str,
        body: PromptOptimizeIn,
        user: UserRecord = Depends(_auth_user),
    ) -> dict[str, Any]:
        _owned_instance(user, agent_instance_id)
        config = runtime.skill_service.ensure_config(user.user_id, _parse_instance_id(agent_instance_id))
        original = body.prompt if body.prompt is not None else config.get("system_prompt", "")
        return build_prompt_optimize_result(original)

    @app.post("/v1/agent-instances/{agent_instance_id}/config/draft/preview")
    def preview_agent_draft(
        agent_instance_id: str, body: PromptOptimizeIn, user: UserRecord = Depends(_auth_user),
    ) -> dict[str, Any]:
        instance = _owned_instance(user, agent_instance_id)
        config = runtime.skill_service.ensure_config(user.user_id, instance.agent_instance_id)
        prompt = (body.prompt if body.prompt is not None else config.get("system_prompt", "")).strip()
        if not prompt:
            prompt = "请根据用户输入提供清晰、可验证的回答。"
        return {
            "config_version_id": str(config["config_version_id"]),
            "status": "draft_preview",
            "answer": f"草稿预览：已收到“{prompt[:200]}”。当前仅使用草稿配置，不创建正式线程、不执行工具、不触发真实触达。",
            "enabled_tool_codes": list(config.get("enabled_tool_codes") or ["get_current_datetime"]),
            "knowledge_document_ids": [str(item) for item in (config.get("knowledge_document_ids") or [])],
        }


    @app.post("/v1/agent-instances/{agent_instance_id}/debug-open")
    def debug_open_instance(agent_instance_id: str, user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        instance = _owned_instance(user, agent_instance_id)
        before = instance.updated_at
        thread = ensure_debug_thread(runtime, user, instance)
        after = repo.get_agent_instance(instance.agent_instance_id)
        if after is not None and after.updated_at != before:
            raise _http_error(500, "opening a conversation must not update the card")
        return {
            "agent_instance_id": str(instance.agent_instance_id),
            "thread_id": thread.thread_id,
            "thread_kind": thread.thread_kind,
            "config_version_id": str(thread.config_version_id) if thread.config_version_id else None,
            "updated_at": after.updated_at.isoformat() if after else instance.updated_at.isoformat(),
        }
