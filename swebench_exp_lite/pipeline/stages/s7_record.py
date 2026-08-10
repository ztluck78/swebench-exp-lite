"""S7 记录（精简版）：汇总评分结果写 result.json + 打印 %Resolved。

与主仓差异（spec 决策）：不回写 tasks.status、不入 experiments.db；
baseline 相关字段缺省 None（S3 不实现，resolved 相对 gold 测试集判定，
与 baseline 无关）。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .base import Stage, StageError


class S7Record(Stage):
    name = "S7_record"

    def command(self, ctx):
        return None

    def outputs(self, ctx):
        return [ctx.result]

    def run(self, ctx) -> None:
        if ctx.dry_run:
            return
        if not ctx.eval_report.exists():
            raise StageError(f"S7 输入缺失: {ctx.eval_report}（S6 未产出？）")
        result = self._build_result(ctx)
        ctx.result.write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        if ctx.manifest:
            ctx.manifest.mark_done(self.name, outputs=[str(ctx.result)])
        pct = result["resolved_pct"]
        verdict = "RESOLVED" if result["resolved"] else "UNRESOLVED"
        print(f"    [S7_record] {verdict}（%Resolved={pct}）→ {ctx.result}")

    def _build_result(self, ctx) -> dict:
        report = {}
        try:
            report = json.loads(ctx.eval_report.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            report = {}
        inst = report.get(ctx.instance_id, {})
        # harness report 的 F2P/P2P 明细在 tests_status 下；
        # 聚合回退报告无 tests_status 时退回顶层取。
        tests_status = inst.get("tests_status") or inst
        f2p = tests_status.get("FAIL_TO_PASS", {})
        p2p = tests_status.get("PASS_TO_PASS", {})
        resolved = bool(inst.get("resolved", False))

        stages_snapshot = dict(ctx.manifest.statuses()) if ctx.manifest else {}
        stages_snapshot["S7_record"] = "done"

        return {
            "instance_id": ctx.instance_id,
            "run_id": ctx.run_id,
            "model": ctx.model,
            "adapter": ctx.adapter,
            "dataset": ctx.dataset,
            "split": ctx.split,
            "resolved": resolved,
            "resolved_pct": 100.0 if resolved else 0.0,
            "report_source": inst.get("source", "instance_report"),
            "fail_to_pass": {
                "pass": len(f2p.get("success", [])),
                "fail": len(f2p.get("failure", [])),
            },
            "pass_to_pass": {
                "pass": len(p2p.get("success", [])),
                "fail": len(p2p.get("failure", [])),
            },
            "baseline_resolved": None,   # S3 不实现（v1.1 可选 --run-baseline）
            "image": ctx.load_image_name(),
            "stages": stages_snapshot,
            "stage_timings": self._stage_timings(ctx),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _stage_timings(ctx) -> dict:
        """从 manifest 的 started/finished 算各阶段耗时（秒）。"""
        timings: dict = {}
        if not ctx.manifest:
            return timings
        for name, st in ctx.manifest.all_stages().items():
            started, finished = st.get("started"), st.get("finished")
            if started and finished:
                try:
                    s = datetime.fromisoformat(started)
                    f = datetime.fromisoformat(finished)
                    timings[name] = round((f - s).total_seconds(), 1)
                except Exception:  # noqa: BLE001
                    pass
        return timings
