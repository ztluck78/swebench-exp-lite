"""平台抽象层：把分散在多处的平台分支收敛到单点入口。

背景：
- 0.1.0 仅在 macOS 验证通过；0.2.0 需在 Windows 11 + PowerShell 跑通。
- 评测代码层 95% 已跨平台（pathlib.Path / subprocess.run list 形式），
  真正卡跨平台的是零星几处平台硬编码：
  * POSIX 风格的 ``/dev/null`` 路径（patch.py 的 git diff 兜底）
  * POSIX 风格的 ``os.kill(pid, 0)`` 进程存活探测（repo.py 的 stale 锁清理）
  * ``import resource`` 资源限制（run_evaluation / prepare_images）
  * 入口脚本对 venv 目录、默认 shell 的写法（不同平台 bin/ vs Scripts/）

本模块对外暴露 4 个无副作用函数，所有平台分支集中在此：

- :func:`null_device` —— ``/dev/null`` 跨平台等价
- :func:`is_process_alive` —— pid 存活探测（POSIX/Win 双实现）
- :func:`venv_bin_dir` —— venv 可执行目录名（``bin`` / ``Scripts``）
- :func:`default_shell` —— subprocess 显式 shell 调用时的默认 shell

仅依赖标准库（os / sys / ctypes），不引入新依赖，符合
"docker / tqdm / unidiff / requests 四件套"约束。
"""
from __future__ import annotations

import os
import sys
from typing import List


def null_device() -> str:
    """返回当前平台的"空设备"路径。

    - POSIX（含 macOS / Linux / WSL）：``/dev/null``
    - Windows：``nul``（NUL 设备，无需扩展名；带扩展名 ``nul:`` 也可，
      但纯 ``nul`` 在 cmd / PowerShell / Git Bash 表现一致）

    使用场景：``git diff --no-index`` 的 "从空文件" 端点，
    ``open(..., 'w')`` 时希望吞掉输出的 sink。
    """
    return "nul" if os.name == "nt" else "/dev/null"


def is_process_alive(pid: int) -> bool:
    """探测给定 pid 是否仍在运行（POSIX/Win 跨平台）。

    POSIX 实现（macOS / Linux / WSL）：
        调 ``os.kill(pid, 0)``，只发信号 0 不真杀。
        - 抛 ``ProcessLookupError``：进程不存在 → False
        - 抛其他 ``OSError``（如 EPERM）：权限不足但进程存在 → True
        - 正常返回：进程存在 → True

    Windows 实现（Docker Desktop WSL2/Hyper-V backend 同样适用）：
        用 ctypes 调 kernel32.OpenProcess + GetExitCodeProcess：
        - OpenProcess 失败（返回 0 / GetLastError == ERROR_INVALID_PARAMETER
          或 ERROR_ACCESS_DENIED 但 PID 已被回收）：进程不存在 → False
        - GetExitCodeProcess 返回 ``STILL_ACTIVE (259)``：进程仍在运行 → True
        - 拿到真实退出码：进程已退出 → False
        必须用 PROCESS_QUERY_LIMITED_INFORMATION（0x1000）权限，避开
        SeDebugPrivilege 需求，普通用户即可调。

    Args:
        pid: 目标进程 ID。

    Returns:
        bool：进程存在且未退出 → True；否则 False。
    """
    if os.name == "nt":
        # 仅在 Windows 路径里 import ctypes，POSIX 不增加无谓依赖
        import ctypes
        from ctypes import wintypes

        STILL_ACTIVE = 259
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        # OpenProcess 返回 HANDLE；非零表示成功
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            exit_code = wintypes.DWORD()
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            if not ok:
                return False
            return exit_code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)

    # POSIX 路径
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        # EPERM 等权限问题：进程存在但本进程无权发信号
        return True


def venv_bin_dir() -> str:
    """返回 venv 可执行目录名（不含 venv 根）。

    - POSIX：``bin``（.venv/bin/python, .venv/bin/pip）
    - Windows：``Scripts``（.venv\\Scripts\\python.exe, .venv\\Scripts\\pip.exe）

    使用场景：入口脚本定位 venv 解释器：
    ``{venv_root}/{venv_bin_dir()}/python`` （POSIX 风格）
    或 ``{venv_root}\\{venv_bin_dir()}\\python.exe``（Windows 风格）
    """
    return "Scripts" if os.name == "nt" else "bin"


def default_shell() -> str:
    """返回 subprocess 显式 ``shell=True`` 时使用的默认 shell。

    - POSIX：``bash``
    - Windows：``cmd.exe``

    注意：本仓内大部分 subprocess 调用都是 list 形式（不依赖 shell），
    本函数仅在确实需要 shell 解析时用。
    """
    return "cmd.exe" if os.name == "nt" else "bash"


__all__: List[str] = [
    "null_device",
    "is_process_alive",
    "venv_bin_dir",
    "default_shell",
]
