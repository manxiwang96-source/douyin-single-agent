from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from langchain_core.messages import AIMessage

from app.chat_sse import should_emit_chatbot_token, stream_chat_events, unpack_stream_item
from tests.fakes import ai_text, ai_tool
from tests.http_helpers import create_and_open, make_client, parse_sse_events, post_chat, register_and_login


ALLOWED_EVENTS = {"progress", "token", "thread", "error"}


def test_unpack_stream_item_tuple_and_dict():
    assert unpack_stream_item(("updates", {"a": 1})) == ("updates", {"a": 1})
    assert unpack_stream_item(["messages", ("chunk", {"langgraph_node": "chatbot"})])[0] == "messages"
    assert unpack_stream_item({"type": "custom", "data": {"dify_nodes": []}}) == ("custom", {"dify_nodes": []})
    assert unpack_stream_item("bare") == (None, "bare")


def test_should_emit_chatbot_token_filters_tools_and_chunks():
    text = SimpleNamespace(content="你好", tool_call_chunks=[], tool_calls=[])
    assert should_emit_chatbot_token(text, {"langgraph_node": "chatbot"}) is True
    assert should_emit_chatbot_token(text, {"langgraph_node": "tools"}) is False
    assert should_emit_chatbot_token(
        SimpleNamespace(content="call", tool_call_chunks=[{"name": "discover_douyin_leads"}], tool_calls=[]),
        {"langgraph_node": "chatbot"},
    ) is False
    assert should_emit_chatbot_token(
        SimpleNamespace(content="", tool_call_chunks=[], tool_calls=[{"name": "search_kb"}]),
        {"langgraph_node": "chatbot"},
    ) is False
    assert should_emit_chatbot_token(SimpleNamespace(content="   ", tool_call_chunks=[], tool_calls=[]), {"langgraph_node": "chatbot"}) is False


class _FakeSnapshot:
    def __init__(self):
        self.values = {"messages": [], "last_image_path": None, "last_video_path": None}
        self.next = ()
        self.interrupts = ()
        self.tasks = ()


class _FakeGraph:
    def __init__(self, items=None, error=None):
        self.items = list(items or [])
        self.error = error
        self.snapshot = _FakeSnapshot()

    async def astream(self, *_args, **_kwargs):
        if self.error is not None:
            raise self.error
        for item in self.items:
            yield item

    async def aget_state(self, _config):
        return self.snapshot

    def get_state(self, _config):
        return self.snapshot


class _FakeRuntime:
    def __init__(self, graph):
        self.graph = graph
        self.settings = SimpleNamespace(assistant_timezone="Asia/Shanghai")


def _collect(runtime, payload=None, config=None):
    async def run():
        events = []
        async for item in stream_chat_events(runtime, "thread-1", payload or {}, config or {}):
            events.append(item)
        return events

    return asyncio.run(run())


def test_stream_emits_token_progress_thread_and_skips_tool_tokens():
    chatbot = SimpleNamespace(content="可见文本", tool_call_chunks=[], tool_calls=[])
    toolish = SimpleNamespace(content="隐藏碎片", tool_call_chunks=[{"index": 0}], tool_calls=[])
    graph = _FakeGraph(
        [
            ("updates", {"chatbot": {"messages": []}}),
            ("messages", (chatbot, {"langgraph_node": "chatbot"})),
            ("messages", (toolish, {"langgraph_node": "chatbot"})),
            ("messages", (SimpleNamespace(content="DIFY", tool_call_chunks=[], tool_calls=[]), {"langgraph_node": "tools"})),
        ]
    )
    events = _collect(_FakeRuntime(graph))
    names = [item["event"] for item in events]
    assert names[0] == "progress"
    assert "token" in names
    assert names[-1] == "thread"
    assert "error" not in names
    tokens = [json.loads(item["data"]) for item in events if item["event"] == "token"]
    assert tokens == [{"delta": "可见文本"}]


def test_stream_error_does_not_emit_fake_thread():
    events = _collect(_FakeRuntime(_FakeGraph(error=RuntimeError("boom"))))
    assert [item["event"] for item in events] == ["error"]
    assert json.loads(events[0]["data"]) == {"detail": "boom"}


def test_precheck_stays_json_and_success_is_sse(runtime, llm):
    llm.responses = [ai_text("收到")]
    client = make_client(runtime)
    unauth = client.post("/v1/threads/missing/messages", json={"content": "hi"})
    assert unauth.status_code == 401
    assert unauth.json() == {"detail": "not authenticated"}
    assert "event-stream" not in (unauth.headers.get("content-type") or "")

    register_and_login(client)
    missing = client.post("/v1/threads/missing/messages", json={"content": "hi"})
    assert missing.status_code == 404
    assert missing.json() == {"detail": "thread not found"}

    opened = create_and_open(client, title="sse-precheck")
    thread_id = opened["thread_id"]
    idle_resume = client.post(f"/v1/threads/{thread_id}/resume", json={"action": "approve"})
    assert idle_resume.status_code == 409
    assert idle_resume.json() == {"detail": "thread is not waiting for review"}

    ok = post_chat(client, f"/v1/threads/{thread_id}/messages", json={"content": "你好", "client_message_id": "c-sse"})
    assert ok.status_code == 200
    assert "text/event-stream" in (ok.headers.get("content-type") or "")
    names = [item["event"] for item in ok.events]
    assert set(names) <= ALLOWED_EVENTS
    assert names[-1] == "thread"
    assert "text_chunk" not in names
    assert ok.json()["messages"][-1]["content"] == "收到"
    tokens = [item["data"]["delta"] for item in ok.events if item["event"] == "token"]
    assert "".join(tokens) == "收到"


def test_hitl_resume_is_sse_and_blocked_message_is_json(runtime, llm):
    llm.responses = [
        ai_tool("generate_image", {"prompt": "bottle"}),
        ai_text("image ready"),
    ]
    client = make_client(runtime)
    register_and_login(client)
    thread_id = create_and_open(client, title="sse-hitl")["thread_id"]
    interrupted = post_chat(client, f"/v1/threads/{thread_id}/messages", json={"content": "draw"})
    assert interrupted.status_code == 200
    assert "text/event-stream" in (interrupted.headers.get("content-type") or "")
    assert interrupted.json()["status"] == "interrupted"
    blocked = client.post(f"/v1/threads/{thread_id}/messages", json={"content": "again"})
    assert blocked.status_code == 409
    assert blocked.json() == {"detail": "thread is waiting for review"}
    resumed = post_chat(
        client,
        f"/v1/threads/{thread_id}/resume",
        json={"action": "approve", "prompt": "bottle", "params": {}},
    )
    assert resumed.status_code == 200
    assert "text/event-stream" in (resumed.headers.get("content-type") or "")
    names = [item["event"] for item in resumed.events]
    assert set(names) <= ALLOWED_EVENTS
    assert names[-1] == "thread"
    assert resumed.json()["status"] == "idle"


def _dify_children(events_or_thread):
    steps = []
    if isinstance(events_or_thread, list):
        for item in events_or_thread:
            if item.get("event") == "progress":
                steps.extend((item.get("data") or {}).get("steps") or [])
    else:
        steps.extend(((events_or_thread.get("progress") or {}).get("steps")) or [])
    children = []
    for step in steps:
        if step.get("tool") == "discover_douyin_leads":
            children.extend(step.get("children") or [])
    return children


def test_http_dify_children_live_overlay_and_no_text_chunk(runtime, llm, dify_client):
    llm.responses = [
        ai_tool("discover_douyin_leads", {"account": "shop1", "keyword": "敏感肌"}),
        ai_text("已完成线索发现"),
    ]
    dify_client.events = [
        {"event": "text_chunk", "data": {"text": "DIFY_SECRET_CHUNK"}},
        {"event": "node_started", "data": {"node_id": "n1", "title": "开始", "index": 0, "node_type": "start"}},
        {"event": "node_finished", "data": {"node_id": "n1", "title": "开始", "index": 0, "status": "succeeded"}},
        {"event": "node_started", "data": {"node_id": "n2", "title": "请求抖音", "index": 1}},
        {
            "event": "node_finished",
            "data": {"node_id": "n2", "title": "请求抖音", "index": 1, "status": "succeeded"},
        },
    ]
    client = make_client(runtime)
    register_and_login(client)
    thread_id = create_and_open(client, title="sse-dify")["thread_id"]
    response = post_chat(
        client,
        f"/v1/threads/{thread_id}/messages",
        json={"content": "帮我找敏感肌线索", "client_message_id": "c-dify"},
    )
    assert response.status_code == 200
    names = [item["event"] for item in response.events]
    assert set(names) <= ALLOWED_EVENTS
    assert "text_chunk" not in names
    assert names.count("thread") == 1
    raw = response.text
    assert "text_chunk" not in raw
    assert "DIFY_SECRET_CHUNK" not in raw
    live_children = _dify_children(response.events)
    assert live_children
    assert {child["id"] for child in live_children} >= {"dify:n1:0", "dify:n2:1"}
    assert all(child["kind"] == "dify_node" for child in live_children)
    thread = response.json()
    replay = _dify_children(thread)
    assert [child["id"] for child in replay] == ["dify:n1:0", "dify:n2:1"]
    assert replay[0]["label"] == "开始"
    assert replay[0]["status"] == "done"
    fetched = client.get(f"/v1/threads/{thread_id}")
    assert fetched.status_code == 200
    assert [child["id"] for child in _dify_children(fetched.json())] == ["dify:n1:0", "dify:n2:1"]
