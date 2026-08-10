# scripts/windows/check-agents.ps1
#
# 0.2.0 起：Windows 11 Agent CLI 可用性检测（与 macOS check-agents.sh 一一对应）。
#
# 四个品牌平行支持，无首选；未装的 CLI 给出安装指引。
# 一个都没装也能跑：replay-agent 零依赖兜底（./run-demo.cmd / run-demo.ps1）。
#
# 行尾：CRLF（见 .gitattributes）。

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "_common.ps1")

Write-Info "==> 检测四个 Agent CLI"
$found = 0

function Check-Agent {
    param(
        [Parameter(Mandatory=$true)][string]$Name,
        [Parameter(Mandatory=$true)][string]$Bin,
        [Parameter(Mandatory=$true)][string]$Adapter,
        [Parameter(Mandatory=$true)][string]$Hint
    )
    if (Test-Command $Bin) {
        Write-Host ("  [可用] {0,-14} ({1,-10}) -> run --adapter {2}" -f $Name, $Bin, $Adapter) -ForegroundColor Green
        $script:found++
    } else {
        Write-Host ("  [缺失] {0,-14} 安装：{1}" -f $Name, $Hint) -ForegroundColor Yellow
    }
}

Check-Agent "Kimi CLI"     "kimi"     "kimi-agent"     "pip install kimi-cli && kimi auth login"
Check-Agent "Qwen Code"    "qwen"     "qwen-agent"     "npm install -g @qwen-code/qwen-code"
Check-Agent "MiMo Code"    "mimo"     "mimo-agent"     "安装 MiMo Code CLI 并确保 PATH 含 ~/.mimocode/bin/mimo"
Check-Agent "opencode"     "opencode" "opencode-agent" "npm i -g opencode-ai 并确保 PATH 含 ~/.npm-global/bin/opencode"

Write-Host ""
if ($script:found -eq 0) {
    Write-Info "没有检测到可用的 Agent CLI。不影响体验闭环："
    Write-Host "  pwsh scripts/windows/run-demo.ps1    # replay-agent 零依赖自检（回放 gold patch）"
    Write-Info "装好任一 CLI 后即可换真实 Agent 做题："
    Write-Host "  pwsh -m swebench_exp_lite run --instance $Script:DemoInstance --adapter kimi-agent"
    Write-Info "详见 GETTING-STARTED.md 第 5 章。"
} else {
    Write-Info "检测到 $script:found 个可用 CLI。用法示例："
    Write-Host "  pwsh -m swebench_exp_lite run --instance $Script:DemoInstance --adapter <上面的 adapter 名>"
    Write-Info "选题参考：pwsh -m swebench_exp_lite candidates"
}
