from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from mcp.server.fastmcp import FastMCP

DEFAULT_CITY = "广州"
DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_COORDS = {
    "广州": (23.1291, 113.2644),
    "guangzhou": (23.1291, 113.2644),
}
WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
WMO_WEATHER = {
    0: "晴",
    1: "晴间多云",
    2: "多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "大毛毛雨",
    56: "冻毛毛雨",
    57: "强冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "冻雨",
    67: "强冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "雪粒",
    80: "阵雨",
    81: "中阵雨",
    82: "强阵雨",
    85: "阵雪",
    86: "强阵雪",
    95: "雷阵雨",
    96: "雷阵雨伴冰雹",
    99: "强雷阵雨伴冰雹",
}

mcp = FastMCP("personal")


def current_datetime_payload(
    now: datetime | None = None,
    timezone: str = DEFAULT_TIMEZONE,
) -> dict[str, Any]:
    zone = ZoneInfo(timezone)
    current = now.astimezone(zone) if now is not None else datetime.now(zone)
    return {
        "iso": current.isoformat(timespec="seconds"),
        "date": current.date().isoformat(),
        "time": current.strftime("%H:%M"),
        "weekday": WEEKDAYS[current.weekday()],
        "timezone": timezone,
    }


def weather_description(code: int | None) -> str:
    if code is None:
        return "未知"
    return WMO_WEATHER.get(int(code), f"天气代码{code}")


def resolve_city_coords(city: str, client: httpx.Client | None = None) -> tuple[str, float, float]:
    name = (city or DEFAULT_CITY).strip() or DEFAULT_CITY
    coords = DEFAULT_COORDS.get(name) or DEFAULT_COORDS.get(name.lower())
    if coords is not None:
        return name, coords[0], coords[1]
    http = client or httpx.Client(timeout=10.0)
    owns = client is None
    try:
        response = http.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": name, "count": 1, "language": "zh"},
        )
        response.raise_for_status()
        results = (response.json() or {}).get("results") or []
        if not results:
            raise RuntimeError(f"unknown city: {name}")
        item = results[0]
        return str(item.get("name") or name), float(item["latitude"]), float(item["longitude"])
    finally:
        if owns:
            http.close()


def fetch_weather(
    latitude: float,
    longitude: float,
    timezone: str = DEFAULT_TIMEZONE,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    http = client or httpx.Client(timeout=10.0)
    owns = client is None
    try:
        response = http.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": "temperature_2m,weather_code",
                "timezone": timezone,
            },
        )
        response.raise_for_status()
        current = (response.json() or {}).get("current") or {}
        temperature = current.get("temperature_2m")
        code = current.get("weather_code")
        return {
            "temperature_c": None if temperature is None else float(temperature),
            "weather_code": code,
            "weather": weather_description(code),
        }
    finally:
        if owns:
            http.close()


def weather_payload(
    city: str = DEFAULT_CITY,
    timezone: str = DEFAULT_TIMEZONE,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    resolved, latitude, longitude = resolve_city_coords(city, client=client)
    weather = fetch_weather(latitude, longitude, timezone=timezone, client=client)
    return {
        "city": resolved,
        "latitude": latitude,
        "longitude": longitude,
        **weather,
    }


@mcp.tool()
def get_current_datetime() -> dict[str, Any]:
    """Return today's weekday and the current local datetime."""
    return current_datetime_payload()


@mcp.tool()
def get_weather(city: str = DEFAULT_CITY) -> dict[str, Any]:
    """Return the current weather and temperature for a city. Defaults to Guangzhou."""
    return weather_payload(city)


if __name__ == "__main__":
    mcp.run(transport="stdio")