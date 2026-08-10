"""mimo --format json 输出解析器。

mimo 0.1.9 的 NDJSON 事件流结构（实测 2026-08-05）：

    {"type":"step_start","timestamp":...,"sessionID":"ses_...","part":{...}}
    {"type":"text",      "part":{"type":"text","text":"...","time":{...}}}
    {"type":"step_finish","part":{"type":"step-finish","reason":"stop",
                                  "snapshot":"<git-sha>","tokens":{...},
                                  "cost":0.0109...}}
    {"type":"tool_call", "part":{"type":"tool-call", ...}}

关键字段：
- `part.snapshot`：mimo 自维护的 git 快照 SHA（兜底 patch）
- `part.tokens`：{total, input, output, cache.{write,read}}
- `part.cost`：实际费用（mimo auto 是 0，xiaomi 走计费）
- `part.reason`："stop" | "error" | "tool_use" 等（判定成功）
- `sessionID`：关联 mimo session list
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MimoJsonParseResult:
    """mimo --format json 输出解析结果。

    Attributes:
        success: mimo 是否成功完成（reason == "stop"）
        reason: step_finish 的 reason 字段
        session_id: mimo session ID
        snapshot: mimo 的最终 git snapshot（兜底 patch 来源）
        tokens: token 统计 dict（含 cache.read/write）
        cost: 实际费用
        last_text: 最后一次 text 事件的文本
        events: 完整 NDJSON 事件流（jsonl 单行 dict）
        parse_errors: 解析失败的行（垃圾行）
    """
    success: bool = False
    reason: Optional[str] = None
    session_id: Optional[str] = None
    snapshot: Optional[str] = None
    tokens: Optional[dict] = None
    cost: Optional[float] = None
    last_text: Optional[str] = None
    events: list[dict] = field(default_factory=list)
    parse_errors: int = 0

    def as_traj_extra(self) -> dict:
        """转换为 write_traj 接受的 **extra 字段。"""
        extra: dict = {}
        if self.session_id:
            extra["mimo_session_id"] = self.session_id
        if self.snapshot:
            extra["mimo_snapshot"] = self.snapshot
        if self.tokens:
            extra["mimo_tokens"] = self.tokens
        if self.cost is not None:
            extra["mimo_cost"] = self.cost
        if self.reason:
            extra["mimo_finish_reason"] = self.reason
        if self.parse_errors:
            extra["mimo_json_parse_errors"] = self.parse_errors
        extra["mimo_event_count"] = len(self.events)
        return extra


def parse_mimo_json_stream(stdout: str) -> MimoJsonParseResult:
    """解析 mimo --format json 的 NDJSON 输出。

    容错：空行、非 JSON 行、缺字段都不抛异常，计数到 parse_errors。
    """
    result = MimoJsonParseResult()
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
        part = ev.get("part", {})

        # 提取 sessionID（每个事件都有）
        if not result.session_id and ev.get("sessionID"):
            result.session_id = ev["sessionID"]

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
        # 其他事件类型（step_start / tool_call / thinking / ...）暂不解析

    # 成功判定：mimo 的 step_finish.reason == "stop"
    result.success = result.reason == "stop"
    return result
