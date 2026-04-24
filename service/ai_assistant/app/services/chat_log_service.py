"""对话日志服务。"""
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
    """保存单条对话记录。

    隐私规则：
    * 普通消息仅存储 DID (脱敏的学号)，`student_id` 为空。
    * 危险消息 (如自杀/暴力) 会存储原始 `student_id` 以便干预。

    返回：
        保存的 ChatLog 实例。
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
    """获取指定学生的最近对话记录。"""
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


