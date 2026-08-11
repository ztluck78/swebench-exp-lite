# swebench-exp-lite

> **v0.3.0 已发布**：[Release Notes](RELEASE_NOTES.md) / [GitHub Release](https://github.com/ztluck78/swebench-exp-lite/releases/tag/v0.3.0)
> **当前状态**：v0.3.0 pre-release（macOS + Windows 11 + Ubuntu x86_64 三平台验证）

SWE-bench 精简教学实验平台：在本地用一条命令跑通「出题 → Agent 做题 → 自动打分」的最小闭环。

## 这是什么

[SWE-bench-Lite](https://www.swebench.com/) 是 300 道真实 GitHub issue 修复题的基准。
本仓库把它裁剪成一个**教学友好**的实验平台：

- **出题**（S1）：从 323 条题库中挑一道题，渲染成给 Agent 的题面四件套
- **做题**（S4）：调用你的 Coding Agent（kimi / qwen / mimo / opencode，或零依赖的 replay-agent）在真实仓库里解题
- **打分**（S6）：在官方评测镜像里跑 gold 测试集，判定 resolved / unresolved
- **记录**（S7）：汇总 `result.json`，输出 %Resolved

## 快速开始

**Windows 11 用户**：请先看 [docs/user-guide-windows.md](docs/user-guide-windows.md)——从装软件到跑通 demo 全流程。

**Ubuntu 用户**：请先看 [docs/user-guide-ubuntu.md](docs/user-guide-ubuntu.md)——Ubuntu 专属完整教程。

### macOS / Linux

```bash
./start.sh          # 幂等安装：venv + 依赖 + DB + 评测镜像 + 自检
./run_demo.sh       # 用 replay-agent 跑 pylint-dev__pylint-7080 闭环演示
./check-agents.sh   # 检测本机可用的 Agent CLI
```

### Ubuntu x86_64

```bash
bash scripts/ubuntu/install.sh        # 幂等安装（含 Ubuntu 专属前置检测）
bash scripts/ubuntu/run-demo.sh       # 闭环演示
bash scripts/ubuntu/check-agents.sh   # Agent CLI 检测
```

### Windows 11

```powershell
pwsh scripts/windows/install.ps1     # 幂等安装
pwsh scripts/windows/run-demo.ps1    # 闭环演示
pwsh scripts/windows/check-agents.ps1  # Agent CLI 检测
```

或 `.cmd` 兌底（pwsh 缺失时降级 PowerShell 5.1）：

```cmd
scripts\windows\install.cmd
scripts\windows\run-demo.cmd
```

完整教程（8 章，手把手）：[GETTING-STARTED.md](GETTING-STARTED.md)

## 一键可视化（推荐）

跑完上面任何一个 `run-demo` 后，平台可以把六阶段闭环（出题 → 解题 → 打分）渲染成一个**自包含 HTML 页面**，
让学生直观看到每一步在干什么、干到哪了、产物长什么样。

```bash
.venv/bin/python -m swebench_exp_lite viz --instance pylint-dev__pylint-7080
# 或 Windows：pwsh -m swebench_exp_lite viz --instance pylint-dev__pylint-7080
```

打开浏览器双击 `output/<iid>/flow.html` 即可（或 `open` / `xdg-open` / `Invoke-Item`），
应能看到：顶部 RESOLVED 徽章 + 6 节点流水线（蓝/紫/橙三段）+ 6 张可折叠阶段卡片
（含教学说明、产物预览、术语 tooltip）+ 阶段耗时时间线 + 键盘快捷键（1-6 / e / c）。

详细设计动机 / 边界 / 跨平台 → [docs/visualizer.md](docs/visualizer.md)

## 平台支持

- **v0.1.0**（已发布）：macOS（Docker Desktop）—— 红线验证 `replay-agent` 跑通 `pylint-dev__pylint-7080`
- **v0.2.0**：+ Windows 11（PowerShell 7+ / 5.1，Docker Desktop WSL2 backend）
  - 平台抽象层 4 函数（`swebench_exp_lite/runtime/platform.py`）
  - 本地集成测试（`scripts/local-test.sh` / `scripts/windows/local-test.ps1`）
  - pre-commit hook 30s 强制门禁（`.githooks/pre-commit`）
- **v0.3.0**（**当前已发布**）：+ Ubuntu x86_64（Docker Engine 原生 daemon）
  - `scripts/ubuntu/` 专用入口脚本（_common.sh + install.sh + run-demo.sh + check-agents.sh + local-test.sh）
  - CI `ubuntu-latest` job 跑完整红线 demo + 断言 `resolved=true`（实测 ~2min）
- **v0.4.0+** 路线图：self-hosted macOS runner（消除 colima/qemu 17m）

> **教学可视化**：跨平台为已发布的三个版本都提供——跑完 demo 后
> `python -m swebench_exp_lite viz --instance X` 生成自包含 HTML 教学页面，
> 让六阶段流程对学生可见、可点击、可悬浮提示。详见 [docs/visualizer.md](docs/visualizer.md)。

## 验证策略（v0.2.0）

v0.3.0 按 user 反馈"目标放在本地，不要烧 CI 时间"重构成**三层架构**（Ubuntu 红线回归 CI 是例外）：

| 层 | 角色 | 何时跑 | 耗时 | 谁负责 |
|---|---|---|---|---|
| **pre-commit hook**（`.githooks/pre-commit`，仓根入库）| 强制门禁——挡快速项 | 每次 `git commit` 自动 | < 1 min | Git（本地）|
| **本地集成测试**（`scripts/local-test.sh` / `scripts/windows/local-test.ps1` / `scripts/ubuntu/local-test.sh`）| **发布门禁**（主）| 任何 commit 前必跑 | 5-10min 首次 / 1-2min 日常 | 开发者本地 |
| **CI 静态 + 单测**（`.github/workflows/ci.yml`，mac/win）| PR 防线 | push / PR 自动 | 30s | GitHub Actions |
| **CI 红线**（`.github/workflows/ci.yml`，ubuntu-latest）| **三平台唯一 CI 红线** | push / PR 自动 | ~2-5min | GitHub Actions |
| **真机红线**（plan §10 跟进）| 多平台验证 | Win11 真机手动 | 5-10min | 用户 / 团队 |

**启用 pre-commit hook**（开发者首次 clone 后跑一次）：
```bash
git config core.hooksPath .githooks
```

**完整规范**：[`docs/verification-spec.md`](docs/verification-spec.md) —— 8 节开发纪律、CI 严禁清单、spec §9 诚实状态。

**为什么 v0.2.0 不在 CI 跑红线**：GitHub Actions hosted runner 物理限制（macOS 无 Docker Desktop → colima 17m；Windows docker load Linux 镜像失败 → `cannot load linux image on windows`），详见 [docs/windows-11-port.md §7](docs/windows-11-port.md)。

## 仓库结构

```
swebench_exp_lite/    # 单一 Python 包：db / builder / runtime / agents / pipeline / cli
                       # 含 platform.py 平台抽象层（v0.2.0 新增）
                       # 含 tests/test_platform.py 14 个跨平台单测
answer_evaluator/     # 评测 harness（原样移植自 SWE-bench 官方，Python-only 裁剪）
data/swe_bench_data/  # swe-bench-lite 数据集（本地 .jsonl，无需联网）
database/             # 题库 SQLite（swe_bench.db，git 忽略，start.sh 下载）+ migrations
docs/                 # 文档
  ├── windows-11-port.md       # Windows 11 移植笔记 + 70+ 分钟 CI 调试教训
  ├── verification-spec.md     # v0.2.0+ 开发纪律规范（8 节）
  ├── user-guide-windows.md    # Windows 11 用户手册
  └── user-guide-ubuntu.md     # Ubuntu x86_64 用户手册
scripts/              # v0.2.0 新增——多平台入口脚本（mac/win/ubuntu 目录托管）
  ├── README.md
  ├── macos/           # macOS 占位（0.1.0 仓根 .sh 保留）
  ├── ubuntu/          # Ubuntu x86_64 适配（0.3.0：_common.sh + 4 脚本 + README）
  ├── windows/         # Windows 11 适配（4 .ps1 + 3 .cmd + _common.ps1 + README）
  ├── local-test.sh    # macOS / Linux 本地集成测试
  └── windows/local-test.ps1  # Windows 本地集成测试
.githooks/pre-commit  # v0.2.0 新增——30s 强制门禁（pip install + 单测 + bash 语法）
.github/workflows/ci.yml  # CI 极简（30s 静态 + 单测，**严禁扩展**——见 spec §3）
RELEASE_NOTES.md      # v0.2.0 发布说明
```

## 致谢与来源

本仓库代码移植精简自 SWE-bench 官方评测 harness 与一个内部实验平台主仓，
评测逻辑版权归 [SWE-bench](https://github.com/princeton-nlp/SWE-bench) 原作者所有（MIT）。
数据集：SWE-bench-Lite（300 条）+ lite-dev（23 条），共 323 条。

## 附录：当前已就绪环境速查（Demo 任务）

> 本仓库在最近一次构建中已经为 **`pylint-dev__pylint-7080`** 这一道题跑通了完整闭环。学生 clone 后可直接 `./run_demo.sh` 复现，无需任何额外联网/安装步骤。

### 任务信息

| 字段 | 值 |
|---|---|
| 任务 ID | `pylint-dev__pylint-7080` |
| 仓库 | `pylint-dev/pylint` |
| 数据集 split | `test`（SWE-bench-Lite） |
| 评测镜像 | `swebench/sweb.eval.x86_64.pylint-dev_1776_pylint-7080:latest`（3.8 GB） |
| 题目 | pylint 的一则真实 GitHub issue 修复题（见 `output/pylint-dev__pylint-7080/task.jsonl`） |

### 已就绪组件（实测快照）

| 组件 | 状态 | 位置 / 备注 |
|---|---|---|
| Python ≥ 3.10 | ✅ | 系统 / Homebrew / pyenv 任一即可 |
| Docker daemon | ✅ | Docker Desktop 运行中即可 |
| `.venv` 四件套 | ✅ | `docker 7.2.0` / `requests 2.34.2` / `tqdm 4.70.0` / `unidiff 1.0.0` |
| 题库 DB | ✅ | `database/swe_bench.db`（5.3 MB，323 条元数据） |
| 评测镜像 | ✅ | 本地已 `docker load`（无需再 pull） |
| 数据集 | ✅ | `data/swe_bench_data/swe-bench-lite.jsonl`（随仓，离线可用） |
| 历史产物 | ✅ | `output/pylint-dev__pylint-7080/result.json`（`resolved=true`） |

### 最近一次实验结果（`run_id = lite-20260810-133651`）

```json
{
  "instance_id": "pylint-dev__pylint-7080",
  "adapter": "replay-agent",
  "resolved": true,
  "resolved_pct": 100.0,
  "report_source": "instance_report",
  "fail_to_pass": { "pass": 1, "fail": 0 },
  "pass_to_pass": { "pass": 120, "fail": 0 }
}
```

- `resolved=true` + `report_source=instance_report` → 红线达标（**非** `report-not-found` 兜底）
- F2P 1/1 通过（修复验证测试）
- P2P 120/120 通过（回归保护测试）

### 怎么再跑一次

```bash
./run_demo.sh
```

预期耗时：约 1 分钟（S2 镜像短路 + S6 评分 ~65 s）。

### 范围声明

> 上表"已就绪"**仅覆盖** `pylint-dev__pylint-7080` 这一道题的 replay-agent 闭环。
> 换真实 Agent（kimi / qwen / mimo / opencode）需先装对应 CLI；
> 换其他 322 道题需 `docker pull` 对应镜像或重跑 `./start.sh`。
> 详见 [GETTING-STARTED.md](GETTING-STARTED.md) 第 5、6 章。
