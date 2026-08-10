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

```bash
./start.sh          # 幂等安装：venv + 依赖 + DB + 评测镜像 + 自检
./run_demo.sh       # 用 replay-agent 跑 pylint-dev__pylint-7080 闭环演示
./check-agents.sh   # 检测本机可用的 Agent CLI
```

完整教程（8 章，手把手）：[GETTING-STARTED.md](GETTING-STARTED.md)

## 平台支持

0.1.0 支持平台：**macOS**（Docker Desktop）。Ubuntu/WSL2、Windows、Apple Silicon 慢速优化列在 v1.1+ 路线图。

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
