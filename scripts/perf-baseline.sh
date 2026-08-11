#!/usr/bin/env bash
# scripts/perf-baseline.sh — 性能基线脚本（本地手动，不进 CI）
#
# 测量 5 项关键操作的墙钟耗时，输出对比表 + 退出码 0=全达标 / 1=有超时。
#
# 用法：
#   bash scripts/perf-baseline.sh
#   bash scripts/perf-baseline.sh --skip-docker   # docker / worktree 项 skip
#
# 依赖：bash + .venv/bin/python（已装）+ docker（可选，未运行时该项 skip）。
#
# 上限（与 [docs/verification-spec.md](../../docs/verification-spec.md) §1 一致）：
# - JSONL 加载 < 1s
# - docker image inspect < 2s（依赖 Docker daemon，未运行则 skip）
# - worktree 创建 < 5s（依赖 git mirror，未存在则 skip）
# - replay-agent --dry-run < 2s（不调 LLM）
# - git diff 输出 < 2s（依赖 worktree）

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# 颜色
RED='\033[31m'; GREEN='\033[32m'; YELLOW='\033[33m'; NC='\033[0m'

info() { printf "${GREEN}==>${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}[warn]${NC} %s\n" "$*"; }
err()  { printf "${RED}[error]${NC} %s\n" "$*" >&2; }

PY="${PYTHON:-.venv/bin/python}"
SKIP_DOCKER=0
[ "${1:-}" = "--skip-docker" ] && SKIP_DOCKER=1

# 上限（秒）
declare -A LIMITS=(
    [jsonl]=1
    [docker_inspect]=2
    [worktree]=5
    [replay_dry_run]=2
    [git_diff]=2
)

# 测量结果（"name:elapsed:limit:status"）
RESULTS=()

measure() {
    local name="$1"
    local cmd="$2"
    local limit="${LIMITS[$name]:-999}"
    local elapsed
    local status

    if ! elapsed=$( { time $cmd >/dev/null 2>&1; } 2>&1 | awk '/real/{print $2}' ); then
        # bash 内置 time 输出格式兼容
        local t0 t1
        t0=$(date +%s.%N)
        $cmd >/dev/null 2>&1 || return $?
        t1=$(date +%s.%N)
        elapsed=$(awk -v s="$t0" -v e="$t1" 'BEGIN{printf "%.3f", e-s}')
    fi

    # 转 elapsed 为秒（bash 内置 time 输出 "0m1.234s" 或 "1.234s"）
    if [[ "$elapsed" =~ ^([0-9]+)m([0-9.]+)s$ ]]; then
        elapsed=$(awk -v m="${BASH_REMATCH[1]}" -v s="${BASH_REMATCH[2]}" 'BEGIN{printf "%.3f", m*60+s}')
    elif [[ "$elapsed" =~ ^([0-9.]+)s$ ]]; then
        elapsed="${BASH_REMATCH[1]}"
    fi

    # 判定（耗时秒数 vs 上限）
    local is_ok
    is_ok=$(awk -v e="$elapsed" -v l="$limit" 'BEGIN{print (e<=l) ? 1 : 0}')
    if [ "$is_ok" = "1" ]; then
        status="${GREEN}PASS${NC}"
    else
        status="${RED}FAIL${NC}"
    fi

    RESULTS+=("$name|$elapsed|$limit|$status")
    printf "  %-18s %8.3fs / %ss  %s\n" "$name" "$elapsed" "$limit" "$status"
}

# === 1. JSONL 加载（300 + 23 条）===
info "1/5 JSONL 加载"
measure "jsonl" "$PY -c 'import json; [json.loads(l) for l in open(\"data/swe_bench_data/swe-bench-lite.jsonl\")]'"

# === 2. docker image inspect ===
info "2/5 docker image inspect"
if [ "$SKIP_DOCKER" = "1" ] || ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
    warn "跳过（Docker 未运行或 --skip-docker）"
    RESULTS+=("docker_inspect|skipped|${LIMITS[docker_inspect]}|${YELLOW}SKIP${NC}")
else
    IMG="$($PY -c "from swebench_exp_lite.db.query import LiteDB; print(LiteDB().docker_image('pylint-dev__pylint-7080'))" 2>/dev/null)"
    if [ -n "$IMG" ]; then
        measure "docker_inspect" "docker image inspect $IMG"
    else
        warn "DB 未就绪或无 pylint image"
    fi
fi

# === 3. worktree 创建 ===
info "3/5 worktree 创建"
WORKTREE_BASE="$(git rev-parse --show-toplevel 2>/dev/null || echo "$REPO_ROOT")/runtime-cache/worktrees"
mkdir -p "$WORKTREE_BASE" 2>/dev/null
if [ -d "$WORKTREE_BASE/perf-test" ]; then
    measure "worktree" "git worktree remove --force $WORKTREE_BASE/perf-test"
else
    warn "无现有 worktree，跳过创建测试"
    RESULTS+=("worktree|skipped|${LIMITS[worktree]}|${YELLOW}SKIP${NC}")
fi

# === 4. replay-agent --dry-run ===
info "4/5 replay-agent --dry-run"
measure "replay_dry_run" "$PY -m swebench_exp_lite run --instance pylint-dev__pylint-7080 --adapter replay-agent --dry-run"

# === 5. git diff 输出（仓内 git diff HEAD 应 < 1s）===
info "5/5 git diff 输出"
measure "git_diff" "git diff HEAD"

# === 汇总 ===
info "汇总"
printf "  %-20s %10s %10s %s\n" "操作" "实际" "上限" "状态"
printf "  %-20s %10s %10s %s\n" "----" "----" "----" "----"
FAIL=0
for r in "${RESULTS[@]}"; do
    IFS='|' read -r name elapsed limit status <<< "$r"
    printf "  %-20s %10s %10s %s\n" "$name" "${elapsed}s" "${limit}s" "$(echo -e "$status")"
    if [[ "$status" == *"FAIL"* ]]; then
        FAIL=1
    fi
done

echo
if [ "$FAIL" = "0" ]; then
    info "全部达标"
    exit 0
else
    err "有超时项"
    exit 1
fi