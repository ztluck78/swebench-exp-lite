"""platform 抽象层单元测试（stdlib unittest，零新依赖）。

覆盖 4 个函数在 POSIX 路径下的真实行为 + Windows 路径下的调用形状
（用 unittest.mock 替代 ctypes，避免在 macOS 上 mock Windows-only 模块）。

运行方式（仓根，无需 pytest）::

    python -m unittest swebench_exp_lite.tests.test_platform -v

CI 步骤见 .github/workflows/ci.yml。

设计选择：
- 0.1.0 时代以"红线验证（./run_demo.sh）"为唯一验收门禁，不要求
  pytest 跑通（见 conftest.py 注释）。
- 0.2.0 起把 platform 抽象层加进来，需要守住 POSIX/Windows 双路径
  行为对齐。用 stdlib unittest 而非 pytest，避免引入新依赖
  （AGENTS.md 严格约束：四件套 docker/tqdm/unidiff/requests）。
"""
from __future__ import annotations

import os
import platform as _platform
import sys
import unittest
from unittest import mock

from swebench_exp_lite.runtime.platform import (
    default_shell,
    is_process_alive,
    null_device,
    venv_bin_dir,
)


# ---------------------------------------------------------------------------
# null_device
# ---------------------------------------------------------------------------
class TestNullDevice(unittest.TestCase):
    def test_returns_string(self):
        result = null_device()
        self.assertIsInstance(result, str)
        self.assertTrue(result)  # 非空

    def test_posix_returns_dev_null(self):
        if os.name == "nt":
            self.skipTest("POSIX-only assertion")
        self.assertEqual(null_device(), "/dev/null")

    def test_windows_returns_nul(self):
        with mock.patch("swebench_exp_lite.runtime.platform.os.name", "nt"):
            self.assertEqual(null_device(), "nul")


# ---------------------------------------------------------------------------
# is_process_alive（POSIX 真路径）
# ---------------------------------------------------------------------------
class TestIsProcessAlivePosix(unittest.TestCase):
    def test_current_process_is_alive(self):
        if os.name == "nt":
            self.skipTest("POSIX-only assertion")
        # 当前进程必然存活
        self.assertTrue(is_process_alive(os.getpid()))

    def test_nonexistent_pid_is_dead(self):
        if os.name == "nt":
            self.skipTest("POSIX-only assertion")
        # 用一个不可能存在的超大 PID
        self.assertFalse(is_process_alive(2**31 - 1))

    def test_zero_pid_returns_bool(self):
        # PID 0 在 POSIX 与 Windows 行为不同：
        # - POSIX: os.kill(0, 0) 检测"本进程组"，通常 True
        # - Windows: PID 0 是 System Idle Process，OpenProcess 受限
        # 函数只承诺"返回 bool"，不承诺具体值
        result = is_process_alive(0)
        self.assertIsInstance(result, bool)


# ---------------------------------------------------------------------------
# is_process_alive（Windows mock 路径）
# ---------------------------------------------------------------------------
class TestIsProcessAliveWindows(unittest.TestCase):
    def _make_fake_ctypes(self, still_active_value):
        """构造一个伪 ctypes：WinDLL 返回 fake kernel32，byref 返回传入对象。"""
        class FakeDWORD:
            def __init__(self):
                self.value = still_active_value
        fake_kernel32 = mock.MagicMock()
        fake_kernel32.OpenProcess.return_value = 1  # 非零句柄
        fake_kernel32.GetExitCodeProcess.return_value = True
        fake_kernel32.CloseHandle.return_value = True
        fake_ctypes = mock.MagicMock()
        fake_ctypes.WinDLL.return_value = fake_kernel32
        fake_ctypes.byref.side_effect = lambda ref: ref
        # 关键：函数内 `from ctypes import wintypes` 走 fake_ctypes.wintypes
        # 这里给 fake ctypes 装一个 wintypes 子模块（MagicMock 自带子属性访问）
        # 但我们需要在 test 里指定 DWORD class 身份（需 value 可读取）
        # 用 MagicMock(spec=...) 不必要，存一个 wintypes 引用即可
        fake_wintypes_module = mock.MagicMock()
        fake_wintypes_module.DWORD = FakeDWORD
        fake_ctypes.wintypes = fake_wintypes_module
        return fake_ctypes, fake_kernel32

    def test_open_process_returns_zero_means_dead(self):
        fake_kernel32 = mock.MagicMock()
        fake_kernel32.OpenProcess.return_value = 0
        fake_ctypes = mock.MagicMock()
        fake_ctypes.WinDLL.return_value = fake_kernel32
        with mock.patch.dict(sys.modules, {"ctypes": fake_ctypes}):
            with mock.patch("swebench_exp_lite.runtime.platform.os.name", "nt"):
                self.assertFalse(is_process_alive(1234))

    def test_still_active_means_alive(self):
        fake_ctypes, _ = self._make_fake_ctypes(still_active_value=259)
        with mock.patch.dict(sys.modules, {"ctypes": fake_ctypes}):
            with mock.patch("swebench_exp_lite.runtime.platform.os.name", "nt"):
                self.assertTrue(is_process_alive(1234))

    def test_exited_process_means_dead(self):
        fake_ctypes, _ = self._make_fake_ctypes(still_active_value=0)
        with mock.patch.dict(sys.modules, {"ctypes": fake_ctypes}):
            with mock.patch("swebench_exp_lite.runtime.platform.os.name", "nt"):
                self.assertFalse(is_process_alive(1234))


# ---------------------------------------------------------------------------
# venv_bin_dir
# ---------------------------------------------------------------------------
class TestVenvBinDir(unittest.TestCase):
    def test_posix_returns_bin(self):
        if os.name == "nt":
            self.skipTest("POSIX-only assertion")
        self.assertEqual(venv_bin_dir(), "bin")

    def test_windows_returns_scripts(self):
        with mock.patch("swebench_exp_lite.runtime.platform.os.name", "nt"):
            self.assertEqual(venv_bin_dir(), "Scripts")


# ---------------------------------------------------------------------------
# default_shell
# ---------------------------------------------------------------------------
class TestDefaultShell(unittest.TestCase):
    def test_posix_returns_bash(self):
        if os.name == "nt":
            self.skipTest("POSIX-only assertion")
        self.assertEqual(default_shell(), "bash")

    def test_windows_returns_cmd(self):
        with mock.patch("swebench_exp_lite.runtime.platform.os.name", "nt"):
            self.assertEqual(default_shell(), "cmd.exe")


# ---------------------------------------------------------------------------
# 一致性断言
# ---------------------------------------------------------------------------
class TestInvariants(unittest.TestCase):
    def test_all_return_str_or_bool(self):
        # null_device / venv_bin_dir / default_shell 返回 str
        # is_process_alive 返回 bool（需要合法 pid）
        self.assertIsInstance(null_device(), str)
        self.assertIsInstance(venv_bin_dir(), str)
        self.assertIsInstance(default_shell(), str)
        self.assertIsInstance(is_process_alive(os.getpid()), bool)


# ---------------------------------------------------------------------------
# Linux 真路径（仅在 Linux 上运行，macOS / Windows 跳过）
# ---------------------------------------------------------------------------
class TestLinuxSpecific(unittest.TestCase):
    """Linux 真机断言：在 ubuntu-latest CI 上真实运行，验证 POSIX 分支
    在 Linux 内核上的实际行为（非 mock）。"""

    def _skip_if_not_linux(self):
        if _platform.system() != "Linux":
            self.skipTest("Linux-only assertion")

    def test_null_device_on_linux(self):
        self._skip_if_not_linux()
        self.assertEqual(null_device(), "/dev/null")

    def test_venv_bin_dir_on_linux(self):
        self._skip_if_not_linux()
        self.assertEqual(venv_bin_dir(), "bin")

    def test_default_shell_on_linux(self):
        self._skip_if_not_linux()
        self.assertEqual(default_shell(), "bash")

    def test_is_process_alive_self_on_linux(self):
        self._skip_if_not_linux()
        self.assertTrue(is_process_alive(os.getpid()))

    def test_resource_import_on_linux(self):
        """验证 answer_evaluator 的跨平台分支在 Linux 上正确：
        import resource 应当成功（Linux 内核支持 rlimit）。
        这守护了 prepare_images.py / run_evaluation.py 的
        ``if platform.system() == 'Linux': import resource`` 分支。"""
        self._skip_if_not_linux()
        import resource  # noqa: F401
        self.assertTrue(hasattr(resource, "setrlimit"))
        self.assertTrue(hasattr(resource, "RLIMIT_NOFILE"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
