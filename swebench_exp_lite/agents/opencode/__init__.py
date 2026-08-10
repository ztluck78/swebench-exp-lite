"""opencode_agent：Opencode CLI Agent 执行模块。

通过本地 opencode CLI（`opencode`）调用模型完成任务，与 kimi_agent /
qwen_agent / mimo_agent 共享 swebench_exp_lite.runtime 基础设施层（repo / patch /
artifacts / protocol）。

核心组件：
- OpencodeAgent: 主循环，管理 opencode CLI 调用
- OpencodeEnvironment: 环境管理（复用 swebench_exp_lite.runtime 基础设施）
- OpencodeConfig: 配置管理
- OpencodePromptBuilder: 提示词构造
- OpencodeAgentRunner: Orchestrator 集成，S4 适配器

前提：
- opencode CLI 已安装并配置（`opencode --version`）
- 非交互模式：`opencode run "<prompt>" --dir <repo> -m <model> --format json --auto`

使用方式：
    from opencode_agent import OpencodeAgent, OpencodeConfig

    config = OpencodeConfig(model="minimax-cn-coding-plan/MiniMax-M3", timeout=1800)
    agent = OpencodeAgent(config)
    result = agent.run(
        instance_id="pylint-dev__astroid-1196",
        issue_path=Path("issue.json"),
        ca_prompt_path=Path("ca-task-prompt.md"),
        repo_dir=Path("repo/"),
        output_dir=Path("output/"),
    )

Orchestrator 集成：
    --adapter opencode-agent
    # 或通过 profile: --profile opencode-agent-e2e
"""
__version__ = "1.0.0"
__author__ = "SWE-bench Exercise Platform"

from .agent import OpencodeAgent
from .config import OpencodeConfig
from .environment import OpencodeEnvironment, OpencodeResult
from .prompt import OpencodePromptBuilder
from .runner import OpencodeAgentRunner

__all__ = [
    "OpencodeAgent",
    "OpencodeConfig",
    "OpencodeEnvironment",
    "OpencodeResult",
    "OpencodePromptBuilder",
    "OpencodeAgentRunner",
]