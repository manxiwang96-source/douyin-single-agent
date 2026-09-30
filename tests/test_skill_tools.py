from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from app.graph import build_invoke_config
from app.skills import SearchCandidate


def _tool(runtime, name: str):
    return next(item for item in runtime.tools if item.name == name)


def _approve(runtime, *, user_id, agent_instance_id, config_version_id, thread_id, kind, code, approval_scope="once"):
    record = runtime.approval_manager.repository.request(
        user_id=user_id, agent_instance_id=agent_instance_id,
        config_version_id=config_version_id, thread_id=thread_id,
        approval_kind=kind, resource_code=code, approval_scope=approval_scope,
    )
    runtime.approval_manager.repository.decide(record.approval_id, user_id=user_id, approved=True)


def test_skill_internal_tools_are_registered_and_scope_bound(runtime, tmp_path: Path):
    names = {item.name for item in runtime.tools}
    assert {"web_search", "list_available_skills", "load_skill", "run_skill_script"} <= names

    user_id = uuid4()
    agent_id = uuid4()
    config = runtime.skill_service.ensure_config(user_id, agent_id)
    config_id = config["config_version_id"]
    thread_id = "skill-tool-thread"
    runtime.skill_service.set_config_skills(
        user_id, agent_id, [runtime.skill_repository.find_skill_by_code("brand-customer-support", user_id=user_id).skill_id]
    )
    candidate_dir = tmp_path / "candidate"
    candidate_dir.mkdir()
    (candidate_dir / "SKILL.md").write_text("# External\nUse the script only after approval.", encoding="utf-8")
    (candidate_dir / "main.py").write_text("print('safe-output')", encoding="utf-8")
    runtime.skill_service.search_provider.register(SearchCandidate(
        candidate_id="tool-external", name="Tool External", description="tool test",
        source_type="github", source_uri=f"file://{candidate_dir}", source_ref="commit-1",
        license="MIT", author="test", version="1.0.0",
    ))
    imported = runtime.skill_service.start_import(user_id, agent_id, "tool-external")
    skill = runtime.skill_service.confirm_import(user_id, imported.import_id)
    runtime.skill_service.set_config_skills(user_id, agent_id, [skill.skill_id])
    config_id = runtime.skill_service.ensure_config(user_id, agent_id)["config_version_id"]
    _approve(runtime, user_id=user_id, agent_instance_id=agent_id, config_version_id=config_id, thread_id=thread_id, kind="skill", code=skill.code, approval_scope="session")
    _approve(runtime, user_id=user_id, agent_instance_id=agent_id, config_version_id=config_id, thread_id=thread_id, kind="tool", code="web_search")
    _approve(runtime, user_id=user_id, agent_instance_id=agent_id, config_version_id=config_id, thread_id=thread_id, kind="tool", code="run_skill_script")
    _approve(runtime, user_id=user_id, agent_instance_id=agent_id, config_version_id=config_id, thread_id=thread_id, kind="script", code=f"{skill.code}:main.py")
    invoke_config = build_invoke_config(
        thread_id=thread_id, user_id=user_id, agent_instance_id=agent_id,
        config_version_id=config_id, enabled_tool_codes=["web_search", "list_available_skills", "load_skill", "run_skill_script"],
    )

    search = json.loads(_tool(runtime, "web_search").invoke({"query": "tool"}, config=invoke_config))
    assert search["ok"] is True
    available = json.loads(_tool(runtime, "list_available_skills").invoke({}, config=invoke_config))
    assert [item["code"] for item in available["items"]] == [skill.code]
    loaded = json.loads(_tool(runtime, "load_skill").invoke({"skill_id": str(skill.skill_id)}, config=invoke_config))
    assert loaded["ok"] is True
    result = json.loads(_tool(runtime, "run_skill_script").invoke({"skill_id": str(skill.skill_id), "script_path": "main.py"}, config=invoke_config))
    assert result["ok"] is True
    assert "safe-output" in result["result"]["output"]


def test_skill_tool_cannot_load_unbound_or_cross_scope_skill(runtime):
    user_id = uuid4()
    agent_id = uuid4()
    other_agent_id = uuid4()
    config = runtime.skill_service.ensure_config(user_id, agent_id)
    skill = runtime.skill_repository.find_skill_by_code("brand-customer-support", user_id=user_id)
    invoke_config = build_invoke_config(
        thread_id="scope-thread", user_id=user_id, agent_instance_id=other_agent_id,
        config_version_id=config["config_version_id"], enabled_tool_codes=["load_skill"],
    )
    loaded = json.loads(_tool(runtime, "load_skill").invoke({"skill_id": str(skill.skill_id)}, config=invoke_config))
    assert loaded["ok"] is False
    assert "scope" in loaded["error"] or "enabled" in loaded["error"]
