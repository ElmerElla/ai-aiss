"""
数据库连接模块

功能介绍：
-----------
本模块负责初始化和管理后端与 MySQL 数据库的异步连接。
使用 SQLAlchemy 2.0 的异步引擎和会话机制，为整个应用提供统一的数据库访问入口。

主要组件：
- engine: 全局异步数据库引擎实例
- AsyncSessionLocal: 异步会话工厂
- Base: SQLAlchemy ORM 声明式基类，所有模型继承此类
- get_db(): 异步上下文管理器，用于安全创建和关闭数据库会话
"""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from contextlib import asynccontextmanager

from app.config import settings

# 全局异步数据库引擎，pool_pre_ping 用于检测连接是否存活，pool_recycle 防止连接超时
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.DEBUG,
)

# 异步会话工厂：不自动过期、不自动刷新、不自动提交
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    """SQLAlchemy ORM 声明式基类，所有数据模型表类均继承自此类。"""
    pass


@asynccontextmanager
async def get_db():
    """
    生成数据库会话的异步上下文管理器。
    
    使用方式：
        async with get_db() as session:
            result = await session.execute(...)
    
    确保会话在使用完毕后自动关闭，避免连接泄漏。
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
