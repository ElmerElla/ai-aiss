"""意图分类与回答生成服务（LangChain 重构版）。

将用户查询分类为：
- ``structured``：结构化数据查询（SQL）
- ``vector``：知识库向量检索
- ``hybrid``：混合查询
"""
from __future__ import annotations

from datetime import date
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableLambda

from app.config import settings
from app.models.models import ChatLog, SenderEnum
from app.schemas.query import IntentType
from app.services.langchain_service import ainvoke_chat_prompt, stream_chat_prompt
from app.utils.logger import logger

_CLASSIFY_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """
你是一个校园智能助手的意图分类器。
根据学生的问题，判断最合适的查询方式，只需回答下列四者之一（全小写英文单词，不含标点）：

structured - 仅限可以通过系统查询的明确结构化数据，例如：
  学生成绩、课程安排、选课信息、个人信息、学院专业列表、教师联系方式等。
  注意：如果询问如何处理事务、政策规定、法律限制等，请不要归类为 structured！

vector - 需要在知识库（文档、规定、指南等）中进行纯文字语义搜索的通用问题，例如：
  校园规章制度、法律法规、惩罚/违纪规定、通知公告、办事流程、设备损坏处理、报修说明、常见服务指南等。

hybrid - 需要结合个人信息查询和知识库搜索的问题，例如：
 "我本学期成绩是否符合奖学金条件"

smalltalk - 闲聊/寒暄/感谢/情绪表达等不需要查询数据库或知识库的问题，例如：
    "你好"、"谢谢"、"你是谁"、"你真棒"、"晚安"

只返回一个单词：structured、vector、hybrid 或 smalltalk。""",
        ),
        ("user", "{query}"),
    ]
)

_REWRITE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "你是一个查询重写助手。将用户最新问题（结合最近3轮历史）重写为独立、完整的查询句。\n"
            "1. 若上文提及具体学期（如202509）、课程或日期，而新问题（如'导出'）缺失该信息，请务必补充。\n"
            "2. 若无缺失信息，输出原句。\n"
            "3. 直接输出结果，不含任何解释。",
        ),
        MessagesPlaceholder("history"),
        ("user", "{query}"),
    ]
)

_MAX_REWRITE_QUERY_CHARS = 1200
_MAX_SUMMARY_HISTORY_COUNT = 6
_MAX_SUMMARY_HISTORY_ITEM_CHARS = 1200
_MAX_SUMMARY_QUERY_CHARS = 1200
_MAX_SUMMARY_CONTEXT_CHARS = 18000


def _build_summary_prompt(current_date_str: str) -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                f"当前系统日期: {current_date_str}。\n"
                "你是一个贴心的校园智能助手。根据数据回答问题，语言风格自然亲切。\n"
                "重要回答规范：\n"
                "1. 课表或课程查询必须列出时间、地点、教师，严禁只列课程名。\n"
                "2. 数据库里的数据直接使用，不要质疑学号位数等格式。\n"
                "3. 不要出现任何英文字段名、属性名或数据库列名（如 credit_earned、term_id、course_name 等），必须转成人类可读自然语言。\n"
                "4. 查询本人未命中时回答无相关安排；查询他人时明确无法查询。\n"
                "5. 严禁输出内部过程说明（如参数、term_id 推断、工具调用、系统判断过程）。\n"
                "6. 严禁出现 term_id、args、tool_calls、JSON字段名 等技术字样。\n"
                "6.5 学期必须使用中文可读格式输出，例如：202501 → 2024-2025学年 第二学期，202509 → 2025-2026学年 第一学期。严禁直接输出原始6位学期ID。\n"
                "7. 涉及上学期/本学期/下学期时，只能依据提供的数据结果，不要按当前日期自行计算学期。\n"
                "8. 面向学生直接作答，不要使用管理员/运维/系统调试口吻。\n"
                "9. 若相关数据或结构化判定明确存在课程记录，禁止回答“没有课程安排/暂无课程”。只有在明确未命中时才能说没有。\n"
                "10. 当问题询问“这周/下周是第几周”时，若结构化数据含 computed_week_info 或结构化判定含“周次判定”，必须严格使用其中给出的周次数字；不得根据 week_no 最大值（如1-16）自行推断当前周。\n"
                "11. 当结构化判定包含“目标周判定”或“目标周无课日”时，必须严格按其作答；未列出的日期一律回答无课，不得从历史或其他周次补全课程。\n"
                "12. 课表回答必须以本次相关数据为唯一事实来源，历史消息只可用于指代消解，不可覆盖本次数据结论。\n"
                "13. 当结构化判定包含\"人员联系方式判定：在教师通讯录匹配到...\"时，应提供该教师的公开联系方式（电话/邮箱/办公室等）。\\n"
                "14. 当结构化判定包含\"人员联系方式判定：未在教师通讯录匹配到...\"时，必须明确说明无法查询其他同学/学生的个人联系方式，并给出合规建议（班级群、课程群、辅导员转达）。\\n"
                "15. 当问题涉及图片内容时，严格遵守【回答要求】中的指令：学术/技术类图片直接回答不要额外推荐；无关图片简短回复后可自然提醒关注校园活动。\\n"
                "16. 当结构化判定包含\"停课判定\"时，必须明确告知用户哪些课程已停课（无需上课），严禁将停课课程按正常课程输出时间地点。若用户询问明天/某天的课表，停了的课不应列入\"有课\"列表，但可单独说明\"XX课程已停课\"以免学生误解。\\n"
                "17. 严禁出现‘系统标记为’‘系统标明’等内部说明话术，严禁输出 cancelled、active、schedule_status 等内部状态值或技术字段名，统一使用‘已停课’‘正常’等中文自然语言。\n"
                "18. 课表时间必须严格按以下节次映射输出，禁止自行推算或凭记忆输出错误时间：\n"
                "    第1-2节 → 08:10-09:40；第3-4节 → 10:00-11:40；第5-6节 → 14:00-15:40；\n"
                "    第7-8节 → 16:00-17:30；第9-10节 → 18:00-19:00；第11-12节 → 20:00-21:40。\n"
                "19. 隐私保护红线：严禁在回答中主动透露用户的个人敏感信息（学号、电话、邮箱、学院、专业、班级、成绩、课表、教师联系方式等），除非用户明确查询这些信息。当用户询问与个人信息无关的问题（如界面评价、通用知识、图片分析、闲聊等）时，禁止引用任何个人数据。\n"
                "20. 日期推算必须严格基于上述当前系统日期，禁止出错。提到‘明天’‘后天’‘下周’等相对日期时必须准确推算，严禁将周六说成周五、将周日说成周一等低级错误。\n"
                "21. 当结构化判定包含‘目标日期判定’时，必须严格使用其中给出的具体日期（如 2026-04-30），禁止自行推算或改写为其他日期。",



            ),
            MessagesPlaceholder("history"),
            ("user", "学生问题：{query}\n\n相关数据：\n{context}"),
        ]
    )


def _to_langchain_history(history: list[ChatLog] | None, limit: int | None = None) -> list[tuple[str, str]]:
    if not history:
        return []

    messages = history[-limit:] if limit else history
    converted: list[tuple[str, str]] = []
    for msg in messages:
        role = "human" if msg.sender == SenderEnum.student else "ai"
        converted.append((role, msg.message_content or ""))
    return converted


def _truncate_tail(text: str, max_chars: int, *, label: str) -> tuple[str, bool]:
    if max_chars <= 0:
        return "", bool(text)
    if len(text) <= max_chars:
        return text, False

    omitted = len(text) - max_chars
    marker = f"\n...[{label}已截断 {omitted} 字符]"
    keep = max_chars - len(marker)
    if keep <= 0:
        return text[:max_chars], True

    omitted = len(text) - keep
    marker = f"\n...[{label}已截断 {omitted} 字符]"
    keep = max_chars - len(marker)
    if keep <= 0:
        return text[:max_chars], True
    return text[:keep] + marker, True


def _truncate_middle(text: str, max_chars: int, *, label: str) -> tuple[str, bool]:
    if max_chars <= 0:
        return "", bool(text)
    if len(text) <= max_chars:
        return text, False

    # 对结构化上下文保留头尾，减少关键信息丢失。
    marker = f"\n...[{label}已截断 {{}} 字符]...\n"
    omitted = len(text) - max_chars
    marker_real = marker.format(omitted)
    remain = max_chars - len(marker_real)
    if remain <= 2:
        return _truncate_tail(text, max_chars, label=label)

    head_keep = remain // 2
    tail_keep = remain - head_keep
    omitted = len(text) - head_keep - tail_keep
    marker_real = marker.format(omitted)
    remain = max_chars - len(marker_real)
    if remain <= 2:
        return _truncate_tail(text, max_chars, label=label)

    head_keep = remain // 2
    tail_keep = remain - head_keep
    return text[:head_keep] + marker_real + text[-tail_keep:], True


def _build_summary_payload(
    query: str,
    context: str,
    history: list[ChatLog] | None,
) -> dict[str, Any]:
    raw_history = _to_langchain_history(history, limit=_MAX_SUMMARY_HISTORY_COUNT)
    payload_history: list[tuple[str, str]] = []
    trimmed_history_items = 0
    for role, content in raw_history:
        clipped, was_trimmed = _truncate_tail(
            content or "",
            _MAX_SUMMARY_HISTORY_ITEM_CHARS,
            label="历史消息",
        )
        payload_history.append((role, clipped))
        if was_trimmed:
            trimmed_history_items += 1

    query_clipped, query_trimmed = _truncate_tail(
        query or "",
        _MAX_SUMMARY_QUERY_CHARS,
        label="问题",
    )
    context_clipped, context_trimmed = _truncate_middle(
        context or "",
        _MAX_SUMMARY_CONTEXT_CHARS,
        label="相关数据",
    )

    dropped_history = max(0, len(history or []) - len(raw_history))
    if query_trimmed or context_trimmed or trimmed_history_items or dropped_history:
        logger.warning(
            "Summarize payload trimmed: query_trimmed={}, context_trimmed={}, history_trimmed_items={}, history_dropped={}, query_len={}, context_len={}, history_count={}",
            query_trimmed,
            context_trimmed,
            trimmed_history_items,
            dropped_history,
            len(query or ""),
            len(context or ""),
            len(history or []),
        )

    return {
        "history": payload_history,
        "query": query_clipped,
        "context": context_clipped,
    }


def _current_date_text() -> str:
    today = date.today()
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    return f"{today.year}年{today.month}月{today.day}日 {weekdays[today.weekday()]}"


async def classify_intent(query: str) -> IntentType:
    """分类用户查询意图。"""
    logger.info("Intent classification start: query_len={}", len(query))

    async def _invoke_classifier(text: str) -> str:
        return await ainvoke_chat_prompt(
            _CLASSIFY_PROMPT,
            {"query": text},
            model=settings.LLM_MODEL_INTENT_CLASSIFY,
            temperature=0.0,
            max_tokens=10,
        )

    chain = RunnableLambda(_invoke_classifier) | StrOutputParser()

    try:
        raw = (await chain.ainvoke(query)).strip().lower()
    except Exception as exc:
        logger.warning(
            "Intent classification failed, fallback to vector: {}: {}",
            exc.__class__.__name__,
            str(exc)[:240],
        )
        return IntentType.vector

    for intent in IntentType:
        if intent.value in raw:
            logger.info("Intent classified: {}", intent.value)
            return intent
    logger.warning("Intent parse uncertain, fallback to vector: raw={}", raw)
    return IntentType.vector


async def rewrite_query_with_context(query: str, history: list[ChatLog]) -> str:
    """结合历史上下文重写用户查询，使其补足缺失信息。"""
    if not history:
        logger.debug("Rewrite skipped: no history")
        return query

    payload: dict[str, Any] = {
        "history": _to_langchain_history(history, limit=3),
        "query": query,
    }

    async def _invoke_rewriter(data: dict[str, Any]) -> str:
        return await ainvoke_chat_prompt(
            _REWRITE_PROMPT,
            data,
            model=settings.LLM_MODEL_QUERY_REWRITE,
            temperature=0.0,
        )

    chain = RunnableLambda(_invoke_rewriter) | StrOutputParser()

    try:
        rewritten = (await chain.ainvoke(payload)).strip()
        result = rewritten if len(rewritten) >= 2 else query
        if len(result) > _MAX_REWRITE_QUERY_CHARS:
            logger.warning(
                "Rewrite output truncated: original_len={}, max_len={}",
                len(result),
                _MAX_REWRITE_QUERY_CHARS,
            )
            result = result[:_MAX_REWRITE_QUERY_CHARS]
        logger.info(
            "Rewrite completed: original_len={}, rewritten_len={}, history_count={}",
            len(query),
            len(result),
            len(history),
        )
        return result
    except Exception as exc:
        logger.warning(
            "Rewrite failed, fallback to original query: {}: {}",
            exc.__class__.__name__,
            str(exc)[:240],
        )
        return query


async def summarize_answer(
    query: str, context: str, history: list[ChatLog] | None = None
) -> str:
    """根据上下文数据生成用户友好的回答。"""
    logger.info(
        "Summarize start: query_len={}, context_len={}, history_count={}",
        len(query),
        len(context),
        len(history or []),
    )
    prompt = _build_summary_prompt(_current_date_text())
    payload = _build_summary_payload(query, context, history)

    async def _invoke_summarizer(data: dict[str, Any]) -> str:
        return await ainvoke_chat_prompt(
            prompt,
            data,
            model=settings.LLM_MODEL_FINAL_ANSWER,
            temperature=0.2,
            max_tokens=4096,
        )

    chain = RunnableLambda(_invoke_summarizer) | StrOutputParser()
    result = await chain.ainvoke(payload)
    logger.info("Summarize completed: answer_len={}", len(result))
    return result


def summarize_answer_stream(
    query: str, context: str, history: list[ChatLog] | None = None
):
    """根据上下文数据生成用户友好的回答 (流式输出)。"""
    logger.info(
        "Summarize stream start: query_len={}, context_len={}, history_count={}",
        len(query),
        len(context),
        len(history or []),
    )
    prompt = _build_summary_prompt(_current_date_text())
    payload = _build_summary_payload(query, context, history)

    yield from stream_chat_prompt(
        prompt,
        payload,
        model=settings.LLM_MODEL_FINAL_ANSWER,
        temperature=0.2,
        max_tokens=4096,
    )
