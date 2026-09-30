from __future__ import annotations

from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage

from app.graph import graph_cache_key
from app.knowledge import kb_namespace, profile_namespace
from tests.fakes import TINY_PNG, ai_text, ai_tool
from tests.graph_helpers import graph_config
from tests.http_helpers import create_and_open, make_client, post_chat, register_and_login


USER_A = "11111111-1111-4111-8111-111111111111"
INST_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
USER_B = "22222222-2222-4222-8222-222222222222"
INST_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def test_graph_nodes_remain_chatbot_and_tools(runtime):
    nodes = set(runtime.graph.get_graph().nodes)
    assert "chatbot" in nodes
    assert "tools" in nodes
    assert "discover_leads" not in nodes
    assert "review_media" not in nodes


def _tool_names(graph):
    tool_node = graph.get_graph().nodes["tools"].data
    return set(tool_node._tools_by_name)


def _node_names(graph):
    return set(graph.get_graph().nodes)


def _edge_pairs(graph):
    return {(edge.source, edge.target) for edge in graph.get_graph().edges}


def test_graph_cache_key_includes_tool_set_and_config_version():
    assert graph_cache_key(["discover_leads", "get_current_datetime"], None) == (
        "",
        ("discover_leads", "get_current_datetime"),
    )
    assert graph_cache_key(["get_current_datetime"], "") == ("", ("get_current_datetime",))
    assert graph_cache_key(["get_current_datetime"], "cfg-1") == (
        "cfg-1",
        ("get_current_datetime",),
    )
    assert graph_cache_key(["get_current_datetime"], None) != graph_cache_key(
        ["get_current_datetime"], "cfg-1"
    )


def test_custom_instances_with_different_tools_do_not_share_graph_cache(runtime):
    custom_a = runtime.graph_for_tool_codes(
        ["get_current_datetime"], config_version_id="custom-a"
    )
    custom_b = runtime.graph_for_tool_codes(
        ["get_current_datetime", "discover_leads"], config_version_id="custom-b"
    )
    assert custom_a is not custom_b
    assert custom_a is runtime.graph_for_tool_codes(
        ["get_current_datetime"], config_version_id="custom-a"
    )
    assert "discover_leads" not in _tool_names(custom_a)
    assert "discover_leads" in _tool_names(custom_b)
    assert _tool_names(custom_a) == {"get_current_datetime"}
    key_a = graph_cache_key(["get_current_datetime"], "custom-a")
    key_b = graph_cache_key(["get_current_datetime", "discover_leads"], "custom-b")
    assert runtime._graph_cache[key_a] is custom_a
    assert runtime._graph_cache[key_b] is custom_b


def test_same_tools_different_config_version_do_not_share_graph_cache(runtime):
    graph_v1 = runtime.graph_for_tool_codes(
        ["get_current_datetime"], config_version_id="cfg-v1"
    )
    graph_v2 = runtime.graph_for_tool_codes(
        ["get_current_datetime"], config_version_id="cfg-v2"
    )
    graph_missing = runtime.graph_for_tool_codes(["get_current_datetime"])
    assert graph_v1 is not graph_v2
    assert graph_v1 is not graph_missing
    assert graph_missing is runtime.graph_for_tool_codes(
        ["get_current_datetime"], config_version_id=""
    )


def test_scoped_and_douyin_graphs_keep_chatbot_tools_topology(runtime):
    custom = runtime.graph_for_tool_codes(
        ["get_current_datetime"], config_version_id="custom-topo"
    )
    douyin = runtime.graph_for_tool_codes(
        ["get_current_datetime", "discover_leads"],
        config_version_id="douyin-published",
    )
    for graph in (runtime.graph, custom, douyin):
        nodes = _node_names(graph)
        edges = _edge_pairs(graph)
        assert "chatbot" in nodes
        assert "tools" in nodes
        assert "discover_leads" not in nodes
        assert "review_media" not in nodes
        assert ("__start__", "chatbot") in edges
        assert ("tools", "chatbot") in edges
        assert any(source == "chatbot" and target == "tools" for source, target in edges)
    assert custom is not douyin
    assert douyin is not runtime.graph


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
    post_chat(client, f"/v1/threads/{thread_id}/messages", json={"content": "draw"})
    resumed = post_chat(
        client,
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


def test_scoped_graph_hallucinated_discover_leads_does_not_call_dify(runtime, llm, dify_client):
    graph = runtime.graph_for_tool_codes(
        ["get_current_datetime"],
        config_version_id="no-leads",
    )
    llm.responses = [
        ai_tool("discover_leads", {"platform": "douyin", "account": "demo", "keyword": "x"}),
        ai_text("unused"),
    ]
    config = graph_config(
        "hallucinated-leads",
        enabled_tool_codes=["get_current_datetime"],
        template_code="custom",
        allowed_workflow_codes=[],
    )
    try:
        graph.invoke({"messages": [HumanMessage(content="find leads")]}, config)
    except Exception:
        pass
    assert dify_client.calls == []
    names = {getattr(tool, "name", "") for tool in (llm.bound_tools or [])}
    assert "discover_leads" not in names
    tool_node = graph.get_graph().nodes["tools"].data
    assert "discover_leads" not in set(tool_node._tools_by_name)
