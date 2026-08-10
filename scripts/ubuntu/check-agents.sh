#!/usr/bin/env bash
# scripts/ubuntu/check-agents.sh — Ubuntu x86_64 Agent CLI 可用性检测
#
# 0.3.0 起：Ubuntu Agent CLI 检测（与 macOS check-agents.sh 一一对应）。
#
# 四个品牌平行支持，无首选；未装的 CLI 给出安装指引（Ubuntu 偏向）。
# 一个都没装也能跑：replay-agent 零依赖兜底（run-demo.sh）。
#
# 行尾：LF（见 .gitattributes）。
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_common.sh"

echo "==> 检测四个 Agent CLI"
found=0

check() {
    local name="$1" bin="$2" adapter="$3" hint="$4"
    if command -v "$bin" >/dev/null 2>&1; then
        printf '  [可用] %-14s %-10s → run --adapter %s\n' "$name" "($bin)" "$adapter"
        found=$((found + 1))
    else
        printf '  [缺失] %-14s 安装：%s\n' "$name" "$hint"
    fi
}

check "Kimi CLI"     kimi     kimi-agent     "pip install kimi-cli && kimi auth login"
check "Qwen Code"    qwen     qwen-agent     "npm install -g @qwen-code/qwen-code 或 snap install qwen-code"
check "MiMo Code"    mimo     mimo-agent     "安装 MiMo Code CLI 并确保 PATH 含 ~/.mimocode/bin/mimo"
check "opencode"     opencode opencode-agent "npm i -g opencode-ai 并确保 PATH 含 ~/.npm-global/bin/opencode"

echo
if [ "$found" -eq 0 ]; then
    cat <<'EOF'
没有检测到可用的 Agent CLI。不影响体验闭环：
  bash scripts/ubuntu/run-demo.sh      # replay-agent 零依赖自检（回放 gold patch）
装好任一 CLI 后即可换真实 Agent 做题：
  .venv/bin/python -m swebench_exp_lite run --instance pylint-dev__pylint-7080 --adapter kimi-agent
详见 GETTING-STARTED.md 第 5 章。
EOF
else
    echo "检测到 $found 个可用 CLI。用法示例："
    echo "  .venv/bin/python -m swebench_exp_lite run --instance pylint-dev__pylint-7080 --adapter <上面的 adapter 名>"
    echo "选题参考：.venv/bin/python -m swebench_exp_lite candidates"
fi
