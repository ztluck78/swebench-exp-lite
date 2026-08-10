"""Brand Runner 集成层（移植自主仓 agent_runtime/brand_runner.py）。

4 个 brand runner（Kimi / Qwen / Mimo / Opencode）的 run 逻辑共享：
1. 设置 sys.path（仅 repo_root；本仓包已安装，无需 tools/ hack）
2. DB 查询获取 repo / repo_dir / repo_url / base_commit
3. 调 `runner.run(...)` 11 个参数
4. 失败时调 `adapter.diagnose_failure()` + raise RuntimeError
5. 读 workspace-state.json + 写 manifest

本模块抽离公共函数（`setup_brand_import_paths` + `run_brand_runner`）。

设计原则：
- runner 实例化保留在调用方（不同 brand 的 model / timeout / max_retries 来源不一样）
- DB / sys.path / manifest 是真公共，统一到本模块
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Optional


def setup_brand_import_paths(repo_root: Path) -> None:
    """设置 brand module 的 import 路径（仅 repo_root）。

    移植自主仓：主仓需把 tools/ 加入 sys.path 才能解析 kimi_agent 等模块；
    本仓的 swebench_exp_lite 包经 pip install -e . 安装后无需该 hack，
    仅保留 repo_root 插入（供子进程场景下解析仓内脚本），幂等。
    """
    rs = str(repo_root)
    if rs not in sys.path:
        sys.path.insert(0, rs)


def run_brand_runner(
    *,
    ctx: Any,
    output_dir: Path,
    runner: Any,
    post_prep_hook: Optional[Callable[[], None]],
    brand_display_name: str,
    adapter: Any,
) -> Any:
    """3 个 brand adapter (Kimi/Qwen/Mimo) 的公共 run 逻辑。

    Args:
        ctx: TaskContext
        output_dir: 产物输出目录
        runner: 已构造好的 AgentRunner 实例（KimiAgentRunner / QwenAgentRunner /
            MimoAgentRunner）；runner 自身的 model/timeout/max_retries 由 adapter
            注入，本函数不关心
        post_prep_hook: 备仓成功后回调（一般传 lambda: _env_preinstall(ctx)）
        brand_display_name: 失败日志里的品牌名（"Kimi" / "Qwen" / "MiMo"）
        adapter: adapter 实例（用于调 self.diagnose_failure 获取诊断日志）

    Returns:
        runner.run() 的返回 result（一般有 .success / .error 字段）

    Raises:
        RuntimeError: result.success=False 时，附 adapter.diagnose_failure 输出
    """
    # ── Step 1: DB 查询 repo 信息 ────────────────────────────────────────
    from swebench_exp_lite.db.query import LiteDB
    db = LiteDB(str(ctx.db_path))
    inst = db.get(ctx.instance_id)
    repo = inst.repo if inst else "unknown"
    repo_dir = ctx.task_dir / repo.replace("/", "__")
    repo_url = f"https://github.com/{repo}.git" if inst else None
    base_commit = inst.base_commit if inst else None

    # ── Step 2: 调 Runner.run() ──────────────────────────────────────────
    result = runner.run(
        instance_id=ctx.instance_id,
        issue_path=ctx.task_dir / "issue.json",
        ca_prompt_path=ctx.ca_prompt,
        repo_dir=repo_dir,
        output_dir=ctx.agent_dir,
        repo_root=ctx.repo_root,
        repo_url=repo_url,
        base_commit=base_commit,
        prep_log_path=ctx.task_dir / "logs" / "S4_repo_prep.log",
        post_prep_hook=post_prep_hook,
    )

    # ── Step 3: 失败时 raise + 附诊断日志 ───────────────────────────────
    if not result.success:
        # C2 修复（SPEC-modularization-round2）：adapter=None 是 s4_worker 的
        # 正常传参（v0.1.5+ 后不再有 AnswerAdapter 实例），旧代码此处会
        # AttributeError；缺失 adapter 时回退 runner 自身的 diagnose_failure。
        diag = (adapter or runner).diagnose_failure(ctx, output_dir)
        raise RuntimeError(
            f"{brand_display_name} Agent 执行失败：{result.error}\n\n[诊断日志]\n{diag}"
        )

    # ── Step 4: 写 manifest workspace_meta ───────────────────────────────
    # 与 base_runner._run_locked 写端对齐：workspace-state.json 落在
    # output_dir（= ctx.agent_dir = task_dir/agent/）下，而非 task_dir 根。
    state_path = output_dir / "workspace-state.json"
    if state_path.exists() and ctx.manifest:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        ctx.manifest.set_workspace_meta(
            mode=os.environ.get("WORKSPACE_MODE", "shared-mirror-worktree"),
            path=state.get("workspace_path"),
            repo=repo,
            repo_url=repo_url,
            base_commit=base_commit,
            final_head=state.get("commit"),
            dirty_files=state.get("dirty_files", []),
            untracked_files=state.get("untracked_files", []),
            retention=state.get("retention", "ephemeral"),
        )
    return result
