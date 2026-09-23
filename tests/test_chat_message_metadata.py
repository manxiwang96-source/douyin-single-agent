from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage

from app.graph import _time_context, build_invoke_config
from app.leads import find_successful_delivery_today
from app.main import MessageIn
from app.repository import DEFAULT_WORKFLOW_CODE
from app.serialize import api_messages_from_state


def test_message_input_and_serialization_preserve_chat_metadata():
    body = MessageIn(content="你好", client_message_id="client-1")
    assert body.client_message_id == "client-1"

    user = HumanMessage(content="你好")
    assistant = AIMessage(content="您好")
    payload = api_messages_from_state({"messages": [user, assistant]})
    assert payload[0]["message_id"] is None
    assert payload[0]["client_message_id"] is None
    assert payload[0]["created_at"] is None
    assert payload[1]["created_at"] is None


def test_time_context_uses_configured_server_timezone_and_history_metadata():
    config = build_invoke_config(
        thread_id="thread-1",
        user_id=uuid4(),
        agent_instance_id=uuid4(),
        assistant_timezone="America/Los_Angeles",
    )
    historical = HumanMessage(
        content="昨天发送了吗",
        additional_kwargs={
            "chat_message": {
                "message_id": "message-1",
                "client_message_id": "client-1",
                "created_at": "2026-09-22T23:59:00-07:00",
            }
        },
    )
    context = _time_context({"messages": [historical]}, config)
    assert "[assistant_timezone=America/Los_Angeles]" in context
    assert "[server_date=" in context
    assert "[message_time=2026-09-22T23:59:00-07:00]" in context


def _delivery_outputs(*, comment: str = "sent", message: str = "sent"):
    return {
        "list_comment": [{"video_id": "video-1", "status": comment}],
        "list_message": [{"video_id": "video-1", "status": message}],
    }


def test_successful_delivery_today_is_scoped_by_date_account_video_channel_and_status(runtime, settings):
    repo = runtime.business_repo
    user = repo.create_user("metadata-lead", "hash-not-secret")
    instance = repo.create_agent_instance(user.user_id, "metadata-lead", intro="ops")
    repo.bind_workflow(user.user_id, instance.agent_instance_id, DEFAULT_WORKFLOW_CODE)
    inputs = {"account": "account-a", "video_id": "video-1", "channels": "comment"}
    now = datetime.fromisoformat("2026-09-23T12:00:00+08:00")

    today = repo.create_workflow_run(
        user.user_id,
        instance.agent_instance_id,
        workflow_code=DEFAULT_WORKFLOW_CODE,
        inputs=inputs,
        status="succeeded",
        outputs=_delivery_outputs(comment="sent", message="failed"),
    )
    repo._workflow_runs[today.id] = today.__class__(**{
        **today.__dict__,
        "created_at": datetime.fromisoformat("2026-09-23T09:00:00+08:00"),
    })
    assert find_successful_delivery_today(
        repo, user.user_id, instance.agent_instance_id, inputs,
        assistant_timezone=settings.assistant_timezone, now=now,
    ) is not None

    message_only = {**inputs, "channels": "message"}
    assert find_successful_delivery_today(
        repo, user.user_id, instance.agent_instance_id, message_only,
        assistant_timezone=settings.assistant_timezone, now=now,
    ) is None

    yesterday = repo.create_workflow_run(
        user.user_id,
        instance.agent_instance_id,
        workflow_code=DEFAULT_WORKFLOW_CODE,
        inputs={**inputs, "video_id": "video-yesterday"},
        status="succeeded",
        outputs=_delivery_outputs(),
    )
    repo._workflow_runs[yesterday.id] = yesterday.__class__(**{
        **yesterday.__dict__,
        "created_at": datetime.fromisoformat("2026-09-22T23:59:00+08:00"),
    })
    assert find_successful_delivery_today(
        repo, user.user_id, instance.agent_instance_id,
        {**inputs, "video_id": "video-yesterday"},
        assistant_timezone=settings.assistant_timezone, now=now,
    ) is None

    failed = repo.create_workflow_run(
        user.user_id,
        instance.agent_instance_id,
        workflow_code=DEFAULT_WORKFLOW_CODE,
        inputs={**inputs, "account": "account-failed"},
        status="failed",
        outputs=_delivery_outputs(),
    )
    repo._workflow_runs[failed.id] = failed.__class__(**{
        **failed.__dict__,
        "created_at": datetime.fromisoformat("2026-09-23T10:00:00+08:00"),
    })
    assert find_successful_delivery_today(
        repo, user.user_id, instance.agent_instance_id,
        {**inputs, "account": "account-failed"},
        assistant_timezone=settings.assistant_timezone, now=now,
    ) is None

    other_account = {**inputs, "account": "account-other"}
    assert find_successful_delivery_today(
        repo, user.user_id, instance.agent_instance_id, other_account,
        assistant_timezone=settings.assistant_timezone, now=now,
    ) is None
