from app.core.config import get_settings
from app.core.redis_keys import format_key


def test_format_key_matches_java_redis_util_protocol(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings.app, "name", "demo-app")

    assert format_key("captcha", "cpt_1") == "demo-app:captcha:cpt_1"
    assert format_key("session", "sess_abc") == "demo-app:session:sess_abc"
