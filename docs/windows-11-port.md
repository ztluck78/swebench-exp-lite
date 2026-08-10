# Windows 11 移植笔记（0.2.0）

> 踩过的坑、决策记录、回退方案。给后续维护者与 v0.3+ Ubuntu 适配者参考。

## 1. 移植目标

- **目标平台**：Windows 11 x86_64 + PowerShell 7+（主）/ PowerShell 5.1（兜底）
- **目标用户**：原生 Windows 用户（非 WSL2）。希望用 `pwsh scripts/windows/install.ps1` 一键装 + `run-demo.ps1` 跑通
- **不改动的红线**：根目录 `start.sh` / `run_demo.sh` / `check-agents.sh` 字节级不动
- **核心交付物**：3 个 `.ps1` + 3 个 `.cmd` + 1 个 `_common.ps1` + 1 个 `README.md` + CI

## 2. 调研阶段的关键发现

### 2.1 Python 包内 95% 已跨平台

- `pathlib.Path` 已是跨平台写法
- 所有 `subprocess.run` 都是 list 形式（无 `shell=True`）
- 无 `os.chmod` / `os.system` / `fork` / `signal.SIG*` 等 POSIX-only 调用
- 无 `platform.system()` 分支

### 2.2 真正卡 Windows 的硬编码只有 3+1 处

调研阶段用 ripgrep 扫了 4 类平台敏感模式，定位 4 处硬编码：

| 文件 | 行号（0.2.0 改动前） | 硬编码 | 修复 |
|---|---|---|---|
| `swebench_exp_lite/runtime/patch.py` | 77 | `"/dev/null"` | 改用 `platform.null_device()` |
| `swebench_exp_lite/runtime/repo.py` | 113 | `os.kill(pid, 0)` | 改用 `platform.is_process_alive(pid)` |
| `answer_evaluator/harness/run_evaluation.py` | 9-10, 522-523 | `import resource` + `setrlimit` | 三分支：Linux import，其他 skip |
| `answer_evaluator/harness/prepare_images.py` | 2, 86 | `import resource` + `setrlimit` | 同上（审计阶段新发现） |

其他被检查过但**未改动**的疑点：

- `answer_evaluator/harness/docker_utils.py:150`：`os.kill(pid, signal.SIGKILL)` 杀容器内 PID
  - 实际行为：macOS 上这是隐藏 bug（容器 PID 是 Docker Desktop VM 内的，宿主 Python 进程杀不到 VM 内进程），但函数后面有 `container.remove(force=True)` 兜底，不影响主流程
  - 决策：**不动**。属于历史遗留 bug，不在 Windows 适配范围
- `answer_evaluator/harness/docker_build.py:521`：`command="tail -f /dev/null"` 容器内命令
  - 容器是 Linux，宿主 OS 无关
- `answer_evaluator/harness/utils.py:334, 342, 346`：`/dev/null` 字符串
  - unified diff 格式标准约定（"new file" 端点），与 OS 无关
- `swebench_exp_lite/agents/*/prompt.py`：`$VENV/bin/activate`
  - Agent 在 Docker 容器内跑（Linux），宿主 OS 无关
- `answer_evaluator/harness/test_spec/python.py`：`posixpath`
  - Python 标准库的 POSIX 路径处理函数库，与宿主 OS 无关

### 2.3 平台抽象层设计：4 个函数

```python
def null_device() -> str          # "/dev/null" / "nul"
def is_process_alive(pid) -> bool # os.kill / ctypes OpenProcess
def venv_bin_dir() -> str         # "bin" / "Scripts"
def default_shell() -> str        # "bash" / "cmd.exe"
```

仅依赖标准库（os / sys / ctypes），不引入新依赖，符合"四件套"约束。
单元测试用 stdlib `unittest` 写（14 个测试用例），**故意不引入 pytest**
（pytest 算新依赖，违反 AGENTS.md「四件套」严格约束）。

Windows mock 路径用 `sys.modules['ctypes']` 替换 + `os.name` mock，验证调用形状。

## 3. 移植决策记录

### 3.1 为什么是 PowerShell 7+ + 5.1 兜底（而不是纯 7+ / 纯 .cmd）？

| 方案 | 优点 | 缺点 | 决策 |
|---|---|---|---|
| 纯 PowerShell 7+ | 现代，社区主推 | Win11 默认装 5.1，需用户手动 `winget install` | ✗ |
| 纯 .cmd / .bat | 零依赖 | 表达力弱（颜色、`$ErrorActionPreference` 不可用） | ✗ |
| **PowerShell 7+ 为主 + .cmd 兜底转发** | 7+ 体验，5.1 兜底，零额外安装 | 多一个 .cmd 文件 | ✓ |

### 3.2 为什么用 `scripts/windows/` 而不是把 `.ps1` 放仓根？

- 仓根的 `start.sh` / `run_demo.sh` / `check-agents.sh` 是 0.1.0 红线脚本（已写进 AGENTS.md "字节级不动"约束）
- 在仓根放 `.ps1` 会和 `.sh` 视觉混在一起，且未来加 Ubuntu 时又要重做决策
- 集中到 `scripts/<platform>/` 模式，未来加 Ubuntu / 其它平台直接复制粘贴

### 3.3 为什么不动 docker_utils.py:150 的 os.kill？

属于"已存在的隐藏 bug"（macOS 上容器 PID 是 VM 内的，宿主 Python 杀不到），不是 Windows 适配引入的问题。修它需要：
1. 改成用 `container.client.api.exec_create` + `kill` 命令（在容器内杀）
2. 或依赖 `container.remove(force=True)` 兜底（当前行为）

按"answer_evaluator 只允许 bug fix 级别最小改动"原则，不在本次范围。

### 3.4 为什么 .gitattributes 必须加？

- Windows 开发者 clone 后，git 默认 `core.autocrlf=true`
- .sh 文件会被自动转 CRLF → 0.1.0 红线 start.sh 立即崩
- .gitattributes 强制 `.sh` 保持 LF、`.ps1` 允许 CRLF（PowerShell 5.1 强依赖）
- 实测加完后，Windows 开发者无需任何 git 配置变更

## 4. 已知坑与未来工作

### 4.1 PowerShell 5.1 默认安装环境

- Win11 默认带 PowerShell 5.1，但 `pwsh`（7+）需手动装
- `.cmd` 兜底已处理：先 `where pwsh`，缺失则降级到 5.1
- CI windows-latest 默认装 5.1，需要 CI 加 `pwsh` 安装步骤（v0.3+）

### 4.2 Windows on ARM 未验证

- 评测镜像 `sweb.eval.x86_64.*` 是 x86_64 Linux 镜像
- Windows 11 on ARM 需 Docker Desktop 启用 x86_64 emulation
- v0.2.0 未在 ARM 实机验证；路线图列入 v0.3+ 实机测试

### 4.3 行尾 BOM 兼容性

- PowerShell 5.1 在 zh-CN 系统下对**无 BOM UTF-8** 解析有坑（中文注释会乱码）
- `_common.ps1` 头部用 UTF-8 with BOM（让 PowerShell 5.1 正确识别）
- `.gitattributes` 不影响 BOM，只管行尾
- 写新 `.ps1` 时建议保持 UTF-8 with BOM

### 4.4 路径含空格的引号

- `C:\Users\My Name\Projects\...` 是常见场景
- `.cmd` 兜底已经用 `"%~dp0xxx.ps1"` 包好
- PowerShell 7+ 默认不展开未引号带空格路径，建议调用方总是包引号

### 4.5 Windows CI 镜像拉取速度

- GitHub Actions windows-latest 拉 x86_64 镜像比 macos-latest 慢（Windows 上 WSL2 桥接）
- demo 题 1-5 分钟属正常范围
- CI 超时可考虑把 SWEBENCH_LITE_OSS 设为本地 OSS 镜像

## 5. 红线升级

依据记忆「版本号应采用诚实的预发布标注（0.1.0）而非 v1.0」：

- 0.1.0：仅 macOS 验证
- 0.2.0（本次）：macOS + Windows 11 双平台验证完成
- 0.3.0+：Ubuntu 加上后

## 6. 验收门禁

双平台 CI 必过（`.github/workflows/ci.yml`）：
- `macos-latest` job：跑 `./start.sh` + `./run_demo.sh`，断言 `result.json.resolved=true`
- `windows-latest` job：跑 `pwsh scripts/windows/install.ps1` + `run-demo.ps1`，同断言
- 两个 job 各自再跑 `python -m unittest swebench_exp_lite.tests.test_platform -v`（14 用例全过）

任何 PR 改动后两个 job 都必须过，方可合并 main。

## 7. 未来加 Ubuntu 适配的 checklist

按本文档 + plan 文件 §6 流程，加 Ubuntu 适配时：

1. 把 `scripts/ubuntu/.gitkeep` 替换为 `install.sh` / `run-demo.sh` / `check-agents.sh` + `_common.sh`（bash 版共享函数库）
2. 复用 macOS 主体（bash 99% 兼容），仅改 docker 启动提示（`systemctl start docker`）与 venv 路径（已是 `bin/`，无需改）
3. `.github/workflows/ci.yml` 的 matrix 加 `ubuntu-latest`
4. `README.md` 平台支持段加 Ubuntu
5. `GETTING-STARTED.md` 1. 环境准备段加 Ubuntu
6. `pyproject.toml` version 升 0.2.0 → 0.3.0
7. 跑过双 job CI 后方可发版

预计 Ubuntu 适配工作量：2-3 小时（0.2.0 时已为 Ubuntu 留 `scripts/ubuntu/` 占位 + matrix 留扩展位）。
