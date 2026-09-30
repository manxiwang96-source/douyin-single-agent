from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.embeddings import EmbeddingsAdapter, hashing_embed_documents
from app.postgres import make_postgres_memory, postgres_store_index
from app.schema import (
    PGVECTOR_MISSING_MESSAGE,
    apply_business_schema,
    ensure_pgvector_extension,
    iter_sql_statements,
    load_business_schema_sql,
)


REQUIRED_TABLES = [
    "app_users",
    "app_sessions",
    "agent_instances",
    "agent_instance_workflows",
    "app_threads",
    "douyin_accounts",
    "job_definitions",
    "job_runs",
    "workflow_runs",
    "engage_videos",
    "engage_comments",
    "engage_dms",
    "media_assets",
    "agent_knowledge_documents",
    "skill_registry",
    "skill_artifacts",
    "skill_imports",
    "agent_config_versions",
    "agent_config_skills",
    "agent_config_tools",
    "agent_config_knowledge_documents",
    "agent_skills",
    "thread_skill_approvals",
    "thread_action_approvals",
    "skill_script_execution_records",
]


def test_business_sql_locks_tables_and_constraints():
    sql = load_business_schema_sql()
    missing = [name for name in REQUIRED_TABLES if f"CREATE TABLE IF NOT EXISTS {name}" not in sql]
    assert missing == [], missing
    assert "UNIQUE (user_id, lower(title))" in sql
    assert "WHERE status <> 'archived'" in sql
    assert "title = btrim(title)" in sql
    assert "UNIQUE (agent_instance_id, workflow_code)" in sql
    assert "UNIQUE (job_id, scheduled_for)" in sql
    assert "token_hash TEXT NOT NULL UNIQUE" in sql
    assert "require_approval BOOLEAN NOT NULL DEFAULT false" in sql
    assert "'cancelled'" in sql
    assert "approved_reply" in sql
    lowered = sql.lower()
    assert "alter table checkpoints" not in lowered
    assert "alter table store" not in lowered
    assert "sqlite" not in lowered
    assert "CREATE TABLE IF NOT EXISTS agent_config_tools" in sql
    assert "CREATE TABLE IF NOT EXISTS agent_config_knowledge_documents" in sql
    assert "CREATE TABLE IF NOT EXISTS agent_skills" in sql
    assert "ALTER TABLE app_threads ADD COLUMN IF NOT EXISTS thread_kind TEXT NOT NULL DEFAULT 'official'" in sql
    assert "thread_kind IN ('debug', 'official')" in sql
    statements = iter_sql_statements(sql)
    assert len(statements) >= len(REQUIRED_TABLES)


def test_iter_sql_statements_does_not_split_on_semicolons_inside_dollar_quotes():
    script = """
    CREATE TABLE IF NOT EXISTS t (id INT);
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1) THEN
            ALTER TABLE t ADD CONSTRAINT t_fk FOREIGN KEY (id) REFERENCES t (id);
        END IF;
    END $$;
    CREATE INDEX IF NOT EXISTS t_idx ON t (id);
    """
    statements = iter_sql_statements(script)
    assert len(statements) == 3
    assert statements[0].startswith("CREATE TABLE IF NOT EXISTS t")
    assert statements[1].startswith("DO $$")
    assert "ALTER TABLE t ADD CONSTRAINT t_fk" in statements[1]
    assert "END $$" in statements[1]
    assert statements[2].startswith("CREATE INDEX IF NOT EXISTS t_idx")


def test_iter_sql_statements_keeps_business_dollar_quoted_blocks_intact():
    statements = iter_sql_statements(load_business_schema_sql())
    do_blocks = [item for item in statements if item.lstrip().startswith("DO $$")]
    assert len(do_blocks) == 3
    for block in do_blocks:
        assert block.count("$$") % 2 == 0
        assert "BEGIN" in block
        assert "END $$" in block
    fk_block = next(item for item in do_blocks if "app_threads_config_version_fk" in item)
    assert "FOREIGN KEY (config_version_id) REFERENCES agent_config_versions (config_version_id)" in fk_block
    assert "END IF" in fk_block
    kind_block = next(item for item in do_blocks if "app_threads_thread_kind_chk" in item)
    assert "CHECK (thread_kind IN ('debug', 'official'))" in kind_block
    assert "END IF" in kind_block
    unique_block = next(item for item in do_blocks if "thread_action_approvals_scope_unique" in item)
    assert "ADD CONSTRAINT thread_action_approvals_scope_unique" in unique_block
    assert "DROP CONSTRAINT thread_action_approvals_user_id_agent_instance_id_config_version_id_thread_id_approval_kind_resource_code_key" in unique_block


def test_approval_scope_column_is_added_before_unique_constraint():
    statements = iter_sql_statements(load_business_schema_sql())
    add_column = next(
        index for index, item in enumerate(statements)
        if item.startswith("ALTER TABLE thread_action_approvals ADD COLUMN IF NOT EXISTS approval_scope")
    )
    unique_upgrade = next(
        index for index, item in enumerate(statements)
        if item.lstrip().startswith("DO $$") and "thread_action_approvals_scope_unique" in item
    )
    assert add_column < unique_upgrade
    config_column = next(
        index for index, item in enumerate(statements)
        if item.startswith("ALTER TABLE app_threads ADD COLUMN IF NOT EXISTS config_version_id")
    )
    config_fk = next(
        index for index, item in enumerate(statements)
        if item.lstrip().startswith("DO $$") and "app_threads_config_version_fk" in item
    )
    assert config_column < config_fk
    thread_kind_column = next(
        index for index, item in enumerate(statements)
        if item.startswith("ALTER TABLE app_threads ADD COLUMN IF NOT EXISTS thread_kind")
    )
    thread_kind_chk = next(
        index for index, item in enumerate(statements)
        if item.lstrip().startswith("DO $$") and "app_threads_thread_kind_chk" in item
    )
    assert thread_kind_column < thread_kind_chk


def test_ensure_pgvector_extension_fails_with_clear_reason():
    conn = MagicMock()
    conn.execute.side_effect = RuntimeError("permission denied")
    with pytest.raises(RuntimeError, match="pgvector"):
        ensure_pgvector_extension(conn)


def test_ensure_pgvector_extension_fails_when_not_registered():
    conn = MagicMock()
    result = MagicMock()
    result.fetchone.return_value = None
    conn.execute.return_value = result
    with pytest.raises(RuntimeError, match="pgvector"):
        ensure_pgvector_extension(conn)
    assert PGVECTOR_MISSING_MESSAGE


def test_apply_business_schema_executes_create_table(monkeypatch):
    statements = []

    class _Conn:
        def execute(self, sql, params=None):
            statements.append(sql)

    apply_business_schema(_Conn())
    created = [item for item in statements if item.startswith("CREATE TABLE IF NOT EXISTS")]
    names = [REQUIRED_TABLES[0], REQUIRED_TABLES[-1], "job_runs", "agent_instance_workflows"]
    for name in names:
        assert any(name in item for item in created), name


class _ConnCM:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, *_args):
        return False


class _FakePool:
    def __init__(self, conn):
        self.conn = conn
        self.wait_called = False

    def wait(self, timeout=10):
        self.wait_called = True

    def connection(self):
        return _ConnCM(self.conn)


def test_make_postgres_memory_enables_pgvector_index_and_schema(monkeypatch):
    captured = []

    class _Conn:
        def execute(self, sql, params=None):
            captured.append(sql)
            result = MagicMock()
            if "pg_extension" in str(sql):
                result.fetchone.return_value = {"ok": 1}
            else:
                result.fetchone.return_value = None
            return result

    fake_pool = _FakePool(_Conn())
    store_calls = {}

    class _Saver:
        def __init__(self, pool):
            self.pool = pool

        def setup(self):
            captured.append("checkpointer.setup")

    class _Store:
        def __init__(self, pool, *, index=None):
            store_calls["index"] = index
            self.pool = pool

        def setup(self):
            captured.append("store.setup")

    embeddings = EmbeddingsAdapter(lambda texts: hashing_embed_documents(texts, 8))
    with (
        patch("app.postgres.ensure_postgres_database"),
        patch("app.postgres.ConnectionPool", return_value=fake_pool),
        patch("app.postgres.AppPostgresSaver", _Saver),
        patch("app.postgres.PostgresStore", _Store),
        patch("app.postgres.PostgresBusinessRepository", lambda pool: "pg-repo"),
    ):
        memory = make_postgres_memory(
            "postgresql://postgres@127.0.0.1:5432/agentdemo",
            embeddings=embeddings,
            embedding_dims=8,
        )
    assert fake_pool.wait_called
    assert any("CREATE EXTENSION IF NOT EXISTS vector" in str(item) for item in captured)
    assert any("CREATE TABLE IF NOT EXISTS app_users" in str(item) for item in captured)
    assert store_calls["index"]["dims"] == 8
    assert store_calls["index"]["fields"] == ["text"]
    assert memory.repository == "pg-repo"
    assert "sqlite" not in "".join(str(item).lower() for item in captured)


def test_postgres_store_index_requires_embeddings():
    with pytest.raises(RuntimeError, match="embeddings"):
        postgres_store_index(None, 1024)


def test_skill_schema_migration_is_idempotent_and_scoped():
    sql = load_business_schema_sql()
    statements = iter_sql_statements(sql)
    skill_statements = [
        statement for statement in statements
        if any(name in statement for name in (
            "skill_registry", "skill_artifacts", "skill_imports",
            "agent_config_versions", "agent_config_skills",
            "thread_skill_approvals", "thread_action_approvals", "skill_script_execution_records",
        ))
    ]
    assert skill_statements
    for statement in skill_statements:
        if statement.startswith("CREATE TABLE") or statement.startswith("CREATE INDEX"):
            assert "IF NOT EXISTS" in statement
    assert "source_ref TEXT NULL" in sql
    assert "content_digest TEXT NOT NULL" in sql
    assert "quarantine_path TEXT NULL" in sql
    assert "UNIQUE (agent_instance_id, version_no)" in sql
    assert "config_version_id UUID NOT NULL" in sql
    assert "ALTER TABLE agent_config_versions ADD COLUMN IF NOT EXISTS knowledge_document_ids JSONB NOT NULL DEFAULT '[]'::jsonb" in sql
    assert "ALTER TABLE app_threads ADD COLUMN IF NOT EXISTS config_version_id UUID NULL" in sql
    assert "app_threads_config_version_fk" in sql
    assert "app_threads_config_version_id_idx" in sql
    assert "approval_kind IN ('import', 'skill', 'script', 'tool')" in sql

    executed = []

    class _Conn:
        def execute(self, statement, params=None):
            executed.append(statement)

    conn = _Conn()
    apply_business_schema(conn)
    apply_business_schema(conn)
    assert len(executed) == len(statements) * 2
    assert all(item.strip() for item in executed)
