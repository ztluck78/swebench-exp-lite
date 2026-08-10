"""出题模块 · 数据模型（TaskInstance）

单一数据源：两版渲染（审阅版 / 做题版）都从同一个 ``TaskInstance`` 读数据，
确保题目本体（背景 / 要求 / 验证标准）必然一致，差异仅在于呈现形式。

全部字段来自 LiteDB.get() + eval_estimate()，不在模块内做任何派生。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TaskInstance:
    """共享数据源，两个版本从此渲染。

    全部字段来自 LiteDB.get() + eval_estimate()。
    """

    # --- 身份标识 ---
    instance_id: str = ""
    repo: str = ""
    version: str = ""
    language: str = ""
    created_at: str = ""
    split: str = ""

    # --- 问题陈述 ---
    problem_statement: str = ""
    hints_text: str = ""

    # --- 版本控制 ---
    base_commit: str = ""
    environment_setup_commit: str = ""

    # --- 评测标准 ---
    fail_to_pass: list = field(default_factory=list)
    pass_to_pass: list = field(default_factory=list)
    gold_patch: str = ""       # 参考答案（diff）
    test_patch: str = ""       # 测试补丁（diff）
    f2p_count: int = 0
    p2p_count: int = 0

    # --- 环境镜像 ---
    image_x86_64: str = ""
    image_arm64: str = ""
    image_mode_x86_64: str = ""   # pull / build
    image_mode_arm64: str = ""
    namespace_x86_64: str = ""
    namespace_arm64: str = ""
    cache_level_x86_64: str = ""
    cache_level_arm64: str = ""
    recommended_timeout: int = 1800

    # --- 难度评估 ---
    difficulty: str = ""        # easy / medium / hard（自动派生）
    patch_size: int = 0
    test_patch_size: int = 0

    # --- 出题辅助（004 迁移新增，DB 已有） ---
    key_files_hint: str = ""    # 关键文件提示（人工标注 / gold_patch 推断）
    repro_snippet: str = ""     # 复现代码片段（构建时正则提取，可能为空）
    difficulty_human: str = ""  # 人工难度标注（区别于 difficulty 自动派生）

    # --- 外部线索（DB 提供，渲染时使用） ---
    repo_url: str = ""
    ssh_url: str = ""
    instance_url: str = ""

    @property
    def source_dir(self) -> str:
        """Agent prompt 约束用的源码顶层目录（C-14 修正）。

        优先从 gold patch 首个 ``diff --git a/<path>`` 头取第一级目录
        （贴近真实修复位置）；取不到再回退 repo 末段推断（不再凭空写死）。
        例：gold patch 改 ``src/marshmallow/schema.py`` -> ``src``；
        ``pylint-dev/astroid`` 且 patch 无头 -> ``astroid``。
        """
        import re

        if self.gold_patch:
            m = re.search(r"^diff --git a/(\S+)", self.gold_patch, re.MULTILINE)
            if m:
                top = m.group(1).split("/", 1)[0]
                if top:
                    return top
        return self.repo.split("/")[-1] if self.repo else ""

    @property
    def difficulty_display(self) -> str:
        """审阅版展示用的难度：优先人工标注，无则降级为自动派生。"""
        return self.difficulty_human or self.difficulty or "（未标注）"

    def to_dict(self) -> dict:
        """展开为普通 dict（调试 / 序列化用）。"""
        return {
            "instance_id": self.instance_id,
            "repo": self.repo,
            "version": self.version,
            "language": self.language,
            "created_at": self.created_at,
            "split": self.split,
            "base_commit": self.base_commit,
            "environment_setup_commit": self.environment_setup_commit,
            "f2p_count": self.f2p_count,
            "p2p_count": self.p2p_count,
            "difficulty": self.difficulty,
            "difficulty_human": self.difficulty_human,
            "key_files_hint": self.key_files_hint,
            "repro_snippet": self.repro_snippet,
            "image_x86_64": self.image_x86_64,
            "image_arm64": self.image_arm64,
            "recommended_timeout": self.recommended_timeout,
            "source_dir": self.source_dir,
        }
