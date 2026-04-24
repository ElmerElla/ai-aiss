"""AI 校园助手 
FastAPI 应用程序入口点。"""
from __future__ import annotations

import warnings
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import admin, auth, query, system
from app.utils.logger import logger, setup_logger

setup_logger()

_INSECURE_DEFAULTS = {
    "JWT_SECRET_KEY": "CHANGE_ME_insecure_default",
    "AES_SECRET_KEY": "0123456789abcdef",
    "DID_SALT": "change_me",
}


def _check_insecure_defaults() -> None:
    for key, default in _INSECURE_DEFAULTS.items():
        if getattr(settings, key) == default:
            logger.warning("Insecure default detected for {}", key)
            warnings.warn(
                f"安全警告: {key} 使用了不安全的默认值。"
                "请在部署到生产环境之前，在 .env 文件中设置强密码。",
                stacklevel=2,
            )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """启动/关闭生命周期。"""
    logger.info("FastAPI lifespan startup begin")
    _check_insecure_defaults()
    logger.info("FastAPI lifespan startup completed")
    yield
    # 关闭时：如果 Redis 连接池已创建，则关闭它
    from app.dependencies import _redis_pool

    if _redis_pool is not None:
        logger.info("Closing redis connection pool")
        await _redis_pool.aclose()
    logger.info("FastAPI lifespan shutdown completed")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "校园 AI 助手后端。"
        "提供 JWT 认证和统一的多模态查询接口。"
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

logger.info("FastAPI app initialized: name={}, version={}", settings.APP_NAME, settings.APP_VERSION)

# ---------------------------------------------------------------------------
# CORS – 在生产环境中限制为你的 Vue 前端源。
# 例如: allow_origins=["https://your-frontend.example.com"]
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(query.router)
app.include_router(system.router)
logger.info("Routers registered: auth/admin/query/system")
