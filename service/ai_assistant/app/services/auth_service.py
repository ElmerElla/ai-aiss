"""
认证服务模块

功能介绍：
-----------
本模块提供用户认证相关的核心服务，包括 JWT 令牌的创建与验证、
学生和管理员的登录认证、以及密码修改功能。

主要功能：
- create_access_token() / decode_access_token(): 学生 JWT 的创建与验证
- create_admin_access_token() / decode_admin_access_token(): 管理员 JWT 的创建与验证
- authenticate_student(): 学生登录认证（AES 解密 + SHA256 哈希验证）
- authenticate_admin(): 管理员登录认证
- change_password(): 学生密码修改

密码安全：
- 前端传输 AES-CBC 加密密码
- 数据库存储 SHA256 哈希值
- 兼容纯 SHA256 和 sha256$ 前缀格式
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.models import AdminStatusEnum, AdminUser, Student
from app.utils.crypto import decrypt_password
from app.utils.logger import logger

_ALGORITHM = settings.JWT_ALGORITHM
_SECRET = settings.JWT_SECRET_KEY
_EXPIRE_MINUTES = settings.JWT_EXPIRE_MINUTES


class PasswordChangeError(Exception):
    """当密码修改验证失败时抛出。"""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _verify_password_hash(plaintext: str, stored_hash: str) -> bool:
    """
    验证明文密码与数据库中存储的密码哈希是否匹配。
    
    兼容格式：
        - 纯 SHA256 十六进制字符串
        - sha256$ 前缀格式
        - 明文（仅用于开发环境兼容）
    """
    if not stored_hash:
        return False

    sha256_hex = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
    if stored_hash == sha256_hex:
        return True

    if stored_hash.startswith("sha256$") and stored_hash[7:] == sha256_hex:
        return True

    # 兼容开发环境可能存在的明文占位。
    return stored_hash == plaintext


def create_access_token(student_id: str) -> tuple[str, int]:
    """
    创建学生 JWT 访问令牌。
    
    参数:
        student_id: 学生学号。
    
    返回:
        (令牌字符串, 过期时间（秒）)
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=_EXPIRE_MINUTES)
    payload = {
        "sub": student_id,
        "role": "student",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)
    logger.info("Access token issued: student_id={}, expires_minutes={}", student_id, _EXPIRE_MINUTES)
    return token, _EXPIRE_MINUTES * 60


def create_admin_access_token(admin_id: int, username: str) -> tuple[str, int]:
    """
    创建管理员 JWT 访问令牌。
    
    参数:
        admin_id: 管理员唯一标识。
        username: 管理员用户名。
    
    返回:
        (令牌字符串, 过期时间（秒）)
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=_EXPIRE_MINUTES)
    payload = {
        "sub": str(admin_id),
        "role": "admin",
        "username": username,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)
    logger.info("Admin access token issued: admin_id={}, username={}", admin_id, username)
    return token, _EXPIRE_MINUTES * 60


def decode_access_token(token: str) -> str:
    """
    解码并验证学生 JWT 令牌。
    
    参数:
        token: JWT 字符串。
    
    返回:
        学生学号。
    
    异常:
        JWTError: 令牌无效、已过期或角色不匹配。
    """
    payload = jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
    role: str | None = payload.get("role")
    if role and role != "student":
        logger.warning("Token decode failed: invalid role for student endpoint, role={}", role)
        raise JWTError("token role mismatch")

    student_id: str | None = payload.get("sub")
    if not student_id:
        logger.warning("Token decode failed: subject missing")
        raise JWTError("缺少声明")
    logger.debug("Token decoded: student_id={}", student_id)
    return student_id


def decode_admin_access_token(token: str) -> dict[str, str | int]:
    """
    解码并验证管理员 JWT 令牌。
    
    参数:
        token: JWT 字符串。
    
    返回:
        包含 admin_id 和 username 的字典。
    
    异常:
        JWTError: 令牌无效、已过期或角色不匹配。
    """
    payload = jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
    role: str | None = payload.get("role")
    if role != "admin":
        logger.warning("Admin token decode failed: role mismatch, role={}", role)
        raise JWTError("token role mismatch")

    sub = payload.get("sub")
    if sub is None:
        logger.warning("Admin token decode failed: subject missing")
        raise JWTError("missing sub")

    try:
        admin_id = int(str(sub))
    except (TypeError, ValueError) as exc:
        logger.warning("Admin token decode failed: invalid admin_id={}", sub)
        raise JWTError("invalid admin id") from exc

    username = str(payload.get("username") or "")
    logger.debug("Admin token decoded: admin_id={}, username={}", admin_id, username)
    return {
        "admin_id": admin_id,
        "username": username,
    }


async def authenticate_student(
    db: AsyncSession, student_id: str, encrypted_password: str
) -> Student:
    """
    验证学生身份（登录认证）。

    认证流程：
        1. 查找学生记录
        2. 解密前端传入的 AES 加密密码
        3. 验证 SHA256 密码哈希

    参数:
        db: 数据库会话。
        student_id: 学生学号。
        encrypted_password: AES 加密的密码密文（iv_base64:ciphertext_base64）。

    返回:
        认证成功的 Student 对象。

    异常:
        ValueError: 学号不存在或密码错误。
    """
    # 1. 查找学生
    logger.info("Authenticate start: student_id={}", student_id)
    result = await db.execute(
        select(Student).where(Student.student_id == student_id)
    )
    student: Student | None = result.scalar_one_or_none()
    if student is None:
        logger.warning("Authenticate failed: student not found, student_id={}", student_id)
        raise ValueError("Invalid credentials")

    # 2. 解密 AES 密码
    try:
        plaintext = decrypt_password(encrypted_password)
    except ValueError:
        logger.warning("Authenticate failed: decrypt error, student_id={}", student_id)
        raise ValueError("Invalid credentials")

    # 3. 验证哈希
    if not _verify_password_hash(plaintext, student.password_hash):
        logger.warning("Authenticate failed: password mismatch, student_id={}", student_id)
        raise ValueError("Invalid credentials")

    logger.info("Authenticate success: student_id={}", student_id)
    return student



async def change_password(
    db: AsyncSession,
    student_id: str,
    encrypted_old_password: str,
    encrypted_new_password: str,
) -> None:
    """
    更新指定学生的密码。
    
    安全校验：
        - 验证旧密码正确性
        - 新密码不能与旧密码相同
    
    参数:
        db: 数据库会话。
        student_id: 学生学号。
        encrypted_old_password: AES 加密的旧密码。
        encrypted_new_password: AES 加密的新密码。
    
    异常:
        PasswordChangeError: 学生不存在、旧密码错误或新密码未变更。
    """

    result = await db.execute(
        select(Student).where(Student.student_id == student_id)
    )
    student: Student | None = result.scalar_one_or_none()
    if student is None:
        logger.warning("Change password failed: student not found, student_id={}", student_id)
        raise PasswordChangeError("student_not_found")

    try:
        old_plain = decrypt_password(encrypted_old_password)
        new_plain = decrypt_password(encrypted_new_password)
    except ValueError as exc:
        logger.warning("Change password failed: decrypt error, student_id={}", student_id)
        raise PasswordChangeError("invalid_cipher") from exc

    old_hash = hashlib.sha256(old_plain.encode("utf-8")).hexdigest()
    if old_hash != student.password_hash:
        logger.warning("Change password failed: old password mismatch, student_id={}", student_id)
        raise PasswordChangeError("invalid_old_password")

    new_hash = hashlib.sha256(new_plain.encode("utf-8")).hexdigest()
    if new_hash == student.password_hash:
        logger.warning("Change password failed: same password, student_id={}", student_id)
        raise PasswordChangeError("password_not_changed")

    student.password_hash = new_hash
    await db.flush()
    await db.commit()
    logger.info("Change password success: student_id={}", student_id)


async def authenticate_admin(
    db: AsyncSession,
    username: str,
    encrypted_password: str,
) -> AdminUser:
    """
    验证管理员身份（登录认证）。
    
    参数:
        db: 数据库会话。
        username: 管理员用户名。
        encrypted_password: AES 加密的密码密文。
    
    返回:
        认证成功的 AdminUser 对象。
    
    异常:
        ValueError: 用户名或密码错误。
        PermissionError: 管理员账号非 active 状态。
    """
    normalized = (username or "").strip()
    logger.info("Admin authenticate start: username={}", normalized)

    result = await db.execute(
        select(AdminUser).where(AdminUser.username == normalized)
    )
    admin: AdminUser | None = result.scalar_one_or_none()
    if admin is None:
        logger.warning("Admin authenticate failed: user not found, username={}", normalized)
        raise ValueError("Invalid credentials")

    if admin.status != AdminStatusEnum.active:
        logger.warning(
            "Admin authenticate failed: account unavailable, admin_id={}, status={}",
            admin.admin_id,
            admin.status.value,
        )
        raise PermissionError("Account unavailable")

    try:
        plaintext = decrypt_password(encrypted_password)
    except ValueError:
        logger.warning("Admin authenticate failed: decrypt error, username={}", normalized)
        raise ValueError("Invalid credentials")

    if not _verify_password_hash(plaintext, admin.password_hash):
        logger.warning("Admin authenticate failed: password mismatch, username={}", normalized)
        raise ValueError("Invalid credentials")

    admin.last_login_at = datetime.now()
    admin.updated_at = datetime.now()
    await db.flush()
    await db.commit()
    logger.info("Admin authenticate success: admin_id={}, username={}", admin.admin_id, admin.username)
    return admin
