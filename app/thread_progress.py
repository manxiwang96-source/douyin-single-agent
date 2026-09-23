from __future__ import annotations

import json
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


def _step(*, id: str, kind: str, tool: str | None, label: str, status: str, children=None, error=None) -> dict[str, Any]:
    step = {
        "id": id,
        "kind": kind,
        "tool": tool,
        "label": label,
        "status": status,
        "spin": status == "running",
    }
    if children:
        step["children"] = children
    if error:
        step["error"] = error
    return step


FAILED_TOOL_STATUSES = frozenset({"failed", "timeout", "auth_expired"})


def _coerce_index(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _normalize_child_status(status: Any) -> str:
    text = str(status or "").strip().lower()
    if text in {"running", "in_progress"}:
        return "running"
    if text in {"failed", "fail", "error", "timeout", "cancelled", "canceled", "auth_expired"}:
        return "failed"
    if text in {"succeeded", "success", "completed", "done", "waiting"}:
        return "done" if text != "waiting" else "waiting"
    return "done"


def dify_child_step(node: dict[str, Any] | None) -> dict[str, Any]:
    source = node if isinstance(node, dict) else {}
    if source.get("kind") == "dify_node":
        step_id = str(source.get("id") or "")
        node_id = str(source.get("node_id") or "")
        index = _coerce_index(source.get("index"))
        if not step_id:
            step_id = f"dify:{node_id}:{index}"
        label = str(source.get("label") or source.get("title") or node_id or step_id)
        status = _normalize_child_status(source.get("status"))
        return _step(
            id=step_id,
            kind="dify_node",
            tool="discover_douyin_leads",
            label=label,
            status=status,
            error=source.get("error"),
        )
    nested = source.get("data") if isinstance(source.get("data"), dict) else {}
    node_id = str(source.get("node_id") or nested.get("node_id") or "")
    index = _coerce_index(source.get("index") if source.get("index") is not None else nested.get("index"))
    title = source.get("title") or nested.get("title") or source.get("label") or node_id
    event_name = str(source.get("event") or "")
    if event_name == "node_started":
        status = "running"
    elif event_name == "node_finished":
        status = _normalize_child_status(nested.get("status") or source.get("status"))
    else:
        status = _normalize_child_status(source.get("status") or nested.get("status"))
    error = source.get("error") or nested.get("error")
    return _step(
        id=f"dify:{node_id}:{index}",
        kind="dify_node",
        tool="discover_douyin_leads",
        label=str(title or node_id),
        status=status,
        error=error,
    )


def _children_from_nodes(nodes: Any) -> list[dict[str, Any]]:
    if not isinstance(nodes, list):
        return []
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    indexes: dict[str, int] = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        child = dify_child_step(node)
        child_id = child["id"]
        index = _coerce_index(node.get("index") if node.get("index") is not None else (node.get("data") or {}).get("index") if isinstance(node.get("data"), dict) else child_id.rsplit(":", 1)[-1])
        indexes[child_id] = index
        if child_id in by_id:
            by_id[child_id] = child
        else:
            order.append(child_id)
            by_id[child_id] = child
    children = [by_id[item] for item in order]
    children.sort(key=lambda item: (indexes.get(item["id"], 0), item["id"]))
    return children


def overlay_live_dify_children(progress: dict[str, Any], live_children: list[dict[str, Any]] | None) -> dict[str, Any]:
    if not live_children:
        return progress
    steps = list(progress.get("steps") or [])
    updated = False
    next_steps: list[dict[str, Any]] = []
    for step in steps:
        if not updated and step.get("tool") == "discover_douyin_leads":
            cloned = dict(step)
            cloned["children"] = list(live_children)
            next_steps.append(cloned)
            updated = True
        else:
            next_steps.append(step)
    if not updated:
        return progress
    return {**progress, "steps": next_steps}


def _parse_tool_payload(content: str) -> dict[str, Any] | None:
    text = (content or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _tool_step_status(payload: dict[str, Any] | None) -> str:
    if not payload:
        return "done"
    status = str(payload.get("status") or "").strip().lower()
    if payload.get("ok") is False or status in FAILED_TOOL_STATUSES:
        return "failed"
    return "done"


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
            payload = _parse_tool_payload(content)
            children = None
            if name == "discover_douyin_leads" and payload is not None:
                children = _children_from_nodes(payload.get("workflow_nodes")) or None
            upsert(
                _step(
                    id=f"tool:{name}:{call_id}",
                    kind="tool",
                    tool=name or None,
                    label=_tool_label(name, "running"),
                    status=_tool_step_status(payload),
                    children=children,
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
                    children=step.get("children"),
                    error=step.get("error"),
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
