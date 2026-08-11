"""Patch 提取单元测试（stdlib unittest，零新依赖）。

覆盖 `runtime/patch.py` 的两个核心契约：
- `is_patch_noise_path`：denylist 噪声文件过滤（守护 untracked patch 不丢合法新增）
- `extract_changed_files`（与 stages/s5_patch.py 同名再导出，便于单测聚焦）

denylist（[patch.py:22-28](file:///Users/zhangtian/DevWorkspace/swebench-exp-lite/swebench_exp_lite/runtime/patch.py#L22-L28)）：
- 文件名 denylist：`.DS_Store` / `Thumbs.db` / `.gitkeep`
- 目录段 denylist：`__pycache__` / `.pytest_cache` / `.venv` / `venv` /
  `.mypy_cache` / `.ruff_cache` / `.ipynb_checkpoints`
- 后缀 denylast：`.pyc` / `.pyo` / `*.egg-info`

运行方式（仓根，无需 pytest）::

    python -m unittest swebench_exp_lite.tests.test_patch -v
"""
from __future__ import annotations

import unittest

from swebench_exp_lite.pipeline.stages.s5_patch import extract_changed_files
from swebench_exp_lite.runtime.patch import is_patch_noise_path


class TestIsPatchNoisePath(unittest.TestCase):
    """denylist 路径过滤。"""

    def test_blocks_pycache_dir(self):
        self.assertTrue(is_patch_noise_path("src/__pycache__/x.py"))

    def test_blocks_pycache_nested(self):
        self.assertTrue(is_patch_noise_path("a/b/c/__pycache__/mod.py"))

    def test_blocks_venv_dir(self):
        self.assertTrue(is_patch_noise_path(".venv/lib/x.py"))

    def test_blocks_venv_no_leading_dot(self):
        self.assertTrue(is_patch_noise_path("venv/lib/x.py"))

    def test_blocks_pyc_suffix(self):
        self.assertTrue(is_patch_noise_path("x.pyc"))

    def test_blocks_pyo_suffix(self):
        self.assertTrue(is_patch_noise_path("a/b/x.pyo"))

    def test_blocks_ds_store_file(self):
        self.assertTrue(is_patch_noise_path("a/.DS_Store"))

    def test_blocks_thumbs_db(self):
        self.assertTrue(is_patch_noise_path("dir/Thumbs.db"))

    def test_blocks_gitkeep(self):
        self.assertTrue(is_patch_noise_path("dir/.gitkeep"))

    def test_blocks_pytest_cache(self):
        self.assertTrue(is_patch_noise_path(".pytest_cache/v/cache"))

    def test_blocks_mypy_cache(self):
        self.assertTrue(is_patch_noise_path("a/.mypy_cache/3.4/foo.py"))

    def test_blocks_ruff_cache(self):
        self.assertTrue(is_patch_noise_path(".ruff_cache/foo.py"))

    def test_blocks_ipynb_checkpoints(self):
        self.assertTrue(is_patch_noise_path("a/.ipynb_checkpoints/x.ipynb"))

    def test_blocks_egg_info_segment(self):
        self.assertTrue(is_patch_noise_path("foo.egg-info/PKG-INFO"))

    def test_allows_legitimate_python(self):
        self.assertFalse(is_patch_noise_path("src/marshmallow/schema.py"))

    def test_allows_legitimate_nested(self):
        self.assertFalse(is_patch_noise_path("a/b/c/d/e.py"))

    def test_allows_empty_string(self):
        self.assertFalse(is_patch_noise_path(""))


class TestExtractChangedFiles(unittest.TestCase):
    """双模式并集（与 stages/s5_patch.py 行为一致）。"""

    def test_dual_mode_union(self):
        patch = (
            "diff --git a/foo.py b/foo.py\n"
            "+++ b/foo.py\n"
            "@@ -1,1 +1,1 @@\n-old\n+new\n"
            "diff --git a/bar.py b/bar.py\n"
        )
        result = extract_changed_files(patch)
        self.assertEqual(sorted(result), ["bar.py", "foo.py"])

    def test_empty_input_returns_empty(self):
        self.assertEqual(extract_changed_files(""), [])

    def test_only_plus_headers(self):
        patch = "diff --git a/x.py b/x.py\n+++ b/x.py\n@@\n-old\n+new\n"
        self.assertIn("x.py", extract_changed_files(patch))

    def test_only_git_headers(self):
        # 无 `+++ b/` 但有 `diff --git a/... b/...` 头（untracked / --binary）
        patch = "diff --git a/y.py b/y.py\n"
        self.assertIn("y.py", extract_changed_files(patch))


class TestPatchIntegration(unittest.TestCase):
    """集成：is_patch_noise_path 与 extract_changed_files 组合使用（真实 patch.py 的 extract_patch_from_repo 内部用）。"""

    def test_noise_filter_only_affects_untracked_paths(self):
        """合法路径 + 噪声路径混合：extract_changed_files 返全部（含噪声），由调用方按 is_patch_noise_path 过滤。"""
        patch = (
            "diff --git a/src/x.py b/src/x.py\n+++ b/src/x.py\n"
            "diff --git a/__pycache__/y.pyc b/__pycache__/y.pyc\n"
        )
        all_files = extract_changed_files(patch)
        # 两个文件都在返回列表
        self.assertEqual(len(all_files), 2)
        # 过滤噪声
        legit = [f for f in all_files if not is_patch_noise_path(f)]
        self.assertEqual(legit, ["src/x.py"])


if __name__ == "__main__":
    unittest.main(verbosity=2)