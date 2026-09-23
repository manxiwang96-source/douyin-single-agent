from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.graph import interrupt_payload
from app.message_metadata import message_metadata


def _media_from_tool_content(content: str) -> dict[str, Any] | None:
    try:
        data = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("ok") and data.get("type") in {"image", "video"} and data.get("url"):
        return {"type": data["type"], "url": data["url"]}
    return None


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


def _bubble(role: str, content: str, media: list[dict[str, Any]], message) -> dict[str, Any]:
    metadata = message_metadata(message)
    return {
        "role": role,
        "content": content,
        "media": media,
        "message_id": metadata.get("message_id"),
        "client_message_id": metadata.get("client_message_id"),
        "created_at": metadata.get("created_at"),
    }


def api_messages_from_state(values: dict[str, Any]) -> list[dict[str, Any]]:
    messages = values.get("messages") or []
    bubbles: list[dict[str, Any]] = []
    buffered_media: list[dict[str, Any]] = []
    for message in messages:
        if isinstance(message, HumanMessage):
            bubbles.append(_bubble("user", _text(message), [], message))
            continue
        if isinstance(message, ToolMessage):
            media = _media_from_tool_content(_text(message))
            if media:
                buffered_media.append(media)
            continue
        if isinstance(message, AIMessage):
            if message.tool_calls:
                continue
            bubbles.append(_bubble("assistant", _text(message), list(buffered_media), message))
            buffered_media = []
    if buffered_media:
        bubbles.append(_bubble("assistant", "", buffered_media, messages[-1]))
    return bubbles


def serialize_thread(runtime, thread_id: str) -> dict[str, Any]:
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = runtime.graph.get_state(config)
    values = snapshot.values or {}
    pending = interrupt_payload(snapshot)
    status = "interrupted" if pending else "idle"
    return {
        "id": thread_id,
        "status": status,
        "timezone": runtime.settings.assistant_timezone,
        "messages": api_messages_from_state(values),
        "interrupt": None
        if pending is None
        else {
            "type": pending.get("type", "review_media"),
            "tool": pending.get("tool"),
            "prompt": pending.get("prompt"),
            "params": pending.get("params") or {},
        },
        "last_image_path": values.get("last_image_path"),
        "last_video_path": values.get("last_video_path"),
    }
