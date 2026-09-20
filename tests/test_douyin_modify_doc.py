from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "modify" / "抖音运营智能体修改设计方案（1）.md"


class TestDouyinModifyDoc(unittest.TestCase):
    def test_doc_exists(self):
        self.assertTrue(DOC.is_file(), f"missing {DOC}")

    def test_required_locked_decisions(self):
        text = DOC.read_text(encoding="utf-8")
        required = [
            "抖音运营智能体修改设计方案（1）",
            "抖音运营智能体",
            "chatbot",
            "tools",
            "create_react_agent",
            "difyctl",
            "reply_douyin_comment",
            "send_douyin_dm",
            "DIFY_COMMENT_APP_ID",
            "DIFY_DM_APP_ID",
            "user_id",
            "app_users",
            "app_threads",
            "douyin_accounts",
            "job_definitions",
            "job_runs",
            "workflow_runs",
            "engage_videos",
            "engage_comments",
            "engage_dms",
            "media_assets",
            "proposed",
            "ready_to_send",
            "approved_reply",
            "cancelled",
            "cancel_job",
            "list_jobs",
            "require_approval",
            "interrupt()",
            "review_media",
            "PostgresSaver",
            "PostgresStore",
            "--no-send",
            "auth_expired",
            "只参考",
            "不整段复制",
            "方案 B",
            "local_session",
            "手动取消",
            "对话取消",
            "https://langgraph.com.cn/agents/tools.1.html",
            "https://langgraph.com.cn/agents/context/index.html",
            "https://langgraph.com.cn/concepts/memory.1.html",
            "https://langgraph.com.cn/concepts/persistence.1.html",
            "https://langgraph.com.cn/how-tos/persistence.1.html",
        ]
        missing = [item for item in required if item not in text]
        self.assertEqual(missing, [], f"missing snippets: {missing}")

    def test_does_not_use_mcp_or_extra_node_for_dify(self):
        text = DOC.read_text(encoding="utf-8")
        required = [
            "为什么不是本仓库再包一个 MCP",
            "为什么不是图节点",
            "为什么不加节点",
            "dify_comment",
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