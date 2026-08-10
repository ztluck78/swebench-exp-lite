"""出题模块 · 渲染层（双版本）

从同一个 :class:`TaskInstance` 渲染：

- ``render_review``            -> 人工审阅版 Markdown（review.md）
- ``render_agent_data``        -> Agent 输入数据 JSON（ca-issue.json，7 字段标准结构）
- ``render_agent_prompt``      -> Agent 任务指令 Markdown（task-prompt.md，8 步完整版）
- ``render_jsonl``             -> 标准 SWE-bench jsonl 行（task.jsonl，12 字段）

swebench-exp-lite 裁剪：剔除 render_agent_prompt_fast（fast prompt 整链）与
render_extract_data（极简 CLI 专用），统一 full 8 步 prompt。

渲染逻辑不关心数据来源，只读 ``TaskInstance``。DB 中 NULL 的字段按现状降级提示，
不自行从外部补取。
"""
from __future__ import annotations

import json

from .models import TaskInstance


# ---------------------------------------------------------------------------
# 共享辅助
# ---------------------------------------------------------------------------
def _format_test_list(tests: list) -> str:
    """把测试名列表渲染为 Markdown 无序列表（空则提示）。"""
    if not tests:
        return "（无）"
    return "\n".join(f"- `{t}`" for t in tests)


def _fmt(value, placeholder: str = "（无）") -> str:
    """统一降级：空字符串 / None 显示为占位符。"""
    if value is None:
        return placeholder
    s = str(value).strip()
    return s if s else placeholder


# C-14：ca-issue.json 位于任务目录（作答 worktree 之外），渲染时未知则写占位说明
_TASK_DIR_UNKNOWN = "（由 orchestrator 注入；作答工作区为独立 worktree，ca-issue.json 不在其中）"


def _task_dir_line(task_dir: str | None) -> str:
    """模板头部注入的任务目录指引行（TASK_DIR）。"""
    display = str(task_dir).strip() if task_dir else _TASK_DIR_UNKNOWN
    return f"任务目录（TASK_DIR，作答工作区外）：{display}"


# ---------------------------------------------------------------------------
# 版本 A：人工审阅版（Markdown）
# ---------------------------------------------------------------------------
def render_review(task: TaskInstance) -> str:
    """渲染人工审阅版 Markdown（review.md）。"""
    return f"""# 任务审阅：{_fmt(task.instance_id, task.repo)}

## 一、题目背景

- **所属仓库**: {_fmt(task.repo)}（[GitHub]({_fmt(task.repo_url, "#")})）
- **数据集版本**: SWE-bench_Lite（split: {_fmt(task.split)}）
- **Issue 时间**: {_fmt(task.created_at)}
- **版本**: {_fmt(task.version)} ｜ **语言**: {_fmt(task.language)}
- **难度**: {task.difficulty_display}（F2P={task.f2p_count}, P2P={task.p2p_count}, patch={task.patch_size}B）
- **Issue 链接**: {_fmt(task.instance_url, "（无）")}

## 二、要求说明

### 问题描述
{_fmt(task.problem_statement)}

### 额外提示
{_fmt(task.hints_text)}

### 复现代码（自动提取）
{_fmt(task.repro_snippet, "（未从 problem_statement 中提取到代码块，需手动编写）")}

## 三、评分标准

| 类别 | 数量 | 说明 |
|---|---|---|
| FAIL_TO_PASS | {task.f2p_count} | 修复后必须通过的测试 |
| PASS_TO_PASS | {task.p2p_count} | 修复前后都必须通过（防回归） |
| 判定公式 | resolved = F2P全过 ∧ P2P全过 |

### FAIL_TO_PASS 测试列表
{_format_test_list(task.fail_to_pass)}

### PASS_TO_PASS 测试列表
{_format_test_list(task.pass_to_pass)}

## 四、预期答案（gold patch）

```diff
{_fmt(task.gold_patch)}
```

## 五、测试补丁（test_patch）

```diff
{_fmt(task.test_patch)}
```

## 六、环境配置

| 架构 | 镜像 | 获取方式 | namespace | cache_level |
|---|---|---|---|---|
| x86_64 | {_fmt(task.image_x86_64)} | {_fmt(task.image_mode_x86_64)} | {_fmt(task.namespace_x86_64)} | {_fmt(task.cache_level_x86_64)} |
| arm64 | {_fmt(task.image_arm64)} | {_fmt(task.image_mode_arm64)} | {_fmt(task.namespace_arm64)} | {_fmt(task.cache_level_arm64)} |

**推荐超时**: {task.recommended_timeout}s

## 七、版本控制

- **base_commit**: `{_fmt(task.base_commit)}`
- **environment_setup_commit**: `{_fmt(task.environment_setup_commit)}`
- **SSH clone**: `{_fmt(task.ssh_url)}`
"""


# ---------------------------------------------------------------------------
# 版本 B-1：Agent 输入数据（JSON，7 字段标准结构）
# ---------------------------------------------------------------------------
def render_agent_data(task: TaskInstance) -> dict:
    """渲染 Agent 输入数据 JSON（标准 7 字段结构）。

    取代 problem_builder.to_solve_dict()：指令与数据分离，只给"数据"，
    不给 gold_patch / test_patch（避免泄露答案），pass_to_pass 只给数量。
    """
    return {
        "instance_id": task.instance_id,
        "repo": task.repo,
        "base_commit": task.base_commit,
        "problem_statement": task.problem_statement,
        "fail_to_pass": task.fail_to_pass,                 # 完整列表
        "pass_to_pass_count": task.p2p_count,              # 仅数量，不给完整列表
        "hints_text": task.hints_text[:2000] if task.hints_text else "",
    }


# ---------------------------------------------------------------------------
# 版本 B-2：Agent 任务指令（Markdown，8 步）
# ---------------------------------------------------------------------------
def render_agent_prompt(task: TaskInstance, task_dir: str | None = None) -> str:
    """渲染 Agent 任务指令 Markdown（task-prompt.md）。

    C-14：``task_dir`` 为任务目录绝对路径（ca-issue.json 所在处，作答
    worktree 之外）；未知时模板内写占位说明，由 orchestrator 注入。
    """
    test_commands = "\n".join(
        f"   - python3 -m pytest {t} -xvs" for t in task.fail_to_pass
    )
    source_dir = task.source_dir

    return f"""# 任务指令

{_task_dir_line(task_dir)}

## 输入数据
- 仓库: {_fmt(task.repo)}（{_fmt(task.repo_url, "#")}）
- 基线 commit: `{_fmt(task.base_commit)}`
- 问题描述: 见 ca-issue.json 的 problem_statement 字段

## 任务步骤

STEP 1 — 读取任务：
   cat "$TASK_DIR/ca-issue.json"
   理解 instance_id、repo、base_commit、problem_statement、fail_to_pass。

STEP 2 — 探索仓库：
   关键文件提示：{_fmt(task.key_files_hint, "（未标注，请自行探索仓库结构）")}

STEP 3 — 编写复现脚本：
   {_fmt(task.repro_snippet, "# 未从 problem_statement 提取到代码块，请根据问题描述自行编写 repro.py")}
   运行确认 bug 存在。

STEP 4 — 分析根因：
   定位问题代码，理解为什么出错。

STEP 5 — 做最小化修复：
   只改源码，DO NOT modify test files，DO NOT add new files。

STEP 6 — 验证修复：
   重跑 repro.py，然后跑 fail_to_pass 中的测试：
{test_commands}

STEP 7 — 回归检查：
   跑相关测试目录的子集，确认没有引入回归。
   提示：有 {task.p2p_count} 条回归测试需要保持通过。

STEP 8 — 输出 diff：
   git diff

## 约束条件
- DO NOT modify test files
- DO NOT add new files
- DO NOT run git commit / git add
- 只改 {source_dir}/ 目录下的源码
- 不修改 ChangeLog、version 文件

## 验证标准
- F2P 测试（{task.f2p_count} 条）必须全部通过
- P2P 测试（{task.p2p_count} 条）必须全部通过
- 输出格式：unified diff（git diff）
"""


# ---------------------------------------------------------------------------
# 可选：标准 SWE-bench jsonl 行（12 字段，可直接喂给 harness）
# ---------------------------------------------------------------------------
def render_jsonl(task: TaskInstance) -> dict:
    """渲染标准 SWE-bench jsonl 行（12 字段，字段名与 swe-bench-lite.jsonl 一致）。"""
    return {
        "instance_id": task.instance_id,
        "repo": task.repo,
        "base_commit": task.base_commit,
        "patch": task.gold_patch,
        "test_patch": task.test_patch,
        "problem_statement": task.problem_statement,
        "hints_text": task.hints_text,
        "created_at": task.created_at,
        "version": task.version,
        "FAIL_TO_PASS": task.fail_to_pass,
        "PASS_TO_PASS": task.pass_to_pass,
        "environment_setup_commit": task.environment_setup_commit,
    }


def dumps_jsonl(task: TaskInstance) -> str:
    """渲染为单行 JSON 字符串（任务 jsonl 文件的一行）。"""
    return json.dumps(render_jsonl(task), ensure_ascii=False)
