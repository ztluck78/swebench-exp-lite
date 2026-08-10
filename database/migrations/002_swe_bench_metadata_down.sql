-- ============================================================================
-- 002_swe_bench_metadata_down.sql
-- 回滚 002_swe_bench_metadata_up.sql：恢复 001 状态
--
-- 改动摘要：
--   1. 删除 v_lite / v_task_full 视图
--   2. 删除 images.base_image_name
--   3. 删除 tasks.issue_created_at
--   4. 重建 v_lite / v_task_full 视图（001 版本，无新字段）
--
-- 前置：SQLite >= 3.35（支持 DROP COLUMN）
-- 本机实测 3.53，OK
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ---- ① 删视图（先删视图再删列） ----
DROP VIEW IF EXISTS v_task_full;
DROP VIEW IF EXISTS v_lite;

-- ---- ② 删 002 新加的列（SQLite 3.35+ 支持 DROP COLUMN） ----
ALTER TABLE images DROP COLUMN base_image_name;
ALTER TABLE tasks  DROP COLUMN issue_created_at;

-- ---- ③ 重建 v_lite 视图（恢复 001 状态，26 字段） ----
CREATE VIEW v_lite AS
SELECT
    t.task_id                                                          AS instance_id,
    t.split                                                            AS split,
    r.repo_full_name                                                   AS repo,
    t.version                                                          AS version,
    t.base_commit                                                      AS base_commit,
    COALESCE(t.language, 'py')                                         AS language,
    t.created_at                                                       AS created_at,
    t.f2p_count                                                        AS f2p_count,
    t.p2p_count                                                        AS p2p_count,
    t.test_patch_size                                                  AS test_patch_size,
    t.patch_size                                                       AS patch_size,
    length(t.problem_statement)                                        AS problem_size,
    (SELECT i.image_name FROM images i
        WHERE i.task_id = t.task_id AND i.arch = 'x86_64' AND i.deleted_at IS NULL)
                                                                     AS image_x86_64,
    (SELECT i.image_name FROM images i
        WHERE i.task_id = t.task_id AND i.arch = 'arm64'  AND i.deleted_at IS NULL)
                                                                     AS image_arm64,
    (SELECT CASE WHEN p.is_remote = 1 THEN 'pull' ELSE 'build' END
        FROM images i JOIN image_pull_info p ON p.image_id = i.image_id
        WHERE i.task_id = t.task_id AND i.arch = 'x86_64' AND i.deleted_at IS NULL AND p.deleted_at IS NULL) AS image_mode_x86_64,
    (SELECT CASE WHEN p.is_remote = 1 THEN 'pull' ELSE 'build' END
        FROM images i JOIN image_pull_info p ON p.image_id = i.image_id
        WHERE i.task_id = t.task_id AND i.arch = 'arm64'  AND i.deleted_at IS NULL AND p.deleted_at IS NULL) AS image_mode_arm64,
    (SELECT CASE WHEN p.is_remote = 1 THEN (p.pull_command || ' ' || COALESCE(p.pull_args, '')) ELSE NULL END
        FROM images i JOIN image_pull_info p ON p.image_id = i.image_id
        WHERE i.task_id = t.task_id AND i.arch = 'x86_64' AND i.deleted_at IS NULL AND p.deleted_at IS NULL) AS pull_cmd_x86_64,
    (SELECT CASE WHEN p.is_remote = 1 THEN (p.pull_command || ' ' || COALESCE(p.pull_args, '')) ELSE NULL END
        FROM images i JOIN image_pull_info p ON p.image_id = i.image_id
        WHERE i.task_id = t.task_id AND i.arch = 'arm64'  AND i.deleted_at IS NULL AND p.deleted_at IS NULL) AS pull_cmd_arm64,
    (SELECT p.notes
        FROM images i JOIN image_pull_info p ON p.image_id = i.image_id
        WHERE i.task_id = t.task_id AND i.arch = 'arm64'  AND i.deleted_at IS NULL AND p.deleted_at IS NULL) AS build_instructions,
    t.problem_statement                                                AS problem_statement,
    t.hints_text                                                       AS hints_text,
    t.patch                                                            AS patch,
    t.test_patch                                                       AS test_patch,
    t.fail_to_pass                                                     AS fail_to_pass,
    t.pass_to_pass                                                     AS pass_to_pass,
    t.environment_setup_commit                                         AS environment_setup_commit
;

-- ---- ④ 重建 v_task_full 视图（恢复 001 状态） ----
CREATE VIEW v_task_full AS
SELECT
    t.task_id, t.dataset_name, t.split, t.language, t.status,
    t.base_commit, t.version, t.problem_statement, t.hints_text,
    t.fail_to_pass, t.pass_to_pass, t.f2p_count, t.p2p_count,
    r.repo_full_name, r.project_name, r.repo_url, r.default_branch,
    COALESCE((
        SELECT json_group_array(json_object(
            'arch', i.arch, 'image_name', i.image_name, 'tag', i.tag,
            'registry', i.registry, 'image_type', i.image_type,
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
