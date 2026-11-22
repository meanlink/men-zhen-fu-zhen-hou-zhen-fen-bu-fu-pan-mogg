from datetime import date, datetime
from enum import Enum

from sqlalchemy import CheckConstraint, Date, DateTime, Enum as SqlEnum, Float, ForeignKey, Integer, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class UserRole(str, Enum):
    ANALYST = "analyst"
    DEPARTMENT_REVIEWER = "department_reviewer"
    OPERATIONS_ADMIN = "operations_admin"


class SampleStatus(str, Enum):
    BOOKED = "booked"
    CHECKED_IN = "checked_in"
    CALLED = "called"
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"


class ReportStatus(str, Enum):
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    REVIEWED = "reviewed"
    ARCHIVED = "archived"


class AttendanceReason(str, Enum):
    NO_SHOW = "no_show"
    CANCELLED = "cancelled"


class AttendanceStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class ImprovementStatus(str, Enum):
    PLANNED = "planned"
    IMPLEMENTED = "implemented"
    EVALUATED = "evaluated"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    role: Mapped[UserRole] = mapped_column(SqlEnum(UserRole, name="user_role"))
    password_hash: Mapped[str] = mapped_column(String(180))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DepartmentSlot(Base):
    __tablename__ = "department_slots"
    __table_args__ = (UniqueConstraint("department_name", "slot_date", "slot_label", name="uq_department_slot"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    department_name: Mapped[str] = mapped_column(String(80), index=True)
    slot_date: Mapped[datetime] = mapped_column(Date, index=True)
    slot_label: Mapped[str] = mapped_column(String(60))
    start_time: Mapped[datetime] = mapped_column(Time)
    end_time: Mapped[datetime] = mapped_column(Time)
    threshold_minutes: Mapped[int] = mapped_column(Integer, default=30)
    capacity: Mapped[int] = mapped_column(Integer, default=20)
    status: Mapped[str] = mapped_column(String(30), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    samples = relationship("WaitSample", back_populates="slot", cascade="all, delete-orphan")
    reports = relationship("ReviewReport", back_populates="slot")


class WaitSample(Base):
    __tablename__ = "wait_samples"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sample_code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    patient_alias: Mapped[str] = mapped_column(String(80))
    department_slot_id: Mapped[int] = mapped_column(ForeignKey("department_slots.id"), index=True)
    appointment_time: Mapped[datetime] = mapped_column(DateTime)
    checkin_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    called_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[SampleStatus] = mapped_column(SqlEnum(SampleStatus, name="sample_status"), default=SampleStatus.BOOKED)
    source_channel: Mapped[str] = mapped_column(String(30), default="预约台")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    slot = relationship("DepartmentSlot", back_populates="samples")


class ReviewReport(Base):
    __tablename__ = "review_reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(160))
    department_slot_id: Mapped[int] = mapped_column(ForeignKey("department_slots.id"), index=True)
    status: Mapped[ReportStatus] = mapped_column(SqlEnum(ReportStatus, name="report_status"), default=ReportStatus.DRAFT)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    missing_checkin_count: Mapped[int] = mapped_column(Integer, default=0)
    p50_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    p90_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    median_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    mad_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    anomaly_count: Mapped[int] = mapped_column(Integer, default=0)
    distribution_json: Mapped[str] = mapped_column(Text, default="[]")
    anomaly_codes_json: Mapped[str] = mapped_column(Text, default="[]")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    slot = relationship("DepartmentSlot", back_populates="reports")

    exclusions = relationship("ReportAttendanceExclusion", lazy="selectin", order_by="ReportAttendanceExclusion.sample_code")


class AttendanceException(Base):
    __tablename__ = "attendance_exceptions"
    __table_args__ = (CheckConstraint(
        "(status = 'PENDING' AND decided_by IS NULL AND decided_at IS NULL AND decision_note IS NULL) OR "
        "(status <> 'PENDING' AND decided_by IS NOT NULL AND decided_at IS NOT NULL AND decision_note IS NOT NULL)",
        name="ck_attendance_decision",
    ),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sample_id: Mapped[int] = mapped_column(ForeignKey("wait_samples.id"), unique=True)
    reason: Mapped[AttendanceReason] = mapped_column(SqlEnum(AttendanceReason, name="attendance_reason"))
    status: Mapped[AttendanceStatus] = mapped_column(SqlEnum(AttendanceStatus, name="attendance_status"))
    evidence: Mapped[str] = mapped_column(String(500))
    submitted_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    decision_note: Mapped[str | None] = mapped_column(String(500))


class ReportAttendanceExclusion(Base):
    __tablename__ = "report_attendance_exclusions"
    report_id: Mapped[int] = mapped_column(ForeignKey("review_reports.id", ondelete="CASCADE"), primary_key=True)
    attendance_id: Mapped[int] = mapped_column(ForeignKey("attendance_exceptions.id"), primary_key=True)
    sample_code: Mapped[str] = mapped_column(String(40))
    reason: Mapped[AttendanceReason] = mapped_column(SqlEnum(AttendanceReason, name="attendance_reason"))


class WaitImprovement(Base):
    __tablename__ = "wait_improvements"
    __table_args__ = (
        CheckConstraint("target_p90 > 0 AND target_p90 < baseline_p90", name="ck_improvement_target"),
        CheckConstraint(
            "(status = 'PLANNED' AND implemented_on IS NULL AND implemented_by IS NULL AND implementation_note IS NULL) OR "
            "(status <> 'PLANNED' AND implemented_on IS NOT NULL AND implemented_by IS NOT NULL AND implementation_note IS NOT NULL)",
            name="ck_improvement_implementation",
        ),
        CheckConstraint(
            "(status = 'EVALUATED' AND comparison_report_id IS NOT NULL AND comparison_p90 IS NOT NULL "
            "AND evaluated_by IS NOT NULL AND evaluated_at IS NOT NULL AND evaluation_note IS NOT NULL) OR "
            "(status <> 'EVALUATED' AND comparison_report_id IS NULL AND comparison_p90 IS NULL "
            "AND evaluated_by IS NULL AND evaluated_at IS NULL AND evaluation_note IS NULL)",
            name="ck_improvement_evaluation",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    baseline_report_id: Mapped[int] = mapped_column(ForeignKey("review_reports.id"), unique=True)
    anomaly_sample_code: Mapped[str] = mapped_column(String(40))
    action_plan: Mapped[str] = mapped_column(String(500))
    baseline_p90: Mapped[float] = mapped_column(Float)
    target_p90: Mapped[float] = mapped_column(Float)
    status: Mapped[ImprovementStatus] = mapped_column(SqlEnum(ImprovementStatus, name="improvement_status"))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    implemented_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    implemented_on: Mapped[date | None] = mapped_column(Date)
    implementation_note: Mapped[str | None] = mapped_column(String(500))
    comparison_report_id: Mapped[int | None] = mapped_column(ForeignKey("review_reports.id"))
    comparison_p90: Mapped[float | None] = mapped_column(Float)
    evaluated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime)
    evaluation_note: Mapped[str | None] = mapped_column(String(500))

    @property
    def outcome(self) -> str | None:
        if self.comparison_p90 is None:
            return None
        return "met" if self.comparison_p90 <= self.target_p90 else "missed"

    @property
    def p90_change(self) -> float | None:
        if self.comparison_p90 is None:
            return None
        return round(self.comparison_p90 - self.baseline_p90, 1)
