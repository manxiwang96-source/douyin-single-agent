from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from app.graph import build_invoke_config, interrupt_payload
from app.skills import SearchCandidate
from tests.fakes import ai_text, ai_tool


def _external_skill(runtime, tmp_path: Path, user_id, agent_id):
    source = tmp_path / "skill"
    source.mkdir()
    (source / "SKILL.md").write_text("# External\nOnly load after approval.", encoding="utf-8")
    runtime.skill_service.search_provider.register(SearchCandidate(
        candidate_id="interrupt-skill", name="Interrupt Skill", description="approval test",
        source_type="github", source_uri=f"file://{source}", source_ref="immutable-ref",
        license="MIT", author="test", version="1.0.0",
    ))
    imported = runtime.skill_service.start_import(user_id, agent_id, "interrupt-skill")
    skill = runtime.skill_service.confirm_import(user_id, imported.import_id)
    runtime.skill_service.set_config_skills(user_id, agent_id, [skill.skill_id])
    config = runtime.skill_service.ensure_config(user_id, agent_id)
    return skill, config


def test_load_skill_interrupt_emits_payload_and_resume_persists_once(runtime, llm, tmp_path):
    user_id, agent_id, thread_id = uuid4(), uuid4(), "skill-approval-interrupt"
    skill, config = _external_skill(runtime, tmp_path, user_id, agent_id)
    llm.responses = [ai_tool("load_skill", {"skill_id": str(skill.skill_id)}), ai_text("loaded")]
    invoke_config = build_invoke_config(
        thread_id=thread_id, user_id=user_id, agent_instance_id=agent_id,
        config_version_id=config["config_version_id"], enabled_tool_codes=["load_skill"],
    )
    runtime.graph_for_tool_codes(["load_skill"]).invoke(
        {"messages": [HumanMessage(content="load it")]}, invoke_config
    )
    pending = interrupt_payload(runtime.graph_for_tool_codes(["load_skill"]).get_state(invoke_config))
    assert pending is not None
    assert pending["type"] == "review_skill"
    assert pending["skill_id"] == str(skill.skill_id)
    assert pending["options"] == ["approve_once", "approve_session", "deny"]

    result = runtime.graph_for_tool_codes(["load_skill"]).invoke(
        Command(resume={"action": "approve_once"}), invoke_config
    )
    assert result["messages"][-1].content == "loaded"
    assert not runtime.approval_manager.ensure(
        user_id=user_id, agent_instance_id=agent_id,
        config_version_id=config["config_version_id"], thread_id=thread_id,
        approval_kind="skill", resource_code=skill.code,
    )


def test_load_skill_interrupt_deny_returns_explainable_tool_result(runtime, llm, tmp_path):
    user_id, agent_id, thread_id = uuid4(), uuid4(), "skill-approval-deny"
    skill, config = _external_skill(runtime, tmp_path, user_id, agent_id)
    llm.responses = [ai_tool("load_skill", {"skill_id": str(skill.skill_id)}), ai_text("handled")]
    invoke_config = build_invoke_config(
        thread_id=thread_id, user_id=user_id, agent_instance_id=agent_id,
        config_version_id=config["config_version_id"], enabled_tool_codes=["load_skill"],
    )
    graph = runtime.graph_for_tool_codes(["load_skill"])
    graph.invoke({"messages": [HumanMessage(content="load it")]}, invoke_config)
    result = graph.invoke(Command(resume={"action": "deny"}), invoke_config)
    assert result["messages"][-1].content == "handled"
    assert "skill approval denied" in result["messages"][-2].content
