"""Registry 单元测试（stdlib unittest，零新依赖）。

覆盖 `runtime/registry.py` 的 5 个核心契约：
- `list_runner_names()` 返回 6 项
- `resolve_runner("replay-agent")` 返回 ReplayRunner 实例
- `resolve_runner("<unknown>")` 抛 ValueError 含可用列表
- `ANSWER_ADAPTER` env 覆盖默认
- 默认走 kimi-agent（mock which 通过预检时返 KimiAgentRunner；不 mock 抛 RuntimeError）

运行方式（仓根，无需 pytest）::

    python -m unittest swebench_exp_lite.tests.test_registry -v
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

from swebench_exp_lite.runtime.registry import (
    DEFAULT_RUNNER,
    RUNNERS,
    list_runner_names,
    resolve_runner,
)
from swebench_exp_lite.runtime.replay_runner import ReplayRunner


class TestRegistryStructure(unittest.TestCase):
    """注册表结构 + 默认 runner。"""

    def test_default_runner_is_kimi_agent(self):
        self.assertEqual(DEFAULT_RUNNER, "kimi-agent")

    def test_list_runner_names_has_six(self):
        names = list_runner_names()
        self.assertEqual(len(names), 6)
        expected = {"kimi-agent", "kimi-fast", "qwen-agent", "mimo-agent",
                    "opencode-agent", "replay-agent"}
        self.assertEqual(set(names), expected)

    def test_replay_agent_has_no_preconditions(self):
        self.assertEqual(RUNNERS["replay-agent"]["preconditions"], [])

    def test_kimi_agent_has_kimi_cli_precondition(self):
        # 预检列表非空（kimi CLI 检测）
        self.assertGreater(len(RUNNERS["kimi-agent"]["preconditions"]), 0)

    def test_registry_class_string_format(self):
        # "module:ClassName" 字符串格式（用于懒加载）
        self.assertIn(":", RUNNERS["replay-agent"]["class"])
        module_path, class_name = RUNNERS["replay-agent"]["class"].split(":")
        self.assertEqual(module_path, "swebench_exp_lite.runtime.replay_runner")
        self.assertEqual(class_name, "ReplayRunner")


class TestResolveReplayAgent(unittest.TestCase):
    """replay-agent 路径：零依赖直接返 ReplayRunner。"""

    def test_resolve_replay_agent_returns_replay_runner(self):
        runner = resolve_runner("replay-agent")
        self.assertIsInstance(runner, ReplayRunner)
        self.assertEqual(runner.name, "replay-agent")


class TestResolveUnknown(unittest.TestCase):
    """未知 runner 抛 ValueError。"""

    def test_resolve_unknown_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            resolve_runner("nonexistent-brand")
        msg = str(ctx.exception)
        self.assertIn("unknown runner", msg)
        self.assertIn("replay-agent", msg)  # 可用列表含 replay-agent


class TestResolveEnvOverride(unittest.TestCase):
    """ANSWER_ADAPTER env 覆盖默认值。"""

    def test_answer_adapter_env_overrides_default(self):
        with mock.patch.dict(os.environ, {"ANSWER_ADAPTER": "replay-agent"}):
            runner = resolve_runner(None)
        self.assertIsInstance(runner, ReplayRunner)


class TestResolveDefaultKimiAgent(unittest.TestCase):
    """默认走 kimi-agent：mock which 通过预检时返 KimiAgentRunner。"""

    def test_resolve_default_kimi_agent_with_mock_which(self):
        # mock shutil.which 让所有 CLI 都返路径 → 所有 precondition 通过
        with mock.patch("swebench_exp_lite.runtime.cli_preconditions.which",
                        return_value="/usr/local/bin/cli"):
            try:
                runner = resolve_runner(None)
            except RuntimeError as e:
                # kimi_agent 模块未安装时可能抛 import 错误
                # 但 precondition 应该已经通过
                self.fail(f"precondition 不应阻塞：{e}")
        # 跑通后断言：实例化成功且 name 为 kimi-agent
        self.assertEqual(runner.name, "kimi-agent")

    def test_resolve_default_raises_runtime_error_without_kimi_cli(self):
        """不 mock which → kimi CLI 缺失 → RuntimeError（precondition 未通过）。"""
        # 注意：本测试假设本机未装 kimi CLI。
        # 若本机装了 kimi，本测试会被跳过。
        from shutil import which
        if which("kimi") is not None:
            self.skipTest("本机已装 kimi CLI，跳过 precondition 失败测试")
        with self.assertRaises(RuntimeError) as ctx:
            resolve_runner(None)
        self.assertIn("kimi", str(ctx.exception).lower())


class TestResolveKimiFast(unittest.TestCase):
    """kimi-fast 也是注册的 runner。"""

    def test_resolve_kimi_fast_with_mock(self):
        with mock.patch("swebench_exp_lite.runtime.cli_preconditions.which",
                        return_value="/usr/local/bin/kimi"):
            runner = resolve_runner("kimi-fast")
        # kimi-fast 是 KimiFastRunner
        self.assertTrue(hasattr(runner, "name"))


if __name__ == "__main__":
    unittest.main(verbosity=2)