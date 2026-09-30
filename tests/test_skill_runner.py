from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from app.skill_runner import RunnerLimits, SkillRunnerError, run_python_script


def write_script(root: Path, name: str, text: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    path.write_text(text, encoding="utf-8")
    return path


def test_python_runner_isolated_and_does_not_inherit_environment(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    script = write_script(workspace, "main.py", "import os\nprint(os.environ.get('SECRET_FROM_PARENT', 'missing'))\n")
    monkeypatch.setenv("SECRET_FROM_PARENT", "should-not-leak")
    result = run_python_script(script, workspace=workspace)
    assert result["exit_code"] == 0
    assert result["output"].strip() == "missing"
    assert "SECRET_FROM_PARENT" not in result["environment"]


def test_python_runner_blocks_node_shell_and_network_imports(tmp_path):
    workspace = tmp_path / "workspace"
    for name in ("main.js", "main.sh"):
        with pytest.raises(SkillRunnerError, match="only Python"):
            run_python_script(write_script(workspace, name, "echo unsafe"), workspace=workspace)
    with pytest.raises(SkillRunnerError, match="blocked module"):
        run_python_script(write_script(workspace, "net.py", "import socket\n"), workspace=workspace)
    with pytest.raises(SkillRunnerError, match="network-enabled"):
        run_python_script(write_script(workspace, "safe.py", "print('ok')\n"), workspace=workspace, network_enabled=True)


def test_python_runner_blocks_path_escape_and_symlink(tmp_path):
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside.py"
    outside.write_text("print('outside')", encoding="utf-8")
    with pytest.raises(SkillRunnerError, match="isolated workspace"):
        run_python_script(outside, workspace=workspace)
    with pytest.raises(SkillRunnerError, match="isolated workspace"):
        run_python_script(workspace / ".." / "outside.py", workspace=workspace)
    link = workspace / "link.py"
    try:
        workspace.mkdir(parents=True, exist_ok=True)
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("当前 Windows 进程没有创建软链接权限")
    with pytest.raises(SkillRunnerError, match="isolated workspace"):
        run_python_script(link, workspace=workspace)


def test_python_runner_timeout_and_output_limits(tmp_path):
    workspace = tmp_path / "workspace"
    slow = write_script(workspace, "slow.py", "while True: pass\n")
    with pytest.raises(SkillRunnerError, match="timed out"):
        run_python_script(slow, workspace=workspace, limits=RunnerLimits(timeout_seconds=0.1))
    large = write_script(workspace, "large.py", "print('x' * 1000)\n")
    with pytest.raises(SkillRunnerError, match="output exceeds"):
        run_python_script(large, workspace=workspace, limits=RunnerLimits(max_output_bytes=20))
    with pytest.raises(SkillRunnerError, match="input exceeds"):
        run_python_script(write_script(workspace, "input.py", "print('ok')\n"), workspace=workspace, input_text="x" * 20, limits=RunnerLimits(max_input_bytes=5))
