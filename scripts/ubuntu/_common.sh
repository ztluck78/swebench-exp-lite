#!/usr/bin/env bash
# scripts/ubuntu/_common.sh — Ubuntu x86_64 共享函数库
#
# 0.3.0 起：Ubuntu 适配共享函数库，被 install.sh / run-demo.sh /
# check-agents.sh 三个入口脚本 source 引用。
#
# 与 start.sh（macOS 0.1.0 红线脚本）和 scripts/windows/_common.ps1
# 保持 5 步幂等语义一致。
#
# Ubuntu 专属处理（相对 macOS 的差异点）：
# - Docker daemon 启动提示：systemctl start docker（非 Docker Desktop）
# - docker 组权限检测：usermod -aG docker
# - python3-venv 包检测：apt install python3-venv
#
# 行尾：LF（.gitattributes *.sh text eol=lf 已覆盖）。

set -euo pipefail

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------
# 仓根：本脚本在 scripts/ubuntu/ 下，向上两级
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV_DIR="$REPO_ROOT/.venv"
VENV_PY="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"
DEMO_INSTANCE="pylint-dev__pylint-7080"

# 0.1.0 资源地址（与 start.sh 保持一致；env 可覆盖）
RELEASE_DB_URL="${SWEBENCH_LITE_DB_URL:-https://github.com/ztluck78/swebench-exp-lite/releases/download/0.1.0/swe_bench.db}"
OSS_BASE="${SWEBENCH_LITE_OSS:-https://github-release-data.oss-cn-beijing.aliyuncs.com}"

# ---------------------------------------------------------------------------
# 颜色输出
# ---------------------------------------------------------------------------
RED='\033[31m'
GREEN='\033[32m'
YELLOW='\033[33m'
CYAN='\033[36m'
NC='\033[0m'

step() { printf '\n%s==> [%s] %s%s\n' "$CYAN" "$1" "$2" "$NC"; }
info() { printf '%s%s%s\n' "$GREEN" "$*" "$NC"; }
warn() { printf '%s[warn] %s%s\n' "$YELLOW" "$*" "$NC"; }
err()  { printf '%s[error] %s%s\n' "$RED" "$*" "$NC" >&2; }

# ---------------------------------------------------------------------------
# Step 1: 环境检查（Python >= 3.10 + Docker + Ubuntu 专属前置）
# ---------------------------------------------------------------------------
step_env_check() {
    step "1/5" "环境检查（python>=3.10 + docker + Ubuntu 前置）"

    # Python 检查（Ubuntu 优先 python3，回退 python）
    PY="${PYTHON:-python3}"
    if ! command -v "$PY" >/dev/null 2>&1; then
        PY="python"
        if ! command -v "$PY" >/dev/null 2>&1; then
            err "找不到 python3 / python（请装 Python >= 3.10：sudo apt install python3）"
            return 1
        fi
    fi
    "$PY" - <<'PYEOF'
import sys
assert sys.version_info >= (3, 10), f"需要 Python>=3.10，当前 {sys.version}"
print(f"python {sys.version.split()[0]} OK")
PYEOF

    # python3-venv 检测（Ubuntu 最小化安装不带 venv 模块）
    if ! "$PY" -m venv --help >/dev/null 2>&1; then
        err "python3-venv 模块缺失。请运行：sudo apt install python3-venv"
        return 1
    fi
    info "python3-venv OK"

    # Docker 检查
    if ! command -v docker >/dev/null 2>&1; then
        err "未安装 docker。请安装 Docker Engine："
        err "  推荐：https://docs.docker.com/engine/install/ubuntu/"
        err "  或：  sudo apt install docker.io"
        err "  注意：不推荐 snap 安装（权限模型不同）"
        return 1
    fi

    # Docker daemon 存活
    if ! docker info >/dev/null 2>&1; then
        err "docker daemon 未运行。请尝试："
        err "  sudo systemctl start docker"
        err "  sudo systemctl enable docker  # 开机自启"
        return 1
    fi

    # Docker 组权限（Ubuntu 专属坑：新装 Docker 后用户未加 docker 组）
    if ! groups | grep -q '\bdocker\b'; then
        warn "当前用户不在 docker 组。如后续 docker 命令报 permission denied，请运行："
        warn "  sudo usermod -aG docker \$USER && newgrp docker"
        warn "  或注销重新登录"
    fi

    info "docker OK"
    return 0
}

# ---------------------------------------------------------------------------
# Step 2: venv + 依赖（幂等）
# ---------------------------------------------------------------------------
step_venv_and_deps() {
    step "2/5" "虚拟环境与依赖（幂等）"

    if [ ! -x "$VENV_PY" ]; then
        "$PY" -m venv "$VENV_DIR"
        info "已创建 .venv"
    else
        info "[skip] .venv 已存在"
    fi
    "$VENV_PIP" install --quiet --upgrade pip
    "$VENV_PIP" install --quiet -e .
    info "依赖就绪（docker/tqdm/unidiff/requests 四件套）"
}

# ---------------------------------------------------------------------------
# Step 3: 题库 DB 下载（幂等）
# ---------------------------------------------------------------------------
step_db_download() {
    step "3/5" "题库 database/swe_bench.db（幂等）"

    local db_path="$REPO_ROOT/database/swe_bench.db"
    if [ -f "$db_path" ]; then
        info "[skip] DB 已存在: $db_path"
        return 0
    fi

    info "DB 缺失，尝试下载: $RELEASE_DB_URL"
    if curl -fL --retry 2 -o "$db_path" "$RELEASE_DB_URL"; then
        info "下载完成"
    else
        rm -f "$db_path"
        err "DB 下载失败（Release URL 可能异常或网络受限）。"
        err "请手动把 swe_bench.db 放到 database/ 下后重跑本脚本。"
        err "或设置 SWEBENCH_LITE_DB_URL 环境变量指向自定义地址。"
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Step 4: 评测镜像（inspect 短路 / pull / OSS tar 降级）
# ---------------------------------------------------------------------------
step_eval_image() {
    step "4/5" "评测镜像（inspect 短路 / pull / OSS tar 降级）"

    local eval_image
    eval_image="$("$VENV_PY" -c "
from swebench_exp_lite.db.query import LiteDB
print(LiteDB().docker_image('$DEMO_INSTANCE'))")"

    if docker image inspect "$eval_image" >/dev/null 2>&1; then
        info "[skip] 镜像本地已存在: $eval_image"
        return 0
    fi

    info "本地缺失，尝试官方拉取: docker pull $eval_image"
    if docker pull "$eval_image"; then
        info "拉取完成"
        return 0
    fi

    local tarball="sweb.eval.x86_64.pylint-dev_1776_pylint-7080.tar.gz"
    info "官方拉取失败，降级 OSS tar: $OSS_BASE/$tarball"
    if curl -fL --retry 2 -o "/tmp/$tarball" "$OSS_BASE/$tarball" \
       && docker load -i "/tmp/$tarball"; then
        rm -f "/tmp/$tarball"
        info "OSS tar 加载完成"
    else
        rm -f "/tmp/$tarball"
        err "镜像获取失败。可手动执行："
        err "  docker pull $eval_image"
        err "  或 docker load -i <本地 tar 路径>"
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Step 5: demo 预热（S2_prepare：镜像/目录就绪）
# ---------------------------------------------------------------------------
step_s2_prepare() {
    step "5/5" "demo 预热（S2_prepare：镜像/目录就绪）"

    "$VENV_PY" - <<PYEOF
from swebench_exp_lite.pipeline import TaskContext
from swebench_exp_lite.pipeline.stages.s2_prepare import S2Prepare
ctx = TaskContext.from_db("$DEMO_INSTANCE", run_id="warmup", adapter="replay-agent")
ctx.ensure_dirs()
S2Prepare().run(ctx)
print("S2_prepare 预热完成")
PYEOF
}

# ---------------------------------------------------------------------------
# 自检：list 冒烟 + DB 323 条断言
# ---------------------------------------------------------------------------
step_self_check() {
    step "自检" "list 冒烟 + DB 323 条断言"

    "$VENV_PY" -m swebench_exp_lite list --limit 3
    "$VENV_PY" - <<'PYEOF'
from swebench_exp_lite.db.query import LiteDB
n = LiteDB().count()
assert n == 323, f"题库应为 323 条，实际 {n}"
print(f"题库断言通过：{n} 条")
PYEOF
}
