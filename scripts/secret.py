#!/usr/bin/env python3
"""配置密文工具——与 backend/src/app/core/crypto.py 配套（Fernet 对称加密）。

用法：
  # Windows PowerShell
  $env:CONFIG_KEY = "<Fernet 密钥，来自密码管理器>"
  # Linux / macOS / CMD
  export CONFIG_KEY="<Fernet 密钥>"        # set CONFIG_KEY=... (CMD)

  python scripts/secret.py generate         # 管理员首次生成 CONFIG_KEY
  python scripts/secret.py encrypt "明文"    # → ENC(密文)，写入 .env
  python scripts/secret.py decrypt "ENC(密文)" # → 明文（验证用）

说明：
  - 密钥格式为 Fernet.generate_key() 的输出（urlsafe base64，44 字符）。
  - 同一明文每次加密结果不同（Fernet 内含时间戳与 IV），属正常现象。
  - CONFIG_KEY 永不提交 git，仅存密码管理器 / 环境变量。
  - 与 Java Jasypt 密文不互通。
  - 依赖 cryptography（已在 backend/pyproject.toml），故建议在 backend 目录
    用 `uv run python ../scripts/secret.py ...` 运行。
"""

from __future__ import annotations

import os
import re
import sys

_ENC_RE = re.compile(r"ENC\(([^)]+)\)")


def _cipher():
    key = os.environ.get("CONFIG_KEY")
    if not key:
        sys.exit("错误：未设置 CONFIG_KEY 环境变量。先生成：python scripts/secret.py generate")
    try:
        from cryptography.fernet import Fernet

        return Fernet(key.encode())
    except Exception as exc:
        sys.exit(f"错误：CONFIG_KEY 无效或未安装 cryptography：{exc}")


def generate() -> None:
    from cryptography.fernet import Fernet

    print(Fernet.generate_key().decode())
    print("# ↑ 将此值存入密码管理器作为 CONFIG_KEY，并在本机设为环境变量。", file=sys.stderr)


def encrypt(plaintext: str) -> None:
    cipher = _cipher()
    token = cipher.encrypt(plaintext.encode()).decode()
    print(f"ENC({token})")


def decrypt(value: str) -> None:
    cipher = _cipher()
    match = _ENC_RE.search(value)
    token = match.group(1) if match else value
    try:
        print(cipher.decrypt(token.encode()).decode())
    except Exception as exc:
        sys.exit(f"错误：解密失败：{exc}")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)
    cmd = sys.argv[1]
    if cmd == "generate":
        generate()
    elif cmd == "encrypt":
        if len(sys.argv) < 3:
            sys.exit('用法：python scripts/secret.py encrypt "明文"')
        encrypt(sys.argv[2])
    elif cmd == "decrypt":
        if len(sys.argv) < 3:
            sys.exit('用法：python scripts/secret.py decrypt "ENC(密文)"')
        decrypt(sys.argv[2])
    else:
        sys.exit(f"未知命令：{cmd}（支持 generate / encrypt / decrypt）")


if __name__ == "__main__":
    main()
