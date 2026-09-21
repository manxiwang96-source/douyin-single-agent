from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from app.media_paths import allocate_media_path
from app.mcp_client import DayFacts, StaticFactsProvider, default_test_facts

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

    def invoke(self, messages, **kwargs):
        self.calls.append(messages)
        if not self.responses:
            raise AssertionError("ScriptedLLM has no remaining responses")
        item = self.responses.pop(0)
        if callable(item):
            item = item(messages)
        return item

    async def ainvoke(self, messages, **kwargs):
        return self.invoke(messages, **kwargs)


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

    def generate(
        self,
        prompt: str,
        params: dict[str, Any] | None = None,
        *,
        user_id: str | None = None,
        agent_instance_id: str | None = None,
    ) -> Path:
        self.calls.append((prompt, params))
        path = allocate_media_path(
            self.media_root,
            "images",
            ".png",
            user_id=user_id,
            agent_instance_id=agent_instance_id,
        )
        path.write_bytes(TINY_PNG)
        return path


class FakeVideoClient:
    def __init__(self, media_root: Path):
        self.media_root = media_root
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def generate(
        self,
        prompt: str,
        params: dict[str, Any] | None = None,
        *,
        user_id: str | None = None,
        agent_instance_id: str | None = None,
    ) -> Path:
        self.calls.append((prompt, params))
        path = allocate_media_path(
            self.media_root,
            "videos",
            ".mp4",
            user_id=user_id,
            agent_instance_id=agent_instance_id,
        )
        path.write_bytes(DUMMY_MP4)
        return path


class FakeEmailClient:
    def __init__(self, to: str = "test@example.com"):
        self.to = to
        self.sends: list[dict[str, Any]] = []

    def send(self, *, subject: str, body: str, to: str | None = None) -> dict[str, Any]:
        record = {
            "ok": True,
            "subject": subject,
            "body": body,
            "to": to or self.to,
        }
        self.sends.append(record)
        return record



class FakeDifyClient:
    def __init__(self, result: dict[str, Any] | None = None):
        self.calls: list[dict[str, Any]] = []
        self.queue: list[Any] = []
        self.result = result or {
            "ok": True,
            "name": "douyin-lead-discovery",
            "workflow_run_id": "wf-fake-1",
            "status": "succeeded",
            "outputs": {
                "list_comment": [
                    {
                        "platform_comment_id": "c1",
                        "video_id": "v1",
                        "source_text": "想买",
                        "candidate_reply": "私信你",
                        "status": "sent",
                    }
                ],
                "list_message": [
                    {
                        "platform_message_id": "m1",
                        "video_id": "v1",
                        "source_text": "多少钱",
                        "status": "sent",
                    }
                ],
                "snapshot": [
                    {
                        "platform_video_id": "v1",
                        "title": "demo",
                        "url": "https://example.test/v1",
                        "keyword": "敏感肌",
                    }
                ],
            },
            "error": None,
        }

    def enqueue(self, result: Any) -> None:
        self.queue.append(result)

    def run(self, name: str, inputs: dict[str, Any], *, user: str | None = None) -> dict[str, Any]:
        self.calls.append({"name": name, "inputs": dict(inputs), "user": user})
        if self.queue:
            item = self.queue.pop(0)
            if callable(item):
                payload = item(name, inputs, user)
            else:
                payload = dict(item)
        else:
            payload = dict(self.result)
        payload.setdefault("name", name)
        return payload


def fake_datetime_weather_tools(facts: DayFacts | None = None) -> list:
    facts = facts or default_test_facts()

    @tool
    def get_current_datetime() -> dict[str, Any]:
        """Return today's weekday and the current local datetime."""
        return {
            "iso": facts.iso,
            "date": facts.date,
            "weekday": facts.weekday,
            "timezone": "Asia/Shanghai",
        }

    @tool
    def get_weather(city: str = "广州") -> dict[str, Any]:
        """Return the current weather and temperature for a city."""
        return {
            "city": city or facts.city,
            "weather": facts.weather,
            "temperature_c": facts.temperature_c,
        }

    return [get_current_datetime, get_weather]


def static_facts_provider(city: str = "广州") -> StaticFactsProvider:
    return StaticFactsProvider(default_test_facts(city))
