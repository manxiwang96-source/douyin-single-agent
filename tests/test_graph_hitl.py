from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from app.graph import interrupt_payload
from tests.fakes import ai_text, ai_tool
from tests.graph_helpers import graph_config


def test_graph_uses_tutorial_nodes(runtime):
    nodes = set(runtime.graph.get_graph().nodes)
    assert "chatbot" in nodes
    assert "tools" in nodes
    assert "review_media" not in nodes
    assert "run_media" not in nodes


def test_bind_tools_disables_parallel_calls(runtime, llm):
    llm.responses = [ai_text("先告诉我产品是什么")]
    config = graph_config("plain")
    runtime.graph.invoke({"messages": [HumanMessage(content="你好")]}, config)
    assert llm.bind_kwargs.get("parallel_tool_calls") is False


def test_search_kb_runs_without_interrupt(runtime, llm):
    llm.responses = [
        ai_tool("search_kb", {"query": "标题规范", "k": 4}),
        ai_text("【标题】春季补水【正文】先结论【标签】#护肤"),
    ]
    config = graph_config("kb")
    result = runtime.graph.invoke(
        {"messages": [HumanMessage(content="帮我写一条笔记")]},
        config,
    )
    snapshot = runtime.graph.get_state(config)
    assert interrupt_payload(snapshot) is None
    assert result["messages"][-1].content.startswith("【标题】")


def test_image_interrupt_approve_calls_client(runtime, llm, image_client):
    llm.responses = [
        ai_tool("generate_image", {"prompt": "3:4 red bottle"}),
        ai_text("已生成配图"),
    ]
    config = graph_config("img-approve")
    runtime.graph.invoke(
        {"messages": [HumanMessage(content="请配一张图")]},
        config,
    )
    snapshot = runtime.graph.get_state(config)
    pending = interrupt_payload(snapshot)
    assert pending is not None
    assert pending["type"] == "review_media"
    assert pending["tool"] == "generate_image"
    assert pending["params"]["quality"] == "low"
    assert pending["params"]["size"] == "1024x1536"
    assert image_client.calls == []

    result = runtime.graph.invoke(
        Command(resume={"action": "approve", "prompt": "edited bottle", "params": {"quality": "low"}}),
        config,
    )
    assert image_client.calls
    assert image_client.calls[0][0] == "edited bottle"
    assert result.get("last_image_path")
    assert "outputs" in result["last_image_path"].replace("\\", "/")
    assert result["messages"][-1].content == "已生成配图"


def test_image_skip_does_not_call_client(runtime, llm, image_client):
    llm.responses = [
        ai_tool("generate_image", {"prompt": "skip me"}),
        ai_text("已跳过配图"),
    ]
    config = graph_config("img-skip")
    runtime.graph.invoke(
        {"messages": [HumanMessage(content="请配图")]},
        config,
    )
    runtime.graph.invoke(Command(resume={"action": "skip"}), config)
    assert image_client.calls == []
    snapshot = runtime.graph.get_state(config)
    assert interrupt_payload(snapshot) is None
    assert snapshot.values.get("last_image_path") in {None, ""}


def test_video_interrupt_approve_calls_client(runtime, llm, video_client):
    llm.responses = [
        ai_tool("generate_video", {"prompt": "9:16 pour"}),
        ai_text("已生成视频"),
    ]
    config = graph_config("vid-approve")
    runtime.graph.invoke(
        {"messages": [HumanMessage(content="请做视频")]},
        config,
    )
    pending = interrupt_payload(runtime.graph.get_state(config))
    assert pending["tool"] == "generate_video"
    assert pending["params"]["duration"] == 2
    assert pending["params"]["resolution"] == "480P"
    result = runtime.graph.invoke(Command(resume={"action": "approve"}), config)
    assert video_client.calls
    assert result.get("last_video_path")
    assert result["messages"][-1].content == "已生成视频"

def test_ainvoke_uses_async_chatbot_path(runtime, llm):
    llm.responses = [ai_text("你好")]
    result = asyncio.run(
        runtime.graph.ainvoke(
            {"messages": [HumanMessage(content="hi")]},
            graph_config("async-chatbot"),
        )
    )
    assert result["messages"][-1].content == "你好"


def _email_graph_config(thread_id: str):
    return graph_config(thread_id, config_version_id=str(uuid4()))


def _tool_scope(config):
    values = config["configurable"]
    return {
        "user_id": UUID(str(values["user_id"])),
        "agent_instance_id": UUID(str(values["agent_instance_id"])),
        "config_version_id": UUID(str(values["config_version_id"])),
        "thread_id": str(values["thread_id"]),
        "approval_kind": "tool",
        "resource_code": "send_email",
    }


def test_send_email_interrupt_approve_calls_client(runtime, llm, email_client):
    llm.responses = [
        ai_tool("send_email", {"subject": "hello", "body": "world"}),
        ai_text("已发送邮件"),
    ]
    config = _email_graph_config("email-approve")
    runtime.graph.invoke(
        {"messages": [HumanMessage(content="发封邮件")]},
        config,
    )
    pending = interrupt_payload(runtime.graph.get_state(config))
    assert pending is not None
    assert pending["type"] == "review_tool"
    assert pending["tool"] == "send_email"
    assert pending["subject"] == "hello"
    assert pending["options"] == ["approve_once", "approve_session", "deny"]
    assert email_client.sends == []

    result = runtime.graph.invoke(Command(resume={"action": "approve_once"}), config)
    assert email_client.sends
    assert email_client.sends[0]["subject"] == "hello"
    assert email_client.sends[0]["body"] == "world"
    assert result["messages"][-1].content == "已发送邮件"
    assert not runtime.approval_manager.ensure(**_tool_scope(config))


def test_send_email_deny_does_not_call_client(runtime, llm, email_client):
    llm.responses = [
        ai_tool("send_email", {"subject": "skip me", "body": "nope"}),
        ai_text("已拒绝发送"),
    ]
    config = _email_graph_config("email-deny")
    runtime.graph.invoke(
        {"messages": [HumanMessage(content="发邮件")]},
        config,
    )
    result = runtime.graph.invoke(Command(resume={"action": "deny"}), config)
    assert email_client.sends == []
    assert interrupt_payload(runtime.graph.get_state(config)) is None
    assert "tool approval denied" in result["messages"][-2].content
    assert result["messages"][-1].content == "已拒绝发送"


def test_send_email_session_approval_allows_second_send(runtime, llm, email_client):
    llm.responses = [
        ai_tool("send_email", {"subject": "one", "body": "a"}),
        ai_text("已发送1"),
        ai_tool("send_email", {"subject": "two", "body": "b"}),
        ai_text("已发送2"),
    ]
    config = _email_graph_config("email-session")
    runtime.graph.invoke({"messages": [HumanMessage(content="发第一封")]}, config)
    runtime.graph.invoke(Command(resume={"action": "approve_session"}), config)
    assert len(email_client.sends) == 1
    result = runtime.graph.invoke({"messages": [HumanMessage(content="发第二封")]}, config)
    assert interrupt_payload(runtime.graph.get_state(config)) is None
    assert [item["subject"] for item in email_client.sends] == ["one", "two"]
    assert result["messages"][-1].content == "已发送2"
    assert runtime.approval_manager.ensure(**_tool_scope(config))

