from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.skill_repository import PostgresSkillRepository
from app.skills import AgentSkillRecord, REQUIRED_CONFIG_TOOL_CODE, utcnow


_RELATION_MARKERS = (
    "agent_config_tools",
    "agent_config_knowledge_documents",
    "agent_skills",
)


class _Result:
    def __init__(self, *, row=None, rows=None):
        self._row = row
        self._rows = list(rows or [])

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _Connection:
    def __init__(self, pool):
        self.pool = pool

    def execute(self, sql, params=()):
        self.pool.calls.append((sql, params))
        compact = " ".join(str(sql).split())
        skip_scripted = (
            any(marker in compact for marker in _RELATION_MARKERS)
            or "enabled_tool_codes = %s, knowledge_document_ids = %s" in compact
        )
        if skip_scripted:
            return _Result()
        if self.pool.responses:
            return self.pool.responses.pop(0)
        return _Result()


class _ConnectionContext:
    def __init__(self, pool):
        self.pool = pool

    def __enter__(self):
        return _Connection(self.pool)

    def __exit__(self, *_args):
        return False


class _Pool:
    def __init__(self):
        self.calls = []
        self.responses = []

    def connection(self):
        return _ConnectionContext(self)


def _sql_calls(pool: _Pool, fragment: str):
    return [(sql, params) for sql, params in pool.calls if fragment in sql]


def _config_row(*, user_id: UUID, agent_id: UUID, status: str = "draft", version_no: int = 1):
    now = datetime.now(timezone.utc)
    return {
        "config_version_id": uuid4(),
        "user_id": user_id,
        "agent_instance_id": agent_id,
        "version_no": version_no,
        "status": status,
        "system_prompt": "",
        "welcome_message": "",
        "example_questions": [],
        "enabled_tool_codes": ["get_current_datetime"],
        "workflow_codes": [],
        "created_at": now,
        "updated_at": now,
    }


def test_platform_seed_is_deterministic_and_upserted():
    first_pool = _Pool()
    second_pool = _Pool()
    PostgresSkillRepository(first_pool)
    PostgresSkillRepository(second_pool)

    first_seed = [call for call in first_pool.calls if "INSERT INTO skill_registry" in call[0]]
    second_seed = [call for call in second_pool.calls if "INSERT INTO skill_registry" in call[0]]
    assert len(first_seed) == len(second_seed) == 4
    assert all("ON CONFLICT (code) WHERE owner_scope = 'platform'" in sql for sql, _ in first_seed)
    assert [params[0] for _, params in first_seed] == [params[0] for _, params in second_seed]
    assert [params[2] for _, params in first_seed] == [params[2] for _, params in second_seed]


def test_skill_query_keeps_user_scope_parameterized():
    pool = _Pool()
    repository = PostgresSkillRepository(pool)
    user_id = uuid4()
    skill_id = uuid4()
    now = datetime.now(timezone.utc)
    pool.responses.append(_Result(rows=[{
        "skill_id": skill_id,
        "owner_scope": "user",
        "owner_user_id": user_id,
        "source_type": "external",
        "code": "private-skill",
        "name": "Private",
        "description": "",
        "trigger_description": "",
        "instructions": "safe",
        "source_uri": "file:///tmp/private",
        "source_ref": "immutable-ref",
        "content_digest": "sha256:abc",
        "risk_level": "low",
        "approval_mode": "once",
        "execution_policy": {"network": False},
        "status": "active",
        "version": 1,
        "created_at": now,
        "updated_at": now,
    }]))

    result = repository.list_skills(user_id=user_id, include_platform=False)
    assert [item.skill_id for item in result] == [skill_id]
    sql, params = pool.calls[-1]
    assert "owner_scope = 'user'" in sql
    assert params == (user_id,)


def test_config_draft_creation_and_publish_preserve_three_part_scope():
    pool = _Pool()
    repository = PostgresSkillRepository(pool)
    user_id, agent_id = uuid4(), uuid4()

    created = _config_row(user_id=user_id, agent_id=agent_id)
    pool.responses.extend([_Result(row=None), _Result(row=created)])
    draft = repository.ensure_draft(user_id, agent_id)
    assert draft["user_id"] == user_id
    assert draft["agent_instance_id"] == agent_id
    assert draft["enabled_tool_codes"] == [REQUIRED_CONFIG_TOOL_CODE]

    select_calls = _sql_calls(pool, "FROM agent_config_versions WHERE user_id = %s AND agent_instance_id = %s AND status = 'draft'")
    assert select_calls
    assert select_calls[0][1] == (user_id, agent_id)

    version_inserts = _sql_calls(pool, "INSERT INTO agent_config_versions")
    assert version_inserts
    insert_sql, insert_params = version_inserts[0]
    assert "INSERT INTO agent_config_versions" in insert_sql
    assert insert_params[1:3] == (user_id, agent_id)

    tool_inserts = _sql_calls(pool, "INSERT INTO agent_config_tools")
    assert tool_inserts
    assert any(params[3] == REQUIRED_CONFIG_TOOL_CODE for _, params in tool_inserts if len(params) >= 4)

    published = {**created, "status": "published"}
    calls_before_publish = len(pool.calls)
    pool.responses.extend([_Result(row=created), _Result(row=published)])
    result = repository.publish_config(user_id, agent_id)
    assert result["status"] == "published"
    assert result["user_id"] == user_id
    assert result["agent_instance_id"] == agent_id

    publish_calls = pool.calls[calls_before_publish:]
    publish_insert = next((params for sql, params in publish_calls if "INSERT INTO agent_config_versions" in sql), None)
    assert publish_insert is not None
    assert publish_insert[1:3] == (user_id, agent_id)
    assert publish_insert[3] == created["version_no"] + 1
    assert any("INSERT INTO agent_config_tools" in sql for sql, _ in publish_calls)
    assert any("INSERT INTO agent_config_knowledge_documents" in sql for sql, _ in publish_calls)


def test_agent_skill_sql_uses_agent_skills_table():
    pool = _Pool()
    repository = PostgresSkillRepository(pool)
    user_id, agent_id = uuid4(), uuid4()
    now = utcnow()
    record = AgentSkillRecord(
        skill_id=uuid4(),
        user_id=user_id,
        agent_instance_id=agent_id,
        name="helper",
        description="desc",
        instructions="do it",
        risk_level="low",
        approval_mode="auto",
        status="active",
        created_at=now,
        updated_at=now,
    )
    saved = repository.save_agent_skill(record)
    assert saved.name == "helper"
    insert_calls = _sql_calls(pool, "INSERT INTO agent_skills")
    assert insert_calls
    assert insert_calls[-1][1][0] == record.skill_id
    assert insert_calls[-1][1][1:3] == (user_id, agent_id)


def test_save_skill_upserts_skill_registry():
    from app.skills import SkillRecord

    pool = _Pool()
    repository = PostgresSkillRepository(pool)
    now = utcnow()
    record = SkillRecord(
        skill_id=uuid4(),
        owner_scope="user",
        owner_user_id=uuid4(),
        source_type="custom",
        code="custom-skill",
        name="helper",
        description="",
        trigger_description="helper",
        instructions="do it",
        source_uri=None,
        source_ref="custom",
        content_digest="abc",
        risk_level="low",
        approval_mode="auto",
        execution_policy={"network": False},
        status="active",
        version=1,
        created_at=now,
        updated_at=now,
    )
    saved = repository.save_skill(record)
    assert saved.source_type == "custom"
    inserts = _sql_calls(pool, "INSERT INTO skill_registry")
    assert inserts
    sql, params = inserts[-1]
    assert "ON CONFLICT (skill_id) DO UPDATE SET" in sql
    assert params[0] == record.skill_id
    assert params[1:4] == ("user", record.owner_user_id, "custom")
