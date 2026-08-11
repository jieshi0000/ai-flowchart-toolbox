#!/usr/bin/env python3
"""
数据库迁移 CLI — 手动执行 db/V{n}__{描述}.sql 文件。

用法:
    python migrate.py              # 执行待处理的迁移
    python migrate.py --check      # 列出待处理/已执行状态，不执行
    python migrate.py --status     # 显示当前版本状态

环境变量:
    DATABASE__URL  数据库连接串（优先；否则按 APP_ENV 层叠读 .env）
    APP_ENV        可选，加载 .env.{APP_ENV} 覆盖基线
"""
import argparse
import sys
from pathlib import Path

# 确保 src/ 可被 import
sys.path.insert(0, str(Path(__file__).parent / "src"))

from app.db.migrate import check_pending, run_migrations, status_info


def _get_url() -> str:
    import os

    from app.core.config import get_settings
    from app.core.crypto import decrypt

    url = os.environ.get("DATABASE__URL")
    if url:
        return decrypt(url)

    get_settings.cache_clear()
    url = get_settings().database.url
    if not url:
        print(
            "[错误] 请设置 DATABASE__URL 环境变量，或在 .env / .env.{APP_ENV} 中配置",
            file=sys.stderr,
        )
        sys.exit(1)
    return url


def main():
    parser = argparse.ArgumentParser(
        description="数据库迁移工具 - 执行 db/V{n}__{desc}.sql 文件"
    )
    parser.add_argument("--check", action="store_true", help="列出待执行/已执行迁移，不执行")
    parser.add_argument("--status", action="store_true", help="显示当前版本状态")
    parser.add_argument("--dir", default="db", help="SQL 迁移文件目录（默认: db/）")
    args = parser.parse_args()

    url = _get_url()
    db_dir = args.dir

    if args.status:
        info = status_info(url, db_dir)
        print(f"  当前数据库版本: {info['current_version']}")
        print(f"  最新迁移文件版本: {info['latest_file_version']}")
        print(f"  待执行迁移数: {info['pending_count']}")
        print()
        for m in info["migrations"]:
            icon = "✅" if m["applied"] else "⬜"
            print(f"  {icon} {m['version']}__{m['description']}.sql")
        return

    if args.check:
        try:
            pending = check_pending(url, db_dir)
        except Exception as e:
            print(f"[错误] {e}", file=sys.stderr)
            sys.exit(2)

        if not pending:
            print("✅ 数据库是最新状态，无需迁移。")
            return
        print(f"\n📋 待执行迁移 ({len(pending)} 个)：")
        for ver, fname, desc in pending:
            print(f"     V{ver}__{desc}.sql")
        return

    # default: migrate
    try:
        executed = run_migrations(url, db_dir)
    except RuntimeError as e:
        print(f"[错误] {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[错误] 迁移执行失败: {e}", file=sys.stderr)
        print("⏩ 可以用 psql -f db/V{n}__{desc}.sql 手动执行。", file=sys.stderr)
        sys.exit(1)

    for fname in executed:
        print(f"  ✅ {fname}")
    if not executed:
        print("✅ 数据库已是最新版本。")
    else:
        print(f"\n✅ 成功执行 {len(executed)} 个迁移。")
        print(f"⏩ 生产环境建议先用 --check 审阅，确认无误后执行。")


if __name__ == "__main__":
    main()
