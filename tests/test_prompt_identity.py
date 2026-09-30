from __future__ import annotations

from app.graph import compose_system_prompt
from app.main import create_app
from app.prompts import CUSTOM_SAFETY_PREFIX, SYSTEM_PROMPT
from tests.fakes import ai_text
from tests.http_helpers import create_and_open, make_client, register_and_login


def test_system_prompt_is_cross_platform_operations_assistant():
    assert "运营助手" in SYSTEM_PROMPT
    assert "抖音和小红书" in SYSTEM_PROMPT
    assert "会真实发送" in SYSTEM_PROMPT
    assert "discover_leads" in SYSTEM_PROMPT
    assert "comment,message" in SYSTEM_PROMPT
    assert "like" in SYSTEM_PROMPT
    assert "collect" in SYSTEM_PROMPT
    assert "max_comments" in SYSTEM_PROMPT
    assert "reply_limit" in SYSTEM_PROMPT
    assert "message_limit" in SYSTEM_PROMPT
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


def test_custom_safety_prefix_is_not_ops_prompt():
    assert "你是运营助手" not in CUSTOM_SAFETY_PREFIX
    assert "会真实发送" not in CUSTOM_SAFETY_PREFIX
    assert "discover_leads" not in CUSTOM_SAFETY_PREFIX
    assert "discover_douyin_leads" not in CUSTOM_SAFETY_PREFIX


def test_compose_system_prompt_keeps_custom_and_douyin_identities_apart():
    custom = compose_system_prompt(template_code="custom", system_prompt="CUSTOM_INSTANCE_PROMPT_MARKER")
    assert CUSTOM_SAFETY_PREFIX.strip() in custom
    assert "CUSTOM_INSTANCE_PROMPT_MARKER" in custom
    assert "你是运营助手" not in custom
    assert "会真实发送" not in custom
    assert "discover_leads" not in custom
    douyin = compose_system_prompt(template_code="douyin_ops", system_prompt="DOUYIN_EXTRA_PROMPT")
    assert "你是运营助手" in douyin
    assert "会真实发送" in douyin
    assert "DOUYIN_EXTRA_PROMPT" in douyin
    assert CUSTOM_SAFETY_PREFIX.strip() not in douyin


def test_custom_chat_uses_safety_prefix_not_ops_prompt(runtime, llm):
    client = make_client(runtime)
    register_and_login(client, "prompt-custom-owner", "password123")
    created = client.post(
        "/v1/agent-instances",
        json={"template_code": "custom", "title": "prompt-custom", "intro": "prompt-custom"},
    )
    assert created.status_code == 201, created.text
    instance_id = created.json()["agent_instance_id"]
    saved = client.put(
        f"/v1/agent-instances/{instance_id}/config/draft",
        json={"system_prompt": "CUSTOM_INSTANCE_PROMPT_MARKER"},
    )
    assert saved.status_code == 200, saved.text
    published = client.post(f"/v1/agent-instances/{instance_id}/config/publish")
    assert published.status_code == 200, published.text
    opened = client.post(f"/v1/agent-instances/{instance_id}/open")
    assert opened.status_code == 200, opened.text
    llm.responses = [ai_text("custom-ok")]
    response = client.post(
        f"/v1/threads/{opened.json()['thread_id']}/messages",
        json={"content": "hello custom"},
    )
    assert response.status_code == 200, response.text
    system = llm.calls[0][0].content
    assert CUSTOM_SAFETY_PREFIX.strip() in system
    assert "CUSTOM_INSTANCE_PROMPT_MARKER" in system
    assert "你是运营助手" not in system
    assert "会真实发送" not in system
    assert "discover_leads" not in system


def test_douyin_chat_keeps_ops_system_prompt(runtime, llm):
    client = make_client(runtime)
    register_and_login(client, "prompt-douyin-owner", "password123")
    opened = create_and_open(client, title="prompt-douyin", template_code="douyin_ops")
    llm.responses = [ai_text("douyin-ok")]
    response = client.post(
        f"/v1/threads/{opened['thread_id']}/messages",
        json={"content": "hello douyin"},
    )
    assert response.status_code == 200, response.text
    system = llm.calls[0][0].content
    assert "你是运营助手" in system
    assert "会真实发送" in system
    assert "discover_leads" in system
    assert CUSTOM_SAFETY_PREFIX.strip() not in system
