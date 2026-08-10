"""PipelineRunner：顺序驱动六阶段（失败即停 + 产物校验 + 断点续跑）。

- 失败即停：任一 StageError 中断并 mark_failed，打印续跑提示；
- 产物存在性校验：阶段完成后校验 outputs()，缺失视为失败；
- 断点续跑：manifest 中已 done 且产物齐备的阶段自动跳过（--force 全量重跑）；
- --dry-run：只打印六阶段命令链，不执行。
"""
from __future__ import annotations

import time
from pathlib import Path

from .context import TaskContext
from .manifest import Manifest
from .stages import STAGES
from .stages.base import StageError


def run_pipeline(ctx: TaskContext) -> Path:
    """执行六阶段闭环，返回 result.json 路径。"""
    ctx.task_dir.mkdir(parents=True, exist_ok=True)
    manifest = Manifest(ctx.task_dir)
    ctx.manifest = manifest
    manifest.set_meta(ctx.run_id, ctx.model, dataset=ctx.dataset, split=ctx.split)

    if ctx.dry_run:
        print(f"[dry-run] instance={ctx.instance_id} adapter={ctx.adapter} "
              f"run_id={ctx.run_id}")
        for stage_cls in STAGES:
            stage = stage_cls()
            cmd = stage.command(ctx)
            shown = " ".join(str(c) for c in cmd) if cmd else "（进程内执行）"
            print(f"  {stage.name:<12} $ {shown}")
        return ctx.result

    started_all = time.time()
    for stage_cls in STAGES:
        stage = stage_cls()
        # 断点续跑：已 done 且产物齐备 → 跳过
        if not ctx.force and manifest.is_done(stage.name):
            outs = stage.outputs(ctx)
            if all(p.exists() for p in outs):
                print(f"[skip] {stage.name}（manifest 已 done 且产物齐备）")
                continue
        print(f"[{stage.name}] 开始")
        manifest.mark_started(stage.name)
        t0 = time.time()
        try:
            stage.run(ctx)
        except StageError as e:
            manifest.mark_failed(stage.name, str(e))
            print(f"[fail] {stage.name}: {e}")
            print(f"       修复后重跑同一命令即可断点续跑（--force 可全量重来）")
            raise
        except Exception as e:  # noqa: BLE001
            manifest.mark_failed(stage.name, f"{type(e).__name__}: {e}")
            print(f"[fail] {stage.name}: {type(e).__name__}: {e}")
            raise
        # 产物存在性校验
        missing = [p for p in stage.outputs(ctx) if not p.exists()]
        if missing:
            msg = f"产物缺失: {', '.join(str(p) for p in missing)}"
            manifest.mark_failed(stage.name, msg)
            raise StageError(f"[{stage.name}] {msg}")
        manifest.mark_done(stage.name, outputs=[str(p) for p in stage.outputs(ctx)])
        print(f"[{stage.name}] 完成（{time.time() - t0:.1f}s）")

    total = time.time() - started_all
    print(f"[pipeline] 六阶段闭环完成，总耗时 {total:.1f}s → {ctx.result}")
    return ctx.result
