from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from app.avatars import avatar_root, save_avatar
from app.catalog import get_agent_catalog
from app.config import project_root
from app.knowledge import index_markdown_file, kb_namespace
from app.repository import (
    CUSTOM_TEMPLATE,
    DEFAULT_THREAD_KIND,
    DEFAULT_WORKFLOW_CODE,
    DOUYIN_OPS_TEMPLATE,
    AgentInstanceRecord,
    KnowledgeDocumentRecord,
    KnowledgeSeed,
    UserRecord,
)
from app.skills import PublishedConfigNotFound, REQUIRED_CONFIG_TOOL_CODE
from app.tool_catalog import resolve_tool_code



CUSTOM_DEFAULT_TOOL_CODES = (REQUIRED_CONFIG_TOOL_CODE,)
DOUYIN_OPS_DEFAULT_TOOL_CODES = (
    REQUIRED_CONFIG_TOOL_CODE,
    "search_kb",
    "discover_leads",
    "generate_image",
    "generate_video",
    "send_email",
    "remember_fact",
    "recall_facts",
    "list_jobs",
    "cancel_job",
)
DOUYIN_OPS_OPTIONAL_DEFAULT_TOOL_CODES = (
    "web_search",
    "list_available_skills",
    "load_skill",
    "run_skill_script",
)


def default_enabled_tool_codes(template_code: str, runtime=None) -> list[str]:
    if template_code == CUSTOM_TEMPLATE:
        wanted = list(CUSTOM_DEFAULT_TOOL_CODES)
    else:
        wanted = list(DOUYIN_OPS_DEFAULT_TOOL_CODES)
        available = {
            resolve_tool_code(str(getattr(item, "name", "") or ""))
            for item in (getattr(runtime, "tools", None) or [])
        }
        available.discard("")
        for extra in DOUYIN_OPS_OPTIONAL_DEFAULT_TOOL_CODES:
            if extra in available and extra not in wanted:
                wanted.append(extra)
    codes: list[str] = []
    for raw in wanted:
        code = resolve_tool_code(raw)
        if not code or code in codes:
            continue
        codes.append(code)
    if REQUIRED_CONFIG_TOOL_CODE not in codes:
        codes.insert(0, REQUIRED_CONFIG_TOOL_CODE)
    return codes


def publish_default_agent_config(runtime, user: UserRecord, instance: AgentInstanceRecord) -> dict[str, Any]:
    skill_repo = runtime.skill_service.repository
    draft = skill_repo.ensure_draft(user.user_id, instance.agent_instance_id)
    knowledge_ids: list = []
    workflow_codes: list[str] = []
    if instance.template_code == DOUYIN_OPS_TEMPLATE:
        knowledge_ids = [
            item.document_id
            for item in runtime.business_repo.list_knowledge_documents(instance.agent_instance_id)
        ]
        workflow_codes = [DEFAULT_WORKFLOW_CODE]
    skill_repo.update_config(
        draft["config_version_id"],
        enabled_tool_codes=default_enabled_tool_codes(instance.template_code, runtime),
        knowledge_document_ids=knowledge_ids,
        workflow_codes=workflow_codes,
    )
    return skill_repo.publish_config(user.user_id, instance.agent_instance_id)


def resolve_published_config(runtime, user_id: UUID, agent_instance_id: UUID) -> dict[str, Any]:
    try:
        config = runtime.skill_service.get_effective_config(
            user_id, agent_instance_id, prefer_draft=False
        )
    except PublishedConfigNotFound:
        config = runtime.skill_service.repository.publish_config(user_id, agent_instance_id)
    if config.get("status") != "published":
        config = runtime.skill_service.repository.publish_config(user_id, agent_instance_id)
    return config


def ensure_official_thread(runtime, user: UserRecord, instance: AgentInstanceRecord):
    repo = runtime.business_repo
    thread = repo.get_latest_active_thread(
        user.user_id, instance.agent_instance_id, thread_kind=DEFAULT_THREAD_KIND
    )
    if thread is None:
        selected_config = resolve_published_config(runtime, user.user_id, instance.agent_instance_id)
        thread = repo.create_app_thread(
            user.user_id,
            instance.agent_instance_id,
            config_version_id=selected_config["config_version_id"],
            thread_kind=DEFAULT_THREAD_KIND,
        )
    return thread


def ensure_debug_thread(runtime, user: UserRecord, instance: AgentInstanceRecord):
    repo = runtime.business_repo
    thread = repo.get_latest_active_thread(
        user.user_id, instance.agent_instance_id, thread_kind="debug"
    )
    if thread is None:
        draft = runtime.skill_service.ensure_config(user.user_id, instance.agent_instance_id)
        thread = repo.create_app_thread(
            user.user_id,
            instance.agent_instance_id,
            config_version_id=draft.get("config_version_id"),
            thread_kind="debug",
        )
    return thread


def isoformat(value) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def demo_knowledge_seeds(root: Path | None = None) -> list[KnowledgeSeed]:
    demo_dir = (root or project_root()) / "knowledge" / "douyin_ops_demo"
    seeds: list[KnowledgeSeed] = []
    if not demo_dir.is_dir():
        return seeds
    for path in sorted(demo_dir.glob("*.md")):
        relative = path.relative_to(root or project_root()).as_posix()
        seeds.append(
            KnowledgeSeed(
                title=path.stem,
                filename=path.name,
                storage_uri=relative,
            )
        )
    return seeds


def instance_card(record: AgentInstanceRecord) -> dict[str, Any]:
    avatar_url = None
    if record.avatar_uri:
        avatar_url = f"/v1/agent-instances/{record.agent_instance_id}/avatar"
    return {
        "agent_instance_id": str(record.agent_instance_id),
        "user_id": str(record.user_id),
        "template_code": record.template_code,
        "title": record.title,
        "intro": record.intro,
        "avatar_uri": record.avatar_uri,
        "avatar_url": avatar_url,
        "agent_mode": record.agent_mode,
        "status": record.status,
        "created_at": isoformat(record.created_at),
        "updated_at": isoformat(record.updated_at),
    }


def store_demo_document(store, record: KnowledgeDocumentRecord, root: Path | None = None) -> None:
    path = (root or project_root()) / record.storage_uri
    namespace = kb_namespace(record.user_id, record.agent_instance_id)
    index_markdown_file(store, namespace, path)


def create_agent_instance_for_user(
    runtime,
    user: UserRecord,
    *,
    template_code: str,
    title: str,
    intro: str = "",
    avatar: str | None = None,
) -> AgentInstanceRecord:
    repo = runtime.business_repo
    avatar_uri = None
    if avatar:
        avatar_uri = save_avatar(avatar_root(runtime.media_root), user.user_id, avatar)
    instance = repo.create_agent_instance(
        user.user_id,
        title,
        intro=intro or "",
        avatar_uri=avatar_uri,
        template_code=template_code or DOUYIN_OPS_TEMPLATE,
    )
    if template_code == DOUYIN_OPS_TEMPLATE:
        repo.bind_workflow(user.user_id, instance.agent_instance_id, DEFAULT_WORKFLOW_CODE)
    seeds = demo_knowledge_seeds() if template_code == DOUYIN_OPS_TEMPLATE else []
    store = getattr(runtime, "memory_store", None)

    def write_seed(record: KnowledgeDocumentRecord) -> None:
        store_demo_document(store, record)

    repo.seed_knowledge_documents(
        user.user_id,
        instance.agent_instance_id,
        seeds,
        write_store=write_seed if store is not None else None,
    )
    instance = repo.get_agent_instance(instance.agent_instance_id) or instance
    publish_default_agent_config(runtime, user, instance)
    return repo.get_agent_instance(instance.agent_instance_id) or instance


def sidebar_payload(runtime, instance: AgentInstanceRecord) -> dict[str, Any]:
    catalog = get_agent_catalog(instance.template_code)
    bindings = runtime.business_repo.list_workflow_bindings(instance.agent_instance_id)
    bound_codes = {item.workflow_code for item in bindings if item.enabled}
    documents = runtime.business_repo.list_knowledge_documents(instance.agent_instance_id)
    workflows = []
    for item in catalog.workflows:
        if item.code not in bound_codes:
            continue
        binding = next(b for b in bindings if b.workflow_code == item.code)
        workflows.append(
            {
                "code": item.code,
                "display_name": item.display_name,
                "enabled": binding.enabled,
            }
        )
    tools = []
    if DEFAULT_WORKFLOW_CODE in bound_codes:
        for item in catalog.tools:
            tools.append(
                {
                    "name": item.name,
                    "display_name": item.display_name,
                    "user_facing_summary": item.user_facing_summary,
                }
            )
    return {
        "agent_instance_id": str(instance.agent_instance_id),
        "title": instance.title,
        "intro": instance.intro,
        "agent_mode": instance.agent_mode,
        "agent_mode_label": "单智能体模式",
        "capability_description": catalog.capability_description,
        "development_notes": catalog.development_notes,
        "knowledge_documents": [
            {
                "document_id": str(item.document_id),
                "title": item.title,
                "filename": item.filename,
                "source": item.source,
                "status": item.status,
            }
            for item in documents
        ],
        "workflows": workflows,
        "tools": tools,
    }


def require_owned_instance(repo, user_id: UUID, agent_instance_id: UUID) -> AgentInstanceRecord:
    instance = repo.get_agent_instance(agent_instance_id)
    if instance is None or instance.user_id != user_id or instance.status == "archived":
        from app.repository import NotFoundError

        raise NotFoundError(f"agent instance not found: {agent_instance_id}")
    return instance