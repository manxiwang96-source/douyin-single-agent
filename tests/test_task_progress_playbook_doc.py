from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "modify" / "Vue聊天页本轮任务流程实施套餐.md"


class TestTaskProgressPlaybookDoc(unittest.TestCase):
    def test_doc_exists(self):
        self.assertTrue(DOC.is_file(), f"missing {DOC}")

    def test_required_locked_decisions(self):
        text = DOC.read_text(encoding="utf-8")
        required = [
            "Vue 聊天页本轮任务流程实施套餐",
            "docs/modify/抖音运营智能体修改设计方案（1）.md",
            "正在回复",
            "正在运行「抖音线索发现与触达」",
            "正在思考",
            "正在整理回复",
            "等待审核「生成图片」",
            "已跳过「生成图片」",
            "User skipped media generation.",
            "round_id",
            "waiting_review",
            "serialize_thread",
            "GET /v1/threads/{thread_id}",
            "applyThread",
            "ChatSidebar",
            "400px",
            "860px",
            "discover_douyin_leads",
            "generate_image",
            "generate_video",
            "search_kb",
            "client_message_id",
            "tests/test_serialize_progress.py",
            "frontend/tests/chat-view.test.ts",
            "memory-bank/architecture.md",
            "中文 Git commit",
            "新增聊天右侧栏本轮任务流程",
        ]
        missing = [item for item in required if item not in text]
        self.assertEqual(missing, [], f"missing snippets: {missing}")

    def test_forbids_out_of_scope_work(self):
        text = DOC.read_text(encoding="utf-8")
        required = [
            "不要上 SSE",
            "不要改 Streamlit",
            "不要修改同学 C 的 Dify",
            "禁止 ALTER",
            "不要新增聊天消息表",
            "主气泡 pending 文案「正在回复」",
            "Skip 算本轮完成",
            "Approve 只追加/更新步骤",
            "不要按整页重算",
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