-- ============================================================================
-- 003_swe_bench_image_strategy_up.sql
-- 数据库元信息补全：镜像策略 + 仓库 URL + 任务定位 三类 6 项派生信息
--
-- 改动摘要：
--   1. images 表新增 3 列：
--      - namespace                 镜像所在的 Docker 命名空间
--                                  ('swebench' for pull, 'none' for build)
--      - cache_level_recommended   harness 推荐 cache_level
--                                  ('env' / 'instance' / 'none')
--      - recommended_timeout       推荐超时秒数（按 F2P+P2P+patch_size 派生）
--   2. tasks 表新增 2 列：
--      - instance_url              GitHub Issue 链接，从 instance_id 派生
--      - exec_difficulty_class     派生难度分级 (easy / medium / hard)
--   3. repositories 表新增 1 列：
--      - ssh_url                   SSH clone URL，从 repo_full_name 派生
--   4. v_lite 兼容视图新增 9 字段（32 → 41）
--   5. v_task_full 在 images JSON 中增 3 字段，顶层增 3 字段
--
-- 设计动机：
--   - Layer A 派生信息前置到 DB，避免每次跑题时重复推导；
--   - 出题方/选题方/教学方都能"开箱即用"地获取 namespace + cache_level + timeout；
--   - instance_url / ssh_url 让人工可以直接从 DB 跳到 GitHub。
--
-- 幂等性：build_swe_bench.py 每次先执行 001 down，再按文件名字典序应用 up 链。
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ---- ① images 表新增镜像策略元信息 ----
ALTER TABLE images ADD COLUMN namespace TEXT NOT NULL DEFAULT 'swebench';
ALTER TABLE images ADD COLUMN cache_level_recommended TEXT NOT NULL DEFAULT 'env';
ALTER TABLE images ADD COLUMN recommended_timeout INTEGER NOT NULL DEFAULT 1800;

-- ---- ② tasks 表新增派生定位与难度字段 ----
ALTER TABLE tasks ADD COLUMN instance_url TEXT;
ALTER TABLE tasks ADD COLUMN exec_difficulty_class TEXT;

-- ---- ③ repositories 表新增 SSH URL ----
ALTER TABLE repositories ADD COLUMN ssh_url TEXT;

-- ---- ④ v_lite 兼容视图：增加 9 个字段 ----
DROP VIEW IF EXISTS v_lite;
CREATE VIEW v_lite AS
SELECT
    t.task_id                                                          AS instance_id,
    t.split                                                            AS split,
    r.repo_full_name                                                   AS repo,
    r.repo_url                                                         AS repo_url,
    r.ssh_url                                                          AS ssh_url,
    r.default_branch                                                   AS default_branch,
    t.version                                                          AS version,
    t.base_commit                                                      AS base_commit,
    t.environment_setup_commit                                         AS environment_setup_commit,
    t.issue_created_at                                                 AS issue_created_at,
    t.instance_url                                                     AS instance_url,
    t.exec_difficulty_class                                            AS exec_difficulty_class,
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
    -- 新增：镜像 namespace（拉镜像时用的命名空间）
    (SELECT i.namespace FROM images i
        WHERE i.task_id = t.task_id AND i.arch = 'x86_64' AND i.deleted_at IS NULL)
                                                                     AS image_namespace_x86_64,
    (SELECT i.namespace FROM images i
        WHERE i.task_id = t.task_id AND i.arch = 'arm64'  AND i.deleted_at IS NULL)
                                                                     AS image_namespace_arm64,
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
    -- 新增：推荐 cache_level（双架构）
    (SELECT i.cache_level_recommended FROM images i
        WHERE i.task_id = t.task_id AND i.arch = 'x86_64' AND i.deleted_at IS NULL)
                                                                     AS cache_level_x86_64,
    (SELECT i.cache_level_recommended FROM images i
        WHERE i.task_id = t.task_id AND i.arch = 'arm64'  AND i.deleted_at IS NULL)
                                                                     AS cache_level_arm64,
    -- 新增：推荐超时（两架构共用同一值，取 x86_64 行）
    (SELECT i.recommended_timeout FROM images i
        WHERE i.task_id = t.task_id AND i.arch = 'x86_64' AND i.deleted_at IS NULL)
                                                                     AS recommended_timeout,
    -- 大字段
    t.problem_statement                                                AS problem_statement,
    t.hints_text                                                       AS hints_text,
    t.patch                                                            AS patch,
    t.test_patch                                                       AS test_patch,
    t.fail_to_pass                                                     AS fail_to_pass,
    t.pass_to_pass                                                     AS pass_to_pass
FROM tasks t
JOIN repositories r ON r.repo_id = t.repo_id
WHERE t.deleted_at IS NULL;

-- ---- ⑤ v_task_full 一站式视图：在 images JSON 增加 namespace/cache_level/timeout ----
DROP VIEW IF EXISTS v_task_full;
CREATE VIEW v_task_full AS
SELECT
    t.task_id, t.dataset_name, t.split, t.language, t.status,
    t.base_commit, t.issue_created_at, t.instance_url, t.exec_difficulty_class,
    t.version, t.problem_statement, t.hints_text,
    t.fail_to_pass, t.pass_to_pass, t.f2p_count, t.p2p_count,
    r.repo_full_name, r.project_name, r.repo_url, r.ssh_url, r.default_branch,
    COALESCE((
        SELECT json_group_array(json_object(
            'arch', i.arch, 'image_name', i.image_name,
            'base_image', i.base_image_name,
            'namespace', i.namespace,
            'cache_level_recommended', i.cache_level_recommended,
            'recommended_timeout', i.recommended_timeout,
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
