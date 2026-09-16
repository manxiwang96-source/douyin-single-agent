from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "小红书运营机器人MVP方案.md"


class TestMvpPlanDoc(unittest.TestCase):
    def test_doc_exists(self):
        self.assertTrue(DOC.is_file(), f"missing {DOC}")

    def test_required_locked_decisions(self):
        text = DOC.read_text(encoding="utf-8")
        required = [
            "小红书运营机器人 MVP 方案",
            "RUN_LIVE_API=1",
            "InMemoryStore",
            "st.chat_input",
            "st.image",
            "st.video",
            "IMAGE_MODEL=gpt-image-2",
            "EMBEDDING_MODEL=BAAI/bge-m3",
            "MEDIA_OUTPUT_DIR=outputs",
            "review_media",
            "FastAPI",
            "480P",
        ]
        missing = [item for item in required if item not in text]
        self.assertEqual(missing, [], f"missing snippets: {missing}")


if __name__ == "__main__":
    unittest.main()
