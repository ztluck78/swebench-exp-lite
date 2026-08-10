"""swebench-exp-lite：SWE-bench 精简教学实验平台。

包结构：
- db:        题库只读查询（LiteDB）
- builder:   出题（题面四件套渲染）
- runtime:   Agent 作答基础设施（移植自 agent_runtime）
- agents:    kimi / qwen / mimo / opencode 四品牌 runner
- pipeline:  六阶段编排（S1→S2→S4→S5→S6→S7）

入口：`python -m swebench_exp_lite --help`
"""
__version__ = "1.0.0"
