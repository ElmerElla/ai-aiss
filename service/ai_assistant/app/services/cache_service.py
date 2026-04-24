"""Redis 缓存服务。

缓存键格式：``chat_cache:{version}:{did}:{query_hash}``

TTL 规则：
- 敏感/隐私查询 → 30 分钟 (settings.CACHE_TTL_SENSITIVE)
- 普通查询 → 1 天 (settings.CACHE_TTL_NORMAL)
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date

import redis.asyncio as aioredis

from app.config import settings
from app.utils.logger import logger

# 敏感信息关键词匹配模式
_SENSITIVE_PATTERNS = re.compile(
    r"(成绩|分数|挂科|作弊|学籍|处分|奖学金|家庭|联系方式|手机|邮箱|生日|身份证)",
    re.IGNORECASE,
)

# 时间敏感查询（相对日期/周/学期）需要跨天失效，避免命中过期语义结果。
_DATE_SENSITIVE_PATTERNS = re.compile(
    r"(今天|今日|明天|后天|昨天|前天|今晚|今早|当前|现在|本周|这周|上周|下周|本学期|这学期|上学期|下学期|today|tomorrow|yesterday|this\s+week|last\s+week|next\s+week|this\s+semester|current\s+semester|next\s+semester|previous\s+semester)",
    re.IGNORECASE,
)

# 课表相关查询：管理员改课后需要主动失效，避免学生拿到旧数据。
_SCHEDULE_SENSITIVE_PATTERNS = re.compile(
    r"(课表|课程表|课程安排|上课|有课|什么课|有啥课|今天.*课|明天.*课|后天.*课|排课|第\s*\d+\s*周|周[一二三四五六日天]|星期|schedule|class\s*schedule)",
    re.IGNORECASE,
)

# 当查询/总结逻辑升级时，提升版本号可自动隔离旧缓存，避免脏缓存复用。
_CACHE_KEY_VERSION = "v3.6"
_SCHEDULE_CACHE_VERSION_KEY = "chat_cache:schedule_version"


def _today_bucket() -> str:
    """返回当天日期桶（本地日期）。"""
    return date.today().isoformat()


def _make_cache_key(did: str, query_text: str) -> str:
    """生成缓存键：chat_cache:{version}:{did}:{query_md5}。"""
    query_hash = hashlib.md5(query_text.strip().lower().encode("utf-8")).hexdigest()
    return f"chat_cache:{_CACHE_KEY_VERSION}:{did}:{query_hash}"


def is_sensitive_query(query_text: str) -> bool:
    """检查查询是否包含敏感关键词。"""
    return bool(_SENSITIVE_PATTERNS.search(query_text))


def is_date_sensitive_query(query_text: str) -> bool:
    """检查查询是否包含相对时间语义（跨天后应重新计算）。"""
    return bool(_DATE_SENSITIVE_PATTERNS.search(query_text or ""))


def is_schedule_sensitive_query(query_text: str) -> bool:
    """检查查询是否与课表相关（管理员调课后应失效重算）。"""
    return bool(_SCHEDULE_SENSITIVE_PATTERNS.search(query_text or ""))


async def get_schedule_cache_version(redis: aioredis.Redis) -> str:
    """获取当前课表缓存版本号。"""
    raw = await redis.get(_SCHEDULE_CACHE_VERSION_KEY)
    if raw is None:
        return "0"
    return str(raw)


async def bump_schedule_cache_version(redis: aioredis.Redis) -> str:
    """管理员改课后递增课表缓存版本号。"""
    version = await redis.incr(_SCHEDULE_CACHE_VERSION_KEY)
    logger.info("Schedule cache version bumped: version={}", version)
    return str(version)


def get_ttl(query_text: str) -> int:
    """根据敏感性返回缓存过期时间（秒）。"""
    if is_sensitive_query(query_text):
        return settings.CACHE_TTL_SENSITIVE
    return settings.CACHE_TTL_NORMAL


async def get_cached_response(
    redis: aioredis.Redis, did: str, query_text: str
) -> dict | None:
    """查询缓存。如果未命中返回 None。"""
    key = _make_cache_key(did, query_text)
    raw = await redis.get(key)
    if raw is None:
        logger.debug("Cache miss: key={}", key)
        return None

    try:
        payload = json.loads(raw)
    except Exception:
        logger.warning("Cache payload parse failed, invalidate key={}", key)
        await redis.delete(key)
        return None

    if not isinstance(payload, dict):
        logger.warning("Cache payload type invalid, invalidate key={}", key)
        await redis.delete(key)
        return None

    if is_date_sensitive_query(query_text):
        meta = payload.get("_cache_meta")
        cached_on = meta.get("date_bucket") if isinstance(meta, dict) else None
        today_bucket = _today_bucket()

        if cached_on != today_bucket:
            logger.info(
                "Cache stale by date guard: key={}, cached_on={}, today={}",
                key,
                cached_on,
                today_bucket,
            )
            await redis.delete(key)
            return None

    if is_schedule_sensitive_query(query_text):
        meta = payload.get("_cache_meta")
        cached_version = str(meta.get("schedule_cache_version")) if isinstance(meta, dict) and meta.get("schedule_cache_version") is not None else None
        current_version = await get_schedule_cache_version(redis)

        if cached_version != current_version:
            logger.info(
                "Cache stale by schedule version: key={}, cached_version={}, current_version={}",
                key,
                cached_version,
                current_version,
            )
            await redis.delete(key)
            return None

    payload.pop("_cache_meta", None)
    logger.info("Cache hit: key={}", key)
    return payload


async def set_cached_response(
    redis: aioredis.Redis,
    did: str,
    query_text: str,
    response: dict,
    *,
    sensitive: bool | None = None,
) -> None:
    """写入缓存。"""
    key = _make_cache_key(did, query_text)
    if sensitive is None:
        sensitive = is_sensitive_query(query_text)
    
    ttl = settings.CACHE_TTL_SENSITIVE if sensitive else settings.CACHE_TTL_NORMAL

    response_payload = dict(response)
    schedule_sensitive = is_schedule_sensitive_query(query_text)
    schedule_cache_version = await get_schedule_cache_version(redis) if schedule_sensitive else None
    response_payload["_cache_meta"] = {
        "date_sensitive": is_date_sensitive_query(query_text),
        "date_bucket": _today_bucket(),
        "schedule_sensitive": schedule_sensitive,
        "schedule_cache_version": schedule_cache_version,
    }

    await redis.set(key, json.dumps(response_payload, ensure_ascii=False), ex=ttl)
    logger.info("Cache set: key={}, ttl={}, sensitive={}", key, ttl, sensitive)

