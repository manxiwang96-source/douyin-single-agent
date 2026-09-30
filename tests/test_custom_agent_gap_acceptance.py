from __future__ import annotations

from pathlib import Path

from app.plaza import DOUYIN_OPS_DEFAULT_TOOL_CODES
from app.prompts import CUSTOM_SAFETY_PREFIX
from app.tool_catalog import DISCOVER_LEADS_TOOL_CODE, LEGACY_DISCOVER_LEADS_TOOL_CODE, resolve_tool_code
from tests.fakes import ai_text, ai_tool
from tests.http_helpers import make_client, post_chat, register_and_login

ROOT = Path(__file__).resolve().parents[1]


def _create(client, template_code: str, title: str) -> dict:
    response = client.post(
        "/v1/agent-instances",
        json={"template_code": template_code, "title": title, "intro": title},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _published(client, instance_id: str) -> dict:
    versions = client.get(f"/v1/agent-instances/{instance_id}/config/versions")
    assert versions.status_code == 200, versions.text
    published = [item for item in versions.json()["items"] if item["status"] == "published"]
    assert published, versions.json()
    return max(published, key=lambda item: item["version_no"])


def _bound_names(llm) -> set[str]:
    return {getattr(tool, "name", "") for tool in (llm.bound_tools or [])}


def test_w35_create_publishes_and_open_pins_published_not_409(runtime):
    client = make_client(runtime)
    register_and_login(client, "w35-create-owner", "password123")

    custom = _create(client, "custom", "w35-custom")
    custom_published = _published(client, custom["agent_instance_id"])
    assert custom_published["enabled_tool_codes"] == ["get_current_datetime"]
    assert LEGACY_DISCOVER_LEADS_TOOL_CODE not in custom_published["enabled_tool_codes"]
    custom_open = client.post(f"/v1/agent-instances/{custom['agent_instance_id']}/open")
    assert custom_open.status_code == 200, custom_open.text
    assert custom_open.status_code != 409
    assert custom_open.json()["config_version_id"] == custom_published["config_version_id"]
    custom_thread = runtime.business_repo.get_app_thread(custom_open.json()["thread_id"])
    assert custom_thread.thread_kind == "official"

    douyin = _create(client, "douyin_ops", "w35-douyin")
    douyin_published = _published(client, douyin["agent_instance_id"])
    codes = douyin_published["enabled_tool_codes"]
    assert codes[0] == "get_current_datetime"
    for code in DOUYIN_OPS_DEFAULT_TOOL_CODES:
        assert code in codes
    assert DISCOVER_LEADS_TOOL_CODE in codes
    assert LEGACY_DISCOVER_LEADS_TOOL_CODE not in codes
    douyin_open = client.post(f"/v1/agent-instances/{douyin['agent_instance_id']}/open")
    assert douyin_open.status_code == 200, douyin_open.text
    assert douyin_open.status_code != 409
    assert douyin_open.json()["config_version_id"] == douyin_published["config_version_id"]
    douyin_thread = runtime.business_repo.get_app_thread(douyin_open.json()["thread_id"])
    assert douyin_thread.thread_kind == "official"


def test_w35_douyin_chat_binds_discover_leads_and_hitl_resume_is_sse(runtime, llm):
    client = make_client(runtime)
    register_and_login(client, "w35-dify-hitl", "password123")
    douyin = _create(client, "douyin_ops", "w35-dify-hitl")
    opened = client.post(f"/v1/agent-instances/{douyin['agent_instance_id']}/open")
    assert opened.status_code == 200, opened.text
    thread_id = opened.json()["thread_id"]

    llm.responses = [ai_text("ops-ok")]
    first = post_chat(client, f"/v1/threads/{thread_id}/messages", json={"content": "hello ops"})
    assert first.status_code == 200, first.text
    assert "text/event-stream" in (first.headers.get("content-type") or "")
    names = _bound_names(llm)
    assert DISCOVER_LEADS_TOOL_CODE in names
    assert LEGACY_DISCOVER_LEADS_TOOL_CODE not in names
    assert resolve_tool_code(LEGACY_DISCOVER_LEADS_TOOL_CODE) == DISCOVER_LEADS_TOOL_CODE

    llm.responses = [
        ai_tool("generate_image", {"prompt": "bottle"}),
        ai_text("image ready"),
    ]
    interrupted = post_chat(client, f"/v1/threads/{thread_id}/messages", json={"content": "draw"})
    assert interrupted.status_code == 200, interrupted.text
    assert interrupted.json()["status"] == "interrupted"
    blocked = client.post(f"/v1/threads/{thread_id}/messages", json={"content": "again"})
    assert blocked.status_code == 409
    resumed = post_chat(
        client,
        f"/v1/threads/{thread_id}/resume",
        json={"action": "approve", "prompt": "bottle", "params": {}},
    )
    assert resumed.status_code == 200, resumed.text
    assert "text/event-stream" in (resumed.headers.get("content-type") or "")
    assert [item["event"] for item in resumed.events][-1] == "thread"
    assert resumed.json()["status"] == "idle"


def test_w35_debug_sse_does_not_pollute_official(runtime, llm):
    client = make_client(runtime)
    register_and_login(client, "w35-debug-owner", "password123")
    custom = _create(client, "custom", "w35-debug")
    instance_id = custom["agent_instance_id"]
    official = client.post(f"/v1/agent-instances/{instance_id}/open")
    assert official.status_code == 200, official.text
    official_id = official.json()["thread_id"]
    debug = client.post(f"/v1/agent-instances/{instance_id}/debug-open")
    assert debug.status_code == 200, debug.text
    assert debug.json()["thread_kind"] == "debug"
    debug_id = debug.json()["thread_id"]
    assert debug_id != official_id
    llm.responses = [ai_text("debug-ok")]
    streamed = post_chat(
        client,
        f"/v1/threads/{debug_id}/messages",
        json={"content": "debug hi"},
    )
    assert streamed.status_code == 200, streamed.text
    assert "text/event-stream" in (streamed.headers.get("content-type") or "")
    official_again = client.post(f"/v1/agent-instances/{instance_id}/open")
    assert official_again.json()["thread_id"] == official_id
    assert runtime.business_repo.get_app_thread(official_id).thread_kind == "official"
    assert runtime.business_repo.get_app_thread(debug_id).thread_kind == "debug"


def test_w35_cross_instance_isolation(runtime):
    alice = make_client(runtime)
    register_and_login(alice, "w35-alice", "password123")
    first = _create(alice, "custom", "alice-one")
    second = _create(alice, "douyin_ops", "alice-two")
    assert first["agent_instance_id"] != second["agent_instance_id"]
    bob = make_client(runtime)
    register_and_login(bob, "w35-bob", "password123")
    assert bob.get("/v1/agent-instances").json()["items"] == []
    assert bob.post(f"/v1/agent-instances/{first['agent_instance_id']}/open").status_code == 404
    assert bob.get(f"/v1/agent-instances/{second['agent_instance_id']}/sidebar").status_code == 404
    alice_open = alice.post(f"/v1/agent-instances/{first['agent_instance_id']}/open")
    assert alice_open.status_code == 200, alice_open.text
    assert bob.post(
        f"/v1/threads/{alice_open.json()['thread_id']}/messages",
        json={"content": "hi"},
    ).status_code == 404


def test_w35_custom_prompt_prefix_is_not_ops_identity(runtime, llm):
    client = make_client(runtime)
    register_and_login(client, "w35-prompt-owner", "password123")
    custom = _create(client, "custom", "w35-prompt")
    instance_id = custom["agent_instance_id"]
    saved = client.put(
        f"/v1/agent-instances/{instance_id}/config/draft",
        json={"system_prompt": "W35_CUSTOM_PROMPT_MARKER"},
    )
    assert saved.status_code == 200, saved.text
    published = client.post(f"/v1/agent-instances/{instance_id}/config/publish")
    assert published.status_code == 200, published.text
    opened = client.post(f"/v1/agent-instances/{instance_id}/open")
    assert opened.status_code == 200, opened.text
    llm.responses = [ai_text("custom-ok")]
    response = post_chat(
        client,
        f"/v1/threads/{opened.json()['thread_id']}/messages",
        json={"content": "hello custom"},
    )
    assert response.status_code == 200, response.text
    system = llm.calls[0][0].content
    assert CUSTOM_SAFETY_PREFIX.strip() in system
    assert "W35_CUSTOM_PROMPT_MARKER" in system
    assert "你是运营助手" not in system
    assert "会真实发送" not in system
    assert DISCOVER_LEADS_TOOL_CODE not in system


def test_w35_architecture_records_gap_fill():
    text = (ROOT / "memory-bank" / "architecture.md").read_text(encoding="utf-8")
    required = [
        "agent_config_tools",
        "agent_config_knowledge_documents",
        "agent_skills",
        "thread_kind",
        "discover_leads",
        "CUSTOM_SAFETY_PREFIX",
        "debug-open",
        "publish_default_agent_config",
        "tool_catalog",
    ]
    missing = [item for item in required if item not in text]
    assert missing == [], missing
    assert "PublishedConfigNotFound" in text

