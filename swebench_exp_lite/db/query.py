"""只读查询接口：SWE-bench 元数据库（规范化 5 表 + 兼容视图）。

移植自 swebench-exercise-platform/database/query.py（@ 63b7b30）：
公开 API 全量保留；本仓不带 build/validate 脚本（DB 由 start.sh 下载或手动放置，
重建流程见 GETTING-STARTED.md FAQ）。

典型用法
--------
    from swebench_exp_lite.db.query import LiteDB
    db = LiteDB()  # 默认路径 database/swe_bench.db

    # 1) 全表（轻量：只取元信息列，不拉 patch/test_patch 大字段）
    for row in db.iter_metadata():
        print(row.instance_id, row.repo, row.image_x86_64)

    # 2) 单条
    row = db.get("sqlfluff__sqlfluff-1517")
    print(row.problem_statement)
    print(row.test_patch)

    # 3) 按 repo / split
    rows = db.filter_by_repo("sqlfluff/sqlfluff")
    rows = db.filter_by_split("dev")

    # 4) 全文搜索（FTS5，对 problem_statement + hints_text）
    hits = db.search("NaN")

    # 5) Docker 镜像名
    print(db.docker_image("sqlfluff__sqlfluff-1517"))            # x86_64
    print(db.docker_image("sqlfluff__sqlfluff-1517", "arm64"))   # arm64

    # 6) 仓库与 base image
    print(db.repository("sqlfluff__sqlfluff-1517"))
    print(db.base_image("sqlfluff__sqlfluff-1517", "arm64"))

设计取舍
--------
- 底层走 `v_lite` 兼容视图：把规范化 schema（repositories / tasks / images /
  image_pull_info …）拍平成旧 `instances` 的列名，因此本类的公开 API
  （instance_id / repo / image_x86_64 / image_mode_* / pull_cmd_* …）保持兼容，
  并增加 repo_url / issue_created_at / base_image_* 等首次运行所需元信息；
- 默认不拉 `patch` / `test_patch` 等大字段，避免 SELECT * 拖慢；
- 用 `LiteRow`（sqlite3.Row 子类）保留字段名访问；
- FTS5 走 BM25 排序（默认），关键词支持 `NaN AND fix` 这种组合。
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from . import DEFAULT_DB_PATH


# 列表字段统一按此顺序引用，避免散落字符串
_BASE_COLS = (
    "instance_id", "split", "repo", "repo_url", "ssh_url", "default_branch",
    "version", "base_commit", "environment_setup_commit",
    "language", "created_at", "issue_created_at",
    "instance_url", "exec_difficulty_class",
    "f2p_count", "p2p_count",
    "test_patch_size", "patch_size", "problem_size",
    "key_files_hint", "repro_snippet", "difficulty_human",
    "image_x86_64", "image_arm64",
    "base_image_x86_64", "base_image_arm64",
    "image_mode_x86_64", "image_mode_arm64",
    "image_namespace_x86_64", "image_namespace_arm64",
    "cache_level_x86_64", "cache_level_arm64",
    "pull_cmd_x86_64", "pull_cmd_arm64",
    "build_instructions", "recommended_timeout",
)
_LARGE_COLS = (
    "problem_statement", "hints_text", "patch", "test_patch",
    "fail_to_pass", "pass_to_pass",
)
_ALL_COLS = _BASE_COLS + _LARGE_COLS


# ---------------------------------------------------------------------------
# Row 类型
# ---------------------------------------------------------------------------
class LiteRow(sqlite3.Row):
    """让 sqlite3.Row 既能按列名访问，又能 .image_x86_64 这样用。

    sqlite3.Row 已经支持 `row["col"]` 和 `row[col_index]`；本类只为了
    减少 dict-style 写法的噪音。
    """

    def __getattr__(self, name: str):
        try:
            return self[name]
        except (IndexError, KeyError):
            raise AttributeError(name)


# ---------------------------------------------------------------------------
# 打开连接的工厂：row_factory = LiteRow
# ---------------------------------------------------------------------------
def _connect(db_path: Path) -> sqlite3.Connection:
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(
            f"DB 不存在: {db_path}\n"
            f"请先执行 ./start.sh 下载题库，或手动放置 swe_bench.db\n"
            f"（从 jsonl 重建的高级选项见 GETTING-STARTED.md FAQ）"
        )
    con = sqlite3.connect(str(db_path))
    con.row_factory = LiteRow
    return con


# ---------------------------------------------------------------------------
# LiteDB 主类
# ---------------------------------------------------------------------------
class LiteDB:
    """SWE-bench (test + dev) 的只读查询入口。

    使用方式：
        db = LiteDB()                  # 默认 DB
        db = LiteDB("/tmp/other.db")   # 指定 DB
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        # 不在构造时开连接，每次调用再开（线程安全 + 短连接）

    # ------------------------------------------------------------------
    # 连接管理
    # ------------------------------------------------------------------
    @contextmanager
    def _con(self):
        con = _connect(self.db_path)
        try:
            yield con
        finally:
            con.close()

    # ------------------------------------------------------------------
    # 总量 / 分组统计
    # ------------------------------------------------------------------
    def count(self, split: Optional[str] = None) -> int:
        with self._con() as con:
            if split:
                return con.execute(
                    "SELECT COUNT(*) FROM v_lite WHERE split=?", (split,)
                ).fetchone()[0]
            return con.execute("SELECT COUNT(*) FROM v_lite").fetchone()[0]

    def repos(self, split: Optional[str] = None) -> dict[str, int]:
        """返回 {repo: count}，按 count 降序。"""
        sql = "SELECT repo, COUNT(*) AS n FROM v_lite"
        params: tuple = ()
        if split:
            sql += " WHERE split=?"
            params = (split,)
        sql += " GROUP BY repo ORDER BY n DESC"
        with self._con() as con:
            return {r["repo"]: r["n"] for r in con.execute(sql, params)}

    # ------------------------------------------------------------------
    # 单条 / 过滤
    # ------------------------------------------------------------------
    def get(self, instance_id: str, *, with_large: bool = True) -> LiteRow:
        cols = _ALL_COLS if with_large else _BASE_COLS
        sql = f"SELECT {','.join(cols)} FROM v_lite WHERE instance_id=?"
        with self._con() as con:
            row = con.execute(sql, (instance_id,)).fetchone()
        if row is None:
            raise KeyError(f"instance_id 不在 DB 中: {instance_id}")
        return row

    def filter_by_repo(self, repo: str, *, with_large: bool = False) -> list[LiteRow]:
        cols = _ALL_COLS if with_large else _BASE_COLS
        sql = f"SELECT {','.join(cols)} FROM v_lite WHERE repo=? ORDER BY instance_id"
        with self._con() as con:
            return list(con.execute(sql, (repo,)))

    def filter_by_split(self, split: str, *, with_large: bool = False) -> list[LiteRow]:
        cols = _ALL_COLS if with_large else _BASE_COLS
        sql = f"SELECT {','.join(cols)} FROM v_lite WHERE split=? ORDER BY instance_id"
        with self._con() as con:
            return list(con.execute(sql, (split,)))

    def iter_metadata(self, split: Optional[str] = None) -> Iterator[LiteRow]:
        """只迭代元信息列（不拉大字段），适合批量实验前的遍历。"""
        sql = f"SELECT {','.join(_BASE_COLS)} FROM v_lite"
        params: tuple = ()
        if split:
            sql += " WHERE split=?"
            params = (split,)
        sql += " ORDER BY split, repo, instance_id"
        with self._con() as con:
            for row in con.execute(sql, params):
                yield row

    # ------------------------------------------------------------------
    # 全文搜索（FTS5）
    # ------------------------------------------------------------------
    def search(
        self,
        keyword: str,
        *,
        split: Optional[str] = None,
        limit: int = 20,
    ) -> list[LiteRow]:
        """对 `problem_statement` + `hints_text` 做 FTS5 搜索。

        支持 FTS5 表达式，例如：
            "NaN"           — 单词
            '"double quote"' — 精确短语
            "NaN OR fix"    — 布尔组合
            "NaN AND fix"   — 必同时出现
        """
        sql = (
            "SELECT v.* FROM tasks_fts f "
            "JOIN tasks t ON t.rowid = f.rowid "
            "JOIN v_lite v ON v.instance_id = t.task_id "
            "WHERE tasks_fts MATCH ?"
        )
        params: list = [keyword]
        if split:
            sql += " AND t.split = ?"
            params.append(split)
        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)
        with self._con() as con:
            return list(con.execute(sql, params))

    # ------------------------------------------------------------------
    # 仓库 clone / checkout 元信息
    # ------------------------------------------------------------------
    def repository(self, instance_id: str) -> dict:
        """返回首次 clone 与 checkout 所需的仓库元信息。"""
        sql = (
            "SELECT repo, repo_url, default_branch, base_commit, "
            "environment_setup_commit, version "
            "FROM v_lite WHERE instance_id=?"
        )
        with self._con() as con:
            row = con.execute(sql, (instance_id,)).fetchone()
        if row is None:
            raise KeyError(f"instance_id 不在 DB 中: {instance_id}")
        return dict(row)

    def repo_url(self, instance_id: str) -> str:
        """返回可直接用于 ``git clone`` 的 GitHub URL。"""
        return self.repository(instance_id)["repo_url"]

    # ------------------------------------------------------------------
    # Docker 镜像名（这是用户最常问的）
    # ------------------------------------------------------------------
    @staticmethod
    def _arch_column(arch: str, x86_col: str, arm_col: str) -> str:
        if arch == "x86_64":
            return x86_col
        if arch == "arm64":
            return arm_col
        raise ValueError(f"arch 仅支持 'x86_64' / 'arm64'，收到 {arch!r}")

    def docker_image(self, instance_id: str, arch: str = "x86_64") -> str:
        col = self._arch_column(arch, "image_x86_64", "image_arm64")
        with self._con() as con:
            row = con.execute(
                f"SELECT {col} AS img FROM v_lite WHERE instance_id=?", (instance_id,)
            ).fetchone()
        if row is None:
            raise KeyError(instance_id)
        return row["img"]

    def base_image(self, instance_id: str, arch: str = "x86_64") -> str:
        """返回 harness 本地构建使用的 base image key。"""
        col = self._arch_column(arch, "base_image_x86_64", "base_image_arm64")
        with self._con() as con:
            row = con.execute(
                f"SELECT {col} AS img FROM v_lite WHERE instance_id=?", (instance_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"instance_id 不在 DB 中: {instance_id}")
        return row["img"]

    def docker_images(self, split: Optional[str] = None) -> list[tuple[str, str, str]]:
        """返回 [(instance_id, image_x86_64, image_arm64), ...]"""
        sql = "SELECT instance_id, image_x86_64, image_arm64 FROM v_lite"
        params: tuple = ()
        if split:
            sql += " WHERE split=?"
            params = (split,)
        sql += " ORDER BY instance_id"
        with self._con() as con:
            return [tuple(r) for r in con.execute(sql, params)]

    # ------------------------------------------------------------------
    # 镜像获取方式（拉取 vs 本地构建）
    # ------------------------------------------------------------------
    def acquisition(self, instance_id: str, arch: str = "x86_64") -> dict:
        """返回某 instance 在某 arch 下的获取方式。

        Returns
        -------
        dict:
            {
                'mode':          'pull' or 'build',
                'pull_cmd':      可执行命令（如可拉）或 None，
                'image_name':    完整的 instance image tag，
                'base_image':    harness 本地构建使用的 base image key，
                'namespace':     该架构下推荐的 Docker namespace (003 增)，
                'cache_level':   该架构下推荐的 harness --cache_level (003 增)，
                'recommended_timeout': 推荐超时秒数 (003 增)，
                'build_note':    如果 mode='build'，给用户看的提示
            }
        """
        mode_col = self._arch_column(
            arch, "image_mode_x86_64", "image_mode_arm64"
        )
        cmd_col = self._arch_column(arch, "pull_cmd_x86_64", "pull_cmd_arm64")
        image_col = self._arch_column(arch, "image_x86_64", "image_arm64")
        base_col = self._arch_column(
            arch, "base_image_x86_64", "base_image_arm64"
        )
        ns_col = self._arch_column(
            arch, "image_namespace_x86_64", "image_namespace_arm64"
        )
        cache_col = self._arch_column(
            arch, "cache_level_x86_64", "cache_level_arm64"
        )

        sql = (
            f"SELECT {mode_col} AS mode, {cmd_col} AS pull_cmd, "
            f"{image_col} AS image_name, {base_col} AS base_image, "
            f"{ns_col} AS namespace, {cache_col} AS cache_level, "
            f"recommended_timeout, build_instructions "
            f"FROM v_lite WHERE instance_id=?"
        )
        with self._con() as con:
            row = con.execute(sql, (instance_id,)).fetchone()
        if row is None:
            raise KeyError(f"instance_id 不在 DB 中: {instance_id}")

        mode = row["mode"]
        return {
            "mode":       mode,
            "pull_cmd":   row["pull_cmd"],
            "image_name": row["image_name"],
            "base_image": row["base_image"],
            "namespace":  row["namespace"],
            "cache_level": row["cache_level"],
            "recommended_timeout": row["recommended_timeout"],
            "build_note": row["build_instructions"] if mode == "build" else None,
        }

    def acquisitions(self, split: Optional[str] = None) -> list[dict]:
        """批量返回所有 instance 的获取方式，适合写预处理脚本。

        Returns: list of dict，每条包含 instance_id, arch, mode, pull_cmd,
        image_name, base_image。
        """
        sql = """
        SELECT instance_id,
               'x86_64' AS arch, image_mode_x86_64 AS mode,
               pull_cmd_x86_64 AS pull_cmd, image_x86_64 AS image_name,
               base_image_x86_64 AS base_image
        FROM v_lite
        UNION ALL
        SELECT instance_id,
               'arm64' AS arch, image_mode_arm64 AS mode,
               pull_cmd_arm64 AS pull_cmd, image_arm64 AS image_name,
               base_image_arm64 AS base_image
        FROM v_lite
        """
        params: tuple = ()
        if split:
            sql = (
                "SELECT * FROM ("
                "SELECT instance_id, 'x86_64' AS arch, image_mode_x86_64 AS mode, "
                "pull_cmd_x86_64 AS pull_cmd, image_x86_64 AS image_name, base_image_x86_64 AS base_image "
                "FROM v_lite WHERE split=? "
                "UNION ALL "
                "SELECT instance_id, 'arm64' AS arch, image_mode_arm64 AS mode, "
                "pull_cmd_arm64 AS pull_cmd, image_arm64 AS image_name, base_image_arm64 AS base_image "
                "FROM v_lite WHERE split=?"
                ") ORDER BY instance_id, arch"
            )
            params = (split, split)
        with self._con() as con:
            return [dict(r) for r in con.execute(sql, params)]

    def acquisition_summary(self) -> dict[str, dict[str, int]]:
        """按 (arch, mode) 统计 Lite 中有多少 instance 各是什么获取方式。

        Returns: {'x86_64': {'pull': 323, 'build': 0}, 'arm64': {'pull': 0, 'build': 323}}
        """
        sql = """
        SELECT
            SUM(CASE WHEN image_mode_x86_64='pull'  THEN 1 ELSE 0 END) AS x86_pull,
            SUM(CASE WHEN image_mode_x86_64='build' THEN 1 ELSE 0 END) AS x86_build,
            SUM(CASE WHEN image_mode_arm64='pull'   THEN 1 ELSE 0 END) AS arm_pull,
            SUM(CASE WHEN image_mode_arm64='build'  THEN 1 ELSE 0 END) AS arm_build
        FROM v_lite
        """
        with self._con() as con:
            row = con.execute(sql).fetchone()
        return {
            "x86_64": {"pull": row["x86_pull"], "build": row["x86_build"]},
            "arm64":  {"pull": row["arm_pull"],  "build": row["arm_build"]},
        }

    # ------------------------------------------------------------------
    # 003 迁移新增：任务定位 / 难度分级 / 仓库 URL
    # ------------------------------------------------------------------
    def instance_url(self, instance_id: str) -> str | None:
        """返回 instance 对应的 GitHub Issue 链接（如有）。"""
        with self._con() as con:
            row = con.execute(
                "SELECT instance_url FROM v_lite WHERE instance_id=?",
                (instance_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"instance_id 不在 DB 中: {instance_id}")
        return row["instance_url"]

    def ssh_url(self, instance_id: str) -> str | None:
        """返回仓库的 SSH clone URL（如有）。"""
        with self._con() as con:
            row = con.execute(
                "SELECT ssh_url FROM v_lite WHERE instance_id=?",
                (instance_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"instance_id 不在 DB 中: {instance_id}")
        return row["ssh_url"]

    def exec_difficulty_class(self, instance_id: str) -> str | None:
        """返回派生难度分级 (easy / medium / hard)。"""
        with self._con() as con:
            row = con.execute(
                "SELECT exec_difficulty_class FROM v_lite WHERE instance_id=?",
                (instance_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"instance_id 不在 DB 中: {instance_id}")
        return row["exec_difficulty_class"]

    def eval_estimate(self, instance_id: str, arch: str = "x86_64") -> dict:
        """一站式返回 003 推出的"跑这道题需要什么"细粒度元信息。

        Returns
        -------
        dict:
            {
                'instance_id':         iid,
                'image_name':          镜像完整 tag (与 acquisition() 重复另存以便一站取),
                'namespace':           该架构下推荐的 Docker namespace,
                'mode':                'pull' / 'build',
                'cache_level':         该架构下推荐的 harness --cache_level,
                'recommended_timeout': 推荐超时秒数,
                'repo_url':            https clone URL,
                'ssh_url':             ssh clone URL,
                'instance_url':        GitHub Issue URL,
                'exec_difficulty':     'easy' / 'medium' / 'hard',
                'f2p_count':           F2P 测试数,
                'p2p_count':           P2P 测试数,
            }
        """
        ns_col = self._arch_column(
            arch, "image_namespace_x86_64", "image_namespace_arm64"
        )
        cache_col = self._arch_column(
            arch, "cache_level_x86_64", "cache_level_arm64"
        )
        image_col = self._arch_column(arch, "image_x86_64", "image_arm64")
        mode_col = self._arch_column(arch, "image_mode_x86_64", "image_mode_arm64")

        sql = (
            f"SELECT {image_col} AS image_name, {mode_col} AS mode, "
            f"{ns_col} AS namespace, {cache_col} AS cache_level, "
            f"recommended_timeout, repo_url, ssh_url, instance_url, "
            f"exec_difficulty_class, f2p_count, p2p_count "
            f"FROM v_lite WHERE instance_id=?"
        )
        with self._con() as con:
            row = con.execute(sql, (instance_id,)).fetchone()
        if row is None:
            raise KeyError(f"instance_id 不在 DB 中: {instance_id}")
        return {
            "instance_id":         instance_id,
            "image_name":          row["image_name"],
            "mode":                row["mode"],
            "namespace":           row["namespace"],
            "cache_level":         row["cache_level"],
            "recommended_timeout": row["recommended_timeout"],
            "repo_url":            row["repo_url"],
            "ssh_url":             row["ssh_url"],
            "instance_url":        row["instance_url"],
            "exec_difficulty":     row["exec_difficulty_class"],
            "f2p_count":           row["f2p_count"],
            "p2p_count":           row["p2p_count"],
        }


__all__ = ["LiteDB", "LiteRow"]

