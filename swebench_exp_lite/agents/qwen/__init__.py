"""qwen_agent：Qwen Code CLI Agent 执行模块。

通过本地 Qwen Code CLI 调用 Qwen 模型完成任务，与 kimi_agent
共享 swebench_exp_lite.runtime 基础设施层（repo / patch / artifacts / protocol）。

核心组件：
- QwenAgent: 主循环，管理 Qwen Code CLI 调用
- QwenEnvironment: 环境管理（复用 swebench_exp_lite.runtime 基础设施）
- QwenConfig: 配置管理
- QwenPromptBuilder: 提示词构造
- QwenAgentRunner: Orchestrator 集成，S4 适配器

前提：
- Qwen Code CLI 已安装并配置（qwen --version）
- 非交互模式：qwen -p "<prompt>" -m <model>

使用方式：
    from qwen_agent import QwenAgent, QwenConfig

    config = QwenConfig(model="qwen-code", timeout=600)
    agent = QwenAgent(config)
    result = agent.run(
        instance_id="pylint-dev__astroid-1196",
        issue_path=Path("issue.json"),
        ca_prompt_path=Path("ca-task-prompt.md"),
        repo_dir=Path("repo/"),
        output_dir=Path("output/"),
    )

Orchestrator 集成：
    --adapter qwen-agent
"""
__version__ = "1.0.0"
__author__ = "SWE-bench Exercise Platform"

from .agent import QwenAgent
from .config import QwenConfig
from .environment import QwenEnvironment, QwenResult
from .prompt import QwenPromptBuilder
from .runner import QwenAgentRunner

__all__ = [
    "QwenAgent",
    "QwenConfig",
    "QwenEnvironment",
    "QwenPromptBuilder",
    "QwenAgentRunner",
    "QwenResult",
]
