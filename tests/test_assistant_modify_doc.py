from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "modify" / "个人超级助理改造方案.md"


class TestAssistantModifyDoc(unittest.TestCase):
    def test_doc_exists(self):
        self.assertTrue(DOC.is_file(), f"missing {DOC}")

    def test_required_locked_decisions(self):
        text = DOC.read_text(encoding="utf-8")
        required = [
            "个人超级助理改造方案",
            "chatbot",
            "tools",
            "不新增节点",
            "SYSTEM_PROMPT",
            "search_kb",
            "【标题】【正文】【标签】",
            "PostgresSaver",
            "PostgresStore",
            "InMemoryStore",
            "FastMCP",
            "MultiServerMCPClient",
            "send_email",
            "run_morning_brief",
            "run_hydrate",
            "POST /v1/assistant/jobs/run",
            "RUN_LIVE_ASSISTANT=1",
            "smtp.163.com",
            "Open-Meteo",
            "APScheduler",
            "ainvoke",
            "create_react_agent",
            "只参考",
            "不整段复制",
            "广州",
            "08:00",
            "https://langgraph.com.cn/agents/mcp/index.html",
            "https://langgraph.com.cn/how-tos/persistence.1.html",
            "https://langgraph.com.cn/concepts/memory.1.html",
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
