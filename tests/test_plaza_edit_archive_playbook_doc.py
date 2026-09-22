from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "modify" / "抖音运营智能体广场编辑与归档实施套餐.md"


class TestPlazaEditArchivePlaybookDoc(unittest.TestCase):
    def test_doc_exists(self):
        self.assertTrue(DOC.is_file(), f"missing {DOC}")

    def test_required_locked_decisions(self):
        text = DOC.read_text(encoding="utf-8")
        required = [
            "抖音运营智能体广场编辑与归档实施套餐",
            "docs/modify/抖音运营智能体修改设计方案（1）.md",
            "广场编辑与归档",
            "PATCH /v1/agent-instances/{id}",
            "DELETE /v1/agent-instances/{id}",
            "archived",
            "CreateAgentModal",
            "AgentCard.vue",
            "PlazaView.vue",
            "frontend/src/api/agents.ts",
            "stopPropagation",
            "二次确认",
            "跳过模板",
            "只做广场",
            "对话页不改",
            "名称已被使用",
            "title already in use",
            "省略=保留",
            "不要改 C 的工作流",
            "不要重做",
            "不要把密钥",
            "中文 commit",
            "广场补齐智能体编辑与归档",
            "npm test",
            "npm run build",
            "Vitest",
            "工人阶段 0–7",
            "Vue 闭环",
            "删除 HTTP",
            "agent-",
            "FastAPI",
            "Streamlit",
        ]
        missing = [item for item in required if item not in text]
        self.assertEqual(missing, [], f"missing snippets: {missing}")

    def test_forbids_backend_ui_libraries_and_chat_edits(self):
        text = DOC.read_text(encoding="utf-8")
        required = [
            "不要改 FastAPI",
            "不要引入 Element Plus / Naive UI / Ant Design Vue",
            "Element Plus",
            "不要恢复归档",
            "不要物理删除",
            "对话页不改",
            "只做广场",
            "不要改 C 的工作流",
            "不要改 Streamlit",
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
