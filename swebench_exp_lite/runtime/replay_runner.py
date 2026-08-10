"""Replay Runner（快速红线验证专用，SPEC-agent-speedup-20260808 Commit 5 衍生）。

用途：e2e 红线验证的本意是"管道代码能否正常产出可判分 patch 并正确打分"，
而不是"LLM 现场解题"。真实 agent 作答（数分钟~数十分钟 + API 费用 +
网络依赖）对验证本地代码正确性没有增量价值。

本 runner 跳过 LLM/CLI/备仓，直接把该实例的 gold patch（来自 DB tasks 表，
由官方数据集定义、必然 resolved=true）写为 .pred，让 S5/S6/S7 用真实
Docker 打分链路验证其余全部管道：

    python -m swebench_exp_lite run \
        --instance pylint-dev__pylint-7080 --adapter replay-agent

S4 耗时从 ~4-25 分钟降到 <1s；全流程瓶颈只剩 S6 镜像（首次构建/拉取后
本地缓存，后续 ~30-90s）。
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional

from .artifacts import write_pred, write_traj
from .protocol import AgentResult


class ReplayRunner:
    """重放 gold patch 的零依赖 runner（无 CLI 预检、无备仓、无 LLM 调用）。

    协议对齐 KimiFastRunner：name / run() / post_check() / diagnose_failure()。
    """

    name = "replay-agent"

    def __init__(self, model: Optional[str] = None, timeout: Optional[int] = None, **_: Any):
        self.model = model or "replay/gold-patch"
        self.timeout = timeout or 60

    def post_check(self, ctx: Any, output_dir: Path) -> bool:
        return (Path(output_dir) / ctx.instance_id / f"{ctx.instance_id}.pred").exists()

    def diagnose_failure(self, ctx: Any, output_dir: Path) -> str:
        return "（replay-agent 无诊断；gold patch 来自 DB tasks.patch）"

    def run(
        self,
        *,
        instance_id: str,
        issue_path: Path,
        ca_prompt_path: Path,
        repo_dir: Path,
        output_dir: Path,
        repo_root: Optional[Path] = None,
        repo_url: Optional[str] = None,
        base_commit: Optional[str] = None,
        prep_log_path: Optional[Path] = None,
        post_prep_hook: Any = None,
    ) -> AgentResult:
        """把 gold patch 写成 .pred；不备仓、不调 CLI。"""
        start = time.time()
        try:
            patch = _load_gold_patch(instance_id, Path(repo_root) if repo_root else None)
        except Exception as e:  # noqa: BLE001
            return AgentResult(
                success=False, instance_id=instance_id,
                error=f"gold patch 加载失败：{e}",
                elapsed_seconds=time.time() - start,
            )
        if not patch or not patch.strip():
            return AgentResult(
                success=False, instance_id=instance_id,
                error=f"数据集中 {instance_id} 的 patch 字段为空",
                elapsed_seconds=time.time() - start,
            )

        write_pred(output_dir, instance_id, self.model, patch,
                   extra={"replay": "gold"})
        # S7 入库要求 traj 带 log_path——写一个单行 replay 日志占位
        log_path = output_dir / "replay-run.log"
        log_path.write_text(
            f"[replay-agent] 重放 gold patch（{len(patch)} 字节），未调用 LLM\n",
            encoding="utf-8",
        )
        traj = write_traj(
            output_dir, instance_id, self.model,
            adapter=self.name, exit_code=0, log_path=str(log_path),
            elapsed_seconds=time.time() - start, one_shot=True,
        )
        pred_path = output_dir / instance_id / f"{instance_id}.pred"
        return AgentResult(
            success=True, instance_id=instance_id,
            pred_path=pred_path, traj_path=traj,
            elapsed_seconds=time.time() - start, exit_code=0,
        )


def _load_gold_patch(instance_id: str, repo_root: Optional[Path]) -> str:
    """从 data/swe_bench_data/*.jsonl 找 instance_id 的 gold patch。

    直接读 jsonl 而非 DB：runner 调用签名里没有 db_path，而 repo_root 有；
    jsonl 是数据事实源，扫描成本低（每文件数百行）。
    """
    import json as _json

    root = repo_root or Path(__file__).resolve().parents[2]
    data_dir = root / "data" / "swe_bench_data"
    for jsonl in sorted(data_dir.glob("swe-bench-*.jsonl")):
        with jsonl.open(encoding="utf-8") as f:
            for line in f:
                if instance_id not in line:
                    continue
                d = _json.loads(line)
                if d.get("instance_id") == instance_id:
                    return d.get("patch") or ""
    raise FileNotFoundError(
        f"{instance_id} 不在 {data_dir} 的任何 jsonl 中"
    )
