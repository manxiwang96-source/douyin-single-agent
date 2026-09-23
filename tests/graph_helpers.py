from __future__ import annotations

from app.graph import DEFAULT_ALLOWED_WORKFLOW_CODES, build_invoke_config

DUMMY_USER_ID = "00000000-0000-4000-8000-000000000001"
DUMMY_AGENT_INSTANCE_ID = "00000000-0000-4000-8000-000000000002"


def graph_config(thread_id: str, **extra):
    allowed = extra.pop("allowed_workflow_codes", DEFAULT_ALLOWED_WORKFLOW_CODES)
    user_id = extra.pop("user_id", DUMMY_USER_ID)
    agent_instance_id = extra.pop("agent_instance_id", DUMMY_AGENT_INSTANCE_ID)
    config = build_invoke_config(
        thread_id=thread_id,
        user_id=user_id,
        agent_instance_id=agent_instance_id,
        allowed_workflow_codes=allowed,
    )
    if extra:
        config["configurable"].update(extra)
    return config
