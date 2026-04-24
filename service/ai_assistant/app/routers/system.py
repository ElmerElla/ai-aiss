"""系统路由：/api/v1/health 和 /api/v1/version"""
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
    return HealthResponse(status="ok", service=settings.APP_NAME)


@router.get(
    "/api/v1/version",
    response_model=VersionResponse,
    summary="版本信息",
)
async def version() -> VersionResponse:
    return VersionResponse(name=settings.APP_NAME, version=settings.APP_VERSION)
