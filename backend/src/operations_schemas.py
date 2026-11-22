from datetime import datetime, time
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, NaiveDatetime, StringConstraints

from .capacity_models import ReleaseStatus
from .recovery_models import RecoveryStatus
from .schemas import Evidence, SampleOut


class ReleaseCreate(BaseModel):
    slot_id: int
    starts_at: time
    ends_at: time
    quantity: int = Field(ge=1, le=100)
    staffing_note: Evidence


class ReleaseDecision(BaseModel):
    decision: Literal['approved', 'rejected']
    note: Evidence


class ReleaseClose(BaseModel):
    note: Evidence


class ReleaseBookingCreate(BaseModel):
    sample_code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=40)]
    patient_alias: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]
    appointment_time: NaiveDatetime


class ReleaseBookingOut(BaseModel):
    sample_id: int
    sample_code: str
    appointment_time: datetime
    booked_by: int
    booked_at: datetime


class ReleaseOut(ReleaseCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: ReleaseStatus
    proposed_by: int
    proposed_at: datetime
    decided_by: int | None
    decided_at: datetime | None
    decision_note: str | None
    closed_by: int | None
    closed_at: datetime | None
    close_note: str | None
    available: int
    bookings: list[ReleaseBookingOut]


class RecoveryCreate(BaseModel):
    sample_id: int
    observed_at: NaiveDatetime
    incident_note: Evidence


class RecoveryDecision(BaseModel):
    decision: Literal['prioritized', 'dismissed']
    note: Evidence


class RecoveryOut(RecoveryCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: RecoveryStatus
    observed_wait_minutes: int
    threshold_minutes: int
    opened_by: int
    opened_at: datetime
    decided_by: int | None
    decided_at: datetime | None
    decision_note: str | None
    called_at: datetime | None
    recorded_by: int | None
    recovery_minutes: int | None
    release_id: int | None


class RecoveryCandidate(SampleOut):
    threshold_minutes: int
