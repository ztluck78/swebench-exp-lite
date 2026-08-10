"""swebench_exp_lite.tests：单元测试基座。

0.1.0 时代以"红线验证（./run_demo.sh）"为唯一验收门禁（见
``conftest.py`` 注释 + AGENTS.md §验收红线），不要求 pytest 跑通。
0.2.0 起把 platform 抽象层加进来，需要单元测试守住 POSIX/Windows 双路径
行为对齐（Windows 路径用 mock 验证调用形状，避免在 macOS 上需要装 ctypes 假模块）。

后续其他模块补测试也往这里加。
"""
