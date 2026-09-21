from __future__ import annotations

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
