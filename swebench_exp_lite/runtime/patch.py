"""补丁提取与噪声过滤（品牌中立）。

提供从 Agent 修改过的 Git 仓库中可靠提取 unified diff 的工具：
- 优先从工作区 git diff 提取（最可靠）
- 回退从日志文本解析（兼容 markdown 代码块）
- 噪声文件过滤（__pycache__ / .venv / .DS_Store 等）

所有函数零外部依赖（仅标准库），可被任何 Agent 适配器复用。
"""
from __future__ import annotations

import re
import subprocess as _sp
from pathlib import Path
from typing import Optional


# C-01：untracked 捕获 denylist（规格 §3.4）。仅作用于 untracked 分支，
# tracked 改动（git diff HEAD --binary）不过滤。
_NOISE_FILE_NAMES = {".DS_Store", "Thumbs.db", ".gitkeep"}
_NOISE_DIR_SEGMENTS = {
    "__pycache__", ".pytest_cache", ".venv", "venv",
    ".mypy_cache", ".ruff_cache", ".ipynb_checkpoints",
}
_NOISE_FILE_SUFFIXES = (".pyc", ".pyo")
_NOISE_SEGMENT_SUFFIXES = (".egg-info",)


def is_patch_noise_path(path: str) -> bool:
    """判断 untracked 路径是否属于 denylist 噪声文件。"""
    segments = [s for s in path.split("/") if s]
    if not segments:
        return False
    basename = segments[-1]
    if basename in _NOISE_FILE_NAMES:
        return True
    if basename.endswith(_NOISE_FILE_SUFFIXES):
        return True
    for seg in segments:
        if seg in _NOISE_DIR_SEGMENTS:
            return True
        if seg.endswith(_NOISE_SEGMENT_SUFFIXES):
            return True
    return False


def extract_patch_from_repo(repo_dir: Path) -> Optional[str]:
    """从仓库工作区提取真实 git diff（Agent 直接修改文件时最可靠）。

    优先取相对 HEAD 的全部改动（含已暂存/未暂存），避免依赖解析日志文本。
    """
    try:
        patches = []
        result = _sp.run(
            ["git", "diff", "HEAD", "--binary"], cwd=str(repo_dir),
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0 and result.stdout.strip():
            patches.append(result.stdout)

        # untracked 文件不属于 git diff HEAD，逐个生成标准 unified diff，
        # 防止 Agent 新建文件时 patch 静默丢失。
        status = _sp.run(
            ["git", "status", "--short", "--untracked-files=all"], cwd=str(repo_dir),
            capture_output=True, text=True, timeout=120,
        )
        if status.returncode == 0:
            for line in status.stdout.splitlines():
                if not line.startswith("?? "):
                    continue
                path = line[3:]
                # C-01：过滤 denylist 噪声文件（合法新增文件不受影响）
                if is_patch_noise_path(path):
                    print(f"[patch-filter] 跳过噪声文件: {path}")
                    continue
                diff = _sp.run(
                    ["git", "diff", "--no-index", "--binary", "/dev/null", path],
                    cwd=str(repo_dir), capture_output=True, text=True, timeout=120,
                )
                if diff.stdout.strip():
                    patches.append(diff.stdout)
        return "".join(patches) or None
    except Exception:
        return None


def extract_patch_from_log(log: str) -> Optional[str]:
    """从 Agent 输出中提取 git diff 输出。

    Agent 最后会输出完整的 ``git diff -- <module>/``，但常包在 markdown
    代码块里带前导缩进，故放宽匹配：允许行首空白，并兼容多种 diff 结尾。
    """
    # 模式1：匹配首个（可能带缩进的）diff --git 块到文件结束
    lines = log.split('\n')
    diff_start = None
    for i, line in enumerate(lines):
        if line.lstrip().startswith('diff --git '):
            diff_start = i
            break
    if diff_start is not None:
        return '\n'.join(lines[diff_start:]).strip()

    # 模式2：正则兜底（允许行首缩进）
    diff_pattern = re.compile(
        r'(?m)^\s*diff --git .+?(?=\n-- |\Z)',
        re.DOTALL,
    )
    match = diff_pattern.search(log)
    if match:
        return match.group(0).strip()

    return None
