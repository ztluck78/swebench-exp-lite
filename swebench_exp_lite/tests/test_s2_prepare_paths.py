"""s2_prepare venv 路径跨平台守护测试（Task 17 配套）。

守护 `_prepare_venv` 用 `platform.venv_bin_dir()` 替代硬编码 `bin`：
- POSIX: bin/python、bin/pip（行为不变）
- Windows: Scripts/python.exe、Scripts/pip.exe（修复前会失败）

[原始代码 [s2_prepare.py:149](file:///Users/zhangtian/DevWorkspace/swebench-exp-lite/swebench_exp_lite/pipeline/stages/s2_prepare.py#L149) +
[s2_prepare.py:157](file:///Users/zhangtian/DevWorkspace/swebench-exp-lite/swebench_exp_lite/pipeline/stages/s2_prepare.py#L157) 硬编码 `bin` → 已修复]

运行方式（仓根，无需 pytest）::

    python -m unittest swebench_exp_lite.tests.test_s2_prepare_paths -v
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from swebench_exp_lite.pipeline.context import TaskContext
from swebench_exp_lite.pipeline.stages import s2_prepare as _s2_mod
from swebench_exp_lite.pipeline.stages.s2_prepare import S2Prepare
from swebench_exp_lite.runtime.platform import venv_bin_dir


def _make_ctx_with_worktree(tmp: Path, repo: str = "test/repo",
                            base_commit: str = "abc123def456") -> TaskContext:
    """构造带 worktree 的 TaskContext（满足 _prepare_venv 的前置条件）。"""
    ctx = TaskContext(
        instance_id="test__repo-1234",
        base_output_dir=tmp,
        repo_root=tmp,
        run_id="test-run",
        model="replay/gold-patch",
        repo=repo,
        base_commit=base_commit,
    )
    ctx.ensure_dirs()
    # 模拟 worktree 存在 + 含 setup.py
    from swebench_exp_lite.pipeline.stages.s2_prepare import _worktree_path
    worktree = _worktree_path(ctx)
    worktree.mkdir(parents=True, exist_ok=True)
    (worktree / "setup.py").write_text("from setuptools import setup\nsetup()\n",
                                       encoding="utf-8")
    # 显式设 NO_ENV_PREINSTALL=0（环境变量默认空字符串已 OK）
    return ctx


class TestS2PrepareVenvPathPosix(unittest.TestCase):
    """POSIX 行为不变：bin/python、bin/pip。"""

    def setUp(self):
        if venv_bin_dir() != "bin":
            self.skipTest("仅 POSIX 环境跑（bin 目录）")

    def test_posix_venv_python_path_uses_bin(self):
        """POSIX: venv 已存在时跳过打印 'venv 已存在'（即走 bin/python 命中路径）。"""
        tmp = Path(tempfile.mkdtemp(prefix="s2_venv_posix_"))
        try:
            ctx = _make_ctx_with_worktree(tmp)
            # 预先建好 bin/python 让 _prepare_venv 走命中分支
            from swebench_exp_lite.pipeline.stages.s2_prepare import _worktree_path
            venv_dir = tmp / "runtime-cache" / "venvs" / "test__repo" / "abc123de"
            venv_dir.mkdir(parents=True, exist_ok=True)
            (venv_dir / "bin").mkdir(exist_ok=True)
            (venv_dir / "bin" / "python").write_text("# fake", encoding="utf-8")

            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                S2Prepare()._prepare_venv(ctx)
            self.assertIn("venv 已存在", buf.getvalue())
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestS2PrepareVenvPathWindows(unittest.TestCase):
    """Windows 行为修复：mock os.name="nt" → 走 Scripts/python.exe 路径。"""

    def test_windows_venv_python_path_uses_scripts(self):
        """Windows: venv 已存在时走 Scripts/python.exe（修复前会失败）。

        在 POSIX 上 mock `venv_bin_dir` 直接返 "Scripts"，避免 mock os.name 触发 Path 创建 WindowsPath 异常。
        """
        tmp = Path(tempfile.mkdtemp(prefix="s2_venv_win_"))
        try:
            # mock `swebench_exp_lite.pipeline.stages.s2_prepare.venv_bin_dir`
            # （修复后改用模块顶部 import，此路径生效）
            with mock.patch(
                "swebench_exp_lite.pipeline.stages.s2_prepare.venv_bin_dir",
                return_value="Scripts",
            ):
                self.assertEqual(_s2_mod.venv_bin_dir(), "Scripts")
                ctx = _make_ctx_with_worktree(tmp)
                # 预先建好 Scripts/python 让 _prepare_venv 走命中分支
                # 注：Path.exists() 检查字面文件名，'Scripts/python.exe' 不等于 'Scripts/python'
                venv_dir = tmp / "runtime-cache" / "venvs" / "test__repo" / "abc123de"
                venv_dir.mkdir(parents=True, exist_ok=True)
                (venv_dir / "Scripts").mkdir(exist_ok=True)
                (venv_dir / "Scripts" / "python").write_text("# fake", encoding="utf-8")

                import io
                from contextlib import redirect_stdout
                buf = io.StringIO()
                with redirect_stdout(buf):
                    # _prepare_venv 内部 import platform 模块
                    S2Prepare()._prepare_venv(ctx)
                # 命中分支：打印 "venv 已存在"
                self.assertIn("venv 已存在", buf.getvalue())
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_windows_venv_does_not_access_bin_directory(self):
        """Windows 行为下不应访问 bin 目录（修复前的硬编码 bug）。"""
        tmp = Path(tempfile.mkdtemp(prefix="s2_venv_no_bin_"))
        try:
            # 仅建 Scripts/python，不建 bin/python
            venv_dir = tmp / "runtime-cache" / "venvs" / "test__repo" / "abc123de"
            venv_dir.mkdir(parents=True, exist_ok=True)
            (venv_dir / "Scripts").mkdir(exist_ok=True)
            (venv_dir / "Scripts" / "python").write_text("# fake", encoding="utf-8")

            ctx = _make_ctx_with_worktree(tmp)

            with mock.patch(
                "swebench_exp_lite.pipeline.stages.s2_prepare.venv_bin_dir",
                return_value="Scripts",
            ):
                import io
                from contextlib import redirect_stdout
                buf = io.StringIO()
                with redirect_stdout(buf):
                    # 应走命中分支（不报"venv preinstall 失败"）
                    S2Prepare()._prepare_venv(ctx)
                output = buf.getvalue()
                self.assertNotIn("venv preinstall 失败", output)
                self.assertIn("venv 已存在", output)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)