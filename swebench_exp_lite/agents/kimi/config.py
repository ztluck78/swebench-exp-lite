"""Kimi Agent 配置管理。

v0.2.0+ · SPEC-modularization-round2 C8：公共骨架上提 BaseAgentConfig，
本文件仅保留 kimi 字段声明 + 差异化 hook（原 ~110 行 → ~60 行）。
顶部 sys.path hack 随基类化删除（import 链路统一由调用方/测试入口保证 tools/ 在 sys.path）。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Optional

from swebench_exp_lite.runtime.base_config import BaseAgentConfig


@dataclass
class KimiConfig(BaseAgentConfig):
    """Kimi Agent 配置。

    Attributes:
        model: Kimi 模型名称（默认 kimi-code/kimi-for-coding）
        kimi_bin: Kimi CLI 可执行文件路径（默认从 PATH 查找）
        timeout: 单次执行超时时间（秒，默认 600）
        session_dir: Kimi 会话目录（默认 ~/.kimi-code/sessions/）
        workspace_root: 项目工作区根目录（默认自动检测）
        log_level: 日志级别（默认 INFO）
        max_retries: 失败重试次数（默认 0）
        retry_delay: 重试间隔（秒，默认 5）
    """

    cli_bin_name: ClassVar[str] = "kimi"
    env_prefix: ClassVar[str] = "KIMI"
    bin_field: ClassVar[str] = "kimi_bin"
    default_timeout: ClassVar[int] = 600
    default_model: ClassVar[Optional[str]] = "kimi-code/kimi-for-coding"

    model: str = "kimi-code/kimi-for-coding"
    kimi_bin: Optional[str] = None
    timeout: int = 600
    session_dir: Optional[Path] = None
    workspace_root: Optional[Path] = None
    log_level: str = "INFO"
    max_retries: int = 0
    retry_delay: int = 5

    def _post_init_brand_hook(self) -> None:
        """kimi 特有：session_dir 默认值（~/.kimi-code/sessions）。"""
        if self.session_dir is None:
            self.session_dir = Path.home() / ".kimi-code" / "sessions"
        self.session_dir = Path(self.session_dir)

    @property
    def kimi_bin_path(self) -> Path:
        """获取 Kimi CLI 可执行文件路径。"""
        if self.kimi_bin is None:
            raise RuntimeError(
                "Kimi CLI 未找到。请确认：\n"
                "  1. 已安装：pip install kimi-cli\n"
                "  2. 已登录：kimi auth login\n"
                "  3. kimi 在 PATH 中，或通过 kimi_bin 参数指定路径"
            )
        return Path(self.kimi_bin)

    def _bin_error_message(self) -> str:
        return "Kimi CLI 未找到（kimi_bin 未设置且 PATH 中无 kimi）"

    @classmethod
    def _from_env_extra(cls) -> dict:
        return {
            "session_dir": (
                Path(os.environ["KIMI_SESSION_DIR"])
                if "KIMI_SESSION_DIR" in os.environ else None
            ),
            "log_level": os.environ.get("KIMI_LOG_LEVEL", "INFO"),
        }
