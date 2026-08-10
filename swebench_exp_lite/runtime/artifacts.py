"""统一产物写入（品牌中立）。

提供 .pred / .traj / .patch 三类产物的标准化写入。
产物布局：<output_dir>/<instance_id>/<instance_id>.<ext>

所有函数零外部依赖（仅标准库），可被任何 Agent 适配器复用。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.context import TaskContext  # 仅类型注解，避免循环依赖


def _tail_lines(path: Path, n: int = 15) -> str:
    """读日志尾部 n 行（不存在/读失败返回空）。"""
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n:])
    except Exception:  # noqa: BLE001
        return ""


def layout(ctx: "TaskContext") -> tuple[Path, Path]:
    """产物布局计算（品牌中立）。

    v0.1.5+ · SPEC-remove-stages-s4-adapter-20260806 Commit 4：
    替代原 AnswerAdapter.prepare() 里的产物路径计算。
    约定：<agent_dir>/<instance_id>/<instance_id>.<ext>

    Returns:
        (pred_path, traj_path) 元组
    """
    pred_path = ctx.agent_dir / ctx.instance_id / f"{ctx.instance_id}.pred"
    traj_path = ctx.agent_dir / ctx.instance_id / f"{ctx.instance_id}.traj"
    return pred_path, traj_path


def write_pred(
    output_dir: Path,
    instance_id: str,
    model: str,
    patch: str,
    extra: Optional[dict] = None,
) -> Path:
    """写入 .pred 文件（S5 消费的标准格式）。

    Args:
        output_dir: 输出根目录
        instance_id: 实例 ID
        model: 模型名称
        patch: model_patch 内容
        extra: 额外并入 pred JSON 的字段（如 {"rescued": True} 救援标记，
            SPEC-agent-speedup-20260808 G2）

    Returns:
        写入的 .pred 文件路径
    """
    instance_dir = output_dir / instance_id
    instance_dir.mkdir(parents=True, exist_ok=True)
    pred_path = instance_dir / f"{instance_id}.pred"
    pred_content = {
        "instance_id": instance_id,
        "model_name_or_path": model,
        "model_patch": patch or "",
    }
    if extra:
        pred_content.update(extra)
    pred_path.write_text(json.dumps(pred_content, indent=2), encoding="utf-8")
    return pred_path


def write_traj(
    output_dir: Path,
    instance_id: str,
    model: str,
    *,
    adapter: str = "",
    exit_code: int | None = None,
    log_path: str | None = None,
    elapsed_seconds: float = 0.0,
    one_shot: bool = False,
    **extra,
) -> Path:
    """写入 .traj 文件（轨迹元数据）。

    Args:
        output_dir: 输出根目录
        instance_id: 实例 ID
        model: 模型名称
        adapter: 适配器名称（如 kimi-agent / kimi-fast）
        exit_code: 退出码
        log_path: 日志文件路径
        elapsed_seconds: 执行耗时（秒）
        one_shot: 是否一次性 API 调用（不启动 Agent 循环）
        **extra: 额外键值对（并入 JSON）

    Returns:
        写入的 .traj 文件路径
    """
    instance_dir = output_dir / instance_id
    instance_dir.mkdir(parents=True, exist_ok=True)
    traj_path = instance_dir / f"{instance_id}.traj"
    content: dict = {
        "instance_id": instance_id,
        "model": model,
    }
    if adapter:
        content["adapter"] = adapter
    if exit_code is not None:
        content["exit_code"] = exit_code
    if log_path:
        content["log_path"] = str(log_path)
    if elapsed_seconds:
        content["elapsed_seconds"] = elapsed_seconds
    if one_shot:
        content["one_shot"] = True
    content.update(extra)
    traj_path.write_text(json.dumps(content, indent=2), encoding="utf-8")
    return traj_path


def write_patch(output_dir: Path, instance_id: str, patch: str) -> Path | None:
    """写入 .patch 文件（原始 unified diff）。

    Args:
        output_dir: 输出根目录
        instance_id: 实例 ID
        patch: diff 内容

    Returns:
        写入的 .patch 文件路径；如果 patch 为空返回 None
    """
    if not patch:
        return None
    instance_dir = output_dir / instance_id
    instance_dir.mkdir(parents=True, exist_ok=True)
    patch_path = instance_dir / f"{instance_id}.patch"
    patch_path.write_text(patch, encoding="utf-8")
    return patch_path


def write_prediction_jsonl(
    instance_id: str,
    patch_path: Path,
    output_path: Path,
    model: str = "unknown",
) -> None:
    """将 git diff 格式 patch 封装为 SWE-bench harness 可消费的 prediction.jsonl。

    读取 patch 文件内容，写入单行 JSON 的 prediction.jsonl。
    品牌中立：可被任意适配器（kimi/qwen/sweagent）的 S5 阶段复用。

    Args:
        instance_id: 实例 ID
        patch_path: git diff 输出文件路径
        output_path: prediction.jsonl 输出路径
        model: 模型名称
    """
    patch = Path(patch_path).read_text(encoding="utf-8")
    pred = {
        "instance_id": instance_id,
        "model_patch": patch,
        "model_name_or_path": model,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(pred, ensure_ascii=False) + "\n", encoding="utf-8")
