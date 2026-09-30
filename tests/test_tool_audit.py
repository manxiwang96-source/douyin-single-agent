from uuid import uuid4

from app.graph import build_invoke_config
from langchain_core.messages import HumanMessage
from langchain_core.tools import StructuredTool, tool
from tests.fakes import ai_text, ai_tool
from app.tools import _with_tool_audit
from app.tool_audit import InMemoryToolAuditRepository, _from_row, digest
from tests.http_helpers import create_and_open, make_client, register_and_login


def test_tool_audit_repository_is_scoped_and_digest_stable():
    repository = InMemoryToolAuditRepository()
    user_id, agent_id, config_id = uuid4(), uuid4(), uuid4()
    record = repository.start(
        user_id=user_id, agent_instance_id=agent_id, config_version_id=config_id,
        thread_id="thread-a", tool_code="get_weather", inputs={"city": "广州"},
    )
    assert record.input_digest == digest({"city": "广州"})
    completed = repository.complete(record.execution_id, status="succeeded", output={"temperature_c": 25})
    assert completed.execution_status == "succeeded"
    assert completed.output_digest == digest({"temperature_c": 25})
    assert len(repository.list_for_scope(user_id=user_id, agent_instance_id=agent_id, config_version_id=config_id, thread_id="thread-a")) == 1
    assert repository.list_for_scope(user_id=uuid4(), agent_instance_id=agent_id, config_version_id=config_id) == []


def test_tool_execution_is_written_with_runtime_scope(runtime):
    client = make_client(runtime)
    register_and_login(client, "audit-owner", "password123")
    agent = create_and_open(client, title="audit-agent", template_code="custom")
    user_id = runtime.business_repo.get_user_by_login_name("audit-owner").user_id
    config = runtime.skill_service.ensure_config(user_id, agent["agent_instance_id"])
    invoke_config = build_invoke_config(
        thread_id=agent["thread_id"],
        user_id=user_id,
        agent_instance_id=agent["agent_instance_id"],
        config_version_id=config["config_version_id"],
    )
    runtime.llm.responses = [ai_tool("get_weather", {"city": "广州"}), ai_text("done")]
    runtime.graph_for_tool_codes(["get_weather"]).invoke(
        {"messages": [HumanMessage(content="天气")]}, invoke_config
    )
    records = runtime.tool_audit_repository.list_for_scope(
        user_id=user_id,
        agent_instance_id=agent["agent_instance_id"],
        config_version_id=config["config_version_id"],
        thread_id=agent["thread_id"],
    )
    assert len(records) == 1
    assert records[0].tool_code == "get_weather"
    assert records[0].execution_status == "succeeded"
    assert records[0].input_digest == digest({"city": "广州"})
    assert records[0].output_digest is not None
    assert runtime.tool_audit_repository.list_for_scope(
        user_id=uuid4(),
        agent_instance_id=agent["agent_instance_id"],
        config_version_id=config["config_version_id"],
    ) == []


def test_tool_execution_failure_is_audited(runtime):
    user_id, agent_id, config_id = uuid4(), uuid4(), uuid4()
    invoke_config = build_invoke_config(
        thread_id="failed-tool", user_id=user_id, agent_instance_id=agent_id,
        config_version_id=config_id,
    )

    @tool
    def failing_tool(value: str) -> str:
        """Fail deterministically for audit coverage."""
        raise RuntimeError("expected failure")

    audited = _with_tool_audit(failing_tool, runtime.tool_audit_repository)
    try:
        audited.invoke({"value": "secret-input"}, config=invoke_config)
    except RuntimeError as exc:
        assert str(exc) == "expected failure"
    else:
        raise AssertionError("failing tool did not raise")
    records = runtime.tool_audit_repository.list_for_scope(
        user_id=user_id, agent_instance_id=agent_id,
        config_version_id=config_id, thread_id="failed-tool",
    )
    assert len(records) == 1
    assert records[0].execution_status == "failed"
    assert records[0].error_code == "RuntimeError"
    assert records[0].output_digest is None


def test_interrupt_is_audited_without_being_marked_failed(runtime, llm):
    client = make_client(runtime)
    register_and_login(client, "audit-interrupt", "password123")
    agent = create_and_open(client, title="audit-interrupt-agent")
    user_id = runtime.business_repo.get_user_by_login_name("audit-interrupt").user_id
    config_version_id = agent["config_version_id"]
    llm.responses = [ai_tool("generate_image", {"prompt": "audit image"}), ai_text("done")]
    response = client.post(
        f"/v1/threads/{agent['thread_id']}/messages", json={"content": "生成图片"}
    )
    assert response.status_code == 200, response.text
    records = runtime.tool_audit_repository.list_for_scope(
        user_id=user_id, agent_instance_id=agent["agent_instance_id"],
        config_version_id=config_version_id, thread_id=agent["thread_id"],
    )
    assert len(records) == 1
    assert records[0].tool_code == "generate_image"
    assert records[0].execution_status == "interrupted"
    assert records[0].error_code == "GraphInterrupt"


def test_async_tool_execution_is_audited(runtime):
    user_id, agent_id, config_id = uuid4(), uuid4(), uuid4()
    invoke_config = build_invoke_config(
        thread_id="async-tool", user_id=user_id, agent_instance_id=agent_id,
        config_version_id=config_id,
    )

    async def async_tool(value: str) -> dict:
        return {"request_id": "mock-1", "value": value}

    audited = _with_tool_audit(
        StructuredTool.from_function(
            coroutine=async_tool, name="async_audit", description="Async audit tool"
        ),
        runtime.tool_audit_repository,
    )
    result = __import__("asyncio").run(
        audited.ainvoke({"value": "async-input"}, config=invoke_config)
    )
    records = runtime.tool_audit_repository.list_for_scope(
        user_id=user_id, agent_instance_id=agent_id,
        config_version_id=config_id, thread_id="async-tool",
    )
    assert result["request_id"] == "mock-1"
    assert len(records) == 1
    assert records[0].execution_status == "succeeded"
    assert records[0].external_request_id == "mock-1"


def test_postgres_row_conversion_accepts_dict_and_tuple():
    values = (
        uuid4(), uuid4(), uuid4(), uuid4(), "thread", "get_weather", "low",
        "not_required", "succeeded", "input", "output", "request", None,
        __import__("datetime").datetime.now(__import__("datetime").timezone.utc), None,
    )
    keys = (
        "execution_id", "user_id", "agent_instance_id", "config_version_id",
        "thread_id", "tool_code", "risk_level", "approval_status",
        "execution_status", "input_digest", "output_digest", "external_request_id",
        "error_code", "created_at", "completed_at",
    )
    record_from_tuple = _from_row(values)
    record_from_dict = _from_row(dict(zip(keys, values)))
    assert record_from_tuple == record_from_dict
    assert record_from_dict.external_request_id == "request"
