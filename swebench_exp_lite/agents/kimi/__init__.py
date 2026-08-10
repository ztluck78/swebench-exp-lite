"""kimi_agent：本地化 Kimi CLI Agent 执行模块。

借鉴 SWE-agent 的核心设计理念（分离 LLM 推理与命令执行、模块化工具系统、
沙箱环境管理），通过调用本地已安装和配置好的 Kimi CLI 来完成任务。

核心组件：
- KimiAgent: 主循环，管理 Kimi CLI 会话生命周期
- KimiEnvironment: 环境管理，仓库准备和产物收集
- KimiConfig: 配置管理，集中化配置
- KimiPromptBuilder: 提示词构造，模板化提示词
- KimiSessionManager: 会话管理，处理沙箱限制
- KimiAgentRunner: Orchestrator 集成，S4 适配器

使用方式：
    from kimi_agent import KimiAgent, KimiConfig

    config = KimiConfig(model="kimi-code/kimi-for-coding", timeout=600)
    agent = KimiAgent(config)
    result = agent.run(
        instance_id="pylint-dev__astroid-1196",
        issue_path=Path("issue.json"),
        ca_prompt_path=Path("ca-task-prompt.md"),
        repo_dir=Path("repo/"),
        output_dir=Path("output/"),
    )

Orchestrator 集成：
    --adapter kimi-agent
"""
__version__ = "1.0.0"
__author__ = "SWE-bench Exercise Platform"

from .agent import KimiAgent
from .config import KimiConfig
from .environment import KimiEnvironment, RunResult
from .prompt import KimiPromptBuilder
from .runner import KimiAgentRunner
from .session import KimiSessionManager

__all__ = [
    "KimiAgent",
    "KimiConfig",
    "KimiEnvironment",
    "KimiPromptBuilder",
    "KimiSessionManager",
    "KimiAgentRunner",
    "RunResult",
]