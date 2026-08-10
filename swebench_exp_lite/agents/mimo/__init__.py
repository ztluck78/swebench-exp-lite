"""mimo_agent：MiMo Code CLI Agent 执行模块。

通过本地 MiMo Code CLI（`mimo`）调用模型完成任务，与 kimi_agent /
qwen_agent 共享 swebench_exp_lite.runtime 基础设施层（repo / patch / artifacts /
protocol）。

核心组件：
- MimoAgent: 主循环，管理 MiMo Code CLI 调用
- MimoEnvironment: 环境管理（复用 swebench_exp_lite.runtime 基础设施）
- MimoConfig: 配置管理
- MimoPromptBuilder: 提示词构造
- MimoAgentRunner: Orchestrator 集成，S4 适配器

前提：
- MiMo Code CLI 已安装并配置（`mimo --version`）
- 非交互模式：`mimo run "message" -m <model> --print-logs`

使用方式：
    from mimo_agent import MimoAgent, MimoConfig

    config = MimoConfig(model="github-copilot/claude-opus-4.8", timeout=600)
    agent = MimoAgent(config)
    result = agent.run(
        instance_id="pylint-dev__astroid-1196",
        issue_path=Path("issue.json"),
        ca_prompt_path=Path("ca-task-prompt.md"),
        repo_dir=Path("repo/"),
        output_dir=Path("output/"),
    )

Orchestrator 集成：
    --adapter mimo-agent
"""
__version__ = "1.0.0"
__author__ = "SWE-bench Exercise Platform"

from .agent import MimoAgent
from .config import MimoConfig
from .environment import MimoEnvironment, MimoResult
from .prompt import MimoPromptBuilder
from .runner import MimoAgentRunner

__all__ = [
    "MimoAgent",
    "MimoConfig",
    "MimoEnvironment",
    "MimoResult",
    "MimoPromptBuilder",
    "MimoAgentRunner",
]
