"""安全服务：检测用户消息中的危险内容。"""
from __future__ import annotations

import json
import re
import dashscope
from dashscope import Generation

from app.config import settings
from app.utils.logger import logger

dashscope.api_key = settings.ALI_API_KEY

# 危险意图关键词匹配模式
_DANGER_PATTERNS = re.compile(
    r"(自杀|轻生|想死|去死|活不下去|结束生命|了断|跳楼|割腕|上吊|服毒"
    r"|暴力|打人|杀人|杀了|伤害|报复|持刀|枪|炸弹|袭击|攻击他人)",
)

# 公共服务联系方式查询（应走知识库检索，不应触发危机干预）
_CONTACT_QUERY_PATTERNS = re.compile(
    r"(电话|号码|联系方式|热线|联系(方式)?|怎么联系|在哪里|地址|值班)",
    re.IGNORECASE,
)
_SERVICE_TARGET_PATTERNS = re.compile(
    r"(急诊|急诊室|校医院|医院|医务室|卫生所|门诊|心理健康中心|心理咨询中心|辅导员|保卫处|保安处|校警|报警)",
    re.IGNORECASE,
)

# 隐私违规：试图查询他人学号
# 匹配 "学号" 后跟任意非数字字符（0-20个），然后是连续5位以上的数字
# 使用 [^0-9] 而不是 \D，更加明确
_PRIVACY_PATTERNS = re.compile(r"(?:学号|工号|student\s*id)[^0-9]{0,20}(\d{5,})", re.IGNORECASE)


def _parse_dangerous_flag(content: str) -> bool | None:
    """从模型输出中提取 dangerous 布尔值，解析失败返回 None。"""
    text = (content or "").strip()
    if not text:
        return None

    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()

    try:
        data = json.loads(text)
        if isinstance(data, dict) and isinstance(data.get("dangerous"), bool):
            return data["dangerous"]
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None

    try:
        data = json.loads(match.group(0))
        if isinstance(data, dict) and isinstance(data.get("dangerous"), bool):
            return data["dangerous"]
    except Exception:
        return None

    return None


def _is_public_service_contact_query(text: str) -> bool:
    """判断是否为公共服务联系方式查询。"""
    normalized = (text or "").strip()
    if not normalized:
        return False

    # 若同时出现明显危险词，交由后续危机检测流程处理，不做放行。
    if _DANGER_PATTERNS.search(normalized):
        return False

    return bool(
        _CONTACT_QUERY_PATTERNS.search(normalized)
        and _SERVICE_TARGET_PATTERNS.search(normalized)
    )


async def is_dangerous(text: str) -> bool:
    """
    使用 LLM 进行感性判断，检查文本是否包含自杀、自残或暴力伤害他人的真实倾向。
    相比正则匹配，LLM 能更好地理解语境（如区分“我想杀了这个BUG”与真实暴力意图）。
    """
    if _is_public_service_contact_query(text):
        logger.info("Safety bypass: detected public service contact query")
        return False

    # 构造 Prompt
    prompt = (
        "你是一个校园心理安全与危机干预助手。请分析以下学生发送的消息，"
        "判断是否存在【自杀/自残风险】或【对他人实施暴力的风险】。\n\n"
        "请结合语境进行感性判断：\n"
        "- 如果是在查询公共服务信息（如急诊室电话、校医院地址、心理健康中心联系方式），请判定为安全。\n"
        "- 如果是开玩笑、比喻（如'这也太难了我想死'、'我要杀了这个bug'），请判定为安全。\n"
        "- 如果是真实的情绪宣泄、求救信号或威胁（如'活着没意思'、'想结束一切'、'我要报复他'），请判定为危险。\n\n"
        "消息内容：\n"
        f"\"{text}\"\n\n"
        "仅输出 JSON 格式结果：{\"dangerous\": true} 或 {\"dangerous\": false}"
    )

    import asyncio
    logger.info("Safety check start: text_len={}", len(text))

    def _call_safety():
        return Generation.call(
            model=settings.LLM_MODEL_SAFETY_CHECK,
            messages=[{"role": "user", "content": prompt}],
            result_format="message",
            temperature=0.0, # 降低随机性
        )

    try:
        response = await asyncio.to_thread(_call_safety)
        if response.status_code == 200:
            content = response.output.choices[0].message.content
            logger.debug("Safety LLM response: {}", content[:120])
            parsed = _parse_dangerous_flag(content)
            if parsed is not None:
                if parsed:
                    logger.warning("Safety check result: dangerous=True (LLM)")
                else:
                    logger.info("Safety check result: dangerous=False (LLM)")
                return parsed
            
            # 如果 LLM 回复格式不对，回退到正则（作为兜底）
            fallback = bool(_DANGER_PATTERNS.search(text))
            logger.warning("Safety LLM format unexpected, regex fallback={}", fallback)
            return fallback
    except Exception as exc:
        # LLM 调用失败时，降级使用正则匹配确保安全
        logger.warning(
            "Safety LLM call failed, fallback to regex: {}: {}",
            exc.__class__.__name__,
            str(exc)[:240],
        )

    fallback = bool(_DANGER_PATTERNS.search(text))
    logger.info("Safety regex fallback result: dangerous={}", fallback)
    return fallback


def is_privacy_violation(text: str, current_student_id: str) -> str | None:
    """检查文本是否试图查询非本人的学号信息。
    
    如果检测到违规，返回被查询的那个学号；否则返回 None。
    """
    matches = _PRIVACY_PATTERNS.findall(text)
    for other_id in matches:
        if other_id != current_student_id:
            logger.warning(
                "Privacy violation detected: requester={}, target={}",
                current_student_id,
                other_id,
            )
            return other_id
    logger.debug("Privacy check passed: requester={}", current_student_id)
    return None
