"""根 conftest：swebench-exp-lite 测试基座占位。

v1.0 以红线验证（./run_demo.sh）为验收，不带 pytest 基座（列 v1.1 路线图）。
本文件保留是为了：
1. 让仓根成为 pytest rootdir 锚点（未来加测试时路径解析稳定）；
2. 保证 `swebench_exp_lite` 包根在 sys.path 可见（editable 安装前的兜底）。
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
