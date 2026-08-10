"""swebench_exp_lite.runtime/lock_cleaner.py — 清理残留并发锁。

从 ``orchestrator.py:27-58`` 迁移（v0.1.5+ · PR #3）。
锁由 ``swebench_exp_lite.runtime.repo.acquire_run_lock`` 建在 ``repo_dir.parent/<id>.run.lock``，
agent runner 异常退出时可能未清理。Orchestrator 仅在 ``--force`` 时调本模块清理。

锁形态来源（swebench_exp_lite.runtime.repo:272 ``lock.mkdir()``）= 目录，rmtree 正确；
兼容历史文件型锁（pre-acquire_run_lock 时期）。
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path


def cleanup_stale_locks(ctx) -> None:
    """清理 3 个可能位置的残留锁。仅在 ``--force`` 时由 Orchestrator 调用。

    Args:
        ctx: TaskContext 实例（需含 ``task_dir`` / ``repo_root`` / ``instance_id``）。

    Returns:
        None。锁存在则清理并打印 ``[force]`` 消息；不可访问则打印 ``[warn]`` 警告。
    """
    cache_root = Path(os.environ.get(
        "SWEBENCH_RUNTIME_CACHE", str(ctx.repo_root / "runtime-cache")))
    # 3 个可能位置（与 acquire_run_lock 实际锁位置对齐）
    candidate_dirs = [
        ctx.task_dir,                                        # 默认位置
        cache_root / "worktrees" / ctx.instance_id,          # shared-mirror-worktree
        cache_root / "snapshots" / ctx.instance_id,          # shared-mirror-snapshot
    ]
    for parent in candidate_dirs:
        lock = parent / f"{ctx.instance_id}.run.lock"
        if not lock.exists():
            continue
        try:
            if lock.is_dir():
                shutil.rmtree(lock)
            else:
                # 兼容历史文件型锁（pre-acquire_run_lock 时期）
                lock.unlink()
            print(f"[force] 清理残留并发锁: {lock}")
        except OSError as e:
            print(f"[warn] 无法清理锁 {lock}: {e}")
