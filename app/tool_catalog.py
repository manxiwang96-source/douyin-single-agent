"""Selectable business tool catalog for agent configuration."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterable, Mapping


BUILTIN_TOOL_CODE = "get_current_datetime"
DISCOVER_LEADS_TOOL_CODE = "discover_leads"
LEGACY_DISCOVER_LEADS_TOOL_CODE = "discover_douyin_leads"

TOOL_CODE_ALIASES: Mapping[str, str] = MappingProxyType(
    {LEGACY_DISCOVER_LEADS_TOOL_CODE: DISCOVER_LEADS_TOOL_CODE}
)

SKILL_INTERNAL_TOOL_CODES = frozenset(
    {
        "web_search",
        "list_available_skills",
        "load_skill",
        "run_skill_script",
    }
)


@dataclass(frozen=True)
class ToolCatalogItem:
    tool_code: str
    display_name: str
    description: str
    risk_level: str
    built_in: bool = False
    group: str = "general"

    def as_dict(self, *, enabled: bool) -> dict[str, object]:
        return {
            "tool_code": self.tool_code,
            "display_name": self.display_name,
            "description": self.description,
            "risk_level": self.risk_level,
            "enabled": bool(enabled),
            "built_in": self.built_in,
            "group": self.group,
        }


class ToolCatalog:
    """Immutable catalog of user-selectable tools. Not sourced from the database."""

    def __init__(self, items: Iterable[ToolCatalogItem]) -> None:
        ordered = tuple(items)
        codes = [item.tool_code for item in ordered]
        if len(set(codes)) != len(codes):
            raise ValueError("duplicate tool_code in catalog")
        if LEGACY_DISCOVER_LEADS_TOOL_CODE in codes:
            raise ValueError("discover_douyin_leads cannot be a catalog tool_code")
        overlap = set(codes) & SKILL_INTERNAL_TOOL_CODES
        if overlap:
            raise ValueError(f"skill internal tools cannot be catalog items: {sorted(overlap)}")
        self._items = ordered
        self._by_code = MappingProxyType({item.tool_code: item for item in ordered})

    @property
    def items(self) -> tuple[ToolCatalogItem, ...]:
        return self._items

    def get(self, tool_code: str) -> ToolCatalogItem | None:
        return self._by_code.get(resolve_tool_code(tool_code))

    def known_codes(self) -> frozenset[str]:
        return frozenset(self._by_code)


def resolve_tool_code(tool_code: str) -> str:
    code = str(tool_code or "").strip()
    return TOOL_CODE_ALIASES.get(code, code)


def unknown_tool_codes(tool_codes: Iterable[str]) -> list[str]:
    unknown: list[str] = []
    seen: set[str] = set()
    for raw in tool_codes:
        code = str(raw or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        if resolve_tool_code(code) not in SELECTABLE_TOOL_CATALOG.known_codes():
            unknown.append(code)
    return unknown


def normalize_enabled_tool_codes(tool_codes: Iterable[str]) -> list[str]:
    resolved: list[str] = []
    seen: set[str] = set()
    for raw in tool_codes:
        code = resolve_tool_code(str(raw or "").strip())
        if not code or code in seen or code not in SELECTABLE_TOOL_CATALOG.known_codes():
            continue
        seen.add(code)
        resolved.append(code)
    if BUILTIN_TOOL_CODE not in seen:
        resolved.insert(0, BUILTIN_TOOL_CODE)
    return resolved


def enabled_tool_code_set(tool_codes: Iterable[str] | None) -> set[str]:
    return {resolve_tool_code(str(code)) for code in (tool_codes or []) if str(code).strip()}


SELECTABLE_TOOL_CATALOG = ToolCatalog(
    (
        ToolCatalogItem(
            tool_code=BUILTIN_TOOL_CODE,
            display_name="当前时间",
            description="获取当前日期和时间。",
            risk_level="low",
            built_in=True,
            group="builtin",
        ),
        ToolCatalogItem(
            tool_code="get_weather",
            display_name="天气",
            description="获取指定城市的当前天气和气温。",
            risk_level="low",
            group="information",
        ),
        ToolCatalogItem(
            tool_code="search_kb",
            display_name="知识库检索",
            description="检索当前智能体实例知识库。",
            risk_level="low",
            group="knowledge",
        ),
        ToolCatalogItem(
            tool_code="remember_fact",
            display_name="记住事实",
            description="跨对话记住关于用户的长期事实。",
            risk_level="medium",
            group="memory",
        ),
        ToolCatalogItem(
            tool_code="recall_facts",
            display_name="回忆事实",
            description="回忆已记住的用户事实。",
            risk_level="low",
            group="memory",
        ),
        ToolCatalogItem(
            tool_code="generate_image",
            display_name="生成图片",
            description="生成小红书图片，调用前需要人工确认。",
            risk_level="medium",
            group="media",
        ),
        ToolCatalogItem(
            tool_code="generate_video",
            display_name="生成视频",
            description="生成小红书视频，调用前需要人工确认。",
            risk_level="medium",
            group="media",
        ),
        ToolCatalogItem(
            tool_code="send_email",
            display_name="发送邮件",
            description="向配置的邮箱发送邮件。",
            risk_level="high",
            group="communication",
        ),
        ToolCatalogItem(
            tool_code=DISCOVER_LEADS_TOOL_CODE,
            display_name="线索发现",
            description="扫描抖音或小红书指定账号、话题或内容，并通过已绑定工作流真实发送评论或私信。",
            risk_level="high",
            group="leads",
        ),
        ToolCatalogItem(
            tool_code="list_jobs",
            display_name="任务列表",
            description="查看当前智能体实例的任务定义和执行记录。",
            risk_level="low",
            group="jobs",
        ),
        ToolCatalogItem(
            tool_code="cancel_job",
            display_name="取消任务",
            description="停用任务定义或取消一次任务执行。",
            risk_level="medium",
            group="jobs",
        ),
    )
)
