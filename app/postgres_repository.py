from __future__ import annotations

from datetime import datetime
from typing import Callable, Sequence
from uuid import UUID, uuid4

from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation
from psycopg.types.json import Jsonb

from app.repository import (
    DEFAULT_WORKFLOW_CODE,
    DOUYIN_OPS_TEMPLATE,
    DuplicateBindingError,
    DuplicateJobRunError,
    DuplicateLoginError,
    DuplicateTitleError,
    InvalidTitleError,
    JobDefinitionRecord,
    JobRunRecord,
    KnowledgeDocumentRecord,
    KnowledgeSeed,
    NotFoundError,
    RepositoryError,
    UserRecord,
    WorkflowBindingRecord,
    AgentInstanceRecord,
    normalize_agent_title,
    require_template_code,
    require_value,
    AGENT_MODES,
    INSTANCE_STATUSES,
    JOB_RUN_STATUSES,
    KNOWLEDGE_SOURCES,
    KNOWLEDGE_STATUSES,
    USER_STATUSES,
    utcnow,
    as_utc,
)


class PostgresBusinessRepository:
    """Production repository backed by psycopg. Not used by default pytest."""

    def __init__(self, pool) -> None:
        self.pool = pool

    def create_user(self, login_name: str, password_hash: str, *, status: str = "active") -> UserRecord:
        name = (login_name or "").strip()
        if not name:
            raise RepositoryError("login_name must not be blank")
        if not password_hash:
            raise RepositoryError("password_hash is required")
        require_value(status, USER_STATUSES, "user status")
        record = UserRecord(
            user_id=uuid4(),
            login_name=name,
            password_hash=password_hash,
            status=status,
            created_at=utcnow(),
        )
        sql = """
            INSERT INTO app_users (user_id, login_name, password_hash, status, created_at, last_login_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
        """
        row = self._fetch_one(
            sql,
            (
                record.user_id,
                record.login_name,
                record.password_hash,
                record.status,
                record.created_at,
                record.last_login_at,
            ),
        )
        return _user_from_row(row)

    def get_user(self, user_id: UUID) -> UserRecord | None:
        row = self._fetch_one("SELECT * FROM app_users WHERE user_id = %s", (user_id,), missing_ok=True)
        return None if row is None else _user_from_row(row)

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
        normalized = normalize_agent_title(title)
        require_template_code(template_code)
        require_value(agent_mode, AGENT_MODES, "agent_mode")
        require_value(status, INSTANCE_STATUSES, "instance status")
        now = utcnow()
        sql = """
            INSERT INTO agent_instances (
                agent_instance_id, user_id, template_code, title, intro, avatar_uri,
                agent_mode, status, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """
        row = self._fetch_one(
            sql,
            (
                uuid4(),
                user_id,
                template_code,
                normalized,
                intro or "",
                avatar_uri,
                agent_mode,
                status,
                now,
                now,
            ),
        )
        return _instance_from_row(row)

    def get_agent_instance(self, agent_instance_id: UUID) -> AgentInstanceRecord | None:
        row = self._fetch_one(
            "SELECT * FROM agent_instances WHERE agent_instance_id = %s",
            (agent_instance_id,),
            missing_ok=True,
        )
        return None if row is None else _instance_from_row(row)

    def archive_agent_instance(self, agent_instance_id: UUID) -> AgentInstanceRecord:
        row = self._fetch_one(
            """
            UPDATE agent_instances
            SET status = 'archived'
            WHERE agent_instance_id = %s
            RETURNING *
            """,
            (agent_instance_id,),
            missing_ok=True,
        )
        if row is None:
            raise NotFoundError(f"agent instance not found: {agent_instance_id}")
        return _instance_from_row(row)

    def bind_workflow(
        self,
        user_id: UUID,
        agent_instance_id: UUID,
        workflow_code: str = DEFAULT_WORKFLOW_CODE,
        *,
        enabled: bool = True,
    ) -> WorkflowBindingRecord:
        code = (workflow_code or "").strip()
        if not code:
            raise RepositoryError("workflow_code must not be blank")
        sql = """
            INSERT INTO agent_instance_workflows (
                id, user_id, agent_instance_id, workflow_code, enabled, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
        """
        row = self._fetch_one(
            sql,
            (uuid4(), user_id, agent_instance_id, code, enabled, utcnow()),
        )
        return _binding_from_row(row)

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
        if not kind:
            raise RepositoryError("job kind is required")
        now = utcnow()
        sql = """
            INSERT INTO job_definitions (
                job_id, user_id, agent_instance_id, kind, cron, timezone,
                enabled, require_approval, payload, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """
        row = self._fetch_one(
            sql,
            (
                uuid4(),
                user_id,
                agent_instance_id,
                kind,
                cron,
                timezone or "Asia/Shanghai",
                enabled,
                bool(require_approval),
                Jsonb(payload or {}),
                now,
                now,
            ),
        )
        return _job_from_row(row)

    def create_job_run(
        self,
        job_id: UUID,
        scheduled_for: datetime,
        *,
        status: str = "scheduled",
        error: str | None = None,
    ) -> JobRunRecord:
        require_value(status, JOB_RUN_STATUSES, "job run status")
        job = self._fetch_one(
            "SELECT * FROM job_definitions WHERE job_id = %s",
            (job_id,),
            missing_ok=True,
        )
        if job is None:
            raise NotFoundError(f"job definition not found: {job_id}")
        stamp = as_utc(scheduled_for)
        sql = """
            INSERT INTO job_runs (
                job_run_id, job_id, user_id, agent_instance_id, scheduled_for,
                status, error, started_at, finished_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """
        row = self._fetch_one(
            sql,
            (
                uuid4(),
                job_id,
                job["user_id"],
                job["agent_instance_id"],
                stamp,
                status,
                error,
                None,
                None,
            ),
        )
        return _job_run_from_row(row)

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
        require_value(source, KNOWLEDGE_SOURCES, "knowledge source")
        require_value(status, KNOWLEDGE_STATUSES, "knowledge status")
        sql = """
            INSERT INTO agent_knowledge_documents (
                document_id, user_id, agent_instance_id, title, filename,
                storage_uri, source, status, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """
        row = self._fetch_one(
            sql,
            (
                uuid4(),
                user_id,
                agent_instance_id,
                title,
                filename,
                storage_uri,
                source,
                status,
                utcnow(),
            ),
        )
        return _document_from_row(row)

    def set_knowledge_document_status(
        self, document_id: UUID, status: str
    ) -> KnowledgeDocumentRecord:
        require_value(status, KNOWLEDGE_STATUSES, "knowledge status")
        row = self._fetch_one(
            """
            UPDATE agent_knowledge_documents
            SET status = %s
            WHERE document_id = %s
            RETURNING *
            """,
            (status, document_id),
            missing_ok=True,
        )
        if row is None:
            raise NotFoundError(f"knowledge document not found: {document_id}")
        return _document_from_row(row)

    def seed_knowledge_documents(
        self,
        user_id: UUID,
        agent_instance_id: UUID,
        documents: Sequence[KnowledgeSeed],
        write_store: Callable[[KnowledgeDocumentRecord], None] | None = None,
    ) -> list[KnowledgeDocumentRecord]:
        if self.get_agent_instance(agent_instance_id) is None:
            raise NotFoundError(f"agent instance not found: {agent_instance_id}")
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

    def _fetch_one(self, sql: str, params=(), *, missing_ok: bool = False):
        try:
            with self.pool.connection() as conn:
                result = conn.execute(sql, params)
                row = result.fetchone() if result is not None and hasattr(result, "fetchone") else None
        except UniqueViolation as exc:
            raise _map_unique_violation(exc) from exc
        except CheckViolation as exc:
            raise _map_check_violation(exc) from exc
        except ForeignKeyViolation as exc:
            raise NotFoundError(str(exc)) from exc
        if row is None and not missing_ok:
            raise RepositoryError("expected a row from SQL")
        return row


def _map_unique_violation(exc: UniqueViolation) -> RepositoryError:
    text = str(exc).lower()
    if "agent_instances_user_id_lower_title_active_uidx" in text or "lower(title)" in text:
        return DuplicateTitleError("title already in use")
    if "agent_instance_workflows_instance_code_uidx" in text:
        return DuplicateBindingError("workflow already bound")
    if "job_runs_job_id_scheduled_for_uidx" in text:
        return DuplicateJobRunError("job run already exists for scheduled_for")
    if "app_users" in text and "login_name" in text:
        return DuplicateLoginError("login_name already exists")
    return RepositoryError(str(exc))


def _map_check_violation(exc: CheckViolation) -> RepositoryError:
    text = str(exc).lower()
    if "agent_instances_title_chk" in text or "title" in text:
        return InvalidTitleError("title must not be blank or contain whitespace")
    return RepositoryError(str(exc))


def _as_uuid(value) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _user_from_row(row) -> UserRecord:
    return UserRecord(
        user_id=_as_uuid(row["user_id"]),
        login_name=row["login_name"],
        password_hash=row["password_hash"],
        status=row["status"],
        created_at=row["created_at"],
        last_login_at=row.get("last_login_at"),
    )


def _instance_from_row(row) -> AgentInstanceRecord:
    return AgentInstanceRecord(
        agent_instance_id=_as_uuid(row["agent_instance_id"]),
        user_id=_as_uuid(row["user_id"]),
        template_code=row["template_code"],
        title=row["title"],
        intro=row["intro"],
        avatar_uri=row.get("avatar_uri"),
        agent_mode=row["agent_mode"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _binding_from_row(row) -> WorkflowBindingRecord:
    return WorkflowBindingRecord(
        id=_as_uuid(row["id"]),
        user_id=_as_uuid(row["user_id"]),
        agent_instance_id=_as_uuid(row["agent_instance_id"]),
        workflow_code=row["workflow_code"],
        enabled=bool(row["enabled"]),
        created_at=row["created_at"],
    )


def _job_from_row(row) -> JobDefinitionRecord:
    payload = row.get("payload") or {}
    return JobDefinitionRecord(
        job_id=_as_uuid(row["job_id"]),
        user_id=_as_uuid(row["user_id"]),
        agent_instance_id=_as_uuid(row["agent_instance_id"]),
        kind=row["kind"],
        cron=row["cron"],
        timezone=row["timezone"],
        enabled=bool(row["enabled"]),
        require_approval=bool(row["require_approval"]),
        payload=dict(payload),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _job_run_from_row(row) -> JobRunRecord:
    return JobRunRecord(
        job_run_id=_as_uuid(row["job_run_id"]),
        job_id=_as_uuid(row["job_id"]),
        user_id=_as_uuid(row["user_id"]),
        agent_instance_id=_as_uuid(row["agent_instance_id"]),
        scheduled_for=row["scheduled_for"],
        status=row["status"],
        error=row.get("error"),
        started_at=row.get("started_at"),
        finished_at=row.get("finished_at"),
    )


def _document_from_row(row) -> KnowledgeDocumentRecord:
    return KnowledgeDocumentRecord(
        document_id=_as_uuid(row["document_id"]),
        user_id=_as_uuid(row["user_id"]),
        agent_instance_id=_as_uuid(row["agent_instance_id"]),
        title=row["title"],
        filename=row["filename"],
        storage_uri=row["storage_uri"],
        source=row["source"],
        status=row["status"],
        created_at=row["created_at"],
    )