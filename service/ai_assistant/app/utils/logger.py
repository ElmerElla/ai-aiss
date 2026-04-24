"""统一日志配置（Loguru）。

- 控制台输出 + 文件落盘
- 文件格式为 .txt，默认位于 service/ai_assistant/logs/
"""
from __future__ import annotations

from pathlib import Path
import sys

from loguru import logger


_CONFIGURED = False


def setup_logger() -> None:
    """初始化全局 logger（幂等）。"""
    global _CONFIGURED
    if _CONFIGURED:
        return

    project_root = Path(__file__).resolve().parents[2]
    log_dir = project_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "ai_assistant_runtime.txt"

    logger.remove()
    logger.add(
        sys.stdout,
        level="INFO",
        enqueue=True,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} - {message}",
    )
    logger.add(
        str(log_file),
        level="DEBUG",
        enqueue=True,
        rotation="10 MB",
        retention="14 days",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} - {message}",
    )

    logger.info("Logger initialized, file sink: {}", log_file)
    _CONFIGURED = True


__all__ = ["logger", "setup_logger"]

# 在首次导入时即初始化，确保所有模块日志都能落盘到 .txt。
setup_logger()
