from tests.http_helpers import create_and_open, make_client, register_and_login


def test_agent_configuration_surface_and_scope(runtime):
    client = make_client(runtime)
    register_and_login(client, "surface-owner", "password123")
    types = client.get("/v1/agent-types")
    assert types.status_code == 200
    assert {item["template_code"] for item in types.json()["items"]} == {"douyin_ops", "custom"}

    instance = create_and_open(client, title="surface-agent", template_code="custom")
    agent_id = instance["agent_instance_id"]
    versions = client.get(f"/v1/agent-instances/{agent_id}/config/versions")
    assert versions.status_code == 200
    items = versions.json()["items"]
    statuses = {item["status"] for item in items}
    assert "published" in statuses
    assert "draft" in statuses

    tools = client.get(f"/v1/agent-instances/{agent_id}/tools")
    assert tools.status_code == 200
    tool_codes = {item["tool_code"] for item in tools.json()["items"]}
    assert {"get_current_datetime", "get_weather"}.issubset(tool_codes)
    updated = client.put(
        f"/v1/agent-instances/{agent_id}/config/draft/tools",
        json={"enabled_tool_codes": ["get_weather"]},
    )
    assert updated.status_code == 200
    assert updated.json()["enabled_tool_codes"] == ["get_current_datetime", "get_weather"]
    assert client.put(
        f"/v1/agent-instances/{agent_id}/config/draft/tools",
        json={"enabled_tool_codes": ["not-a-tool"]},
    ).status_code == 400

    created = client.post(
        f"/v1/agent-instances/{agent_id}/knowledge",
        json={"title": "内部规则", "filename": "rules.md", "storage_uri": "knowledge/rules.md"},
    )
    assert created.status_code == 201, created.text
    document = created.json()
    listed = client.get(f"/v1/agent-instances/{agent_id}/knowledge").json()
    assert listed["items"][0]["document_id"] == document["document_id"]
    updated_doc = client.patch(
        f"/v1/agent-instances/{agent_id}/knowledge/{document['document_id']}",
        json={"title": "内部规则 v2", "status": "ready"},
    )
    assert updated_doc.status_code == 200
    assert updated_doc.json()["title"] == "内部规则 v2"
    deleted = client.delete(f"/v1/agent-instances/{agent_id}/knowledge/{document['document_id']}")
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "archived"


def test_skill_patch_and_knowledge_are_isolated_between_users(runtime):
    owner = make_client(runtime)
    register_and_login(owner, "surface-a", "password123")
    agent = create_and_open(owner, title="owned-agent", template_code="custom")
    agent_id = agent["agent_instance_id"]
    platform = next(item for item in owner.get("/v1/skills/catalog").json()["items"] if item["owner_scope"] == "platform")
    enabled = owner.patch(f"/v1/agent-instances/{agent_id}/skills/{platform['skill_id']}", json={"enabled": True})
    assert enabled.status_code == 200
    assert len(enabled.json()["items"]) == 1

    other = make_client(runtime)
    register_and_login(other, "surface-b", "password123")
    assert other.get(f"/v1/agent-instances/{agent_id}/tools").status_code == 404
    assert other.get(f"/v1/agent-instances/{agent_id}/config/versions").status_code == 404
    assert other.delete(f"/v1/agent-instances/{agent_id}/skills/{platform['skill_id']}").status_code == 404
