"""swebench-exp-lite 顶层 CLI。

子命令：
- build       出题：从题库渲染题面四件套
- list        列出题库实例（可按 split/repo 过滤）
- info        查看单个实例详情（含镜像/难度/测试数）
- run         跑六阶段闭环（S1→S2→S4→S5→S6→S7）
- candidates  按 p2p/patch_size 升序推荐"适合上手"的题
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime


def _db(args):
    from .db.query import LiteDB
    return LiteDB(getattr(args, "db", None))


def _default_model(adapter: str) -> str:
    return {
        "replay-agent": "replay/gold-patch",
        "kimi-agent": "kimi-code/kimi-for-coding",
        "kimi-fast": "kimi-code/kimi-for-coding-fast",
        "qwen-agent": "qwen/qwen-coder",
        "mimo-agent": "mimo/mimo-coder",
        "opencode-agent": "opencode/opencode",
    }.get(adapter, f"swebench-exp-lite/{adapter}")


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------
def cmd_build(args) -> int:
    from .builder import TaskBuilder
    builder = TaskBuilder(getattr(args, "db", None))
    paths = builder.build_and_render(args.instance, args.output)
    for kind, p in paths.items():
        print(f"  {kind:<7} {p}")
    return 0


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------
def cmd_list(args) -> int:
    db = _db(args)
    rows = db.filter_by_split(args.split) if args.split else list(db.iter_metadata())
    if args.repo:
        rows = [r for r in rows if r["repo"] == args.repo]
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]
    print(f"{'instance_id':<48} {'repo':<32} {'diff':<7} {'p2p':>4} {'patch':>6}")
    for r in rows:
        print(f"{r['instance_id']:<48} {r['repo']:<32} "
              f"{(r['exec_difficulty_class'] or '-'):<7} "
              f"{r['p2p_count']:>4} {r['patch_size']:>6}")
    print(f"\n共 {len(rows)} 条（题库总计 {db.count()}）")
    return 0


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------
def cmd_info(args) -> int:
    db = _db(args)
    row = db.get(args.instance)
    est = db.eval_estimate(args.instance)
    print(json.dumps({
        "instance_id": row["instance_id"],
        "repo": row["repo"],
        "split": row["split"],
        "version": row["version"],
        "language": row["language"],
        "difficulty": row["exec_difficulty_class"],
        "f2p_count": row["f2p_count"],
        "p2p_count": row["p2p_count"],
        "patch_size": row["patch_size"],
        "test_patch_size": row["test_patch_size"],
        "base_commit": row["base_commit"],
        "instance_url": row["instance_url"],
        "image": est["image_name"],
        "image_mode": est["mode"],
        "recommended_timeout": est["recommended_timeout"],
        "problem_statement_head": (row["problem_statement"] or "")[:400] + "…",
    }, indent=2, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------
def cmd_run(args) -> int:
    from .pipeline import TaskContext, run_pipeline
    from .pipeline.stages.base import StageError

    overrides = {"adapter": args.adapter}
    if args.model:
        overrides["model"] = args.model
    else:
        overrides["model"] = _default_model(args.adapter)
    if args.run_id:
        if "/" in args.run_id or "\\" in args.run_id:
            print("错误：--run-id 不得含路径分隔符", file=sys.stderr)
            return 2
        overrides["run_id"] = args.run_id
    else:
        overrides["run_id"] = "lite-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    if args.timeout:
        overrides["timeout"] = args.timeout
    overrides["dry_run"] = args.dry_run
    overrides["force"] = args.force
    if args.output_dir:
        overrides["base_output_dir"] = args.output_dir

    ctx = TaskContext.from_db(args.instance, **overrides)
    try:
        result_path = run_pipeline(ctx)
    except (StageError, Exception) as e:  # noqa: BLE001
        print(f"\n[pipeline] 失败：{e}", file=sys.stderr)
        return 1
    if not args.dry_run and result_path.exists():
        print(f"\nresult.json：{result_path}")
        print(result_path.read_text(encoding="utf-8"))
    return 0


# ---------------------------------------------------------------------------
# candidates
# ---------------------------------------------------------------------------
def cmd_candidates(args) -> int:
    """按 p2p 数量、patch 大小升序推荐适合上手的题（回归面小、修复面小）。"""
    db = _db(args)
    rows = list(db.iter_metadata(split=args.split))
    rows.sort(key=lambda r: (r["p2p_count"] or 0, r["patch_size"] or 0))
    print(f"{'instance_id':<48} {'diff':<7} {'p2p':>4} {'patch':>6}")
    for r in rows[: args.limit]:
        print(f"{r['instance_id']:<48} "
              f"{(r['exec_difficulty_class'] or '-'):<7} "
              f"{r['p2p_count']:>4} {r['patch_size']:>6}")
    return 0


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    from .runtime.registry import list_runner_names
    p = argparse.ArgumentParser(
        prog="swebench-exp-lite",
        description="SWE-bench 精简教学实验平台：出题 → Agent 做题 → 自动打分")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("build", help="出题：渲染题面四件套")
    sp.add_argument("--instance", required=True)
    sp.add_argument("-o", "--output", default="output")
    sp.add_argument("--db", default=None, help="swe_bench.db 路径（默认 database/swe_bench.db）")
    sp.set_defaults(func=cmd_build)

    sp = sub.add_parser("list", help="列出题库实例")
    sp.add_argument("--split", default=None, help="test / dev")
    sp.add_argument("--repo", default=None)
    sp.add_argument("--limit", type=int, default=0)
    sp.add_argument("--db", default=None)
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("info", help="查看实例详情")
    sp.add_argument("--instance", required=True)
    sp.add_argument("--db", default=None)
    sp.set_defaults(func=cmd_info)

    sp = sub.add_parser("run", help="跑六阶段闭环")
    sp.add_argument("--instance", required=True)
    sp.add_argument("--adapter", default="replay-agent", choices=list_runner_names(),
                    help="作答 runner（默认 replay-agent 零依赖自检）")
    sp.add_argument("--model", default=None, help="model 名（默认按 adapter 推导）")
    sp.add_argument("--run-id", default=None)
    sp.add_argument("--timeout", type=int, default=None, help="harness 测试超时秒数")
    sp.add_argument("--output-dir", default=None)
    sp.add_argument("--dry-run", action="store_true", help="只打印六阶段命令链")
    sp.add_argument("--force", action="store_true", help="忽略断点续跑，全量重来")
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("candidates", help="推荐适合上手的题（p2p/patch_size 升序）")
    sp.add_argument("--split", default=None)
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--db", default=None)
    sp.set_defaults(func=cmd_candidates)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
