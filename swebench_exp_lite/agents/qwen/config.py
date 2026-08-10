"""Qwen Agent 配置管理。

v0.2.0+ · SPEC-modularization-round2 C8：公共骨架上提 BaseAgentConfig，
本文件仅保留 qwen 字段声明（无特有字段；原 ~90 行 → ~45 行）。
qwen_bin_path property 保留做向后兼容别名（AGENTS §3.12 M 项）。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Optional

from swebench_exp_lite.runtime.base_config import BaseAgentConfig


@dataclass
class QwenConfig(BaseAgentConfig):
    """Qwen Agent 配置。

    Attributes:
        model: Qwen 模型名称（默认从 QWEN_MODEL 环境变量读取，兜底不设让 CLI 用默认值）
        qwen_bin: Qwen Code CLI 可执行文件路径（默认从 PATH 查找 qwen）
        timeout: 单次执行超时时间（秒，默认 600）
        workspace_root: 项目工作区根目录
        max_retries: 失败重试次数（默认 0）
        retry_delay: 重试间隔（秒，默认 5）
    """

    cli_bin_name: ClassVar[str] = "qwen"
    env_prefix: ClassVar[str] = "QWEN"
    bin_field: ClassVar[str] = "qwen_bin"
    default_timeout: ClassVar[int] = 600
    default_model: ClassVar[Optional[str]] = "qwen-code"

    model: Optional[str] = "qwen-code"
    qwen_bin: Optional[str] = None
    timeout: int = 600
    workspace_root: Optional[Path] = None
    max_retries: int = 0
    retry_delay: int = 5

    @property
    def qwen_bin_path(self) -> Path:
        """获取 Qwen Code CLI 可执行文件路径。"""
        if self.qwen_bin is None:
            raise RuntimeError(
                "Qwen Code CLI 未找到。请确认：\n"
                "  1. 已安装 Qwen Code CLI\n"
                "  2. qwen 在 PATH 中，或通过 qwen_bin 参数指定路径"
            )
        return Path(self.qwen_bin)

    def _bin_error_message(self) -> str:
        return "Qwen Code CLI 未找到（qwen_bin 未设置且 PATH 中无 qwen）"
