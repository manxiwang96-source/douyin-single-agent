from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Callable

from langchain_core.messages import AIMessage

from app.media_paths import allocate_media_path

TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
DUMMY_MP4 = b"ftypmp42fake-mp4-bytes"


class ScriptedLLM:
    def __init__(self, responses: list | None = None):
        self.responses = list(responses or [])
        self.calls: list[Any] = []
        self.bind_kwargs: dict[str, Any] = {}
        self.bound_tools = None

    def bind_tools(self, tools, **kwargs):
        self.bound_tools = tools
        self.bind_kwargs = kwargs
        return self

    def invoke(self, messages):
        self.calls.append(messages)
        if not self.responses:
            raise AssertionError("ScriptedLLM has no remaining responses")
        item = self.responses.pop(0)
        if callable(item):
            item = item(messages)
        return item


def ai_text(content: str) -> AIMessage:
    return AIMessage(content=content)


def ai_tool(name: str, args: dict[str, Any], call_id: str = "call-1") -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"name": name, "args": args, "id": call_id, "type": "tool_call"}
        ],
    )


class FakeImageClient:
    def __init__(self, media_root: Path):
        self.media_root = media_root
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def generate(self, prompt: str, params: dict[str, Any] | None = None) -> Path:
        self.calls.append((prompt, params))
        path = allocate_media_path(self.media_root, "images", ".png")
        path.write_bytes(TINY_PNG)
        return path


class FakeVideoClient:
    def __init__(self, media_root: Path):
        self.media_root = media_root
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def generate(self, prompt: str, params: dict[str, Any] | None = None) -> Path:
        self.calls.append((prompt, params))
        path = allocate_media_path(self.media_root, "videos", ".mp4")
        path.write_bytes(DUMMY_MP4)
        return path
