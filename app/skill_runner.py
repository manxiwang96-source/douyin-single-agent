from __future__ import annotations

import ast
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


class SkillRunnerError(RuntimeError):
    pass


@dataclass(frozen=True)
class RunnerLimits:
    timeout_seconds: float = 5.0
    max_output_bytes: int = 64 * 1024
    max_input_bytes: int = 64 * 1024


_BLOCKED_IMPORTS = {
    "socket", "subprocess", "requests", "httpx", "urllib", "ftplib", "paramiko",
    "ctypes", "multiprocessing", "shutil", "secrets",
}


def _validate_script(path: Path, workspace: Path) -> None:
    if path.suffix.lower() != ".py":
        raise SkillRunnerError("only Python scripts are supported; Node/Shell execution is blocked")
    root = workspace.resolve()
    resolved = path.resolve()
    if path.is_symlink() or root not in resolved.parents:
        raise SkillRunnerError("script must stay inside the isolated workspace")
    if not resolved.is_file():
        raise SkillRunnerError("script not found")
    try:
        tree = ast.parse(resolved.read_text(encoding="utf-8"), filename=str(resolved))
    except (OSError, SyntaxError) as exc:
        raise SkillRunnerError("script is not valid UTF-8 Python") from exc
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [item.name.split(".", 1)[0] for item in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [(node.module or "").split(".", 1)[0]]
        else:
            continue
        if any(name in _BLOCKED_IMPORTS for name in names):
            raise SkillRunnerError("script requests a blocked module")


def run_python_script(
    script_path: str | Path,
    *,
    workspace: str | Path,
    input_text: str = "",
    limits: RunnerLimits | None = None,
    network_enabled: bool = False,
) -> dict[str, object]:
    if network_enabled:
        raise SkillRunnerError("network-enabled Skill scripts are not permitted by the default runner")
    limits = limits or RunnerLimits()
    root = Path(workspace).resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = Path(script_path)
    _validate_script(path, root)
    if len(input_text.encode("utf-8")) > limits.max_input_bytes:
        raise SkillRunnerError("script input exceeds the configured limit")
    env = {"PYTHONIOENCODING": "utf-8", "PYTHONHASHSEED": "0"}
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-S", str(path.resolve())],
            cwd=root, input=input_text, text=True, capture_output=True,
            timeout=limits.timeout_seconds, env=env, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SkillRunnerError("script execution timed out") from exc
    output = (completed.stdout or "") + (completed.stderr or "")
    encoded = output.encode("utf-8", errors="replace")
    if len(encoded) > limits.max_output_bytes:
        raise SkillRunnerError("script output exceeds the configured limit")
    return {"exit_code": completed.returncode, "output": output, "network_enabled": False, "environment": sorted(env)}
