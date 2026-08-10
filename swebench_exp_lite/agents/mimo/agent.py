"""Mimo Agent 主循环（DESIGN Step 3 P4 重构后）。

thin agent——7 步主流程全部继承自 swebench_exp_lite.runtime.base_agent.BaseAgent。
mimo 特有：D10 防御（D11 防御前移到 BaseAgentRunner._post_invoke_brand_hook）、
D4 清理（也在 runner 层），Agent 层只保留：
- _pre_invoke_brand_hook 记录 base_commit（供 post_invoke 用）
- _invoke_cli 调 mimo CLI 子进程
- _parse_output 解析 NDJSON 事件流
- _post_invoke_brand_hook 二次 detect（供 traj 字段）+ （实际 undo 在 runner 层）
- _write_pred_and_traj override 传 mimo 特有元数据（PR-3）
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

from .config import MimoConfig
from .environment import MimoEnvironment, MimoResult
from ._mimo_json import MimoJsonParseResult, parse_mimo_json_stream
from .prompt import MimoPromptBuilder
from swebench_exp_lite.runtime.base_agent import BaseAgent
from swebench_exp_lite.runtime.proc import run_cmd as _ar_run_cmd


class MimoAgent(BaseAgent[MimoResult]):
    """Mimo Agent 主类（DESIGN Step 3 P4 重构后）。

    行为完全保留原 MimoAgent——D10 防御的 undo 部分已前移到
    BaseAgentRunner._post_invoke_brand_hook（基类 9 步骨架第 5 步后调用）。
    Agent 层 _post_invoke_brand_hook 只做"二次 detect"（供 traj 字段记录 mimo_committed）
    + log 解析完整性补全。
    """
    name = "mimo-agent"
    result_class = MimoResult

    def __init__(
        self,
        config: Optional[MimoConfig] = None,
        prompt_builder: Optional[MimoPromptBuilder] = None,
    ):
        super().__init__(config=config or MimoConfig.from_env())
        self.environment = MimoEnvironment(self.config.workspace_root)
        self.prompt_builder = prompt_builder or MimoPromptBuilder()

    def _log_filename(self) -> str:
        return "mimo-stream.jsonl"

    def _pre_invoke_brand_hook(self, repo_dir, timeout, model) -> dict:
        """Mimo 特有：调 CLI 前记录 base_commit（D10 防御前置）。

        Returns:
            {"base_commit": "abc123"} —— 供 _post_invoke_brand_hook 用
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
        """调 MiMo Code CLI（mimo run <prompt> -m <model> --format json --dangerously-skip-permissions）。"""
        return self._invoke_mimo(prompt, repo_dir, log_path, timeout, model)

    def _invoke_mimo(
        self,
        prompt: str,
        repo_dir: Path,
        log_path: Path,
        timeout: int,
        model: str,
    ) -> tuple[str, int]:
        """调 mimo CLI 子进程（独立函数保留向后兼容）。"""
        cmd = [
            str(self.config.mimo_bin_path),
            "run", prompt,  # 位置参数
            "-m", model,
            "--dangerously-skip-permissions",  # 非交互模式
        ]
        if self.config.json_output:
            cmd.extend(["--format", "json"])  # D2：NDJSON 事件流
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

    def _parse_output(self, raw_stdout: str, log_path: Path) -> MimoJsonParseResult:
        """Mimo 特有：解析 NDJSON 事件流（D2 决策）。"""
        if self.config.json_output:
            return parse_mimo_json_stream(raw_stdout)
        return MimoJsonParseResult()

    def _post_invoke_brand_hook(
        self, repo_dir, ctx_state, raw_stdout, log_path, parse_result,
    ) -> None:
        """Mimo 特有：D10 防御"二次 detect"——供 traj 字段记录 mimo_committed。

        注意：D10 undo（git reset）已前移到 BaseAgentRunner._post_invoke_brand_hook，
        本 hook 只做 detect + log 完整性补全（D4 cleanup 也在 runner 层）。
        """
        # 二次 detect（runner 层已做 undo；如果 undo 成功，这里 committed=False）
        base_commit = ctx_state.get("base_commit")
        mimo_committed = _detect_mimo_committed(repo_dir, base_commit)
        if mimo_committed and base_commit:
            print(
                f"    [mimo-agent] D10 防御：检测到 mimo auto-commit（已由 runner 层撤回）"
            )

    def _write_pred_and_traj(
        self,
        output_dir, instance_id, model, log_path, returncode,
        start_time, parse_result, patch,
    ) -> None:
        """Mimo 特有 override：写 .pred 和 .traj，traj 含 mimo 特有元数据。

        复用基类 _write_pred_and_traj 的核心逻辑，但额外把
        MimoJsonParseResult.as_traj_extra() 喂给 write_traj，落到 .traj 文件。

        目的：F1 轨迹查看器（swebench-exp-web）读 .traj 即可拿 mimo 上下文
        （mimo_session_id / mimo_snapshot / mimo_tokens / mimo_cost /
        mimo_finish_reason / mimo_event_count），不用重新解析 NDJSON。

        函数内 import 防御 Step 4 修过的 sys.path 环依赖 bug。
        """
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

    def _make_error_result(self, instance_id: str, error: str, **kwargs) -> MimoResult:
        """mimo 用 MimoResult（向后兼容）。"""
        return MimoResult(
            success=False, instance_id=instance_id, error=error,
            elapsed_seconds=kwargs.get("elapsed_seconds", 0.0),
        )


# === Mimo 私有 helper ===
def _detect_mimo_committed(repo_dir: Path, base_commit: Optional[str]) -> bool:
    """检测 mimo 是否在 base_commit 之后做了 commit。"""
    if not base_commit:
        return False
    result = _ar_run_cmd(
        ["git", "log", "--oneline", f"{base_commit}..HEAD"],
        cwd=repo_dir, timeout=30, check=False,
    )
    return bool(result.stdout.strip())


# === 兼容导出（外部可能 import） ===
def parse_mimo_json_stream_pub(raw_stdout: str):
    """[兼容] 公开导出。"""
    return parse_mimo_json_stream(raw_stdout)
