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
    statements = iter_sql_statements(sql)
    assert len(statements) >= len(REQUIRED_TABLES)


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
