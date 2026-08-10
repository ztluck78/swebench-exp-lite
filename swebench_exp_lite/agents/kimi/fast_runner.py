"""Kimi Fast Runner（v0.1.5+ 从 stages/s4/adapter/kimi.py 拆分 + 独立化为 BaseAgentRunner 子类）。

kimi-fast：一次性出 patch 的骨架适配器（简单任务粗筛通道）。
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.context import TaskContext


class KimiFastRunner:
    """kimi-fast 一次性出 patch 的执行器。

    v0.1.5+ Commit 4 升级：name 类属性（让 resolve_runner() 知道名字）
    + post_check() 默认实现（替代 AnswerAdapter.post_check）。
    """
    name = "kimi-fast"

    def post_check(self, ctx, output_dir) -> bool:
        """产物落地校验：kimi-fast 写出 .pred 在标准布局。"""
        from pathlib import Path as _P
        return (_P(output_dir) / ctx.instance_id / f"{ctx.instance_id}.pred").exists()

    def diagnose_failure(self, ctx, output_dir) -> str:
        """kimi-fast 失败诊断（默认实现就够了）。"""
        return "（kimi-fast runner 默认诊断；详见 logs/S4_solve.log）"

    def __init__(self, model=None, timeout=None, fallback=None):
        self.api_key = os.environ.get("MOONSHOT_API_KEY") or os.environ.get("KIMI_API_KEY")
        self.base_url = os.environ.get("MOONSHOT_BASE_URL", "https://api.kimi.com/coding/v1").rstrip("/")
        self.model = model or os.environ.get("MOONSHOT_MODEL", "kimi-code/kimi-for-coding")
        self.timeout = timeout or int(os.environ.get("KIMI_FAST_TIMEOUT", "300"))
        if fallback is None:
            self.fallback = os.environ.get("KIMI_FAST_FALLBACK", "0") != "0"
        else:
            self.fallback = fallback

    def run(self, ctx, output_dir):
        """执行 kimi-fast 一次性出 patch。"""
        if not self.api_key:
            sub = {"phase": "call_api", "outcome": "soft_failed",
                   "error": "MOONSHOT_API_KEY/KIMI_API_KEY 未设置"}
            self._record_sub_attempt(ctx, sub)
            self._fallback_or_raise(ctx, output_dir, "未设置 MOONSHOT_API_KEY / KIMI_API_KEY，kimi-fast 不可用")
            return

        log_path = output_dir / "kimi-fast.log"
        try:
            prompt = self._build_prompt(ctx)
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(f"[kimi-fast] model={self.model} base_url={self.base_url}\n")
                f.write(f"[kimi-fast] prompt 长度={len(prompt)} 字符\n")
            
            # Phase 1: call_api
            try:
                t0 = time.time()
                content = self._call_api(prompt)
                sub_api = {"phase": "call_api", "outcome": "resolved",
                          "wall_time_seconds": round(time.time() - t0, 1), "model": self.model}
            except Exception as e:
                sub_api = {"phase": "call_api", "outcome": "soft_failed",
                          "error": f"{type(e).__name__}: {e}"}
                self._record_sub_attempt(ctx, sub_api)
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"[kimi-fast] call_api failed: {e}\n")
                self._fallback_or_raise(ctx, output_dir, f"kimi-fast API 失败：{e}")
                return
            self._record_sub_attempt(ctx, sub_api)

            # Phase 2: extract_diff
            try:
                t0 = time.time()
                patch = self._extract_diff(content)
                sub_extract = {"phase": "extract_diff", "outcome": "resolved" if patch else "soft_failed",
                              "wall_time_seconds": round(time.time() - t0, 1),
                              "patch_bytes": len(patch.encode("utf-8"))}
                if not patch:
                    sub_extract["error"] = "未从模型输出中提取到 diff"
            except Exception as e:
                sub_extract = {"phase": "extract_diff", "outcome": "soft_failed",
                              "error": f"{type(e).__name__}: {e}"}
            self._record_sub_attempt(ctx, sub_extract)
            
            if not patch:
                raw_dump = output_dir / "kimi-fast.raw_response.txt"
                try:
                    raw_dump.write_text(content, encoding="utf-8")
                except Exception:
                    pass
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"[kimi-fast] extract_diff failed: 未提取到 diff（原始响应已写入 {raw_dump}，前 500 字符：{content[:500]!r}）\n")
                self._fallback_or_raise(ctx, output_dir, "kimi-fast 未提取到 diff")
                return

            # Phase 3: write_artifacts
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[kimi-fast] 提取到 patch {len(patch)} 字符\n")
            self._write_artifacts(ctx, output_dir, patch, log_path)
            self._record_sub_attempt(ctx, {
                "phase": "write_artifacts", "outcome": "resolved",
                "patch_chars": len(patch),
                "patch_path": str(output_dir / ctx.instance_id / f"{ctx.instance_id}.patch"),
            })
            print(f"    [S4/kimi-fast] 一次性生成 patch 完成（{len(patch)} 字符）")
        except Exception as e:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[kimi-fast] 失败：{e}\n")
            self._record_sub_attempt(ctx, {"phase": "fallback", "outcome": "soft_failed",
                                          "error": f"{type(e).__name__}: {e}"})
            self._fallback_or_raise(ctx, output_dir, f"kimi-fast 执行失败：{e}")

    def _record_sub_attempt(self, ctx, sub_attempt):
        manifest = getattr(ctx, "manifest", None)
        if not manifest:
            return
        existing = manifest.get_stage_raw("S4_solve").get("adapter_attempts", [])
        if existing:
            existing[-1].setdefault("sub_attempts", []).append(sub_attempt)
            manifest.set_stage_meta("S4_solve", adapter_attempts=existing)

    def _fallback_or_raise(self, ctx, output_dir, reason):
        # v0.1.5+ · SPEC-remove-stages-s4-adapter-20260806 Commit 4：
        # 不再走 AnswerAdapter shim，回退直接用 swebench_exp_lite.runtime + run_brand_runner
        if not self.fallback:
            raise RuntimeError(reason)
        print(f"    [warn] {reason}\n    [S4/kimi-fast] 自动回退到 kimi-agent 完整流程")
        from swebench_exp_lite.runtime import resolve_runner
        from swebench_exp_lite.runtime.brand_runner import run_brand_runner, setup_brand_import_paths
        setup_brand_import_paths(ctx.repo_root)
        runner = resolve_runner("kimi-agent")
        run_brand_runner(
            ctx=ctx, output_dir=output_dir, runner=runner,
            post_prep_hook=None,
            brand_display_name="Kimi",
            adapter=None,
        )

    @staticmethod
    def _build_prompt(ctx):
        import json as _json
        issue_path = Path(ctx.task_dir) / "ca-issue.json"
        if not issue_path.exists():
            issue_path = Path(ctx.task_dir) / "issue.json"
        issue = issue_path.read_text(encoding="utf-8") if issue_path.exists() else "{}"
        ca = Path(ctx.ca_prompt)
        ca_text = ca.read_text(encoding="utf-8") if ca.exists() else ""
        return (
            "你是 SWE-bench 解题专家。请一次性给出修复补丁，不要提问。\n"
            "只输出一个 unified diff 代码块（diff --git 开头），不要修改测试文件。\n\n"
            f"## 任务数据（ca-issue.json）\n```json\n{issue}\n```\n\n"
            f"## 任务指令\n{ca_text}\n\n"
            "再次强调：直接输出最终 unified diff，无需解释过程。"
        )

    def _call_api(self, prompt):
        import json as _json
        import urllib.request
        payload = _json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 1.0,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]

    @staticmethod
    def _extract_diff(content):
        m = re.search(r"```(?:diff|patch)?\s*\n(diff --git.*?)```", content, re.DOTALL)
        if m:
            return m.group(1).strip()
        idx = content.find("diff --git")
        if idx >= 0:
            return content[idx:].strip()
        return ""

    def _write_artifacts(self, ctx, output_dir, patch, log_path):
        import json as _json
        instance_dir = output_dir / ctx.instance_id
        instance_dir.mkdir(parents=True, exist_ok=True)
        (instance_dir / f"{ctx.instance_id}.patch").write_text(patch, encoding="utf-8")
        (instance_dir / f"{ctx.instance_id}.pred").write_text(_json.dumps({
            "instance_id": ctx.instance_id, "model_name_or_path": self.model, "model_patch": patch,
        }, indent=2), encoding="utf-8")
        (instance_dir / f"{ctx.instance_id}.traj").write_text(_json.dumps({
            "instance_id": ctx.instance_id, "adapter": "kimi-fast", "model": self.model,
            "one_shot": True, "log_path": str(log_path),
        }, indent=2), encoding="utf-8")
