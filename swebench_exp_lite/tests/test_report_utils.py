"""report_utils 三级降级测试（stdlib unittest，零新依赖）。

覆盖 `pipeline/report_utils.py` 的三级降级契约：
- L1：逐实例 `report.json` 存在 → `report_source=="instance_report"`
- L2：逐实例缺失 + 聚合存在 → `_resolved_from_aggregated` 推导 + `report_source=="aggregated_report"`
- L3：两者皆无 → `resolved=False` + `note="report not found"`（红线 grep 应无此痕迹）

H1 路径约定：[report_utils.py:31-34](file:///Users/zhangtian/DevWorkspace/swebench-exp-lite/swebench_exp_lite/pipeline/report_utils.py#L31-L34) +
[run_evaluation.py:94-98](file:///Users/zhangtian/DevWorkspace/swebench-exp-lite/answer_evaluator/harness/run_evaluation.py#L94-L98)
（run_id / model 的 `/` 替换为 `__`）。

运行方式（仓根，无需 pytest）::

    python -m unittest swebench_exp_lite.tests.test_report_utils -v
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from swebench_exp_lite.pipeline.report_utils import (
    _copy_report,
    _find_aggregated_report,
    _find_report,
    _resolved_from_aggregated,
)


def _ctx(repo_root: Path, instance_id: str = "test__repo-1234") -> SimpleNamespace:
    """构造最小 TaskContext-like 对象（report_utils 仅用 repo_root / instance_id）。"""
    return SimpleNamespace(repo_root=repo_root, instance_id=instance_id)


class TestFindReport(unittest.TestCase):
    """_find_report 路径拼接（H1 路径约定）。"""

    def test_path_replaces_slashes(self):
        """run_id / model 中的 `/` 替换为 `__`，避免嵌套目录。"""
        p = _find_report(Path("/repo"), "run/with/slash", "model/with/slash",
                         "test__repo-1234")
        # 应拆为 run__with__slash / model__with__slash / test__repo-1234 / report.json
        self.assertIn("run__with__slash", str(p))
        self.assertIn("model__with__slash", str(p))
        self.assertTrue(str(p).endswith("test__repo-1234/report.json"))


class TestFindAggregatedReport(unittest.TestCase):
    """_find_aggregated_report 路径拼接。"""

    def test_aggregated_path_layout(self):
        p = _find_aggregated_report(Path("/repo"), "run-1", "model-1")
        self.assertIn("logs/run_evaluation/_aggregate", str(p))
        self.assertTrue(str(p).endswith("model-1.run-1.json"))


class TestResolvedFromAggregated(unittest.TestCase):
    """_resolved_from_aggregated 推导 resolved。"""

    def test_instance_in_resolved_ids_returns_true(self):
        agg = {
            "resolved_ids": ["a", "b", "c"],
            "unresolved_ids": [],
            "empty_patch_ids": [],
        }
        tmp = tempfile.mkdtemp(prefix="agg_test_")
        try:
            agg_path = Path(tmp) / "agg.json"
            agg_path.write_text(json.dumps(agg), encoding="utf-8")
            self.assertTrue(_resolved_from_aggregated(agg_path, "b"))
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_instance_in_unresolved_returns_false(self):
        agg = {
            "resolved_ids": ["a"],
            "unresolved_ids": ["b"],
            "empty_patch_ids": [],
        }
        tmp = tempfile.mkdtemp(prefix="agg_test_")
        try:
            agg_path = Path(tmp) / "agg.json"
            agg_path.write_text(json.dumps(agg), encoding="utf-8")
            self.assertFalse(_resolved_from_aggregated(agg_path, "b"))
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_instance_in_empty_patch_returns_false(self):
        agg = {
            "resolved_ids": ["a"],
            "unresolved_ids": [],
            "empty_patch_ids": ["c"],
        }
        tmp = tempfile.mkdtemp(prefix="agg_test_")
        try:
            agg_path = Path(tmp) / "agg.json"
            agg_path.write_text(json.dumps(agg), encoding="utf-8")
            self.assertFalse(_resolved_from_aggregated(agg_path, "c"))
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_instance_unknown_returns_none(self):
        agg = {
            "resolved_ids": ["a"],
            "unresolved_ids": ["b"],
            "empty_patch_ids": [],
        }
        tmp = tempfile.mkdtemp(prefix="agg_test_")
        try:
            agg_path = Path(tmp) / "agg.json"
            agg_path.write_text(json.dumps(agg), encoding="utf-8")
            self.assertIsNone(_resolved_from_aggregated(agg_path, "unknown"))
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_corrupted_agg_returns_none(self):
        tmp = tempfile.mkdtemp(prefix="agg_test_")
        try:
            agg_path = Path(tmp) / "agg.json"
            agg_path.write_text("{invalid json", encoding="utf-8")
            self.assertIsNone(_resolved_from_aggregated(agg_path, "any"))
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestCopyReportLevel1(unittest.TestCase):
    """L1：逐实例 report.json 存在 → 直接复制。"""

    def test_instance_report_copies_directly(self):
        tmp = tempfile.mkdtemp(prefix="copy_test_")
        try:
            repo_root = Path(tmp)
            iid = "test__repo-1234"
            # 写 L1 逐实例 report.json
            instance_report = _find_report(repo_root, "run-1", "model-1", iid)
            instance_report.parent.mkdir(parents=True, exist_ok=True)
            original = {"patch_exists": True, "resolved": True}
            instance_report.write_text(json.dumps(original), encoding="utf-8")

            dest = repo_root / "output" / iid / "eval" / "report.json"
            dest.parent.mkdir(parents=True, exist_ok=True)
            _copy_report(_ctx(repo_root, iid), run_id="run-1", model="model-1",
                         dest=dest)
            copied = json.loads(dest.read_text(encoding="utf-8"))
            # 原文复制（含 source="instance_report" 不一定，但至少 patch_exists/resolved）
            self.assertEqual(copied.get("patch_exists"), True)
            self.assertEqual(copied.get("resolved"), True)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestCopyReportLevel2(unittest.TestCase):
    """L2：逐实例缺失 + 聚合存在 → 从聚合推导。"""

    def test_aggregated_fallback_marks_resolved(self):
        tmp = tempfile.mkdtemp(prefix="copy_test_")
        try:
            repo_root = Path(tmp)
            iid = "test__repo-1234"
            # 写聚合报告（不含逐实例）
            agg_path = _find_aggregated_report(repo_root, "run-2", "model-2")
            agg_path.parent.mkdir(parents=True, exist_ok=True)
            agg_path.write_text(json.dumps({
                "resolved_ids": [iid],
                "unresolved_ids": [],
                "empty_patch_ids": [],
            }), encoding="utf-8")

            dest = repo_root / "output" / iid / "eval" / "report.json"
            dest.parent.mkdir(parents=True, exist_ok=True)
            _copy_report(_ctx(repo_root, iid), run_id="run-2", model="model-2",
                         dest=dest)
            copied = json.loads(dest.read_text(encoding="utf-8"))
            self.assertEqual(copied[iid]["resolved"], True)
            self.assertEqual(copied[iid]["source"], "aggregated_report")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_aggregated_fallback_marks_unresolved(self):
        tmp = tempfile.mkdtemp(prefix="copy_test_")
        try:
            repo_root = Path(tmp)
            iid = "test__repo-1234"
            agg_path = _find_aggregated_report(repo_root, "run-3", "model-3")
            agg_path.parent.mkdir(parents=True, exist_ok=True)
            agg_path.write_text(json.dumps({
                "resolved_ids": [],
                "unresolved_ids": [iid],
                "empty_patch_ids": [],
            }), encoding="utf-8")

            dest = repo_root / "output" / iid / "eval" / "report.json"
            dest.parent.mkdir(parents=True, exist_ok=True)
            _copy_report(_ctx(repo_root, iid), run_id="run-3", model="model-3",
                         dest=dest)
            copied = json.loads(dest.read_text(encoding="utf-8"))
            self.assertEqual(copied[iid]["resolved"], False)
            self.assertEqual(copied[iid]["source"], "aggregated_report")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestCopyReportLevel3(unittest.TestCase):
    """L3：两者皆无 → 兜底 note="report not found"。"""

    def test_both_missing_falls_back_to_report_not_found(self):
        tmp = tempfile.mkdtemp(prefix="copy_test_")
        try:
            repo_root = Path(tmp)
            iid = "test__repo-1234"
            # 不写任何 report

            dest = repo_root / "output" / iid / "eval" / "report.json"
            dest.parent.mkdir(parents=True, exist_ok=True)
            _copy_report(_ctx(repo_root, iid), run_id="run-4", model="model-4",
                         dest=dest)
            copied = json.loads(dest.read_text(encoding="utf-8"))
            self.assertEqual(copied[iid]["resolved"], False)
            self.assertEqual(copied[iid]["note"], "report not found")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)