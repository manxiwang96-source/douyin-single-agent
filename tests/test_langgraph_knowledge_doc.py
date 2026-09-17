from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "knowledge" / "LangGraph智能体创建知识地图：多智能体协作与任务编排.md"


class TestLangGraphKnowledgeDoc(unittest.TestCase):
    def test_doc_exists(self):
        self.assertTrue(DOC.is_file(), f"missing {DOC}")

    def test_required_knowledge_areas_and_learning_steps(self):
        text = DOC.read_text(encoding="utf-8")
        required = [
            "StateGraph",
            "任务编排模式",
            "多智能体协作",
            "Supervisor",
            "Orchestrator-Worker",
            "Human-in-the-loop",
            "上下文、短期记忆与长期记忆",
            "生产化、观测与评估",
            "第 1 步",
            "第 6 步",
            "练习",
            "验收",
        ]
        missing = [item for item in required if item not in text]
        self.assertEqual(missing, [], f"missing snippets: {missing}")

    def test_learning_resources_use_specific_langgraph_urls(self):
        text = DOC.read_text(encoding="utf-8")
        urls = set(re.findall(r"https://langgraph\.com\.cn/[^)\s]+", text))
        self.assertGreaterEqual(len(urls), 15)
        self.assertTrue(
            all(url.startswith("https://langgraph.com.cn/") for url in urls)
        )
        required_urls = {
            "https://langgraph.com.cn/tutorials/workflows/index.html",
            "https://langgraph.com.cn/concepts/multi_agent.1.html",
            "https://langgraph.com.cn/how-tos/multi_agent/index.html",
            "https://langgraph.com.cn/concepts/subgraphs.1.html",
            "https://langgraph.com.cn/concepts/persistence.1.html",
            "https://langgraph.com.cn/agents/human-in-the-loop/index.html",
            "https://langgraph.com.cn/agents/evals/index.html",
            "https://langgraph.com.cn/agents/deployment/index.html",
        }
        self.assertEqual(required_urls - urls, set())


if __name__ == "__main__":
    unittest.main()
