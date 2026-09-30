from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.approvals import ApprovalManager


@dataclass(frozen=True)
class SkillRuntimeContext:
    user_id: UUID
    agent_instance_id: UUID
    config_version_id: UUID
    status: str
    system_prompt: str
    skill_ids: tuple[UUID, ...]
    skill_codes: tuple[str, ...]
    skill_instructions: tuple[str, ...]
    enabled_tool_codes: tuple[str, ...]
    knowledge_document_ids: tuple[str, ...]
    workflow_codes: tuple[str, ...]

    @property
    def prompt_context(self) -> str:
        chunks = [item.strip() for item in self.skill_instructions if item.strip()]
        if not chunks:
            return ""
        return "\n\n已批准加载的 Skill 指令（仅作为行为约束，不授予工具或脚本权限）：\n" + "\n\n---\n\n".join(chunks)


def build_skill_runtime_context(
    skill_service, *, user_id: UUID, agent_instance_id: UUID,
    prefer_draft: bool = False, approvals: ApprovalManager | None = None,
    thread_id: str | None = None, config_version_id: UUID | None = None,
) -> SkillRuntimeContext:
    if config_version_id is None:
        config = skill_service.get_effective_config(user_id, agent_instance_id, prefer_draft=prefer_draft)
    else:
        config = skill_service.repository.get_config(config_version_id)
        if (config.get("user_id") != user_id
                or config.get("agent_instance_id") != agent_instance_id):
            raise ValueError("config version does not belong to the current agent scope")
    bindings = skill_service.repository.list_bindings(config["config_version_id"])
    skills = []
    for binding in bindings:
        try:
            skill = skill_service.repository.get_skill(binding.skill_id)
        except Exception:
            continue
        if skill.status != "active":
            continue
        # Platform skills marked auto are safe baseline behavior. User/imported
        # skills require an independent Skill approval for this thread.
        if skill.owner_scope != "platform" or skill.approval_mode != "auto":
            if approvals is None or not thread_id or not approvals.ensure(
                user_id=user_id, agent_instance_id=agent_instance_id,
                config_version_id=config["config_version_id"], thread_id=thread_id,
                approval_kind="skill", resource_code=skill.code,
            ):
                continue
        skills.append(skill)
    return SkillRuntimeContext(
        user_id=user_id, agent_instance_id=agent_instance_id,
        config_version_id=config["config_version_id"], status=config["status"],
        system_prompt=config.get("system_prompt", ""),
        skill_ids=tuple(item.skill_id for item in skills),
        skill_codes=tuple(item.code for item in skills),
        skill_instructions=tuple(item.instructions for item in skills),
        enabled_tool_codes=tuple(config.get("enabled_tool_codes") or ()),
        knowledge_document_ids=tuple(str(item) for item in (config.get("knowledge_document_ids") or ())),
        workflow_codes=tuple(config.get("workflow_codes") or ()),
    )


def tool_codes(tools: list[Any]) -> set[str]:
    return {str(getattr(item, "name", "")) for item in tools if getattr(item, "name", "")}


def select_tools(tools: list[Any], enabled_tool_codes: list[str] | tuple[str, ...] | None) -> list[Any]:
    """Select one exact list for both model binding and ToolNode construction."""
    if enabled_tool_codes is None:
        return list(tools)
    allowed = set(enabled_tool_codes)
    return [item for item in tools if getattr(item, "name", "") in allowed]


def enforce_independent_approval(
    approvals: ApprovalManager, *, context: SkillRuntimeContext, thread_id: str,
    approval_kind: str, resource_code: str,
) -> bool:
    if approval_kind not in {"import", "skill", "script", "tool"}:
        raise ValueError(f"unknown approval kind: {approval_kind}")
    return approvals.ensure(
        user_id=context.user_id, agent_instance_id=context.agent_instance_id,
        config_version_id=context.config_version_id, thread_id=thread_id,
        approval_kind=approval_kind, resource_code=resource_code,
    )



def approved_resource_codes(
    approvals: ApprovalManager, *, context: SkillRuntimeContext, thread_id: str,
    approval_kind: str, candidates: list[str] | tuple[str, ...],
) -> set[str]:
    """Return only independently approved resources of one approval kind."""
    if approval_kind not in {"import", "skill", "script", "tool"}:
        raise ValueError(f"unknown approval kind: {approval_kind}")
    return {
        code for code in candidates
        if approvals.ensure(
            user_id=context.user_id, agent_instance_id=context.agent_instance_id,
            config_version_id=context.config_version_id, thread_id=thread_id,
            approval_kind=approval_kind, resource_code=code,
        )
    }
