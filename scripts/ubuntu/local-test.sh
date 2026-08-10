#!/usr/bin/env bash
# scripts/ubuntu/local-test.sh — Ubuntu x86_64 本地集成测试
#
# 0.3.0 起：Ubuntu 本地集成测试（与 scripts/local-test.sh 一一对应，
# 针对 Ubuntu 定制 Docker 诊断提示）。
#
# 完整跑 install + red-line demo + 校验 result.json。
# 是 CI 静态 + 单测之外**主要**的"真跑通"验证手段。
#
# 用法：
#   bash scripts/ubuntu/local-test.sh                   # 跑 install + demo
#   bash scripts/ubuntu/local-test.sh --skip-install   # 只跑 demo（install 已跑过）
#
# 退出码 0 = 通过；非 0 = 失败。
# 失败时输出诊断建议。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

DEMO_INSTANCE="pylint-dev__pylint-7080"
RESULT_PATH="output/${DEMO_INSTANCE}/result.json"
SKIP_INSTALL=0

if [ "${1:-}" = "--skip-install" ]; then
    SKIP_INSTALL=1
fi

# 颜色输出
RED='\033[31m'
GREEN='\033[32m'
YELLOW='\033[33m'
NC='\033[0m'

info() { printf "${GREEN}==>${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}[warn]${NC} %s\n" "$*"; }
err()  { printf "${RED}[error]${NC} %s\n" "$*" >&2; }

# === Step 1: 环境检查 ===
info "Step 1/4: 环境检查"
if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
    err "找不到 python3 / python（请装 Python >= 3.10：sudo apt install python3）"
    exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
    err "找不到 docker（请安装 Docker Engine）"
    echo ""
    echo "安装方式（推荐 Docker CE）："
    echo "  https://docs.docker.com/engine/install/ubuntu/"
    echo "  或：sudo apt install docker.io"
    echo "  注意：不推荐 snap 安装（权限模型不同）"
    exit 1
fi
if ! docker info >/dev/null 2>&1; then
    err "docker daemon 未运行"
    echo ""
    echo "诊断："
    echo "  - 启动 Docker：sudo systemctl start docker"
    echo "  - 开机自启：    sudo systemctl enable docker"
    echo "  - 检查状态：    sudo systemctl status docker"
    echo "  - 权限问题：    sudo usermod -aG docker \$USER && newgrp docker"
    exit 1
fi
info "环境 OK"

# === Step 2: install ===
if [ "$SKIP_INSTALL" = "1" ]; then
    info "Step 2/4: 跳过 install（--skip-install）"
else
    info "Step 2/4: 跑 install（bash scripts/ubuntu/install.sh）"
    if ! bash scripts/ubuntu/install.sh; then
        err "install 失败（看上方输出）"
        echo ""
        echo "诊断："
        echo "  - 确认 Docker daemon 在跑：sudo systemctl status docker"
        echo "  - 确认 docker 组权限：groups | grep docker"
        echo "  - 确认 python3-venv 已装：python3 -m venv --help"
        echo "  - 确认 4GB 镜像拉得到：docker pull swebench/sweb.eval.x86_64.${DEMO_INSTANCE}:latest"
        echo "  - GFW 用户设 SWEBENCH_LITE_OSS 走 OSS tar 降级"
        exit 1
    fi
    info "install OK"
fi

# === Step 3: red-line demo ===
info "Step 3/4: 跑 red-line demo（bash scripts/ubuntu/run-demo.sh）"
if ! bash scripts/ubuntu/run-demo.sh; then
    err "demo 失败"
    exit 1
fi
info "demo OK"

# === Step 4: 校验 result.json ===
info "Step 4/4: 校验 result.json"
if [ ! -f "$RESULT_PATH" ]; then
    err "未找到 $RESULT_PATH"
    exit 1
fi

# 用 python 解析 + 校验（避免 jq 依赖）
RESOLVED=$(.venv/bin/python -c "
import json, sys
d = json.load(open('$RESULT_PATH'))
print(d.get('resolved'), d.get('report_source'))
")
RESOLVED_BOOL=$(echo "$RESOLVED" | awk '{print $1}')
REPORT_SOURCE=$(echo "$RESOLVED" | awk '{print $2}')

if [ "$RESOLVED_BOOL" != "True" ]; then
    err "result.json.resolved != true（actual: $RESOLVED_BOOL）"
    echo "  result.json 全文："
    cat "$RESULT_PATH"
    exit 1
fi

if [ "$REPORT_SOURCE" != "instance_report" ]; then
    warn "report_source = $REPORT_SOURCE（不是 instance_report，可能走降级路径）"
fi

info "本地集成测试通过"
echo ""
echo "  result.json:     $RESULT_PATH"
echo "  resolved:        $RESOLVED_BOOL"
echo "  report_source:   $REPORT_SOURCE"
echo ""
echo "  这是 replay-agent 零依赖跑通；不代表任何模型能力。"
echo "  跑真实 Agent：.venv/bin/python -m swebench_exp_lite run --instance ${DEMO_INSTANCE} --adapter kimi-agent"
