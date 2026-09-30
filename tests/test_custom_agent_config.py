from __future__ import annotations

from uuid import UUID

import pytest

from app.knowledge import kb_namespace
from app.plaza import DOUYIN_OPS_DEFAULT_TOOL_CODES
from app.skills import (
    InMemorySkillRepository,
    KnowledgeDocumentNotOwnedError,
    PROMPT_OPTIMIZE_LOCKED_FIELDS,
    PublishedConfigNotFound,
    UnknownToolCodeError,
    build_prompt_optimize_result,
    validate_draft_knowledge_document_ids,
    validate_draft_tool_codes,
)
from tests.fakes import ai_text, ai_tool
from tests.http_helpers import make_client, post_chat, register_and_login


def _create(client, template_code: str, title: str):
    response = client.post("/v1/agent-instances", json={"template_code": template_code, "title": title, "intro": title})
    assert response.status_code == 201, response.text
    return response.json()


def test_custom_instance_isolated_from_douyin_template_and_defaults_to_time_tool(runtime):
    client = make_client(runtime)
    register_and_login(client, "custom-owner", "password123")
    custom = _create(client, "custom", "custom-agent")
    instance_id = custom["agent_instance_id"]

    assert custom["template_code"] == "custom"
    sidebar = client.get(f"/v1/agent-instances/{instance_id}/sidebar")
    assert sidebar.status_code == 200
    assert sidebar.json()["workflows"] == []
    assert sidebar.json()["tools"] == []

    config = client.get(f"/v1/agent-instances/{instance_id}/config")
    assert config.status_code == 200
    assert config.json()["enabled_tool_codes"] == ["get_current_datetime"]
    assert config.json()["knowledge_document_ids"] == []

    preview = client.post(f"/v1/agent-instances/{instance_id}/config/draft/preview", json={"prompt": "测试草稿"})
    assert preview.status_code == 200
    assert preview.json()["status"] == "draft_preview"
    assert preview.json()["enabled_tool_codes"] == ["get_current_datetime"]
    assert "不创建正式线程" in preview.json()["answer"]



def test_threads_keep_the_published_config_version_after_a_new_publish(runtime, llm):
    client = make_client(runtime)
    register_and_login(client, "thread-config-owner", "password123")
    instance = _create(client, "custom", "versioned-agent")
    instance_id = instance["agent_instance_id"]
    user = runtime.business_repo.get_user_by_login_name("thread-config-owner")

    draft = client.put(
        f"/v1/agent-instances/{instance_id}/config/draft",
        json={"system_prompt": "旧版本提示词"},
    ).json()
    published_old = client.post(f"/v1/agent-instances/{instance_id}/config/publish").json()
    old_thread = runtime.business_repo.create_app_thread(
        user.user_id, runtime.business_repo.get_agent_instance(UUID(instance_id)).agent_instance_id,
        config_version_id=UUID(published_old["config_version_id"]),
    )
    assert old_thread.thread_kind == "official"

    client.put(
        f"/v1/agent-instances/{instance_id}/config/draft",
        json={"system_prompt": "新版本提示词"},
    )
    published_new = client.post(f"/v1/agent-instances/{instance_id}/config/publish").json()
    new_thread = runtime.business_repo.create_app_thread(
        user.user_id, UUID(instance_id),
        config_version_id=UUID(published_new["config_version_id"]),
    )

    llm.responses = [ai_text("旧回复"), ai_text("新回复")]
    old_response = client.post(f"/v1/threads/{old_thread.thread_id}/messages", json={"content": "测试旧线程"})
    new_response = client.post(f"/v1/threads/{new_thread.thread_id}/messages", json={"content": "测试新线程"})
    assert old_response.status_code == 200, old_response.text
    assert new_response.status_code == 200, new_response.text
    assert "旧版本提示词" in llm.calls[0][0].content
    assert "新版本提示词" in llm.calls[1][0].content
    assert "新版本提示词" not in llm.calls[0][0].content
    assert old_thread.config_version_id == UUID(published_old["config_version_id"])
    assert new_thread.config_version_id == UUID(published_new["config_version_id"])


def test_knowledge_selection_is_scoped_to_instance_and_config_version(runtime):
    client = make_client(runtime)
    register_and_login(client, "knowledge-owner", "password123")
    douyin = _create(client, "douyin_ops", "knowledge-agent")
    custom = _create(client, "custom", "empty-agent")

    knowledge = client.get(f"/v1/agent-instances/{douyin['agent_instance_id']}/knowledge")
    assert knowledge.status_code == 200
    document = knowledge.json()["items"][0]
    selected = client.put(
        f"/v1/agent-instances/{douyin['agent_instance_id']}/config/draft",
        json={"knowledge_document_ids": [document["document_id"]]},
    )
    assert selected.status_code == 200
    assert selected.json()["knowledge_document_ids"] == [document["document_id"]]
    skill_repo = runtime.skill_repository
    version_id = UUID(selected.json()["config_version_id"])
    assert (version_id, UUID(document["document_id"])) in skill_repo.config_knowledge_documents

    cross_instance = client.put(
        f"/v1/agent-instances/{custom['agent_instance_id']}/config/draft",
        json={"knowledge_document_ids": [document["document_id"]]},
    )
    assert cross_instance.status_code == 403

    other = make_client(runtime)
    register_and_login(other, "knowledge-other", "password123")
    assert other.get(f"/v1/agent-instances/{douyin['agent_instance_id']}/knowledge").status_code == 404


def test_draft_tools_persist_datetime_and_relation_backed_codes(runtime):
    client = make_client(runtime)
    register_and_login(client, "tool-relation-owner", "password123")
    custom = _create(client, "custom", "tool-agent")
    instance_id = custom["agent_instance_id"]

    updated = client.put(
        f"/v1/agent-instances/{instance_id}/config/draft",
        json={"enabled_tool_codes": ["discover_leads"]},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["enabled_tool_codes"] == ["get_current_datetime", "discover_leads"]

    loaded = client.get(f"/v1/agent-instances/{instance_id}/config")
    assert loaded.status_code == 200, loaded.text
    assert loaded.json()["enabled_tool_codes"] == ["get_current_datetime", "discover_leads"]

    skill_repo = runtime.skill_repository
    version_id = UUID(loaded.json()["config_version_id"])
    assert (version_id, "get_current_datetime") in skill_repo.config_tools
    assert (version_id, "discover_leads") in skill_repo.config_tools
    assert skill_repo.config_versions[version_id]["enabled_tool_codes"] == [
        "get_current_datetime",
        "discover_leads",
    ]


def test_tool_catalog_api_maps_legacy_leads_alias_and_rejects_unknown(runtime):
    client = make_client(runtime)
    register_and_login(client, "tool-catalog-owner", "password123")
    custom = _create(client, "custom", "catalog-agent")
    instance_id = custom["agent_instance_id"]

    listed = client.get(f"/v1/agent-instances/{instance_id}/tools")
    assert listed.status_code == 200, listed.text
    payload = listed.json()
    items = payload["items"]
    codes = [item["tool_code"] for item in items]
    assert payload["config_version_id"]
    assert "discover_leads" in codes
    assert "discover_douyin_leads" not in codes
    assert "load_skill" not in codes
    assert "run_skill_script" not in codes
    datetime_item = next(item for item in items if item["tool_code"] == "get_current_datetime")
    assert datetime_item["display_name"] == "当前时间"
    assert datetime_item["description"]
    assert datetime_item["risk_level"] == "low"
    assert datetime_item["built_in"] is True
    assert datetime_item["enabled"] is True
    assert datetime_item["group"] == "builtin"
    leads_item = next(item for item in items if item["tool_code"] == "discover_leads")
    assert leads_item["display_name"] == "线索发现"
    assert leads_item["built_in"] is False
    assert leads_item["risk_level"] == "high"
    assert leads_item["group"]

    mapped = client.put(
        f"/v1/agent-instances/{instance_id}/config/draft/tools",
        json={"enabled_tool_codes": ["discover_douyin_leads"]},
    )
    assert mapped.status_code == 200, mapped.text
    assert mapped.json()["enabled_tool_codes"] == ["get_current_datetime", "discover_leads"]
    assert "discover_douyin_leads" not in mapped.json()["enabled_tool_codes"]

    both = client.put(
        f"/v1/agent-instances/{instance_id}/config/draft/tools",
        json={"enabled_tool_codes": ["discover_leads", "discover_douyin_leads"]},
    )
    assert both.status_code == 200, both.text
    assert both.json()["enabled_tool_codes"] == ["get_current_datetime", "discover_leads"]

    listed_after = client.get(f"/v1/agent-instances/{instance_id}/tools")
    enabled = {item["tool_code"]: item["enabled"] for item in listed_after.json()["items"]}
    assert enabled["discover_leads"] is True
    assert enabled["get_current_datetime"] is True

    unknown = client.put(
        f"/v1/agent-instances/{instance_id}/config/draft/tools",
        json={"enabled_tool_codes": ["not-a-tool"]},
    )
    assert unknown.status_code == 400


def test_put_draft_rejects_unknown_tools_maps_alias_and_fills_datetime(runtime):
    client = make_client(runtime)
    register_and_login(client, "draft-validate-owner", "password123")
    custom = _create(client, "custom", "draft-validate-agent")
    instance_id = custom["agent_instance_id"]

    unknown = client.put(
        f"/v1/agent-instances/{instance_id}/config/draft",
        json={"enabled_tool_codes": ["not-a-tool"]},
    )
    assert unknown.status_code == 400
    assert unknown.json()["detail"] == "unknown tool code"

    internal = client.put(
        f"/v1/agent-instances/{instance_id}/config/draft",
        json={"enabled_tool_codes": ["load_skill"]},
    )
    assert internal.status_code == 400

    mapped = client.put(
        f"/v1/agent-instances/{instance_id}/config/draft",
        json={"enabled_tool_codes": ["discover_douyin_leads"]},
    )
    assert mapped.status_code == 200, mapped.text
    assert mapped.json()["enabled_tool_codes"] == ["get_current_datetime", "discover_leads"]
    assert "discover_douyin_leads" not in mapped.json()["enabled_tool_codes"]

    filled = client.put(
        f"/v1/agent-instances/{instance_id}/config/draft",
        json={"enabled_tool_codes": ["search_kb"]},
    )
    assert filled.status_code == 200, filled.text
    assert filled.json()["enabled_tool_codes"] == ["get_current_datetime", "search_kb"]
    skill_repo = runtime.skill_repository
    version_id = UUID(filled.json()["config_version_id"])
    assert (version_id, "get_current_datetime") in skill_repo.config_tools
    assert (version_id, "search_kb") in skill_repo.config_tools


def test_draft_tool_and_knowledge_validators():
    assert validate_draft_tool_codes([]) == ["get_current_datetime"]
    assert validate_draft_tool_codes(["discover_douyin_leads"]) == ["get_current_datetime", "discover_leads"]
    with pytest.raises(UnknownToolCodeError):
        validate_draft_tool_codes(["not-a-tool"])
    owned = UUID("33333333-3333-3333-3333-333333333333")
    assert validate_draft_knowledge_document_ids([owned], allowed_document_ids=[owned]) == [str(owned)]
    with pytest.raises(KnowledgeDocumentNotOwnedError):
        validate_draft_knowledge_document_ids(
            [UUID("44444444-4444-4444-4444-444444444444")],
            allowed_document_ids=[owned],
        )
    result = build_prompt_optimize_result("keep-tools")
    assert PROMPT_OPTIMIZE_LOCKED_FIELDS.isdisjoint(result)
    assert result["original_prompt"] == "keep-tools"
    assert result["optimized_prompt"] != result["original_prompt"]


def _published_item(client, instance_id: str) -> dict:
    versions = client.get(f"/v1/agent-instances/{instance_id}/config/versions")
    assert versions.status_code == 200, versions.text
    published = [item for item in versions.json()["items"] if item["status"] == "published"]
    assert published, versions.json()
    return max(published, key=lambda item: item["version_no"])


def test_create_publishes_custom_default_and_open_pins_published(runtime):
    client = make_client(runtime)
    register_and_login(client, "create-publish-custom", "password123")
    custom = _create(client, "custom", "published-custom")
    instance_id = custom["agent_instance_id"]
    published = _published_item(client, instance_id)
    assert published["enabled_tool_codes"] == ["get_current_datetime"]
    assert "discover_douyin_leads" not in published["enabled_tool_codes"]
    draft = client.get(f"/v1/agent-instances/{instance_id}/config")
    assert draft.status_code == 200
    assert draft.json()["status"] == "draft"
    assert draft.json()["config_version_id"] != published["config_version_id"]
    opened = client.post(f"/v1/agent-instances/{instance_id}/open")
    assert opened.status_code == 200, opened.text
    assert opened.json()["config_version_id"] == published["config_version_id"]
    thread = runtime.business_repo.get_app_thread(opened.json()["thread_id"])
    assert thread.thread_kind == "official"
    assert str(thread.config_version_id) == published["config_version_id"]


def test_create_publishes_douyin_explicit_default_tools(runtime):
    client = make_client(runtime)
    register_and_login(client, "create-publish-douyin", "password123")
    douyin = _create(client, "douyin_ops", "published-douyin")
    published = _published_item(client, douyin["agent_instance_id"])
    codes = published["enabled_tool_codes"]
    assert codes[0] == "get_current_datetime"
    for code in DOUYIN_OPS_DEFAULT_TOOL_CODES:
        assert code in codes
    assert "discover_leads" in codes
    assert "discover_douyin_leads" not in codes
    assert published["workflow_codes"] == ["douyin-lead-discovery"]
    assert published["knowledge_document_ids"]
    opened = client.post(f"/v1/agent-instances/{douyin['agent_instance_id']}/open")
    assert opened.status_code == 200, opened.text
    assert opened.json()["config_version_id"] == published["config_version_id"]


def test_open_publishes_legacy_draft_instead_of_409(runtime):
    client = make_client(runtime)
    register_and_login(client, "legacy-open-owner", "password123")
    user = runtime.business_repo.get_user_by_login_name("legacy-open-owner")
    instance = runtime.business_repo.create_agent_instance(
        user.user_id, "legacy-open-agent", intro="x", template_code="custom"
    )
    draft = runtime.skill_service.repository.ensure_draft(user.user_id, instance.agent_instance_id)
    assert draft["status"] == "draft"
    versions_before = runtime.skill_service.list_config_versions(user.user_id, instance.agent_instance_id)
    assert all(item["status"] != "published" for item in versions_before)
    with pytest.raises(PublishedConfigNotFound):
        runtime.skill_service.get_effective_config(user.user_id, instance.agent_instance_id, prefer_draft=False)
    opened = client.post(f"/v1/agent-instances/{instance.agent_instance_id}/open")
    assert opened.status_code == 200, opened.text
    assert opened.status_code != 409
    published = [
        item
        for item in runtime.skill_service.list_config_versions(user.user_id, instance.agent_instance_id)
        if item["status"] == "published"
    ]
    assert published
    assert opened.json()["config_version_id"] == str(published[0]["config_version_id"])
    thread = runtime.business_repo.get_app_thread(opened.json()["thread_id"])
    assert thread.thread_kind == "official"
    assert thread.config_version_id == published[0]["config_version_id"]
    effective = runtime.skill_service.get_effective_config(
        user.user_id, instance.agent_instance_id, prefer_draft=False
    )
    assert effective["status"] == "published"
    assert effective["config_version_id"] == published[0]["config_version_id"]


def test_get_effective_config_does_not_return_draft_as_published():
    repo = InMemorySkillRepository()
    user_id, agent_id = UUID("11111111-1111-1111-1111-111111111111"), UUID("22222222-2222-2222-2222-222222222222")
    draft = repo.ensure_draft(user_id, agent_id)
    with pytest.raises(PublishedConfigNotFound):
        repo.get_effective_config(user_id, agent_id, prefer_draft=False)
    loaded = repo.get_effective_config(user_id, agent_id, prefer_draft=True)
    assert loaded["status"] == "draft"
    assert loaded["config_version_id"] == draft["config_version_id"]


def _bound_names(llm) -> set[str]:
    return {getattr(tool, "name", "") for tool in (llm.bound_tools or [])}


def test_custom_chat_does_not_bind_unselected_discover_leads(runtime, llm):
    client = make_client(runtime)
    register_and_login(client, "custom-tools-owner", "password123")
    custom = _create(client, "custom", "custom-no-leads")
    opened = client.post(f"/v1/agent-instances/{custom['agent_instance_id']}/open")
    assert opened.status_code == 200, opened.text
    llm.responses = [ai_text("ok")]
    response = client.post(
        f"/v1/threads/{opened.json()['thread_id']}/messages",
        json={"content": "hi"},
    )
    assert response.status_code == 200, response.text
    names = _bound_names(llm)
    assert "discover_leads" not in names
    assert "get_current_datetime" in names


def test_douyin_default_chat_binds_discover_leads(runtime, llm):
    client = make_client(runtime)
    register_and_login(client, "douyin-tools-owner", "password123")
    douyin = _create(client, "douyin_ops", "douyin-default-tools")
    opened = client.post(f"/v1/agent-instances/{douyin['agent_instance_id']}/open")
    assert opened.status_code == 200, opened.text
    llm.responses = [ai_text("ok")]
    response = client.post(
        f"/v1/threads/{opened.json()['thread_id']}/messages",
        json={"content": "hi"},
    )
    assert response.status_code == 200, response.text
    names = _bound_names(llm)
    assert "discover_leads" in names
    assert "get_current_datetime" in names


def test_datetime_only_douyin_published_does_not_bind_all_tools(runtime, llm):
    client = make_client(runtime)
    register_and_login(client, "douyin-datetime-owner", "password123")
    douyin = _create(client, "douyin_ops", "douyin-datetime-only")
    instance_id = douyin["agent_instance_id"]
    saved = client.put(
        f"/v1/agent-instances/{instance_id}/config/draft",
        json={"enabled_tool_codes": ["get_current_datetime"]},
    )
    assert saved.status_code == 200, saved.text
    published = client.post(f"/v1/agent-instances/{instance_id}/config/publish")
    assert published.status_code == 200, published.text
    assert published.json()["enabled_tool_codes"] == ["get_current_datetime"]
    opened = client.post(f"/v1/agent-instances/{instance_id}/open")
    assert opened.status_code == 200, opened.text
    llm.responses = [ai_text("ok")]
    response = client.post(
        f"/v1/threads/{opened.json()['thread_id']}/messages",
        json={"content": "hi"},
    )
    assert response.status_code == 200, response.text
    names = _bound_names(llm)
    runtime_names = {getattr(tool, "name", "") for tool in (runtime.tools or [])}
    assert names == {"get_current_datetime"}
    assert "discover_leads" not in names
    assert names != runtime_names


def test_debug_rereads_draft_while_official_stays_on_published(runtime, llm):
    client = make_client(runtime)
    register_and_login(client, "debug-draft-owner", "password123")
    custom = _create(client, "custom", "debug-vs-official")
    instance_id = custom["agent_instance_id"]
    saved = client.put(
        f"/v1/agent-instances/{instance_id}/config/draft",
        json={
            "system_prompt": "PUBLISHED_PROMPT_MARKER",
            "enabled_tool_codes": ["get_current_datetime"],
        },
    )
    assert saved.status_code == 200, saved.text
    published = client.post(f"/v1/agent-instances/{instance_id}/config/publish")
    assert published.status_code == 200, published.text
    opened = client.post(f"/v1/agent-instances/{instance_id}/open")
    assert opened.status_code == 200, opened.text
    official_id = opened.json()["thread_id"]
    draft = client.put(
        f"/v1/agent-instances/{instance_id}/config/draft",
        json={
            "system_prompt": "DRAFT_PROMPT_MARKER",
            "enabled_tool_codes": ["get_current_datetime", "discover_leads"],
        },
    )
    assert draft.status_code == 200, draft.text
    assert draft.json()["status"] == "draft"
    user = runtime.business_repo.get_user_by_login_name("debug-draft-owner")
    debug_thread = runtime.business_repo.create_app_thread(
        user.user_id,
        UUID(instance_id),
        thread_kind="debug",
    )
    llm.responses = [ai_text("official-ok"), ai_text("debug-ok")]
    official = client.post(f"/v1/threads/{official_id}/messages", json={"content": "official hi"})
    official_names = _bound_names(llm)
    official_prompt = llm.calls[0][0].content
    assert official.status_code == 200, official.text
    debug = client.post(f"/v1/threads/{debug_thread.thread_id}/messages", json={"content": "debug hi"})
    debug_names = _bound_names(llm)
    debug_prompt = llm.calls[1][0].content
    assert debug.status_code == 200, debug.text
    assert "PUBLISHED_PROMPT_MARKER" in official_prompt
    assert "DRAFT_PROMPT_MARKER" not in official_prompt
    assert "discover_leads" not in official_names
    assert "get_current_datetime" in official_names
    assert "DRAFT_PROMPT_MARKER" in debug_prompt
    assert "PUBLISHED_PROMPT_MARKER" not in debug_prompt
    assert "discover_leads" in debug_names
    assert "get_current_datetime" in debug_names

def _index_instance_doc(runtime, user_id, instance_id, filename: str, text: str):
    record = runtime.business_repo.add_knowledge_document(
        user_id,
        instance_id,
        title=filename,
        filename=filename,
        storage_uri=filename,
        source="user_upload",
        status="ready",
    )
    runtime.memory_store.put(
        kb_namespace(user_id, instance_id),
        f"{filename}:0",
        {"text": text, "source": filename, "chunk_id": f"{filename}:0"},
    )
    return record


def test_search_kb_uses_selected_documents_only(runtime, llm):
    client = make_client(runtime)
    register_and_login(client, "kb-runtime-owner", "password123")
    first = _create(client, "custom", "kb-runtime-a")
    second = _create(client, "custom", "kb-runtime-b")
    user = runtime.business_repo.get_user_by_login_name("kb-runtime-owner")
    inst_a = UUID(first["agent_instance_id"])
    inst_b = UUID(second["agent_instance_id"])
    keep = _index_instance_doc(runtime, user.user_id, inst_a, "keep.md", "KEEP_DOC_MARKER selected keep file")
    _index_instance_doc(runtime, user.user_id, inst_a, "skip.md", "SKIP_DOC_MARKER unselected skip file")
    _index_instance_doc(runtime, user.user_id, inst_b, "other.md", "OTHER_INSTANCE_MARKER other instance file")

    saved = client.put(
        f"/v1/agent-instances/{inst_a}/config/draft",
        json={
            "enabled_tool_codes": ["get_current_datetime", "search_kb"],
            "knowledge_document_ids": [str(keep.document_id)],
        },
    )
    assert saved.status_code == 200, saved.text
    published = client.post(f"/v1/agent-instances/{inst_a}/config/publish")
    assert published.status_code == 200, published.text
    opened_a = client.post(f"/v1/agent-instances/{inst_a}/open")
    assert opened_a.status_code == 200, opened_a.text

    empty_b = client.put(
        f"/v1/agent-instances/{inst_b}/config/draft",
        json={"enabled_tool_codes": ["get_current_datetime", "search_kb"]},
    )
    assert empty_b.status_code == 200, empty_b.text
    published_b = client.post(f"/v1/agent-instances/{inst_b}/config/publish")
    assert published_b.status_code == 200, published_b.text
    opened_b = client.post(f"/v1/agent-instances/{inst_b}/open")
    assert opened_b.status_code == 200, opened_b.text

    llm.responses = [
        ai_tool("search_kb", {"query": "KEEP_DOC_MARKER SKIP_DOC_MARKER OTHER_INSTANCE_MARKER", "k": 8}),
        ai_text("done-a"),
        ai_tool("search_kb", {"query": "KEEP_DOC_MARKER SKIP_DOC_MARKER OTHER_INSTANCE_MARKER", "k": 8}),
        ai_text("done-b"),
    ]
    response_a = client.post(
        f"/v1/threads/{opened_a.json()['thread_id']}/messages",
        json={"content": "search a"},
    )
    assert response_a.status_code == 200, response_a.text
    payload_a = "\n".join(str(getattr(item, "content", item)) for item in llm.calls[1])
    assert "KEEP_DOC_MARKER" in payload_a
    assert "keep.md" in payload_a
    assert "skip.md" not in payload_a
    assert "SKIP_DOC_MARKER" not in payload_a
    assert "OTHER_INSTANCE_MARKER" not in payload_a

    response_b = client.post(
        f"/v1/threads/{opened_b.json()['thread_id']}/messages",
        json={"content": "search b"},
    )
    assert response_b.status_code == 200, response_b.text
    payload_b = "\n".join(str(getattr(item, "content", item)) for item in llm.calls[3])
    assert "NO_HITS" in payload_b
    assert "KEEP_DOC_MARKER" not in payload_b
    assert "OTHER_INSTANCE_MARKER" not in payload_b
    assert "keep.md" not in payload_b



def test_debug_open_reuses_debug_thread_and_does_not_pollute_official(runtime):
    client = make_client(runtime)
    register_and_login(client, "debug-open-owner", "password123")
    custom = _create(client, "custom", "debug-open-agent")
    instance_id = custom["agent_instance_id"]
    official = client.post(f"/v1/agent-instances/{instance_id}/open")
    assert official.status_code == 200, official.text
    official_id = official.json()["thread_id"]
    card_before = client.get("/v1/agent-instances").json()["items"][0]["updated_at"]

    debug = client.post(f"/v1/agent-instances/{instance_id}/debug-open")
    assert debug.status_code == 200, debug.text
    assert debug.json()["thread_kind"] == "debug"
    debug_id = debug.json()["thread_id"]
    assert debug_id != official_id
    debug_again = client.post(f"/v1/agent-instances/{instance_id}/debug-open")
    assert debug_again.status_code == 200, debug_again.text
    assert debug_again.json()["thread_id"] == debug_id
    official_again = client.post(f"/v1/agent-instances/{instance_id}/open")
    assert official_again.status_code == 200, official_again.text
    assert official_again.json()["thread_id"] == official_id
    assert runtime.business_repo.get_app_thread(official_id).thread_kind == "official"
    assert runtime.business_repo.get_app_thread(debug_id).thread_kind == "debug"
    card_after = client.get("/v1/agent-instances").json()["items"][0]["updated_at"]
    assert card_after == card_before


def test_debug_open_before_official_does_not_return_debug(runtime):
    client = make_client(runtime)
    register_and_login(client, "debug-first-owner", "password123")
    custom = _create(client, "custom", "debug-first-agent")
    instance_id = custom["agent_instance_id"]
    debug = client.post(f"/v1/agent-instances/{instance_id}/debug-open")
    assert debug.status_code == 200, debug.text
    official = client.post(f"/v1/agent-instances/{instance_id}/open")
    assert official.status_code == 200, official.text
    assert official.json()["thread_id"] != debug.json()["thread_id"]
    assert runtime.business_repo.get_app_thread(official.json()["thread_id"]).thread_kind == "official"
    assert runtime.business_repo.get_app_thread(debug.json()["thread_id"]).thread_kind == "debug"


def test_debug_open_messages_use_real_sse(runtime, llm):
    client = make_client(runtime)
    register_and_login(client, "debug-sse-owner", "password123")
    custom = _create(client, "custom", "debug-sse-agent")
    instance_id = custom["agent_instance_id"]
    debug = client.post(f"/v1/agent-instances/{instance_id}/debug-open")
    assert debug.status_code == 200, debug.text
    llm.responses = [ai_text("debug-sse-ok")]
    response = post_chat(
        client,
        f"/v1/threads/{debug.json()['thread_id']}/messages",
        json={"content": "debug hi"},
    )
    assert response.status_code == 200, response.text
    assert "text/event-stream" in (response.headers.get("content-type") or "")
    names = [item["event"] for item in response.events]
    assert names[-1] == "thread"
    assert "error" not in names
    assert response.json()["messages"][-1]["content"] == "debug-sse-ok"
