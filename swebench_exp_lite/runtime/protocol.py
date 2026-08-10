"""Agent 应答协议（品牌中立）。

定义与 Agent 适配器无关的基础数据类型，供 infrastructure 层与
adapter 层共享，打破 swebench_exp_lite.runtime → kimi_agent 的反向依赖。

v0.1.5+ 增加：
- Precondition：品牌中立的前置能力（CLI 可用性检查等无需 ctx 的探测）；
  与 swebench-orchestrator/contracts/base.py:Precondition 并存但解耦。

用法：
    from swebench_exp_lite.runtime.protocol import AgentResult, Precondition

AgentResult 是 kimi_agent.environment.RunResult 的父类，
任何品牌中立的工具函数（如 acquire_run_lock）可用它替代
具体品牌的 RunResult。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional



@dataclass
class Precondition:
    """品牌中立的前置能力（无 ctx 参数；CLI 可用性、Python 包探测等）。

    与 swebench-orchestrator/contracts/base.py:Precondition 的关系（Round3B R3 澄清）：
    两者**刻意不合并**，因为语义不同：
    - orchestrator/contracts/base.py:Precondition.check(ctx) 接受 TaskContext，
      用于调度前依赖 ctx 的能力校验（如 repo_checkout_ready 检查 checkout 状态）
    - 本版 check() 无参（CLI 可用性检查不需要 ctx），适合 brand-runtime 自检
    若未来需要单一类型，应把两者统一为 `check(ctx=None)`，但会改变 preflight
    的调用约定，故保留双定义并显式标注边界，避免误合并。

    Attributes:
        name: 唯一名（用于日志/聚合）
        check: 无参可调用，返 (ok: bool, detail: str)
        hint: 失败时给用户的提示
    """
    name: str
    check: Callable[[], tuple[bool, str]]
    hint: str = ""

@dataclass
class AgentResult:
    """Agent 作答结果（品牌中立基础类型）。

    字段含义与 kimi_agent.environment.RunResult 一致，
    RunResult 仅为 AgentResult 的具名子类（Phase 3+ 收敛）。
    """
    success: bool
    instance_id: str
    pred_path: Optional[Path] = None
    traj_path: Optional[Path] = None
    patch_path: Optional[Path] = None
    log_path: Optional[Path] = None
    elapsed_seconds: float = 0.0
    error: Optional[str] = None
    exit_code: Optional[int] = None
    # SPEC-agent-speedup-20260808 G1：S4 拆相计时（validate/workspace/prompt/
    # invoke_cli/parse_output/artifacts 各段秒数）。默认空 dict，旧消费者无感。
    phase_timings: dict = field(default_factory=dict)
