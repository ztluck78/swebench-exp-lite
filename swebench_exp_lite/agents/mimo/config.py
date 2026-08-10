"""Mimo Agent 配置管理。

v0.2.0+ · SPEC-modularization-round2 C8：公共骨架上提 BaseAgentConfig，
本文件保留 mimo 字段声明 + 差异化 hook（bin 兜底路径 / print_logs / json_output）。
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Optional

from swebench_exp_lite.runtime.base_config import BaseAgentConfig


@dataclass
class MimoConfig(BaseAgentConfig):
    """Mimo Agent 配置。

    Attributes:
        model: 模型名称（格式 `provider/model`，如 `xiaomi/mimo-v2.5-pro`），
            默认从 MIMO_MODEL 环境变量读取
        mimo_bin: MiMo Code CLI 可执行文件路径（默认从 PATH 查找 mimo，
            兜底为 `~/.mimocode/bin/mimo`）
        timeout: 单次执行超时时间（秒，默认 1800 — mimo 慢，D7 配置）
        workspace_root: 项目工作区根目录
        max_retries: 失败重试次数（默认 0）
        retry_delay: 重试间隔（秒，默认 5）
        print_logs: 是否把日志打到 stderr（默认 False，避免与 swebench_exp_lite.runtime.progress 重复处理）
        json_output: 是否用 `--format json` 启用结构化 NDJSON 事件流（默认 True，D2 决策必做）
    """

    cli_bin_name: ClassVar[str] = "mimo"
    env_prefix: ClassVar[str] = "MIMO"
    bin_field: ClassVar[str] = "mimo_bin"
    default_timeout: ClassVar[int] = 1800
    default_model: ClassVar[Optional[str]] = "xiaomi/mimo-v2.5-pro"

    model: Optional[str] = "xiaomi/mimo-v2.5-pro"
    mimo_bin: Optional[str] = None
    timeout: int = 1800
    workspace_root: Optional[Path] = None
    max_retries: int = 0
    retry_delay: int = 5
    print_logs: bool = False  # 默认关：避免 progress 观测的双重处理
    json_output: bool = True  # D2 决策：默认开 NDJSON 解析，喂 process 评估

    def _find_bin(self) -> Optional[str]:
        """mimo 特有：env MIMO_BIN → PATH → ~/.mimocode/bin/mimo 兜底。"""
        return (
            os.environ.get("MIMO_BIN")
            or shutil.which(self.cli_bin_name)
            or str(Path.home() / ".mimocode" / "bin" / "mimo")
        )

    def _bin_exists(self) -> bool:
        """mimo 语义：bin 路径必须真实存在（kimi/qwen 只查非 None）。"""
        return bool(self.mimo_bin) and Path(self.mimo_bin).exists()

    @property
    def mimo_bin_path(self) -> Path:
        """获取 MiMo Code CLI 可执行文件路径。"""
        if not self.mimo_bin or not Path(self.mimo_bin).exists():
            raise RuntimeError(
                "MiMo Code CLI 未找到。请确认：\n"
                "  1. 已安装 MiMo Code CLI（`mimo --version` 应可用）\n"
                "  2. mimo 在 PATH 中，或通过 mimo_bin 参数指定路径\n"
                "  3. 或设置 MIMO_BIN 环境变量"
            )
        return Path(self.mimo_bin)

    def _bin_error_message(self) -> str:
        return "MiMo Code CLI 未找到（mimo_bin 无效）"

    @classmethod
    def _from_env_extra(cls) -> dict:
        return {
            "print_logs": os.environ.get("MIMO_PRINT_LOGS", "false").lower() == "true",
            "json_output": os.environ.get("MIMO_JSON_OUTPUT", "true").lower() != "false",
        }
