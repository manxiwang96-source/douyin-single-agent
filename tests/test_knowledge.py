from __future__ import annotations

from app.knowledge import index_knowledge_dir, search_kb, split_markdown


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
