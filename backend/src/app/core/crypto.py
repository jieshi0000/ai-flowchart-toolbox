"""配置密文解密：支持整值或嵌入式 ENC(...)。"""

from __future__ import annotations

import os
import re

# Fernet token 为 urlsafe base64，不含 ')'，可用非贪婪匹配
_ENC_RE = re.compile(r"ENC\(([^)]+)\)")


def decrypt(value: str) -> str:
    """将字符串中的 ENC(密文) 替换为明文；无 ENC 则原样返回。"""
    if not isinstance(value, str) or "ENC(" not in value:
        return value

    key = os.environ.get("CONFIG_KEY")
    if not key:
        raise ValueError("CONFIG_KEY 未设置，无法解密 ENC 值")

    from cryptography.fernet import Fernet

    cipher = Fernet(key.encode())

    def _repl(match: re.Match[str]) -> str:
        try:
            return cipher.decrypt(match.group(1).encode()).decode()
        except Exception as exc:
            raise ValueError(f"ENC 解密失败: {exc}") from exc

    return _ENC_RE.sub(_repl, value)
