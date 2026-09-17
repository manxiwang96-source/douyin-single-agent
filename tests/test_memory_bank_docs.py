from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "memory-bank" / "design-document.md"
STACK = ROOT / "memory-bank" / "tech-stack.md"
PLAN = ROOT / "memory-bank" / "implementation-plan.md"


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


def test_memory_bank_docs_lock_assistant_upgrade():
    text = "\n".join([_read(DESIGN), _read(STACK), _read(PLAN)])
    required = [
        "个人超级助理",
        "chatbot",
        "tools",
        "PostgresSaver",
        "PostgresStore",
        "InMemorySaver",
        "FastMCP",
        "MultiServerMCPClient",
        "send_email",
        "run_morning_brief",
        "run_hydrate",
        "POST /v1/assistant/jobs/run",
        "RUN_LIVE_ASSISTANT=1",
        "create_react_agent",
        "只参考",
        "不整段复制",
        "smtp.163.com",
        "Open-Meteo",
        "APScheduler",
        "ainvoke",
    ]
    missing = [item for item in required if item not in text]
    assert missing == [], f"missing snippets: {missing}"


def test_memory_bank_docs_do_not_commit_secrets():
    text = "\n".join(
        [
            _read(DESIGN),
            _read(STACK),
            _read(PLAN),
            _read(ROOT / "memory-bank" / "architecture.md"),
        ]
    )
    forbidden = ["205102", "UNhb48n7W9uWmpgx"]
    found = [item for item in forbidden if item in text]
    assert found == [], f"secrets leaked: {found}"
