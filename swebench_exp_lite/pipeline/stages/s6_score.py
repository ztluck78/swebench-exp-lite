"""S6 评分：子进程调 harness run_evaluation 跑真实 prediction。

H1 路径约定：子进程固定 cwd=仓根 → 报告落
`<repo>/logs/run_evaluation/{run_id_san}/{model__}/{iid}/report.json`，
聚合落 `<repo>/logs/run_evaluation/_aggregate/{model__}.{run_id_san}.json`。
主仓 cwd=repo_root/tools（报告落 tools/logs/）；lite 仓去掉 tools/ 前缀。

`--dataset_name` 传本地 jsonl（harness load_swebench_dataset 原生支持），
摆脱 HF datasets 与联网依赖。
"""
from __future__ import annotations

import sys

from .base import Stage, StageError, run_cmd
from ..report_utils import _copy_report


class S6Score(Stage):
    name = "S6_score"

    def command(self, ctx) -> list[str]:
        return [
            sys.executable, "-m", "answer_evaluator.harness.run_evaluation",
            "-p", str(ctx.prediction.resolve()),
            "-id", ctx.run_id,
            "--instance_ids", ctx.instance_id,
            "--dataset_name", ctx.dataset,
            "--split", ctx.split,
            "--namespace", ctx.namespace,
            "--cache_level", ctx.cache_level,
            "--timeout", str(ctx.timeout),
        ]

    def outputs(self, ctx):
        return [ctx.eval_report]

    def run(self, ctx) -> None:
        ctx.ensure_dirs()
        if ctx.dry_run:
            return
        if not ctx.prediction.exists():
            raise StageError(f"S6 输入缺失: {ctx.prediction}（S5 未产出？）")
        rid = ctx.run_id or ""
        if "/" in rid or "\\" in rid:
            raise StageError(
                f"run_id 含路径分隔符: {rid!r}（拼进报告路径会建出嵌套目录）")
        # H1：cwd=仓根（非主仓的 repo_root/tools）
        run_cmd(self.command(ctx), cwd=ctx.repo_root, ctx=ctx,
                log_name=self.name, timeout=ctx.timeout + 1800)
        _copy_report(ctx, run_id=ctx.run_id, model=ctx.model, dest=ctx.eval_report)
        print(f"    [S6_score] 评分报告就绪: {ctx.eval_report}")
