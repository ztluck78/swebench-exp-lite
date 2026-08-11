"""六阶段的中文教学文案（教学内容的唯一来源）。

每阶段含三块：
- phase：大段分组（出题/解题/打分）
- title / what / why：教学说明（白话 + 教学意义）
- inputs / outputs：数据契约（教学用，非代码契约）

教学作者只需修订本文件即可调整页面文案，不需要碰渲染器。

> 字数控制：单阶段文案 100-180 字白话，不引申到其他阶段。
"""
from __future__ import annotations

# 三段着色：与渲染器 CSS 类名约定（phase-issue / phase-solve / phase-grade）
PHASES = {
    "issue": {"label": "出题", "color": "#3b82f6", "description": "从题库准备一道可作答的题目"},
    "solve": {"label": "解题", "color": "#8b5cf6", "description": "让 Agent 在真实仓库里尝试修复"},
    "grade": {"label": "打分", "color": "#f59e0b", "description": "用官方评测镜像跑测试集判定结果"},
}

# 教学阶段到 phase 的映射（与 STAGES 顺序一致）
STAGE_PHASES = {
    "S1_build":   "issue",
    "S2_prepare": "solve",
    "S4_solve":   "solve",
    "S5_patch":   "solve",
    "S6_score":   "grade",
    "S7_record":  "grade",
}

# 教学阶段展示顺序与中文标签（流水线节点用）
STAGE_LABELS = {
    "S1_build":   "出题",
    "S2_prepare": "环境准备",
    "S4_solve":   "Agent 作答",
    "S5_patch":   "补丁规范化",
    "S6_score":   "评分",
    "S7_record":   "记录",
}

GUIDES: dict[str, dict] = {
    "S1_build": {
        "phase": "issue",
        "title": "S1 出题：从 LiteDB 渲染题面四件套",
        "what": (
            "从题库查询该实例的元数据（仓库、Issue 描述、F2P/P2P 测试列表、"
            "gold patch），渲染成 4 类文件：人工审阅版 Markdown（review.md）、"
            "Agent 输入数据 JSON（ca-issue.json）、Agent 任务指令 Markdown"
            "（ca-task-prompt.md，8 步完整版）、标准 SWE-bench jsonl 行（task.jsonl）。"
        ),
        "why": (
            "SWE-bench Lite 是 323 道真实 GitHub Issue 修复题；这一步把 DB 里的"
            "结构化数据变成可读的题面，是整个闭环的起点。ca- 前缀专门给 code agent "
            "看（含问题不含答案），review.md 是给人看的（含 gold patch 用于核对），"
            "两份严格隔离避免答案泄露。"
        ),
        "inputs": ["LiteDB 一次查询（db.eval_estimate + db.get）"],
        "outputs": ["review.md", "ca-issue.json", "ca-task-prompt.md", "task.jsonl"],
    },
    "S2_prepare": {
        "phase": "solve",
        "title": "S2 环境准备：评测镜像 + git worktree + venv 预装",
        "what": (
            "做三件互不依赖的幂等准备：1) docker image inspect 评测镜像，缺失则按 "
            "DB 记录的 pull 命令拉取（仍缺失则提示走 start.sh 的 OSS tar 降级）；"
            "2) 为 Agent 准备独立 git worktree（与主分支隔离，复用共享 mirror）；"
            "3) 在 worktree 内建 venv 并 pip install -e . + pytest（best-effort，"
            "失败不阻断）。replay-agent 跳过 2、3（无需真实仓库）。"
        ),
        "why": (
            "评测镜像决定了 S6 跑测试的环境（Python 版本、依赖、OS），必须和官方"
            "一致否则结果不可比；worktree 让 Agent 在不污染主分支的情况下作答；"
            "venv 预装节省后续 Agent 探索时间。三步都「幂等」，已就绪直接跳过，"
            "支持断点续跑。"
        ),
        "inputs": ["DB 记录的镜像名 + 拉取命令", "repo URL + base_commit"],
        "outputs": ["image.json（含 image/arch/digest/built_at）"],
    },
    "S4_solve": {
        "phase": "solve",
        "title": "S4 作答：调 runner 生成 model_patch",
        "what": (
            "通过 registry 解析出 runner，分两条路径：replay-agent 在进程内直跑"
            "（零依赖、<1s，重放 gold patch 闭环自检）；四品牌 runner（kimi/qwen/"
            "mimo/opencode）spawn 子进程跑 s4_worker，硬超时 SIGKILL 防止 CLI 挂起"
            "拖死主流程。runner 从 ca-issue.json 读问题，从 ca-task-prompt.md 读"
            "8 步指令，在 repo_dir 里修改代码，最终输出 .pred（含 model_patch 字段）。"
        ),
        "why": (
            "这是闭环中唯一与 LLM 交互的阶段（replay-agent 例外）。两条路径区分是"
            "为了让初学者能在零依赖环境下验证整条流水线（replay），同时为后续接入"
            "真实模型留好协议接口（品牌 runner）。子进程 + 超时 kill 是工程化的"
            "安全网，避免某个 CLI 异常挂起时整个 run 瘫痪。"
        ),
        "inputs": ["ca-issue.json", "ca-task-prompt.md", "repo_dir（worktree）"],
        "outputs": ["agent/<iid>/<iid>.pred（model_patch + exit_code）", "agent/<iid>/<iid>.traj"],
    },
    "S5_patch": {
        "phase": "solve",
        "title": "S5 补丁规范化：把 .pred 转成 prediction.jsonl",
        "what": (
            "从 .pred 取出 model_patch 字段，写成三处：agent/<iid>.patch（顶层副本）、"
            "patch/model.patch（教学解读用）、patch/changed-files.txt（受影响文件"
            "列表，正则提取 `+++ b/` 与 `diff --git` 两路并集）+ diff-stat.txt"
            "（files_changed/patch_bytes 摘要）。最后调 write_prediction_jsonl 生成"
            "harness 可消费的 prediction.jsonl（标准 SWE-bench 格式）。"
        ),
        "why": (
            "prediction.jsonl 是 S6 harness 的唯一输入，格式必须严格匹配官方协议；"
            "把 patch 同时落到 agent/ 与 patch/ 是为了让 Agent 自己的产物和教学"
            "解读产物分离——前者证明「Agent 做了啥」，后者方便学生直接 diff 阅读。"
            "空 patch 会被显式提示（harness 会判 unresolved）。"
        ),
        "inputs": ["agent/<iid>/<iid>.pred（来自 S4）"],
        "outputs": [
            "agent/<iid>.patch", "patch/model.patch",
            "patch/changed-files.txt", "patch/diff-stat.txt",
            "prediction.jsonl",
        ],
    },
    "S6_score": {
        "phase": "grade",
        "title": "S6 评分：在官方镜像里跑 harness 判定",
        "what": (
            "以仓根为 cwd spawn 子进程调 answer_evaluator.harness.run_evaluation，"
            "把 prediction.jsonl + dataset_name（本地 jsonl）+ namespace + cache_level "
            "+ timeout 传过去。harness 启动容器、apply patch、跑 FAIL_TO_PASS（修复"
            "后必须过）+ PASS_TO_PASS（修复前后都得过，防回归）两组测试，产出"
            "report.json（含 tests_status / resolved 字段）。跑完 _copy_report 把"
            "报告同步到 output/<iid>/eval/report.json。"
        ),
        "why": (
            "这是闭环中唯一「客观打分」的阶段——不再依赖任何 LLM，而是用真实测试"
            "集做硬判定。resolved = F2P 全过 ∧ P2P 全过（与 baseline 无关，"
            "lite 仓 S3 baseline 未实现）。这是 SWE-bench 评测的可信度基石："
            "对模型能力的衡量完全交给代码与测试，而非人评。"
        ),
        "inputs": ["prediction.jsonl", "评测镜像（来自 S2）", "本地 jsonl dataset"],
        "outputs": ["eval/report.json（含 F2P/P2P success/failure 列表）"],
    },
    "S7_record": {
        "phase": "grade",
        "title": "S7 记录：汇总结果写 result.json + 打印 %Resolved",
        "what": (
            "读 eval/report.json 取该 instance 的 tests_status 块，统计 F2P/P2P "
            "pass/fail 数量；从 manifest 算各阶段耗时（stage_timings）。汇总成一个"
            "扁平 dict：instance_id/run_id/model/adapter/resolved/resolved_pct/"
            "fail_to_pass/pass_to_pass/image/stages/stage_timings/generated_at，"
            "写到 output/<iid>/result.json。最后根据 resolved 字段打印 RESOLVED "
            "或 UNRESOLVED 终局。"
        ),
        "why": (
            "result.json 是给学生和后续脚本看的「最终成绩单」：6 个布尔 stage 状态"
            "让你知道哪步没跑过；stage_timings 让你看出耗时瓶颈（典型情况是 "
            "S6_score 占 99%）；resolved/resolved_pct 是直接可读的判定。lite 仓"
            "不回写 tasks.status、不入 experiments.db（spec 决策），保持精简。"
        ),
        "inputs": ["eval/report.json（来自 S6）", "manifest.json（stage_timings）"],
        "outputs": ["result.json（含 resolved / F2P / P2P / stage_timings）"],
    },
}

# 教学术语字典（用于页面 <abbr> 悬浮提示）
TERMS: dict[str, str] = {
    "F2P": "FAIL_TO_PASS：修复前失败、修复后必须通过的测试（修 bug 的核心证据）",
    "P2P": "PASS_TO_PASS：修复前后都必须通过的测试（防回归）",
    "gold patch": "官方维护的参考修复方案（评测集中已存在的正确答案）",
    "worktree": "git worktree：与主分支隔离的独立工作目录，Agent 在里面作答不污染主分支",
    "harness": "SWE-bench 官方评测框架，负责拉镜像、apply patch、跑测试、判 resolved",
    "replay-agent": "零依赖的回放 runner，直接复制 gold patch 用于验证流水线本身",
    "resolved": "F2P 全过 ∧ P2P 全过（与 baseline 无关）",
    "%Resolved": "通过题目占总题目的百分比，是 SWE-bench 排行榜的统一指标",
    "LiteDB": "本地 SQLite 题库（database/swe_bench.db），存 323 道题的结构化元信息",
    "OSS tar": "阿里云 OSS 上的 docker 镜像 tar 备份（start.sh 拉取降级方案）",
}