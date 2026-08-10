"""answer_evaluator.harness.reporting 单元测试。

make_run_report 负责把 predictions + dataset 聚合成最终评测报告，处理
patch 为空、报告缺失、JSON 损坏、resolved/unresolved 分类、聚合报告
落盘路径等边界。本套件用 monkeypatch 把 RUN_EVALUATION_LOG_DIR 重定向
到 tmp_path，client=None 路径避免依赖 Docker SDK。

对应 P0 守护目标：reporting.py 当前覆盖率 0%，目标 80%+。
"""
from __future__ import annotations

import json

import pytest

from answer_evaluator.harness import reporting
from answer_evaluator.harness.constants import (
    KEY_INSTANCE_ID,
    KEY_MODEL,
    KEY_PREDICTION,
    LOG_REPORT,
)


def _mk_prediction(iid="i1", model="m1", patch="diff"):
    return {KEY_INSTANCE_ID: iid, KEY_MODEL: model, KEY_PREDICTION: patch}


def _mk_instance(iid="i1"):
    return {KEY_INSTANCE_ID: iid}


@pytest.fixture
def redirected_log_dir(tmp_path, monkeypatch):
    """把 reporting 模块的 RUN_EVALUATION_LOG_DIR 重定向到 tmp_path。"""
    fake_dir = tmp_path / "run_eval_logs"
    fake_dir.mkdir()
    monkeypatch.setattr(reporting, "RUN_EVALUATION_LOG_DIR", fake_dir)
    return fake_dir


def _place_report(log_dir, run_id, model, iid, content):
    """在 log_dir/<run_id>/<model>/<iid>/report.json 放一份报告。"""
    p = log_dir / run_id / model.replace("/", "__") / iid / LOG_REPORT
    p.parent.mkdir(parents=True, exist_ok=True)
    if content is not None:
        p.write_text(content, encoding="utf-8")
    else:
        p.touch()
    return p


# --------------------------------------------------------------------------- #
# 主分类路径：resolved / unresolved / error / empty_patch / incomplete
# --------------------------------------------------------------------------- #
def test_make_run_report_classifies_resolved_unresolved_and_incomplete(
    redirected_log_dir,
):
    run_id = "run-001"
    _place_report(redirected_log_dir, run_id, "m1", "i1",
                  json.dumps({"i1": {"resolved": True}}))
    _place_report(redirected_log_dir, run_id, "m1", "i2",
                  json.dumps({"i2": {"resolved": False}}))
    preds = {"i1": _mk_prediction("i1"), "i2": _mk_prediction("i2")}
    dataset = [_mk_instance("i1"), _mk_instance("i2"), _mk_instance("i3")]
    rpath = reporting.make_run_report(preds, dataset, run_id, client=None)
    assert rpath.exists()
    r = json.loads(rpath.read_text())
    assert r["total_instances"] == 3
    assert r["submitted_instances"] == 2
    assert r["completed_instances"] == 2
    assert r["resolved_instances"] == 1
    assert r["unresolved_instances"] == 1
    assert r["empty_patch_instances"] == 0
    assert r["error_instances"] == 0
    assert r["incomplete_ids"] == ["i3"]
    assert r["resolved_ids"] == ["i1"]
    assert r["unresolved_ids"] == ["i2"]
    assert r["completed_ids"] == ["i1", "i2"]
    assert r["submitted_ids"] == ["i1", "i2"]
    assert r["schema_version"] == 2


# --------------------------------------------------------------------------- #
# 空 / None patch
# --------------------------------------------------------------------------- #
def test_make_run_report_handles_empty_patch(redirected_log_dir):
    run_id = "run-002"
    preds = {"i1": _mk_prediction("i1", patch="")}
    dataset = [_mk_instance("i1")]
    rpath = reporting.make_run_report(preds, dataset, run_id, client=None)
    r = json.loads(rpath.read_text())
    assert r["empty_patch_instances"] == 1
    assert r["completed_instances"] == 0
    assert r["empty_patch_ids"] == ["i1"]
    # 空 patch 路径不应误报为 error
    assert r["error_instances"] == 0


def test_make_run_report_handles_none_patch(redirected_log_dir):
    run_id = "run-003"
    preds = {"i1": _mk_prediction("i1", patch=None)}
    dataset = [_mk_instance("i1")]
    rpath = reporting.make_run_report(preds, dataset, run_id, client=None)
    r = json.loads(rpath.read_text())
    assert r["empty_patch_instances"] == 1
    assert r["empty_patch_ids"] == ["i1"]


# --------------------------------------------------------------------------- #
# report.json 缺失 / 空 / 非法 JSON / 缺键
# --------------------------------------------------------------------------- #
def test_make_run_report_treats_missing_report_as_error(redirected_log_dir):
    run_id = "run-004"
    preds = {"i1": _mk_prediction("i1")}
    dataset = [_mk_instance("i1")]
    # 不放 report.json
    rpath = reporting.make_run_report(preds, dataset, run_id, client=None)
    r = json.loads(rpath.read_text())
    assert r["error_instances"] == 1
    assert r["completed_instances"] == 0
    assert r["error_ids"] == ["i1"]


def test_make_run_report_treats_empty_report_file_as_error(redirected_log_dir):
    run_id = "run-005"
    _place_report(redirected_log_dir, run_id, "m1", "i1", "")
    preds = {"i1": _mk_prediction("i1")}
    dataset = [_mk_instance("i1")]
    rpath = reporting.make_run_report(preds, dataset, run_id, client=None)
    r = json.loads(rpath.read_text())
    assert r["error_instances"] == 1
    # 修复后：空文件先验 content 再 add completed，空文件只算 error 不算 completed
    assert r["completed_instances"] == 0


def test_make_run_report_treats_invalid_json_as_error(redirected_log_dir):
    run_id = "run-006"
    _place_report(redirected_log_dir, run_id, "m1", "i1", "{not valid json")
    preds = {"i1": _mk_prediction("i1")}
    dataset = [_mk_instance("i1")]
    rpath = reporting.make_run_report(preds, dataset, run_id, client=None)
    r = json.loads(rpath.read_text())
    assert r["error_instances"] == 1


def test_make_run_report_treats_missing_instance_id_key_as_error(redirected_log_dir):
    # report.json 合法 JSON 但缺 instance_id 键 → KeyError → error
    run_id = "run-007"
    _place_report(redirected_log_dir, run_id, "m1", "i1",
                  json.dumps({"some_other_key": {"resolved": True}}))
    preds = {"i1": _mk_prediction("i1")}
    dataset = [_mk_instance("i1")]
    rpath = reporting.make_run_report(preds, dataset, run_id, client=None)
    r = json.loads(rpath.read_text())
    assert r["error_instances"] == 1


# --------------------------------------------------------------------------- #
# 聚合报告路径与文件名 sanitize
# --------------------------------------------------------------------------- #
def test_make_run_report_writes_aggregate_to_dedicated_dir(redirected_log_dir):
    run_id = "run-008"
    _place_report(redirected_log_dir, run_id, "m1", "i1",
                  json.dumps({"i1": {"resolved": True}}))
    preds = {"i1": _mk_prediction("i1")}
    dataset = [_mk_instance("i1")]
    rpath = reporting.make_run_report(preds, dataset, run_id, client=None)
    assert rpath.parent == redirected_log_dir / "_aggregate"
    assert rpath.name == "m1.run-008.json"


def test_make_run_report_sanitizes_model_slashes_in_aggregate_filename(
    redirected_log_dir,
):
    run_id = "run-009"
    _place_report(redirected_log_dir, run_id, "org/model", "i1",
                  json.dumps({"i1": {"resolved": True}}))
    preds = {"i1": _mk_prediction("i1", model="org/model")}
    dataset = [_mk_instance("i1")]
    rpath = reporting.make_run_report(preds, dataset, run_id, client=None)
    # model 含 '/' 被 sanitize 为 '__'
    assert rpath.name == "org__model.run-009.json"


def test_make_run_report_sanitizes_run_id_slashes(redirected_log_dir):
    run_id = "user/branch"
    _place_report(redirected_log_dir, run_id, "m1", "i1",
                  json.dumps({"i1": {"resolved": True}}))
    preds = {"i1": _mk_prediction("i1")}
    dataset = [_mk_instance("i1")]
    rpath = reporting.make_run_report(preds, dataset, run_id, client=None)
    assert rpath.name == "m1.user__branch.json"


# --------------------------------------------------------------------------- #
# 实例筛选与去重
# --------------------------------------------------------------------------- #
def test_make_run_report_skips_instances_without_prediction(redirected_log_dir):
    run_id = "run-010"
    _place_report(redirected_log_dir, run_id, "m1", "i1",
                  json.dumps({"i1": {"resolved": True}}))
    preds = {"i1": _mk_prediction("i1")}
    dataset = [_mk_instance("i1"), _mk_instance("i2")]  # i2 无 prediction
    rpath = reporting.make_run_report(preds, dataset, run_id, client=None)
    r = json.loads(rpath.read_text())
    assert r["total_instances"] == 2
    assert r["submitted_instances"] == 1
    assert r["incomplete_ids"] == ["i2"]
    assert r["completed_ids"] == ["i1"]


def test_make_run_report_ignores_predictions_not_in_dataset(redirected_log_dir):
    # prediction 不在 dataset → submitted 只反映与 dataset 的交集
    run_id = "run-011"
    _place_report(redirected_log_dir, run_id, "m1", "i1",
                  json.dumps({"i1": {"resolved": True}}))
    preds = {"i1": _mk_prediction("i1"), "i2": _mk_prediction("i2")}
    dataset = [_mk_instance("i1")]
    rpath = reporting.make_run_report(preds, dataset, run_id, client=None)
    r = json.loads(rpath.read_text())
    assert r["total_instances"] == 1
    # 修复后：submitted 为 predictions 与 dataset 的交集
    assert r["submitted_instances"] == 1
    assert r["submitted_ids"] == ["i1"]
    # 循环只处理 dataset 中的 i1，i2 不被分类
    assert r["completed_ids"] == ["i1"]
    assert r["resolved_ids"] == ["i1"]


# --------------------------------------------------------------------------- #
# client=None 路径不依赖 Docker SDK
# --------------------------------------------------------------------------- #
def test_make_run_report_client_none_path_completes(redirected_log_dir):
    run_id = "run-012"
    _place_report(redirected_log_dir, run_id, "m1", "i1",
                  json.dumps({"i1": {"resolved": True}}))
    preds = {"i1": _mk_prediction("i1")}
    dataset = [_mk_instance("i1")]
    rpath = reporting.make_run_report(preds, dataset, run_id, client=None)
    r = json.loads(rpath.read_text())
    assert r["resolved_instances"] == 1
    # client=None 时 unstopped_containers 是空集
    assert r.get("unstopped_instances", 0) == 0
