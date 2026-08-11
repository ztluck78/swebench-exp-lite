"""CLI Preconditions 单元测试（stdlib unittest，零新依赖）。

覆盖 `runtime/cli_preconditions.py` 的 4 个工厂（kimi / qwen / mimo / opencode）
的 `_check()` 双分支（which 返回 None / 真实路径）+ `Precondition` 三字段结构。

运行方式（仓根，无需 pytest）::

    python -m unittest swebench_exp_lite.tests.test_cli_preconditions -v
"""
from __future__ import annotations

import unittest
from unittest import mock

from swebench_exp_lite.runtime.cli_preconditions import (
    kimi_cli_available,
    mimo_cli_available,
    opencode_cli_available,
    qwen_cli_available,
)
from swebench_exp_lite.runtime.protocol import Precondition


# 4 个工厂 + 对应 bin 名 + hint 关键字
FACTORIES = [
    (kimi_cli_available, "kimi", "kimi CLI"),
    (qwen_cli_available, "qwen", "Qwen Code CLI"),
    (mimo_cli_available, "mimo", "MiMo"),
    (opencode_cli_available, "opencode", "opencode CLI"),
]


class TestPreconditionStructure(unittest.TestCase):
    """所有工厂返回 Precondition(name, check, hint) 三字段。"""

    def test_all_factories_return_precondition(self):
        for factory, _bin, _hint_kw in FACTORIES:
            with self.subTest(factory=factory.__name__):
                pc = factory()
                self.assertIsInstance(pc, Precondition)
                self.assertTrue(pc.name)
                self.assertTrue(pc.hint)
                self.assertTrue(callable(pc.check))

    def test_all_factory_names_unique(self):
        names = [factory().name for factory, _, _ in FACTORIES]
        self.assertEqual(len(names), len(set(names)))


class TestPreconditionCheck(unittest.TestCase):
    """`_check()` 双分支：which 返回 None → False；返回路径 → True。"""

    def test_check_returns_false_when_which_returns_none(self):
        for factory, bin_name, _hint_kw in FACTORIES:
            with self.subTest(bin=bin_name):
                pc = factory()
                with mock.patch(
                    "swebench_exp_lite.runtime.cli_preconditions.which",
                    return_value=None,
                ):
                    ok, detail = pc.check()
                self.assertFalse(ok)
                self.assertIn(bin_name, detail)

    def test_check_returns_true_when_which_returns_path(self):
        for factory, bin_name, _hint_kw in FACTORIES:
            with self.subTest(bin=bin_name):
                pc = factory()
                with mock.patch(
                    "swebench_exp_lite.runtime.cli_preconditions.which",
                    return_value=f"/usr/local/bin/{bin_name}",
                ):
                    ok, detail = pc.check()
                self.assertTrue(ok)
                self.assertEqual(detail, "")

    def test_check_signature_takes_no_args(self):
        """Precondition.check() 必须无参（v0.1.5+ 品牌中立预检约定）。"""
        for factory, _, _ in FACTORIES:
            with self.subTest(factory=factory.__name__):
                pc = factory()
                # 应能无参调
                try:
                    pc.check()
                except TypeError as e:
                    self.fail(f"check() 必须无参：{e}")


class TestPreconditionHints(unittest.TestCase):
    """hint 字段非空 + 含安装指引。"""

    def test_hints_are_non_empty_and_helpful(self):
        for factory, bin_name, hint_kw in FACTORIES:
            with self.subTest(hint=hint_kw):
                pc = factory()
                # hint 非空
                self.assertTrue(pc.hint)
                # hint 含品牌关键字（大小写不敏感）
                self.assertIn(hint_kw.lower(), pc.hint.lower(),
                              f"hint 应包含 {hint_kw!r}（大小写不敏感），实际：{pc.hint!r}")


class TestPreconditionIntegrationWithRegistry(unittest.TestCase):
    """集成：Precondition 与 registry.RUNNERS 配合——所有真实品牌 runner 都用 _check 验证 CLI。"""

    def test_real_brands_register_preconditions(self):
        from swebench_exp_lite.runtime.registry import RUNNERS
        for brand in ("kimi-agent", "kimi-fast", "qwen-agent",
                      "mimo-agent", "opencode-agent"):
            with self.subTest(brand=brand):
                self.assertGreater(len(RUNNERS[brand]["preconditions"]), 0,
                                   f"{brand} 至少应有 1 个 precondition")
                # 第一个 precondition 应是 CLI 检测
                pc = RUNNERS[brand]["preconditions"][0]
                self.assertIsInstance(pc, Precondition)


if __name__ == "__main__":
    unittest.main(verbosity=2)