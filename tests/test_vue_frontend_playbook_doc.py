from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "modify" / "抖音运营智能体Vue前端实施套餐.md"


class TestVueFrontendPlaybookDoc(unittest.TestCase):
    def test_doc_exists(self):
        self.assertTrue(DOC.is_file(), f"missing {DOC}")

    def test_required_locked_decisions(self):
        text = DOC.read_text(encoding="utf-8")
        required = [
            "抖音运营智能体 Vue 前端实施套餐",
            "Vue 3",
            "Vite",
            "Vue Router",
            "Pinia",
            "Axios",
            "douyin_ops",
            "抖音运营助手",
            "capability_description",
            "SYSTEM_PROMPT",
            "单智能体模式",
            "多智能体模式",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "frontend/",
            "CreateAgentModal",
            "不要改 C 的工作流",
            "Element Plus",
            "Naive UI",
            "Ant Design Vue",
            "title already in use",
            "DIFY_LIVE_ENABLED",
            "一次完整交付",
            "不要停在 CORS",
            "不是要开 6 个对话",
            "同一弹窗",
            "不刷新整页",
            "不改路由",
            "agent-",
            "POST /v1/agent-instances",
            "点进对话不算最近编辑",
            "抖音线索发现与触达",
            "discover_douyin_leads",
            "不要重做",
            "Vitest",
            "阶段 0",
            "阶段 5",
            "仅参考框架",
            "未发布",
            "AI生成头像",
            "对话式智能体",
            "docs/modify/抖音运营智能体修改设计方案（1）.md",
        ]
        missing = [item for item in required if item not in text]
        self.assertEqual(missing, [], f"missing snippets: {missing}")

    def test_forbids_ui_libraries_and_worker_redo(self):
        text = DOC.read_text(encoding="utf-8")
        required = [
            "不要引入 Element Plus / Naive UI / Ant Design Vue",
            "不改工人图",
            "不改 Streamlit",
            "不要重做 Dify",
            "轻量自定义组件",
        ]
        missing = [item for item in required if item not in text]
        self.assertEqual(missing, [], f"missing snippets: {missing}")

    def test_secrets_are_not_committed(self):
        text = DOC.read_text(encoding="utf-8")
        forbidden = ["205102", "UNhb48n7W9uWmpgx"]
        found = [item for item in forbidden if item in text]
        self.assertEqual(found, [], f"secrets leaked: {found}")


if __name__ == "__main__":
    unittest.main()
