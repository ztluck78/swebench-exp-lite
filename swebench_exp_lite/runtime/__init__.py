"""swebench_exp_lite.runtime：Agent 作答域基础设施。

提供品牌中立的仓库准备、补丁提取、产物写入和子进程执行工具。
所有函数零外部依赖（仅标准库），可被任何 Agent 适配器复用。

模块：
- proc:       run_cmd / CmdError（统一子进程执行器）
- repo:       setup_repo / cleanup_worktree / acquire_run_lock（共享 mirror + worktree）
- patch:      extract_patch_from_repo / extract_patch_from_log（git diff 提取 + 噪声过滤）
- artifacts:  write_pred / write_traj / write_patch（统一产物写入）
- protocol:   AgentResult（品牌中立的 Agent 应答结果）
- progress:   ProgressWatcher / ProgressState / summarize（作答进度观测）
"""
__version__ = "0.1.0"

from .proc import run_cmd, run_cmd_to_file, CmdError  # noqa: F401
from .repo import (                  # noqa: F401
    setup_repo,
    cleanup_worktree,
    acquire_run_lock,
    write_snapshot_meta,
    get_repo_info,
)
from .base_runner import BaseAgentRunner  # noqa: F401
from .base_agent import BaseAgent  # noqa: F401
from .brand_runner import run_brand_runner, setup_brand_import_paths  # noqa: F401
from .protocol import AgentResult    # noqa: F401
from .prompt import StandardPromptBuilder  # noqa: F401
from .patch import (                 # noqa: F401
    extract_patch_from_repo,
    extract_patch_from_log,
    is_patch_noise_path,
)
from .artifacts import (             # noqa: F401
    write_pred,
    write_traj,
    write_patch,
)
from .progress import (              # noqa: F401
    ProgressWatcher,
    ProgressState,
    resolve_log_paths,
    summarize,
)
from .lock_cleaner import cleanup_stale_locks  # noqa: F401

# v0.1.5+ · SPEC-remove-stages-s4-adapter-20260806：brand 注册表
from .registry import (                  # noqa: F401
    DEFAULT_RUNNER,
    RUNNERS,
    list_runner_names,
    resolve_runner,
)
# v0.1.5+ · SPEC-remove-stages-s4-adapter-20260806 Commit 2：CLI 预检工厂
from .cli_preconditions import (   # noqa: F401
    kimi_cli_available,
    mimo_cli_available,
    qwen_cli_available,
)



__all__ = [
    "run_cmd", "run_cmd_to_file", "CmdError",
    "setup_repo", "cleanup_worktree", "acquire_run_lock", "write_snapshot_meta",
    "get_repo_info",
    "extract_patch_from_repo", "extract_patch_from_log", "is_patch_noise_path",
    "write_pred", "write_traj", "write_patch",
    "StandardPromptBuilder",
    "BaseAgentRunner",
    "BaseAgent",
    "run_brand_runner", "setup_brand_import_paths",
    "ProgressWatcher", "ProgressState", "resolve_log_paths", "summarize",
    "cleanup_stale_locks",
]
