"""Kimi Agent 会话管理。

借鉴 SWE-agent 的环境管理设计，处理 Kimi CLI 的会话目录和沙箱限制。
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from .config import KimiConfig


class KimiSessionManager:
    """Kimi CLI 会话管理器。

    职责：
    1. 检测沙箱环境
    2. 管理会话目录（~/.kimi-code/sessions/）
    3. 处理权限问题（沙箱限制）
    4. 提供会话生命周期管理
    """

    def __init__(self, config: KimiConfig):
        self.config = config
        self._is_sandbox: Optional[bool] = None

    @property
    def is_sandbox(self) -> bool:
        """检测是否在沙箱环境中。"""
        if self._is_sandbox is None:
            self._is_sandbox = self._detect_sandbox()
        return self._is_sandbox

    @staticmethod
    def _detect_sandbox() -> bool:
        """检测当前是否在沙箱环境中。

        检测方法：
        1. 检查环境变量（如 QODER_SANDBOX）
        2. 尝试写入 ~/.kimi-code/sessions/ 测试目录
        """
        # 方法 1：检查环境变量
        if os.environ.get("QODER_SANDBOX") or os.environ.get("SANDBOX"):
            return True

        # 方法 2：尝试写入测试目录
        test_dir = Path.home() / ".kimi-code" / "sessions" / ".sandbox_test"
        try:
            test_dir.mkdir(parents=True, exist_ok=True)
            test_dir.rmdir()
            return False
        except (PermissionError, OSError):
            return True

    def check_session_dir(self) -> tuple[bool, Optional[str]]:
        """检查会话目录是否可用。

        Returns:
            (is_available, error_message)
        """
        session_dir = self.config.session_dir

        # 检查目录是否存在
        if not session_dir.exists():
            try:
                session_dir.mkdir(parents=True, exist_ok=True)
                return True, None
            except (PermissionError, OSError) as e:
                return False, f"无法创建会话目录 {session_dir}：{e}"

        # 检查是否可写
        test_file = session_dir / ".write_test"
        try:
            test_file.write_text("test", encoding="utf-8")
            test_file.unlink()
            return True, None
        except (PermissionError, OSError) as e:
            return False, f"会话目录 {session_dir} 不可写：{e}"

    def ensure_session_dir(self) -> Path:
        """确保会话目录可用，如果不可用则尝试修复。

        Returns:
            会话目录路径

        Raises:
            RuntimeError: 如果会话目录不可用且无法修复
        """
        is_available, error = self.check_session_dir()
        if is_available:
            return self.config.session_dir

        # 尝试修复：创建符号链接到工作区内的目录
        if self.is_sandbox:
            return self._fix_sandbox_session_dir()

        raise RuntimeError(
            f"Kimi 会话目录不可用：{error}\n"
            "请确保 ~/.kimi-code/sessions/ 目录存在且可写，"
            "或在正常终端中运行（不在沙箱中）。"
        )

    def _fix_sandbox_session_dir(self) -> Path:
        """在沙箱环境中修复会话目录。

        策略：在工作区内创建会话目录，然后创建符号链接。
        """
        workspace_root = self.config.workspace_root
        if workspace_root is None:
            workspace_root = Path.cwd()

        # 在工作区内创建会话目录
        local_session_dir = workspace_root / ".kimi_sessions"
        local_session_dir.mkdir(parents=True, exist_ok=True)

        # 创建符号链接
        target = self.config.session_dir
        if target.exists() or target.is_symlink():
            target.unlink()

        target.symlink_to(local_session_dir)

        return local_session_dir

    def get_session_id(self, repo_dir: Path) -> str:
        """生成会话 ID（基于仓库路径的哈希）。"""
        import hashlib
        repo_str = str(repo_dir.resolve())
        hash_suffix = hashlib.md5(repo_str.encode()).hexdigest()[:12]
        # 清理路径中的特殊字符
        clean_name = repo_str.replace("/", "_").replace("\\", "_").replace(":", "_")
        # 取最后两级目录
        parts = clean_name.split("_")
        if len(parts) >= 2:
            name = "_".join(parts[-2:])
        else:
            name = clean_name
        return f"wd_{name}_{hash_suffix}"

    def cleanup_sessions(self, max_age_hours: int = 24):
        """清理过期的会话目录。

        Args:
            max_age_hours: 最大保留时间（小时）
        """
        import time
        session_dir = self.config.session_dir
        if not session_dir.exists():
            return

        cutoff = time.time() - (max_age_hours * 3600)
        for item in session_dir.iterdir():
            if item.is_dir() and item.stat().st_mtime < cutoff:
                shutil.rmtree(item, ignore_errors=True)

    def get_session_info(self) -> dict:
        """获取会话目录信息。"""
        session_dir = self.config.session_dir
        info = {
            "session_dir": str(session_dir),
            "exists": session_dir.exists(),
            "is_sandbox": self.is_sandbox,
        }

        if session_dir.exists():
            try:
                sessions = [d.name for d in session_dir.iterdir() if d.is_dir()]
                info["session_count"] = len(sessions)
                info["sessions"] = sessions[:10]  # 最多显示 10 个
            except PermissionError:
                info["error"] = "无法读取会话目录"

        return info