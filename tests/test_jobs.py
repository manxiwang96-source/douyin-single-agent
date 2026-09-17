from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from app.jobs import catch_up_jobs, run_hydrate, run_morning_brief
from app.main import create_app
from tests.fakes import ai_text, ai_tool


def test_morning_brief_runs_at_3am(runtime, llm, email_client):
    llm.responses = [
        ai_tool("send_email", {"subject": "晨间简报 2026-09-17", "body": "今天星期四小雨，带伞出门。"}),
        ai_text("已发送晨报"),
    ]
    now = datetime(2026, 9, 17, 3, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    result = run_morning_brief(runtime, now=now)
    assert result["status"] == "sent"
    assert result["facts"]["weekday"] == "星期四"
    assert result["facts"]["weather"] == "小雨"
    assert result["facts"]["temperature_c"] == 22.5
    assert email_client.sends
    assert result["facts"]["city"] == "广州"


def test_morning_brief_fallback_when_model_skips_email(runtime, llm, email_client):
    llm.responses = [ai_text("建议带伞，但我不发邮件。")]
    result = run_morning_brief(runtime, force=True)
    assert result["status"] == "sent_fallback"
    assert email_client.sends
    assert "小雨" in email_client.sends[0]["body"]


def test_morning_brief_falls_back_when_graph_times_out(runtime, email_client):
    async def hang(*_args, **_kwargs):
        await asyncio.sleep(5)

    runtime.graph.ainvoke = hang
    result = run_morning_brief(runtime, force=True, graph_timeout_s=0.05)
    assert result["status"] == "sent_fallback"
    assert email_client.sends
    assert "星期四" in email_client.sends[0]["body"]


def test_morning_brief_is_idempotent_without_force(runtime, llm, email_client):
    llm.responses = [
        ai_tool("send_email", {"subject": "晨间简报", "body": "事实和建议"}),
        ai_text("已发送"),
    ]
    first = run_morning_brief(runtime)
    second = run_morning_brief(runtime)
    assert first["status"] in {"sent", "sent_fallback"}
    assert second["status"] == "skipped"
    assert len(email_client.sends) == 1


def test_hydrate_does_not_call_llm(runtime, llm, email_client):
    llm.calls.clear()
    result = run_hydrate(runtime, "10")
    assert result["status"] == "sent"
    assert llm.calls == []
    assert email_client.sends
    assert email_client.sends[-1]["subject"] == "喝水提醒"
    assert "10:00" in email_client.sends[-1]["body"]


def test_hydrate_08_merges_into_morning_brief(runtime, email_client):
    result = run_hydrate(runtime, "08")
    assert result["status"] == "merged_into_morning_brief"
    assert email_client.sends == []


def test_catch_up_skips_after_22(runtime, llm, email_client):
    llm.responses = [ai_text("unused")]
    now = datetime(2026, 9, 17, 23, 10, tzinfo=ZoneInfo("Asia/Shanghai"))
    results = catch_up_jobs(runtime, now=now)
    assert results == []
    assert email_client.sends == []


def test_catch_up_morning_and_current_hydrate(runtime, llm, email_client):
    llm.responses = [
        ai_tool("send_email", {"subject": "晨间简报", "body": "建议"}),
        ai_text("已发送"),
    ]
    now = datetime(2026, 9, 17, 10, 5, tzinfo=ZoneInfo("Asia/Shanghai"))
    results = catch_up_jobs(runtime, now=now)
    kinds = [item["kind"] for item in results]
    assert "morning_brief" in kinds
    assert "hydrate" in kinds
    assert any(item.get("slot") == "10" for item in results)


def test_jobs_api_morning_brief(runtime, llm, email_client):
    llm.responses = [
        ai_tool("send_email", {"subject": "晨间简报", "body": "建议"}),
        ai_text("已发送"),
    ]
    client = TestClient(create_app(runtime))
    response = client.post("/v1/assistant/jobs/run", json={"kind": "morning_brief", "force": True})
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "morning_brief"
    assert body["status"] in {"sent", "sent_fallback"}
    assert email_client.sends


def test_jobs_api_hydrate_requires_slot(runtime):
    client = TestClient(create_app(runtime))
    response = client.post("/v1/assistant/jobs/run", json={"kind": "hydrate"})
    assert response.status_code == 400


def test_test_runtime_uses_in_memory_checkpointer(runtime):
    assert isinstance(runtime.checkpointer, InMemorySaver)