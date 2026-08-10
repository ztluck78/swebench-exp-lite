"""CLI 可用性预检（品牌中立，被 registry.RUNNERS 引用）。

v0.1.5+ · SPEC-remove-stages-s4-adapter-20260806 Commit 2：

承接 swebench-orchestrator/contracts/preconditions/cli.py 里的
kimi_cli_available / qwen_cli_available 工厂，新增 mimo_cli_available。
搬家原因：brand 包与 swebench_exp_lite.runtime 不应 import 总控（swebench-orchestrator）
模块，违反依赖方向。

双轨并存：总控 contracts/preconditions.py 旧实现保留
（被 S4Solve.CONTRACT.preconditions 引用），本模块是 brand-runtime 自检的家。
后续 SPEC 再考虑总控那边的 brand 专属 3 个是否清理。

设计：每个工厂返 swebench_exp_lite.runtime.protocol.Precondition（无 ctx 形参），
由 registry.resolve_runner() 在 preflight 阶段统一跑。
"""
from __future__ import annotations

from shutil import which

from .protocol import Precondition


__all__ = [
    "kimi_cli_available",
    "qwen_cli_available",
    "mimo_cli_available",
    "opencode_cli_available",
]


def kimi_cli_available() -> Precondition:
    """kimi CLI 在 PATH 中可用。

    检查方式：shutil.which("kimi") 非 None。
    失败 hint：引导用户去 wiki/05-workflow.md §Prerequisites 安装。
    """
    def _check():
        if which("kimi") is None:
            return False, "kimi CLI 未安装或未在 PATH 中"
        return True, ""
    return Precondition(
        name="kimi_cli_available",
        check=_check,
        hint="请安装 Kimi CLI：pip install kimi-cli && kimi auth login",
    )


def qwen_cli_available() -> Precondition:
    """Qwen Code CLI 在 PATH 中可用。

    检查方式：shutil.which("qwen") 非 None。
    """
    def _check():
        if which("qwen") is None:
            return False, "qwen CLI 未安装或未在 PATH 中"
        return True, ""
    return Precondition(
        name="qwen_cli_available",
        check=_check,
        hint="请安装 Qwen Code CLI：npm install -g @qwen-code/qwen-code 或 brew install qwen-code",
    )


def mimo_cli_available() -> Precondition:
    """MiMo Code CLI 在 PATH 中可用。

    v0.1.5+ 新增：mimo_agent 适配器需要 CLI；
    默认安装位置 ~/.mimocode/bin/mimo（参考 docs/SPEC-mimo-agent-20260805）。
    """
    def _check():
        if which("mimo") is None:
            return False, "mimo CLI 未安装或未在 PATH 中"
        return True, ""
    return Precondition(
        name="mimo_cli_available",
        check=_check,
        hint="请安装 MiMo Code CLI 并确保 PATH 含 ~/.mimocode/bin/mimo",
    )


def opencode_cli_available() -> Precondition:
    """Opencode CLI 在 PATH 中可用。

    v0.2.7+ 新增：opencode_agent 适配器需要 CLI；
    默认安装位置 ~/.npm-global/bin/opencode（npm 全局安装）。
    """
    def _check():
        if which("opencode") is None:
            return False, "opencode CLI 未安装或未在 PATH 中"
        return True, ""
    return Precondition(
        name="opencode_cli_available",
        check=_check,
        hint="请安装 opencode CLI 并确保 PATH 含 ~/.npm-global/bin/opencode（npm i -g opencode-ai）",
    )
