from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.media_paths import allocate_media_path


class ImageGenerationError(RuntimeError):
    pass


class ImageClient:
    def __init__(
        self,
        settings: Settings,
        media_root: Path,
        http_client: httpx.Client | None = None,
    ):
        self.settings = settings
        self.media_root = media_root
        self.http_client = http_client or httpx.Client(timeout=60.0)

    def build_payload(self, prompt: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        merged = dict(self.settings.default_image_params())
        if params:
            merged.update({key: value for key, value in params.items() if value is not None})
        model = merged.pop("model", self.settings.image_model)
        size = merged.pop("size", self.settings.image_size)
        tier_key = self.settings.image_tier_param
        tier_value = merged.pop(tier_key, self.settings.image_quality)
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            tier_key: tier_value,
            "size": size,
        }
        payload.update(merged)
        return payload

    def generate(self, prompt: str, params: dict[str, Any] | None = None) -> Path:
        payload = self.build_payload(prompt, params)
        url = f"{self.settings.openai_api_base_url}/images/generations"
        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        response = self.http_client.post(url, json=payload, headers=headers)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ImageGenerationError(f"image generation failed: {exc.response.text}") from exc
        data = response.json()
        raw = _extract_image_bytes(data, self.http_client)
        path = allocate_media_path(self.media_root, "images", ".png")
        path.write_bytes(raw)
        return path


def _extract_image_bytes(data: dict[str, Any], http_client: httpx.Client) -> bytes:
    items = data.get("data") or []
    if not items:
        raise ImageGenerationError("image response missing data")
    item = items[0]
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"])
    if item.get("url"):
        downloaded = http_client.get(item["url"])
        downloaded.raise_for_status()
        return downloaded.content
    raise ImageGenerationError("image response missing b64_json/url")