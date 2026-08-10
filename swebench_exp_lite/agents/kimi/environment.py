"""Kimi Agent 环境管理。

借鉴 SWE-agent 的 SWEEnv 设计，管理本地仓库和产物收集。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from swebench_exp_lite.runtime.base_environment import BaseEnvironment
from swebench_exp_lite.runtime.proc import run_cmd
from swebench_exp_lite.runtime.repo import (
    _shared_mirror_path as _ar_shared_mirror_path,
    _ensure_mirror as _ar_ensure_mirror,
    _mirror_lock_is_stale as _ar_mirror_lock_is_stale,
    get_repo_info,
)
from swebench_exp_lite.runtime.protocol import AgentResult


@dataclass
class RunResult(AgentResult):
    """Kimi Agent 运行结果。

    继承 swebench_exp_lite.runtime.protocol.AgentResult 所有字段。
    Phase 3+ 新增品牌特定字段应在此类声明。
    """


class KimiEnvironment(BaseEnvironment):
    """Kimi Agent 执行环境管理（C9：公共骨架上提 BaseEnvironment）。

    职责：
    1. 仓库准备（克隆/检出到指定 commit）——基类委托 swebench_exp_lite.runtime.repo
    2. 工作空间初始化（创建输出目录）——基类（include_output_dir=True）
    3. 产物收集（.pred / .traj / .patch / 日志）——kimi 多路径探测，本类保留
    4. 环境清理——基类委托
    """

    include_output_dir = True  # kimi 特有：prepare_workspace 额外返回 output 顶层

    def _detect_workspace_root(self) -> Path:
        """kimi 特有：从当前文件向上查找含 pyproject.toml 的目录（qwen/mimo 用 cwd）。

        移植适配：主仓以“向上找 tools/ 目录”定位仓根；本仓包已安装在
        site-packages，改以 pyproject.toml 为仓根标记，找不到回退 cwd。
        """
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "pyproject.toml").is_file():
                return parent
        return Path.cwd()

    def _shared_mirror_path(self, repo_url: str) -> Path:
        """[委托] swebench_exp_lite.runtime.repo._shared_mirror_path。"""
        return _ar_shared_mirror_path(self.workspace_root, repo_url)

    def _ensure_mirror(self, repo_url: str, mirror: Path, base_commit: str) -> None:
        """[委托] swebench_exp_lite.runtime.repo._ensure_mirror。"""
        return _ar_ensure_mirror(repo_url, mirror, base_commit)

    @staticmethod
    def _mirror_lock_is_stale(lock: Path) -> bool:
        """[委托] swebench_exp_lite.runtime.repo._mirror_lock_is_stale。"""
        return _ar_mirror_lock_is_stale(lock)

    # write_workspace_state / prepare_workspace / cleanup_worktree / setup_repo
    # 上提 BaseEnvironment（C9）；时间字段统一 generated_at（旧 timestamp 退役，
    # 修复 web artifacts 服务读不到 kimi 运行时间的问题）。

    def collect_artifacts(
        self,
        output_dir: Path,
        instance_id: str,
        model: str,
    ) -> RunResult:
        """收集 Agent 执行产物。

        Args:
            output_dir: 输出目录
            instance_id: 实例 ID
            model: 模型名称

        Returns:
            RunResult 包含产物路径
        """
        # v0.2.x（R2 重构 b5041ef）起 output_dir 即 agent 目录
        # （worker_entry 传 ctx.agent_dir），与 qwen/mimo 语义一致。
        # 旧布局「output_dir 是实验根、pred 在其 agent/ 子目录」作回退兼容：
        # 旧实验目录重跑收集/审计时不至于误报缺失。
        if (output_dir / "agent").is_dir() and not (
            output_dir / instance_id / f"{instance_id}.pred"
        ).exists():
            agent_dir = output_dir / "agent"
        else:
            agent_dir = output_dir
        log_path = agent_dir / "kimi-run.log"

        # 查找 .pred 文件
        pred_path = agent_dir / instance_id / f"{instance_id}.pred"
        if not pred_path.exists():
            pred_path = agent_dir / f"{instance_id}.pred"

        # 查找 .traj 文件
        traj_path = agent_dir / instance_id / f"{instance_id}.traj"
        if not traj_path.exists():
            traj_path = agent_dir / f"{instance_id}.traj"

        # 查找 .patch 文件
        patch_path = agent_dir / instance_id / f"{instance_id}.patch"
        if not patch_path.exists():
            patch_path = agent_dir / f"{instance_id}.patch"

        # 判断成功状态
        success = False
        error = None

        if pred_path.exists():
            try:
                pred_content = json.loads(pred_path.read_text(encoding="utf-8"))
                patch = pred_content.get("model_patch", "")
                success = patch is not None and len(patch.strip()) > 0
                if not success:
                    error = "model_patch 为空"
            except (json.JSONDecodeError, KeyError) as e:
                error = f"解析 .pred 文件失败：{e}"
        else:
            error = ".pred 文件不存在"

        return RunResult(
            success=success,
            instance_id=instance_id,
            pred_path=pred_path if pred_path.exists() else None,
            traj_path=traj_path if traj_path.exists() else None,
            patch_path=patch_path if patch_path.exists() else None,
            log_path=log_path if log_path.exists() else None,
            error=error,
        )

    def get_repo_info(self, repo_dir: Path) -> dict:
        """L2 去重：委托 swebench_exp_lite.runtime.repo.get_repo_info（行为契约以原 KimiEnvironment 为准）。

        原 42 行重复实现已删除；模块级 ``from swebench_exp_lite.runtime.repo import get_repo_info``
        已被 ``write_workspace_state``（line 105）使用。保留此方法签名以保持向后兼容。
        """
        return get_repo_info(repo_dir)
