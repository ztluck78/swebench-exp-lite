"""仓库准备与工作区管理（品牌中立）。

提供 Agent 作答所需的 Git 仓库操作基础设施：
- 共享 bare mirror + detached worktree 模式（避免重复 clone）
- 工作区并发锁（实例级互斥）
- 工作区快照元数据写入

所有函数零外部依赖（仅标准库 + swebench_exp_lite.runtime.proc），可被任何 Agent 适配器复用。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from typing import Optional

from .platform import is_process_alive
from .proc import CmdError, run_cmd


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

def _shared_mirror_path(workspace_root: Path, repo_url: str) -> Path:
    """返回稳定的共享 mirror 路径，不把 URL 原文当作文件名。"""
    key = hashlib.sha256(repo_url.rstrip("/").encode("utf-8")).hexdigest()[:16]
    name = repo_url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
    safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
    return workspace_root / "runtime-cache" / "git-mirrors" / f"{safe_name}-{key}.git"


def _has_commit(repo_dir: Path, commit: str) -> bool:
    """探测本地是否已含该 commit 对象（查询类，允许失败）。"""
    result = run_cmd(
        ["git", "cat-file", "-t", commit],
        cwd=repo_dir,
        timeout=60,
        check=False,
    )
    return result.returncode == 0


def _git_clone(url: str, target: Path) -> None:
    """完整克隆仓库（SWE-bench base_commit 通常在历史深处，必须完整历史）。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    run_cmd(
        ["git", "clone", url, str(target)],
        timeout=1800,
        error_prefix="git clone",
    )


def _git_checkout(repo_dir: Path, commit: str) -> None:
    """检出到指定 commit。commit 缺失时依次：unshallow -> 定向 fetch。

    所有步骤经 run_cmd：超时必报错（绝不在网络操作被截断后假装继续），
    失败异常携带 git 原始 stderr，便于直达根因。
    """
    if not _has_commit(repo_dir, commit):
        # 1) 尝试 unshallow（大仓库可能耗时数分钟；若本地已是完整克隆会
        #    报 not shallow 错误，check=False 交由第 2 步判定）
        run_cmd(
            ["git", "fetch", "--unshallow"],
            cwd=repo_dir,
            timeout=1800,
            check=False,
            error_prefix="git fetch --unshallow",
        )
        # 2) 仍缺失则定向 fetch 该 commit（需服务端允许按 SHA 拉取）
        if not _has_commit(repo_dir, commit):
            try:
                run_cmd(
                    ["git", "fetch", "origin", commit],
                    cwd=repo_dir,
                    timeout=1800,
                    error_prefix="git fetch 定向拉取",
                )
            except CmdError as e:
                raise CmdError(
                    f"无法获取 commit {commit}（unshallow/定向 fetch 均失败）"
                ) from e
            if not _has_commit(repo_dir, commit):
                raise CmdError(
                    f"fetch 声称成功但 commit {commit} 仍不可达（对象库异常）"
                )

    run_cmd(
        ["git", "checkout", commit],
        cwd=repo_dir,
        timeout=300,
        error_prefix=f"git checkout {commit}",
    )


def _mirror_lock_is_stale(lock: Path) -> bool:
    """C-12：判定 mirror 锁是否为 stale 残留（可安全清除）。

    持有者进程已死（platform.is_process_alive 探测返回 False）或
    持锁超 600s（TTL）即判 stale；meta 读取失败（竞态/刚创建）视为正常等待。
    """
    try:
        meta = json.loads((lock / "meta.json").read_text(encoding="utf-8"))
        acquired_at = float(meta.get("acquired_at", 0))
        pid = int(meta.get("pid", 0))
    except Exception:  # noqa: BLE001 — meta 缺失/读取竞态：按正常等待处理
        return False
    if time.time() - acquired_at > 600:
        return True
    # 跨平台进程存活探测：POSIX 走 os.kill(pid, 0)，Windows 走 ctypes OpenProcess
    if not is_process_alive(pid):
        return True
    return False  # 进程仍在运行，继续等待


def _ensure_mirror(repo_url: str, mirror: Path, base_commit: str) -> None:
    """创建或更新 mirror，并确认目标 commit 可用。

    C-12：锁目录内写 meta.json（pid + acquired_at）；等待时检测持锁方
    已死（ProcessLookupError）或超 TTL（600s）则清除残锁重新抢锁，
    崩溃残留锁不再干等 60s 报错。
    """
    mirror.parent.mkdir(parents=True, exist_ok=True)
    lock = mirror.with_name(mirror.name + ".lock")
    acquired = False
    try:
        for _ in range(600):
            try:
                lock.mkdir()
                acquired = True
                break
            except FileExistsError:
                if _mirror_lock_is_stale(lock):
                    shutil.rmtree(lock, ignore_errors=True)
                    continue
                time.sleep(0.1)
        if not acquired:
            raise CmdError(f"等待共享 mirror 锁超时：{lock}")
        try:
            (lock / "meta.json").write_text(
                json.dumps({"pid": os.getpid(), "acquired_at": time.time()}),
                encoding="utf-8",
            )
        except OSError:
            pass  # 元数据写入失败不影响持锁本身（后续等待方按正常等待处理）
        if not mirror.exists():
            run_cmd(["git", "clone", "--mirror", repo_url, str(mirror)], timeout=1800, error_prefix="git clone --mirror")
        if not _has_commit(mirror, base_commit):
            run_cmd(["git", "--git-dir", str(mirror), "fetch", "--prune", "origin"], timeout=1800, error_prefix="git mirror fetch")
        if not _has_commit(mirror, base_commit):
            raise CmdError(f"共享 mirror 中不存在 base_commit：{base_commit} ({mirror})")
    finally:
        if acquired:
            shutil.rmtree(lock, ignore_errors=True)


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------

def setup_repo(
    repo_url: str,
    repo_dir: Path,
    base_commit: str,
    *,
    workspace_root: Path,
    experiment_id: str | None = None,
    use_shared_cache: bool = False,
) -> Path:
    """准备代码仓库。

    默认使用 ``runtime-cache/git-mirrors`` 中的共享 bare mirror，
    再为当前实验建立独立 detached worktree；这避免把完整仓库放入
    experiments/，也避免同一仓库被每个任务重复 clone。
    ``use_shared_cache=False`` 保留旧的 experiment-local 行为。

    Args:
        repo_url: 仓库 URL
        repo_dir: 目标目录
        base_commit: 基线 commit
        workspace_root: 项目工作区根目录
        experiment_id: 实验 ID（可选）
        use_shared_cache: 是否使用共享 cache 模式

    Returns:
        准备好的仓库目录路径
    """
    repo_dir = Path(repo_dir)
    if use_shared_cache:
        mirror = _shared_mirror_path(workspace_root, repo_url)
        _ensure_mirror(repo_url, mirror, base_commit)
        repo_dir.parent.mkdir(parents=True, exist_ok=True)
        if repo_dir.exists():
            if (repo_dir / ".git").exists():
                # C-02：复用前先清除上次作答残留（崩溃/SIGKILL 现场），
                # 保证复用路径幂等；失败经 run_cmd 必抛 CmdError。
                run_cmd(
                    ["git", "reset", "--hard"],
                    cwd=repo_dir, timeout=300, error_prefix="git reset --hard",
                )
                run_cmd(
                    ["git", "clean", "-fdx"],
                    cwd=repo_dir, timeout=300, error_prefix="git clean -fdx",
                )
                _git_checkout(repo_dir, base_commit)
            else:
                raise CmdError(f"工作区路径已存在但不是 Git 仓库：{repo_dir}")
        else:
            # C-15a：worktree 目录可能被外部 rm -rf 删除但 mirror 中仍
            # 有注册，先 prune 清除 stale 条目再 add（避免"missing but
            # already registered"报错）。
            run_cmd(
                ["git", "--git-dir", str(mirror), "worktree", "prune"],
                timeout=30,
                check=False,
                error_prefix="git worktree prune",
            )
            run_cmd(
                ["git", "--git-dir", str(mirror), "worktree", "add", "--detach", str(repo_dir), base_commit],
                timeout=300,
                error_prefix="git worktree add",
            )
        return repo_dir

    if repo_dir.exists() and (repo_dir / ".git").is_dir():
        _git_checkout(repo_dir, base_commit)
    else:
        _git_clone(repo_url, repo_dir)
        _git_checkout(repo_dir, base_commit)
    return repo_dir


def cleanup_worktree(repo_dir: Path, mirror: Path | None = None) -> None:
    """删除实验 worktree，但不删除共享 mirror。

    无论目录是否存在都尝试从 mirror 取消注册（处理外部 rm -rf 场景）。
    """
    repo_dir = Path(repo_dir)
    if mirror and mirror.exists():
        # 先尝试 git worktree remove（目录存在时正常路径）
        run_cmd(["git", "--git-dir", str(mirror), "worktree", "remove", "--force", str(repo_dir)],
                timeout=300, check=False, error_prefix="git worktree remove")
        # C-15a：再 prune 清理外部删除导致的 stale 注册
        run_cmd(["git", "--git-dir", str(mirror), "worktree", "prune"],
                timeout=30, check=False, error_prefix="git worktree prune")
    if repo_dir.exists():
        shutil.rmtree(repo_dir, ignore_errors=True)
    # C-15（P14a）：清理失败不再静默，残留需人工处理
    if repo_dir.exists():
        print(f"[warn] worktree 清理失败（残留需人工处理）：{repo_dir}")


def acquire_run_lock(repo_dir: Path, instance_id: str) -> tuple:
    """C-11：instance 级并发守卫锁（mkdir 原子性，fail-fast 不等待）。

    锁目录为 ``repo_dir.parent/<instance_id>.run.lock``，仅用于互斥、不写 pid。
    返回 ``(lock, None)`` 表示获锁成功；``(None, AgentResult)`` 表示已有
    运行中的作答，调用方应直接返回该拒绝结果。
    """
    # Phase 3：swebench_exp_lite.runtime.protocol.AgentResult 替代 kimi_agent.environment.RunResult，
    # 消除基础设施层 → 适配层的反向依赖。
    from .protocol import AgentResult  # noqa: PLC0415

    lock = Path(repo_dir).parent / f"{instance_id}.run.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock.mkdir()
    except FileExistsError:
        return None, AgentResult(
            success=False,
            instance_id=instance_id,
            error=f"实例 {instance_id} 已有运行中的作答（锁：{lock}）",
        )
    return lock, None


def write_snapshot_meta(repo_dir: Path, instance_id: str, source_commit: Optional[str]) -> Path:
    """C-06：snapshot.json 写入实例子目录 snapshots/<instance_id>/snapshot.json。

    旧实现写 repo_dir.parent（即 snapshots/ 根），多实例依次保留 snapshot
    时会互相覆盖；字段结构不变。
    """
    from datetime import datetime, timezone

    snapshot_meta = {
        "experiment_id": instance_id,
        "reason": os.environ.get("WORKSPACE_SNAPSHOT_REASON", "manual retention=snapshot"),
        "source_commit": source_commit,
        "workspace_path": str(repo_dir),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    path = Path(repo_dir) / "snapshot.json"
    path.write_text(json.dumps(snapshot_meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# 仓库信息查询（DESIGN §1 抽 4 小优化 #1：3 adapter 共用 get_repo_info）
# --------------------------------------------------------------------------- #
def get_repo_info(repo_dir: Path) -> dict:
    """查询仓库的当前状态（commit / branch / diff / untracked）。

    三个 adapter 之前都各自实现（kimi 45 行，qwen/mimo 类似），重复度高。
    抽到 swebench_exp_lite.runtime 后 3 个 brand 共用，行为契约以原 KimiEnvironment 为准。

    Args:
        repo_dir: 仓库目录（必须是 git 仓库）

    Returns:
        dict: 含 commit / branch / has_changes / diff_stat / status /
              untracked_files / dirty_files（任一字段查询失败不影响其他字段）
    """
    info: dict = {}

    # HEAD commit
    result = run_cmd(["git", "rev-parse", "HEAD"], cwd=repo_dir, timeout=30, check=False)
    if result.returncode == 0:
        info["commit"] = result.stdout.strip()

    # current branch
    result = run_cmd(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo_dir, timeout=30, check=False,
    )
    if result.returncode == 0:
        info["branch"] = result.stdout.strip()

    # diff stat
    result = run_cmd(["git", "diff", "--stat"], cwd=repo_dir, timeout=30, check=False)
    if result.returncode == 0 and result.stdout.strip():
        info["has_changes"] = True
        info["diff_stat"] = result.stdout.strip()

    # status（含 untracked）
    result = run_cmd(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=repo_dir, timeout=30, check=False,
    )
    if result.returncode == 0:
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        info["status"] = lines
        info["untracked_files"] = [line[3:] for line in lines if line.startswith("?? ")]
        info["dirty_files"] = [line[3:] for line in lines if not line.startswith("?? ")]
    else:
        info["status_error"] = result.stderr.strip()

    return info
