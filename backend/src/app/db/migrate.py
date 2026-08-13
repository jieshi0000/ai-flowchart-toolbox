import hashlib
import re
from pathlib import Path
from typing import List, Tuple

from sqlalchemy import create_engine, text

V_FILE_RE = re.compile(r"V(\d+)__(.+)\.sql$", re.IGNORECASE)
MIGRATIONS_TABLE = "schema_migrations"
MIGRATIONS_DDL = f"""
CREATE TABLE IF NOT EXISTS {MIGRATIONS_TABLE} (
    version     INTEGER     PRIMARY KEY,
    filename    VARCHAR(255) NOT NULL,
    checksum    VARCHAR(64) NOT NULL,
    executed_at TIMESTAMP   NOT NULL DEFAULT now()
);
"""


def _scan_files(db_dir: str = "db") -> List[Tuple[int, str, str, str]]:
    """返回 [(版本号, 文件名, 描述, checksum)]，已排序"""
    d = Path(db_dir)
    if not d.exists():
        raise FileNotFoundError(f"迁移目录不存在: {d}")

    result = []
    for f in sorted(d.iterdir()):
        if not f.is_file():
            continue
        m = V_FILE_RE.match(f.name)
        if not m:
            continue
        ver = int(m.group(1))
        desc = m.group(2)
        content = f.read_text(encoding="utf-8")
        chk = hashlib.sha256(content.encode()).hexdigest()
        result.append((ver, f.name, desc, chk))

    if not result:
        raise FileNotFoundError(f"未找到 V{{n}}__{{描述}}.sql 文件")
    return result


def _init_tracking_table(engine):
    with engine.begin() as conn:
        conn.execute(text(MIGRATIONS_DDL))


def _executed_versions(engine) -> dict[int, str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT version, checksum FROM {MIGRATIONS_TABLE} ORDER BY version"
            )
        ).fetchall()
    return {r[0]: r[1] for r in rows}


def check_pending(database_url: str, db_dir: str = "db") -> list:
    """返回待执行迁移列表。为空列表表示已是最新。"""
    files = _scan_files(db_dir)
    engine = create_engine(database_url)
    try:
        _init_tracking_table(engine)
        executed = _executed_versions(engine)
    finally:
        engine.dispose()

    pending = []
    for ver, fname, desc, chk in files:
        if ver in executed:
            if executed[ver] != chk:
                raise RuntimeError(
                    f"checksum 不匹配: {fname}\n"
                    f"已执行的迁移文件不可修改！请撤销本次改动。"
                )
            continue
        pending.append((ver, fname, desc))

    return pending


def run_migrations(database_url: str, db_dir: str = "db") -> List[str]:
    """执行待处理的迁移。返回本次执行的迁移文件名列表（可用于下游日志）。"""
    files = _scan_files(db_dir)
    engine = create_engine(database_url)
    try:
        _init_tracking_table(engine)
        executed = _executed_versions(engine)

        pending = []
        for ver, fname, desc, chk in files:
            if ver in executed:
                if executed[ver] != chk:
                    raise RuntimeError(
                        f"checksum 不匹配: {fname} —— "
                        f"已执行的迁移文件不可修改！请撤销本次改动。"
                    )
                continue
            pending.append((ver, fname, desc, chk))

        if not pending:
            return []

        sql_cache = {}
        d = Path(db_dir)
        for _, fname, _, _ in pending:
            sql_cache[fname] = (d / fname).read_text(encoding="utf-8")

        executed_files = []
        for ver, fname, desc, chk in pending:
            try:
                with engine.begin() as conn:
                    # 迁移文件是 PostgreSQL 原始 SQL。使用 exec_driver_sql
                    # 可避免 SQLAlchemy text() 将 JSON 文本中的冒号误识别为
                    # bind 参数（例如 {"x": 0} 会被解析为 : 0）。
                    conn.exec_driver_sql(sql_cache[fname])
                    conn.execute(
                        text(
                            f"INSERT INTO {MIGRATIONS_TABLE} "
                            f"(version, filename, checksum) "
                            f"VALUES (:v, :f, :c)"
                        ),
                        {"v": ver, "f": fname, "c": chk},
                    )
                executed_files.append(fname)
            except Exception:
                raise RuntimeError(f"V{ver}__{desc}.sql 执行失败，已回滚该迁移。") from None
        return executed_files
    finally:
        engine.dispose()


def status_info(database_url: str, db_dir: str = "db") -> dict:
    """返回版本状态信息"""
    files = _scan_files(db_dir)
    engine = create_engine(database_url)
    try:
        _init_tracking_table(engine)
        executed = _executed_versions(engine)
    finally:
        engine.dispose()

    latest_file = max(v for v, _, _, _ in files) if files else 0
    latest_db = max(executed.keys()) if executed else 0

    migration_status = []
    for ver, fname, desc, _ in files:
        migration_status.append(
            {"version": f"V{ver}", "filename": fname, "description": desc, "applied": ver in executed}
        )

    return {
        "current_version": f"V{latest_db}" if latest_db else "无",
        "latest_file_version": f"V{latest_file}",
        "pending_count": len(files) - len(executed),
        "migrations": migration_status,
    }
