import base64
import random
import secrets
import string

from captcha.image import ImageCaptcha

from app.core.redis import get_redis
from app.core.redis_keys import format_key

CAPTCHA_BIZ = "captcha"
CAPTCHA_TTL = 300
_IMAGE = ImageCaptcha(width=160, height=60)


def _random_code(length: int = 4) -> str:
    return "".join(random.choices(string.digits, k=length))


def _render_image(code: str) -> str:
    raw = _IMAGE.generate(code).read()
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:image/png;base64,{encoded}"


async def create_captcha() -> tuple[str, str]:
    code = _random_code()
    captcha_key = secrets.token_urlsafe(16)
    redis = get_redis()
    await redis.setex(format_key(CAPTCHA_BIZ, captcha_key), CAPTCHA_TTL, code.lower())
    return captcha_key, _render_image(code)


async def verify_captcha(captcha_key: str, captcha: str) -> bool:
    redis = get_redis()
    key = format_key(CAPTCHA_BIZ, captcha_key)
    stored = await redis.get(key)
    if not stored:
        return False
    await redis.delete(key)
    return stored == captcha.strip().lower()
