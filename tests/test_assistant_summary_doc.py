from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "summary" / "个人超级助手总结与逻辑复盘（2）.md"


class TestAssistantSummaryDoc(unittest.TestCase):
    def test_doc_exists(self):
        self.assertTrue(DOC.is_file(), f"missing {DOC}")

    def test_title_and_required_recap_points(self):
        text = DOC.read_text(encoding="utf-8")
        required = [
            "个人超级助手总结与逻辑复盘（2）",
            "chatbot",
            "tools",
            "PostgresSaver",
            "PostgresStore",
            "FastMCP",
            "MultiServerMCPClient",
            "send_email",
            "run_morning_brief",
            "run_hydrate",
            "APScheduler",
            "ainvoke",
            "search_kb",
            "interrupt()",
            "RUN_LIVE_ASSISTANT=1",
            "mcp_servers",
            "mcp_client",
            "McpFactsProvider",
            "软调度",
            "硬调度",
            "assistant.jobs",
            "assistant.profile",
            "checkpoints",
            "checkpoint_blobs",
            "checkpoint_writes",
            "checkpoint_migrations",
            "store_migrations",
            "InMemorySaver",
            "InMemoryStore",
            "create_react_agent",
            "stdio",
            "Open-Meteo",
            "SMTP_TO",
            "今天星期几",
        ]
        missing = [item for item in required if item not in text]
        self.assertEqual(missing, [], f"missing snippets: {missing}")

    def test_maps_knowledge_to_specific_langgraph_urls(self):
        text = DOC.read_text(encoding="utf-8")
        urls = set(re.findall(r"https://langgraph\.com\.cn/[^)\s]+", text))
        self.assertGreaterEqual(len(urls), 15)
        self.assertTrue(all(url.startswith("https://langgraph.com.cn/") for url in urls))
        required_urls = {
            "https://langgraph.com.cn/agents/mcp/index.html",
            "https://langgraph.com.cn/reference/mcp/index.html",
            "https://langgraph.com.cn/concepts/memory.1.html",
            "https://langgraph.com.cn/concepts/persistence.1.html",
            "https://langgraph.com.cn/how-tos/persistence.1.html",
            "https://langgraph.com.cn/tutorials/get-started/2-add-tools/index.html",
            "https://langgraph.com.cn/tutorials/get-started/3-add-memory/index.html",
            "https://langgraph.com.cn/tutorials/get-started/4-human-in-the-loop/index.html",
        }
        self.assertEqual(required_urls - urls, set())

    def test_each_heading_starts_with_plain_language(self):
        lines = DOC.read_text(encoding="utf-8").splitlines()
        missing = []
        for idx, line in enumerate(lines):
            if line.startswith("##"):
                window = "\n".join(lines[idx:idx + 7])
                if "人话" not in window:
                    missing.append(line)
        self.assertEqual(missing, [], f"headings missing 人话: {missing}")

    def test_secrets_are_not_committed(self):
        text = DOC.read_text(encoding="utf-8")
        forbidden = ["205102", "UNhb48n7W9uWmpgx"]
        found = [item for item in forbidden if item in text]
        self.assertEqual(found, [], f"secrets leaked: {found}")


if __name__ == "__main__":
    unittest.main()