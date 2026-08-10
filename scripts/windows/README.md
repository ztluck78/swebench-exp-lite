# scripts/windows/ — Windows 11 适配

0.2.0 新增：把 0.1.0 时代的 macOS bash 入口（start.sh / run_demo.sh /
check-agents.sh）翻译成 PowerShell 形态，作为 Windows 11 用户的主操作界面。

> **本文档是技术参考（给维护者）**。
> **Windows 用户**请看 [docs/user-guide-windows.md](../../docs/user-guide-windows.md)——从装软件到跑通 demo 的完整流程 + FAQ。

## 文件清单

| 文件 | 对应 macOS | 作用 |
|---|---|---|
| `_common.ps1` | （start.sh 内联） | 共享函数库：颜色、路径、5 个 Step 函数 |
| `install.ps1` | `start.sh` | 五步幂等安装：环境检查 → venv+依赖 → DB → 镜像 → S2 预热 + 自检 |
| `install.cmd` | （无） | install.ps1 的 .cmd 兜底转发 |
| `run-demo.ps1` | `run_demo.sh` | replay-agent 闭环演示入口 |
| `run-demo.cmd` | （无） | run-demo.ps1 的 .cmd 兜底转发 |
| `check-agents.ps1` | `check-agents.sh` | kimi/qwen/mimo/opencode 四个 CLI 可用性检测 |
| `check-agents.cmd` | （无） | check-agents.ps1 的 .cmd 兜底转发 |
| `README.md` | （本文件） | Windows 11 专属说明 |

## 必备依赖

- **Python ≥ 3.10**（[python.org](https://www.python.org/downloads/windows/) 下载器，安装时勾 "Add Python to PATH"）
- **Docker Desktop for Windows**（启用 WSL2 backend；Settings → Resources → WSL Integration）
- **PowerShell 7+**（推荐 `winget install Microsoft.PowerShell`，旧版 5.1 也可降级跑）

## 首次运行 PowerShell 执行策略调整

第一次跑 `.ps1` 可能被系统拒绝（"running scripts is disabled on this system"）。
以**管理员身份**启动一次 PowerShell，执行：

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

仅影响当前用户，不需要全局放开。

## 一键安装 + 跑 demo

```powershell
# Step 1：安装（幂等，重复跑跳过已就绪步骤）
pwsh scripts/windows/install.ps1

# Step 2：跑 replay-agent 闭环演示
pwsh scripts/windows/run-demo.ps1
```

成功后 `output\pylint-dev__pylint-7080\result.json` 含 `resolved=true`，
且可追溯 `logs\run_evaluation\` 下真实 report.json。

## 已知坑

### Windows on ARM 注意事项

评测镜像 `sweb.eval.x86_64.*` 是 x86_64 Linux 镜像。Windows 11 on ARM
设备需要在 Docker Desktop Settings → Features in development 勾选
"Use Rosetta for x86/amd64 emulation on Apple Silicon" 的等价项
（Windows 11 ARM 称 "x86_64 emulation"）。本仓 0.2.0 仅在 x86_64
Windows 11 上验证。

### PowerShell 5.1 vs 7+ 差异

| 场景 | 5.1 | 7+ |
|---|---|---|
| 行尾要求 | 强制 CRLF | CRLF / LF 都接受 |
| `Test-Command` 速度 | 较慢 | 较快 |
| ANSI 颜色 | 部分支持 | 原生支持 |

`.cmd` 兜底会优先用 7+ 的 `pwsh`，缺失时降级到 5.1 的 `powershell`。

### 路径含空格的引号规则

如果仓根路径含空格（典型场景：`C:\Users\My Name\Projects\...`），所有
调用 `.ps1` 的位置需要包双引号。`install.cmd` / `run-demo.cmd` 已经处理。

### 行尾问题

`.gitattributes` 强制 `.sh` 保持 LF、`.ps1` 允许 CRLF。如果 Windows
Git 默认 `core.autocrlf=true` 把 .sh 转 CRLF，0.1.0 红线会崩——克隆后
请先 `git config core.autocrlf false` 再操作。

## 验证状态

| 平台 | 验证 |
|---|---|
| macOS（Intel + Apple Silicon Rosetta） | 0.1.0 已验证 |
| Windows 11 x86_64 + PowerShell 7+ | 0.2.0 实机验证（见 .github/workflows/ci.yml） |
| Windows 11 x86_64 + PowerShell 5.1 | 0.2.0 .cmd 兜底路径（CI windows-latest 默认 5.1） |
| Windows 11 ARM | 路线图外（x86_64 emulation 未验证） |
| WSL2 | 路线图外（直接复用 macOS .sh 即可） |

## 不在 0.2.0 范围

- WSL2 适配（用户已选原生 Windows 11；WSL2 直接跑仓根 .sh 即可）
- ARM 架构
- Docker Desktop 之外的其他容器运行时（Podman 等）
- answer_evaluator 内部深度重构（仅做平台硬编码的 bug fix 级别最小改动）

## 相关链接

- 顶层 README.md：项目说明 + 平台支持
- AGENTS.md：仓库约定 + 0.2.0 红线（macOS + Windows 11 双平台）
- GETTING-STARTED.md：完整教程（含 Windows 11 章节）
- docs/windows-11-port.md：Windows 11 移植笔记（踩过的坑、决策记录）
