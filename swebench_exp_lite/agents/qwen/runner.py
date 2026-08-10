"""Qwen Agent Orchestrator 集成（DESIGN Step 2 P3 重构后）。

thin adapter——9 步主流程全部继承自 swebench_exp_lite.runtime.base_runner.BaseAgentRunner。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .agent import QwenAgent
from .config import QwenConfig
from .environment import QwenResult
from swebench_exp_lite.runtime.base_runner import BaseAgentRunner


class QwenAgentRunner(BaseAgentRunner[QwenResult]):
    """Qwen Agent Orchestrator 适配器（DESIGN Step 2 P3 重构后）。

    行为完全保留原 QwenAgentRunner。
    """

    name = "qwen-agent"

    def __init__(
        self,
        model: Optional[str] = None,
        timeout: int = 600,
        max_retries: int = 0,
    ):
        super().__init__(
            model=model or "qwen-code",  # qwen 默认走 CLI 默认 model
            timeout=timeout,
            max_retries=max_retries,
        )

    # C10：_get_agent 走 BaseAgentRunner 模板（config_class/agent_class 声明式）
    config_class = QwenConfig
    agent_class = QwenAgent

    def _start_message(self) -> str:
        return "启动 Qwen Code CLI"

    def _make_error_result(self, instance_id: str, error: str) -> QwenResult:
        """qwen 用 QwenResult（向后兼容）。"""
        return QwenResult(success=False, instance_id=instance_id, error=error)

