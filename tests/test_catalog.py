from __future__ import annotations

import pytest

from app.catalog import AGENT_CATALOG, get_agent_catalog
from app.tool_catalog import (
    SELECTABLE_TOOL_CATALOG,
    SKILL_INTERNAL_TOOL_CODES,
    resolve_tool_code,
    unknown_tool_codes,
)


def test_douyin_ops_catalog_is_read_only_product_metadata():
    catalog = get_agent_catalog("douyin_ops")
    assert AGENT_CATALOG["douyin_ops"] is catalog
    assert catalog.display_name == "运营助手"
    assert catalog.agent_mode == "single"
    assert catalog.workflows[0].code == "douyin-lead-discovery"
    assert catalog.tools[0].name == "discover_leads"
    assert "真实" in catalog.capability_description
    assert "不能代替真实扫描" in catalog.development_notes
    with pytest.raises(Exception):
        catalog.display_name = "changed"


def test_unknown_catalog_template_is_rejected():
    with pytest.raises(KeyError, match="unsupported agent template"):
        get_agent_catalog("personal_assistant")


def test_custom_catalog_is_minimal_and_supported():
    custom = get_agent_catalog("custom")
    assert custom.template_code == "custom"
    assert custom.workflows == ()
    assert [item.name for item in custom.tools] == ["get_current_datetime"]

def test_selectable_tool_catalog_uses_discover_leads_not_legacy_alias():
    codes = [item.tool_code for item in SELECTABLE_TOOL_CATALOG.items]
    assert "discover_leads" in codes
    assert "discover_douyin_leads" not in codes
    assert resolve_tool_code("discover_douyin_leads") == "discover_leads"
    datetime_item = SELECTABLE_TOOL_CATALOG.get("get_current_datetime")
    assert datetime_item is not None
    assert datetime_item.built_in is True
    assert datetime_item.display_name == "当前时间"
    assert datetime_item.group == "builtin"
    assert datetime_item.risk_level == "low"
    assert all(item.built_in is (item.tool_code == "get_current_datetime") for item in SELECTABLE_TOOL_CATALOG.items)
    assert SKILL_INTERNAL_TOOL_CODES.isdisjoint(codes)
    catalog_names = [item.name for catalog in AGENT_CATALOG.values() for item in catalog.tools]
    assert "discover_leads" in catalog_names
    assert "discover_douyin_leads" not in catalog_names


def test_unknown_tool_code_is_rejected_after_alias_resolution():
    assert unknown_tool_codes(["discover_douyin_leads"]) == []
    assert unknown_tool_codes(["discover_leads", "discover_douyin_leads"]) == []
    assert unknown_tool_codes(["not-a-tool"]) == ["not-a-tool"]
    assert unknown_tool_codes(["load_skill"]) == ["load_skill"]
