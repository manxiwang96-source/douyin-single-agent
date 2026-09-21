from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any
from uuid import UUID

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.config import get_config
from langgraph.types import Command, interrupt

from app.knowledge import format_kb_hits, kb_namespace, profile_namespace
from app.knowledge import search_kb as kb_search
from app.media_paths import media_url_for
from app.repository import NotFoundError

MEDIA_TOOL_NAMES = {"generate_image", "generate_video"}
KB_TOOL_NAMES = {"search_kb"}
PROFILE_NAMESPACE = ("assistant", "profile")


def _runtime_configurable() -> dict[str, Any]:
    try:
        config = get_config()
    except Exception:
        return {}
    return dict((config or {}).get("configurable") or {})


def _owner_ids() -> tuple[str | None, str | None, str | None]:
    configurable = _runtime_configurable()
    user_id = configurable.get("user_id")
    agent_instance_id = configurable.get("agent_instance_id")
    thread_id = configurable.get("thread_id")
    return (
        str(user_id) if user_id else None,
        str(agent_instance_id) if agent_instance_id else None,
        str(thread_id) if thread_id else None,
    )


def _decision(
    raw: Any, default_prompt: str, default_params: dict[str, Any]
) -> tuple[str, str, dict[str, Any]]:
    if not isinstance(raw, dict):
        raw = {"action": str(raw)}
    action = str(raw.get("action") or "approve").lower()
    prompt = raw.get("prompt") or default_prompt
    extra = raw.get("params") or {}
    if not isinstance(extra, dict):
        extra = {}
    return action, prompt, {**default_params, **extra}


def _skip_update(tool_name: str, tool_call_id: str) -> dict[str, Any]:
    return {
        "messages": [
            ToolMessage(
                content="User skipped media generation.",
                tool_call_id=tool_call_id,
                name=tool_name,
            )
        ]
    }


def _record_media_asset(
    *,
    business_repo,
    user_id: str | None,
    agent_instance_id: str | None,
    thread_id: str | None,
    kind: str,
    path,
    media_root,
) -> None:
    if business_repo is None or not user_id or not agent_instance_id:
        return
    try:
        relative = path.resolve().relative_to(media_root.resolve()).as_posix()
        business_repo.add_media_asset(
            UUID(str(user_id)),
            UUID(str(agent_instance_id)),
            kind=kind,
            storage_uri=relative,
            thread_id=thread_id,
        )
    except (NotFoundError, ValueError):
        return


def _media_update(
    *,
    tool_name: str,
    tool_call_id: str,
    kind: str,
    path,
    media_root,
    path_key: str,
) -> dict[str, Any]:
    url = media_url_for(path, media_root)
    payload = {
        "ok": True,
        "type": kind,
        "path": str(path),
        "url": url,
    }
    return {
        path_key: str(path),
        "messages": [
            ToolMessage(
                content=json.dumps(payload, ensure_ascii=False),
                tool_call_id=tool_call_id,
                name=tool_name,
            )
        ],
    }


def build_tools(
    *,
    store,
    image_client,
    video_client,
    settings,
    media_root,
    memory_store=None,
    email_client=None,
    extra_tools=None,
    business_repo=None,
):
    @tool
    def search_kb(query: str, k: int = 4) -> str:
        """Search the current agent-instance knowledge base. Only call this for a supplementary lookup."""
        user_id, agent_instance_id, _thread_id = _owner_ids()
        namespace = ("kb",)
        target = store
        if user_id and agent_instance_id:
            namespace = kb_namespace(user_id, agent_instance_id)
            target = memory_store if memory_store is not None else store
        hits = kb_search(target, query=query, k=int(k or 4), namespace=namespace)
        return format_kb_hits(hits)

    @tool
    def generate_image(
        prompt: str,
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """Generate a 3:4 Xiaohongshu image. Pauses for human approval before calling the image API."""
        default_params = settings.default_image_params()
        action, final_prompt, params = _decision(
            interrupt(
                {
                    "type": "review_media",
                    "tool": "generate_image",
                    "prompt": prompt,
                    "params": default_params,
                }
            ),
            prompt,
            default_params,
        )
        if action in {"skip", "reject", "cancel"}:
            return Command(update=_skip_update("generate_image", tool_call_id))
        user_id, agent_instance_id, thread_id = _owner_ids()
        path = image_client.generate(
            final_prompt,
            params,
            user_id=user_id,
            agent_instance_id=agent_instance_id,
        )
        _record_media_asset(
            business_repo=business_repo,
            user_id=user_id,
            agent_instance_id=agent_instance_id,
            thread_id=thread_id,
            kind="image",
            path=path,
            media_root=media_root,
        )
        return Command(
            update=_media_update(
                tool_name="generate_image",
                tool_call_id=tool_call_id,
                kind="image",
                path=path,
                media_root=media_root,
                path_key="last_image_path",
            )
        )

    @tool
    def generate_video(
        prompt: str,
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """Generate a 9:16 Xiaohongshu video. Pauses for human approval before calling the video API."""
        default_params = settings.default_video_params()
        action, final_prompt, params = _decision(
            interrupt(
                {
                    "type": "review_media",
                    "tool": "generate_video",
                    "prompt": prompt,
                    "params": default_params,
                }
            ),
            prompt,
            default_params,
        )
        if action in {"skip", "reject", "cancel"}:
            return Command(update=_skip_update("generate_video", tool_call_id))
        user_id, agent_instance_id, thread_id = _owner_ids()
        path = video_client.generate(
            final_prompt,
            params,
            user_id=user_id,
            agent_instance_id=agent_instance_id,
        )
        _record_media_asset(
            business_repo=business_repo,
            user_id=user_id,
            agent_instance_id=agent_instance_id,
            thread_id=thread_id,
            kind="video",
            path=path,
            media_root=media_root,
        )
        return Command(
            update=_media_update(
                tool_name="generate_video",
                tool_call_id=tool_call_id,
                kind="video",
                path=path,
                media_root=media_root,
                path_key="last_video_path",
            )
        )

    tools = [search_kb, generate_image, generate_video]

    if memory_store is not None:

        @tool
        def remember_fact(fact: str) -> str:
            """Remember a long-term fact about the user across conversations."""
            text = (fact or "").strip()
            if not text:
                return "empty fact"
            user_id, agent_instance_id, _thread_id = _owner_ids()
            if not user_id or not agent_instance_id:
                return json.dumps({"ok": False, "error": "missing instance context"}, ensure_ascii=False)
            key = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
            memory_store.put(profile_namespace(user_id, agent_instance_id), key, {"text": text})
            return json.dumps({"ok": True, "key": key}, ensure_ascii=False)

        @tool
        def recall_facts(query: str = "") -> str:
            """Recall remembered facts about the user."""
            user_id, agent_instance_id, _thread_id = _owner_ids()
            if not user_id or not agent_instance_id:
                return "NO_FACTS"
            hits = memory_store.search(
                profile_namespace(user_id, agent_instance_id),
                query=query or None,
                limit=20,
            )
            facts = []
            for hit in hits:
                value = getattr(hit, "value", None) or {}
                text = value.get("text")
                if text:
                    facts.append(text)
            if not facts:
                return "NO_FACTS"
            return "\n".join(facts)

        tools.extend([remember_fact, recall_facts])

    if email_client is not None:

        @tool
        def send_email(subject: str, body: str) -> str:
            """Send an email to the configured personal inbox."""
            result = email_client.send(subject=subject, body=body)
            return json.dumps(
                {
                    "ok": True,
                    "subject": result.get("subject"),
                    "to": result.get("to"),
                },
                ensure_ascii=False,
            )

        tools.append(send_email)

    if extra_tools:
        tools.extend(list(extra_tools))
    return tools
