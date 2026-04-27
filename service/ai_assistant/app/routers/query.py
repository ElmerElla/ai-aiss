"""
智能查询路由模块

功能介绍：
-----------
本模块是 AI 校园助手的核心路由，提供单一统一的查询端点 /api/v1/query，
处理来自认证学生的文本/图像/音频多模态问题。

完整处理流程：
1. 解码多模态输入（图像 → 文本，音频 → 文本）
2. 组合统一查询文本
3. 安全检查（自杀/暴力内容拦截 + 隐私违规检测）
4. Redis 缓存查找（通过 DID + 查询哈希）
5. 会话历史加载（Redis 会话隔离）
6. 查询重写（结合上下文补全缺失信息）
7. 意图分类（structured / vector / hybrid / smalltalk）
8. 查询执行（SQL 结构化查询 / 向量知识库检索 / 混合）
9. LLM 总结生成回答（qwen-plus，支持流式 SSE）
10. 响应缓存与对话日志持久化

附加接口：
- DELETE /sessions → 清除当前学生的所有会话缓存与历史

输出模式：
- 默认：SSE 流式输出（text/event-stream）
- JSON：当 output_type="json" 时返回完整 JSON
"""
from __future__ import annotations

import time
import uuid
from types import SimpleNamespace

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

import json
from fastapi.responses import StreamingResponse
from app.config import settings
from app.database import AsyncSessionLocal
from app.dependencies import get_current_user, get_db, get_redis
from app.models.models import SenderEnum, SystemActionEnum
from app.schemas.query import IntentType, QueryRequest, QueryResponse
from app.services import (
    cache_service,
    chat_log_service,
    intent_service,
    media_service,
    query_service,
    safety_service,
)
from app.utils.logger import logger
from app.utils.privacy import generate_did

router = APIRouter(prefix="/api/v1", tags=["查询"])


def _is_smalltalk_like(text: str) -> bool:
    """
    判断查询是否为简短的寒暄/礼貌用语。
    
    用于辅助路由决策，识别无需检索数据库的闲聊场景。
    """
    normalized = (text or "").strip().lower()
    if not normalized:
        return False
    keywords = (
        "你好", "您好", "嗨", "哈喽", "在吗", "谢谢", "多谢", "辛苦了", "晚安", "早上好",
        "hello", "hi", "hey", "thanks", "thank you", "good morning", "good night",
    )
    return len(normalized) <= 40 and any(k in normalized for k in keywords)


def _is_pure_image_qa(text: str) -> bool:
    """
    判断是否为纯图片问答（而非以图片为辅助的结构化查询）。
    
    逻辑：
        - 若文本为空 → 判定为纯图片问答
        - 若包含课表/成绩/选课等结构化关键词 → 非纯图片问答
        - 若包含解释/分析/评价等图片理解关键词 → 纯图片问答
        - 文本很短（< 16 字）且无结构化关键词 → 纯图片问答
    """
    if not text:
        return True
    text_lower = text.strip().lower()

    # 明确是结构化查询意图的，不走图片问答逻辑
    structured_keywords = (
        "课表", "课程", "成绩", "分数", "学分", "绩点", "考试", "选课",
        "教室", "教师", "老师", "联系方式", "电话", "邮箱", "办公室",
        "我的", "查询", "查一下", "查找", "导出", "list", "schedule", "score", "grade",
    )
    if any(kw in text_lower for kw in structured_keywords):
        return False

    # 图片解释/评价/问答类关键词
    image_qa_keywords = (
        "解释", "说明", "分析", "解读", "描述", "讲讲", "翻译", "总结", "概括",
        "谈谈", "怎么看", "怎么理解", "什么意思", "是什么", "介绍一下",
        "帮我看看", "看一下", "瞅瞅", "瞧一瞧", "什么内容",
        "怎么样", "如何", "评价", "点评", "觉得", "看法", "建议",
        "好看吗", "美观", "设计", "界面", "布局", "风格", "配色",
        "优缺点", "改进", "完善", "优化", "对比", "像什么", "属于什么", "什么类型",
        "describe", "explain", "analyze", "analysis", "what is", "what's this",
        "tell me about", "interpret", "summarize", "summarise",
        "how about", "what do you think", "review", "opinion", "suggestion",
        "look like", "type of", "kind of", "ui", "interface", "design",
    )
    if any(kw in text_lower for kw in image_qa_keywords):
        return True

    # 文本很短（< 16 字）且没有结构化关键词，大概率是图片问答
    return len(text.strip()) < 16


def _is_campus_related_image(img_text: str) -> bool:
    """
    判断图片内容是否与校园/学术知识相关。
    
    通过关键词匹配识别课本、课件、代码、公式、流程图等学术内容，
    用于决定图片问答的回答策略。
    """
    if not img_text:
        return False
    text_lower = img_text.lower()
    campus_keywords = (
        # 学术/技术类
        "流程图", "数据流图", "uml", "类图", "时序图", "思维导图", "架构图",
        "系统图", "模块图", "e-r图", "拓扑图", "状态图", "用例图", "活动图",
        "课本", "教材", "笔记", "课件", "ppt", "幻灯片", "试卷", "习题", "题目",
        "公式", "定理", "定义", "概念", "推导", "证明", "计算",
        "代码", "程序", "算法", "伪代码", "函数", "变量", "类", "接口",
        "数据结构", "操作系统", "计算机网络", "数据库", "软件工程", "编译原理",
        "离散数学", "高等数学", "线性代数", "概率论", "高数", "线代", "概率",
        "马克思主义", "毛泽东", "思想概论", "毛概", "马原", "思修", "思想道德",
        "近代史", "思政", "政治", "哲学", "经济学", "管理学", "心理学",
        "教育学", "法学", "医学", "生物学", "化学", "物理", "英语", "语文",
        "文学", "历史", "地理", "数学", "计算机", "编程", "技术", "工程",
        "科学", "实验", "报告", "论文", "文献", "综述", "参考文献", "引用",
        "设计模式", "网络协议", "sql", "html", "css", "javascript", "java",
        "python", "c++", "c语言", "编程语言", "框架", "库", "api", "接口",
        "学期", "学分", "必修", "选修", "专业课", "公共课", "通识课",
        # 学生事务/规章制度类（学生手册、奖励评选、学籍管理等）
        "奖励", "评选", "奖学金", "助学金", "优秀学生", "三好学生", "标兵",
        "学生手册", "规章制度", "管理办法", "规定", "条例", "细则", "章程",
        "请假", "报销", "申请", "审批", "流程", "材料", "条件", "要求",
        "处分", "违纪", "警告", "通报", "纪律",
        "毕业证", "学位证", "成绩单", "学籍", "转专业", "休学", "退学", "复学",
        "宿舍", "食堂", "图书馆", "教务", "校历", "通知", "公告", "办事指南",
        "辅导员", "班主任", "院长", "校长", "办公会", "会议",
    )
    return any(kw in text_lower for kw in campus_keywords)


_PURE_STRUCTURED_PATTERNS = (
    r"我的(?:个人)?信息",
    r"(?:查|看|导出|显示|帮我查|帮我找).*?(?:课表|课程表|成绩|分数|学分|绩点|选课记录|选课)",
    r"(?:查|看|找).*?(?:老师|教师|教授|讲师|导师|辅导员).*?(?:联系|电话|邮箱|办公|办公室)",
    r"(?:查|看|找).*?(?:教室|机房|实验室)",
    r"(?:学院|专业|班级|院系).*?(?:目录|列表|有哪些|全部)",
    r"(?:这学期|上学期|下学期|本学期|上一学期|下一学期).*?(?:成绩|课表|选课)",
    r"(?:第\s*\d{1,2}\s*周|下周|本周|上周|今天|明天|后天|昨天|前天).*?(?:课表|有课|什么课|课程|安排)",
)
_KB_INDICATOR_PATTERNS = (
    r"怎么办", r"怎么弄", r"怎么处理", r"如何申请", r"怎么申请",
    r"需要什么材料", r"什么条件", r"符合条件", r"要求",
    r"为什么", r"原因", r"解释", r"什么是",
)


def _is_pure_structured_query(text: str) -> bool:
    """
    判断查询是否为明显的纯结构化查询（单一意图，无需知识库辅助）。
    
    通过正则模式匹配识别课表、成绩、教师联系方式等明确结构化意图，
    同时排除包含"为什么"/"怎么办"等需要知识库辅助的混合意图。
    """
    text_lower = (text or "").lower()
    has_pure = any(re.search(p, text_lower) for p in _PURE_STRUCTURED_PATTERNS)
    if not has_pure:
        return False
    has_kb = any(re.search(p, text_lower) for p in _KB_INDICATOR_PATTERNS)
    return not has_kb


def _sse_response(generator):
    """
    统一构造 SSE 响应对象。
    
    设置专用 HTTP 头（Cache-Control、X-Accel-Buffering 等），
    降低被反向代理缓冲或改写的概率，确保流式输出顺畅。
    """
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _to_public_stream_error(exc: Exception) -> str:
    """
    将内部异常转换为用户友好的公开错误信息。
    
    针对模型输入超长、AI 服务不可用等常见错误提供明确的提示语。
    """
    raw = str(exc or "").strip()
    lowered = raw.lower()

    if "range of input length should be [1, 30720]" in lowered or "invalidparameter" in lowered:
        return "当前问题关联的数据过多，已超过模型输入上限。请缩小问题范围或新开会话后重试。"
    if "generation api error" in lowered:
        return "AI 生成服务暂时不可用，请稍后重试。"
    return "生成回答时发生异常，请稍后重试。"


def _session_history_key(did: str, session_id: str) -> str:
    """
    构建 Redis 中会话隔离历史的存储键名。
    
    格式：chat:session_history:{did}:{session_id}
    """
    return f"chat:session_history:{did}:{session_id}"


async def _load_session_history(
    redis: aioredis.Redis,
    *,
    did: str,
    session_id: str,
    limit: int,
):
    """
    从 Redis 加载会话隔离历史记录。
    
    返回兼容 intent_service 的消息对象列表，用于查询重写和回答生成。
    通过会话隔离避免并发会话之间的上下文串话。
    """
    key = _session_history_key(did, session_id)
    raw_items = await redis.lrange(key, -limit, -1)

    history = []
    for raw in raw_items:
        try:
            payload = json.loads(raw)
            sender = SenderEnum(payload.get("sender", SenderEnum.student.value))
            content = payload.get("content", "")
        except Exception:
            continue
        history.append(SimpleNamespace(sender=sender, message_content=content))
    return history


async def _append_session_history(
    redis: aioredis.Redis,
    *,
    did: str,
    session_id: str,
    sender: SenderEnum,
    content: str,
):
    """
    向 Redis 写入单条会话历史记录。
    
    自动裁剪列表长度至 MAX_HISTORY_COUNT，并设置 7 天过期时间。
    """
    key = _session_history_key(did, session_id)
    await redis.rpush(
        key,
        json.dumps({"sender": sender.value, "content": content}, ensure_ascii=False),
    )
    await redis.ltrim(key, -settings.MAX_HISTORY_COUNT, -1)
    await redis.expire(key, 60 * 60 * 24 * 7)


@router.post(
    "/query",
    summary="向校园助手发送问题",
    response_model=None,
    description=(
        "接受文本、base64图像和/或base64音频。"
        "需要有效的JWT Bearer令牌。"
    ),
)
async def query_endpoint(
    body: QueryRequest,
    student_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> StreamingResponse | QueryResponse:
    """
    智能问答核心接口（支持多模态输入和流式输出）。
    
    参数:
        body: 查询请求体（含文本/图片/音频/session_id/output_type）
        student_id: 从 JWT 解析的当前学生学号
        db: 数据库会话
        redis: Redis 客户端
    
    返回:
        StreamingResponse: SSE 流式输出（默认）
        QueryResponse: 完整 JSON 响应（output_type="json" 时）
    
    完整处理流程详见模块文档字符串。
    """
    start_ms = time.time()
    session_id = body.session_id or str(uuid.uuid4())
    wants_json_output = (body.output_type or "").strip().lower() == "json"
    did = generate_did(student_id)
    logger.info(
        "Query request received: student_id={}, session_id={}, has_text={}, has_image={}, has_audio={}, wants_json_output={}",
        student_id,
        session_id,
        bool(body.text),
        bool(body.image_base64),
        bool(body.audio_base64),
        wants_json_output,
    )

    # ------------------------------------------------------------------
    # 1. 构建统一文本查询从多模态输入
    # ------------------------------------------------------------------
    text_parts: list[str] = []

    if body.image_base64:
        try:
            logger.info("Image modality detected, running image_to_text")
            img_text = await media_service.image_to_text(body.image_base64)
            text_parts.append(f"[图片内容] {img_text}")
        except RuntimeError as exc:
            logger.exception("Image processing failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"图片处理失败: {exc}",
            )

    if body.audio_base64:
        try:
            logger.info("Audio modality detected, running audio_to_text")
            audio_text = await media_service.audio_to_text(body.audio_base64)
            text_parts.append(f"[语音转文字] {audio_text}")
        except RuntimeError as exc:
            logger.exception("Audio processing failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"音频处理失败: {exc}",
            )
        except Exception as exc:
            logger.exception("Audio processing failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"音频处理失败: {exc}",
            )

    if body.text:
        text_parts.append(body.text)

    if not text_parts:
        logger.warning("Query rejected: no valid modality payload")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="至少需要提供文本、image_base64或audio_base64中的一个。",
        )

    unified_query = "\n".join(text_parts)
    logger.info("Unified query built: len={}", len(unified_query))

    # ------------------------------------------------------------------
    # 2. 缓存查找
    # ------------------------------------------------------------------
    # 对于极快的响应，我们先查询缓存。
    # 如果命中了安全的查询，直接返回。
    redis_available = True
    try:
        cached = await cache_service.get_cached_response(redis, did, unified_query)
    except Exception:
        cached = None
        redis_available = False
        logger.exception("Redis cache lookup failed, continue with DB fallback history")

    if cached:
        elapsed = int((time.time() - start_ms) * 1000)
        logger.info("Cache hit: did={}, elapsed_ms={}", did[:12], elapsed)

        if wants_json_output:
            return QueryResponse(
                answer=cached["answer"],
                session_id=session_id,
                response_time_ms=elapsed,
                cached=True,
                suggested_questions=cached.get("suggested_questions", []),
            )

        async def _mock_stream_cache():
            final_payload = {
                "chunk": cached["answer"],
                "done": False,
            }
            yield f"data: {json.dumps(final_payload, ensure_ascii=False)}\n\n"
            done_payload = {
                "chunk": "",
                "response_time_ms": elapsed,
                "cached": True,
                "done": True,
            }
            if "suggested_questions" in cached:
                done_payload["suggested_questions"] = cached["suggested_questions"]
            yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
        return _sse_response(_mock_stream_cache())
    if redis_available:
        logger.info("Cache miss: did={}", did[:12])
    else:
        logger.warning("Cache skipped due to Redis failure: did={}", did[:12])

    # ------------------------------------------------------------------
    # 3. 获取最近历史记录
    # ------------------------------------------------------------------
    # 尽早发起数据库请求
    # 使用 session 级历史，避免并发会话互相污染上下文
    if redis_available:
        try:
            history = await _load_session_history(
                redis,
                did=did,
                session_id=session_id,
                limit=settings.MAX_HISTORY_COUNT,
            )
            logger.info("Session history loaded from Redis: count={}", len(history))
        except Exception:
            # Redis 异常时降级到原有 DID 历史，保证可用性
            logger.exception("Redis session history load failed, fallback to DB history")
            history = await chat_log_service.get_recent_messages(
                db, student_id, limit=settings.MAX_HISTORY_COUNT
            )
            logger.info("History loaded from DB fallback: count={}", len(history))
    else:
        history = await chat_log_service.get_recent_messages(
            db, student_id, limit=settings.MAX_HISTORY_COUNT
        )
        logger.info(
            "History loaded from DB fallback due to Redis cache failure: count={}",
            len(history),
        )

    # ------------------------------------------------------------------
    # 4. 并发执行：安全检查、隐私检查 和 意图重写
    # ------------------------------------------------------------------
    import asyncio
    
    # 将多个异步任务一起打包以节省时间
    danger_task = asyncio.create_task(safety_service.is_dangerous(unified_query))
    rewrite_task = asyncio.create_task(intent_service.rewrite_query_with_context(unified_query, history))
    logger.info("Parallel tasks started: danger_check + query_rewrite")
    
    # 隐私检查：禁止查询他人学号
    other_student_id = safety_service.is_privacy_violation(unified_query, student_id)
    if other_student_id:
        logger.warning(
            "Privacy violation blocked: requester={}, target_student_id={}",
            student_id,
            other_student_id,
        )
        answer = (
            f"❌ 隐私保护提示：检测到你正在查询学号 {other_student_id} 的信息。\n\n"
            "根据校园数据安全规范，你只能访问自己的个人数据（如课表、成绩、选课等），"
            "无法查询其他同学的信息。\n\n"
            "如果你需要了解他人的安排，建议直接询问对方。"
        )
        
        # 记录此次交互 (取消所有等待的后台任务不是必须的，因为Python会自然回收，也可以不取消)
        await chat_log_service.log_message(
            db, student_id=student_id, sender=SenderEnum.student,
            message_content=unified_query, system_action=SystemActionEnum.none, is_dangerous=False
        )
        try:
            await _append_session_history(
                redis,
                did=did,
                session_id=session_id,
                sender=SenderEnum.student,
                content=unified_query,
            )
        except Exception:
            pass
        elapsed = int((time.time() - start_ms) * 1000)
        await chat_log_service.log_message(
            db, student_id=student_id, sender=SenderEnum.agent,
            message_content=answer, system_action=SystemActionEnum.none,
            response_time_ms=elapsed, is_dangerous=False
        )
        try:
            await _append_session_history(
                redis,
                did=did,
                session_id=session_id,
                sender=SenderEnum.agent,
                content=answer,
            )
        except Exception:
            pass

        if wants_json_output:
            return QueryResponse(
                answer=answer,
                session_id=session_id,
                response_time_ms=elapsed,
                cached=False,
            )
        
        async def _mock_stream1():
            yield f"data: {json.dumps({'chunk': answer, 'done': False}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'chunk': '', 'response_time_ms': elapsed, 'cached': False, 'done': True}, ensure_ascii=False)}\n\n"
        return _sse_response(_mock_stream1())

    dangerous = await danger_task
    system_action = SystemActionEnum.flag_danger if dangerous else SystemActionEnum.none
    logger.info("Danger check completed: dangerous={}", dangerous)

    if dangerous:
        logger.warning("Dangerous content detected, return intervention response")
        # 记录学生的回合，保留真实的 student_id
        await chat_log_service.log_message(
            db, student_id=student_id, sender=SenderEnum.student,
            message_content=unified_query, system_action=SystemActionEnum.flag_danger, is_dangerous=True
        )
        try:
            await _append_session_history(
                redis,
                did=did,
                session_id=session_id,
                sender=SenderEnum.student,
                content=unified_query,
            )
        except Exception:
            pass
        answer = (
            "我注意到你可能正在经历一些困难，你并不孤单。"
            "请立即联系学校心理健康中心或拨打心理援助热线：北京 010-82951332，全国 400-161-9995。"
            "你的老师和辅导员也随时可以帮助你。"
        )
        elapsed = int((time.time() - start_ms) * 1000)
        await chat_log_service.log_message(
            db, student_id=student_id, sender=SenderEnum.agent,
            message_content=answer, system_action=SystemActionEnum.flag_danger,
            response_time_ms=elapsed, is_dangerous=True
        )
        try:
            await _append_session_history(
                redis,
                did=did,
                session_id=session_id,
                sender=SenderEnum.agent,
                content=answer,
            )
        except Exception:
            pass

        if wants_json_output:
            return QueryResponse(
                answer=answer,
                session_id=session_id,
                response_time_ms=elapsed,
                cached=False,
            )
        
        async def _mock_stream2():
            yield f"data: {json.dumps({'chunk': answer, 'done': False}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'chunk': '', 'response_time_ms': elapsed, 'cached': False, 'done': True}, ensure_ascii=False)}\n\n"
        return _sse_response(_mock_stream2())

    # 获取重写后的自然语言查询
    contextual_query = await rewrite_task
    logger.info("Query rewrite completed: len={}", len(contextual_query))

    # 记录学生的回合 (仅 DID，不记录原始 student_id)
    await chat_log_service.log_message(
        db, student_id=student_id, sender=SenderEnum.student,
        message_content=unified_query, system_action=SystemActionEnum.none, is_dangerous=False
    )
    try:
        await _append_session_history(
            redis,
            did=did,
            session_id=session_id,
            sender=SenderEnum.student,
            content=unified_query,
        )
    except Exception:
        pass
    
    # ------------------------------------------------------------------
    # 5. 意图分类 (基于重写后的查询)
    # ------------------------------------------------------------------
    try:
        intent = await intent_service.classify_intent(contextual_query)
    except Exception:
        intent = IntentType.vector  # 后备方案
        logger.exception("Intent classify failed, fallback to vector")
    logger.info("Intent resolved: {}", intent.value)

    # ------------------------------------------------------------------
    # 5.5 图片纯问答场景：跳过检索，直接基于图片描述回答
    # ------------------------------------------------------------------
    skip_query_execution = False
    image_direct_context = ""
    suggest_task = None
    if body.image_base64 and _is_pure_image_qa(body.text or ""):
        # 强制改为 smalltalk，避免触发任何检索
        intent = IntentType.smalltalk
        if _is_campus_related_image(img_text):
            image_direct_context = (
                f"[图片内容]\n{img_text}\n\n"
                "【回答要求】请直接根据图片内容回答用户问题，不要做无关推荐，"
                "不要提及检索或数据库过程，严禁输出与图片无关的课程、教师、课表等信息。"
            )
            logger.info("Image query routed as campus-related direct QA")
        else:
            image_direct_context = (
                f"[图片内容]\n{img_text}\n\n"
                "【回答要求】图片内容与校园知识无关。请先简短友好地回应图片内容（1-2句话），"
                "然后自然地提醒用户关注近期课程或校园活动，但不需要列出具体课程明细。"
            )
            logger.info("Image query routed as non-campus direct QA")
        skip_query_execution = True
        # 异步启动推荐问题生成
        suggest_task = asyncio.create_task(intent_service.generate_suggested_questions(img_text or ""))

    # ------------------------------------------------------------------
    # 6. 查询执行 (基于重写后的查询)
    # ------------------------------------------------------------------
    try:
        if skip_query_execution:
            context = image_direct_context
            logger.info("Query pipeline skipped for image direct QA: context_len={}", len(context))
        else:
            # execute_query 内部现在支持从 query 文本中提取 term_id (例如 202509)
            logger.info("Executing query pipeline with intent={}", intent.value)
            context = await query_service.execute_query(
                db,
                contextual_query,
                intent,
                student_id,
                raw_query=unified_query,
            )
            logger.info("Query pipeline completed: context_len={}", len(context))
    except Exception as exc:
        logger.exception("Query execution failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"查询执行失败: {exc}",
        )

    # 意图后处理：根据实际返回的上下文纠正意图
    # 当原始分类为 vector 但 execute_query 中触发了结构化查询时，
    # 可能同时执行了向量检索，需根据 context 内容判断真实查询类型。
    has_structured = "结构化判定" in context or "结构化数据结果:" in context
    has_vector = "知识库内容：\n" in context

    if intent == IntentType.vector and has_structured:
        if has_vector:
            intent = IntentType.hybrid
            logger.info("Intent corrected after execution: vector -> hybrid (both structured and vector context detected)")
        else:
            intent = IntentType.structured
            logger.info("Intent corrected after execution: vector -> structured (structured context detected)")
    elif intent == IntentType.structured and not has_structured and has_vector:
        intent = IntentType.vector
        logger.info("Intent corrected after execution: structured -> vector (vector context detected)")
    elif intent == IntentType.hybrid and has_structured and not has_vector:
        intent = IntentType.structured
        logger.info("Intent corrected after execution: hybrid -> structured (only structured context detected)")
    elif intent == IntentType.hybrid and has_structured and has_vector:
        if _is_pure_structured_query(unified_query):
            intent = IntentType.structured
            logger.info("Intent corrected after execution: hybrid -> structured by pure_structured_guard")
    elif intent == IntentType.hybrid and not has_structured and has_vector:
        intent = IntentType.vector
        logger.info("Intent corrected after execution: hybrid -> vector (only vector context detected)")

    summary_history = history
    if cache_service.is_schedule_sensitive_query(unified_query):
        summary_history = []
        logger.info(
            "Schedule-sensitive summarize uses empty history: session_id={}",
            session_id,
        )

    if wants_json_output:
        # 避免长耗时总结阶段占用数据库连接
        try:
            await db.rollback()
        except Exception:
            logger.exception("Request session rollback before json summarize failed")

        try:
            final_ans = await intent_service.summarize_answer(
                unified_query,
                context,
                history=summary_history,
            )
        except Exception as exc:
            logger.exception("JSON summarize failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"回答生成失败: {exc}",
            )

        elapsed = int((time.time() - start_ms) * 1000)

        # 获取推荐问题（如果启用了）
        suggested_questions = []
        if suggest_task is not None:
            try:
                suggested_questions = await suggest_task
                logger.info("JSON suggested questions ready: count={}", len(suggested_questions))
            except Exception:
                logger.exception("Failed to get suggested questions for JSON output")

        sensitive = cache_service.is_sensitive_query(unified_query)
        cache_payload = {"answer": final_ans}
        if suggested_questions:
            cache_payload["suggested_questions"] = suggested_questions
        await cache_service.set_cached_response(
            redis,
            did,
            unified_query,
            cache_payload,
            sensitive=sensitive,
        )
        logger.info("JSON response cached: sensitive={}", sensitive)

        async with AsyncSessionLocal() as json_db:
            await chat_log_service.log_message(
                json_db,
                student_id=student_id,
                sender=SenderEnum.agent,
                message_content=final_ans,
                system_action=SystemActionEnum.none,
                response_time_ms=elapsed,
                is_dangerous=False,
            )
        logger.info("JSON agent response persisted")

        try:
            await _append_session_history(
                redis,
                did=did,
                session_id=session_id,
                sender=SenderEnum.agent,
                content=final_ans,
            )
        except Exception:
            pass

        return QueryResponse(
            answer=final_ans,
            session_id=session_id,
            response_time_ms=elapsed,
            cached=False,
            suggested_questions=suggested_questions,
        )

    # ------------------------------------------------------------------
    # 7. 准备流式输出生成器
    # ------------------------------------------------------------------
    # 结束当前请求会话中的事务，尽早归还连接到连接池。
    # StreamingResponse 生命周期较长，避免在流式期间持有连接。
    try:
        await db.rollback()
    except Exception:
        logger.exception("Request session rollback before streaming failed")

    async def sse_generator():
        try:
            full_answer_list = []
            logger.info("SSE generation started")
            
            # 获取同步生成器
            def _get_gen():
                return intent_service.summarize_answer_stream(
                    unified_query, context, history=summary_history
                )
                
            token_gen = await asyncio.to_thread(_get_gen)
            
            chunk_count = 0
            while True:
                def _get_next():
                    try:
                        return next(token_gen)
                    except StopIteration:
                        return None
                chunk = await asyncio.to_thread(_get_next)
                if chunk is None:
                    break
                
                full_answer_list.append(chunk)
                chunk_count += 1
                if chunk_count % 20 == 0:
                    logger.debug("SSE stream progress: chunks={}", chunk_count)
                payload = json.dumps({"chunk": chunk, "done": False}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
                
            final_ans = "".join(full_answer_list)
            if not final_ans.strip():
                raise RuntimeError("Empty stream answer")
            elapsed = int((time.time() - start_ms) * 1000)
            logger.info("SSE generation completed: chunks={}, answer_len={}, elapsed_ms={}", chunk_count, len(final_ans), elapsed)

            # 获取推荐问题（如果启用了）
            suggested_questions = []
            if suggest_task is not None:
                try:
                    suggested_questions = await suggest_task
                    logger.info("Suggested questions ready: count={}", len(suggested_questions))
                except Exception:
                    logger.exception("Failed to get suggested questions")

            # 发送最后的数据包，包含完全的响应元数据段以及通知结束
            final_payload_obj = {
                "chunk": "",
                "response_time_ms": elapsed,
                "cached": False,
                "done": True,
            }
            if suggested_questions:
                final_payload_obj["suggested_questions"] = suggested_questions
            final_payload = json.dumps(final_payload_obj, ensure_ascii=False)
            yield f"data: {final_payload}\n\n"
            
            # Streaming 结束后，在此保存缓存和聊天日志
            sensitive = cache_service.is_sensitive_query(unified_query)
            await cache_service.set_cached_response(
                redis, did, unified_query,
                {"answer": final_ans},
                sensitive=sensitive,
            )
            logger.info("Response cached: sensitive={}", sensitive)

            # 使用独立短生命周期会话写入最终回答，避免复用长连接请求会话。
            async with AsyncSessionLocal() as stream_db:
                await chat_log_service.log_message(
                    stream_db,
                    student_id=student_id,
                    sender=SenderEnum.agent,
                    message_content=final_ans,
                    system_action=SystemActionEnum.none,
                    response_time_ms=elapsed,
                    is_dangerous=False,
                )
            logger.info("Agent response persisted")
            try:
                await _append_session_history(
                    redis,
                    did=did,
                    session_id=session_id,
                    sender=SenderEnum.agent,
                    content=final_ans,
                )
            except Exception:
                pass
            
        except Exception as exc:
            logger.exception("SSE generator failed")
            public_error = _to_public_stream_error(exc)
            yield f"data: {json.dumps({'error': public_error, 'done': True}, ensure_ascii=False)}\n\n"

    return _sse_response(sse_generator())


@router.delete(
    "/sessions",
    summary="清除当前学生的所有会话缓存与历史",
)
async def clear_cache_endpoint(
    student_id: str = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    清除当前学生的所有 Redis 会话缓存与历史记录。
    
    删除两类数据：
        - chat_cache:*:{did}:*       → 查询响应缓存
        - chat:session_history:{did}:* → 会话隔离历史
    
    返回清除的键数量。
    """
    did = generate_did(student_id)
    deleted_keys_count = 0
    logger.info("Clear sessions start: student_id={}, did={}", student_id, did[:12])

    async def _delete_by_pattern(pattern: str) -> int:
        deleted = 0
        batch: list[str] = []
        async for key in redis.scan_iter(match=pattern, count=200):
            batch.append(key)
            if len(batch) >= 200:
                deleted += await redis.delete(*batch)
                batch.clear()
        if batch:
            deleted += await redis.delete(*batch)
        return deleted

    try:
        deleted_keys_count += await _delete_by_pattern(f"chat_cache:*:{did}:*")
    except Exception:
        logger.exception("Error clearing cache keys")

    try:
        deleted_keys_count += await _delete_by_pattern(f"chat:session_history:{did}:*")
    except Exception:
        logger.exception("Error clearing history keys")

    logger.info("Clear sessions completed: deleted_keys_count={}", deleted_keys_count)
    return {"message": "清除成功", "deleted_keys_count": deleted_keys_count}

