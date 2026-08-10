"""Opencode Agent Orchestrator 集成。

thin adapter——9 步主流程全部继承自 swebench_exp_lite.runtime.base_runner.BaseAgentRunner。

参考 kimi_agent/runner.py 的极简模板（无 D10/D4 brand hook）：
opencode 不 auto-commit（PoC 2026-08-09 实测验证），也不创建 .mimocode/
类临时目录，所以不需要 mimo 那种 D10 防御 + D4 清理。

完整设计：[docs/DESIGN-base-agent-runner-step2-20260805.md](../../../../docs/DESIGN-base-agent-runner-step2-20260805.md)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .agent import OpencodeAgent
from .config import OpencodeConfig
from .environment import OpencodeResult
from swebench_exp_lite.runtime.base_runner import BaseAgentRunner


class OpencodeAgentRunner(BaseAgentRunner[OpencodeResult]):
    """Opencode Agent Orchestrator 适配器。

    9 步主流程从基类继承，只实现 3 个差异化 hook：
    - _get_agent 走声明式（config_class/agent_class）
    - _start_message 中文日志
    - _make_error_result 返回 OpencodeResult
    """

    name = "opencode-agent"

    def __init__(
        self,
        model: Optional[str] = None,
        timeout: int = 1800,
        max_retries: int = 0,
    ):
        super().__init__(
            model=model or "minimax-cn-coding-plan/MiniMax-M3",
            timeout=timeout,
            max_retries=max_retries,
        )

    # 声明式（基类模板方法会反射调用）
    config_class = OpencodeConfig
    agent_class = OpencodeAgent

    def _start_message(self) -> str:
        return "启动 Opencode Agent"

    def _make_error_result(self, instance_id: str, error: str) -> OpencodeResult:
        """opencode 用 OpencodeResult（向后兼容 orchestrator/s4_adapter.py 的类型检查）。"""
        return OpencodeResult(success=False, instance_id=instance_id, error=error)