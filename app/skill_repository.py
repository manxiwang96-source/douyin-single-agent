from __future__ import annotations

from typing import Any
from uuid import UUID, NAMESPACE_URL, uuid4, uuid5

from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation
from psycopg.types.json import Jsonb

from app.repository import RepositoryError, utcnow
from app.skills import (
    AgentSkillRecord,
    InMemorySkillRepository,
    PublishedConfigNotFound,
    REQUIRED_CONFIG_TOOL_CODE,
    SkillArtifactRecord,
    SkillBindingRecord,
    SkillImportRecord,
    SkillNotFoundError,
    SkillRecord,
    _validate_agent_skill,
    normalize_enabled_tool_codes,
    normalize_knowledge_document_ids,
    prefer_required_config_tool,
)


class PostgresSkillRepository:
    """PostgreSQL persistence adapter for Skill/config state.

    It intentionally implements the same narrow repository surface consumed by
    ``SkillService``; existing business repository methods and LangGraph state
    remain independent.
    """

    def __init__(self, pool) -> None:
        self.pool = pool
        self._seed_platform_skills()

    def _fetch_all(self, sql: str, params=()):
        try:
            with self.pool.connection() as conn:
                result = conn.execute(sql, params)
                return list(result.fetchall()) if result is not None else []
        except (UniqueViolation, CheckViolation, ForeignKeyViolation) as exc:
            raise RepositoryError(str(exc)) from exc

    def _fetch_one(self, sql: str, params=(), *, missing_ok: bool = False):
        try:
            with self.pool.connection() as conn:
                result = conn.execute(sql, params)
                row = result.fetchone() if result is not None else None
        except (UniqueViolation, CheckViolation, ForeignKeyViolation) as exc:
            raise RepositoryError(str(exc)) from exc
        if row is None and not missing_ok:
            raise RepositoryError("expected a row from SQL")
        return row

    def _execute(self, sql: str, params=()) -> None:
        try:
            with self.pool.connection() as conn:
                conn.execute(sql, params)
        except (UniqueViolation, CheckViolation, ForeignKeyViolation) as exc:
            raise RepositoryError(str(exc)) from exc

    def _seed_platform_skills(self) -> None:
        seeds = InMemorySkillRepository()
        for item in seeds.list_skills():
            self._execute(
                """
                INSERT INTO skill_registry (
                    skill_id, owner_scope, owner_user_id, source_type, code, name,
                    description, trigger_description, instructions, source_uri,
                    source_ref, content_digest, risk_level, approval_mode,
                    execution_policy, status, version, created_at, updated_at
                ) VALUES (%s, 'platform', NULL, %s, %s, %s, %s, %s, %s, NULL,
                          %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (code) WHERE owner_scope = 'platform' DO UPDATE SET
                    name = EXCLUDED.name, description = EXCLUDED.description,
                    trigger_description = EXCLUDED.trigger_description, instructions = EXCLUDED.instructions,
                    source_ref = EXCLUDED.source_ref, content_digest = EXCLUDED.content_digest,
                    risk_level = EXCLUDED.risk_level, approval_mode = EXCLUDED.approval_mode,
                    execution_policy = EXCLUDED.execution_policy, status = EXCLUDED.status,
                    version = EXCLUDED.version, updated_at = EXCLUDED.updated_at
                """,
                (
                    uuid5(NAMESPACE_URL, f"agentdemo:platform-skill:{item.code}"), item.source_type, item.code, item.name,
                    item.description, item.trigger_description, item.instructions,
                    item.source_ref, item.content_digest, item.risk_level,
                    item.approval_mode, Jsonb(item.execution_policy), item.status,
                    item.version, item.created_at, item.updated_at,
                ),
            )

    def list_skills(self, *, user_id: UUID | None = None, include_platform: bool = True) -> list[SkillRecord]:
        if include_platform:
            rows = self._fetch_all(
                """
                SELECT * FROM skill_registry
                WHERE status = 'active' AND (
                    owner_scope = 'platform' OR (owner_scope = 'user' AND owner_user_id = %s)
                ) ORDER BY owner_scope, name
                """,
                (user_id,),
            )
        else:
            rows = self._fetch_all(
                """
                SELECT * FROM skill_registry
                WHERE status = 'active' AND owner_scope = 'user' AND owner_user_id = %s
                ORDER BY name
                """,
                (user_id,),
            )
        return [_skill_from_row(row) for row in rows]

    def get_skill(self, skill_id: UUID) -> SkillRecord:
        row = self._fetch_one("SELECT * FROM skill_registry WHERE skill_id = %s", (skill_id,), missing_ok=True)
        if row is None:
            raise SkillNotFoundError(f"skill not found: {skill_id}")
        return _skill_from_row(row)

    def find_skill_by_code(self, code: str, *, user_id: UUID | None = None) -> SkillRecord | None:
        row = self._fetch_one(
            """
            SELECT * FROM skill_registry
            WHERE code = %s AND status = 'active' AND (
                owner_scope = 'platform' OR (owner_scope = 'user' AND owner_user_id = %s)
            ) ORDER BY owner_scope LIMIT 1
            """,
            (code, user_id),
            missing_ok=True,
        )
        return None if row is None else _skill_from_row(row)

    def save_skill(self, record: SkillRecord) -> SkillRecord:
        self._execute(
            """
            INSERT INTO skill_registry (
                skill_id, owner_scope, owner_user_id, source_type, code, name,
                description, trigger_description, instructions, source_uri, source_ref,
                content_digest, risk_level, approval_mode, execution_policy, status,
                version, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (skill_id) DO UPDATE SET
                owner_scope = EXCLUDED.owner_scope,
                owner_user_id = EXCLUDED.owner_user_id,
                source_type = EXCLUDED.source_type,
                code = EXCLUDED.code,
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                trigger_description = EXCLUDED.trigger_description,
                instructions = EXCLUDED.instructions,
                source_uri = EXCLUDED.source_uri,
                source_ref = EXCLUDED.source_ref,
                content_digest = EXCLUDED.content_digest,
                risk_level = EXCLUDED.risk_level,
                approval_mode = EXCLUDED.approval_mode,
                execution_policy = EXCLUDED.execution_policy,
                status = EXCLUDED.status,
                version = EXCLUDED.version,
                updated_at = EXCLUDED.updated_at
            """,
            (
                record.skill_id, record.owner_scope, record.owner_user_id, record.source_type,
                record.code, record.name, record.description, record.trigger_description,
                record.instructions, record.source_uri, record.source_ref, record.content_digest,
                record.risk_level, record.approval_mode, Jsonb(record.execution_policy),
                record.status, record.version, record.created_at, record.updated_at,
            ),
        )
        return record

    def save_artifact(self, record: SkillArtifactRecord) -> SkillArtifactRecord:
        self._execute(
            """
            INSERT INTO skill_artifacts (
                artifact_id, skill_id, content_digest, storage_key, manifest,
                file_count, total_bytes, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (artifact_id) DO UPDATE SET
                manifest = EXCLUDED.manifest, file_count = EXCLUDED.file_count,
                total_bytes = EXCLUDED.total_bytes
            """,
            (
                record.artifact_id, record.skill_id, record.content_digest, record.storage_key,
                Jsonb(record.manifest), record.file_count, record.total_bytes, record.created_at,
            ),
        )
        return record

    def get_artifact_for_skill(self, skill_id: UUID) -> SkillArtifactRecord:
        row = self._fetch_one(
            "SELECT * FROM skill_artifacts WHERE skill_id = %s ORDER BY created_at DESC LIMIT 1",
            (skill_id,), missing_ok=True,
        )
        if row is None:
            raise SkillNotFoundError(f"skill artifact not found: {skill_id}")
        return SkillArtifactRecord(
            artifact_id=_as_uuid(row["artifact_id"]), skill_id=_as_uuid(row["skill_id"]),
            content_digest=row["content_digest"], storage_key=row["storage_key"],
            manifest=dict(row.get("manifest") or {}), file_count=int(row["file_count"]),
            total_bytes=int(row["total_bytes"]), created_at=row["created_at"],
        )

    def save_import(self, record: SkillImportRecord) -> SkillImportRecord:
        self._execute(
            """
            INSERT INTO skill_imports (
                import_id, user_id, target_agent_instance_id, source_uri, source_ref,
                skill_path, status, source_metadata, scan_report, content_digest,
                imported_skill_id, requested_at, completed_at, confirmed_by,
                failure_reason, quarantine_path, expires_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (import_id) DO UPDATE SET
                status = EXCLUDED.status, scan_report = EXCLUDED.scan_report,
                content_digest = EXCLUDED.content_digest, imported_skill_id = EXCLUDED.imported_skill_id,
                completed_at = EXCLUDED.completed_at, confirmed_by = EXCLUDED.confirmed_by,
                failure_reason = EXCLUDED.failure_reason, quarantine_path = EXCLUDED.quarantine_path,
                expires_at = EXCLUDED.expires_at
            """,
            (
                record.import_id, record.user_id, record.target_agent_instance_id,
                record.source_uri, record.source_ref, record.skill_path, record.status,
                Jsonb(record.source_metadata), Jsonb(record.scan_report), record.content_digest,
                record.imported_skill_id, record.requested_at, record.completed_at,
                record.confirmed_by, record.failure_reason, record.quarantine_path, record.expires_at,
            ),
        )
        return record

    def get_import(self, import_id: UUID) -> SkillImportRecord:
        row = self._fetch_one("SELECT * FROM skill_imports WHERE import_id = %s", (import_id,), missing_ok=True)
        if row is None:
            raise SkillNotFoundError(f"skill import not found: {import_id}")
        return _import_from_row(row)

    def list_imports(self, *, user_id: UUID | None = None) -> list[SkillImportRecord]:
        if user_id is None:
            rows = self._fetch_all("SELECT * FROM skill_imports ORDER BY requested_at DESC")
        else:
            rows = self._fetch_all("SELECT * FROM skill_imports WHERE user_id = %s ORDER BY requested_at DESC", (user_id,))
        return [_import_from_row(row) for row in rows]

    def unbind_skill_everywhere(self, skill_id: UUID) -> None:
        self._execute("DELETE FROM agent_config_skills WHERE skill_id = %s", (skill_id,))

    def bind_skill(self, record: SkillBindingRecord) -> SkillBindingRecord:
        self._execute(
            """
            INSERT INTO agent_config_skills (
                config_version_id, user_id, agent_instance_id, skill_id, priority, enabled
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (config_version_id, skill_id) DO UPDATE SET
                priority = EXCLUDED.priority, enabled = EXCLUDED.enabled
            """,
            (record.config_version_id, record.user_id, record.agent_instance_id, record.skill_id, record.priority, record.enabled),
        )
        return record

    def unbind_skill(self, config_version_id: UUID, skill_id: UUID) -> None:
        self._execute(
            "DELETE FROM agent_config_skills WHERE config_version_id = %s AND skill_id = %s",
            (config_version_id, skill_id),
        )

    def list_bindings(self, config_version_id: UUID) -> list[SkillBindingRecord]:
        rows = self._fetch_all(
            "SELECT * FROM agent_config_skills WHERE config_version_id = %s AND enabled = TRUE ORDER BY priority",
            (config_version_id,),
        )
        return [_binding_from_row(row) for row in rows]

    def ensure_draft(self, user_id: UUID, agent_instance_id: UUID) -> dict[str, Any]:
        row = self._fetch_one(
            "SELECT * FROM agent_config_versions WHERE user_id = %s AND agent_instance_id = %s AND status = 'draft' ORDER BY version_no DESC LIMIT 1",
            (user_id, agent_instance_id), missing_ok=True,
        )
        if row is None:
            now = utcnow()
            row = self._fetch_one(
                """
                INSERT INTO agent_config_versions (
                    config_version_id, user_id, agent_instance_id, version_no, status,
                    system_prompt, welcome_message, example_questions, enabled_tool_codes, workflow_codes, knowledge_document_ids,
                    created_at, updated_at
                ) VALUES (%s, %s, %s, 1, 'draft', '', '', %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (uuid4(), user_id, agent_instance_id, Jsonb([]), Jsonb([REQUIRED_CONFIG_TOOL_CODE]), Jsonb([]), Jsonb([]), now, now),
            )
            config = _config_from_row(row)
            self._replace_config_tools(config, [REQUIRED_CONFIG_TOOL_CODE])
            self._replace_config_knowledge_documents(config, [])
            return self._hydrate_config(config)
        return self._hydrate_config(_config_from_row(row))

    def get_effective_config(self, user_id: UUID, agent_instance_id: UUID, *, prefer_draft: bool = False) -> dict[str, Any]:
        if prefer_draft:
            row = self._fetch_one(
                "SELECT * FROM agent_config_versions WHERE user_id = %s AND agent_instance_id = %s AND status = 'draft' ORDER BY version_no DESC LIMIT 1",
                (user_id, agent_instance_id), missing_ok=True,
            )
            if row is None:
                return self.ensure_draft(user_id, agent_instance_id)
            return self._hydrate_config(_config_from_row(row))
        row = self._fetch_one(
            "SELECT * FROM agent_config_versions WHERE user_id = %s AND agent_instance_id = %s AND status = 'published' ORDER BY version_no DESC LIMIT 1",
            (user_id, agent_instance_id), missing_ok=True,
        )
        if row is None:
            raise PublishedConfigNotFound(f"published config not found for agent instance {agent_instance_id}")
        return self._hydrate_config(_config_from_row(row))

    def list_config_versions(self, user_id: UUID, agent_instance_id: UUID) -> list[dict[str, Any]]:
        rows = self._fetch_all(
            "SELECT * FROM agent_config_versions WHERE user_id = %s AND agent_instance_id = %s ORDER BY version_no DESC",
            (user_id, agent_instance_id),
        )
        return [self._hydrate_config(_config_from_row(row)) for row in rows]

    def get_config(self, config_version_id: UUID) -> dict[str, Any]:
        row = self._fetch_one("SELECT * FROM agent_config_versions WHERE config_version_id = %s", (config_version_id,), missing_ok=True)
        if row is None:
            raise RepositoryError(f"config version not found: {config_version_id}")
        return self._hydrate_config(_config_from_row(row))

    def update_config(self, config_version_id: UUID, **fields: Any) -> dict[str, Any]:
        allowed = {"system_prompt", "welcome_message", "example_questions", "enabled_tool_codes", "workflow_codes", "knowledge_document_ids"}
        values = {key: value for key, value in fields.items() if key in allowed}
        config = self.get_config(config_version_id)
        if not values:
            return config
        tool_codes = values.pop("enabled_tool_codes", None)
        document_ids = values.pop("knowledge_document_ids", None)
        if tool_codes is not None:
            self._replace_config_tools(config, tool_codes)
            values["enabled_tool_codes"] = list(config["enabled_tool_codes"])
        if document_ids is not None:
            self._replace_config_knowledge_documents(config, document_ids)
            values["knowledge_document_ids"] = [str(item) for item in config["knowledge_document_ids"]]
        if values:
            assignments = []
            params: list[Any] = []
            for key, value in values.items():
                assignments.append(f"{key} = %s")
                params.append(Jsonb(value) if key in {"example_questions", "enabled_tool_codes", "workflow_codes", "knowledge_document_ids"} else value)
            assignments.append("updated_at = %s")
            params.extend([utcnow(), config_version_id])
            self._execute(
                f"UPDATE agent_config_versions SET {', '.join(assignments)} WHERE config_version_id = %s",
                tuple(params),
            )
        return self.get_config(config_version_id)

    def publish_config(self, user_id: UUID, agent_instance_id: UUID) -> dict[str, Any]:
        draft = self.ensure_draft(user_id, agent_instance_id)
        published = self._fetch_one(
            "UPDATE agent_config_versions SET status = 'published', updated_at = %s WHERE config_version_id = %s RETURNING *",
            (utcnow(), draft["config_version_id"]),
        )
        now = utcnow()
        new_id = uuid4()
        self._execute(
            """
            INSERT INTO agent_config_versions (
                config_version_id, user_id, agent_instance_id, version_no, status,
                system_prompt, welcome_message, example_questions, enabled_tool_codes, workflow_codes, knowledge_document_ids,
                created_at, updated_at
            ) VALUES (%s, %s, %s, %s, 'draft', %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                new_id, user_id, agent_instance_id, draft["version_no"] + 1,
                published["system_prompt"], published["welcome_message"], Jsonb(published["example_questions"]),
                Jsonb(list(draft.get("enabled_tool_codes") or [])), Jsonb(published["workflow_codes"]),
                Jsonb([str(item) for item in (draft.get("knowledge_document_ids") or [])]), now, now,
            ),
        )
        self._copy_config_relations(draft["config_version_id"], new_id)
        return self._hydrate_config(_config_from_row(published))

    def _hydrate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        version_id = config["config_version_id"]
        tool_codes = self._list_config_tool_codes(version_id)
        if not tool_codes:
            jsonb_tools = normalize_enabled_tool_codes(config.get("enabled_tool_codes"))
            if jsonb_tools:
                self._replace_config_tools(config, jsonb_tools)
                self._mirror_config_jsonb(config)
                tool_codes = list(config["enabled_tool_codes"])
        if tool_codes:
            if REQUIRED_CONFIG_TOOL_CODE not in tool_codes:
                self._replace_config_tools(config, tool_codes)
                self._mirror_config_jsonb(config)
                tool_codes = list(config["enabled_tool_codes"])
            config["enabled_tool_codes"] = prefer_required_config_tool(tool_codes)
        else:
            config["enabled_tool_codes"] = []

        document_ids = self._list_config_knowledge_ids(version_id)
        if not document_ids:
            jsonb_docs = list(config.get("knowledge_document_ids") or [])
            if jsonb_docs:
                self._replace_config_knowledge_documents(config, jsonb_docs)
                self._mirror_config_jsonb(config)
                document_ids = list(config["knowledge_document_ids"])
        config["knowledge_document_ids"] = document_ids
        return config

    def _list_config_tool_codes(self, config_version_id: UUID) -> list[str]:
        rows = self._fetch_all(
            "SELECT tool_code FROM agent_config_tools WHERE config_version_id = %s AND enabled = TRUE ORDER BY created_at, tool_code",
            (config_version_id,),
        )
        codes: list[str] = []
        for row in rows:
            code = row["tool_code"]
            if code not in codes:
                codes.append(code)
        return prefer_required_config_tool(codes)

    def _list_config_knowledge_ids(self, config_version_id: UUID) -> list[UUID]:
        rows = self._fetch_all(
            "SELECT document_id FROM agent_config_knowledge_documents WHERE config_version_id = %s ORDER BY created_at, document_id",
            (config_version_id,),
        )
        ids: list[UUID] = []
        for row in rows:
            document_id = _as_uuid(row["document_id"])
            if document_id not in ids:
                ids.append(document_id)
        return ids

    def _replace_config_tools(self, config: dict[str, Any], tool_codes) -> None:
        version_id = config["config_version_id"]
        codes = normalize_enabled_tool_codes(tool_codes, require_datetime=True)
        self._execute("DELETE FROM agent_config_tools WHERE config_version_id = %s", (version_id,))
        now = utcnow()
        for code in codes:
            self._execute(
                """
                INSERT INTO agent_config_tools (
                    config_version_id, user_id, agent_instance_id, tool_code, enabled, created_at
                ) VALUES (%s, %s, %s, %s, TRUE, %s)
                ON CONFLICT (config_version_id, tool_code) DO UPDATE SET enabled = TRUE
                """,
                (version_id, config["user_id"], config["agent_instance_id"], code, now),
            )
        config["enabled_tool_codes"] = list(codes)

    def _replace_config_knowledge_documents(self, config: dict[str, Any], document_ids) -> None:
        version_id = config["config_version_id"]
        ids = normalize_knowledge_document_ids(document_ids)
        self._execute("DELETE FROM agent_config_knowledge_documents WHERE config_version_id = %s", (version_id,))
        now = utcnow()
        for document_id in ids:
            self._execute(
                """
                INSERT INTO agent_config_knowledge_documents (
                    config_version_id, user_id, agent_instance_id, document_id, created_at
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (config_version_id, document_id) DO NOTHING
                """,
                (version_id, config["user_id"], config["agent_instance_id"], document_id, now),
            )
        config["knowledge_document_ids"] = list(ids)

    def _copy_config_relations(self, source_version_id: UUID, target_version_id: UUID) -> None:
        now = utcnow()
        self._execute(
            """
            INSERT INTO agent_config_tools (
                config_version_id, user_id, agent_instance_id, tool_code, enabled, created_at
            )
            SELECT %s, user_id, agent_instance_id, tool_code, enabled, %s
            FROM agent_config_tools
            WHERE config_version_id = %s
            ON CONFLICT (config_version_id, tool_code) DO UPDATE SET enabled = EXCLUDED.enabled
            """,
            (target_version_id, now, source_version_id),
        )
        self._execute(
            """
            INSERT INTO agent_config_knowledge_documents (
                config_version_id, user_id, agent_instance_id, document_id, created_at
            )
            SELECT %s, user_id, agent_instance_id, document_id, %s
            FROM agent_config_knowledge_documents
            WHERE config_version_id = %s
            ON CONFLICT (config_version_id, document_id) DO NOTHING
            """,
            (target_version_id, now, source_version_id),
        )

    def _mirror_config_jsonb(self, config: dict[str, Any]) -> None:
        self._execute(
            """
            UPDATE agent_config_versions
            SET enabled_tool_codes = %s, knowledge_document_ids = %s, updated_at = %s
            WHERE config_version_id = %s
            """,
            (
                Jsonb(list(config.get("enabled_tool_codes") or [])),
                Jsonb([str(item) for item in (config.get("knowledge_document_ids") or [])]),
                utcnow(),
                config["config_version_id"],
            ),
        )

    def save_agent_skill(self, record: AgentSkillRecord) -> AgentSkillRecord:
        validated = _validate_agent_skill(record)
        self._execute(
            """
            INSERT INTO agent_skills (
                skill_id, user_id, agent_instance_id, name, description, instructions,
                risk_level, approval_mode, status, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (skill_id) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                instructions = EXCLUDED.instructions,
                risk_level = EXCLUDED.risk_level,
                approval_mode = EXCLUDED.approval_mode,
                status = EXCLUDED.status,
                updated_at = EXCLUDED.updated_at
            """,
            (
                validated.skill_id, validated.user_id, validated.agent_instance_id, validated.name,
                validated.description, validated.instructions, validated.risk_level, validated.approval_mode,
                validated.status, validated.created_at, validated.updated_at,
            ),
        )
        return validated

    def get_agent_skill(self, skill_id: UUID) -> AgentSkillRecord:
        row = self._fetch_one("SELECT * FROM agent_skills WHERE skill_id = %s", (skill_id,), missing_ok=True)
        if row is None:
            raise SkillNotFoundError(f"agent skill not found: {skill_id}")
        return _agent_skill_from_row(row)

    def list_agent_skills(
        self,
        user_id: UUID,
        agent_instance_id: UUID,
        *,
        include_archived: bool = False,
    ) -> list[AgentSkillRecord]:
        if include_archived:
            rows = self._fetch_all(
                """
                SELECT * FROM agent_skills
                WHERE user_id = %s AND agent_instance_id = %s
                ORDER BY created_at
                """,
                (user_id, agent_instance_id),
            )
        else:
            rows = self._fetch_all(
                """
                SELECT * FROM agent_skills
                WHERE user_id = %s AND agent_instance_id = %s AND status = 'active'
                ORDER BY created_at
                """,
                (user_id, agent_instance_id),
            )
        return [_agent_skill_from_row(row) for row in rows]

    def update_agent_skill(self, skill_id: UUID, **fields: Any) -> AgentSkillRecord:
        current = self.get_agent_skill(skill_id)
        allowed = {"name", "description", "instructions", "risk_level", "approval_mode", "status"}
        values = {key: value for key, value in fields.items() if key in allowed and value is not None}
        updated = AgentSkillRecord(
            skill_id=current.skill_id,
            user_id=current.user_id,
            agent_instance_id=current.agent_instance_id,
            name=values.get("name", current.name),
            description=values.get("description", current.description),
            instructions=values.get("instructions", current.instructions),
            risk_level=values.get("risk_level", current.risk_level),
            approval_mode=values.get("approval_mode", current.approval_mode),
            status=values.get("status", current.status),
            created_at=current.created_at,
            updated_at=utcnow(),
        )
        return self.save_agent_skill(updated)

    def archive_agent_skill(self, skill_id: UUID) -> AgentSkillRecord:
        return self.update_agent_skill(skill_id, status="archived")


def _as_uuid(value) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _skill_from_row(row) -> SkillRecord:
    return SkillRecord(
        skill_id=_as_uuid(row["skill_id"]), owner_scope=row["owner_scope"], owner_user_id=_as_uuid(row["owner_user_id"]) if row.get("owner_user_id") else None,
        source_type=row["source_type"], code=row["code"], name=row["name"], description=row["description"],
        trigger_description=row["trigger_description"], instructions=row["instructions"], source_uri=row.get("source_uri"),
        source_ref=row.get("source_ref"), content_digest=row["content_digest"], risk_level=row["risk_level"],
        approval_mode=row["approval_mode"], execution_policy=dict(row.get("execution_policy") or {}), status=row["status"],
        version=int(row["version"]), created_at=row["created_at"], updated_at=row["updated_at"],
    )


def _import_from_row(row) -> SkillImportRecord:
    return SkillImportRecord(
        import_id=_as_uuid(row["import_id"]), user_id=_as_uuid(row["user_id"]), target_agent_instance_id=_as_uuid(row["target_agent_instance_id"]),
        source_uri=row["source_uri"], source_ref=row.get("source_ref"), skill_path=row.get("skill_path"), status=row["status"],
        source_metadata=dict(row.get("source_metadata") or {}), scan_report=dict(row.get("scan_report") or {}), content_digest=row.get("content_digest"),
        imported_skill_id=_as_uuid(row["imported_skill_id"]) if row.get("imported_skill_id") else None, requested_at=row["requested_at"],
        completed_at=row.get("completed_at"), confirmed_by=_as_uuid(row["confirmed_by"]) if row.get("confirmed_by") else None,
        failure_reason=row.get("failure_reason") or "", quarantine_path=row.get("quarantine_path"),
        expires_at=row.get("expires_at"),
    )


def _binding_from_row(row) -> SkillBindingRecord:
    return SkillBindingRecord(
        config_version_id=_as_uuid(row["config_version_id"]), agent_instance_id=_as_uuid(row["agent_instance_id"]), user_id=_as_uuid(row["user_id"]),
        skill_id=_as_uuid(row["skill_id"]), priority=int(row["priority"]), enabled=bool(row["enabled"]),
    )


def _config_from_row(row) -> dict[str, Any]:
    return {
        "config_version_id": _as_uuid(row["config_version_id"]), "user_id": _as_uuid(row["user_id"]),
        "agent_instance_id": _as_uuid(row["agent_instance_id"]), "version_no": int(row["version_no"]),
        "status": row["status"], "system_prompt": row["system_prompt"], "welcome_message": row["welcome_message"],
        "example_questions": list(row.get("example_questions") or []), "enabled_tool_codes": list(row.get("enabled_tool_codes") or []),
        "workflow_codes": list(row.get("workflow_codes") or []), "knowledge_document_ids": list(row.get("knowledge_document_ids") or []), "created_at": row["created_at"], "updated_at": row["updated_at"],
    }


def _agent_skill_from_row(row) -> AgentSkillRecord:
    return AgentSkillRecord(
        skill_id=_as_uuid(row['skill_id']),
        user_id=_as_uuid(row['user_id']),
        agent_instance_id=_as_uuid(row['agent_instance_id']),
        name=row['name'],
        description=row.get('description') or '',
        instructions=row.get('instructions') or '',
        risk_level=row['risk_level'],
        approval_mode=row['approval_mode'],
        status=row['status'],
        created_at=row['created_at'],
        updated_at=row['updated_at'],
    )
