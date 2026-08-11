# swebench-exp-lite 测试方案（v0.3.0）

> 本文档基于 **2026-08-11 仓库实测代码状态** 编写，所有结论均引用真实文件 + 行号为证据，
> 不依赖任何假设。配套约束见 `AGENTS.md` 与 `docs/verification-spec.md`。
> 核心纪律（务必遵守）：
> - 红线门禁是 `run_demo.sh` / `scripts/local-test.sh`（replay 自检），**pytest 是补充不是替代**；
> - CI 30s 静态窗口**严禁扩展**（verification-spec §3 严禁清单）；
> - **不引入新依赖**（仅 `docker/tqdm/unidiff/requests` 四件套 + 标准库）；
> - 复用真实 fixture：`database/swe_bench.db`（323 条，随本地/ubuntu-redline 落地）、`data/swe_bench_data/*.jsonl`；**不造假数据**。

---

## 一、项目功能现状摘要（基于实测代码）

**现在能做什么（已验证）：**

1. **六阶段闭环已贯通**：`S1_build`（题面四件套）→ `S2_prepare`（镜像 inspect/pull + worktree 备仓 + venv preinstall）→ `S4_solve`（Agent 作答，含 `replay-agent` 零依赖自检）→ `S5`（patch→prediction）→ `S6_score`（harness 真实打分）→ `S7_record`（result.json 汇总）。编排入口 `swebench_exp_lite/cli.py:99 cmd_run` → `pipeline.runner.run_pipeline`，`dry_run` 在 S1（`s1_build.py:29`）/S2（`s2_prepare.py:66`）/S6（`s6_score.py:40`）/S7（`s7_record.py:25`）**均早返回**，仅打印命令链——这是无 Docker 也能校验命令组装的关键设计。

2. **只读题库查询完备**：`db/query.py` 的 `LiteDB` 在 4 次迁移后的 `v_lite` 视图（001–004）上工作，提供 `get / eval_estimate / acquisition / search(FTS5) / docker_image` 等。实测：`count()=323`（test 300 + dev 23），demo 实例 `pylint-dev__pylint-7080` 存在（`cli.py` 依赖此实例做红线，`ci.yml:154` / `local-test.sh:21` 同款）。

3. **跨平台抽象已就位**：`runtime/platform.py` 收敛 4 个函数（`null_device / is_process_alive / venv_bin_dir / default_shell`），仅依赖标准库；harness 的 `import resource` 走 `if platform.system()=="Linux"` 分支（`run_evaluation.py:9-10,524-526`、`prepare_images.py:88-90`）。已有基线 `tests/test_platform.py` 在 macOS/Windows 实跑 **14 例**（Linux-only 的 5 例 `TestLinuxSpecific` 在非 Linux 跳过），覆盖了 POSIX 真路径 + Windows mock 主分支。

4. **出题渲染与答案隔离已实现**：`builder/renderer.py` 四套输出——`review.md`（含 gold patch + test_patch，出题人审阅）、`task.jsonl`（12 字段，含 patch，harness 评分用）、`ca-issue.json`（7 字段，**刻意不含 patch/test_patch**）、`ca-task-prompt.md`（8 步指令）。隔离规则见 `builder.py:34-39`（`ca-` 前缀约定）。

5. **harness 官方移植可用**：`answer_evaluator/harness/grading.py` 的 `get_eval_report` 完整实现 F2P/P2P 解析与 `resolved` 判定（FULL=`resolved=True`，`grading.py:215-232,289`），且自带 `harness/tests/test_grading.py` 等三套单测（AGENTS.md 规定此目录**冻结、仅 bug-fix**）。

**不能做什么 / 已知风险路径（必须测试守护）：**

- **S3 baseline 已砍掉**：`S7_record._build_result` 写死 `baseline_resolved=None`（`s7_record.py:73`），`resolved` 仅相对 gold 测试集判定；任何"对比 baseline"的期望都会落空。
- **`report_source` 降级有误导**：当 instance 不在 harness 报告中时 `inst={}`，`inst.get("source","instance_report")` 会返回 `"instance_report"`（`s7_record.py:64`），与真实证据缺失矛盾——需契约测试钉死此降级行为。
- **replay-ant 与基类 `post_check` 布局不一致**：`replay_runner.post_check` 查 `output_dir/<iid>/<iid>.pred`（`replay_runner.py:39-40`），而 `base_runner.post_check` 经 `artifacts.layout` 查 `agent_dir/<iid>/<iid>.pred`（`base_runner.py:383-385` / `artifacts.py:37`）。两者各自自洽（ReplayRunner 非 BaseAgentRunner 子类），但双实现是维护隐患，需合约测试固化。
- **venv preinstall 失败不阻断**：`S2._prepare_venv` 异常仅 warn（`s2_prepare.py:164-165`），意味着"环境未装好"可能静默流入 S4；性能与正确性都需基线守护（见 §四）。
- **arm64 不在支持范围**：`LiteDB.acquisition_summary` 文档注明 arm64 为 `build=323 / pull=0`（`query.py:388-406`），测试只能断言 x86_64 路径，arm64 执行须 skip。
- **Windows 11 真机红线未做**：verification-spec §4 明确 `[10] 未做`，由用户真机跑 `local-test.ps1`——CI 不可覆盖。
- **字段命名易混但非 bug**：`eval_estimate` 返回键 `exec_difficulty`（`query.py:495`），而 `builder` 读 `get()` 行的 `exec_difficulty_class`（`builder.py:104`）；`v_lite` 暴露的是后者。测试需显式断言两侧键名，防止后续误改。

---

## 二、测试分层建议 + 优先级矩阵

| 层级 | 角色 | 是否需要 Docker / 网络 / DB | 落点 | 耗时预算 |
|---|---|---|---|---|
| **单元测试**（stdlib `unittest`，零新依赖） | 守住纯函数 / 协议 / schema | 否（DB 类用例 skip-if-missing） | `swebench_exp_lite/tests/*.py` + 既有 `test_platform.py`；CI 30s 窗口 + pre-commit | <30s 总包 |
| **集成测试**（真实 Docker + 真实 DB） | replay 黄金路径真实打分 | 是（Docker + DB） | `scripts/local-test.sh` 主门禁；`ubuntu-redline` job | 5–10 min |
| **端到端红线** | 全链路通畅证明 | 是 | `run_demo.sh` / `scripts/local-test.sh` / `scripts/windows/local-test.ps1` | 5–10 min |

**优先级矩阵：**

| 优先级 | 用例 | 理由 |
|---|---|---|
| **P0 必修** | `test_platform`（现有 14 例）+ Windows `GetExitCodeProcess` 失败分支补 1 例 | POS/WIN 双路径对齐是 0.2.0 核心交付，缺口即回归风险 |
| **P0** | DB `get` / `eval_estimate` / `acquisition` 真实数据断言（含缺失 KeyError） | 只读层是出题与 S2 的唯一事实源，schema 改动高频 |
| **P0** | renderer CA 答案隔离（`ca-issue.json`/`ca-task-prompt.md` 不得含 gold patch） | 教学平台若泄露答案属硬伤 |
| **P0** | registry `resolve_runner`（replay 解析、未知名 ValueError、precondition 失败 RuntimeError） | runner 协议入口，错误退出路径必须钉死 |
| **P0** | Manifest 读写 + 损坏备份 + result.json 字段契约（含 `baseline_resolved=None`、降级 `report_source`） | result.json 是学生看的"成绩单"，schema 不可漂移 |
| **P0** | replay-runner 写 `.pred` 真实校验（gold patch 落地、缺失返回 success=False） | 零依赖自检是红线门禁的底座 |
| **P1 应修** | renderer `_fmt` NULL 降级、`source_dir` 推导、hints 截断（`[:2000]`） | 健壮性，NULL 字段在真实题库中普遍存在 |
| **P1** | harness `run_evaluation` replay 黄金路径（S6 真实打分 resolved=True） | 集成层证据，但已部分被 `local-test.sh` 红线覆盖，宜抽成可复用用例 |
| **P1** | dry-run 命令链组装（S6 `run_evaluation` argv、S2 `docker image inspect` argv） | 无 Docker 也能守住参数契约 |
| **P2 可选** | 性能基线脚本（`scripts/perf-baseline.sh`，墙钟 + cProfile） | 教学项目非必需，但能防 S6/venv 回归 |
| **P2** | harness `GIT_APPLY_CMDS` 三级回退、FAIL_ONLY_REPOS 分支 | 依赖官方移植，已有 `harness/tests/*` 覆盖，仅做回归看门，不改 |

---

## 三、测试用例最小可执行描述

> 约定：所有读取 `swe_bench.db` 的用例均用
> `LiteDB(DEFAULT_DB_PATH)`；DB 缺失时 `skipTest`（本地 / ubuntu-redline 有库，mac/win 静态 CI 跳过）。
> 不引入 pytest，沿用 `python -m unittest`（与 `test_platform.py` 一致）。

### 3.1 DB 查询层（`swebench_exp_lite/tests/test_db_query.py`）

| 用例名 | 测什么 | fixture | 断言 | 需网络/Docker | 耗时 |
|---|---|---|---|---|---|
| `test_get_existing` | `get()` 大字段非缺失 | `pylint-dev__pylint-7080` 真实行 | `row.repo=="pylint-dev/pylint"`；`row.fail_to_pass` 为 JSON 文本且 `json.loads` 后可迭代 | 否（DB） | <10ms |
| `test_get_with_large_false` | `with_large=False` 仅取元信息列 | 同上 | `row.instance_id` 存在；访问 `row.fail_to_pass` 抛 `AttributeError`（列未选） | 否 | <10ms |
| `test_get_missing` | 缺失实例报错 | `"no_such_instance"` | `pytest.raises`→ 实际 `assertRaises(KeyError)` | 否 | <10ms |
| `test_eval_estimate_keys_x86` | `eval_estimate(arch="x86_64")` 字段全集 | 同上 | 返回 dict 含 `image_name/mode/namespace/cache_level/recommended_timeout/repo_url/ssh_url/instance_url/exec_difficulty/f2p_count/p2p_count`；`mode=="pull"` | 否 | <10ms |
| `test_eval_estimate_arm64_build` | arm64 走 build 路径 | 同上 | `mode=="build"`；`build_note` 非空（镜像策略派生） | 否 | <10ms |
| `test_eval_estimate_missing` | 缺失实例 | `"no_such"` | `assertRaises(KeyError)` | 否 | <10ms |
| `test_acquisition_pull_cmd` | `acquisition()` pull_cmd 形态 | 同上 | `mode=="pull"` 时 `pull_cmd` 以 `"docker pull"` 开头；`mode=="build"` 时 `pull_cmd is None` | 否 | <10ms |
| `test_count_splits` | 总量与 split 分组 | 全库 | `count()==323`；`count("dev")==23`；`count("test")==300` | 否 | <50ms |
| `test_search_fts` | FTS5 检索 | 关键词如 `"pylint"` | 返回列表且每条 `instance_id` 命中；空关键词优雅返回 `[]` | 否 | <50ms |

### 3.2 题面渲染（`tests/test_renderer.py`）

| 用例名 | 测什么 | fixture | 断言 | 网络/Docker | 耗时 |
|---|---|---|---|---|---|
| `test_ca_issue_no_answer_leak` | **答案隔离（P0）** | 用 `TaskBuilder().build("pylint-dev__pylint-7080")` 真实 TaskInstance | `render_agent_data(task)` 的 dict **不含** `patch`/`test_patch` 键，且不含 `pass_to_pass` 完整列表（仅 `pass_to_pass_count`） | 否（DB） | <20ms |
| `test_ca_prompt_no_gold_substring` | prompt 不得含 gold diff | 同上 | 渲染 `ca-task-prompt.md` 文本中**不包含** `task.gold_patch` 子串（防误植入答案） | 否 | <20ms |
| `test_review_contains_gold` | review.md 是含答案的审阅版 | 同上 | `render_review` 文本含 `task.gold_patch` 与 `task.test_patch`（审阅者需要） | 否 | <20ms |
| `test_jsonl_fields` | `task.jsonl` 12 字段契约 | 同上 | `render_jsonl` dict 含 `instance_id/repo/base_commit/patch/test_patch/problem_statement/hints_text/created_at/version/FAIL_TO_PASS/PASS_TO_PASS/environment_setup_commit`；`FAIL_TO_PASS` 为 list | 否 | <20ms |
| `test_fmt_null_degradation` | `_fmt` NULL 降级占位 | 无（纯函数） | `_fmt(None)=="（无）"`；`_fmt("")=="（无）"`；`_fmt("x")=="x"` | 否 | <1ms |
| `test_source_dir_from_gold` | `TaskInstance.source_dir` 推导 | 真实 gold_patch | 首个 `diff --git a/<path>` 的第一级目录；无头时回退 repo 末段 | 否（DB） | <1ms |
| `test_hints_truncation` | `hints_text[:2000]` 截断 | 长 hints 实例 | `render_agent_data` 的 `hints_text` 长度 ≤2000 | 否（DB） | <20ms |

### 3.3 Platform 抽象层（`tests/test_platform.py` 补全评估）

**现状评估**：现有 14 例已覆盖 `null_device`/`venv_bin_dir`/`default_shell` 的 POSIX 真值 + Windows（`os.name` mock）值，以及 `is_process_alive` 的 POSIX 真路径（当前进程存、超大 PID 亡、`pid=0` 返回 bool）与 Windows mock 三条主分支（`OpenProcess==0`→亡、`STILL_ACTIVE==259`→存、`exited==0`→亡）。**结论：Windows mock 基本完备，无需大面积补全。**

**唯一缺口（建议补 1 例，P0）**：`is_process_alive` Windows 分支中 `GetExitCodeProcess` 返回 `ok=False` 的早退路径（`platform.py:82-83` `if not ok: return False`）当前无覆盖。

```python
# 建议追加到 TestIsProcessAliveWindows
def test_getexitcode_call_failed_means_dead(self):
    fake_kernel32 = mock.MagicMock()
    fake_kernel32.OpenProcess.return_value = 1
    fake_kernel32.GetExitCodeProcess.return_value = False   # ok=False 分支
    fake_ctypes = mock.MagicMock()
    fake_ctypes.WinDLL.return_value = fake_kernel32
    fake_ctypes.wintypes = mock.MagicMock()
    fake_ctypes.wintypes.DWORD = mock.MagicMock()
    with mock.patch.dict(sys.modules, {"ctypes": fake_ctypes}):
        with mock.patch("swebench_exp_lite.runtime.platform.os.name", "nt"):
            self.assertFalse(is_process_alive(1234))
```

### 3.4 Agent runner 协议（`tests/test_registry.py` + `tests/test_replay_runner.py`）

| 用例名 | 测什么 | fixture | 断言 | 网络/Docker | 耗时 |
|---|---|---|---|---|---|
| `test_resolve_replay` | `resolve_runner("replay-agent")` | 无 | 返回 `ReplayRunner` 实例；无 precondition 报错 | 否 | <10ms |
| `test_resolve_unknown` | 未知名报错 | 无 | `assertRaises(ValueError)`（registry.py:88-90） | 否 | <10ms |
| `test_resolve_precondition_fail` | precondition 不通过 | mock `pc.check()→(False, "x")` | `assertRaises(RuntimeError)`（registry.py:97-101） | 否 | <10ms |
| `test_resolve_env_override` | `ANSWER_ADAPTER` env 生效 | 设 env=replay-agent | 解析为该 runner；清理 env | 否 | <10ms |
| `test_replay_writes_pred` | 真实 gold 落地 `.pred` | `data/swe_bench_data/*.jsonl`（真实） | `ReplayRunner().run(...).success==True`；`pred_path` 存在且其 JSON 含 `model_patch` 非空 | 否（需 repo_root 数据） | <1s |
| `test_replay_missing_patch` | 缺失 patch 优雅失败 | 伪造不存在 instance_id | 返回 `AgentResult(success=False)`（replay_runner.py:69-74） | 否 | <1s |
| `test_post_check_layout_contract` | 固化 replay vs 基类布局差异 | 真实写出的 `.pred` | 显式断言 `replay_runner.post_check` 路径 == `write_pred` 实际路径（防止日后布局漂移导致红线误判） | 否 | <1s |

### 3.5 Manifest / result.json 契约（`tests/test_manifest.py`）

| 用例名 | 测什么 | fixture | 断言 | 网络/Docker | 耗时 |
|---|---|---|---|---|---|
| `test_manifest_roundtrip` | set_meta/mark_started/mark_done | `tmp_path` | `manifest.json` 含 `instance_id/run_id/model`；`stages.S1_build.status=="done"`；`statuses()` 映射正确 | 否 | <10ms |
| `test_manifest_corrupt_backup` | 损坏 json 自动备份 | 先写垃圾到 `manifest.json` | 构造后生成 `manifest.bak-*.json` 且 `data` 重置为空壳（manifest.py:37-47） | 否 | <10ms |
| `test_s7_result_schema` | result.json 字段稳定 | 构造假 `eval_report.json`（含 tests_status）喂 `S7Record._build_result` | 含 `resolved/resolved_pct/report_source/fail_to_pass/pass_to_pass/baseline_resolved/stages/stage_timings/generated_at`；`baseline_resolved is None` | 否 | <10ms |
| `test_s7_report_source_degraded` | 降级误导钉死 | `eval_report` 中**不含** instance_id | `report_source=="instance_report"` 且 `resolved==False`（明确记录此降级行为，未来若要修再改契约） | 否 | <10ms |
| `test_stage_timings` | 耗时计算 | manifest 写入 started/finished ISO | `stage_timings` 返回各阶段秒数（浮点、四舍五入 1 位） | 否 | <10ms |

### 3.6 Harness 集成（`answer_evaluator/harness/tests/*` 复用 + 红线）

- 官方移植已有 `test_grading.py` / `test_test_spec.py` / `test_reporting.py`（**冻结，仅 bug-fix**），覆盖 `get_eval_report` 的 F2P/P2P 解析、`FAIL_ONLY_REPOS` 分支、report 聚合。本方案**不重复造**，仅做以下衔接：
- `test_s6_run_evaluation_replay`（集成，落 `local-test.sh` + `ubuntu-redline`）：以 `pylint-dev__pylint-7080` 的 gold patch 构造 `prediction.jsonl`，调用 `run_evaluation` 真实打分 → `report.json` 的 `resolved==True`。**这就是 `run_demo.sh` 红线的程序化版本**，建议抽成可复用函数，避免脚本与代码双重维护。
- `test_prepare_images_resource_linux`（Linux 专属）：`if platform.system()=="Linux": import resource` 分支（prepare_images.py:88-90）已由 `test_platform.TestLinuxSpecific.test_resource_import_on_linux` 守护，无需另写。

---

## 四、性能基线表（教学场景 = 墙钟耗时 + 资源占用）

> 测量手段：**容器外 stopwatch**（`time python -m ...` 或 `time.time()` 包裹）、CPU 用 `cProfile`（标准库，无新依赖）。
> 一律用 `replay-agent` 做确定性计时（S4≈0），隔离 S6 镜像开销。区分 **镜像缓存命中** vs **缺失**。

| 操作 | 可接受上限（建议值） | 测量方式 | 备注 / 风险点 |
|---|---|---|---|
| **S6_score 单实例（镜像已缓存）** | ≤120s（实测 30–90s） | `time` 包裹 `run_demo.sh` 或 S6 subprocess | 占全链路 ~99%；首次需构建/拉取，后续走本地缓存 |
| **S6_score 单实例（镜像缺失，需 pull/build）** | ≤600s（受 `timeout+1800`） | 删镜像后 `time` 跑红线 | 网络/GFW 主要瓶颈；OSS tar 降级路径更慢 |
| **S2 venv preinstall（缓存命中）** | <1s（直接 skip） | `time` 测 `_prepare_venv`（venv 已存在） | 见 `s2_prepare.py:149-151` 早退 |
| **S2 venv preinstall（缓存缺失）** | ≤600s（`ENV_PREINSTALL_TIMEOUT`） | 删 `runtime-cache/venvs/*` 后计时 | **最大 wall_time 浪费点**；`pip install -e .` + pytest |
| **docker image inspect** | ≤2s | `time` 直跑（`s2_prepare.py:29`） | 无镜像时返回 False 不报错 |
| **docker pull（官方/缓存）** | 网络相关，不卡上限 | `time docker pull` | GFW 用户走 `SWEBENCH_LITE_OSS` 阿里云 OSS tar 降级（`local-test.sh:66`） |
| **docker load（OSS tar）** | 数分钟级 | `time docker load` | Windows hosted runner 物理不支持（verification-spec §3） |
| **JSONL 加载（300+23 条）** | ≤100ms | `time` 包裹 `load_swebench_dataset` | 纯 `json.loads` 循环，非瓶颈 |
| **worktree 备仓（首建）** | 60–180s | `time` 测 `setup_repo`（首次 clone） | 网络 + IO，复用后 <1s |
| **git diff / git apply（patch 应用）** | <1s | `time` 包裹 `patch.py` | harness `GIT_APPLY_CMDS` 三级回退 |
| **DB `get()` 单条** | <10ms | `timeit` | 视索引，已建 partial index |
| **DB `count/search`** | <50ms | `timeit` | FTS5 BM25 |

**性能用例落地建议（P2）**：写 `scripts/perf-baseline.sh`，在 `local-test.sh` 红线跑通后追加，输出各上限对比表；不进 CI（超 30s 且需 Docker）。

---

## 五、CI 集成建议（取舍理由）

**严格遵守 verification-spec §3 严禁清单：CI 不跑红线 demo、不装 colima/qemu、不 docker load OSS、不扩 30s 窗口。**

| 测试集合 | 进 CI 30s（static job）？ | 进 pre-commit？ | 进 local-test / ubuntu-redline？ | 取舍理由 |
|---|---|---|---|---|
| `test_platform`（stdlib，无 DB/Docker） | ✅ 现有 | ✅ | ✅ | 零副作用、<1s；POSIX 真值 + WIN mock 双路径守护，正属于"PR 防线"职责 |
| `test_db_query`（DB 真实数据） | ❌ | ⚠️ 仅当 DB 存在时 | ✅ | 需 `swe_bench.db`（5.3MB，gitignore，CI mac/win 无）；ubuntu-redline 经 `install.sh` 落地后有库，可在此扩充跑 |
| `test_renderer` / `test_manifest` / `test_registry` | ❌（renderer/manifest 部分不需 DB，技术上可进） | ✅（不需 Docker 的子集） | ✅ | 纯函数/协议类，pre-commit 1min 内能跑完；DB 强依赖的子集留给本地 |
| `test_replay_runner`（真实 `.pred` 写出） | ❌ | ⚠️ DB 存在时 | ✅ | 需 `data/*.jsonl`（随仓），不需 Docker；pre-commit 若有库可跑 |
| harness 集成 `run_evaluation`（真实打分） | ❌ | ❌ | ✅（ubuntu-redline + 本地） | 必须 Docker；正是红线本体，下放给本地/ubuntu |
| 性能基线 | ❌ | ❌ | ⚠️ 本地可选 | 超 30s 且需 Docker，违反严禁清单 |

**CI 改动纪律**：任何修改 `.github/workflows/ci.yml` 的 PR **必须保留严禁清单**（verification-spec §3 末尾）。新增 DB / harness / replay 用例**只能**落到 `local-test.sh` 与主仓红线，不允许塞进 static job。

**pre-commit 调整建议**：当前 `.githooks/pre-commit` 跑 `pip install + 14 单测 + bash 语法`；建议把 §三 中"不需 Docker、不需 DB（或 DB 可选 skip）"的纯函数/协议用例并入同一 `unittest` 发现，使单测包仍 <1min，且不触碰红线。

---

## 六、已知边界与遗留风险（如何用 mock / 契约兜底）

1. **Docker 依赖路径（S2 镜像、S6 评分）无法在 mac/win CI 跑** → 用两层兜底：(a) `dry_run` 命令链组装契约测试（无 Docker 也能校验 S6 `run_evaluation` argv、S2 `docker image inspect` argv）；(b) 真实打分下放 `ubuntu-redline` + 本地 `local-test.sh`。
2. **网络 / 大模型路径（kimi/qwen/mimo/opencode）不可自动化** → 仅 `replay-agent` 零依赖可进流水线；其余靠用户真机 + `local-test.ps1` 手动验证；registry 单测用 **mock precondition** 而非真实 CLI 拦截。
3. **arm64 不在支持范围** → 所有涉及镜像执行的用例断言 **x86_64** 路径；`acquisition(arch="arm64")` 仅做字段/模式断言，不触发 build 执行。
4. **`swe_bench.db` 不入库（gitignore）** → DB 强依赖用例一律 `skipTest` 当库缺失；本地与 ubuntu-redline 经 `start.sh`/`install.sh` 落地后自然有库。
5. **`baseline_resolved` 恒为 None** → S7 合约测试显式断言，避免后续误以为"漏跑 baseline"。
6. **`report_source` 降级误导（§一风险）** → 已用 `test_s7_report_source_degraded` 钉死当前行为；若要改为 `"report_not_found"` 属契约变更，须同步改 `s7_record.py:64` 并评审。
7. **replay vs 基类 `post_check` 布局双实现（§一风险）** → `test_post_check_layout_contract` 固化当前路径，防止红线误判"未产出 pred"。

---

## 七、落地清单（建议新增文件）

```
swebench_exp_lite/tests/
  test_platform.py        # 现有 14 例 + 补 Windows GetExitCodeProcess 失败分支 1 例（§3.3）
  test_db_query.py        # 新增（§3.1，skip-if-DB-missing）
  test_renderer.py        # 新增（§3.2，含 CA 答案隔离 P0）
  test_registry.py        # 新增（§3.4，mock precondition）
  test_replay_runner.py   # 新增（§3.4，真实 .pred 写出）
  test_manifest.py        # 新增（§3.5，result.json 契约）

scripts/
  perf-baseline.sh        # 新增（§四，P2，本地可选，不进 CI）

# 复用（不改）：answer_evaluator/harness/tests/* （冻结）
# 复用（不改）：run_demo.sh / scripts/local-test.sh / scripts/windows/local-test.ps1
# 不建议改：.github/workflows/ci.yml（严守 30s + 严禁清单）
```

> 全部用例共用 `python -m unittest discover`（或显式模块）运行，零新依赖、零网络（DB 类 skip-if-missing）、零 Docker（除红线脚本本身）。红线门禁仍是 `run_demo.sh` 与 `local-test.sh`，本方案只扩充"快速 PR 防线"与"本地集成"两层，不替代红线。
