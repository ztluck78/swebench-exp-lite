# swebench-exp-lite

SWE-bench 精简教学实验平台：在本地用一条命令跑通「出题 → Agent 做题 → 自动打分」的最小闭环。

## 这是什么

[SWE-bench-Lite](https://www.swebench.com/) 是 300 道真实 GitHub issue 修复题的基准。
本仓库把它裁剪成一个**教学友好**的实验平台：

- **出题**（S1）：从 323 条题库中挑一道题，渲染成给 Agent 的题面四件套
- **做题**（S4）：调用你的 Coding Agent（kimi / qwen / mimo / opencode，或零依赖的 replay-agent）在真实仓库里解题
- **打分**（S6）：在官方评测镜像里跑 gold 测试集，判定 resolved / unresolved
- **记录**（S7）：汇总 `result.json`，输出 %Resolved

## 快速开始

### macOS / Linux

```bash
./start.sh          # 幂等安装：venv + 依赖 + DB + 评测镜像 + 自检
./run_demo.sh       # 用 replay-agent 跑 pylint-dev__pylint-7080 闭环演示
./check-agents.sh   # 检测本机可用的 Agent CLI
```

### Windows 11

```powershell
pwsh scripts/windows/install.ps1     # 幂等安装
pwsh scripts/windows/run-demo.ps1    # 闭环演示
pwsh scripts/windows/check-agents.ps1  # Agent CLI 检测
```

或 `.cmd` 兜底（pwsh 缺失时降级 PowerShell 5.1）：

```cmd
scripts\windows\install.cmd
scripts\windows\run-demo.cmd
```

完整教程（8 章，手把手）：[GETTING-STARTED.md](GETTING-STARTED.md)

## 平台支持

- **0.1.0**：macOS（Docker Desktop）—— 红线验证 `replay-agent` 跑通 `pylint-dev__pylint-7080`
- **0.2.0**：+ Windows 11（PowerShell 7+ / 5.1，Docker Desktop WSL2 backend）
- 路线图：Ubuntu、WSL2、ARM x86_64 emulation 验证

## 仓库结构

```
swebench_exp_lite/    # 单一 Python 包：db / builder / runtime / agents / pipeline / cli
answer_evaluator/     # 评测 harness（原样移植自 SWE-bench 官方，Python-only 裁剪）
data/swe_bench_data/  # swe-bench-lite 数据集（本地 .jsonl，无需联网）
database/             # 题库 SQLite（swe_bench.db，git 忽略，start.sh 下载）+ migrations
docs/                 # import 依赖映射表等移植文档
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
