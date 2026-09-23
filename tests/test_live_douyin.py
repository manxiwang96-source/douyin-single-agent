from __future__ import annotations

import os

import pytest

from app.config import Settings
from app.dify_client import DifyClient
from app.leads import run_discover_douyin_leads
from app.repository import DEFAULT_WORKFLOW_CODE, InMemoryBusinessRepository

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_DOUYIN") != "1",
    reason="RUN_LIVE_DOUYIN is not 1",
)


def test_live_discover_douyin_leads_true_send_writes_workflow_run():
    settings = Settings()
    if not settings.dify_live_enabled:
        pytest.skip("DIFY_LIVE_ENABLED is not true")
    if not (settings.dify_base_url or "").strip() or not (settings.dify_api_key or "").strip():
        pytest.skip("missing DIFY_BASE_URL or DIFY_API_KEY")
    account = os.environ.get("LIVE_DOUYIN_ACCOUNT", "").strip()
    video_id = os.environ.get("LIVE_DOUYIN_VIDEO_ID", "").strip()
    if not account or not video_id:
        pytest.skip("missing LIVE_DOUYIN_ACCOUNT or LIVE_DOUYIN_VIDEO_ID")

    repo = InMemoryBusinessRepository()
    user = repo.create_user("live-douyin", "hash-not-secret")
    instance = repo.create_agent_instance(user.user_id, "live-douyin", intro="live smoke")
    repo.bind_workflow(user.user_id, instance.agent_instance_id, DEFAULT_WORKFLOW_CODE)
    client = DifyClient(settings)
    result = run_discover_douyin_leads(
        settings=settings,
        business_repo=repo,
        dify_client=client,
        configurable={
            "thread_id": "live-douyin-thread",
            "user_id": str(user.user_id),
            "agent_instance_id": str(instance.agent_instance_id),
            "allowed_workflow_codes": [DEFAULT_WORKFLOW_CODE],
        },
        account=account,
        video_id=video_id,
    )
    runs = repo.list_workflow_runs(user.user_id, instance.agent_instance_id)
    assert runs, "workflow_runs was not written"
    recorded = runs[0]
    assert recorded.inputs["no_send"] is False
    assert recorded.inputs["auto_login"] is True
    assert recorded.inputs["assess"] is True
    assert recorded.inputs["platform"] == "douyin"
    assert recorded.inputs["limit"] == 20
    assert recorded.inputs["channels"] == "comment,message"
    assert recorded.inputs["account"] == account
    assert recorded.inputs["video_id"] == video_id
    assert "keyword" not in recorded.inputs
    if (settings.douyin_http_base_url or "").strip():
        assert recorded.inputs["base_url"] == settings.douyin_http_base_url
    else:
        assert recorded.inputs["base_url"] == "http://192.168.1.33:8765"
    if not (settings.douyin_http_api_token or "").strip():
        assert "api_token" not in recorded.inputs
    assert result["ok"] is True, result.get("error") or result.get("summary") or result
    assert recorded.status in {"succeeded", "success", "completed"}
    summary = str(result.get("summary") or "")
    assert summary
    assert "dify live disabled" not in summary
    assert recorded.workflow_run_id or result.get("workflow_run_id")
