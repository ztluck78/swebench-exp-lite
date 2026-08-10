"""S4 worker 子进程入口：`python -m swebench_exp_lite.pipeline.stages.s4_worker '<json>'`。

主仓用独立 worker_entry.py + sys.path hack；lite 仓包已安装，
worker 只需解析 JSON 配置 → resolve_runner → runner.run()，退出码 0/1。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: s4_worker '<config-json>'", file=sys.stderr)
        return 2
    cfg = json.loads(sys.argv[1])

    from ...runtime.registry import resolve_runner
    runner = resolve_runner(cfg["adapter"])
    result = runner.run(
        instance_id=cfg["instance_id"],
        issue_path=Path(cfg["issue_path"]),
        ca_prompt_path=Path(cfg["ca_prompt_path"]),
        repo_dir=Path(cfg["repo_dir"]),
        output_dir=Path(cfg["output_dir"]),
        repo_root=Path(cfg["repo_root"]),
        repo_url=cfg.get("repo_url"),
        base_commit=cfg.get("base_commit"),
    )
    if not result.success:
        print(f"[s4_worker] {cfg['adapter']} 失败: {result.error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
