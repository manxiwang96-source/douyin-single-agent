from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "modify" / "抖音运营智能体删除HTTP实施套餐.md"


class TestDeleteHttpPlaybookDoc(unittest.TestCase):
    def test_doc_exists(self):
        self.assertTrue(DOC.is_file(), f"missing {DOC}")

    def test_required_locked_decisions(self):
        text = DOC.read_text(encoding="utf-8")
        required = [
            "抖音运营智能体删除 HTTP 实施套餐",
            "docs/modify/抖音运营智能体修改设计方案（1）.md",
            "DELETE /v1/agent-instances/{id}",
            "archive_agent_instance",
            "require_owned_instance",
            "_owned_instance",
            "GET /v1/agent-instances",
            "PATCH /v1/agent-instances/{id}",
            '"status": "archived"',
            "not authenticated",
            "agent instance not found",
            "tests/test_auth_plaza.py",
            "test_archived_title_can_be_reused",
            "memory-bank/architecture.md",
            "逻辑删除",
            "不要改仓库",
            "不要物理删除",
            "不要加 GET /{id}",
            "不要改前端",
            "Streamlit",
            "不要改 C 的工作流",
            "不要把密钥",
            "中文 commit",
            "补齐智能体实例逻辑删除 HTTP",
        ]
        missing = [item for item in required if item not in text]
        self.assertEqual(missing, [], f"missing snippets: {missing}")

    def test_forbids_repo_rewrite_and_frontend(self):
        text = DOC.read_text(encoding="utf-8")
        required = [
            "不用改仓库逻辑",
            "不要新增 purge 方法",
            "不要做成 `POST .../archive`",
            "二次 DELETE 也是 404",
            "本窗口不把删除、修改映射到前端",
            "禁止 ALTER",
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