"""S4 作答：调 resolve_runner() 选定的 runner 生成 model_patch。

- replay-agent：进程内直跑（零依赖，<1s，重放 gold patch 的闭环自检）；
- 四品牌（kimi/qwen/mimo/opencode）：spawn 子进程跑 s4_worker，
  硬超时 SIGKILL（避免 CLI 挂起拖死主流程）。

产物：agent/<iid>/<iid>.pred / .traj（runner 协议约定）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from .base import Stage, StageError


class S4Solve(Stage):
    name = "S4_solve"

    def command(self, ctx):
        return [sys.executable, "-m", "swebench_exp_lite.pipeline.stages.s4_worker",
                "<config-json>"]

    def outputs(self, ctx):
        return [ctx.agent_pred]

    def run(self, ctx) -> None:
        ctx.ensure_dirs()
        if ctx.dry_run:
            return
        # preconditions（CLI 可用性预检）在 resolve_runner 内触发，
        # 未装 CLI 时给出友好报错与安装指引
        from ...runtime.registry import resolve_runner
        runner = resolve_runner(ctx.adapter)

        if ctx.adapter == "replay-agent":
            result = self._run_inproc(ctx, runner)
        else:
            result = self._run_subprocess(ctx, runner.name)
            # 子进程路径下从 runner 拿不到实例 model，保持 ctx.model

        if not result.get("success"):
            raise StageError(f"S4 ({runner.name}) 作答失败: {result.get('error')}")

        # replay：model 对齐 runner（replay/gold-patch），保证 S6 报告路径可追溯
        runner_model = getattr(runner, "model", None)
        if ctx.adapter == "replay-agent" and runner_model:
            ctx.model = runner_model

        if not ctx.agent_pred.exists():
            raise StageError(f"S4 产物缺失: {ctx.agent_pred}")
        print(f"    [S4_solve] .pred 就绪: {ctx.agent_pred}")

    def _run_inproc(self, ctx, runner) -> dict:
        """replay-agent 进程内直跑（无 CLI/网络/备仓依赖）。"""
        result = runner.run(
            instance_id=ctx.instance_id,
            issue_path=ctx.ca_issue,
            ca_prompt_path=ctx.ca_prompt,
            repo_dir=ctx.task_dir / (ctx.repo.replace("/", "__") or "repo"),
            output_dir=ctx.agent_dir,
            repo_root=ctx.repo_root,
            repo_url=ctx.repo_url or None,
            base_commit=ctx.base_commit or None,
        )
        return {"success": result.success, "error": result.error}

    def _run_subprocess(self, ctx, adapter_name: str) -> dict:
        """品牌 runner 走 worker 子进程（超时 kill）。"""
        config = {
            "adapter": adapter_name,
            "instance_id": ctx.instance_id,
            "issue_path": str(ctx.ca_issue),
            "ca_prompt_path": str(ctx.ca_prompt),
            "repo_dir": str(ctx.task_dir / (ctx.repo.replace("/", "__") or "repo")),
            "output_dir": str(ctx.agent_dir),
            "repo_root": str(ctx.repo_root),
            "repo_url": ctx.repo_url or None,
            "base_commit": ctx.base_commit or None,
        }
        timeout = int(os.environ.get("SWEBENCH_S4_TIMEOUT", "1800"))
        cmd = [sys.executable, "-m", "swebench_exp_lite.pipeline.stages.s4_worker",
               json.dumps(config, ensure_ascii=False)]
        print(f"    $ {' '.join(cmd[:3])} <config>（timeout={timeout}s）")
        log_path = ctx.task_dir / "logs" / "S4_solve.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as log_f:
            try:
                proc = subprocess.run(
                    cmd, cwd=str(ctx.repo_root), timeout=timeout,
                    stdout=log_f, stderr=subprocess.STDOUT, text=True,
                )
            except subprocess.TimeoutExpired:
                raise StageError(
                    f"S4 ({adapter_name}) 超时 {timeout}s 被杀；"
                    f"可调大 SWEBENCH_S4_TIMEOUT 后重跑（断点续跑跳过已完成阶段）"
                )
        if proc.returncode != 0:
            return {"success": False,
                    "error": f"worker exit={proc.returncode}（日志: {log_path}）"}
        return {"success": True, "error": ""}
