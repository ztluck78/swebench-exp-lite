-- ============================================================================
-- 003_swe_bench_image_strategy_down.sql
-- 回滚 003_swe_bench_image_strategy_up.sql：恢复 002 状态
--
-- 改动摘要：
--   1. 删除 v_lite / v_task_full 视图
--   2. 删除 003 新加的列（SQLite 3.35+）：
--      - images.namespace
--      - images.cache_level_recommended
--      - images.recommended_timeout
--      - tasks.instance_url
--      - tasks.exec_difficulty_class
--      - repositories.ssh_url
--   3. 重建 v_lite 视图（恢复 002 版本，32 字段）
--   4. 重建 v_task_full 视图（恢复 002 版本）
--
-- 前置：SQLite >= 3.35（支持 DROP COLUMN）
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ---- ① 删视图（先删视图再删列） ----
DROP VIEW IF EXISTS v_task_full;
DROP VIEW IF EXISTS v_lite;

-- ---- ② 删 003 新加的列（SQLite 3.35+ 支持 DROP COLUMN） ----
ALTER TABLE images       DROP COLUMN namespace;
ALTER TABLE images       DROP COLUMN cache_level_recommended;
ALTER TABLE images       DROP COLUMN recommended_timeout;
ALTER TABLE tasks        DROP COLUMN instance_url;
ALTER TABLE tasks        DROP COLUMN exec_difficulty_class;
ALTER TABLE repositories DROP COLUMN ssh_url;

-- ---- ③ 重建 v_lite 视图（恢复 002 状态，32 字段） ----
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
    -- 实例镜像(双架构)
    (SELECT i.image_name FROM images i
        WHERE i.task_id = t.task_id AND i.arch = 'x86_64' AND i.deleted_at IS NULL)
                                                                     AS image_x86_64,
    (SELECT i.image_name FROM images i
        WHERE i.task_id = t.task_id AND i.arch = 'arm64'  AND i.deleted_at IS NULL)
                                                                     AS image_arm64,
    -- base image(双架构)
    (SELECT i.base_image_name FROM images i
        WHERE i.task_id = t.task_id AND i.arch = 'x86_64' AND i.deleted_at IS NULL)
                                                                     AS base_image_x86_64,
    (SELECT i.base_image_name FROM images i
        WHERE i.task_id = t.task_id AND i.arch = 'arm64'  AND i.deleted_at IS NULL)
                                                                     AS base_image_arm64,
    -- 镜像获取方式
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

-- ---- ④ 重建 v_task_full 视图（恢复 002 状态） ----
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
