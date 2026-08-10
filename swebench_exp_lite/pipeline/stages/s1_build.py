"""S1 出题：进程内调 builder，从 LiteDB 取数生成题面四件套。

产物（output/<iid>/）：review.md / ca-issue.json / ca-task-prompt.md / task.jsonl。
主仓以子进程调 assessment-builder/cli.py；lite 仓包已安装，直接进程内调用。
"""
from __future__ import annotations

from pathlib import Path

from ...builder import TaskBuilder
from .base import Stage


class S1Build(Stage):
    name = "S1_build"

    def command(self, ctx):
        return [
            "python", "-c",
            f"from swebench_exp_lite.builder import TaskBuilder; "
            f"TaskBuilder().build_and_render('{ctx.instance_id}', '{ctx.base_output_dir}')",
        ]

    def outputs(self, ctx):
        return [ctx.review, ctx.ca_issue, ctx.ca_prompt, ctx.task_jsonl]

    def run(self, ctx) -> None:
        ctx.ensure_dirs()
        if ctx.dry_run:
            return
        builder = TaskBuilder(str(ctx.db_path) if ctx.db_path else None)
        paths = builder.build_and_render(ctx.instance_id, str(ctx.base_output_dir))
        for kind in ("review", "issue", "prompt", "jsonl"):
            if not paths.get(kind):
                from .base import StageError
                raise StageError(f"S1 未生成 {kind}（instance={ctx.instance_id}）")
        print(f"    [S1_build] 四件套就绪: {ctx.task_dir}")
