"""answer_evaluator：从 princeton-nlp/SWE-bench v4.1.0 提炼的 harness 评分与镜像构建核心。

来源：princeton-nlp/SWE-bench @ f7bbbb2ccdf479001d6467c9e34af59e44a840f9（上游 commit 日期 2026-03-19）
     经 swebench-exercise-platform 主仓提炼后，再随 swebench-exp-lite 做二次裁剪。
协议：MIT License（见本目录 LICENSE）

swebench-exp-lite 裁剪说明：
- 仅保留 harness/ 子包（评分 + 镜像构建），云端评测子包与 collect.* 顶层依赖不随移植；
- Python-only：constants/dockerfiles/log_parsers 仅留 python 语言文件，
  test_spec 删 javascript 分支；
- 数据集仅支持本地 .json/.jsonl（剔除 HF datasets 联网分支与 python-dotenv）。
"""
__version__ = "4.1.0-extracted-lite"
__upstream__ = "princeton-nlp/SWE-bench"
__upstream_sha__ = "f7bbbb2ccdf479001d6467c9e34af59e44a840f9"
