"""认证路由：POST /api/v1/auth/login"""
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
