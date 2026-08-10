# scripts/local-test.ps1 — Windows 本地集成测试
#
# 完整跑 install + red-line demo + 校验 result.json。
# 是 CI 静态 + 单测之外**主要**的"真跑通"验证手段。
#
# 用法：
#   pwsh scripts/local-test.ps1                  # 跑 install + demo
#   pwsh scripts/local-test.ps1 -SkipInstall     # 只跑 demo（install 已跑过）
#
# 退出码 0 = 通过；非 0 = 失败。
# 失败时输出诊断建议。
#
# 配合 plan §10 "Windows 11 真机验证"：本脚本是 Windows 验证版；
# macOS / Linux 用户跑 scripts/local-test.sh。
[CmdletBinding()]
param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"

$REPO_ROOT = (Resolve-Path "$PSScriptRoot/..").Path
Set-Location $REPO_ROOT

$DEMO_INSTANCE = "pylint-dev__pylint-7080"
$RESULT_PATH = "output/$DEMO_INSTANCE/result.json"

function Write-Info([string]$msg) { Write-Host "==> $msg" -ForegroundColor Green }
function Write-Warn([string]$msg) { Write-Host "[warn] $msg" -ForegroundColor Yellow }
function Write-Err([string]$msg)  { Write-Host "[error] $msg" -ForegroundColor Red }

# === Step 1: 环境检查 ===
Write-Info "Step 1/4: 环境检查"
$py = $null
if (Get-Command python -ErrorAction SilentlyContinue) { $py = "python" }
else { Write-Err "找不到 python（请装 Python ≥ 3.10，python.org 下载器）"; exit 1 }

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Err "找不到 docker（请装 Docker Desktop for Windows，启用 WSL2 backend）"
    exit 1
}
$dockerInfo = & docker info 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Err "docker daemon 未运行（请启动 Docker Desktop，等 tray 图标变绿）"
    exit 1
}
Write-Info "环境 OK"

# === Step 2: install ===
if ($SkipInstall) {
    Write-Info "Step 2/4: 跳过 install（-SkipInstall）"
} else {
    Write-Info "Step 2/4: 跑 install（pwsh scripts/windows/install.ps1）"
    try {
        & pwsh scripts/windows/install.ps1
    } catch {
        Write-Err "install 失败：$_"
        Write-Host ""
        Write-Host "诊断："
        Write-Host "  - 确认 Docker Desktop 在跑（tray 图标变绿）"
        Write-Host "  - 确认 Docker 在 Linux containers 模式（右键 tray → Switch to Linux containers）"
        Write-Host "  - 确认 4GB 镜像拉得到：docker pull swebench/sweb.eval.x86_64.${DEMO_INSTANCE}:latest"
        Write-Host "  - GFW 用户设 `$env:SWEBENCH_LITE_OSS 走 OSS tar 降级"
        exit 1
    }
    Write-Info "install OK"
}

# === Step 3: red-line demo ===
Write-Info "Step 3/4: 跑 red-line demo（pwsh scripts/windows/run-demo.ps1）"
try {
    & pwsh scripts/windows/run-demo.ps1
} catch {
    Write-Err "demo 失败：$_"
    exit 1
}
Write-Info "demo OK"

# === Step 4: 校验 result.json ===
Write-Info "Step 4/4: 校验 result.json"
if (-not (Test-Path $RESULT_PATH)) {
    Write-Err "未找到 $RESULT_PATH"
    exit 1
}

$resolved = $false
$reportSource = ""
try {
    $r = Get-Content $RESULT_PATH -Raw | ConvertFrom-Json
    $resolved = $r.resolved
    $reportSource = $r.report_source
} catch {
    Write-Err "result.json 解析失败：$_"
    Get-Content $RESULT_PATH
    exit 1
}

if (-not $resolved) {
    Write-Err "result.json.resolved != true（actual: $resolved）"
    Get-Content $RESULT_PATH
    exit 1
}

if ($reportSource -ne "instance_report") {
    Write-Warn "report_source = $reportSource（不是 instance_report，可能走降级路径）"
}

Write-Info "✓ 本地集成测试通过"
Write-Host ""
Write-Host "  result.json:     $RESULT_PATH"
Write-Host "  resolved:        $resolved"
Write-Host "  report_source:   $reportSource"
Write-Host ""
Write-Host "  这是 replay-agent 零依赖跑通；不代表任何模型能力。"
Write-Host "  跑真实 Agent：pwsh -m swebench_exp_lite run --instance $DEMO_INSTANCE --adapter kimi-agent"
