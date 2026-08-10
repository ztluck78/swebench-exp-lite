"""出题模块 · 数据层（TaskBuilder）

DB 直取：从 LiteDB 一次查询拿到 TaskInstance 所需的全部字段，不做任何外部采集
或预处理。若 instance_id 不在 DB 中，抛出 KeyError 并提示先运行 ./start.sh
下载题库（或手动放置 database/swe_bench.db）。

移植自主仓 tools/assessment-builder/builder.py：剔除 sys.path hack（包已安装）、
fast prompt 整链（choose_prompt_mode / FAST_PATCH_SIZE_LIMIT / prompt_mode 参数），
统一 full 8 步 prompt。

对齐真实 API：
- ``LiteDB.get(iid)``           返回 LiteRow（含 problem_statement / patch / test_patch / F2P / P2P 等大字段）
- ``LiteDB.eval_estimate(iid)`` 返回 dict，键为 image_name / mode / namespace / cache_level /
                                 recommended_timeout / repo_url / ssh_url / instance_url / exec_difficulty …
"""
from __future__ import annotations

import json
import os

from ..db.query import LiteDB
from .models import TaskInstance
from .renderer import (
    dumps_jsonl,
    render_agent_data,
    render_agent_prompt,
    render_review,
)


# ---------------------------------------------------------------------------
# 文件名命名规则（集中在这一处维护）
# ---------------------------------------------------------------------------
# 给 code agent 的输入文件统一加 `ca-` 前缀（code agent 缩写），便于一眼区分：
#   ca-issue.json       -> Agent 输入数据（7 字段）
#   ca-task-prompt.md   -> Agent 任务指令（8 步）
# 与之相对：review.md（出题人审阅版，含答案）、task.jsonl（harness 评分用，含答案），
# 这两个不带前缀，且绝不能交给 code agent，以免泄露答案。
CA_PREFIX = "ca-"


class TaskBuilder:
    """出题主类：DB 查询 -> TaskInstance -> 双版本文件。

    使用
    ----
        builder = TaskBuilder()                       # 默认 database/swe_bench.db
        task = builder.build("pylint-dev__astroid-1196")
        paths = builder.render(task, "output/")
    """

    def __init__(self, db_path=None):
        """
        Parameters
        ----------
        db_path : str | Path | None
            指定 LiteDB 路径；None 时用 database.query.DEFAULT_DB_PATH（仓库内默认库）。
        """
        self.db_path = db_path

    # ------------------------------------------------------------------
    # 构建（DB 直取）
    # ------------------------------------------------------------------
    def build(self, instance_id: str) -> TaskInstance:
        """从 DB 查询并构建 TaskInstance。

        不在 DB 中的任务会抛出 KeyError（由 LiteDB.get 产生），提示用户先入库。
        """
        return self._build_from_db(instance_id)

    def _build_from_db(self, instance_id: str) -> TaskInstance:
        """从 LiteDB 一次查询获取全部字段。"""
        db = LiteDB(self.db_path)

        # 一次查询拿大字段（patch / test_patch / F2P / P2P / problem_statement）
        row = db.get(instance_id)

        # 一站式拿镜像策略 + 难度 + URL（x86_64 / arm64 各一次）
        est_x86 = db.eval_estimate(instance_id, arch="x86_64")
        est_arm = db.eval_estimate(instance_id, arch="arm64")

        # 解析 JSON 字段（DB 中存的是字符串型 JSON）
        f2p = json.loads(row["fail_to_pass"]) if row["fail_to_pass"] else []
        p2p = json.loads(row["pass_to_pass"]) if row["pass_to_pass"] else []

        # 直接填充 TaskInstance，无需任何采集/处理/校验
        return TaskInstance(
            instance_id=row["instance_id"],
            repo=row["repo"],
            version=row["version"],
            language=row["language"],
            created_at=row["created_at"],
            split=row["split"],
            problem_statement=row["problem_statement"],
            hints_text=row["hints_text"],
            base_commit=row["base_commit"],
            environment_setup_commit=row["environment_setup_commit"],
            fail_to_pass=f2p,
            pass_to_pass=p2p,
            gold_patch=row["patch"],
            test_patch=row["test_patch"],
            f2p_count=row["f2p_count"],
            p2p_count=row["p2p_count"],
            difficulty=row["exec_difficulty_class"],   # 自动派生难度
            patch_size=row["patch_size"],
            test_patch_size=row["test_patch_size"],
            # 出题辅助（004 迁移新增，当前可能为 NULL，按现状使用）
            key_files_hint=row["key_files_hint"],
            repro_snippet=row["repro_snippet"],
            difficulty_human=row["difficulty_human"],
            # 环境镜像（eval_estimate 提供）
            image_x86_64=est_x86["image_name"],
            image_arm64=est_arm["image_name"],
            image_mode_x86_64=est_x86["mode"],
            image_mode_arm64=est_arm["mode"],
            namespace_x86_64=est_x86["namespace"],
            namespace_arm64=est_arm["namespace"],
            cache_level_x86_64=est_x86["cache_level"],
            cache_level_arm64=est_arm["cache_level"],
            recommended_timeout=est_x86["recommended_timeout"],
            # 外部线索
            repo_url=est_x86["repo_url"],
            ssh_url=est_x86["ssh_url"],
            instance_url=est_x86["instance_url"],
        )

    # ------------------------------------------------------------------
    # 渲染 + 导出（输出层）
    # ------------------------------------------------------------------
    def render(
        self,
        task: TaskInstance,
        output_dir: str,
        *,
        include_jsonl: bool = True,
        only_review: bool = False,
        only_agent: bool = False,
    ) -> dict:
        """从同一数据源生成双版本文件（统一 full 8 步 prompt）。

        Parameters
        ----------
        task : TaskInstance
            由 ``build()`` 产出的题目实例。
        output_dir : str
            输出根目录；实际文件写在 ``{output_dir}/{instance_id}/`` 下。
        include_jsonl : bool
            是否额外生成标准 jsonl 行（task.jsonl）。默认 True（约定 4 文件）。
        only_review : bool
            只生成人工审阅版（review.md）。
        only_agent : bool
            只生成 Agent 做题版（issue.json + task-prompt.md）。

        Returns
        -------
        dict : 形如 {"review": path, "issue": path, "prompt": path, "jsonl": path}
               未生成的文件对应值为 None。
        """
        if only_review and only_agent:
            raise ValueError("--only-review 与 --only-agent 互斥，不能同时指定")

        task_dir = os.path.join(output_dir, task.instance_id)
        os.makedirs(task_dir, exist_ok=True)

        paths: dict = {"review": None, "issue": None, "prompt": None, "jsonl": None}

        if not only_agent:
            review_path = os.path.join(task_dir, "review.md")
            with open(review_path, "w", encoding="utf-8") as f:
                f.write(render_review(task))
            paths["review"] = review_path

        if not only_review:
            # ca- = code agent：这两个文件是给 code agent 的输入，统一加 CA_PREFIX 前缀
            issue_data = render_agent_data(task)
            issue_path = os.path.join(task_dir, f"{CA_PREFIX}issue.json")
            with open(issue_path, "w", encoding="utf-8") as f:
                json.dump(issue_data, f, indent=2, ensure_ascii=False)
            paths["issue"] = issue_path
            # L5 修复：移除重复 issue.json 写入（P2 修复引入的"兼容旧版 run-kimi.sh"，
            # 现 run-kimi.sh 已退役，agent_process_evaluator/loader.py:254 仍
            # 兼容读 issue.json，但新数据写在 ca-issue.json — 单一真相源更清晰）

            prompt_path = os.path.join(task_dir, f"{CA_PREFIX}task-prompt.md")
            with open(prompt_path, "w", encoding="utf-8") as f:
                f.write(render_agent_prompt(task, task_dir=task_dir))
            paths["prompt"] = prompt_path

        if include_jsonl and not only_review:
            jsonl_path = os.path.join(task_dir, "task.jsonl")
            with open(jsonl_path, "w", encoding="utf-8") as f:
                f.write(dumps_jsonl(task) + "\n")
            paths["jsonl"] = jsonl_path

        return paths

    def build_and_render(
        self,
        instance_id: str,
        output_dir: str,
        *,
        include_jsonl: bool = True,
        only_review: bool = False,
        only_agent: bool = False,
    ) -> dict:
        """便捷方法：构建并立即渲染。返回 render() 的文件路径 dict。"""
        task = self.build(instance_id)
        return self.render(
            task,
            output_dir,
            include_jsonl=include_jsonl,
            only_review=only_review,
            only_agent=only_agent,
        )
