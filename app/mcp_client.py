from __future__ import annotations

import asyncio
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

from app.config import Settings, project_root


def personal_mcp_script() -> str:
    return str(project_root() / "mcp_servers" / "personal.py")


def parse_tool_payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        texts = []
        for item in raw:
            if isinstance(item, str):
                texts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                texts.append(item.get("text") or "")
        return parse_tool_payload("".join(texts))
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}
        if isinstance(data, dict):
            return data
        return {"text": text}
    return {"text": str(raw)}


def run_coroutine(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


async def aload_mcp_tools(settings: Settings | None = None) -> list:
    settings = settings or Settings()
    client = MultiServerMCPClient(
        {
            "personal": {
                "transport": "stdio",
                "command": sys.executable,
                "args": [personal_mcp_script()],
                "cwd": str(project_root()),
            }
        }
    )
    return await client.get_tools()


def load_mcp_tools(settings: Settings | None = None) -> list:
    return run_coroutine(aload_mcp_tools(settings))


@dataclass
class DayFacts:
    weekday: str
    weather: str
    temperature_c: float | None
    city: str
    iso: str = ""
    date: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class StaticFactsProvider:
    def __init__(self, facts: DayFacts):
        self.facts = facts

    async def aget_facts(self, city: str) -> DayFacts:
        if city and city != self.facts.city:
            return DayFacts(
                weekday=self.facts.weekday,
                weather=self.facts.weather,
                temperature_c=self.facts.temperature_c,
                city=city,
                iso=self.facts.iso,
                date=self.facts.date,
            )
        return self.facts


def _tool_by_name(tools: list, name: str):
    for item in tools:
        if getattr(item, "name", None) == name:
            return item
    raise KeyError(name)


async def _ainvoke_tool(tool, payload: dict[str, Any]) -> dict[str, Any]:
    if hasattr(tool, "ainvoke"):
        raw = await tool.ainvoke(payload)
    else:
        raw = tool.invoke(payload)
    return parse_tool_payload(raw)


class McpFactsProvider:
    def __init__(self, tools: list, default_city: str = "广州"):
        self.tools = tools
        self.default_city = default_city

    async def aget_facts(self, city: str | None = None) -> DayFacts:
        city = city or self.default_city
        datetime_payload = await _ainvoke_tool(_tool_by_name(self.tools, "get_current_datetime"), {})
        weather_payload = await _ainvoke_tool(
            _tool_by_name(self.tools, "get_weather"),
            {"city": city},
        )
        temperature = weather_payload.get("temperature_c")
        if temperature is not None:
            temperature = float(temperature)
        return DayFacts(
            weekday=str(datetime_payload.get("weekday") or ""),
            weather=str(weather_payload.get("weather") or ""),
            temperature_c=temperature,
            city=str(weather_payload.get("city") or city),
            iso=str(datetime_payload.get("iso") or ""),
            date=str(datetime_payload.get("date") or ""),
        )


def default_test_facts(city: str = "广州") -> DayFacts:
    return DayFacts(
        weekday="星期四",
        weather="小雨",
        temperature_c=22.5,
        city=city,
        iso="2026-09-17T08:00:00+08:00",
        date="2026-09-17",
    )