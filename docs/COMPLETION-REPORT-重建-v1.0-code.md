# swebench-exp-lite 重建完成报告（v1.0-code）

> 依据计划：`重建_swebench-exp-lite_教学仓_task-54a.md`（源 spec：v4 最终合并版重建计划）
> 完成时间：2026-08-10 ｜ 仓库：`ztluck78/swebench-exp-lite`（私有，main = `c116bbf`）

## 一、成果摘要

在当前目录全新构造了 swebench-exp-lite 教学仓库：单一 Python 包 `swebench_exp_lite`
+ 原样移植裁剪的 `answer_evaluator`，共 94 个 .py 文件、9 个 Phase 分段提交全部推送。
**v1.0 出口红线实跑通过**：macOS 上 replay-agent 跑通
`pylint-dev__pylint-7080` 出题→做题→打分闭环，`result.json` 输出
`resolved=true / resolved_pct=100.0`（F2P 1/1、P2P 120/120），流程本体 44s，
且 resolved 可追溯 harness 真实 report.json（非兜底）。

## 二、关键步骤（Phase 0-9）

| Phase | 内容 | 提交 |
|---|---|---|
| 0 | H3 import 依赖映射表（四类模式全树扫描） | `cbd91e3` |
| 1 | 仓库骨架（git init / pyproject 四件套 / README / AGENTS / conftest）+ 建仓 | `cbd91e3` |
| 2 | 数据层（jsonl 323 条 + 8 SQL + LiteDB 移植） | `d057eaf` |
| 3 | answer_evaluator 移植裁剪（Python-only、modal 清理、本地 jsonl） | `4079c63` |
| 4 | runtime + 四品牌 agents 移植重构（H2 字段清点） | `f5c1252` |
| 5 | builder 移植精简（剔 fast prompt 整链） | `9d470e7` |
| 6 | pipeline 重写 + 顶层 CLI（~1300 行核心新代码，H1/H2 落地） | `f59492c` |
| 7 | start.sh / run_demo.sh / check-agents.sh | `fb2cd8e` |
| 8 | 红线验证通过 + 两处修复（manifest 负耗时、bash 全角字符） | `825b728` |
| 9 | GETTING-STARTED.md（8 章自包含教程，实跑核对） | `c116bbf` |

## 三、主要文件

```
swebench_exp_lite/          # 单一包
├── cli.py / __main__.py    # build/list/info/run/candidates
├── db/query.py             # LiteDB 全公开 API（323 条）
├── builder/                # 出题四件套（full 8 步 prompt）
├── runtime/                # 19 文件（registry 六项 / replay_runner / progress 等）
├── agents/{kimi,qwen,mimo,opencode}/
└── pipeline/               # context(H2 白名单) / manifest / report_utils(H1) /
                            # runner + stages/{s1,s2,s4,s5,s6,s7}
answer_evaluator/           # harness 原样移植 + Python-only 裁剪
data/swe_bench_data/        # swe-bench-lite(300) + lite-dev(23)
database/migrations/        # 8 个 SQL（swe_bench.db git 忽略）
start.sh / run_demo.sh / check-agents.sh
GETTING-STARTED.md / README.md / AGENTS.md / docs/import-map-swebench-exp-lite.md
```

## 四、验证证据

- **红线**：`output/pylint-dev__pylint-7080/result.json` → `resolved=true`、
  `resolved_pct=100.0`、`report_source=instance_report`、`fail_to_pass 1/0`、
  `pass_to_pass 120/0`；流程本体 44s（2-5 分钟达标）。
- **H1 加强判定**：`logs/run_evaluation/<run_id>/replay__gold-patch/<iid>/report.json`
  真实存在且含 `"resolved": true`；result.json grep 无 "report not found"。
- **grep 零残留**：answer_evaluator 内 modal（排除 multimodal）/ 非 python 语言
  import / 全仓 datasets·dotenv import 均零命中；pip list 仅四件套。
- **registry**：RUNNERS 六项齐全；`resolve_runner('replay-agent')` 可实例化。
- **start.sh 幂等**：删 .venv 重跑，DB/镜像短路不重复下载；323 断言通过。
- **断点续跑**：S1-S5 skip、S6/S7 重跑实测生效。
- **指南**：grep 无主仓路径引用；replay 语义与 "resolved 与 baseline 无关" 两处澄清在文。

## 五、关键排障

1. **镜像环境损坏**：首次红线 unresolved。主仓 gold 对照实验定位为评测镜像
   20 小时前被本地重建导致依赖漂移（120 个回归测试全挂），与移植无关；
   `docker pull` 官方原版镜像后恢复。教训写入 FAQ Q3（勿 force_rebuild 官方镜像）。
2. **spec 遗漏修正**：`harness/__init__.py` 引用被删的 remove_containers、
   `full_dataset` 为聚合报告必需（Phase 3 误删后恢复）——均补记入 import-map。

## 六、遗留（按用户决策延后）

- **Phase 10 v1.0-release**：Release 上传 DB、OSS 上传镜像 tar（~1.14GB）、
  替换 `start.sh` 中 `RELEASE_DB_URL` / `OSS_BASE` 两处占位符、fresh clone 验证。
- v1.1 路线图：S3_baseline / `--run-baseline`、Ubuntu/WSL2 红线、pytest 基座。
