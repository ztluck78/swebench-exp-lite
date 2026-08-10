# Windows 11 用户手册 — swebench-exp-lite

> 面向 Windows 11 用户的完整操作手册。从"装软件"到"跑通 demo"全流程，~1-1.5 小时。
>
> **macOS / Linux 用户**：请改用 [GETTING-STARTED.md](../GETTING-STARTED.md)。
> **开发者 / 维护者**：请看 [docs/windows-11-port.md](windows-11-port.md)（移植笔记）和 [scripts/windows/README.md](../scripts/windows/README.md)（技术参考）。

---

## 1. 这是什么 / 适合谁

**swebench-exp-lite** 是一个 SWE-bench 教学实验平台，让你本地跑"出题 → Agent 做题 → 自动打分"的最小闭环。**不需要联网**跑数据集（数据集随仓），**不需要大模型**（`replay-agent` 跑通即可验证链路）。

**这次要做什么**（3 步）：
1. 装 4 个软件（Python / Git / Docker Desktop / PowerShell 7+）
2. Clone 项目
3. 跑两个命令：`install.ps1` + `run-demo.ps1`

**期望结果**：`output\pylint-dev__pylint-7080\result.json` 含 `"resolved": true`。

> **零 LLM 风险**：`replay-agent` 把官方 gold patch 直接写回评分链路，不调任何模型 API，不会产生任何费用。

## 2. 环境准备（15-25 分钟一次性，一般网络）

> 按典型家庭/办公网络（50-100 Mbps）估算。慢网络会拉长——主要是 Docker Desktop 1GB+ 下载。
> 踩坑场景（Python 未勾 PATH / Docker WSL2 backend 未启等）额外 +10-20 min。

### 系统要求

| 项 | 要求 |
|---|---|
| OS | Windows 11 x86_64（Win10 不在官方支持） |
| RAM | ≥ 8 GB（推荐 16 GB） |
| 磁盘 | ≥ 20 GB 可用（Docker 镜像 + 评测容器） |
| 网络 | 拉 4GB 评测镜像（GFW 用户会自动走阿里云 OSS 降级） |

### 必备软件清单

| 软件 | 来源 | 装时关键选项 |
|---|---|---|
| **Python 3.10+** | [python.org](https://www.python.org/downloads/windows/) | **勾 "Add Python to PATH"**（必勾！）|
| **Git** | [git-scm.com](https://git-scm.com/download/win) | 默认即可 |
| **Docker Desktop for Windows** | [docker.com](https://www.docker.com/products/docker-desktop/) | 装完**必须重启 Windows** |
| **PowerShell 7+**（推荐）| `winget install Microsoft.PowerShell` | 装后用 `pwsh` 命令（不是 `powershell`） |

### Docker Desktop 必做

装完 Docker Desktop 后：

1. **重启 Windows**（WSL2 kernel 需要）
2. 打开 Docker Desktop，等任务栏 tray 图标**变绿** = daemon 起来
3. 打开 Settings → Resources → WSL Integration
4. 确认 "Enable integration with my default WSL distro" 已勾
5. 退出 Settings（自动保存）

**这一步是整个流程最容易失败的一步**——Docker Desktop 没装好、daemon 没启、WSL2 没启用都会让后续 install 失败。

### 验证（每装完一个软件就跑一下）

```powershell
# PowerShell 7+ 中跑（Win+R 输入 `pwsh`）
python --version        # 应输出 Python 3.10.x 或更高
git --version          # 应输出 git version 2.x
docker --version       # 应输出 Docker version 24.x
docker info            # 应输出 Server Version（关键：验证 daemon 在跑）
pwsh --version         # 应输出 PowerShell 7.x
```

**如果 `docker info` 报 "Cannot connect to Docker daemon"**：
- 任务栏找 Docker 图标，确保是"运行中"状态（图标不是灰的）
- 必要时右键 → Restart

## 3. 项目拉取（5 分钟）

```powershell
cd C:\Users\<你的用户名>\Projects
git clone git@github.com:ztluck78/swebench-exp-lite.git
cd swebench-exp-lite
```

> **没用过 SSH？** 浏览器登录 GitHub → 右上角头像 → Settings → SSH and GPG keys → New SSH key（按 GitHub 提示操作）。或者直接用 HTTPS：`git clone https://github.com/ztluck78/swebench-exp-lite.git`

### 目录结构（速览）

```
swebench-exp-lite/
├── README.md                 # 项目门面
├── GETTING-STARTED.md        # 跨平台教程（macOS/Linux）
├── docs/
│   └── user-guide-windows.md  # ← 你正在读
├── start.sh / run_demo.sh    # macOS / Linux 入口（你不用看）
├── scripts/windows/          # Windows 入口
│   ├── install.ps1           # 一键安装
│   ├── run-demo.ps1          # 一键跑 demo
│   ├── check-agents.ps1      # 检测 Agent CLI
│   ├── _common.ps1           # 共享函数库
│   ├── install.cmd / run-demo.cmd  # .cmd 兜底转发
│   └── README.md             # 开发者向技术参考
└── swebench_exp_lite/        # Python 包（你不用动）
```

**你接下来要改动的**：只有 `scripts/windows/*.ps1`（如果要改）——`swebench_exp_lite/` 是冻结的 Python 包。

## 4. 一键安装（5-10 分钟）

```powershell
# 首次以 PowerShell 7+ 跑（Win+R → pwsh）
pwsh scripts/windows/install.ps1
```

**会跑 5 步**：

| Step | 做什么 | 首次耗时 | 你看到 |
|---|---|---|---|
| 1/5 | 环境检查 | < 1s | `python OK: Python 3.10.x` `docker OK` |
| 2/5 | 装 venv + 四件套 | 30s | `依赖就绪（docker/tqdm/unidiff/requests 四件套）`|
| 3/5 | 下题库 DB | 1s | `下载完成` |
| 4/5 | 拉评测镜像 | 3-5 min | `Loaded image: swebench/sweb.eval.x86_64.${DEMO_INSTANCE}:latest` |
| 5/5 | S2 预热 + 自检 | < 1s | `题库断言通过：323 条` |

**完成标志**：屏幕底部看到 `安装完成。下一步：pwsh scripts/windows/run-demo.ps1`。

### 幂等性

重复跑 `install.ps1` 跳过已就绪步骤，秒过。**日常用不到重装**——只有环境异常（Docker 重装、Python 升级）才重跑。

### 失败怎么办

**Step 1 失败**（环境检查不通过）：

```
[error] 未找到 python（请装 Python ≥ 3.10，python.org 下载器）
```
→ 检查 Python 是否在 PATH：`where.exe python`（应输出路径）。没装或没勾 "Add to PATH" 就重装。

```
[error] 未找到 docker（请装 Docker Desktop for Windows，启用 WSL2 backend）
```
→ 装 Docker Desktop，重启 Windows，等 tray 图标变绿。

```
[error] docker daemon 未运行（请启动 Docker Desktop，等 tray 图标变绿）
```
→ 启动 Docker Desktop。如果 daemon 启动后仍报，任务栏 → Restart。

**Step 4 失败**（拉镜像失败）：

```
[error] docker load 失败 (size=1025089797, err='cannot load linux image on windows')
```
→ Docker Desktop 在 **Windows containers** 模式。任务栏 Docker 图标右键 → "Switch to Linux containers"。

```
[error] OSS tar 下载失败：[网络错误]
```
→ GFW 拦截。设环境变量走阿里云 OSS 镜像源：
```powershell
$env:SWEBENCH_LITE_OSS = "https://your-mirror.com"
pwsh scripts/windows/install.ps1
```

**Step 5 失败**（自检 323 断言不过）：

```
[error] 题库断言失败：实际 X 条
```
→ 删 `.venv` 和 `database\swe_bench.db`，重跑 install。

## 5. 一键跑 demo（1-2 分钟）

```powershell
pwsh scripts/windows/run-demo.ps1
```

**完成标志**：屏幕底部看到 `Instances resolved: 1` `Instances unresolved: 0` `本次流程本体耗时: Xs`。

### 验证 result.json

```powershell
# 核心验证：resolved 是不是 true
Get-Content output\pylint-dev__pylint-7080\result.json | ConvertFrom-Json | Select-Object resolved, report_source, resolved_pct
```

期望输出：

```
resolved       : True
report_source  : instance_report
resolved_pct   : 100.0
```

**`resolved=True` + `report_source=instance_report` = 红线达标**（非 report-not-found 兜底）。

### result.json 字段解读

```json
{
  "instance_id": "pylint-dev__pylint-7080",
  "resolved": true,                    ← 金标准：F2P 全过 ∧ P2P 全过
  "resolved_pct": 100.0,
  "report_source": "instance_report",  ← 真实 harness 逐实例报告
  "fail_to_pass": {"pass": 1, "fail": 0},  ← 修复验证测试
  "pass_to_pass": {"pass": 120, "fail": 0}, ← 回归测试
  "image": "swebench/sweb.eval.x86_64.${DEMO_INSTANCE}:latest",
  "stage_timings": {...}
}
```

### 失败怎么办

```
[error] run-demo.ps1 失败
```
→ 看具体哪步错：
- **Step 1（python OK）→ Step 2（依赖就绪）**：重新 install
- **Step 2 → Step 3（DB 下载）**：网络问题，手动下 [DB](https://github.com/ztluck78/swebench-exp-lite/releases/download/0.1.0/swe_bench.db) 放 `database\`
- **Step 3 → Step 4（评测镜像）**：见 §4 Step 4 失败
- **Step 4 → Step 5**：inspect 镜像是否完整：
  ```powershell
  docker images swebench/sweb.eval.x86_64.pylint-dev__pylint-7080
  ```
  如果 REPOSITORY/TAG 列空，说明镜像没装好，重跑 install。

## 6. 跑真实 Agent（可选，~30 min）

`replay-agent` 跑通证明"管道通畅"，**不代表任何模型能力**。要真做实验：

### 装 Agent CLI（任选一个）

```powershell
# Kimi CLI
pip install kimi-cli && kimi auth login

# Qwen Code
npm install -g @qwen-code/qwen-code

# opencode
npm install -g opencode-ai
```

**装完验证**：

```powershell
pwsh scripts/windows/check-agents.ps1
```

期望输出（任一即可）：

```
[可用] Kimi CLI       (kimi)         → run --adapter kimi-agent
[可用] Qwen Code      (qwen)         → run --adapter qwen-agent
[可用] opencode       (opencode)     → run --adapter opencode-agent
```

### 跑真实 Agent

```powershell
pwsh -m swebench_exp_lite run --instance pylint-dev__pylint-7080 --adapter kimi-agent
```

首次跑耗时较长（要 clone 目标仓库 + Agent 作答 + 评分，~10-30 min）。

**注意**：`--adapter` 必须用 `check-agents.ps1` 列出的 adapter 名，否则会报 `adapter not found`。

## 7. 进阶（按需阅读）

### 换题

```powershell
# 列所有题（前 10）
pwsh -m swebench_exp_lite list --limit 10

# 推荐适合上手的题（按 P2P 数 + patch 大小排序）
pwsh -m swebench_exp_lite candidates --limit 10

# 看题详情
pwsh -m swebench_exp_lite info --instance django__django-11099

# 跑其他题
pwsh -m swebench_exp_lite run --instance django__django-11099 --adapter replay-agent
```

### 看完整评测报告

```
output\
  <instance_id>\
    result.json              ← 结论
    manifest.json            ← 阶段状态 + 时间戳
    logs\
      run_evaluation\
        <run_id>\
          replay__gold-patch\
            <instance_id>\
              eval.sh              ← 跑测试的脚本
              report.json         ← F2P/P2P 逐测试结果
              test_output.txt     ← pytest 完整输出
```

`logs\run_evaluation\...report.json` 是核心证据——F2P/P2P 逐测试通过/失败明细。

### 跑所有 323 道题（仅建议在 Linux 跑）

```powershell
# PowerShell 批量跑所有题（replay-agent，~5-10 min/题）
# 强烈建议在 Linux/macOS 跑，Windows Docker IO 慢
$ids = pwsh -m swebench_exp_lite list --limit 9999 | Select-String -Pattern "\S+__\S+"
foreach ($id in $ids) { pwsh -m swebench_exp_lite run --instance $id.Line --adapter replay-agent }
```

## 8. 常见问题（FAQ）

### Q1: PowerShell 报"running scripts is disabled on this system"

```powershell
# 第一次以管理员身份跑一次
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

或用 `.cmd` 兜底（`.cmd` 内部以 `-ExecutionPolicy Bypass` 调 ps1，不需要手动改策略）：

```powershell
scripts\windows\install.cmd
```

### Q2: 路径含空格报错（`C:\Users\My Name\...`）

`.ps1` 和 `.cmd` 内部已对 `$Script:RepoRoot` 等关键路径加引号，正常情况自动处理。

**如果仍报错**：
- 改用户主目录为无空格路径（如 `C:\dev\...`）
- 或在 PowerShell 中 cd 到仓根目录后用 `./scripts/windows/...` 相对路径

### Q3: Docker Desktop 默认在 Windows containers 模式

**这是 Windows 真机最常见的坑**：

- 任务栏 Docker 图标右键 → "Switch to Linux containers"
- 切换后 Docker Desktop 重启 daemon（~10s）
- 验证：`docker info | findstr "Operating System"` 应输出 `Operating System: Docker Desktop`（不是 `Windows`）

### Q4: 4GB 镜像拉不到（GFW）

设 `SWEBENCH_LITE_OSS` 环境变量指向阿里云 OSS 镜像源：

```powershell
$env:SWEBENCH_LITE_OSS = "https://your-mirror.com"
pwsh scripts/windows/install.ps1
```

`install.ps1` 会自动尝试 `docker pull`，失败时降级到 OSS tar 加载。

### Q5: 镜像拉到了但容器跑不起来（WSL2 内存不足）

Docker Desktop → Settings → Resources → WSL Integration → Memory → 调大（推荐 4-8 GB）。

### Q6: demo 跑完没 result.json

**通常原因**：
- Step 4 拉镜像失败 → 重新 `install.ps1`
- 容器启动失败 → 看 `logs\run_evaluation\<run_id>\replay__gold-patch\test_output.txt`

**调试**：
```powershell
# 手动跑容器看错
docker run --rm -it swebench/sweb.eval.x86_64.pylint-dev__pylint-7080:latest bash
```

### Q7: 跑真实 Agent 超时

默认 `--timeout` 1800s（30 min）。大仓库或慢模型可能不够：

```powershell
$env:SWEBENCH_S4_TIMEOUT = "3600"  # 改 1 小时
pwsh -m swebench_exp_lite run --instance <iid> --adapter kimi-agent
```

### Q8: result.json 的 `resolved: false`

**这是 F2P 或 P2P 没全过**——Agent 没修对（如果用真实 Agent），或 gold patch 自身在当前镜像下复现失败（极少见）。

查看 `logs\run_evaluation\...report.json` 找具体哪个测试失败。

## 9. 反馈

跑通后**强烈建议**开 issue 附上：
- `output\pylint-dev__pylint-7080\result.json` 全文
- `pwsh --version` + `python --version` + Docker Desktop 版本
- 任何意外行为 / 改进建议

**这是推动 0.2.0 → 1.0 跨平台完整闭环的关键数据**——目前 Windows 真机验证覆盖度低，你的报告直接帮助 v1.0 发布判断。

### 提 issue 模板

```markdown
## 环境
- Windows 版本：Win 11 23H2 (build 22631.XXXX)
- Python：3.10.11
- Docker Desktop：4.18.0
- PowerShell：7.3.4

## 跑通结果
result.json.resolved: true
result.json.report_source: instance_report

## 命令输出（截关键部分）
... (install + run-demo 的关键步骤输出)

## 建议
（任何对脚本、文档、功能的建议）
```

## 附录 A：单次完整跑通的命令序列（复制粘贴用）

```powershell
# 1. 一次性 PowerShell 策略（首次）
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 2. Clone
cd C:\Users\<你的用户名>\Projects
git clone git@github.com:ztluck78/swebench-exp-lite.git
cd swebench-exp-lite

# 3. 装
pwsh scripts/windows/install.ps1

# 4. 跑 demo
pwsh scripts/windows/run-demo.ps1

# 5. 验证
Get-Content output\pylint-dev__pylint-7080\result.json | ConvertFrom-Json | Select-Object resolved, report_source

# 6. （可选）装 Agent + 跑真实 Agent
npm install -g @qwen-code/qwen-code
pwsh scripts/windows/check-agents.ps1
pwsh -m swebench_exp_lite run --instance pylint-dev__pylint-7080 --adapter qwen-agent
```

## 附录 B：仓库其他文档导航

| 文档 | 用途 |
|---|---|
| [README.md](../README.md) | 项目门面（多平台）|
| [GETTING-STARTED.md](../GETTING-STARTED.md) | 跨平台教程（macOS / Linux 详细，Windows 简化）|
| [scripts/windows/README.md](../scripts/windows/README.md) | PowerShell 脚本技术参考（给维护者）|
| [docs/windows-11-port.md](windows-11-port.md) | 移植笔记（给维护者看踩过的坑）|
| [AGENTS.md](../AGENTS.md) | AI 助手 / 贡献者约定 |
