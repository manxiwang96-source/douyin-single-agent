from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.store.postgres import PostgresStore
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_SAFE_DB = re.compile(r"^[A-Za-z0-9_]+$")


class ThreadedAsyncCheckpointMixin:
    """Expose async checkpointer methods by running the sync API in a worker thread."""

    async def aget_tuple(self, config):
        return await asyncio.to_thread(self.get_tuple, config)

    async def aput(self, config, checkpoint, metadata, new_versions):
        return await asyncio.to_thread(self.put, config, checkpoint, metadata, new_versions)

    async def aput_writes(self, config, writes, task_id, task_path=""):
        return await asyncio.to_thread(self.put_writes, config, writes, task_id, task_path)

    async def adelete_thread(self, thread_id):
        return await asyncio.to_thread(self.delete_thread, thread_id)


class AppPostgresSaver(ThreadedAsyncCheckpointMixin, PostgresSaver):
    """Production saver compatible with graph.ainvoke."""


@dataclass
class PostgresMemory:
    checkpointer: AppPostgresSaver
    store: PostgresStore
    pool: ConnectionPool


def admin_uri(uri: str) -> str:
    parsed = urlparse(uri)
    return urlunparse(parsed._replace(path="/postgres"))


def database_name(uri: str) -> str:
    parsed = urlparse(uri)
    name = (parsed.path or "").lstrip("/")
    if not name or not _SAFE_DB.fullmatch(name):
        raise ValueError("POSTGRES_URI database name must be alphanumeric or underscore")
    return name


def ensure_postgres_database(uri: str) -> None:
    try:
        with psycopg.connect(uri, autocommit=True) as conn:
            conn.execute("SELECT 1")
        return
    except psycopg.OperationalError as exc:
        # Connection-time errors may not include SQLSTATE, and Windows can
        # mojibake the localized "database does not exist" message. Inspect
        # pg_database through the admin database instead of parsing text.
        original = exc
    db_name = database_name(uri)
    with psycopg.connect(admin_uri(uri), autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (db_name,),
        ).fetchone()
        if exists is None:
            conn.execute(f'CREATE DATABASE "{db_name}"')
            return
    raise original


def make_postgres_memory(uri: str) -> PostgresMemory:
    if not uri:
        raise RuntimeError("POSTGRES_URI is required for production memory")
    ensure_postgres_database(uri)
    pool = ConnectionPool(
        conninfo=uri,
        min_size=1,
        max_size=10,
        open=True,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
    )
    pool.wait(timeout=10)
    checkpointer = AppPostgresSaver(pool)
    store = PostgresStore(pool)
    checkpointer.setup()
    store.setup()
    return PostgresMemory(checkpointer=checkpointer, store=store, pool=pool)
