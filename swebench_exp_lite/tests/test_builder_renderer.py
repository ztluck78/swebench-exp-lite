"""Builder / Renderer 单元测试（stdlib unittest，零新依赖）。

覆盖 `TaskBuilder.build_and_render` + 4 个 renderer 函数：
- `render_review`（人工审阅版，含 gold patch）
- `render_agent_data`（CA 数据，**不含** gold_patch 防泄露）
- `render_agent_prompt`（8 步指令）
- `render_jsonl`（12 字段喂 harness）

CA 前缀隔离（ca-）单一来源：[builder.py:39](file:///Users/zhangtian/DevWorkspace/swebench-exp-lite/swebench_exp_lite/builder/builder.py#L39)。

运行方式（仓根，无需 pytest）::

    python -m unittest swebench_exp_lite.tests.test_builder_renderer -v
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from swebench_exp_lite.builder.builder import CA_PREFIX, TaskBuilder
from swebench_exp_lite.builder.models import TaskInstance
from swebench_exp_lite.builder.renderer import (
    dumps_jsonl,
    render_agent_data,
    render_agent_prompt,
    render_jsonl,
    render_review,
)


def _make_task(**overrides) -> TaskInstance:
    """构造 TaskInstance dataclass（不依赖 DB）。"""
    defaults = dict(
        instance_id="test__repo-1234",
        repo="test/repo",
        version="1.0.0",
        language="py",
        created_at="2024-01-01T00:00:00Z",
        split="dev",
        problem_statement="Test problem statement.",
        hints_text="Test hints text.",
        base_commit="abc123def456",
        environment_setup_commit="env_setup_789",
        fail_to_pass=["tests/test_x.py::test_foo", "tests/test_x.py::test_bar"],
        pass_to_pass=["tests/test_y.py::test_baz"],
        gold_patch="diff --git a/src/x.py b/src/x.py\n@@ -1,1 +1,1 @@\n-old\n+new\n",
        test_patch="diff --git a/tests/test_x.py b/tests/test_x.py\n@@ -10,1 +10,1 @@\n-old\n+new\n",
        f2p_count=2,
        p2p_count=1,
        key_files_hint="src/x.py",
        repro_snippet="print('repro')",
        difficulty_human="L1-easy",
        difficulty="hard",
        repo_url="https://github.com/test/repo",
        ssh_url="git@github.com:test/repo.git",
        instance_url="https://github.com/test/repo/issues/1",
        image_x86_64="swebench/sweb.eval.x86_64.test__repo-1234:latest",
        image_arm64="swebench/sweb.eval.arm64.test__repo-1234:latest",
        image_mode_x86_64="pull",
        image_mode_arm64="build",
        namespace_x86_64="swebench",
        namespace_arm64="swebench",
        cache_level_x86_64="env",
        cache_level_arm64="env",
        recommended_timeout=1800,
        patch_size=42,
        test_patch_size=42,
    )
    defaults.update(overrides)
    return TaskInstance(**defaults)


class TestRenderAgentDataAntiLeak(unittest.TestCase):
    """最关键：CA 数据严禁泄露 gold_patch / test_patch / pass_to_pass 完整列表。"""

    def test_render_agent_data_has_seven_keys_no_leak(self):
        task = _make_task()
        data = render_agent_data(task)
        # 必含 7 字段
        expected = {"instance_id", "repo", "base_commit", "problem_statement",
                    "fail_to_pass", "pass_to_pass_count", "hints_text"}
        self.assertEqual(set(data.keys()), expected)
        # 严禁含 gold_patch / test_patch
        self.assertNotIn("gold_patch", data)
        self.assertNotIn("test_patch", data)
        # pass_to_pass 仅给数量，不给完整列表
        self.assertNotIn("pass_to_pass", data)
        self.assertEqual(data["pass_to_pass_count"], task.p2p_count)

    def test_render_agent_data_hints_truncated_to_2000_chars(self):
        long_hints = "x" * 5000
        task = _make_task(hints_text=long_hints)
        data = render_agent_data(task)
        self.assertEqual(len(data["hints_text"]), 2000)


class TestRenderReview(unittest.TestCase):
    """人工审阅版（含答案）。"""

    def test_render_review_includes_gold_patch_section(self):
        task = _make_task()
        md = render_review(task)
        # 含 4. 预期答案（gold patch）段
        self.assertIn("## 四、预期答案", md)
        self.assertIn("gold patch", md)
        self.assertIn("diff --git a/src/x.py", md)

    def test_render_review_includes_test_patch_section(self):
        task = _make_task()
        md = render_review(task)
        self.assertIn("## 五、测试补丁", md)
        self.assertIn("diff --git a/tests/test_x.py", md)

    def test_render_review_includes_seven_section_headers(self):
        task = _make_task()
        md = render_review(task)
        # 7 个二级标题：背景/要求/评分/答案/测试/环境/版本控制
        self.assertGreaterEqual(md.count("\n## "), 7)

    def test_render_review_null_field_falls_back_to_placeholder(self):
        task = _make_task(hints_text=None, repo_url=None)
        md = render_review(task)
        # None 字段渲染为 "（无）"
        self.assertIn("（无）", md)

    def test_render_review_difficulty_display_priority(self):
        task = _make_task(difficulty_human="L1-easy", difficulty="hard")
        md = render_review(task)
        # 优先 difficulty_human
        self.assertIn("L1-easy", md)


class TestRenderAgentPrompt(unittest.TestCase):
    """8 步指令 + task_dir 注入。"""

    def test_render_agent_prompt_has_eight_steps(self):
        task = _make_task()
        md = render_agent_prompt(task, task_dir="/tmp/task")
        # 8 个 STEP
        for i in range(1, 9):
            self.assertIn(f"STEP {i}", md)

    def test_render_agent_prompt_includes_task_dir(self):
        task = _make_task()
        md = render_agent_prompt(task, task_dir="/tmp/my_task")
        self.assertIn("/tmp/my_task", md)
        self.assertIn("TASK_DIR", md)

    def test_render_agent_prompt_task_dir_unknown_marker(self):
        task = _make_task()
        md = render_agent_prompt(task, task_dir=None)
        # task_dir 为 None 时显示占位说明
        self.assertIn("由 orchestrator 注入", md)

    def test_render_agent_prompt_includes_repro_snippet(self):
        task = _make_task(repro_snippet="print('hello')")
        md = render_agent_prompt(task, task_dir="/tmp/t")
        self.assertIn("print('hello')", md)


class TestRenderJsonl(unittest.TestCase):
    """标准 SWE-bench jsonl 行（12 字段）。"""

    def test_render_jsonl_has_twelve_keys(self):
        task = _make_task()
        data = render_jsonl(task)
        expected = {"instance_id", "repo", "base_commit", "patch", "test_patch",
                    "problem_statement", "hints_text", "created_at", "version",
                    "FAIL_TO_PASS", "PASS_TO_PASS", "environment_setup_commit"}
        self.assertEqual(set(data.keys()), expected)

    def test_dumps_jsonl_round_trip(self):
        task = _make_task()
        line = dumps_jsonl(task)
        data = json.loads(line)
        self.assertEqual(data, render_jsonl(task))

    def test_dumps_jsonl_is_single_line(self):
        task = _make_task()
        line = dumps_jsonl(task)
        self.assertNotIn("\n", line)


class TestTaskInstanceProperties(unittest.TestCase):
    """TaskInstance 派生属性：source_dir / difficulty_display。"""

    def test_source_dir_from_gold_patch(self):
        task = _make_task(gold_patch="diff --git a/src/x.py b/src/x.py\n@@ ...")
        self.assertEqual(task.source_dir, "src")

    def test_source_dir_fallback_to_repo_basename(self):
        task = _make_task(gold_patch="", repo="foo/bar")
        self.assertEqual(task.source_dir, "bar")

    def test_source_dir_nested_path_first_segment(self):
        task = _make_task(gold_patch="diff --git a/lib/sub/foo.py b/lib/sub/foo.py\n@@ ...")
        self.assertEqual(task.source_dir, "lib")

    def test_difficulty_display_priority_human_over_auto(self):
        task = _make_task(difficulty_human="L1-easy", difficulty="hard")
        self.assertEqual(task.difficulty_display, "L1-easy")

    def test_difficulty_display_fallback_when_all_empty(self):
        task = _make_task(difficulty_human="", difficulty="")
        self.assertEqual(task.difficulty_display, "（未标注）")

    def test_difficulty_display_fallback_when_difficulty_only(self):
        task = _make_task(difficulty_human="", difficulty="medium")
        self.assertEqual(task.difficulty_display, "medium")


class TestTaskBuilderRender(unittest.TestCase):
    """TaskBuilder.build_and_render 进程内写出（不依赖 DB）。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.task = _make_task()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_render_default_writes_four_files(self):
        builder = TaskBuilder()
        paths = builder.render(self.task, self.tmp)
        task_dir = Path(self.tmp) / self.task.instance_id
        # 4 个文件均存在
        self.assertTrue((task_dir / "review.md").exists())
        self.assertTrue((task_dir / f"{CA_PREFIX}issue.json").exists())
        self.assertTrue((task_dir / f"{CA_PREFIX}task-prompt.md").exists())
        self.assertTrue((task_dir / "task.jsonl").exists())

    def test_render_only_review_writes_one_file(self):
        builder = TaskBuilder()
        paths = builder.render(self.task, self.tmp, only_review=True)
        self.assertEqual(paths, {"review": paths["review"], "issue": None,
                                 "prompt": None, "jsonl": None})
        self.assertTrue(Path(paths["review"]).exists())

    def test_render_only_agent_excludes_review_only(self):
        """only_agent=True 时不写 review.md（task.jsonl 仍写：builder.py:189 `not only_review`）。"""
        builder = TaskBuilder()
        paths = builder.render(self.task, self.tmp, only_agent=True)
        self.assertIsNone(paths["review"])
        # issue / prompt / jsonl 都有
        self.assertIsNotNone(paths["issue"])
        self.assertIsNotNone(paths["prompt"])
        self.assertIsNotNone(paths["jsonl"])

    def test_render_rejects_only_review_and_only_agent(self):
        builder = TaskBuilder()
        with self.assertRaises(ValueError) as ctx:
            builder.render(self.task, self.tmp, only_review=True, only_agent=True)
        self.assertIn("互斥", str(ctx.exception))

    def test_render_uses_ca_prefix_for_agent_files(self):
        """守护 CA 前缀单一来源：[builder.py:39](file:///Users/zhangtian/DevWorkspace/swebench-exp-lite/swebench_exp_lite/builder/builder.py#L39)"""
        builder = TaskBuilder()
        paths = builder.render(self.task, self.tmp)
        self.assertTrue(paths["issue"].endswith(f"{CA_PREFIX}issue.json"))
        self.assertTrue(paths["prompt"].endswith(f"{CA_PREFIX}task-prompt.md"))

    def test_render_ca_issue_json_no_gold_patch(self):
        """CA issue.json 反序列化后严禁含 gold_patch（防泄露）。"""
        builder = TaskBuilder()
        paths = builder.render(self.task, self.tmp)
        with open(paths["issue"], encoding="utf-8") as f:
            data = json.load(f)
        self.assertNotIn("gold_patch", data)
        self.assertNotIn("test_patch", data)


if __name__ == "__main__":
    unittest.main(verbosity=2)