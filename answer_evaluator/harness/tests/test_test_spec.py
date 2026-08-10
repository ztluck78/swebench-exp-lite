"""answer_evaluator.harness.test_spec 单元测试。

TestSpec 是 SWE-bench 评测的镜像与脚本规格，承载 Docker 镜像 key 生成、
平台架构识别、eval/setup/install 脚本拼接逻辑。本套件覆盖 TestSpec 全部
property + make_test_spec 的 JSON 解析（字符串/列表/缺失键）+
get_test_specs_from_dataset 幂等性。

对应 P0 守护目标：test_spec.py 当前覆盖率 21.8%，目标 70%+。
"""
from __future__ import annotations

import hashlib

import pytest

from answer_evaluator.harness.constants import (
    KEY_INSTANCE_ID,
    MAP_REPO_TO_EXT,
    MAP_REPO_VERSION_TO_SPECS,
)
from answer_evaluator.harness.test_spec.test_spec import (
    TestSpec,
    get_test_specs_from_dataset,
    make_test_spec,
)


@pytest.fixture(autouse=True)
def _stub_network_fetches(monkeypatch):
    """禁止 make_test_spec 触发真实 GitHub fetch requirements.txt。

    make_test_spec 内部链 make_env_script_list → make_env_script_list_py →
    get_requirements → get_requirements_by_commit 会真去 GitHub raw 拉文件，
    测试环境无网络时抛 ValueError。这里把整个网络函数替换为返回桩字符串。
    """
    from answer_evaluator.harness.test_spec import python as _py
    monkeypatch.setattr(_py, "get_requirements_by_commit",
                        lambda repo, commit: "# stubbed requirements\n")


def _mk_spec(*, docker_specs=None, namespace=None, arch="x86_64",
             instance_id="django__django-12345", repo="django/django",
             version="5.0", language="py",
             base_image_tag="latest", env_image_tag="latest",
             instance_image_tag="latest",
             env_script_list=None, repo_script_list=None, eval_script_list=None):
    return TestSpec(
        instance_id=instance_id, repo=repo, version=version,
        repo_script_list=repo_script_list or ["echo repo"],
        eval_script_list=eval_script_list or ["echo eval"],
        env_script_list=env_script_list or ["echo env"],
        arch=arch, FAIL_TO_PASS=["a"], PASS_TO_PASS=["b"],
        language=language, docker_specs=docker_specs or {},
        namespace=namespace,
        base_image_tag=base_image_tag, env_image_tag=env_image_tag,
        instance_image_tag=instance_image_tag,
    )


# --------------------------------------------------------------------------- #
# 脚本拼接 property
# --------------------------------------------------------------------------- #
def test_setup_env_script_has_shebang_and_set_euxo():
    s = _mk_spec().setup_env_script
    assert s.startswith("#!/bin/bash\nset -euxo pipefail\n")
    assert "echo env" in s
    assert s.endswith("\n")


def test_eval_script_uses_set_uxo_without_e_to_allow_revert():
    # eval_script 用 set -uxo（不 -e），避免中途退出拿不到 revert 时机
    lines = _mk_spec().eval_script.split("\n")
    assert lines[0] == "#!/bin/bash"
    assert lines[1] == "set -uxo pipefail"
    assert "echo eval" in lines


def test_install_repo_script_has_shebang_and_euxo():
    s = _mk_spec().install_repo_script
    assert s.startswith("#!/bin/bash\nset -euxo pipefail\n")
    assert "echo repo" in s


# --------------------------------------------------------------------------- #
# base_image_key
# --------------------------------------------------------------------------- #
def test_base_image_key_no_docker_specs_uses_short_format():
    key = _mk_spec(docker_specs={}).base_image_key
    ext = MAP_REPO_TO_EXT["django/django"]
    assert key == f"sweb.base.{ext}.x86_64:latest"


def test_base_image_key_with_docker_specs_includes_hash_prefix():
    specs = {"conda_version": "py311_23.11.0-2"}
    key = _mk_spec(docker_specs=specs).base_image_key
    expected_hash = hashlib.sha256(str(specs).encode("utf-8")).hexdigest()[:10]
    assert expected_hash in key
    assert key.startswith("sweb.base.py.x86_64.")


def test_base_image_key_respects_arch():
    key = _mk_spec(arch="arm64").base_image_key
    # 格式为 sweb.base.py.arm64:latest（arch 直接拼入，无点分隔）
    assert "arm64" in key
    assert ".arm64:" in key


# --------------------------------------------------------------------------- #
# env_image_key
# --------------------------------------------------------------------------- #
def test_env_image_key_hash_length_22():
    spec = _mk_spec(env_script_list=["echo env"])
    key = spec.env_image_key
    expected = hashlib.sha256(
        str(spec.env_script_list).encode("utf-8")
    ).hexdigest()[:22]
    assert expected in key
    assert key.startswith("sweb.env.py.x86_64.")


def test_env_image_key_with_docker_specs_appends_specs_to_hash():
    specs = {"conda_version": "x"}
    spec = _mk_spec(docker_specs=specs)
    hash_key = str(spec.env_script_list) + str(specs)
    expected = hashlib.sha256(hash_key.encode("utf-8")).hexdigest()[:22]
    assert expected in spec.env_image_key


# --------------------------------------------------------------------------- #
# instance_image_key
# --------------------------------------------------------------------------- #
def test_instance_image_key_no_namespace():
    spec = _mk_spec(instance_id="django__django-12345", namespace=None)
    assert spec.instance_image_key == "sweb.eval.x86_64.django__django-12345:latest"


def test_instance_image_key_lowercases_instance_id():
    spec = _mk_spec(instance_id="Django__Django-12345", namespace=None)
    assert "django__django-12345" in spec.instance_image_key


def test_instance_image_key_with_namespace_replaces_dunder():
    spec = _mk_spec(instance_id="django__django-12345", namespace="myorg")
    key = spec.instance_image_key
    assert key.startswith("myorg/sweb.eval.x86_64.django_1776_django-12345:latest")


def test_is_remote_image_reflects_namespace():
    assert _mk_spec(namespace=None).is_remote_image is False
    assert _mk_spec(namespace="myorg").is_remote_image is True


def test_get_instance_container_name_no_run_id():
    spec = _mk_spec(instance_id="django__django-1")
    assert spec.get_instance_container_name() == "sweb.eval.django__django-1"


def test_get_instance_container_name_with_run_id():
    spec = _mk_spec(instance_id="django__django-1")
    assert spec.get_instance_container_name("run-abc") == "sweb.eval.django__django-1.run-abc"


# --------------------------------------------------------------------------- #
# platform
# --------------------------------------------------------------------------- #
def test_platform_x86_64():
    assert _mk_spec(arch="x86_64").platform == "linux/x86_64"


def test_platform_arm64():
    assert _mk_spec(arch="arm64").platform == "linux/arm64/v8"


def test_platform_invalid_raises():
    with pytest.raises(ValueError, match="Invalid architecture"):
        _mk_spec(arch="mips").platform


# --------------------------------------------------------------------------- #
# dockerfile property
# --------------------------------------------------------------------------- #
def test_base_dockerfile_returns_string_with_from():
    df = _mk_spec(arch="x86_64").base_dockerfile
    assert isinstance(df, str)
    assert "FROM" in df


def test_env_dockerfile_references_base_image_key():
    spec = _mk_spec()
    assert spec.base_image_key in spec.env_dockerfile


def test_instance_dockerfile_references_env_image_key():
    spec = _mk_spec()
    assert spec.env_image_key in spec.instance_dockerfile


# --------------------------------------------------------------------------- #
# make_test_spec
# --------------------------------------------------------------------------- #
def _mk_instance_dict(**overrides):
    base = {
        "repo": "django/django",
        "instance_id": "django__django-12345",
        "base_commit": "abc",
        "patch": "diff --git a/x b/x\n",
        "test_patch": "diff --git a/t b/t\n",
        "problem_statement": "ps",
        "hints_text": "",
        "created_at": "2024-01-01",
        "version": "5.0",
        "FAIL_TO_PASS": '["a", "b"]',
        "PASS_TO_PASS": '["c"]',
        "environment_setup_commit": "abc",
    }
    base.update(overrides)
    return base


def test_make_test_spec_parses_json_string_f2p_p2p():
    spec = make_test_spec(_mk_instance_dict())
    assert spec.instance_id == "django__django-12345"
    assert spec.FAIL_TO_PASS == ["a", "b"]
    assert spec.PASS_TO_PASS == ["c"]
    assert spec.language == "py"
    assert spec.version == "5.0"
    assert spec.arch == "x86_64"  # 默认


def test_make_test_spec_accepts_list_f2p_p2p():
    inst = _mk_instance_dict(FAIL_TO_PASS=["x"], PASS_TO_PASS=["y"])
    spec = make_test_spec(inst)
    assert spec.FAIL_TO_PASS == ["x"]
    assert spec.PASS_TO_PASS == ["y"]


def test_make_test_spec_missing_f2p_p2p_returns_empty_list():
    # 验证实例（无 F2P/P2P 键）→ []
    inst = _mk_instance_dict()
    del inst["FAIL_TO_PASS"]
    del inst["PASS_TO_PASS"]
    spec = make_test_spec(inst)
    assert spec.FAIL_TO_PASS == []
    assert spec.PASS_TO_PASS == []


def test_make_test_spec_idempotent_on_test_spec():
    spec1 = make_test_spec(_mk_instance_dict())
    spec2 = make_test_spec(spec1)  # 已是 TestSpec → 直接返回
    assert spec1 is spec2


def test_make_test_spec_asserts_tags_not_none():
    inst = _mk_instance_dict()
    with pytest.raises(AssertionError):
        make_test_spec(inst, base_image_tag=None)
    with pytest.raises(AssertionError):
        make_test_spec(inst, env_image_tag=None)
    with pytest.raises(AssertionError):
        make_test_spec(inst, instance_image_tag=None)


def test_make_test_spec_uses_specs_from_map():
    spec = make_test_spec(_mk_instance_dict())
    expected_specs = MAP_REPO_VERSION_TO_SPECS["django/django"]["5.0"]
    assert spec.docker_specs == expected_specs.get("docker_specs", {})


def test_make_test_spec_passes_namespace_through():
    spec = make_test_spec(_mk_instance_dict(), namespace="myorg")
    assert spec.namespace == "myorg"
    assert spec.is_remote_image is True


def test_make_test_spec_passes_image_tags_through():
    spec = make_test_spec(
        _mk_instance_dict(),
        base_image_tag="v1", env_image_tag="v2", instance_image_tag="v3",
    )
    assert spec.base_image_tag == "v1"
    assert spec.env_image_tag == "v2"
    assert spec.instance_image_tag == "v3"


# --------------------------------------------------------------------------- #
# get_test_specs_from_dataset
# --------------------------------------------------------------------------- #
def test_get_test_specs_from_dataset_idempotent_on_testspec():
    spec = _mk_spec()
    out = get_test_specs_from_dataset([spec])
    assert out == [spec]


def test_get_test_specs_from_dataset_converts_swebenchinstance():
    inst = _mk_instance_dict()
    out = get_test_specs_from_dataset([inst])
    assert len(out) == 1
    assert isinstance(out[0], TestSpec)
    assert out[0].FAIL_TO_PASS == ["a", "b"]
    assert out[0].instance_id == "django__django-12345"


def test_get_test_specs_from_dataset_mixed_list_converts_only_non_testspec():
    spec = _mk_spec()
    inst = _mk_instance_dict()
    out = get_test_specs_from_dataset([spec, inst])
    assert len(out) == 2
    assert out[0] is spec
    # 修复后：检查整个 list 是否全为 TestSpec，混合 list 的 dict 元素也会被转换
    assert isinstance(out[1], TestSpec)
    assert out[1].instance_id == "django__django-12345"
