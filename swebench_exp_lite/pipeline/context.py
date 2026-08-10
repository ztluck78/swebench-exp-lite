"""TaskContext：单个任务的运行参数与路径约定（pipeline 聚合根）。

每个任务 = `output/<instance_id>/` 目录，承载六阶段全部产物。

字段来源（H2 白名单；由 `grep -rhoE "ctx\\.[a-z_]+"` 清点 runtime+agents
消费面得出下限，任何删字段须有 grep 证据）：

- instance_id / run_id / model / namespace / timeout / dry_run：CLI run 参数
- db_path：默认 database/swe_bench.db（from_db 可覆盖）
- repo / repo_url / base_commit / split：from_db() 从 LiteDB 填充
  （git_workspace 用 ctx.repo 拼 clone URL —— 主仓 git_workspace.py:36 实证）
- dataset：默认本地 data/swe_bench_data/swe-bench-lite.jsonl（H1/离线口径）
- repo_root：包根向上两级；所有子进程 cwd 基准（S6 固定 cwd=repo_root，H1）
- manifest：pipeline.manifest.Manifest，断点续跑状态
- task_dir / agent_dir / ca_prompt 等路径属性：runtime + agents 消费
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from ..db import DEFAULT_DB_PATH, REPO_ROOT, TEST_JSONL

if TYPE_CHECKING:  # 避免循环导入
    from .manifest import Manifest


@dataclass
class TaskContext:
    instance_id: str
    base_output_dir: Path = field(default_factory=lambda: REPO_ROOT / "output")
    repo_root: Path = field(default_factory=lambda: REPO_ROOT)
    run_id: str = ""
    model: str = "replay/gold-patch"
    # 本地 jsonl 数据集（harness load_swebench_dataset 原生支持本地路径）
    dataset: str = field(default_factory=lambda: str(TEST_JSONL))
    split: str = "test"
    db_path: Path = field(default_factory=lambda: DEFAULT_DB_PATH)
    namespace: str = "swebench"   # 远端拉取模式用官方 namespace
    cache_level: str = "env"      # harness --cache_level 参数
    timeout: int = 1800           # harness --timeout 参数（秒）
    adapter: str = "replay-agent" # S4 runner 名（registry RUNNERS 键）
    force: bool = False
    dry_run: bool = False
    manifest: "Optional[Manifest]" = field(default=None, repr=False)
    # 仓库元信息（from_db 填充；S2 worktree 拼 URL 用 ctx.repo）
    repo: str = ""
    base_commit: str = ""

    def __post_init__(self):
        # 外部（CLI）常以字符串传入路径，统一转 Path
        self.base_output_dir = Path(self.base_output_dir)
        self.repo_root = Path(self.repo_root)
        self.db_path = Path(self.db_path)

    @property
    def repo_url(self) -> str:
        """git clone URL（由 ctx.repo 推导；runtime 备仓消费）。"""
        return f"https://github.com/{self.repo}.git" if self.repo else ""

    @classmethod
    def from_db(cls, instance_id: str, db_path: Optional[Path] = None,
                **overrides) -> "TaskContext":
        """从 LiteDB 填充镜像/仓库元信息（namespace/cache_level/timeout/repo/base_commit/split）。

        DB 缺失或实例未收录时降级：打印告警，用安全默认值继续
        （namespace=swebench cache_level=env timeout=1800）。
        """
        ctx = cls(instance_id=instance_id,
                  db_path=db_path or DEFAULT_DB_PATH, **overrides)
        try:
            from ..db.query import LiteDB
            db = LiteDB(ctx.db_path)
            acq = db.acquisition(instance_id, arch="x86_64")
            ns = acq["namespace"] or ""
            ctx.namespace = "" if ns in ("none", "") else ns
            ctx.cache_level = acq["cache_level"] or "env"
            ctx.timeout = acq["recommended_timeout"] or 1800
            ctx._db_image_name = acq["image_name"] or ""
            inst = db.get(instance_id, with_large=False)
            ctx.repo = inst.repo or ""
            ctx.base_commit = inst.base_commit or ""
            if "split" not in overrides and inst.split:
                ctx.split = inst.split
        except Exception as e:  # noqa: BLE001 — 降级不阻断
            ctx._db_image_name = ""
            print(f"    [warn] from_db 降级：{type(e).__name__}: {e}"
                  f"（用默认 namespace/cache_level/timeout 继续）")
        return ctx

    def load_image_name(self) -> str:
        """当前任务的评测镜像名（image.json > DB 元信息 > 空）。"""
        import json as _json
        if self.image_json.exists():
            try:
                name = _json.loads(self.image_json.read_text(encoding="utf-8")).get("image", "")
                if name and name != "unknown":
                    return name
            except Exception:  # noqa: BLE001
                pass
        return getattr(self, "_db_image_name", "")

    # ---- 目录 ----
    @property
    def task_dir(self) -> Path:
        return Path(self.base_output_dir) / self.instance_id

    def path(self, *parts) -> Path:
        return self.task_dir.joinpath(*parts)

    def ensure_dirs(self) -> None:
        for d in (self.task_dir, self.agent_dir, self.eval_dir):
            d.mkdir(parents=True, exist_ok=True)

    # ---- S1 出题产物 ----
    @property
    def ca_issue(self) -> Path:     return self.path("ca-issue.json")
    @property
    def ca_prompt(self) -> Path:    return self.path("ca-task-prompt.md")
    @property
    def review(self) -> Path:       return self.path("review.md")
    @property
    def task_jsonl(self) -> Path:    return self.path("task.jsonl")

    # ---- S2 环境产物 ----
    @property
    def image_json(self) -> Path:   return self.path("image.json")

    # ---- S4 作答产物 ----
    @property
    def agent_dir(self) -> Path:       return self.path("agent")
    @property
    def agent_run_dir(self) -> Path:   return self.path("agent", self.instance_id)
    @property
    def agent_traj(self) -> Path:      return self.path("agent", self.instance_id, f"{self.instance_id}.traj")
    @property
    def agent_pred(self) -> Path:      return self.path("agent", self.instance_id, f"{self.instance_id}.pred")
    @property
    def agent_patch(self) -> Path:     return self.path("agent", f"{self.instance_id}.patch")

    @property
    def patch_dir(self) -> Path:       return self.path("patch")
    @property
    def patch_stat(self) -> Path:      return self.path("patch", "diff-stat.txt")
    @property
    def changed_files(self) -> Path:   return self.path("patch", "changed-files.txt")

    # ---- S5 补丁→prediction ----
    @property
    def prediction(self) -> Path:  return self.path("prediction.jsonl")

    # ---- S6 评分产物 ----
    @property
    def eval_dir(self) -> Path:    return self.path("eval")
    @property
    def eval_report(self) -> Path: return self.path("eval", "report.json")

    # ---- S7 结果 ----
    @property
    def result(self) -> Path:      return self.path("result.json")
