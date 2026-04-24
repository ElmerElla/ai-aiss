"""隐私工具：DID (脱敏用户令牌) 生成。"""
from __future__ import annotations

import hashlib

from app.config import settings


def generate_did(student_id: str) -> str:
    """从 student_id 生成稳定、单向的 DID。

    DID 存储在 chat_log 中以替代原始 student_id，确保保护隐私。
    同一学生总是生成相同的 DID，因此可以在不暴露真实 ID 的情况下进行历史日志关联。

    参数:
        student_id: 学生的真实 ID。

    返回:
        一个 64 字符的十六进制字符串 (SHA-256)。
    """
    data = f"{student_id}:{settings.DID_SALT}".encode("utf-8")
    return hashlib.sha256(data).hexdigest()
