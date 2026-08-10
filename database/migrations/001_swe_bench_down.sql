-- ============================================================================
-- 001_swe_bench_down.sql
-- 回滚 001_swe_bench_up.sql：删除视图、触发器、索引与全部 5 张表 + FTS5。
-- 执行方式：sqlite3 <db> < 001_swe_bench_down.sql
--           或由 database/build_swe_bench.py 的 --down 模式执行。
-- 注意：DROP 顺序需先视图/触发器/索引，再子表→父表；FTS5 虚表最后。
-- ============================================================================

DROP VIEW IF EXISTS v_task_full;
DROP VIEW IF EXISTS v_lite;

DROP TRIGGER IF EXISTS tasks_au;
DROP TRIGGER IF EXISTS tasks_ad;
DROP TRIGGER IF EXISTS tasks_ai;

DROP INDEX IF EXISTS idx_dl_img;
DROP INDEX IF EXISTS idx_pull_img;
DROP INDEX IF EXISTS idx_images_task;
DROP INDEX IF EXISTS idx_tasks_status;
DROP INDEX IF EXISTS idx_tasks_split;
DROP INDEX IF EXISTS idx_tasks_repo;

DROP TABLE IF EXISTS image_download_info;
DROP TABLE IF EXISTS image_pull_info;
DROP TABLE IF EXISTS images;
DROP TABLE IF EXISTS tasks;
DROP TABLE IF EXISTS repositories;
DROP TABLE IF EXISTS tasks_fts;
