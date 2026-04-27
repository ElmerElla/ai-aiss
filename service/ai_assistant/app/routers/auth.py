"""
学生认证路由模块

功能介绍：
-----------
本模块提供学生端的认证相关 API 接口，前缀为 /api/v1/auth。

接口列表：
- POST /auth/login          → 学生登录（验证 AES 加密密码，返回 JWT）
- POST /auth/change-password → 修改密码（需携带旧密码验证）

安全机制：
- 前端密码使用 AES-CBC 加密传输，后端解密后验证 SHA256 哈希
- 登录成功后返回 JWT Bearer Token，后续请求通过 Authorization 头携带
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.schemas.auth import (
    ChangePasswordRequest,
    ChangePasswordResponse,
    LoginRequest,
    TokenResponse,
)
from app.services.auth_service import (
    PasswordChangeError,
    authenticate_student,
    change_password,
    create_access_token,
)

router = APIRouter(prefix="/api/v1/auth", tags=["认证"])


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="学生登录",
    description=(
        "使用学生ID和AES-CBC加密密码进行认证。"
        "返回JWT Bearer令牌。"
    ),
)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    学生登录接口。
    
    流程：
        1. 解密前端 AES 加密密码
        2. 验证学号和密码哈希
        3. 生成 JWT Token 并返回
    
    异常:
        HTTPException(401): 学号或密码无效。
    """
    try:
        student = await authenticate_student(
            db, body.student_id, body.encrypted_password
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="学生ID或密码无效",
        )

    token, expires_in = create_access_token(student.student_id)
    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        student_id=student.student_id,
    )


@router.post(
    "/change-password",
    response_model=ChangePasswordResponse,
    summary="修改学生密码",
    description="需要有效的Bearer Token，旧密码验证通过后才能更新新密码。",
)
async def change_password_endpoint(
    body: ChangePasswordRequest,
    current_student_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChangePasswordResponse:
    """
    学生修改密码接口。
    
    安全校验：
        - 只能修改自己的密码（通过 Token 中的 student_id 校验）
        - 必须提供正确的旧密码
        - 新密码不能与旧密码相同
    
    异常:
        HTTPException(403): 试图修改他人密码。
        HTTPException(404): 学生不存在。
        HTTPException(400): 旧密码错误或新密码与旧密码相同。
    """
    if body.student_id != current_student_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="禁止修改其他学生的密码",
        )

    try:
        await change_password(
            db,
            student_id=current_student_id,
            encrypted_old_password=body.encrypted_old_password,
            encrypted_new_password=body.encrypted_new_password,
        )
    except PasswordChangeError as exc:
        reason = exc.reason
        if reason == "student_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="学生不存在",
            )
        if reason == "invalid_old_password":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="旧密码不正确",
            )
        if reason == "password_not_changed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="新密码不能与旧密码相同",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="加密数据无效",
        ) from exc

    return ChangePasswordResponse(student_id=current_student_id)
