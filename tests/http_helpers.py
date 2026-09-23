from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient

from app.main import create_app


def make_client(runtime) -> TestClient:
    return TestClient(create_app(runtime))


def register_and_login(
    client: TestClient,
    login_name: str = "alice",
    password: str = "password123",
) -> dict:
    registered = client.post(
        "/v1/auth/register",
        json={"login_name": login_name, "password": password},
    )
    assert registered.status_code == 201, registered.text
    login = client.post(
        "/v1/auth/login",
        json={"login_name": login_name, "password": password},
    )
    assert login.status_code == 200, login.text
    body = login.json()
    client.headers["Authorization"] = f"Bearer {body['token']}"
    return body


def create_and_open(
    client: TestClient,
    *,
    title: str = "agent-a",
    intro: str = "ops",
    template_code: str = "douyin_ops",
) -> dict:
    created = client.post(
        "/v1/agent-instances",
        json={"template_code": template_code, "title": title, "intro": intro},
    )
    assert created.status_code == 201, created.text
    instance = created.json()
    opened = client.post(f"/v1/agent-instances/{instance['agent_instance_id']}/open")
    assert opened.status_code == 200, opened.text
    return {**instance, **opened.json()}


def parse_sse_events(text: str) -> list[dict[str, Any]]:
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    events: list[dict[str, Any]] = []
    for block in normalized.split("\n\n"):
        event_name = None
        data_lines: list[str] = []
        for raw_line in block.split("\n"):
            line = raw_line.strip("\ufeff")
            if not line or line.startswith(":"):
                continue
            if line.startswith("event:"):
                event_name = line[6:].strip()
                continue
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if event_name is None and not data_lines:
            continue
        raw = "\n".join(data_lines)
        payload: Any = raw
        if raw:
            try:
                payload = json.loads(raw)
            except (TypeError, ValueError):
                payload = raw
        events.append({"event": event_name or "message", "data": payload, "raw": raw})
    return events


class ChatHttpResponse:
    def __init__(self, response, events: list[dict[str, Any]] | None = None):
        self.status_code = response.status_code
        self.headers = response.headers
        self.text = response.text
        self.content = response.content
        self._response = response
        self.events = events if events is not None else []

    def json(self):
        if self.status_code != 200:
            return self._response.json()
        threads = [item["data"] for item in self.events if item.get("event") == "thread"]
        if not threads:
            raise AssertionError(f"missing thread SSE event: {self.text}")
        return threads[-1]


def post_chat(client: TestClient, url: str, json: dict | None = None) -> ChatHttpResponse:
    response = client.post(url, json=json)
    if response.status_code != 200:
        return ChatHttpResponse(response)
    return ChatHttpResponse(response, parse_sse_events(response.text))
