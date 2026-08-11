CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS demo_product (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(100) NOT NULL,
    description     TEXT,
    price           DECIMAL(16,4) NOT NULL DEFAULT 0,
    stock           INTEGER     NOT NULL DEFAULT 0,
    view_count      BIGINT      NOT NULL DEFAULT 0,
    is_active       BOOLEAN     NOT NULL DEFAULT true,
    status          VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    publish_date    DATE,
    category_id     UUID,
    tags            TEXT[],
    ratings         INTEGER[],
    attributes      JSONB,
    created_at      TIMESTAMP   NOT NULL DEFAULT now(),
    updated_at      TIMESTAMP   NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMP
);

COMMENT ON TABLE demo_product IS '示例商品表（脚手架演示用，可删除）';

CREATE INDEX IF NOT EXISTS idx_demo_product_status ON demo_product(status);
CREATE INDEX IF NOT EXISTS idx_demo_product_category ON demo_product(category_id);
