"""Kimi Agent Orchestrator 集成（DESIGN Step 2 P2 重构后）。

thin adapter——9 步主流程全部继承自 swebench_exp_lite.runtime.base_runner.BaseAgentRunner，
子类只实现必要的差异化点（_get_agent / _start_message）。

完整设计：[docs/DESIGN-base-agent-runner-step2-20260805.md](../../../../docs/DESIGN-base-agent-runner-step2-20260805.md)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .agent import KimiAgent
from .config import KimiConfig
from .environment import RunResult
from swebench_exp_lite.runtime.base_runner import BaseAgentRunner


class KimiAgentRunner(BaseAgentRunner[RunResult]):
    """Kimi Agent Orchestrator 适配器（DESIGN Step 2 P2 重构后）。

    行为完全保留原 KimiAgentRunner——9 步主流程从基类继承，只实现差异化 hook。
    """

    name = "kimi-agent"

    def __init__(
        self,
        model: Optional[str] = None,
        timeout: int = 600,
        max_retries: int = 0,
    ):
        super().__init__(
            model=model or "kimi-code/kimi-for-coding",
            timeout=timeout,
            max_retries=max_retries,
        )

    # C10：_get_agent 走 BaseAgentRunner 模板（config_class/agent_class 声明式）
    config_class = KimiConfig
    agent_class = KimiAgent

    def _start_message(self) -> str:
        return "启动 Kimi Agent"

    def _make_error_result(self, instance_id: str, error: str) -> RunResult:
        """kimi 用 RunResult（向后兼容 orchestrator/s4_adapter.py 的类型检查）。"""
        return RunResult(success=False, instance_id=instance_id, error=error)

