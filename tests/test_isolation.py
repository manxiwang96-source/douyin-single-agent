from __future__ import annotations

from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage

from app.knowledge import kb_namespace, profile_namespace
from tests.fakes import TINY_PNG, ai_text, ai_tool
from tests.graph_helpers import graph_config
from tests.http_helpers import create_and_open, make_client, register_and_login


USER_A = "11111111-1111-4111-8111-111111111111"
INST_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
USER_B = "22222222-2222-4222-8222-222222222222"
INST_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def test_graph_nodes_remain_chatbot_and_tools(runtime):
    nodes = set(runtime.graph.get_graph().nodes)
    assert "chatbot" in nodes
    assert "tools" in nodes
    assert "discover_douyin_leads" not in nodes
    assert "review_media" not in nodes


def test_invoke_config_carries_owner_and_bindings(runtime, llm):
    llm.responses = [ai_text("ok")]
    config = graph_config("cfg-owner", allowed_workflow_codes=["douyin-lead-discovery"])
    runtime.graph.invoke({"messages": [HumanMessage(content="hi")]}, config)
    assert config["configurable"]["thread_id"] == "cfg-owner"
    assert config["configurable"]["user_id"]
    assert config["configurable"]["agent_instance_id"]
    assert config["configurable"]["allowed_workflow_codes"] == ["douyin-lead-discovery"]


def test_profile_memory_is_isolated_per_instance(runtime, llm):
    llm.responses = [
        ai_tool("remember_fact", {"fact": "user-a-secret-pref"}),
        ai_text("saved"),
        ai_tool("recall_facts", {"query": "secret"}),
        ai_text("none"),
    ]
    runtime.graph.invoke(
        {"messages": [HumanMessage(content="remember my pref")]},
        graph_config("mem-a", user_id=USER_A, agent_instance_id=INST_A),
    )
    runtime.graph.invoke(
        {"messages": [HumanMessage(content="what is my pref")]},
        graph_config("mem-b", user_id=USER_B, agent_instance_id=INST_B),
    )
    hits_a = runtime.memory_store.search(
        profile_namespace(USER_A, INST_A), query="secret", limit=10
    )
    hits_b = runtime.memory_store.search(
        profile_namespace(USER_B, INST_B), query="secret", limit=10
    )
    texts_a = [hit.value.get("text") for hit in hits_a]
    texts_b = [hit.value.get("text") for hit in hits_b]
    assert "user-a-secret-pref" in texts_a
    assert "user-a-secret-pref" not in texts_b


def test_chatbot_retrieves_only_current_instance_kb(runtime, llm):
    runtime.memory_store.put(
        kb_namespace(USER_A, INST_A),
        "a1",
        {"text": "ONLY_INSTANCE_A_KB_MARKER", "source": "a.md", "chunk_id": "a1"},
    )
    runtime.memory_store.put(
        kb_namespace(USER_B, INST_B),
        "b1",
        {"text": "ONLY_INSTANCE_B_KB_MARKER", "source": "b.md", "chunk_id": "b1"},
    )
    llm.responses = [ai_text("ok")]
    runtime.graph.invoke(
        {"messages": [HumanMessage(content="ONLY_INSTANCE_A_KB_MARKER please")]},
        graph_config("kb-a", user_id=USER_A, agent_instance_id=INST_A),
    )
    payload = llm.calls[0]
    texts = []
    for message in payload:
        content = getattr(message, "content", "")
        if isinstance(message, SystemMessage) or isinstance(content, str):
            texts.append(str(content))
    joined = "\n".join(texts)
    assert "ONLY_INSTANCE_A_KB_MARKER" in joined
    assert "ONLY_INSTANCE_B_KB_MARKER" not in joined


def test_http_media_is_isolated_and_recorded(runtime, llm, image_client):
    llm.responses = [
        ai_tool("generate_image", {"prompt": "bottle"}),
        ai_text("image ready"),
    ]
    client = make_client(runtime)
    register_and_login(client, login_name="alice")
    opened = create_and_open(client, title="agent-a")
    thread_id = opened["thread_id"]
    client.post(f"/v1/threads/{thread_id}/messages", json={"content": "draw"})
    resumed = client.post(
        f"/v1/threads/{thread_id}/resume",
        json={"action": "approve", "prompt": "bottle", "params": {}},
    )
    assert resumed.status_code == 200
    url = None
    for message in resumed.json()["messages"]:
        for item in message.get("media") or []:
            url = item["url"]
    assert url
    parts = url.strip("/").split("/")
    assert parts[:2] == ["v1", "media"]
    assert parts[2] == opened["user_id"]
    assert parts[3] == opened["agent_instance_id"]
    assert parts[4] == "images"
    media = client.get(url)
    assert media.status_code == 200
    assert media.content == TINY_PNG
    assets = runtime.business_repo.list_media_assets(UUID(opened["agent_instance_id"]))
    assert assets
    assert assets[0].kind == "image"
    assert opened["user_id"] in assets[0].storage_uri
    other = make_client(runtime)
    register_and_login(other, login_name="bob")
    forbidden = other.get(url)
    assert forbidden.status_code in {403, 404}
    anon = make_client(runtime)
    assert anon.get(url).status_code == 401
