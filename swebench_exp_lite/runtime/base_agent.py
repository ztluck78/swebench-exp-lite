"""BaseAgent：3 个 Agent 的共同骨架（DESIGN Step 3）。

3 个 adapter（kimi / qwen / mimo）的 `*Agent.run()` 之前是 ~700 行同构代码
+ 7 步骨架（验证 config / 准备 workspace / 构造 prompt / 调 CLI / 提 patch /
写产物 / collect 产物）。抽到基类后 3 thin agent 只剩 ~30-80 行
+ 5 hook override。

5 hook（差异化点）：
- `_invoke_cli(prompt, repo_dir, log_path, timeout, model)` — abstract 必实现，
  调 brand CLI 子进程并返 (raw_stdout, returncode) 或 proc
- `_parse_output(raw_stdout, log_path)` — 解析 CLI 输出（kimi/qwen 返 None；
  mimo 解析 NDJSON 返 MimoJsonParseResult）
- `_pre_invoke_brand_hook(...)` — mimo 记录 base_commit（D10 防御前置）
- `_post_invoke_brand_hook(...)` — mimo D10 detect + D4 cleanup
- `_make_error_result(instance_id, error, **kwargs)` — 失败时构造 Result

使用方式：
    from swebench_exp_lite.runtime.base_agent import BaseAgent
    
    class KimiAgent(BaseAgent[RunResult]):
        name = "kimi-agent"
        result_class = RunResult
        
        def __init__(self, config):
            self.config = config
            self.environment = KimiEnvironment(...)
            self.prompt_builder = KimiPromptBuilder()
        
        def _invoke_cli(self, prompt, repo_dir, log_path, timeout, model):
            # 调 kimi CLI 子进程
            ...
            return raw_stdout, returncode
        
        # _parse_output / _pre_invoke / _post_invoke 用默认 no-op
        # _make_error_result override 返 RunResult
"""
from __future__ import annotations

import contextlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Generic, Optional, Tuple, Type, TypeVar

from .artifacts import write_patch, write_pred, write_traj
from .patch import extract_patch_from_repo, extract_patch_from_log
from .protocol import AgentResult


# TResult 泛型：每个 adapter 有自己的 Result 子类（RunResult / QwenResult / MimoResult）
TResult = TypeVar("TResult", bound=AgentResult)

# SPEC-agent-speedup-20260808 G1：phase_timings 落盘文件名（worker 与
# orchestrator 父进程之间的传递载体；父进程读后并入 manifest attempt）。
PHASE_TIMINGS_FILENAME = "s4_phase_timings.json"


@contextlib.contextmanager
def _phase(timings: dict, name: str):
    """记录一个相位的耗时（秒）到 timings[name]。"""
    t0 = time.monotonic()
    try:
        yield
    finally:
        timings[name] = round(time.monotonic() - t0, 3)


class BaseAgent(Generic[TResult]):
    """所有 Agent 的共同骨架——7 步主流程 + 5 hook 容纳差异化。

    3 个 adapter 共用此基类，子类只实现 _invoke_cli 即可。
    TResult 是泛型参数，让 type checker 知道 _make_error_result 返回的子类类型。
    """

    name: str = "base"  # 子类覆盖（"kimi-agent" / "qwen-agent" / "mimo-agent"）
    result_class: Type[TResult] = AgentResult  # 子类覆盖（RunResult / QwenResult / MimoResult）

    def __init__(self, config: Any):
        self.config = config
        # 5 个标准属性（子类可覆盖；通常在 __init__ 里设置）
        self.environment: Any = None
        self.prompt_builder: Any = None
        self.session_manager: Any = None  # kimi 独有；其他 brand 默认 None
        # session_dir 检查函数（默认 no-op；kimi override）
        self._ensure_session_dir: Optional[Callable[[], None]] = None

    # ──────────────────────────────────────────────────────────
    # 5 hook（差异化点）
    # ──────────────────────────────────────────────────────────

    def _invoke_cli(
        self,
        prompt: str,
        repo_dir: Path,
        log_path: Path,
        timeout: int,
        model: str,
    ) -> Tuple[str, int]:
        """调 brand CLI 子进程。**abstract**，子类必实现。

        Args:
            prompt: 构造好的 prompt 字符串
            repo_dir: 仓库目录
            log_path: CLI 输出写到这个文件
            timeout: 超时秒数
            model: 模型名称

        Returns:
            (raw_stdout, returncode) — returncode 是子进程退出码
        """
        raise NotImplementedError(f"{type(self).__name__}._invoke_cli not implemented")

    def _parse_output(self, raw_stdout: str, log_path: Path) -> Any:
        """解析 CLI 输出（可选 hook）。kimi/qwen 默认 None；mimo 解析 NDJSON。

        Returns:
            解析结果对象（mimo 返 MimoJsonParseResult；kimi/qwen 返 None）
        """
        return None

    def _pre_invoke_brand_hook(
        self,
        repo_dir: Path,
        timeout: int,
        model: str,
    ) -> dict:
        """调 CLI 之前的 brand 特殊步骤（mimo 用：记录 base_commit 供 D10 防御）。

        Returns:
            dict: 上下文状态（mimo 返 {"base_commit": "abc"}；kimi/qwen 返 {}）
        """
        return {}

    def _post_invoke_brand_hook(
        self,
        repo_dir: Path,
        ctx_state: dict,
        raw_stdout: str,
        log_path: Path,
        parse_result: Any,
    ) -> None:
        """调 CLI 之后的 brand 特殊步骤（mimo 用：D10 detect + reset + D4 cleanup）。

        Args:
            repo_dir: 仓库目录
            ctx_state: _pre_invoke_brand_hook 返回的状态（mimo 用 base_commit）
            raw_stdout: CLI 输出
            log_path: log 文件路径
            parse_result: _parse_output 返回的对象
        """
        pass  # 默认 no-op

    def _make_error_result(self, instance_id: str, error: str, **kwargs) -> TResult:
        """失败时构造 Result。子类覆盖返自己的 Result 子类。"""
        return AgentResult(success=False, instance_id=instance_id, error=error)

    def _log_filename(self) -> str:
        """CLI 输出日志文件名（基类默认 run.log）。"""
        return "run.log"

    def _rescue_pred_on_failure(
        self,
        *,
        repo_dir: Path,
        output_dir: Path,
        instance_id: str,
        model: str,
    ) -> None:
        """G2（SPEC-agent-speedup-20260808）：失败路径的 .pred 兜底救援。

        场景：agent 已在 worktree 留下真实改动（git diff 非空），但运行
        在写产物之前/之中崩了（CLI 超时、调用异常等），整轮成果被丢弃
        （2026-08-04 astroid-1196 跑了 472s 却颗粒无收即此类）。
        此处从 worktree diff 提取补丁写出 pred 并标记 rescued=true，
        让 S5/S6 仍能对这次尝试打分。

        守卫：pred 已存在且 model_patch 非空时不覆盖；agent 未产生任何
        改动（如 validate/prompt 阶段就失败）时不写。任何异常吞掉。
        """
        try:
            pred_path = output_dir / instance_id / f"{instance_id}.pred"
            if pred_path.exists():
                existing = json.loads(pred_path.read_text(encoding="utf-8"))
                if (existing.get("model_patch") or "").strip():
                    return  # 已有有效 pred，不覆盖
            patch = extract_patch_from_repo(repo_dir)
            if patch:
                write_pred(
                    output_dir, instance_id, model, patch,
                    extra={"rescued": True},
                )
        except Exception:  # noqa: BLE001 - 救援失败绝不放大原始错误
            pass

    # ──────────────────────────────────────────────────────────
    # 7 步主流程（基类实现，子类不覆盖）
    # ──────────────────────────────────────────────────────────

    def run(
        self,
        instance_id: str,
        issue_path: Path,
        ca_prompt_path: Path,
        repo_dir: Path,
        output_dir: Path,
        timeout: Optional[int] = None,
    ) -> TResult:
        """执行 Agent 任务（orchestrator 调用入口）。

        7 步主流程：
        1. 验证 config
        2. 准备 workspace
        3. 构造 prompt
        4. pre_invoke hook（mimo 记录 base_commit）
        5. _invoke_cli（调 brand CLI）
        6. _parse_output（kimi/qwen no-op；mimo 解析 NDJSON）
        7. post_invoke hook（mimo D10/D4）
        + 提 patch + 写产物 + collect 产物
        """
        timeout = timeout or self.config.timeout
        start_time = time.time()
        # G1 拆相计时：每个 return 路径都必须经 _ret() 挂载 timings
        timings: dict[str, float] = {}

        def _ret(result: TResult) -> TResult:
            try:
                # 挂活引用而非快照：return 后 enclosing `with _phase` 退出时
                # 会把当前相位补记进同一 dict，调用方读到的是完整版本
                result.phase_timings = timings
            except Exception:  # noqa: BLE001 - 计时挂载绝不影响主流程
                pass
            return result

        try:
            # Step 1: 验证 config
            with _phase(timings, "validate"):
                errors = self.config.validate()
                if errors:
                    err_result = self._make_error_result(
                        instance_id,
                        f"配置错误：{'; '.join(errors)}",
                    )
                else:
                    err_result = None
                # Step 1.5: 检查 session_dir（kimi 独有，其他 brand 默认 no-op）
                if err_result is None and self._ensure_session_dir is not None:
                    try:
                        self._ensure_session_dir()
                    except RuntimeError as e:
                        err_result = self._make_error_result(
                            instance_id,
                            f"session_dir 错误：{e}",
                        )
            if err_result is not None:
                return _ret(err_result)

            # Step 2: 准备 workspace
            with _phase(timings, "workspace"):
                dirs = self.environment.prepare_workspace(output_dir)

            # Step 3: 构造 prompt
            with _phase(timings, "prompt"):
                try:
                    prompt = self.prompt_builder.build_prompt(
                        issue_path=issue_path,
                        ca_prompt_path=ca_prompt_path,
                    )
                except Exception as e:
                    return _ret(self._make_error_result(
                        instance_id,
                        f"提示词构造失败：{e}",
                    ))

            # Step 4: pre_invoke hook（mimo 记录 base_commit 供 D10 防御）
            model = getattr(self.config, "model", None) or "default"
            with _phase(timings, "pre_invoke"):
                ctx_state = self._pre_invoke_brand_hook(
                    repo_dir=repo_dir, timeout=timeout, model=model,
                )

            # Step 5: 调 brand CLI
            log_path = dirs["agent"] / self._log_filename()
            with _phase(timings, "invoke_cli"):
                try:
                    raw_stdout, returncode = self._invoke_cli(
                        prompt=prompt,
                        repo_dir=repo_dir,
                        log_path=log_path,
                        timeout=timeout,
                        model=model,
                    )
                except subprocess.TimeoutExpired:
                    self._rescue_pred_on_failure(
                        repo_dir=repo_dir, output_dir=output_dir,
                        instance_id=instance_id, model=model,
                    )
                    return _ret(self._make_error_result(
                        instance_id,
                        f"超时（{timeout}秒）",
                        elapsed_seconds=time.time() - start_time,
                    ))
                except Exception as e:
                    self._rescue_pred_on_failure(
                        repo_dir=repo_dir, output_dir=output_dir,
                        instance_id=instance_id, model=model,
                    )
                    return _ret(self._make_error_result(
                        instance_id,
                        f"{self.name} 调用失败：{e}",
                        elapsed_seconds=time.time() - start_time,
                    ))

            # Step 6: 解析 output（kimi/qwen no-op；mimo 解析 NDJSON）
            with _phase(timings, "parse_output"):
                parse_result = self._parse_output(raw_stdout, log_path)

            # Step 7: post_invoke hook（mimo D10/D4）
            with _phase(timings, "post_invoke"):
                self._post_invoke_brand_hook(
                    repo_dir=repo_dir,
                    ctx_state=ctx_state,
                    raw_stdout=raw_stdout,
                    log_path=log_path,
                    parse_result=parse_result,
                )

            with _phase(timings, "artifacts"):
                # 提 patch（基类统一——从 git diff + log 解析回退）
                patch = extract_patch_from_repo(repo_dir)
                if not patch:
                    # kimi/qwen 走 log 解析回退
                    log_content = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
                    if log_content:
                        patch = extract_patch_from_log(log_content)
                    # mimo 走 parse_result 路径（post_invoke 之后可能改了 log）
                    if not patch and parse_result is not None and hasattr(parse_result, "as_traj_extra"):
                        # mimo 已经在 _post_invoke_brand_hook 把 patch 提走了（D10 之前）
                        # 如果还是空，可能是 parse_result 含 patch
                        patch = getattr(parse_result, "patch", None)

                # 写产物（基类统一——用 artifacts.write_pred / write_traj / write_patch）
                write_patch(output_dir, instance_id, patch or "")
                self._write_pred_and_traj(
                    output_dir, instance_id, model, log_path, returncode,
                    start_time, parse_result, patch,
                )

                # collect 产物
                result = self.environment.collect_artifacts(
                    output_dir=output_dir,
                    instance_id=instance_id,
                    model=model,
                )
                result.elapsed_seconds = time.time() - start_time
                result.exit_code = returncode
                return _ret(result)

        except subprocess.TimeoutExpired:
            self._rescue_pred_on_failure(
                repo_dir=repo_dir, output_dir=output_dir,
                instance_id=instance_id,
                model=getattr(self.config, "model", None) or "default",
            )
            return _ret(self._make_error_result(
                instance_id,
                f"超时（{timeout}秒）",
                elapsed_seconds=time.time() - start_time,
            ))
        except Exception as e:
            self._rescue_pred_on_failure(
                repo_dir=repo_dir, output_dir=output_dir,
                instance_id=instance_id,
                model=getattr(self.config, "model", None) or "default",
            )
            return _ret(self._make_error_result(
                instance_id,
                str(e),
                elapsed_seconds=time.time() - start_time,
            ))
        finally:
            # G1：无论成败，把拆相计时落盘到产物目录（父进程读后并入 manifest）。
            # best-effort：目录不可写等异常吞掉，绝不影响主流程。
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / PHASE_TIMINGS_FILENAME).write_text(
                    json.dumps(
                        {
                            "instance_id": instance_id,
                            "phase_timings": timings,
                            "elapsed_seconds": round(time.time() - start_time, 3),
                            "written_at": time.time(),
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
            except Exception:  # noqa: BLE001
                pass

    def _write_pred_and_traj(
        self,
        output_dir: Path,
        instance_id: str,
        model: str,
        log_path: Path,
        returncode: int,
        start_time: float,
        parse_result: Any,
        patch: Optional[str],
    ) -> None:
        """写 .pred 和 .traj。基类提供 kimi/qwen 默认；mimo override 含 mimo 特有字段。"""
        write_pred(output_dir, instance_id, model, patch or "")
        write_traj(
            output_dir, instance_id, model,
            adapter=self.name,
            exit_code=returncode,
            log_path=str(log_path),
            elapsed_seconds=time.time() - start_time,
        )
