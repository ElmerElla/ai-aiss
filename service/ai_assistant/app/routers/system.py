"""
系统路由模块

功能介绍：
-----------
本模块提供系统级别的公共 API 接口，无需认证即可访问。

接口列表：
- GET /api/v1/health  → 服务健康检查
- GET /api/v1/version → 获取应用名称和版本号

用途：
- 供负载均衡器、监控系统和前端进行服务可用性探测
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings

router = APIRouter(tags=["系统"])


class HealthResponse(BaseModel):
    status: str
    service: str


class VersionResponse(BaseModel):
    name: str
    version: str


@router.get(
    "/api/v1/health",
    response_model=HealthResponse,
    summary="健康检查",
)
async def health() -> HealthResponse:
    """服务健康检查接口，返回当前服务运行状态。"""
    return HealthResponse(status="ok", service=settings.APP_NAME)


@router.get(
    "/api/v1/version",
    response_model=VersionResponse,
    summary="版本信息",
)
async def version() -> VersionResponse:
    """获取应用版本信息接口。"""
    return VersionResponse(name=settings.APP_NAME, version=settings.APP_VERSION)
