"""
对话日志服务模块

功能介绍：
-----------
本模块负责持久化存储学生与 AI 助手的对话记录。

隐私保护：
- 普通消息仅存储 DID（脱敏学号），不保存原始 student_id
- 危险消息（自杀/暴力倾向）会存储原始 student_id，以便进行人工干预

主要功能：
- log_message(): 保存单条对话记录
- get_recent_messages(): 获取指定学生的最近对话历史
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ChatLog, SenderEnum, SystemActionEnum
from app.utils.logger import logger
from app.utils.privacy import generate_did


async def log_message(
    db: AsyncSession,
    *,
    student_id: str,
    sender: SenderEnum,
    message_content: str,
    system_action: SystemActionEnum = SystemActionEnum.none,
    response_time_ms: int | None = None,
    is_dangerous: bool = False,
) -> ChatLog:
    """
    保存单条对话记录到数据库。

    隐私规则：
        - 普通消息仅存储 DID（脱敏学号），student_id 字段为空
        - 危险消息（如自杀/暴力）会存储原始 student_id 以便人工干预

    参数:
        db: 数据库会话。
        student_id: 学生真实学号（内部处理为 DID 或保留）。
        sender: 消息发送者类型（student/agent/system）。
        message_content: 消息内容文本。
        system_action: 系统干预动作标记。
        response_time_ms: 响应耗时（毫秒）。
        is_dangerous: 是否为危险内容。

    返回:
        保存后的 ChatLog 实例。
    """
    did = generate_did(student_id)
    raw_student_id: str | None = student_id if is_dangerous else None

    entry = ChatLog(
        did=did,
        student_id=raw_student_id,
        timestamp=datetime.now(timezone.utc),
        sender=sender,
        message_content=message_content,
        system_action=system_action,
        response_time_ms=response_time_ms,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    logger.info(
        "Chat log persisted: did={}, sender={}, dangerous={}, action={}",
        did[:12],
        sender.value,
        is_dangerous,
        system_action.value,
    )
    return entry


async def get_recent_messages(
    db: AsyncSession, student_id: str, limit: int = 10
) -> list[ChatLog]:
    """
    获取指定学生的最近对话记录。
    
    按时间倒序查询，返回时逆序为从旧到新，便于构建上下文。
    
    参数:
        db: 数据库会话。
        student_id: 学生学号。
        limit: 返回的最大记录数。
    """
    did = generate_did(student_id)
    stmt = (
        select(ChatLog)
        .where(ChatLog.did == did)
        .order_by(desc(ChatLog.timestamp))
        .limit(limit)
    )
    result = await db.execute(stmt)
    # 逆序返回（从旧到新），以便构建上下文
    rows = list(reversed(result.scalars().all()))
    logger.info("Chat history loaded: did={}, count={}, limit={}", did[:12], len(rows), limit)
    return rows


