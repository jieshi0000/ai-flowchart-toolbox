-- D02 后续完善：浏览器会话只用于恢复关联，不作为资源授权依据。
-- 已存在的任务保留 NULL，避免升级时伪造会话归属；新版客户端会在创建时传入 session_id。
ALTER TABLE flowchart_task
    ADD COLUMN session_id VARCHAR(64);

ALTER TABLE flowchart_task
    ADD CONSTRAINT ck_flowchart_task_session_id
    CHECK (
        session_id IS NULL
        OR session_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$'
    );

-- 按用户和浏览器会话恢复任务；user_id 始终在查询条件中，避免 session_id 成为授权依据。
CREATE INDEX idx_flowchart_task_user_session_created_at
    ON flowchart_task(user_id, session_id, created_at DESC)
    WHERE session_id IS NOT NULL;

-- 缓存已清理时，工作台可按用户恢复最近的未结束任务。
CREATE INDEX idx_flowchart_task_active_user_created_at
    ON flowchart_task(user_id, created_at DESC)
    WHERE status IN (
        'waiting',
        'submitting',
        'provider_queued',
        'provider_processing',
        'validating',
        'rendering'
    );
