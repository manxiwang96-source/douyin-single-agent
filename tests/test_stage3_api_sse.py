from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from app.skills import SearchCandidate
from tests.http_helpers import create_and_open, make_client, parse_sse_events, post_chat, register_and_login
from tests.fakes import ai_text, ai_tool


def _register_external(runtime, tmp_path: Path):
    source = tmp_path / "external-skill"
    source.mkdir()
    (source / "SKILL.md").write_text("# External\nUse approved script only.", encoding="utf-8")
    (source / "main.py").write_text("print('api-safe')", encoding="utf-8")
    runtime.skill_service.search_provider.register(SearchCandidate(
        candidate_id="api-external-skill",
        name="API External Skill",
        description="continuous approval test",
        source_type="github",
        source_uri=f"file://{source}",
        source_ref="immutable-api-ref",
        license="MIT",
        author="test",
        version="1.0.0",
    ))
    return source


def _create_custom_with_skill(runtime, client, tmp_path: Path):
    created = client.post(
        "/v1/agent-instances",
        json={"template_code": "custom", "title": "api-skill", "intro": "ops"},
    )
    assert created.status_code == 201, created.text
    instance = created.json()
    agent_id = instance["agent_instance_id"]
    found = client.post("/v1/skills/discovery/search", json={"query": "API External", "limit": 10})
    assert found.status_code == 200, found.text
    candidate_id = found.json()["items"][0]["candidate_id"]
    started = client.post("/v1/skills/imports", json={"candidate_id": candidate_id, "target_agent_instance_id": agent_id})
    assert started.status_code == 201, started.text
    import_id = started.json()["import_id"]
    confirmed = client.post(f"/v1/skills/imports/{import_id}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    skill_id = confirmed.json()["skill_id"]
    configured = client.put(
        f"/v1/agent-instances/{agent_id}/config/draft/skills",
        json={"skill_ids": [skill_id]},
    )
    assert configured.status_code == 200, configured.text
    rejected = client.put(
        f"/v1/agent-instances/{agent_id}/config/draft/tools",
        json={"enabled_tool_codes": ["load_skill", "run_skill_script"]},
    )
    assert rejected.status_code == 400, rejected.text
    record = runtime.business_repo.get_agent_instance(UUID(agent_id))
    draft = runtime.skill_service.ensure_config(record.user_id, record.agent_instance_id)
    runtime.skill_service.repository.update_config(
        draft["config_version_id"],
        enabled_tool_codes=["get_current_datetime", "load_skill", "run_skill_script"],
    )
    published = client.post(f"/v1/agent-instances/{agent_id}/config/publish")
    assert published.status_code == 200, published.text
    opened = client.post(f"/v1/agent-instances/{agent_id}/open")
    assert opened.status_code == 200, opened.text
    return {**instance, **opened.json()}, confirmed.json()


def test_media_sse_emits_approval_and_rejects_invalid_or_duplicate_resume(runtime, llm, image_client):
    llm.responses = [ai_tool("generate_image", {"prompt": "sse bottle"}), ai_text("done")]
    client = make_client(runtime)
    register_and_login(client, login_name="sse-media")
    opened = create_and_open(client, title="sse-media")
    thread_id = opened["thread_id"]
    response = client.post(f"/v1/threads/{thread_id}/messages", json={"content": "draw"})
    assert response.status_code == 200
    events = parse_sse_events(response.text)
    assert any(item["event"] == "approval" and item["data"]["type"] == "review_media" for item in events)
    assert image_client.calls == []
    invalid = client.post(f"/v1/threads/{thread_id}/resume", json={"action": "not-an-option"})
    assert invalid.status_code == 400
    resumed = client.post(f"/v1/threads/{thread_id}/resume", json={"action": "approve"})
    assert resumed.status_code == 200
    assert len(image_client.calls) == 1
    assert image_client.calls[0][0] == "sse bottle"
    duplicate = client.post(f"/v1/threads/{thread_id}/resume", json={"action": "approve"})
    assert duplicate.status_code == 409


def test_skill_script_http_sse_requires_skill_tool_script_approvals_in_order(runtime, llm, tmp_path):
    _register_external(runtime, tmp_path)
    client = make_client(runtime)
    register_and_login(client, login_name="sse-skill")
    opened, skill = _create_custom_with_skill(runtime, client, tmp_path)
    thread_id = opened["thread_id"]
    skill_id = skill["skill_id"]
    llm.responses = [
        ai_tool("run_skill_script", {"skill_id": skill_id, "script_path": "main.py", "input_text": "hello"}),
        ai_text("script complete"),
    ]
    first = client.post(f"/v1/threads/{thread_id}/messages", json={"content": "run script"})
    assert first.status_code == 200
    first_events = parse_sse_events(first.text)
    first_approval = next(item["data"] for item in first_events if item["event"] == "approval")
    assert first_approval["type"] == "review_skill"
    assert first_approval["skill_id"] == skill_id
    assert first_approval["options"] == ["approve_once", "approve_session", "deny"]
    bad = client.post(f"/v1/threads/{thread_id}/resume", json={"action": "approve"})
    assert bad.status_code == 400
    second = client.post(f"/v1/threads/{thread_id}/resume", json={"action": "approve_once"})
    assert second.status_code == 200
    second_approval = next(item["data"] for item in parse_sse_events(second.text) if item["event"] == "approval")
    assert second_approval["type"] == "review_tool"
    assert second_approval["tool"] == "run_skill_script"
    third = client.post(f"/v1/threads/{thread_id}/resume", json={"action": "approve_once"})
    assert third.status_code == 200
    third_events = parse_sse_events(third.text)
    third_approval = next(item["data"] for item in third_events if item["event"] == "approval")
    assert third_approval["type"] == "review_skill_script"
    assert third_approval["script_path"] == "main.py"
    fourth = client.post(f"/v1/threads/{thread_id}/resume", json={"action": "approve_once"})
    assert fourth.status_code == 200
    fourth_body = next(item["data"] for item in parse_sse_events(fourth.text) if item["event"] == "thread")
    assert fourth_body["status"] == "idle"
    body = fourth_body
    assert body["messages"][-1]["content"] == "script complete"
    duplicate = client.post(f"/v1/threads/{thread_id}/resume", json={"action": "approve_once"})
    assert duplicate.status_code == 409
    assert len([item for item in runtime.tool_audit_repository.list_for_scope(
        user_id=UUID(client.get("/v1/me").json()["user_id"]),
        agent_instance_id=UUID(opened["agent_instance_id"]),
        config_version_id=runtime.skill_service.get_effective_config(
            UUID(client.get("/v1/me").json()["user_id"]),
            UUID(opened["agent_instance_id"]),
            prefer_draft=False,
        )["config_version_id"],
        thread_id=thread_id,
    ) if item.tool_code == "run_skill_script" and item.execution_status == "succeeded"]) == 1


