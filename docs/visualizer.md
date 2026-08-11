# 流程可视化教学模块（`swebench_exp_lite.visualizer`）

> 面向学生与课堂演示：**跑通实验 ≠ 理解实验**。本模块把「出题 → 解题 → 打分」
> 六大阶段的可视化渲染成一个自包含 HTML 页面，让学生直观看到每一步在干什么、
> 干到哪了、产物长什么样。

## 这是什么

学生跑完 `swebench-exp-lite run --instance X` 后，再跑一条 `viz` 命令就能生成
一份可在浏览器双击打开的 HTML 页面：

- 顶部：resolved 徽章 + run_id/model/adapter/F2P/P2P 元信息
- 流水线示意：6 节点横排（出题 / 环境准备 / Agent 作答 / 补丁规范化 / 评分 / 记录），
  按「出题→解题→打分」三段着色（蓝/紫/橙）
- 6 张可折叠阶段卡片：每张含「做什么 / 为什么需要 / 输入输出 / 本次实测 / 产物预览」
- 阶段耗时时间线：相对耗时比例，最长段标「瓶颈」（典型 S6_score > 99%）
- 教学术语速查：F2P / P2P / gold patch / worktree / harness / replay-agent 等 10 条
- 内联 `<abbr>` tooltip：阶段说明中首次出现的术语自动包裹，下划线 + 悬浮提示
- 产物文件链接：「产物路径」栏中的每个产物都可点击（`file://` 链接，✓/✘ 标记是否存在）

## 用法

```bash
# 先跑一次完整 run（生成产物）
./run_demo.sh

# 再生成可视化页面（默认输出 output/<iid>/flow.html）
python -m swebench_exp_lite viz --instance pylint-dev__pylint-7080

# 用浏览器打开
open output/pylint-dev__pylint-7080/flow.html     # macOS
xdg-open output/pylint-dev__pylint-7080/flow.html # Linux
explorer output\pylint-dev__pylint-7080\flow.html # Windows

# 或一步到位（生成后自动打开）
python -m swebench_exp_lite viz --instance pylint-dev__pylint-7080 --open
```

## 子命令参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--instance` | （必填） | 与 `run` 一致，如 `pylint-dev__pylint-7080` |
| `-o / --output` | `output/<iid>/flow.html` | HTML 输出路径 |
| `--task-dir` | `output/<iid>/` | 覆盖产物目录（用于测试 / 归档） |
| `--open` | False | 生成后用 `webbrowser.open()` 打开 |

## 键盘快捷键（在 flow.html 中）

| 键 | 行为 |
|---|---|
| `1` `2` `3` `4` `5` `6` | 切换对应阶段卡片（S1→S7）展开 |
| `e` | 全部展开 |
| `c` | 全部折叠 |
| 点击流水线节点 | 滚动到对应阶段卡片并展开 |
| 点击术语（带下划线）| 浏览器原生 tooltip 弹出（无需 JS） |
| 点击产物路径 | 用 `file://` 链接打开对应文件 |

## 设计决策

### 1. 自包含 HTML（非 Web 服务）

| 维度 | 自包含 HTML | Flask 服务 | React SPA |
|---|---|---|---|
| 依赖 | 0 | +Flask | +Node + React |
| 部署 | 双击 / file:// | 起服务端口 | 构建 + 服务 |
| 离线 | 天然 | 否 | 否 |
| 分享 | 单文件可邮件 | 仅本机 | 仅本机 |
| 与项目气质 | 匹配（极简冻结） | 增加运行时 | 严重超载 |

**结论**：用 Python f-string + 内嵌 CSS + 原生 JS，生成单一 `.html` 文件，
所有数据 inline 渲染，零外部依赖。

### 2. 只读不写

与既有管线完全解耦，**只读 `output/<iid>/` 既有产物**：

- `manifest.json`：六阶段状态 / 起止时间戳 / 产物路径
- `result.json`：resolved / resolved_pct / F2P / P2P / stage_timings
- `ca-issue.json` / `ca-task-prompt.md` / `review.md` / `task.jsonl`（S1 产物）
- `image.json`（S2 产物）
- `agent/<iid>.pred` / `.traj`（S4 产物）
- `patch/model.patch` / `changed-files.txt` / `diff-stat.txt` / `prediction.jsonl`（S5 产物）
- `eval/report.json`（S6 产物）

不修改任何 manifest / result / 产物路径结构。

### 3. 容忍缺失

任一阶段产物缺失（部分跑通 / 中途失败 / 手动跑），UI 独立显示「未运行」徽标，不崩。

```bash
# 测试场景：手动造一个部分产物的 manifest.json
python -c "
from swebench_exp_lite.visualizer import load_all, write
flow = load_all('/tmp/partial-task-output/partial-test-iid')
write(flow, '/tmp/partial-task-output/partial-test-iid/flow.html')
"
```

## 文件结构

```
swebench_exp_lite/visualizer/
├── __init__.py        # 17 行  子包入口
├── data_loader.py     # 311 行  FlowData/StageData 契约 + 读 manifest/result/产物
├── stage_guides.py    # 175 行  六阶段中文教学文案（唯一来源）+ 术语字典
└── renderer.py        # 680 行  HTML/CSS/JS 渲染器（含内嵌 CSS、原文 abbr 包裹、产物 file:// 链接）
```

## 教学作者如何修订文案

只需编辑 `swebench_exp_lite/visualizer/stage_guides.py`：

- `GUIDES[stage_name]["what"]`：白话说明（做什么）
- `GUIDES[stage_name]["why"]`：教学意义（为什么需要）
- `GUIDES[stage_name]["inputs"]` / `["outputs"]`：数据契约
- `TERMS[term]`：术语解释（自动用于底部速查 + 内联 `<abbr>` tooltip）

修改后无需改渲染器，下次跑 `viz` 即生效。

## 跨平台

`viz` 子命令仅用 Python 标准库（`html` / `json` / `pathlib` / `datetime` /
`webbrowser`），与 macOS / Windows / Ubuntu 平台无关。已验证：

- macOS：`./run_demo.sh` + `python -m swebench_exp_lite viz --instance X` + `open ...`
- Linux / WSL：`./run_demo.sh` + `viz` + `xdg-open ...`
- Windows（PowerShell）：`pwsh scripts/windows/run-demo.ps1` + `viz` + `explorer ...`

## 不做什么（首版边界）

- ❌ 不监听 pipeline 实时进度（那是「实时联动 GUI」，超出首版范围）
- ❌ 不做多用户协同（学生各自跑各自的实验，看各自的页面）
- ❌ 不做 `--all` 批量聚合（留接口：未来 `viz --all` 起聚合页）
- ❌ 不做 `--serve` 本地 HTTP 服务（留接口：未来产物太多装不下时上服务）
- ❌ 不做 `--diff <iid1> <iid2>`（留接口：未来对比两次跑）

需要这些能力时改 `cli.py` 的 `viz` subparser 加新参数即可，渲染器接口已经预留。