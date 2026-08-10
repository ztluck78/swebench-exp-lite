"""Opencode Agent 环境管理。

复用 swebench_exp_lite.runtime 基础设施（共享 mirror + worktree），
OpencodeResult 继承品牌中立的 AgentResult，并扩展 opencode 特有字段。

与 mimo 的差异：
- mimo 的 mimo_committed / mimo_undone_commits 等 D10 防御字段：opencode 不需要
  （opencode 不 auto-commit，PoC 2026-08-09 实测验证）
- mimo 的 .mimocode/ 临时目录清理：opencode 不需要
- opencode 特有字段：snapshot（git blob hash，仅供观测）+ has_error（独立 error 事件）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from swebench_exp_lite.runtime.base_environment import BaseEnvironment
from swebench_exp_lite.runtime.protocol import AgentResult


@dataclass
class OpencodeResult(AgentResult):
    """Opencode Agent 运行结果。

    继承 swebench_exp_lite.runtime.protocol.AgentResult 所有字段，
    并扩展 opencode 特有字段（snapshot / tokens / cost / events / session_id / error 标记）。

    opencode 特有字段：
    - snapshot: opencode 自维护的最终 git blob SHA（仅供观测，不用于 patch 提取）
    - tokens: token 统计 dict {total, input, output, reasoning, cache.{write,read}}
    - cost: 实际费用
    - last_text: 最后一次 text 事件的文本
    - events: 完整 NDJSON 事件流（jsonl 单行 dict）
    - session_id: opencode session ID
    - opencode_reason: step_finish.reason（"stop"=成功）
    - opencode_has_error: 是否出现过 error 事件
    - opencode_json_parse_errors: NDJSON 解析失败的行数
    """
    snapshot: Optional[str] = None
    tokens: Optional[dict] = None
    cost: Optional[float] = None
    last_text: Optional[str] = None
    events: list[dict] = field(default_factory=list)
    session_id: Optional[str] = None
    opencode_reason: Optional[str] = None
    opencode_has_error: bool = False
    opencode_json_parse_errors: int = 0


class OpencodeEnvironment(BaseEnvironment):
    """Opencode Agent 环境管理器。

    职责：
    1. 仓库准备（基类委托 swebench_exp_lite.runtime.repo；本类仅 override 默认参数）
    2. 工作空间目录创建（基类）
    3. 产物收集（本类保留，含 opencode 特有字段）
    """

    def setup_repo(
        self,
        repo_url: str,
        repo_dir: Path,
        base_commit: str,
        experiment_id: str = "",
        use_shared_cache: bool = True,
    ) -> None:
        """opencode 默认值：experiment_id="" / use_shared_cache=True。"""
        super().setup_repo(
            repo_url, repo_dir, base_commit,
            experiment_id=experiment_id, use_shared_cache=use_shared_cache,
        )

    def collect_artifacts(
        self,
        output_dir: Path,
        instance_id: str,
        model: str,
        *,
        snapshot: Optional[str] = None,
        tokens: Optional[dict] = None,
        cost: Optional[float] = None,
        last_text: Optional[str] = None,
        events: Optional[list[dict]] = None,
        session_id: Optional[str] = None,
        opencode_reason: Optional[str] = None,
        opencode_has_error: bool = False,
        opencode_json_parse_errors: int = 0,
    ) -> OpencodeResult:
        """收集产物，检查 .pred / .traj / .patch 是否存在，并填入 opencode 特有字段。"""
        instance_dir = output_dir / instance_id
        pred_path = instance_dir / f"{instance_id}.pred"
        traj_path = instance_dir / f"{instance_id}.traj"
        patch_path = instance_dir / f"{instance_id}.patch"

        success = pred_path.exists()
        error = None if success else f"产物缺失：{'pred' if not pred_path.exists() else ''}"
        return OpencodeResult(
            success=success,
            instance_id=instance_id,
            pred_path=pred_path if pred_path.exists() else None,
            traj_path=traj_path if traj_path.exists() else None,
            patch_path=patch_path if patch_path.exists() else None,
            error=error,
            snapshot=snapshot,
            tokens=tokens,
            cost=cost,
            last_text=last_text,
            events=list(events) if events else [],
            session_id=session_id,
            opencode_reason=opencode_reason,
            opencode_has_error=opencode_has_error,
            opencode_json_parse_errors=opencode_json_parse_errors,
        )