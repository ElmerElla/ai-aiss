"""
管理员相关 Pydantic 模式模块

功能介绍：
-----------
本模块定义了管理员接口的请求和响应数据模型（Schema），
用于 FastAPI 的请求校验、序列化和自动文档生成。

模式列表：
- AdminLoginRequest / AdminTokenResponse: 登录请求与响应
- AdminMeResponse: 当前管理员信息
- AdminDashboardSummaryResponse: 管理面板统计
- AdminTermItem / AdminClassItem: 元数据项
- AdminScheduleItem / AdminScheduleListResponse: 课表查询
- UpdateScheduleStatusRequest / UpdateScheduleStatusResponse: 课表状态更新
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.models import AdminRoleEnum, ScheduleStatusEnum


class AdminLoginRequest(BaseModel):
    """管理员登录请求，兼容 `password` 与 `encrypted_password` 字段名。"""

    model_config = ConfigDict(populate_by_name=True)

    username: str = Field(..., description="管理员用户名")
    encrypted_password: str = Field(
        ..., description="AES-CBC加密密码（iv_base64:cipher_base64）"
    )

    @model_validator(mode="before")
    @classmethod
    def _support_legacy_password(cls, values):
        if isinstance(values, dict) and "encrypted_password" not in values:
            if legacy := values.get("password"):
                values = {**values, "encrypted_password": legacy}
        return values


class AdminTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Token validity in seconds")
    admin_id: int
    username: str
    display_name: str
    role: AdminRoleEnum


class AdminMeResponse(BaseModel):
    admin_id: int
    admin_code: str
    username: str
    display_name: str
    role: AdminRoleEnum


class AdminDashboardSummaryResponse(BaseModel):
    pending_adjustments: int
    active_schedules: int
    cancelled_schedules: int
    total_classes: int
    total_terms: int


class AdminTermItem(BaseModel):
    term_id: str
    start_date: date
    end_date: date


class AdminClassItem(BaseModel):
    class_id: str
    class_name: str
    grade: int
    major_name: str
    department_name: str


class AdminScheduleItem(BaseModel):
    schedule_id: str
    term_id: str
    course_id: str
    course_name: str
    teacher_id: str
    teacher_name: str
    room_id: str
    room_location: str
    week_no: int
    day_of_week: int
    start_period: int
    end_period: int
    week_pattern: str | None = None
    schedule_status: ScheduleStatusEnum
    version: int
    updated_at: datetime
    classes: list[AdminClassItem]


class AdminScheduleListResponse(BaseModel):
    total: int
    items: list[AdminScheduleItem]


class UpdateScheduleStatusRequest(BaseModel):
    schedule_status: Literal["active", "cancelled"]
    reason: str | None = Field(None, max_length=255)


class UpdateScheduleStatusResponse(BaseModel):
    schedule_id: str
    schedule_status: ScheduleStatusEnum
    version: int
    updated_at: datetime
