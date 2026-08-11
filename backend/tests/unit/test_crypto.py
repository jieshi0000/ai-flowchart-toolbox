"""指甲切片：验证 Settings 加载时自动解密 ENC(...)。"""

import pytest
from cryptography.fernet import Fernet

from app.core.config import Settings
from app.core.crypto import decrypt


@pytest.fixture
def config_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("CONFIG_KEY", key)
    return key


def _enc(key: str, plaintext: str) -> str:
    token = Fernet(key.encode()).encrypt(plaintext.encode()).decode()
    return f"ENC({token})"


class TestDecrypt:
    def test_plain_passthrough(self):
        assert decrypt("hello") == "hello"

    def test_full_value(self, config_key):
        assert decrypt(_enc(config_key, "secret")) == "secret"

    def test_embedded_in_url(self, config_key):
        enc_pwd = _enc(config_key, "RealPass!")
        # 规范示例：密码段用 ENC(...) 嵌入连接串
        raw = enc_pwd[4:-1]
        url = f"postgresql://app:ENC({raw})@localhost:5432/db"
        assert decrypt(url) == "postgresql://app:RealPass!@localhost:5432/db"

    def test_missing_key_raises(self, monkeypatch):
        monkeypatch.delenv("CONFIG_KEY", raising=False)
        key = Fernet.generate_key().decode()
        with pytest.raises(ValueError, match="CONFIG_KEY"):
            decrypt(_enc(key, "x"))


class TestSettingsAutoDecrypt:
    def test_database_url_full_enc(self, config_key, monkeypatch):
        plain = "postgresql://app:RealPass!@localhost:5432/nail_clip"
        monkeypatch.setenv("DATABASE__URL", _enc(config_key, plain))
        # 避免读到仓库 .env 里的明文盖掉我们的用例意图：显式关掉 env_file
        s = Settings(_env_file=None)
        assert s.database.url == plain

    def test_redis_url_plain_still_works(self, monkeypatch):
        monkeypatch.delenv("CONFIG_KEY", raising=False)
        monkeypatch.setenv("REDIS__URL", "redis://:plain@localhost:6379/0")
        s = Settings(_env_file=None)
        assert s.redis.url == "redis://:plain@localhost:6379/0"

    def test_sso_client_secret_enc(self, config_key, monkeypatch):
        monkeypatch.setenv("AUTH__SSO__CLIENT_SECRET", _enc(config_key, "sso-secret"))
        s = Settings(_env_file=None)
        assert s.auth.sso.client_secret == "sso-secret"
