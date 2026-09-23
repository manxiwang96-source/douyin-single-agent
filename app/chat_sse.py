from __future__ import annotations

import json
from typing import Any, AsyncIterator

from langgraph.errors import GraphBubbleUp, GraphInterrupt

from app.serialize import serialize_thread
from app.thread_progress import dify_child_step, overlay_live_dify_children, thread_progress


def unpack_stream_item(item: Any) -> tuple[str | None, Any]:
    if isinstance(item, dict):
        return item.get("type"), item.get("data")
    if isinstance(item, (tuple, list)) and len(item) >= 2:
        return item[0], item[1]
    return None, item


def next_chatbot_delta(text: str, seen: str) -> tuple[str | None, str]:
    if not text:
        return None, seen
    if text.startswith(seen):
        delta = text[len(seen):]
        return (delta or None), text
    if seen.startswith(text):
        return None, seen
    return text, seen + text


def message_text(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
        return "".join(parts)
    return str(content or "")


def should_emit_chatbot_token(message: Any, metadata: Any) -> bool:
    if not isinstance(metadata, dict):
        return False
    if metadata.get("langgraph_node") != "chatbot":
        return False
    tool_call_chunks = getattr(message, "tool_call_chunks", None) or []
    if tool_call_chunks:
        return False
    tool_calls = getattr(message, "tool_calls", None) or []
    if tool_calls:
        return False
    return bool(message_text(message).strip())


def sse_event(event: str, data: Any) -> dict[str, str]:
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


def live_children_from_custom(data: Any) -> list[dict[str, Any]] | None:
    payload = data
    if isinstance(payload, dict) and "dify_nodes" not in payload and isinstance(payload.get("data"), dict):
        payload = payload.get("data")
    if not isinstance(payload, dict):
        return None
    nodes = payload.get("dify_nodes")
    if not isinstance(nodes, list):
        return None
    children: list[dict[str, Any]] = []
    for node in nodes:
        if isinstance(node, dict):
            children.append(dify_child_step(node))
    return children


def _chatbot_update_message(data: Any) -> Any:
    if not isinstance(data, dict):
        return None
    update = data.get("chatbot")
    if isinstance(update, dict):
        messages = update.get("messages") or []
        if isinstance(messages, list) and messages:
            return messages[-1]
    return None


def _unpack_message_item(data: Any) -> tuple[Any, dict[str, Any]]:
    if isinstance(data, (tuple, list)) and len(data) >= 2:
        metadata = data[1] if isinstance(data[1], dict) else {}
        return data[0], metadata
    return data, {}


async def _graph_snapshot(graph, config):
    getter = getattr(graph, "aget_state", None)
    if callable(getter):
        return await getter(config)
    return graph.get_state(config)


async def stream_chat_events(runtime, thread_id: str, payload, config) -> AsyncIterator[dict[str, str]]:
    live_children: list[dict[str, Any]] = []
    seen = ""
    try:
        async for item in runtime.graph.astream(
            payload,
            config,
            stream_mode=["updates", "messages", "custom"],
            version="v2",
        ):
            mode, data = unpack_stream_item(item)
            if mode == "custom":
                children = live_children_from_custom(data)
                if children is not None:
                    live_children = children
                snapshot = await _graph_snapshot(runtime.graph, config)
                progress = overlay_live_dify_children(thread_progress(snapshot), live_children)
                yield sse_event("progress", progress)
                continue
            if mode == "messages":
                message_chunk, metadata = _unpack_message_item(data)
                if should_emit_chatbot_token(message_chunk, metadata):
                    delta, seen = next_chatbot_delta(message_text(message_chunk), seen)
                    if delta:
                        yield sse_event("token", {"delta": delta})
                continue
            if mode == "updates":
                snapshot = await _graph_snapshot(runtime.graph, config)
                progress = overlay_live_dify_children(thread_progress(snapshot), live_children)
                yield sse_event("progress", progress)
                fallback = _chatbot_update_message(data)
                if fallback is not None and should_emit_chatbot_token(
                    fallback, {"langgraph_node": "chatbot"}
                ):
                    delta, seen = next_chatbot_delta(message_text(fallback), seen)
                    if delta:
                        yield sse_event("token", {"delta": delta})
        yield sse_event("thread", serialize_thread(runtime, thread_id))
    except (GraphInterrupt, GraphBubbleUp):
        yield sse_event("thread", serialize_thread(runtime, thread_id))
    except Exception as exc:
        detail = str(exc).strip() or "chat stream failed"
        yield sse_event("error", {"detail": detail})
