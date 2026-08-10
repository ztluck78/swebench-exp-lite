"""S2 环境准备：评测镜像惰性检查 + git worktree 备仓 + venv 预装。

三件事都幂等（已就绪则跳过）：
1. docker image inspect 评测镜像；缺失时尝试 DB 记录的 pull 命令，
   再失败提示走 start.sh 的 OSS tar 降级；
2. worktree 备仓（用 ctx.repo 拼 URL，委托 runtime.repo.setup_repo 的
   shared mirror + worktree 机制）——replay-agent 跳过（无需真实仓库）；
3. venv 预装 pip install -e . + pytest（best-effort，失败不阻断）。

产物：image.json。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from ...db.query import LiteDB
from .base import Stage, StageError, run_cmd


def _docker_image_exists(name: str) -> bool:
    if not name or shutil.which("docker") is None:
        return False
    r = subprocess.run(["docker", "image", "inspect", name],
                       capture_output=True, timeout=30)
    return r.returncode == 0


def _image_digest(name: str | None) -> str | None:
    if not name or name == "unknown" or shutil.which("docker") is None:
        return None
    try:
        r = subprocess.run(
            ["docker", "image", "inspect", "--format", "{{index .RepoDigests 0}}", name],
            capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    return None


def _worktree_path(ctx) -> Path:
    """worktree 目标路径（与 runtime.base_runner 一致的 cache 布局）。"""
    cache = Path(os.environ.get("SWEBENCH_RUNTIME_CACHE",
                                str(ctx.repo_root / "runtime-cache")))
    return cache / "worktrees" / ctx.instance_id


class S2Prepare(Stage):
    name = "S2_prepare"

    def command(self, ctx):
        return ["docker", "image", "inspect", ctx.load_image_name() or "<eval-image>"]

    def outputs(self, ctx):
        return [ctx.image_json]

    def run(self, ctx) -> None:
        ctx.ensure_dirs()
        if ctx.dry_run:
            return
        name = self._prepare_image(ctx)
        if ctx.adapter != "replay-agent":
            self._prepare_git_workspace(ctx)
            self._prepare_venv(ctx)
        image_data = {
            "image": name or "unknown", "kind": "eval",
            "arch": "x86_64", "namespace": ctx.namespace,
            "built_at": datetime.now(timezone.utc).isoformat(),
            "digest": _image_digest(name),
        }
        ctx.image_json.write_text(
            json.dumps(image_data, indent=2, ensure_ascii=False), encoding="utf-8")
        if ctx.manifest:
            ctx.manifest.set_image(image_data)

    # ---- 1) 评测镜像（惰性：已存在则跳过）----
    def _prepare_image(self, ctx) -> str | None:
        try:
            db = LiteDB(str(ctx.db_path))
            name = db.docker_image(ctx.instance_id, arch="x86_64")
            acq = db.acquisition(ctx.instance_id, arch="x86_64")
        except Exception as e:  # noqa: BLE001
            print(f"    [warn] S2 读 DB 镜像元信息失败（{e}），跳过镜像预检")
            return None
        if _docker_image_exists(name):
            print(f"    [skip] 评测镜像本地已存在: {name}")
            return name
        pull_cmd = acq.get("pull_cmd")
        if pull_cmd and shutil.which("docker"):
            print(f"    [S2_prepare/image] 本地缺失，尝试拉取: {pull_cmd}")
            try:
                run_cmd(pull_cmd.split(), cwd=ctx.repo_root, ctx=ctx,
                        log_name="S2_prepare", timeout=3600)
                return name
            except StageError as e:
                print(f"    [warn] 拉取失败: {e}")
        raise StageError(
            f"评测镜像 {name} 本地不存在且拉取失败。\n"
            f"    请运行 ./start.sh（含 OSS tar 降级），或手动 "
            f"docker pull / docker load 该镜像后重试。"
        )

    # ---- 2) git worktree 备仓（幂等；replay-agent 不走此路径）----
    def _prepare_git_workspace(self, ctx) -> None:
        wt = _worktree_path(ctx)
        if (wt / ".git").exists():
            print(f"    [skip] worktree 已存在: {wt}")
            return
        if not ctx.repo or not ctx.base_commit:
            print("    [warn] repo/base_commit 缺失（DB 降级），跳过 worktree 预备（S4 将自行备仓）")
            return
        print(f"    [S2_prepare/git] 准备仓库 worktree: {wt}（{ctx.repo_url}）")
        try:
            from ...runtime.repo import setup_repo
            setup_repo(
                repo_url=ctx.repo_url,
                repo_dir=wt,
                base_commit=ctx.base_commit,
                workspace_root=ctx.repo_root,
                experiment_id=ctx.instance_id,
                use_shared_cache=True,
            )
            print(f"    [S2_prepare/git] worktree 备仓成功: {wt}")
        except Exception as e:  # noqa: BLE001
            print(f"    [warn] worktree 备仓失败（S4 将自行重试）: {e}")

    # ---- 3) venv 预装（best-effort，幂等）----
    def _prepare_venv(self, ctx) -> None:
        if os.environ.get("NO_ENV_PREINSTALL") == "1":
            return
        repo_dir = _worktree_path(ctx)
        if not repo_dir.is_dir():
            return
        if not any((repo_dir / f).exists()
                   for f in ("setup.py", "pyproject.toml", "setup.cfg")):
            return
        cache = Path(os.environ.get("SWEBENCH_RUNTIME_CACHE",
                                    str(ctx.repo_root / "runtime-cache")))
        repo_slug = ctx.repo.replace("/", "__")
        commit_short = ctx.base_commit[:8] if ctx.base_commit else "unknown"
        venv_dir = cache / "venvs" / repo_slug / commit_short
        if (venv_dir / "bin" / "python").exists():
            print(f"    [skip] venv 已存在: {venv_dir}")
            return
        try:
            from ...runtime.proc import run_cmd as _agent_run_cmd
            timeout = int(os.environ.get("ENV_PREINSTALL_TIMEOUT", "600"))
            _agent_run_cmd([sys.executable, "-m", "venv", str(venv_dir)],
                           cwd=repo_dir, timeout=180, error_prefix="create venv")
            pip = str(venv_dir / "bin" / "pip")
            _agent_run_cmd([pip, "install", "--quiet", "-e", str(repo_dir)],
                           cwd=repo_dir, timeout=timeout, error_prefix="pip install -e .")
            _agent_run_cmd([pip, "install", "--quiet", "pytest"],
                           cwd=repo_dir, timeout=180, check=False,
                           error_prefix="pip install pytest")
            print(f"    [S2_prepare/venv] preinstall ok: {venv_dir}")
        except Exception as e:  # noqa: BLE001
            print(f"    [warn] venv preinstall 失败（agent 将自行探索）: {e}")
