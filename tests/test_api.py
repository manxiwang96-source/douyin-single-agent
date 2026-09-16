from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from tests.fakes import DUMMY_MP4, TINY_PNG, ai_text, ai_tool


def test_import_main_does_not_boot_runtime():
    import app.main as main

    assert getattr(main, "app", None) is None


def test_health_and_config(runtime):
    client = TestClient(create_app(runtime))
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    config = client.get("/v1/config")
    assert config.status_code == 200
    body = config.json()
    assert body["image_quality"] == "low"
    assert body["image_size"] == "1024x1536"
    assert body["video_duration"] == 2
    assert body["video_resolution"] == "480P"


def test_thread_message_resume_and_media(runtime, llm, image_client, media_root):
    llm.responses = [
        ai_tool("generate_image", {"prompt": "bottle"}),
        ai_text("配图已就绪"),
    ]
    client = TestClient(create_app(runtime))
    created = client.post("/v1/threads")
    assert created.status_code == 200
    thread_id = created.json()["id"]

    empty = client.get(f"/v1/threads/{thread_id}")
    assert empty.status_code == 200
    assert empty.json()["status"] == "idle"

    interrupted = client.post(
        f"/v1/threads/{thread_id}/messages",
        json={"content": "请配图"},
    )
    assert interrupted.status_code == 200
    body = interrupted.json()
    assert body["status"] == "interrupted"
    assert body["interrupt"]["type"] == "review_media"
    assert body["interrupt"]["tool"] == "generate_image"

    blocked = client.post(
        f"/v1/threads/{thread_id}/messages",
        json={"content": "再发一条"},
    )
    assert blocked.status_code == 409

    resumed = client.post(
        f"/v1/threads/{thread_id}/resume",
        json={"action": "approve", "prompt": "bottle", "params": {}},
    )
    assert resumed.status_code == 200
    payload = resumed.json()
    assert payload["status"] == "idle"
    media_items = []
    for message in payload["messages"]:
        media_items.extend(message.get("media") or [])
    assert media_items
    assert media_items[0]["type"] == "image"
    url = media_items[0]["url"]
    assert url.startswith("/v1/media/images/")

    media = client.get(url)
    assert media.status_code == 200
    assert media.headers["content-type"].startswith("image/png")
    assert media.content == TINY_PNG
    assert image_client.calls


def test_skip_resume_has_no_media_url(runtime, llm, image_client):
    llm.responses = [
        ai_tool("generate_image", {"prompt": "skip"}),
        ai_text("已跳过"),
    ]
    client = TestClient(create_app(runtime))
    thread_id = client.post("/v1/threads").json()["id"]
    client.post(f"/v1/threads/{thread_id}/messages", json={"content": "图"})
    resumed = client.post(
        f"/v1/threads/{thread_id}/resume",
        json={"action": "skip"},
    )
    assert resumed.status_code == 200
    media_items = [
        item
        for message in resumed.json()["messages"]
        for item in (message.get("media") or [])
    ]
    assert media_items == []
    assert image_client.calls == []


def test_video_media_content_type(runtime, llm, video_client):
    llm.responses = [
        ai_tool("generate_video", {"prompt": "pour"}),
        ai_text("视频好了"),
    ]
    client = TestClient(create_app(runtime))
    thread_id = client.post("/v1/threads").json()["id"]
    client.post(f"/v1/threads/{thread_id}/messages", json={"content": "视频"})
    resumed = client.post(
        f"/v1/threads/{thread_id}/resume",
        json={"action": "approve"},
    )
    media_items = [
        item
        for message in resumed.json()["messages"]
        for item in (message.get("media") or [])
    ]
    assert media_items[0]["type"] == "video"
    media = client.get(media_items[0]["url"])
    assert media.status_code == 200
    assert media.headers["content-type"].startswith("video/mp4")
    assert media.content == DUMMY_MP4


def test_unknown_thread_404(runtime):
    client = TestClient(create_app(runtime))
    response = client.get("/v1/threads/missing")
    assert response.status_code == 404
