from __future__ import annotations

from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.message_metadata import with_message_metadata
from app.serialize import api_messages_from_state, serialize_thread
from app.thread_progress import overlay_live_dify_children, thread_progress


class FakeSnapshot:
    def __init__(self, messages, next=(), interrupts=(), values=None):
        payload = {"messages": messages, "last_image_path": None, "last_video_path": None}
        if values:
            payload.update(values)
        self.values = payload
        self.next = tuple(next)
        self.interrupts = list(interrupts)
        self.tasks = ()


class FakeRuntime:
    def __init__(self, snapshot):
        self.settings = SimpleNamespace(assistant_timezone="Asia/Shanghai")
        self.graph = SimpleNamespace(get_state=lambda config: snapshot)


def _human(content: str, client_message_id: str | None = "client-1", message_id: str = "user-1"):
    message = HumanMessage(content=content, id=message_id)
    if client_message_id is None:
        return message
    return with_message_metadata(
        message,
        {
            "message_id": message_id,
            "client_message_id": client_message_id,
            "created_at": "2026-09-23T12:00:00+08:00",
        },
    )


def _ai_tool(name: str, call_id: str = "call-1", args=None):
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args or {}, "id": call_id, "type": "tool_call"}],
    )


def _tool_result(name: str, call_id: str, content: str):
    return ToolMessage(content=content, tool_call_id=call_id, name=name)


def _labels(progress) -> list[str]:
    return [step["label"] for step in progress["steps"]]


def test_empty_thread_is_idle():
    progress = thread_progress(FakeSnapshot([]))
    assert progress == {"round_id": None, "phase": "idle", "steps": []}


def test_user_message_without_tools_is_thinking():
    progress = thread_progress(FakeSnapshot([_human("hello")], next=("chatbot",)))
    assert progress["round_id"] == "client-1"
    assert progress["phase"] == "thinking"
    assert progress["steps"][0]["id"] == "thinking"
    assert progress["steps"][0]["label"] == '正在思考'
    assert progress["steps"][0]["status"] == "running"
    assert progress["steps"][0]["spin"] is True
    assert '正在整理回复' not in _labels(progress)


def test_round_id_falls_back_to_message_id():
    progress = thread_progress(FakeSnapshot([HumanMessage(content="hi", id="legacy-id")]))
    assert progress["round_id"] == "legacy-id"
    assert progress["phase"] == "thinking"


def test_discover_leads_running_uses_workflow_label():
    progress = thread_progress(
        FakeSnapshot(
            [_human("scan"), _ai_tool("discover_douyin_leads", "call-dify")],
            next=("tools",),
        )
    )
    assert progress["phase"] == "running"
    leads = progress["steps"][1]
    assert leads["id"] == "tool:discover_douyin_leads:call-dify"
    assert leads["label"] == '正在运行「抖音线索发现与触达」'
    assert leads["status"] == "running"
    assert leads["spin"] is True
    assert progress["steps"][0]["status"] == "done"
    assert progress["steps"][0]["spin"] is False


def test_named_tool_stays_after_completion():
    progress = thread_progress(
        FakeSnapshot(
            [
                _human("search"),
                _ai_tool("search_kb"),
                _tool_result("search_kb", "call-1", "{'hits': []}"),
            ],
            next=("chatbot",),
        )
    )
    assert progress["phase"] == "composing"
    assert progress["steps"][1]["label"] == '知识库检索'
    assert progress["steps"][1]["status"] == "done"
    assert progress["steps"][1]["spin"] is False
    assert progress["steps"][2]["label"] == '正在整理回复'
    assert progress["steps"][2]["status"] == "running"
    assert progress["steps"][2]["spin"] is True


def test_unknown_mcp_tool_uses_generic_label():
    progress = thread_progress(
        FakeSnapshot([_human("weather"), _ai_tool("get_weather", "call-w")])
    )
    assert progress["phase"] == "running"
    assert progress["steps"][1]["label"] == '正在调用「get_weather」'


def test_image_hitl_waiting_does_not_spin():
    progress = thread_progress(
        FakeSnapshot(
            [_human("draw"), _ai_tool("generate_image")],
            interrupts=[{"type": "review_media", "tool": "generate_image", "prompt": "bottle", "params": {}}],
        )
    )
    assert progress["phase"] == "waiting_review"
    review = progress["steps"][1]
    assert review["label"] == '等待审核「生成图片」'
    assert review["status"] == "waiting"
    assert review["spin"] is False
    assert review["kind"] == "review"


def test_approve_keeps_round_and_updates_image_step():
    messages = [_human("draw"), _ai_tool("generate_image")]
    waiting = thread_progress(
        FakeSnapshot(
            messages,
            interrupts=[{"type": "review_media", "tool": "generate_image", "prompt": "bottle"}],
        )
    )
    approved = thread_progress(FakeSnapshot(messages, next=("tools",)))
    assert approved["round_id"] == waiting["round_id"] == "client-1"
    assert [step["id"] for step in waiting["steps"]] == [step["id"] for step in approved["steps"]]
    assert approved["phase"] == "running"
    assert approved["steps"][1]["label"] == '正在生成图片'
    assert approved["steps"][1]["status"] == "running"
    assert approved["steps"][1]["spin"] is True


def test_skip_is_done_without_composing():
    progress = thread_progress(
        FakeSnapshot(
            [
                _human("draw"),
                _ai_tool("generate_image"),
                _tool_result("generate_image", "call-1", "User skipped media generation."),
            ],
            next=("chatbot",),
        )
    )
    assert progress["phase"] == "done"
    assert progress["steps"][-1]["label"] == '已跳过「生成图片」'
    assert progress["steps"][-1]["status"] == "done"
    assert '正在整理回复' not in _labels(progress)
    assert all(step["status"] != "running" for step in progress["steps"])


def test_final_assistant_marks_composing_done():
    progress = thread_progress(
        FakeSnapshot(
            [
                _human("search"),
                _ai_tool("search_kb"),
                _tool_result("search_kb", "call-1", "hits"),
                AIMessage(content="done"),
            ]
        )
    )
    assert progress["phase"] == "done"
    assert progress["steps"][-1]["id"] == "composing"
    assert progress["steps"][-1]["label"] == '正在整理回复'
    assert progress["steps"][-1]["status"] == "done"
    assert progress["steps"][-1]["spin"] is False


def test_new_user_message_resets_round():
    progress = thread_progress(
        FakeSnapshot(
            [
                _human("old", client_message_id="client-old", message_id="user-old"),
                _ai_tool("search_kb", "call-old"),
                _tool_result("search_kb", "call-old", "hits"),
                AIMessage(content="old reply"),
                _human("new", client_message_id="client-new", message_id="user-new"),
            ]
        )
    )
    assert progress["round_id"] == "client-new"
    assert progress["phase"] == "thinking"
    assert _labels(progress) == ['正在思考']


def test_serialize_thread_keeps_chat_bubbles_and_media():
    image_json = '{"ok": true, "type": "image", "url": "/v1/media/u/a/images/x.png"}'
    snapshot = FakeSnapshot(
        [
            _human("draw"),
            _ai_tool("generate_image"),
            _tool_result("generate_image", "call-1", image_json),
            AIMessage(content="image ready"),
        ]
    )
    payload = serialize_thread(FakeRuntime(snapshot), "thread-1")
    roles = [item["role"] for item in payload["messages"]]
    contents = [item["content"] for item in payload["messages"]]
    assert roles == ["user", "assistant"]
    assert contents == ["draw", "image ready"]
    assert payload["messages"][1]["media"] == [{"type": "image", "url": "/v1/media/u/a/images/x.png"}]
    assert payload["progress"]["phase"] == "done"
    assert payload["interrupt"] is None
    bubbles = api_messages_from_state(snapshot.values)
    assert all("tool_calls" not in item for item in bubbles)


def test_discover_leads_replays_workflow_nodes():
    progress = thread_progress(
        FakeSnapshot(
            [
                _human("scan"),
                _ai_tool("discover_douyin_leads", "call-dify"),
                _tool_result(
                    "discover_douyin_leads",
                    "call-dify",
                    '{"ok": true, "status": "succeeded", "workflow_nodes": ['
                    '{"node_id": "n1", "title": "开始", "index": 0, "status": "succeeded"},'
                    '{"node_id": "n2", "title": "请求抖音", "index": 1, "status": "failed", "error": "timeout"}'
                    "]}",
                ),
                AIMessage(content="done"),
            ]
        )
    )
    leads = next(step for step in progress["steps"] if step["tool"] == "discover_douyin_leads")
    children = leads["children"]
    assert [child["id"] for child in children] == ["dify:n1:0", "dify:n2:1"]
    assert children[0]["kind"] == "dify_node"
    assert children[0]["label"] == "开始"
    assert children[0]["status"] == "done"
    assert children[0]["spin"] is False
    assert children[1]["label"] == "请求抖音"
    assert children[1]["status"] == "failed"
    assert children[1]["spin"] is False
    assert children[1]["error"] == "timeout"
    payload = serialize_thread(
        FakeRuntime(
            FakeSnapshot(
                [
                    _human("scan"),
                    _ai_tool("discover_douyin_leads", "call-dify"),
                    _tool_result(
                        "discover_douyin_leads",
                        "call-dify",
                        '{"ok": true, "status": "succeeded", "workflow_nodes": ['
                        '{"node_id": "n1", "title": "开始", "index": 0, "status": "succeeded"}'
                        "]}",
                    ),
                    AIMessage(content="done"),
                ]
            )
        ),
        "thread-replay",
    )
    replay = next(step for step in payload["progress"]["steps"] if step["tool"] == "discover_douyin_leads")
    assert replay["children"][0]["id"] == "dify:n1:0"


def test_failed_tool_marks_parent_failed():
    progress = thread_progress(
        FakeSnapshot(
            [
                _human("scan"),
                _ai_tool("discover_douyin_leads", "call-dify"),
                _tool_result(
                    "discover_douyin_leads",
                    "call-dify",
                    '{"ok": false, "status": "timeout", "error": "dify timeout"}',
                ),
            ],
            next=("chatbot",),
        )
    )
    leads = next(step for step in progress["steps"] if step["tool"] == "discover_douyin_leads")
    assert leads["status"] == "failed"
    assert leads["spin"] is False
    assert leads["label"] == '正在运行「抖音线索发现与触达」'


def test_overlay_live_dify_children_only_touches_leads_step():
    progress = thread_progress(
        FakeSnapshot(
            [_human("scan"), _ai_tool("discover_douyin_leads", "call-dify")],
            next=("tools",),
        )
    )
    overlay = overlay_live_dify_children(
        progress,
        [
            {
                "id": "dify:n1:0",
                "kind": "dify_node",
                "tool": "discover_douyin_leads",
                "label": "开始",
                "status": "running",
                "spin": True,
            }
        ],
    )
    leads = next(step for step in overlay["steps"] if step["tool"] == "discover_douyin_leads")
    assert leads["children"][0]["id"] == "dify:n1:0"
    assert leads["children"][0]["status"] == "running"
    search = thread_progress(FakeSnapshot([_human("search"), _ai_tool("search_kb")]))
    untouched = overlay_live_dify_children(
        search,
        [{"id": "dify:n1:0", "kind": "dify_node", "label": "开始", "status": "running", "spin": True}],
    )
    assert untouched == search
