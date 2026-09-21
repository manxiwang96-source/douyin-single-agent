from __future__ import annotations

from tests.fakes import DUMMY_MP4, TINY_PNG, ai_text, ai_tool
from tests.http_helpers import create_and_open, make_client, register_and_login


def test_import_main_does_not_boot_runtime():
    import app.main as main

    assert getattr(main, "app", None) is None


def test_health_and_config(runtime):
    client = make_client(runtime)
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


def _open_thread(runtime):
    client = make_client(runtime)
    register_and_login(client)
    opened = create_and_open(client, title="agent-chat")
    return client, opened["thread_id"]


def test_thread_message_resume_and_media(runtime, llm, image_client, media_root):
    llm.responses = [
        ai_tool("generate_image", {"prompt": "bottle"}),
        ai_text("image ready"),
    ]
    client, thread_id = _open_thread(runtime)

    empty = client.get(f"/v1/threads/{thread_id}")
    assert empty.status_code == 200
    assert empty.json()["status"] == "idle"
    assert empty.json()["id"] == thread_id

    interrupted = client.post(
        f"/v1/threads/{thread_id}/messages",
        json={"content": "draw an image"},
    )
    assert interrupted.status_code == 200
    body = interrupted.json()
    assert body["status"] == "interrupted"
    assert body["interrupt"]["type"] == "review_media"
    assert body["interrupt"]["tool"] == "generate_image"

    blocked = client.post(
        f"/v1/threads/{thread_id}/messages",
        json={"content": "another one"},
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
    parts = url.strip("/").split("/")
    assert parts[:2] == ["v1", "media"]
    assert parts[4] == "images"
    assert len(parts) == 6

    media = client.get(url)
    assert media.status_code == 200
    assert media.headers["content-type"].startswith("image/png")
    assert media.content == TINY_PNG
    assert image_client.calls


def test_skip_resume_has_no_media_url(runtime, llm, image_client):
    llm.responses = [
        ai_tool("generate_image", {"prompt": "skip"}),
        ai_text("skipped"),
    ]
    client, thread_id = _open_thread(runtime)
    client.post(f"/v1/threads/{thread_id}/messages", json={"content": "image"})
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
        ai_text("video ready"),
    ]
    client, thread_id = _open_thread(runtime)
    client.post(f"/v1/threads/{thread_id}/messages", json={"content": "video"})
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
    client = make_client(runtime)
    register_and_login(client)
    response = client.get("/v1/threads/missing")
    assert response.status_code == 404
