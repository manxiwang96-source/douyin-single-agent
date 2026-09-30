from __future__ import annotations

from pathlib import Path

from app.skills import ConfiguredWebSearchProvider, SearchCandidate
from tests.http_helpers import create_and_open, make_client, register_and_login


def _register_instance(client, title: str):
    return create_and_open(client, title=title)


def test_skill_and_config_endpoints_require_bearer(runtime):
    client = make_client(runtime)
    assert client.get("/v1/skills/catalog").status_code == 401
    assert client.get("/v1/prompt-templates").status_code == 401


def test_platform_skill_selection_config_draft_publish_and_prompt_optimize(runtime):
    client = make_client(runtime)
    register_and_login(client)
    instance = _register_instance(client, "skill-agent")
    agent_id = instance["agent_instance_id"]

    catalog = client.get("/v1/skills/catalog")
    assert catalog.status_code == 200
    platform = next(item for item in catalog.json()["items"] if item["owner_scope"] == "platform")
    before = client.get(f"/v1/agent-instances/{agent_id}/skills").json()
    assert before["items"] == []

    selected = client.put(
        f"/v1/agent-instances/{agent_id}/config/draft/skills",
        json={"skill_ids": [platform["skill_id"]]},
    )
    assert selected.status_code == 200, selected.text
    assert [item["skill_id"] for item in selected.json()["items"]] == [platform["skill_id"]]
    current = client.get(f"/v1/agent-instances/{agent_id}/config").json()
    assert current["status"] == "draft"

    updated = client.put(
        f"/v1/agent-instances/{agent_id}/config/draft",
        json={
            "system_prompt": "你是一个严谨的运营助手",
            "example_questions": ["帮我整理线索"],
            "enabled_tool_codes": ["get_current_datetime", "get_weather"],
            "workflow_codes": ["douyin-lead-discovery"],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["system_prompt"] == "你是一个严谨的运营助手"
    before_optimize = client.get(f"/v1/agent-instances/{agent_id}/config").json()
    before_skills = client.get(f"/v1/agent-instances/{agent_id}/skills").json()
    optimized = client.post(
        f"/v1/agent-instances/{agent_id}/config/draft/prompt/optimize",
        json={},
    )
    assert optimized.status_code == 200
    assert optimized.json()["optimized_prompt"] != optimized.json()["original_prompt"]
    after_optimize = client.get(f"/v1/agent-instances/{agent_id}/config").json()
    assert after_optimize["system_prompt"] == "你是一个严谨的运营助手"
    assert after_optimize["enabled_tool_codes"] == before_optimize["enabled_tool_codes"]
    assert after_optimize["workflow_codes"] == before_optimize["workflow_codes"]
    assert after_optimize["knowledge_document_ids"] == before_optimize["knowledge_document_ids"]
    assert client.get(f"/v1/agent-instances/{agent_id}/skills").json() == before_skills
    assert set(optimized.json()) == {"original_prompt", "optimized_prompt", "change_summary", "risk_notice"}
    assert "工具、Skill、工作流" in optimized.json()["change_summary"]
    assert "enabled_tool_codes" not in optimized.json()
    assert "workflow_codes" not in optimized.json()
    assert "skill_ids" not in optimized.json()

    published = client.post(f"/v1/agent-instances/{agent_id}/config/publish")
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    assert client.get(f"/v1/agent-instances/{agent_id}/config").json()["status"] == "draft"

    templates = client.get("/v1/prompt-templates")
    assert templates.status_code == 200
    template_items = templates.json()["items"]
    assert {item["template_id"] for item in template_items} >= {
        "brand-customer-support", "short-video-content", "lead-operations", "enterprise-knowledge-qna"
    }
    for item in template_items:
        assert len(item["prompt"]) >= 200
        assert "角色：" in item["prompt"]
        assert "预期输出：" in item["prompt"]
        assert "适用工具/Skill：" in item["prompt"]
        assert item["variables"]


def test_external_skill_search_import_confirmation_and_agent_isolation(runtime, tmp_path: Path):
    source = tmp_path / "external-skill"
    source.mkdir()
    (source / "SKILL.md").write_text("# Private external skill\nDo safe research.", encoding="utf-8")
    runtime.skill_service.search_provider.register(SearchCandidate(
        candidate_id="mock-external",
        name="Mock External Skill",
        description="searchable external skill",
        source_type="github",
        source_uri=f"file://{source}",
        source_ref="immutable-commit-001",
        license="MIT",
        author="fixture",
        version="1.0.0",
        metadata={"repository": "fixture/external"},
    ))

    client = make_client(runtime)
    register_and_login(client, "skill-owner", "password123")
    agent_a = _register_instance(client, "agent-a")
    agent_b = _register_instance(client, "agent-b")
    agent_a_id = agent_a["agent_instance_id"]
    agent_b_id = agent_b["agent_instance_id"]

    candidates = client.post("/v1/skills/discovery/search", json={"query": "external"})
    assert candidates.status_code == 200
    assert candidates.json()["items"][0]["candidate_id"] == "mock-external"
    imported = client.post(
        "/v1/skills/imports",
        json={"candidate_id": "mock-external", "target_agent_instance_id": agent_a_id},
    )
    assert imported.status_code == 201, imported.text
    import_body = imported.json()
    assert import_body["status"] == "awaiting_confirmation"
    import_id = import_body["import_id"]
    assert client.get(f"/v1/agent-instances/{agent_a_id}/skills").json()["items"] == []

    confirmed = client.post(f"/v1/skills/imports/{import_id}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    skill_id = confirmed.json()["skill_id"]
    a_skills = client.get(f"/v1/agent-instances/{agent_a_id}/skills").json()["items"]
    b_skills = client.get(f"/v1/agent-instances/{agent_b_id}/skills").json()["items"]
    assert [item["skill_id"] for item in a_skills] == [skill_id]
    assert b_skills == []
    assert any(item["skill_id"] == skill_id for item in client.get("/v1/skills/catalog").json()["items"])

    other = make_client(runtime)
    register_and_login(other, "other-owner", "password123")
    other_agent = _register_instance(other, "other-agent")
    assert all(item["skill_id"] != skill_id for item in other.get("/v1/skills/catalog").json()["items"])
    assert other.get(f"/v1/skills/imports/{import_id}").status_code == 403
    assert other.get(f"/v1/agent-instances/{other_agent['agent_instance_id']}/skills").json()["items"] == []


def test_unconfigured_real_search_returns_503_without_exposing_credentials(runtime):
    runtime.skill_service.search_provider = ConfiguredWebSearchProvider(
        "internal", endpoint="", api_key="server-secret", github_token="github-secret"
    )
    client = make_client(runtime)
    register_and_login(client, "search-owner", "password123")
    response = client.post("/v1/skills/discovery/search", json={"query": "external"})
    assert response.status_code == 503
    assert "web search service is not configured" in response.json()["detail"]
    assert "server-secret" not in response.text
    assert "github-secret" not in response.text



def test_skill_import_lifecycle_reject_retry_and_revoke_api(runtime, tmp_path: Path):
    source = tmp_path / "external-lifecycle"
    source.mkdir()
    (source / "SKILL.md").write_text("# Lifecycle Skill\nSafe retry test.", encoding="utf-8")
    runtime.skill_service.search_provider.register(SearchCandidate(
        candidate_id="lifecycle-skill", name="Lifecycle Skill", description="lifecycle",
        source_type="github", source_uri=f"file://{source}", source_ref="immutable-lifecycle-001",
        license="MIT", author="fixture", version="1.0.0",
    ))
    client = make_client(runtime)
    register_and_login(client, "lifecycle-owner", "password123")
    agent = _register_instance(client, "lifecycle-agent")
    agent_id = agent["agent_instance_id"]

    imported = client.post("/v1/skills/imports", json={
        "candidate_id": "lifecycle-skill", "target_agent_instance_id": agent_id,
    })
    assert imported.status_code == 201
    import_id = imported.json()["import_id"]
    quarantine = Path(imported.json()["quarantine_path"])
    assert quarantine.is_dir()

    rejected = client.post(f"/v1/skills/imports/{import_id}/reject")
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["quarantine_path"] is None
    assert not quarantine.exists()

    retried = client.post(f"/v1/skills/imports/{import_id}/retry")
    assert retried.status_code == 200
    assert retried.json()["status"] == "awaiting_confirmation"
    confirmed = client.post(f"/v1/skills/imports/{import_id}/confirm")
    assert confirmed.status_code == 200
    skill_id = confirmed.json()["skill_id"]
    assert client.get(f"/v1/agent-instances/{agent_id}/skills").json()["items"]

    revoked = client.post(f"/v1/skills/{skill_id}/revoke")
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    assert client.get(f"/v1/agent-instances/{agent_id}/skills").json()["items"] == []
    assert all(item["skill_id"] != skill_id for item in client.get("/v1/skills/catalog").json()["items"])


def test_create_declarative_skill_mirrors_private_registry_and_binds_draft(runtime):
    client = make_client(runtime)
    register_and_login(client, "skill-author", "password123")
    instance = _register_instance(client, "custom-skill-agent")
    agent_id = instance["agent_instance_id"]

    created = client.post(
        f"/v1/agent-instances/{agent_id}/skills",
        json={
            "name": "每日简报",
            "description": "按日程汇总",
            "instructions": "当用户要简报时整理当日事项",
            "risk_level": "low",
            "approval_mode": "auto",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    skill_id = body["skill_id"]
    assert body["name"] == "每日简报"
    assert body["owner_scope"] == "user"
    assert body["source_type"] == "custom"
    assert body["risk_level"] == "low"
    assert body["approval_mode"] == "auto"
    assert body["owner_user_id"]

    from uuid import UUID

    repo = runtime.skill_service.repository
    agent_skill = repo.get_agent_skill(UUID(skill_id))
    registry = repo.get_skill(UUID(skill_id))
    assert agent_skill.skill_id == registry.skill_id == UUID(skill_id)
    assert agent_skill.name == "每日简报"
    assert agent_skill.instructions == "当用户要简报时整理当日事项"
    assert registry.owner_scope == "user"
    assert registry.source_type == "custom"
    assert registry.owner_user_id == agent_skill.user_id

    listed = client.get(f"/v1/agent-instances/{agent_id}/skills")
    assert listed.status_code == 200
    assert [item["skill_id"] for item in listed.json()["items"]] == [skill_id]
    bindings = repo.list_bindings(UUID(listed.json()["config_version_id"]))
    assert any(item.skill_id == UUID(skill_id) and item.enabled for item in bindings)
    assert any(item["skill_id"] == skill_id for item in client.get("/v1/skills/catalog").json()["items"])


def test_create_declarative_skill_validates_name_and_enums(runtime):
    client = make_client(runtime)
    register_and_login(client, "skill-validator", "password123")
    instance = _register_instance(client, "validate-skill-agent")
    agent_id = instance["agent_instance_id"]
    url = f"/v1/agent-instances/{agent_id}/skills"

    empty_name = client.post(url, json={"name": "  ", "risk_level": "low", "approval_mode": "auto"})
    assert empty_name.status_code == 400
    assert "name" in empty_name.json()["detail"]

    bad_risk = client.post(url, json={"name": "helper", "risk_level": "critical", "approval_mode": "auto"})
    assert bad_risk.status_code == 400
    assert "risk_level" in bad_risk.json()["detail"]

    bad_approval = client.post(url, json={"name": "helper", "risk_level": "low", "approval_mode": "never"})
    assert bad_approval.status_code == 400
    assert "approval_mode" in bad_approval.json()["detail"]


def test_create_declarative_skill_rejects_cross_user_instance(runtime):
    owner = make_client(runtime)
    register_and_login(owner, "skill-owner-a", "password123")
    instance = _register_instance(owner, "owned-agent")
    agent_id = instance["agent_instance_id"]

    other = make_client(runtime)
    register_and_login(other, "skill-owner-b", "password123")
    response = other.post(
        f"/v1/agent-instances/{agent_id}/skills",
        json={"name": "not-mine", "risk_level": "low", "approval_mode": "once"},
    )
    assert response.status_code == 404


def test_patch_and_delete_declarative_skill_sync_agent_skills_and_registry(runtime):
    client = make_client(runtime)
    register_and_login(client, "skill-editor", "password123")
    instance = _register_instance(client, "edit-skill-agent")
    agent_id = instance["agent_instance_id"]
    created = client.post(
        f"/v1/agent-instances/{agent_id}/skills",
        json={
            "name": "初稿",
            "description": "old",
            "instructions": "先这样",
            "risk_level": "medium",
            "approval_mode": "once",
        },
    )
    assert created.status_code == 201, created.text
    skill_id = created.json()["skill_id"]

    patched = client.patch(
        f"/v1/agent-instances/{agent_id}/skills/{skill_id}",
        json={
            "enabled": True,
            "name": "改名Skill",
            "description": "new",
            "instructions": "改后的指令",
            "risk_level": "high",
            "approval_mode": "always",
        },
    )
    assert patched.status_code == 200, patched.text
    assert any(item["skill_id"] == skill_id and item["name"] == "改名Skill" for item in patched.json()["items"])

    from uuid import UUID

    repo = runtime.skill_service.repository
    agent_skill = repo.get_agent_skill(UUID(skill_id))
    registry = repo.get_skill(UUID(skill_id))
    assert agent_skill.name == registry.name == "改名Skill"
    assert agent_skill.instructions == registry.instructions == "改后的指令"
    assert agent_skill.risk_level == registry.risk_level == "high"
    assert agent_skill.approval_mode == registry.approval_mode == "always"
    assert registry.source_type == "custom"

    deleted = client.delete(f"/v1/agent-instances/{agent_id}/skills/{skill_id}")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["items"] == []
    assert repo.get_agent_skill(UUID(skill_id)).status == "archived"
    assert repo.get_skill(UUID(skill_id)).status == "archived"
    assert client.get(f"/v1/agent-instances/{agent_id}/skills").json()["items"] == []
    assert all(item["skill_id"] != skill_id for item in client.get("/v1/skills/catalog").json()["items"])
