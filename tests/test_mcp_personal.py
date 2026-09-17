from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_core.messages import HumanMessage

from mcp_servers.personal import current_datetime_payload, weather_description, weather_payload
from tests.fakes import ai_text


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


def test_datetime_payload_weekday():
    now = datetime(2026, 9, 17, 8, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    payload = current_datetime_payload(now=now)
    assert payload["weekday"] == "星期四"
    assert payload["date"] == "2026-09-17"


def test_weather_payload_uses_guangzhou_and_open_meteo():
    client = FakeClient(
        {
            "api.open-meteo.com": {
                "current": {"temperature_2m": 22.5, "weather_code": 61},
            }
        }
    )
    payload = weather_payload("广州", client=client)
    assert payload["city"] == "广州"
    assert payload["temperature_c"] == 22.5
    assert payload["weather"] == "小雨"
    assert any("api.open-meteo.com" in url for url, _ in client.calls)


def test_weather_description_unknown_code():
    assert weather_description(None) == "未知"
    assert "天气代码" in weather_description(1234)


def test_graph_nodes_remain_chatbot_and_tools(runtime, llm):
    nodes = set(runtime.graph.get_graph().nodes)
    assert "chatbot" in nodes
    assert "tools" in nodes
    extra = nodes - {"chatbot", "tools", "__start__", "__end__"}
    assert extra == set()
    llm.responses = [ai_text("你好")]
    runtime.graph.invoke(
        {"messages": [HumanMessage(content="你好")]},
        {"configurable": {"thread_id": "nodes"}},
    )
    names = {getattr(tool, "name", None) for tool in llm.bound_tools}
    assert names >= {
        "search_kb",
        "generate_image",
        "generate_video",
        "remember_fact",
        "recall_facts",
        "send_email",
        "get_current_datetime",
        "get_weather",
    }