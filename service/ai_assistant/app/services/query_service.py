"""
查询执行服务模块

功能介绍：
-----------
本模块是 AI 校园助手的查询执行核心，负责根据意图类型执行不同的查询策略：

查询类型：
- structured（结构化）: 使用 LLM 规划工具调用，执行 SQL 查询（成绩/课表/选课/学籍等）
- vector（向量检索）: 使用百炼知识库进行语义检索（规章制度/办事流程等）
- hybrid（混合）: 同时执行结构化查询和向量检索，结果融合
- smalltalk（闲聊）: 跳过检索，直接由 LLM 自然回复

工具列表：
- get_my_scores: 查询成绩
- get_my_schedule: 查询课表（含学期/周次推断）
- get_my_enrollment: 查询选课记录
- get_my_info: 查询个人学籍信息
- get_my_academic_overview: 查询班级/专业/学院
- list_departments_and_majors: 查询全校院系列表
- search_teachers: 查询教师通讯录

隐私保证：
- 所有查询严格限定为当前登录学生自己的数据
- 无法读取其他学生的记录
- 无法访问系统内部日志
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import date
import json
import re
import time
from typing import Any

from dashscope import Application
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import RunnableBranch, RunnableLambda
from langchain_core.tools import tool
from pydantic import ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.models import (
    Classroom,
    Class,
    Course,
    Department,
    Enrollment,
    Major,
    Schedule,
    ScheduleClassMap,
    ScheduleStatusEnum,
    Score,
    Student,
    Teacher,
    Term,
)
from app.schemas.query import IntentType
from app.services.langchain_service import ainvoke_chat_prompt
from app.utils.logger import logger


_NOT_FOUND_TEXT = "未在知识库中找到相关信息。"

# 学期ID正则：匹配 20XX + (01-12)
_TERM_ID_PATTERN = re.compile(r"\b(20\d{2}(?:0[1-9]|1[0-2]))\b")


def _format_term_id(term_id: str | None) -> str:
    """将学期ID（如 202501、202509）转换为可读学期名称。"""
    if not term_id or not isinstance(term_id, str) or len(term_id) != 6:
        return term_id or ""
    try:
        year = int(term_id[:4])
        month = int(term_id[4:6])
    except ValueError:
        return term_id
    if 1 <= month <= 8:
        return f"{year - 1}-{year}学年 第二学期"
    else:
        return f"{year}-{year + 1}学年 第一学期"


def _replace_term_ids_in_text(text: str) -> str:
    """将文本中的所有学期ID替换为可读学期名称。"""
    return _TERM_ID_PATTERN.sub(lambda m: _format_term_id(m.group(1)), text)


# 英文字段名 → 中文可读名称映射（用于结构化上下文美化）
_FIELD_NAME_MAP: dict[str, str] = {
    # 成绩相关
    "course_name": "课程名称",
    "term_id": "学期",
    "score": "成绩",
    "credit": "学分",
    "credit_earned": "是否获得学分",
    # 课表相关
    "course_id": "课程编号",
    "week_no": "周次",
    "day_of_week": "星期",
    "start_period": "开始节次",
    "end_period": "结束节次",
    "week_pattern": "周次模式",
    "room_id": "教室编号",
    "room_location": "教室位置",
    "room_type": "教室类型",
    "teacher_id": "教师编号",
    "teacher_name": "教师姓名",
    "teacher_title": "教师职称",
    "department_name": "学院名称",
    # 个人信息相关
    "student_id": "学号",
    "name": "姓名",
    "gender": "性别",
    "phone": "电话",
    "email": "邮箱",
    "office": "办公室",
    "department_name": "学院",
    "major_name": "专业",
    "class_name": "班级",
    "enrollment_year": "入学年份",
    # 教师通讯录
    "teacher_name": "教师姓名",
    "department_name": "学院",
    # 通用容器
    "rows": "记录列表",
    "row": "记录",
    "entries": "课表条目",
    "keyword": "查询关键词",
    "tool": "查询工具",
    "result": "查询结果",
    "error": "错误信息",
    # 课表元数据
    "term_source": "学期来源",
    "term_start_date": "学期开始日期",
    "term_end_date": "学期结束日期",
    "computed_week_info": "计算周次信息",
    "entries_all_weeks_count": "全周条目数",
    "entries_scope": "条目范围",
    "target_week_no": "目标周次",
    "target_week_entries_count": "目标周条目数",
    "target_week_day_counts": "目标周日次统计",
    "schedule_status": "课程状态",
    "status": "学籍状态",
}


# 枚举值 → 中文可读状态（在数据层转换，避免 LLM 暴露英文内部值）
_STATUS_VALUE_MAP: dict[str, str] = {
    "active": "正常",
    "suspended": "学籍暂停",
    "graduated": "已毕业",
    "cancelled": "已停课",
}


def _translate_field_names(obj: Any) -> Any:
    """递归遍历对象，将英文字段名替换为中文，转换学期ID和布尔值。"""
    if isinstance(obj, dict):
        new_obj: dict[str, Any] = {}
        for k, v in obj.items():
            new_k = _FIELD_NAME_MAP.get(k, k)
            new_obj[new_k] = _translate_field_names(v)
        return new_obj
    elif isinstance(obj, list):
        return [_translate_field_names(item) for item in obj]
    elif isinstance(obj, bool):
        return "是" if obj else "否"
    elif isinstance(obj, str):
        return _replace_term_ids_in_text(obj)
    return obj


_QUERY_DECOMPOSE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "你是一个查询优化助手。将用户问题拆解为 1-3 个用于知识库检索的核心关键词或短语。"
            "每行输出一个短语，不要输出序号或解释。",
        ),
        ("user", "{query}"),
    ]
)

_HYBRID_RERANK_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "你是校园知识库检索重排器。你会收到来自两个来源的候选内容："
            "retriever 与 app。请执行去重、筛选与重排，只保留和用户问题最相关、最有信息量的内容。"
            "输出纯文本，不要解释过程，不要加标题。",
        ),
        (
            "user",
            "用户问题:\n{query}\n\n"
            "Retriever候选:\n{retriever_text}\n\n"
            "App候选:\n{app_text}",
        ),
    ]
)

_STRUCTURED_TOOL_PLAN_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "你是校园智能助手的结构化查询工具规划器。"
            "你只能从给定工具清单中选择，并返回 JSON。"
            "\n严格要求："
            "\n1. 仅输出 JSON，不要解释。"
            "\n2. JSON 必须包含键 tool_calls。"
            "\n3. tool_calls 是数组，元素对象包含 name 和 args 两个键。"
            "\n4. 若无需结构化查询，输出一个空的 tool_calls 数组。"
            "\n5. 不得编造工具名，不得输出 SQL。"
            "\n6. term_id 如存在需使用 6 位数字，例如 202509。"
            "\n7. 如果用户的一个问题包含多个查询意图（例如同时问'专业班级'和'课表'），"
            "请在 tool_calls 中列出所有需要的工具，不要遗漏。"
            "\n可用工具："
            "\n- get_my_scores(term_id?): 查询学生成绩"
            "\n- get_my_schedule(term_id?): 查询学生课表（含学期、周次信息）"
            "\n- get_my_enrollment(term_id?): 查询学生选课记录"
            "\n- get_my_info(): 查询学生个人学籍及联系信息"
            "\n- get_my_academic_overview(): 查询学生班级/专业/学院信息"
            "\n- list_departments_and_majors(): 查询全校学院及专业目录"
            "\n- search_teachers(keyword?): 查询教师通讯录",
        ),
        (
            "user",
            "用户问题：{query}\n"
            "分类意图：{intent}\n"
            "显式学期ID（如有）：{explicit_term_id}",
        ),
    ]
)


class BailianLangChainRetriever(BaseRetriever):
    """LangChain retriever wrapper for existing Bailian KnowledgeRetriever."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    backend: Any = Field(...)

    def _get_relevant_documents(self, query: str) -> list[Document]:
        raw = self.backend.search(query)
        if not raw or raw == _NOT_FOUND_TEXT:
            return []
        return [
            Document(page_content=line.strip(), metadata={"source": "bailian", "query": query})
            for line in raw.split("\n\n")
            if line.strip()
        ]

    async def _aget_relevant_documents(self, query: str) -> list[Document]:
        raw = await asyncio.to_thread(self.backend.search, query)
        if not raw or raw == _NOT_FOUND_TEXT:
            return []
        return [
            Document(page_content=line.strip(), metadata={"source": "bailian", "query": query})
            for line in raw.split("\n\n")
            if line.strip()
        ]


def _log_route_metrics(route: str, fragment_count: int, start_ts: float) -> None:
    """Emit structured metrics for vector route tuning."""
    latency_ms = int((time.perf_counter() - start_ts) * 1000)
    logger.info(
        "vector_search route=%s fragment_count=%d latency_ms=%d",
        route,
        fragment_count,
        latency_ms,
    )


def _has_retriever_config() -> bool:
    return bool(
        settings.BAILIAN_INDEX_ID
        and settings.BAILIAN_WORKSPACE_ID
        and settings.ALIBABA_CLOUD_ACCESS_KEY_ID
        and settings.ALIBABA_CLOUD_ACCESS_KEY_SECRET
    )


def _has_app_config() -> bool:
    return bool(settings.BAILIAN_APP_ID and settings.ALI_API_KEY)


_SCHEDULE_KEYWORDS = (
    "课程表",
    "课表",
    "上课",
    "有课",
    "什么课",
    "有啥课",
    "课程安排",
    "排课",
    "节",
    "周",
    "本周",
    "上周",
    "下周",
    "星期",
    "周几",
    "本学期",
    "上学期",
    "下学期",
    "schedule",
    "我的课",
)
_SCORE_KEYWORDS = ("成绩", "分数", "绩点", "gpa", "score", "学分")
_ENROLLMENT_KEYWORDS = ("选课", "报名", "退课", "enrollment")
_INFO_KEYWORDS = ("我的信息", "个人信息", "学籍", "profile")
_ACADEMIC_KEYWORDS = ("班级", "所属", "专业", "学院", "院系", "major", "department", "class")
_TEACHER_KEYWORDS = ("教师", "老师", "teacher", "导师", "辅导员", "办公", "联系方式")
_DIRECTORY_KEYWORDS = ("学院目录", "专业目录", "有哪些学院", "有哪些专业", "院系列表", "专业列表")

_CONTACT_LOOKUP_KEYWORDS = (
    "联系方式",
    "联系电话",
    "电话",
    "手机号",
    "手机号码",
    "邮箱",
    "email",
    "mail",
    "contact",
    "phone",
)

_NON_PERSON_CONTACT_TARGETS = (
    "学校",
    "学院",
    "大学",
    "医院",
    "急诊",
    "急诊室",
    "医务室",
    "卫生所",
    "中心",
    "保卫",
    "图书馆",
    "宿舍",
    "食堂",
    "教务",
)

WEEKDAY_NAMES = {
    1: "周一",
    2: "周二",
    3: "周三",
    4: "周四",
    5: "周五",
    6: "周六",
    7: "周日",
}

# 节次 → 时间段映射（按学校实际作息）
_PERIOD_TIME_MAP: dict[int, tuple[str, str]] = {
    1: ("08:10", "09:40"),
    2: ("08:10", "09:40"),
    3: ("10:00", "11:40"),
    4: ("10:00", "11:40"),
    5: ("14:00", "15:40"),
    6: ("14:00", "15:40"),
    7: ("16:00", "17:30"),
    8: ("16:00", "17:30"),
    9: ("18:00", "19:00"),
    10: ("18:00", "19:00"),
    11: ("20:00", "21:40"),
    12: ("20:00", "21:40"),
}


def _format_period_time(start_period: int, end_period: int) -> str:
    """根据起止节次格式化时间段字符串。"""
    start_info = _PERIOD_TIME_MAP.get(start_period)
    end_info = _PERIOD_TIME_MAP.get(end_period)
    if not start_info or not end_info:
        return ""
    return f"{start_info[0]}-{end_info[1]}"



def _normalize_contact_target(value: str) -> str:
    """清洗姓名关键词，去掉职位后缀和空白。"""
    normalized = (value or "").strip()
    normalized = re.sub(r"的$", "", normalized)
    normalized = re.sub(r"(老师|同学|教授|讲师|导师)$", "", normalized)
    normalized = re.sub(r"的$", "", normalized)
    return normalized.strip()


def _extract_contact_target_name(query: str) -> str | None:
    """从“某某联系方式/电话”类问题中提取人名关键词。"""
    text = (query or "").strip()
    if not text:
        return None

    lowered = text.lower()
    if not any(kw in lowered for kw in _CONTACT_LOOKUP_KEYWORDS):
        return None

    patterns = (
        r"(?:请问|问一下|我想问(?:一下)?|麻烦问(?:一下)?|帮我查(?:一下)?|帮我问(?:一下)?)([\u4e00-\u9fa5]{2,4})(?:老师|同学|教授|讲师|导师)?(?:的)?(?:联系电话|联系方式|电话|手机号|手机号码|邮箱)",
        r"([\u4e00-\u9fa5]{2,4})(?:老师|教授|讲师|导师)(?:的)?(?:联系电话|联系方式|电话|手机号|手机号码|邮箱)",
        r"([\u4e00-\u9fa5]{2,4})(?:同学)(?:的)?(?:联系电话|联系方式|电话|手机号|手机号码|邮箱)",
        r"([\u4e00-\u9fa5]{2,4})(?:的)?(?:联系电话|联系方式|电话|手机号|手机号码|邮箱)",
    )

    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        candidate = _normalize_contact_target(match.group(1))
        if not candidate:
            continue
        if len(candidate) < 2 or len(candidate) > 4:
            continue
        if any(token in candidate for token in _NON_PERSON_CONTACT_TARGETS):
            continue
        return candidate

    return None


# ---------------------------------------------------------------------------
# 学期工具
# ---------------------------------------------------------------------------

def _guess_term_id(reference_date: date) -> str:
    """基于年份和月份推测学期ID (01=春季, 02=秋季)。"""

    semester_code = "01" if reference_date.month <= 6 else "02"
    return f"{reference_date.year}{semester_code}"


async def resolve_term_id(
    db: AsyncSession, reference_date: date | None = None
) -> dict:
    """根据参考日期解析最合适的学期信息。"""

    reference_date = reference_date or date.today()

    def _meta(term: Term | None, source: str, fallback_id: str | None = None) -> dict:
        return {
            "term_id": term.term_id if term else fallback_id,
            "start_date": getattr(term, "start_date", None),
            "end_date": getattr(term, "end_date", None),
            "source": source,
        }


    current_q = (
        select(Term)
        .where(Term.start_date <= reference_date, Term.end_date >= reference_date)
        .order_by(Term.start_date.desc())
        .limit(1)
    )
    term = (await db.execute(current_q)).scalar_one_or_none()
    if term:
        return _meta(term, "current")

    upcoming_q = (
        select(Term)
        .where(Term.start_date > reference_date)
        .order_by(Term.start_date.asc())
        .limit(1)
    )
    term = (await db.execute(upcoming_q)).scalar_one_or_none()
    if term:
        return _meta(term, "upcoming")

    previous_q = (
        select(Term)
        .where(Term.end_date < reference_date)
        .order_by(Term.end_date.desc())
        .limit(1)
    )
    term = (await db.execute(previous_q)).scalar_one_or_none()
    if term:
        return _meta(term, "previous")

    guessed = _guess_term_id(reference_date)
    return _meta(None, "guess", guessed)


def _extract_week_numbers(entries: list[dict[str, Any]]) -> list[int]:
    weeks: set[int] = set()
    for entry in entries:
        raw = entry.get("week_no")
        if isinstance(raw, int):
            weeks.add(raw)
            continue
        if isinstance(raw, str) and raw.isdigit():
            weeks.add(int(raw))
    return sorted(weeks)


def _build_computed_week_info(
    term_start_date: date | None,
    term_end_date: date | None,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    today = date.today()
    weeks = _extract_week_numbers(entries)
    week_min = weeks[0] if weeks else None
    week_max = weeks[-1] if weeks else None

    info: dict[str, Any] = {
        "today": today.isoformat(),
        "term_start_date": term_start_date.isoformat() if isinstance(term_start_date, date) else None,
        "term_end_date": term_end_date.isoformat() if isinstance(term_end_date, date) else None,
        "week_range_min": week_min,
        "week_range_max": week_max,
        "current_week_no": None,
        "next_week_no": None,
        "status": "no_term_boundary",
    }

    if not isinstance(term_start_date, date) or not isinstance(term_end_date, date):
        return info

    if today < term_start_date:
        info["status"] = "before_term"
        info["current_week_no"] = 0
        info["next_week_no"] = 1
        return info

    raw_current_week = ((today - term_start_date).days // 7) + 1
    info["current_week_no"] = max(1, raw_current_week)
    info["next_week_no"] = info["current_week_no"] + 1
    info["status"] = "in_term" if today <= term_end_date else "after_term"

    return info


_EXPLICIT_WEEK_PATTERN = re.compile(r"第\s*(\d{1,2})\s*周")


def _as_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _extract_explicit_week_no(query: str) -> int | None:
    match = _EXPLICIT_WEEK_PATTERN.search(query or "")
    if not match:
        return None
    week_no = _as_int(match.group(1))
    if week_no is None:
        return None
    return week_no if 1 <= week_no <= 30 else None


def _resolve_target_week_no(query: str, week_info: dict[str, Any] | None) -> int | None:
    normalized = (query or "").replace(" ", "")

    explicit_week_no = _extract_explicit_week_no(normalized)
    if explicit_week_no is not None:
        return explicit_week_no

    if not isinstance(week_info, dict):
        return None

    current_week_no = _as_int(week_info.get("current_week_no"))
    next_week_no = _as_int(week_info.get("next_week_no"))

    if any(word in normalized for word in ("下周", "下一周", "下礼拜", "下星期")):
        return next_week_no

    if any(word in normalized for word in ("这周", "本周", "这一周", "这礼拜", "这星期")):
        return current_week_no

    if any(word in normalized for word in ("上周", "上一周", "上礼拜", "上星期")):
        if current_week_no is None:
            return None
        return max(1, current_week_no - 1)

    return None


def _resolve_target_weekday(query: str) -> int | None:
    """从查询中解析目标星期几（1=周一, 7=周日）。"""
    normalized = (query or "").replace(" ", "")
    weekday_patterns: dict[int, tuple[str, ...]] = {
        1: ("周一", "星期一", "礼拜一", "周1", "星期1"),
        2: ("周二", "星期二", "礼拜二", "周2", "星期2"),
        3: ("周三", "星期三", "礼拜三", "周3", "星期3"),
        4: ("周四", "星期四", "礼拜四", "周4", "星期4"),
        5: ("周五", "星期五", "礼拜五", "周5", "星期5"),
        6: ("周六", "星期六", "礼拜六", "周6", "星期6"),
        7: ("周日", "星期天", "礼拜天", "星期日", "周7", "星期7", "周天"),
    }
    for day_num, keywords in weekday_patterns.items():
        if any(kw in normalized for kw in keywords):
            return day_num
    return None


def _compute_date_for_weekday_query(query: str) -> date | None:
    """解析查询中的相对星期几，计算对应的实际日期。

    支持：下周四、下周一、本周四 等语义。
    """
    from datetime import timedelta

    target_weekday = _resolve_target_weekday(query)
    if target_weekday is None:
        return None

    today = date.today()
    target_python_weekday = target_weekday - 1  # Monday=0

    normalized = (query or "").replace(" ", "")
    if "下周" in normalized or "下星期" in normalized or "下礼拜" in normalized:
        # 明确指"下周"：下周一开始算
        days_to_next_monday = (7 - today.weekday()) % 7
        if days_to_next_monday == 0:
            days_to_next_monday = 7
        next_monday = today + timedelta(days=days_to_next_monday)
        return next_monday + timedelta(days=target_python_weekday)

    if "本周" in normalized or "这星期" in normalized or "这礼拜" in normalized or "这周" in normalized:
        # 本周：从本周一开始算
        this_monday = today + timedelta(days=-today.weekday())
        return this_monday + timedelta(days=target_python_weekday)

    # 未明确"本周/下周"，但包含星期几（如"周四的课表"），按习惯推断为"下N个周四"
    # 这里保守返回 None，避免歧义；由 caller 决定是否 fallback
    return None


def _build_target_week_day_counts(entries: list[dict[str, Any]], target_week_no: int) -> dict[int, int]:
    counts = {day: 0 for day in range(1, 8)}
    for entry in entries:
        week_no = _as_int(entry.get("week_no"))
        day_of_week = _as_int(entry.get("day_of_week"))
        if week_no != target_week_no or day_of_week not in counts:
            continue
        counts[day_of_week] += 1
    return counts


def _compact_schedule_result_for_week_query(result: dict[str, Any], query: str) -> dict[str, Any]:
    entries = result.get("entries")
    if not isinstance(entries, list):
        return result

    target_week_no = _resolve_target_week_no(query, result.get("computed_week_info"))
    if target_week_no is None:
        return result

    target_entries = [
        entry
        for entry in entries
        if _as_int(entry.get("week_no")) == target_week_no
    ]

    compacted = dict(result)
    compacted["entries_all_weeks_count"] = len(entries)
    compacted["entries_scope"] = "target_week_only"
    compacted["target_week_no"] = target_week_no
    compacted["target_week_entries_count"] = len(target_entries)
    compacted["target_week_day_counts"] = _build_target_week_day_counts(entries, target_week_no)
    # 若查询包含相对星期几（如下周四），计算出实际日期供 LLM 参考
    target_date = _compute_date_for_weekday_query(query)
    if target_date:
        compacted["target_date"] = target_date.isoformat()
    compacted["entries"] = target_entries
    return compacted


# ---------------------------------------------------------------------------
# 结构化（SQL）查询助手
# ---------------------------------------------------------------------------
"""返回学生的成绩，可选按学期过滤。"""
async def get_my_scores(db: AsyncSession, student_id: str, term_id: str | None = None) -> list[dict]:
    q = (
        select(Score, Course, Term)
        .join(Course, Score.course_id == Course.course_id)
        .join(Term, Score.term_id == Term.term_id)
        .where(Score.student_id == student_id)  # 隐私约束
    )
    if term_id:
        q = q.where(Score.term_id == term_id)
    result = await db.execute(q)
    rows = []
    for score, course, term in result.all():
        rows.append({
            "course_name": course.course_name,
            "term_id": term.term_id,
            "score": score.score,
            "credit": course.credit,
            "credit_earned": bool(score.credit_earned),
        })
    return rows


async def get_my_schedule(
    db: AsyncSession,
    student_id: str,
    term_id: str | None = None,
) -> dict:
    """返回课程表，并在未指定时自动推断当前学期。"""

    if term_id:
        manual_term = (await db.execute(select(Term).where(Term.term_id == term_id))).scalar_one_or_none()
        term_meta = {
            "term_id": term_id,
            "start_date": getattr(manual_term, "start_date", None),
            "end_date": getattr(manual_term, "end_date", None),
            "source": "manual",
        }
    else:
        term_meta = await resolve_term_id(db)

    resolved_term_id = term_meta["term_id"]

    # 先解析学生所属班级，再通过 schedule_class_map 查询班级课表。
    student_class_id = (
        await db.execute(
            select(Student.class_id).where(Student.student_id == student_id).limit(1)
        )
    ).scalar_one_or_none()

    if student_class_id is None:
        computed_week_info = _build_computed_week_info(
            term_meta.get("start_date"),
            term_meta.get("end_date"),
            [],
        )
        return {
            "term_id": resolved_term_id,
            "term_source": term_meta["source"],
            "term_start_date": term_meta.get("start_date"),
            "term_end_date": term_meta.get("end_date"),
            "computed_week_info": computed_week_info,
            "entries": [],
        }

    base_query = (
        select(Schedule, Course, Teacher, Classroom, Department)
        .join(ScheduleClassMap, ScheduleClassMap.schedule_id == Schedule.schedule_id)
        .join(Course, Schedule.course_id == Course.course_id)
        .join(Teacher, Schedule.teacher_id == Teacher.teacher_id)
        .join(Classroom, Schedule.room_id == Classroom.room_id)
        .join(Department, Teacher.dept_id == Department.dept_id)
        .where(ScheduleClassMap.class_id == student_class_id)
        .order_by(Schedule.day_of_week, Schedule.start_period)
    )

    query = base_query
    if resolved_term_id:
        query = query.where(Schedule.term_id == resolved_term_id)

    result = await db.execute(query)

    def _collect(rows):
        entries = []
        for sched, course, teacher, classroom, dept in rows:
            entries.append({
                "course_id": course.course_id,
                "course_name": course.course_name,
                "term_id": sched.term_id,
                "week_no": sched.week_no,
                "day_of_week": sched.day_of_week,
                "start_period": sched.start_period,
                "end_period": sched.end_period,
                "time_range": _format_period_time(sched.start_period, sched.end_period),
                "week_pattern": sched.week_pattern,
                "room_id": classroom.room_id,
                "room_location": classroom.location,
                "room_type": classroom.room_type.value,
                "teacher_id": teacher.teacher_id,
                "teacher_name": teacher.name,
                "teacher_title": teacher.title,
                "teacher_phone": teacher.phone,
                "teacher_email": teacher.email,
                "teacher_office_hours": teacher.office_hours,
                "teacher_office_room": teacher.office_room,
                "department_name": dept.name,
                "schedule_status": _STATUS_VALUE_MAP.get(sched.schedule_status.value, sched.schedule_status.value),
            })
        return entries

    rows = _collect(result.all())
    term_source = term_meta["source"]

    if not rows and term_id is None:
        fallback_rows = _collect((await db.execute(base_query)).all())
        if fallback_rows:
            rows = fallback_rows
            resolved_term_id = None
            term_source = "all_terms"

    computed_week_info = _build_computed_week_info(
        term_meta.get("start_date"),
        term_meta.get("end_date"),
        rows,
    )

    return {
        "term_id": resolved_term_id,
        "term_source": term_source,
        "term_start_date": term_meta.get("start_date"),
        "term_end_date": term_meta.get("end_date"),
        "computed_week_info": computed_week_info,
        "entries": rows,
    }


async def get_my_info(db: AsyncSession, student_id: str) -> dict | None:
    """返回学生的非敏感个人信息（含学院、专业、班级）。"""
    q = (
        select(Student, Class, Major, Department)
        .join(Class, Student.class_id == Class.class_id)
        .join(Major, Class.major_id == Major.major_id)
        .join(Department, Major.dept_id == Department.dept_id)
        .where(Student.student_id == student_id)
    )
    result = await db.execute(q)
    row = result.one_or_none()
    if not row:
        return None
    student, class_, major, dept = row

    # 解析 class.name 为专业和班级，例如 "软件工程2022-1班"
    class_name = class_.name or ""
    major_name = major.name or ""
    class_name_parsed = class_name
    # 尝试从 class.name 中提取末尾的 "年份-班号班" 格式
    match = re.search(r"(\d{4}-\d+班)$", class_name)
    if match:
        # 前面部分作为专业（应与 major.name 一致），后面作为班级
        class_name_parsed = match.group(1)

    return {
        "student_id": student.student_id,
        "name": student.name,
        "gender": student.gender,
        "enroll_year": student.enroll_year,
        "class_id": student.class_id,
        "phone": student.phone,
        "email": student.email,
        "status": _STATUS_VALUE_MAP.get(student.status.value, student.status.value) if student.status else None,
        "department_name": dept.name,
        "major_name": major_name,
        "class_name": class_name_parsed,
    }


async def get_my_enrollment(db: AsyncSession, student_id: str, term_id: str | None = None) -> list[dict]:
    """返回学生的选课记录。"""
    q = (
        select(Enrollment, Course, Term)
        .join(Course, Enrollment.course_id == Course.course_id)
        .join(Term, Enrollment.term_id == Term.term_id)
        .where(Enrollment.student_id == student_id)  # 隐私约束
    )
    if term_id:
        q = q.where(Enrollment.term_id == term_id)
    result = await db.execute(q)
    return [
        {
            "course_id": enr.course_id,
            "course_name": course.course_name,
            "term_id": term.term_id,
            "credit": course.credit,
            "course_type": course.course_type.value,
        }
        for enr, course, term in result.all()
    ]


async def get_my_academic_overview(db: AsyncSession, student_id: str) -> dict | None:
    """返回学生所在班级/专业/学院信息。"""

    q = (
        select(Student, Class, Major, Department)
        .join(Class, Student.class_id == Class.class_id)
        .join(Major, Class.major_id == Major.major_id)
        .join(Department, Major.dept_id == Department.dept_id)
        .where(Student.student_id == student_id)
    )
    result = await db.execute(q)
    row = result.one_or_none()
    if not row:
        return None
    student, class_, major, dept = row
    return {
        "student_id": student.student_id,
        "class_id": class_.class_id,
        "class_name": class_.name,
        "major_id": major.major_id,
        "major_name": major.name,
        "department_id": dept.dept_id,
        "department_name": dept.name,
        "grade": class_.grade,
    }


async def list_departments_and_majors(db: AsyncSession) -> list[dict]:
    """列出所有学院及其下属专业。"""

    q = (
        select(Department, Major)
        .join(Major, Major.dept_id == Department.dept_id, isouter=True)
        .order_by(Department.name, Major.name)
    )
    result = await db.execute(q)

    grouped: dict[str, dict] = {}
    for dept, major in result.all():
        entry = grouped.setdefault(
            dept.dept_id,
            {"department_id": dept.dept_id, "department_name": dept.name, "majors": []},
        )
        if major:
            entry["majors"].append(
                {
                    "major_id": major.major_id,
                    "major_name": major.name,
                }
            )
    return list(grouped.values())


async def list_teacher_directory(
    db: AsyncSession,
    dept_id: str | None = None,
    name_keyword: str | None = None,
) -> list[dict]:
    """列出教师通讯录，可按学院/姓名筛选。"""

    q = (
        select(Teacher, Department)
        .join(Department, Teacher.dept_id == Department.dept_id)
        .order_by(Teacher.name)
    )
    if dept_id:
        q = q.where(Teacher.dept_id == dept_id)
    if name_keyword:
        like_pattern = f"%{name_keyword}%"
        q = q.where(Teacher.name.like(like_pattern))

    result = await db.execute(q)
    return [
        {
            "teacher_id": teacher.teacher_id,
            "teacher_name": teacher.name,
            "title": teacher.title,
            "department_id": dept.dept_id,
            "department_name": dept.name,
            "phone": teacher.phone,
            "email": teacher.email,
            "office_hours": teacher.office_hours,
            "office_room": teacher.office_room,
        }
        for teacher, dept in result.all()
    ]


def _format_schedule_preview(entries: list[dict]) -> str:
    if not entries:
        return ""

    grouped: dict[int, list[dict]] = defaultdict(list)
    for entry in entries:
        grouped[entry["day_of_week"]].append(entry)

    lines: list[str] = []
    for day in sorted(grouped.keys()):
        day_name = WEEKDAY_NAMES.get(day, f"周{day}")
        lines.append(f"{day_name}：")
        day_entries = sorted(grouped[day], key=lambda x: (x["week_no"], x["start_period"]))
        for e in day_entries:
            weeks = e["week_pattern"] or f"第{e['week_no']}周"
            contact_parts = [p for p in (e["teacher_phone"], e["teacher_email"]) if p]
            contact = f"（{' / '.join(contact_parts)}）" if contact_parts else ""
            office = f" 办公：{e['teacher_office_room']}" if e.get("teacher_office_room") else ""
            status_tag = "【已停课】" if e.get("schedule_status") == "cancelled" else ""
            lines.append(
                "  - {status}{course} | 周次:{weeks} | 节次:{start}-{end}({time}) | 地点:{room_loc}({room_id},{room_type}) | 教师:{teacher}{contact}{office}".format(
                    status=status_tag,
                    course=e["course_name"],
                    weeks=weeks,
                    start=e["start_period"],
                    end=e["end_period"],
                    time=e.get("time_range", ""),
                    room_loc=e["room_location"],
                    room_id=e["room_id"],
                    room_type=e["room_type"],
                    teacher=e["teacher_name"],
                    contact=contact,
                    office=office,
                )
            )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 向量（知识库）查询助手
# ---------------------------------------------------------------------------


def _dedupe_texts(texts: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for text in texts:
        item = text.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        merged.append(item)
    return merged


async def _build_query_fragments(query: str) -> list[str]:
    async def _invoke_decomposer(text: str) -> str:
        return await ainvoke_chat_prompt(
            _QUERY_DECOMPOSE_PROMPT,
            {"query": text},
            model=settings.LLM_MODEL_VECTOR_DECOMPOSE,
            temperature=0.0,
            max_tokens=128,
        )

    chain = RunnableLambda(_invoke_decomposer) | StrOutputParser()

    try:
        raw = await chain.ainvoke(query)
        fragments = [
            line.strip("-* ").strip()
            for line in raw.split("\n")
            if line.strip()
        ]
        fragments = _dedupe_texts(fragments)
        return fragments[:3] if fragments else [query]
    except Exception:
        return [query]


def _vector_route(_: str) -> str:
    """Decide vector route among retriever/app/hybrid-rerank."""
    has_retriever = _has_retriever_config()
    has_app = _has_app_config()

    if has_retriever and has_app:
        logger.debug("Vector route selected: hybrid-rerank")
        return "hybrid-rerank"
    if has_retriever:
        logger.debug("Vector route selected: retriever")
        return "retriever"
    logger.debug("Vector route selected: app")
    return "app"


async def _search_with_retriever(query: str, *, emit_metrics: bool = True) -> str:
    start_ts = time.perf_counter()
    logger.info("Retriever search start: query_len={}", len(query))
    from app.services.retriever_service import get_retriever

    retriever = BailianLangChainRetriever(backend=get_retriever())
    fragments = await _build_query_fragments(query)

    tasks = [retriever.aget_relevant_documents(fragment) for fragment in fragments]
    results = await asyncio.gather(*tasks)

    all_texts: list[str] = []
    for docs in results:
        for doc in docs:
            all_texts.append(doc.page_content)

    merged = _dedupe_texts(all_texts)
    if emit_metrics:
        _log_route_metrics("retriever", len(fragments), start_ts)
    logger.info("Retriever search end: fragments={}, hits={}", len(fragments), len(merged))
    return "\n\n---\n\n".join(merged) if merged else _NOT_FOUND_TEXT


async def _search_with_app(query: str, *, emit_metrics: bool = True) -> str:
    start_ts = time.perf_counter()
    logger.info("Bailian app search start: query_len={}", len(query))

    def _call_bailian_app() -> Any:
        return Application.call(
            app_id=settings.BAILIAN_APP_ID,
            prompt=query,
            api_key=settings.ALI_API_KEY,
        )

    response = await asyncio.to_thread(_call_bailian_app)
    if response.status_code != 200:
        logger.warning(
            "Bailian app search unavailable: status_code={}, message={}, fallback=not_found_text",
            response.status_code,
            response.message,
        )
        # 对外降级为“未命中”，避免 403/权限问题导致主流程报错中断。
        return _NOT_FOUND_TEXT
    if emit_metrics:
        _log_route_metrics("app", 1, start_ts)
    logger.info("Bailian app search end: text_len={}", len(response.output.text or ""))
    return response.output.text


async def _hybrid_rerank(query: str, retriever_text: str, app_text: str) -> str:
    logger.info(
        "Hybrid rerank start: retriever_len={}, app_len={}",
        len(retriever_text or ""),
        len(app_text or ""),
    )
    # 如果有一侧无结果，直接返回另一侧，避免无意义模型调用。
    if retriever_text == _NOT_FOUND_TEXT and app_text == _NOT_FOUND_TEXT:
        return _NOT_FOUND_TEXT
    if retriever_text == _NOT_FOUND_TEXT:
        return app_text
    if app_text == _NOT_FOUND_TEXT:
        return retriever_text

    reranked = await ainvoke_chat_prompt(
        _HYBRID_RERANK_PROMPT,
        {
            "query": query,
            "retriever_text": retriever_text,
            "app_text": app_text,
        },
        model=settings.LLM_MODEL_HYBRID_RERANK,
        temperature=0.0,
        max_tokens=2048,
    )

    result = reranked.strip()
    logger.info("Hybrid rerank end: result_len={}", len(result))
    return result if result else _NOT_FOUND_TEXT


async def _search_with_hybrid_rerank(query: str) -> str:
    start_ts = time.perf_counter()
    logger.info("Hybrid search start: query_len={}", len(query))
    fragments = await _build_query_fragments(query)

    retriever_task = asyncio.create_task(_search_with_retriever(query, emit_metrics=False))
    app_task = asyncio.create_task(_search_with_app(query, emit_metrics=False))
    retriever_text, app_text = await asyncio.gather(retriever_task, app_task)

    if app_text == _NOT_FOUND_TEXT and retriever_text != _NOT_FOUND_TEXT:
        logger.info("Hybrid search degraded: app unavailable/empty, using retriever result")
    elif app_text == _NOT_FOUND_TEXT and retriever_text == _NOT_FOUND_TEXT:
        logger.info("Hybrid search result empty: both app and retriever returned not_found")

    final_text = await _hybrid_rerank(query, retriever_text, app_text)
    _log_route_metrics("hybrid-rerank", len(fragments), start_ts)
    logger.info("Hybrid search end: final_len={}", len(final_text or ""))
    return final_text


async def vector_search(query: str) -> str:
    """LangChain Router + Retriever based vector search.

    - `retriever` 路由：Bailian Retrieve API（query decomposition + 并发检索）
    - `app` 路由：回退到百炼应用模式
    - `hybrid-rerank` 路由：并发获取 retriever/app，再由 LLM 重排融合
    """

    route_chain = RunnableLambda(_vector_route)

    # Note: we must await async functions inside the lambda if we want to run them asynchronously
    # Langchain's RunnableBranch/RunnableLambda with async functions requires careful handling.
    # The safest way in LangChain is to define standard async funcs first and pass them.
    
    async def run_retriever(x: dict) -> str:
        return await _search_with_retriever(x["query"])
        
    async def run_hybrid(x: dict) -> str:
        return await _search_with_hybrid_rerank(x["query"])
        
    async def run_app(x: dict) -> str:
        return await _search_with_app(x["query"])

    router = RunnableBranch(
        (lambda x: x["route"] == "retriever", run_retriever),
        (lambda x: x["route"] == "hybrid-rerank", run_hybrid),
        run_app,
    )

    logger.info("Vector search dispatcher start: query_len={}", len(query))
    chain = {"query": RunnableLambda(lambda x: x), "route": route_chain} | router
    result = await chain.ainvoke(query)
    logger.info("Vector search dispatcher end: result_len={}", len(result or ""))
    return result


# ---------------------------------------------------------------------------
# 高级调度器
# ---------------------------------------------------------------------------


def _detect_primary_structured_tool(query: str) -> str | None:
    """基于问题文本确定首选结构化工具，用于规划失败时兜底。"""
    query_lower = (query or "").lower()

    if _extract_contact_target_name(query):
        return "search_teachers"

    # 优先级说明：成绩/选课语义优先于课表语义。
    # 避免"上学期成绩"因包含"上学期"被误判为课表查询。
    if any(kw in query_lower for kw in _SCORE_KEYWORDS):
        return "get_my_scores"
    if any(kw in query_lower for kw in _ENROLLMENT_KEYWORDS):
        return "get_my_enrollment"
    if any(kw in query_lower for kw in _SCHEDULE_KEYWORDS):
        return "get_my_schedule"
    if any(kw in query_lower for kw in _TEACHER_KEYWORDS):
        return "search_teachers"
    if any(kw in query_lower for kw in _INFO_KEYWORDS):
        return "get_my_info"
    if any(kw in query_lower for kw in _DIRECTORY_KEYWORDS):
        return "list_departments_and_majors"
    if any(kw in query_lower for kw in _ACADEMIC_KEYWORDS):
        return "get_my_academic_overview"
    return None


_TOOL_PRIORITY = {
    "get_my_info": 0,
    "get_my_academic_overview": 1,
    "get_my_schedule": 2,
    "get_my_scores": 3,
    "get_my_enrollment": 4,
    "search_teachers": 5,
    "list_departments_and_majors": 6,
}


def _detect_all_structured_tools(query: str) -> list[str]:
    """检测查询中涉及的所有结构化工具，支持多意图联合查询。"""
    query_lower = (query or "").lower()
    if not query_lower:
        return []

    tools: set[str] = set()

    if _extract_contact_target_name(query):
        tools.add("search_teachers")

    if any(kw in query_lower for kw in _SCORE_KEYWORDS):
        tools.add("get_my_scores")
    if any(kw in query_lower for kw in _ENROLLMENT_KEYWORDS):
        tools.add("get_my_enrollment")
    if any(kw in query_lower for kw in _SCHEDULE_KEYWORDS):
        tools.add("get_my_schedule")
    if any(kw in query_lower for kw in _TEACHER_KEYWORDS):
        tools.add("search_teachers")
    if any(kw in query_lower for kw in _INFO_KEYWORDS):
        tools.add("get_my_info")
    if any(kw in query_lower for kw in _DIRECTORY_KEYWORDS):
        tools.add("list_departments_and_majors")
    if any(kw in query_lower for kw in _ACADEMIC_KEYWORDS):
        tools.add("get_my_academic_overview")

    return sorted(tools, key=lambda t: _TOOL_PRIORITY.get(t, 99))


def _contains_structured_topic(query: str) -> bool:
    """判断问题是否明显属于结构化查询主题。"""
    query_lower = (query or "").lower()
    if not query_lower:
        return False

    if _extract_contact_target_name(query):
        return True

    return (
        any(kw in query_lower for kw in _SCHEDULE_KEYWORDS)
        or any(kw in query_lower for kw in _SCORE_KEYWORDS)
        or any(kw in query_lower for kw in _ENROLLMENT_KEYWORDS)
        or any(kw in query_lower for kw in _INFO_KEYWORDS)
        or any(kw in query_lower for kw in _ACADEMIC_KEYWORDS)
        or any(kw in query_lower for kw in _TEACHER_KEYWORDS)
        or any(kw in query_lower for kw in _DIRECTORY_KEYWORDS)
    )


def _tool_args_with_term(tool_name: str, explicit_term_id: str | None) -> dict[str, Any]:
    """为支持学期参数的工具补齐显式学期。"""
    if (
        explicit_term_id
        and tool_name in {"get_my_scores", "get_my_schedule", "get_my_enrollment"}
    ):
        return {"term_id": explicit_term_id}
    return {}


def _fallback_tool_calls(query: str, explicit_term_id: str | None) -> list[dict[str, Any]]:
    """当 LLM 规划失败时，使用规则生成保底工具调用（支持多意图）。"""
    contact_target = _extract_contact_target_name(query)
    if contact_target:
        return [{"name": "search_teachers", "args": {"keyword": contact_target}}]

    tools = _detect_all_structured_tools(query)
    if not tools:
        return []
    return [
        {"name": tool_name, "args": _tool_args_with_term(tool_name, explicit_term_id)}
        for tool_name in tools
    ]


def _align_tool_calls_with_query(
    query: str,
    tool_calls: list[dict[str, Any]],
    explicit_term_id: str | None,
) -> list[dict[str, Any]]:
    """若规划与问题主题明显不一致，则强制纠偏；同时补充多意图查询缺失的工具。"""
    preferred_tool = _detect_primary_structured_tool(query)
    contact_target = _extract_contact_target_name(query)
    cleaned: list[dict[str, Any]] = []
    for call in tool_calls:
        if not isinstance(call, dict):
            continue
        name = str(call.get("name", "")).strip()
        args = call.get("args", {})
        if not isinstance(args, dict):
            args = {}
        if explicit_term_id and name in {"get_my_scores", "get_my_schedule", "get_my_enrollment"}:
            args = {**args, "term_id": explicit_term_id}
        if name == "search_teachers":
            raw_keyword = str(args.get("keyword", "")).strip()
            normalized_keyword = _normalize_contact_target(raw_keyword)
            if contact_target and not normalized_keyword:
                args = {**args, "keyword": contact_target}
            elif normalized_keyword and normalized_keyword != raw_keyword:
                args = {**args, "keyword": normalized_keyword}
        cleaned.append({"name": name, "args": args})

    if contact_target:
        search_calls = [call for call in cleaned if call.get("name") == "search_teachers"]
        other_calls = [call for call in cleaned if call.get("name") != "search_teachers"]
        if not search_calls:
            logger.warning(
                "Tool plan mismatch for contact query, force search_teachers: target={}",
                contact_target,
            )
            return [{"name": "search_teachers", "args": {"keyword": contact_target}}]
        # 保证教师检索优先执行。
        return [search_calls[0], *other_calls]

    # 多意图查询：检测查询需要的所有工具，补充 LLM 规划遗漏的
    required_tools = set(_detect_all_structured_tools(query))
    planned_tools = {call.get("name") for call in cleaned}
    missing_tools = required_tools - planned_tools
    if missing_tools:
        logger.info(
            "Supplementing missing tools from plan: missing={}, required={}",
            missing_tools,
            required_tools,
        )
        for tool_name in sorted(missing_tools, key=lambda t: _TOOL_PRIORITY.get(t, 99)):
            cleaned.append(
                {"name": tool_name, "args": _tool_args_with_term(tool_name, explicit_term_id)}
            )

    if not preferred_tool:
        return cleaned

    if any(call.get("name") == preferred_tool for call in cleaned):
        return cleaned

    logger.warning(
        "Tool plan mismatch with query topic, fallback to preferred tool: {}",
        preferred_tool,
    )
    return _fallback_tool_calls(query, explicit_term_id)


def _sanitize_term_id(term_id: str | None, explicit_term_id: str | None) -> str | None:
    """规范化学期ID：用户显式学期优先，其次才使用规划器学期。"""
    explicit_candidate = (explicit_term_id or "").strip()
    if re.fullmatch(r"20\d{4}", explicit_candidate):
        return explicit_candidate

    planned_candidate = (term_id or "").strip()
    if re.fullmatch(r"20\d{4}", planned_candidate):
        return planned_candidate

    return None


async def _term_exists(db: AsyncSession, term_id: str | None) -> bool:
    """检查学期ID是否存在于 term 表。"""
    if not term_id:
        return False
    q = select(Term.term_id).where(Term.term_id == term_id).limit(1)
    return (await db.execute(q)).scalar_one_or_none() is not None


async def _latest_term_id_for_scores(db: AsyncSession, student_id: str) -> str | None:
    """获取该学生在成绩表中的最近学期ID。"""
    q = (
        select(Score.term_id)
        .where(Score.student_id == student_id)
        .order_by(Score.term_id.desc())
        .limit(1)
    )
    return (await db.execute(q)).scalar_one_or_none()


async def _latest_term_id_for_enrollment(db: AsyncSession, student_id: str) -> str | None:
    """获取该学生在选课表中的最近学期ID。"""
    q = (
        select(Enrollment.term_id)
        .where(Enrollment.student_id == student_id)
        .order_by(Enrollment.term_id.desc())
        .limit(1)
    )
    return (await db.execute(q)).scalar_one_or_none()


async def _latest_term_id_for_schedule(db: AsyncSession, student_id: str) -> str | None:
    """获取该学生可匹配到课程表记录的最近学期ID。"""
    q = (
        select(Schedule.term_id)
        .join(ScheduleClassMap, ScheduleClassMap.schedule_id == Schedule.schedule_id)
        .join(Student, Student.class_id == ScheduleClassMap.class_id)
        .where(Student.student_id == student_id)
        .where(Schedule.schedule_status == ScheduleStatusEnum.active)
        .order_by(Schedule.term_id.desc())
        .limit(1)
    )
    return (await db.execute(q)).scalar_one_or_none()


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    """从 LLM 文本中提取首个 JSON 对象。"""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()

    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _json_default(value: Any) -> Any:
    """将不可直接 JSON 序列化的对象降级为字符串（主要处理 date）。"""
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "value"):
        return getattr(value, "value")
    return str(value)


def _build_structured_verdicts(executed_results: list[dict[str, Any]], query: str) -> str:
    """基于工具结果生成机器判定，约束总结阶段不要反向臆断。"""
    verdicts: list[str] = []
    contact_target = _extract_contact_target_name(query)
    teacher_search_executed = False

    for item in executed_results:
        if item.get("tool") != "search_teachers":
            continue

        teacher_search_executed = True
        result = item.get("result")
        if not isinstance(result, dict):
            continue

        rows = result.get("rows")
        if not isinstance(rows, list):
            continue

        matched_teacher_names = sorted(
            {
                str(row.get("teacher_name", "")).strip()
                for row in rows
                if isinstance(row, dict) and str(row.get("teacher_name", "")).strip()
            }
        )

        if contact_target:
            if matched_teacher_names:
                sample = "、".join(matched_teacher_names[:3])
                verdicts.append(
                    f"人员联系方式判定：在教师通讯录匹配到“{sample}”，可提供教师公开联系方式。"
                )
            else:
                verdicts.append(
                    f"人员联系方式判定：未在教师通讯录匹配到“{contact_target}”。"
                    "若用户询问同学/学生个人联系方式，必须明确拒绝并说明隐私保护，"
                    "建议通过班级群、课程群或辅导员转达。"
                )
        elif matched_teacher_names:
            verdicts.append(f"教师通讯录判定：已匹配教师记录 {len(matched_teacher_names)} 条。")

    if contact_target and not teacher_search_executed:
        verdicts.append(
            f"人员联系方式判定：这是对“{contact_target}”的联系方式查询。"
            "必须先检索教师通讯录；若未匹配教师，再明确拒绝同学联系方式查询。"
        )

    for item in executed_results:
        if item.get("tool") != "get_my_schedule":
            continue
        result = item.get("result")
        if not isinstance(result, dict):
            continue

        target_week_no = _resolve_target_week_no(query, result.get("computed_week_info"))
        entries = result.get("entries")
        target_date_raw = result.get("target_date")
        if target_date_raw:
            verdicts.append(
                f"目标日期判定：用户查询对应的具体日期为 {target_date_raw}。"
                "总结时必须严格使用该日期，禁止自行推算成其他日期。"
            )
        if (
            isinstance(entries, list)
            and result.get("entries_scope") == "target_week_only"
            and isinstance(target_week_no, int)
        ):
            verdicts.append(f"课表判定：已按目标周第{target_week_no}周收敛，共 {len(entries)} 条记录。")
        elif isinstance(entries, list) and entries:
            verdicts.append(f"课表判定：存在课程安排，共 {len(entries)} 条记录。")
        elif isinstance(entries, list):
            verdicts.append("课表判定：未查询到课程安排。")

        # 判定已停课的记录
        if isinstance(entries, list):
            cancelled_entries = [
                e for e in entries
                if isinstance(e, dict) and e.get("schedule_status") == "cancelled"
            ]
            if cancelled_entries:
                cancelled_names = sorted(
                    {
                        str(e.get("course_name", "")).strip()
                        for e in cancelled_entries
                        if str(e.get("course_name", "")).strip()
                    }
                )
                names_text = "、".join(cancelled_names)
                verdicts.append(
                    f"停课判定：以下课程已停课，共 {len(cancelled_entries)} 条：{names_text}。"
                    "这些课程必须明确告知用户‘已停课，无需上课’，严禁按正常课程输出时间地点。"
                )
            active_entries = [
                e for e in entries
                if isinstance(e, dict) and e.get("schedule_status") != "cancelled"
            ]
            if active_entries:
                verdicts.append(
                    f"正常课程判定：除停课外，共有 {len(active_entries)} 条正常课程安排。"
                )

        week_info = result.get("computed_week_info")
        if isinstance(week_info, dict):
            current_week_no = week_info.get("current_week_no")
            next_week_no = week_info.get("next_week_no")
            status = week_info.get("status")
            today = week_info.get("today")
            term_start = week_info.get("term_start_date")

            if isinstance(current_week_no, int) and isinstance(next_week_no, int):
                verdicts.append(
                    f"周次判定：今天={today}，依据学期起始日 {term_start} 计算，当前第{current_week_no}周，下周第{next_week_no}周。"
                )
            elif status == "before_term":
                verdicts.append("周次判定：当前学期尚未开始，当前周=0，下周=1。")

        day_counts = result.get("target_week_day_counts")
        if isinstance(day_counts, dict) and isinstance(target_week_no, int):
            normalized_day_counts: dict[int, int] = {}
            for day in range(1, 8):
                raw = day_counts.get(day)
                if raw is None:
                    raw = day_counts.get(str(day))
                normalized_day_counts[day] = _as_int(raw) or 0

            distribution = "，".join(
                f"{WEEKDAY_NAMES.get(day, f'周{day}')}={normalized_day_counts[day]}"
                for day in range(1, 8)
            )
            verdicts.append(f"目标周判定：第{target_week_no}周按天记录数：{distribution}。")

            no_class_days = [
                WEEKDAY_NAMES.get(day, f"周{day}")
                for day in range(1, 8)
                if normalized_day_counts[day] == 0
            ]
            if no_class_days:
                verdicts.append(
                    "目标周无课日："
                    + "、".join(no_class_days)
                    + "。这些日期必须回答“无课”，严禁补全课程。"
                )

    if not verdicts:
        return ""

    return "结构化判定：\n" + "\n".join(f"- {line}" for line in verdicts)


def _filter_teacher_directory(
    directory: list[dict[str, Any]],
    keyword: str | None,
) -> list[dict[str, Any]]:
    """按关键词过滤教师通讯录（姓名/学院/电话/邮箱）。"""
    if not keyword:
        return directory

    kw = keyword.strip().lower()
    if not kw:
        return directory

    result: list[dict[str, Any]] = []
    for item in directory:
        name = (item.get("teacher_name") or "").lower()
        dept = (item.get("department_name") or "").lower()
        phone = (item.get("phone") or "").lower()
        email = (item.get("email") or "").lower()
        if kw in name or kw in dept or kw in phone or kw in email:
            result.append(item)
    return result


def _build_structured_tools(
    db: AsyncSession,
    student_id: str,
    explicit_term_id: str | None,
):
    """构建结构化查询工具列表，供 LLM 规划调用。"""
    logger.debug("Building structured tools for student_id={}", student_id)

    @tool("get_my_scores")
    async def get_my_scores_tool(term_id: str | None = None) -> dict[str, Any]:
        """查询当前登录学生的成绩。可选参数 term_id。"""
        resolved_term_id = _sanitize_term_id(term_id, explicit_term_id)
        if (
            resolved_term_id
            and not await _term_exists(db, resolved_term_id)
            and explicit_term_id is None
            and term_id is not None
        ):
            logger.warning(
                "Invalid term_id from planner ignored in get_my_scores: {}",
                resolved_term_id,
            )
            resolved_term_id = None

        rows = await get_my_scores(db, student_id, term_id=resolved_term_id)

        # 仅在用户未显式给出学期时，允许对模型推断错误做兜底修复。
        if not rows and explicit_term_id is None and term_id is not None:
            fallback_term_id = await _latest_term_id_for_scores(db, student_id)
            if fallback_term_id and fallback_term_id != resolved_term_id:
                rows = await get_my_scores(db, student_id, term_id=fallback_term_id)
                resolved_term_id = fallback_term_id

        return {"term_id": resolved_term_id, "rows": rows}

    @tool("get_my_schedule")
    async def get_my_schedule_tool(term_id: str | None = None) -> dict[str, Any]:
        """查询当前登录学生的课程表。可选参数 term_id。"""
        resolved_term_id = _sanitize_term_id(term_id, explicit_term_id)

        if (
            resolved_term_id
            and not await _term_exists(db, resolved_term_id)
            and explicit_term_id is None
            and term_id is not None
        ):
            logger.warning(
                "Invalid term_id from planner ignored in get_my_schedule: {}",
                resolved_term_id,
            )
            resolved_term_id = None

        schedule = await get_my_schedule(db, student_id, term_id=resolved_term_id)

        if (
            not schedule.get("entries")
            and explicit_term_id is None
            and term_id is not None
        ):
            fallback_term_id = await _latest_term_id_for_schedule(db, student_id)
            if fallback_term_id and fallback_term_id != resolved_term_id:
                schedule = await get_my_schedule(db, student_id, term_id=fallback_term_id)

        return schedule

    @tool("get_my_enrollment")
    async def get_my_enrollment_tool(term_id: str | None = None) -> dict[str, Any]:
        """查询当前登录学生的选课记录。可选参数 term_id。"""
        resolved_term_id = _sanitize_term_id(term_id, explicit_term_id)

        if (
            resolved_term_id
            and not await _term_exists(db, resolved_term_id)
            and explicit_term_id is None
            and term_id is not None
        ):
            logger.warning(
                "Invalid term_id from planner ignored in get_my_enrollment: {}",
                resolved_term_id,
            )
            resolved_term_id = None

        rows = await get_my_enrollment(db, student_id, term_id=resolved_term_id)

        if not rows and explicit_term_id is None and term_id is not None:
            fallback_term_id = await _latest_term_id_for_enrollment(db, student_id)
            if fallback_term_id and fallback_term_id != resolved_term_id:
                rows = await get_my_enrollment(db, student_id, term_id=fallback_term_id)
                resolved_term_id = fallback_term_id

        return {"term_id": resolved_term_id, "rows": rows}

    @tool("get_my_info")
    async def get_my_info_tool() -> dict[str, Any]:
        """查询当前登录学生的学籍及联系信息。"""
        row = await get_my_info(db, student_id)
        return {"row": row}

    @tool("get_my_academic_overview")
    async def get_my_academic_overview_tool() -> dict[str, Any]:
        """查询当前登录学生的班级/专业/学院信息。"""
        row = await get_my_academic_overview(db, student_id)
        return {"row": row}

    @tool("list_departments_and_majors")
    async def list_departments_and_majors_tool() -> dict[str, Any]:
        """查询全校学院及专业目录。"""
        rows = await list_departments_and_majors(db)
        return {"rows": rows}

    @tool("search_teachers")
    async def search_teachers_tool(keyword: str | None = None) -> dict[str, Any]:
        """查询教师通讯录；可按 keyword 过滤姓名/学院/电话/邮箱。"""
        rows = await list_teacher_directory(db)
        filtered = _filter_teacher_directory(rows, keyword)
        return {"keyword": keyword, "rows": filtered}

    return {
        "get_my_scores": get_my_scores_tool,
        "get_my_schedule": get_my_schedule_tool,
        "get_my_enrollment": get_my_enrollment_tool,
        "get_my_info": get_my_info_tool,
        "get_my_academic_overview": get_my_academic_overview_tool,
        "list_departments_and_majors": list_departments_and_majors_tool,
        "search_teachers": search_teachers_tool,
    }


async def _plan_and_run_structured_tools(
    db: AsyncSession,
    query: str,
    intent: IntentType,
    student_id: str,
    explicit_term_id: str | None,
) -> str | None:
    """让 LLM 先规划工具调用，再执行并返回结构化上下文文本。"""
    if intent not in (IntentType.structured, IntentType.hybrid):
        logger.debug("Tool plan skipped by intent: {}", intent.value)
        return None

    tool_map = _build_structured_tools(db, student_id, explicit_term_id)
    logger.info("Tool plan start: query_len={}, intent={}", len(query), intent.value)

    raw_plan = await ainvoke_chat_prompt(
        _STRUCTURED_TOOL_PLAN_PROMPT,
        {
            "query": query,
            "intent": intent.value,
            "explicit_term_id": explicit_term_id or "",
        },
        model=settings.LLM_MODEL_TOOL_PLANNER,
        temperature=0.0,
        max_tokens=1024,
    )

    plan = _extract_json_object(raw_plan)
    tool_calls: list[dict[str, Any]] = []

    if not plan:
        logger.warning("Tool plan parse failed, raw_len={}", len(raw_plan or ""))
        tool_calls = _fallback_tool_calls(query, explicit_term_id)
        if tool_calls:
            logger.info("Tool plan fallback activated by parse failure")
    else:
        raw_tool_calls = plan.get("tool_calls")
        if isinstance(raw_tool_calls, list) and raw_tool_calls:
            tool_calls = raw_tool_calls
        else:
            logger.info("Tool plan produced no tool calls")
            tool_calls = _fallback_tool_calls(query, explicit_term_id)
            if tool_calls:
                logger.info("Tool plan fallback activated by empty plan")

    if not tool_calls:
        return None

    tool_calls = _align_tool_calls_with_query(query, tool_calls, explicit_term_id)
    if not tool_calls:
        return None

    executed_results: list[dict[str, Any]] = []
    for call in tool_calls[:6]:
        if not isinstance(call, dict):
            continue
        name = str(call.get("name", "")).strip()
        args = call.get("args", {})
        if not isinstance(args, dict):
            args = {}

        if name == "search_teachers":
            raw_keyword = str(args.get("keyword", "")).strip()
            normalized_keyword = _normalize_contact_target(raw_keyword)
            inferred_target = _extract_contact_target_name(query)
            if inferred_target and not normalized_keyword:
                args = {**args, "keyword": inferred_target}
            elif normalized_keyword and normalized_keyword != raw_keyword:
                args = {**args, "keyword": normalized_keyword}

        selected_tool = tool_map.get(name)
        if selected_tool is None:
            logger.warning("Unknown tool skipped: {}", name)
            continue

        try:
            logger.info("Tool invoking: name={}, args={}", name, args)
            result = await selected_tool.ainvoke(args)
            if name == "get_my_schedule" and isinstance(result, dict):
                result = _compact_schedule_result_for_week_query(result, query)
            executed_results.append(
                {"tool": name, "result": result}
            )
            logger.info("Tool invoke success: name={}", name)
        except Exception as exc:
            executed_results.append(
                {"tool": name, "error": "工具调用失败"}
            )
            logger.exception("Tool invoke failed: name={}", name)

    if not executed_results:
        logger.warning("Tool plan executed no results")
        return None

    logger.info("Tool plan completed: executed_count={}", len(executed_results))

    # 美化结构化数据：替换英文字段名为中文、转换学期ID、转换布尔值
    formatted_results = _translate_field_names(executed_results)
    structured_json = json.dumps(
        formatted_results, ensure_ascii=False, indent=2, default=_json_default
    )
    verdict_text = _build_structured_verdicts(executed_results, query)

    if verdict_text:
        return "结构化数据结果:\n" + structured_json + "\n\n" + verdict_text
    return "结构化数据结果:\n" + structured_json

def _extract_term_id_from_text(text: str) -> str | None:
    """尝试从文本中提取学期ID (如 202501, 202502, 202509 等)。"""
    # 匹配模式：20XX + (01|02|03|09)
    match = re.search(r"\b(20\d{2}(?:0[1-9]|1[0-2]))\b", text)
    if match:
        return match.group(1)
    return None


async def _extract_relative_term_id_from_text(
    db: AsyncSession,
    text: str,
) -> str | None:
    """从“上学期/下学期/本学期”等相对描述解析学期ID。"""
    normalized = (text or "").replace(" ", "")

    prev_terms = ("上学期", "上一学期", "上个学期")
    curr_terms = ("本学期", "这学期", "当前学期")
    next_terms = ("下学期", "下一学期", "下个学期")

    target = None
    if any(kw in normalized for kw in prev_terms):
        target = "previous"
    elif any(kw in normalized for kw in curr_terms):
        target = "current"
    elif any(kw in normalized for kw in next_terms):
        target = "next"

    if target is None:
        return None

    terms = (
        (await db.execute(select(Term).order_by(Term.start_date.asc())))
        .scalars()
        .all()
    )
    if not terms:
        return None

    today = date.today()
    current_idx: int | None = None
    for idx, term in enumerate(terms):
        if term.start_date <= today <= term.end_date:
            current_idx = idx
            break

    # 若当前不在任一学期范围内，取“截至今天最近已开始的学期”。
    if current_idx is None:
        started_indices = [i for i, term in enumerate(terms) if term.start_date <= today]
        current_idx = started_indices[-1] if started_indices else 0

    if target == "current":
        return terms[current_idx].term_id

    if target == "previous":
        prev_idx = current_idx - 1
        return terms[prev_idx].term_id if prev_idx >= 0 else None

    next_idx = current_idx + 1
    return terms[next_idx].term_id if next_idx < len(terms) else None


async def execute_query(
    db: AsyncSession,
    query: str,
    intent: IntentType,
    student_id: str,
    raw_query: str | None = None,
) -> str:
    """运行适当的查询策略并返回原始上下文文本。

    参数:
        db:         异步数据库会话。
        query:      用户完整的文本问题。
        intent:     分类后的意图类型。
        student_id: 已认证的学生 (用于强制执行隐私限制)。
        raw_query:  用户原始输入（未重写）。用于稳定解析“上/下/本学期”。

    返回:
        作为 JSON / 文本字符串的上下文数据，准备好供 LLM 进行总结。
    """
    parts: list[str] = []
    logger.info(
        "Execute query start: student_id={}, intent={}, query_len={}",
        student_id,
        intent.value,
        len(query),
    )

    query_lower = query.lower()
    
    # 学期解析优先级：
    # 1) 用户原始输入中的相对学期（上/下/本学期）
    # 2) 用户原始输入中的显式学期ID
    # 3) 重写文本中的相对学期
    # 4) 重写文本中的显式学期ID
    source_query = raw_query or query

    explicit_term_id = await _extract_relative_term_id_from_text(db, source_query)
    if explicit_term_id is None:
        explicit_term_id = _extract_term_id_from_text(source_query)
    if explicit_term_id is None:
        explicit_term_id = await _extract_relative_term_id_from_text(db, query)
    if explicit_term_id is None:
        explicit_term_id = _extract_term_id_from_text(query)

    if explicit_term_id:
        logger.info("Resolved explicit term id from query: {}", explicit_term_id)

    has_structured_topic = _contains_structured_topic(source_query) or _contains_structured_topic(query)
    if intent == IntentType.smalltalk and has_structured_topic:
        logger.warning("Intent corrected: smalltalk -> structured by topic guard")
        intent = IntentType.structured
    elif intent == IntentType.smalltalk:
        logger.info("Execute query short-circuited by smalltalk intent")
        return "闲聊场景：无需执行结构化查询或知识库检索。请直接自然、简洁地回复用户。"

    is_self_query = (student_id in query) or any(kw in query_lower for kw in ("我的", "my"))

    structured_topic_detected = (
        is_self_query
        or has_structured_topic
    )

    run_structured = intent in (IntentType.structured, IntentType.hybrid) or structured_topic_detected
    if intent == IntentType.vector and run_structured:
        intent = IntentType.hybrid
    logger.info(
        "Execute query branch: run_structured={}, effective_intent={}",
        run_structured,
        intent.value,
    )

    tool_context: str | None = None
    if run_structured:
        try:
            tool_context = await _plan_and_run_structured_tools(
                db=db,
                query=query,
                intent=intent,
                student_id=student_id,
                explicit_term_id=explicit_term_id,
            )
            if tool_context:
                parts.append(tool_context)
                logger.info("Tool context appended: context_len={}", len(tool_context))
        except Exception as exc:
            tool_context = None
            logger.warning(
                "Tool pipeline failed: {}: {}",
                exc.__class__.__name__,
                str(exc)[:240],
            )

    if run_structured and not tool_context:
        logger.info("No structured context produced by tool planner")

    if intent in (IntentType.vector, IntentType.hybrid):
        try:
            kb_result = await vector_search(query)
            if kb_result and kb_result != _NOT_FOUND_TEXT:
                parts.append("知识库内容：\n" + kb_result)
                logger.info("Knowledge context appended: len={}", len(kb_result or ""))
            else:
                logger.info("Knowledge search returned empty/not_found, skipping context append")
        except RuntimeError as exc:
            parts.append(f"（知识库查询失败：{exc}）")
            logger.exception("Knowledge search failed")
    result = "\n\n".join(parts) if parts else "未找到相关数据。"
    logger.info("Execute query end: context_len={}", len(result))
    return result
