"""Opencode Agent 配置管理。

v0.2.7+ · 基于 mimo_agent 模板克隆，opencode 专属适配：
- cli_bin_name: opencode（npm 全局安装，无需 ~/.mimocode/ 兜底）
- env_prefix: OPENCODE（环境变量覆盖模型/超时等）
- default_model: minimax-cn-coding-plan/MiniMax-M3（PoC 实测本地凭证可用）
- json_output: 默认 True（NDJSON 事件流喂 .traj）
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Optional

from swebench_exp_lite.runtime.base_config import BaseAgentConfig


@dataclass
class OpencodeConfig(BaseAgentConfig):
    """Opencode Agent 配置。

    Attributes:
        model: 模型名称（格式 `provider/model`，如 `minimax-cn-coding-plan/MiniMax-M3`），
            默认从 OPENCODE_MODEL 环境变量读取
        opencode_bin: opencode CLI 可执行文件路径（默认从 PATH 查找 opencode，
            兜底为 `~/.npm-global/bin/opencode`）
        timeout: 单次执行超时时间（秒，默认 1800）
        workspace_root: 项目工作区根目录
        max_retries: 失败重试次数（默认 0）
        retry_delay: 重试间隔（秒，默认 5）
        print_logs: 是否把日志打到 stderr（默认 False，避免与 swebench_exp_lite.runtime.progress 重复处理）
        json_output: 是否用 `--format json` 启用结构化 NDJSON 事件流（默认 True）
        pure: 是否用 `--pure` 不加载外部 plugins（默认 True，agent 集成最佳）
    """

    cli_bin_name: ClassVar[str] = "opencode"
    env_prefix: ClassVar[str] = "OPENCODE"
    bin_field: ClassVar[str] = "opencode_bin"
    default_timeout: ClassVar[int] = 1800
    default_model: ClassVar[Optional[str]] = "minimax-cn-coding-plan/MiniMax-M3"

    model: str = "minimax-cn-coding-plan/MiniMax-M3"
    opencode_bin: Optional[str] = None
    timeout: int = 1800
    workspace_root: Optional[Path] = None
    max_retries: int = 0
    retry_delay: int = 5
    print_logs: bool = False
    json_output: bool = True
    pure: bool = True

    def _find_bin(self) -> Optional[str]:
        """opencode 特有：env OPENCODE_BIN → PATH → ~/.npm-global/bin/opencode 兜底。"""
        return (
            os.environ.get("OPENCODE_BIN")
            or shutil.which(self.cli_bin_name)
            or str(Path.home() / ".npm-global" / "bin" / "opencode")
        )

    def _bin_exists(self) -> bool:
        """opencode 语义：bin 路径必须真实存在。"""
        return bool(self.opencode_bin) and Path(self.opencode_bin).exists()

    @property
    def opencode_bin_path(self) -> Path:
        """获取 opencode CLI 可执行文件路径。"""
        if not self.opencode_bin or not Path(self.opencode_bin).exists():
            raise RuntimeError(
                "opencode CLI 未找到。请确认：\n"
                "  1. 已安装 opencode CLI（`opencode --version` 应可用）\n"
                "  2. opencode 在 PATH 中，或通过 opencode_bin 参数指定路径\n"
                "  3. 或设置 OPENCODE_BIN 环境变量"
            )
        return Path(self.opencode_bin)

    def _bin_error_message(self) -> str:
        return "opencode CLI 未找到（opencode_bin 无效）"

    @classmethod
    def _from_env_extra(cls) -> dict:
        return {
            "print_logs": os.environ.get("OPENCODE_PRINT_LOGS", "false").lower() == "true",
            "json_output": os.environ.get("OPENCODE_JSON_OUTPUT", "true").lower() != "false",
            "pure": os.environ.get("OPENCODE_PURE", "true").lower() != "false",
        }