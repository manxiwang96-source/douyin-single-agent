from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from langchain_core.messages import HumanMessage, ToolMessage

from app.knowledge import (
    KnowledgeUploadError,
    MAX_KNOWLEDGE_UPLOAD_BYTES,
    decode_knowledge_upload,
    index_knowledge_dir,
    kb_namespace,
    search_kb,
    selected_document_filenames,
    split_markdown,
    validate_knowledge_upload_filename,
)
from tests.fakes import ai_text, ai_tool
from tests.graph_helpers import graph_config
from tests.http_helpers import make_client, register_and_login

USER_A = "11111111-1111-4111-8111-111111111111"
INST_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
USER_B = "22222222-2222-4222-8222-222222222222"
INST_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def _put_kb(runtime, user_id, instance_id, chunk_id: str, source: str, text: str) -> None:
    runtime.memory_store.put(
        kb_namespace(user_id, instance_id),
        chunk_id,
        {"text": text, "source": source, "chunk_id": chunk_id},
    )


def _tool_content(result) -> str:
    messages = [item for item in result["messages"] if isinstance(item, ToolMessage)]
    assert messages, "expected search_kb tool message"
    return str(messages[-1].content)


def test_split_markdown_uses_headings():
    text = "# Title\n\n## One\nhello\n\n## Two\nworld"
    chunks = split_markdown(text, "demo.md")
    sources = [item["section"] for item in chunks]
    assert any("One" in item or item == "##" for item in sources)
    assert any(item["text"] for item in chunks)


def test_search_kb_hits_related_chunk(runtime):
    hits = search_kb(runtime.store, "封面建议", k=4)
    assert hits, "expected at least one semantic hit"
    joined = "\n".join(f"{item['source']} {item['text']}" for item in hits)
    assert "visual-specs.md" in joined
    assert "封面" in joined


def test_search_kb_hits_compliance(runtime):
    hits = search_kb(runtime.store, "禁止声称已经登录小红书", k=4)
    assert hits
    joined = "\n".join(f"{item['source']} {item['text']}" for item in hits)
    assert "compliance.md" in joined


def test_index_knowledge_dir_indexes_demo_files(runtime, knowledge_dir):
    assert index_knowledge_dir(runtime.store, knowledge_dir) >= 4


def test_selected_document_filenames_keeps_checked_names_only():
    keep_id = uuid4()
    skip_id = uuid4()
    docs = [
        SimpleNamespace(document_id=keep_id, filename="keep.md"),
        SimpleNamespace(document_id=skip_id, filename="skip.md"),
    ]
    assert selected_document_filenames(docs, [keep_id]) == ["keep.md"]
    assert selected_document_filenames(docs, []) == []
    assert selected_document_filenames(docs, None) == []


def test_search_kb_does_not_return_other_instance_documents(runtime):
    _put_kb(runtime, USER_A, INST_A, "a1", "a.md", "ONLY_INSTANCE_A_KB_MARKER")
    _put_kb(runtime, USER_B, INST_B, "b1", "b.md", "ONLY_INSTANCE_B_KB_MARKER")
    hits = search_kb(
        runtime.memory_store,
        "ONLY_INSTANCE_A_KB_MARKER",
        k=4,
        namespace=kb_namespace(USER_A, INST_A),
    )
    joined = "\n".join(f"{item['source']} {item['text']}" for item in hits)
    assert "ONLY_INSTANCE_A_KB_MARKER" in joined
    assert "ONLY_INSTANCE_B_KB_MARKER" not in joined


def test_search_kb_filters_unselected_sources(runtime):
    _put_kb(runtime, USER_A, INST_A, "keep", "keep.md", "KEEP_DOC_MARKER selected keep file")
    _put_kb(runtime, USER_A, INST_A, "skip", "skip.md", "SKIP_DOC_MARKER unselected skip file")
    hits = search_kb(
        runtime.memory_store,
        "KEEP_DOC_MARKER SKIP_DOC_MARKER",
        k=8,
        namespace=kb_namespace(USER_A, INST_A),
        allowed_sources=["keep.md"],
    )
    joined = "\n".join(f"{item['source']} {item['text']}" for item in hits)
    assert "keep.md" in joined
    assert "KEEP_DOC_MARKER" in joined
    assert "skip.md" not in joined
    assert "SKIP_DOC_MARKER" not in joined


def test_search_kb_returns_empty_when_no_sources_selected(runtime):
    _put_kb(runtime, USER_A, INST_A, "keep", "keep.md", "KEEP_DOC_MARKER selected keep file")
    assert search_kb(
        runtime.memory_store,
        "KEEP_DOC_MARKER",
        k=4,
        namespace=kb_namespace(USER_A, INST_A),
        allowed_sources=[],
    ) == []


def test_search_kb_tool_does_not_fall_back_to_global_store(runtime):
    tool = next(item for item in runtime.tools if getattr(item, "name", "") == "search_kb")
    result = tool.invoke({"query": "封面建议", "k": 4})
    assert result == "NO_HITS"
    assert "visual-specs.md" not in result


def test_search_kb_tool_filters_instance_and_selected_sources(runtime, llm):
    _put_kb(runtime, USER_A, INST_A, "keep", "keep.md", "KEEP_DOC_MARKER selected keep file")
    _put_kb(runtime, USER_A, INST_A, "skip", "skip.md", "SKIP_DOC_MARKER unselected skip file")
    _put_kb(runtime, USER_B, INST_B, "other", "other.md", "OTHER_INSTANCE_MARKER other instance file")
    llm.responses = [
        ai_tool("search_kb", {"query": "KEEP_DOC_MARKER SKIP_DOC_MARKER OTHER_INSTANCE_MARKER", "k": 8}),
        ai_text("done"),
    ]
    result = runtime.graph.invoke(
        {"messages": [HumanMessage(content="search now")]},
        graph_config(
            "kb-filter-a",
            user_id=USER_A,
            agent_instance_id=INST_A,
            knowledge_sources=["keep.md"],
        ),
    )
    content = _tool_content(result)
    assert "KEEP_DOC_MARKER" in content
    assert "keep.md" in content
    assert "skip.md" not in content
    assert "SKIP_DOC_MARKER" not in content
    assert "OTHER_INSTANCE_MARKER" not in content


def test_search_kb_tool_returns_empty_when_no_sources_selected(runtime, llm):
    _put_kb(runtime, USER_A, INST_A, "keep", "keep.md", "KEEP_DOC_MARKER selected keep file")
    llm.responses = [
        ai_tool("search_kb", {"query": "KEEP_DOC_MARKER", "k": 4}),
        ai_text("done"),
    ]
    result = runtime.graph.invoke(
        {"messages": [HumanMessage(content="search now")]},
        graph_config(
            "kb-filter-empty",
            user_id=USER_A,
            agent_instance_id=INST_A,
            knowledge_sources=[],
        ),
    )
    content = _tool_content(result)
    assert content == "NO_HITS"
    assert "KEEP_DOC_MARKER" not in content
    assert "keep.md" not in content

def _create_agent(client, title: str):
    response = client.post(
        "/v1/agent-instances",
        json={"template_code": "custom", "title": title, "intro": title},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_validate_knowledge_upload_filename_and_decode():
    assert validate_knowledge_upload_filename(r"C:\\tmp\\notes.MD") == "notes.MD"
    assert validate_knowledge_upload_filename("rules.txt") == "rules.txt"
    with pytest.raises(KnowledgeUploadError):
        validate_knowledge_upload_filename("notes.pdf")
    with pytest.raises(KnowledgeUploadError):
        decode_knowledge_upload(b"")
    with pytest.raises(KnowledgeUploadError):
        decode_knowledge_upload(b"a" * (MAX_KNOWLEDGE_UPLOAD_BYTES + 1))
    with pytest.raises(KnowledgeUploadError):
        decode_knowledge_upload(b"\xff\xfe")


def test_json_knowledge_metadata_post_still_works(runtime):
    client = make_client(runtime)
    register_and_login(client, "knowledge-json-owner", "password123")
    instance = _create_agent(client, "json-knowledge")
    created = client.post(
        f"/v1/agent-instances/{instance['agent_instance_id']}/knowledge",
        json={"title": "internal-rules", "filename": "rules.md", "storage_uri": "knowledge/rules.md"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["source"] == "user_upload"
    assert body["filename"] == "rules.md"
    listed = client.get(f"/v1/agent-instances/{instance['agent_instance_id']}/knowledge").json()
    assert body["document_id"] not in listed["selected_document_ids"]


def test_knowledge_upload_indexes_and_selects_draft(runtime):
    client = make_client(runtime)
    register_and_login(client, "knowledge-upload-owner", "password123")
    instance = _create_agent(client, "upload-knowledge")
    instance_id = instance["agent_instance_id"]
    marker = "W22_UPLOAD_MD_MARKER unique knowledge upload text"
    created = client.post(
        f"/v1/agent-instances/{instance_id}/knowledge",
        files={"file": ("notes.md", f"## Upload\n{marker}\n".encode("utf-8"), "text/markdown")},
        data={"title": "upload-notes"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["title"] == "upload-notes"
    assert body["filename"] == "notes.md"
    assert body["source"] == "user_upload"
    assert body["status"] == "ready"
    listed = client.get(f"/v1/agent-instances/{instance_id}/knowledge")
    assert listed.status_code == 200
    payload = listed.json()
    assert body["document_id"] in payload["selected_document_ids"]
    version_id = UUID(payload["config_version_id"])
    assert (version_id, UUID(body["document_id"])) in runtime.skill_repository.config_knowledge_documents
    user = runtime.business_repo.get_user_by_login_name("knowledge-upload-owner")
    hits = search_kb(
        runtime.memory_store,
        marker,
        k=4,
        namespace=kb_namespace(user.user_id, instance_id),
    )
    joined = "\n".join(f"{item['source']} {item['text']}" for item in hits)
    assert "notes.md" in joined
    assert marker in joined
    saved = runtime.media_root / body["storage_uri"]
    assert saved.is_file()
    assert marker.encode("utf-8") in saved.read_bytes()


def test_knowledge_upload_accepts_txt_and_rejects_invalid(runtime):
    client = make_client(runtime)
    register_and_login(client, "knowledge-upload-types", "password123")
    instance = _create_agent(client, "upload-types")
    instance_id = instance["agent_instance_id"]
    txt = client.post(
        f"/v1/agent-instances/{instance_id}/knowledge",
        files={"file": ("memo.txt", b"W22_UPLOAD_TXT_MARKER plain text memo\n", "text/plain")},
    )
    assert txt.status_code == 201, txt.text
    assert txt.json()["filename"] == "memo.txt"
    assert txt.json()["status"] == "ready"
    assert client.post(
        f"/v1/agent-instances/{instance_id}/knowledge",
        files={"file": ("notes.pdf", b"%PDF-1.4 fake", "application/pdf")},
    ).status_code == 400
    too_large = client.post(
        f"/v1/agent-instances/{instance_id}/knowledge",
        files={"file": ("big.md", b"a" * (MAX_KNOWLEDGE_UPLOAD_BYTES + 1), "text/markdown")},
    )
    assert too_large.status_code == 400
    empty = client.post(
        f"/v1/agent-instances/{instance_id}/knowledge",
        files={"file": ("empty.md", b"   \n", "text/markdown")},
    )
    assert empty.status_code == 400


def test_knowledge_upload_is_404_for_other_user(runtime):
    owner = make_client(runtime)
    register_and_login(owner, "knowledge-upload-owner-a", "password123")
    instance = _create_agent(owner, "owned-upload")
    other = make_client(runtime)
    register_and_login(other, "knowledge-upload-owner-b", "password123")
    assert other.get(f"/v1/agent-instances/{instance['agent_instance_id']}/knowledge").status_code == 404
    uploaded = other.post(
        f"/v1/agent-instances/{instance['agent_instance_id']}/knowledge",
        files={"file": ("notes.md", b"## Other\nshould not upload\n", "text/markdown")},
    )
    assert uploaded.status_code == 404
