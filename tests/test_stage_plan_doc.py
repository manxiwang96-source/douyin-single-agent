from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "stage"
README = STAGE / "README.md"
PLAYBOOK = STAGE / "抖音运营智能体分阶段实施套餐.md"
DESIGN = ROOT / "docs" / "modify" / "抖音运营智能体修改设计方案（1）.md"


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


def test_stage_entry_files_exist():
    assert README.is_file()
    assert PLAYBOOK.is_file()
    assert DESIGN.is_file()
    assert not (ROOT / "stage1").exists()


def test_readme_tells_new_chat_to_do_one_phase():
    text = _read(README)
    required = [
        "stage/抖音运营智能体分阶段实施套餐.md",
        "docs/modify/抖音运营智能体修改设计方案（1）.md",
        "只实现那一个阶段",
        "不要重建 stage1/",
        "阶段 0",
        "阶段 7",
        "discover_douyin_leads",
        "no_send=false",
        "Bearer",
    ]
    missing = [item for item in required if item not in text]
    assert missing == [], missing


def test_playbook_locks_phased_execution():
    text = _read(PLAYBOOK)
    required = [
        "抖音运营智能体分阶段实施套餐",
        "一次只做当前阶段",
        "阶段 0 — 文档与配置",
        "阶段 1 — 业务表与仓库",
        "阶段 2 — 登录与广场 API",
        "阶段 3 — 对话隔离",
        "阶段 4 — Dify 工具（mock）",
        "阶段 5 — 任务取消",
        "阶段 6 — Streamlit 过渡客户端",
        "阶段 7 — 真实 Dify 交付",
        "app_sessions",
        "pbkdf2_sha256",
        "DIFY_LIVE_ENABLED",
        "RUN_LIVE_DOUYIN=1",
        "discover_douyin_leads",
        "/v1/workflows/run",
        "no_send=false",
        "allowed_workflow_codes",
        "knowledge/douyin_ops_demo",
        "会真实发送",
        "login_name",
        "scheduler_enabled",
        "POST /v1/agent-instances/{id}/open",
        "list_jobs",
        "cancel_job",
        "create_react_agent",
        "difyctl",
        "reply_douyin_comment",
        "send_douyin_dm",
        "(user_id, agent_instance_id, \"profile\"",
        "(user_id, agent_instance_id, \"kb\")",
        "Authorization: Bearer",
        "docs/modify/抖音运营智能体修改设计方案（1）.md",
        "不要把已删除的 `stage1/` 当源",
    ]
    missing = [item for item in required if item not in text]
    assert missing == [], missing


def test_playbook_forbids_worker_code_outside_phase_and_secret_leak():
    text = _read(PLAYBOOK) + "\n" + _read(README)
    required = [
        "不要改 C 的工作流",
        "密钥只写本地 `.env`",
        "不写 `agent_memory`",
        "test_assistant_summary_doc.py",
    ]
    missing = [item for item in required if item not in text]
    assert missing == [], missing
    forbidden = ["205102", "UNhb48n7W9uWmpgx", "app-"]
    # "app-..." appears in design as key prefix instruction; playbook should not include live key prefixes with values.
    found = [item for item in forbidden[:2] if item in text]
    assert found == [], found


def test_memory_bank_points_at_stage_playbook():
    plan = _read(ROOT / "memory-bank" / "implementation-plan.md")
    arch = _read(ROOT / "memory-bank" / "architecture.md")
    assert "stage/README.md" in plan
    assert "stage/抖音运营智能体分阶段实施套餐.md" in plan
    assert "stage1/" in plan
    assert "stage/README.md" in arch