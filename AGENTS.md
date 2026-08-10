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
| `scripts/windows/` | Windows 11 适配（PowerShell + .cmd 兌底） | 0.2.0 新增；幂等；与 macOS .sh 逐段对应；详见 scripts/windows/README.md |
| `scripts/ubuntu/` | 未来 Ubuntu 适配位 | 占位（`.gitkeep`） |
| `scripts/macos/` | macOS 入口扩展示位 | 0.1.0 脚本仍留在仓根，本目录未来扩展用 |
| `.gitattributes` | 行尾规范化 | 新增：`.sh` 强制 LF，`.ps1` 允许 CRLF（防 Windows 开发者 clober 根 .sh） |
| `.github/workflows/ci.yml` | 双平台红线条目 | macos-latest + windows-latest 并行 |

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

## 验收红线（0.2.0 出口）

**双平台** repl-record Red-Line（0.2.0 起）：

- **macOS**：`./run_demo.sh` 以 replay-agent 跑通 `pylint-dev__pylint-7080`：
  `output/pylint-dev__pylint-7080/result.json` 含 `resolved=true` 且该 resolved
  可追溯 `logs/run_evaluation/` 下真实 report.json（非 report-not-found 兌底）。
- **Windows 11**：`pwsh scripts/windows/run-demo.ps1` 同等验证：
  `output\pylint-dev__pylint-7080\result.json` 含 `resolved=true` 且可追溯
  `logs\run_evaluation\` 下真实 report.json。

两个平台在 CI（`.github/workflows/ci.yml`）的 `macos-latest` 与
`windows-latest` 两个 job 上同时验证通过，方可发版。
