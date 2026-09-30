from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from app.config import Settings, project_root
from app.dify_client import DifyClient
from app.embeddings import make_openai_embeddings
from app.graph import build_graph, graph_cache_key, interrupt_payload
from app.image_client import ImageClient
from app.knowledge import index_knowledge_dir, make_store
from app.mcp_client import McpFactsProvider, StaticFactsProvider, default_test_facts, load_mcp_tools
from app.media_paths import ensure_media_dirs, resolve_media_root
from app.postgres import make_postgres_memory
from app.repository import InMemoryBusinessRepository
from app.approvals import ApprovalManager, PostgresApprovalRepository
from app.skill_repository import PostgresSkillRepository
from app.skills import InMemorySkillRepository, SkillService, make_search_provider
from app.tools import build_tools
from app.tool_audit import InMemoryToolAuditRepository, PostgresToolAuditRepository
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
    skill_repository: Any = None
    skill_service: Any = None
    approval_manager: Any = None
    llm: Any = None
    tools: list[Any] | None = None
    _graph_cache: dict[tuple[str, tuple[str, ...]], Any] | None = None
    tool_audit_repository: Any = None

    def graph_for_tool_codes(self, allowed_tool_codes=None, config_version_id=None):
        """Build/cache a scoped graph while preserving the existing topology."""
        if allowed_tool_codes is None:
            return self.graph
        key = graph_cache_key(allowed_tool_codes, config_version_id)
        if self._graph_cache is None:
            self._graph_cache = {}
        if key not in self._graph_cache:
            self._graph_cache[key] = build_graph(
                llm=self.llm, tools=list(self.tools or []),
                checkpointer=self.checkpointer, store=self.memory_store,
                allowed_tool_codes=key[1],
            )
        return self._graph_cache[key]


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
    skill_repository=None,
    skill_service=None,
    approval_manager=None,
    tool_audit_repository=None,
    clock=None,
    weather_client=None,
    weather_provider=None,
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

    if skill_repository is None:
        skill_repository = PostgresSkillRepository(pg_pool) if production and pg_pool is not None else InMemorySkillRepository()
    if tool_audit_repository is None:
        tool_audit_repository = PostgresToolAuditRepository(pg_pool) if production and pg_pool is not None else InMemoryToolAuditRepository()

    if approval_manager is None:
        approval_repository = PostgresApprovalRepository(pg_pool) if production and pg_pool is not None else None
        approval_manager = ApprovalManager(approval_repository)

    if skill_service is None:
        quarantine_root = Path(settings.skill_quarantine_dir)
        if not quarantine_root.is_absolute():
            quarantine_root = root / quarantine_root
        skill_service = SkillService(
            skill_repository,
            search_provider=make_search_provider(settings),
            quarantine_root=quarantine_root,
        )

    if facts_provider is None:
        if extra_tools:
            facts_provider = McpFactsProvider(extra_tools, default_city=settings.assistant_city)
        else:
            facts_provider = StaticFactsProvider(default_test_facts(settings.assistant_city))

    if not production and weather_provider is None and weather_client is None:
        fallback_city = settings.assistant_city or "广州"

        def weather_provider(city: str = "") -> dict[str, Any]:
            target = (city or fallback_city).strip() or fallback_city
            facts = default_test_facts(target)
            return {
                "city": target or facts.city,
                "weather": facts.weather,
                "temperature_c": facts.temperature_c,
            }

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
        skill_service=skill_service,
        approval_manager=approval_manager,
        tool_audit_repository=tool_audit_repository,
        clock=clock,
        weather_client=weather_client,
        weather_provider=weather_provider,
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
        skill_repository=skill_repository,
        skill_service=skill_service,
        approval_manager=approval_manager,
        tool_audit_repository=tool_audit_repository,
        llm=llm, tools=list(tools), _graph_cache={},
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
    skill_repository=None,
    skill_service=None,
    approval_manager=None,
    tool_audit_repository=None,
    clock=None,
    weather_client=None,
    weather_provider=None,
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
        skill_repository=skill_repository,
        skill_service=skill_service,
        approval_manager=approval_manager,
        tool_audit_repository=tool_audit_repository,
        clock=clock,
        weather_client=weather_client,
        weather_provider=weather_provider,
    )
