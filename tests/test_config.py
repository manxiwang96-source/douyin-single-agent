from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_cheapest_image_params_come_from_settings():
    settings = Settings(
        image_model="gpt-image-2",
        image_quality="low",
        image_size="1024x1536",
        image_tier_param="quality",
    )
    params = settings.default_image_params()
    assert params["model"] == "gpt-image-2"
    assert params["quality"] == "low"
    assert params["size"] == "1024x1536"


def test_cheapest_video_params_include_resolution():
    settings = Settings(
        video_model="wan3.0-video",
        video_duration=2,
        video_resolution="480P",
        video_size="9:16",
        video_aspect_param="ratio",
    )
    params = settings.default_video_params()
    assert params["model"] == "wan3.0-video"
    assert params["duration"] == 2
    assert params["resolution"] == "480P"
    assert params["ratio"] == "9:16"


def test_video_provider_aliyun_wan3_alias():
    settings = Settings(video_provider="aliyun_wan3")
    assert settings.video_provider == "dashscope"


def test_unknown_image_provider_fails():
    with pytest.raises(ValidationError):
        Settings(image_provider="local")


def test_unknown_video_provider_fails():
    with pytest.raises(ValidationError):
        Settings(video_provider="runway")


def test_base_urls_strip_trailing_slash():
    settings = Settings(
        openai_api_base_url="https://aitokens.website/v1/",
        embedding_base_url="https://api.siliconflow.cn/v1/",
        dashscope_endpoint="https://dashscope.aliyuncs.com/api/v1/",
    )
    assert settings.openai_api_base_url == "https://aitokens.website/v1"
    assert settings.embedding_base_url == "https://api.siliconflow.cn/v1"
    assert settings.dashscope_endpoint == "https://dashscope.aliyuncs.com/api/v1"
