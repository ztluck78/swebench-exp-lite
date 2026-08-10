# scripts/ubuntu/ — Ubuntu x86_64 适配

0.3.0 新增：把 0.1.0 时代的 macOS bash 入口（start.sh / run_demo.sh /
check-agents.sh）针对 Ubuntu x86_64 定制，作为 Ubuntu 用户的主操作界面。

> **本文档是技术参考（给维护者）**。
> **Ubuntu 用户**请看 [GETTING-STARTED.md](../../GETTING-STARTED.md)——完整教程。

## 文件清单

| 文件 | 对应 macOS | 作用 |
|---|---|---|
| `_common.sh` | （start.sh 内联） | 共享函数库：颜色、路径、5 个 Step 函数、Ubuntu 专属前置检测 |
| `install.sh` | `start.sh` | 五步幂等安装：环境检查 → venv+依赖 → DB → 镜像 → S2 预热 + 自检 |
| `run-demo.sh` | `run_demo.sh` | replay-agent 闭环演示入口 |
| `check-agents.sh` | `check-agents.sh` | kimi/qwen/mimo/opencode 四个 CLI 可用性检测 |
| `local-test.sh` | `scripts/local-test.sh` | Ubuntu 本地集成测试（install + demo + 校验 result.json） |
| `README.md` | （本文件） | Ubuntu 专属说明 |

## 必备依赖

- **Python >= 3.10**（`sudo apt install python3 python3-venv python3-pip`）
- **Docker Engine**（推荐 Docker CE，不推荐 snap）
  - 安装：https://docs.docker.com/engine/install/ubuntu/
  - 或：`sudo apt install docker.io`
- **bash**（Ubuntu 默认自带）
- **curl**（Ubuntu 默认自带）

## Docker 安装与权限配置

```bash
# 1. 安装 Docker Engine（推荐 Docker CE）
# 详见：https://docs.docker.com/engine/install/ubuntu/
# 或简装：
sudo apt update && sudo apt install -y docker.io

# 2. 启动 Docker daemon
sudo systemctl start docker
sudo systemctl enable docker   # 开机自启

# 3. 把当前用户加入 docker 组（免 sudo）
sudo usermod -aG docker $USER
newgrp docker   # 或注销重新登录
```

**注意**：不推荐通过 `snap install docker` 安装——snap 有独立的
权限模型（snap confinement），可能导致 Docker 组权限、卷挂载等
行为与 Docker CE 不同。

## 一键安装 + 跑 demo

```bash
# Step 1：安装（幂等，重复跑跳过已就绪步骤）
bash scripts/ubuntu/install.sh

# Step 2：跑 replay-agent 闭环演示
bash scripts/ubuntu/run-demo.sh
```

成功后 `output/pylint-dev__pylint-7080/result.json` 含 `resolved=true`，
且可追溯 `logs/run_evaluation/` 下真实 report.json。

## 已知坑

### python3-venv 包

Ubuntu 默认 Python3 是最小化安装，不带 `venv` 模块。如果
`python3 -m venv` 报 `ensurepip failed`，需要：

```bash
sudo apt install python3-venv
```

### Docker 组权限

新装 Docker 后，当前用户默认不在 `docker` 组，`docker info` 会报
`permission denied`。需要：

```bash
sudo usermod -aG docker $USER
newgrp docker   # 或注销重新登录
```

### docker.io vs Docker CE

Ubuntu apt 仓库的 `docker.io` 版本可能较旧，但仍可正常使用。
推荐使用 Docker 官方 CE 仓库以获取最新稳定版：

```bash
# 卸载旧版（如有）
sudo apt remove docker docker-engine docker.io containerd runc

# 装 Docker CE
# 详见：https://docs.docker.com/engine/install/ubuntu/
```

### snap Docker 权限坑

snap 安装的 Docker 有独立权限模型（snap confinement），可能与
Docker CE 行为不同（卷挂载、网络、组权限等）。**推荐用 apt 安装**。

### Ubuntu 22.04 vs 24.04

| 版本 | 默认 Python | 兼容性 |
|---|---|---|
| Ubuntu 22.04 LTS | 3.10 | 满足 >= 3.10 |
| Ubuntu 24.04 LTS | 3.12 | 满足 >= 3.10 |

两个 LTS 版本都兼容，无需额外操作。

### 架构限定

本适配**仅覆盖 x86_64**。ARM Ubuntu（AWS Graviton、树莓派等）
不在 0.3.0 范围——评测镜像 `sweb.eval.x86_64.*` 是 x86_64 架构。

## 验证状态

| 平台 | 验证 |
|---|---|
| macOS（Intel + Apple Silicon Rosetta） | 0.1.0 已验证 |
| Windows 11 x86_64 + PowerShell 7+ | 0.2.0 实机验证 |
| Ubuntu 22.04/24.04 x86_64 | 0.3.0 CI 红线验证（ubuntu-latest） |
| Ubuntu ARM (aarch64) | 路线图外 |
| WSL2 | 路线图外（直接复用仓根 start.sh 即可） |

## 不在 0.3.0 范围

- ARM 架构（aarch64）
- WSL2（直接跑仓根 start.sh 即可）
- Docker Desktop 之外的其他容器运行时（Podman 等）
- snap Docker

## 相关链接

- 顶层 README.md：项目说明 + 平台支持
- AGENTS.md：仓库约定 + 0.3.0 红线（macOS + Windows 11 + Ubuntu 三平台）
- GETTING-STARTED.md：完整教程
- docs/ubuntu-port.md：Ubuntu 移植笔记（设计决策、踩坑记录）
- docs/windows-11-port.md：Windows 11 移植笔记（v0.2.0 教训）
