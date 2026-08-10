"""Kimi Agent 提示词构造。

借鉴 SWE-agent 的 Jinja2 模板设计理念，提供结构化的提示词构造。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


class KimiPromptBuilder:
    """Kimi Agent 提示词构造器。

    职责：
    1. 从 issue.json 和 ca-task-prompt.md 构造完整提示词
    2. 支持自定义模板
    3. 注入约束条件和验证标准
    """

    # 默认提示词模板
    DEFAULT_TEMPLATE = """你是一个专业的软件工程师，正在解决一个 GitHub Issue。

## 任务信息

{task_info}

## 问题描述

{problem_statement}

## 任务步骤

{steps}

## 约束条件

{constraints}

## 验证标准

{validation_criteria}

请按照上述步骤完成任务，最终输出 `git diff` 格式的修复补丁。
"""

    # 默认步骤模板
    # STEP 0 是 2026-08-08 mwaskom__seaborn-3010 Kimi 实验复盘后加的兑底版本：
    # Agent 默认看到 .venv 缺包就会走 pip install，但 S4 preinstall 已在
    # runtime-cache/venvs/<instance_id>/ 建好 venv。这个 STEP 0 提示 Agent 先
    # ls ../.. 看 venv 是否预装，避充外重复 pip install 浪费 wall_time。
    DEFAULT_STEPS = """STEP 0 — 环境探查（务必先做，不要直接 pip install）：

   0a) 看一下 pyproject.toml 的 dependencies 段，确认任务仓库需要哪些包（matplotlib/pandas/numpy/pytest 等）。
   0b) 看 `runtime-cache/venvs/<instance_id>/` 是否已存在：
       - 若存在：直接 `source $VENV/bin/activate`，后续所有 python/pytest 命令用这个 venv。
       - 若不存在：才考虑 `pip install -e .`，但优先看是否系统里已有 conda/venv 可复用。
   0c) 跑一次 sanity check：`python -c "import <top_module>"`，确认 venv 真的能用。

   不要跳过 0b。S4 preinstall 已在 runtime-cache/venvs/<instance_id>/ 建好带依赖的 venv，
   反复 pip install 是 wall_time 的最大浪费。

STEP 1 — 理解任务：
   阅读问题描述，理解 bug 的表现和期望行为。

STEP 2 — 探索代码库：
   定位相关代码文件，理解代码结构和逻辑。

STEP 3 — 复现问题：
   编写一个最小化的复现脚本，确认 bug 存在。

STEP 4 — 分析根因：
   追踪代码执行路径，找到问题的根本原因。

STEP 5 — 实施修复：
   做最小化的代码修改，只改源码文件。

STEP 6 — 验证修复：
   重新运行复现脚本，确认 bug 已修复。
   运行相关的测试用例，确保没有引入回归。

STEP 7 — 输出补丁：
   运行 `git diff` 输出完整的修复补丁。"""

    # 默认约束条件
    DEFAULT_CONSTRAINTS = """- 只修改源码文件，不修改测试文件
- 不添加新文件
- 不执行 git commit 或 git add
- 修复必须是最小化的，只解决核心问题"""

    # 默认验证标准
    DEFAULT_VALIDATION_CRITERIA = """- 复现脚本显示 bug 已修复
- 相关测试用例全部通过
- 输出格式为 unified diff（git diff）"""

    def __init__(
        self,
        template: Optional[str] = None,
        steps: Optional[str] = None,
        constraints: Optional[str] = None,
        validation_criteria: Optional[str] = None,
    ):
        self.template = template or self.DEFAULT_TEMPLATE
        self.steps = steps or self.DEFAULT_STEPS
        self.constraints = constraints or self.DEFAULT_CONSTRAINTS
        self.validation_criteria = validation_criteria or self.DEFAULT_VALIDATION_CRITERIA

    # ca-task-prompt.md 里追加"环境提示"段的 marker。
    # 检查这个 marker 避免重复注入（可以重复跑、幂等）。
    # 2026-08-08：统一改为 brand 中立 marker，跟 swebench_exp_lite.runtime.StandardPromptBuilder 一致。
    ENV_HINT_MARKER = "<!-- ENV-HINT:autoinjected -->"

    def build_prompt(
        self,
        issue_path: Path,
        ca_prompt_path: Optional[Path] = None,
    ) -> str:
        """构造完整提示词。

        Args:
            issue_path: issue.json 文件路径
            ca_prompt_path: ca-task-prompt.md 文件路径（可选，优先使用）

        Returns:
            完整的提示词字符串
        """
        # 优先使用 ca-task-prompt.md（由 assessment-builder 生成），
        # 但会自动追加"环境提示"段（避免重复注入有 marker 检查）。
        if ca_prompt_path and ca_prompt_path.exists():
            prompt_text = ca_prompt_path.read_text(encoding="utf-8")
            # 复用 swebench_exp_lite.runtime 的 env hint 注入（统一路径推断）
            from swebench_exp_lite.runtime.prompt import StandardPromptBuilder
            builder = StandardPromptBuilder()
            return builder._inject_env_hint(prompt_text, ca_prompt_path)

        # 从 issue.json 构造提示词
        if not issue_path.exists():
            raise FileNotFoundError(f"issue.json 不存在：{issue_path}")

        issue = json.loads(issue_path.read_text(encoding="utf-8"))
        return self._build_from_issue(issue)

    def _build_from_issue(self, issue: dict) -> str:
        """从 issue 字典构造提示词。"""
        # 提取任务信息
        task_info_parts = []
        if "instance_id" in issue:
            task_info_parts.append(f"- 实例 ID：{issue['instance_id']}")
        if "repo" in issue:
            task_info_parts.append(f"- 仓库：{issue['repo']}")
        if "base_commit" in issue:
            task_info_parts.append(f"- 基线 commit：{issue['base_commit']}")
        if "version" in issue:
            task_info_parts.append(f"- 版本：{issue['version']}")
        task_info = "\n".join(task_info_parts) if task_info_parts else "（无）"

        # 提取问题描述
        problem_statement = issue.get("problem_statement", "（无）")

        # 提取 fail_to_pass 测试
        f2p = issue.get("fail_to_pass", [])
        if isinstance(f2p, str):
            try:
                f2p = json.loads(f2p)
            except json.JSONDecodeError:
                f2p = [f2p]

        # 构造步骤（注入 F2P 测试信息）
        steps = self.steps
        if f2p:
            f2p_tests = "\n".join(f"   - {t}" for t in f2p[:5])  # 最多显示 5 个
            steps += f"\n\nSTEP 8 — 运行 F2P 测试：\n{f2p_tests}"

        # 构造完整提示词
        return self.template.format(
            task_info=task_info,
            problem_statement=problem_statement,
            steps=steps,
            constraints=self.constraints,
            validation_criteria=self.validation_criteria,
        )

    def build_simple_prompt(
        self,
        instance_id: str,
        repo: str,
        problem_statement: str,
        fail_to_pass: list[str],
    ) -> str:
        """构造简单提示词（不依赖文件）。"""
        task_info = f"- 实例 ID：{instance_id}\n- 仓库：{repo}"

        f2p_tests = "\n".join(f"   - {t}" for t in fail_to_pass[:5])
        steps = self.steps
        if f2p_tests:
            steps += f"\n\nSTEP 8 — 运行 F2P 测试：\n{f2p_tests}"

        return self.template.format(
            task_info=task_info,
            problem_statement=problem_statement,
            steps=steps,
            constraints=self.constraints,
            validation_criteria=self.validation_criteria,
        )

    @classmethod
    def from_config(cls, config: dict) -> "KimiPromptBuilder":
        """从配置字典创建构造器。"""
        return cls(
            template=config.get("template"),
            steps=config.get("steps"),
            constraints=config.get("constraints"),
            validation_criteria=config.get("validation_criteria"),
        )

