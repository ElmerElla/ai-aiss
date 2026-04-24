"""LangChain + DashScope 适配器工具。

此模块将提供商特定的 API 调用集中在一处，同时提供
与 LangChain 兼容的辅助函数，用于提示渲染、调用和流式处理。
"""
from __future__ import annotations

import asyncio
from typing import Any, Iterator

import requests
from dashscope import Generation
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate

from app.config import settings
from app.utils.logger import logger


def _count_messages_chars(messages: list[dict[str, str]]) -> int:
    return sum(len(m.get("content") or "") for m in messages)


def _truncate_tail(text: str, max_chars: int) -> str:
    """截断文本尾部并附加说明，保证返回长度不超过 max_chars。"""
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text

    # 首轮按当前差值生成提示；若提示过长则自动退化为硬截断。
    omitted = len(text) - max_chars
    marker = f"\n...[内容已截断 {omitted} 字符]"
    keep = max_chars - len(marker)
    if keep <= 0:
        return text[:max_chars]

    omitted = len(text) - keep
    marker = f"\n...[内容已截断 {omitted} 字符]"
    keep = max_chars - len(marker)
    if keep <= 0:
        return text[:max_chars]
    return text[:keep] + marker


def _trim_messages_for_dashscope(
    messages: list[dict[str, str]],
    *,
    max_total_chars: int,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """按总字符数裁剪消息，优先丢弃旧历史，再裁剪最后一条。"""
    if max_total_chars <= 0 or not messages:
        return messages, {"original_chars": 0, "final_chars": 0, "dropped_messages": 0}

    trimmed = [dict(m) for m in messages]
    original_chars = _count_messages_chars(trimmed)
    total_chars = original_chars
    dropped_messages = 0

    if total_chars <= max_total_chars:
        return trimmed, {
            "original_chars": original_chars,
            "final_chars": total_chars,
            "dropped_messages": dropped_messages,
        }

    # 保留首条(system)和末条(最新 user/assistant)，先移除中间旧历史。
    while total_chars > max_total_chars and len(trimmed) > 2:
        removed = trimmed.pop(1)
        total_chars -= len(removed.get("content") or "")
        dropped_messages += 1

    # 仍超限时，优先裁剪最后一条消息（通常包含大段 context）。
    if total_chars > max_total_chars:
        last_idx = len(trimmed) - 1
        last_content = trimmed[last_idx].get("content") or ""
        overflow = total_chars - max_total_chars
        keep_chars = max(0, len(last_content) - overflow)
        new_last = _truncate_tail(last_content, keep_chars)
        total_chars = total_chars - len(last_content) + len(new_last)
        trimmed[last_idx]["content"] = new_last

    # 极端情况下再裁剪首条消息。
    if total_chars > max_total_chars:
        first_content = trimmed[0].get("content") or ""
        overflow = total_chars - max_total_chars
        keep_chars = max(0, len(first_content) - overflow)
        new_first = _truncate_tail(first_content, keep_chars)
        total_chars = total_chars - len(first_content) + len(new_first)
        trimmed[0]["content"] = new_first

    return trimmed, {
        "original_chars": original_chars,
        "final_chars": total_chars,
        "dropped_messages": dropped_messages,
    }


def _build_dashscope_session() -> requests.Session | None:
    """Create a DashScope HTTP session, optionally ignoring env proxy vars."""
    if settings.DASHSCOPE_TRUST_ENV_PROXY:
        return None

    session = requests.Session()
    # Ignore host-level HTTP(S)_PROXY vars to avoid accidental proxy routing.
    session.trust_env = False
    session.proxies.update({"http": None, "https": None})
    return session


def _message_to_dashscope(message: BaseMessage) -> dict[str, str]:
    """将 LangChain 消息对象转换为 DashScope 的消息格式。"""
    role = "user"
    if isinstance(message, SystemMessage):
        role = "system"
    elif isinstance(message, AIMessage):
        role = "assistant"
    elif isinstance(message, HumanMessage):
        role = "user"

    content = message.content
    if not isinstance(content, str):
        content = str(content)

    return {"role": role, "content": content}


def build_dashscope_messages(
    prompt: ChatPromptTemplate,
    variables: dict[str, Any],
) -> list[dict[str, str]]:
    """渲染 ChatPromptTemplate 并将其转换为 DashScope 消息。"""
    prompt_value = prompt.invoke(variables)
    messages = [_message_to_dashscope(m) for m in prompt_value.to_messages()]
    logger.debug("DashScope messages built: count={}", len(messages))
    return messages


async def ainvoke_chat_prompt(
    prompt: ChatPromptTemplate,
    variables: dict[str, Any],
    *,
    model: str,
    temperature: float,
    max_tokens: int | None = None,
) -> str:
    """根据 LangChain 提示模板执行非流式 DashScope 聊天调用。"""
    raw_messages = build_dashscope_messages(prompt, variables)
    messages, trim_stats = _trim_messages_for_dashscope(
        raw_messages,
        max_total_chars=settings.DASHSCOPE_MAX_INPUT_CHARS,
    )
    if trim_stats["original_chars"] > trim_stats["final_chars"]:
        logger.warning(
            "LLM invoke input truncated: model={}, original_chars={}, final_chars={}, dropped_messages={}",
            model,
            trim_stats["original_chars"],
            trim_stats["final_chars"],
            trim_stats["dropped_messages"],
        )
    logger.info(
        "LLM invoke start: model={}, temperature={}, max_tokens={}, messages={}",
        model,
        temperature,
        max_tokens,
        len(messages),
    )

    def _call() -> Any:
        session = _build_dashscope_session()
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "result_format": "message",
            "temperature": temperature,
            "api_key": settings.ALI_API_KEY,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if session is not None:
            kwargs["session"] = session

        try:
            return Generation.call(**kwargs)
        finally:
            if session is not None:
                session.close()

    response = await asyncio.to_thread(_call)
    if response.status_code != 200:
        logger.error(
            "LLM invoke failed: model={}, status_code={}, message={}",
            model,
            response.status_code,
            response.message,
        )
        raise RuntimeError(
            f"Generation API error: {response.status_code} - {response.message}"
        )

    content = response.output.choices[0].message.content.strip()
    logger.info("LLM invoke success: model={}, content_len={}", model, len(content))
    return content


def stream_chat_prompt(
    prompt: ChatPromptTemplate,
    variables: dict[str, Any],
    *,
    model: str,
    temperature: float,
    max_tokens: int | None = None,
) -> Iterator[str]:
    """通过 LangChain 提示模板流式返回 DashScope 聊天调用的块。"""
    raw_messages = build_dashscope_messages(prompt, variables)
    messages, trim_stats = _trim_messages_for_dashscope(
        raw_messages,
        max_total_chars=settings.DASHSCOPE_MAX_INPUT_CHARS,
    )
    if trim_stats["original_chars"] > trim_stats["final_chars"]:
        logger.warning(
            "LLM stream input truncated: model={}, original_chars={}, final_chars={}, dropped_messages={}",
            model,
            trim_stats["original_chars"],
            trim_stats["final_chars"],
            trim_stats["dropped_messages"],
        )
    logger.info(
        "LLM stream start: model={}, temperature={}, max_tokens={}, messages={}",
        model,
        temperature,
        max_tokens,
        len(messages),
    )

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "result_format": "message",
        "stream": True,
        "incremental_output": True,
        "temperature": temperature,
        "api_key": settings.ALI_API_KEY,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens

    session = _build_dashscope_session()
    if session is not None:
        kwargs["session"] = session

    responses = Generation.call(**kwargs)

    chunk_count = 0
    try:
        for response in responses:
            if response.status_code == 200:
                chunk = response.output.choices[0].message.content
                chunk_count += 1
                if chunk_count % 20 == 0:
                    logger.debug("LLM stream progress: model={}, chunks={}", model, chunk_count)
                yield chunk
            else:
                logger.error(
                    "LLM stream failed: model={}, status_code={}, message={}",
                    model,
                    response.status_code,
                    response.message,
                )
                raise RuntimeError(
                    f"Generation API error: {response.status_code} - {response.message}"
                )
    finally:
        if session is not None:
            session.close()

    logger.info("LLM stream end: model={}, total_chunks={}", model, chunk_count)
