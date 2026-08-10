"""Qwen Agent 环境管理。

复用 swebench_exp_lite.runtime 基础设施（共享 mirror + worktree），
QwenResult 继承品牌中立的 AgentResult。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from swebench_exp_lite.runtime.base_environment import BaseEnvironment
from swebench_exp_lite.runtime.protocol import AgentResult


@dataclass
class QwenResult(AgentResult):
    """Qwen Agent 运行结果。

    继承 swebench_exp_lite.runtime.protocol.AgentResult 所有字段。
    """


class QwenEnvironment(BaseEnvironment):
    """Qwen Agent 环境管理器（C9：公共骨架上提 BaseEnvironment）。

    职责：
    1. 仓库准备（基类委托 swebench_exp_lite.runtime.repo；本类仅 override 默认参数）
    2. 工作空间目录创建（基类）
    3. 产物收集（本类保留）
    """

    def setup_repo(
        self,
        repo_url: str,
        repo_dir: Path,
        base_commit: str,
        experiment_id: str = "",
        use_shared_cache: bool = True,
    ) -> None:
        """qwen 默认值：experiment_id="" / use_shared_cache=True。"""
        super().setup_repo(
            repo_url, repo_dir, base_commit,
            experiment_id=experiment_id, use_shared_cache=use_shared_cache,
        )

    # prepare_workspace / write_workspace_state / cleanup_worktree 上提
    # BaseEnvironment（C9）；时间字段统一 generated_at。

    def collect_artifacts(
        self, output_dir: Path, instance_id: str, model: str,
    ) -> QwenResult:
        """收集产物，检查 .pred / .traj / .patch 是否存在。"""
        instance_dir = output_dir / instance_id
        pred_path = instance_dir / f"{instance_id}.pred"
        traj_path = instance_dir / f"{instance_id}.traj"
        patch_path = instance_dir / f"{instance_id}.patch"

        success = pred_path.exists()
        error = None if success else f"产物缺失：{'pred' if not pred_path.exists() else ''}"
        return QwenResult(
            success=success,
            instance_id=instance_id,
            pred_path=pred_path if pred_path.exists() else None,
            traj_path=traj_path if traj_path.exists() else None,
            patch_path=patch_path if patch_path.exists() else None,
            error=error,
        )
