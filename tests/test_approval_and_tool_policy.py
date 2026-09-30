from __future__ import annotations

import json
from uuid import UUID, uuid4

from langchain_core.messages import HumanMessage

from app.approvals import ApprovalManager
from app.graph import interrupt_payload
from app.graph import build_graph
from app.skill_runtime import approved_resource_codes, build_skill_runtime_context, select_tools
from tests.fakes import ai_text, ai_tool
from tests.graph_helpers import graph_config
from tests.http_helpers import create_and_open, make_client, register_and_login


def test_approval_kinds_are_independent_and_scope_isolated():
    manager = ApprovalManager()
    user = uuid4()
    agent = uuid4()
    config = uuid4()
    other_thread = "thread-other"
    skill = manager.repository.request(
        user_id=user, agent_instance_id=agent, config_version_id=config,
        thread_id="thread-1", approval_kind="skill", resource_code="external-skill",
    )
    manager.repository.decide(skill.approval_id, user_id=user, approved=True)
    assert manager.ensure(user_id=user, agent_instance_id=agent, config_version_id=config, thread_id="thread-1", approval_kind="skill", resource_code="external-skill")
    assert not manager.ensure(user_id=user, agent_instance_id=agent, config_version_id=config, thread_id="thread-1", approval_kind="tool", resource_code="send_email")
    assert not manager.ensure(user_id=user, agent_instance_id=agent, config_version_id=config, thread_id=other_thread, approval_kind="skill", resource_code="external-skill")
    assert not manager.ensure(user_id=uuid4(), agent_instance_id=agent, config_version_id=config, thread_id="thread-1", approval_kind="skill", resource_code="external-skill")


def test_skill_approval_does_not_grant_tool_or_script(runtime):
    user = uuid4()
    agent = uuid4()
    config = runtime.skill_service.ensure_config(user, agent)
    lead = runtime.skill_repository.find_skill_by_code("lead-operations", user_id=user)
    runtime.skill_service.set_config_skills(user, agent, [lead.skill_id])
    thread_id = "approval-thread"
    context = build_skill_runtime_context(runtime.skill_service, user_id=user, agent_instance_id=agent, approvals=runtime.approval_manager, thread_id=thread_id, config_version_id=config["config_version_id"])
    assert context.skill_codes == ()
    approval = runtime.approval_manager.repository.request(
        user_id=user, agent_instance_id=agent, config_version_id=config["config_version_id"],
        thread_id=thread_id, approval_kind="skill", resource_code="lead-operations",
    )
    runtime.approval_manager.repository.decide(approval.approval_id, user_id=user, approved=True)
    context = build_skill_runtime_context(runtime.skill_service, user_id=user, agent_instance_id=agent, approvals=runtime.approval_manager, thread_id=thread_id, config_version_id=config["config_version_id"])
    assert context.skill_codes == ("lead-operations",)
    assert approved_resource_codes(runtime.approval_manager, context=context, thread_id=thread_id, approval_kind="tool", candidates=["send_email"]) == set()
    assert approved_resource_codes(runtime.approval_manager, context=context, thread_id=thread_id, approval_kind="script", candidates=["lead-operations/main.py"]) == set()


def test_scoped_graph_model_and_toolnode_have_same_tools(runtime, llm):
    selected = select_tools(runtime.tools, ["get_current_datetime"])
    graph = runtime.graph_for_tool_codes(["get_current_datetime"])
    llm.responses = [ai_text("ok")]
    graph.invoke({"messages": []}, {"configurable": {"thread_id": "tool-policy"}})
    assert {tool.name for tool in llm.bound_tools} == {tool.name for tool in selected}
    tool_node = graph.get_graph().nodes["tools"].data
    assert set(tool_node._tools_by_name) == {tool.name for tool in selected}
    topology = set(graph.get_graph().nodes) - {"__start__", "__end__"}
    assert topology == {"chatbot", "tools"}


def test_approval_api_requires_scope_and_keeps_kinds_independent(runtime):
    client = make_client(runtime)
    register_and_login(client)
    opened = create_and_open(client, title="approval-api")
    config = client.get(f"/v1/agent-instances/{opened['agent_instance_id']}/config").json()
    body = {
        "thread_id": opened["thread_id"],
        "config_version_id": config["config_version_id"],
        "approval_kind": "skill",
        "resource_code": "external-skill",
    }
    created = client.post(f"/v1/agent-instances/{opened['agent_instance_id']}/approvals", json=body)
    assert created.status_code == 201, created.text
    approval_id = created.json()["approval_id"]
    decided = client.post(f"/v1/approvals/{approval_id}/decision", json={"approved": True, "reason": "test"})
    assert decided.status_code == 200
    assert decided.json()["status"] == "approved"
    tool_request = {**body, "approval_kind": "tool", "resource_code": "send_email"}
    tool_created = client.post(f"/v1/agent-instances/{opened['agent_instance_id']}/approvals", json=tool_request)
    assert tool_created.status_code == 201
    listed = client.get(f"/v1/agent-instances/{opened['agent_instance_id']}/approvals", params={"thread_id": opened["thread_id"]})
    assert {item["approval_kind"] for item in listed.json()["items"]} == {"skill", "tool"}
    assert listed.json()["items"][0]["config_version_id"] == config["config_version_id"]


def _send_email_tool(runtime):
    return next(item for item in runtime.tools if item.name == "send_email")


def test_send_email_without_scope_does_not_send(runtime, email_client):
    result = json.loads(_send_email_tool(runtime).invoke({"subject": "x", "body": "y"}))
    assert result["ok"] is False
    assert result["error"] == "missing instance context"
    assert email_client.sends == []


def test_send_email_requires_tool_hitl_skill_approval_does_not_bypass(runtime, llm, email_client):
    config = graph_config("email-skill-bypass", config_version_id=str(uuid4()))
    values = config["configurable"]
    record = runtime.approval_manager.repository.request(
        user_id=UUID(str(values["user_id"])),
        agent_instance_id=UUID(str(values["agent_instance_id"])),
        config_version_id=UUID(str(values["config_version_id"])),
        thread_id=str(values["thread_id"]),
        approval_kind="skill",
        resource_code="external-skill",
        approval_scope="session",
    )
    runtime.approval_manager.repository.decide(record.approval_id, user_id=UUID(str(values["user_id"])), approved=True)
    llm.responses = [
        ai_tool("send_email", {"subject": "secret", "body": "payload"}),
        ai_text("blocked"),
    ]
    runtime.graph.invoke({"messages": [HumanMessage(content="发邮件")]}, config)
    pending = interrupt_payload(runtime.graph.get_state(config))
    assert pending is not None
    assert pending["type"] == "review_tool"
    assert pending["tool"] == "send_email"
    assert email_client.sends == []


def test_send_email_always_grant_sends_without_new_interrupt(runtime, llm, email_client):
    config = graph_config("email-always", config_version_id=str(uuid4()))
    values = config["configurable"]
    user_id = UUID(str(values["user_id"]))
    record = runtime.approval_manager.repository.request(
        user_id=user_id,
        agent_instance_id=UUID(str(values["agent_instance_id"])),
        config_version_id=UUID(str(values["config_version_id"])),
        thread_id=str(values["thread_id"]),
        approval_kind="tool",
        resource_code="send_email",
        approval_scope="always",
    )
    runtime.approval_manager.repository.decide(record.approval_id, user_id=user_id, approved=True)
    llm.responses = [
        ai_tool("send_email", {"subject": "granted", "body": "ok"}),
        ai_text("已发送"),
    ]
    result = runtime.graph.invoke({"messages": [HumanMessage(content="发邮件")]}, config)
    assert interrupt_payload(runtime.graph.get_state(config)) is None
    assert email_client.sends
    assert email_client.sends[0]["subject"] == "granted"
    assert result["messages"][-1].content == "已发送"
    assert not runtime.approval_manager.ensure(
        user_id=user_id,
        agent_instance_id=UUID(str(values["agent_instance_id"])),
        config_version_id=UUID(str(values["config_version_id"])),
        thread_id=str(values["thread_id"]),
        approval_kind="tool",
        resource_code="send_email",
    )

