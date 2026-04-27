"""
统一日志配置模块

功能介绍：
-----------
本模块基于 Loguru 配置全局日志系统，提供控制台输出和文件落盘双通道。

输出目标：
- 控制台（stdout）: INFO 级别及以上，带颜色
- 文件（logs/ai_assistant_runtime.txt）: DEBUG 级别及以上，按 10MB 轮转，保留 14 天

格式：
    时间 | 级别 | 模块名:函数名:行号 - 消息

使用方式：
    from app.utils.logger import logger
    logger.info("操作日志 {}", value)
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
