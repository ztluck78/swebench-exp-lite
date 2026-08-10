-- ============================================================================
-- 004_swe_bench_task_hints_up.sql
-- 出题辅助信息前置：关键文件提示 + 复现代码 + 人工难度
--
-- 改动摘要：
--   1. tasks 表新增 3 列：
--      - key_files_hint     关键文件提示（缩小 Agent 搜索范围）
--                           来源：人工标注 / 从 gold_patch 的 +++ 路径推断
--                           初始 NULL，出题时填充
--      - repro_snippet      复现代码片段（从 problem_statement 正则提取）
--                           来源：确定性派生函数 _derive_repro_snippet()
--                           构建时自动填充
--      - difficulty_human   人工难度标注（区别于 exec_difficulty_class 自动派生）
--                           来源：出题人人工标注
--                           初始 NULL，标注后回写
--   2. v_lite 兼容视图新增 3 字段（41 → 44）
--   3. v_task_full 一站式视图顶层新增 3 字段
--
-- 设计动机：
--   - 出题模块（Task Builder）以 DB 优先为原则，prompt 模板中的
--     STEP 2（关键文件提示）和 STEP 3（复现脚本）需要这两个字段；
--   - repro_snippet 是确定性派生（正则提取，不依赖 LLM），适合 DB 一次算好；
--   - key_files_hint 和 difficulty_human 属于任务级稳定信息，但当前
--     暂无自动填充逻辑，留 NULL 由出题人填充。
--
-- 幂等性：build_swe_bench.py 每次先执行 001 down，再按文件名字典序应用 up 链。
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ---- ① tasks 表新增出题辅助字段 ----
ALTER TABLE tasks ADD COLUMN key_files_hint TEXT;
ALTER TABLE tasks ADD COLUMN repro_snippet TEXT;
ALTER TABLE tasks ADD COLUMN difficulty_human TEXT;

-- ---- ② v_lite 兼容视图：增加 3 个字段（41 → 44） ----
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
    -- 新增：出题辅助字段
    t.key_files_hint                                                   AS key_files_hint,
    t.repro_snippet                                                    AS repro_snippet,
    t.difficulty_human                                                 AS difficulty_human,
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
    -- 镜像 namespace（双架构）
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
    -- 推荐 cache_level（双架构）
    (SELECT i.cache_level_recommended FROM images i
        WHERE i.task_id = t.task_id AND i.arch = 'x86_64' AND i.deleted_at IS NULL)
                                                                     AS cache_level_x86_64,
    (SELECT i.cache_level_recommended FROM images i
        WHERE i.task_id = t.task_id AND i.arch = 'arm64'  AND i.deleted_at IS NULL)
                                                                     AS cache_level_arm64,
    -- 推荐超时（两架构共用同一值，取 x86_64 行）
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

-- ---- ③ v_task_full 一站式视图：顶层新增 3 字段 ----
DROP VIEW IF EXISTS v_task_full;
CREATE VIEW v_task_full AS
SELECT
    t.task_id, t.dataset_name, t.split, t.language, t.status,
    t.base_commit, t.issue_created_at, t.instance_url, t.exec_difficulty_class,
    t.key_files_hint, t.repro_snippet, t.difficulty_human,
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
