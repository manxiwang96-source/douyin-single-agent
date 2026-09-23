from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings, project_root
from app.runtime import LLM_MAX_TOKENS, LLM_TIMEOUT_S, make_llm


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
        dify_base_url="http://192.168.1.158/v1/",
        douyin_http_base_url="http://example.test/",
    )
    assert settings.openai_api_base_url == "https://aitokens.website/v1"
    assert settings.embedding_base_url == "https://api.siliconflow.cn/v1"
    assert settings.dashscope_endpoint == "https://dashscope.aliyuncs.com/api/v1"
    assert settings.dify_base_url == "http://192.168.1.158/v1"
    assert settings.douyin_http_base_url == "http://example.test"


def test_assistant_defaults():
    settings = Settings(
        _env_file=None,
        postgres_uri="",
        smtp_user="",
        smtp_password="",
        smtp_from="",
        smtp_to="",
        assistant_city="广州",
        assistant_timezone="Asia/Shanghai",
    )
    assert settings.assistant_city == "广州"
    assert settings.assistant_timezone == "Asia/Shanghai"
    assert settings.smtp_host == "smtp.163.com"
    assert settings.smtp_port == 465
    assert settings.smtp_ssl is True
    assert settings.scheduler_enabled is False
    assert settings.dify_timeout_s == 300
    assert settings.dify_live_enabled is False
    assert settings.dify_lead_app_id == "douyin-lead-discovery"
    assert settings.douyin_http_base_url == ""
    assert settings.douyin_http_api_token == ""
    assert settings.mcp_enabled is True



def test_default_cors_origins_include_vite_and_streamlit():
    settings = Settings(_env_file=None)
    origins = settings.cors_origin_list()
    assert "http://localhost:5173" in origins
    assert "http://127.0.0.1:5173" in origins
    assert "http://localhost:8501" in origins
    assert "http://127.0.0.1:8501" in origins


def test_smtp_from_and_to_default_to_user():
    settings = Settings(smtp_user="user@163.com", smtp_password="x", smtp_from="", smtp_to="")
    assert settings.smtp_from == "user@163.com"
    assert settings.smtp_to == "user@163.com"


def test_validate_production_requires_postgres_and_smtp():
    settings = Settings(
        postgres_uri="",
        smtp_user="",
        smtp_password="",
        smtp_from="",
        smtp_to="",
    )
    with pytest.raises(RuntimeError, match="POSTGRES_URI"):
        settings.validate_production()
    settings = Settings(
        postgres_uri="postgresql://postgres@127.0.0.1:5432/agentdemo",
        smtp_user="",
        smtp_password="",
        smtp_from="",
        smtp_to="",
    )
    missing = settings.missing_production_fields()
    assert "SMTP_USER" in missing
    assert "SMTP_PASSWORD" in missing
    assert "SMTP_TO" in missing


def test_validate_production_passes_with_required_fields():
    settings = Settings(
        postgres_uri="postgresql://postgres@127.0.0.1:5432/agentdemo",
        smtp_user="user@163.com",
        smtp_password="secret",
        smtp_from="",
        smtp_to="",
    )
    settings.validate_production()
    assert settings.smtp_to == "user@163.com"



def test_public_config_excludes_dify_secrets():
    settings = Settings(
        _env_file=None,
        dify_base_url="http://192.168.1.158/v1",
        dify_api_key="secret-key",
        douyin_http_api_token="secret-token",
        dify_live_enabled=False,
    )
    public = settings.public_config()
    assert public["dify_lead_app_id"] == "douyin-lead-discovery"
    assert public["dify_live_enabled"] is False
    assert "dify_api_key" not in public
    assert "douyin_http_api_token" not in public
    assert "dify_base_url" not in public


def test_env_example_has_assistant_fields_without_secrets():
    text = Path(project_root() / ".env.example").read_text(encoding="utf-8")
    required = [
        "POSTGRES_URI=",
        "ASSISTANT_CITY=",
        "ASSISTANT_TIMEZONE=",
        "SCHEDULER_ENABLED=false",
        "SMTP_HOST=smtp.163.com",
        "SMTP_PORT=465",
        "SMTP_SSL=true",
        "SMTP_USER=",
        "SMTP_PASSWORD=",
        "SMTP_FROM=",
        "SMTP_TO=",
        "CORS_ORIGINS=",
        "DIFY_TIMEOUT_S=300",
        "DIFY_LIVE_ENABLED=false",
    ]
    missing = [item for item in required if item not in text]
    assert missing == [], missing
    forbidden = ["205102", "UNhb48n7W9uWmpgx"]
    found = [item for item in forbidden if item in text]
    assert found == [], found


def test_requirements_include_assistant_dependencies():
    text = Path(project_root() / "requirements.txt").read_text(encoding="utf-8")
    required = [
        "langchain-mcp-adapters",
        "mcp",
        "psycopg[binary,pool]",
        "langgraph-checkpoint-postgres",
        "apscheduler",
    ]
    missing = [item for item in required if item not in text]
    assert missing == [], missing

def test_make_llm_sets_timeout_and_max_tokens(settings):
    llm = make_llm(settings)
    assert llm.max_tokens == LLM_MAX_TOKENS
    assert llm.request_timeout == LLM_TIMEOUT_S
    assert llm.max_retries == 1
