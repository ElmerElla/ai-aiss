from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class IntentType(str, Enum):
    structured = "structured"
    vector = "vector"
    hybrid = "hybrid"
    smalltalk = "smalltalk"


class QueryRequest(BaseModel):
    text: str | None = Field(None, description="文本问题")
    image_base64: str | None = Field(None, description="Base64 编码的图像")
    audio_base64: str | None = Field(None, description="Base64 编码的音频 (wav/mp3)")
    session_id: str | None = Field(None, description="会话 ID，用于上下文关联")
    output_type: str | None = Field(
        None,
        description='输出类型。仅当值为 "json" 时返回结构化 JSON，其他情况默认流式 SSE。',
    )


class QueryResponse(BaseModel):
    answer: str = Field(..., description="助手生成的回答")
    session_id: str = Field(..., description="本次会话 ID")
    response_time_ms: int = Field(..., description="耗时（毫秒）")
    cached: bool = Field(False, description="是否来自缓存")

