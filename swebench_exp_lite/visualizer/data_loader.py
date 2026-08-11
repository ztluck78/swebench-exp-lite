"""数据加载器：从 output/<iid>/ 既有产物构建 FlowData。

设计原则：
- 只读不写：与管线解耦，不修改任何 manifest / result / 产物
- 容忍缺失：每个文件缺失都返回 None/[]，不抛错，让 UI 单独显示「未运行」
- 复用约定：路径来自 pipeline.context.TaskContext 的 property，不重复硬编码

输出契约：
- FlowData：顶层信息（instance_id / resolved / stages 列表）
- StageData：单阶段信息（status / duration / preview 各阶段专属）

调用：
    flow = load_all(Path("output/pylint-dev__pylint-7080"))
    # flow.stages[0].preview["review_head"] ... 渲染时按 stage 取
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# 教学阶段顺序（与 pipeline.stages.STAGES 一致：S1/S2/S4/S5/S6/S7，无 S3）
STAGE_ORDER = ["S1_build", "S2_prepare", "S4_solve", "S5_patch", "S6_score", "S7_record"]

# 各阶段可读取的产物路径模板（相对 task_dir；产物缺失视为「未运行」）
STAGE_ARTIFACTS: dict[str, list[str]] = {
    "S1_build":   ["ca-issue.json", "ca-task-prompt.md", "review.md", "task.jsonl"],
    "S2_prepare": ["image.json"],
    "S4_solve":   ["agent/{iid}/{iid}.pred", "agent/{iid}/{iid}.traj"],
    "S5_patch":   ["prediction.jsonl", "agent/{iid}.patch",
                   "patch/model.patch", "patch/changed-files.txt", "patch/diff-stat.txt"],
    "S6_score":   ["eval/report.json"],
    "S7_record":  ["result.json"],
}

# 预览文件最大读取行数（防止大产物卡顿渲染）
PREVIEW_HEAD_LINES = 60
PREVIEW_PATCH_LINES = 80
PREVIEW_TAIL_LINES = 200


# --------------------------------------------------------------------------- #
#  数据结构
# --------------------------------------------------------------------------- #
@dataclass
class StageData:
    """单阶段的全部展示数据。"""
    name: str
    status: str = "pending"           # pending / running / done / failed
    started_at: str | None = None
    finished_at: str | None = None
    duration_s: float = 0.0
    command: list[str] | None = None
    outputs: list[str] = field(default_factory=list)
    error: str | None = None
    preview: dict[str, Any] = field(default_factory=dict)


@dataclass
class FlowData:
    """顶层信息（含 6 个阶段 + 汇总评分）。"""
    instance_id: str
    task_dir: str
    run_id: str = ""
    model: str = ""
    adapter: str = ""
    resolved: bool = False
    resolved_pct: float = 0.0
    image: str = ""
    report_source: str = ""
    f2p_pass: int = 0
    f2p_fail: int = 0
    p2p_pass: int = 0
    p2p_fail: int = 0
    stages: list[StageData] = field(default_factory=list)
    generated_at: str = ""
    manifest_missing: bool = False    # True 时只显示提示


# --------------------------------------------------------------------------- #
#  顶层入口
# --------------------------------------------------------------------------- #
def load_all(task_dir: str | Path) -> FlowData:
    """读取 task_dir 下所有产物，构建 FlowData。"""
    task_dir = Path(task_dir)
    instance_id = task_dir.name
    flow = FlowData(instance_id=instance_id, task_dir=str(task_dir))

    manifest_path = task_dir / "manifest.json"
    if not manifest_path.exists():
        flow.manifest_missing = True
        # 即使 manifest 缺失，仍填充空 stages 让 UI 显示骨架
        flow.stages = [StageData(name=n) for n in STAGE_ORDER]
        return flow

    manifest = _read_json(manifest_path)
    flow.run_id = manifest.get("run_id") or ""
    flow.model = manifest.get("model") or ""
    flow.image = (manifest.get("image") or {}).get("image", "")
    flow.generated_at = manifest.get("updated") or ""

    # 顶层 result.json 优先（adapter / resolved / F2P/P2P 都在这里）
    result_path = task_dir / "result.json"
    result = _read_json(result_path)
    if result:
        flow.adapter = result.get("adapter") or ""
        flow.resolved = bool(result.get("resolved", False))
        flow.resolved_pct = float(result.get("resolved_pct", 0.0))
        flow.report_source = result.get("report_source") or ""
        f2p = result.get("fail_to_pass") or {}
        p2p = result.get("pass_to_pass") or {}
        flow.f2p_pass = int(f2p.get("pass", 0))
        flow.f2p_fail = int(f2p.get("fail", 0))
        flow.p2p_pass = int(p2p.get("pass", 0))
        flow.p2p_fail = int(p2p.get("fail", 0))

    # 6 阶段：从 manifest.stages 取状态/时间/产物
    stages_raw = (manifest.get("stages") or {})
    for name in STAGE_ORDER:
        st_raw = stages_raw.get(name) or {}
        stage = StageData(
            name=name,
            status=st_raw.get("status") or "pending",
            started_at=st_raw.get("started"),
            finished_at=st_raw.get("finished"),
            duration_s=_compute_duration(st_raw.get("started"), st_raw.get("finished")),
            outputs=list(st_raw.get("outputs") or []),
            error=st_raw.get("error"),
        )
        # 各阶段专属 preview（产物预览）
        stage.preview = _build_preview(task_dir, name, instance_id)
        # 子命令链（来自 stage.command()，仅展示用；不实际执行）
        stage.command = _stage_command_hint(name)
        flow.stages.append(stage)

    return flow


# --------------------------------------------------------------------------- #
#  工具函数
# --------------------------------------------------------------------------- #
def _read_json(path: Path) -> dict:
    """读 JSON，缺失/损坏返回 {}（绝不抛错）。"""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — 容忍一切 IO/解析错误
        return {}


def _read_text(path: Path, max_lines: int = PREVIEW_HEAD_LINES) -> str:
    """读文本文件前 max_lines 行（防止大产物卡顿）。"""
    if not path.exists():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        head = "\n".join(lines[:max_lines])
        if len(lines) > max_lines:
            head += f"\n\n...（共 {len(lines)} 行，仅显示前 {max_lines} 行）"
        return head
    except Exception:  # noqa: BLE001
        return ""


def _compute_duration(started: str | None, finished: str | None) -> float:
    """从 ISO 时间戳算秒数；任一缺失返回 0。"""
    if not started or not finished:
        return 0.0
    try:
        s = datetime.fromisoformat(started)
        f = datetime.fromisoformat(finished)
        return round((f - s).total_seconds(), 1)
    except Exception:  # noqa: BLE001
        return 0.0


def _stage_command_hint(name: str) -> list[str]:
    """dry-run 命令链（来自 stage.command()），仅用于展示。"""
    # 与 pipeline/stages/*.py 的 command() 方法保持一致
    hints = {
        "S1_build":   ["python", "-c", "TaskBuilder().build_and_render(<iid>, <output>)"],
        "S2_prepare": ["docker", "image", "inspect", "<eval-image>"],
        "S4_solve":   ["python", "-m", "swebench_exp_lite.pipeline.stages.s4_worker", "<config-json>"],
        "S5_patch":   ["python", "-c", "write_prediction_jsonl(<iid>, <patch>, <pred>)"],
        "S6_score":   ["python", "-m", "answer_evaluator.harness.run_evaluation", "-p", "<pred>", ...],
        "S7_record":   ["(进程内聚合：读 report.json → 写 result.json)"],
    }
    return hints.get(name, [])


def _build_preview(task_dir: Path, stage_name: str, instance_id: str) -> dict:
    """各阶段专属预览数据。"""
    builders = {
        "S1_build":   _preview_s1,
        "S2_prepare": _preview_s2,
        "S4_solve":   _preview_s4,
        "S5_patch":   _preview_s5,
        "S6_score":   _preview_s6,
        "S7_record":  _preview_s7,
    }
    fn = builders.get(stage_name)
    return fn(task_dir, instance_id) if fn else {}


def _preview_s1(task_dir: Path, instance_id: str) -> dict:
    """S1 出题预览：ca-issue 7 字段 + review.md 前 60 行 + ca-prompt 头。"""
    issue_path = task_dir / "ca-issue.json"
    issue = _read_json(issue_path)
    return {
        "issue_fields": {k: issue.get(k) for k in (
            "instance_id", "repo", "version", "base_commit",
            "problem_statement_head", "image_path", "docker_image",
        ) if k in issue} if issue else {},
        "issue_raw_keys": sorted(issue.keys()) if issue else [],
        "review_head": _read_text(task_dir / "review.md", PREVIEW_HEAD_LINES),
        "prompt_head": _read_text(task_dir / "ca-task-prompt.md", PREVIEW_HEAD_LINES),
    }


def _preview_s2(task_dir: Path, instance_id: str) -> dict:
    """S2 环境准备预览：image.json 全字段。"""
    image = _read_json(task_dir / "image.json")
    return {"image_info": image} if image else {}


def _preview_s4(task_dir: Path, instance_id: str) -> dict:
    """S4 作答预览：.pred 摘要 + .traj 头。"""
    pred_path = task_dir / "agent" / instance_id / f"{instance_id}.pred"
    pred = _read_json(pred_path)
    preview = {}
    if pred:
        patch = pred.get("model_patch") or ""
        preview["pred_keys"] = sorted(pred.keys())
        preview["patch_bytes"] = len(patch.encode("utf-8"))
        preview["patch_lines"] = patch.count("\n") + 1 if patch else 0
        preview["patch_head"] = _read_text(pred_path, PREVIEW_PATCH_LINES // 2) if False else (
            "\n".join(patch.splitlines()[:PREVIEW_PATCH_LINES // 2])
            if patch else ""
        )
        if len(patch.splitlines()) > PREVIEW_PATCH_LINES // 2:
            preview["patch_head"] += (
                f"\n...（共 {len(patch.splitlines())} 行，仅显示前 {PREVIEW_PATCH_LINES // 2}）"
            )
        preview["exit_code"] = pred.get("exit_code")
    traj_path = task_dir / "agent" / instance_id / f"{instance_id}.traj"
    if traj_path.exists():
        try:
            traj_text = traj_path.read_text(encoding="utf-8", errors="replace")
            traj_lines = traj_text.splitlines()
            preview["traj_steps"] = traj_text.count('"role"')  # 粗略步数
            preview["traj_total_lines"] = len(traj_lines)
        except Exception:  # noqa: BLE001
            pass
    return preview


def _preview_s5(task_dir: Path, instance_id: str) -> dict:
    """S5 补丁规范化预览：model.patch diff 高亮 + changed-files + diff-stat。"""
    patch_path = task_dir / "patch" / "model.patch"
    preview = {}
    if patch_path.exists():
        text = patch_path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        preview["patch_total_lines"] = len(lines)
        preview["patch_head"] = "\n".join(lines[:PREVIEW_PATCH_LINES])
        if len(lines) > PREVIEW_PATCH_LINES:
            preview["patch_head"] += f"\n...（共 {len(lines)} 行，仅显示前 {PREVIEW_PATCH_LINES}）"
    cf = task_dir / "patch" / "changed-files.txt"
    if cf.exists():
        preview["changed_files"] = [
            ln for ln in cf.read_text(encoding="utf-8").splitlines() if ln.strip()
        ]
    stat = task_dir / "patch" / "diff-stat.txt"
    if stat.exists():
        preview["diff_stat"] = stat.read_text(encoding="utf-8").strip()
    preview["prediction_head"] = _read_text(task_dir / "prediction.jsonl", 5)
    return preview


def _preview_s6(task_dir: Path, instance_id: str) -> dict:
    """S6 评分预览：report.json 的 F2P/P2P 统计 + 部分明细。"""
    report_path = task_dir / "eval" / "report.json"
    report = _read_json(report_path)
    if not report:
        return {}
    inst_data = report.get(instance_id, {}) or {}
    tests = inst_data.get("tests_status") or inst_data
    f2p = tests.get("FAIL_TO_PASS") or {}
    p2p = tests.get("PASS_TO_PASS") or {}
    preview = {
        "resolved": inst_data.get("resolved"),
        "patch_exists": inst_data.get("patch_exists"),
        "patch_applied": inst_data.get("patch_successfully_applied"),
        "f2p_pass": f2p.get("success", []),
        "f2p_fail": f2p.get("failure", []),
        "p2p_pass": p2p.get("success", []),
        "p2p_fail": p2p.get("failure", []),
        "f2p_pass_count": len(f2p.get("success", [])),
        "f2p_fail_count": len(f2p.get("failure", [])),
        "p2p_pass_count": len(p2p.get("success", [])),
        "p2p_fail_count": len(p2p.get("failure", [])),
    }
    return preview


def _preview_s7(task_dir: Path, instance_id: str) -> dict:
    """S7 记录预览：result.json 全字段。"""
    return _read_json(task_dir / "result.json")