INSERT INTO sys_user (id, username, phone, password_hash, nickname, role, status)
VALUES (
    '01900000-0000-7000-8000-000000000001',
    'admin',
    NULL,
    '$2b$12$nO/USnHvytaofA1j1LGTj.DXdZynXEfSzi7SgPuhjwYfgwQpt6Xdi',
    '管理员',
    'admin',
    'ENABLED'
)
ON CONFLICT (id) DO NOTHING;
