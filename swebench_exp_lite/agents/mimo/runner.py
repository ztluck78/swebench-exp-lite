"""Mimo Agent Orchestrator 集成（DESIGN Step 2 P4 重构后）。

thin adapter——9 步主流程全部继承自 swebench_exp_lite.runtime.base_runner.BaseAgentRunner。
D10 防御（mimo auto-commit detect + reset）+ D4 清理（.mimocode/）通过
_post_invoke_brand_hook 注入。

实测关键事实（2026-08-05）：
1. CLI 形态：mimo run "message" -m <model> --dangerously-skip-permissions
   - prompt 是位置参数（--prompt 是 mimo 的全局选项，给 mimo run 用会显示 help）
   - 必需 --dangerously-skip-permissions 才能非交互
2. 默认模型：mimo-v2.5-pro（Xiaomi 自家，OAuth 登录）
3. 退出码恒 0：必须用产物（patch 内容）+ NDJSON step_finish.reason 判定成功
4. .mimocode/ 56MB 写 cwd，worktree 生命周期自动清理
5. mimo 默认 build agent 不 commit（D10 防御是兜底，2026-08-05 实测未触发）

完整设计：[docs/DESIGN-base-agent-runner-step2-20260805.md](../../../../docs/DESIGN-base-agent-runner-step2-20260805.md)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .agent import MimoAgent, _detect_mimo_committed
from .config import MimoConfig
from .environment import MimoResult
from swebench_exp_lite.runtime.base_runner import BaseAgentRunner


class MimoAgentRunner(BaseAgentRunner[MimoResult]):
    """Mimo Agent Orchestrator 适配器（DESIGN Step 2 P4 重构后）。

    行为完全保留原 MimoAgentRunner——D10 + D4 防御通过 _post_invoke_brand_hook
    注入（基类第 5 步调用）。
    """

    name = "mimo-agent"

    def __init__(
        self,
        model: Optional[str] = None,
        timeout: int = 1800,  # mimo 慢，D7 配 1800s
        max_retries: int = 0,
    ):
        super().__init__(
            model=model or "xiaomi/mimo-v2.5-pro",
            timeout=timeout,
            max_retries=max_retries,
        )

    # C10：_get_agent 走 BaseAgentRunner 模板（config_class/agent_class 声明式）
    config_class = MimoConfig
    agent_class = MimoAgent

    def _start_message(self) -> str:
        return "启动 MiMo Code CLI"

    def _make_error_result(self, instance_id: str, error: str) -> MimoResult:
        """mimo 用 MimoResult（向后兼容）。"""
        return MimoResult(success=False, instance_id=instance_id, error=error)

    def _post_invoke_brand_hook(
        self,
        agent: MimoAgent,
        repo_dir: Path,
        base_commit: Optional[str],
        output_dir: Path,
        parse_result=None,
    ) -> None:
        """Mimo D10 + D4 防御（在基类 9 步骨架第 5 步后调用）。

        D10：mimo 理论上能 git commit，实测未触发但兜底——base_commit 之前如果有
        新 commit，reset 掉（保证 patch 提取自 base_commit..HEAD 的 working tree）。

        D4：清理 .mimocode/ 56MB 临时目录（worktree 生命周期自动清理，但 runner
        内部可能不依赖 worktree 路径，所以显式调用）。

        注意：基类第 6 步 write_workspace_state 在本 hook 之后——所以 workspace
        状态记录的是"reset 后"的状态，符合预期。
        """
        # D10 防御
        mimo_committed = _detect_mimo_committed(repo_dir, base_commit)
        undone = _undo_mimo_commit(repo_dir, base_commit) if mimo_committed else 0
        if mimo_committed:
            print(
                f"    [mimo-agent] D10 防御：检测到 mimo auto-commit，已撤回"
                f"（HEAD reset 到 {base_commit[:8] if base_commit else '?'}）"
            )
        # D4 清理
        _cleanup_mimo_state(repo_dir)


# === Mimo D10/D4 内部 helper（私有，本模块用） ===
def _undo_mimo_commit(repo_dir: Path, base_commit: Optional[str]) -> int:
    """撤回到 base_commit（git reset --mixed，不动 working tree）。"""
    if not base_commit:
        return 0
    from swebench_exp_lite.runtime.proc import run_cmd as _ar_run_cmd
    result = _ar_run_cmd(
        ["git", "reset", "--mixed", base_commit],
        cwd=repo_dir, timeout=30, check=False,
    )
    return 0 if result.returncode == 0 else 1


def _cleanup_mimo_state(repo_dir: Path) -> None:
    """清理 .mimocode/ 56MB 临时目录。"""
    import shutil
    mimocode = repo_dir / ".mimocode"
    if mimocode.exists():
        try:
            shutil.rmtree(mimocode)
        except Exception:  # noqa: BLE001
            pass  # best-effort cleanup

