# tools/answer_evaluator

从 `princeton-nlp/SWE-bench` v4.1.0 提炼的 harness 评分与镜像构建核心，作为本项目自研模块。

## 提炼记录

| 项 | 值 |
|---|---|
| 上游 | [princeton-nlp/SWE-bench](https://github.com/princeton-nlp/SWE-bench) |
| 版本 | v4.1.0 |
| 提炼 commit SHA | `f7bbbb2ccdf479001d6467c9e34af59e44a840f9` |
| 提炼日期 | 2026-08-02 |
| 上游协议 | MIT（见 [LICENSE](./LICENSE)） |
| 原始目录 | `swebench/harness/`（10,238 行） |

## 提炼内容

完整复制上游 `swebench/harness/` 子包：

```
harness/
├── run_evaluation.py       # 评分入口：subprocess 调用 `python -m answer_evaluator.run_evaluation`
├── grading.py              # F2P/P2P 判定（评分公式实现）
├── test_spec/              # 镜像名 / Dockerfile 生成
├── constants/              # MAP_REPO_VERSION_TO_SPECS 版本映射
├── docker_build.py         # 镜像构建
├── docker_utils.py         # Docker SDK 封装
├── prepare_images.py       # 镜像准备入口
├── log_parsers/            # 测试日志解析
├── utils.py / reporting.py / remove_containers.py
└── dockerfiles/            # 基础 Dockerfile 模板
```

## 已剔除

- `modal_eval/`（云端 modal.com 评测，本项目不使用）
- `swebench.collect.*` / `swebench.inference.*` / `swebench.versioning.*` 等其他子包的顶层 import 依赖

## 使用方式

原 `swebench.harness.*` 的调用点现在改为 `answer_evaluator.harness.*`：

```python
# 评分
[sys.executable, "-m", "answer_evaluator.harness.run_evaluation", ...]

# 镜像准备
[sys.executable, "-m", "answer_evaluator.harness.prepare_images", ...]

# 镜像名解析（延迟可选 import）
from answer_evaluator.harness.test_spec import make_test_spec
```

## 验证门槛

提炼后的评分结果必须与原 `tools/SWE-bench/` 输出一致。验证方法：

```bash
# gold 冒烟（不调 LLM，最稳）
python -m answer_evaluator.harness.run_evaluation \
    --predictions_path gold --max_workers 1 \
    --instance_ids sympy__sympy-20590 --run_id smoke-gold
# 对比 logs/run_evaluation/smoke-gold/ 与 tools/SWE-bench/logs/run_evaluation/smoke-gold/ 的 report.json
```

## 上游漂移监控

- 关注上游 [Releases](https://github.com/princeton-nlp/SWE-bench/releases) 与 PR（新 repo 支持、Docker spec 修复）
- 升级时执行：
  1. `git clone princeton-nlp/SWE-bench` 至临时目录，校验新 SHA
  2. 与本目录 diff，重点关注 `test_spec/`、`constants/`、`docker_build.py`
  3. 同步后重跑 gold 冒烟，验证评分输出一致

## 已知限制

- 仅保留单 GPU / 本地 Docker 评测路径（Pro 与 modal 路径未提炼）
- 不携带数据集构建工具（HF 上游用），本项目使用自研 `database/` 模块