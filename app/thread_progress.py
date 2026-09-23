from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.graph import interrupt_payload
from app.message_metadata import message_metadata

SKIP_TOOL_CONTENT = "User skipped media generation."

MEDIA_TOOLS = {
    "generate_image": {
        "running": '正在生成图片',
        "waiting": '等待审核「生成图片」',
        "skipped": '已跳过「生成图片」',
    },
    "generate_video": {
        "running": '正在生成视频',
        "waiting": '等待审核「生成视频」',
        "skipped": '已跳过「生成视频」',
    },
}

NAMED_TOOL_LABELS = {
    "discover_douyin_leads": '正在运行「抖音线索发现与触达」',
    "search_kb": '知识库检索',
    "remember_fact": '记住事实',
    "recall_facts": '回忆事实',
    "send_email": '发送邮件',
    "list_jobs": '查看任务',
    "cancel_job": '取消任务',
    **{name: spec["running"] for name, spec in MEDIA_TOOLS.items()},
}


def _text(message) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text") or "")
        return "".join(parts)
    return str(content or "")


def _round_id(message) -> str | None:
    metadata = message_metadata(message)
    client_id = metadata.get("client_message_id")
    if client_id:
        return str(client_id)
    message_id = getattr(message, "id", None)
    if message_id:
        return str(message_id)
    return None


def _tool_name(call: Any) -> str:
    if isinstance(call, dict):
        return str(call.get("name") or "")
    return str(getattr(call, "name", "") or "")


def _tool_call_id(call: Any) -> str:
    if isinstance(call, dict):
        return str(call.get("id") or call.get("tool_call_id") or "")
    return str(getattr(call, "id", None) or getattr(call, "tool_call_id", None) or "")


def _tool_label(name: str, state: str = "running") -> str:
    if name in MEDIA_TOOLS:
        return MEDIA_TOOLS[name].get(state) or MEDIA_TOOLS[name]["running"]
    if name in NAMED_TOOL_LABELS:
        return NAMED_TOOL_LABELS[name]
    if name:
        return f"正在调用「{name}」"
    return '正在调用工具'


def _step(*, id: str, kind: str, tool: str | None, label: str, status: str) -> dict[str, Any]:
    return {
        "id": id,
        "kind": kind,
        "tool": tool,
        "label": label,
        "status": status,
        "spin": status == "running",
    }


def _idle() -> dict[str, Any]:
    return {"round_id": None, "phase": "idle", "steps": []}


def _thinking(*, done: bool) -> dict[str, Any]:
    return _step(
        id="thinking",
        kind="thinking",
        tool=None,
        label='正在思考',
        status="done" if done else "running",
    )


def thread_progress(snapshot) -> dict[str, Any]:
    values = getattr(snapshot, "values", None) or {}
    messages = list(values.get("messages") or [])
    last_human_idx = max(
        (index for index, message in enumerate(messages) if isinstance(message, HumanMessage)),
        default=-1,
    )
    if last_human_idx < 0:
        return _idle()

    round_id = _round_id(messages[last_human_idx])
    round_messages = messages[last_human_idx + 1 :]
    pending = interrupt_payload(snapshot)
    next_nodes = [str(item) for item in (getattr(snapshot, "next", None) or ())]

    steps: list[dict[str, Any]] = [_thinking(done=False)]
    by_id = {"thinking": 0}
    call_names: dict[str, str] = {}
    skipped = False
    has_tool = False
    final_assistant = False

    def upsert(step: dict[str, Any]) -> None:
        existing = by_id.get(step["id"])
        if existing is None:
            by_id[step["id"]] = len(steps)
            steps.append(step)
            return
        steps[existing] = step

    for message in round_messages:
        if isinstance(message, AIMessage):
            tool_calls = list(getattr(message, "tool_calls", None) or [])
            if tool_calls:
                has_tool = True
                for call in tool_calls:
                    name = _tool_name(call)
                    call_id = _tool_call_id(call) or name
                    call_names[call_id] = name
                    upsert(
                        _step(
                            id=f"tool:{name}:{call_id}",
                            kind="tool",
                            tool=name or None,
                            label=_tool_label(name, "running"),
                            status="running",
                        )
                    )
                continue
            final_assistant = True
            continue
        if isinstance(message, ToolMessage):
            has_tool = True
            call_id = str(getattr(message, "tool_call_id", "") or "")
            name = str(getattr(message, "name", "") or call_names.get(call_id) or "")
            if call_id:
                call_names[call_id] = name
            content = _text(message)
            if content == SKIP_TOOL_CONTENT:
                skipped = True
                upsert(
                    _step(
                        id=f"tool:{name}:{call_id}",
                        kind="review",
                        tool=name or None,
                        label=_tool_label(name, "skipped"),
                        status="done",
                    )
                )
                continue
            upsert(
                _step(
                    id=f"tool:{name}:{call_id}",
                    kind="tool",
                    tool=name or None,
                    label=_tool_label(name, "running"),
                    status="done",
                )
            )

    if pending and pending.get("type") == "review_media":
        tool = str(pending.get("tool") or "")
        updated = False
        for index, step in enumerate(steps):
            if step.get("tool") == tool or (tool and str(step.get("id") or "").startswith(f"tool:{tool}:")):
                steps[index] = _step(
                    id=step["id"],
                    kind="review",
                    tool=tool or step.get("tool"),
                    label=_tool_label(tool, "waiting"),
                    status="waiting",
                )
                updated = True
                break
        if not updated:
            upsert(
                _step(
                    id=f"review:{tool or 'media'}",
                    kind="review",
                    tool=tool or None,
                    label=_tool_label(tool, "waiting"),
                    status="waiting",
                )
            )
        steps[0] = _thinking(done=True)
        return {"round_id": round_id, "phase": "waiting_review", "steps": steps}

    progressed = has_tool or skipped or final_assistant
    if progressed:
        steps[0] = _thinking(done=True)

    if skipped:
        return {
            "round_id": round_id,
            "phase": "done",
            "steps": [step for step in steps if step["kind"] != "composing"],
        }

    unfinished = any(step["kind"] == "tool" and step["status"] == "running" for step in steps)
    if unfinished:
        return {"round_id": round_id, "phase": "running", "steps": steps}

    if final_assistant:
        upsert(
            _step(
                id="composing",
                kind="composing",
                tool=None,
                label='正在整理回复',
                status="done",
            )
        )
        return {"round_id": round_id, "phase": "done", "steps": steps}

    if has_tool or (progressed and "chatbot" in next_nodes):
        upsert(
            _step(
                id="composing",
                kind="composing",
                tool=None,
                label='正在整理回复',
                status="running",
            )
        )
        return {"round_id": round_id, "phase": "composing", "steps": steps}

    return {"round_id": round_id, "phase": "thinking", "steps": steps}
