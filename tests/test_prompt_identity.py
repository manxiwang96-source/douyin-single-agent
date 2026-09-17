from __future__ import annotations

from pathlib import Path

from app.main import create_app
from app.prompts import SYSTEM_PROMPT


def test_system_prompt_is_personal_assistant():
    assert "个人超级助理" in SYSTEM_PROMPT
    assert "你是小红书运营助手" not in SYSTEM_PROMPT
    assert "不是小红书运营助手" in SYSTEM_PROMPT
    assert "search_kb" in SYSTEM_PROMPT
    assert "【标题】" in SYSTEM_PROMPT
    assert "【正文】" in SYSTEM_PROMPT
    assert "【标签】" in SYSTEM_PROMPT
    assert "明确要求" in SYSTEM_PROMPT
    assert "禁止调用 search_kb" in SYSTEM_PROMPT or "禁止搜" in SYSTEM_PROMPT


def test_fastapi_title_is_personal_assistant(runtime):
    app = create_app(runtime)
    assert app.title == "个人超级助理"


def test_streamlit_title_is_personal_assistant():
    text = Path("ui/streamlit_app.py").read_text(encoding="utf-8")
    assert 'st.title("个人超级助理")' in text
    assert "个人超级助理" in text
    assert "小红书运营助手" not in text
    assert "Xiaohongshu Ops Assistant" not in text