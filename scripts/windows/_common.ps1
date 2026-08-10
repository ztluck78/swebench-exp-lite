# scripts/windows/_common.ps1
#
# 0.2.0 起：Windows 适配共享函数库，被 install.ps1 / run-demo.ps1 /
# check-agents.ps1 三个入口脚本 dot-source 引用。
#
# 0.1.0 时代只有 macOS bash 脚本（start.sh / run_demo.sh / check-agents.sh），
# 本文件是 PowerShell 端的等价"bash 函数库"——把测试输出、错误处理、
# 路径定位等重复代码集中一处。
#
# 行尾：CRLF（PowerShell 5.1 强依赖 CRLF；见 .gitattributes）。
# 编码：UTF-8 with BOM（PowerShell 5.1 在 zh-CN 系统下对无 BOM UTF-8 解析有坑）。

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ANSI 颜色（PowerShell 5.1 默认不支持 ANSI，需要先 enable）
$Host.UI.RawUI.WindowTitle = "swebench-exp-lite installer"

# ---------------------------------------------------------------------------
# 颜色常量（PowerShell 7+ 原生支持；5.1 退化到无色也不影响功能）
# ---------------------------------------------------------------------------
$Script:ColorReset   = "`e[0m"
$Script:ColorGreen   = "`e[32m"
$Script:ColorYellow  = "`e[33m"
$Script:ColorRed     = "`e[31m"
$Script:ColorCyan    = "`e[36m"

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------
# 仓根：本脚本在 scripts/windows/ 下，向上两级
$Script:RepoRoot = (Resolve-Path "$PSScriptRoot/../..").Path
$Script:VenvDir  = Join-Path $Script:RepoRoot ".venv"
$Script:VenvPy   = Join-Path $Script:VenvDir "Scripts/python.exe"
$Script:DemoInstance = "pylint-dev__pylint-7080"

# 0.1.0 资源地址（与 start.sh 保持一致；env 可覆盖）
$Script:ReleaseDbUrl = if ($env:SWEBENCH_LITE_DB_URL) {
    $env:SWEBENCH_LITE_DB_URL
} else {
    "https://github.com/ztluck78/swebench-exp-lite/releases/download/0.1.0/swe_bench.db"
}
$Script:OssBase = if ($env:SWEBENCH_LITE_OSS) {
    $env:SWEBENCH_LITE_OSS
} else {
    "https://github-release-data.oss-cn-beijing.aliyuncs.com"
}

# ---------------------------------------------------------------------------
# Test-Command：检测命令是否在 PATH 中（等价 bash `command -v`）
# ---------------------------------------------------------------------------
function Test-Command {
    param([Parameter(Mandatory=$true)][string]$Name)
    $found = Get-Command $Name -ErrorAction SilentlyContinue
    return [bool]$found
}

# ---------------------------------------------------------------------------
# Get-VenvPython：返回 .venv\Scripts\python.exe 绝对路径；不存在则抛错
# ---------------------------------------------------------------------------
function Get-VenvPython {
    if (-not (Test-Path $Script:VenvPy)) {
        throw "未找到 venv 解释器：$Script:VenvPy。请先运行 install.ps1 完成安装。"
    }
    return $Script:VenvPy
}

# ---------------------------------------------------------------------------
# Write-Step：带 ANSI 颜色 + 步骤编号的输出（等价 bash `printf '\n==> [%s] %s\n'`）
# ---------------------------------------------------------------------------
function Write-Step {
    param(
        [Parameter(Mandatory=$true)][string]$Step,
        [Parameter(Mandatory=$true)][string]$Message
    )
    $line = "==> [$Step] $Message"
    Write-Host ""
    Write-Host $line -ForegroundColor Cyan
}

# ---------------------------------------------------------------------------
# Write-Info / Write-Warn / Write-Err：带颜色的提示
# ---------------------------------------------------------------------------
function Write-Info {
    param([Parameter(Mandatory=$true)][string]$Message)
    Write-Host $Message -ForegroundColor Green
}

function Write-Warn {
    param([Parameter(Mandatory=$true)][string]$Message)
    Write-Host "[warn] $Message" -ForegroundColor Yellow
}

function Write-Err {
    param([Parameter(Mandatory=$true)][string]$Message)
    Write-Host "[error] $Message" -ForegroundColor Red
}

# ---------------------------------------------------------------------------
# Step-EnvCheck：环境检查（Python >= 3.10 + Docker Desktop 运行中）
# 返回 $true 表示通过；$false 表示失败
# ---------------------------------------------------------------------------
function Step-EnvCheck {
    Write-Step "1/5" "环境检查（python>=3.10 + docker）"

    # Python 检查（Windows 上用 python，不依赖 python3）
    $py = $null
    if (Test-Command "python") { $py = "python" }
    elseif (Test-Command "py") { $py = "py -3" }
    else {
        Write-Err "找不到 python。请先安装 Python >= 3.10（python.org 下载器）并加入 PATH。"
        return $false
    }
    $ver = & $py --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Err "python --version 失败：$ver"
        return $false
    }
    Write-Info "python OK: $ver"

    # Docker 检查
    if (-not (Test-Command "docker")) {
        Write-Err "未安装 docker（请装 Docker Desktop for Windows，启用 WSL2 backend）。"
        return $false
    }
    # Windows Docker Desktop 在 hosted runner 默认是 Windows containers mode；
    # load Linux 镜像会报 'cannot load linux image on windows'。查 DockerCli.exe 路径
    # 以便后续 Step-EvalImage 失败时能切到 Linux containers。
    $dockerCli = Join-Path $env:ProgramFiles "Docker\Docker\DockerCli.exe"
    $Script:DockerCliAvailable = Test-Path $dockerCli
    $Script:WslAvailable = [bool](Get-Command wsl -ErrorAction SilentlyContinue)
    if (-not $Script:DockerCliAvailable) {
        Write-Warn "DockerCli.exe 不在（hosted runner 常见）；daemon mode 切换可能受限"
    }
    if (-not $Script:WslAvailable) {
        Write-Warn "wsl 也不在；WSL2 docker load fallback 不可用"
    }
    docker info 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Err "docker daemon 未运行（请启动 Docker Desktop，等状态栏图标稳定后再试）。"
        return $false
    }
    Write-Info "docker OK"
    return $true
}

# ---------------------------------------------------------------------------
# Step-VenvAndDeps：创建 venv + 安装依赖（幂等）
# ---------------------------------------------------------------------------
function Step-VenvAndDeps {
    Write-Step "2/5" "虚拟环境与依赖（幂等）"

    if (-not (Test-Path (Join-Path $Script:VenvDir "Scripts/python.exe"))) {
        Write-Info "创建 .venv（首次安装）"
        python -m venv $Script:VenvDir
        if ($LASTEXITCODE -ne 0) { throw "venv 创建失败" }
    } else {
        Write-Info "[skip] .venv 已存在"
    }

    & $Script:VenvPy -m pip install --quiet --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade 失败" }
    & $Script:VenvPy -m pip install --quiet -e .
    if ($LASTEXITCODE -ne 0) { throw "pip install -e . 失败" }
    Write-Info "依赖就绪（docker/tqdm/unidiff/requests 四件套）"
}

# ---------------------------------------------------------------------------
# Step-DbDownload：题库 DB 下载（幂等）
# ---------------------------------------------------------------------------
function Step-DbDownload {
    Write-Step "3/5" "题库 database/swe_bench.db（幂等）"

    $dbPath = Join-Path $Script:RepoRoot "database/swe_bench.db"
    if (Test-Path $dbPath) {
        Write-Info "[skip] DB 已存在: $dbPath"
        return
    }

    Write-Info "DB 缺失，尝试下载: $Script:ReleaseDbUrl"
    try {
        Invoke-WebRequest -Uri $Script:ReleaseDbUrl -OutFile $dbPath -UseBasicParsing
    } catch {
        Remove-Item $dbPath -ErrorAction SilentlyContinue
        Write-Err "DB 下载失败：$($_.Exception.Message)"
        Write-Err "0.2.0 阶段 Release URL 可能异常或网络受限。请手动把 swe_bench.db 放到 database/ 下后重跑。"
        throw
    }
    Write-Info "下载完成"
}

# ---------------------------------------------------------------------------
# Step-EvalImage：评测镜像就绪（inspect 短路 / pull / OSS tar 降级）
# ---------------------------------------------------------------------------
function Step-EvalImage {
    Write-Step "4/5" "评测镜像（inspect 短路 / pull / OSS tar 降级）"

    # 通过 LiteDB 查询 demo 镜像名
    $evalImage = & $Script:VenvPy -c "
from swebench_exp_lite.db.query import LiteDB
print(LiteDB().docker_image('$Script:DemoInstance'))
"
    $evalImage = $evalImage.Trim()
    if (-not $evalImage) { throw "LiteDB 未返回镜像名" }

    docker image inspect $evalImage 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Info "[skip] 镜像本地已存在: $evalImage"
        return
    }

    Write-Info "本地缺失，尝试官方拉取: docker pull $evalImage"
    docker pull $evalImage 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        $tarball = "sweb.eval.x86_64.pylint-dev_1776_pylint-7080.tar.gz"
        $tarPath = Join-Path $env:TEMP $tarball
        Write-Info "官方拉取失败，降级 OSS tar: $Script:OssBase/$tarball"
        try {
            Invoke-WebRequest -Uri "$Script:OssBase/$tarball" -OutFile $tarPath -UseBasicParsing
        } catch {
            Write-Err "OSS tar 下载失败：$($_.Exception.Message)"
            throw
        }
        docker load -i $tarPath 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            # 诊断：重新调 docker load 抓错（不吞 stderr）
            $loadLog = & docker load -i $tarPath 2>&1
            $tarSize = if (Test-Path $tarPath) { (Get-Item $tarPath).Length } else { -1 }
            $firstLine = ($loadLog | Select-Object -First 1)
            $errExcerpt = if ($null -ne $firstLine) { $firstLine } else { '(无输出)' }
            Write-Err "OSS tar: path=$tarPath size=$tarSize bytes"
            Write-Err "docker load stderr: $errExcerpt"
            throw "docker load 失败 (size=$tarSize, err='$errExcerpt')"
        }
        Remove-Item $tarPath -ErrorAction SilentlyContinue
        Write-Info "OSS tar 加载完成"
    } else {
        Write-Info "拉取完成"
    }
}

# ---------------------------------------------------------------------------
# Step-S2Prepare：S2 预热（镜像/目录就绪）
# ---------------------------------------------------------------------------
function Step-S2Prepare {
    Write-Step "5/5" "demo 预热（S2_prepare：镜像/目录就绪）"

    & $Script:VenvPy -c @"
from swebench_exp_lite.pipeline import TaskContext
from swebench_exp_lite.pipeline.stages.s2_prepare import S2Prepare
ctx = TaskContext.from_db("$Script:DemoInstance", run_id="warmup", adapter="replay-agent")
ctx.ensure_dirs()
S2Prepare().run(ctx)
print("S2_prepare 预热完成")
"@
    if ($LASTEXITCODE -ne 0) { throw "S2 预热失败" }
}

# ---------------------------------------------------------------------------
# Step-SelfCheck：list 冒烟 + 323 条断言
# ---------------------------------------------------------------------------
function Step-SelfCheck {
    Write-Step "自检" "list 冒烟 + DB 323 条断言"

    & $Script:VenvPy -m swebench_exp_lite list --limit 3
    if ($LASTEXITCODE -ne 0) { throw "list 冒烟失败" }

    & $Script:VenvPy -c @"
from swebench_exp_lite.db.query import LiteDB
n = LiteDB().count()
assert n == 323, f"题库应为 323 条，实际 {n}"
print(f"题库断言通过：{n} 条")
"@
    if ($LASTEXITCODE -ne 0) { throw "DB 323 条断言失败" }
}

# ---------------------------------------------------------------------------
# Resolve-ResourcePath：解析 OSS / GitHub Release URL（兼容 env 覆盖）
# ---------------------------------------------------------------------------
function Resolve-ResourcePath {
    param(
        [Parameter(Mandatory=$true)][string]$RelativePath
    )
    # 默认走 OSS（macOS 兼容走法）；用户可用 env 切到自定义 URL
    $base = if ($env:SWEBENCH_LITE_OSS) { $env:SWEBENCH_LITE_OSS } else { $Script:OssBase }
    return "$base/$RelativePath"
}

# ---------------------------------------------------------------------------
# 顶层入口：被 dot-source 引用时不应自动跑 install
# 只有显式执行（.\_common.ps1）才会走到这里
# ---------------------------------------------------------------------------
if ($MyInvocation.InvocationName -ne ".") {
    Write-Warn "_common.ps1 是共享函数库，请用 install.ps1 / run-demo.ps1 / check-agents.ps1 入口。"
}
