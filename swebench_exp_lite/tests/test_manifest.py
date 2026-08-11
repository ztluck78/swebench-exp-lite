"""Manifest 契约测试（stdlib unittest，零新依赖）。

覆盖 `pipeline/manifest.py` 的状态机 + 损坏 JSON 备份 + 原子写。
守护 6 个核心契约：
- mark_started 重置计时 + 清空 outputs + pop error
- mark_failed 记录 error 字段
- 损坏 JSON 备份为 manifest.bak-<ts>.json
- save 用 os.replace 原子写，无 .tmp 残留
- statuses() 返回 dict
- is_done() 判定

运行方式（仓根，无需 pytest）::

    python -m unittest swebench_exp_lite.tests.test_manifest -v
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from swebench_exp_lite.pipeline.manifest import Manifest


def _tmp_task_dir() -> Path:
    """创建临时 task_dir（含 manifest.json 路径）。"""
    tmp = tempfile.mkdtemp(prefix="manifest_test_")
    return Path(tmp)


class TestManifestInit(unittest.TestCase):
    """初始化 + 重读。"""

    def test_initial_state_empty_stages(self):
        task_dir = _tmp_task_dir()
        try:
            m = Manifest(task_dir)
            self.assertEqual(m.statuses(), {})
        finally:
            import shutil
            shutil.rmtree(task_dir, ignore_errors=True)

    def test_initial_state_data_has_required_keys(self):
        task_dir = _tmp_task_dir()
        try:
            m = Manifest(task_dir)
            for key in ("instance_id", "run_id", "model", "stages"):
                self.assertIn(key, m.data)
        finally:
            import shutil
            shutil.rmtree(task_dir, ignore_errors=True)


class TestManifestMarkStarted(unittest.TestCase):
    """mark_started 重置计时 + 清空 outputs + pop error。"""

    def setUp(self):
        self.task_dir = _tmp_task_dir()
        self.m = Manifest(self.task_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.task_dir, ignore_errors=True)

    def test_mark_started_sets_status_running(self):
        self.m.mark_started("S1_build")
        self.assertEqual(self.m._stage("S1_build")["status"], "running")
        self.assertIsNotNone(self.m._stage("S1_build")["started"])

    def test_mark_started_resets_outputs_and_clears_error(self):
        """mark_started 重跑时清空旧产物记录 + pop error。"""
        # 先 mark_failed 留下 error
        self.m.mark_failed("S6_score", "timeout")
        self.assertEqual(self.m._stage("S6_score").get("error"), "timeout")
        # 再 mark_started 重跑
        self.m.mark_started("S6_score")
        st = self.m._stage("S6_score")
        self.assertEqual(st["status"], "running")
        self.assertEqual(st["outputs"], [])
        self.assertNotIn("error", st)

    def test_mark_started_resets_finished(self):
        self.m.mark_done("S1_build")
        self.m.mark_started("S1_build")
        self.assertIsNone(self.m._stage("S1_build")["finished"])


class TestManifestMarkDone(unittest.TestCase):
    """mark_done 持久化产物列表。"""

    def setUp(self):
        self.task_dir = _tmp_task_dir()
        self.m = Manifest(self.task_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.task_dir, ignore_errors=True)

    def test_mark_done_sets_status_done(self):
        self.m.mark_started("S1_build")
        self.m.mark_done("S1_build")
        self.assertEqual(self.m._stage("S1_build")["status"], "done")
        self.assertIsNotNone(self.m._stage("S1_build")["finished"])

    def test_mark_done_persists_outputs(self):
        self.m.mark_done("S1_build", outputs=["/path/a", "/path/b"])
        self.assertEqual(self.m._stage("S1_build")["outputs"],
                         ["/path/a", "/path/b"])

    def test_mark_done_no_outputs_leaves_empty_list(self):
        self.m.mark_done("S1_build")
        self.assertEqual(self.m._stage("S1_build")["outputs"], [])


class TestManifestMarkFailed(unittest.TestCase):
    """mark_failed 记录 error。"""

    def setUp(self):
        self.task_dir = _tmp_task_dir()
        self.m = Manifest(self.task_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.task_dir, ignore_errors=True)

    def test_mark_failed_sets_status_failed(self):
        self.m.mark_failed("S6_score", "timeout")
        self.assertEqual(self.m._stage("S6_score")["status"], "failed")

    def test_mark_failed_records_error_field(self):
        self.m.mark_failed("S6_score", "docker image inspect 失败")
        self.assertEqual(self.m._stage("S6_score")["error"],
                         "docker image inspect 失败")

    def test_mark_failed_without_error_string(self):
        self.m.mark_failed("S6_score")
        # 不传 error 字符串也不应抛
        self.assertEqual(self.m._stage("S6_score")["status"], "failed")


class TestManifestCorruptedJSON(unittest.TestCase):
    """损坏 JSON 备份为 manifest.bak-<ts>.json + 重新初始化。"""

    def test_corrupted_json_backs_up_and_reinitializes(self):
        task_dir = _tmp_task_dir()
        try:
            manifest_path = task_dir / "manifest.json"
            manifest_path.write_text("{invalid json", encoding="utf-8")
            # 实例化应备份损坏文件
            m = Manifest(task_dir)
            # 备份文件存在（manifest.bak-*.json）
            bak_files = list(task_dir.glob("manifest.bak-*.json"))
            self.assertGreater(len(bak_files), 0)
            # 原文件已被 rename 或保留但 m.data 是新空结构
            self.assertEqual(m.data["stages"], {})
        finally:
            import shutil
            shutil.rmtree(task_dir, ignore_errors=True)


class TestManifestSaveAtomicWrite(unittest.TestCase):
    """save 用 os.replace 原子写，无 .tmp 残留。"""

    def setUp(self):
        self.task_dir = _tmp_task_dir()
        self.m = Manifest(self.task_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.task_dir, ignore_errors=True)

    def test_save_uses_atomic_replace_no_tmp_residue(self):
        self.m.mark_done("S1_build")
        # save 后 task_dir 中不应有 .tmp-* 残留
        tmp_files = list(self.task_dir.glob("*.tmp-*.json"))
        self.assertEqual(tmp_files, [])
        # manifest.json 存在且内容合法
        self.assertTrue((self.task_dir / "manifest.json").exists())
        with open(self.task_dir / "manifest.json", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("stages", data)

    def test_save_updates_updated_field(self):
        before = self.m.data.get("updated")
        self.m.mark_done("S1_build")
        after = self.m.data.get("updated")
        # updated 字段在 save 时刷新
        self.assertIsNotNone(after)
        self.assertNotEqual(before, after)


class TestManifestQueries(unittest.TestCase):
    """statuses() / is_done() / all_stages()。"""

    def setUp(self):
        self.task_dir = _tmp_task_dir()
        self.m = Manifest(self.task_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.task_dir, ignore_errors=True)

    def test_statuses_returns_stage_dict(self):
        self.m.mark_started("S1_build")
        self.m.mark_done("S1_build")
        self.m.mark_started("S2_prepare")
        self.assertEqual(self.m.statuses(),
                         {"S1_build": "done", "S2_prepare": "running"})

    def test_is_done_predicate(self):
        self.m.mark_done("S1_build")
        self.assertTrue(self.m.is_done("S1_build"))
        self.assertFalse(self.m.is_done("S2_prepare"))
        self.assertFalse(self.m.is_done("__nonexistent__"))

    def test_all_stages_returns_dict(self):
        self.m.mark_done("S1_build")
        all_st = self.m.all_stages()
        self.assertIn("S1_build", all_st)
        self.assertEqual(all_st["S1_build"]["status"], "done")


class TestManifestSetMeta(unittest.TestCase):
    """set_meta 写入 run_id / model / dataset / split / created。"""

    def setUp(self):
        self.task_dir = _tmp_task_dir()
        self.m = Manifest(self.task_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.task_dir, ignore_errors=True)

    def test_set_meta_writes_run_id_and_model(self):
        self.m.set_meta("run-123", "kimi-code/kimi-for-coding")
        self.assertEqual(self.m.data["run_id"], "run-123")
        self.assertEqual(self.m.data["model"], "kimi-code/kimi-for-coding")
        # created 应被首次设置
        self.assertIsNotNone(self.m.data.get("created"))

    def test_set_meta_with_dataset_and_split(self):
        self.m.set_meta("run-1", "model", dataset="SWE-bench_Lite", split="dev")
        self.assertEqual(self.m.data["dataset"], "SWE-bench_Lite")
        self.assertEqual(self.m.data["split"], "dev")

    def test_set_meta_does_not_overwrite_created(self):
        """created 仅在首次设置时被写入。"""
        self.m.set_meta("run-1", "model")
        first_created = self.m.data["created"]
        self.m.set_meta("run-2", "model2")
        # created 不变
        self.assertEqual(self.m.data["created"], first_created)


class TestManifestSetImage(unittest.TestCase):
    """set_image 写入镜像元数据。"""

    def setUp(self):
        self.task_dir = _tmp_task_dir()
        self.m = Manifest(self.task_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.task_dir, ignore_errors=True)

    def test_set_image_writes_image_data(self):
        img_data = {"image": "swebench/sweb.eval.x86_64.test:latest",
                    "kind": "eval", "arch": "x86_64"}
        self.m.set_image(img_data)
        self.assertEqual(self.m.data["image"], img_data)


class TestManifestReload(unittest.TestCase):
    """重读 manifest.json（断点续跑场景）。"""

    def test_reload_preserves_existing_data(self):
        task_dir = _tmp_task_dir()
        try:
            m1 = Manifest(task_dir)
            m1.set_meta("run-1", "model")
            m1.mark_done("S1_build")
            # 新实例化读取同一文件
            m2 = Manifest(task_dir)
            self.assertEqual(m2.data["run_id"], "run-1")
            self.assertEqual(m2.statuses().get("S1_build"), "done")
        finally:
            import shutil
            shutil.rmtree(task_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)