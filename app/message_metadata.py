from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from langchain_core.messages import BaseMessage

MESSAGE_METADATA_KEY = "chat_message"


def new_message_metadata(*, client_message_id: str | None = None, created_at: datetime | None = None) -> dict[str, Any]:
    return {
        "message_id": str(uuid4()),
        "client_message_id": client_message_id,
        "created_at": created_at.isoformat() if created_at is not None else None,
    }


def message_metadata(message: BaseMessage | None) -> dict[str, Any]:
    if message is None:
        return {}
    additional_kwargs = getattr(message, "additional_kwargs", {}) or {}
    value = additional_kwargs.get(MESSAGE_METADATA_KEY)
    return dict(value) if isinstance(value, dict) else {}


def with_message_metadata(message: BaseMessage, metadata: dict[str, Any]) -> BaseMessage:
    additional_kwargs = dict(getattr(message, "additional_kwargs", {}) or {})
    additional_kwargs[MESSAGE_METADATA_KEY] = dict(metadata)
    updates = {"id": metadata.get("message_id"), "additional_kwargs": additional_kwargs}
    model_copy = getattr(message, "model_copy", None)
    if callable(model_copy):
        return model_copy(update=updates)
    return message.copy(update=updates)
