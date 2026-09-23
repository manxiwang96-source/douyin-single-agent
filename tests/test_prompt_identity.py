from __future__ import annotations

from pathlib import Path

from app.main import create_app
from app.prompts import SYSTEM_PROMPT


def test_system_prompt_is_douyin_operations_assistant():
    assert "抖音运营助手" in SYSTEM_PROMPT
    assert "会真实发送" in SYSTEM_PROMPT
    assert "discover_douyin_leads" in SYSTEM_PROMPT
    assert "douyin-lead-discovery" in SYSTEM_PROMPT
    assert "实例知识库" in SYSTEM_PROMPT
    assert "不能代替真实扫描" in SYSTEM_PROMPT
    assert "小红书【标题】【正文】【标签】模板" in SYSTEM_PROMPT
    assert "【标题】" not in SYSTEM_PROMPT.replace("小红书【标题】【正文】【标签】模板", "")
    assert "不是小红书运营助手" not in SYSTEM_PROMPT
    assert "已有 video_id 时不要再要 keyword" in SYSTEM_PROMPT
    assert "comment,message" in SYSTEM_PROMPT
    assert "comment,dm" in SYSTEM_PROMPT
    assert "然后立刻调用 discover_douyin_leads" in SYSTEM_PROMPT
    assert "job_status" in SYSTEM_PROMPT
    assert "written" in SYSTEM_PROMPT
    assert "message_details" in SYSTEM_PROMPT


def test_fastapi_title_is_douyin_operations_assistant(runtime):
    app = create_app(runtime)
    assert app.title == "抖音运营助手"


def test_streamlit_title_is_douyin_operations_assistant():
    text = Path("ui/streamlit_app.py").read_text(encoding="utf-8")
    assert 'st.title("抖音运营助手")' in text
    assert "抖音运营助手" in text
    assert "小红书运营助手" not in text
    assert "Xiaohongshu Ops Assistant" not in text
