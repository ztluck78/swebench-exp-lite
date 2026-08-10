"""Mimo Agent 环境管理。

复用 swebench_exp_lite.runtime 基础设施（共享 mirror + worktree），
MimoResult 继承品牌中立的 AgentResult，并扩展 mimo 特有字段。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from swebench_exp_lite.runtime.base_environment import BaseEnvironment
from swebench_exp_lite.runtime.protocol import AgentResult


@dataclass
class MimoResult(AgentResult):
    """Mimo Agent 运行结果。

    继承 swebench_exp_lite.runtime.protocol.AgentResult 所有字段，
    并扩展 mimo 特有字段（snapshot / tokens / cost / events / session_id / D10 防御标记）。

    mimo 特有字段：
    - snapshot: mimo 自维护的最终 git snapshot SHA（兜底 patch）
    - tokens: token 统计 dict {total, input, output, cache.{write,read}}
    - cost: 实际费用（mimo-auto 走 0 计费）
    - last_text: 最后一次 text 事件的文本
    - events: 完整 NDJSON 事件流（jsonl 单行 dict）
    - session_id: mimo session ID
    - mimo_reason: step_finish.reason（"stop"=成功）
    - mimo_committed: mimo 是否真 auto-commit 了（D10 防御检测）
    - mimo_undone_commits: D10 撤回了几个 commit
    - mimo_json_parse_errors: NDJSON 解析失败的行数
    """
    snapshot: Optional[str] = None
    tokens: Optional[dict] = None
    cost: Optional[float] = None
    last_text: Optional[str] = None
    events: list[dict] = field(default_factory=list)
    session_id: Optional[str] = None
    mimo_reason: Optional[str] = None
    mimo_committed: bool = False
    mimo_undone_commits: int = 0
    mimo_json_parse_errors: int = 0


class MimoEnvironment(BaseEnvironment):
    """Mimo Agent 环境管理器（C9：公共骨架上提 BaseEnvironment）。

    职责：
    1. 仓库准备（基类委托 swebench_exp_lite.runtime.repo；本类仅 override 默认参数）
    2. 工作空间目录创建（基类）
    3. 产物收集（本类保留，含 mimo 特有字段）
    """

    def setup_repo(
        self,
        repo_url: str,
        repo_dir: Path,
        base_commit: str,
        experiment_id: str = "",
        use_shared_cache: bool = True,
    ) -> None:
        """mimo 默认值：experiment_id="" / use_shared_cache=True。"""
        super().setup_repo(
            repo_url, repo_dir, base_commit,
            experiment_id=experiment_id, use_shared_cache=use_shared_cache,
        )

    # prepare_workspace / write_workspace_state / cleanup_worktree 上提
    # BaseEnvironment（C9）；时间字段统一 generated_at。

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
        mimo_reason: Optional[str] = None,
        mimo_committed: bool = False,
        mimo_undone_commits: int = 0,
        mimo_json_parse_errors: int = 0,
    ) -> MimoResult:
        """收集产物，检查 .pred / .traj / .patch 是否存在，并填入 mimo 特有字段。"""
        instance_dir = output_dir / instance_id
        pred_path = instance_dir / f"{instance_id}.pred"
        traj_path = instance_dir / f"{instance_id}.traj"
        patch_path = instance_dir / f"{instance_id}.patch"

        success = pred_path.exists()
        error = None if success else f"产物缺失：{'pred' if not pred_path.exists() else ''}"
        return MimoResult(
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
            mimo_reason=mimo_reason,
            mimo_committed=mimo_committed,
            mimo_undone_commits=mimo_undone_commits,
            mimo_json_parse_errors=mimo_json_parse_errors,
        )
