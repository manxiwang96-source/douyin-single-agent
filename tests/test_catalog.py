from __future__ import annotations

import pytest

from app.catalog import AGENT_CATALOG, get_agent_catalog


def test_douyin_ops_catalog_is_read_only_product_metadata():
    catalog = get_agent_catalog("douyin_ops")
    assert AGENT_CATALOG["douyin_ops"] is catalog
    assert catalog.display_name == "抖音运营助手"
    assert catalog.agent_mode == "single"
    assert catalog.workflows[0].code == "douyin-lead-discovery"
    assert catalog.tools[0].name == "discover_douyin_leads"
    assert "真实" in catalog.capability_description
    assert "不能代替真实扫描" in catalog.development_notes
    with pytest.raises(Exception):
        catalog.display_name = "changed"


def test_unknown_catalog_template_is_rejected():
    with pytest.raises(KeyError, match="unsupported agent template"):
        get_agent_catalog("personal_assistant")
