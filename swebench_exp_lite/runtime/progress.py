"""progress：Agent 作答过程结构化进度观测器（方案 B）。

设计动机：
- S4 作答期间只有哑日志（kimi-run.log / qwen-run.log），用户无法回答
  "进行到哪一步了、有没有卡住、碰到了什么问题"；
- 本模块 tail 作答运行日志，按八阶段解题模型（S1–S7，见 wiki/18）推断
  当前阶段，检测已知弯路信号，把结构化状态原子写入 progress.json。

品牌中立：只依赖"纯文本运行日志"这一事实，不绑定 Kimi/Qwen 任何品牌，
日志文件名由 resolve_log_paths() 自动探测（kimi-run.log / qwen-run.log /
*-run.log）。零外部依赖（仅标准库）。

核心概念：
- STAGES:        七阶段定义（S1理解→S2探索→S3复现→S4根因→S5修复→S6验证→S7交付）
- ProgressState: 增量解析器，feed(chunk) 吃日志文本，维护阶段/弯路/最近动作
- ProgressWatcher: 后台轮询线程，tail 日志文件并原子写 progress.json
- summarize():   把状态字典压成一行人类可读摘要（控制台/看板共用）

CLI 用法（cwd=tools/）：
    python -m swebench_exp_lite.runtime.progress <task_dir>            # 打快照
    python -m swebench_exp_lite.runtime.progress <task_dir> --watch    # 持续观察
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# 阶段定义（对齐 wiki/18 八阶段模型中的执行阶段 S1–S7；S0 元决策在 prompt
# 构造层完成，不出现在运行日志里）
# ---------------------------------------------------------------------------

STAGES: list[dict] = [
    {"id": "S0", "name": "启动中", "index": 0},
    {"id": "S1", "name": "理解任务", "index": 1},
    {"id": "S2", "name": "探索代码", "index": 2},
    {"id": "S3", "name": "复现问题", "index": 3},
    {"id": "S4", "name": "根因定位", "index": 4},
    {"id": "S5", "name": "最小修复", "index": 5},
    {"id": "S6", "name": "验证修复", "index": 6},
    {"id": "S7", "name": "交付结果", "index": 7},
]
STAGE_BY_ID = {s["id"]: s for s in STAGES}

# 阶段信号规则（基于 trajectories/ 下 5 个真实任务日志回放校准）：
# 分两类通道，避免提示词步骤复述（STEP 列表）与规划性自言自语污染阶段判断：
# - NARRATIVE 信号：只匹配 Agent 自己的叙述行（行首 •）；
# - OUTPUT 信号：只匹配短行（命令输出/命令句），排除 pip 安装噪声。
# strong=True 可把阶段置为任意方向（含 S6→S4 回退迭代）；
# strong=False 只允许向前推进。
_NARRATIVE_SIGNALS: list[tuple[str, bool, "re.Pattern"]] = [
    # S1 理解任务（kimi：开场白）
    ("S1", True, re.compile(r"solve this (swe-bench|swe_bench)", re.I)),
    # S2 探索代码
    ("S2", True, re.compile(r"explor", re.I)),
    ("S2", False, re.compile(r"(repo|repository) structure", re.I)),
    # S3 复现问题（strong=False：验证期提及 repro 不应把阶段从 S6 拽回 S3，
    # 真正的回退迭代由 S4 根因重定位强信号表达）
    ("S3", False, re.compile(r"\brepro", re.I)),
    ("S3", False, re.compile(r"confirm(ing|ed)? the (bug|issue|problem)", re.I)),
    ("S3", True, re.compile(r"bug (reproduced|confirmed)", re.I)),
    # S4 根因定位
    ("S4", True, re.compile(r"root cause", re.I)),
    ("S4", True, re.compile(r"the (bug|issue|problem) is (in|that|at|:)", re.I)),
    # S5 最小修复（只认"动手修"叙述；"the fix should"属规划设计，不算）
    ("S5", True, re.compile(r"(implement|apply|made|making|make|wrote|writing) (the |a |my )?(minimal )?fix", re.I)),
    ("S5", True, re.compile(r"fix (it|this|the (bug|issue|code))", re.I)),
    # qwen 风格："modify/update/change <文件>"、"edit <源码文件>"（动词+文件对象）
    ("S5", True, re.compile(r"\b(modify|modifying|update|updating|change|changing|patch)\S* (the |a |my )?[\w/.-]+\.(py|js|ts|go|java|rs|rb|c|cpp|h|md|yml|yaml|toml|cfg|ini|json)\b", re.I)),
    # S6 验证修复（strong=False：避免开局技能列表里的
    # "verification-before-completion" 提及把阶段拉到 S6）
    ("S6", False, re.compile(r"\bverif", re.I)),
    ("S6", False, re.compile(r"run (the |my )?(tests?|test suite|reproducer)", re.I)),
    ("S6", False, re.compile(r"after (the |my )?fix", re.I)),
    # S7 交付结果
    ("S7", True, re.compile(r"final (answer|diff|patch|summary)", re.I)),
    ("S7", True, re.compile(r"to resume this session", re.I)),
]
_OUTPUT_SIGNALS: list[tuple[str, bool, "re.Pattern"]] = [
    # S6 验证修复（测试结果/pytest 命令行）
    ("S6", True, re.compile(r"\d+ (passed|failed)", re.I)),
    ("S6", True, re.compile(r"^\$?\s*(python[\d.]*|pytest|uv run|tox) .*pytest", re.I)),
    # S7 交付结果
    ("S7", True, re.compile(r"^\$?\s*git diff", re.I)),
    # 注：曾有裸 "model_patch" 信号，已移除——Agent 读取 baseline/
    # prediction.jsonl 等历史产物时文件内容同样包含该字段，会把阶段从
    # S2 误拽到 S7（qwen-stream 回放实测）。S7 由 git diff / result 事件 /
    # "final summary" 等更具体的信号覆盖，移除后 kimi 5 条基线零漂移。
]

# 弯路/问题信号（对齐已识别的 5 类常见弯路 + 网络/卡死类）。
# category 用于聚合计数；repeat_threshold 达到后在摘要中升级为"反复"告警。
DETOUR_SIGNALS: list[dict] = [
    {"category": "cmd_not_found", "label": "命令不存在",
     "pattern": re.compile(r"command not found", re.I)},
    {"category": "missing_module", "label": "依赖缺失",
     "pattern": re.compile(r"(ModuleNotFoundError|No module named)", re.I)},
    {"category": "env_managed", "label": "环境受限(PEP668)",
     "pattern": re.compile(r"externally[- ]managed[- ]environment", re.I)},
    {"category": "test_failed", "label": "测试失败",
     "pattern": re.compile(r"(=\s*\d+\s+failed|^FAILED\s)", re.I | re.M)},
    {"category": "git_error", "label": "git错误",
     "pattern": re.compile(r"fatal: (unable to read|not a git repository|bad object|could not read)", re.I)},
    {"category": "api_error", "label": "API/网络异常",
     "pattern": re.compile(r"(rate.?limit|\b429\b|\b503\b|connection (reset|refused|timed? ?out))", re.I)},
]

# traceback 单独处理：S3 复现阶段出现 traceback 是预期行为（复现成功证据），
# 只有进入 S5 及以后再出现才算问题信号。
_TRACEBACK_RE = re.compile(r"Traceback \(most recent call last\)")

# 2 空格缩进延续行中伪装成叙述的常见命令输出噪声（traceback 帧/pip 输出等）。
# 叙述通道 = • 行 + 2 空格缩进延续行（排除以下噪声）。
_NARRATIVE_NOISE_RE = re.compile(
    r"^\s*(File |Collecting |Downloading |Using cached |Requirement |"
    r"Installing collected|Successfully installed|Defaulting to user|"
    r"WARNING: |Installing dependencies|╰─|│)")

# 运行日志探测顺序（品牌中立：kimi/qwen/通用 *-run.log）
_RUN_LOG_CANDIDATES = ("kimi-run.log", "qwen-stream.jsonl", "qwen-run.log",
                       "kimi-fast.log")

# 疑似卡死的日志静默阈值（秒）
DEFAULT_IDLE_WARN_SECONDS = 120

# 信号规则校准来源声明：
# - kimi-cli：叙述通道（• 行/2 空格延续行）基于 Kimi CLI 真实日志校准；
# - qwen-cli：stream-json 事件通道（thinking/tool_use/tool_result/result）
#   基于 Qwen Code CLI --output-format stream-json 真实作答日志校准。
# 输出通道（pytest 结果/git diff）是品牌无关的，即使叙述通道全部 miss，
# S6/S7 仍可被识别，阶段推断不会完全瘫痪。
CALIBRATED_FOR = ["kimi-cli", "qwen-cli"]

# 自举窗口：开局日志是技能列表/提示词复述等元讨论，在 S1 信号触发前
# （或超过该行数前）不接受其它阶段信号，避免被拉到中后段阶段。
_BOOTSTRAP_MAX_LINES = 25


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# 路径解析
# ---------------------------------------------------------------------------

def resolve_log_paths(task_dir: Path) -> tuple[Optional[Path], Path]:
    """解析任务目录下的运行日志与 progress.json 路径。

    布局约定（orchestrator）：task_dir/agent/<run>.log + task_dir/agent/progress.json。
    agent 模块内部还有一层 agent/ 子目录（task_dir/agent/agent/<run>.log），
    故对候选名做 rglob；兼容 trajectories/ 历史布局（日志在 task_dir 根）。

    Returns:
        (run_log or None, progress_json_path)
        run_log 在作答尚未启动日志时可能为 None（watcher 会持续重探测）。
    """
    task_dir = Path(task_dir)
    agent_dir = task_dir / "agent"
    search_dirs = [agent_dir, task_dir]
    for d in search_dirs:
        if not d.is_dir():
            continue
        for name in _RUN_LOG_CANDIDATES:
            # 直接子级优先，其次递归查找（agent/agent/ 嵌套布局）
            p = d / name
            if p.exists():
                return p, d / "progress.json"
            hits = sorted(d.rglob(name))
            if hits:
                return hits[0], d / "progress.json"
        # 通用回退：任意 *-run.log（同样递归）
        hits = sorted(d.rglob("*-run.log"))
        if hits:
            return hits[0], d / "progress.json"
    # 尚未找到日志：progress.json 默认落 agent/ 下
    return None, agent_dir / "progress.json"


# ---------------------------------------------------------------------------
# 增量解析状态机
# ---------------------------------------------------------------------------

class ProgressState:
    """运行日志增量解析器。

    用法：
        state = ProgressState(instance_id="...")
        state.feed(chunk_text)      # 可多次增量喂入
        state.to_dict()             # 序列化（写 progress.json）
    """

    def __init__(self, instance_id: str = "", log_file: str = ""):
        self.instance_id = instance_id
        self.log_file = log_file
        self.started_at = time.time()
        self.lines_processed = 0
        self.finished = False
        self.current_stage = "S0"
        self.stage_history: list[dict] = []
        self.warnings: dict[str, dict] = {}
        self.last_action: dict = {}
        self.resets = 0  # 日志截断重置次数（agent 重试场景，Step 3 前叫 run_with_retry）
        self._pending_line = ""  # 跨 chunk 的不完整行
        self._in_diff_block = False
        self._stream_mode: Optional[bool] = None  # None=自动探测（qwen stream-json）
        self._first_thinking_done = False  # 首个 thinking 已注入 S1 锚点
        # R4：watcher 线程写（feed）与主线程读（summary_line/to_dict）并发，
        # 无锁时 to_dict 迭代 warnings dict 可能撞上 _record_warning 加键
        # 招 RuntimeError（dictionary changed size during iteration）
        self._lock = threading.RLock()

    # -- 公共 API ----------------------------------------------------------

    def feed(self, chunk: str) -> None:
        """增量喂入日志文本（任意切分方式，内部按行重组）。"""
        with self._lock:
            text = self._pending_line + chunk
            lines = text.split("\n")
            self._pending_line = lines.pop()  # 最后一段可能不完整，留到下次
            for line in lines:
                self._feed_line(line)

    def flush(self) -> None:
        """日志结束（进程退出）时把残留行也处理掉。"""
        with self._lock:
            if self._pending_line:
                self._feed_line(self._pending_line)
                self._pending_line = ""

    def reset(self, reason: str = "") -> None:
        """重置解析状态（日志被截断重写时由 watcher 调用）。

        保留 instance_id / log_file / started_at（总耗时应覆盖整个运行含重试）。
        """
        with self._lock:
            self.lines_processed = 0
            self.finished = False
            self.current_stage = "S0"
            self.stage_history = []
            self.warnings = {}
            self.last_action = {}
            self._pending_line = ""
            self._in_diff_block = False
            self._stream_mode = None
            self._first_thinking_done = False
            self.resets += 1

    def to_dict(self) -> dict:
        with self._lock:
            cur = STAGE_BY_ID.get(self.current_stage, STAGES[0])
            elapsed = time.time() - self.started_at
            idle = self._idle_seconds()
            warnings = sorted(
                (dict(w) for w in self.warnings.values()), key=lambda w: -w["count"])
            d = {
                "schema_version": 1,
                "instance_id": self.instance_id,
                "log_file": self.log_file,
                "calibrated_for": CALIBRATED_FOR,
                "updated_at": _now_iso(),
                "elapsed_seconds": round(elapsed, 1),
                "idle_seconds": round(idle, 1),
                "lines_processed": self.lines_processed,
                "resets": self.resets,
                "finished": self.finished,
                "stage": cur,
                "stage_history": list(self.stage_history[-20:]),
                "last_action": dict(self.last_action),
                "warnings": warnings,
            }
        # summary 统一从序列化 dict 组装（单路径，消除双路漂移）
        d["summary"] = summarize(d)
        return d

    def summary_line(self) -> str:
        return self.to_dict()["summary"]

    # -- 内部 --------------------------------------------------------------

    def _idle_seconds(self) -> float:
        """日志文件静默时长（基于 mtime）；文件不存在返回 0。"""
        if not self.log_file:
            return 0.0
        try:
            mtime = Path(self.log_file).stat().st_mtime
        except OSError:
            return 0.0
        return max(0.0, time.time() - mtime)

    def _feed_line(self, line: str) -> None:
        self.lines_processed += 1
        stripped = line.strip()

        # Qwen CLI stream-json 事件通道（--output-format stream-json 的 NDJSON）。
        # 自动探测：日志首行可能是 stderr 警告，故不锁死 False，
        # 而是见到首个带 "type" 键的 JSON 行才锁定流模式。
        if self._stream_mode is None and stripped.startswith("{") and '"type"' in stripped[:80]:
            self._stream_mode = True
        if self._stream_mode:
            if stripped.startswith("{"):
                try:
                    self._feed_qwen_event(json.loads(stripped))
                except (json.JSONDecodeError, TypeError):
                    pass  # 残缺/非 JSON 行静默跳过
            return

        # diff 代码块内部不做阶段判断（diff 行含大量误导词）
        if stripped.startswith("```diff"):
            self._in_diff_block = True
        if self._in_diff_block:
            if stripped == "```":
                self._in_diff_block = False
            return

        if not stripped:
            return

        # 结束标记（Kimi CLI 会话结束语）
        if "to resume this session" in stripped.lower():
            self._set_stage("S7", source_line=self.lines_processed, reason="session-end-marker")
            self.finished = True

        # 阶段信号：叙述通道 = Agent 自己的话（• 行 + 2 空格缩进延续行，
        # 排除 traceback 帧/pip 输出等伪装噪声）；输出通道只认短行。
        # 两通道分离是为排除提示词 STEP 复述与规划性文本的阶段污染。
        is_narrative = stripped.startswith("•") or (
            line.startswith("  ") and not line.startswith("    ")
            and not _NARRATIVE_NOISE_RE.match(line))
        signals = _NARRATIVE_SIGNALS if is_narrative else _OUTPUT_SIGNALS
        if not is_narrative and len(stripped) > 300:
            signals = ()  # 长输出块（pip 安装/大段 traceback）不做阶段判断
        for stage_id, strong, pat in signals:
            if pat.search(line):
                self._maybe_advance(stage_id, strong=strong)
                break  # 每行只取第一个命中的阶段信号，避免互相打架

        # 弯路信号
        for sig in DETOUR_SIGNALS:
            if sig["pattern"].search(line):
                self._record_warning(sig["category"], sig["label"], stripped)
        # traceback：仅 S5 及以后才算问题（S3 复现期的 traceback 是预期证据）
        if _TRACEBACK_RE.search(line) and self._stage_index() >= STAGE_BY_ID["S5"]["index"]:
            self._record_warning("post_fix_traceback", "修复后仍报错", stripped)

        # 最近动作：优先 Agent 叙述行（• 开头），否则取短行；
        # 排除 session 结束语等无信息量行
        if "to resume this session" in stripped.lower():
            pass
        elif stripped.startswith("•") or (len(stripped) < 160 and not stripped.startswith(" ")):
            self.last_action = {
                "line": self.lines_processed,
                "ts": _now_iso(),
                "text": stripped[:150],
            }

    # -- Qwen stream-json 事件通道 -------------------------------------------

    def _feed_qwen_event(self, ev: dict) -> None:
        """解析 Qwen Code CLI stream-json 事件（thinking/tool_use/tool_result/result）。

        与文本通道的对应关系：
        - thinking      ≈ Agent 叙述（走 NARRATIVE 信号）
        - tool_use      ≈ 动作记录（shell/edit/read 工具名 + 首参数 → last_action）
        - tool_result   ≈ 命令输出（走 OUTPUT 信号 + 弯路检测；is_error 记告警）
        - result        ≈ 会话结束（置 S7 + finished）
        """
        etype = ev.get("type")
        msg = ev.get("message") or {}
        contents = msg.get("content") if isinstance(msg, dict) else None

        if etype == "assistant" and isinstance(contents, list):
            for c in contents:
                if not isinstance(c, dict):
                    continue
                ctype = c.get("type")
                if ctype == "thinking":
                    text = (c.get("thinking") or "").strip()
                    if text:
                        # 首个 thinking = Agent 开始思考 = 理解阶段锚点；
                        # 流模式事件密度高于文本行，不依赖行计数自举门
                        if not self._first_thinking_done:
                            self._first_thinking_done = True
                            if self._stage_index() == 0:
                                self._set_stage("S1", source_line=self.lines_processed,
                                                reason="qwen-first-thinking")
                        self._route_signals(text, narrative=True)
                        self.last_action = {"line": self.lines_processed,
                                            "ts": _now_iso(), "text": text[:150]}
                elif ctype == "text":
                    text = (c.get("text") or "").strip()
                    if not text:
                        continue
                    # 最终回答含完整 diff → 交付信号（文本通道中 diff 块被
                    # 跳过，事件通道需在此显式识别）
                    if "diff --git " in text:
                        self._set_stage("S7", source_line=self.lines_processed,
                                        reason="qwen-final-diff")
                    else:
                        self._route_signals(text, narrative=True)
                    self.last_action = {"line": self.lines_processed,
                                        "ts": _now_iso(), "text": text[:150]}
                elif ctype == "tool_use":
                    name = c.get("name", "")
                    inp = c.get("input") if isinstance(c.get("input"), dict) else {}
                    head = inp.get("command") or inp.get("file_path") \
                        or inp.get("path") or inp.get("pattern") or ""
                    desc = f"{name}: {head}"[:150]
                    self.last_action = {"line": self.lines_processed,
                                        "ts": _now_iso(), "text": desc}

        elif etype == "user" and isinstance(contents, list):
            for c in contents:
                if not isinstance(c, dict) or c.get("type") != "tool_result":
                    continue
                if c.get("is_error"):
                    self._record_warning("tool_error", "工具调用失败",
                                         self._flatten_result(c)[:120])
                text = self._flatten_result(c)
                if not text:
                    continue
                # 输出信号逐行跑：tool_result 常超 300 字被整体跳过，
                # 而 pytest 结果行（"N passed"）是短行，逐行扫描不丢信号
                for tl in text.split("\n"):
                    tls = tl.strip()
                    if tls and len(tls) <= 300:
                        for stage_id, strong, pat in _OUTPUT_SIGNALS:
                            if pat.search(tl):
                                self._maybe_advance(stage_id, strong=strong)
                                break
                # 弯路检测：逐行跑，与文本通道同一套规则
                for tl in text.split("\n"):
                    for sig in DETOUR_SIGNALS:
                        if sig["pattern"].search(tl):
                            self._record_warning(sig["category"], sig["label"],
                                                 tl.strip()[:120])
                    if _TRACEBACK_RE.search(tl) and \
                            self._stage_index() >= STAGE_BY_ID["S5"]["index"]:
                        self._record_warning("post_fix_traceback", "修复后仍报错",
                                             tl.strip()[:120])

        elif etype == "result":
            self._set_stage("S7", source_line=self.lines_processed,
                            reason="qwen-result-event")
            self.finished = True
            text = (ev.get("result") or "").strip()
            if text:
                self._route_signals(text, narrative=False)

    def _route_signals(self, text: str, *, narrative: bool) -> None:
        """对事件文本跑阶段信号（复用文本通道的 NARRATIVE/OUTPUT 规则）。"""
        signals = _NARRATIVE_SIGNALS if narrative else _OUTPUT_SIGNALS
        if not narrative and len(text) > 300:
            return  # 长输出块不做阶段判断（与文本通道一致）
        for stage_id, strong, pat in signals:
            if pat.search(text):
                self._maybe_advance(stage_id, strong=strong)
                break

    @staticmethod
    def _flatten_result(c: dict) -> str:
        """tool_result.content 可能是 str 或 list[{type:text,...}]，统一压平。"""
        content = c.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(
                x.get("text", "") for x in content
                if isinstance(x, dict) and x.get("type") == "text")
        return ""

    def _stage_index(self, stage_id: Optional[str] = None) -> int:
        return STAGE_BY_ID.get(stage_id or self.current_stage, STAGES[0])["index"]

    def _maybe_advance(self, stage_id: str, *, strong: bool) -> None:
        # 自举门：S1 触发前只认 S1（开局元讨论噪声隔离）；
        # 超过 _BOOTSTRAP_MAX_LINES 仍未触发则注入隐式 S1 锚点后放行
        # （兼容无 S1 信号的日志，保证阶段轨迹从 S1 起步）
        if self._stage_index() == 0 and stage_id != "S1":
            if self.lines_processed < _BOOTSTRAP_MAX_LINES:
                return
            self._set_stage("S1", source_line=self.lines_processed,
                            reason="implicit-bootstrap")
        new_idx = self._stage_index(stage_id)
        cur_idx = self._stage_index()
        if stage_id == self.current_stage:
            return
        # 弱信号只允许向前；强信号允许回退（S6 验证失败回退 S4 的迭代机制）
        if not strong and new_idx < cur_idx:
            return
        self._set_stage(stage_id, source_line=self.lines_processed,
                        reason="fallback-iteration" if new_idx < cur_idx else "forward")

    def _set_stage(self, stage_id: str, *, source_line: int, reason: str) -> None:
        if stage_id == self.current_stage and reason != "fallback-iteration":
            return
        self.current_stage = stage_id
        self.stage_history.append({
            "stage": stage_id,
            "ts": _now_iso(),
            "line": source_line,
            "reason": reason,
        })

    def _record_warning(self, category: str, label: str, sample: str) -> None:
        w = self.warnings.get(category)
        if w is None:
            self.warnings[category] = {
                "category": category,
                "label": label,
                "count": 1,
                "first_line": self.lines_processed,
                "sample": sample[:120],
            }
        else:
            w["count"] += 1
            w["sample"] = sample[:120]  # 保留最近一次样本


# ---------------------------------------------------------------------------
# 摘要
# ---------------------------------------------------------------------------

def _fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    return f"{seconds // 60}m{seconds % 60:02d}s"


def summarize(state_dict: Optional[dict] = None) -> str:
    """把进度状态（to_dict() 产物）压成一行人类可读摘要（单路径）。

    形如：[S3复现问题] 12m05s | ⚠ 依赖缺失x2 命令不存在x1 | 最近：Now run reproducer.
    """
    if not state_dict:
        return "[?] 无进度数据"
    stage = state_dict.get("stage", STAGES[0])
    elapsed = _fmt_duration(state_dict.get("elapsed_seconds", 0))
    warns = {w["category"]: w for w in state_dict.get("warnings", [])}
    last = (state_dict.get("last_action") or {}).get("text", "")
    finished = state_dict.get("finished", False)
    idle = state_dict.get("idle_seconds", 0)

    parts = [f"[{stage['id']}{stage['name']}] {elapsed}"]
    if finished:
        parts.append("✅已完成")
    if warns:
        seg = " ".join(f"{w['label']}x{w['count']}" for w in warns.values())
        parts.append(f"⚠ {seg}")
    if idle > DEFAULT_IDLE_WARN_SECONDS and not finished:
        parts.append(f"⏸ 日志静默{_fmt_duration(idle)}（疑似卡住）")
    if last:
        parts.append(f"最近：{last[:60]}")
    return " | ".join(parts)


# ---------------------------------------------------------------------------
# 后台 watcher
# ---------------------------------------------------------------------------

class ProgressWatcher:
    """tail 运行日志并原子写 progress.json 的后台线程。

    用法：
        watcher = ProgressWatcher(task_dir, instance_id="...")
        watcher.start()          # 守护线程，主进程退出自动结束
        ...
        line = watcher.summary_line()   # 随时取一行摘要
        watcher.stop()           # 停线程并写最终快照
    """

    def __init__(self, task_dir: Path, instance_id: str = "",
                 poll_interval: float = 2.0):
        self.task_dir = Path(task_dir)
        self.instance_id = instance_id
        self.poll_interval = poll_interval
        self.state = ProgressState(instance_id=instance_id)
        self._stop_evt = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._log_path: Optional[Path] = None
        self._progress_path: Optional[Path] = None
        self._fh = None
        self._fh_path: Optional[Path] = None

    # -- 生命周期 ----------------------------------------------------------

    def start(self) -> "ProgressWatcher":
        self._thread = threading.Thread(target=self._loop, name="progress-watcher", daemon=True)
        self._thread.start()
        return self

    def stop(self, write_final: bool = True) -> None:
        self._stop_evt.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        if self._fh is not None:
            try:
                self._fh.close()
            except OSError:
                pass
        if write_final:
            self.state.flush()
            self._write_progress()

    # -- 查询 --------------------------------------------------------------

    def progress_path(self) -> Optional[Path]:
        return self._progress_path

    def summary_line(self) -> str:
        try:
            return self.state.summary_line()
        except Exception:  # noqa: BLE001 — 观测器永远不反噬主流程
            return "[?] 进度观测异常"

    def snapshot(self) -> dict:
        return self.state.to_dict()

    # -- 内部 --------------------------------------------------------------

    def _loop(self) -> None:
        while not self._stop_evt.is_set():
            try:
                self._poll_once()
            except Exception:  # noqa: BLE001 — 观测器任何异常都不允许反噬作答
                pass
            self._stop_evt.wait(self.poll_interval)

    def _poll_once(self) -> None:
        # 日志路径探测（作答启动初期日志可能还没创建）
        if self._log_path is None or not self._log_path.exists():
            found, prog = resolve_log_paths(self.task_dir)
            if found is not None:
                self._log_path = found
                self._progress_path = prog
                self.state.log_file = str(found)
        if self._log_path is None:
            return

        # 日志可能被重建（重试），检测 inode/大小回退则重开
        if self._fh is None or self._fh_path != self._log_path:
            if self._fh is not None:
                self._fh.close()
            self._fh = open(self._log_path, "r", encoding="utf-8", errors="replace")
            self._fh_path = self._log_path

        # R3：同路径截断检测（agent 重试时以 "w" 模式重开日志，Step 3 前叫 run_with_retry）。
        # 文件变小 → seek(0) 重读并重置解析状态，避免旧 attempt 的阶段/告警
        # 叠加在新日志上。
        try:
            if os.fstat(self._fh.fileno()).st_size < self._fh.tell():
                self._fh.seek(0)
                self.state.reset(reason="log-truncated")
        except OSError:
            pass

        chunk = self._fh.read()
        if chunk:
            self.state.feed(chunk)
            self._write_progress()

    def _write_progress(self) -> None:
        if self._progress_path is None:
            _, self._progress_path = resolve_log_paths(self.task_dir)
        try:
            self._progress_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._progress_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(self.state.to_dict(), ensure_ascii=False, indent=2),
                           encoding="utf-8")
            os.replace(tmp, self._progress_path)
        except OSError:
            pass  # 写盘失败静默跳过，下一轮再试


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_snapshot(task_dir: Path) -> int:
    log_path, prog_path = resolve_log_paths(task_dir)
    if log_path is None and not prog_path.exists():
        print(f"[progress] 未在 {task_dir} 找到运行日志或 progress.json")
        return 1
    if prog_path.exists():
        # 已有 watcher 落盘的快照，直接读
        data = json.loads(prog_path.read_text(encoding="utf-8"))
        print(data.get("summary", ""))
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    # 无快照（如事后分析历史目录）：离线全量回放
    state = ProgressState(instance_id=task_dir.name, log_file=str(log_path))
    state.feed(log_path.read_text(encoding="utf-8", errors="replace"))
    state.flush()
    d = state.to_dict()
    print(d.get("summary", ""))
    print(json.dumps(d, ensure_ascii=False, indent=2))
    return 0


def _watch_loop(task_dir: Path, interval: float) -> int:
    watcher = ProgressWatcher(task_dir).start()
    last = ""
    try:
        while True:
            line = watcher.summary_line()
            if line != last:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {line}", flush=True)
                last = line
            if watcher.state.finished:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        watcher.stop()
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="swebench_exp_lite.runtime.progress",
        description="Agent 作答进度观测器：阶段推断 + 弯路检测 + progress.json")
    p.add_argument("task_dir", help="任务目录（含 agent/kimi-run.log 的 experiments 任务目录或 trajectories 目录）")
    p.add_argument("--watch", action="store_true", help="持续观察并打印摘要变化")
    p.add_argument("--interval", type=float, default=5.0, help="--watch 模式的轮询间隔秒数")
    args = p.parse_args(argv)

    task_dir = Path(args.task_dir)
    if not task_dir.is_dir():
        print(f"[progress] 目录不存在：{task_dir}")
        return 2
    if args.watch:
        return _watch_loop(task_dir, args.interval)
    return _print_snapshot(task_dir)


if __name__ == "__main__":
    raise SystemExit(main())
