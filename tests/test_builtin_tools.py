from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from langchain_core.tools import tool

from app.runtime import build_test_runtime
from app.tools import build_tools
from tests.fakes import static_facts_provider


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, routes: dict[str, dict]):
        self.routes = routes
        self.calls: list[tuple[str, dict]] = []

    def get(self, url: str, params=None):
        self.calls.append((url, params or {}))
        for key, payload in self.routes.items():
            if key in url:
                return FakeResponse(payload)
        raise AssertionError(f"unexpected url {url}")

    def close(self) -> None:
        return None


def _tool_names(tools) -> list[str]:
    return [str(getattr(item, "name", "")) for item in tools]


def _tool_by_name(tools, name: str):
    matches = [item for item in tools if getattr(item, "name", None) == name]
    assert len(matches) == 1, name
    return matches[0]


def _payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    raise AssertionError(f"expected dict payload, got {raw!r}")


def test_runtime_registers_builtin_datetime_and_weather_without_mcp(
    settings,
    embeddings,
    llm,
    image_client,
    video_client,
    media_root,
    knowledge_dir,
    email_client,
    dify_client,
):
    runtime = build_test_runtime(
        settings,
        embeddings,
        llm,
        image_client,
        video_client,
        media_root,
        knowledge_dir,
        extra_tools=[],
        email_client=email_client,
        facts_provider=static_facts_provider(settings.assistant_city),
        dify_client=dify_client,
    )
    names = _tool_names(runtime.tools)
    assert names.count("get_current_datetime") == 1
    assert names.count("get_weather") == 1


def test_builtin_datetime_uses_fake_clock(settings, image_client, video_client, media_root):
    now = datetime(2026, 9, 17, 8, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    tools = build_tools(
        store=None,
        image_client=image_client,
        video_client=video_client,
        settings=settings,
        media_root=media_root,
        extra_tools=[],
        clock=lambda: now,
        weather_provider=lambda city: {"city": city, "weather": "小雨", "temperature_c": 22.5},
    )
    payload = _payload(_tool_by_name(tools, "get_current_datetime").invoke({}))
    assert payload["weekday"] == "星期四"
    assert payload["date"] == "2026-09-17"
    assert payload["timezone"] == "Asia/Shanghai"


def test_builtin_weather_uses_fake_provider(settings, image_client, video_client, media_root):
    tools = build_tools(
        store=None,
        image_client=image_client,
        video_client=video_client,
        settings=settings,
        media_root=media_root,
        extra_tools=[],
        clock=lambda: datetime(2026, 9, 17, 8, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        weather_provider=lambda city: {"city": city, "weather": "晴", "temperature_c": 18.0},
    )
    payload = _payload(_tool_by_name(tools, "get_weather").invoke({"city": "上海"}))
    assert payload == {"city": "上海", "weather": "晴", "temperature_c": 18.0}


def test_builtin_weather_uses_injected_client_not_public_network(
    settings, image_client, video_client, media_root
):
    client = FakeClient(
        {
            "api.open-meteo.com": {
                "current": {"temperature_2m": 22.5, "weather_code": 61},
            }
        }
    )
    tools = build_tools(
        store=None,
        image_client=image_client,
        video_client=video_client,
        settings=settings,
        media_root=media_root,
        extra_tools=[],
        weather_client=client,
    )
    payload = _payload(_tool_by_name(tools, "get_weather").invoke({"city": "广州"}))
    assert payload["city"] == "广州"
    assert payload["temperature_c"] == 22.5
    assert payload["weather"] == "小雨"
    assert any("api.open-meteo.com" in url for url, _ in client.calls)


def test_name_conflict_prefers_builtin_and_keeps_other_extra_tools(
    settings, image_client, video_client, media_root
):
    @tool
    def get_current_datetime() -> dict[str, Any]:
        """MCP datetime extra tool."""
        return {"weekday": "FROM_MCP"}

    @tool
    def get_weather(city: str = "广州") -> dict[str, Any]:
        """MCP weather extra tool."""
        return {"city": city, "weather": "FROM_MCP"}

    @tool
    def extra_fact() -> dict[str, Any]:
        """Unrelated extra tool kept after merge."""
        return {"ok": True}

    tools = build_tools(
        store=None,
        image_client=image_client,
        video_client=video_client,
        settings=settings,
        media_root=media_root,
        extra_tools=[get_current_datetime, get_weather, extra_fact],
        clock=lambda: datetime(2026, 9, 17, 8, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        weather_provider=lambda city: {"city": city, "weather": "小雨", "temperature_c": 22.5},
    )
    names = _tool_names(tools)
    assert names.count("get_current_datetime") == 1
    assert names.count("get_weather") == 1
    assert names.count("extra_fact") == 1
    datetime_payload = _payload(_tool_by_name(tools, "get_current_datetime").invoke({}))
    weather_payload = _payload(_tool_by_name(tools, "get_weather").invoke({}))
    assert datetime_payload["weekday"] == "星期四"
    assert weather_payload["weather"] == "小雨"


def test_default_runtime_weather_does_not_request_open_meteo(runtime, monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("default tests must not request Open-Meteo")

    monkeypatch.setattr("mcp_servers.personal.httpx.Client", blocked)
    payload = _payload(_tool_by_name(runtime.tools, "get_weather").invoke({"city": "广州"}))
    assert payload["city"] == "广州"
    assert payload["weather"] == "小雨"
    assert payload["temperature_c"] == 22.5
