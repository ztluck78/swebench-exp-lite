"""ReplayRunner 单元测试（stdlib unittest，零新依赖）。

覆盖 `runtime/replay_runner.py` 的 4 个核心契约：
- run() 写出 .pred 含 gold patch（dev split 真实实例）
- 不存在 instance 返回失败 AgentResult
- 空 patch 返回失败 AgentResult
- traj 含 replay-run.log 路径

依赖真实 `data/swe_bench_data/swe-bench-lite-dev.jsonl`（仓内固定）。

运行方式（仓根，无需 pytest）::

    python -m unittest swebench_exp_lite.tests.test_replay_runner -v
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from swebench_exp_lite.runtime.protocol import AgentResult
from swebench_exp_lite.runtime.replay_runner import ReplayRunner, _load_gold_patch


def _make_output_dir() -> Path:
    """构造临时 output_dir（含 agent/<iid>/ 子目录）。"""
    tmp = tempfile.mkdtemp(prefix="replay_test_")
    return Path(tmp)


class TestReplayRunnerSuccess(unittest.TestCase):
    """成功路径：写出 .pred + .traj。"""

    def test_run_writes_pred_with_gold_patch(self):
        output_dir = _make_output_dir()
        try:
            runner = ReplayRunner()
            result = runner.run(
                instance_id="sqlfluff__sqlfluff-1625",
                issue_path=Path("/dev/null"),
                ca_prompt_path=Path("/dev/null"),
                repo_dir=Path("/dev/null"),
                output_dir=output_dir,
                repo_root=None,
            )
            self.assertTrue(result.success, f"应成功：{result.error}")
            pred_path = output_dir / "sqlfluff__sqlfluff-1625" / "sqlfluff__sqlfluff-1625.pred"
            self.assertTrue(pred_path.exists())
            import json
            data = json.loads(pred_path.read_text(encoding="utf-8"))
            self.assertEqual(data["instance_id"], "sqlfluff__sqlfluff-1625")
            self.assertTrue(data["model_patch"])  # gold patch 非空
        finally:
            import shutil
            shutil.rmtree(output_dir, ignore_errors=True)

    def test_run_writes_traj_with_replay_run_log_path(self):
        output_dir = _make_output_dir()
        try:
            runner = ReplayRunner()
            result = runner.run(
                instance_id="sqlfluff__sqlfluff-1625",
                issue_path=Path("/dev/null"),
                ca_prompt_path=Path("/dev/null"),
                repo_dir=Path("/dev/null"),
                output_dir=output_dir,
                repo_root=None,
            )
            self.assertTrue(result.success)
            self.assertIsNotNone(result.traj_path)
            # traj 文件存在
            self.assertTrue(Path(result.traj_path).exists())
            # replay-run.log 存在
            log_path = output_dir / "replay-run.log"
            self.assertTrue(log_path.exists())
            # traj 含 log_path 字段
            import json
            traj_data = json.loads(Path(result.traj_path).read_text(encoding="utf-8"))
            self.assertEqual(traj_data["log_path"], str(log_path))
            # adapter = "replay-agent"
            self.assertEqual(traj_data["adapter"], "replay-agent")
        finally:
            import shutil
            shutil.rmtree(output_dir, ignore_errors=True)


class TestReplayRunnerMissingInstance(unittest.TestCase):
    """失败路径：instance 不在 jsonl 中。"""

    def test_missing_instance_returns_failure_result(self):
        output_dir = _make_output_dir()
        try:
            runner = ReplayRunner()
            result = runner.run(
                instance_id="nonexistent__repo-9999",
                issue_path=Path("/dev/null"),
                ca_prompt_path=Path("/dev/null"),
                repo_dir=Path("/dev/null"),
                output_dir=output_dir,
                repo_root=None,
            )
            self.assertFalse(result.success)
            self.assertIn("gold patch 加载失败", result.error)
            # exit_code 未设置（默认 None）
            self.assertIsNone(result.exit_code)
        finally:
            import shutil
            shutil.rmtree(output_dir, ignore_errors=True)


class TestReplayRunnerEmptyPatch(unittest.TestCase):
    """失败路径：jsonl 中 patch 为空字符串。"""

    def test_empty_patch_returns_failure_result(self):
        # 临时写一个 jsonl 让 _load_gold_patch 返回 ""
        with mock.patch(
            "swebench_exp_lite.runtime.replay_runner._load_gold_patch",
            return_value="",
        ):
            output_dir = _make_output_dir()
            try:
                runner = ReplayRunner()
                result = runner.run(
                    instance_id="any__instance-1",
                    issue_path=Path("/dev/null"),
                    ca_prompt_path=Path("/dev/null"),
                    repo_dir=Path("/dev/null"),
                    output_dir=output_dir,
                    repo_root=None,
                )
                self.assertFalse(result.success)
                self.assertIn("patch 字段为空", result.error)
            finally:
                import shutil
                shutil.rmtree(output_dir, ignore_errors=True)

    def test_whitespace_only_patch_is_treated_as_empty(self):
        """仅空白字符的 patch 也应视为空（[replay_runner.py:69-70](file:///Users/zhangtian/DevWorkspace/swebench-exp-lite/swebench_exp_lite/runtime/replay_runner.py#L69-L70)）。"""
        with mock.patch(
            "swebench_exp_lite.runtime.replay_runner._load_gold_patch",
            return_value="   \n\t  \n",
        ):
            output_dir = _make_output_dir()
            try:
                runner = ReplayRunner()
                result = runner.run(
                    instance_id="any__instance-2",
                    issue_path=Path("/dev/null"),
                    ca_prompt_path=Path("/dev/null"),
                    repo_dir=Path("/dev/null"),
                    output_dir=output_dir,
                    repo_root=None,
                )
                # [replay_runner.py:69] 用 `not patch.strip()` 检测空白 patch
                self.assertFalse(result.success)
                self.assertIn("patch 字段为空", result.error)
            finally:
                import shutil
                shutil.rmtree(output_dir, ignore_errors=True)


class TestReplayRunnerLoadGoldPatch(unittest.TestCase):
    """_load_gold_patch 辅助函数：从 data/swe_bench_data/*.jsonl 读 gold patch。"""

    def test_load_gold_patch_returns_real_patch(self):
        # 不传 repo_root → 自动探测仓根
        patch = _load_gold_patch("sqlfluff__sqlfluff-1625", None)
        self.assertTrue(patch)
        self.assertIn("diff --git", patch)

    def test_load_gold_patch_missing_raises_filenotfounderror(self):
        with self.assertRaises(FileNotFoundError) as ctx:
            _load_gold_patch("nonexistent__repo-9999", None)
        self.assertIn("不在", str(ctx.exception))


class TestReplayRunnerProtocol(unittest.TestCase):
    """ReplayRunner 协议：name / post_check / diagnose_failure / 默认参数。"""

    def test_name_is_replay_agent(self):
        runner = ReplayRunner()
        self.assertEqual(runner.name, "replay-agent")

    def test_default_model_and_timeout(self):
        runner = ReplayRunner()
        self.assertEqual(runner.model, "replay/gold-patch")
        self.assertEqual(runner.timeout, 60)

    def test_post_check_returns_true_when_pred_exists(self):
        output_dir = _make_output_dir()
        try:
            runner = ReplayRunner()
            runner.run(
                instance_id="sqlfluff__sqlfluff-1625",
                issue_path=Path("/dev/null"),
                ca_prompt_path=Path("/dev/null"),
                repo_dir=Path("/dev/null"),
                output_dir=output_dir,
                repo_root=None,
            )
            # post_check：pred_path 存在
            from swebench_exp_lite.runtime.protocol import AgentResult
            ctx_mock = mock.MagicMock()
            ctx_mock.instance_id = "sqlfluff__sqlfluff-1625"
            self.assertTrue(runner.post_check(ctx_mock, output_dir))
        finally:
            import shutil
            shutil.rmtree(output_dir, ignore_errors=True)

    def test_diagnose_failure_returns_replay_specific_message(self):
        runner = ReplayRunner()
        ctx_mock = mock.MagicMock()
        ctx_mock.instance_id = "any"
        diag = runner.diagnose_failure(ctx_mock, Path("/tmp/none"))
        self.assertIn("replay-agent", diag)
        self.assertIn("无诊断", diag)


if __name__ == "__main__":
    unittest.main(verbosity=2)