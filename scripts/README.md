# scripts/ — 平台脚本集中目录

0.2.0 起：把多平台启动脚本统一收口到这里。`start.sh` / `run_demo.sh` /
`check-agents.sh` 这三个 0.1.0 时代的 macOS bash 脚本**仍保留在仓根**
（0.1.0 红线零破坏），新加的平台走 `scripts/<platform>/` 子目录。

## 平台索引

| 平台 | 安装 | 跑 demo | 检测 Agent | 验证状态 |
|---|---|---|---|---|
| macOS（0.1.0 红线） | `./start.sh` | `./run_demo.sh` | `./check-agents.sh` | 已验证 |
| Windows 11（0.2.0） | `pwsh scripts/windows/install.ps1` | `pwsh scripts/windows/run-demo.ps1` | `pwsh scripts/windows/check-agents.ps1` | 0.2.0 新增 |
| Windows 11（.cmd 兜底） | `./scripts/windows/install.cmd` | `./scripts/windows/run-demo.cmd` | `./scripts/windows/check-agents.cmd` | 同上，pwsh 缺失时降级 powershell 5.1 |
| Ubuntu | （未来） | （未来） | （未来） | `scripts/ubuntu/.gitkeep` 占位 |

## 各平台子目录

- `scripts/macos/`：macOS 入口占位。0.1.0 的 `.sh` 仍在仓根，未来如果 macOS 脚本要扩展（如 Apple Silicon 专属优化），会搬到这里。
- `scripts/windows/`：Windows 11 适配主体（0.2.0 新增）。详细说明见 [windows/README.md](windows/README.md)。
- `scripts/ubuntu/`：未来扩展位，目前只放 `.gitkeep`。

## 跨平台代码复用

所有平台脚本最终都调用同一个 Python 入口：

```bash
python -m swebench_exp_lite run --instance <iid> --adapter <adapter>   # macOS / Linux
pwsh -m swebench_exp_lite run --instance <iid> --adapter <adapter>    # Windows PowerShell
```

跨平台逻辑全部收敛在 `swebench_exp_lite/runtime/platform.py`
（0.2.0 新增的 4 个函数：`null_device` / `is_process_alive` /
`venv_bin_dir` / `default_shell`），平台脚本只做"环境准备 + 调用入口"。
