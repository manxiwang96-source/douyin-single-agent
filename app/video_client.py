from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.media_paths import allocate_media_path


class VideoGenerationError(RuntimeError):
    pass


class VideoClient:
    def __init__(
        self,
        settings: Settings,
        media_root: Path,
        http_client: httpx.Client | None = None,
        sleeper=time.sleep,
    ):
        self.settings = settings
        self.media_root = media_root
        self.http_client = http_client or httpx.Client(timeout=60.0)
        self.sleeper = sleeper

    def build_payload(self, prompt: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        merged = dict(self.settings.default_video_params())
        if params:
            merged.update({key: value for key, value in params.items() if value is not None})
        model = merged.pop("model", self.settings.video_model)
        duration = int(merged.pop("duration", self.settings.video_duration))
        resolution = merged.pop("resolution", self.settings.video_resolution)
        aspect_key = self.settings.video_aspect_param
        aspect_value = merged.pop(aspect_key, self.settings.video_size)
        parameters: dict[str, Any] = {
            "duration": duration,
            "resolution": resolution,
            aspect_key: aspect_value,
        }
        parameters.update(merged)
        return {
            "model": model,
            "input": {"prompt": prompt},
            "parameters": parameters,
        }

    def generate(
        self,
        prompt: str,
        params: dict[str, Any] | None = None,
        *,
        user_id: str | None = None,
        agent_instance_id: str | None = None,
    ) -> Path:
        payload = self.build_payload(prompt, params)
        create_url = (
            f"{self.settings.dashscope_endpoint}/services/aigc/video-generation/video-synthesis"
        )
        headers = {
            "Authorization": f"Bearer {self.settings.dashscope_api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }
        if self.settings.dashscope_workspace_id:
            headers["X-DashScope-WorkSpace"] = self.settings.dashscope_workspace_id
        response = self.http_client.post(create_url, json=payload, headers=headers)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VideoGenerationError(f"video creation failed: {exc.response.text}") from exc
        created = response.json()
        task_id = (created.get("output") or {}).get("task_id")
        if not task_id:
            raise VideoGenerationError(f"video creation missing task_id: {created}")
        video_url = self._poll_task(task_id, headers)
        downloaded = self.http_client.get(video_url)
        downloaded.raise_for_status()
        path = allocate_media_path(
            self.media_root,
            "videos",
            ".mp4",
            user_id=user_id,
            agent_instance_id=agent_instance_id,
        )
        path.write_bytes(downloaded.content)
        return path

    def _poll_task(self, task_id: str, headers: dict[str, str]) -> str:
        task_url = f"{self.settings.dashscope_endpoint}/tasks/{task_id}"
        deadline = time.monotonic() + float(self.settings.video_timeout_s)
        while True:
            response = self.http_client.get(task_url, headers=headers)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise VideoGenerationError(f"video poll failed: {exc.response.text}") from exc
            body = response.json()
            output = body.get("output") or {}
            status = str(output.get("task_status") or body.get("task_status") or "").upper()
            if status == "SUCCEEDED":
                video_url = output.get("video_url") or output.get("videoUrl")
                if not video_url and output.get("results"):
                    video_url = output["results"][0].get("url")
                if not video_url:
                    raise VideoGenerationError(f"video succeeded without url: {body}")
                return video_url
            if status in {"FAILED", "CANCELED", "UNKNOWN", "CANCELED"}:
                raise VideoGenerationError(f"video task {status}: {body}")
            if time.monotonic() >= deadline:
                raise VideoGenerationError("video task timed out")
            self.sleeper(float(self.settings.video_poll_interval_s))