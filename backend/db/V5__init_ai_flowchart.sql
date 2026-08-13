-- Day 2: AI 流程图领域表。
-- 业务主键由应用使用 UUID v7 生成；本迁移不增加跨表外键，归属和状态一致性由应用层保证。

CREATE TABLE IF NOT EXISTS flowchart_document (
    id              UUID PRIMARY KEY,
    user_id         VARCHAR(64) NOT NULL,
    title           VARCHAR(100) NOT NULL,
    direction       VARCHAR(4) NOT NULL DEFAULT 'TB',
    diagram_data    JSONB NOT NULL,
    mermaid_source  TEXT NOT NULL DEFAULT '',
    version         INTEGER NOT NULL DEFAULT 1,
    source_task_id  UUID,
    expires_at      TIMESTAMP NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_flowchart_document_direction CHECK (direction IN ('TB', 'LR')),
    CONSTRAINT ck_flowchart_document_version CHECK (version >= 1)
);

CREATE TABLE IF NOT EXISTS flowchart_task (
    id                  UUID PRIMARY KEY,
    user_id             VARCHAR(64) NOT NULL,
    type                VARCHAR(40) NOT NULL,
    status              VARCHAR(32) NOT NULL DEFAULT 'waiting',
    progress            INTEGER NOT NULL DEFAULT 0,
    stage               VARCHAR(80),
    request_snapshot    JSONB NOT NULL,
    result              JSONB,
    document_id         UUID,
    output_file_id      UUID,
    provider_id         VARCHAR(80),
    model_name          VARCHAR(160),
    provider_request_id VARCHAR(255),
    provider_status     VARCHAR(40),
    idempotency_key     VARCHAR(128) NOT NULL,
    poll_count          INTEGER NOT NULL DEFAULT 0,
    retry_count         INTEGER NOT NULL DEFAULT 0,
    next_poll_at        TIMESTAMP,
    deadline_at         TIMESTAMP,
    last_provider_error TEXT,
    usage_report_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    queue_wait_ms       INTEGER,
    provider_wait_ms    INTEGER,
    render_duration_ms  INTEGER,
    error_code          VARCHAR(100),
    error_message       TEXT,
    cost_points         INTEGER NOT NULL DEFAULT 0,
    expires_at          TIMESTAMP NOT NULL,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_flowchart_task_idempotency UNIQUE (user_id, idempotency_key),
    CONSTRAINT ck_flowchart_task_progress CHECK (progress BETWEEN 0 AND 100),
    CONSTRAINT ck_flowchart_task_retry_count CHECK (retry_count >= 0),
    CONSTRAINT ck_flowchart_task_poll_count CHECK (poll_count >= 0)
);

CREATE TABLE IF NOT EXISTS flowchart_file (
    id              UUID PRIMARY KEY,
    user_id         VARCHAR(64) NOT NULL,
    document_id     UUID,
    task_id         UUID,
    original_name   VARCHAR(255) NOT NULL,
    stored_path     VARCHAR(500) NOT NULL,
    file_size       BIGINT NOT NULL,
    mime_type       VARCHAR(80) NOT NULL,
    format          VARCHAR(20) NOT NULL,
    file_role       VARCHAR(40) NOT NULL,
    expires_at      TIMESTAMP NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_flowchart_file_size CHECK (file_size >= 0),
    CONSTRAINT ck_flowchart_file_format CHECK (format IN ('SVG', 'PNG', 'MERMAID', 'JSON'))
);

CREATE TABLE IF NOT EXISTS flowchart_template (
    id              UUID PRIMARY KEY,
    user_id         VARCHAR(64),
    type            VARCHAR(40) NOT NULL,
    category        VARCHAR(80) NOT NULL,
    name            VARCHAR(120) NOT NULL,
    description     TEXT,
    config          JSONB NOT NULL,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS flowchart_quota_log (
    id              UUID PRIMARY KEY,
    user_id         VARCHAR(64) NOT NULL,
    task_id         UUID,
    action          VARCHAR(20) NOT NULL,
    points          INTEGER NOT NULL,
    balance_before  INTEGER,
    balance_after   INTEGER,
    reason          VARCHAR(255),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS flowchart_provider_call (
    id              UUID PRIMARY KEY,
    task_id         UUID NOT NULL,
    user_id         VARCHAR(64) NOT NULL,
    provider_id     VARCHAR(80) NOT NULL,
    model_name      VARCHAR(160) NOT NULL,
    protocol        VARCHAR(40) NOT NULL,
    request_id      VARCHAR(255),
    operation       VARCHAR(20) NOT NULL,
    status          VARCHAR(20) NOT NULL,
    duration_ms     INTEGER,
    poll_count      INTEGER NOT NULL DEFAULT 0,
    retry_count     INTEGER NOT NULL DEFAULT 0,
    fallback_reason VARCHAR(255),
    cost_amount     NUMERIC(12, 6),
    error_code      VARCHAR(120),
    error_message   TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS flowchart_event (
    id              UUID PRIMARY KEY,
    user_id         VARCHAR(64),
    event_name      VARCHAR(80) NOT NULL,
    task_id         UUID,
    document_id     UUID,
    payload         JSONB,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE flowchart_document IS '流程图文档表，diagram_data 为唯一权威的 JSON 中间结构';
COMMENT ON TABLE flowchart_task IS '异步任务表，记录模型提交、供应商轮询、校验、渲染和导出任务';
COMMENT ON TABLE flowchart_file IS '导出文件表，保存 SVG、PNG、Mermaid、JSON 的对象存储路径';
COMMENT ON TABLE flowchart_template IS '流程图模板表，user_id 为空时表示系统模板';
COMMENT ON TABLE flowchart_quota_log IS '积分流水表，记录冻结、确认扣减和退款';
COMMENT ON TABLE flowchart_provider_call IS '模型调用日志表，不保存 API Key 或请求密文';
COMMENT ON TABLE flowchart_event IS '埋点事件表，记录生成、编辑、导出和下载行为';

CREATE INDEX IF NOT EXISTS idx_flowchart_document_user_id
    ON flowchart_document(user_id);
CREATE INDEX IF NOT EXISTS idx_flowchart_document_expires_at
    ON flowchart_document(expires_at);

CREATE INDEX IF NOT EXISTS idx_flowchart_task_user_id
    ON flowchart_task(user_id);
CREATE INDEX IF NOT EXISTS idx_flowchart_task_status
    ON flowchart_task(status);
CREATE INDEX IF NOT EXISTS idx_flowchart_task_document_id
    ON flowchart_task(document_id);
CREATE INDEX IF NOT EXISTS idx_flowchart_task_next_poll_at
    ON flowchart_task(next_poll_at)
    WHERE status IN ('provider_queued', 'provider_processing');
CREATE INDEX IF NOT EXISTS idx_flowchart_task_deadline_at
    ON flowchart_task(deadline_at)
    WHERE status IN ('waiting', 'submitting', 'provider_queued', 'provider_processing');

CREATE INDEX IF NOT EXISTS idx_flowchart_file_user_id
    ON flowchart_file(user_id);
CREATE INDEX IF NOT EXISTS idx_flowchart_file_expires_at
    ON flowchart_file(expires_at);

CREATE INDEX IF NOT EXISTS idx_flowchart_template_user_category
    ON flowchart_template(user_id, category);
CREATE INDEX IF NOT EXISTS idx_flowchart_provider_call_task_id
    ON flowchart_provider_call(task_id);
CREATE INDEX IF NOT EXISTS idx_flowchart_provider_call_provider_model
    ON flowchart_provider_call(provider_id, model_name);
CREATE INDEX IF NOT EXISTS idx_flowchart_event_name
    ON flowchart_event(event_name);
