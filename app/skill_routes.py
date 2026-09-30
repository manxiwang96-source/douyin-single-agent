from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.auth import hash_token
from app.plaza import require_owned_instance
from app.repository import NotFoundError, UserRecord, utcnow
from app.runtime import AppRuntime
from app.skills import (
    SkillError,
    SkillImportStateError,
    SkillNotFoundError,
    SkillSecurityError,
    serialize_import,
    serialize_search_candidate,
    serialize_skill,
)


class SkillSearchIn(BaseModel):
    query: str = ""
    limit: int = Field(default=10, ge=1, le=50)


class SkillImportIn(BaseModel):
    candidate_id: str = Field(min_length=1)
    target_agent_instance_id: str | None = None


class ConfigSkillIn(BaseModel):
    skill_ids: list[str] = Field(default_factory=list)


class SkillBindingPatchIn(BaseModel):
    enabled: bool = True
    name: str | None = None
    description: str | None = None
    instructions: str | None = None
    risk_level: str | None = None
    approval_mode: str | None = None


class AgentSkillCreateIn(BaseModel):
    name: str = ""
    description: str = ""
    instructions: str = ""
    risk_level: str = "medium"
    approval_mode: str = "once"


bearer_scheme = HTTPBearer(auto_error=False)


def _http_error(status_code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=detail)


def register_skill_routes(app: FastAPI, runtime: AppRuntime) -> None:
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

    @app.post("/v1/skills/discovery/search")
    def search_skills(body: SkillSearchIn, user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        del user
        try:
            items = runtime.skill_service.search(body.query, limit=body.limit)
        except SkillError as exc:
            raise _http_error(503, str(exc)) from exc
        return {"items": [serialize_search_candidate(item) for item in items]}

    @app.get("/v1/skills/catalog")
    def get_skill_catalog(user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        return {"items": [serialize_skill(item) for item in runtime.skill_service.list_catalog(user.user_id)]}

    @app.post("/v1/skills/imports", status_code=201)
    def start_skill_import(
        body: SkillImportIn,
        agent_instance_id: str | None = None,
        user: UserRecord = Depends(_auth_user),
    ) -> dict[str, Any]:
        target_id = agent_instance_id or body.target_agent_instance_id
        if not target_id:
            raise _http_error(400, "target_agent_instance_id is required")
        _owned_instance(user, target_id)
        try:
            item = runtime.skill_service.start_import(user.user_id, _parse_instance_id(target_id), body.candidate_id)
        except SkillNotFoundError as exc:
            raise _http_error(404, str(exc)) from exc
        except SkillSecurityError as exc:
            raise _http_error(400, str(exc)) from exc
        except SkillError as exc:
            raise _http_error(503, str(exc)) from exc
        return serialize_import(item)

    @app.get("/v1/skills/imports/{import_id}")
    def get_skill_import(import_id: str, user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        try:
            item = runtime.skill_service.get_import_for_user(user.user_id, UUID(import_id))
        except ValueError as exc:
            raise _http_error(404, "skill import not found") from exc
        except SkillNotFoundError as exc:
            raise _http_error(404, str(exc)) from exc
        except SkillSecurityError as exc:
            raise _http_error(403, str(exc)) from exc
        return serialize_import(item)

    @app.post("/v1/skills/imports/{import_id}/confirm")
    def confirm_skill_import(import_id: str, user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        try:
            skill = runtime.skill_service.confirm_import(user.user_id, UUID(import_id))
        except ValueError as exc:
            raise _http_error(404, "skill import not found") from exc
        except SkillNotFoundError as exc:
            raise _http_error(404, str(exc)) from exc
        except SkillImportStateError as exc:
            raise _http_error(409, str(exc)) from exc
        except SkillSecurityError as exc:
            raise _http_error(403, str(exc)) from exc
        return serialize_skill(skill)

    @app.post("/v1/skills/imports/{import_id}/reject")
    def reject_skill_import(import_id: str, user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        try:
            item = runtime.skill_service.reject_import(user.user_id, UUID(import_id))
        except ValueError as exc:
            raise _http_error(404, "skill import not found") from exc
        except SkillNotFoundError as exc:
            raise _http_error(404, str(exc)) from exc
        except SkillImportStateError as exc:
            raise _http_error(409, str(exc)) from exc
        except SkillSecurityError as exc:
            raise _http_error(403, str(exc)) from exc
        return serialize_import(item)

    @app.post("/v1/skills/imports/{import_id}/retry")
    def retry_skill_import(import_id: str, user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        try:
            item = runtime.skill_service.retry_import(user.user_id, UUID(import_id))
        except ValueError as exc:
            raise _http_error(404, "skill import not found") from exc
        except SkillNotFoundError as exc:
            raise _http_error(404, str(exc)) from exc
        except SkillImportStateError as exc:
            raise _http_error(409, str(exc)) from exc
        except SkillSecurityError as exc:
            raise _http_error(403, str(exc)) from exc
        return serialize_import(item)

    @app.post("/v1/skills/imports/{import_id}/expire")
    def expire_skill_import(import_id: str, user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        try:
            item = runtime.skill_service.expire_import(user.user_id, UUID(import_id))
        except ValueError as exc:
            raise _http_error(404, "skill import not found") from exc
        except SkillNotFoundError as exc:
            raise _http_error(404, str(exc)) from exc
        except SkillImportStateError as exc:
            raise _http_error(409, str(exc)) from exc
        except SkillSecurityError as exc:
            raise _http_error(403, str(exc)) from exc
        return serialize_import(item)

    @app.post("/v1/skills/{skill_id}/revoke")
    def revoke_skill(skill_id: str, user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        try:
            skill = runtime.skill_service.revoke_skill(user.user_id, UUID(skill_id))
        except ValueError as exc:
            raise _http_error(404, "skill not found") from exc
        except SkillNotFoundError as exc:
            raise _http_error(404, str(exc)) from exc
        except SkillSecurityError as exc:
            raise _http_error(403, str(exc)) from exc
        return serialize_skill(skill)

    @app.get("/v1/agent-instances/{agent_instance_id}/skills")
    def list_agent_skills(agent_instance_id: str, user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        _owned_instance(user, agent_instance_id)
        config = runtime.skill_service.ensure_config(user.user_id, _parse_instance_id(agent_instance_id))
        return {
            "config_version_id": str(config["config_version_id"]),
            "items": [serialize_skill(item) for item in runtime.skill_service.list_available(user.user_id, _parse_instance_id(agent_instance_id))],
        }

    @app.post("/v1/agent-instances/{agent_instance_id}/skills", status_code=201)
    def create_agent_skill(
        agent_instance_id: str,
        body: AgentSkillCreateIn,
        user: UserRecord = Depends(_auth_user),
    ) -> dict[str, Any]:
        instance = _owned_instance(user, agent_instance_id)
        try:
            skill = runtime.skill_service.create_declarative_skill(
                user.user_id,
                instance.agent_instance_id,
                name=body.name,
                description=body.description,
                instructions=body.instructions,
                risk_level=body.risk_level,
                approval_mode=body.approval_mode,
            )
        except SkillNotFoundError as exc:
            raise _http_error(404, str(exc)) from exc
        except SkillSecurityError as exc:
            raise _http_error(403, str(exc)) from exc
        except SkillError as exc:
            raise _http_error(400, str(exc)) from exc
        return serialize_skill(skill)

    @app.patch("/v1/agent-instances/{agent_instance_id}/skills/{skill_id}")
    def patch_agent_skill(agent_instance_id: str, skill_id: str, body: SkillBindingPatchIn, user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        instance = _owned_instance(user, agent_instance_id)
        try:
            target = UUID(skill_id)
            metadata = {
                key: value
                for key, value in {
                    "name": body.name,
                    "description": body.description,
                    "instructions": body.instructions,
                    "risk_level": body.risk_level,
                    "approval_mode": body.approval_mode,
                }.items()
                if value is not None
            }
            if metadata:
                runtime.skill_service.update_declarative_skill(
                    user.user_id,
                    instance.agent_instance_id,
                    target,
                    **metadata,
                )
            current = runtime.skill_service.list_available(user.user_id, instance.agent_instance_id)
            ids = [item.skill_id for item in current if item.skill_id != target]
            if body.enabled:
                ids.append(target)
            items = runtime.skill_service.set_config_skills(user.user_id, instance.agent_instance_id, ids)
        except ValueError as exc:
            raise _http_error(400, "invalid skill_id") from exc
        except SkillNotFoundError as exc:
            raise _http_error(404, str(exc)) from exc
        except SkillSecurityError as exc:
            raise _http_error(403, str(exc)) from exc
        except SkillError as exc:
            raise _http_error(400, str(exc)) from exc
        config = runtime.skill_service.ensure_config(user.user_id, instance.agent_instance_id)
        return {"config_version_id": str(config["config_version_id"]), "items": [serialize_skill(item) for item in items]}

    @app.delete("/v1/agent-instances/{agent_instance_id}/skills/{skill_id}")
    def delete_agent_skill(agent_instance_id: str, skill_id: str, user: UserRecord = Depends(_auth_user)) -> dict[str, Any]:
        instance = _owned_instance(user, agent_instance_id)
        try:
            items = runtime.skill_service.remove_instance_skill(
                user.user_id,
                instance.agent_instance_id,
                UUID(skill_id),
            )
        except ValueError as exc:
            raise _http_error(400, "invalid skill_id") from exc
        except SkillNotFoundError as exc:
            raise _http_error(404, str(exc)) from exc
        except SkillSecurityError as exc:
            raise _http_error(403, str(exc)) from exc
        except SkillError as exc:
            raise _http_error(400, str(exc)) from exc
        config = runtime.skill_service.ensure_config(user.user_id, instance.agent_instance_id)
        return {"config_version_id": str(config["config_version_id"]), "items": [serialize_skill(item) for item in items]}

    @app.put("/v1/agent-instances/{agent_instance_id}/config/draft/skills")
    def update_agent_skills(
        agent_instance_id: str,
        body: ConfigSkillIn,
        user: UserRecord = Depends(_auth_user),
    ) -> dict[str, Any]:
        _owned_instance(user, agent_instance_id)
        try:
            skill_ids = [UUID(item) for item in body.skill_ids]
            items = runtime.skill_service.set_config_skills(user.user_id, _parse_instance_id(agent_instance_id), skill_ids)
        except ValueError as exc:
            raise _http_error(400, "invalid skill_id") from exc
        except SkillNotFoundError as exc:
            raise _http_error(404, str(exc)) from exc
        except SkillSecurityError as exc:
            raise _http_error(403, str(exc)) from exc
        config = runtime.skill_service.ensure_config(user.user_id, _parse_instance_id(agent_instance_id))
        return {"config_version_id": str(config["config_version_id"]), "items": [serialize_skill(item) for item in items]}
