-- ============================================================================
-- 001_swe_bench_up.sql
-- 规范化 SWE-bench 元数据库（5 表 + FTS5 + 一站式视图）
--
-- 覆盖范围（当前）：SWE-bench Lite（test 300 + dev 23 = 323）。
-- 多数据集就绪：tasks.dataset_name / split / language 三列使将来加
--   Verified / Original / Pro 时零改表，仅多插数据。
-- 执行方式：由 database/build_swe_bench.py 读取并以 executescript 应用。
-- 注意：PRAGMA foreign_keys 为会话级，需在连接上单独开启（脚本已处理）。
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ① 代码仓库（Lite 18 个；多数据集后自动增多）
CREATE TABLE repositories (
    repo_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_full_name TEXT NOT NULL UNIQUE,        -- 'django/django'
    project_name   TEXT,
    repo_url       TEXT NOT NULL,               -- https://github.com/django/django
    default_branch TEXT,
    vcs            TEXT NOT NULL DEFAULT 'git',
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_at     TEXT                         -- 软删除
);

-- ② 任务（核心，多数据集就绪）
CREATE TABLE tasks (
    task_id                   TEXT PRIMARY KEY,  -- instance_id
    repo_id                   INTEGER NOT NULL REFERENCES repositories(repo_id),
    dataset_name              TEXT NOT NULL DEFAULT 'lite',  -- lite/verified/original/pro…
    split                     TEXT,              -- test / dev / train
    language                  TEXT,              -- python/js/ts/go（pro 用）
    base_commit               TEXT NOT NULL,
    environment_setup_commit  TEXT,
    version                   TEXT,
    problem_statement         TEXT NOT NULL,
    hints_text                TEXT,
    patch                     TEXT NOT NULL,     -- 金标准 diff
    test_patch                TEXT NOT NULL,
    fail_to_pass              TEXT NOT NULL,     -- JSON 文本（JSON1 解析）
    pass_to_pass              TEXT NOT NULL,
    -- 预计算指标（保留扁平库价值）
    f2p_count                 INTEGER,
    p2p_count                 INTEGER,
    patch_size                INTEGER,
    test_patch_size           INTEGER,
    -- 管理库定位：状态跟踪
    status                    TEXT NOT NULL DEFAULT 'imported'
                                 CHECK (status IN ('imported','pending','running','resolved','failed','error')),
    created_at                TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at                TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_at                TEXT
);

-- ③ 运行镜像（修正关键：支持多架构，1:N from task）
CREATE TABLE images (
    image_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id       TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    arch          TEXT NOT NULL DEFAULT 'x86_64' CHECK (arch IN ('x86_64','arm64')),
    image_name    TEXT NOT NULL,                 -- swebench/sweb.eval.x86_64.xxx:latest
    tag           TEXT NOT NULL DEFAULT 'latest',
    registry      TEXT NOT NULL DEFAULT 'dockerhub',
    image_type    TEXT NOT NULL DEFAULT 'eval' CHECK (image_type IN ('eval','pro')),
    dockerhub_tag TEXT,                          -- pro 原始字段
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_at    TEXT,
    UNIQUE (task_id, arch)                       -- 替代旧单列 task_id UNIQUE
);

-- ④ 镜像拉取信息（1:N，每架构各自策略）
CREATE TABLE image_pull_info (
    pull_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id     INTEGER NOT NULL REFERENCES images(image_id) ON DELETE CASCADE,
    registry_url TEXT NOT NULL DEFAULT 'https://hub.docker.com',
    pull_command TEXT NOT NULL DEFAULT 'docker pull',  -- 或 'docker build'
    pull_args    TEXT,
    is_remote    INTEGER NOT NULL DEFAULT 1,    -- 1 远端pull / 0 本地build
    notes        TEXT,                          -- arm 本地构建说明
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_at   TEXT
);

-- ⑤ 镜像下载信息（按决策：仅结构，不插数据）
CREATE TABLE image_download_info (
    download_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id      INTEGER NOT NULL REFERENCES images(image_id) ON DELETE CASCADE,
    download_url  TEXT,
    checksum      TEXT,
    checksum_type TEXT DEFAULT 'sha256' CHECK (checksum_type IN ('sha256','md5','sha512')),
    cache_path    TEXT,
    file_size     INTEGER,
    expires_at    TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_at    TEXT
);

-- ---- 索引（partial，软删除友好） ------------------------------------------------
CREATE INDEX idx_tasks_repo    ON tasks(repo_id)    WHERE deleted_at IS NULL;
CREATE INDEX idx_tasks_split   ON tasks(split)      WHERE deleted_at IS NULL;
CREATE INDEX idx_tasks_status  ON tasks(status)     WHERE deleted_at IS NULL;
CREATE INDEX idx_images_task   ON images(task_id)   WHERE deleted_at IS NULL;
CREATE INDEX idx_pull_img      ON image_pull_info(image_id);
CREATE INDEX idx_dl_img        ON image_download_info(image_id);

-- ---- FTS5 全文检索（挂在 problem_statement + hints_text） ----------------------
CREATE VIRTUAL TABLE tasks_fts USING fts5(
    task_id UNINDEXED,
    problem_statement,
    hints_text,
    content='tasks',
    content_rowid='rowid'
);
CREATE TRIGGER tasks_ai AFTER INSERT ON tasks BEGIN
  INSERT INTO tasks_fts(rowid, task_id, problem_statement, hints_text)
  VALUES (new.rowid, new.task_id, new.problem_statement, new.hints_text);
END;
CREATE TRIGGER tasks_ad AFTER DELETE ON tasks BEGIN
  INSERT INTO tasks_fts(tasks_fts, rowid, task_id, problem_statement, hints_text)
  VALUES('delete', old.rowid, old.task_id, old.problem_statement, old.hints_text);
END;
CREATE TRIGGER tasks_au AFTER UPDATE ON tasks BEGIN
  INSERT INTO tasks_fts(tasks_fts, rowid, task_id, problem_statement, hints_text)
  VALUES('delete', old.rowid, old.task_id, old.problem_statement, old.hints_text);
  INSERT INTO tasks_fts(rowid, task_id, problem_statement, hints_text)
  VALUES (new.rowid, new.task_id, new.problem_statement, new.hints_text);
END;

-- ---- 一站式视图：按 task_id 出全部五类（含多架构镜像与拉取策略） -----------------
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
JOIN repositories r ON r.repo_id = t.repo_id;

-- ---- 兼容视图 v_lite：把规范化 schema 拍平成旧 instances 的列名 ----
-- 目的：database.query.LiteDB 的既有 API（instance_id / repo / image_x86_64 /
--       image_mode_* / pull_cmd_* / build_instructions …）无需改动即可在新
--       schema 上工作，调用方无感。
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
        WHERE i.task_id = t.task_id AND i.arch = 'x86_64' AND i.deleted_at IS NULL)        AS image_x86_64,
    (SELECT i.image_name FROM images i
        WHERE i.task_id = t.task_id AND i.arch = 'arm64'  AND i.deleted_at IS NULL)        AS image_arm64,
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
FROM tasks t
JOIN repositories r ON r.repo_id = t.repo_id
WHERE t.deleted_at IS NULL;
