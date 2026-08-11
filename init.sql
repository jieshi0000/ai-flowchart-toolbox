-- 由 scaffold 生成，PG 首次启动时自动执行。
-- POSTGRES_DB=flowchart_toolbox_db 已由 PG 镜像自动创建，本脚本只需创建业务用户并授权。
-- 确保本地开发与生产部署的数据库用户/名称/密码完全一致。

-- 0. 预创建扩展（需要超级用户权限）
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 1. 创建业务用户（如不存在）
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'flowchart_toolbox_user') THEN
    CREATE USER flowchart_toolbox_user WITH PASSWORD 'flowchart_toolbox_123456';
  END IF;
END
$$;

-- 2. 授权业务用户访问业务库
GRANT ALL PRIVILEGES ON DATABASE flowchart_toolbox_db TO flowchart_toolbox_user;

-- 3. 授权业务用户在 public schema 下执行 DDL（建表、建索引等）
--    这确保 Flyway 在执行迁移时拥有足够的权限。
GRANT ALL PRIVILEGES ON SCHEMA public TO flowchart_toolbox_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO flowchart_toolbox_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO flowchart_toolbox_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO flowchart_toolbox_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO flowchart_toolbox_user;
