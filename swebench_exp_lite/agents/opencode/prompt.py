"""Opencode Agent 提示词构造。

行为契约与原 MimoPromptBuilder 100% 一致——通过继承复用基类。
后续如需 opencode 定制（多模板 / 变体），在子类里 override build_prompt。
"""
from __future__ import annotations

from swebench_exp_lite.runtime.prompt import StandardPromptBuilder


class OpencodePromptBuilder(StandardPromptBuilder):
    """Opencode Agent 提示词构造器（继承标准基类）。"""
    pass