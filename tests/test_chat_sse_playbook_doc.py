from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "modify" / "Vue聊天页流式输出与Dify节点进度实施套餐.md"


class TestChatSsePlaybookDoc(unittest.TestCase):
    def test_doc_exists(self):
        self.assertTrue(DOC.is_file(), f"missing {DOC}")

    def test_required_locked_decisions(self):
        text = DOC.read_text(encoding="utf-8")
        required = [
            "Vue 聊天页流式输出与 Dify 节点进度实施套餐",
            "流式输出",
            "text/event-stream",
            "progress",
            "token",
            "thread",
            "error",
            "astream",
            'version="v2"',
            "get_stream_writer",
            "response_mode=streaming",
            "workflow_nodes",
            "dify_node",
            "discover_douyin_leads",
            "AbortController",
            "applyThread",
            "CHAT_TIMEOUT_MS",
            "sse-starlette",
            "中文 Git commit",
            "新增聊天流式输出与Dify节点进度实施套餐",
            "FakeDifyClient",
            "EventSourceResponse",
            "phase=running",
            "正在回复",
        ]
        missing = [item for item in required if item not in text]
        self.assertEqual(missing, [], f"missing snippets: {missing}")

    def test_forbids_out_of_scope_work(self):
        text = DOC.read_text(encoding="utf-8")
        required = [
            "不要改 Streamlit",
            "不要修改同学 C 的 Dify",
            "不要新增聊天消息表",
            "不要转发 text_chunk",
            "不要 EventSource",
            "Jobs / morning brief 仍走 ainvoke",
            ".local/",
            "DouyinView.vue",
            "Streamlit 废弃",
            "不要改那篇旧文档",
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