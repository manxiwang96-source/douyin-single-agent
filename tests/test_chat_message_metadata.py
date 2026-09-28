from __future__ import annotations

from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage

from app.graph import _time_context, build_invoke_config
from app.main import MessageIn
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
