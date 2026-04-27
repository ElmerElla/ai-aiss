"""
学生认证相关 Pydantic 模式模块

功能介绍：
-----------
本模块定义了学生认证接口的请求和响应数据模型（Schema）。

模式列表：
- LoginRequest / TokenResponse: 登录请求与响应
- ChangePasswordRequest / ChangePasswordResponse: 修改密码请求与响应

兼容处理：
- 同时支持 encrypted_password 和 password 字段名（向后兼容）
- 同时支持 encrypted_old_password/old_password 和 encrypted_new_password/new_password
"""
from pydantic import BaseModel, ConfigDict, Field, model_validator


class LoginRequest(BaseModel):
    """登录请求，兼容 `password` 与 `encrypted_password` 字段名。"""

    model_config = ConfigDict(populate_by_name=True)

    student_id: str = Field(..., description="学生ID")
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


class ChangePasswordRequest(BaseModel):
    """修改密码请求，需携带旧/新加密密码。"""

    model_config = ConfigDict(populate_by_name=True)

    student_id: str = Field(..., description="学生ID")
    encrypted_old_password: str = Field(..., description="旧密码（AES-CBC加密）")
    encrypted_new_password: str = Field(..., description="新密码（AES-CBC加密）")

    @model_validator(mode="before")
    @classmethod
    def _support_legacy_fields(cls, values):
        if isinstance(values, dict):
            updated = dict(values)
            if "encrypted_old_password" not in updated and (legacy := updated.get("old_password")):
                updated["encrypted_old_password"] = legacy
            if "encrypted_new_password" not in updated and (legacy_new := updated.get("new_password")):
                updated["encrypted_new_password"] = legacy_new
            return updated
        return values


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Token validity in seconds")
    student_id: str


class ChangePasswordResponse(BaseModel):
    success: bool = Field(True, description="标记密码已更新")
    student_id: str = Field(..., description="已修改密码的学号")
    detail: str = Field("密码已更新", description="可读提示信息")
