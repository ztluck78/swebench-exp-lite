"""answer_evaluator.harness.grading 单元测试。

grading 是平台核心评分引擎，直接决定 %Resolved = count(FULL)/count(total)。
本套件覆盖所有纯函数（test_passed/test_failed / compute_fail_to_pass /
compute_pass_to_pass / get_resolution_status / get_eval_tests_report）
以及文件 IO 函数 get_logs_eval / get_eval_report（用 monkeypatch 注入
fake repo+parser，零真实 Docker / 零真实日志依赖）。

对应 P0 守护目标：answer_evaluator.harness 覆盖率 14.3% → 80%+。
"""
from __future__ import annotations

from types import SimpleNamespace

from answer_evaluator.harness import grading
from answer_evaluator.harness.constants import (
    APPLY_PATCH_FAIL,
    END_TEST_OUTPUT,
    EvalType,
    FAIL_ONLY_REPOS,
    FAIL_TO_FAIL,
    FAIL_TO_PASS,
    KEY_INSTANCE_ID,
    KEY_PREDICTION,
    PASS_TO_FAIL,
    PASS_TO_PASS,
    RESET_FAILED,
    ResolvedStatus,
    START_TEST_OUTPUT,
    TESTS_ERROR,
    TESTS_TIMEOUT,
    TestStatus,
)

P = TestStatus.PASSED.value
F = TestStatus.FAILED.value
E = TestStatus.ERROR.value
X = TestStatus.XFAIL.value
S = TestStatus.SKIPPED.value


# --------------------------------------------------------------------------- #
# 纯函数：状态判定
# --------------------------------------------------------------------------- #
def test_test_passed_recognizes_passed_and_xfail():
    assert grading.test_passed("a", {"a": P}) is True
    assert grading.test_passed("a", {"a": X}) is True
    assert grading.test_passed("a", {"a": F}) is False
    assert grading.test_passed("a", {"a": S}) is False
    assert grading.test_passed("a", {}) is False


def test_test_failed_recognizes_missing_and_failed_error():
    assert grading.test_failed("a", {}) is True
    assert grading.test_failed("a", {"a": F}) is True
    assert grading.test_failed("a", {"a": E}) is True
    assert grading.test_failed("a", {"a": P}) is False
    assert grading.test_failed("a", {"a": X}) is False
    assert grading.test_failed("a", {"a": S}) is False


# --------------------------------------------------------------------------- #
# compute_fail_to_pass / compute_pass_to_pass
# --------------------------------------------------------------------------- #
def _report(f2p_s, f2p_f, p2p_s, p2p_f):
    return {
        FAIL_TO_PASS: {"success": f2p_s, "failure": f2p_f},
        PASS_TO_PASS: {"success": p2p_s, "failure": p2p_f},
    }


def test_compute_fail_to_pass_full():
    assert grading.compute_fail_to_pass(_report(["a"], [], ["b"], [])) == 1.0


def test_compute_fail_to_pass_partial():
    r = _report(["a"], ["b"], ["c"], [])
    assert grading.compute_fail_to_pass(r) == 0.5


def test_compute_fail_to_pass_zero_cases_returns_one():
    # F2P 列表空（0 success + 0 failure）→ 返回 1（不参与计算）
    r = _report([], [], ["c"], [])
    assert grading.compute_fail_to_pass(r) == 1


def test_compute_pass_to_pass_full():
    assert grading.compute_pass_to_pass(_report(["a"], [], ["b", "c"], [])) == 1.0


def test_compute_pass_to_pass_partial():
    r = _report([], [], ["a"], ["b"])
    assert grading.compute_pass_to_pass(r) == 0.5


def test_compute_pass_to_pass_zero_cases_returns_one():
    r = _report(["a"], [], [], [])
    assert grading.compute_pass_to_pass(r) == 1


# --------------------------------------------------------------------------- #
# get_resolution_status（评分公式核心）
# --------------------------------------------------------------------------- #
def test_resolution_full_when_f2p_and_p2p_both_one():
    r = _report(["a"], [], ["b"], [])
    assert grading.get_resolution_status(r) == ResolvedStatus.FULL.value


def test_resolution_partial_when_f2p_partial_and_p2p_one():
    r = _report(["a"], ["b"], ["c"], [])
    assert grading.get_resolution_status(r) == ResolvedStatus.PARTIAL.value


def test_resolution_no_when_p2p_has_failure():
    r = _report(["a"], [], ["c"], ["d"])
    assert grading.get_resolution_status(r) == ResolvedStatus.NO.value


def test_resolution_no_when_f2p_zero_success():
    r = _report([], ["b"], ["c"], [])
    assert grading.get_resolution_status(r) == ResolvedStatus.NO.value


def test_resolution_no_when_f2p_full_but_p2p_has_failure():
    r = _report(["a"], [], [], ["d"])
    assert grading.get_resolution_status(r) == ResolvedStatus.NO.value


def test_resolution_full_when_both_lists_empty():
    # F2P 空 + P2P 空 → 两者 compute 都返回 1 → FULL（边界）
    r = _report([], [], [], [])
    assert grading.get_resolution_status(r) == ResolvedStatus.FULL.value


# --------------------------------------------------------------------------- #
# get_eval_tests_report
# --------------------------------------------------------------------------- #
def test_eval_tests_report_pass_and_fail_mode_all_success():
    eval_sm = {"a": P, "b": P}
    gold = {"FAIL_TO_PASS": ["a"], "PASS_TO_PASS": ["b"]}
    r = grading.get_eval_tests_report(eval_sm, gold)
    assert r[FAIL_TO_PASS]["success"] == ["a"]
    assert r[FAIL_TO_PASS]["failure"] == []
    assert r[PASS_TO_PASS]["success"] == ["b"]
    assert r[PASS_TO_PASS]["failure"] == []


def test_eval_tests_report_f2p_failure_classified():
    eval_sm = {"a": F}
    gold = {"FAIL_TO_PASS": ["a"], "PASS_TO_PASS": []}
    r = grading.get_eval_tests_report(eval_sm, gold)
    assert r[FAIL_TO_PASS]["success"] == []
    assert r[FAIL_TO_PASS]["failure"] == ["a"]


def test_eval_tests_report_missing_case_treated_as_failure():
    eval_sm = {}
    gold = {"FAIL_TO_PASS": ["a"], "PASS_TO_PASS": []}
    r = grading.get_eval_tests_report(eval_sm, gold)
    assert r[FAIL_TO_PASS]["failure"] == ["a"]


def test_eval_tests_report_fail_only_mode_treats_non_failed_as_success():
    eval_sm = {"a": F, "b": P, "c": S}
    gold = {"FAIL_TO_PASS": ["a", "b", "c"], "PASS_TO_PASS": []}
    r = grading.get_eval_tests_report(eval_sm, gold, eval_type=EvalType.FAIL_ONLY)
    assert r[FAIL_TO_PASS]["failure"] == ["a"]
    assert set(r[FAIL_TO_PASS]["success"]) == {"b", "c"}


def test_eval_tests_report_calculate_to_fail_populates_f2f_p2f():
    eval_sm = {"a": F, "b": P, "c": F}
    gold = {
        "FAIL_TO_PASS": [], "PASS_TO_PASS": [],
        FAIL_TO_FAIL: ["a", "b"], PASS_TO_FAIL: ["c"],
    }
    r = grading.get_eval_tests_report(eval_sm, gold, calculate_to_fail=True)
    assert r[FAIL_TO_FAIL]["failure"] == ["a"]
    assert r[FAIL_TO_FAIL]["success"] == ["b"]
    assert r[PASS_TO_FAIL]["failure"] == ["c"]
    assert r[PASS_TO_FAIL]["success"] == []


def test_eval_tests_report_default_eval_type_is_pass_and_fail():
    # 不传 eval_type → 默认 PASS_AND_FAIL（test_passed/test_failed 语义）
    eval_sm = {"a": P, "b": F}
    gold = {"FAIL_TO_PASS": ["a", "b"], "PASS_TO_PASS": []}
    r = grading.get_eval_tests_report(eval_sm, gold)
    assert r[FAIL_TO_PASS]["success"] == ["a"]
    assert r[FAIL_TO_PASS]["failure"] == ["b"]


# --------------------------------------------------------------------------- #
# get_logs_eval（文件 IO，monkeypatch 注入 fake repo+parser）
# --------------------------------------------------------------------------- #
def _patch_fake_repo(monkeypatch, parser_fn, test_cmd="pytest"):
    """注入 fake/repo 到 grading 模块引用的两个全局 dict。"""
    monkeypatch.setitem(grading.MAP_REPO_TO_PARSER, "fake/repo", parser_fn)
    monkeypatch.setitem(
        grading.MAP_REPO_VERSION_TO_SPECS, "fake/repo",
        {"1.0": {"test_cmd": test_cmd}},
    )


def test_get_logs_eval_returns_empty_when_bad_code_present(tmp_path, monkeypatch):
    _patch_fake_repo(monkeypatch, lambda content, spec: {"x": P})
    spec = SimpleNamespace(repo="fake/repo", version="1.0")
    log = tmp_path / "run.log"
    log.write_text(
        f"some setup\n{APPLY_PATCH_FAIL}\n{START_TEST_OUTPUT}\nfoo\n{END_TEST_OUTPUT}\n"
    )
    sm, found = grading.get_logs_eval(spec, str(log))
    assert sm == {} and found is False


def test_get_logs_eval_returns_empty_on_reset_failed(tmp_path, monkeypatch):
    _patch_fake_repo(monkeypatch, lambda content, spec: {"x": P})
    spec = SimpleNamespace(repo="fake/repo", version="1.0")
    log = tmp_path / "run.log"
    log.write_text(f"{RESET_FAILED}\n{START_TEST_OUTPUT}\nx\n{END_TEST_OUTPUT}")
    sm, found = grading.get_logs_eval(spec, str(log))
    assert found is False


def test_get_logs_eval_returns_empty_on_tests_error(tmp_path, monkeypatch):
    _patch_fake_repo(monkeypatch, lambda content, spec: {"x": P})
    spec = SimpleNamespace(repo="fake/repo", version="1.0")
    log = tmp_path / "run.log"
    log.write_text(f"{TESTS_ERROR}\n{START_TEST_OUTPUT}\nx\n{END_TEST_OUTPUT}")
    sm, found = grading.get_logs_eval(spec, str(log))
    assert found is False


def test_get_logs_eval_returns_empty_on_tests_timeout(tmp_path, monkeypatch):
    _patch_fake_repo(monkeypatch, lambda content, spec: {"x": P})
    spec = SimpleNamespace(repo="fake/repo", version="1.0")
    log = tmp_path / "run.log"
    log.write_text(f"{TESTS_TIMEOUT}\n{START_TEST_OUTPUT}\nx\n{END_TEST_OUTPUT}")
    sm, found = grading.get_logs_eval(spec, str(log))
    assert found is False


def test_get_logs_eval_returns_empty_when_no_test_output_markers(tmp_path, monkeypatch):
    _patch_fake_repo(monkeypatch, lambda content, spec: {"x": P})
    spec = SimpleNamespace(repo="fake/repo", version="1.0")
    log = tmp_path / "run.log"
    log.write_text("plain log without markers")
    sm, found = grading.get_logs_eval(spec, str(log))
    assert sm == {} and found is False


def test_get_logs_eval_parses_between_markers(tmp_path, monkeypatch):
    calls = []

    def fake_parser(content, spec):
        calls.append(content)
        return {"a": P}

    _patch_fake_repo(monkeypatch, fake_parser)
    spec = SimpleNamespace(repo="fake/repo", version="1.0")
    log = tmp_path / "run.log"
    log.write_text(f"pre\n{START_TEST_OUTPUT}\nMARKER_CONTENT\n{END_TEST_OUTPUT}\npost")
    sm, found = grading.get_logs_eval(spec, str(log))
    assert found is True
    assert sm == {"a": P}
    # 第一次调用应只处理 markers 之间的内容（不含 pre / post）
    assert "MARKER_CONTENT" in calls[0]
    assert "pre" not in calls[0]


def test_get_logs_eval_fallback_to_full_content_when_markers_empty(tmp_path, monkeypatch):
    calls = []

    def fake_parser(content, spec):
        calls.append(content)
        # markers 之间空 → 返回空；全 log 调用（含 FULL_LOG_TOKEN）→ 返回有内容
        if "FULL_LOG_TOKEN" in content:
            return {"a": P}
        return {}

    _patch_fake_repo(monkeypatch, fake_parser)
    spec = SimpleNamespace(repo="fake/repo", version="1.0")
    log = tmp_path / "run.log"
    log.write_text(f"FULL_LOG_TOKEN\n{START_TEST_OUTPUT}\n\n{END_TEST_OUTPUT}\npost")
    sm, found = grading.get_logs_eval(spec, str(log))
    assert found is True
    assert sm == {"a": P}
    assert len(calls) == 2  # markers 内 + 全 log fallback


def test_get_logs_eval_test_cmd_list_uses_last_element(tmp_path, monkeypatch):
    # test_cmd 是 list 时取最后一个元素；parser 不消费 test_cmd，仅验证不抛
    _patch_fake_repo(
        monkeypatch,
        lambda content, spec: {"a": P},
        test_cmd=["conda run", "pytest -v"],
    )
    spec = SimpleNamespace(repo="fake/repo", version="1.0")
    log = tmp_path / "run.log"
    log.write_text(f"{START_TEST_OUTPUT}\nx\n{END_TEST_OUTPUT}")
    sm, found = grading.get_logs_eval(spec, str(log))
    assert found is True
    assert sm == {"a": P}


# --------------------------------------------------------------------------- #
# get_eval_report（顶层报告生成）
# --------------------------------------------------------------------------- #
def _fake_test_spec(iid="i1", repo="fake/repo", version="1.0",
                    f2p=("a",), p2p=("b",)):
    return SimpleNamespace(
        instance_id=iid, repo=repo, version=version,
        FAIL_TO_PASS=list(f2p), PASS_TO_PASS=list(p2p),
    )


def test_eval_report_patch_is_none(monkeypatch):
    spec = _fake_test_spec()
    pred = {KEY_INSTANCE_ID: "i1", KEY_PREDICTION: None}
    r = grading.get_eval_report(spec, pred, "/no/such/log", include_tests_status=False)
    assert r["i1"]["patch_is_None"] is True
    assert r["i1"]["resolved"] is False
    assert r["i1"]["patch_exists"] is False


def test_eval_report_patch_exists_but_log_not_found(monkeypatch):
    spec = _fake_test_spec()
    pred = {KEY_INSTANCE_ID: "i1", KEY_PREDICTION: "diff --git ..."}
    monkeypatch.setattr(grading, "get_logs_eval", lambda s, lp: ({}, False))
    r = grading.get_eval_report(spec, pred, "/no/such/log", include_tests_status=False)
    assert r["i1"]["patch_exists"] is True
    assert r["i1"]["patch_successfully_applied"] is False
    assert r["i1"]["resolved"] is False


def test_eval_report_resolved_true_when_full(monkeypatch):
    spec = _fake_test_spec(f2p=("a",), p2p=("b",))
    pred = {KEY_INSTANCE_ID: "i1", KEY_PREDICTION: "diff"}
    monkeypatch.setattr(grading, "get_logs_eval",
                        lambda s, lp: ({"a": P, "b": P}, True))
    r = grading.get_eval_report(spec, pred, "/log", include_tests_status=False)
    assert r["i1"]["patch_successfully_applied"] is True
    assert r["i1"]["resolved"] is True


def test_eval_report_resolved_false_when_f2p_partial(monkeypatch):
    spec = _fake_test_spec(f2p=("a", "c"), p2p=("b",))
    pred = {KEY_INSTANCE_ID: "i1", KEY_PREDICTION: "diff"}
    monkeypatch.setattr(grading, "get_logs_eval",
                        lambda s, lp: ({"a": P, "b": P, "c": F}, True))
    r = grading.get_eval_report(spec, pred, "/log", include_tests_status=False)
    assert r["i1"]["resolved"] is False


def test_eval_report_resolved_false_when_p2p_failure(monkeypatch):
    spec = _fake_test_spec(f2p=("a",), p2p=("b", "d"))
    pred = {KEY_INSTANCE_ID: "i1", KEY_PREDICTION: "diff"}
    monkeypatch.setattr(grading, "get_logs_eval",
                        lambda s, lp: ({"a": P, "b": P, "d": F}, True))
    r = grading.get_eval_report(spec, pred, "/log", include_tests_status=False)
    assert r["i1"]["resolved"] is False  # P2P 有失败 → NO


def test_eval_report_includes_tests_status_when_asked(monkeypatch):
    spec = _fake_test_spec()
    pred = {KEY_INSTANCE_ID: "i1", KEY_PREDICTION: "diff"}
    monkeypatch.setattr(grading, "get_logs_eval",
                        lambda s, lp: ({"a": P, "b": P}, True))
    r = grading.get_eval_report(spec, pred, "/log", include_tests_status=True)
    assert "tests_status" in r["i1"]
    assert r["i1"]["tests_status"][FAIL_TO_PASS]["success"] == ["a"]


def test_eval_report_excludes_tests_status_by_default(monkeypatch):
    spec = _fake_test_spec()
    pred = {KEY_INSTANCE_ID: "i1", KEY_PREDICTION: "diff"}
    monkeypatch.setattr(grading, "get_logs_eval",
                        lambda s, lp: ({"a": P, "b": P}, True))
    r = grading.get_eval_report(spec, pred, "/log", include_tests_status=False)
    assert "tests_status" not in r["i1"]


def test_eval_report_fail_only_repo_uses_fail_only_eval_type(monkeypatch):
    # FAIL_ONLY_REPOS 内的 repo → EvalType.FAIL_ONLY
    spec = _fake_test_spec(repo=next(iter(FAIL_ONLY_REPOS)),
                           f2p=("a",), p2p=("b",))
    pred = {KEY_INSTANCE_ID: "i1", KEY_PREDICTION: "diff"}
    monkeypatch.setattr(grading, "get_logs_eval",
                        lambda s, lp: ({"a": F, "b": P}, True))
    r = grading.get_eval_report(spec, pred, "/log", include_tests_status=False)
    assert r["i1"]["resolved"] is False
