"""brand 注册表（runtime 唯一 brand 边界）。

移植自主仓 agent_runtime/registry.py：brand 选择下沉到本模块，
总控 S4 不再感知具体 brand。

接新 agent 时，只需在本文件 `RUNNERS` 字典加 1 行 +
在 swebench_exp_lite/agents/<brand>/ 实现 BaseAgentRunner 子类 +
（如需 CLI 预检）在 runtime/cli_preconditions.py 加工厂。

preconditions 对未装 CLI 友好报错；replay-agent 零依赖兜底（无预检）。
"""
from __future__ import annotations

import importlib
import os
from typing import Optional

from .base_runner import BaseAgentRunner
from .cli_preconditions import (
    kimi_cli_available,
    mimo_cli_available,
    opencode_cli_available,
    qwen_cli_available,
)


DEFAULT_RUNNER = "kimi-agent"


# 品牌中立注册表（接新 agent 仅改这一处 + 加 swebench_exp_lite/agents/<brand>/ 包）
# value 是 dict：
#   - "class":         "module:ClassName" 字符串，import 时按需解析
#   - "preconditions": Precondition 对象列表（resolve_runner 时按 preflight 跑）
RUNNERS: dict[str, dict] = {
    "kimi-agent": {
        "class":         "swebench_exp_lite.agents.kimi:KimiAgentRunner",
        "preconditions": [kimi_cli_available()],
    },
    "kimi-fast": {
        "class":         "swebench_exp_lite.agents.kimi.fast_runner:KimiFastRunner",
        "preconditions": [kimi_cli_available()],
    },
    "qwen-agent": {
        "class":         "swebench_exp_lite.agents.qwen:QwenAgentRunner",
        "preconditions": [qwen_cli_available()],
    },
    "mimo-agent": {
        "class":         "swebench_exp_lite.agents.mimo:MimoAgentRunner",
        "preconditions": [mimo_cli_available()],
    },
    "opencode-agent": {
        "class":         "swebench_exp_lite.agents.opencode:OpencodeAgentRunner",
        "preconditions": [opencode_cli_available()],
    },
    # 快速红线验证：重放 gold patch，跳过 LLM/CLI/备仓（无预检）
    "replay-agent": {
        "class":         "swebench_exp_lite.runtime.replay_runner:ReplayRunner",
        "preconditions": [],
    },
}


def list_runner_names() -> list[str]:
    """返回所有已注册 runner 名（CLI argparse choices 动态拉取用）。"""
    return list(RUNNERS.keys())


def resolve_runner(name: Optional[str] = None) -> BaseAgentRunner:
    """品牌中立的选择器；默认走 ANSWER_ADAPTER env。

    执行顺序：
      1. 解析 name（CLI 参数 > ANSWER_ADAPTER env > DEFAULT_RUNNER）
      2. 跑该 brand 注册的 preconditions（preflight 拦截；Commit 2 落地预检内容）
      3. import 模块 + 构造 Runner 实例

    Args:
        name: runner 名（CLI --adapter 传入）；None 时读 env，再走 DEFAULT_RUNNER

    Returns:
        BaseAgentRunner 实例

    Raises:
        ValueError:    name 不在 RUNNERS 注册表里
        RuntimeError:  任意 precondition 不通过（带 brand-specific hint）
    """
    name = (name or os.environ.get("ANSWER_ADAPTER") or DEFAULT_RUNNER).lower()
    if name not in RUNNERS:
        raise ValueError(
            f"unknown runner: {name!r}; available: {list_runner_names()}"
        )

    entry = RUNNERS[name]

    # Precondition 预检（preflight 阶段，worker 启动前）
    for pc in entry.get("preconditions", []):
        ok, detail = pc.check()
        if not ok:
            hint = f"  → {pc.hint}" if pc.hint else ""
            raise RuntimeError(
                f"[{name}] precondition 未通过：{detail}\n{hint}"
            )

    # import + 实例化
    module_path, class_name = entry["class"].split(":")
    module = importlib.import_module(module_path)
    runner_cls = getattr(module, class_name)
    return runner_cls()


__all__ = ["DEFAULT_RUNNER", "RUNNERS", "list_runner_names", "resolve_runner"]
