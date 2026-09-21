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


def with_pending_user(
    messages: list[dict[str, Any]], pending: str | None
) -> list[dict[str, Any]]:
    text = (pending or "").strip()
    if not text:
        return list(messages)
    for item in messages:
        if item.get("role") == "user" and (item.get("content") or "") == text:
            return list(messages)
    return list(messages) + [{"role": "user", "content": text, "previews": []}]


def agent_mode_label(mode: str | None) -> str:
    if (mode or "single") == "single":
        return "单智能体模式"
    return "多智能体模式"


def auth_gate(session: dict[str, Any]) -> dict[str, Any]:
    token = str(session.get("token") or "").strip()
    if not token:
        return {
            "authenticated": False,
            "page": "login",
            "thread_id": None,
            "agent_instance_id": None,
        }
    page = session.get("page") or "plaza"
    thread_id = session.get("thread_id")
    agent_instance_id = session.get("agent_instance_id")
    if page == "chat" and thread_id and agent_instance_id:
        return {
            "authenticated": True,
            "page": "chat",
            "thread_id": thread_id,
            "agent_instance_id": agent_instance_id,
        }
    return {
        "authenticated": True,
        "page": "plaza",
        "thread_id": None,
        "agent_instance_id": None,
    }


def plaza_cards(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for item in items or []:
        cards.append(
            {
                "agent_instance_id": item.get("agent_instance_id"),
                "title": item.get("title") or "",
                "intro": item.get("intro") or "",
                "avatar_url": item.get("avatar_url"),
                "agent_mode": item.get("agent_mode") or "single",
                "agent_mode_label": agent_mode_label(item.get("agent_mode")),
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
            }
        )
    return cards


def create_instance_payload(
    title: str,
    intro: str = "",
    avatar: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "template_code": "douyin_ops",
        "title": title,
        "intro": intro or "",
    }
    if avatar:
        payload["avatar"] = avatar
    return payload


def sidebar_view(payload: dict[str, Any] | None) -> dict[str, Any]:
    data = payload or {}
    return {
        "title": data.get("title") or "",
        "intro": data.get("intro") or "",
        "capability_description": data.get("capability_description") or "",
        "development_notes": data.get("development_notes") or "",
        "agent_mode": data.get("agent_mode") or "single",
        "agent_mode_label": data.get("agent_mode_label")
        or agent_mode_label(data.get("agent_mode")),
        "knowledge_documents": list(data.get("knowledge_documents") or []),
        "workflows": list(data.get("workflows") or []),
        "tools": list(data.get("tools") or []),
        "readonly": True,
    }
