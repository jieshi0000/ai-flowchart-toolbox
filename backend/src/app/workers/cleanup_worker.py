"""导出文件到期清理 Worker 的可测试入口。"""

from app.services.export_service import cleanup_expired_export_files


async def run_cleanup(**kwargs):
    return await cleanup_expired_export_files(**kwargs)


__all__ = ["cleanup_expired_export_files", "run_cleanup"]
