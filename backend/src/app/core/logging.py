import sys
from pathlib import Path

from loguru import logger

from app.core.config import get_settings


def setup_logging():
    settings = get_settings()
    log_level = settings.log.level.upper()
    log_types = [t.strip() for t in settings.log.types.split(",")]
    use_console = "console" in log_types
    use_file = "file" in log_types

    logger.remove()

    if use_console:
        fmt = (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        )
        logger.add(sys.stdout, format=fmt, level=log_level, colorize=True)

    if use_file and settings.log.dir:
        log_path = Path(settings.log.dir)
        log_path.mkdir(parents=True, exist_ok=True)
        file_fmt = (
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{name}:{function}:{line} | "
            "{message}"
        )
        log_file = log_path / f"{settings.app.name}.log"
        logger.add(
            str(log_file),
            format=file_fmt,
            level=log_level,
            rotation="10 MB",
            retention="5 files",
            encoding="utf-8",
        )
