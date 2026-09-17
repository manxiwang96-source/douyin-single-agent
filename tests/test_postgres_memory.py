from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.postgres import admin_uri, database_name
from app.runtime import build_runtime


def test_postgres_uri_helpers():
    uri = "postgresql://postgres@127.0.0.1:5432/agentdemo"
    assert database_name(uri) == "agentdemo"
    assert admin_uri(uri).endswith("/postgres")


def test_unsafe_database_name_rejected():
    with pytest.raises(ValueError):
        database_name("postgresql://postgres@127.0.0.1:5432/bad-name")


def test_production_runtime_requires_postgres_without_fallback(
    settings, embeddings, llm, image_client, video_client, media_root, knowledge_dir
):
    settings.postgres_uri = ""
    settings.smtp_user = "test@example.com"
    settings.smtp_password = "x"
    settings.smtp_to = "test@example.com"
    with pytest.raises(RuntimeError, match="POSTGRES_URI"):
        build_runtime(
            settings,
            embeddings=embeddings,
            llm=llm,
            image_client=image_client,
            video_client=video_client,
            knowledge_dir=knowledge_dir,
            media_root=media_root,
            extra_tools=[],
        )


def test_test_runtime_stays_in_memory(runtime):
    assert isinstance(runtime.checkpointer, InMemorySaver)
    assert runtime.pg_pool is None

from unittest.mock import MagicMock, patch

import psycopg

from app.postgres import ensure_postgres_database


class _FakeConn:
    def __init__(self, execute):
        self.execute = execute

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_ensure_creates_database_when_target_is_missing():
    created = []

    def execute(sql, params=None):
        result = MagicMock()
        if "pg_database" in str(sql):
            result.fetchone.return_value = None
        elif "CREATE DATABASE" in str(sql):
            created.append(sql)
        return result

    def fake_connect(uri, **kwargs):
        if uri.rstrip("/").endswith("agentdemo"):
            raise psycopg.OperationalError('connection failed: "agentdemo"')
        return _FakeConn(execute)

    with patch("app.postgres.psycopg.connect", side_effect=fake_connect):
        ensure_postgres_database("postgresql://postgres@127.0.0.1:5432/agentdemo")
    assert created
    assert "agentdemo" in created[0]


def test_ensure_reraises_when_database_already_exists():
    def execute(sql, params=None):
        result = MagicMock()
        result.fetchone.return_value = (1,)
        return result

    def fake_connect(uri, **kwargs):
        if uri.rstrip("/").endswith("agentdemo"):
            raise psycopg.OperationalError("password authentication failed")
        return _FakeConn(execute)

    with patch("app.postgres.psycopg.connect", side_effect=fake_connect):
        with pytest.raises(psycopg.OperationalError, match="password authentication failed"):
            ensure_postgres_database("postgresql://postgres@127.0.0.1:5432/agentdemo")

import asyncio

from langgraph.checkpoint.memory import InMemorySaver

from app.postgres import ThreadedAsyncCheckpointMixin


class _ThreadedMemorySaver(ThreadedAsyncCheckpointMixin, InMemorySaver):
    pass


def test_threaded_async_mixin_get_tuple_does_not_raise():
    saver = _ThreadedMemorySaver()
    result = asyncio.run(saver.aget_tuple({"configurable": {"thread_id": "t-async"}}))
    assert result is None

