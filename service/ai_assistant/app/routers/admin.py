"""管理员路由：登录与课表管理。"""
from __future__ import annotations

from datetime import datetime
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
import redis.asyncio as aioredis
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_admin, get_db, get_redis
from app.models.models import (
    AdminActionLog,
    AdminUser,
    Class,
    Classroom,
    Course,
    Department,
    Major,
    Schedule,
    ScheduleAdjustment,
    ScheduleAdjustmentStatusEnum,
    ScheduleClassMap,
    ScheduleStatusEnum,
    Teacher,
    Term,
)
from app.schemas.admin import (
    AdminClassItem,
    AdminDashboardSummaryResponse,
    AdminLoginRequest,
    AdminMeResponse,
    AdminScheduleItem,
    AdminScheduleListResponse,
    AdminTermItem,
    AdminTokenResponse,
    UpdateScheduleStatusRequest,
    UpdateScheduleStatusResponse,
)
from app.services.auth_service import (
    authenticate_admin,
    create_admin_access_token,
)
from app.services import cache_service
from app.utils.logger import logger

router = APIRouter(prefix="/api/v1/admin", tags=["管理员"])


@router.post(
    "/auth/login",
    response_model=AdminTokenResponse,
    summary="管理员登录",
    description="使用管理员用户名和AES加密密码进行认证，返回管理员JWT令牌。",
)
async def admin_login(
    body: AdminLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> AdminTokenResponse:
    try:
        admin = await authenticate_admin(db, body.username, body.encrypted_password)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="管理员用户名或密码无效",
        )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="管理员账号不可用",
        )

    token, expires_in = create_admin_access_token(admin.admin_id, admin.username)
    return AdminTokenResponse(
        access_token=token,
        expires_in=expires_in,
        admin_id=admin.admin_id,
        username=admin.username,
        display_name=admin.display_name,
        role=admin.role,
    )


@router.get(
    "/auth/me",
    response_model=AdminMeResponse,
    summary="获取当前管理员信息",
)
async def admin_me(
    current_admin: AdminUser = Depends(get_current_admin),
) -> AdminMeResponse:
    return AdminMeResponse(
        admin_id=current_admin.admin_id,
        admin_code=current_admin.admin_code,
        username=current_admin.username,
        display_name=current_admin.display_name,
        role=current_admin.role,
    )


@router.get(
    "/dashboard/summary",
    response_model=AdminDashboardSummaryResponse,
    summary="管理员概览统计",
)
async def dashboard_summary(
    _current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminDashboardSummaryResponse:
    pending_adjustments = (
        await db.execute(
            select(func.count())
            .select_from(ScheduleAdjustment)
            .where(ScheduleAdjustment.status == ScheduleAdjustmentStatusEnum.pending)
        )
    ).scalar_one()

    active_schedules = (
        await db.execute(
            select(func.count())
            .select_from(Schedule)
            .where(Schedule.schedule_status == ScheduleStatusEnum.active)
        )
    ).scalar_one()

    cancelled_schedules = (
        await db.execute(
            select(func.count())
            .select_from(Schedule)
            .where(Schedule.schedule_status == ScheduleStatusEnum.cancelled)
        )
    ).scalar_one()

    total_classes = (await db.execute(select(func.count()).select_from(Class))).scalar_one()
    total_terms = (await db.execute(select(func.count()).select_from(Term))).scalar_one()

    return AdminDashboardSummaryResponse(
        pending_adjustments=pending_adjustments,
        active_schedules=active_schedules,
        cancelled_schedules=cancelled_schedules,
        total_classes=total_classes,
        total_terms=total_terms,
    )


@router.get(
    "/meta/terms",
    response_model=list[AdminTermItem],
    summary="获取学期列表",
)
async def list_terms(
    _current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> list[AdminTermItem]:
    terms = (
        await db.execute(select(Term).order_by(Term.start_date.desc()))
    ).scalars().all()
    return [
        AdminTermItem(
            term_id=term.term_id,
            start_date=term.start_date,
            end_date=term.end_date,
        )
        for term in terms
    ]


@router.get(
    "/meta/classes",
    response_model=list[AdminClassItem],
    summary="获取班级列表",
)
async def list_classes(
    _current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> list[AdminClassItem]:
    rows = (
        await db.execute(
            select(Class, Major, Department)
            .join(Major, Class.major_id == Major.major_id)
            .join(Department, Major.dept_id == Department.dept_id)
            .order_by(Class.grade.desc(), Class.class_id.asc())
        )
    ).all()

    return [
        AdminClassItem(
            class_id=class_.class_id,
            class_name=class_.name,
            grade=class_.grade,
            major_name=major.name,
            department_name=dept.name,
        )
        for class_, major, dept in rows
    ]


@router.get(
    "/schedules",
    response_model=AdminScheduleListResponse,
    summary="管理员课表列表",
)
async def list_schedules(
    term_id: str | None = Query(None, description="学期ID"),
    class_id: str | None = Query(None, description="班级ID"),
    week_no: int | None = Query(None, ge=1, description="第几周"),
    schedule_status: ScheduleStatusEnum | None = Query(None, description="课表状态"),
    keyword: str | None = Query(None, description="关键词（课程/教师/教室/班级）"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminScheduleListResponse:
    query = (
        select(Schedule, Course, Teacher, Classroom, Class, Major, Department)
        .join(ScheduleClassMap, ScheduleClassMap.schedule_id == Schedule.schedule_id)
        .join(Course, Schedule.course_id == Course.course_id)
        .join(Teacher, Schedule.teacher_id == Teacher.teacher_id)
        .join(Classroom, Schedule.room_id == Classroom.room_id)
        .join(Class, ScheduleClassMap.class_id == Class.class_id)
        .join(Major, Class.major_id == Major.major_id)
        .join(Department, Major.dept_id == Department.dept_id)
    )

    if term_id:
        query = query.where(Schedule.term_id == term_id)
    if class_id:
        query = query.where(Class.class_id == class_id)
    if week_no is not None:
        query = query.where(Schedule.week_no == week_no)
    if schedule_status:
        query = query.where(Schedule.schedule_status == schedule_status)
    if keyword:
        like_pattern = f"%{keyword.strip()}%"
        query = query.where(
            or_(
                Course.course_name.like(like_pattern),
                Teacher.name.like(like_pattern),
                Classroom.location.like(like_pattern),
                Class.name.like(like_pattern),
            )
        )

    query = query.order_by(
        Schedule.term_id.desc(),
        Schedule.week_no.asc(),
        Schedule.day_of_week.asc(),
        Schedule.start_period.asc(),
        Schedule.schedule_id.asc(),
    )

    rows = (await db.execute(query)).all()

    grouped: dict[str, dict] = {}
    for schedule, course, teacher, classroom, class_, major, dept in rows:
        item = grouped.get(schedule.schedule_id)
        if item is None:
            item = {
                "schedule_id": schedule.schedule_id,
                "term_id": schedule.term_id,
                "course_id": schedule.course_id,
                "course_name": course.course_name,
                "teacher_id": schedule.teacher_id,
                "teacher_name": teacher.name,
                "room_id": schedule.room_id,
                "room_location": classroom.location,
                "week_no": schedule.week_no,
                "day_of_week": schedule.day_of_week,
                "start_period": schedule.start_period,
                "end_period": schedule.end_period,
                "week_pattern": schedule.week_pattern,
                "schedule_status": schedule.schedule_status,
                "version": schedule.version,
                "updated_at": schedule.updated_at,
                "classes": [],
                "_class_ids": set(),
            }
            grouped[schedule.schedule_id] = item

        if class_.class_id not in item["_class_ids"]:
            item["classes"].append(
                AdminClassItem(
                    class_id=class_.class_id,
                    class_name=class_.name,
                    grade=class_.grade,
                    major_name=major.name,
                    department_name=dept.name,
                )
            )
            item["_class_ids"].add(class_.class_id)

    all_items: list[AdminScheduleItem] = []
    for data in grouped.values():
        data.pop("_class_ids", None)
        all_items.append(AdminScheduleItem(**data))

    total = len(all_items)
    items = all_items[offset : offset + limit]

    return AdminScheduleListResponse(total=total, items=items)


@router.patch(
    "/schedules/{schedule_id}/status",
    response_model=UpdateScheduleStatusResponse,
    summary="更新课表状态",
)
async def update_schedule_status(
    schedule_id: str,
    body: UpdateScheduleStatusRequest,
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> UpdateScheduleStatusResponse:
    schedule = (
        await db.execute(
            select(Schedule).where(Schedule.schedule_id == schedule_id).limit(1)
        )
    ).scalar_one_or_none()

    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="课表记录不存在",
        )

    target_status = ScheduleStatusEnum(body.schedule_status)
    if schedule.schedule_status == target_status:
        return UpdateScheduleStatusResponse(
            schedule_id=schedule.schedule_id,
            schedule_status=schedule.schedule_status,
            version=schedule.version,
            updated_at=schedule.updated_at,
        )

    before_state = {
        "schedule_status": schedule.schedule_status.value,
        "version": schedule.version,
    }

    schedule.schedule_status = target_status
    schedule.version = (schedule.version or 0) + 1
    schedule.updated_by_admin_id = current_admin.admin_id
    schedule.updated_at = datetime.now()

    after_state = {
        "schedule_status": schedule.schedule_status.value,
        "version": schedule.version,
    }

    db.add(
        AdminActionLog(
            admin_id=current_admin.admin_id,
            action_type="schedule_status_update",
            target_table="schedule",
            target_pk=schedule.schedule_id,
            reason=(body.reason or "").strip() or None,
            before_json=json.dumps(before_state, ensure_ascii=False),
            after_json=json.dumps(after_state, ensure_ascii=False),
            request_ip=None,
            created_at=datetime.now(),
        )
    )

    await db.flush()
    await db.commit()

    try:
        await cache_service.bump_schedule_cache_version(redis)
    except Exception:
        logger.exception("Schedule cache version bump failed after status update")

    logger.info(
        "Schedule status updated by admin: schedule_id={}, admin_id={}, from={}, to={}",
        schedule.schedule_id,
        current_admin.admin_id,
        before_state["schedule_status"],
        after_state["schedule_status"],
    )

    return UpdateScheduleStatusResponse(
        schedule_id=schedule.schedule_id,
        schedule_status=schedule.schedule_status,
        version=schedule.version,
        updated_at=schedule.updated_at,
    )
