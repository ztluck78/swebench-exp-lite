# scripts/windows/install.ps1
#
# 0.2.0 起：Windows 11 幂等安装入口（与 macOS start.sh 一一对应）。
#
# 五步：环境检查 → venv+依赖 → DB → 评测镜像 → S2 预热 + 自检。
# 与 start.sh 的"幂等 + 重复执行跳过"语义一致。
#
# 运行：
#   pwsh scripts/windows/install.ps1
# 或
#   ./scripts/windows/install.cmd   （自动转发到 pwsh / powershell 5.1）
#
# 行尾：CRLF（见 .gitattributes）。

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# 共享函数（颜色 / 路径 / 步骤 / 检查）
. (Join-Path $PSScriptRoot "_common.ps1")

Write-Info "swebench-exp-lite Windows 11 安装入口（0.2.0 pre-release）"
Write-Info "仓库根: $Script:RepoRoot"

# Step 1-5
if (-not (Step-EnvCheck))      { exit 1 }
Step-VenvAndDeps
Step-DbDownload
Step-EvalImage
Step-S2Prepare

# 自检
Step-SelfCheck

Write-Host ""
Write-Info "安装完成。下一步：pwsh scripts/windows/run-demo.ps1（replay-agent 闭环演示，2-5 分钟）"
