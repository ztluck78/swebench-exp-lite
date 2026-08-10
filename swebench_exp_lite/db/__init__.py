"""swebench_exp_lite.db：题库数据层。

- `query.LiteDB`：swe_bench.db 的只读查询接口（从主仓 database/query.py 移植精简）。
- 本仓不带 build/validate 脚本：DB 由 start.sh 下载或手动放置；
  如需从 jsonl 重建，见 GETTING-STARTED.md FAQ（高级选项）。
"""
from __future__ import annotations

from pathlib import Path

# 仓库根 = swebench_exp_lite/ 的上一级
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# 数据库文件默认路径（相对仓库根；git 忽略，start.sh 下载或手动放置）
DEFAULT_DB_PATH = REPO_ROOT / "database" / "swe_bench.db"

# Lite 数据 jsonl 路径（随仓携带，harness 直接读本地文件，无需联网）
DATA_DIR = REPO_ROOT / "data" / "swe_bench_data"
TEST_JSONL = DATA_DIR / "swe-bench-lite.jsonl"
DEV_JSONL = DATA_DIR / "swe-bench-lite-dev.jsonl"

# Docker 镜像命名（与 answer_evaluator.harness.test_spec 保持一致）
DOCKER_NAMESPACE = "swebench"
DOCKER_TAG = "latest"

__all__ = [
    "REPO_ROOT", "DEFAULT_DB_PATH", "DATA_DIR",
    "TEST_JSONL", "DEV_JSONL",
    "DOCKER_NAMESPACE", "DOCKER_TAG",
]
