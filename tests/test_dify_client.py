from __future__ import annotations

import json

import httpx

from app.dify_client import DifyClient


def test_live_disabled_without_http_client_does_not_post(settings, monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("DifyClient must not create httpx.Client when live is disabled")

    monkeypatch.setattr("app.dify_client.httpx.Client", boom)
    client = DifyClient(settings)
    result = client.run("douyin-lead-discovery", {"account": "shop1"}, user="user-1")
    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["error"] == "dify live disabled"
    assert result["name"] == "douyin-lead-discovery"


def test_http_401_maps_to_auth_expired(settings):
    posts: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        posts.append(request)
        return httpx.Response(401, json={"message": "unauthorized"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    live_settings = settings.model_copy(update={"dify_api_key": "fake-key"})
    client = DifyClient(live_settings, http_client=http)
    result = client.run(
        "douyin-lead-discovery",
        {"account": "shop1", "no_send": False, "auto_login": True},
        user="user-1",
    )
    assert result["ok"] is False
    assert result["status"] == "auth_expired"
    assert result["error"] == "auth_expired"
    assert len(posts) == 1
    request = posts[0]
    assert str(request.url) == "https://dify.example.test/v1/workflows/run"
    assert request.headers["Authorization"] == "Bearer fake-key"
    body = json.loads(request.content)
    assert body["response_mode"] == "blocking"
    assert body["user"] == "user-1"
    assert body["inputs"]["no_send"] is False
    assert "user" not in body["inputs"]


def test_timeout_is_classified(settings):
    class TimeoutClient:
        def post(self, *_args, **_kwargs):
            raise httpx.TimeoutException("slow")

    live_settings = settings.model_copy(update={"dify_api_key": "fake-key"})
    client = DifyClient(live_settings, http_client=TimeoutClient())
    result = client.run("douyin-lead-discovery", {"account": "shop1"}, user="user-1")
    assert result["ok"] is False
    assert result["status"] == "timeout"
    assert "timeout" in (result["error"] or "")
