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