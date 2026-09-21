from __future__ import annotations

from pathlib import Path

BUSINESS_SCHEMA_PATH = Path(__file__).resolve().parent / "sql" / "001_business.sql"
PGVECTOR_MISSING_MESSAGE = (
    "pgvector extension is required for PostgresStore embedding index, "
    "but it is not available. Install pgvector for this PostgreSQL version "
    "and allow CREATE EXTENSION vector."
)


def load_business_schema_sql() -> str:
    return BUSINESS_SCHEMA_PATH.read_text(encoding="utf-8")


def iter_sql_statements(script: str) -> list[str]:
    statements: list[str] = []
    buffer: list[str] = []
    for raw_line in (script or "").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buffer.append(raw_line)
        if stripped.endswith(";"):
            statement = "\n".join(buffer).strip().rstrip(";").strip()
            if statement:
                statements.append(statement)
            buffer = []
    tail = "\n".join(buffer).strip().rstrip(";").strip()
    if tail:
        statements.append(tail)
    return statements


def apply_business_schema(conn) -> None:
    for statement in iter_sql_statements(load_business_schema_sql()):
        conn.execute(statement)


def ensure_pgvector_extension(conn) -> None:
    try:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    except Exception as exc:
        raise RuntimeError(f"{PGVECTOR_MISSING_MESSAGE} CREATE EXTENSION failed: {exc}") from exc
    result = conn.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
    row = result.fetchone() if result is not None and hasattr(result, "fetchone") else None
    if row is None:
        raise RuntimeError(PGVECTOR_MISSING_MESSAGE)