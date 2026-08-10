# scripts/macos/

0.1.0 时代 macOS 入口脚本（`start.sh` / `run_demo.sh` / `check-agents.sh`）
**仍保留在仓根**，不搬到这里。理由：

- AGENTS.md 明确这些 .sh 是"部署与演示入口，保持幂等"
- 0.1.0 红线验证（`./run_demo.sh` → `output/pylint-dev__pylint-7080/result.json`
  `resolved=true`）走仓根路径，搬位置会破坏现有文档与 CI 引用
- 现有 macOS 用户（包括 CI 流水线）的命令记忆零迁移

本目录作为 0.3.0+ 扩展位。未来如果 macOS 脚本要扩展（例如 Apple Silicon
专属 Rosetta 优化、macOS 14+ 专属快捷指令），会搬到这里，并通过
`scripts/macos/install.sh` 等入口做软链到仓根 .sh 保持兼容。

当前文件：仅 `README.md`（占位）。
