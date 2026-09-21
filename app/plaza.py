from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from app.avatars import avatar_root, save_avatar
from app.catalog import get_agent_catalog
from app.config import project_root
from app.knowledge import index_markdown_file, kb_namespace
from app.repository import (
    DEFAULT_WORKFLOW_CODE,
    DOUYIN_OPS_TEMPLATE,
    AgentInstanceRecord,
    KnowledgeDocumentRecord,
    KnowledgeSeed,
    UserRecord,
)


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
    repo.bind_workflow(user.user_id, instance.agent_instance_id, DEFAULT_WORKFLOW_CODE)
    seeds = demo_knowledge_seeds()
    store = getattr(runtime, "memory_store", None)

    def write_seed(record: KnowledgeDocumentRecord) -> None:
        store_demo_document(store, record)

    repo.seed_knowledge_documents(
        user.user_id,
        instance.agent_instance_id,
        seeds,
        write_store=write_seed if store is not None else None,
    )
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