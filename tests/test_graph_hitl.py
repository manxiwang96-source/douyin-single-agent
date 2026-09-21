from __future__ import annotations

import asyncio

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

