"""品牌中立的 Prompt 构造器（DESIGN §1 优化 #2）。

3 adapter 中 qwen + mimo 的 PromptBuilder 100% 同构（69 行同款），
抽到 swebench_exp_lite.runtime 后两者共用。kimi_agent 因为有 Jinja2 模板差异，
仍保留自己的 PromptBuilder，但可以基于本基类扩展。

使用方式：
    from swebench_exp_lite.runtime.prompt import StandardPromptBuilder
    builder = StandardPromptBuilder()
    prompt = builder.build_prompt(issue_path, ca_prompt_path)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


class StandardPromptBuilder:
    """标准 Prompt 构造器（qwen + mimo 共用基类）。

    行为契约：
    1. ca_prompt_path 存在时自动追加"环境提示"段（venv 路径）后返回
    2. 否则从 issue.json 构造基础 prompt
    3. issue.json 缺失关键字段时用占位文本

    3 adapter 行为对齐：
    - qwen: 复用本类
    - mimo: 复用本类
    - kimi: 自有 PromptBuilder（KimiPromptBuilder），env hint 逻辑同源（marker 一致）
    """

    # ca_prompt_path 里追加"环境提示"段的 marker（与 KimiPromptBuilder 同步）。
    # 幂等：build_prompt 多次调用不会重复注入。
    ENV_HINT_MARKER = "<!-- ENV-HINT:autoinjected -->"

    def build_prompt(
        self,
        issue_path: Path,
        ca_prompt_path: Optional[Path] = None,
    ) -> str:
        """构造提示词。

        优先使用 ca-task-prompt.md（由 assessment-builder 生成），
        然后从 issue.json 构造。
        """
        if ca_prompt_path and ca_prompt_path.exists():
            prompt_text = ca_prompt_path.read_text(encoding="utf-8")
            return self._inject_env_hint(prompt_text, ca_prompt_path)

        if not issue_path.exists():
            raise FileNotFoundError(f"issue.json 不存在：{issue_path}")

        issue = json.loads(issue_path.read_text(encoding="utf-8"))
        return self._build_from_issue(issue)

    @staticmethod
    def _infer_venv_path(ca_prompt_path: Path) -> Optional[Path]:
        """从 ca-task-prompt.md 路径推断预装 venv 路径。

        优先读 env_ready.json（S2 统一准备后准确路径）；
        fallback 到旧路径推断（兼容 S4 fallback preinstall）。
        """
        try:
            instance_id = ca_prompt_path.parent.name
            project_root = ca_prompt_path.parent.parent.parent

            # 优先：读 env_ready.json（S2 统一准备后准确路径）
            env_ready = project_root / "runtime-cache" / "env_ready" / f"{instance_id}.json"
            if env_ready.exists():
                import json
                ready = json.loads(env_ready.read_text(encoding="utf-8"))
                venv_path = ready.get("venv_path", "")
                if venv_path and Path(venv_path).exists():
                    return Path(venv_path)

            # fallback：旧路径推断（S4 fallback preinstall）
            venv_dir = project_root / "runtime-cache" / "venvs" / instance_id
            if (venv_dir / "bin").is_dir():
                return venv_dir
            return None
        except (AttributeError, IndexError, json.JSONDecodeError):
            return None

    def _inject_env_hint(self, prompt_text: str, ca_prompt_path: Path) -> str:
        """在 ca-task-prompt.md 末尾追加"环境提示"段（幂等）。

        动机与 KimiPromptBuilder._inject_env_hint 一致：
        S4 preinstall 会在 runtime-cache/venvs/<id>/ 建好 venv，
        但 Agent 读 ca-task-prompt.md 后看不到这条信息 → 误用 .venv → 浪费 wall_time
        装包甚至撞 s4_hard_timeout。

        幂等性：检查 ENV_HINT_MARKER 已存在则跳过，可重复 build_prompt。
        """
        if self.ENV_HINT_MARKER in prompt_text:
            return prompt_text  # 已注入，不重复

        venv_dir = self._infer_venv_path(ca_prompt_path)
        if venv_dir is None:
            return prompt_text  # 推不出 venv 路径（或不存在），不注入

        try:
            worktree = ca_prompt_path.parent.parent.parent / "runtime-cache" / "worktrees" / ca_prompt_path.parent.name
            worktree_hint = f"\n- 仓库 worktree: `{worktree}`" if worktree.is_dir() else ""
        except (AttributeError, IndexError):
            worktree_hint = ""

        env_hint = (
            f"\n{self.ENV_HINT_MARKER}\n\n"
            f"## 环境提示（S4 preinstall 自动追加 · Agent 不要 pip install）\n\n"
            f"S4 preinstall 已为本次任务建好 venv，**直接用这个 venv 跑测试**，不要再去 pip install：\n"
            f"- VENV: `{venv_dir}`\n"
            f"- 激活: `source \"$VENV/bin/activate\"`（或直接用 `$VENV/bin/python` / `$VENV/bin/pytest`）{worktree_hint}\n"
            f"- venv 里已装本任务仓库及其所有依赖（含 numpy/pandas/matplotlib/pytest/django 等）\n"
            f"- 若仍 `ModuleNotFoundError: No module named 'xxx'`：\n"
            f"  - 先 `cat pyproject.toml | grep dependencies` 看实际依赖名（不一定是 `xxx`）\n"
            f"  - 必要时才 `pip install`（但先看是不是 Python 版本不兼容 — 例如 Python 3.13+ 删除了 `cgi`，django 4.1 等老仓库需要切 Python 3.9–3.12）\n\n"
            f"不要从头建 venv 或跑 `pip install -e .` —— preinstall 已 best-effort 完成。\n"
        )

        return prompt_text.rstrip() + "\n" + env_hint

    @staticmethod
    def _build_from_issue(issue: dict) -> str:
        """从 issue 字典构造提示词。"""
        parts = []
        if "instance_id" in issue:
            parts.append(f"实例 ID：{issue['instance_id']}")
        if "repo" in issue:
            parts.append(f"仓库：{issue['repo']}")
        if "base_commit" in issue:
            parts.append(f"基线 commit：{issue['base_commit']}")

        header = "\n".join(f"- {p}" for p in parts) if parts else ""
        problem = issue.get("problem_statement", "（无问题描述）")

        return f"""## 任务信息

{header}

## 问题描述

{problem}

你是一个专业的软件工程师。请按照以下流程完成任务：
0. 环境探查（务必先做，不要直接 pip install）：
   - 看 pyproject.toml 的 dependencies 段，确认任务仓库需要哪些包（matplotlib/pandas/numpy/pytest 等）。
   - 看 `runtime-cache/venvs/<instance_id>/` 是否已存在预装 venv：
     * 存在 → `source $VENV/bin/activate`，后续所有 python/pytest 用这个 venv。
     * 不存在 → 才考虑 `pip install -e .`。
   - sanity check：`python -c "import <top_module>"` 确认能用。
   提示：S4 preinstall 已在 runtime-cache/venvs/<instance_id>/ 建好带依赖的 venv；
         反复 pip install 是 wall_time 的最大浪费。
1. 理解任务：阅读问题描述，理解 bug 的表现和期望行为
2. 探索代码库：定位相关代码文件，理解代码结构和逻辑
3. 复现问题：编写最小化复现脚本，确认 bug 存在
4. 分析根因：追踪代码执行路径，找到问题的根本原因
5. 实施修复：做最小化的代码修改，只改源码文件，不修改测试文件
6. 验证修复：重新运行复现脚本和相关测试
7. 输出补丁：运行 `git diff` 输出完整的 unified diff

约束：只修改源码文件，不添加新文件，不执行 git commit。"""
