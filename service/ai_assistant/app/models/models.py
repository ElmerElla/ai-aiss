"""
数据模型模块

功能介绍：
-----------
本模块使用 SQLAlchemy 2.0 声明式语法定义了 AI 校园助手的所有数据库表结构，
包括学生、教师、课程、课表、成绩、选课、管理员、对话日志等核心实体。

每个类对应一张数据库表，包含字段定义、约束、索引和关系映射。
所有模型继承自 app.database.Base。

主要实体：
- AdminUser / AdminActionLog: 管理员与审计日志
- Department / Major / Class: 院系、专业、班级
- Teacher: 教师信息
- Term: 学期
- Course / Classroom: 课程与教室
- Student / Enrollment / Score: 学生、选课、成绩
- Schedule / ScheduleClassMap / ScheduleAdjustment: 课表及调课
- ChatLog: 对话日志
"""
from __future__ import annotations

import enum
from datetime import date

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ---------------------------------------------------------------------------
# 管理员表 (AdminUser) / 管理审计表 (AdminActionLog)
# ---------------------------------------------------------------------------
class AdminRoleEnum(str, enum.Enum):
    """管理员角色枚举。"""
    super_admin = "super_admin"
    scheduler_admin = "scheduler_admin"
    security_admin = "security_admin"
    readonly_admin = "readonly_admin"


class AdminStatusEnum(str, enum.Enum):
    """管理员账号状态枚举。"""
    active = "active"
    disabled = "disabled"
    locked = "locked"


class AdminUser(Base):
    """管理员用户表，存储后台管理员的登录凭证、角色和状态信息。"""
    __tablename__ = "admin_user"

    admin_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    admin_code: Mapped[str] = mapped_column(String(32), nullable=False)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[AdminRoleEnum] = mapped_column(
        Enum(AdminRoleEnum), nullable=False, default=AdminRoleEnum.scheduler_admin
    )
    status: Mapped[AdminStatusEnum] = mapped_column(
        Enum(AdminStatusEnum), nullable=False, default=AdminStatusEnum.active
    )
    last_login_at: Mapped[DateTime | None] = mapped_column(DateTime)
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("admin_code", name="uk_admin_code"),
        UniqueConstraint("username", name="uk_admin_username"),
        Index("idx_admin_role_status", "role", "status"),
    )

    action_logs: Mapped[list["AdminActionLog"]] = relationship(
        "AdminActionLog", back_populates="admin"
    )
    updated_schedules: Mapped[list["Schedule"]] = relationship(
        "Schedule", back_populates="updated_by_admin"
    )
    created_schedule_mappings: Mapped[list["ScheduleClassMap"]] = relationship(
        "ScheduleClassMap", back_populates="created_by_admin"
    )
    requested_adjustments: Mapped[list["ScheduleAdjustment"]] = relationship(
        "ScheduleAdjustment",
        back_populates="requested_by_admin",
        foreign_keys="ScheduleAdjustment.requested_by_admin_id",
    )
    approved_adjustments: Mapped[list["ScheduleAdjustment"]] = relationship(
        "ScheduleAdjustment",
        back_populates="approved_by_admin",
        foreign_keys="ScheduleAdjustment.approved_by_admin_id",
    )


class AdminActionLog(Base):
    """管理操作审计日志表，记录管理员对课表等数据的关键变更操作。"""
    __tablename__ = "admin_action_log"

    action_log_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    admin_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("admin_user.admin_id", onupdate="CASCADE"),
        nullable=False,
    )
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_table: Mapped[str] = mapped_column(String(64), nullable=False)
    target_pk: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255))
    before_json: Mapped[str | None] = mapped_column(Text)
    after_json: Mapped[str | None] = mapped_column(Text)
    request_ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("idx_action_admin_time", "admin_id", "created_at"),
        Index("idx_action_target", "target_table", "target_pk", "created_at"),
    )

    admin: Mapped["AdminUser"] = relationship("AdminUser", back_populates="action_logs")


# ---------------------------------------------------------------------------
# 院系表 (Department)
# ---------------------------------------------------------------------------
class Department(Base):
    """院系表，存储学校下属各学院/系的基本信息。"""
    __tablename__ = "department"

    dept_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    __table_args__ = (UniqueConstraint("name", name="uk_department_name"),)

    majors: Mapped[list["Major"]] = relationship("Major", back_populates="department")
    teachers: Mapped[list["Teacher"]] = relationship(
        "Teacher", back_populates="department"
    )


# ---------------------------------------------------------------------------
# 专业表 (Major)
# ---------------------------------------------------------------------------
class Major(Base):
    """专业表，存储各院系下设的专业信息，与院系一对多关联。"""
    __tablename__ = "major"

    major_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    dept_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("department.dept_id", onupdate="CASCADE"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("dept_id", "name", name="uk_major_dept_name"),
        Index("idx_major_dept_id", "dept_id"),
    )

    department: Mapped["Department"] = relationship("Department", back_populates="majors")
    classes: Mapped[list["Class"]] = relationship("Class", back_populates="major")


# ---------------------------------------------------------------------------
# 班级表 (Class)
# ---------------------------------------------------------------------------
class Class(Base):
    """班级表，存储各年级的班级信息，与专业一对多关联。"""
    __tablename__ = "class"

    class_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    major_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("major.major_id", onupdate="CASCADE"), nullable=False
    )
    grade: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("major_id", "grade", "name", name="uk_class_major_grade_name"),
        Index("idx_class_major_id", "major_id"),
    )

    major: Mapped["Major"] = relationship("Major", back_populates="classes")
    students: Mapped[list["Student"]] = relationship("Student", back_populates="class_")
    schedule_mappings: Mapped[list["ScheduleClassMap"]] = relationship(
        "ScheduleClassMap", back_populates="class_"
    )


# ---------------------------------------------------------------------------
# 教师表 (Teacher)
# ---------------------------------------------------------------------------
class Teacher(Base):
    """教师表，存储教师的基本信息、所属院系及联系方式。"""
    __tablename__ = "teacher"

    teacher_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str | None] = mapped_column(String(50))
    dept_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("department.dept_id", onupdate="CASCADE"), nullable=False
    )
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(255))
    office_hours: Mapped[str | None] = mapped_column(String(255))
    office_room: Mapped[str | None] = mapped_column(String(100))

    __table_args__ = (Index("idx_teacher_dept_id", "dept_id"),)

    department: Mapped["Department"] = relationship(
        "Department", back_populates="teachers"
    )
    schedules: Mapped[list["Schedule"]] = relationship(
        "Schedule", back_populates="teacher"
    )


# ---------------------------------------------------------------------------
# 学期表 (Term)
# ---------------------------------------------------------------------------
class Term(Base):
    """学期表，定义学期的起始和结束日期，用于课表和成绩的时间范围约束。"""
    __tablename__ = "term"

    term_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)

    __table_args__ = (
        CheckConstraint("start_date < end_date", name="ck_term_dates"),
    )

    enrollments: Mapped[list["Enrollment"]] = relationship(
        "Enrollment", back_populates="term"
    )
    scores: Mapped[list["Score"]] = relationship("Score", back_populates="term")
    schedules: Mapped[list["Schedule"]] = relationship("Schedule", back_populates="term")
    adjustments: Mapped[list["ScheduleAdjustment"]] = relationship(
        "ScheduleAdjustment", back_populates="term"
    )


# ---------------------------------------------------------------------------
# 课程表 (Course)
# ---------------------------------------------------------------------------
class CourseTypeEnum(str, enum.Enum):
    """课程类型枚举。"""
    public_required = "公共必修课"
    major_required = "专业必修课"
    major_elective = "专业选修课"


class Course(Base):
    """课程表，存储课程名称、学分和课程类型（必修/选修）。"""
    __tablename__ = "course"

    course_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    course_name: Mapped[str] = mapped_column(String(255), nullable=False)
    credit: Mapped[int] = mapped_column(Integer, nullable=False)
    course_type: Mapped[CourseTypeEnum] = mapped_column(
        Enum(
            CourseTypeEnum,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=CourseTypeEnum.major_required,
    )

    __table_args__ = (
        Index("idx_course_course_name", "course_name"),
        CheckConstraint("credit > 0", name="ck_course_credit"),
    )

    enrollments: Mapped[list["Enrollment"]] = relationship(
        "Enrollment", back_populates="course"
    )
    scores: Mapped[list["Score"]] = relationship("Score", back_populates="course")
    schedules: Mapped[list["Schedule"]] = relationship(
        "Schedule", back_populates="course"
    )


# ---------------------------------------------------------------------------
# 教室表 (Classroom)
# ---------------------------------------------------------------------------
class RoomTypeEnum(str, enum.Enum):
    """教室类型枚举。"""
    normal = "普通教室"
    computer = "计算机机房"
    lab = "实验室"
    auditorium = "阶梯教室"
    other = "其他"


class Classroom(Base):
    """教室表，存储教室的位置、类型和容纳人数。"""
    __tablename__ = "classroom"

    room_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    room_type: Mapped[RoomTypeEnum] = mapped_column(
        Enum(
            RoomTypeEnum,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=RoomTypeEnum.normal,
    )
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        Index("idx_classroom_location", "location"),
        CheckConstraint("capacity > 0", name="ck_classroom_capacity"),
    )

    schedules: Mapped[list["Schedule"]] = relationship(
        "Schedule", back_populates="classroom"
    )


# ---------------------------------------------------------------------------
# 学生表 (Student)
# ---------------------------------------------------------------------------
class StudentStatusEnum(str, enum.Enum):
    """学生学籍状态枚举。"""
    active = "active"
    suspended = "suspended"
    withdrawn = "withdrawn"
    graduated = "graduated"


class Student(Base):
    """学生表，存储学生的学籍信息、所属班级及联系方式。"""
    __tablename__ = "student"

    student_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    gender: Mapped[str] = mapped_column(String(10), nullable=False)
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    enroll_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    class_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("class.class_id", onupdate="CASCADE"), nullable=False
    )
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[StudentStatusEnum] = mapped_column(
        Enum(StudentStatusEnum), nullable=False, default=StudentStatusEnum.active
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__ = (
        Index("idx_student_class_id", "class_id"),
        Index("idx_student_enroll_year", "enroll_year"),
    )

    class_: Mapped["Class"] = relationship("Class", back_populates="students")
    enrollments: Mapped[list["Enrollment"]] = relationship(
        "Enrollment", back_populates="student"
    )
    scores: Mapped[list["Score"]] = relationship("Score", back_populates="student")


# ---------------------------------------------------------------------------
# 选课表 (Enrollment)
# ---------------------------------------------------------------------------
class Enrollment(Base):
    """选课表，记录学生在各学期的选课情况。"""
    __tablename__ = "enrollment"

    enrollment_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("student.student_id", onupdate="CASCADE"), nullable=False
    )
    course_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("course.course_id", onupdate="CASCADE"), nullable=False
    )
    term_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("term.term_id", onupdate="CASCADE"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("student_id", "course_id", "term_id", name="uk_enrollment"),
        Index("idx_enrollment_course_term", "course_id", "term_id"),
    )

    student: Mapped["Student"] = relationship("Student", back_populates="enrollments")
    course: Mapped["Course"] = relationship("Course", back_populates="enrollments")
    term: Mapped["Term"] = relationship("Term", back_populates="enrollments")


# ---------------------------------------------------------------------------
# 成绩表 (Score)
# ---------------------------------------------------------------------------
class Score(Base):
    """成绩表，记录学生的课程成绩、学分获得情况及作弊标记。"""
    __tablename__ = "score"

    score_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("student.student_id", onupdate="CASCADE"), nullable=False
    )
    course_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("course.course_id", onupdate="CASCADE"), nullable=False
    )
    term_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("term.term_id", onupdate="CASCADE"), nullable=False
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credit_earned: Mapped[bool] = mapped_column(
        SmallInteger, nullable=False, default=False
    )
    cheating: Mapped[bool] = mapped_column(SmallInteger, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint(
            "student_id", "course_id", "term_id", name="uk_score_student_course_term"
        ),
        Index("idx_score_course_term", "course_id", "term_id"),
        CheckConstraint("score >= 0 AND score <= 100", name="ck_score_range"),
    )

    student: Mapped["Student"] = relationship("Student", back_populates="scores")
    course: Mapped["Course"] = relationship("Course", back_populates="scores")
    term: Mapped["Term"] = relationship("Term", back_populates="scores")


# ---------------------------------------------------------------------------
# 课程安排 (Schedule)
# ---------------------------------------------------------------------------
class ScheduleStatusEnum(str, enum.Enum):
    """课表状态枚举。"""
    active = "active"
    cancelled = "cancelled"


class Schedule(Base):
    """课表表，定义课程的上课时间、地点、教师及班级映射关系。"""
    __tablename__ = "schedule"

    schedule_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    course_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("course.course_id", onupdate="CASCADE"), nullable=False
    )
    teacher_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("teacher.teacher_id", onupdate="CASCADE"), nullable=False
    )
    room_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("classroom.room_id", onupdate="CASCADE"), nullable=False
    )
    term_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("term.term_id", onupdate="CASCADE"), nullable=False
    )
    week_no: Mapped[int] = mapped_column(Integer, nullable=False)
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    start_period: Mapped[int] = mapped_column(Integer, nullable=False)
    end_period: Mapped[int] = mapped_column(Integer, nullable=False)
    week_pattern: Mapped[str | None] = mapped_column(String(255))
    schedule_status: Mapped[ScheduleStatusEnum] = mapped_column(
        Enum(ScheduleStatusEnum), nullable=False, default=ScheduleStatusEnum.active
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_by_admin_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("admin_user.admin_id", onupdate="CASCADE", ondelete="SET NULL"),
    )
    updated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("idx_schedule_term_course", "term_id", "course_id"),
        Index(
            "idx_schedule_term_teacher_time",
            "term_id", "teacher_id", "week_no", "day_of_week", "start_period",
        ),
        Index(
            "idx_schedule_term_room_time",
            "term_id", "room_id", "week_no", "day_of_week", "start_period",
        ),
        Index(
            "idx_schedule_term_status_time",
            "term_id", "schedule_status", "week_no", "day_of_week", "start_period",
        ),
        CheckConstraint("day_of_week BETWEEN 1 AND 7", name="ck_schedule_day_of_week"),
        CheckConstraint(
            "start_period >= 1 AND end_period >= 1 AND start_period <= end_period",
            name="ck_schedule_periods",
        ),
        CheckConstraint(
            "week_no >= 1 AND week_no <= 30", name="ck_schedule_week_no"
        ),
    )

    course: Mapped["Course"] = relationship("Course", back_populates="schedules")
    teacher: Mapped["Teacher"] = relationship("Teacher", back_populates="schedules")
    classroom: Mapped["Classroom"] = relationship("Classroom", back_populates="schedules")
    term: Mapped["Term"] = relationship("Term", back_populates="schedules")
    updated_by_admin: Mapped["AdminUser | None"] = relationship(
        "AdminUser", back_populates="updated_schedules"
    )
    class_mappings: Mapped[list["ScheduleClassMap"]] = relationship(
        "ScheduleClassMap", back_populates="schedule"
    )
    adjustments: Mapped[list["ScheduleAdjustment"]] = relationship(
        "ScheduleAdjustment", back_populates="schedule"
    )


# ---------------------------------------------------------------------------
# 排课-班级映射表 (ScheduleClassMap)
# ---------------------------------------------------------------------------
class ScheduleClassMap(Base):
    """排课与班级的多对多映射表，支持一个课程安排对应多个班级。"""
    __tablename__ = "schedule_class_map"

    schedule_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("schedule.schedule_id", onupdate="CASCADE", ondelete="CASCADE"),
        primary_key=True,
    )
    class_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("class.class_id", onupdate="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    created_by_admin_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("admin_user.admin_id", onupdate="CASCADE", ondelete="SET NULL"),
    )

    __table_args__ = (
        Index("idx_scm_class", "class_id"),
        Index("idx_scm_class_schedule", "class_id", "schedule_id"),
    )

    schedule: Mapped["Schedule"] = relationship("Schedule", back_populates="class_mappings")
    class_: Mapped["Class"] = relationship("Class", back_populates="schedule_mappings")
    created_by_admin: Mapped["AdminUser | None"] = relationship(
        "AdminUser", back_populates="created_schedule_mappings"
    )


# ---------------------------------------------------------------------------
# 调课单表 (ScheduleAdjustment)
# ---------------------------------------------------------------------------
class ScheduleAdjustmentOperationEnum(str, enum.Enum):
    """调课操作类型枚举。"""
    move = "move"
    change_room = "change_room"
    change_teacher = "change_teacher"
    cancel = "cancel"
    recover = "recover"


class ScheduleAdjustmentStatusEnum(str, enum.Enum):
    """调课单状态枚举。"""
    pending = "pending"
    applied = "applied"
    rejected = "rejected"
    rolled_back = "rolled_back"


class ScheduleAdjustment(Base):
    """调课单表，记录课表调整申请的操作类型、变更前后信息及审批状态。"""
    __tablename__ = "schedule_adjustment"

    adjustment_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    schedule_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("schedule.schedule_id", onupdate="CASCADE"),
        nullable=False,
    )
    term_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("term.term_id", onupdate="CASCADE"),
        nullable=False,
    )
    operation_type: Mapped[ScheduleAdjustmentOperationEnum] = mapped_column(
        Enum(ScheduleAdjustmentOperationEnum), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[ScheduleAdjustmentStatusEnum] = mapped_column(
        Enum(ScheduleAdjustmentStatusEnum), nullable=False, default=ScheduleAdjustmentStatusEnum.pending
    )
    expected_schedule_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    old_week_no: Mapped[int] = mapped_column(Integer, nullable=False)
    old_day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    old_start_period: Mapped[int] = mapped_column(Integer, nullable=False)
    old_end_period: Mapped[int] = mapped_column(Integer, nullable=False)
    old_room_id: Mapped[str] = mapped_column(String(32), nullable=False)
    old_teacher_id: Mapped[str] = mapped_column(String(32), nullable=False)

    new_week_no: Mapped[int | None] = mapped_column(Integer)
    new_day_of_week: Mapped[int | None] = mapped_column(SmallInteger)
    new_start_period: Mapped[int | None] = mapped_column(Integer)
    new_end_period: Mapped[int | None] = mapped_column(Integer)
    new_room_id: Mapped[str | None] = mapped_column(String(32))
    new_teacher_id: Mapped[str | None] = mapped_column(String(32))

    requested_by_admin_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("admin_user.admin_id", onupdate="CASCADE"),
        nullable=False,
    )
    approved_by_admin_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("admin_user.admin_id", onupdate="CASCADE", ondelete="SET NULL"),
    )
    requested_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    approved_at: Mapped[DateTime | None] = mapped_column(DateTime)
    applied_at: Mapped[DateTime | None] = mapped_column(DateTime)
    rollback_of_adjustment_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("schedule_adjustment.adjustment_id", onupdate="CASCADE", ondelete="SET NULL"),
    )
    conflict_snapshot: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("idx_adj_term_status", "term_id", "status", "requested_at"),
        Index("idx_adj_schedule_time", "schedule_id", "requested_at"),
        Index("idx_adj_requester_time", "requested_by_admin_id", "requested_at"),
        CheckConstraint("old_day_of_week BETWEEN 1 AND 7", name="ck_adj_old_day"),
        CheckConstraint(
            "old_start_period >= 1 AND old_end_period >= 1 AND old_start_period <= old_end_period",
            name="ck_adj_old_period",
        ),
        CheckConstraint(
            "new_day_of_week IS NULL OR (new_day_of_week BETWEEN 1 AND 7)",
            name="ck_adj_new_day",
        ),
        CheckConstraint(
            "(new_start_period IS NULL AND new_end_period IS NULL) "
            "OR (new_start_period >= 1 AND new_end_period >= 1 AND new_start_period <= new_end_period)",
            name="ck_adj_new_period",
        ),
    )

    schedule: Mapped["Schedule"] = relationship("Schedule", back_populates="adjustments")
    term: Mapped["Term"] = relationship("Term", back_populates="adjustments")
    requested_by_admin: Mapped["AdminUser"] = relationship(
        "AdminUser",
        back_populates="requested_adjustments",
        foreign_keys=[requested_by_admin_id],
    )
    approved_by_admin: Mapped["AdminUser | None"] = relationship(
        "AdminUser",
        back_populates="approved_adjustments",
        foreign_keys=[approved_by_admin_id],
    )


# ---------------------------------------------------------------------------
# 对话日志 (ChatLog)
# ---------------------------------------------------------------------------
class SenderEnum(str, enum.Enum):
    """对话消息发送者类型枚举。"""
    student = "student"
    agent = "agent"
    system = "system"


class SystemActionEnum(str, enum.Enum):
    """系统对消息采取的干预动作枚举。"""
    none = "none"
    flag_danger = "flag_danger"
    report = "report"
    block = "block"


class ChatLog(Base):
    """对话日志表，持久化存储学生与 AI 助手的问答记录，支持隐私脱敏。"""
    __tablename__ = "chat_log"

    log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    did: Mapped[str] = mapped_column(String(64), nullable=False)
    student_id: Mapped[str | None] = mapped_column(String(32))
    timestamp: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    sender: Mapped[SenderEnum] = mapped_column(Enum(SenderEnum), nullable=False)
    message_content: Mapped[str] = mapped_column(Text, nullable=False)
    system_action: Mapped[SystemActionEnum] = mapped_column(
        Enum(SystemActionEnum), nullable=False, default=SystemActionEnum.none
    )
    response_time_ms: Mapped[int | None] = mapped_column(BigInteger)

    __table_args__ = (
        Index("idx_did_timestamp", "did", "timestamp"),
        Index("idx_system_action", "system_action"),
        Index("idx_student_id", "student_id"),
    )
