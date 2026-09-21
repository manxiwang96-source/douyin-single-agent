from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from langchain_core.messages import HumanMessage

from app.job_control import cancel_job_run, disable_job, run_cancel_job, run_list_jobs
from app.repository import JobDisabledError, JobRunNotCancellableError
from tests.fakes import ai_text, ai_tool
from tests.graph_helpers import graph_config
from tests.http_helpers import make_client, register_and_login


def _owner_with_job(repo, title: str = "job-a"):
    user = repo.create_user(f"job-{title}", "hash-not-secret")
    instance = repo.create_agent_instance(user.user_id, title, intro="ops")
    job = repo.create_job_definition(
        user.user_id,
        instance.agent_instance_id,
        kind="douyin_topic_engage",
        cron="0 8 * * *",
    )
    return user, instance, job


def _configurable(user, instance):
    return {
        "user_id": str(user.user_id),
        "agent_instance_id": str(instance.agent_instance_id),
        "thread_id": "job-thread",
    }


def test_disabled_job_refuses_new_run_and_keeps_row(runtime):
    repo = runtime.business_repo
    user, instance, job = _owner_with_job(repo, "disable-a")
    disabled = disable_job(repo, user_id=user.user_id, job_id=job.job_id)
    assert disabled["deleted"] is False
    assert disabled["job"]["enabled"] is False
    assert repo.get_job_definition(job.job_id) is not None
    with pytest.raises(JobDisabledError):
        repo.create_job_run(job.job_id, datetime(2026, 9, 22, 8, 0, tzinfo=timezone.utc))
    again = disable_job(repo, user_id=user.user_id, job_id=job.job_id)
    assert again["job"]["enabled"] is False
    assert len(repo.list_job_definitions(user.user_id, instance.agent_instance_id)) == 1


def test_cancel_run_is_status_and_does_not_withdraw_sent(runtime):
    repo = runtime.business_repo
    user, instance, job = _owner_with_job(repo, "cancel-a")
    run = repo.create_job_run(
        job.job_id,
        datetime(2026, 9, 22, 8, 0, tzinfo=timezone.utc),
        status="running",
    )
    workflow = repo.create_workflow_run(
        user.user_id,
        instance.agent_instance_id,
        workflow_code="douyin-lead-discovery",
        inputs={"account": "shop1"},
        status="running",
        job_run_id=run.job_run_id,
        workflow_run_id="wf-cancel",
    )
    repo.add_engage_video(
        user.user_id,
        instance.agent_instance_id,
        platform_video_id="v1",
        status="replying",
        job_run_id=run.job_run_id,
        workflow_run_id="wf-cancel",
    )
    sent = repo.add_engage_comment(
        user.user_id,
        instance.agent_instance_id,
        platform_comment_id="c-sent",
        video_id="v1",
        status="sent",
        source_text="想买",
    )
    proposed = repo.add_engage_comment(
        user.user_id,
        instance.agent_instance_id,
        platform_comment_id="c-open",
        video_id="v1",
        status="proposed",
        source_text="看看",
    )
    other = repo.add_engage_comment(
        user.user_id,
        instance.agent_instance_id,
        platform_comment_id="c-other",
        video_id="v-other",
        status="proposed",
        source_text="别的视频",
    )
    sending_dm = repo.add_engage_dm(
        user.user_id,
        instance.agent_instance_id,
        platform_message_id="m-open",
        video_id="v1",
        status="sending",
        source_text="多少钱",
    )
    sent_dm = repo.add_engage_dm(
        user.user_id,
        instance.agent_instance_id,
        platform_message_id="m-sent",
        video_id="v1",
        status="sent",
        source_text="已买",
    )
    result = cancel_job_run(repo, user_id=user.user_id, job_run_id=run.job_run_id)
    assert result["deleted"] is False
    assert result["run"]["status"] == "cancelled"
    stored = repo.get_job_run(run.job_run_id)
    assert stored is not None
    assert stored.status == "cancelled"
    assert repo.get_job_definition(job.job_id) is not None
    assert repo.get_job_definition(job.job_id).enabled is True
    assert repo.list_job_runs(user.user_id, instance.agent_instance_id)
    comments = {item.platform_comment_id: item.status for item in repo.list_engage_comments(user.user_id, instance.agent_instance_id)}
    dms = {item.platform_message_id: item.status for item in repo.list_engage_dms(user.user_id, instance.agent_instance_id)}
    assert comments[sent.platform_comment_id] == "sent"
    assert comments[proposed.platform_comment_id] == "cancelled"
    assert comments[other.platform_comment_id] == "proposed"
    assert dms[sending_dm.platform_message_id] == "cancelled"
    assert dms[sent_dm.platform_message_id] == "sent"
    stored_wf = repo.list_workflow_runs(user.user_id, instance.agent_instance_id)[0]
    assert stored_wf.id == workflow.id
    assert stored_wf.status == "cancelled"
    assert result["local"]["comments"] == 1
    assert result["local"]["dms"] == 1
    assert result["local"]["workflow_runs"] == 1


def test_terminal_run_cannot_be_cancelled(runtime):
    repo = runtime.business_repo
    user, _instance, job = _owner_with_job(repo, "done-a")
    succeeded = repo.create_job_run(job.job_id, datetime(2026, 9, 22, 8, 0, tzinfo=timezone.utc), status="succeeded")
    failed = repo.create_job_run(job.job_id, datetime(2026, 9, 23, 8, 0, tzinfo=timezone.utc), status="failed")
    with pytest.raises(JobRunNotCancellableError):
        cancel_job_run(repo, user_id=user.user_id, job_run_id=succeeded.job_run_id)
    with pytest.raises(JobRunNotCancellableError):
        cancel_job_run(repo, user_id=user.user_id, job_run_id=failed.job_run_id)
    assert repo.get_job_run(succeeded.job_run_id).status == "succeeded"


def test_tools_only_see_current_instance_jobs(runtime):
    repo = runtime.business_repo
    user, instance, job = _owner_with_job(repo, "tool-a")
    other = repo.create_agent_instance(user.user_id, "tool-b", intro="ops")
    other_job = repo.create_job_definition(
        user.user_id,
        other.agent_instance_id,
        kind="douyin_topic_engage",
        cron="0 8 * * *",
    )
    listed = run_list_jobs(repo, _configurable(user, instance))
    ids = {item["job_id"] for item in listed["jobs"]}
    assert str(job.job_id) in ids
    assert str(other_job.job_id) not in ids
    denied = run_cancel_job(repo, _configurable(user, instance), job_id=str(other_job.job_id))
    assert denied["ok"] is False
    assert denied["status"] == "forbidden"
    assert repo.get_job_definition(other_job.job_id).enabled is True


def test_http_disable_and_cancel_same_rows(runtime):
    repo = runtime.business_repo
    client = make_client(runtime)
    login = register_and_login(client, login_name="job-http")
    created = client.post(
        "/v1/agent-instances",
        json={"template_code": "douyin_ops", "title": "http-job", "intro": "ops"},
    )
    assert created.status_code == 201
    instance_id = created.json()["agent_instance_id"]
    job = repo.create_job_definition(
        UUID(login["user_id"]),
        UUID(instance_id),
        kind="douyin_topic_engage",
        cron="0 8 * * *",
    )
    run = repo.create_job_run(job.job_id, datetime(2026, 9, 22, 8, 0, tzinfo=timezone.utc), status="sending")
    disabled = client.post(f"/v1/jobs/{job.job_id}/disable")
    assert disabled.status_code == 200
    assert disabled.json()["deleted"] is False
    assert disabled.json()["job"]["enabled"] is False
    cancelled = client.post(f"/v1/job-runs/{run.job_run_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["run"]["status"] == "cancelled"
    assert repo.get_job_definition(job.job_id) is not None
    assert repo.get_job_run(run.job_run_id).status == "cancelled"


def test_http_cross_user_is_403_and_missing_is_404(runtime):
    repo = runtime.business_repo
    owner = make_client(runtime)
    owner_login = register_and_login(owner, login_name="job-owner")
    created = owner.post(
        "/v1/agent-instances",
        json={"template_code": "douyin_ops", "title": "owner-job", "intro": "ops"},
    )
    job = repo.create_job_definition(
        UUID(owner_login["user_id"]),
        UUID(created.json()["agent_instance_id"]),
        kind="douyin_topic_engage",
        cron="0 8 * * *",
    )
    run = repo.create_job_run(job.job_id, datetime(2026, 9, 22, 8, 0, tzinfo=timezone.utc), status="running")
    other = make_client(runtime)
    register_and_login(other, login_name="job-other")
    assert other.post(f"/v1/jobs/{job.job_id}/disable").status_code == 403
    assert other.post(f"/v1/job-runs/{run.job_run_id}/cancel").status_code == 403
    assert owner.post(f"/v1/jobs/{uuid4()}/disable").status_code == 404
    assert owner.post(f"/v1/job-runs/{uuid4()}/cancel").status_code == 404
    finished = repo.create_job_run(job.job_id, datetime(2026, 9, 23, 8, 0, tzinfo=timezone.utc), status="succeeded")
    assert owner.post(f"/v1/job-runs/{finished.job_run_id}/cancel").status_code == 409
    assert repo.get_job_definition(job.job_id).enabled is True


def test_graph_job_tools_keep_tutorial_nodes(runtime, llm):
    repo = runtime.business_repo
    user, instance, job = _owner_with_job(repo, "graph-job")
    run = repo.create_job_run(job.job_id, datetime(2026, 9, 22, 8, 0, tzinfo=timezone.utc), status="running")
    llm.responses = [
        ai_tool("list_jobs", {}),
        ai_text("当前有一条定时任务"),
        ai_tool("cancel_job", {"job_id": str(job.job_id), "run_id": str(run.job_run_id)}),
        ai_text("已停用任务并取消这次运行"),
    ]
    config = graph_config(
        "job-graph",
        user_id=str(user.user_id),
        agent_instance_id=str(instance.agent_instance_id),
    )
    first = runtime.graph.invoke({"messages": [HumanMessage(content="有哪些任务")]}, config)
    listed = json.loads(first["messages"][-2].content)
    assert listed["ok"] is True
    second = runtime.graph.invoke({"messages": [HumanMessage(content="取消")]}, config)
    payload = json.loads(second["messages"][-2].content)
    assert payload["ok"] is True
    assert payload["job"]["enabled"] is False
    assert payload["run"]["status"] == "cancelled"
    nodes = set(runtime.graph.get_graph().nodes)
    assert nodes >= {"chatbot", "tools"}
    assert "list_jobs" not in nodes
    assert "cancel_job" not in nodes
    assert second["messages"][-1].content == "已停用任务并取消这次运行"
