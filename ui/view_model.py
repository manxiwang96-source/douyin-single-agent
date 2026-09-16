from __future__ import annotations

from typing import Any


def absolute_media_url(api_base: str, url: str) -> str:
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    base = api_base.rstrip("/")
    return f"{base}{url if url.startswith('/') else '/' + url}"


def message_previews(message: dict[str, Any], api_base: str) -> list[dict[str, str]]:
    previews: list[dict[str, str]] = []
    for item in message.get("media") or []:
        kind = item.get("type")
        url = absolute_media_url(api_base, item.get("url") or "")
        if kind == "image" and url:
            previews.append({"widget": "image", "url": url})
        elif kind == "video" and url:
            previews.append({"widget": "video", "url": url})
    return previews


def build_chat_view(thread: dict[str, Any], api_base: str) -> dict[str, Any]:
    messages = []
    for item in thread.get("messages") or []:
        messages.append(
            {
                "role": item.get("role"),
                "content": item.get("content") or "",
                "previews": message_previews(item, api_base),
            }
        )
    pending = thread.get("interrupt")
    interrupted = thread.get("status") == "interrupted" or bool(pending)
    return {
        "messages": messages,
        "interrupt": pending,
        "chat_input_enabled": not interrupted,
    }


def interrupt_card(view: dict[str, Any]) -> dict[str, Any]:
    pending = view.get("interrupt") or {}
    visible = bool(pending)
    return {
        "visible": visible,
        "tool": pending.get("tool") if visible else None,
        "prompt": pending.get("prompt") if visible else "",
        "params": pending.get("params") if visible else {},
    }
