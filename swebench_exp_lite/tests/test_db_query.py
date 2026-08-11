"""DB 查询层单元测试（stdlib unittest，零新依赖）。

覆盖 `LiteDB` 在 4 次迁移后 schema（001~004）下的行为，含 NULL 缺失字段降级、
数据正确性守护（count=323/dev=23/test=300，arm64 全 build）、FTS5 BM25 搜索。

运行方式（仓根，无需 pytest）::

    python -m unittest swebench_exp_lite.tests.test_db_query -v

CI 步骤见 .github/workflows/ci.yml。DB 不存在时 `skipTest`（CI 上 DB 不入库）。
"""
from __future__ import annotations

import unittest
from pathlib import Path

from swebench_exp_lite.db import DEFAULT_DB_PATH
from swebench_exp_lite.db.query import LiteDB


# 已知实例：dev split 第一条（保证 schema 稳定回归测试）
DEV_FIRST_INSTANCE = "sqlfluff__sqlfluff-1625"

# eval_estimate 必含的 11 字段（[query.py:485-498](file:///Users/zhangtian/DevWorkspace/swebench-exp-lite/swebench_exp_lite/db/query.py#L485-L498)）
EVAL_ESTIMATE_REQUIRED_KEYS = {
    "instance_id", "image_name", "mode", "namespace", "cache_level",
    "recommended_timeout", "repo_url", "ssh_url", "instance_url",
    "exec_difficulty", "f2p_count", "p2p_count",
}


def _db_or_skip(test: unittest.TestCase) -> LiteDB | None:
    """DB 存在则返回 LiteDB 实例；否则 skipTest。

    CI 静态门禁无 DB（`.gitignore` 排除 `database/*.db`），必须优雅跳过。
    """
    if not DEFAULT_DB_PATH.exists():
        test.skipTest(f"DB 不存在：{DEFAULT_DB_PATH}（CI 上无 DB 是预期；本地跑 start.sh 下载）")
    return LiteDB()


class TestLiteDBCountAndSplits(unittest.TestCase):
    """数据正确性守护（实测值：323 / dev=23 / test=300）。"""

    def setUp(self):
        self.db = _db_or_skip(self)

    def test_count_total_equals_323(self):
        self.assertEqual(self.db.count(), 323)

    def test_count_dev_equals_23(self):
        self.assertEqual(self.db.count(split="dev"), 23)

    def test_count_test_equals_300(self):
        self.assertEqual(self.db.count(split="test"), 300)


class TestLiteDBGet(unittest.TestCase):
    """get() 行为 + 异常 + 大字段。"""

    def setUp(self):
        self.db = _db_or_skip(self)

    def test_get_returns_lite_row_with_all_cols(self):
        row = self.db.get(DEV_FIRST_INSTANCE)
        self.assertIsNotNone(row)
        # LiteRow 应至少含 instance_id / repo / base_commit
        self.assertEqual(row["instance_id"], DEV_FIRST_INSTANCE)
        self.assertTrue(row["repo"])
        self.assertTrue(row["base_commit"])

    def test_get_missing_raises_keyerror(self):
        with self.assertRaises(KeyError) as ctx:
            self.db.get("nonexistent__repo-9999")
        self.assertIn("不在 DB 中", str(ctx.exception))

    def test_with_large_false_excludes_test_patch(self):
        row = self.db.get(DEV_FIRST_INSTANCE, with_large=False)
        # _BASE_COLS 不含 test_patch；访问应抛 IndexError
        with self.assertRaises(IndexError):
            _ = row["test_patch"]


class TestLiteDBEvalEstimate(unittest.TestCase):
    """eval_estimate() 11 字段 + arch 维度。"""

    def setUp(self):
        self.db = _db_or_skip(self)

    def test_eval_estimate_returns_required_keys(self):
        est = self.db.eval_estimate(DEV_FIRST_INSTANCE, arch="x86_64")
        missing = EVAL_ESTIMATE_REQUIRED_KEYS - set(est.keys())
        self.assertEqual(missing, set(), f"缺少字段：{missing}")

    def test_eval_estimate_instance_id_echoes_input(self):
        est = self.db.eval_estimate(DEV_FIRST_INSTANCE, arch="x86_64")
        self.assertEqual(est["instance_id"], DEV_FIRST_INSTANCE)

    def test_eval_estimate_x86_64_arch(self):
        est = self.db.eval_estimate(DEV_FIRST_INSTANCE, arch="x86_64")
        self.assertIn(est["mode"], ("pull", "build"))

    def test_eval_estimate_arm64_arch(self):
        est = self.db.eval_estimate(DEV_FIRST_INSTANCE, arch="arm64")
        # arm64 全 build（无官方镜像）
        self.assertEqual(est["mode"], "build")


class TestLiteDBMigration004Nullable(unittest.TestCase):
    """004 迁移新增字段（key_files_hint / repro_snippet / difficulty_human）可能为 NULL。"""

    def setUp(self):
        self.db = _db_or_skip(self)

    def test_004_fields_nullable_no_exception(self):
        # 扫所有 instance 验证 004 字段可访问且 NULL 不抛异常
        for row in self.db.iter_metadata():
            _ = row["key_files_hint"]   # 可能 None
            _ = row["repro_snippet"]   # 可能 None
            _ = row["difficulty_human"]  # 可能 None


class TestLiteDBErrors(unittest.TestCase):
    """错误路径：DB 文件不存在 / arch 非法。"""

    def test_db_file_not_found_raises_filenotfounderror(self):
        fake_db = Path("/tmp/swebench_test_nonexistent_xyz.db")
        if fake_db.exists():
            fake_db.unlink()
        with self.assertRaises(FileNotFoundError) as ctx:
            db = LiteDB(fake_db)
            db.count()  # 触发连接
        self.assertIn("DB 不存在", str(ctx.exception))

    def test_invalid_arch_raises_value_error(self):
        db = _db_or_skip(self)
        with self.assertRaises(ValueError) as ctx:
            db.docker_image(DEV_FIRST_INSTANCE, arch="mips")
        self.assertIn("arch 仅支持", str(ctx.exception))


class TestLiteDBAggregations(unittest.TestCase):
    """聚合：acquisition_summary / repos / search / iter_metadata。"""

    def setUp(self):
        self.db = _db_or_skip(self)

    def test_acquisition_summary_arm64_all_build(self):
        summary = self.db.acquisition_summary()
        # 实测：x86_64 全部 pull，arm64 全部 build（无官方镜像）
        self.assertEqual(summary["x86_64"]["pull"], 323)
        self.assertEqual(summary["x86_64"]["build"], 0)
        self.assertEqual(summary["arm64"]["pull"], 0)
        self.assertEqual(summary["arm64"]["build"], 323)

    def test_search_uses_fts5_bm25(self):
        results = self.db.search("None", limit=5)
        # FTS5 至少返回 1 条（即便 dummy 关键词）
        self.assertGreater(len(results), 0, "FTS5 搜索应至少返回 1 条结果")
        for r in results[:2]:
            self.assertTrue(r["instance_id"])

    def test_repos_descending_count(self):
        repos = self.db.repos()
        items = list(repos.items())
        self.assertGreater(len(items), 0)
        # 第一项 count ≥ 第二项
        if len(items) >= 2:
            self.assertGreaterEqual(items[0][1], items[1][1])

    def test_iter_metadata_yields_323(self):
        rows = list(self.db.iter_metadata())
        self.assertEqual(len(rows), 323)


class TestLiteDBRepository(unittest.TestCase):
    """repository() / repo_url() 元信息。"""

    def setUp(self):
        self.db = _db_or_skip(self)

    def test_repository_returns_required_keys(self):
        info = self.db.repository(DEV_FIRST_INSTANCE)
        for key in ("repo", "repo_url", "default_branch", "base_commit",
                    "environment_setup_commit", "version"):
            self.assertIn(key, info)

    def test_repo_url_contains_github(self):
        url = self.db.repo_url(DEV_FIRST_INSTANCE)
        self.assertIn("github.com", url)


class TestLiteDBDockerImages(unittest.TestCase):
    """docker_image() / docker_images()。"""

    def setUp(self):
        self.db = _db_or_skip(self)

    def test_docker_image_returns_tag(self):
        img = self.db.docker_image(DEV_FIRST_INSTANCE)
        self.assertTrue(img)
        self.assertIn("/", img)  # 形如 "swebench/sweb.eval.x86_64.xxx:latest"

    def test_docker_images_returns_tuples(self):
        results = self.db.docker_images()
        self.assertGreater(len(results), 0)
        # 每条 (instance_id, image_x86_64, image_arm64)
        first = results[0]
        self.assertEqual(len(first), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)