"""Harness Grading 纯函数测试（stdlib unittest，零新依赖）。

**仅测试**，不改 `answer_evaluator/harness/grading.py`（AGENTS.md 冻结边界）。
覆盖 `grading.py` 的纯函数：
- `test_passed` / `test_failed`：TestStatus 谓词
- `compute_fail_to_pass` / `compute_pass_to_pass`：比例计算 + 除零兜底
- `get_resolution_status`：FULL / PARTIAL / NO 三种判定
- `get_eval_report`：patch_is_None 分支（无需 repo 即可测）

运行方式（仓根，无需 pytest）::

    python -m unittest swebench_exp_lite.tests.test_harness_grading -v
"""
from __future__ import annotations

import unittest

from answer_evaluator.harness.constants import (
    FAIL_TO_PASS,
    KEY_INSTANCE_ID,
    KEY_PREDICTION,
    PASS_TO_PASS,
    ResolvedStatus,
    TestStatus,
)
from answer_evaluator.harness.grading import (
    compute_fail_to_pass,
    compute_pass_to_pass,
    get_resolution_status,
    test_failed,
    test_passed,
)


class TestTestPassed(unittest.TestCase):
    """test_passed(case, status_map) 谓词：PASSED/XFAIL 算 pass。"""

    def test_passed_for_passed_status(self):
        sm = {"test_x.py::test_a": TestStatus.PASSED.value}
        self.assertTrue(test_passed("test_x.py::test_a", sm))

    def test_passed_for_xfail_status(self):
        sm = {"test_x.py::test_a": TestStatus.XFAIL.value}
        self.assertTrue(test_passed("test_x.py::test_a", sm))

    def test_passed_false_for_failed_status(self):
        sm = {"test_x.py::test_a": TestStatus.FAILED.value}
        self.assertFalse(test_passed("test_x.py::test_a", sm))

    def test_passed_false_for_error_status(self):
        sm = {"test_x.py::test_a": TestStatus.ERROR.value}
        self.assertFalse(test_passed("test_x.py::test_a", sm))

    def test_passed_false_for_missing_case(self):
        # case 不在 status_map 中 → 视为未通过
        sm = {"other_test": TestStatus.PASSED.value}
        self.assertFalse(test_passed("missing_test", sm))


class TestTestFailed(unittest.TestCase):
    """test_failed(case, status_map) 谓词：FAILED/ERROR 或缺失算 fail。"""

    def test_failed_for_failed_status(self):
        sm = {"t1": TestStatus.FAILED.value}
        self.assertTrue(test_failed("t1", sm))

    def test_failed_for_error_status(self):
        sm = {"t1": TestStatus.ERROR.value}
        self.assertTrue(test_failed("t1", sm))

    def test_failed_for_missing_case(self):
        sm = {}
        self.assertTrue(test_failed("t1", sm))

    def test_failed_false_for_passed_status(self):
        sm = {"t1": TestStatus.PASSED.value}
        self.assertFalse(test_failed("t1", sm))

    def test_failed_false_for_xfail_status(self):
        # XFAIL 视为预期失败，不计入 fail
        sm = {"t1": TestStatus.XFAIL.value}
        self.assertFalse(test_failed("t1", sm))


class TestComputeFailToPass(unittest.TestCase):
    """compute_fail_to_pass(report) + 除零兜底。"""

    def test_basic_ratio(self):
        report = {FAIL_TO_PASS: {"success": ["t1", "t2"], "failure": ["t3"]}}
        self.assertAlmostEqual(compute_fail_to_pass(report), 2 / 3)

    def test_all_success(self):
        report = {FAIL_TO_PASS: {"success": ["t1", "t2", "t3"], "failure": []}}
        self.assertAlmostEqual(compute_fail_to_pass(report), 1.0)

    def test_all_failure(self):
        report = {FAIL_TO_PASS: {"success": [], "failure": ["t1", "t2"]}}
        self.assertAlmostEqual(compute_fail_to_pass(report), 0.0)

    def test_zero_total_returns_one(self):
        """除零兜底：[grading.py:199-200](file:///Users/zhangtian/DevWorkspace/swebench-exp-lite/answer_evaluator/harness/grading.py#L199-L200)"""
        report = {FAIL_TO_PASS: {"success": [], "failure": []}}
        self.assertEqual(compute_fail_to_pass(report), 1)


class TestComputePassToPass(unittest.TestCase):
    """compute_pass_to_pass(report) + 除零兜底。"""

    def test_basic_ratio(self):
        report = {PASS_TO_PASS: {"success": ["t1"], "failure": ["t2", "t3"]}}
        self.assertAlmostEqual(compute_pass_to_pass(report), 1 / 3)

    def test_all_success(self):
        report = {PASS_TO_PASS: {"success": ["t1", "t2"], "failure": []}}
        self.assertAlmostEqual(compute_pass_to_pass(report), 1.0)

    def test_zero_total_returns_one(self):
        """除零兜底：[grading.py:209-211](file:///Users/zhangtian/DevWorkspace/swebench-exp-lite/answer_evaluator/harness/grading.py#L209-L211)"""
        report = {PASS_TO_PASS: {"success": [], "failure": []}}
        self.assertEqual(compute_pass_to_pass(report), 1)


class TestGetResolutionStatus(unittest.TestCase):
    """get_resolution_status 判定 FULL / PARTIAL / NO。"""

    def _report(self, f2p_success: int, f2p_total: int,
                p2p_success: int, p2p_total: int) -> dict:
        return {
            FAIL_TO_PASS: {
                "success": [f"t_f2p_{i}" for i in range(f2p_success)],
                "failure": [f"t_f2p_fail_{i}" for i in range(f2p_total - f2p_success)],
            },
            PASS_TO_PASS: {
                "success": [f"t_p2p_{i}" for i in range(p2p_success)],
                "failure": [f"t_p2p_fail_{i}" for i in range(p2p_total - p2p_success)],
            },
        }

    def test_full_when_both_one(self):
        # f2p=1.0, p2p=1.0 → FULL
        report = self._report(f2p_success=2, f2p_total=2,
                              p2p_success=3, p2p_total=3)
        self.assertEqual(get_resolution_status(report), ResolvedStatus.FULL.value)

    def test_partial_when_f2p_between_zero_and_one(self):
        # f2p=0.5, p2p=1.0 → PARTIAL
        report = self._report(f2p_success=1, f2p_total=2,
                              p2p_success=2, p2p_total=2)
        self.assertEqual(get_resolution_status(report), ResolvedStatus.PARTIAL.value)

    def test_no_when_p2p_broken(self):
        # f2p=1.0, p2p=0.0 → NO（回归破坏）
        report = self._report(f2p_success=2, f2p_total=2,
                              p2p_success=0, p2p_total=2)
        self.assertEqual(get_resolution_status(report), ResolvedStatus.NO.value)

    def test_no_when_f2p_zero(self):
        # f2p=0, p2p=1.0 → NO（未修复 bug）
        report = self._report(f2p_success=0, f2p_total=2,
                              p2p_success=2, p2p_total=2)
        self.assertEqual(get_resolution_status(report), ResolvedStatus.NO.value)

    def test_full_when_both_zero_total_uses_division_by_zero_guard(self):
        """除零兜底：f2p_total=0/p2p_total=0 时两个 metric 都返 1.0 → FULL。"""
        report = self._report(f2p_success=0, f2p_total=0,
                              p2p_success=0, p2p_total=0)
        self.assertEqual(get_resolution_status(report), ResolvedStatus.FULL.value)

    def test_no_when_f2p_partial_and_p2p_partial(self):
        # f2p=0.5, p2p=0.5 → NO（p2p 破坏）
        report = self._report(f2p_success=1, f2p_total=2,
                              p2p_success=1, p2p_total=2)
        self.assertEqual(get_resolution_status(report), ResolvedStatus.NO.value)


class TestGetEvalReportPatchIsNone(unittest.TestCase):
    """get_eval_report 在 patch 为 None 时直接返回（不调 log parser）。"""

    def test_patch_is_none_returns_minimal_report(self):
        # 构造一个最简单的 test_spec 与 prediction，但 patch 为 None
        # 由于 get_eval_report 内部用 repo 查 MAP，这里用 mock 跳过日志解析
        from unittest import mock
        with mock.patch("answer_evaluator.harness.grading.get_logs_eval") as mock_logs:
            prediction = {
                KEY_INSTANCE_ID: "test__repo-1234",
                KEY_PREDICTION: None,
            }
            mock_test_spec = mock.MagicMock()
            mock_test_spec.repo = "test/repo"
            mock_test_spec.version = "1.0"
            mock_test_spec.instance_id = "test__repo-1234"
            mock_test_spec.FAIL_TO_PASS = []
            mock_test_spec.PASS_TO_PASS = []

            report = mock_logs.return_value  # 实际不调用
            # 重设以确保不调用
            mock_logs.return_value = ({}, False)
            mock_logs.side_effect = None

            # patch=None 分支直接返，不调 get_logs_eval
            from answer_evaluator.harness.grading import get_eval_report
            result = get_eval_report(
                test_spec=mock_test_spec,
                prediction=prediction,
                test_log_path="/tmp/nonexistent",
                include_tests_status=False,
            )
            self.assertEqual(result[prediction[KEY_INSTANCE_ID]]["patch_is_None"], True)
            self.assertEqual(result[prediction[KEY_INSTANCE_ID]]["resolved"], False)


if __name__ == "__main__":
    unittest.main(verbosity=2)