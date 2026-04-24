"""依赖注入定义。"""
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
    """获取数据库会话。"""
    async with AsyncSessionLocal() as session:
        yield session


# ---------------------------------------------------------------------------
# Redis 客户端
# ---------------------------------------------------------------------------
def get_redis_client() -> aioredis.Redis:
    """获取 Redis 客户端单例。"""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_pool


async def get_redis() -> aioredis.Redis:
    """获取 Redis 客户端依赖。"""
    return get_redis_client()


# ---------------------------------------------------------------------------
# 当前用户
# ---------------------------------------------------------------------------
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> str:
    """获取当前登录用户的学号。"""
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
    """获取当前登录管理员。"""
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

