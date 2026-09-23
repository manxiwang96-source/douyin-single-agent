from __future__ import annotations

from datetime import datetime
from typing import Callable, Sequence
from uuid import UUID, uuid4

from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation
from psycopg.types.json import Jsonb

from app.repository import (
    ACCOUNT_STATUSES,
    DEFAULT_WORKFLOW_CODE,
    DOUYIN_OPS_TEMPLATE,
    DuplicateBindingError,
    DuplicateJobRunError,
    DuplicateLoginError,
    DuplicateTitleError,
    DouyinAccountRecord,
    JobDisabledError,
    ENGAGE_COMMENT_STATUSES,
    ENGAGE_DM_STATUSES,
    ENGAGE_VIDEO_STATUSES,
    EngageCommentRecord,
    EngageDmRecord,
    EngageVideoRecord,
    InvalidTitleError,
    JobDefinitionRecord,
    JobRunRecord,
    KnowledgeDocumentRecord,
    KnowledgeSeed,
    MediaAssetRecord,
    MEDIA_KINDS,
    MEDIA_STORAGE_STATUSES,
    NotFoundError,
    RepositoryError,
    SessionRecord,
    ThreadRecord,
    UNSET,
    UserRecord,
    WORKFLOW_RUN_STATUSES,
    WorkflowBindingRecord,
    WorkflowRunRecord,
    AgentInstanceRecord,
    normalize_agent_title,
    require_template_code,
    require_value,
    AGENT_MODES,
    INSTANCE_STATUSES,
    JOB_RUN_STATUSES,
    KNOWLEDGE_SOURCES,
    KNOWLEDGE_STATUSES,
    THREAD_STATUSES,
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

    def get_user_by_login_name(self, login_name: str) -> UserRecord | None:
        name = (login_name or "").strip()
        row = self._fetch_one(
            "SELECT * FROM app_users WHERE login_name = %s",
            (name,),
            missing_ok=True,
        )
        return None if row is None else _user_from_row(row)

    def set_user_last_login(self, user_id: UUID, at: datetime | None = None) -> UserRecord:
        row = self._fetch_one(
            """
            UPDATE app_users
            SET last_login_at = %s
            WHERE user_id = %s
            RETURNING *
            """,
            (as_utc(at or utcnow()), user_id),
            missing_ok=True,
        )
        if row is None:
            raise NotFoundError(f"user not found: {user_id}")
        return _user_from_row(row)

    def create_session(self, user_id: UUID, token_hash: str, expires_at: datetime) -> SessionRecord:
        if not token_hash:
            raise RepositoryError("token_hash is required")
        sql = """
            INSERT INTO app_sessions (session_id, user_id, token_hash, expires_at, created_at)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
        """
        row = self._fetch_one(
            sql,
            (uuid4(), user_id, token_hash, as_utc(expires_at), utcnow()),
        )
        return _session_from_row(row)

    def get_session_by_token_hash(self, token_hash: str) -> SessionRecord | None:
        row = self._fetch_one(
            "SELECT * FROM app_sessions WHERE token_hash = %s",
            (token_hash,),
            missing_ok=True,
        )
        return None if row is None else _session_from_row(row)

    def delete_session(self, session_id: UUID) -> None:
        self._execute("DELETE FROM app_sessions WHERE session_id = %s", (session_id,))

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

    def list_agent_instances(
        self, user_id: UUID, *, include_archived: bool = False
    ) -> list[AgentInstanceRecord]:
        if include_archived:
            sql = "SELECT * FROM agent_instances WHERE user_id = %s ORDER BY created_at"
            rows = self._fetch_all(sql, (user_id,))
        else:
            sql = """
                SELECT * FROM agent_instances
                WHERE user_id = %s AND status <> 'archived'
                ORDER BY created_at
            """
            rows = self._fetch_all(sql, (user_id,))
        return [_instance_from_row(row) for row in rows]

    def update_agent_instance(
        self,
        agent_instance_id: UUID,
        user_id: UUID,
        *,
        title: str | None | object = UNSET,
        intro: str | None | object = UNSET,
        avatar_uri: str | None | object = UNSET,
    ) -> AgentInstanceRecord:
        current = self.get_agent_instance(agent_instance_id)
        if current is None or current.user_id != user_id:
            raise NotFoundError(f"agent instance not found: {agent_instance_id}")
        new_title = current.title
        new_intro = current.intro
        new_avatar = current.avatar_uri
        if title is not UNSET:
            new_title = normalize_agent_title(str(title or ""))
        if intro is not UNSET:
            new_intro = intro or ""
        if avatar_uri is not UNSET:
            new_avatar = avatar_uri
        if new_title == current.title and new_intro == current.intro and new_avatar == current.avatar_uri:
            return current
        row = self._fetch_one(
            """
            UPDATE agent_instances
            SET title = %s, intro = %s, avatar_uri = %s, updated_at = %s
            WHERE agent_instance_id = %s AND user_id = %s
            RETURNING *
            """,
            (new_title, new_intro, new_avatar, utcnow(), agent_instance_id, user_id),
            missing_ok=True,
        )
        if row is None:
            raise NotFoundError(f"agent instance not found: {agent_instance_id}")
        return _instance_from_row(row)

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

    def list_workflow_bindings(self, agent_instance_id: UUID) -> list[WorkflowBindingRecord]:
        rows = self._fetch_all(
            """
            SELECT * FROM agent_instance_workflows
            WHERE agent_instance_id = %s
            ORDER BY created_at
            """,
            (agent_instance_id,),
        )
        return [_binding_from_row(row) for row in rows]

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
        if not job["enabled"]:
            raise JobDisabledError(f"job is disabled: {job_id}")
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

    def get_job_definition(self, job_id: UUID) -> JobDefinitionRecord | None:
        row = self._fetch_one(
            "SELECT * FROM job_definitions WHERE job_id = %s",
            (job_id,),
            missing_ok=True,
        )
        return _job_from_row(row) if row is not None else None

    def list_job_definitions(
        self,
        user_id: UUID,
        agent_instance_id: UUID | None = None,
    ) -> list[JobDefinitionRecord]:
        sql = "SELECT * FROM job_definitions WHERE user_id = %s"
        params: list = [user_id]
        if agent_instance_id is not None:
            sql += " AND agent_instance_id = %s"
            params.append(agent_instance_id)
        sql += " ORDER BY created_at ASC"
        rows = self._fetch_all(sql, tuple(params))
        return [_job_from_row(row) for row in rows]

    def set_job_enabled(self, job_id: UUID, enabled: bool) -> JobDefinitionRecord:
        row = self._fetch_one(
            """
            UPDATE job_definitions
            SET enabled = %s, updated_at = %s
            WHERE job_id = %s
            RETURNING *
            """,
            (bool(enabled), utcnow(), job_id),
            missing_ok=True,
        )
        if row is None:
            raise NotFoundError(f"job definition not found: {job_id}")
        return _job_from_row(row)

    def get_job_run(self, job_run_id: UUID) -> JobRunRecord | None:
        row = self._fetch_one(
            "SELECT * FROM job_runs WHERE job_run_id = %s",
            (job_run_id,),
            missing_ok=True,
        )
        return _job_run_from_row(row) if row is not None else None

    def list_job_runs(
        self,
        user_id: UUID,
        agent_instance_id: UUID | None = None,
        *,
        job_id: UUID | None = None,
    ) -> list[JobRunRecord]:
        sql = "SELECT * FROM job_runs WHERE user_id = %s"
        params: list = [user_id]
        if agent_instance_id is not None:
            sql += " AND agent_instance_id = %s"
            params.append(agent_instance_id)
        if job_id is not None:
            sql += " AND job_id = %s"
            params.append(job_id)
        sql += " ORDER BY scheduled_for ASC"
        rows = self._fetch_all(sql, tuple(params))
        return [_job_run_from_row(row) for row in rows]

    def update_job_run(
        self,
        job_run_id: UUID,
        *,
        status: str | None = None,
        error: str | None | object = UNSET,
        started_at: datetime | None | object = UNSET,
        finished_at: datetime | None | object = UNSET,
    ) -> JobRunRecord:
        current = self.get_job_run(job_run_id)
        if current is None:
            raise NotFoundError(f"job run not found: {job_run_id}")
        next_status = current.status if status is None else status
        require_value(next_status, JOB_RUN_STATUSES, "job run status")
        next_error = current.error if error is UNSET else error
        next_started = current.started_at if started_at is UNSET else started_at
        next_finished = current.finished_at if finished_at is UNSET else finished_at
        row = self._fetch_one(
            """
            UPDATE job_runs
            SET status = %s, error = %s, started_at = %s, finished_at = %s
            WHERE job_run_id = %s
            RETURNING *
            """,
            (next_status, next_error, next_started, next_finished, job_run_id),
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

    def list_knowledge_documents(self, agent_instance_id: UUID) -> list[KnowledgeDocumentRecord]:
        rows = self._fetch_all(
            """
            SELECT * FROM agent_knowledge_documents
            WHERE agent_instance_id = %s
            ORDER BY created_at
            """,
            (agent_instance_id,),
        )
        return [_document_from_row(row) for row in rows]

    def create_app_thread(
        self,
        user_id: UUID,
        agent_instance_id: UUID,
        *,
        thread_id: str | None = None,
        title: str | None = None,
        status: str = "active",
    ) -> ThreadRecord:
        require_value(status, THREAD_STATUSES, "thread status")
        now = utcnow()
        sql = """
            INSERT INTO app_threads (
                thread_id, user_id, agent_instance_id, title, status, created_at, last_active_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """
        row = self._fetch_one(
            sql,
            (thread_id or str(uuid4()), user_id, agent_instance_id, title, status, now, now),
        )
        return _thread_from_row(row)

    def get_app_thread(self, thread_id: str) -> ThreadRecord | None:
        row = self._fetch_one(
            "SELECT * FROM app_threads WHERE thread_id = %s",
            (thread_id,),
            missing_ok=True,
        )
        return None if row is None else _thread_from_row(row)

    def get_latest_active_thread(self, user_id: UUID, agent_instance_id: UUID) -> ThreadRecord | None:
        row = self._fetch_one(
            """
            SELECT * FROM app_threads
            WHERE user_id = %s AND agent_instance_id = %s AND status = 'active'
            ORDER BY last_active_at DESC, created_at DESC
            LIMIT 1
            """,
            (user_id, agent_instance_id),
            missing_ok=True,
        )
        return None if row is None else _thread_from_row(row)

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
        require_value(kind, MEDIA_KINDS, "media kind")
        require_value(storage_status, MEDIA_STORAGE_STATUSES, "media storage status")
        sql = """
            INSERT INTO media_assets (
                asset_id, user_id, agent_instance_id, thread_id, kind,
                storage_uri, storage_status, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """
        row = self._fetch_one(
            sql,
            (
                uuid4(),
                user_id,
                agent_instance_id,
                thread_id,
                kind,
                storage_uri,
                storage_status,
                utcnow(),
            ),
        )
        return _media_from_row(row)

    def list_media_assets(self, agent_instance_id: UUID) -> list[MediaAssetRecord]:
        rows = self._fetch_all(
            """
            SELECT * FROM media_assets
            WHERE agent_instance_id = %s
            ORDER BY created_at ASC
            """,
            (agent_instance_id,),
        )
        return [_media_from_row(row) for row in rows]

    def upsert_douyin_account(
        self,
        user_id: UUID,
        agent_instance_id: UUID,
        account: str,
        *,
        display_name: str | None = None,
        status: str = "active",
    ) -> DouyinAccountRecord:
        name = (account or "").strip()
        if not name:
            raise RepositoryError("account is required")
        require_value(status, ACCOUNT_STATUSES, "douyin account status")
        existing = self.get_douyin_account(user_id, agent_instance_id, name)
        now = utcnow()
        if existing is not None:
            row = self._fetch_one(
                """
                UPDATE douyin_accounts
                SET display_name = %s, status = %s, updated_at = %s
                WHERE account_id = %s
                RETURNING *
                """,
                (
                    display_name if display_name is not None else existing.display_name,
                    status,
                    now,
                    existing.account_id,
                ),
            )
            return _account_from_row(row)
        row = self._fetch_one(
            """
            INSERT INTO douyin_accounts (
                account_id, user_id, agent_instance_id, account, display_name, status, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (uuid4(), user_id, agent_instance_id, name, display_name, status, now),
        )
        return _account_from_row(row)

    def get_douyin_account(
        self, user_id: UUID, agent_instance_id: UUID, account: str
    ) -> DouyinAccountRecord | None:
        row = self._fetch_one(
            """
            SELECT * FROM douyin_accounts
            WHERE user_id = %s AND agent_instance_id = %s AND account = %s
            """,
            (user_id, agent_instance_id, (account or "").strip()),
            missing_ok=True,
        )
        return _account_from_row(row) if row is not None else None

    def list_douyin_accounts(self, user_id: UUID, agent_instance_id: UUID) -> list[DouyinAccountRecord]:
        rows = self._fetch_all(
            """
            SELECT * FROM douyin_accounts
            WHERE user_id = %s AND agent_instance_id = %s
            ORDER BY updated_at ASC
            """,
            (user_id, agent_instance_id),
        )
        return [_account_from_row(row) for row in rows]

    def create_workflow_run(
        self,
        user_id: UUID,
        agent_instance_id: UUID,
        *,
        workflow_code: str,
        inputs: dict | None = None,
        status: str = "running",
        thread_id: str | None = None,
        job_run_id: UUID | None = None,
        dify_app_id: str | None = None,
        outputs: dict | None = None,
        workflow_run_id: str | None = None,
        error: str | None = None,
    ) -> WorkflowRunRecord:
        require_value(status, WORKFLOW_RUN_STATUSES, "workflow run status")
        row = self._fetch_one(
            """
            INSERT INTO workflow_runs (
                id, user_id, agent_instance_id, workflow_code, dify_app_id, thread_id, job_run_id,
                inputs, outputs, workflow_run_id, status, error, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                uuid4(),
                user_id,
                agent_instance_id,
                workflow_code,
                dify_app_id,
                thread_id,
                job_run_id,
                Jsonb(inputs or {}),
                Jsonb(outputs) if outputs is not None else None,
                workflow_run_id,
                status,
                error,
                utcnow(),
            ),
        )
        return _workflow_run_from_row(row)

    def update_workflow_run(
        self,
        run_id: UUID,
        *,
        status: str | None = None,
        outputs: dict | None = None,
        error: str | None = None,
        workflow_run_id: str | None = None,
    ) -> WorkflowRunRecord:
        current = self._fetch_one(
            "SELECT * FROM workflow_runs WHERE id = %s",
            (run_id,),
            missing_ok=True,
        )
        if current is None:
            raise NotFoundError(f"workflow run not found: {run_id}")
        next_status = status if status is not None else current["status"]
        require_value(next_status, WORKFLOW_RUN_STATUSES, "workflow run status")
        next_outputs = outputs if outputs is not None else current.get("outputs")
        next_error = error if error is not None else current.get("error")
        next_workflow_run_id = (
            workflow_run_id if workflow_run_id is not None else current.get("workflow_run_id")
        )
        row = self._fetch_one(
            """
            UPDATE workflow_runs
            SET status = %s, outputs = %s, error = %s, workflow_run_id = %s
            WHERE id = %s
            RETURNING *
            """,
            (
                next_status,
                Jsonb(next_outputs) if next_outputs is not None else None,
                next_error,
                next_workflow_run_id,
                run_id,
            ),
        )
        return _workflow_run_from_row(row)

    def list_workflow_runs(
        self,
        user_id: UUID,
        agent_instance_id: UUID,
        *,
        status: str | None = None,
        since: datetime | None = None,
    ) -> list[WorkflowRunRecord]:
        sql = """
            SELECT * FROM workflow_runs
            WHERE user_id = %s AND agent_instance_id = %s
        """
        params: list = [user_id, agent_instance_id]
        if status is not None:
            sql += " AND status = %s"
            params.append(status)
        if since is not None:
            sql += " AND created_at >= %s"
            params.append(as_utc(since))
        sql += " ORDER BY created_at ASC"
        rows = self._fetch_all(sql, tuple(params))
        return [_workflow_run_from_row(row) for row in rows]

    def add_engage_video(
        self,
        user_id: UUID,
        agent_instance_id: UUID,
        *,
        platform_video_id: str,
        status: str,
        keyword: str | None = None,
        title: str | None = None,
        url: str | None = None,
        thread_id: str | None = None,
        job_run_id: UUID | None = None,
        workflow_run_id: str | None = None,
    ) -> EngageVideoRecord:
        require_value(status, ENGAGE_VIDEO_STATUSES, "engage video status")
        now = utcnow()
        row = self._fetch_one(
            """
            INSERT INTO engage_videos (
                id, user_id, agent_instance_id, job_run_id, thread_id, workflow_run_id,
                platform_video_id, keyword, title, url, status, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                uuid4(),
                user_id,
                agent_instance_id,
                job_run_id,
                thread_id,
                workflow_run_id,
                platform_video_id,
                keyword,
                title,
                url,
                status,
                now,
                now,
            ),
        )
        return _engage_video_from_row(row)

    def list_engage_videos(self, user_id: UUID, agent_instance_id: UUID) -> list[EngageVideoRecord]:
        rows = self._fetch_all(
            """
            SELECT * FROM engage_videos
            WHERE user_id = %s AND agent_instance_id = %s
            ORDER BY created_at ASC
            """,
            (user_id, agent_instance_id),
        )
        return [_engage_video_from_row(row) for row in rows]

    def add_engage_comment(
        self,
        user_id: UUID,
        agent_instance_id: UUID,
        *,
        platform_comment_id: str,
        video_id: str,
        status: str,
        source_text: str = "",
        candidate_reply: str | None = None,
        approved_reply: str | None = None,
        thread_id: str | None = None,
        workflow_run_id: str | None = None,
    ) -> EngageCommentRecord:
        require_value(status, ENGAGE_COMMENT_STATUSES, "engage comment status")
        now = utcnow()
        row = self._fetch_one(
            """
            INSERT INTO engage_comments (
                id, user_id, agent_instance_id, platform_comment_id, video_id, source_text,
                candidate_reply, approved_reply, status, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                uuid4(),
                user_id,
                agent_instance_id,
                platform_comment_id,
                video_id,
                source_text or "",
                candidate_reply,
                approved_reply,
                status,
                now,
                now,
            ),
        )
        return _engage_comment_from_row(row)

    def update_engage_comment(self, comment_id: UUID, *, status: str) -> EngageCommentRecord:
        require_value(status, ENGAGE_COMMENT_STATUSES, "engage comment status")
        row = self._fetch_one(
            """
            UPDATE engage_comments
            SET status = %s, updated_at = %s
            WHERE id = %s
            RETURNING *
            """,
            (status, utcnow(), comment_id),
            missing_ok=True,
        )
        if row is None:
            raise NotFoundError(f"engage comment not found: {comment_id}")
        return _engage_comment_from_row(row)

    def list_engage_comments(self, user_id: UUID, agent_instance_id: UUID) -> list[EngageCommentRecord]:
        rows = self._fetch_all(
            """
            SELECT * FROM engage_comments
            WHERE user_id = %s AND agent_instance_id = %s
            ORDER BY created_at ASC
            """,
            (user_id, agent_instance_id),
        )
        return [_engage_comment_from_row(row) for row in rows]

    def add_engage_dm(
        self,
        user_id: UUID,
        agent_instance_id: UUID,
        *,
        platform_message_id: str,
        video_id: str,
        status: str,
        source_text: str = "",
        candidate_reply: str | None = None,
        approved_reply: str | None = None,
        thread_id: str | None = None,
        workflow_run_id: str | None = None,
    ) -> EngageDmRecord:
        require_value(status, ENGAGE_DM_STATUSES, "engage dm status")
        now = utcnow()
        row = self._fetch_one(
            """
            INSERT INTO engage_dms (
                id, user_id, agent_instance_id, platform_message_id, video_id, source_text,
                candidate_reply, approved_reply, status, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                uuid4(),
                user_id,
                agent_instance_id,
                platform_message_id,
                video_id,
                source_text or "",
                candidate_reply,
                approved_reply,
                status,
                now,
                now,
            ),
        )
        return _engage_dm_from_row(row)

    def update_engage_dm(self, dm_id: UUID, *, status: str) -> EngageDmRecord:
        require_value(status, ENGAGE_DM_STATUSES, "engage dm status")
        row = self._fetch_one(
            """
            UPDATE engage_dms
            SET status = %s, updated_at = %s
            WHERE id = %s
            RETURNING *
            """,
            (status, utcnow(), dm_id),
            missing_ok=True,
        )
        if row is None:
            raise NotFoundError(f"engage dm not found: {dm_id}")
        return _engage_dm_from_row(row)

    def list_engage_dms(self, user_id: UUID, agent_instance_id: UUID) -> list[EngageDmRecord]:
        rows = self._fetch_all(
            """
            SELECT * FROM engage_dms
            WHERE user_id = %s AND agent_instance_id = %s
            ORDER BY created_at ASC
            """,
            (user_id, agent_instance_id),
        )
        return [_engage_dm_from_row(row) for row in rows]

    def _execute(self, sql: str, params=()) -> None:
        try:
            with self.pool.connection() as conn:
                conn.execute(sql, params)
        except UniqueViolation as exc:
            raise _map_unique_violation(exc) from exc
        except CheckViolation as exc:
            raise _map_check_violation(exc) from exc
        except ForeignKeyViolation as exc:
            raise NotFoundError(str(exc)) from exc

    def _fetch_all(self, sql: str, params=()):
        try:
            with self.pool.connection() as conn:
                result = conn.execute(sql, params)
                return list(result.fetchall()) if result is not None else []
        except UniqueViolation as exc:
            raise _map_unique_violation(exc) from exc
        except CheckViolation as exc:
            raise _map_check_violation(exc) from exc
        except ForeignKeyViolation as exc:
            raise NotFoundError(str(exc)) from exc

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


def _session_from_row(row) -> SessionRecord:
    return SessionRecord(
        session_id=_as_uuid(row["session_id"]),
        user_id=_as_uuid(row["user_id"]),
        token_hash=row["token_hash"],
        expires_at=row["expires_at"],
        created_at=row["created_at"],
    )


def _thread_from_row(row) -> ThreadRecord:
    return ThreadRecord(
        thread_id=str(row["thread_id"]),
        user_id=_as_uuid(row["user_id"]),
        agent_instance_id=_as_uuid(row["agent_instance_id"]),
        title=row.get("title"),
        status=row["status"],
        created_at=row["created_at"],
        last_active_at=row["last_active_at"],
    )


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


def _media_from_row(row) -> MediaAssetRecord:
    return MediaAssetRecord(
        asset_id=_as_uuid(row["asset_id"]),
        user_id=_as_uuid(row["user_id"]),
        agent_instance_id=_as_uuid(row["agent_instance_id"]),
        kind=row["kind"],
        storage_uri=row["storage_uri"],
        storage_status=row["storage_status"],
        created_at=row["created_at"],
        thread_id=row.get("thread_id"),
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
def _account_from_row(row) -> DouyinAccountRecord:
    return DouyinAccountRecord(
        account_id=_as_uuid(row["account_id"]),
        user_id=_as_uuid(row["user_id"]),
        agent_instance_id=_as_uuid(row["agent_instance_id"]),
        account=row["account"],
        display_name=row.get("display_name"),
        status=row["status"],
        updated_at=row["updated_at"],
    )


def _workflow_run_from_row(row) -> WorkflowRunRecord:
    inputs = row.get("inputs") or {}
    outputs = row.get("outputs")
    return WorkflowRunRecord(
        id=_as_uuid(row["id"]),
        user_id=_as_uuid(row["user_id"]),
        agent_instance_id=_as_uuid(row["agent_instance_id"]),
        workflow_code=row["workflow_code"],
        inputs=dict(inputs),
        status=row["status"],
        created_at=row["created_at"],
        dify_app_id=row.get("dify_app_id"),
        thread_id=row.get("thread_id"),
        job_run_id=_as_uuid(row["job_run_id"]) if row.get("job_run_id") else None,
        outputs=dict(outputs) if outputs is not None else None,
        workflow_run_id=row.get("workflow_run_id"),
        error=row.get("error"),
    )


def _engage_video_from_row(row) -> EngageVideoRecord:
    return EngageVideoRecord(
        id=_as_uuid(row["id"]),
        user_id=_as_uuid(row["user_id"]),
        agent_instance_id=_as_uuid(row["agent_instance_id"]),
        platform_video_id=row["platform_video_id"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        job_run_id=_as_uuid(row["job_run_id"]) if row.get("job_run_id") else None,
        thread_id=row.get("thread_id"),
        workflow_run_id=row.get("workflow_run_id"),
        keyword=row.get("keyword"),
        title=row.get("title"),
        url=row.get("url"),
    )


def _engage_comment_from_row(row) -> EngageCommentRecord:
    return EngageCommentRecord(
        id=_as_uuid(row["id"]),
        user_id=_as_uuid(row["user_id"]),
        agent_instance_id=_as_uuid(row["agent_instance_id"]),
        platform_comment_id=row["platform_comment_id"],
        video_id=row["video_id"],
        source_text=row.get("source_text") or "",
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        score=row.get("score"),
        candidate_reply=row.get("candidate_reply"),
        approved_reply=row.get("approved_reply"),
        require_approval=bool(row.get("require_approval") or False),
        attempt_count=int(row.get("attempt_count") or 0),
        verify_result=row.get("verify_result"),
        screenshot_uri=row.get("screenshot_uri"),
    )


def _engage_dm_from_row(row) -> EngageDmRecord:
    return EngageDmRecord(
        id=_as_uuid(row["id"]),
        user_id=_as_uuid(row["user_id"]),
        agent_instance_id=_as_uuid(row["agent_instance_id"]),
        platform_message_id=row["platform_message_id"],
        video_id=row["video_id"],
        source_text=row.get("source_text") or "",
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        score=row.get("score"),
        candidate_reply=row.get("candidate_reply"),
        approved_reply=row.get("approved_reply"),
        require_approval=bool(row.get("require_approval") or False),
        attempt_count=int(row.get("attempt_count") or 0),
        verify_result=row.get("verify_result"),
        screenshot_uri=row.get("screenshot_uri"),
    )
