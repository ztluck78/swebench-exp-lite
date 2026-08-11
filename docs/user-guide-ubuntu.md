# Ubuntu x86_64 用户手册 — swebench-exp-lite

> 面向 Ubuntu 用户的完整操作手册。从"装软件"到"跑通 demo"全流程，~30-45 分钟。
>
> **macOS 用户**：请改用 [GETTING-STARTED.md](../GETTING-STARTED.md)。
> **Windows 用户**：请看 [docs/user-guide-windows.md](user-guide-windows.md)。
> **开发者 / 维护者**：请看 [docs/ubuntu-port.md](ubuntu-port.md)（移植笔记）和 [scripts/ubuntu/README.md](../scripts/ubuntu/README.md)（技术参考）。

---

## 1. 这是什么 / 适合谁

**swebench-exp-lite** 是一个 SWE-bench 教学实验平台，让你本地跑"出题 → Agent 做题 → 自动打分"的最小闭环。**不需要联网**跑数据集（数据集随仓），**不需要大模型**（`replay-agent` 跑通即可验证链路）。

**Ubuntu 是三平台中运行最"原生"的环境**——评测镜像是 x86_64 Linux 镜像，在 Ubuntu 上直接运行，无需 Rosetta（macOS）或 WSL2（Windows），速度最快。

**这次要做什么**（3 步）：
1. 装 3 个软件（Python 3 / Git / Docker Engine）
2. Clone 项目
3. 跑两个命令：`install.sh` + `run-demo.sh`

**期望结果**：`output/pylint-dev__pylint-7080/result.json` 含 `"resolved": true`。

> **零 LLM 风险**：`replay-agent` 把官方 gold patch 直接写回评分链路，不调任何模型 API，不会产生任何费用。

## 2. 环境准备（10-15 分钟一次性）

> Ubuntu 22.04/24.04 LTS 自带的软件已经很齐全，大部分时间花在 Docker 安装上。

### 系统要求

| 项 | 要求 |
|---|---|
| OS | Ubuntu 22.04/24.04 x86_64（ARM/aarch64 不在支持范围） |
| RAM | ≥ 8 GB（推荐 16 GB） |
| 磁盘 | ≥ 20 GB 可用（Docker 镜像 + 评测容器） |
| 网络 | 拉 4GB 评测镜像（GFW 用户会自动走阿里云 OSS 降级） |

### 必备软件清单

| 软件 | 来源 | 装时关键说明 |
|---|---|---|
| **Python 3.10+** | `sudo apt install python3 python3-venv python3-pip` | **必须同时装 python3-venv** |
| **Git** | `sudo apt install git` | Ubuntu 通常已自带 |
| **Docker Engine** | [官方文档](https://docs.docker.com/engine/install/ubuntu/) 或 `sudo apt install docker.io` | 装完需加 docker 组权限 |

> **不推荐 `snap install docker`**——snap 有独立的权限模型（snap confinement），卷挂载、组权限等可能与 Docker CE 行为不同。

### Docker 安装与权限配置（最关键的一步）

**方式 A：apt 简装（够用）**

```bash
# 安装 docker.io（Ubuntu 仓库版本）
sudo apt update
sudo apt install -y docker.io

# 启动 + 开机自启
sudo systemctl start docker
sudo systemctl enable docker

# 把当前用户加入 docker 组（免 sudo 跑 docker）
sudo usermod -aG docker $USER
newgrp docker   # 立即生效；或注销重新登录
```

**方式 B：Docker CE 官方安装（推荐，版本更新）**

```bash
# 按 Docker 官方文档操作：
# https://docs.docker.com/engine/install/ubuntu/
```

**这一步是整个流程最容易出错的地方**——docker 组权限没配对会让后续所有 docker 命令报 `permission denied`。

### 验证（每装完一个软件就跑一下）

```bash
python3 --version       # 应输出 Python 3.10.x 或更高
python3 -m venv --help  # 应输出 venv 帮助信息（不报错 = OK）
git --version           # 应输出 git version 2.x
docker --version        # 应输出 Docker version 2x.x
docker info             # 应输出 Server Version（关键：验证 daemon 在跑 + 权限 OK）
```

**如果 `docker info` 报 "permission denied"**：
- 当前用户不在 docker 组。运行：`sudo usermod -aG docker $USER && newgrp docker`
- 或者注销重新登录后重试

**如果 `docker info` 报 "Cannot connect to Docker daemon"**：
- Docker daemon 没启动。运行：`sudo systemctl start docker`

**如果 `python3 -m venv --help` 报 "No module named venv"**：
- 缺 python3-venv 包。运行：`sudo apt install python3-venv`

## 3. 项目拉取（2 分钟）

```bash
cd ~/Projects   # 或你偏好的工作目录
git clone git@github.com:ztluck78/swebench-exp-lite.git
cd swebench-exp-lite
```

> **没用过 SSH？** 浏览器登录 GitHub → 右上角头像 → Settings → SSH and GPG keys → New SSH key（按 GitHub 提示操作）。或者直接用 HTTPS：`git clone https://github.com/ztluck78/swebench-exp-lite.git`

### 目录结构（速览）

```
swebench-exp-lite/
├── README.md                 # 项目门面
├── GETTING-STARTED.md        # 跨平台教程
├── docs/
│   ├── user-guide-windows.md  # Windows 用户手册
│   └── user-guide-ubuntu.md   # ← 你正在读
├── start.sh / run_demo.sh    # macOS 入口（你不用看）
├── scripts/ubuntu/           # Ubuntu 入口
│   ├── install.sh            # 一键安装
│   ├── run-demo.sh           # 一键跑 demo
│   ├── check-agents.sh       # 检测 Agent CLI
│   ├── local-test.sh         # 本地集成测试
│   ├── _common.sh            # 共享函数库
│   └── README.md             # 开发者向技术参考
├── scripts/windows/          # Windows 入口（你不用看）
└── swebench_exp_lite/        # Python 包（你不用动）
```

**你接下来要改动的**：只有 `scripts/ubuntu/*.sh`（如果要改）——`swebench_exp_lite/` 是冻结的 Python 包。

## 4. 一键安装（5-10 分钟）

```bash
bash scripts/ubuntu/install.sh
```

**会跑 5 步**：

| Step | 做什么 | 首次耗时 | 你看到 |
|---|---|---|---|
| 1/5 | 环境检查 | < 1s | `python 3.10.x OK` `python3-venv OK` `docker OK` |
| 2/5 | 装 venv + 四件套 | 30s | `依赖就绪（docker/tqdm/unidiff/requests 四件套）` |
| 3/5 | 下题库 DB | 1s | `下载完成` |
| 4/5 | 拉评测镜像 | 3-5 min | `Loaded image: swebench/sweb.eval.x86_64.${DEMO_INSTANCE}:latest` |
| 5/5 | S2 预热 + 自检 | < 1s | `题库断言通过：323 条` |

**完成标志**：屏幕底部看到 `安装完成。下一步：bash scripts/ubuntu/run-demo.sh（replay-agent 闭环演示，2-5 分钟）`。

### 幂等性

重复跑 `install.sh` 跳过已就绪步骤，秒过。**日常用不到重装**——只有环境异常（Docker 重装、Python 升级）才重跑。

### 失败怎么办

**Step 1 失败**（环境检查不通过）：

```
[error] 找不到 python3 / python（请装 Python >= 3.10：sudo apt install python3）
```
→ 运行：`sudo apt install python3`

```
[error] python3-venv 模块缺失。请运行：sudo apt install python3-venv
```
→ 运行：`sudo apt install python3-venv`

```
[error] 未安装 docker。请安装 Docker Engine：
```
→ 看 §2 "Docker 安装与权限配置"

```
[error] docker daemon 未运行。请尝试：sudo systemctl start docker
```
→ 运行：`sudo systemctl start docker`

**Step 1 warn**（不阻断，但需关注）：

```
[warn] 当前用户不在 docker 组。如后续 docker 命令报 permission denied，请运行：
[warn]   sudo usermod -aG docker $USER && newgrp docker
```
→ 最好立即处理：`sudo usermod -aG docker $USER && newgrp docker`

**Step 4 失败**（拉镜像失败）：

```
[error] 镜像获取失败。可手动执行：docker pull ...
```
→ 网络问题。GFW 用户设环境变量走阿里云 OSS 镜像源：
```bash
export SWEBENCH_LITE_OSS="https://your-mirror.com"
bash scripts/ubuntu/install.sh
```

**Step 5 失败**（自检 323 断言不过）：

```
[error] 题库断言失败：实际 X 条
```
→ 删 `.venv` 和 `database/swe_bench.db`，重跑 install。

## 5. 一键跑 demo（1-2 分钟）

```bash
bash scripts/ubuntu/run-demo.sh
```

**完成标志**：屏幕底部看到 `Instances resolved: 1` `Instances unresolved: 0` `本次流程本体耗时: Xs`。

### 验证 result.json

```bash
# 核心验证：resolved 是不是 true
cat output/pylint-dev__pylint-7080/result.json | python3 -m json.tool | grep -E '"resolved"|"report_source"|"resolved_pct"'
```

期望输出：

```
    "resolved": true,
    "resolved_pct": 100.0,
    "report_source": "instance_report",
```

**`resolved=true` + `report_source=instance_report` = 红线达标**（非 report-not-found 兜底）。

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
[error] 请先运行 bash scripts/ubuntu/install.sh 完成安装
```
→ `.venv` 不存在或不可执行，重跑 install。

```
评测镜像容器启动失败
```
→ inspect 镜像是否完整：
```bash
docker images swebench/sweb.eval.x86_64.pylint-dev__pylint-7080
```
如果 REPOSITORY/TAG 列空，说明镜像没装好，重跑 install。

**调试**：
```bash
# 手动跑容器看错
docker run --rm -it swebench/sweb.eval.x86_64.pylint-dev__pylint-7080:latest bash
```

## 6. 跑真实 Agent（可选，~30 min）

`replay-agent` 跑通证明"管道通畅"，**不代表任何模型能力**。要真做实验：

### 装 Agent CLI（任选一个）

```bash
# Kimi CLI
pip install kimi-cli && kimi auth login

# Qwen Code
npm install -g @qwen-code/qwen-code
# 或 Ubuntu snap：snap install qwen-code

# opencode
npm install -g opencode-ai
```

**装完验证**：

```bash
bash scripts/ubuntu/check-agents.sh
```

期望输出（任一即可）：

```
  [可用] Kimi CLI       (kimi)       → run --adapter kimi-agent
  [可用] Qwen Code      (qwen)       → run --adapter qwen-agent
  [可用] opencode       (opencode)   → run --adapter opencode-agent
```

### 跑真实 Agent

```bash
.venv/bin/python -m swebench_exp_lite run --instance pylint-dev__pylint-7080 --adapter kimi-agent
```

首次跑耗时较长（要 clone 目标仓库 + Agent 作答 + 评分，~10-30 min）。

**注意**：`--adapter` 必须用 `check-agents.sh` 列出的 adapter 名，否则会报 `adapter not found`。

## 7. 流程可视化（推荐）

跑完 demo 后，平台会把六阶段闭环（**出题 → 解题 → 打分**）渲染成一个**自包含 HTML 页面**，
让学生直观看到每一步在干什么、干到哪了、产物长什么样。

**一句话**：把 `output/<iid>/` 下分散的产物（manifest / result / diff / 报告），
聚合成一个**可点击 / 悬浮提示**的网页。

### 一行使用

```bash
.venv/bin/python -m swebench_exp_lite viz --instance pylint-dev__pylint-7080
```

打开浏览器双击 `output/pylint-dev__pylint-7080/flow.html` 即可（或 `xdg-open output/pylint-dev__pylint-7080/flow.html`），
应能看到：

- 顶部 **RESOLVED 100%** 徽章 + 元信息（run_id / model / adapter / image / F2P / P2P）
- 6 节点流水线（按出题/解题/打分三段着色：蓝/紫/橙）
- 6 张可折叠阶段卡片：每张含「做什么 / 为什么需要 / 输入输出 / 产物预览」
- 鼠标悬停术语（F2P / P2P / gold patch / harness 等）自动弹出解释
- 点击产物路径直接打开原文件
- 阶段耗时时间线（S6_score 占 99% 时标「瓶颈」）

**键盘快捷键**：`1`-`6` 切换阶段卡片 / `e` 全展开 / `c` 全折叠

> 详细设计动机 / 边界 / 跨平台 / 教学作者如何修订文案 → 见 [visualizer.md](visualizer.md)

## 8. 进阶（按需阅读）

### 换题

```bash
# 列所有题（前 10）
.venv/bin/python -m swebench_exp_lite list --limit 10

# 推荐适合上手的题（按 P2P 数 + patch 大小排序）
.venv/bin/python -m swebench_exp_lite candidates --limit 10

# 看题详情
.venv/bin/python -m swebench_exp_lite info --instance django__django-11099

# 跑其他题
.venv/bin/python -m swebench_exp_lite run --instance django__django-11099 --adapter replay-agent
```

### 看完整评测报告

```
output/
  <instance_id>/
    result.json              ← 结论
    manifest.json            ← 阶段状态 + 时间戳
    logs/
      run_evaluation/
        <run_id>/
          replay__gold-patch/
            <instance_id>/
              eval.sh              ← 跑测试的脚本
              report.json         ← F2P/P2P 逐测试结果
              test_output.txt     ← pytest 完整输出
```

`logs/run_evaluation/...report.json` 是核心证据——F2P/P2P 逐测试通过/失败明细。

### 跑所有 323 道题（Ubuntu 最适合！）

Ubuntu 是三平台中跑全量评测最快的——原生 Linux 容器，无虚拟化开销。

```bash
# bash 批量跑所有题（replay-agent，~2-5 min/题）
for id in $(.venv/bin/python -m swebench_exp_lite list --limit 9999 | grep -oP '\S+__\S+'); do
  .venv/bin/python -m swebench_exp_lite run --instance "$id" --adapter replay-agent
done
```

### 跑本地集成测试

本地集成测试一键跑 install + demo + 校验 result.json，是验证环境完整性的终极手段：

```bash
bash scripts/ubuntu/local-test.sh                    # 跑 install + demo
bash scripts/ubuntu/local-test.sh --skip-install     # 只跑 demo（install 已跑过）
```

退出码 0 = 通过；非 0 = 失败（会输出诊断建议）。

## 9. 常见问题（FAQ）

### Q1: docker info 报 "permission denied"

**这是 Ubuntu 最常见的坑**：

```bash
# 把当前用户加入 docker 组
sudo usermod -aG docker $USER
newgrp docker   # 立即生效
# 或注销重新登录
```

验证：`groups | grep docker` 应包含 `docker`。

### Q2: python3 -m venv 报 "ensurepip is not available"

Ubuntu 最小化安装不带 venv 模块：

```bash
sudo apt install python3-venv
```

### Q3: Docker daemon 没有启动

```bash
# 启动
sudo systemctl start docker

# 开机自启（推荐）
sudo systemctl enable docker

# 检查状态
sudo systemctl status docker
```

### Q4: 4GB 镜像拉不到（GFW）

设 `SWEBENCH_LITE_OSS` 环境变量指向阿里云 OSS 镜像源：

```bash
export SWEBENCH_LITE_OSS="https://your-mirror.com"
bash scripts/ubuntu/install.sh
```

`install.sh` 会自动尝试 `docker pull`，失败时降级到 OSS tar 加载。

### Q5: docker.io 还是 Docker CE？

两种都能用：

| 来源 | 版本 | 推荐场景 |
|---|---|---|
| `sudo apt install docker.io` | 可能较旧 | 快速上手、不想折腾 |
| [Docker CE](https://docs.docker.com/engine/install/ubuntu/) | 最新稳定版 | 生产环境、追求最新特性 |

**不推荐** `snap install docker`——snap 的权限模型不同，可能导致卷挂载、组权限异常。

### Q6: demo 跑完没 result.json

**通常原因**：
- Step 4 拉镜像失败 → 重新 `install.sh`
- 容器启动失败 → 看 `logs/run_evaluation/<run_id>/replay__gold-patch/test_output.txt`

**调试**：
```bash
# 手动跑容器看错
docker run --rm -it swebench/sweb.eval.x86_64.pylint-dev__pylint-7080:latest bash
```

### Q7: 跑真实 Agent 超时

默认 `--timeout` 1800s（30 min）。大仓库或慢模型可能不够：

```bash
export SWEBENCH_S4_TIMEOUT="3600"   # 改 1 小时
.venv/bin/python -m swebench_exp_lite run --instance <iid> --adapter kimi-agent
```

### Q8: result.json 的 `resolved: false`

**这是 F2P 或 P2P 没全过**——Agent 没修对（如果用真实 Agent），或 gold patch 自身在当前镜像下复现失败（极少见）。

查看 `logs/run_evaluation/...report.json` 找具体哪个测试失败。

### Q9: Ubuntu 22.04 vs 24.04 有区别吗？

| 版本 | 默认 Python | 兼容性 |
|---|---|---|
| Ubuntu 22.04 LTS | 3.10 | 满足 >= 3.10，直接用 |
| Ubuntu 24.04 LTS | 3.12 | 满足 >= 3.10，直接用 |

两个 LTS 版本都兼容，无需额外操作。

### Q10: ARM Ubuntu（aarch64）能跑吗？

**不能**。评测镜像 `sweb.eval.x86_64.*` 是 x86_64 架构，ARM Ubuntu（AWS Graviton、树莓派等）不在 0.3.0 支持范围。

### Q11: WSL2 里的 Ubuntu 能跑吗？

可以，但 WSL2 不是 0.3.0 的官方目标。WSL2 用户建议直接用仓根 `start.sh`（bash 脚本在 WSL2 里正常跑），或者用 Windows 的 `install.ps1` / `run-demo.ps1`。

## 10. 反馈

跑通后**强烈建议**开 issue 附上：
- `output/pylint-dev__pylint-7080/result.json` 全文
- `python3 --version` + `docker --version` + `lsb_release -a`
- 任何意外行为 / 改进建议

**Ubuntu 真机反馈是推动 v0.3.0 → v1.0 的重要数据**——目前 CI 红线已跑通，但个人桌面 / 服务器环境的多样性仍需要真实用户验证。

### 提 issue 模板

```markdown
## 环境
- Ubuntu 版本：22.04 LTS / 24.04 LTS
- Python：3.10.x / 3.12.x
- Docker：Docker CE 2x.x / docker.io 20.10.x
- 安装方式：apt / Docker CE 官方

## 跑通结果
result.json.resolved: true
result.json.report_source: instance_report

## 命令输出（截关键部分）
... (install + run-demo 的关键步骤输出)

## 建议
（任何对脚本、文档、功能的建议）
```

## 附录 A：单次完整跑通的命令序列（复制粘贴用）

```bash
# 1. 装依赖（一次性）
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git curl
sudo apt install -y docker.io
sudo systemctl start docker && sudo systemctl enable docker
sudo usermod -aG docker $USER && newgrp docker

# 2. Clone
cd ~/Projects
git clone git@github.com:ztluck78/swebench-exp-lite.git
cd swebench-exp-lite

# 3. 装
bash scripts/ubuntu/install.sh

# 4. 跑 demo
bash scripts/ubuntu/run-demo.sh

# 5. 验证
cat output/pylint-dev__pylint-7080/result.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'resolved={d[\"resolved\"]}  report_source={d[\"report_source\"]}')"

# 6.（可选）装 Agent + 跑真实 Agent
pip install kimi-cli && kimi auth login
bash scripts/ubuntu/check-agents.sh
.venv/bin/python -m swebench_exp_lite run --instance pylint-dev__pylint-7080 --adapter kimi-agent
```

## 附录 B：仓库其他文档导航

| 文档 | 用途 |
|---|---|
| [README.md](../README.md) | 项目门面（三平台） |
| [GETTING-STARTED.md](../GETTING-STARTED.md) | 跨平台教程（macOS / Linux / Windows） |
| [scripts/ubuntu/README.md](../scripts/ubuntu/README.md) | Ubuntu bash 脚本技术参考（给维护者） |
| [docs/ubuntu-port.md](ubuntu-port.md) | Ubuntu 移植笔记（给维护者看踩过的坑） |
| [docs/user-guide-windows.md](user-guide-windows.md) | Windows 11 用户手册 |
| [AGENTS.md](../AGENTS.md) | AI 助手 / 贡献者约定 |
