"""S5 补丁→prediction：把 S4 的 .pred 规范化为 harness 可消费的 prediction.jsonl。

附带产物：agent/<iid>.patch、patch/model.patch、patch/changed-files.txt、
patch/diff-stat.txt（教学解读用）。
"""
from __future__ import annotations

import json
import re

from .base import Stage, StageError


def extract_changed_files(patch: str) -> list[str]:
    """changed-files 统计双模式并集。

    `^\\+\\+\\+ b/` 覆盖常规文本 diff；二进制 untracked 文件经
    `git diff --no-index --binary` 生成的块没有 `+++ ` 行，
    故另取 `^diff --git a/\\S+ b/` 头，两者取并集。
    """
    plus_headers = re.findall(r"^\+\+\+ b/(.+)$", patch, flags=re.MULTILINE)
    git_headers = re.findall(r"^diff --git a/\S+ b/(\S+)$", patch, flags=re.MULTILINE)
    return sorted(set(plus_headers) | set(git_headers))


class S5Patch(Stage):
    name = "S5_patch"

    def command(self, ctx):
        return [
            "python", "-c",
            "from swebench_exp_lite.runtime.artifacts import write_prediction_jsonl; ...",
        ]

    def outputs(self, ctx):
        return [ctx.prediction]

    def run(self, ctx) -> None:
        if ctx.dry_run:
            return
        if not ctx.agent_pred.exists():
            raise StageError(f"S5 输入缺失: {ctx.agent_pred}（S4 未产出？）")
        pred = json.loads(ctx.agent_pred.read_text(encoding="utf-8"))
        patch = pred.get("model_patch", "")

        ctx.agent_patch.write_text(patch, encoding="utf-8")
        ctx.patch_dir.mkdir(parents=True, exist_ok=True)
        (ctx.patch_dir / "model.patch").write_text(patch, encoding="utf-8")
        changed = extract_changed_files(patch)
        ctx.changed_files.write_text(
            "\n".join(changed) + ("\n" if changed else ""), encoding="utf-8")
        ctx.patch_stat.write_text(
            f"files_changed: {len(changed)}\npatch_bytes: {len(patch.encode('utf-8'))}\n",
            encoding="utf-8",
        )

        # 品牌中立：直接调 runtime.artifacts，不走子进程
        from ...runtime.artifacts import write_prediction_jsonl
        write_prediction_jsonl(ctx.instance_id, ctx.agent_patch,
                               ctx.prediction, ctx.model)
        if not patch.strip():
            print("    [S5_patch] 注意：model_patch 为空（harness 将判 unresolved）")
        print(f"    [S5_patch] prediction.jsonl 就绪（patch {len(patch)}B，"
              f"{len(changed)} 个文件）")
