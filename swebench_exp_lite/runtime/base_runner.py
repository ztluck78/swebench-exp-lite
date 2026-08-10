"""BaseAgentRunner：3 个 Agent Runner 的共同骨架（DESIGN Step 2）。

3 个 adapter（kimi / qwen / mimo）的 `*AgentRunner._run_locked` 之前是
~700 行同构代码 + 6 个字面量差异（log tag / 启动消息 / Result 类 / 
_get_agent / 类名 / self.name）。抽到基类后 3 thin adapter 只剩
~50 行 + 必要 hook override。

5 个 hook（差异化点）：
- `_get_agent(repo_root)` — abstract 必实现
- `_make_error_result(iid, err)` — 备仓失败返回（基类默认 RunResult）
- `_log_tag()` — 日志 tag（基类默认 f"[{self.name}]"）
- `_start_message()` — 启动消息文案
- `_post_invoke_brand_hook(...)` — mimo D10/D4 特殊步骤

使用方式：
    from swebench_exp_lite.runtime.base_runner import BaseAgentRunner
    
    class KimiAgentRunner(BaseAgentRunner[RunResult]):
        name = "kimi-agent"
        
        def __init__(self, model="kimi-code/kimi-for-coding", timeout=600, max_retries=0, **kwargs):
            super().__init__(model=model, timeout=timeout, max_retries=max_retries, **kwargs)
        
        def _get_agent(self, repo_root):
            from kimi_agent.agent import KimiAgent
            if not self._agent:
                from kimi_agent.config import KimiConfig
                self._agent = KimiAgent(KimiConfig(model=self.model, timeout=self.timeout, ...))
            return self._agent
"""
from __future__ import annotations

import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Generic, Optional, TypeVar

from .protocol import AgentResult


# TResult 泛型：每个 adapter 有自己的 Result 子类（RunResult / QwenResult / MimoResult）
TResult = TypeVar("TResult", bound=AgentResult)


class BaseAgentRunner(Generic[TResult]):
    """所有 Agent Runner 的共同骨架——9 步流程 + 5 hook 容纳差异化。

    3 个 adapter 共用此基类，子类只实现 _get_agent 即可。
    TResult 是泛型参数，让 type checker 知道 _make_error_result 返回的子类类型。
    """

    name: str = "base"  # 子类覆盖（"kimi-agent" / "qwen-agent" / "mimo-agent"）

    # C10（SPEC-modularization-round2）：声明式 _get_agent 模板。
    # 子类声明 config_class / agent_class 即可免实现 _get_agent；
    # 有特殊构造逻辑的仍可 override _get_agent / _build_config。
    config_class: Optional[type] = None
    agent_class: Optional[type] = None

    def __init__(
        self,
        *,
        model: str = "",
        timeout: int = 1800,
        max_retries: int = 0,
        **kwargs,
    ):
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self._agent: Any = None  # 缓存的 brand Agent 实例（lazy init）
        # 吸收 kwargs（不同 adapter 的额外 config 字段）
        for k, v in kwargs.items():
            setattr(self, k, v)

    # ──────────────────────────────────────────────────────────
    # 入口 run()（3 个 adapter 共有：repo_dir 改写 + C-11 并发锁 + 调 _run_locked）
    # ──────────────────────────────────────────────────────────

    def run(
        self,
        instance_id: str,
        issue_path: Path,
        ca_prompt_path: Path,
        repo_dir: Path,
        output_dir: Path,
        repo_root: Optional[Path] = None,
        repo_url: Optional[str] = None,
        base_commit: Optional[str] = None,
        prep_log_path: Optional[Path] = None,
        post_prep_hook: Optional[Callable[[], None]] = None,
    ) -> TResult:
        """执行 Agent 任务（orchestrator 调用入口）。

        流程（3 个 adapter 共有）：
        1. repo_root 默认 Path.cwd()
        2. WORKSPACE_MODE 决定 shared_cache；shared_cache=True 时把 repo_dir
           改写到 runtime-cache/worktrees/{instance_id}（避免污染实验结果目录）
        3. C-11 并发守卫（acquire_run_lock）——同实例第二次并发运行显式拒绝
        4. 调 _run_locked() 跑 9 步主流程
        5. finally 释放锁

        Args:
            instance_id: 实例 ID
            issue_path: issue.json 路径
            ca_prompt_path: ca-task-prompt.md 路径
            repo_dir: 期望的代码仓库目录（基类会按 WORKSPACE_MODE 改写）
            output_dir: 输出目录
            repo_root: 项目根目录（默认 Path.cwd()）
            repo_url: 仓库 URL（用于自动克隆）
            base_commit: 基线 commit（用于自动 checkout）
            prep_log_path: 备仓独立日志路径
            post_prep_hook: 备仓后回调（C-03 环境预装等）

        Returns:
            TResult (AgentResult 子类)
        """
        if repo_root is None:
            repo_root = Path.cwd()

        # WORKSPACE_MODE 决定 shared_cache；shared_cache=True 时把 repo_dir
        # 改写到 runtime-cache 下（与原 3 runner.py 行为对齐）
        shared_cache = os.environ.get("WORKSPACE_MODE", "shared-mirror-worktree") != "experiment-local"
        if shared_cache and repo_url and base_commit:
            cache_root = Path(
                os.environ.get("SWEBENCH_RUNTIME_CACHE", str(repo_root / "runtime-cache"))
            )
            retention = os.environ.get("WORKSPACE_RETENTION", "ephemeral")
            root_name = "snapshots" if retention == "snapshot" else "worktrees"
            repo_dir = cache_root / root_name / instance_id

        # C-11：同实例并发守卫
        lock, refused = self._acquire_lock(repo_dir, instance_id)
        if refused is not None:
            print(f"    {self._log_tag()} {refused.error}")
            return refused

        try:
            return self._run_locked(
                instance_id=instance_id,
                issue_path=issue_path,
                ca_prompt_path=ca_prompt_path,
                repo_dir=repo_dir,
                output_dir=output_dir,
                repo_root=repo_root,
                repo_url=repo_url,
                base_commit=base_commit,
                prep_log_path=prep_log_path,
                post_prep_hook=post_prep_hook,
                shared_cache=shared_cache,
            )
        finally:
            # Path.rmdir() 不支持 missing_ok 关键字，改用存在性判断（修复 C-11 锁释放 TypeError）
            if lock.exists():
                lock.rmdir()

    def _acquire_lock(self, repo_dir: Path, instance_id: str):
        """C-11 并发锁——子类可覆盖（默认用 swebench_exp_lite.runtime.repo.acquire_run_lock）。

        Returns:
            (lock_path, refused_result_or_None)
        """
        from .repo import acquire_run_lock as _ar_acquire_run_lock
        return _ar_acquire_run_lock(repo_dir, instance_id)

    # ──────────────────────────────────────────────────────────
    # 5 hook（差异化点）
    # ──────────────────────────────────────────────────────────

    def _get_agent(self, repo_root: Path) -> Any:
        """返回 brand Agent 实例（lazy init + 缓存）。

        C10 模板化：子类声明 config_class / agent_class 即走默认实现
        （agent_class(config=_build_config(repo_root))）；特殊构造可 override。
        未声明 config_class/agent_class 且未 override → NotImplementedError。
        """
        if self.config_class is None or self.agent_class is None:
            raise NotImplementedError(f"{type(self).__name__}._get_agent not implemented")
        if self._agent is None:
            self._agent = self.agent_class(config=self._build_config(repo_root))
        return self._agent

    def _build_config(self, repo_root: Path) -> Any:
        """构造 brand Config（模板默认 4 公共参数；brand 特有字段由 Config 默认值兜底）。"""
        return self.config_class(
            model=self.model,
            timeout=self.timeout,
            max_retries=self.max_retries,
            workspace_root=repo_root,
        )

    def _make_error_result(self, instance_id: str, error: str) -> TResult:
        """备仓失败时构造 Result。基类默认返 AgentResult，子类可覆盖。"""
        return AgentResult(success=False, instance_id=instance_id, error=error)

    def _log_tag(self) -> str:
        """日志 tag。基类默认 f"[{self.name}]"，3 adapter 都走默认。"""
        return f"[{self.name}]"

    def _start_message(self) -> str:
        """启动消息。基类默认 "启动 {self.name} Agent"，子类可覆盖。"""
        return f"启动 {self.name} Agent"

    def _post_invoke_brand_hook(
        self,
        agent: Any,
        repo_dir: Path,
        base_commit: Optional[str],
        output_dir: Path,
        parse_result: Any = None,
    ) -> None:
        """agent.run() 之后的 brand 特殊步骤（Step 3 重构后方法名从 run_with_retry 改回 run）。

        mimo 用这里调 D10（detect auto-commit + reset）+ D4（清理 .mimocode/）。
        kimi/qwen 默认 no-op（什么都不做）。

        Args:
            agent: brand Agent 实例（KimiAgent / QwenAgent / MimoAgent）
            repo_dir: 仓库目录
            base_commit: 备仓时的基线 commit（用于 D10 reset 对比）
            output_dir: 产物输出目录
            parse_result: agent 解析 NDJSON/stream-json 后的结果对象
        """
        pass  # 默认 no-op

    # ──────────────────────────────────────────────────────────
    # 9 步主流程（基类实现，子类不覆盖）
    # ──────────────────────────────────────────────────────────

    def _run_locked(
        self,
        *,
        instance_id: str,
        issue_path: Path,
        ca_prompt_path: Path,
        repo_dir: Path,
        output_dir: Path,
        repo_root: Path,
        repo_url: Optional[str],
        base_commit: Optional[str],
        prep_log_path: Optional[Path],
        post_prep_hook: Optional[Callable[[], None]],
        shared_cache: bool,
    ) -> TResult:
        """已持有 C-11 并发锁后的实际作答流程。

        9 步骨架：
        1. _get_agent(repo_root)  # hook #1
        2. setup_repo / 复用 worktree（同构）
        3. post_prep_hook() 回调（best-effort）
        4. print 启动消息（用 hook #2+#3）
        5. agent.run()  # 同构（Step 3 起，方法名从 run_with_retry 改为 run）
        6. _post_invoke_brand_hook()  # hook #5
        7. write_workspace_state + write_snapshot_meta（同构）
        8. print 成功/失败（用 hook #2）
        9. finally cleanup_worktree（同构）
        """
        agent = self._get_agent(repo_root)

        # Step 1: 备仓（同构——检查 .git / setup_repo / 失败返回 Result）
        if repo_url and base_commit:
            if (repo_dir / ".git").exists():
                # C-03 幂等跳过：worktree 已就绪（如断点续跑/预建）
                print(f"    {self._log_tag()} 仓库已就绪，复用：{repo_dir}")
                self._log_prep(prep_log_path, f"仓库已就绪，复用（跳过 setup_repo）：{repo_dir}")
            else:
                print(f"    {self._log_tag()} 准备仓库：{repo_url} @ {base_commit} -> {repo_dir}")
                self._log_prep(prep_log_path, f"开始备仓：{repo_url} @ {base_commit} -> {repo_dir}")
                try:
                    agent.environment.setup_repo(
                        repo_url=repo_url,
                        repo_dir=repo_dir,
                        base_commit=base_commit,
                        experiment_id=instance_id,
                        use_shared_cache=shared_cache,
                    )
                    self._log_prep(
                        prep_log_path,
                        "备仓成功（共享 mirror/worktree）" if shared_cache else "备仓成功（experiment-local）",
                    )
                except Exception as e:
                    tb = traceback.format_exc()
                    self._log_prep(prep_log_path, f"备仓失败：{e}\n{tb}")
                    return self._make_error_result(
                        instance_id,
                        f"仓库准备失败（详见 {prep_log_path or '备仓日志'}）：{e}",
                    )

        # Step 2: post_prep_hook（best-effort，不阻断）
        if post_prep_hook is not None:
            try:
                post_prep_hook()
            except Exception as e:  # noqa: BLE001
                print(f"    [warn] 备仓后回调执行失败（best-effort，不阻断作答）：{e}")

        # Step 3: print 启动消息（用 hook _log_tag + _start_message）
        print(f"    {self._log_tag()} {self._start_message()}...")
        print(f"    {self._log_tag()} 模型：{self.model}")
        print(f"    {self._log_tag()} 超时：{self.timeout}s")
        print(f"    {self._log_tag()} 仓库：{repo_dir}")
        print(f"    {self._log_tag()} 输出：{output_dir}")

        try:
            # Step 4: 调 brand Agent（同构）
            # Step 3 重构后 BaseAgent 公开方法名是 `run()`（不是 Step 2 时的
            # `run_with_retry()`），三个 thin agent (Kimi/Qwen/Mimo) 都继承
            # 自 BaseAgent，这里统一通过 `agent.run()` 调用。
            result = agent.run(
                instance_id=instance_id,
                issue_path=issue_path,
                ca_prompt_path=ca_prompt_path,
                repo_dir=repo_dir,
                output_dir=output_dir,
                timeout=self.timeout,
            )

            # Step 5: brand 特殊步骤（mimo D10/D4 在这里）
            # 注意：parse_result 不传（agent 内部已解析，外部 hook 不必重复）
            self._post_invoke_brand_hook(
                agent=agent,
                repo_dir=repo_dir,
                base_commit=base_commit,
                output_dir=output_dir,
                parse_result=None,
            )

            # Step 6: write workspace_state + write_snapshot_meta（同构）
            state_path = output_dir / "workspace-state.json"
            retention = os.environ.get("WORKSPACE_RETENTION", "ephemeral")
            state = agent.environment.write_workspace_state(
                repo_dir, state_path, retention=retention, adapter=self.name
            )
            if retention == "snapshot":
                # C-06：写入实例子目录，避免多实例 snapshot 元数据互相覆盖
                from .repo import write_snapshot_meta as _ar_write_snapshot_meta
                _ar_write_snapshot_meta(repo_dir, instance_id, state.get("commit"))

            # Step 7: print 成功/失败（用 hook _log_tag）
            if result.success:
                print(
                    f"    {self._log_tag()} 执行成功（{result.elapsed_seconds:.1f}s），"
                    f"补丁：{result.patch_path}"
                )
            else:
                print(
                    f"    {self._log_tag()} 执行失败：{result.error}（{result.elapsed_seconds:.1f}s）"
                )
            return result
        finally:
            # Step 8: cleanup_worktree（同构——重点实验 retention=snapshot 不清理）
            if shared_cache and os.environ.get("WORKSPACE_RETENTION", "ephemeral") != "snapshot":
                from .repo import _shared_mirror_path as _ar_shared_mirror_path
                mirror = _ar_shared_mirror_path(repo_root, repo_url) if repo_url else None
                agent.environment.cleanup_worktree(repo_dir, mirror=mirror)

    # ──────────────────────────────────────────────────────────
    # 工具方法
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _log_prep(log_path: Optional[Path], message: str) -> None:
        """把备仓步骤追加写入独立日志（写入失败不影响主流程）。"""
        if not log_path:
            return
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as f:
                f.write(
                    f"===== {datetime.now(timezone.utc).isoformat()} =====\n"
                    f"{message}\n\n"
                )
        except Exception:  # noqa: BLE001
            pass

    def post_check(self, ctx: Any, output_dir: Path) -> bool:
        """产物落地校验（品牌中立默认实现）。

        v0.1.5+ · SPEC-remove-stages-s4-adapter-20260806 Commit 4：
        从原 AnswerAdapter.post_check() 迁移到 BaseAgentRunner。
        检查 .pred 文件是否在标准布局下落地。
        """
        from .artifacts import layout as _artifacts_layout  # noqa: PLC0415
        pred_path, _ = _artifacts_layout(ctx)
        return pred_path.exists()

    def diagnose_failure(self, ctx: Any, output_dir: Path) -> str:
        """brand 失败诊断（品牌中立默认实现）。

        v0.1.5+ · SPEC-remove-stages-s4-adapter-20260806 Commit 4：
        从原 AnswerAdapter.diagnose_failure() 迁移到 BaseAgentRunner。

        v0.2.0+ · SPEC-modularization-round2-20260806 C2（A2 修复）：
        旧实现硬编码 agent/kimi-run.log，qwen（qwen-stream.jsonl）/
        mimo（mimo-stream.jsonl）失败时读不到任何作答日志，诊断恒为空。
        现泛化为扫 task_dir/agent/ 下全部 *.log + *.jsonl（按名排序，
        自动覆盖任何 brand 的日志命名），再附 S4 阶段固定日志。
        brand 子类仍可 override 加专属诊断。
        """
        from .artifacts import _tail_lines  # noqa: PLC0415
        task_dir = Path(ctx.task_dir)
        candidates: list[Path] = []
        agent_dir = task_dir / "agent"
        if agent_dir.is_dir():
            candidates += sorted(agent_dir.glob("*.log"))
            candidates += sorted(agent_dir.glob("*.jsonl"))
        candidates += [
            task_dir / "logs" / "S4_repo_prep.log",
            task_dir / "logs" / "S4_solve.log",
        ]
        parts = []
        seen: set[Path] = set()
        for log in candidates:
            if log in seen:
                continue
            seen.add(log)
            tail = _tail_lines(log)
            if tail:
                parts.append(f"--- {log.name} 尾部 ---\n{tail}")
        return "\n".join(parts) if parts else "（无可用日志）"

    def get_status(self) -> dict:
        """获取适配器状态。"""
        if self._agent:
            return self._agent.get_status()
        return {
            "model": self.model,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "initialized": False,
        }
