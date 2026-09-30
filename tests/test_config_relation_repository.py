from __future__ import annotations

from uuid import uuid4

import pytest

from app.skills import (
    AgentSkillRecord,
    InMemorySkillRepository,
    REQUIRED_CONFIG_TOOL_CODE,
    SkillError,
    SkillNotFoundError,
    utcnow,
)


def _repo():
    return InMemorySkillRepository()


def test_ensure_draft_writes_datetime_tool_relation():
    repo = _repo()
    user_id, agent_id = uuid4(), uuid4()
    draft = repo.ensure_draft(user_id, agent_id)
    assert draft["enabled_tool_codes"] == [REQUIRED_CONFIG_TOOL_CODE]
    assert draft["knowledge_document_ids"] == []
    tool = repo.config_tools[(draft["config_version_id"], REQUIRED_CONFIG_TOOL_CODE)]
    assert tool.enabled is True
    assert tool.user_id == user_id
    assert tool.agent_instance_id == agent_id


def test_update_config_uses_relation_tables_and_mirrors_json():
    repo = _repo()
    user_id, agent_id = uuid4(), uuid4()
    draft = repo.ensure_draft(user_id, agent_id)
    document_id = uuid4()
    updated = repo.update_config(
        draft["config_version_id"],
        enabled_tool_codes=["discover_leads"],
        knowledge_document_ids=[str(document_id)],
    )
    assert updated["enabled_tool_codes"] == [REQUIRED_CONFIG_TOOL_CODE, "discover_leads"]
    assert updated["knowledge_document_ids"] == [document_id]
    assert repo.config_tools[(draft["config_version_id"], "discover_leads")].enabled is True
    assert repo.config_knowledge_documents[(draft["config_version_id"], document_id)].document_id == document_id
    stored = repo.config_versions[draft["config_version_id"]]
    assert stored["enabled_tool_codes"] == [REQUIRED_CONFIG_TOOL_CODE, "discover_leads"]
    assert stored["knowledge_document_ids"] == [document_id]


def test_read_backfills_relation_tables_from_legacy_jsonb():
    repo = _repo()
    user_id, agent_id = uuid4(), uuid4()
    draft = repo.ensure_draft(user_id, agent_id)
    version_id = draft["config_version_id"]
    document_id = uuid4()
    repo.config_tools.clear()
    repo.config_knowledge_documents.clear()
    repo.config_versions[version_id]["enabled_tool_codes"] = ["discover_leads"]
    repo.config_versions[version_id]["knowledge_document_ids"] = [document_id]
    loaded = repo.get_config(version_id)
    assert loaded["enabled_tool_codes"] == [REQUIRED_CONFIG_TOOL_CODE, "discover_leads"]
    assert loaded["knowledge_document_ids"] == [document_id]
    assert (version_id, REQUIRED_CONFIG_TOOL_CODE) in repo.config_tools
    assert (version_id, "discover_leads") in repo.config_tools
    assert (version_id, document_id) in repo.config_knowledge_documents


def test_empty_relation_and_jsonb_does_not_invent_published_tools():
    repo = _repo()
    user_id, agent_id = uuid4(), uuid4()
    draft = repo.ensure_draft(user_id, agent_id)
    version_id = draft["config_version_id"]
    repo.config_versions[version_id]["status"] = "published"
    repo.config_versions[version_id]["enabled_tool_codes"] = []
    repo.config_versions[version_id]["knowledge_document_ids"] = []
    repo.config_tools.clear()
    repo.config_knowledge_documents.clear()
    loaded = repo.get_config(version_id)
    assert loaded["enabled_tool_codes"] == []
    assert loaded["knowledge_document_ids"] == []
    assert repo.get_effective_config(user_id, agent_id)["enabled_tool_codes"] == []


def test_publish_copies_relation_rows_to_new_draft():
    repo = _repo()
    user_id, agent_id = uuid4(), uuid4()
    draft = repo.ensure_draft(user_id, agent_id)
    document_id = uuid4()
    repo.update_config(
        draft["config_version_id"],
        enabled_tool_codes=["discover_leads"],
        knowledge_document_ids=[document_id],
    )
    published = repo.publish_config(user_id, agent_id)
    new_draft = repo.get_draft(user_id, agent_id)
    assert published["status"] == "published"
    assert published["config_version_id"] != new_draft["config_version_id"]
    assert new_draft["enabled_tool_codes"] == [REQUIRED_CONFIG_TOOL_CODE, "discover_leads"]
    assert new_draft["knowledge_document_ids"] == [document_id]
    assert (published["config_version_id"], "discover_leads") in repo.config_tools
    assert (new_draft["config_version_id"], "discover_leads") in repo.config_tools
    assert (new_draft["config_version_id"], document_id) in repo.config_knowledge_documents


def test_agent_skills_crud_and_archive():
    repo = _repo()
    user_id, agent_id = uuid4(), uuid4()
    now = utcnow()
    created = repo.save_agent_skill(
        AgentSkillRecord(
            skill_id=uuid4(),
            user_id=user_id,
            agent_instance_id=agent_id,
            name="  draft helper  ",
            description="desc",
            instructions="do it",
            risk_level="medium",
            approval_mode="once",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    assert created.name == "draft helper"
    assert repo.get_agent_skill(created.skill_id).skill_id == created.skill_id
    listed = repo.list_agent_skills(user_id, agent_id)
    assert [item.skill_id for item in listed] == [created.skill_id]
    renamed = repo.update_agent_skill(created.skill_id, name="renamed")
    assert renamed.name == "renamed"
    archived = repo.archive_agent_skill(created.skill_id)
    assert archived.status == "archived"
    assert repo.list_agent_skills(user_id, agent_id) == []
    assert repo.list_agent_skills(user_id, agent_id, include_archived=True)[0].status == "archived"
    with pytest.raises(SkillNotFoundError):
        repo.get_agent_skill(uuid4())
    with pytest.raises(SkillError):
        repo.save_agent_skill(
            AgentSkillRecord(
                skill_id=uuid4(),
                user_id=user_id,
                agent_instance_id=agent_id,
                name="bad",
                description="",
                instructions="",
                risk_level="critical",
                approval_mode="once",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
