# v0.3.0 Release Notes

> 发布日期：2026-08-11
> 核心变更：Ubuntu x86_64 适配 + CI 红线回归

## 概述

v0.3.0 是 swebench-exp-lite 的 **Ubuntu x86_64 适配版本**。在 v0.2.0（macOS + Windows 11）的基础上，把项目扩展到三平台支持。Ubuntu 是三平台中评测镜像运行最“原生”的环境（x86_64 Linux 镜像在 Ubuntu 上直接运行，无需 Rosetta 或 WSL2），同时是 CI 唯一能跑完整红线的平台。

**Python 代码层零改动**：0.2.0 的平台抽象层（`platform.py`）和 `answer_evaluator` 跨平台分支已完全兼容 Ubuntu，无需任何修改。

## 主要变更

### 新增：Ubuntu x86_64 适配

| 文件 | 作用 |
|---|---|
| `scripts/ubuntu/_common.sh` | 共享函数库：5 个 Step 函数 + Ubuntu 专属前置检测（docker 组 / python3-venv） |
| `scripts/ubuntu/install.sh` | 幂等安装入口（与 macOS start.sh / Windows install.ps1 对应） |
| `scripts/ubuntu/run-demo.sh` | replay-agent 闭环演示 |
| `scripts/ubuntu/check-agents.sh` | Agent CLI 可用性检测 |
| `scripts/ubuntu/local-test.sh` | Ubuntu 本地集成测试 |
| `scripts/ubuntu/README.md` | Ubuntu 专属说明（依赖、已知坑、验证状态） |

### CI 红线回归（关键变化）

| 阶段 | v0.2.0 | v0.3.0 |
|---|---|---|
| mac/win CI | 静态 + 单测（30s） | 不变 |
| ubuntu CI | 静态 + 单测（30s） | **静态 + 红线 + 断言**（~2-5min） |
| CI 架构 | 单 job 三平台矩阵 | 双 job：static（mac/win）+ ubuntu-redline |

Ubuntu 是唯一能在 CI 原生跑 Docker 红线的平台（Linux on Linux，无虚拟化层，实测 1m40s）。

### 单测补充

- `test_platform.py` 新增 `TestLinuxSpecific` 类（5 个测试用例）：Linux 真路径断言 + `import resource` 守护

### 文档

| 文件 | 作用 |
|---|---|
| `docs/ubuntu-port.md` | 新增——Ubuntu 移植笔记（设计决策、踩坑记录、CI 设计） |
| `README.md` | 平台支持段加 Ubuntu；快速开始加 Ubuntu 代码块 |
| `GETTING-STARTED.md` | 环境准备加 Ubuntu；一键安装加 Ubuntu 段 |
| `AGENTS.md` | scripts/ubuntu/ 从“占位”改为正式描述 |
| `docs/windows-11-port.md` | §8 checklist 标记各项完成 |

## 破坏性变更

**无破坏性变更**：

- 仓根 `.sh`（`start.sh` / `run_demo.sh` / `check-agents.sh`）**保留**，字节级不动
- Python 包 import 路径未变
- 数据格式未变
- v0.2.0 的 Windows PowerShell 脚本未变

迁移成本：**零**。

## 升级指南

```bash
git pull origin main

# Ubuntu 用户
bash scripts/ubuntu/install.sh
bash scripts/ubuntu/run-demo.sh

# macOS 用户（不变）
./scripts/local-test.sh

# Windows 用户（不变）
pwsh scripts/windows/local-test.ps1
```

---

# v0.2.0 Release Notes

> 发布日期：2026-08-10
> GitHub Release：https://github.com/ztluck78/swebench-exp-lite/releases/tag/v0.2.0
> commit 范围：1db6bc7..4ae9b67（v0.1.0..v0.2.0 HEAD）
> 35 个文件变更，+2475 / -46 行

## 概述

v0.2.0 是 swebench-exp-lite 的 **Windows 11 跨平台适配版本**。在 v0.1.0（仅 macOS 验证）的基础上，把项目从"macOS only"扩展到"macOS + Windows 11"，同时把所有 Python 平台硬编码（`/dev/null` / `os.kill(pid, 0)` / `import resource`）抽离到 `swebench_exp_lite/runtime/platform.py` 单一平台抽象层。

**v0.2.0 仍按"诚实的预发布标注"原则**——按 memory `2352d250`（"有限验证时必须降级到 0.1.0 pre-release"），v0.2.0 在"扩到 2 个平台验证"状态下，pre-release 性质仍保留（spec §9 [7] CI 双红线断言部分 / [10] Windows 真机红线未做——见下方"已知问题"）。

**v0.2.0 的核心成果**：发布门禁从"CI 自动化 17m"重构成"本地集成测试 1-2m + pre-commit hook 30s 强制门禁"——按 user 反馈"目标放在本地，不要烧 CI 时间"调整。

## 主要变更

### 新增：Windows 11 适配（核心）

| 文件 | 作用 |
|---|---|
| `scripts/windows/install.ps1` + `install.cmd` | 幂等安装：环境检查 → venv+依赖 → DB → 镜像 → S2 预热 + 自检 |
| `scripts/windows/run-demo.ps1` + `run-demo.cmd` | 跑 replay-agent 红线 demo |
| `scripts/windows/check-agents.ps1` + `check-agents.cmd` | 检测 kimi / qwen / mimo / opencode CLI |
| `scripts/windows/_common.ps1` | 共享函数库（颜色输出、错误处理、URL 解析、POSIX 兼容）|
| `scripts/windows/README.md` | Windows 11 专属说明（必备软件、坑、启用方法）|
| `scripts/README.md` | 平台选择索引 |
| `scripts/macos/README.md` / `scripts/ubuntu/.gitkeep` | macOS 占位 + Ubuntu 未来扩展位 |

### 新增：平台抽象层（4 个 Python 平台硬编码修复）

| 文件 | 修复内容 |
|---|---|
| `swebench_exp_lite/runtime/platform.py` | **新增** —— 4 个函数：`null_device` / `is_process_alive` / `venv_bin_dir` / `default_shell`（仅依赖 stdlib）|
| `swebench_exp_lite/runtime/patch.py` | `/dev/null` → `null_device()` |
| `swebench_exp_lite/runtime/repo.py` | `os.kill(pid, 0)` → `is_process_alive(pid)` |
| `answer_evaluator/harness/run_evaluation.py` | `import resource` 三分支（Linux import，其他 skip）|
| `answer_evaluator/harness/prepare_images.py` | 同上（v0.2.0 新发现，对方 spec 漏的）|

### 新增：本地集成测试（发布门禁主）

| 文件 | 作用 |
|---|---|
| `scripts/local-test.sh` | macOS / Linux 一键跑 install + demo + 校验 result.json |
| `scripts/windows/local-test.ps1` | Windows 一键跑（`-SkipInstall` 参数复用）|
| 退出码 0 = 通过 | 4 步：环境检查 → install → demo → 校验 result.json.resolved=true |

### 新增：pre-commit hook（强制门禁）

| 文件 | 作用 |
|---|---|
| `.githooks/pre-commit` | commit 前 30s 强制门禁：pip install + 14 单测 + bash 语法检查 |
| 启用方法 | `git config core.hooksPath .githooks`（开发者首次 clone 后跑一次）|
| `docs/verification-spec.md` §1 | 文档解释"pre-commit hook 是 spec 纪律的强制落地"|

### 新增：开发纪律规范

| 文件 | 作用 |
|---|---|
| `docs/verification-spec.md` | v0.2.0+ 开发纪律（8 节）：三层验证架构 / Commit 前必跑 / CI 严禁 / spec §9 诚实状态 / 严禁 commit 流程 / 教训留底 / 加新平台纪律 / 后续改进 |
| `docs/windows-11-port.md` | Windows 11 移植笔记（7 节），含 70+ 分钟 CI 调试教训 |
| `docs/user-guide-windows.md` | Windows 11 用户手册（必备软件 → 跑通 demo 全流程）|

### 修复 / 改动

- `pyproject.toml`：version `1.0.0` → `0.2.0`（按 memory `2352d250` 诚实预发布标注）
- `start.sh`：增量增加 `swebench-exp-lite` 仓根 `.sh` 脚本
- `swebench_exp_lite/tests/test_platform.py`：14 个单测覆盖 POSIX 真路径 + Windows mock 路径

### CI 重构（关键变化）

| 阶段 | v0.1.0 | v0.2.0 |
|---|---|---|
| 策略 | CI 跑完整红线（17m 调试失败）| **本地集成测试为主，CI 为辅**（按 user 反馈"目标放在本地"调整）|
| macOS CI | 17m 跑 colima + qemu + x86_64 模拟红线 | 30s 静态 + 单测（hosted runner 跑 colima 17m 不可靠，**撤回**）|
| Windows CI | 物理跑不了 `docker load Linux 镜像`（DockerCli.exe GUI 客户端缺失）| 30s 静态 + 单测（红线由本地 + 真机承担）|
| 触发 | PR + push 跑红线 | **PR 静态 + 单测**；红线由开发者本地 `local-test.sh` 跑 |
| `.github/workflows/ci.yml` | 79 行（去掉了 v0.2.0 调试期的 colima / install / run-demo / 断言，**严禁再扩展**）| 同上 |

详细见 [`docs/verification-spec.md`](docs/verification-spec.md) §3 严禁清单。

## 破坏性变更

**无破坏性变更**。具体：

- ✅ 仓根 `.sh`（`start.sh` / `run_demo.sh` / `check-agents.sh`）**保留**，与 v0.1.0 完全兼容
- ✅ Python 包 import 路径（`swebench_exp_lite.*`）未变
- ✅ 数据格式（`swe_bench.db` / `output/<iid>/result.json`）未变
- ✅ answer_evaluator API 未变

迁移成本：**零**。从 v0.1.0 升 v0.2.0 只需 `git pull` + 开发者首次 clone 跑 `git config core.hooksPath .githooks`。

## 已知问题（spec §9 诚实标注）

按 [`docs/verification-spec.md`](docs/verification-spec.md) §4：

| spec §9 验收项 | 状态 | 实际承担者 |
|---|---|---|
| [1-6, 8-9] 平台抽象 / Python / answer_evaluator / PowerShell / 目录 / 文档 / macOS 不回归 / 版本号 | ✓ 完全满足 | 仓根代码 + 单测 + 文档 |
| **[7] CI 4 项** | ⚠ **部分**：CI 不再跑红线 demo | macos / windows / ubuntu CI 跑静态；**红线由本地集成测试承担** |
| **[10] Windows 11 真机红线 3 项** | ✗ **未做** | 用户在 Win11 真机跑 `install.ps1` + `run-demo.ps1` |

**关键原则**（按 memory `2352d250` + `fd24e575`）：

- spec 文字是 spec 文字——**不改写**。v0.2.0 不假装 spec [7] / [10] 完全满足
- 实际未达成的项**诚实标注**——不自评"完美"
- 替代方案（本地集成测试）**不替代** spec 硬指标，只**下放**给真正能跑的人（用户真机）
- 完整跨平台验证（macOS + Windows 真机 + 真实 Agent 批量跑测 + baseline 对比）完成后才升 v1.0

## 升级指南

```bash
# 1. 拉最新
git pull origin main

# 2. (开发者首次) 启用 pre-commit hook
git config core.hooksPath .githooks

# 3. 跑本地集成测试验证 v0.2.0 在你机器上能跑通
./scripts/local-test.sh            # macOS / Linux
# 或
pwsh scripts/windows/local-test.ps1  # Windows
```

**期望输出**：
```
==> Step 4/4: 校验 result.json
==> ✓ 本地集成测试通过

  result.json:     output/pylint-dev__pylint-7080/result.json
  resolved:        True
  report_source:   instance_report
```

如果失败：检查 Docker daemon 在跑 + Linux containers 模式（Windows）/ Docker Desktop 启动（macOS）。

## 致谢

- 按 [SWE-bench](https://github.com/princeton-nlp/SWE-bench) 评测方法
- 复用 `answer_evaluator/` harness（原 SWE-bench 官方评测）
- 平台抽象层设计参考对方 spec 的 `swebench_exp_lite/runtime/platform.py` 提议

## 反馈

- **Issues**：https://github.com/ztluck78/swebench-exp-lite/issues
- **Discussions**：https://github.com/ztluck78/swebench-exp-lite/discussions
- **本地集成测试**：`./scripts/local-test.sh` 跑通 → 反馈到 issue 附 result.json

---

完整 changelog 见 git log：`git log v0.1.0..v0.2.0`
开发纪律见：[`docs/verification-spec.md`](docs/verification-spec.md)
Windows 11 移植笔记见：[`docs/windows-11-port.md`](docs/windows-11-port.md)
