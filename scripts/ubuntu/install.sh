#!/usr/bin/env bash
# scripts/ubuntu/install.sh — Ubuntu x86_64 幂等安装入口
#
# 0.3.0 起：Ubuntu 幂等安装（与 macOS start.sh / Windows install.ps1 一一对应）。
#
# 五步：环境检查 → venv+依赖 → DB → 评测镜像 → S2 预热 + 自检。
# 与 start.sh 的"幂等 + 重复执行跳过"语义一致。
#
# 运行：
#   bash scripts/ubuntu/install.sh
#
# 行尾：LF（见 .gitattributes）。
set -euo pipefail

# 共享函数（颜色 / 路径 / 步骤 / 检查）
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

info "swebench-exp-lite Ubuntu x86_64 安装入口（0.3.0）"
info "仓库根: $REPO_ROOT"

# Step 1-5
step_env_check     || exit 1
step_venv_and_deps
step_db_download
step_eval_image
step_s2_prepare

# 自检
step_self_check

echo
info "安装完成。下一步：bash scripts/ubuntu/run-demo.sh（replay-agent 闭环演示，2-5 分钟）"
