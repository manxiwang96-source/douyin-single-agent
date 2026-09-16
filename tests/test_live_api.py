from __future__ import annotations

import os

import pytest

from app.config import Settings, project_root
from app.embeddings import make_openai_embeddings
from app.image_client import ImageClient
from app.knowledge import index_knowledge_dir, make_store, search_kb
from app.media_paths import resolve_media_root
from app.runtime import make_llm
from app.video_client import VideoClient

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_API") != "1",
    reason="RUN_LIVE_API is not 1",
)


def _settings() -> Settings:
    return Settings()


def test_live_chat_completion():
    settings = _settings()
    if not settings.openai_api_key:
        pytest.skip("missing OPENAI_API_KEY")
    llm = make_llm(settings)
    message = llm.invoke("只回复：好")
    assert getattr(message, "content", "")


def test_live_cheapest_image():
    settings = _settings()
    if not settings.openai_api_key:
        pytest.skip("missing OPENAI_API_KEY")
    media_root = resolve_media_root(settings.media_output_dir, project_root())
    client = ImageClient(settings, media_root)
    path = client.generate("minimal red bottle, 3:4, cheap test")
    assert path.is_file()
    assert path.parent.name == "images"
    assert path.stat().st_size > 0


def test_live_cheapest_video():
    settings = _settings()
    if not settings.dashscope_api_key:
        pytest.skip("missing DASHSCOPE_API_KEY")
    media_root = resolve_media_root(settings.media_output_dir, project_root())
    client = VideoClient(settings, media_root)
    path = client.generate("a bottle rotating slowly")
    assert path.is_file()
    assert path.parent.name == "videos"
    assert path.stat().st_size > 0


def test_live_kb_embedding_search():
    settings = _settings()
    if not settings.embedding_api_key:
        pytest.skip("missing EMBEDDING_API_KEY")
    embeddings = make_openai_embeddings(settings)
    store = make_store(embeddings.embed_documents, settings.embedding_dims)
    indexed = index_knowledge_dir(store, project_root() / "knowledge")
    assert indexed > 0
    hits = search_kb(store, "小红书标题规范", k=4)
    assert hits
