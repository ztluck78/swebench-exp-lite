"""pipeline.stages：六阶段 Stage 实现（S3 不实现，v1.1 可选）。"""
from .s1_build import S1Build
from .s2_prepare import S2Prepare
from .s4_solve import S4Solve
from .s5_patch import S5Patch
from .s6_score import S6Score
from .s7_record import S7Record

STAGES = [S1Build, S2Prepare, S4Solve, S5Patch, S6Score, S7Record]

__all__ = ["STAGES", "S1Build", "S2Prepare", "S4Solve",
           "S5Patch", "S6Score", "S7Record"]
