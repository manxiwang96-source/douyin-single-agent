from __future__ import annotations

import json
from typing import Annotated, Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Command, interrupt

from app.knowledge import format_kb_hits
from app.knowledge import search_kb as kb_search
from app.media_paths import media_url_for

MEDIA_TOOL_NAMES = {"generate_image", "generate_video"}
KB_TOOL_NAMES = {"search_kb"}


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


def build_tools(*, store, image_client, video_client, settings, media_root):
    @tool
    def search_kb(query: str, k: int = 4) -> str:
        """Search the demo Xiaohongshu operations knowledge base. Call this before writing copy."""
        hits = kb_search(store, query=query, k=int(k or 4))
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
        path = image_client.generate(final_prompt, params)
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
        path = video_client.generate(final_prompt, params)
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

    return [search_kb, generate_image, generate_video]
