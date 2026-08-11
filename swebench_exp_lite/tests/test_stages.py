"""Stages 进程内逻辑测试（stdlib unittest，零新依赖）。

覆盖 S1 / S5 / S7 三阶段进程内逻辑：
- S1Build().run(ctx) 产出四件套（真实 DB）
- extract_changed_files 双模式并集（[s5_patch.py:21-23](file:///Users/zhangtian/DevWorkspace/swebench-exp-lite/swebench_exp_lite/pipeline/stages/s5_patch.py#L21-L23)）
- S5Patch 输入缺失抛 StageError
- S7Record 14 字段 dict（含 resolved_pct=100/0、stage_timings、baseline_resolved=None）
- S7Record 输入缺失抛 StageError

S2/S4/S6 涉及 Docker / subprocess，本测试文件**不覆盖**（由 run_demo.sh 红线承担）。

运行方式（仓根，无需 pytest）::

    python -m unittest swebench_exp_lite.tests.test_stages -v
"""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from swebench_exp_lite.db import DEFAULT_DB_PATH
from swebench_exp_lite.pipeline.context import TaskContext
from swebench_exp_lite.pipeline.manifest import Manifest
from swebench_exp_lite.pipeline.stages.s1_build import S1Build
from swebench_exp_lite.pipeline.stages.s5_patch import S5Patch, extract_changed_files
from swebench_exp_lite.pipeline.stages.s7_record import S7Record
from swebench_exp_lite.pipeline.stages.base import StageError


def _db_or_skip(test: unittest.TestCase) -> None:
    if not DEFAULT_DB_PATH.exists():
        test.skipTest(f"DB 不存在：{DEFAULT_DB_PATH}")


def _make_ctx(tmp: Path, instance_id: str = "sqlfluff__sqlfluff-1625") -> TaskContext:
    """构造 TaskContext（真实 instance_id 需 DB）。"""
    ctx = TaskContext(
        instance_id=instance_id,
        base_output_dir=tmp,
        repo_root=tmp,
        run_id="test-run",
        model="replay/gold-patch",
        adapter="replay-agent",
    )
    ctx.ensure_dirs()
    ctx.manifest = Manifest(ctx.task_dir)
    ctx.manifest.set_meta(ctx.run_id, ctx.model)
    return ctx


class TestS1Build(unittest.TestCase):
    """S1 出题：进程内 builder.build_and_render 写四件套。"""

    def setUp(self):
        _db_or_skip(self)
        self.tmp = tempfile.mkdtemp(prefix="s1_test_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_s1_build_produces_four_files(self):
        ctx = _make_ctx(Path(self.tmp))
        S1Build().run(ctx)
        self.assertTrue(ctx.review.exists())
        self.assertTrue(ctx.ca_issue.exists())
        self.assertTrue(ctx.ca_prompt.exists())
        self.assertTrue(ctx.task_jsonl.exists())

    def test_s1_build_ca_issue_no_gold_patch(self):
        """ca-issue.json 反序列化后严禁含 gold_patch（防泄露）。"""
        ctx = _make_ctx(Path(self.tmp))
        S1Build().run(ctx)
        data = json.loads(ctx.ca_issue.read_text(encoding="utf-8"))
        self.assertNotIn("gold_patch", data)
        self.assertNotIn("test_patch", data)


class TestExtractChangedFiles(unittest.TestCase):
    """双模式并集：[s5_patch.py:21-23](file:///Users/zhangtian/DevWorkspace/swebench-exp-lite/swebench_exp_lite/pipeline/stages/s5_patch.py#L21-L23)"""

    def test_dual_mode_union(self):
        patch = (
            "diff --git a/foo.py b/foo.py\n"
            "+++ b/foo.py\n"
            "@@ -1,1 +1,1 @@\n-old\n+new\n"
            "diff --git a/bar.py b/bar.py\n"  # 仅有 diff 头（如 git --binary untracked）
            "--- a/bar.py\n+++ b/bar.py\n"
        )
        result = extract_changed_files(patch)
        self.assertEqual(sorted(result), ["bar.py", "foo.py"])

    def test_empty_input_returns_empty(self):
        self.assertEqual(extract_changed_files(""), [])

    def test_only_plus_headers(self):
        patch = "diff --git a/x.py b/x.py\n+++ b/x.py\n@@\n-old\n+new\n"
        result = extract_changed_files(patch)
        self.assertIn("x.py", result)

    def test_only_git_headers(self):
        patch = "diff --git a/y.py b/y.py\n--- a/y.py\n+++ b/y.py\n"
        result = extract_changed_files(patch)
        self.assertIn("y.py", result)


class TestS5PatchMissingInput(unittest.TestCase):
    """S5Patch 输入缺失抛 StageError。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="s5_test_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_s5_patch_missing_input_raises_stage_error(self):
        ctx = _make_ctx(Path(self.tmp))
        # 不写 ctx.agent_pred → S5 应抛 StageError
        with self.assertRaises(StageError) as ctx_exc:
            S5Patch().run(ctx)
        self.assertIn("S5 输入缺失", str(ctx_exc.exception))


class TestS7Record(unittest.TestCase):
    """S7 记录：14 字段 dict + stage_timings 数值 + baseline_resolved=None。"""

    def setUp(self):
        _db_or_skip(self)
        self.tmp = tempfile.mkdtemp(prefix="s7_test_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_eval_report(self, ctx, resolved: bool):
        """构造 eval/report.json。"""
        ctx.eval_dir.mkdir(parents=True, exist_ok=True)
        report = {
            ctx.instance_id: {
                "patch_is_None": False,
                "patch_exists": True,
                "patch_successfully_applied": True,
                "resolved": resolved,
                "tests_status": {
                    "FAIL_TO_PASS": {
                        "success": ["t1", "t2"] if resolved else ["t1"],
                        "failure": [] if resolved else ["t2"],
                    },
                    "PASS_TO_PASS": {
                        "success": ["t3"],
                        "failure": [],
                    },
                },
            }
        }
        ctx.eval_report.write_text(json.dumps(report), encoding="utf-8")

    def test_s7_record_missing_input_raises_stage_error(self):
        ctx = _make_ctx(Path(self.tmp))
        # 不写 ctx.eval_report → S7 应抛 StageError
        with self.assertRaises(StageError) as ctx_exc:
            S7Record().run(ctx)
        self.assertIn("S7 输入缺失", str(ctx_exc.exception))

    def test_s7_resolved_pct_100_when_resolved(self):
        ctx = _make_ctx(Path(self.tmp))
        self._write_eval_report(ctx, resolved=True)
        result = S7Record()._build_result(ctx)
        self.assertEqual(result["resolved"], True)
        self.assertEqual(result["resolved_pct"], 100.0)

    def test_s7_resolved_pct_0_when_unresolved(self):
        ctx = _make_ctx(Path(self.tmp))
        self._write_eval_report(ctx, resolved=False)
        result = S7Record()._build_result(ctx)
        self.assertEqual(result["resolved"], False)
        self.assertEqual(result["resolved_pct"], 0.0)

    def test_s7_baseline_resolved_is_none(self):
        """S3 未实现：[s7_record.py:73](file:///Users/zhangtian/DevWorkspace/swebench-exp-lite/swebench_exp_lite/pipeline/stages/s7_record.py#L73)"""
        ctx = _make_ctx(Path(self.tmp))
        self._write_eval_report(ctx, resolved=True)
        result = S7Record()._build_result(ctx)
        self.assertIsNone(result["baseline_resolved"])

    def test_s7_record_builds_14_field_result(self):
        ctx = _make_ctx(Path(self.tmp))
        self._write_eval_report(ctx, resolved=True)
        result = S7Record()._build_result(ctx)
        # 14 字段稳定性守护（schema 改动需谨慎）
        expected_keys = {
            "instance_id", "run_id", "model", "adapter", "dataset",
            "split", "resolved", "resolved_pct", "report_source",
            "fail_to_pass", "pass_to_pass", "baseline_resolved",
            "image", "stages", "stage_timings", "generated_at",
        }
        self.assertEqual(set(result.keys()), expected_keys)

    def test_s7_stage_timings_is_float(self):
        """manifest 中某 stage 含 started + finished → result.stage_timings[name] 为 float。"""
        ctx = _make_ctx(Path(self.tmp))
        self._write_eval_report(ctx, resolved=True)
        # 标记 S1_build 为 done 并设时间戳
        ctx.manifest.mark_started("S1_build")
        ctx.manifest._stage("S1_build")["finished"] = datetime.now(timezone.utc).isoformat()
        ctx.manifest.save()
        result = S7Record()._build_result(ctx)
        timings = result["stage_timings"]
        self.assertIn("S1_build", timings)
        # float（可能 0.0 因瞬间完成）
        self.assertIsInstance(timings["S1_build"], (int, float))

    def test_s7_run_writes_result_json(self):
        ctx = _make_ctx(Path(self.tmp))
        self._write_eval_report(ctx, resolved=True)
        S7Record().run(ctx)
        self.assertTrue(ctx.result.exists())
        data = json.loads(ctx.result.read_text(encoding="utf-8"))
        self.assertEqual(data["resolved"], True)
        self.assertEqual(data["report_source"], "instance_report")


if __name__ == "__main__":
    unittest.main(verbosity=2)