"""Qwen Agent 主循环（DESIGN Step 3 P3 重构后）。

thin agent——7 步主流程全部继承自 swebench_exp_lite.runtime.base_agent.BaseAgent。
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from .config import QwenConfig
from .environment import QwenEnvironment, QwenResult
from .prompt import QwenPromptBuilder
from swebench_exp_lite.runtime.base_agent import BaseAgent


class QwenAgent(BaseAgent[QwenResult]):
    """Qwen Agent 主类（DESIGN Step 3 P3 重构后）。

    行为完全保留原 QwenAgent。
    """

    name = "qwen-agent"
    result_class = QwenResult

    def __init__(
        self,
        config: Optional[QwenConfig] = None,
        prompt_builder: Optional[QwenPromptBuilder] = None,
    ):
        super().__init__(config=config or QwenConfig.from_env())
        self.environment = QwenEnvironment(self.config.workspace_root)
        self.prompt_builder = prompt_builder or QwenPromptBuilder()

    def _log_filename(self) -> str:
        return "qwen-stream.jsonl"

    def _invoke_cli(
        self,
        prompt: str,
        repo_dir: Path,
        log_path: Path,
        timeout: int,
        model: str,
    ) -> tuple[str, int]:
        """调 Qwen Code CLI（qwen -p "<prompt>" -m <model> --output-format stream-json）。"""
        return self._invoke_qwen(prompt, repo_dir, log_path, timeout, model)

    def _invoke_qwen(
        self,
        prompt: str,
        repo_dir: Path,
        log_path: Path,
        timeout: int,
        model: str,
    ) -> tuple[str, int]:
        """调 qwen CLI 子进程（独立函数保留向后兼容）。"""
        cmd = [
            str(self.config.qwen_bin_path),
            "-p", prompt,
            "-m", model,
            "--output-format", "stream-json",
            "--yolo",  # 非交互模式
        ]
        with open(log_path, "w", encoding="utf-8") as log_f:
            proc = subprocess.run(
                cmd, cwd=str(repo_dir), stdout=log_f,
                stderr=subprocess.STDOUT, timeout=timeout,
            )
        return "", proc.returncode

    def _make_error_result(self, instance_id: str, error: str, **kwargs) -> QwenResult:
        """qwen 用 QwenResult（向后兼容）。"""
        return QwenResult(
            success=False, instance_id=instance_id, error=error,
            elapsed_seconds=kwargs.get("elapsed_seconds", 0.0),
        )
