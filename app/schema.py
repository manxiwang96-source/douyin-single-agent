from __future__ import annotations

import re
from pathlib import Path

BUSINESS_SCHEMA_PATH = Path(__file__).resolve().parent / "sql" / "001_business.sql"
PGVECTOR_MISSING_MESSAGE = (
    "pgvector extension is required for PostgresStore embedding index, "
    "but it is not available. Install pgvector for this PostgreSQL version "
    "and allow CREATE EXTENSION vector."
)
_DOLLAR_TAG_RE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)?\$")


def load_business_schema_sql() -> str:
    return BUSINESS_SCHEMA_PATH.read_text(encoding="utf-8")


def iter_sql_statements(script: str) -> list[str]:
    """Split a SQL script into statements without cutting dollar-quoted bodies."""
    statements: list[str] = []
    buffer: list[str] = []
    in_single = False
    dollar_tag: str | None = None
    i = 0
    text = script or ""
    n = len(text)

    def flush() -> None:
        statement = "".join(buffer).strip().rstrip(";").strip()
        buffer.clear()
        if statement:
            statements.append(statement)

    while i < n:
        ch = text[i]
        if dollar_tag is not None:
            if text.startswith(dollar_tag, i):
                buffer.append(dollar_tag)
                i += len(dollar_tag)
                dollar_tag = None
                continue
            buffer.append(ch)
            i += 1
            continue
        if in_single:
            buffer.append(ch)
            if ch == "'" and i + 1 < n and text[i + 1] == "'":
                buffer.append("'")
                i += 2
                continue
            if ch == "'":
                in_single = False
            i += 1
            continue
        if ch == "-" and i + 1 < n and text[i + 1] == "-":
            i += 2
            while i < n and text[i] not in "\r\n":
                i += 1
            continue
        if ch == "'":
            in_single = True
            buffer.append(ch)
            i += 1
            continue
        if ch == "$":
            match = _DOLLAR_TAG_RE.match(text, i)
            if match:
                dollar_tag = match.group(0)
                buffer.append(dollar_tag)
                i += len(dollar_tag)
                continue
        if ch == ";":
            flush()
            i += 1
            continue
        if ch == "\r":
            if buffer:
                buffer.append("\n")
            i += 1
            if i < n and text[i] == "\n":
                i += 1
            continue
        if ch == "\n":
            if buffer:
                buffer.append("\n")
            i += 1
            continue
        buffer.append(ch)
        i += 1

    flush()
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
