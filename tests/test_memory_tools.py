from __future__ import annotations

from langchain_core.messages import HumanMessage

from app.knowledge import profile_namespace
from tests.fakes import ai_text, ai_tool
from tests.graph_helpers import DUMMY_AGENT_INSTANCE_ID, DUMMY_USER_ID, graph_config


def test_remember_and_recall_facts(runtime, llm):
    llm.responses = [
        ai_tool("remember_fact", {"fact": "喜欢喝乌龙茶"}),
        ai_text("已记住"),
        ai_tool("recall_facts", {"query": "茶"}),
        ai_text("你喜欢喝乌龙茶"),
    ]
    config = graph_config("memory")
    runtime.graph.invoke({"messages": [HumanMessage(content="记住我喜欢喝乌龙茶")]}, config)
    result = runtime.graph.invoke({"messages": [HumanMessage(content="我喜欢什么茶？")]}, config)
    hits = runtime.memory_store.search(profile_namespace(DUMMY_USER_ID, DUMMY_AGENT_INSTANCE_ID), limit=10)
    texts = [hit.value.get("text") for hit in hits]
    assert "喜欢喝乌龙茶" in texts
    assert result["messages"][-1].content == "你喜欢喝乌龙茶"
