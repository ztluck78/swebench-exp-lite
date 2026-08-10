-- ============================================================================
-- 002_swe_bench_metadata_up.sql
-- 数据库元信息补全：补 audit 暴露的 3 个缺口
--
-- 改动摘要：
--   1. images 表新增 base_image_name 列
--      命名规则：sweb.base.{language}.{arch}[.{docker_specs_hash}]:latest
--      来源：tools/SWE-bench/swebench/harness/test_spec/test_spec.py:72-87
--      每个 images 行只保存当前 arch 对应的 base image，保持规范化。
--   2. tasks 表新增 issue_created_at 列
--      原始需求：审计 3.10 指出 DB 创建时间 ≠ issue 提交时间，前者无意义
--      取值：jsonl 中 instance_id 同名字段（issue 在 GitHub 的提交时间）
--   3. v_lite 视图新增 5 字段：repo_url, default_branch,
--      base_image_x86_64, base_image_arm64, issue_created_at
--   4. v_task_full 视图在 images JSON 中新增 base_image 字段
--   5. repositories.default_branch 保持可空；首次运行只需 repo_url + base_commit，
--      不依赖默认分支。
--
-- 构建幂等性：build_swe_bench.py 每次先执行 001 down，再按顺序应用 up 链。
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ---- ① images 表新增当前架构对应的 base image 名称 ----
-- SQLite 的 ADD COLUMN 不支持 IF NOT EXISTS；构建器会先完整清理旧 schema，
-- 再按顺序应用迁移链，因此不会重复执行本语句。
ALTER TABLE images ADD COLUMN base_image_name TEXT;

-- ---- ② tasks 表新增 issue_created_at 字段（jsonl 原始时间） ----
ALTER TABLE tasks ADD COLUMN issue_created_at TEXT;

-- ---- ③ v_lite 兼容视图：增加 5 个字段 ----
-- 注意：必须先 DROP 再 CREATE；新视图完整列出所有 26 + 5 = 31 字段
DROP VIEW IF EXISTS v_lite;
CREATE VIEW v_lite AS
SELECT
    t.task_id                                                          AS instance_id,
    t.split                                                            AS split,
    r.repo_full_name                                                   AS repo,
    r.repo_url                                                         AS repo_url,
    r.default_branch                                                   AS default_branch,
    t.version                                                          AS version,
    t.base_commit                                                      AS base_commit,
    t.issue_created_at                                                 AS issue_created_at,
    COALESCE(t.language, 'py')                                         AS language,
    t.created_at                                                       AS created_at,
    t.f2p_count                                                        AS f2p_count,
    t.p2p_count                                                        AS p2p_count,
    t.test_patch_size                                                  AS test_patch_size,
    t.patch_size                                                       AS patch_size,
    length(t.problem_statement)                                        AS problem_size,
    -- 实例镜像（双架构）
    (SELECT i.image_name FROM images i
        WHERE i.task_id = t.task_id AND i.arch = 'x86_64' AND i.deleted_at IS NULL)
                                                                     AS image_x86_64,
    (SELECT i.image_name FROM images i
        WHERE i.task_id = t.task_id AND i.arch = 'arm64'  AND i.deleted_at IS NULL)
                                                                     AS image_arm64,
    -- 镜像获取方式（pull / build）
    (SELECT CASE WHEN p.is_remote = 1 THEN 'pull' ELSE 'build' END
        FROM images i JOIN image_pull_info p ON p.image_id = i.image_id
        WHERE i.task_id = t.task_id AND i.arch = 'x86_64'
          AND i.deleted_at IS NULL AND p.deleted_at IS NULL)         AS image_mode_x86_64,
    (SELECT CASE WHEN p.is_remote = 1 THEN 'pull' ELSE 'build' END
        FROM images i JOIN image_pull_info p ON p.image_id = i.image_id
        WHERE i.task_id = t.task_id AND i.arch = 'arm64'
          AND i.deleted_at IS NULL AND p.deleted_at IS NULL)         AS image_mode_arm64,
    -- 完整 docker pull 命令
    (SELECT CASE WHEN p.is_remote = 1
                 THEN (p.pull_command || ' ' || COALESCE(p.pull_args, ''))
                 ELSE NULL END
        FROM images i JOIN image_pull_info p ON p.image_id = i.image_id
        WHERE i.task_id = t.task_id AND i.arch = 'x86_64'
          AND i.deleted_at IS NULL AND p.deleted_at IS NULL)         AS pull_cmd_x86_64,
    (SELECT CASE WHEN p.is_remote = 1
                 THEN (p.pull_command || ' ' || COALESCE(p.pull_args, ''))
                 ELSE NULL END
        FROM images i JOIN image_pull_info p ON p.image_id = i.image_id
        WHERE i.task_id = t.task_id AND i.arch = 'arm64'
          AND i.deleted_at IS NULL AND p.deleted_at IS NULL)         AS pull_cmd_arm64,
    -- arm64 本地构建说明（若 arm64 = build）
    (SELECT p.notes
        FROM images i JOIN image_pull_info p ON p.image_id = i.image_id
        WHERE i.task_id = t.task_id AND i.arch = 'arm64'
          AND i.deleted_at IS NULL AND p.deleted_at IS NULL)         AS build_instructions,
    -- 新增：base image 名称（双架构，由每个架构行的单列投影）
    (SELECT i.base_image_name FROM images i
        WHERE i.task_id = t.task_id AND i.arch = 'x86_64' AND i.deleted_at IS NULL)
                                                                     AS base_image_x86_64,
    (SELECT i.base_image_name FROM images i
        WHERE i.task_id = t.task_id AND i.arch = 'arm64'  AND i.deleted_at IS NULL)
                                                                     AS base_image_arm64,
    -- 大字段
    t.problem_statement                                                AS problem_statement,
    t.hints_text                                                       AS hints_text,
    t.patch                                                            AS patch,
    t.test_patch                                                       AS test_patch,
    t.fail_to_pass                                                     AS fail_to_pass,
    t.pass_to_pass                                                     AS pass_to_pass,
    t.environment_setup_commit                                         AS environment_setup_commit
FROM tasks t
JOIN repositories r ON r.repo_id = t.repo_id
WHERE t.deleted_at IS NULL;

-- ---- ④ v_task_full 一站式视图：在 images JSON 增加 base_image ----
DROP VIEW IF EXISTS v_task_full;
CREATE VIEW v_task_full AS
SELECT
    t.task_id, t.dataset_name, t.split, t.language, t.status,
    t.base_commit, t.issue_created_at, t.version,
    t.problem_statement, t.hints_text,
    t.fail_to_pass, t.pass_to_pass, t.f2p_count, t.p2p_count,
    r.repo_full_name, r.project_name, r.repo_url, r.default_branch,
    COALESCE((
        SELECT json_group_array(json_object(
            'arch', i.arch, 'image_name', i.image_name,
            'base_image', i.base_image_name,
            'tag', i.tag, 'registry', i.registry, 'image_type', i.image_type,
            'pull_infos', (
                SELECT json_group_array(json_object(
                    'registry_url', pi.registry_url, 'pull_command', pi.pull_command,
                    'pull_args', pi.pull_args, 'is_remote', pi.is_remote, 'notes', pi.notes))
                FROM image_pull_info pi
                WHERE pi.image_id = i.image_id AND pi.deleted_at IS NULL),
            'download_infos', (
                SELECT json_group_array(json_object(
                    'download_url', di.download_url, 'checksum', di.checksum,
                    'cache_path', di.cache_path))
                FROM image_download_info di
                WHERE di.image_id = i.image_id AND di.deleted_at IS NULL)
        ))
        FROM images i WHERE i.task_id = t.task_id AND i.deleted_at IS NULL
    ), '[]') AS images
FROM tasks t
JOIN repositories r ON r.repo_id = t.repo_id
WHERE t.deleted_at IS NULL;
