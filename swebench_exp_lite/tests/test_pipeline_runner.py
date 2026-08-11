"""PipelineRunner 单元测试（stdlib unittest，零新依赖）。

覆盖 `pipeline/runner.py` 的 4 个核心契约：
- dry-run 打印 6 行命令链不执行
- 断点续跑跳过已 done 且产物齐备的 stage
- 产物缺失抛 StageError 含 "产物缺失"
- StageError 触发 manifest.mark_failed 并 re-raise

通过 mock `STAGES` 列表为 fake Stage 类实现进程内单测，不调真实 stage.run()。

运行方式（仓根，无需 pytest）::

    python -m unittest swebench_exp_lite.tests.test_pipeline_runner -v
"""
from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from swebench_exp_lite.pipeline.context import TaskContext
from swebench_exp_lite.pipeline.manifest import Manifest
from swebench_exp_lite.pipeline.stages.base import Stage, StageError


def _make_ctx(tmp: Path, dry_run: bool = False) -> TaskContext:
    """构造 TaskContext（含 dry_run 参数）。"""
    ctx = TaskContext(
        instance_id="test__repo-1234",
        base_output_dir=tmp,
        repo_root=tmp,
        run_id="test-run",
        model="replay/gold-patch",
        adapter="replay-agent",
        dry_run=dry_run,
    )
    # 先建 task_dir，否则 Manifest.save() 会抛 FileNotFoundError
    ctx.ensure_dirs()
    ctx.manifest = Manifest(ctx.task_dir)
    ctx.manifest.set_meta(ctx.run_id, ctx.model)
    return ctx


def _fake_stage_factory(name: str, run_behavior, output_paths=None):
    """构造一个 fake Stage 类（必须直接实现 run，因 Stage 是 ABC）。

    ABC 的 abstract 检查走类体内 __abstractmethods__，必须在类体内定义 run。
    """
    class FakeStage(Stage):
        def run(self, ctx):
            return run_behavior()

        def outputs(self, ctx):
            return list(output_paths or [])

        def command(self, ctx):
            return [f"echo {name}"]

    FakeStage.name = name
    return FakeStage


class TestPipelineRunnerDryRun(unittest.TestCase):
    """dry_run=True：打印 6 行命令链，不创建 stage 实例副作用。"""

    def test_dry_run_prints_six_stage_chain(self):
        tmp = tempfile.mkdtemp(prefix="runner_dry_")
        try:
            ctx = _make_ctx(Path(tmp), dry_run=True)

            fake_stages = [_fake_stage_factory(f"S{i}_fake", lambda: None) for i in range(1, 7)]
            buf = io.StringIO()
            with mock.patch("swebench_exp_lite.pipeline.runner.STAGES", fake_stages):
                with redirect_stdout(buf):
                    from swebench_exp_lite.pipeline.runner import run_pipeline
                    run_pipeline(ctx)
            output = buf.getvalue()
            # 1 行 [dry-run] 总头 + 6 行 stage 命令（带 fake 名）
            self.assertIn("[dry-run] instance=test__repo-1234", output)
            for i in range(1, 7):
                self.assertIn(f"S{i}_fake", output)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestPipelineRunnerResume(unittest.TestCase):
    """断点续跑：manifest 已 done + 产物齐备 → 跳过 stage.run()。"""

    def test_resume_skips_done_stage_with_outputs(self):
        tmp = tempfile.mkdtemp(prefix="runner_resume_")
        try:
            ctx = _make_ctx(Path(tmp))

            # 构造一个 done 的 stage，output 文件已存在
            output_file = ctx.task_dir / "fake_output.txt"
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text("done", encoding="utf-8")
            ctx.manifest.mark_done("S1_fake", outputs=[str(output_file)])

            run_called = [False]

            def run_behavior():
                run_called[0] = True
                raise AssertionError("stage.run 不应被调用")

            fake_stages = [_fake_stage_factory("S1_fake", run_behavior, [output_file])]
            buf = io.StringIO()
            with mock.patch("swebench_exp_lite.pipeline.runner.STAGES", fake_stages):
                with redirect_stdout(buf):
                    from swebench_exp_lite.pipeline.runner import run_pipeline
                    run_pipeline(ctx)
            self.assertFalse(run_called[0], "已 done 的 stage 不应被调 run()")
            self.assertIn("[skip] S1_fake", buf.getvalue())
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_resume_reruns_done_stage_when_outputs_missing(self):
        """已 done 但产物缺失（人为删除）→ 重跑 → run() 创建产物。"""
        tmp = tempfile.mkdtemp(prefix="runner_resume_rerun_")
        try:
            ctx = _make_ctx(Path(tmp))
            # manifest 记 done，但 output_file 不存在
            output_file = ctx.task_dir / "fake_output_missing.txt"
            ctx.manifest.mark_done("S1_fake", outputs=[str(output_file)])

            run_called = [False]

            def run_behavior():
                run_called[0] = True
                # 模拟真实 stage：创建产物文件
                output_file.write_text("produced", encoding="utf-8")

            fake_stages = [_fake_stage_factory("S1_fake", run_behavior, [output_file])]
            with mock.patch("swebench_exp_lite.pipeline.runner.STAGES", fake_stages):
                with redirect_stdout(io.StringIO()):
                    from swebench_exp_lite.pipeline.runner import run_pipeline
                    run_pipeline(ctx)
            self.assertTrue(run_called[0], "产物缺失时应重跑")
            self.assertEqual(ctx.manifest.statuses().get("S1_fake"), "done")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestPipelineRunnerMissingOutputs(unittest.TestCase):
    """stage.run() 成功但 outputs() 缺失 → StageError 含 '产物缺失'。"""

    def test_missing_outputs_raises_stage_error(self):
        tmp = tempfile.mkdtemp(prefix="runner_missing_")
        try:
            ctx = _make_ctx(Path(tmp))
            output_file = ctx.task_dir / "should_not_exist.txt"

            # stage.run 成功（不报错），但 output_file 不存在
            fake_stages = [_fake_stage_factory("S1_fake", lambda: None, [output_file])]
            with mock.patch("swebench_exp_lite.pipeline.runner.STAGES", fake_stages):
                from swebench_exp_lite.pipeline.runner import run_pipeline
                with self.assertRaises(StageError) as ctx_exc:
                    run_pipeline(ctx)
            self.assertIn("产物缺失", str(ctx_exc.exception))
            # manifest 应记录 failed
            self.assertEqual(ctx.manifest.statuses().get("S1_fake"), "failed")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestPipelineRunnerStageError(unittest.TestCase):
    """stage.run() 抛 StageError → manifest.mark_failed + re-raise。"""

    def test_stage_error_triggers_mark_failed_and_reraises(self):
        tmp = tempfile.mkdtemp(prefix="runner_stage_err_")
        try:
            ctx = _make_ctx(Path(tmp))

            def run_behavior():
                raise StageError("fake stage failed")

            fake_stages = [_fake_stage_factory("S1_fake", run_behavior, [])]
            with mock.patch("swebench_exp_lite.pipeline.runner.STAGES", fake_stages):
                from swebench_exp_lite.pipeline.runner import run_pipeline
                with self.assertRaises(StageError) as ctx_exc:
                    run_pipeline(ctx)
            self.assertIn("fake stage failed", str(ctx_exc.exception))
            self.assertEqual(ctx.manifest.statuses().get("S1_fake"), "failed")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_generic_exception_triggers_mark_failed(self):
        """守护 [runner.py:50-58](file:///Users/zhangtian/DevWorkspace/swebench-exp-lite/swebench_exp_lite/pipeline/runner.py#L50-L58) 双路 except。"""
        tmp = tempfile.mkdtemp(prefix="runner_gen_")
        try:
            ctx = _make_ctx(Path(tmp))

            def run_behavior():
                raise ValueError("unexpected error")

            fake_stages = [_fake_stage_factory("S1_fake", run_behavior, [])]
            with mock.patch("swebench_exp_lite.pipeline.runner.STAGES", fake_stages):
                from swebench_exp_lite.pipeline.runner import run_pipeline
                with self.assertRaises(ValueError):
                    run_pipeline(ctx)
            self.assertEqual(ctx.manifest.statuses().get("S1_fake"), "failed")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)