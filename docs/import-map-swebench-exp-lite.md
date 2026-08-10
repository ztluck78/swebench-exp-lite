# Import 依赖映射表 — swebench-exp-lite（H3 移植前置）

> 扫描基准：主仓 `swebench-exercise-platform` @ `63b7b30`（main，2026-08-10）。
> 扫描范围：`tools/agent_runtime`、`tools/{kimi,qwen,mimo,opencode}_agent`、
> `tools/assessment-builder`、`tools/swebench-orchestrator`、`tools/answer_evaluator`、`database/`。
> 四类模式：`from agent_runtime` / `from answer_evaluator` / `from tools` / 字面 `"tools"` 路径拼接。
> 处置图例：**改** = 改 import/路径后保留；**删** = 不随移植携带；**留** = 原样保留。

## 1. `from agent_runtime`（→ 改为 `swebench_exp_lite.runtime`）

| 消费方 | 引用模块 | 处置 |
|---|---|---|
| kimi_agent/{runner,config,agent,environment,prompt}.py | base_runner/base_config/base_agent/base_environment/proc/repo/protocol/prompt | **改** → `swebench_exp_lite.runtime.*` |
| qwen_agent/{runner,config,agent,environment,prompt}.py | 同上（无 repo） | **改** |
| mimo_agent/{runner,config,agent,environment,prompt}.py | 同上 + proc.run_cmd | **改** |
| opencode_agent/{runner,config,agent,environment,prompt}.py | 同上 + proc.run_cmd | **改** |
| orchestrator/stages/s4/main.py | resolve_runner / artifacts.layout / base_agent.PHASE_TIMINGS_FILENAME | **改**（重写进 `pipeline/stages/s4_solve.py`，直接 import runtime） |
| orchestrator/cli/run.py | list_runner_names | **改**（并入新 cli.py candidates/run 帮助） |
| registry.py 的 RUNNERS class 字符串 | `kimi_agent:...` 等 | **改** → `swebench_exp_lite.agents.kimi:...` 等（replay-agent → `swebench_exp_lite.runtime.replay_runner:ReplayRunner`） |

注：评审曾疑 agent_runtime→answer_evaluator 依赖边，grep 证实**不存在**，本表不列。

## 2. `from answer_evaluator`（包名不动，全部 **留**）

harness 内部自引用（run_evaluation / prepare_images / log_parsers/* / test_spec/* 等）。
answer_evaluator 整体原样移植，包名与内部 import 均不改；仅按裁剪清单删非 Python 语言文件与 modal 残留。
唯一联动：`pipeline/stages/s6_score.py` 以子进程 `python -m answer_evaluator.harness.run_evaluation` 调用，cwd=仓根（H1）。

## 3. `from tools`（全部 **删**，不随移植携带）

| 出现点 | 用途 | 处置 |
|---|---|---|
| orchestrator/stages/s7_record.py:90 `from tools.record_experiment import record_experiment` | S7 回写 experiments.db | **删**（lite 版 S7 只写 result.json + manifest，不入 DB） |
| tools/report_meta/*（`from tools.report_meta.renderer`） | 报告渲染 CLI | **删**（不移植 report_meta） |
| tools/tests/test_report_meta.py | 上述测试 | **删** |

## 4. 字面 `"tools"` 路径拼接（逐点改造）

| 出现点 | 原语义 | 新仓处置 |
|---|---|---|
| agent_runtime/brand_runner.py:46 `sys.path.insert(repo_root/"tools")` | worker 子进程解析 kimi_agent 等 | **改**：新包 pip -e 安装后无需 hack；`setup_brand_import_paths` 仅保留 repo_root 插入（幂等），docstring 同步 |
| kimi_agent/environment.py:45-50 `_detect_workspace_root` 向上找 `tools/` 目录 | 定位仓根 | **改**：向上找含 `pyproject.toml` 的目录，找不到回退 `Path.cwd()` |
| orchestrator/stages/s1_build.py:23 `repo_root/"tools"/"assessment-builder"/"cli.py"` | S1 子进程调 builder | **改**：新 pipeline S1 直接进程内调 `swebench_exp_lite.builder` |
| orchestrator/stages/s2_env.py:105、s2_prepare/docker_image.py:62、s3_baseline.py:62,76、s6_score.py:53,72 `run_cmd(..., cwd=repo_root/"tools")` | 子进程 cwd=tools/ | **改**：新 pipeline 统一 cwd=仓根（H1：S6 报告落 `<repo>/logs/run_evaluation/...`） |
| s2_prepare/venv_preinstall.py:34-35、s4/preinstall.py:32、s4/progress.py:26 `setup_tools_path(repo_root/"tools")` | sys.path 预置 | **删**：新包已安装，无需 path 预置 |
| s4/worker_entry.py:124-126 `setup_orchestrator_path/setup_tools_path` | worker 入口 path hack | **删**（S4 重写为直接 `resolve_runner()` 子进程，无独立 worker_entry） |
| orchestrator/stages/report_utils.py:27 `repo_root/"tools"/"logs"/...` | harness 报告读取 | **改**：移植进 `pipeline/report_utils.py`，路径基准去 `tools/` 前缀 → `<repo>/logs/run_evaluation/...`（H1） |
| assessment-builder 裸 import（`from builder import ...`，靠 cli.py 所在目录在 sys.path[0]） | 脚本式运行 | **改**：重构为正规包 `swebench_exp_lite.builder`，内部相对 import |
| replay_runner.py:11 docstring 中的 `python tools/swebench-orchestrator/cli run` 示例 | 仅文档 | **改**：docstring 换成 `python -m swebench_exp_lite run` |

## 5. 附加清点（H3 附带结论）

- **progress.py**：消费方仅 orchestrator/stages/s4/progress.py（重写后不用）与各 config docstring 提及。
  处置：**带**（~730 行全量随 runtime 移植），但 `runtime/__init__.py` 保持导出不变以维持包面一致；新 pipeline S4 不启动 ProgressWatcher。
- **database.query**：brand_runner.py:82 `from database.query import LiteDB` → **改** `from swebench_exp_lite.db.query import LiteDB`。
- **compat 委托壳**：kimi runner 的 `write_snapshot_meta`/`acquire_run_lock` 壳函数 → **删**（调用方直接走 runtime.repo）。
- **agent_runtime/__init__.py** 导出的 `cli_preconditions` 工厂缺 opencode（registry 单独 import），移植时保持现状。
