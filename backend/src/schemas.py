from datetime import date, datetime, time
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from .models import AttendanceReason, AttendanceStatus, ImprovementStatus, ReportStatus, SampleStatus, UserRole


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    display_name: str
    role: UserRole


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class SlotCreate(BaseModel):
    department_name: str = Field(min_length=2, max_length=80)
    slot_date: date
    slot_label: str = Field(min_length=2, max_length=60)
    start_time: time
    end_time: time
    threshold_minutes: int = Field(ge=5, le=240)
    capacity: int = Field(ge=1, le=100)


class SlotOut(SlotCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str


class SampleCreate(BaseModel):
    sample_code: str = Field(min_length=3, max_length=40)
    patient_alias: str = Field(min_length=2, max_length=80)
    department_slot_id: int
    appointment_time: datetime
    checkin_time: datetime | None = None
    source_channel: str = "预约台"
    note: str | None = None


class SampleAction(BaseModel):
    event_time: datetime
    note: str | None = None


class SampleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sample_code: str
    patient_alias: str
    department_slot_id: int
    appointment_time: datetime
    checkin_time: datetime | None
    called_time: datetime | None
    completed_time: datetime | None
    status: SampleStatus
    source_channel: str
    note: str | None


class ReportCreate(BaseModel):
    department_slot_id: int
    title: str = Field(min_length=4, max_length=160)


class ReviewAction(BaseModel):
    review_note: str = Field(min_length=4, max_length=500)


class ExcludedAttendanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    attendance_id: int
    sample_code: str
    reason: AttendanceReason


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    report_code: str
    title: str
    department_slot_id: int
    status: ReportStatus
    sample_count: int
    missing_checkin_count: int
    p50_minutes: float | None
    p90_minutes: float | None
    median_minutes: float | None
    mad_minutes: float | None
    anomaly_count: int
    distribution: list[dict]
    anomaly_codes: list[str]
    exclusions: list[ExcludedAttendanceOut]
    summary: str | None
    review_note: str | None
    created_at: datetime
    reviewed_at: datetime | None
    archived_at: datetime | None


class AuditOut(BaseModel):
    action: str
    target_type: str
    target_id: str
    created_at: datetime


Evidence = Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=500)]


class AttendanceCreate(BaseModel):
    sample_id: int
    reason: AttendanceReason
    evidence: Evidence


class AttendanceDecision(BaseModel):
    decision: Literal[AttendanceStatus.CONFIRMED, AttendanceStatus.REJECTED]
    decision_note: Evidence


class AttendanceOut(AttendanceCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: AttendanceStatus
    submitted_by: int
    submitted_at: datetime
    decided_by: int | None
    decided_at: datetime | None
    decision_note: str | None


class ImprovementCreate(BaseModel):
    baseline_report_id: int
    anomaly_sample_code: str = Field(min_length=3, max_length=40)
    target_p90: float = Field(gt=0, allow_inf_nan=False)
    action_plan: Evidence


class ImplementationAction(BaseModel):
    implemented_on: date
    implementation_note: Evidence


class EvaluationAction(BaseModel):
    comparison_report_id: int
    evaluation_note: Evidence


class ImprovementOut(ImprovementCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: ImprovementStatus
    baseline_p90: float
    created_by: int
    created_at: datetime
    implemented_by: int | None
    implemented_on: date | None
    implementation_note: str | None
    comparison_report_id: int | None
    comparison_p90: float | None
    evaluated_by: int | None
    evaluated_at: datetime | None
    evaluation_note: str | None
    outcome: Literal["met", "missed"] | None
    p90_change: float | None
