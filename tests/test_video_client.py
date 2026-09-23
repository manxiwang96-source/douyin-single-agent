from __future__ import annotations

import json
from pathlib import Path

import httpx

from app.config import Settings
from app.video_client import VideoClient
from tests.fakes import DUMMY_MP4


class _Transport(httpx.BaseTransport):
    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.polls = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        if request.method == "POST" and url.endswith("video-synthesis"):
            return httpx.Response(200, json={"output": {"task_id": "task-1"}})
        if request.method == "GET" and url.endswith("/tasks/task-1"):
            self.polls += 1
            if self.polls < 2:
                return httpx.Response(200, json={"output": {"task_status": "RUNNING"}})
            return httpx.Response(
                200,
                json={
                    "output": {
                        "task_status": "SUCCEEDED",
                        "video_url": "https://cdn.example.test/v.mp4",
                    }
                },
            )
        if url == "https://cdn.example.test/v.mp4":
            return httpx.Response(200, content=DUMMY_MP4)
        return httpx.Response(404, text="missing")


def test_video_payload_includes_cheapest_resolution(tmp_path: Path):
    settings = Settings(
        dashscope_api_key="k",
        dashscope_endpoint="https://dashscope.example.test/api/v1",
        video_model="wan3.0-video",
        video_duration=2,
        video_resolution="480P",
        video_size="9:16",
        video_aspect_param="ratio",
        video_poll_interval_s=0,
        video_timeout_s=10,
    )
    media_root = tmp_path / "outputs"
    transport = _Transport()
    client = VideoClient(
        settings,
        media_root,
        http_client=httpx.Client(transport=transport),
        sleeper=lambda _s: None,
    )
    payload = client.build_payload("pour toner")
    assert payload["model"] == "wan3.0-video"
    assert payload["input"] == {"prompt": "pour toner"}
    assert payload["parameters"]["duration"] == 2
    assert payload["parameters"]["resolution"] == "480P"
    assert payload["parameters"]["ratio"] == "9:16"
    path = client.generate("pour toner")
    assert path.parent == media_root / "videos"
    assert path.read_bytes() == DUMMY_MP4
    create_req = transport.requests[0]
    assert create_req.headers["X-DashScope-Async"] == "enable"
    body = json.loads(create_req.content.decode("utf-8"))
    assert body["parameters"]["resolution"] == "480P"
