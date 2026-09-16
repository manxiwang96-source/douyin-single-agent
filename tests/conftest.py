from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings, project_root
from app.embeddings import EmbeddingsAdapter, hashing_embed_documents
from app.runtime import build_test_runtime
from tests.fakes import FakeImageClient, FakeVideoClient, ScriptedLLM


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
def runtime(settings, embeddings, llm, image_client, video_client, media_root, knowledge_dir):
    return build_test_runtime(
        settings,
        embeddings,
        llm,
        image_client,
        video_client,
        media_root,
        knowledge_dir,
    )
