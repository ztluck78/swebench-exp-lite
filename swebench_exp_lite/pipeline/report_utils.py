"""Harness 评分报告定位/解析工具（H1 路径约定）。

移植自主仓 stages/report_utils.py，路径基准去掉 tools/ 前缀：
lite 仓 S6 子进程固定 cwd=仓根，harness 报告落
`<repo>/logs/run_evaluation/{run_id_san}/{model 的 / 换 __}/{iid}/report.json`，
聚合报告落 `<repo>/logs/run_evaluation/_aggregate/{model__}.{run_id_san}.json`
（与 answer_evaluator/harness/reporting.py 写入端同构）。

S7 三级降级：逐实例 report.json → 聚合报告推导 resolved_ids →
兜底 resolved=False + note="report not found"。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .context import TaskContext


def _find_report(repo_root: Path, run_id: str, model: str, instance_id: str) -> Path:
    """定位 harness 写出的逐实例 report.json。

    harness 以 cwd=仓根 运行，日志写到
    logs/run_evaluation/<run_id_san>/<model__>/<iid>/report.json
    （model / run_id 的 '/' 均替换为 '__'，与 harness 内部逻辑一致）。
    注意：空 patch 时 harness 提前返回，不会写此文件，需回退到聚合报告。
    """
    model_dir = model.replace("/", "__")
    run_id_san = run_id.replace("/", "__")
    parts = [run_id_san, model_dir, instance_id, "report.json"]
    return repo_root / "logs" / "run_evaluation" / Path(*parts)


def _find_aggregated_report(repo_root: Path, run_id: str, model: str) -> Path:
    """定位 harness 写出的聚合报告。

    写入端在 answer_evaluator/harness/reporting.py 的 make_run_report()：
    logs/run_evaluation/_aggregate/<model__>.<run_id_san>.json。
    """
    model_dir = model.replace("/", "__")
    run_id_san = run_id.replace("/", "__")
    return (
        repo_root
        / "logs"
        / "run_evaluation"
        / "_aggregate"
        / f"{model_dir}.{run_id_san}.json"
    )


def _resolved_from_aggregated(agg_path: Path, instance_id: str) -> "Optional[bool]":
    """从聚合报告推导某实例是否 resolved（无法判定时返回 None）。"""
    try:
        agg = json.loads(agg_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    resolved_ids = set(agg.get("resolved_ids", []) or [])
    unresolved_ids = set(agg.get("unresolved_ids", []) or [])
    empty_ids = set(agg.get("empty_patch_ids", []) or [])
    if instance_id in resolved_ids:
        return True
    if instance_id in unresolved_ids or instance_id in empty_ids:
        return False
    return None


def _copy_report(ctx: "TaskContext", run_id: str, model: str, dest: Path) -> None:
    """把 harness 的评分结果复制回任务目录（三级降级）。

    1. 逐实例 report.json 存在 → 原样复制；
    2. 空 patch 等场景 harness 不写逐实例报告 → 读聚合报告推导 resolved；
    3. 两者皆无 → resolved=False + note="report not found"（兜底，
       红线验证要求 grep 无此痕迹，出现即说明 H1 路径约定被破坏）。
    """
    src = _find_report(ctx.repo_root, run_id, model, ctx.instance_id)
    if src.exists():
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        return
    agg = _find_aggregated_report(ctx.repo_root, run_id, model)
    if agg.exists():
        r = _resolved_from_aggregated(agg, ctx.instance_id)
        if r is not None:
            dest.write_text(
                json.dumps(
                    {ctx.instance_id: {"resolved": r, "source": "aggregated_report"}},
                    indent=2,
                ),
                encoding="utf-8",
            )
            return
    dest.write_text(
        json.dumps({ctx.instance_id: {"resolved": False, "note": "report not found"}}),
        encoding="utf-8",
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
