from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "modify" / "抖音运营智能体Dify真实状态回传实施套餐.md"


class TestDifyStatusReturnPlaybookDoc(unittest.TestCase):
    def test_doc_exists(self):
        self.assertTrue(DOC.is_file(), f"missing {DOC}")

    def test_required_locked_decisions(self):
        text = DOC.read_text(encoding="utf-8")
        required = [
            "抖音运营智能体 Dify 真实状态回传实施套餐",
            "docs/modify/抖音运营智能体修改设计方案（1）.md",
            "douyin-lead-discovery.yml",
            "job_status",
            "job_response",
            "dify_workflow_status",
            "真实任务状态",
            "workflow_ok",
            "delivery_ok",
            "job status unavailable",
            "workflow_status=succeeded",
            "unverified",
            "message_details",
            "delivery",
            "written",
            "list_message",
            "list_comment",
            "不要修改同学 C 的 Dify DSL",
            "不改 Vue、Streamlit",
            "不重做工人阶段 0–7",
            "tests/test_dify_client.py",
            "tests/test_discover_leads.py",
            "memory-bank/architecture.md",
            "中文 Git commit",
            "不要把密钥",
        ]
        missing = [item for item in required if item not in text]
        self.assertEqual(missing, [], f"missing snippets: {missing}")

    def test_forbids_false_success_paths(self):
        text = DOC.read_text(encoding="utf-8")
        required = [
            "状态缺失不能猜成成功",
            "错误响应不得伪装成一条成功记录",
            "不再默认 `sent`",
            "`written.dms` / `written.comments` 只表示本地写入数量",
            "外层 Dify status=succeeded + job_status=failed",
            "`job_status` 缺失",
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
