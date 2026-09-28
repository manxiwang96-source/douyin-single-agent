from __future__ import annotations

from app.main import create_app
from app.prompts import SYSTEM_PROMPT


def test_system_prompt_is_cross_platform_operations_assistant():
    assert "运营助手" in SYSTEM_PROMPT
    assert "抖音和小红书" in SYSTEM_PROMPT
    assert "会真实发送" in SYSTEM_PROMPT
    assert "discover_leads" in SYSTEM_PROMPT
    assert "douyin-lead-discovery" in SYSTEM_PROMPT
    assert "实例知识库" in SYSTEM_PROMPT
    assert "不能代替真实扫描" in SYSTEM_PROMPT
    assert "lead_ok" in SYSTEM_PROMPT
    assert "job_status" in SYSTEM_PROMPT
    assert "written" in SYSTEM_PROMPT
    assert "message_details" in SYSTEM_PROMPT
    assert "discover_douyin_leads" not in SYSTEM_PROMPT
    assert "只能抖音" not in SYSTEM_PROMPT
    assert "同一账号" not in SYSTEM_PROMPT
    assert "小红书【标题】【正文】【标签】模板" not in SYSTEM_PROMPT


def test_fastapi_title_is_operations_assistant(runtime):
    app = create_app(runtime)
    assert app.title == "运营助手"
