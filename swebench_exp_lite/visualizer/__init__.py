"""swebench_exp_lite.visualizer：六阶段流程可视化教学模块。

读取 output/<iid>/ 既有产物（manifest.json / result.json / ca-issue.json /
model.patch / eval/report.json），渲染为自包含 HTML 页面，让学生直观看到
六阶段闭环每一步在干什么、干到哪了、产物长什么样。

教学价值：跑通实验 ≠ 理解实验。本模块让「跑」和「懂」对齐。

设计约束（来自 AGENTS.md 依赖口径）：
- 不引入新依赖（仍只有 docker/tqdm/unidiff/requests 四件套）
- 不改既有管线（manifest/result 产物结构冻结）
- 纯 Python 渲染 + 原生 JS，输出单一 .html 文件可双击打开
"""
from .data_loader import FlowData, StageData, load_all
from .renderer import render, write

__all__ = ["FlowData", "StageData", "load_all", "render", "write"]