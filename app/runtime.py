from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

from app.config import Settings, project_root
from app.embeddings import make_openai_embeddings
from app.graph import build_graph, interrupt_payload
from app.image_client import ImageClient
from app.knowledge import index_knowledge_dir, make_store
from app.media_paths import ensure_media_dirs, resolve_media_root
from app.tools import build_tools
from app.video_client import VideoClient

__all__ = [
    "AppRuntime",
    "build_runtime",
    "build_test_runtime",
    "interrupt_payload",
    "make_llm",
    "make_sqlite_checkpointer",
]


@dataclass
class AppRuntime:
    settings: Settings
    media_root: Path
    graph: Any
    store: Any
    image_client: ImageClient
    video_client: VideoClient
    checkpointer: Any
    sqlite_conn: sqlite3.Connection | None = None


def make_llm(settings: Settings):
    return ChatOpenAI(
        model=settings.openai_api_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_api_base_url,
        temperature=0.4,
    )


def make_sqlite_checkpointer(
    root: Path | None = None,
) -> tuple[SqliteSaver, sqlite3.Connection]:
    root = (root or project_root()).resolve()
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "checkpoints.sqlite"
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    return saver, conn


def build_runtime(
    settings: Settings | None = None,
    *,
    embeddings=None,
    llm=None,
    image_client: ImageClient | None = None,
    video_client: VideoClient | None = None,
    checkpointer=None,
    knowledge_dir: Path | None = None,
    media_root: Path | None = None,
    sqlite_conn: sqlite3.Connection | None = None,
) -> AppRuntime:
    settings = settings or Settings()
    root = project_root()
    media_root = media_root or resolve_media_root(settings.media_output_dir, root)
    ensure_media_dirs(media_root)
    knowledge_dir = knowledge_dir or (root / "knowledge")

    if embeddings is None:
        embeddings = make_openai_embeddings(settings)
    store = make_store(embeddings.embed_documents, settings.embedding_dims)
    indexed = index_knowledge_dir(store, knowledge_dir)
    if indexed == 0:
        raise RuntimeError(f"no knowledge files indexed from {knowledge_dir}")

    image_client = image_client or ImageClient(settings, media_root)
    video_client = video_client or VideoClient(settings, media_root)
    llm = llm or make_llm(settings)
    tools = build_tools(
        store=store,
        image_client=image_client,
        video_client=video_client,
        settings=settings,
        media_root=media_root,
    )
    if checkpointer is None:
        checkpointer, sqlite_conn = make_sqlite_checkpointer(root)
    graph = build_graph(llm=llm, tools=tools, checkpointer=checkpointer)
    return AppRuntime(
        settings=settings,
        media_root=media_root,
        graph=graph,
        store=store,
        image_client=image_client,
        video_client=video_client,
        checkpointer=checkpointer,
        sqlite_conn=sqlite_conn,
    )


def build_test_runtime(
    settings: Settings,
    embeddings,
    llm,
    image_client,
    video_client,
    media_root: Path,
    knowledge_dir: Path,
) -> AppRuntime:
    return build_runtime(
        settings,
        embeddings=embeddings,
        llm=llm,
        image_client=image_client,
        video_client=video_client,
        checkpointer=InMemorySaver(),
        knowledge_dir=knowledge_dir,
        media_root=media_root,
    )
