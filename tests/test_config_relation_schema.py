from __future__ import annotations

from app.schema import apply_business_schema, iter_sql_statements, load_business_schema_sql


RELATION_TABLES = [
    "agent_config_tools",
    "agent_config_knowledge_documents",
    "agent_skills",
]


def test_config_relation_tables_and_thread_kind_are_idempotent():
    sql = load_business_schema_sql()
    statements = iter_sql_statements(sql)
    for name in RELATION_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {name}" in sql
    create_statements = [
        item for item in statements
        if item.startswith("CREATE TABLE IF NOT EXISTS") and any(name in item for name in RELATION_TABLES)
    ]
    index_statements = [
        item for item in statements
        if item.startswith("CREATE INDEX IF NOT EXISTS") and any(name in item for name in RELATION_TABLES)
    ]
    assert len(create_statements) == 3
    assert len(index_statements) == 3
    for statement in create_statements + index_statements:
        assert "IF NOT EXISTS" in statement

    assert "PRIMARY KEY (config_version_id, tool_code)" in sql
    assert "PRIMARY KEY (config_version_id, document_id)" in sql
    assert "skill_id UUID PRIMARY KEY" in sql
    assert "CREATE INDEX IF NOT EXISTS agent_config_tools_instance_idx" in sql
    assert "CREATE INDEX IF NOT EXISTS agent_config_knowledge_documents_instance_idx" in sql
    assert "CREATE INDEX IF NOT EXISTS agent_skills_owner_idx" in sql
    assert "REFERENCES agent_knowledge_documents (document_id)" in sql
    assert "CONSTRAINT agent_skills_risk_chk CHECK (risk_level IN ('low', 'medium', 'high'))" in sql
    assert "CONSTRAINT agent_skills_approval_chk CHECK (approval_mode IN ('auto', 'once', 'session', 'always'))" in sql
    assert "CONSTRAINT agent_skills_status_chk CHECK (status IN ('active', 'archived'))" in sql

    assert "ALTER TABLE app_threads ADD COLUMN IF NOT EXISTS thread_kind TEXT NOT NULL DEFAULT 'official'" in sql
    assert "thread_kind" in sql
    assert "'debug'" in sql
    assert "'official'" in sql
    assert "CHECK (thread_kind IN ('debug', 'official'))" in sql
    assert "app_threads_thread_kind_chk" in sql

    # JSONB cache columns remain; this window must not drop them.
    assert "enabled_tool_codes JSONB NOT NULL DEFAULT '[\"get_current_datetime\"]'::jsonb" in sql
    assert "knowledge_document_ids JSONB NOT NULL DEFAULT '[]'::jsonb" in sql
    lowered = sql.lower()
    assert "drop column enabled_tool_codes" not in lowered
    assert "drop column knowledge_document_ids" not in lowered
    assert "alter table checkpoints" not in lowered
    assert "alter table store" not in lowered

    executed = []

    class _Conn:
        def execute(self, statement, params=None):
            executed.append(statement)

    apply_business_schema(_Conn())
    apply_business_schema(_Conn())
    assert len(executed) == len(statements) * 2
    created = [item for item in executed if item.startswith("CREATE TABLE IF NOT EXISTS")]
    for name in RELATION_TABLES:
        assert sum(1 for item in created if f"CREATE TABLE IF NOT EXISTS {name}" in item) == 2
