"""swebench_exp_lite.builder：出题模块（S1）。

从 LiteDB 取数 → TaskInstance → 渲染题面四件套：

- review.md           出题人审阅版（含答案，绝不交给 Agent）
- ca-issue.json       Agent 输入数据（7 字段，无答案）
- ca-task-prompt.md   Agent 任务指令（full 8 步）
- task.jsonl          标准 SWE-bench jsonl 行（harness 评分用，含答案）

移植自主仓 tools/assessment-builder：剔除 fast prompt 整链、render_extract_data、
manager 多数据源与独立 CLI（build/list/info 并入顶层 cli.py）。
"""
from .builder import CA_PREFIX, TaskBuilder
from .models import TaskInstance

__all__ = ["CA_PREFIX", "TaskBuilder", "TaskInstance"]
