from pathlib import Path


def test_douyin_demo_knowledge_covers_phase_zero_boundaries():
    root = Path("knowledge/douyin_ops_demo")
    files = sorted(root.glob("*.md"))
    assert len(files) >= 1
    text = "\n".join(path.read_text(encoding="utf-8") for path in files)
    assert "会真实发送" in text
    assert "douyin-lead-discovery" in text
    assert "知识库不能代替真实扫描" in text
