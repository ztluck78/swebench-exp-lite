# AGENTS.md — swebench-exp-lite

面向 AI 编码助手与协作开发者的仓库约定。

## 目录边界

| 目录 | 职责 | 修改约定 |
|---|---|---|
| `swebench_exp_lite/` | 单一 Python 包：db / builder / runtime / agents / pipeline / cli | 所有新功能进这里；import 一律 `swebench_exp_lite.*` |
| `answer_evaluator/` | 评测 harness（原样移植 + Python-only 裁剪） | **冻结**：只允许 bug fix 级别的最小改动；不改包名与内部 import；不引入 datasets / python-dotenv |
| `data/swe_bench_data/` | swe-bench-lite 数据集（.jsonl） | 冻结，不手改数据 |
| `database/migrations/` | 建表 SQL | 冻结；schema 变更走 FAQ 的重建流程 |
| `docs/` | import 映射表、移植笔记等 | 可增补 |
| `start.sh / run_demo.sh / check-agents.sh` | macOS 部署与演示入口 | 0.1.0 红线脚本，字节级不动；幂等 |
| `scripts/windows/` | Windows 11 适配（PowerShell + .cmd 兑底） | 0.2.0 新增；幂等；与 macOS .sh 逐段对应；详见 scripts/windows/README.md |
| `scripts/ubuntu/` | Ubuntu x86_64 适配（bash 入口脚本） | 0.3.0 新增；幂等；与 macOS .sh 逐段对应；含 Ubuntu 专属前置检测（docker 组 / python3-venv）；详见 scripts/ubuntu/README.md |
| `scripts/macos/` | macOS 入口扩展示位 | 0.1.0 脚本仍留在仓根，本目录未来扩展用 |
| `.gitattributes` | 行尾规范化 | 新增：`.sh` 强制 LF，`.ps1` 允许 CRLF（防 Windows 开发者 clober 根 .sh） |
| `.github/workflows/ci.yml` | **PR 防线** + **Ubuntu CI 红线** | 0.3.0 重构后：static job（mac/win，30s 静态） + ubuntu-redline job（Ubuntu，静态 + 红线 ~2-5min）。完整红线由本地集成测试（见 `scripts/local-test.sh` / `scripts/windows/local-test.ps1` / `scripts/ubuntu/local-test.sh`）和真机验证（plan §10 跟进）承担 |

依赖口径：全仓只允许 docker / tqdm / unidiff / requests 四件套。
禁止引入 `datasets`、`python-dotenv`（数据集走本地 .jsonl）。

## 提交纪律

1. 提交前第一件事：`git branch --show-current` + `git status --porcelain`，确认分支与改动面。
2. 精确 `git add <文件路径>`，禁止 `git add .`（swe_bench.db / logs/ / output/ 等产物不得入库）。
3. 一次提交只做一件事；提交信息说明动机而非动作。
4. 红线验证（`./run_demo.sh` 的 result.json resolved=true）是发布门禁，破坏即回滚。

## 双仓维护声明

本仓（lite）是从主仓 `swebench-exercise-platform` 故意裁剪出的**冻结精简子集**：

- 不从主仓自动同步；主仓的后续修复需要**手动 cherry-pick** 回流，且须重新过红线验证。
- 反向禁止：本仓的教学化简化不得回流污染主仓。
- 移植来源基准 SHA 见首个 commit message。

## 验收红线（0.3.0 出口）— **本地集成测试为主，Ubuntu CI 红线为辅**

0.2.0 重构后验证策略（受 user 反馈"本地完整测试，不要再烧 CI 时间"调整）：

- **本地集成测试**（**主**，任何人 clone 后必跑）：
  - macOS / Linux：`./scripts/local-test.sh`
  - Windows：`pwsh scripts/windows/local-test.ps1`
  - 这两个脚本跑完整 `install + red-line demo + 校验 result.json.resolved=true`，
    退出码 0 = 通过，是 0.2.0 发布门禁。**不是** "PR 验证"——是"我本地能跑通"。

- **CI**（**辅**，仅 PR 防线）：`.github/workflows/ci.yml` 三平台矩阵
  (`ubuntu-latest` + `macos-latest` + `windows-latest`) 跑
  `pip install -e .` + import smoke + 单测 + bash/PowerShell 脚本语法检查。
  ~30s，挡 import / 语法 / 单测挂类回归。**不跑** install.ps1 / run-demo.ps1。

- **真机红线**（plan §10 跟进项）：用户在 Win11 x86_64 + Docker Desktop 真机
  跑 `pwsh scripts/windows/install.ps1` + `run-demo.ps1`，确认个人 Docker Desktop
  默认 Linux containers mode（与 hosted runner 不同）下脚本直接跑通。

**关于 spec §9 [7] 硬指标的诚实状态**（不擅自重新解读）：
- spec [7] 第三项"双 job 各自断言 result.json.resolved == true" —— **0.2.0 未字面满足**
- 原计划让 macos + windows CI 都跑 install.ps1 + 断言，但：
  - macos hosted runner 默认无 Docker Desktop；用 colima + qemu x86_64 模拟 17m 才跑通（CI run 31370934024）
  - windows hosted runner 物理跑不了 `docker load Linux 镜像`（DockerCli.exe GUI 客户端缺失 + WSL2 fallback 走 host Windows daemon）
- 因此 CI 红线层撤回，**完整红线**由本地集成测试（已实现，~5-10 min）+ plan §10 真机承担

**手动跑通红线（replay-agent，零 LLM）**：
- **macOS**：`./run_demo.sh` 跑通 `pylint-dev__pylint-7080`，`output/pylint-dev__pylint-7080/result.json`
  含 `resolved=true`，可追溯 `logs/run_evaluation/` 下真实 report.json（`report_source=instance_report`）。
- **Windows 11**：`pwsh scripts/windows/run-demo.ps1` 同等验证。
- 这就是本地集成测试脚本要跑的内容。

## docs/windows-11-port.md §CI 限制（v0.2.0 之前 CI 调试的全部记录）

`docs/windows-11-port.md` 保留 v0.2.0 之前 70+ 分钟 CI 调试的完整记录：
- macos colima + qemu x86_64 模拟（CI run 31370934024 / 31379261939，~17m）
- windows docker load 物理限制（CI run 31377862695 等多次）
- 多次"先改规则再自评"的口径偏差

**这些不再用于 v0.2.0 验证**，仅作为教训留底。新策略是"本地集成测试为主，CI 只挡静态"。

