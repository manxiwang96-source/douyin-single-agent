from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta

from langchain_core.messages import HumanMessage

from app.dify_client import DifyClient
from app.leads import build_dify_inputs, normalize_lead_channels, run_discover_douyin_leads
from app.repository import DEFAULT_WORKFLOW_CODE, utcnow
from tests.fakes import FakeDifyClient, ai_text, ai_tool
from tests.graph_helpers import graph_config


def _bound_owner(repo, title: str = "lead-a"):
    user = repo.create_user("lead-user", "hash-not-secret")
    instance = repo.create_agent_instance(user.user_id, title, intro="ops")
    repo.bind_workflow(user.user_id, instance.agent_instance_id, DEFAULT_WORKFLOW_CODE)
    return user, instance


def _configurable(user, instance, *, allowed=None):
    return {
        "thread_id": "lead-thread",
        "user_id": str(user.user_id),
        "agent_instance_id": str(instance.agent_instance_id),
        "allowed_workflow_codes": list(allowed if allowed is not None else [DEFAULT_WORKFLOW_CODE]),
    }


def test_build_dify_inputs_omits_empty_http_fields_and_forces_true_send(settings):
    inputs = build_dify_inputs(
        settings,
        account="shop1",
        keyword="敏感肌",
        limit=5,
        channels="comment,message",
    )
    assert inputs["account"] == "shop1"
    assert inputs["keyword"] == "敏感肌"
    assert inputs["limit"] == 5
    assert inputs["channels"] == "comment,message"
    assert inputs["platform"] == "douyin"
    assert inputs["no_send"] is False
    assert inputs["auto_login"] is True
    assert inputs["assess"] is True
    assert inputs["base_url"] == "http://192.168.1.33:8765"
    assert "api_token" not in inputs
    defaults = build_dify_inputs(settings, account="shop1", video_id="v9")
    assert defaults["platform"] == "douyin"
    assert defaults["limit"] == 20
    assert defaults["channels"] == "comment,message"
    assert defaults["assess"] is True
    assert defaults["no_send"] is False
    assert defaults["video_id"] == "v9"
    assert defaults["base_url"] == "http://192.168.1.33:8765"
    assert "keyword" not in defaults
    assert "api_token" not in defaults
    filled = settings.model_copy(
        update={"douyin_http_base_url": "http://c.example.test", "douyin_http_api_token": "tok"}
    )
    with_http = build_dify_inputs(filled, account="shop1", video_id="v9")
    assert with_http["base_url"] == "http://c.example.test"
    assert with_http["api_token"] == "tok"
    assert with_http["video_id"] == "v9"


def test_normalize_lead_channels_maps_aliases_and_rejects_invalid():
    assert normalize_lead_channels("") == "comment,message"
    assert normalize_lead_channels("comment,message") == "comment,message"
    assert normalize_lead_channels("comment") == "comment"
    assert normalize_lead_channels("message") == "message"
    assert normalize_lead_channels("comment,dm") == "comment,message"
    assert normalize_lead_channels("评论、私信") == "comment,message"
    assert normalize_lead_channels("评论，私信") == "comment,message"
    assert normalize_lead_channels("dm") == "message"
    assert normalize_lead_channels("message,comment") == "comment,message"
    assert normalize_lead_channels("foo,bar") == "comment,message"


def test_build_dify_inputs_drops_keyword_when_video_id_present_and_sanitizes_channels(settings):
    inputs = build_dify_inputs(
        settings,
        account="wmq",
        keyword="敏感肌",
        video_id="7674838941266087168",
        channels="comment,dm",
    )
    assert inputs["account"] == "wmq"
    assert inputs["video_id"] == "7674838941266087168"
    assert "keyword" not in inputs
    assert inputs["channels"] == "comment,message"
    chinese = build_dify_inputs(
        settings,
        account="wmq",
        video_id="7674838941266087168",
        channels="评论、私信",
    )
    assert chinese["channels"] == "comment,message"
    assert "keyword" not in chinese


def test_missing_account_or_keyword_does_not_call_dify(runtime, settings):
    repo = runtime.business_repo
    user, instance = _bound_owner(repo)
    client = FakeDifyClient()
    missing_account = run_discover_douyin_leads(
        settings=settings,
        business_repo=repo,
        dify_client=client,
        configurable=_configurable(user, instance),
        account="",
        keyword="敏感肌",
    )
    missing_target = run_discover_douyin_leads(
        settings=settings,
        business_repo=repo,
        dify_client=client,
        configurable=_configurable(user, instance),
        account="shop1",
        keyword="",
        video_id="",
    )
    assert missing_account["ok"] is False
    assert missing_target["ok"] is False
    assert client.calls == []
    assert repo.list_workflow_runs(user.user_id, instance.agent_instance_id) == []


def test_unbound_workflow_is_rejected(runtime, settings):
    repo = runtime.business_repo
    user = repo.create_user("unbound", "hash-not-secret")
    instance = repo.create_agent_instance(user.user_id, "unbound-a")
    client = FakeDifyClient()
    result = run_discover_douyin_leads(
        settings=settings,
        business_repo=repo,
        dify_client=client,
        configurable=_configurable(user, instance, allowed=[]),
        account="shop1",
        keyword="敏感肌",
    )
    assert result["ok"] is False
    assert result["error"] == "workflow not bound"
    assert client.calls == []


def test_paused_and_needs_login_accounts_are_blocked_without_projection_row_allowed(runtime, settings):
    repo = runtime.business_repo
    user, instance = _bound_owner(repo, "acct-a")
    client = FakeDifyClient()
    allowed = run_discover_douyin_leads(
        settings=settings,
        business_repo=repo,
        dify_client=client,
        configurable=_configurable(user, instance),
        account="shop-new",
        keyword="敏感肌",
    )
    assert allowed["ok"] is True
    assert client.calls
    repo.upsert_douyin_account(user.user_id, instance.agent_instance_id, "shop-paused", status="paused")
    repo.upsert_douyin_account(user.user_id, instance.agent_instance_id, "shop-login", status="needs_login")
    client.calls.clear()
    paused = run_discover_douyin_leads(
        settings=settings,
        business_repo=repo,
        dify_client=client,
        configurable=_configurable(user, instance),
        account="shop-paused",
        keyword="敏感肌",
    )
    login = run_discover_douyin_leads(
        settings=settings,
        business_repo=repo,
        dify_client=client,
        configurable=_configurable(user, instance),
        account="shop-login",
        video_id="v1",
    )
    assert paused["ok"] is False
    assert paused["status"] == "paused"
    assert login["ok"] is False
    assert login["status"] == "needs_login"
    assert client.calls == []


def test_successful_fake_run_writes_workflow_and_engage_rows(runtime, settings):
    repo = runtime.business_repo
    user, instance = _bound_owner(repo, "write-a")
    client = FakeDifyClient()
    result = run_discover_douyin_leads(
        settings=settings,
        business_repo=repo,
        dify_client=client,
        configurable=_configurable(user, instance),
        account="shop1",
        keyword="敏感肌",
        limit=3,
    )
    assert result["ok"] is True
    assert client.calls[0]["inputs"]["no_send"] is False
    assert client.calls[0]["inputs"]["auto_login"] is True
    assert client.calls[0]["user"] == str(user.user_id)
    runs = repo.list_workflow_runs(user.user_id, instance.agent_instance_id)
    assert len(runs) == 1
    assert runs[0].status == "succeeded"
    assert runs[0].inputs["no_send"] is False
    assert repo.list_engage_videos(user.user_id, instance.agent_instance_id)
    assert repo.list_engage_comments(user.user_id, instance.agent_instance_id)
    assert repo.list_engage_dms(user.user_id, instance.agent_instance_id)


def test_unknown_outputs_are_unverified_and_record_workflow_run(runtime, settings):
    repo = runtime.business_repo
    user, instance = _bound_owner(repo, "shape-a")
    client = FakeDifyClient(
        {
            "ok": True,
            "status": "succeeded",
            "dify_workflow_status": "succeeded",
            "workflow_ok": True,
            "job_status": "succeeded",
            "workflow_run_id": "wf-odd",
            "outputs": {"unexpected": {"raw": True}},
            "error": None,
        }
    )
    result = run_discover_douyin_leads(
        settings=settings,
        business_repo=repo,
        dify_client=client,
        configurable=_configurable(user, instance),
        account="shop1",
        keyword="敏感肌",
    )
    assert result["ok"] is False
    assert result["status"] == "unverified"
    assert "delivery response unavailable" in result["error"]
    runs = repo.list_workflow_runs(user.user_id, instance.agent_instance_id)
    assert len(runs) == 1
    assert runs[0].outputs == {"unexpected": {"raw": True}}
    assert repo.list_engage_comments(user.user_id, instance.agent_instance_id) == []




def _run_with_result(runtime, settings, result):
    repo = runtime.business_repo
    user = repo.create_user(f"lead-user-{len(repo._users)}", "hash-not-secret")
    instance = repo.create_agent_instance(user.user_id, f"status-{len(repo._workflow_runs)}", intro="ops")
    repo.bind_workflow(user.user_id, instance.agent_instance_id, DEFAULT_WORKFLOW_CODE)
    client = FakeDifyClient(result)
    output = run_discover_douyin_leads(
        settings=settings,
        business_repo=repo,
        dify_client=client,
        configurable=_configurable(user, instance),
        account="shop1",
        keyword="敏感肌",
    )
    return output, repo, user, instance


def test_outer_success_inner_job_failed_is_not_success(runtime, settings):
    result, repo, user, instance = _run_with_result(
        runtime,
        settings,
        {
            "ok": False,
            "status": "failed",
            "dify_workflow_status": "succeeded",
            "workflow_ok": True,
            "workflow_run_id": "wf-failed",
            "job_id": "job-failed",
            "job_status": "failed",
            "outputs": {
                "job_id": "job-failed",
                "job_status": "failed",
                "job_response": '{"data":{"status":"failed","error":"当前账号未登录"}}',
                "list_comment": '{"ok":false,"error":"评论接口失败"}',
                "list_message": '{"ok":false,"error":"私信接口失败"}',
            },
            "error": "当前账号未登录",
        },
    )
    assert result["ok"] is False
    assert result["workflow_ok"] is True
    assert result["delivery_ok"] is False
    assert result["status"] == "failed"
    assert result["dify_workflow_status"] == "succeeded"
    assert result["job_status"] == "failed"
    assert result["error"] == "当前账号未登录; comments: 评论接口失败; dms: 私信接口失败"
    assert result["delivery"]["comments"] == {"sent": 0, "failed": 1, "unverified": 0}
    assert result["delivery"]["dms"] == {"sent": 0, "failed": 1, "unverified": 0}
    assert result["message_details"] == []
    assert repo.list_engage_comments(user.user_id, instance.agent_instance_id) == []


def test_cancelled_and_unknown_job_status_are_not_success(runtime, settings):
    cancelled, *_ = _run_with_result(
        runtime,
        settings,
        {
            "ok": False,
            "status": "cancelled",
            "dify_workflow_status": "succeeded",
            "workflow_ok": True,
            "job_status": "cancelled",
            "outputs": {"job_status": "cancelled"},
            "error": "job cancelled",
        },
    )
    unknown, *_ = _run_with_result(
        runtime,
        settings,
        {
            "ok": False,
            "status": "unverified",
            "dify_workflow_status": "succeeded",
            "workflow_ok": True,
            "job_status": "unverified",
            "outputs": {},
            "error": "job status unavailable",
        },
    )
    assert cancelled["status"] == "cancelled"
    assert cancelled["ok"] is False
    assert unknown["status"] == "unverified"
    assert unknown["error"] == "job status unavailable"
    assert unknown["ok"] is False


def test_list_error_objects_are_not_records_and_dm_details_preserve_dify_fields(runtime, settings):
    result, repo, user, instance = _run_with_result(
        runtime,
        settings,
        {
            "ok": True,
            "status": "succeeded",
            "dify_workflow_status": "succeeded",
            "workflow_ok": True,
            "workflow_run_id": "wf-delivery",
            "job_id": "job-delivery",
            "job_status": "succeeded",
            "outputs": {
                "job_status": "succeeded",
                "job_response": '{"status":"succeeded"}',
                "list_comment": '{"ok":false,"error":"评论列表失败"}',
                "list_message": [
                    {
                        "message_id": "m-1",
                        "video_id": "v-1",
                        "source_text": "多少钱",
                        "content": "您好，售价99元",
                        "content_source": "template",
                        "status": "sent",
                    }
                ],
            },
            "error": None,
        },
    )
    assert result["ok"] is False
    assert result["delivery_ok"] is False
    assert result["delivery"]["comments"] == {"sent": 0, "failed": 1, "unverified": 0}
    assert result["delivery"]["dms"] == {"sent": 1, "failed": 0, "unverified": 0}
    assert result["message_details"] == [
        {
            "message_id": "m-1",
            "video_id": "v-1",
            "source_text": "多少钱",
            "content": "您好，售价99元",
            "content_source": "template",
            "status": "sent",
        }
    ]
    assert repo.list_engage_comments(user.user_id, instance.agent_instance_id) == []
    dms = repo.list_engage_dms(user.user_id, instance.agent_instance_id)
    assert len(dms) == 1
    assert dms[0].status == "sent"


def test_job_response_and_list_message_error_are_authoritative(runtime, settings):
    result, repo, user, instance = _run_with_result(
        runtime,
        settings,
        {
            "ok": True,
            "status": "succeeded",
            "dify_workflow_status": "succeeded",
            "workflow_ok": True,
            "workflow_run_id": "wf-authoritative",
            "job_id": "job-authoritative",
            "job_status": "succeeded",
            "outputs": {
                "job_status": "succeeded",
                "job_response": '{"data":{"status":"failed","error_message":"账号未登录"}}',
                "list_comment": [],
                "list_message": '{"ok":false,"error":"私信列表失败"}',
            },
            "error": None,
        },
    )
    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["job_status"] == "failed"
    assert result["error"] == "账号未登录; dms: 私信列表失败"
    assert result["delivery"]["dms"] == {"sent": 0, "failed": 1, "unverified": 0}
    assert repo.list_engage_dms(user.user_id, instance.agent_instance_id) == []


def test_item_failure_reason_alias_is_returned_without_using_written_count(runtime, settings):
    result, _repo, _user, _instance = _run_with_result(
        runtime,
        settings,
        {
            "ok": True,
            "status": "succeeded",
            "dify_workflow_status": "succeeded",
            "workflow_ok": True,
            "job_status": "succeeded",
            "outputs": {
                "job_response": '{"status":"succeeded"}',
                "list_comment": [],
                "list_message": [
                    {
                        "message_id": "m-reason",
                        "status": "failed",
                        "reason": "私信窗口打开失败",
                    }
                ],
            },
            "error": None,
        },
    )
    assert result["ok"] is False
    assert result["delivery"]["dms"] == {"sent": 0, "failed": 1, "unverified": 0}
    assert result["error"] == "私信窗口打开失败"
    assert result["message_details"][0]["reason"] == "私信窗口打开失败"


def test_written_count_does_not_override_failed_delivery(runtime, settings):
    result, _repo, _user, _instance = _run_with_result(
        runtime,
        settings,
        {
            "ok": True,
            "status": "succeeded",
            "dify_workflow_status": "succeeded",
            "workflow_ok": True,
            "workflow_run_id": "wf-written",
            "job_id": "job-written",
            "job_status": "succeeded",
            "outputs": {
                "job_status": "succeeded",
                "list_message": [
                    {"message_id": "m-failed", "status": "failed", "error": "窗口打开失败"}
                ],
                "list_comment": [],
            },
            "error": None,
        },
    )
    assert result["ok"] is False
    assert result["written"]["dms"] == 1
    assert result["delivery"]["dms"] == {"sent": 0, "failed": 1, "unverified": 0}
    assert "发送成功 1" not in result["summary"]

def test_in_progress_run_is_reused_within_ten_minutes(runtime, settings):
    repo = runtime.business_repo
    user, instance = _bound_owner(repo, "dedup-a")
    inputs = build_dify_inputs(settings, account="shop1", keyword="敏感肌")
    existing = repo.create_workflow_run(
        user.user_id,
        instance.agent_instance_id,
        workflow_code=DEFAULT_WORKFLOW_CODE,
        inputs=inputs,
        status="running",
        thread_id="lead-thread",
    )
    client = FakeDifyClient()
    result = run_discover_douyin_leads(
        settings=settings,
        business_repo=repo,
        dify_client=client,
        configurable=_configurable(user, instance),
        account="shop1",
        keyword="敏感肌",
    )
    assert result["ok"] is True
    assert result["reused"] is True
    assert result["id"] == str(existing.id)
    assert client.calls == []
    assert len(repo.list_workflow_runs(user.user_id, instance.agent_instance_id)) == 1

    stale = repo.create_workflow_run(
        user.user_id,
        instance.agent_instance_id,
        workflow_code=DEFAULT_WORKFLOW_CODE,
        inputs=build_dify_inputs(settings, account="shop2", keyword="敏感肌"),
        status="running",
    )
    stale = replace(stale, created_at=utcnow() - timedelta(minutes=11))
    repo._workflow_runs[stale.id] = stale
    second = FakeDifyClient()
    fresh = run_discover_douyin_leads(
        settings=settings,
        business_repo=repo,
        dify_client=second,
        configurable=_configurable(user, instance),
        account="shop2",
        keyword="敏感肌",
    )
    assert fresh["ok"] is True
    assert "reused" not in fresh
    assert second.calls


def test_graph_tool_sanitizes_channels_and_omits_keyword_when_video_id_present(runtime, llm, dify_client):
    repo = runtime.business_repo
    user, instance = _bound_owner(repo, "graph-video")
    llm.responses = [
        ai_tool(
            "discover_douyin_leads",
            {
                "account": "wmq",
                "video_id": "7674838941266087168",
                "keyword": "不要用",
                "channels": "comment,dm",
            },
        ),
        ai_text("已按视频开始评论和私信线索发现"),
    ]
    config = graph_config(
        "lead-graph-video",
        user_id=str(user.user_id),
        agent_instance_id=str(instance.agent_instance_id),
    )
    result = runtime.graph.invoke({"messages": [HumanMessage(content="用账号和视频做线索发现")]}, config)
    assert dify_client.calls
    inputs = dify_client.calls[0]["inputs"]
    assert inputs["account"] == "wmq"
    assert inputs["video_id"] == "7674838941266087168"
    assert "keyword" not in inputs
    assert inputs["channels"] == "comment,message"
    assert inputs["no_send"] is False
    payload = json.loads(result["messages"][-2].content)
    assert payload["ok"] is True


def test_graph_tool_uses_fake_and_keeps_tutorial_nodes(runtime, llm, dify_client):
    repo = runtime.business_repo
    user, instance = _bound_owner(repo, "graph-a")
    llm.responses = [
        ai_tool("discover_douyin_leads", {"account": "shop1", "keyword": "敏感肌", "limit": 2}),
        ai_text("已真实发送评论和私信"),
    ]
    config = graph_config(
        "lead-graph",
        user_id=str(user.user_id),
        agent_instance_id=str(instance.agent_instance_id),
    )
    result = runtime.graph.invoke({"messages": [HumanMessage(content="去评论")]}, config)
    nodes = set(runtime.graph.get_graph().nodes)
    assert nodes >= {"chatbot", "tools"}
    assert "discover_douyin_leads" not in nodes
    assert dify_client.calls
    assert dify_client.calls[0]["inputs"]["no_send"] is False
    payload = json.loads(result["messages"][-2].content)
    assert payload["ok"] is True
    assert repo.list_workflow_runs(user.user_id, instance.agent_instance_id)
    assert result["messages"][-1].content == "已真实发送评论和私信"


def test_default_runtime_does_not_use_live_dify_client(runtime):
    assert isinstance(runtime.dify_client, FakeDifyClient)
    assert not isinstance(runtime.dify_client, DifyClient)

def test_live_douyin_smoke_is_opt_in():
    from pathlib import Path

    source = Path(__file__).with_name("test_live_douyin.py").read_text(encoding="utf-8")
    assert "RUN_LIVE_DOUYIN" in source
    assert "LIVE_DOUYIN_ACCOUNT" in source
    assert "LIVE_DOUYIN_VIDEO_ID" in source
    assert "no_send" in source
    assert "DifyClient" in source
    assert "pytest.skip" in source
