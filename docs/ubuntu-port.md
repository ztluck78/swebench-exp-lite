# Ubuntu x86_64 移植笔记（0.3.0）

> 设计决策、踩坑记录。给后续维护者与 v0.4+ 其他平台适配者参考。

## 1. 移植目标

- **目标平台**：Ubuntu 22.04/24.04 x86_64 + Docker Engine（原生 Linux daemon）
- **目标用户**：Ubuntu 桌面 / 服务器用户，期望 `bash scripts/ubuntu/install.sh` 一键装 + `run-demo.sh` 跑通
- **不改动的红线**：仓根 `start.sh` / `run_demo.sh` / `check-agents.sh` 字节级不动（0.1.0 红线约束）
- **核心交付物**：5 个 `.sh` + 1 个 `README.md` + CI 红线升级 + docs/ubuntu-port.md

## 2. 调研阶段的关键发现

### 2.1 Python 代码层 100% 跨平台就绪

- `platform.py` 4 个函数以 `os.name == "nt"` 做分支，Linux 走 POSIX 实现——与 macOS 返回值完全一致
- `answer_evaluator` 的 `import resource` 分支已是 `platform.system() == "Linux"` 条件——Ubuntu 直接命中
- 无 `/dev/null` / `os.kill(pid, 0)` 等硬编码残留（0.2.0 已修复）
- 评测镜像 `sweb.eval.x86_64.*` 是 x86_64 Linux 镜像，在 Ubuntu 上**原生运行**

### 2.2 Ubuntu 是三平台中最"原生"的环境

| 维度 | macOS | Windows 11 | Ubuntu |
|---|---|---|---|
| 评测镜像运行方式 | Rosetta 模拟（Apple Silicon）/ 原生（Intel） | WSL2 模拟 | **原生（最快）** |
| Docker daemon | Docker Desktop VM 内 | WSL2/Hyper-V 内 | **Linux 原生进程** |
| 镜像拉取速度 | 中 | 慢（WSL2 桥接） | **快（原生）** |

### 2.3 CI 已在 ubuntu-latest 跑通过完整红线

`docs/windows-11-port.md` §7.7 记录 CI run `31381524262`：ubuntu-latest job
完整跑通 `start.sh` + `run_demo.sh` + 断言 `result.json.resolved=true`，
耗时仅 **1m40s**。这证明：

1. 仓根 bash 脚本在 Ubuntu 上直接可用
2. Ubuntu runner 原生 Docker 是 CI 红线的最佳平台
3. 无需 colima/qemu（macOS 的 17m 问题）或 DockerCli.exe（Windows 的物理限制）

## 3. 移植决策记录

### 3.1 为什么是专用 Ubuntu 脚本（而不是复用仓根 .sh）？

| 方案 | 优点 | 缺点 | 决策 |
|---|---|---|---|
| 复用仓根 start.sh | 零新增代码 | 无法加 Ubuntu 专属前置检测（docker 组/python3-venv）；错误提示是 macOS 偏向 | -- |
| **专用 scripts/ubuntu/** | 与 scripts/windows/ 镜像对称；Ubuntu 专属前置检测；systemctl 提示 | 多一组文件维护 | ✓ |
| 修改仓根 .sh 为通用 | 统一入口 | 违反 AGENTS.md "字节级不动"约束；改动面大 | -- |

选择专用脚本，理由：
1. 与 0.2.0 Windows 适配的 `scripts/<platform>/` 模式一致
2. 可加 Ubuntu 专属前置检测（docker 组权限、python3-venv 包），不影响仓根红线脚本
3. 错误提示针对 Ubuntu 定制（`systemctl start docker`、`usermod -aG docker`）

### 3.2 为什么 CI 红线回归 ubuntu-latest？

0.2.0 撤回 CI 红线的根因：
- macOS colima+qemu 17m 太慢且不鲁棒
- Windows hosted runner 物理上无法 `docker load` Linux 镜像

**这两个理由在 Ubuntu 上都不成立**：
- Ubuntu runner 原生 Docker，无需虚拟化层
- 实测 1m40s 跑完（vs macOS 17m）
- Linux on Linux，镜像加载无任何限制

因此 0.3.0 把 ubuntu-latest 升级为 CI 唯一红线跑通平台，mac/win 保持静态验证。

### 3.3 为什么 CI 拆成两个 job（static + ubuntu-redline）？

| 方案 | 优点 | 缺点 | 决策 |
|---|---|---|---|
| 单 job 三平台矩阵 | 简单 | mac/win 等 ubuntu 红线浪费时间 | -- |
| **拆成 static（mac/win）+ ubuntu-redline** | mac/win 30s 快速反馈；ubuntu 独立跑红线 | 两个 job | ✓ |

拆分理由：保持 PR 快速反馈（mac/win 30s），同时 ubuntu 红线不阻塞其他平台。

## 4. 已知坑与解决方案

### 4.1 python3-venv 包

**现象**：Ubuntu 默认 Python3 是最小化安装，`python3 -m venv` 报
`The virtual environment was not created successfully because ensurepip is not available.`

**解决**：`sudo apt install python3-venv`

**脚本处理**：`_common.sh` 的 `step_env_check` 在环境检查阶段检测
`python3 -m venv --help`，失败则给出安装指引并退出。

### 4.2 Docker 组权限

**现象**：新装 Docker 后，`docker info` 报 `permission denied`。
Ubuntu 用户默认不在 `docker` 组。

**解决**：`sudo usermod -aG docker $USER && newgrp docker`（或注销重新登录）

**脚本处理**：`_common.sh` 的 `step_env_check` 用 `groups | grep -q '\bdocker\b'`
检测，不在组内给出 warn 提示（不阻断，因为 CI runner 默认已配好）。

### 4.3 docker.io vs Docker CE

**现象**：Ubuntu apt 仓库的 `docker.io` 版本可能较旧（22.04 上约 20.10），
而 Docker 官方 CE 仓库提供最新稳定版。

**决策**：脚本不假定安装方式，只检测 `docker` 命令存在且 daemon 存活。
文档推荐 Docker CE 但声明 docker.io 也可用。

### 4.4 snap Docker

**现象**：`snap install docker` 安装的 Docker 有独立权限模型
（snap confinement），在卷挂载、网络、组权限等方面可能与 Docker CE 不同。

**决策**：文档明确推荐 apt 安装，不推荐 snap。脚本不主动检测 snap。

### 4.5 架构限定

评测镜像 `sweb.eval.x86_64.*` 是 x86_64 架构。ARM Ubuntu（AWS Graviton、
树莓派）不在 0.3.0 范围。文档已声明。

### 4.6 systemd 假定

Ubuntu 脚本使用 `systemctl` 管理 Docker daemon。WSL2 内 Ubuntu 默认无
systemd，但本仓已声明 WSL2 在路线图外（直接跑仓根 start.sh 即可），
因此可假定 systemd 存在。

## 5. CI 设计

### 5.1 双 job 架构

```yaml
jobs:
  static:                  # macOS + Windows，30s 静态验证
    matrix: [macos-latest, windows-latest]
    timeout-minutes: 5

  ubuntu-redline:          # Ubuntu，静态 + 红线 ~2-5min
    runs-on: ubuntu-latest
    timeout-minutes: 10
```

### 5.2 ubuntu-redline job 步骤

1. Checkout + Setup Python + pip install（与 static 一致）
2. Platform import smoke + answer_evaluator import smoke + 单测（与 static 一致）
3. bash scripts syntax check（含 ubuntu 脚本）
4. `bash scripts/ubuntu/install.sh`（红线安装）
5. `bash scripts/ubuntu/run-demo.sh`（红线 demo）
6. Python 断言 `result.json.resolved == True` + `report_source == instance_report`

### 5.3 耗时预期

基于 CI run `31381524262` 实证：
- 静态步骤：~30s
- install + demo + 断言：~1m40s
- 总计：~2-3min（timeout 设 10min 留充裕余量）

## 6. 验证状态

| 平台 | 验证方式 | 状态 |
|---|---|---|
| macOS（Intel + Apple Silicon） | 0.1.0 真机 + 本地集成测试 | ✓ |
| Windows 11 x86_64 | 0.2.0 本地集成测试 + 真机 | ✓ |
| Ubuntu 22.04/24.04 x86_64 | 0.3.0 CI 红线 + 本地集成测试 | ✓ |
| Ubuntu ARM (aarch64) | 路线图外 | -- |
| WSL2 | 路线图外（复用仓根 .sh） | -- |

## 7. 与 Windows 11 移植的对比

| 维度 | Windows 11（0.2.0） | Ubuntu（0.3.0） |
|---|---|---|
| 代码层改动 | 3+1 处硬编码修复 → platform.py | 零改动 |
| 新增脚本 | 7 个（4 .ps1 + 3 .cmd） | 5 个 .sh + 1 README |
| CI 红线 | 物理不可行（hosted runner 限制） | 原生可行（1m40s） |
| 已知坑数 | 5+（行尾、BOM、WSL2、PowerShell 5.1） | 3（docker 组、python3-venv、snap） |
| 工作量 | ~8 小时 | ~3-4 小时 |
| 调试 CI run 次数 | 10+（70+ 分钟） | 预期 1-2 次 |

## 8. 不在 0.3.0 范围

- ARM 架构（aarch64）
- WSL2（直接跑仓根 start.sh 即可）
- Docker Desktop / Podman 等非 Docker Engine 容器运行时
- snap Docker
- Ubuntu 衍生发行版（Linux Mint、Pop!_OS 等，预期兼容但未验证）
