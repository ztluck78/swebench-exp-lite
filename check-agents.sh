#!/usr/bin/env bash
# check-agents.sh — 检测本机可用的 Coding Agent CLI
#
# 四个品牌平行支持，无首选；未装的 CLI 给出安装指引。
# 一个都没装也能跑：replay-agent 零依赖兜底（./run_demo.sh）。
set -u
cd "$(dirname "$0")"

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
check "Qwen Code"    qwen     qwen-agent     "npm install -g @qwen-code/qwen-code 或 brew install qwen-code"
check "MiMo Code"    mimo     mimo-agent     "安装 MiMo Code CLI 并确保 PATH 含 ~/.mimocode/bin/mimo"
check "opencode"     opencode opencode-agent "npm i -g opencode-ai 并确保 PATH 含 ~/.npm-global/bin/opencode"

echo
if [ "$found" -eq 0 ]; then
    cat <<'EOF'
没有检测到可用的 Agent CLI。不影响体验闭环：
  ./run_demo.sh                  # replay-agent 零依赖自检（回放 gold patch）
装好任一 CLI 后即可换真实 Agent 做题：
  .venv/bin/python -m swebench_exp_lite run --instance pylint-dev__pylint-7080 --adapter kimi-agent
详见 GETTING-STARTED.md 第 5 章。
EOF
else
    echo "检测到 $found 个可用 CLI。用法示例："
    echo "  .venv/bin/python -m swebench_exp_lite run --instance pylint-dev__pylint-7080 --adapter <上面的 adapter 名>"
    echo "选题参考：.venv/bin/python -m swebench_exp_lite candidates"
fi
