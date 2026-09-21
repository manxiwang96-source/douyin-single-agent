from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable, Protocol, Sequence
from uuid import UUID, uuid4

DOUYIN_OPS_TEMPLATE = "douyin_ops"
DEFAULT_WORKFLOW_CODE = "douyin-lead-discovery"
TITLE_WHITESPACE = re.compile(r"\s")

USER_STATUSES = frozenset({"active", "disabled"})
INSTANCE_STATUSES = frozenset({"draft", "active", "archived"})
AGENT_MODES = frozenset({"single", "multi"})
JOB_RUN_STATUSES = frozenset(
    {
        "scheduled",
        "running",
        "waiting_review",
        "sending",
        "succeeded",
        "failed",
        "skipped",
        "cancelled",
    }
)
KNOWLEDGE_SOURCES = frozenset({"seeded_demo", "user_upload"})
KNOWLEDGE_STATUSES = frozenset({"uploaded", "indexing", "ready", "failed", "archived"})
THREAD_STATUSES = frozenset({"active", "interrupted", "closed", "archived"})
MEDIA_KINDS = frozenset({"image", "video"})
MEDIA_STORAGE_STATUSES = frozenset({"stored", "offloaded", "expired", "missing"})
UNSET = object()


class RepositoryError(Exception):
    """Base error for business-table operations."""


class InvalidTitleError(RepositoryError):
    """Agent instance title failed product naming rules."""


class DuplicateTitleError(RepositoryError):
    """An active/draft instance already uses this title for the user."""


class DuplicateBindingError(RepositoryError):
    """The instance already binds this workflow_code."""


class DuplicateJobRunError(RepositoryError):
    """(job_id, scheduled_for) must stay unique."""


class DuplicateLoginError(RepositoryError):
    """login_name is already taken."""


class UnsupportedTemplateError(RepositoryError):
    """v1 only accepts douyin_ops."""


class NotFoundError(RepositoryError):
    """Referenced row is missing."""


class InvalidStatusError(RepositoryError):
    """Status/source/mode is outside the locked vocabulary."""


@dataclass(frozen=True)
class UserRecord:
    user_id: UUID
    login_name: str
    password_hash: str
    status: str
    created_at: datetime
    last_login_at: datetime | None = None


@dataclass(frozen=True)
class AgentInstanceRecord:
    agent_instance_id: UUID
    user_id: UUID
    template_code: str
    title: str
    intro: str
    avatar_uri: str | None
    agent_mode: str
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class WorkflowBindingRecord:
    id: UUID
    user_id: UUID
    agent_instance_id: UUID
    workflow_code: str
    enabled: bool
    created_at: datetime


@dataclass(frozen=True)
class JobDefinitionRecord:
    job_id: UUID
    user_id: UUID
    agent_instance_id: UUID
    kind: str
    cron: str
    timezone: str
    enabled: bool
    require_approval: bool
    payload: dict
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class JobRunRecord:
    job_run_id: UUID
    job_id: UUID
    user_id: UUID
    agent_instance_id: UUID
    scheduled_for: datetime
    status: str
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None


@dataclass(frozen=True)
class KnowledgeDocumentRecord:
    document_id: UUID
    user_id: UUID
    agent_instance_id: UUID
    title: str
    filename: str
    storage_uri: str
    source: str
    status: str
    created_at: datetime


@dataclass(frozen=True)
class KnowledgeSeed:
    title: str
    filename: str
    storage_uri: str
    source: str = "seeded_demo"


@dataclass(frozen=True)
class SessionRecord:
    session_id: UUID
    user_id: UUID
    token_hash: str
    expires_at: datetime
    created_at: datetime


@dataclass(frozen=True)
class ThreadRecord:
    thread_id: str
    user_id: UUID
    agent_instance_id: UUID
    title: str | None
    status: str
    created_at: datetime
    last_active_at: datetime


@dataclass(frozen=True)
class MediaAssetRecord:
    asset_id: UUID
    user_id: UUID
    agent_instance_id: UUID
    kind: str
    storage_uri: str
    storage_status: str
    created_at: datetime
    thread_id: str | None = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_agent_title(title: str) -> str:
    if not isinstance(title, str):
        raise InvalidTitleError("title must be a string")
    trimmed = title.strip()
    if not trimmed:
        raise InvalidTitleError("title must not be blank")
    if TITLE_WHITESPACE.search(trimmed):
        raise InvalidTitleError("title must not contain whitespace")
    return trimmed


def require_template_code(template_code: str) -> str:
    if template_code != DOUYIN_OPS_TEMPLATE:
        raise UnsupportedTemplateError("v1 only accepts template_code=douyin_ops")
    return template_code


def require_value(value: str, allowed: frozenset[str], label: str) -> str:
    if value not in allowed:
        raise InvalidStatusError(f"invalid {label}: {value}")
    return value


class BusinessRepository(Protocol):
    def create_user(self, login_name: str, password_hash: str, *, status: str = "active") -> UserRecord: ...

    def get_user(self, user_id: UUID) -> UserRecord | None: ...

    def get_user_by_login_name(self, login_name: str) -> UserRecord | None: ...

    def set_user_last_login(self, user_id: UUID, at: datetime | None = None) -> UserRecord: ...

    def create_session(self, user_id: UUID, token_hash: str, expires_at: datetime) -> SessionRecord: ...

    def get_session_by_token_hash(self, token_hash: str) -> SessionRecord | None: ...

    def delete_session(self, session_id: UUID) -> None: ...

    def create_agent_instance(
        self,
        user_id: UUID,
        title: str,
        *,
        intro: str = "",
        avatar_uri: str | None = None,
        template_code: str = DOUYIN_OPS_TEMPLATE,
        agent_mode: str = "single",
        status: str = "active",
    ) -> AgentInstanceRecord: ...

    def get_agent_instance(self, agent_instance_id: UUID) -> AgentInstanceRecord | None: ...

    def list_agent_instances(
        self, user_id: UUID, *, include_archived: bool = False
    ) -> list[AgentInstanceRecord]: ...

    def update_agent_instance(
        self,
        agent_instance_id: UUID,
        user_id: UUID,
        *,
        title: str | None | object = UNSET,
        intro: str | None | object = UNSET,
        avatar_uri: str | None | object = UNSET,
    ) -> AgentInstanceRecord: ...

    def archive_agent_instance(self, agent_instance_id: UUID) -> AgentInstanceRecord: ...

    def bind_workflow(
        self,
        user_id: UUID,
        agent_instance_id: UUID,
        workflow_code: str = DEFAULT_WORKFLOW_CODE,
        *,
        enabled: bool = True,
    ) -> WorkflowBindingRecord: ...

    def list_workflow_bindings(self, agent_instance_id: UUID) -> list[WorkflowBindingRecord]: ...

    def create_job_definition(
        self,
        user_id: UUID,
        agent_instance_id: UUID,
        *,
        kind: str,
        cron: str,
        timezone: str = "Asia/Shanghai",
        payload: dict | None = None,
        require_approval: bool = False,
        enabled: bool = True,
    ) -> JobDefinitionRecord: ...

    def create_job_run(
        self,
        job_id: UUID,
        scheduled_for: datetime,
        *,
        status: str = "scheduled",
        error: str | None = None,
    ) -> JobRunRecord: ...

    def add_knowledge_document(
        self,
        user_id: UUID,
        agent_instance_id: UUID,
        *,
        title: str,
        filename: str,
        storage_uri: str,
        source: str,
        status: str = "uploaded",
    ) -> KnowledgeDocumentRecord: ...

    def set_knowledge_document_status(
        self, document_id: UUID, status: str
    ) -> KnowledgeDocumentRecord: ...

    def seed_knowledge_documents(
        self,
        user_id: UUID,
        agent_instance_id: UUID,
        documents: Sequence[KnowledgeSeed],
        write_store: Callable[[KnowledgeDocumentRecord], None] | None = None,
    ) -> list[KnowledgeDocumentRecord]: ...

    def list_knowledge_documents(self, agent_instance_id: UUID) -> list[KnowledgeDocumentRecord]: ...

    def create_app_thread(
        self,
        user_id: UUID,
        agent_instance_id: UUID,
        *,
        thread_id: str | None = None,
        title: str | None = None,
        status: str = "active",
    ) -> ThreadRecord: ...

    def get_app_thread(self, thread_id: str) -> ThreadRecord | None: ...

    def get_latest_active_thread(self, user_id: UUID, agent_instance_id: UUID) -> ThreadRecord | None: ...

    def add_media_asset(
        self,
        user_id: UUID,
        agent_instance_id: UUID,
        *,
        kind: str,
        storage_uri: str,
        thread_id: str | None = None,
        storage_status: str = "stored",
    ) -> MediaAssetRecord: ...

    def list_media_assets(self, agent_instance_id: UUID) -> list[MediaAssetRecord]: ...


class InMemoryBusinessRepository:
    """Test repository that mirrors SQL uniqueness and naming rules."""

    def __init__(self) -> None:
        self._users: dict[UUID, UserRecord] = {}
        self._instances: dict[UUID, AgentInstanceRecord] = {}
        self._bindings: dict[UUID, WorkflowBindingRecord] = {}
        self._jobs: dict[UUID, JobDefinitionRecord] = {}
        self._job_runs: dict[UUID, JobRunRecord] = {}
        self._documents: dict[UUID, KnowledgeDocumentRecord] = {}
        self._sessions: dict[UUID, SessionRecord] = {}
        self._threads: dict[str, ThreadRecord] = {}
        self._media_assets: dict[UUID, MediaAssetRecord] = {}

    def create_user(self, login_name: str, password_hash: str, *, status: str = "active") -> UserRecord:
        name = (login_name or "").strip()
        if not name:
            raise RepositoryError("login_name must not be blank")
        if not password_hash:
            raise RepositoryError("password_hash is required")
        require_value(status, USER_STATUSES, "user status")
        if any(item.login_name == name for item in self._users.values()):
            raise DuplicateLoginError(f"login_name already exists: {name}")
        record = UserRecord(
            user_id=uuid4(),
            login_name=name,
            password_hash=password_hash,
            status=status,
            created_at=utcnow(),
        )
        self._users[record.user_id] = record
        return record

    def get_user(self, user_id: UUID) -> UserRecord | None:
        return self._users.get(user_id)

    def get_user_by_login_name(self, login_name: str) -> UserRecord | None:
        name = (login_name or "").strip()
        for item in self._users.values():
            if item.login_name == name:
                return item
        return None

    def set_user_last_login(self, user_id: UUID, at: datetime | None = None) -> UserRecord:
        user = self._require_user(user_id)
        updated = replace(user, last_login_at=as_utc(at or utcnow()))
        self._users[user_id] = updated
        return updated

    def create_session(self, user_id: UUID, token_hash: str, expires_at: datetime) -> SessionRecord:
        self._require_user(user_id)
        if not token_hash:
            raise RepositoryError("token_hash is required")
        if any(item.token_hash == token_hash for item in self._sessions.values()):
            raise RepositoryError("token_hash already exists")
        record = SessionRecord(
            session_id=uuid4(),
            user_id=user_id,
            token_hash=token_hash,
            expires_at=as_utc(expires_at),
            created_at=utcnow(),
        )
        self._sessions[record.session_id] = record
        return record

    def get_session_by_token_hash(self, token_hash: str) -> SessionRecord | None:
        for item in self._sessions.values():
            if item.token_hash == token_hash:
                return item
        return None

    def delete_session(self, session_id: UUID) -> None:
        self._sessions.pop(session_id, None)

    def create_agent_instance(
        self,
        user_id: UUID,
        title: str,
        *,
        intro: str = "",
        avatar_uri: str | None = None,
        template_code: str = DOUYIN_OPS_TEMPLATE,
        agent_mode: str = "single",
        status: str = "active",
    ) -> AgentInstanceRecord:
        self._require_user(user_id)
        normalized = normalize_agent_title(title)
        require_template_code(template_code)
        require_value(agent_mode, AGENT_MODES, "agent_mode")
        require_value(status, INSTANCE_STATUSES, "instance status")
        self._assert_title_available(user_id, normalized)
        now = utcnow()
        record = AgentInstanceRecord(
            agent_instance_id=uuid4(),
            user_id=user_id,
            template_code=template_code,
            title=normalized,
            intro=intro or "",
            avatar_uri=avatar_uri,
            agent_mode=agent_mode,
            status=status,
            created_at=now,
            updated_at=now,
        )
        self._instances[record.agent_instance_id] = record
        return record

    def get_agent_instance(self, agent_instance_id: UUID) -> AgentInstanceRecord | None:
        return self._instances.get(agent_instance_id)

    def update_agent_instance(
        self,
        agent_instance_id: UUID,
        user_id: UUID,
        *,
        title: str | None | object = UNSET,
        intro: str | None | object = UNSET,
        avatar_uri: str | None | object = UNSET,
    ) -> AgentInstanceRecord:
        record = self._require_instance(agent_instance_id, user_id)
        changes: dict[str, Any] = {}
        if title is not UNSET:
            normalized = normalize_agent_title(str(title or ""))
            if normalized != record.title:
                self._assert_title_available(user_id, normalized, exclude=agent_instance_id)
            changes["title"] = normalized
        if intro is not UNSET:
            changes["intro"] = intro or ""
        if avatar_uri is not UNSET:
            changes["avatar_uri"] = avatar_uri
        if not changes:
            return record
        updated = replace(record, **changes, updated_at=utcnow())
        self._instances[agent_instance_id] = updated
        return updated

    def archive_agent_instance(self, agent_instance_id: UUID) -> AgentInstanceRecord:
        record = self._instances.get(agent_instance_id)
        if record is None:
            raise NotFoundError(f"agent instance not found: {agent_instance_id}")
        archived = replace(record, status="archived")
        self._instances[agent_instance_id] = archived
        return archived

    def bind_workflow(
        self,
        user_id: UUID,
        agent_instance_id: UUID,
        workflow_code: str = DEFAULT_WORKFLOW_CODE,
        *,
        enabled: bool = True,
    ) -> WorkflowBindingRecord:
        instance = self._require_instance(agent_instance_id, user_id)
        code = (workflow_code or "").strip()
        if not code:
            raise RepositoryError("workflow_code must not be blank")
        for binding in self._bindings.values():
            if binding.agent_instance_id == instance.agent_instance_id and binding.workflow_code == code:
                raise DuplicateBindingError(
                    f"workflow already bound: {instance.agent_instance_id} {code}"
                )
        record = WorkflowBindingRecord(
            id=uuid4(),
            user_id=user_id,
            agent_instance_id=instance.agent_instance_id,
            workflow_code=code,
            enabled=enabled,
            created_at=utcnow(),
        )
        self._bindings[record.id] = record
        return record

    def list_workflow_bindings(self, agent_instance_id: UUID) -> list[WorkflowBindingRecord]:
        records = [
            item for item in self._bindings.values() if item.agent_instance_id == agent_instance_id
        ]
        return sorted(records, key=lambda item: item.created_at)

    def create_job_definition(
        self,
        user_id: UUID,
        agent_instance_id: UUID,
        *,
        kind: str,
        cron: str,
        timezone: str = "Asia/Shanghai",
        payload: dict | None = None,
        require_approval: bool = False,
        enabled: bool = True,
    ) -> JobDefinitionRecord:
        instance = self._require_instance(agent_instance_id, user_id)
        if not kind:
            raise RepositoryError("job kind is required")
        now = utcnow()
        record = JobDefinitionRecord(
            job_id=uuid4(),
            user_id=user_id,
            agent_instance_id=instance.agent_instance_id,
            kind=kind,
            cron=cron,
            timezone=timezone or "Asia/Shanghai",
            enabled=enabled,
            require_approval=bool(require_approval),
            payload=dict(payload or {}),
            created_at=now,
            updated_at=now,
        )
        self._jobs[record.job_id] = record
        return record

    def create_job_run(
        self,
        job_id: UUID,
        scheduled_for: datetime,
        *,
        status: str = "scheduled",
        error: str | None = None,
    ) -> JobRunRecord:
        job = self._jobs.get(job_id)
        if job is None:
            raise NotFoundError(f"job definition not found: {job_id}")
        require_value(status, JOB_RUN_STATUSES, "job run status")
        stamp = as_utc(scheduled_for)
        for existing in self._job_runs.values():
            if existing.job_id == job_id and existing.scheduled_for == stamp:
                raise DuplicateJobRunError(
                    f"job run already exists for {job_id} at {stamp.isoformat()}"
                )
        record = JobRunRecord(
            job_run_id=uuid4(),
            job_id=job_id,
            user_id=job.user_id,
            agent_instance_id=job.agent_instance_id,
            scheduled_for=stamp,
            status=status,
            error=error,
            started_at=None,
            finished_at=None,
        )
        self._job_runs[record.job_run_id] = record
        return record

    def add_knowledge_document(
        self,
        user_id: UUID,
        agent_instance_id: UUID,
        *,
        title: str,
        filename: str,
        storage_uri: str,
        source: str,
        status: str = "uploaded",
    ) -> KnowledgeDocumentRecord:
        instance = self._require_instance(agent_instance_id, user_id)
        require_value(source, KNOWLEDGE_SOURCES, "knowledge source")
        require_value(status, KNOWLEDGE_STATUSES, "knowledge status")
        record = KnowledgeDocumentRecord(
            document_id=uuid4(),
            user_id=user_id,
            agent_instance_id=instance.agent_instance_id,
            title=title,
            filename=filename,
            storage_uri=storage_uri,
            source=source,
            status=status,
            created_at=utcnow(),
        )
        self._documents[record.document_id] = record
        return record

    def set_knowledge_document_status(
        self, document_id: UUID, status: str
    ) -> KnowledgeDocumentRecord:
        record = self._documents.get(document_id)
        if record is None:
            raise NotFoundError(f"knowledge document not found: {document_id}")
        require_value(status, KNOWLEDGE_STATUSES, "knowledge status")
        updated = replace(record, status=status)
        self._documents[document_id] = updated
        return updated

    def seed_knowledge_documents(
        self,
        user_id: UUID,
        agent_instance_id: UUID,
        documents: Sequence[KnowledgeSeed],
        write_store: Callable[[KnowledgeDocumentRecord], None] | None = None,
    ) -> list[KnowledgeDocumentRecord]:
        self._require_instance(agent_instance_id, user_id)
        seeded: list[KnowledgeDocumentRecord] = []
        for item in documents:
            record = self.add_knowledge_document(
                user_id,
                agent_instance_id,
                title=item.title,
                filename=item.filename,
                storage_uri=item.storage_uri,
                source=item.source,
                status="uploaded",
            )
            if write_store is None:
                seeded.append(record)
                continue
            try:
                write_store(record)
            except Exception:
                record = self.set_knowledge_document_status(record.document_id, "failed")
            else:
                record = self.set_knowledge_document_status(record.document_id, "ready")
            seeded.append(record)
        return seeded

    def list_knowledge_documents(self, agent_instance_id: UUID) -> list[KnowledgeDocumentRecord]:
        records = [
            item for item in self._documents.values() if item.agent_instance_id == agent_instance_id
        ]
        return sorted(records, key=lambda item: item.created_at)

    def create_app_thread(
        self,
        user_id: UUID,
        agent_instance_id: UUID,
        *,
        thread_id: str | None = None,
        title: str | None = None,
        status: str = "active",
    ) -> ThreadRecord:
        instance = self._require_instance(agent_instance_id, user_id)
        require_value(status, THREAD_STATUSES, "thread status")
        now = utcnow()
        record = ThreadRecord(
            thread_id=thread_id or str(uuid4()),
            user_id=user_id,
            agent_instance_id=instance.agent_instance_id,
            title=title,
            status=status,
            created_at=now,
            last_active_at=now,
        )
        if record.thread_id in self._threads:
            raise RepositoryError(f"thread already exists: {record.thread_id}")
        self._threads[record.thread_id] = record
        return record

    def get_app_thread(self, thread_id: str) -> ThreadRecord | None:
        return self._threads.get(thread_id)

    def get_latest_active_thread(self, user_id: UUID, agent_instance_id: UUID) -> ThreadRecord | None:
        records = [
            item
            for item in self._threads.values()
            if item.user_id == user_id
            and item.agent_instance_id == agent_instance_id
            and item.status == "active"
        ]
        if not records:
            return None
        return sorted(records, key=lambda item: (item.last_active_at, item.created_at), reverse=True)[0]

    def add_media_asset(
        self,
        user_id: UUID,
        agent_instance_id: UUID,
        *,
        kind: str,
        storage_uri: str,
        thread_id: str | None = None,
        storage_status: str = "stored",
    ) -> MediaAssetRecord:
        instance = self._require_instance(agent_instance_id, user_id)
        require_value(kind, MEDIA_KINDS, "media kind")
        require_value(storage_status, MEDIA_STORAGE_STATUSES, "media storage status")
        record = MediaAssetRecord(
            asset_id=uuid4(),
            user_id=user_id,
            agent_instance_id=instance.agent_instance_id,
            kind=kind,
            storage_uri=storage_uri,
            storage_status=storage_status,
            created_at=utcnow(),
            thread_id=thread_id,
        )
        self._media_assets[record.asset_id] = record
        return record

    def list_media_assets(self, agent_instance_id: UUID) -> list[MediaAssetRecord]:
        records = [
            item for item in self._media_assets.values() if item.agent_instance_id == agent_instance_id
        ]
        return sorted(records, key=lambda item: item.created_at)

    def list_agent_instances(
        self, user_id: UUID, *, include_archived: bool = False
    ) -> list[AgentInstanceRecord]:
        records = [item for item in self._instances.values() if item.user_id == user_id]
        if not include_archived:
            records = [item for item in records if item.status != "archived"]
        return sorted(records, key=lambda item: item.created_at)

    def _require_user(self, user_id: UUID) -> UserRecord:
        user = self._users.get(user_id)
        if user is None:
            raise NotFoundError(f"user not found: {user_id}")
        return user

    def _require_instance(self, agent_instance_id: UUID, user_id: UUID) -> AgentInstanceRecord:
        record = self._instances.get(agent_instance_id)
        if record is None or record.user_id != user_id:
            raise NotFoundError(f"agent instance not found: {agent_instance_id}")
        return record

    def _assert_title_available(
        self, user_id: UUID, title: str, *, exclude: UUID | None = None
    ) -> None:
        needle = title.lower()
        for record in self._instances.values():
            if exclude is not None and record.agent_instance_id == exclude:
                continue
            if (
                record.user_id == user_id
                and record.status != "archived"
                and record.title.lower() == needle
            ):
                raise DuplicateTitleError(f"title already in use: {title}")


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)