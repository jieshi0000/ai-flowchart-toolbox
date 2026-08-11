CREATE TABLE IF NOT EXISTS sys_user (
    id            UUID PRIMARY KEY,
    username      VARCHAR(50),
    phone         VARCHAR(20),
    password_hash VARCHAR(255),
    nickname      VARCHAR(50),
    role          VARCHAR(20) NOT NULL DEFAULT 'user',
    status        VARCHAR(20) NOT NULL DEFAULT 'ENABLED',
    deleted_at    TIMESTAMP,
    created_at    TIMESTAMP NOT NULL DEFAULT now(),
    updated_at    TIMESTAMP NOT NULL DEFAULT now()
);

COMMENT ON TABLE sys_user IS '系统用户表';

CREATE INDEX IF NOT EXISTS idx_sys_user_username ON sys_user(username);
CREATE INDEX IF NOT EXISTS idx_sys_user_phone ON sys_user(phone);
