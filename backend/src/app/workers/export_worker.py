"""Chromium 导出 Worker 的可测试入口。"""

from app.services.export_service import render_document_export


async def run_export(task_id, **kwargs):
    return await render_document_export(task_id, **kwargs)


__all__ = ["render_document_export", "run_export"]
