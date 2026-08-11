# Test Strategy — swebench-exp-lite v0.3.0

> 测试方案 + 性能基线 + 重构风险预警。本文档**不**重复
> [docs/verification-spec.md](./verification-spec.md) 的流程纪律
> （CI 30s 上限 / pre-commit < 1min / local-test.sh 等），仅记录测试维度的
> 落地规范。冲突时以 verification-spec.md 为准。

## 1. 测试分层矩阵

| 层 | 角色 | 何时跑 | 耗时 | 测试范围 |
|---|---|---|---|---|
| **单测**（`swebench_exp_lite/tests/`）| 守护关键链路 + 跨平台分支 | pre-commit + CI（unittest discover）| < 30s | DB / Builder-Renderer / Manifest / Pipeline Runner / Replay Runner / Registry / CLI Preconditions / Stages / Patch / report_utils / s2_prepare 路径 / Harness grading / Platform |
| **本地红线**（`scripts/local-test.sh` / `scripts/ubuntu/local-test.sh`）| 端到端真实 Docker 闭环 | commit 前自觉 + release 前必跑 | 5-10min 首次 / 1-2min 日常 | `run_demo.sh` 全跑 + `result.json.resolved=true` |
| **性能基线**（`scripts/perf-baseline.sh`）| 5 项关键操作耗时对比 | 本地手动 | < 30s | JSONL / docker / worktree / replay dry-run / git diff |

### 优先级矩阵

- **P0 必修（已落）**：DB / Builder-Renderer / Manifest / Pipeline Runner / Replay Runner / Registry / CLI Preconditions / Stages / Harness grading / Platform
- **P1 应修（已落）**：Patch / report_utils / s2_prepare 跨平台修复
- **P2 可选（已落）**：性能基线脚本 / 测试方案文档

## 2. 17 Task 实施清单

| Task | 文件 | 用例数 | 状态 |
|---|---|---|---|
| 1 | `tests/test_db_query.py` | 21 | 已落 |
| 2 | `tests/test_builder_renderer.py` | 26 | 已落 |
| 3 | `tests/test_manifest.py` | 22 | 已落 |
| 4 | `tests/test_pipeline_runner.py` | 6 | 已落 |
| 5 | `tests/test_replay_runner.py` | 11 | 已落 |
| 6 | `tests/test_registry.py` | 11 | 已落 |
| 7 | `tests/test_cli_preconditions.py` | 7 | 已落 |
| 8 | `tests/test_stages.py` | 14 | 已落 |
| 9 | `tests/test_platform.py`（追加）| +1 | 已落 |
| 10 | `scripts/perf-baseline.sh` | 5 项 | 已落 |
| 11 | `.github/workflows/ci.yml`（discover）| —— | 已落 |
| 12 | `.githooks/pre-commit`（discover）| —— | 已落 |
| 13 | `docs/test-strategy.md` | —— | 本文档 |
| 14 | `tests/test_harness_grading.py` | 24 | 已落 |
| 15 | `tests/test_patch.py` | 22 | 已落 |
| 16 | `tests/test_report_utils.py` | 11 | 已落 |
| 17 | `s2_prepare.py` 修复 + `tests/test_s2_prepare_paths.py` | 3 | 已落 |

**总计**：198 用例，0.1s 通过；6 个 skip（5 Linux-only + 1 本机已装 kimi CLI）。

## 3. 性能基线表

| 操作 | 可接受耗时上限（本地 Linux x86_64）| 测量方式 | 备注 |
|---|---|---|---|
| **JSONL 加载（300 + 23 条）** | < 1s | `time python -c 'import json; [json.loads(l) for l in open("data/...")]'` | 主用于 replay_runner._load_gold_patch |
| **docker image inspect** | < 2s | `time docker image inspect <image>` | 复用本地缓存后必命中 |
| **worktree remove** | < 5s | `time git worktree remove --force` | 已有 worktree 时 |
| **replay-agent --dry-run** | < 2s | `time python -m swebench_exp_lite run ... --dry-run` | 不调 LLM |
| **git diff HEAD** | < 2s | `time git diff HEAD` | 仓内文件少 |

**测量方式**：`scripts/perf-baseline.sh`（输出对比表 + 退出码 0=全达标 / 1=有超时）。
Docker / worktree 项若前置条件缺失自动 SKIP，不阻断。

### 进阶性能参考（不计基线）

| 操作 | 实测 | 备注 |
|---|---|---|
| S6 docker image pull（首次）| < 600s | GFW 走 OSS tar 降级 |
| S6 OSS tar download（4GB）| < 300s | OSS 北京节点 |
| S6 容器内 eval.sh 跑测 | < 1800s | S6 占 99% 时间 |
| S2 venv 预装（首次 cold）| < 180s | `ENV_PREINSTALL_TIMEOUT=600` |
| DB 全量 iter_metadata（323 条）| < 0.5s | 仅基础列 |
| DB get 全字段 | < 0.05s | 含 patch / test_patch |

## 4. CI / pre-commit 取舍

### CI（`.github/workflows/ci.yml`）

- **static job**（mac/win）：`python -m unittest discover -s swebench_exp_lite/tests -v`（替换原 `test_platform` 单文件）
- **ubuntu-redline job**：同步替换；install / run-demo / 断言步骤**不动**
- **总耗时**：mac/win < 30s；ubuntu-redline < 2-5min
- **不进 CI**：性能基线脚本（依赖 Docker / 网络，可能引入抖动）

### pre-commit（`.githooks/pre-commit`）

- 单测 `discover` 模式（替换 `test_platform` 单文件）
- 总耗时：pip install + 单测 + bash -n 合计 < 1 min

### 取舍理由

- **CI 30s 静态层**：discover 自动包含未来新增测试，不需手动维护列表
- **pre-commit < 1min**：同上
- **本地红线**：`scripts/local-test.sh` 仍是 release 门禁（[verification-spec.md](./verification-spec.md) §1）

## 5. 重构风险预警

### 5.1 Registry 不要改元类自动注册

当前 `RUNNERS` 字典 + 字符串 `class` 路径 + importlib 懒加载（[registry.py:104-106](./swebench_exp_lite/runtime/registry.py)）。**不要**改用元类自动注册——会让 precondition 顺序不可控，且 debug 不直观。`test_registry.py::test_list_runner_names_has_six` 守护此契约。

### 5.2 Manifest 不要改成直接 `write_text`

[manifest.py:53-57](./swebench_exp_lite/pipeline/manifest.py) 用 `tmp + os.replace` 守护并发与断点续跑。任何改成 `path.write_text` 直接写的重构会破坏原子性——并发跑两个 pipeline 时可能读到半写 JSON。`test_manifest.py::test_save_uses_atomic_replace_no_tmp_residue` 守护此契约。

### 5.3 PipelineRunner 不要漏 `except Exception` 分支

[runtime.py:50-58](./swebench_exp_lite/pipeline/runner.py) 用 `except StageError` + `except Exception` 双路捕获，保证 `mark_failed` 必被调。漏掉 Exception 分支会让 `mark_started` 永远卡在 running 状态，断点续跑失效。`test_pipeline_runner.py::test_generic_exception_triggers_mark_failed` 守护此契约。

### 5.4 CA 前缀不要让 agent 文件名落非 ca- 前缀

[builder.py:39](./swebench_exp_lite/builder/builder.py) 定义 `CA_PREFIX = "ca-"` 单一来源；agent 文件名必须落 `ca-issue.json` / `ca-task-prompt.md`。任何让文件名落到非 `ca-` 前缀的修改都会破坏 S4 runner 路径解析（KimiAgent 等读 `ca-issue.json`）。`test_builder_renderer.py::test_render_uses_ca_prefix_for_agent_files` 守护此契约。

### 5.5 s2_prepare.py 不要重引入 `bin` 硬编码（Task 17）

[s2_prepare.py:147-159](./swebench_exp_lite/pipeline/stages/s2_prepare.py) 已改用 `platform.venv_bin_dir()`。**不要**改回 `venv_dir / "bin" / "python"` 字面量——Windows 上 `Scripts/python.exe` 走不通，破坏跨平台。`test_s2_prepare_paths.py` 守护此契约。

## 6. 互链

- 项目阶段：[README.md](../README.md) v0.3.0
- 验证规范：[docs/verification-spec.md](./verification-spec.md)
- 教学文案：[swebench_exp_lite/visualizer/stage_guides.py](../swebench_exp_lite/visualizer/stage_guides.py)
- 红线入口：[run_demo.sh](../run_demo.sh) / [scripts/local-test.sh](../scripts/local-test.sh) / [scripts/ubuntu/local-test.sh](../scripts/ubuntu/local-test.sh)
- CI 模板：[.github/workflows/ci.yml](../.github/workflows/ci.yml)
- pre-commit：[.githooks/pre-commit](../.githooks/pre-commit)