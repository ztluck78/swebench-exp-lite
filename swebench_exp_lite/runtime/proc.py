"""统一子进程执行器：杜绝"静默吞异常"。

设计动机（来自 sqlfluff__sqlfluff-1733 端到端实战事故）：
environment.py 曾裸调 subprocess.run 执行 `git fetch --unshallow`，
超时异常未检查、返回码未校验，导致仓库处于半残状态却继续 checkout，
最终以误导性的"产物缺失"报错收场，根因排查耗时远超故障本身。

本模块约定：
- 所有子进程调用必须经 run_cmd()，禁止裸调 subprocess.run；
- 超时（TimeoutExpired）一律包装为 CmdError 显式抛出，绝不静默继续；
- 失败（returncode != 0）时异常必含：命令、退出码、stderr 尾部；
- 查询类调用（允许失败、由调用方判定）显式传 check=False。
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional, Sequence, Union

PathLike = Union[str, Path, None]


class CmdError(RuntimeError):
    """子进程执行失败（非零退出 / 超时 / 无法启动），消息含完整上下文。"""


def _cmd_str(cmd: Sequence[str]) -> str:
    return " ".join(str(c) for c in cmd)


def run_cmd(
    cmd: Sequence[str],
    cwd: PathLike = None,
    timeout: float = 1800,
    check: bool = True,
    error_prefix: str = "",
) -> subprocess.CompletedProcess:
    """执行子进程并强制结果检查。

    Args:
        cmd: 命令列表
        cwd: 工作目录
        timeout: 超时秒数（超时必抛 CmdError，绝不静默）
        check: True = 非零退出码抛 CmdError；False = 仅返回结果由调用方判定
            （只允许用于"允许失败"的查询类命令，如 git cat-file 探测）
        error_prefix: 错误消息前缀（如 "git clone"），便于日志定位

    Returns:
        subprocess.CompletedProcess

    Raises:
        CmdError: 超时 / check=True 且非零退出 / 命令无法启动
    """
    prefix = f"{error_prefix}: " if error_prefix else ""
    try:
        result = subprocess.run(
            [str(c) for c in cmd],
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise CmdError(
            f"{prefix}命令超时（{timeout}s 被强制终止，操作可能未完成，"
            f"不可继续后续步骤）: {_cmd_str(cmd)}"
        ) from e
    except (OSError, FileNotFoundError) as e:
        raise CmdError(f"{prefix}命令无法启动: {_cmd_str(cmd)}（{e}）") from e

    if check and result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise CmdError(
            f"{prefix}命令失败（exit {result.returncode}）: {_cmd_str(cmd)}"
            + (f"\nstderr: {stderr}" if stderr else "")
        )
    return result


def run_cmd_to_file(
    cmd: Sequence[str],
    log_path: "PathLike",
    cwd: "PathLike" = None,
    timeout: float = 1800,
) -> subprocess.CompletedProcess:
    """执行子进程并把 stdout+stderr 写到 log 文件（不 capture 到内存）。

    用途：Agent CLI 调用场景——kimi/qwen/mimo 都把 CLI 输出写到大文件
    （kimi 通常 10-50MB；mimo NDJSON 也可能 100KB+），不应该 capture 到
    Python 内存里（OOM 风险）。DESIGN §1 优化 #3：3 brand 共用此模式。

    Args:
        cmd: 命令列表
        log_path: 日志文件路径（覆盖写）
        cwd: 工作目录
        timeout: 超时秒数（超时必抛 CmdError）

    Returns:
        subprocess.CompletedProcess（stdout/stderr 都被重定向到文件，无返回值）

    Raises:
        CmdError: 超时 / 命令无法启动
    """
    from pathlib import Path as _Path
    log_p = _Path(log_path)
    log_p.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(log_p, "w", encoding="utf-8") as log_f:
            result = subprocess.run(
                [str(c) for c in cmd],
                cwd=str(cwd) if cwd is not None else None,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                timeout=timeout,
            )
        return result
    except subprocess.TimeoutExpired as e:
        raise CmdError(
            f"命令超时（{timeout}s 被强制终止）: {_cmd_str(cmd)}"
        ) from e
    except (OSError, FileNotFoundError) as e:
        raise CmdError(f"命令无法启动: {_cmd_str(cmd)}（{e}）") from e
