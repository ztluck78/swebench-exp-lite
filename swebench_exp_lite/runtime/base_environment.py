"""BaseEnvironment：3 个 brand Environment 的公共骨架（SPEC-modularization-round2 C9）。

qwen/mimo Environment 的 setup_repo / cleanup_worktree / prepare_workspace /
write_workspace_state 一字不差；kimi 仅 workspace_root 探测与产物收集不同。
抽基类后子类保留：Result 类 + collect_artifacts（brand 差异最大处）+ 必要 override。

统一决策（SPEC §2.3.2）：
- workspace-state.json 时间字段统一 ``generated_at``（旧 kimi 写 ``timestamp``，
  qwen/mimo 写 ``generated_at``，双命名漂移已导致 web artifacts 服务读不到
  kimi 运行时间——本基类修复该问题）
- write_workspace_state 写 get_repo_info 全量 + 元数据（kimi 旧输出超集，
  qwen/mimo 旧输出子集 → 统一全量，消费方 brand_runner / web 全兼容）
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar, Optional

from .repo import (
    setup_repo as _ar_setup_repo,
    cleanup_worktree as _ar_cleanup_worktree,
    get_repo_info,
)


class BaseEnvironment:
    """3 brand Environment 公共骨架。

    子类可覆盖的 ClassVar：
        include_output_dir: prepare_workspace 是否额外返回 "output" 顶层目录
            （kimi True；qwen/mimo False）
    """

    include_output_dir: ClassVar[bool] = False

    def __init__(self, workspace_root: Optional[Path] = None):
        self.workspace_root = workspace_root or self._detect_workspace_root()

    def _detect_workspace_root(self) -> Path:
        """默认 Path.cwd()（qwen/mimo 语义）；kimi override 向上找仓根标记。"""
        return Path.cwd()

    # ------------------------------------------------------------------
    # 仓库准备（委托 swebench_exp_lite.runtime.repo）
    # ------------------------------------------------------------------
    def setup_repo(
        self,
        repo_url: str,
        repo_dir: Path,
        base_commit: str,
        experiment_id: str | None = None,
        use_shared_cache: bool = False,
    ) -> Path:
        """准备代码仓库（委托 swebench_exp_lite.runtime.repo.setup_repo；kimi 默认值）。

        qwen/mimo 子类 override 默认值（experiment_id="" / use_shared_cache=True）。
        """
        return _ar_setup_repo(
            repo_url=repo_url,
            repo_dir=repo_dir,
            base_commit=base_commit,
            workspace_root=self.workspace_root,
            experiment_id=experiment_id,
            use_shared_cache=use_shared_cache,
        )

    def cleanup_worktree(self, repo_dir: Path, mirror: Optional[Path] = None) -> None:
        """清理实验 worktree（委托 swebench_exp_lite.runtime.repo.cleanup_worktree）。"""
        return _ar_cleanup_worktree(repo_dir, mirror=mirror)

    # ------------------------------------------------------------------
    # 工作空间
    # ------------------------------------------------------------------
    def prepare_workspace(self, output_dir: Path) -> dict[str, Path]:
        """创建工作空间目录结构（agent/ + logs/；kimi 额外 output 顶层）。"""
        output_dir = Path(output_dir)
        dirs: dict[str, Path] = {}
        if self.include_output_dir:
            dirs["output"] = output_dir
        dirs["agent"] = output_dir / "agent"
        dirs["logs"] = output_dir / "logs"
        for d in dirs.values():
            d.mkdir(parents=True, exist_ok=True)
        return dirs

    def write_workspace_state(
        self,
        repo_dir: Path,
        state_path: Path,
        retention: str = "ephemeral",
        adapter: str = "",
    ) -> dict:
        """写入可发布的工作区摘要（不复制源码）。

        统一版（C9）：get_repo_info 全量 + workspace_path / retention /
        generated_at / adapter。时间字段统一 generated_at（消除旧 kimi
        timestamp 双命名漂移；web artifacts 服务按 generated_at 排序）。
        """
        info = get_repo_info(repo_dir)
        state: dict = {
            **info,
            "workspace_path": str(repo_dir),
            "retention": retention,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "adapter": adapter,
        }
        state_path = Path(state_path)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        return state


__all__ = ["BaseEnvironment"]
