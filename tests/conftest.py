from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings, project_root
from app.embeddings import EmbeddingsAdapter, hashing_embed_documents
from app.runtime import build_test_runtime
from tests.fakes import (
    FakeDifyClient,
    FakeEmailClient,
    FakeImageClient,
    FakeVideoClient,
    ScriptedLLM,
    fake_datetime_weather_tools,
    static_facts_provider,
)


@pytest.fixture(autouse=True)
def _fast_password_hash(monkeypatch):
    monkeypatch.setattr("app.auth.DEFAULT_ITERATIONS", 2_000)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        openai_api_key="test-openai",
        openai_api_base_url="https://example.test/v1",
        openai_api_model="gpt-test",
        image_provider="gateway",
        image_model="gpt-image-2",
        image_quality="low",
        image_size="1024x1536",
        image_tier_param="quality",
        video_provider="dashscope",
        video_model="wan3.0-video",
        video_duration=2,
        video_resolution="480P",
        video_size="9:16",
        video_aspect_param="ratio",
        dashscope_api_key="test-dashscope",
        dashscope_endpoint="https://dashscope.example.test/api/v1",
        embedding_model="BAAI/bge-m3",
        embedding_base_url="https://embed.example.test/v1",
        embedding_api_key="test-embed",
        embedding_dims=64,
        media_output_dir="outputs",
        postgres_uri="",
        assistant_city="广州",
        assistant_timezone="Asia/Shanghai",
        scheduler_enabled=False,
        mcp_enabled=False,
        dify_base_url="https://dify.example.test/v1",
        dify_api_key="",
        dify_lead_app_id="douyin-lead-discovery",
        douyin_http_base_url="",
        douyin_http_api_token="",
        dify_timeout_s=300,
        dify_live_enabled=False,
        smtp_host="smtp.example.test",
        smtp_port=465,
        smtp_ssl=True,
        smtp_user="test@example.com",
        smtp_password="test-pass",
        smtp_from="test@example.com",
        smtp_to="test@example.com",
    )


@pytest.fixture
def media_root(tmp_path: Path) -> Path:
    root = tmp_path / "outputs"
    (root / "images").mkdir(parents=True)
    (root / "videos").mkdir(parents=True)
    return root


@pytest.fixture
def knowledge_dir() -> Path:
    return project_root() / "knowledge"


@pytest.fixture
def embeddings(settings: Settings) -> EmbeddingsAdapter:
    return EmbeddingsAdapter(
        lambda texts: hashing_embed_documents(texts, settings.embedding_dims)
    )


@pytest.fixture
def llm() -> ScriptedLLM:
    return ScriptedLLM()


@pytest.fixture
def image_client(media_root: Path) -> FakeImageClient:
    return FakeImageClient(media_root)


@pytest.fixture
def video_client(media_root: Path) -> FakeVideoClient:
    return FakeVideoClient(media_root)


@pytest.fixture
def email_client() -> FakeEmailClient:
    return FakeEmailClient()


@pytest.fixture
def dify_client() -> FakeDifyClient:
    return FakeDifyClient()


@pytest.fixture
def runtime(settings, embeddings, llm, image_client, video_client, media_root, knowledge_dir, email_client, dify_client):
    return build_test_runtime(
        settings,
        embeddings,
        llm,
        image_client,
        video_client,
        media_root,
        knowledge_dir,
        extra_tools=fake_datetime_weather_tools(),
        email_client=email_client,
        facts_provider=static_facts_provider(settings.assistant_city),
        dify_client=dify_client,
    )
