"""BaseAgentConfig：3 个 brand Config 的公共骨架（SPEC-modularization-round2 C8）。

3 个 brand config.py 原 ~250 行同构代码（bin 查找 / validate 三检 / to_dict /
from_dict / from_env）。抽到基类后子类只保留：dataclass 字段声明 + ClassVar +
差异化 hook。

设计决策（SPEC §9 Q3 = 类属性声明 + hook，字段留子类的变体）：
- 子类**保留自己的 dataclass 字段**（kimi_bin / qwen_bin / mimo_bin 等），
  构造器 API / to_dict 键 / from_dict 兼容性零破坏；
- 基类只声明 ClassVar（cli_bin_name / env_prefix / bin_field / default_timeout /
  default_model）+ 提供共享方法（__post_init__ / validate / to_dict / from_dict /
  from_env）；
- brand 特有字段走 _from_env_extra() / _post_init_brand_hook() hook：
  kimi(session_dir/log_level)、mimo(print_logs/json_output + ~/.mimocode 兜底)。

向后兼容：qwen_bin_path / kimi_bin_path / mimo_bin_path property 由子类保留
（名字与错误文案是 brand 对外契约）。
"""
from __future__ import annotations

import os
import shutil
from dataclasses import fields
from pathlib import Path
from typing import ClassVar, Optional

from .env_utils import safe_int_env


class BaseAgentConfig:
    """3 brand Config 公共骨架。子类是 @dataclass，继承本类的方法。

    子类必须声明的 ClassVar：
        cli_bin_name:    shutil.which 查找目标（"kimi" / "qwen" / "mimo"）
        env_prefix:      from_env 环境变量前缀（"KIMI" / "QWEN" / "MIMO"）
        bin_field:       bin 路径的 dataclass 字段名（"kimi_bin" 等）
        default_timeout: timeout 默认值（kimi/qwen 600，mimo 1800）
        default_model:   model 默认值（仅 kimi 非 None）
    """

    cli_bin_name: ClassVar[str] = ""
    env_prefix: ClassVar[str] = ""
    bin_field: ClassVar[str] = ""
    default_timeout: ClassVar[int] = 600
    default_model: ClassVar[Optional[str]] = None

    # ── 构造后处理 ──────────────────────────────────────────────
    def __post_init__(self):
        if getattr(self, self.bin_field) is None:
            setattr(self, self.bin_field, self._find_bin())
        self._post_init_brand_hook()
        if getattr(self, "workspace_root", None):
            self.workspace_root = Path(self.workspace_root)

    def _find_bin(self) -> Optional[str]:
        """从 PATH 查找 CLI（mimo override：env → PATH → ~/.mimocode/bin 兜底）。"""
        return shutil.which(self.cli_bin_name)

    def _post_init_brand_hook(self) -> None:
        """brand 特有构造后处理（kimi: session_dir 默认值；默认 no-op）。"""

    # ── 校验 ────────────────────────────────────────────────────
    def validate(self) -> list[str]:
        """验证配置，返回错误列表（timeout>0 / max_retries>=0 / bin 存在）。"""
        errors = []
        if not self._bin_exists():
            errors.append(self._bin_error_message())
        if self.timeout <= 0:
            errors.append(f"超时时间必须为正数（当前：{self.timeout}）")
        if self.max_retries < 0:
            errors.append(f"重试次数不能为负数（当前：{self.max_retries}）")
        return errors

    def _bin_exists(self) -> bool:
        """bin 可用性判定（kimi/qwen: 非 None；mimo override: 路径存在）。"""
        return bool(getattr(self, self.bin_field))

    def _bin_error_message(self) -> str:
        return f"{self.cli_bin_name} CLI 未找到（{self.bin_field} 无效）"

    # ── 序列化 ──────────────────────────────────────────────────
    def to_dict(self) -> dict:
        """转字典（Path → str；字段来自子类 dataclass 声明）。"""
        out = {}
        for f in fields(self):
            v = getattr(self, f.name)
            if isinstance(v, Path):
                v = str(v)
            out[f.name] = v
        return out

    @classmethod
    def from_dict(cls, data: dict):
        """从字典创建（忽略未知键）。"""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_env(cls):
        """从环境变量创建配置（{prefix}_* 命名；brand 特有字段走 hook）。"""
        prefix = cls.env_prefix
        raw_model = os.environ.get(f"{prefix}_MODEL")
        kwargs = {
            "model": cls.default_model if raw_model is None else raw_model,
            cls.bin_field: os.environ.get(f"{prefix}_BIN"),
            "timeout": safe_int_env(f"{prefix}_TIMEOUT", cls.default_timeout),
            "workspace_root": (
                Path(os.environ[f"{prefix}_WORKSPACE_ROOT"])
                if f"{prefix}_WORKSPACE_ROOT" in os.environ else None
            ),
            "max_retries": safe_int_env(f"{prefix}_MAX_RETRIES", 0),
            "retry_delay": safe_int_env(f"{prefix}_RETRY_DELAY", 5),
        }
        kwargs.update(cls._from_env_extra())
        return cls(**kwargs)

    @classmethod
    def _from_env_extra(cls) -> dict:
        """brand 特有 env 字段（kimi: session_dir/log_level；mimo: print_logs/json_output）。"""
        return {}


__all__ = ["BaseAgentConfig"]
