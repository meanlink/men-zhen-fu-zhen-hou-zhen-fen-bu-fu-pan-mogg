from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AttendanceException, AttendanceStatus, SampleStatus, User, WaitSample
from ..schemas import AttendanceCreate, AttendanceDecision

CLINIC_TIMEZONE = ZoneInfo("Asia/Shanghai")


def locked_sample(db: Session, sample_id: int) -> WaitSample:
    sample = db.get(WaitSample, sample_id, with_for_update=True, populate_existing=True)
    if not sample:
        raise HTTPException(404, "候诊样本不存在")
    return sample


def attendance_for_sample(db: Session, sample_id: int) -> AttendanceException | None:
    return db.scalar(select(AttendanceException).where(AttendanceException.sample_id == sample_id))


def ensure_no_attendance_hold(db: Session, sample_id: int) -> None:
    attendance = attendance_for_sample(db, sample_id)
    if attendance and attendance.status != AttendanceStatus.REJECTED:
        raise HTTPException(409, "核销待复核或已确认，当前不能补录候诊事件")


def ensure_unattended(sample: WaitSample) -> None:
    if sample.status not in (SampleStatus.BOOKED, SampleStatus.NEEDS_REVIEW) or any(
        (sample.checkin_time, sample.called_time, sample.completed_time)
    ):
        raise HTTPException(409, "已有到诊记录的样本不能核销")


def submit_attendance(db: Session, payload: AttendanceCreate, user: User) -> AttendanceException:
    sample = locked_sample(db, payload.sample_id)
    if attendance_for_sample(db, sample.id):
        raise HTTPException(409, "该预约已有核销记录")
    ensure_unattended(sample)
    cutoff = max(datetime.combine(sample.slot.slot_date, sample.slot.end_time), sample.appointment_time)
    if datetime.now(CLINIC_TIMEZONE).replace(tzinfo=None) < cutoff:
        raise HTTPException(409, "时段结束且预约时间已过后才能核销")
    row = AttendanceException(**payload.model_dump(), status=AttendanceStatus.PENDING, submitted_by=user.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def decide_attendance(db: Session, attendance_id: int, payload: AttendanceDecision, user: User) -> AttendanceException:
    sample_id = db.scalar(select(AttendanceException.sample_id).where(AttendanceException.id == attendance_id))
    if sample_id is None:
        raise HTTPException(404, "核销记录不存在")
    sample = locked_sample(db, sample_id)
    row = attendance_for_sample(db, sample_id)
    if row.status != AttendanceStatus.PENDING:
        raise HTTPException(409, "只有待复核的核销记录可以处理")
    if row.submitted_by == user.id:
        raise HTTPException(409, "请由另一位人员复核核销记录")
    if payload.decision == AttendanceStatus.CONFIRMED:
        ensure_unattended(sample)
    row.status = payload.decision
    row.decided_by = user.id
    row.decided_at = datetime.utcnow()
    row.decision_note = payload.decision_note
    db.commit()
    db.refresh(row)
    return row
