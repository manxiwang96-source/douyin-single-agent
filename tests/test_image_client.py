from __future__ import annotations

import base64
from pathlib import Path

import httpx

from app.config import Settings
from app.image_client import ImageClient
from tests.fakes import TINY_PNG


class _Transport(httpx.BaseTransport):
    def __init__(self):
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        body = {
            "data": [
                {
                    "b64_json": base64.b64encode(TINY_PNG).decode("ascii"),
                }
            ]
        }
        return httpx.Response(200, json=body)


def test_image_payload_is_cheapest(tmp_path: Path):
    settings = Settings(
        openai_api_key="k",
        openai_api_base_url="https://gateway.example.test/v1",
        image_model="gpt-image-2",
        image_quality="low",
        image_size="1024x1536",
        image_tier_param="quality",
    )
    media_root = tmp_path / "outputs"
    transport = _Transport()
    client = ImageClient(
        settings,
        media_root,
        http_client=httpx.Client(transport=transport),
    )
    payload = client.build_payload("a red bottle")
    assert payload["model"] == "gpt-image-2"
    assert payload["prompt"] == "a red bottle"
    assert payload["quality"] == "low"
    assert payload["size"] == "1024x1536"
    path = client.generate("a red bottle")
    assert path.parent == media_root / "images"
    assert path.read_bytes() == TINY_PNG
    posted = transport.requests[0]
    assert str(posted.url) == "https://gateway.example.test/v1/images/generations"
    assert posted.method == "POST"
