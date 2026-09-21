from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta

from langchain_core.messages import HumanMessage

from app.dify_client import DifyClient
from app.leads import build_dify_inputs, run_discover_douyin_leads
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
    assert inputs["no_send"] is False
    assert inputs["auto_login"] is True
    assert "base_url" not in inputs
    assert "api_token" not in inputs
    filled = settings.model_copy(
        update={"douyin_http_base_url": "http://c.example.test", "douyin_http_api_token": "tok"}
    )
    with_http = build_dify_inputs(filled, account="shop1", video_id="v9")
    assert with_http["base_url"] == "http://c.example.test"
    assert with_http["api_token"] == "tok"
    assert with_http["video_id"] == "v9"


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


def test_unknown_outputs_still_succeed_and_record_workflow_run(runtime, settings):
    repo = runtime.business_repo
    user, instance = _bound_owner(repo, "shape-a")
    client = FakeDifyClient(
        {
            "ok": True,
            "status": "succeeded",
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
    assert result["ok"] is True
    runs = repo.list_workflow_runs(user.user_id, instance.agent_instance_id)
    assert len(runs) == 1
    assert runs[0].outputs == {"unexpected": {"raw": True}}
    assert repo.list_engage_comments(user.user_id, instance.agent_instance_id) == []


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
