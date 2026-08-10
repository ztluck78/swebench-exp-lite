# GETTING-STARTED — swebench-exp-lite 完整教程

本教程自包含：从零开始，到用真实 Coding Agent 在 SWE-bench 题目上做题、打分。
预计总耗时 30 分钟（其中 demo 闭环 1-5 分钟）。

## 目录

- [0. 这个实验是什么](#0-这个实验是什么)
- [1. 环境准备](#1-环境准备)
- [2. 一键安装](#2-一键安装)
- [3. 手把手：pylint-dev__pylint-7080](#3-手把手pylint-dev__pylint-7080)
- [4. 理解实验](#4-理解实验)
- [5. 换真实 Agent](#5-换真实-agent)
- [6. 做更多题](#6-做更多题)
- [7. FAQ](#7-faq)

---

## 0. 这个实验是什么

[SWE-bench](https://www.swebench.com/) 把真实的 GitHub issue 变成"考题"：
给定一个开源仓库在有 bug 时的 commit 和 issue 描述，要求修复 bug。
本仓库用其中 **SWE-bench-Lite**（300 道 test 题 + 23 道 dev 题，共 323 条，全部 Python）。

一道题的解剖结构：

```
┌─────────────────────────────────────────────────────────────┐
│ instance（一道题）                                            │
│  ├── repo + base_commit    有 bug 的代码现场（git 快照）       │
│  ├── problem_statement     issue 原文（题面）                 │
│  ├── patch (gold patch)    官方修复（标准答案，不给学生看）     │
│  ├── test_patch            新增的回归测试（判分依据之一）       │
│  ├── FAIL_TO_PASS (F2P)    修复前失败、修复后必须通过的测试     │
│  └── PASS_TO_PASS (P2P)    修复前后都必须通过的测试（防回归）    │
└─────────────────────────────────────────────────────────────┘
```

一次完整实验的闭环：

```
出题(S1) → 环境准备(S2) → Agent做题(S4) → 补丁规范化(S5) → Docker打分(S6) → 记录(S7)
```

Agent 交出的修复 diff 叫 **model_patch**。打分在官方评测 Docker 镜像里进行：
应用 model_patch + test_patch，跑全部 F2P/P2P 测试：

```
resolved = F2P 全部通过 ∧ P2P 全部通过
%Resolved = resolved 的题数 / 总题数 × 100
```

## 1. 环境准备

**v1.0 支持平台：macOS（Docker Desktop）**。

| 平台 | 状态 |
|---|---|
| macOS（Intel / Apple Silicon） | v1.0 支持。Apple Silicon 通过 Rosetta 跑 x86_64 镜像，速度约为原生 1/2-1/3，demo 约 1-2 分钟，属正常预期 |
| Ubuntu / WSL2 | v1.1 路线图（脚本与路径约定已按 POSIX 设计，主要差在镜像 arch 与 Docker 配置） |
| Windows 原生 | v1.1+ 路线图 |

需要预装：

- **Python >= 3.10**（`python3 --version` 检查；推荐 3.10-3.12）
- **Docker Desktop** 并且 daemon 处于运行状态（`docker info` 能输出即 OK）
- **磁盘空间**：单个评测镜像 1-4 GB；本教程的 demo 镜像约 4 GB
- **git / curl**（macOS 自带）

不需要联网拉数据集——数据集（.jsonl）与题库元数据随仓/随安装提供。
唯一需要网络的场景：首次下载题库 DB 与评测镜像（见第 2 章）。

## 2. 一键安装

```bash
git clone <本仓库地址> swebench-exp-lite   # 或直接用已有目录
cd swebench-exp-lite
./start.sh
```

`start.sh` 幂等（可重复执行），共五步 + 自检，逐段解释：

| 步骤 | 做什么 | 幂等行为 |
|---|---|---|
| 1/5 环境检查 | python>=3.10、docker daemon 存活 | 不通过直接退出并给出原因 |
| 2/5 venv + 依赖 | 创建 `.venv`，`pip install -e .`（依赖仅四件套：docker / tqdm / unidiff / requests） | `.venv` 已存在则复用 |
| 3/5 题库 DB | `database/swe_bench.db`（323 条元数据）缺失时从 Release 下载（URL：`https://github.com/ztluck78/swebench-exp-lite/releases/download/v1.0/swe_bench.db`，可用 `SWEBENCH_LITE_DB_URL` 覆盖） | 已存在则跳过，不重复下载 |
| 4/5 评测镜像 | 对 demo 题的镜像做 `docker image inspect`；缺失则官方 `docker pull`，再失败降级 OSS tar（`docker save`/`load`，基址可用 `SWEBENCH_LITE_OSS` 覆盖） | 本地已有则短路 |
| 5/5 demo 预热 | 预跑 S2_prepare（镜像/目录就绪），让正式 demo 更快 | 幂等 |
| 自检 | `python -m swebench_exp_lite list` 冒烟 + 断言题库恰 323 条；失败非零退出 | — |

看到 `安装完成。下一步：./run_demo.sh` 即安装成功。

## 3. 手把手：pylint-dev__pylint-7080

### 3.1 跑起来

```bash
./run_demo.sh
```

约 1-5 分钟（首次稍慢）。成功输出尾部：

```json
{
  "instance_id": "pylint-dev__pylint-7080",
  "run_id": "lite-20260810-131029",
  "model": "replay/gold-patch",
  "adapter": "replay-agent",
  "resolved": true,
  "resolved_pct": 100.0,
  "report_source": "instance_report",
  "fail_to_pass": { "pass": 1, "fail": 0 },
  "pass_to_pass": { "pass": 120, "fail": 0 },
  "baseline_resolved": null,
  "image": "swebench/sweb.eval.x86_64.pylint-dev_1776_pylint-7080:latest",
  ...
}
```

### 3.2 这道题是什么

`pylint-dev__pylint-7080`：pylint 的 issue #7080 —— `--recursive=y` 时 `ignore-paths`
配置被完全忽略。官方修复只加了一行：对路径先做 `os.path.normpath` 再匹配。

用 `info` 命令随时查看题目元信息：

```bash
.venv/bin/python -m swebench_exp_lite info --instance pylint-dev__pylint-7080
```

### 3.3 产物目录逐文件解读

所有产物在 `output/pylint-dev__pylint-7080/`：

| 文件 | 阶段 | 是什么 | 能给 Agent 看吗 |
|---|---|---|---|
| `review.md` | S1 | 出题人审阅版（**含 gold patch 与 test_patch**） | 绝不 |
| `ca-issue.json` | S1 | Agent 输入数据（7 字段，无答案） | 是 |
| `ca-task-prompt.md` | S1 | Agent 任务指令（8 步流程） | 是 |
| `task.jsonl` | S1 | 标准 SWE-bench jsonl 行（含答案，harness 用） | 绝不 |
| `image.json` | S2 | 本任务评测镜像元信息 | — |
| `agent/<iid>/<iid>.pred` | S4 | Agent 作答结果（含 model_patch） | — |
| `agent/<iid>/<iid>.traj` | S4 | 作答轨迹元数据 | — |
| `prediction.jsonl` | S5 | harness 可消费的规范化 prediction | — |
| `patch/model.patch` | S5 | model_patch 单独落盘（diff 文件） | — |
| `patch/changed-files.txt` / `diff-stat.txt` | S5 | 改动统计 | — |
| `eval/report.json` | S6 | harness 逐测试判定明细 | — |
| `result.json` | S7 | 最终结论（resolved / %Resolved / 耗时） | — |
| `manifest.json` | 全程 | 各阶段状态/时间戳（断点续跑依据） | — |

### 3.4 result.json 逐字段

- `instance_id / run_id / model`：实验身份三元组。harness 报告路径由 run_id + model 拼出（`/` 换 `__`）。
- `adapter`：作答方。本 demo 是 `replay-agent`（回放器，不是模型）。
- `resolved / resolved_pct`：判定结论。100.0 表示 F2P 全过且 P2P 全过。
- `report_source`：resolved 的证据来源。`instance_report` = harness 逐实例真实报告；
  若为 `aggregated_report` 或 `report not found` 则表示证据降级，应排查。
- `fail_to_pass / pass_to_pass`：两类测试的通过/失败计数。
- `baseline_resolved`：v1.0 恒为 `null`（不跑 baseline，见第 4 章澄清）。
- `image`：打分所用评测镜像。
- `stage_timings`：各阶段耗时（秒），S6 占大头。

### 3.5 gold patch 隔离（教学点）

注意 S1 产物里 `review.md` / `task.jsonl` **含金标准答案**，而 `ca-issue.json` /
`ca-task-prompt.md` 不含——出题层从同一 `TaskInstance` 渲染两个版本，靠文件命名
（`ca-` 前缀 = code agent 可见）实现答案隔离。真实实验中绝不能把 `review.md`
喂给 Agent，否则等于开卷抄答案。

### 3.6 replay 自检语义（重要声明）

**replay-agent 是回放已知 gold patch 的闭环自检，证明链路通畅，不代表模型解题能力。**
它把标准答案直接写进评分链路，resolved=true 是"管道正确"的证明，不是"模型会做题"
的证明。要看真实解题能力，进入第 5 章。

## 4. 理解实验

### 4.1 产物链路

```
LiteDB(题库) ─S1→ ca-issue.json + ca-task-prompt.md     （题面）
                 ─S2→ image.json + 评测镜像就绪            （环境）
Agent          ─S4→ <iid>.pred（model_patch 在其中）      （作答）
                 ─S5→ prediction.jsonl                    （规范化）
harness        ─S6→ logs/run_evaluation/<run_id>/<model>/<iid>/report.json（打分）
                 ─S7→ result.json                         （结论）
```

### 4.2 %Resolved 公式

```
单题：resolved = (F2P 全部 PASSED) ∧ (P2P 全部 PASSED)
批量：%Resolved = resolved 题数 / 总题数 × 100
```

F2P 验证"bug 真的修好了"，P2P 验证"没有修坏别的"。空 patch 一定 unresolved。

### 4.3 APPLY_PATCH_PASS 是什么

harness 评测日志里有 `>>>>> Applied Patch`（APPLY_PATCH_PASS）与
`>>>>> Patch Apply Failed`（APPLY_PATCH_FAIL）两个标记：model_patch 若无法
`git apply` 到 base_commit 上，连测试都不会跑，直接判 unresolved。
所以 Agent 输出规范 unified diff 是硬要求。

### 4.4 思考题：空 patch 会怎样？

把 `prediction.jsonl` 的 model_patch 置空再跑 S6：harness 会把该实例计入
`empty_patch_ids`，resolved=false，且不写逐实例 report.json（S7 走聚合报告
推导）。可以动手验证：断点续跑只重跑 S6/S7 即可。

### 4.5 澄清：resolved 与 baseline 无关

resolved 是相对 **gold 测试集**（官方 test_patch 定义的 F2P/P2P）判定的，
与"修复前测试是否本来就通过"（baseline）无关。本仓 v1.0 不跑 baseline
（`baseline_resolved` 恒为 null），不影响任何判定。v1.1 可选 `--run-baseline`。

## 5. 换真实 Agent

### 5.1 检测可用 CLI

```bash
./check-agents.sh
```

### 5.2 四个品牌平行支持（无首选）

| adapter | CLI | 安装（请以官方文档为准） |
|---|---|---|
| `kimi-agent` | `kimi` | `pip install kimi-cli && kimi auth login` |
| `kimi-fast` | `kimi` | 同上（快速模式） |
| `qwen-agent` | `qwen` | `npm install -g @qwen-code/qwen-code` 或 `brew install qwen-code` |
| `mimo-agent` | `mimo` | MiMo Code CLI，确保 PATH 含 `~/.mimocode/bin` |
| `opencode-agent` | `opencode` | `npm i -g opencode-ai`，确保 PATH 含 `~/.npm-global/bin` |
| `replay-agent` | （无） | 零依赖兜底，永远可用 |

未安装对应 CLI 时，`run` 会在 preflight 阶段友好报错并附安装指引，不会白跑。

### 5.3 用法

```bash
.venv/bin/python -m swebench_exp_lite run \
    --instance pylint-dev__pylint-7080 --adapter kimi-agent
```

首次跑真实 Agent 会：克隆目标仓库（shared mirror + worktree，缓存于
`runtime-cache/`）→ venv 预装（best-effort）→ Agent 作答（默认超时 1800s，
`SWEBENCH_S4_TIMEOUT` 可调）→ 打分。

### 5.4 三种失败的读法

1. **preflight 失败**（`precondition 未通过`）：CLI 没装/没登录，按报错里的指引安装。
2. **S4 作答失败/超时**（`worker exit=…` / 超时被杀）：看 `output/<iid>/logs/S4_solve.log`；
   超时可加大 `SWEBENCH_S4_TIMEOUT` 后重跑（断点续跑会跳过已完成阶段）。
3. **S6 unresolved**：patch 能应用但测试没过（真没修对）；或 `patch_successfully_applied=false`
   （diff 格式/基线问题）。看 `eval/report.json` 的逐测试明细定位。

## 6. 做更多题

```bash
# 全库列表（可 --split test/dev、--repo 过滤）
.venv/bin/python -m swebench_exp_lite list --limit 10

# 推荐"适合上手"的题：P2P 少（回归面小）+ patch 小（修复面小）排序
.venv/bin/python -m swebench_exp_lite candidates --limit 10

# 看详情再决定
.venv/bin/python -m swebench_exp_lite info --instance <instance_id>

# 只出题不跑实验
.venv/bin/python -m swebench_exp_lite build --instance <instance_id> -o output
```

提示：每道题首次打分需要对应评测镜像（`docker_image` 列可查镜像名）。
镜像缺失时 S2 会尝试 `docker pull`；批量实验前建议先准备好镜像。

## 7. FAQ

**Q1：`docker info` 报错？**
启动 Docker Desktop 并等状态栏图标稳定。macOS 上确认给 Docker 分配了足够内存
（建议 >=8GB，Settings → Resources）。

**Q2：DB 下载失败（URL 是占位符）？**
v1.0-code 阶段 Release 可能尚未上传。把任意来源的 `swe_bench.db`（323 条、
含 v_lite 视图）放到 `database/` 下即可；或设置 `SWEBENCH_LITE_DB_URL` 指向
你自己的存放地址。

**Q3：评测镜像拉不下来？**
`start.sh` 会依次尝试官方 pull 与 OSS tar 降级（`SWEBENCH_LITE_OSS` 覆盖基址）。
也可以手动 `docker load` 别人导出的 tar：`docker load -i sweb.eval.x86_64.<repo>_<iid>.tar.gz`。
注意：不要随意 `--force_rebuild` 重建官方评测镜像——重建会拉取最新依赖，
可能破坏 2022 年代码环境的兼容性（真实案例：pylint-7080 镜像重建后 120 个
回归测试全挂，重新 `docker pull` 官方镜像后恢复）。

**Q4：跑到一半中断了怎么办？**
直接重跑同一条命令。manifest 记录了各阶段状态，已 done 且产物齐备的阶段自动
跳过；想全量重来加 `--force`。

**Q5：`run_id` 有什么限制？**
不得含 `/` 或 `\`（会拼进报告路径）。默认自动生成 `lite-<时间戳>`。

**Q6：Apple Silicon 上很慢？**
预期现象：x86_64 镜像经 Rosetta 模拟执行，S6 打分耗时约为 Intel 原生 2-3 倍。
demo 题 1-2 分钟内完成属正常。

**Q7：如何从 jsonl 重建题库 DB（高级）？**
本仓不带构建脚本（保持精简）。需要时参考 SWE-bench 官方数据流程：以
`data/swe_bench_data/*.jsonl` 为源，按 `database/migrations/001-004` 的 schema
建库并填充 `repositories/tasks/images` 等表与 `v_lite` 视图、`tasks_fts` 索引。

**Q8：能加新的 Agent 吗？**
可以。在 `swebench_exp_lite/agents/<brand>/` 实现 `BaseAgentRunner` 子类，
在 `swebench_exp_lite/runtime/registry.py` 的 `RUNNERS` 加一行（可选配
precondition 工厂），即接入 `run --adapter <brand>`。

**Q9：为什么 v1.0 不跑 baseline（S3）？**
resolved 相对 gold 测试集判定，baseline 只影响"这道题是否本来就能通过"的
对照分析，不影响判定本身。教学场景先砍掉以降低理解成本，v1.1 可选回归。

**Q10：实验结果能复现吗？**
同一 instance + 同一 model_patch 的打分是确定的（Docker 镜像固定）。
真实 Agent 作答不具确定性，同一题多次尝试结果可能不同。

---

*本教程所有命令均在 macOS + Docker Desktop 环境实跑核对（v1.0-code）。*
