"""Opencode Agent 主循环。

基于 mimo_agent 模板克隆，opencode 专属适配：
- _invoke_cli 拼接 `opencode run <prompt> --dir <repo> -m <model> --format json --auto [--pure]`
- _parse_output 走 opencode NDJSON 事件流解析
- 无 D10/D4 防御（opencode 不 auto-commit，PoC 2026-08-09 实测验证）

完整调用格式（实测 2026-08-09）：
    opencode run "<prompt>" --dir <repo> -m <model> --format json --auto [--pure]
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

from .config import OpencodeConfig
from .environment import OpencodeEnvironment, OpencodeResult
from ._opencode_json import OpencodeJsonParseResult, parse_opencode_json_stream
from .prompt import OpencodePromptBuilder
from swebench_exp_lite.runtime.base_agent import BaseAgent
from swebench_exp_lite.runtime.proc import run_cmd as _ar_run_cmd


class OpencodeAgent(BaseAgent[OpencodeResult]):
    """Opencode Agent 主类。

    7 步主流程继承自 swebench_exp_lite.runtime.base_agent.BaseAgent，
    仅实现 opencode 差异化的 4 个 hook：_invoke_cli / _parse_output /
    _write_pred_and_traj / _make_error_result。
    """
    name = "opencode-agent"
    result_class = OpencodeResult

    def __init__(
        self,
        config: Optional[OpencodeConfig] = None,
        prompt_builder: Optional[OpencodePromptBuilder] = None,
    ):
        super().__init__(config=config or OpencodeConfig.from_env())
        self.environment = OpencodeEnvironment(self.config.workspace_root)
        self.prompt_builder = prompt_builder or OpencodePromptBuilder()

    def _log_filename(self) -> str:
        return "opencode-stream.jsonl"

    def _pre_invoke_brand_hook(self, repo_dir, timeout, model) -> dict:
        """opencode 特有：调 CLI 前记录 base_commit（patch 提取用）。

        Returns:
            {"base_commit": "abc123"} —— 供后续 git diff base_commit 用
        """
        base_commit = _ar_run_cmd(
            ["git", "rev-parse", "HEAD"], cwd=repo_dir, timeout=30, check=False,
        )
        return {"base_commit": base_commit.stdout.strip() if base_commit.returncode == 0 else None}

    def _invoke_cli(
        self,
        prompt: str,
        repo_dir: Path,
        log_path: Path,
        timeout: int,
        model: str,
    ) -> tuple[str, int]:
        """调 opencode CLI 子进程。

        命令格式：opencode run <prompt> --dir <repo> -m <model> --format json --auto [--pure]
        """
        cmd = [
            str(self.config.opencode_bin_path),
            "run", prompt,  # 位置参数
            "--dir", str(repo_dir),  # 工作目录
            "-m", model,  # provider/model
            "--auto",  # 跳权限确认（非交互）
        ]
        if self.config.json_output:
            cmd.extend(["--format", "json"])  # NDJSON 事件流
        if self.config.pure:
            cmd.append("--pure")  # 不加载外部 plugins
        if self.config.print_logs:
            cmd.append("--print-logs")

        with open(log_path, "w", encoding="utf-8") as log_f:
            proc = subprocess.run(
                cmd, cwd=str(repo_dir), stdout=log_f,
                stderr=subprocess.STDOUT, timeout=timeout,
            )
        # 读 log 取 raw_stdout（_parse_output 需要原始 NDJSON）
        raw_stdout = log_path.read_text(encoding="utf-8", errors="replace")
        return raw_stdout, proc.returncode

    def _parse_output(self, raw_stdout: str, log_path: Path) -> OpencodeJsonParseResult:
        """opencode 特有：解析 NDJSON 事件流。"""
        if self.config.json_output:
            return parse_opencode_json_stream(raw_stdout)
        return OpencodeJsonParseResult()

    def _post_invoke_brand_hook(
        self, repo_dir, ctx_state, raw_stdout, log_path, parse_result,
    ) -> None:
        """opencode 特有：什么都不做。

        与 mimo 不同：
        - 无 D10 防御（opencode 不 auto-commit，PoC 实测验证）
        - 无 D4 清理（opencode 不创建 .mimocode/ 类临时目录）

        patch 提取由基类通过 `git diff base_commit` 自动完成。
        """
        pass

    def _write_pred_and_traj(
        self,
        output_dir, instance_id, model, log_path, returncode,
        start_time, parse_result, patch,
    ) -> None:
        """opencode 特有 override：写 .pred 和 .traj，traj 含 opencode 特有元数据。"""
        import time as _time
        from swebench_exp_lite.runtime.artifacts import write_pred as _write_pred
        from swebench_exp_lite.runtime.artifacts import write_traj as _write_traj
        _write_pred(output_dir, instance_id, model, patch or "")
        extra: dict = {}
        if parse_result is not None and hasattr(parse_result, "as_traj_extra"):
            extra = parse_result.as_traj_extra()
        _write_traj(
            output_dir, instance_id, model,
            adapter=self.name,
            exit_code=returncode,
            log_path=str(log_path),
            elapsed_seconds=_time.time() - start_time,
            **extra,
        )

    def _make_error_result(self, instance_id: str, error: str, **kwargs) -> OpencodeResult:
        """opencode 用 OpencodeResult。"""
        return OpencodeResult(
            success=False, instance_id=instance_id, error=error,
            elapsed_seconds=kwargs.get("elapsed_seconds", 0.0),
        )


# === 兼容导出（外部可能 import） ===
def parse_opencode_json_stream_pub(raw_stdout: str):
    """[兼容] 公开导出。"""
    return parse_opencode_json_stream(raw_stdout)