"""
隐私脱敏工具模块

功能介绍：
-----------
本模块提供 DID（Decentralized Identifier / 脱敏标识符）生成工具，
用于在对话日志中替代原始学号，保护用户隐私。

特点：
- 单向哈希：无法从 DID 反推出原始 student_id
- 稳定性：同一学号 + 同一盐值始终生成相同 DID
- 可关联性：可在不暴露真实身份的情况下追踪同一用户的历史记录

主要函数：
- generate_did(): 从 student_id 生成 64 位十六进制 DID
"""
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
