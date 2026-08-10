"""swebench_exp_lite.runtime: 环境变量工具（M6 修复 + 共享）。

提供容错的 env var 读取工具，让 brand agent config（kimi / qwen / mimo）在用户
设了非法 env 值时回退到 default + 发 RuntimeWarning，而不是 ValueError 崩溃。

修复 P1+ M6（report-comprehensive-analysis §5 M6 标 🟡）。
"""
from __future__ import annotations

import os
import warnings
from typing import Optional


def safe_int_env(name: str, default: int) -> int:
    """读 env var 为 int；非法值回退 ``default`` 并发 ``RuntimeWarning``（M6 兼容）。

    用法::

        timeout = safe_int_env("KIMI_TIMEOUT", 600)
        # 若 KIMI_TIMEOUT=foo → 警告 + 回退 600（不抛 ValueError）

    优先级：
    1. ``os.environ[name]`` 不存在 → 返回 ``default``
    2. 存在且 ``int(raw)`` 成功 → 返回解析值
    3. 存在但解析失败 → 发 ``RuntimeWarning`` + 返回 ``default``

    Args:
        name: 环境变量名
        default: 不存在或非法时的回退值

    Returns:
        解析后的 int 值
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (ValueError, TypeError):
        warnings.warn(
            f"环境变量 {name}={raw!r} 不是合法整数，回退默认值 {default}。",
            RuntimeWarning,
            stacklevel=2,
        )
        return default


__all__ = ["safe_int_env"]
