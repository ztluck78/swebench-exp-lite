"""opencode --format json 输出解析器。

opencode 1.18.15 的 NDJSON 事件流结构（实测 2026-08-09）：

    {"type":"step_start",  "timestamp":..., "sessionID":"ses_...", "part":{...}}
    {"type":"tool_use",    "part":{"type":"tool", "tool":"bash|edit|read|glob|...",
                                     "state":{"status","input","output","metadata":{...}}}}
    {"type":"text",        "part":{"type":"text", "text":"..."}}
    {"type":"step_finish", "part":{"type":"step-finish", "reason":"tool-calls|stop",
                                     "snapshot":"<git-blob-hash>",
                                     "tokens":{total,input,output,reasoning,cache:{write,read}},
                                     "cost":0}}
    {"type":"error",       "error":{"name":"UnknownError", "data":{"message":"..."}}}

关键差异（vs mimo）：
- 事件类型是 `tool_use`（mimo 是 `tool_call`）
- 有独立 `error` 事件（mimo 没有，靠 step_finish.reason 判定）
- `snapshot` 是 git 对象 blob hash（mimo 是 commit SHA）—— 不能直接用于 patch 提取
- patch 提取走 `git diff <base_commit>` 即可（opencode 不 auto-commit，PoC 验证）

成功判定：`step_finish.reason == "stop"` AND 无 `error` 事件。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class OpencodeJsonParseResult:
    """opencode --format json 输出解析结果。

    Attributes:
        success: opencode 是否成功完成（reason == "stop" 且无 error 事件）
        reason: 最后一个 step_finish 的 reason 字段
        has_error: 是否出现过 error 事件
        error_message: 第一个 error 事件的消息
        session_id: opencode session ID（"ses_..."）
        snapshot: 最后 step_finish 的 snapshot（git blob hash，仅供观测）
        tokens: token 统计 dict（含 cache.read/write）
        cost: 实际费用
        last_text: 最后一次 text 事件的文本
        events: 完整 NDJSON 事件流（jsonl 单行 dict）
        parse_errors: 解析失败的行数
    """
    success: bool = False
    reason: Optional[str] = None
    has_error: bool = False
    error_message: Optional[str] = None
    session_id: Optional[str] = None
    snapshot: Optional[str] = None
    tokens: Optional[dict] = None
    cost: Optional[float] = None
    last_text: Optional[str] = None
    events: list[dict] = field(default_factory=list)
    parse_errors: int = 0

    def as_traj_extra(self) -> dict:
        """转换为 write_traj 接受的 **extra 字段（F1 轨迹查看器用）。"""
        extra: dict = {}
        if self.session_id:
            extra["opencode_session_id"] = self.session_id
        if self.snapshot:
            extra["opencode_snapshot"] = self.snapshot
        if self.tokens:
            extra["opencode_tokens"] = self.tokens
        if self.cost is not None:
            extra["opencode_cost"] = self.cost
        if self.reason:
            extra["opencode_finish_reason"] = self.reason
        if self.has_error:
            extra["opencode_has_error"] = True
            if self.error_message:
                extra["opencode_error_message"] = self.error_message
        if self.parse_errors:
            extra["opencode_json_parse_errors"] = self.parse_errors
        extra["opencode_event_count"] = len(self.events)
        return extra


def parse_opencode_json_stream(stdout: str) -> OpencodeJsonParseResult:
    """解析 opencode --format json 的 NDJSON 输出。

    容错：空行、非 JSON 行、缺字段都不抛异常，计数到 parse_errors。
    """
    result = OpencodeJsonParseResult()
    if not stdout:
        return result

    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            result.parse_errors += 1
            continue

        result.events.append(ev)
        ev_type = ev.get("type")

        # 提取 sessionID（每个事件都有）
        if not result.session_id and ev.get("sessionID"):
            result.session_id = ev["sessionID"]

        # part 在 step_start/step_finish/tool_use/text 上是 dict
        # error 事件是顶层 {"error": {...}} 结构
        part = ev.get("part") if isinstance(ev.get("part"), dict) else {}

        if ev_type == "text":
            text = part.get("text")
            if text:
                result.last_text = text
        elif ev_type == "step_finish":
            result.reason = part.get("reason", result.reason)
            result.snapshot = part.get("snapshot", result.snapshot)
            if part.get("tokens") is not None:
                result.tokens = part["tokens"]
            if part.get("cost") is not None:
                result.cost = part["cost"]
        elif ev_type == "error":
            result.has_error = True
            err = ev.get("error", {})
            data = err.get("data", {}) if isinstance(err, dict) else {}
            msg = data.get("message") if isinstance(data, dict) else None
            if msg and not result.error_message:
                result.error_message = msg
        # 其他事件类型（step_start / tool_use）暂不解析（用 events 全量保存够用）

    # 成功判定：最后一个 step_finish.reason == "stop" 且全程无 error 事件
    result.success = (result.reason == "stop") and not result.has_error
    return result