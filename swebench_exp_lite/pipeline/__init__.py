"""swebench_exp_lite.pipeline：六阶段编排（S1→S2→S4→S5→S6→S7）。

S3（baseline）不实现（v1.1 可选 --run-baseline）；省略 S3 不影响
resolved 判定——resolved 相对 gold 测试集判定，与 baseline 无关。
"""
from .context import TaskContext
from .manifest import Manifest
from .runner import run_pipeline

__all__ = ["TaskContext", "Manifest", "run_pipeline"]
