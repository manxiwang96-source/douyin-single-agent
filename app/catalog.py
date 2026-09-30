"""Read-only product catalog for agent templates and sidebar metadata."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class ToolCatalog:
    name: str
    display_name: str
    user_facing_summary: str


@dataclass(frozen=True)
class WorkflowCatalog:
    code: str
    display_name: str


@dataclass(frozen=True)
class AgentCatalog:
    template_code: str
    display_name: str
    capability_description: str
    development_notes: str
    agent_mode: str
    workflows: tuple[WorkflowCatalog, ...]
    tools: tuple[ToolCatalog, ...]


CUSTOM_CATALOG = AgentCatalog(
    template_code="custom",
    display_name="自定义智能体",
    capability_description="按用户配置的提示词、知识库、Skill、工具和工作流运行。默认仅启用当前时间工具。",
    development_notes="custom 实例不继承运营助手工作流；所有额外 Skill、脚本和工具均需显式配置并按独立审批策略执行。",
    agent_mode="single",
    workflows=(),
    tools=(ToolCatalog(name="get_current_datetime", display_name="当前时间", user_facing_summary="获取当前日期和时间。"),),
)

DOUYIN_OPS_CATALOG = AgentCatalog(
    template_code="douyin_ops",
    display_name="运营助手",
    capability_description=(
        "帮助用户围绕抖音和小红书账号、话题完成运营规划、内容整理、知识检索，"
        "并通过已绑定的线索发现工作流执行真实的评论或私信触达。"
    ),
    development_notes=(
        "v1 保持单智能体模式；双平台线索发现由 douyin-lead-discovery 工作流完成。"
        "调用前会明确提示真实发送，实例知识库仅用于补充运营信息，不能代替真实扫描和触达。"
    ),
    agent_mode="single",
    workflows=(
        WorkflowCatalog(
            code="douyin-lead-discovery",
            display_name="线索发现与触达",
        ),
    ),
    tools=(
        ToolCatalog(
            name="discover_leads",
            display_name="线索发现",
            user_facing_summary="扫描抖音或小红书指定账号、话题或内容，并通过已绑定工作流真实发送评论或私信。",
        ),
    ),
)

AGENT_CATALOG: Mapping[str, AgentCatalog] = MappingProxyType(
    {
        "douyin_ops": DOUYIN_OPS_CATALOG,
        "custom": CUSTOM_CATALOG,
    }
)


def get_agent_catalog(template_code: str) -> AgentCatalog:
    """Return the immutable catalog entry for a supported template."""
    try:
        return AGENT_CATALOG[template_code]
    except KeyError as exc:
        raise KeyError(f"unsupported agent template: {template_code}") from exc
