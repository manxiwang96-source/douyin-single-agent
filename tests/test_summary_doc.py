from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "summary" / "小红书运营助手对话机器人MVP总结与逻辑复盘（1）.md"


class TestSummaryDoc(unittest.TestCase):
    def test_doc_exists(self):
        self.assertTrue(DOC.is_file(), f"missing {DOC}")

    def test_required_recap_points(self):
        text = DOC.read_text(encoding="utf-8")
        required = [
            "小红书运营助手对话机器人 MVP 总结与逻辑复盘（1）",
            "chatbot",
            "tools",
            "search_kb",
            "generate_image",
            "generate_video",
            "interrupt()",
            "review_media",
            "InMemoryStore",
            "SqliteSaver",
            "pending_user",
            "RUN_LIVE_API=1",
            "480P",
            "quality=low",
            "【标题】【正文】【标签】",
        ]
        missing = [item for item in required if item not in text]
        self.assertEqual(missing, [], f"missing snippets: {missing}")


if __name__ == "__main__":
    unittest.main()
