"""渲染器：把 FlowData + stage_guides 渲染成自包含 HTML 页面。

设计要点：
- 单文件输出（CSS/JS 全内嵌），双击 file:// 即可打开
- HTML escape：所有用户/DB 内容必须转义，防止 XSS
- 数据注入：JSON 块 <script>FLOW_DATA = {...}</script>，避免在 HTML 里裸塞字符串
- 渲染时机：render() 同步生成字符串，write() 落盘

页面骨架（与 plan §5 对齐）：
- 顶部 header（resolved 大字 + 元信息）
- 流水线示意（6 节点 + 连线 + 耗时）
- 三段分组（出题/解题/打分）
- 6 张阶段详情卡片（折叠展开）
- 阶段时间线（底部）
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .data_loader import FlowData
from .stage_guides import GUIDES, PHASES, STAGE_LABELS, STAGE_PHASES, TERMS


# --------------------------------------------------------------------------- #
#  转义辅助
# --------------------------------------------------------------------------- #
def _e(s: Any) -> str:
    """HTML escape，None 返回 ''。"""
    if s is None:
        return ""
    return html.escape(str(s), quote=True)


def _t(s: str | None) -> str:
    """渲染正文文本：先 HTML escape，再用 <abbr> 包裹已知术语（§5.4 教学术语悬浮提示）。

    顺序很重要：先 escape 保证 XSS 安全，然后对转义后的字符串做术语包裹。
    因为 TERMS 都是 ASCII（F2P / P2P / gold patch / worktree 等），转义不会改变它们，
    所以 pattern 匹配仍然有效。
    """
    if not s:
        return ""
    escaped = html.escape(str(s), quote=True)
    out = escaped
    # 按长度倒序匹配，避兔 'gold patch' 被 'gold' 提前吞掉
    for term in sorted(TERMS.keys(), key=len, reverse=True):
        title = html.escape(TERMS[term], quote=True)
        out = out.replace(
            term,
            f'<abbr class="term" title="{title}">{term}</abbr>',
        )
    return out


def _json_safe(obj: Any) -> Any:
    """JSON 序列化前的轻量消毒（Path → str、bytes → str）。"""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(x) for x in obj]
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, bytes):
        try:
            return obj.decode("utf-8", errors="replace")
        except Exception:
            return ""
    return obj


# --------------------------------------------------------------------------- #
#  顶部 Header
# --------------------------------------------------------------------------- #
def _render_header(flow: FlowData) -> str:
    verdict_class = "resolved-yes" if flow.resolved else "resolved-no"
    verdict_label = "RESOLVED" if flow.resolved else "UNRESOLVED"
    return f"""
<header class="page-header">
  <div class="header-left">
    <h1>SWE-bench Lite <span class="muted">流程可视化</span></h1>
    <p class="instance">{_e(flow.instance_id)}</p>
  </div>
  <div class="header-right">
    <div class="verdict {verdict_class}">
      <span class="verdict-label">{verdict_label}</span>
      <span class="verdict-pct">{flow.resolved_pct:.0f}%</span>
    </div>
    <table class="meta-table">
      <tr><th>run_id</th><td><code>{_e(flow.run_id)}</code></td></tr>
      <tr><th>model</th><td><code>{_e(flow.model)}</code></td></tr>
      <tr><th>adapter</th><td><code>{_e(flow.adapter)}</code></td></tr>
      <tr><th>image</th><td><code>{_e(flow.image)}</code></td></tr>
      <tr><th>F2P</th><td>{flow.f2p_pass} pass / {flow.f2p_fail} fail</td></tr>
      <tr><th>P2P</th><td>{flow.p2p_pass} pass / {flow.p2p_fail} fail</td></tr>
    </table>
  </div>
</header>
"""


# --------------------------------------------------------------------------- #
#  流水线示意（6 节点 + 连线 + 耗时）
# --------------------------------------------------------------------------- #
def _render_pipeline(flow: FlowData) -> str:
    if flow.manifest_missing:
        return '<section class="pipeline"><div class="empty">manifest.json 不存在，无法渲染流水线</div></section>'

    nodes = []
    for i, stage in enumerate(flow.stages):
        phase = STAGE_PHASES.get(stage.name, "solve")
        label = STAGE_LABELS.get(stage.name, stage.name)
        duration = f"{stage.duration_s:.1f}s" if stage.duration_s > 0 else "—"
        is_last = (i == len(flow.stages) - 1)
        nodes.append(f"""
<div class="node node-{phase}" data-stage="{_e(stage.name)}">
  <div class="node-status status-{_e(stage.status)}">{_e(_status_icon(stage.status))}</div>
  <div class="node-name">{_e(label)}</div>
  <div class="node-id">{_e(stage.name)}</div>
  <div class="node-duration">{duration}</div>
</div>
{"<div class='connector'></div>" if not is_last else ""}
""")
    nodes_html = "\n".join(nodes)

    legend = ""
    for key, info in PHASES.items():
        legend += (
            f'<span class="legend-item"><span class="legend-dot" '
            f'style="background:{info["color"]}"></span>'
            f'{_e(info["label"])}：{_e(info["description"])}</span>'
        )

    return f"""
<section class="pipeline">
  <h2>流水线（六阶段闭环）</h2>
  <div class="pipeline-flow">{nodes_html}</div>
  <div class="legend">{legend}</div>
</section>
"""


def _status_icon(status: str) -> str:
    return {"done": "✓", "failed": "✗", "running": "↻", "pending": "○"}.get(status, "?")


# --------------------------------------------------------------------------- #
#  阶段详情卡片
# --------------------------------------------------------------------------- #
def _render_stages(flow: FlowData) -> str:
    if flow.manifest_missing:
        return ""

    cards = []
    for stage in flow.stages:
        guide = GUIDES.get(stage.name, {})
        phase = guide.get("phase", "solve")
        cards.append(f"""
<article class="stage-card phase-{phase}" data-stage="{_e(stage.name)}">
  <header class="stage-card-header" onclick="this.parentElement.classList.toggle('open')">
    <span class="stage-badge">{_e(STAGE_LABELS.get(stage.name, stage.name))}</span>
    <span class="stage-title">{_e(guide.get("title", stage.name))}</span>
    <span class="stage-status status-{_e(stage.status)}">{_e(_status_icon(stage.status))} {_e(stage.status)}</span>
    <span class="stage-duration">{stage.duration_s:.1f}s</span>
    <span class="toggle">▾</span>
  </header>
  <div class="stage-card-body">
    <div class="grid-2">
      <div>
        <h3>做什么</h3>
        <p>{_t(guide.get("what", ""))}</p>
      </div>
      <div>
        <h3>为什么需要</h3>
        <p>{_t(guide.get("why", ""))}</p>
      </div>
    </div>
    <div class="grid-2">
      <div>
        <h3>输入</h3>
        <ul class="io-list">{_render_io_list(guide.get("inputs", []))}</ul>
      </div>
      <div>
        <h3>输出（产物）</h3>
        <ul class="io-list">{_render_io_list(guide.get("outputs", []))}</ul>
      </div>
    </div>
    <div class="run-block">
      <h3>本次运行实测</h3>
      <table class="kv-table">
        <tr><th>起止</th><td>{_e(stage.started_at or "—")} → {_e(stage.finished_at or "—")}</td></tr>
        <tr><th>耗时</th><td>{stage.duration_s:.1f}s</td></tr>
        <tr><th>子命令链</th><td><code>{_e(_join_command(stage.command))}</code></td></tr>
        <tr><th>产物路径</th><td>{_render_product_links(stage.outputs, flow.task_dir) or "（无）"}</td></tr>
        {"<tr><th>错误</th><td class='error'>" + _e(stage.error) + "</td></tr>" if stage.error else ""}
      </table>
    </div>
    <div class="preview-block">
      <h3>产物预览</h3>
      {_render_preview(stage.name, stage.preview)}
    </div>
  </div>
</article>
""")
    return '<section class="stages"><h2>阶段详情（点击展开）</h2>' + "\n".join(cards) + "</section>"


def _render_io_list(items: list[str]) -> str:
    if not items:
        return "<li class='muted'>（无）</li>"
    return "".join(f"<li>{_e(it)}</li>" for it in items)


def _render_product_links(outputs: list[str], task_dir: str) -> str:
    """产物路径渲染为可点击的 file:// 链接（§5.3 第 4 块“跳转到产物文件”）。

    仅在文件实际存在时生成链接，缺失的产物仍以 <code> 文本展示（带 ✘ 提示）。
    """
    if not outputs:
        return ""
    parts = []
    base = Path(task_dir)
    for o in outputs:
        path = Path(o)
        # 计算 file:// URL（仅当路径存在时点击才有效）
        try:
            rel = path.relative_to(base)
            exists = path.exists()
            label = _e(str(rel))
        except ValueError:
            rel = None
            exists = path.exists()
            label = _e(path.name)
        if exists:
            url = path.resolve().as_uri()
            mark = "✓"
            parts.append(
                f'<a class="file-link" href="{_e(url)}" target="_blank" '
                f'title="{_e(str(path))}"><code>{label}</code></a> <span class="file-mark">{mark}</span>'
            )
        else:
            parts.append(
                f'<span class="file-missing" title="{_e(str(path))}">'
                f'<code>{label}</code> <span class="file-mark">✘</span></span>'
            )
    return "<br>".join(parts)


def _join_command(cmd: list[str] | None) -> str:
    """拼接子命令链为展示字符串（容忍 list 中混入 ... / None 等非 str）。"""
    if not cmd:
        return "（进程内）"
    parts = []
    for c in cmd:
        if c is None:
            continue
        if not isinstance(c, str):
            parts.append(str(c))
        else:
            parts.append(c)
    return " ".join(parts) if parts else "（进程内）"


def _render_preview(stage_name: str, preview: dict) -> str:
    """按阶段名分发到专属预览渲染。"""
    builders = {
        "S1_build":   _preview_s1_html,
        "S2_prepare": _preview_s2_html,
        "S4_solve":   _preview_s4_html,
        "S5_patch":   _preview_s5_html,
        "S6_score":   _preview_s6_html,
        "S7_record":  _preview_s7_html,
    }
    fn = builders.get(stage_name)
    return fn(preview) if fn else "<div class='muted'>（无预览数据）</div>"


def _preview_s1_html(p: dict) -> str:
    if not p:
        return "<div class='muted'>S1 未运行或产物缺失</div>"
    issue_fields = p.get("issue_fields") or {}
    issue_keys = p.get("issue_raw_keys") or []
    rows = "".join(f"<tr><th>{_e(k)}</th><td><code>{_e(v)}</code></td></tr>" for k, v in issue_fields.items())
    keys_html = (
        f"<details><summary>ca-issue.json 全字段 ({len(issue_keys)})</summary>"
        f"<code>{_e(', '.join(issue_keys))}</code></details>"
    ) if issue_keys else ""
    return f"""
<div class="preview-tabs">
  <div><h4>ca-issue.json（给 Agent 的输入，7 字段）</h4>
    <table class="kv-table">{rows or "<tr><td class='muted'>（空）</td></tr>"}</table>
    {keys_html}
  </div>
  <div><h4>review.md（人工审阅版头 60 行）</h4>
    <pre class="md">{_e(p.get('review_head', ''))}</pre>
  </div>
  <div><h4>ca-task-prompt.md（Agent 任务指令头）</h4>
    <pre class="md">{_e(p.get('prompt_head', ''))}</pre>
  </div>
</div>
"""


def _preview_s2_html(p: dict) -> str:
    if not p:
        return "<div class='muted'>S2 未运行或 image.json 缺失</div>"
    img = p.get("image_info") or {}
    rows = "".join(f"<tr><th>{_e(k)}</th><td><code>{_e(v)}</code></td></tr>" for k, v in img.items())
    return f"<table class='kv-table'>{rows}</table>"


def _preview_s4_html(p: dict) -> str:
    if not p:
        return "<div class='muted'>S4 未运行或 .pred 缺失</div>"
    pred_keys = p.get("pred_keys") or []
    exit_code = p.get("exit_code")
    patch_bytes = p.get("patch_bytes", 0)
    patch_lines = p.get("patch_lines", 0)
    traj_steps = p.get("traj_steps")
    traj_total = p.get("traj_total_lines")
    return f"""
<table class="kv-table">
  <tr><th>.pred 字段</th><td><code>{_e(', '.join(pred_keys)) or '（空）'}</code></td></tr>
  <tr><th>model_patch</th><td>{patch_bytes} bytes / {patch_lines} 行</td></tr>
  <tr><th>exit_code</th><td><code>{_e(exit_code)}</code></td></tr>
  {f"<tr><th>.traj</th><td>{traj_steps} 步 / {traj_total} 行</td></tr>" if traj_steps else ""}
</table>
<details><summary>model_patch 前 40 行</summary>
<pre class="patch">{_e(p.get('patch_head', ''))}</pre>
</details>
"""


def _preview_s5_html(p: dict) -> str:
    if not p:
        return "<div class='muted'>S5 未运行或 model.patch 缺失</div>"
    files = p.get("changed_files") or []
    diff_stat = p.get("diff_stat", "")
    patch_head = p.get("patch_head", "")
    total = p.get("patch_total_lines", 0)
    return f"""
<table class="kv-table">
  <tr><th>diff-stat</th><td><code>{_e(diff_stat) or '（无）'}</code></td></tr>
  <tr><th>patch 行数</th><td>{total}</td></tr>
  <tr><th>changed-files</th><td><code>{_e(', '.join(files)) or '（无）'}</code></td></tr>
</table>
<details open><summary>model.patch diff（前 80 行）</summary>
<pre class="diff">{_highlight_diff(patch_head)}</pre>
</details>
<details><summary>prediction.jsonl</summary>
<pre class="json">{_e(p.get('prediction_head', ''))}</pre>
</details>
"""


def _preview_s6_html(p: dict) -> str:
    if not p:
        return "<div class='muted'>S6 未运行或 eval/report.json 缺失</div>"
    f2p_pass = p.get("f2p_pass", [])
    f2p_fail = p.get("f2p_fail", [])
    p2p_pass = p.get("p2p_pass", [])
    p2p_fail = p.get("p2p_fail", [])
    patch_applied = p.get("patch_applied")
    return f"""
<table class="kv-table">
  <tr><th>patch_exists</th><td>{_e(p.get('patch_exists'))}</td></tr>
  <tr><th>patch_applied</th><td>{_e(patch_applied)}</td></tr>
  <tr><th>resolved</th><td><strong>{_e(p.get('resolved'))}</strong></td></tr>
</table>
<div class="test-grid">
  <div class="test-col">
    <h4 class="ok">FAIL_TO_PASS pass（{len(f2p_pass)}）</h4>
    <ul class="test-list">{"".join(f"<li class='ok'>{_e(t)}</li>" for t in f2p_pass[:20]) or "<li class='muted'>（无）</li>"}</ul>
    {f"<details><summary>展开剩余 {len(f2p_pass)-20} 条</summary><ul class='test-list'>{''.join(f'<li class=ok>{_e(t)}</li>' for t in f2p_pass[20:])}</ul></details>" if len(f2p_pass) > 20 else ""}
    <h4 class="fail">FAIL_TO_PASS fail（{len(f2p_fail)}）</h4>
    <ul class="test-list">{"".join(f"<li class='fail'>{_e(t)}</li>" for t in f2p_fail[:20]) or "<li class='muted'>（无）</li>"}</ul>
  </div>
  <div class="test-col">
    <h4 class="ok">PASS_TO_PASS pass（{len(p2p_pass)}）</h4>
    <ul class="test-list">{"".join(f"<li class='ok'>{_e(t)}</li>" for t in p2p_pass[:20]) or "<li class='muted'>（无）</li>"}</ul>
    {f"<details><summary>展开剩余 {len(p2p_pass)-20} 条</summary><ul class='test-list'>{''.join(f'<li class=ok>{_e(t)}</li>' for t in p2p_pass[20:])}</ul></details>" if len(p2p_pass) > 20 else ""}
    <h4 class="fail">PASS_TO_PASS fail（{len(p2p_fail)}）</h4>
    <ul class="test-list">{"".join(f"<li class='fail'>{_e(t)}</li>" for t in p2p_fail[:20]) or "<li class='muted'>（无）</li>"}</ul>
  </div>
</div>
"""


def _preview_s7_html(p: dict) -> str:
    if not p:
        return "<div class='muted'>S7 未运行或 result.json 缺失</div>"
    rows = ""
    for k, v in p.items():
        if k == "stages":
            stages = v or {}
            rows += f"<tr><th>stages</th><td>{_render_stages_kv(stages)}</td></tr>"
        elif k == "stage_timings":
            timings = v or {}
            timing_rows = "".join(
                f"<span class='timing-chip'><code>{_e(k)}</code>: {v:.1f}s</span>"
                for k, v in timings.items()
            )
            rows += f"<tr><th>stage_timings</th><td>{timing_rows}</td></tr>"
        elif k == "resolved":
            rows += f"<tr><th>resolved</th><td><strong class='resolved-yes'>{_e(v)}</strong></td></tr>"
        else:
            rows += f"<tr><th>{_e(k)}</th><td><code>{_e(v)}</code></td></tr>"
    return f"<table class='kv-table'>{rows}</table>"


def _render_stages_kv(stages: dict) -> str:
    return " ".join(
        f"<span class='stage-chip status-{_e(v)}'>{_e(k)}:{_e(v)}</span>"
        for k, v in stages.items()
    )


def _highlight_diff(text: str) -> str:
    """diff 三色高亮（增/删/上下文），HTML escape 在外层完成。"""
    lines = text.splitlines()
    out = []
    for ln in lines:
        if ln.startswith("+++") or ln.startswith("---"):
            out.append(f'<span class="diff-header">{_e(ln)}</span>')
        elif ln.startswith("+"):
            out.append(f'<span class="diff-add">{_e(ln)}</span>')
        elif ln.startswith("-"):
            out.append(f'<span class="diff-del">{_e(ln)}</span>')
        elif ln.startswith("@@"):
            out.append(f'<span class="diff-hunk">{_e(ln)}</span>')
        else:
            out.append(f'<span class="diff-ctx">{_e(ln)}</span>')
    return "\n".join(out)


# --------------------------------------------------------------------------- #
#  阶段时间线（底部）
# --------------------------------------------------------------------------- #
def _render_timeline(flow: FlowData) -> str:
    if flow.manifest_missing:
        return ""
    total_dur = sum(s.duration_s for s in flow.stages)
    if total_dur <= 0:
        return "<section class='timeline'><h2>阶段耗时时间线</h2><div class='muted'>无耗时数据</div></section>"

    bars = []
    max_dur = max((s.duration_s for s in flow.stages), default=1.0)
    for stage in flow.stages:
        pct = (stage.duration_s / total_dur * 100) if total_dur > 0 else 0
        bar_pct = (stage.duration_s / max_dur * 100) if max_dur > 0 else 0
        phase = STAGE_PHASES.get(stage.name, "solve")
        phase_color = PHASES[phase]["color"]
        is_bottleneck = stage.duration_s == max_dur and stage.duration_s > 0
        bottleneck_mark = " <span class='bottleneck'>瓶颈</span>" if is_bottleneck else ""
        bars.append(f"""
<div class="timeline-row">
  <div class="timeline-label">
    <span class="timeline-name">{_e(STAGE_LABELS.get(stage.name, stage.name))}</span>
    <code class="timeline-id">{_e(stage.name)}</code>
  </div>
  <div class="timeline-track">
    <div class="timeline-bar" style="width:{bar_pct:.1f}%;background:{phase_color}"></div>
    <span class="timeline-bar-label">{stage.duration_s:.1f}s</span>
  </div>
  <div class="timeline-pct">{pct:.1f}%{bottleneck_mark}</div>
</div>
""")
    total_msg = f"总耗时 <strong>{total_dur:.1f}s</strong>"
    return f"""
<section class="timeline">
  <h2>阶段耗时时间线（{total_msg}）</h2>
  <div class="timeline-body">{"".join(bars)}</div>
</section>
"""


# --------------------------------------------------------------------------- #
#  术语字典（底部参考）
# --------------------------------------------------------------------------- #
def _render_terms() -> str:
    items = "".join(
        f"<dt><code>{_e(k)}</code></dt><dd>{_e(v)}</dd>"
        for k, v in TERMS.items()
    )
    return f"""
<section class="terms">
  <h2>术语速查</h2>
  <dl class="terms-list">{items}</dl>
</section>
"""


# --------------------------------------------------------------------------- #
#  CSS
# --------------------------------------------------------------------------- #
_CSS = """
:root {
  --bg: #f8fafc;
  --card: #ffffff;
  --border: #e2e8f0;
  --text: #1e293b;
  --muted: #64748b;
  --code-bg: #f1f5f9;
  --ok: #16a34a;
  --fail: #dc2626;
  --phase-issue: #3b82f6;
  --phase-solve: #8b5cf6;
  --phase-grade: #f59e0b;
}
* { box-sizing: border-box; }
body {
  margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
    "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.6;
}
body > section, body > header { max-width: 1200px; margin: 0 auto; padding: 24px; }
# page-header.page-header { background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
  color: #f1f5f9; padding: 32px; border-radius: 0 0 12px 12px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 32px; }
.page-header h1 { margin: 0 0 8px 0; font-size: 28px; }
.page-header h1 .muted { color: #94a3b8; font-weight: 400; }
.page-header .instance { margin: 0; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 16px; opacity: 0.9; }
.header-right { display: flex; flex-direction: column; align-items: flex-end; gap: 16px; }
.verdict { display: flex; align-items: baseline; gap: 12px;
  padding: 12px 20px; border-radius: 8px; font-weight: 600; }
.verdict.resolved-yes { background: #dcfce7; color: #166534; }
.verdict.resolved-no { background: #fee2e2; color: #991b1b; }
.verdict-label { font-size: 18px; }
.verdict-pct { font-size: 32px; }
.meta-table { font-size: 13px; }
.meta-table th { text-align: right; padding: 2px 12px 2px 0; color: #94a3b8; font-weight: 500; }
.meta-table td { padding: 2px 0; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
code { background: var(--code-bg); padding: 2px 6px; border-radius: 4px;
  font-size: 13px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.muted { color: var(--muted); }
/* §5.4 教学术语悬浮提示 */
abbr.term { text-decoration: underline dotted #2563eb; text-decoration-thickness: 2px;
  text-underline-offset: 3px; cursor: help; color: #1d4ed8;
  font-weight: 500; border-bottom: none; background: #eff6ff;
  padding: 0 3px; border-radius: 3px; }
abbr.term:hover { background: #dbeafe; color: #1e3a8a; }
/* §5.3 产物文件链接 */
a.file-link { text-decoration: none; color: #1d4ed8; }
a.file-link code { background: #fef3c7; color: #92400e; }
a.file-link:hover code { background: #fde68a; color: #78350f; }
.file-missing code { color: var(--muted); text-decoration: line-through; background: #fee2e2; }
.file-mark { font-size: 11px; margin-left: 4px; font-weight: 600; }
.file-link + .file-mark { color: var(--ok); }
.file-missing .file-mark { color: var(--fail); }
section h2 { margin-top: 32px; padding-bottom: 8px; border-bottom: 2px solid var(--border); }
.pipeline-flow { display: flex; align-items: center; justify-content: space-between;
  gap: 8px; padding: 24px 0; flex-wrap: wrap; }
.node { flex: 1; min-width: 130px; padding: 16px; border-radius: 8px;
  background: var(--card); border: 2px solid var(--border); text-align: center;
  cursor: pointer; transition: all 0.2s; position: relative; }
.node:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
.node-issue { border-top: 4px solid var(--phase-issue); }
.node-solve { border-top: 4px solid var(--phase-solve); }
.node-grade { border-top: 4px solid var(--phase-grade); }
.node-status { font-size: 24px; margin-bottom: 8px; }
.status-done { color: var(--ok); }
.status-failed { color: var(--fail); }
.status-running { color: #2563eb; animation: spin 1s linear infinite; }
.status-pending { color: var(--muted); }
@keyframes spin { from { transform: rotate(0); } to { transform: rotate(360deg); } }
.node-name { font-weight: 600; font-size: 15px; }
.node-id { font-size: 11px; color: var(--muted); font-family: ui-monospace, monospace;
  margin: 4px 0; }
.node-duration { font-size: 13px; color: var(--muted); }
.connector { width: 32px; height: 2px; background: linear-gradient(90deg, var(--border), var(--border)); }
.legend { display: flex; flex-wrap: wrap; gap: 16px; padding: 16px; background: var(--card);
  border-radius: 8px; font-size: 13px; }
.legend-item { display: inline-flex; align-items: center; gap: 8px; }
.legend-dot { display: inline-block; width: 12px; height: 12px; border-radius: 50%; }
.stage-card { background: var(--card); border-radius: 8px; margin: 16px 0;
  border: 1px solid var(--border); overflow: hidden; }
.stage-card.phase-issue { border-left: 4px solid var(--phase-issue); }
.stage-card.phase-solve { border-left: 4px solid var(--phase-solve); }
.stage-card.phase-grade { border-left: 4px solid var(--phase-grade); }
.stage-card-header { display: flex; align-items: center; gap: 16px; padding: 16px;
  cursor: pointer; user-select: none; }
.stage-card-header:hover { background: #f1f5f9; }
.stage-badge { background: #f1f5f9; padding: 4px 8px; border-radius: 4px;
  font-size: 12px; font-weight: 600; }
.stage-title { flex: 1; font-weight: 500; }
.stage-status { font-size: 13px; padding: 2px 8px; border-radius: 12px; background: #f1f5f9; }
.stage-card.open .stage-status.status-done { background: #dcfce7; color: #166534; }
.stage-card.open .stage-status.status-failed { background: #fee2e2; color: #991b1b; }
.stage-duration { font-size: 13px; color: var(--muted); font-family: ui-monospace, monospace; }
.toggle { font-size: 18px; transition: transform 0.2s; }
.stage-card.open .toggle { transform: rotate(180deg); }
.stage-card-body { display: none; padding: 16px 24px; border-top: 1px solid var(--border); }
.stage-card.open .stage-card-body { display: block; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 16px; }
@media (max-width: 768px) { .grid-2 { grid-template-columns: 1fr; } }
.grid-2 h3, .run-block h3, .preview-block h3 { font-size: 14px; color: var(--muted);
  text-transform: uppercase; margin: 0 0 8px 0; letter-spacing: 0.5px; }
.io-list { padding-left: 20px; margin: 0; }
.io-list li { margin: 4px 0; }
.kv-table { width: 100%; border-collapse: collapse; font-size: 13px; margin: 8px 0; }
.kv-table th { text-align: left; padding: 6px 12px 6px 0; color: var(--muted);
  font-weight: 500; vertical-align: top; width: 140px; }
.kv-table td { padding: 6px 0; vertical-align: top; }
.kv-table .error { color: var(--fail); }
.run-block, .preview-block { margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--border); }
.preview-tabs > div { margin: 12px 0; }
.preview-tabs h4 { margin: 8px 0; font-size: 13px; color: var(--muted); }
pre { background: #0f172a; color: #e2e8f0; padding: 16px; border-radius: 6px;
  overflow-x: auto; font-size: 12px; line-height: 1.5; margin: 8px 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
pre.md { background: #1e293b; }
pre.json { background: #082f49; }
.diff-add { color: #86efac; }
.diff-del { color: #fca5a5; }
.diff-header { color: #94a3b8; font-weight: 600; }
.diff-hunk { color: #fbbf24; }
.diff-ctx { color: #cbd5e1; }
.test-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-top: 8px; }
@media (max-width: 768px) { .test-grid { grid-template-columns: 1fr; } }
.test-col h4 { margin: 12px 0 4px 0; font-size: 13px; }
.test-col h4.ok { color: var(--ok); }
.test-col h4.fail { color: var(--fail); }
.test-list { list-style: none; padding: 0; margin: 0;
  max-height: 200px; overflow-y: auto; font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.test-list li { padding: 4px 8px; border-radius: 4px; margin: 2px 0; }
.test-list li.ok { background: #dcfce7; color: #166534; }
.test-list li.fail { background: #fee2e2; color: #991b1b; }
.timeline-body { margin-top: 16px; }
.timeline-row { display: grid; grid-template-columns: 180px 1fr 100px;
  align-items: center; gap: 16px; padding: 8px 0; }
.timeline-label { display: flex; flex-direction: column; gap: 2px; }
.timeline-name { font-weight: 500; font-size: 14px; }
.timeline-id { font-size: 11px; color: var(--muted); }
.timeline-track { position: relative; background: #f1f5f9; height: 28px;
  border-radius: 4px; overflow: hidden; }
.timeline-bar { height: 100%; border-radius: 4px; transition: width 0.5s; }
.timeline-bar-label { position: absolute; top: 50%; left: 12px;
  transform: translateY(-50%); font-size: 12px; color: #1e293b; font-weight: 500; }
.timeline-pct { text-align: right; font-family: ui-monospace, monospace;
  font-size: 13px; color: var(--muted); }
.bottleneck { color: var(--fail); font-weight: 600; }
.terms-list { display: grid; grid-template-columns: 200px 1fr; gap: 8px 16px;
  margin: 0; }
.terms-list dt { font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 13px; }
.terms-list dd { margin: 0; font-size: 14px; }
.stage-chip { display: inline-block; padding: 2px 8px; border-radius: 12px;
  background: #f1f5f9; font-size: 11px; margin: 2px; }
.stage-chip.status-done { background: #dcfce7; color: #166534; }
.stage-chip.status-failed { background: #fee2e2; color: #991b1b; }
.timing-chip { display: inline-block; padding: 2px 8px; background: #f1f5f9;
  border-radius: 4px; font-size: 12px; margin: 2px; }
.empty { padding: 24px; background: var(--card); border-radius: 8px;
  text-align: center; color: var(--muted); }
"""


# --------------------------------------------------------------------------- #
#  JS（仅交互：节点→卡片锚点、键盘快捷键）
# --------------------------------------------------------------------------- #
_JS = """
document.addEventListener('DOMContentLoaded', () => {
  // 流水线节点点击 → 滚动到对应阶段卡片并展开
  document.querySelectorAll('.node').forEach(node => {
    node.addEventListener('click', () => {
      const stageName = node.dataset.stage;
      const card = document.querySelector(`.stage-card[data-stage="${stageName}"]`);
      if (card) {
        card.classList.add('open');
        card.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  });
  // 键盘：1-6 切换阶段展开
  document.addEventListener('keydown', (e) => {
    const map = { '1': 'S1_build', '2': 'S2_prepare', '3': 'S4_solve',
                  '4': 'S5_patch', '5': 'S6_score', '6': 'S7_record' };
    const stageName = map[e.key];
    if (stageName) {
      const card = document.querySelector(`.stage-card[data-stage="${stageName}"]`);
      if (card) {
        card.classList.toggle('open');
        card.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }
    // e 全部展开 / c 全部折叠
    if (e.key === 'e') document.querySelectorAll('.stage-card').forEach(c => c.classList.add('open'));
    if (e.key === 'c') document.querySelectorAll('.stage-card').forEach(c => c.classList.remove('open'));
  });
});
"""


# --------------------------------------------------------------------------- #
#  顶层渲染
# --------------------------------------------------------------------------- #
HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>流程可视化 · {instance_id}</title>
<style>{css}</style>
</head>
<body>
{header}
{pipeline}
{stages}
{timeline}
{terms}
<footer style="max-width:1200px;margin:32px auto;padding:24px;color:var(--muted);font-size:12px;text-align:center;">
  SWE-bench Lite 流程可视化教学模块 ·
  数据来源：output/{instance_id}/manifest.json + result.json + 阶段产物 ·
  键盘快捷键：1-6 切换阶段 · e 全展开 · c 全折叠
</footer>
<script>{js}</script>
</body>
</html>
"""


def render(flow: FlowData) -> str:
    """生成完整 HTML 字符串。"""
    return HTML_TEMPLATE.format(
        instance_id=_e(flow.instance_id),
        css=_CSS,
        header=_render_header(flow),
        pipeline=_render_pipeline(flow),
        stages=_render_stages(flow),
        timeline=_render_timeline(flow),
        terms=_render_terms(),
        js=_JS,
    )


def write(flow: FlowData, output_path: str | Path) -> Path:
    """写 HTML 到 output_path，返回绝对路径。"""
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render(flow), encoding="utf-8")
    return output_path