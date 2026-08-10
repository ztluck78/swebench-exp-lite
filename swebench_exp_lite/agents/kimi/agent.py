"""Kimi Agent 主循环（DESIGN Step 3 P2 重构后）。

thin agent——7 步主流程全部继承自 swebench_exp_lite.runtime.base_agent.BaseAgent，
子类只实现必要的差异化点（_invoke_cli / _make_error_result / _log_filename / _ensure_session_dir）。
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from .config import KimiConfig
from .environment import KimiEnvironment, RunResult
from .prompt import KimiPromptBuilder
from .session import KimiSessionManager
from swebench_exp_lite.runtime.base_agent import BaseAgent


class KimiAgent(BaseAgent[RunResult]):
    """Kimi Agent 主类（DESIGN Step 3 P2 重构后）。

    行为完全保留原 KimiAgent——7 步主流程从基类继承，只实现差异化 hook。
    """

    name = "kimi-agent"
    result_class = RunResult

    def __init__(
        self,
        config: Optional[KimiConfig] = None,
        prompt_builder: Optional[KimiPromptBuilder] = None,
    ):
        # BaseAgent.__init__ 接受 config 并设置 self.config
        super().__init__(config=config or KimiConfig.from_env())
        # 5 个标准属性（基类有默认值 None；这里设置 brand 特有的）
        self.environment = KimiEnvironment(self.config.workspace_root)
        self.prompt_builder = prompt_builder or KimiPromptBuilder()
        # kimi 独有：session_manager + session_dir 检查
        self.session_manager = KimiSessionManager(self.config)
        self._ensure_session_dir = self.session_manager.ensure_session_dir

    def _log_filename(self) -> str:
        return "kimi-run.log"

    def _invoke_cli(
        self,
        prompt: str,
        repo_dir: Path,
        log_path: Path,
        timeout: int,
        model: str,
    ) -> tuple[str, int]:
        """调 Kimi CLI 子进程（kimi -p "<prompt>" -m <model>）。"""
        return self._invoke_kimi(prompt, repo_dir, log_path, timeout)

    def _invoke_kimi(
        self,
        prompt: str,
        repo_dir: Path,
        log_path: Path,
        timeout: int,
    ) -> tuple[str, int]:
        """调 kimi CLI 子进程（独立函数保留向后兼容）。

        kimi CLI 没有 --session-dir 选项(0.x/1.x 均无,官方文档确认),重构时
        误加该参数导致 unknown option 直接退出。会话目录管理由 KimiSessionManager
        负责:正常环境用默认 ~/.kimi-code(当前可写),沙箱 EPERM 时经
        _fix_sandbox_session_dir 符号链接兜底。无需在此传 session 目录参数。

        批准标志(-y/--yolo/--auto)与 -p 非交互模式互斥(0.34.0 硬约束),不传。
        """
        cmd = [
            str(self.config.kimi_bin_path),
            "-p", prompt,
            "-m", self.config.model,
        ]
        with open(log_path, "w", encoding="utf-8") as log_f:
            proc = subprocess.run(
                cmd, cwd=str(repo_dir), stdout=log_f,
                stderr=subprocess.STDOUT, timeout=timeout,
            )
        return "", proc.returncode

    @staticmethod
    def _extract_patch_from_repo(repo_dir: Path) -> str:
        """提取 repo 相对 HEAD 的 patch（含 untracked 新增文件，T-01 噪声过滤测试依赖）。

        薄包装：调用基类 brand 中立的 `swebench_exp_lite.runtime.patch.extract_patch_from_repo`。
        该实现已统一处理 tracked diff + untracked 转换 + denylist 噪声过滤
        （__pycache__ / .pytest_cache / .venv / venv / .mypy_cache / .ruff_cache /
        .ipynb_checkpoints / .DS_Store / Thumbs.db / .gitkeep / *.pyc / *.pyo / *.egg-info）。
        返类型从 Optional[str] 转 str（空时返 ""，与原 KimiAgent API 兼容）。

        函数内 import 防御 Step 4 修过的 sys.path 环依赖 bug（base_agent 顶部 import
        在 worker 子进程可能 ModuleNotFoundError）。

        注：t_s4s7 集成测试 + test_spec_audit.py:PatchDenylistTest 2 个测试调用此方法。
        """
        from swebench_exp_lite.runtime.patch import extract_patch_from_repo as _extract_from_repo
        return _extract_from_repo(repo_dir) or ""

    def _make_error_result(self, instance_id: str, error: str, **kwargs) -> RunResult:
        """kimi 用 RunResult（向后兼容）。"""
        return RunResult(
            success=False, instance_id=instance_id, error=error,
            elapsed_seconds=kwargs.get("elapsed_seconds", 0.0),
        )
