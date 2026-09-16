from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("REQUEST_EXTRAS must be a JSON object")
    return data


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    openai_api_key: str = ""
    openai_api_base_url: str = "https://aitokens.website/v1"
    openai_api_model: str = "gpt-5.6-sol"

    image_provider: str = "gateway"
    image_model: str = "gpt-image-2"
    image_quality: str = "low"
    image_size: str = "1024x1536"
    image_tier_param: str = "quality"
    image_request_extras: str = ""

    video_provider: str = "dashscope"
    video_model: str = "wan3.0-video"
    video_duration: int = 2
    video_resolution: str = "480P"
    video_size: str = "9:16"
    video_aspect_param: str = "ratio"
    video_poll_interval_s: float = 3
    video_timeout_s: float = 180
    video_request_extras: str = ""

    dashscope_api_key: str = ""
    dashscope_workspace_id: str = ""
    dashscope_region: str = "cn-beijing"
    dashscope_endpoint: str = "https://dashscope.aliyuncs.com/api/v1"

    embedding_model: str = "BAAI/bge-m3"
    embedding_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_api_key: str = ""
    embedding_dims: int = 1024

    media_output_dir: str = "outputs"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    streamlit_api_base: str = "http://127.0.0.1:8000"
    cors_origins: str = "http://localhost:8501,http://127.0.0.1:8501"

    @field_validator(
        "embedding_base_url",
        "openai_api_base_url",
        "dashscope_endpoint",
        "streamlit_api_base",
    )
    @classmethod
    def strip_slash(cls, value: str) -> str:
        return (value or "").rstrip("/")

    @field_validator("image_provider")
    @classmethod
    def validate_image_provider(cls, value: str) -> str:
        if value != "gateway":
            raise ValueError(
                f"Unsupported IMAGE_PROVIDER={value}; only gateway is implemented"
            )
        return value

    @field_validator("video_provider")
    @classmethod
    def validate_video_provider(cls, value: str) -> str:
        if value == "aliyun_wan3":
            return "dashscope"
        if value != "dashscope":
            raise ValueError(
                f"Unsupported VIDEO_PROVIDER={value}; only dashscope is implemented"
            )
        return value

    def image_extras(self) -> dict[str, Any]:
        return _parse_json_object(self.image_request_extras)

    def video_extras(self) -> dict[str, Any]:
        return _parse_json_object(self.video_request_extras)

    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    def default_image_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": self.image_model,
            self.image_tier_param: self.image_quality,
            "size": self.image_size,
        }
        params.update(self.image_extras())
        return params

    def default_video_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": self.video_model,
            "duration": int(self.video_duration),
            "resolution": self.video_resolution,
            self.video_aspect_param: self.video_size,
        }
        params.update(self.video_extras())
        return params

    def public_config(self) -> dict[str, Any]:
        return {
            "openai_api_model": self.openai_api_model,
            "image_provider": self.image_provider,
            "image_model": self.image_model,
            "image_quality": self.image_quality,
            "image_size": self.image_size,
            "image_tier_param": self.image_tier_param,
            "video_provider": self.video_provider,
            "video_model": self.video_model,
            "video_duration": int(self.video_duration),
            "video_resolution": self.video_resolution,
            "video_size": self.video_size,
            "video_aspect_param": self.video_aspect_param,
            "media_output_dir": self.media_output_dir,
            "streamlit_api_base": self.streamlit_api_base,
        }