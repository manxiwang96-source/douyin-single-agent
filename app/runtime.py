from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from app.config import Settings, project_root
from app.dify_client import DifyClient
from app.embeddings import make_openai_embeddings
from app.graph import build_graph, interrupt_payload
from app.image_client import ImageClient
from app.knowledge import index_knowledge_dir, make_store
from app.mcp_client import McpFactsProvider, StaticFactsProvider, default_test_facts, load_mcp_tools
from app.media_paths import ensure_media_dirs, resolve_media_root
from app.postgres import make_postgres_memory
from app.repository import InMemoryBusinessRepository
from app.tools import build_tools
from app.video_client import VideoClient

__all__ = [
    "AppRuntime",
    "LLM_MAX_TOKENS",
    "LLM_TIMEOUT_S",
    "build_runtime",
    "build_test_runtime",
    "interrupt_payload",
    "make_llm",
]

LLM_TIMEOUT_S = 90.0
LLM_MAX_TOKENS = 1024


@dataclass
class AppRuntime:
    settings: Settings
    media_root: Path
    graph: Any
    store: Any
    memory_store: Any
    image_client: Any
    video_client: Any
    checkpointer: Any
    email_client: Any
    facts_provider: Any
    pg_pool: Any = None
    business_repo: Any = None
    dify_client: Any = None


def make_llm(settings: Settings):
    return ChatOpenAI(
        model=settings.openai_api_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_api_base_url,
        temperature=0.4,
        timeout=LLM_TIMEOUT_S,
        max_retries=1,
        max_tokens=LLM_MAX_TOKENS,
    )


def build_runtime(
    settings: Settings | None = None,
    *,
    embeddings=None,
    llm=None,
    image_client=None,
    video_client=None,
    checkpointer=None,
    knowledge_dir: Path | None = None,
    media_root: Path | None = None,
    memory_store=None,
    extra_tools=None,
    email_client=None,
    facts_provider=None,
    pg_pool=None,
    business_repo=None,
    dify_client=None,
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

    production = checkpointer is None
    if production:
        settings.validate_production()
        memory = make_postgres_memory(
            settings.postgres_uri,
            embeddings=embeddings,
            embedding_dims=settings.embedding_dims,
        )
        checkpointer = memory.checkpointer
        memory_store = memory.store
        pg_pool = memory.pool
        business_repo = memory.repository
    else:
        if memory_store is None:
            memory_store = make_store(embeddings.embed_documents, settings.embedding_dims)
        if business_repo is None:
            business_repo = InMemoryBusinessRepository()

    image_client = image_client or ImageClient(settings, media_root)
    video_client = video_client or VideoClient(settings, media_root)
    llm = llm or make_llm(settings)

    if extra_tools is None and settings.mcp_enabled:
        extra_tools = load_mcp_tools(settings)
    extra_tools = list(extra_tools or [])

    if email_client is None:
        from app.email_client import SmtpEmailClient

        email_client = SmtpEmailClient(settings)
    dify_client = dify_client or DifyClient(settings)

    if facts_provider is None:
        if extra_tools:
            facts_provider = McpFactsProvider(extra_tools, default_city=settings.assistant_city)
        else:
            facts_provider = StaticFactsProvider(default_test_facts(settings.assistant_city))

    tools = build_tools(
        store=store,
        image_client=image_client,
        video_client=video_client,
        settings=settings,
        media_root=media_root,
        memory_store=memory_store,
        email_client=email_client,
        extra_tools=extra_tools,
        business_repo=business_repo,
        dify_client=dify_client,
    )
    graph = build_graph(
        llm=llm,
        tools=tools,
        checkpointer=checkpointer,
        store=memory_store,
    )
    return AppRuntime(
        settings=settings,
        media_root=media_root,
        graph=graph,
        store=store,
        memory_store=memory_store,
        image_client=image_client,
        video_client=video_client,
        checkpointer=checkpointer,
        email_client=email_client,
        facts_provider=facts_provider,
        pg_pool=pg_pool,
        business_repo=business_repo,
        dify_client=dify_client,
    )


def build_test_runtime(
    settings: Settings,
    embeddings,
    llm,
    image_client,
    video_client,
    media_root: Path,
    knowledge_dir: Path,
    extra_tools=None,
    email_client=None,
    facts_provider=None,
    memory_store=None,
    dify_client=None,
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
        memory_store=memory_store,
        extra_tools=extra_tools,
        email_client=email_client,
        facts_provider=facts_provider,
        dify_client=dify_client,
    )
