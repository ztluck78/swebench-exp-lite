"""Stage 基类与共享子进程工具（精简自主仓 stages/base.py）。

不带 contracts 双轨体系（spec：不做 contracts/walltime 双段监控/batch）：
Stage 只声明 name / command() / outputs() / run()，由 runner 顺序驱动。
"""
from __future__ import annotations

import os
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..context import TaskContext


class StageError(RuntimeError):
    """阶段失败（runner 失败即停）。"""


def run_cmd(cmd: list[str], cwd: Path, ctx: "TaskContext",
            log_name: str | None = None, timeout: int | None = None) -> None:
    """执行子进程（实时透传输出 + 日志落盘 + 超时保护）。

    日志落 `ctx.task_dir/logs/<log_name>.log`（聚合根自包含）。
    timeout 未传时取 STAGE_CMD_TIMEOUT（默认 3600s）。
    """
    if ctx.dry_run:
        return
    if timeout is None:
        timeout = int(os.environ.get("STAGE_CMD_TIMEOUT", "3600"))
    cmd_str = " ".join(str(c) for c in cmd)
    print(f"    $ {cmd_str}")

    log_path = None
    if log_name:
        try:
            log_dir = ctx.task_dir / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / f"{log_name}.log"
        except Exception as e:  # noqa: BLE001
            print(f"    [warn] 无法创建阶段日志目录: {e}")

    with subprocess.Popen(
        [str(c) for c in cmd], cwd=str(cwd),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    ) as proc:
        log_f = open(log_path, "a", encoding="utf-8") if log_path else None
        try:
            if log_f:
                log_f.write(f"$ {cmd_str}\n")
            try:
                for line in proc.stdout:
                    if log_f:
                        log_f.write(line)
                    print(line, end="", flush=True)
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                raise StageError(f"[{log_name or 'cmd'}] 子进程超时 {timeout}s 被杀: {cmd_str}")
        finally:
            if log_f:
                log_f.write(f"[exit={proc.returncode}]\n")
                log_f.close()
    if proc.returncode != 0:
        raise StageError(
            f"[{log_name or 'cmd'}] 子进程退出码 {proc.returncode}: {cmd_str}\n"
            f"    详情见日志: {log_path or '(未落盘)'}"
        )


class Stage(ABC):
    name: str = ""

    def command(self, ctx: "TaskContext") -> list[str] | None:
        """dry-run 展示用的命令链；纯进程内阶段返回 None。"""
        return None

    def outputs(self, ctx: "TaskContext") -> list[Path]:
        """本阶段必须产出的文件（runner 做存在性校验 + 断点续跑判据）。"""
        return []

    @abstractmethod
    def run(self, ctx: "TaskContext") -> None: ...
