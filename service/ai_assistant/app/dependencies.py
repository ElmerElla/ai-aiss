"""
依赖注入模块

功能介绍：
-----------
本模块定义了 FastAPI 路由中使用的所有依赖项（Dependencies），
包括数据库会话、Redis 客户端、当前用户认证和管理员认证。

依赖项列表：
- get_db(): 获取异步数据库会话
- get_redis_client() / get_redis(): 获取 Redis 客户端单例
- get_current_user(): 从 JWT Token 中解析当前登录学生学号
- get_current_admin(): 从 JWT Token 中解析当前登录管理员信息

使用方式（在路由中声明依赖）：
    async def my_endpoint(
        db: AsyncSession = Depends(get_db),
        current_user: str = Depends(get_current_user),
    ):
        ...
"""
from __future__ import annotations

from typing import AsyncGenerator

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.models import AdminStatusEnum, AdminUser
from app.services.auth_service import decode_access_token, decode_admin_access_token

_bearer_scheme = HTTPBearer(auto_error=False)

# Redis 连接池
_redis_pool: aioredis.Redis | None = None


# ---------------------------------------------------------------------------
# 数据库会话
# ---------------------------------------------------------------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    获取数据库会话依赖。
    
    通过 AsyncSessionLocal 创建异步数据库会话，并在请求结束后自动关闭。
    """
    async with AsyncSessionLocal() as session:
        yield session


# ---------------------------------------------------------------------------
# Redis 客户端
# ---------------------------------------------------------------------------
def get_redis_client() -> aioredis.Redis:
    """
    获取 Redis 客户端单例（懒加载）。
    
    首次调用时根据配置创建 Redis 连接，后续调用返回已创建的实例。
    """
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_pool


async def get_redis() -> aioredis.Redis:
    """
    获取 Redis 客户端依赖（供 FastAPI Depends 使用）。
    
    实际调用 get_redis_client() 返回单例。
    """
    return get_redis_client()


# ---------------------------------------------------------------------------
# 当前用户
# ---------------------------------------------------------------------------
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> str:
    """
    从请求头中的 Bearer Token 解析当前登录学生的学号。
    
    参数:
        credentials: HTTP Authorization 头中解析出的 Bearer 凭证。
    
    返回:
        当前登录学生的学号字符串。
    
    异常:
        HTTPException(401): Token 缺失、无效或已过期时抛出。
    """
    exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="认证失败",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or not credentials.scheme or not credentials.credentials:
        raise exception

    try:
        student_id = decode_access_token(credentials.credentials)
    except (HTTPException, JWTError):
        raise exception
    return student_id


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    """
    从请求头中的 Bearer Token 解析当前登录管理员信息。
    
    不仅验证 Token 有效性，还会查询数据库确认管理员账号存在且状态为 active。
    
    参数:
        credentials: HTTP Authorization 头中解析出的 Bearer 凭证。
        db: 数据库会话，用于查询管理员信息。
    
    返回:
        当前登录的 AdminUser 对象。
    
    异常:
        HTTPException(401): Token 无效或管理员不存在。
        HTTPException(403): 管理员账号状态非 active（被禁用或锁定）。
    """
    exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="管理员认证失败",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or not credentials.scheme or not credentials.credentials:
        raise exception

    try:
        payload = decode_admin_access_token(credentials.credentials)
    except (HTTPException, JWTError):
        raise exception

    admin_id = int(payload["admin_id"])
    admin = (
        await db.execute(
            select(AdminUser).where(AdminUser.admin_id == admin_id).limit(1)
        )
    ).scalar_one_or_none()

    if admin is None:
        raise exception
    if admin.status != AdminStatusEnum.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="管理员账号不可用",
        )
    return admin

