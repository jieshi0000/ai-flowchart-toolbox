"""文件管理兼容入口，集中导出 D14 的下载与清理能力。"""

from app.services.file_service import FileDownload, cleanup_expired_files, download_file
from app.services.object_storage import (
    MinioObjectStorage,
    ObjectStorage,
    ObjectStorageError,
    get_object_storage,
)

__all__ = [
    "FileDownload",
    "MinioObjectStorage",
    "ObjectStorage",
    "ObjectStorageError",
    "cleanup_expired_files",
    "download_file",
    "get_object_storage",
]
