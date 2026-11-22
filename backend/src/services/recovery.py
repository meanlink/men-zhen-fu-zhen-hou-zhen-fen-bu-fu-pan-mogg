from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from ..capacity_models import ReleasedBooking
from ..models import DepartmentSlot, SampleStatus, User, WaitSample
from ..operations_schemas import RecoveryCandidate, RecoveryCreate, RecoveryDecision, RecoveryOut
from ..recovery_models import QueueRecovery, RecoveryStatus
from ..schemas import SampleOut
from .attendance import CLINIC_TIMEZONE, ensure_no_attendance_hold, locked_sample


def recovery_rows(db: Session) -> list[RecoveryOut]:
    order = case((QueueRecovery.status == RecoveryStatus.PENDING, 0), (QueueRecovery.status == RecoveryStatus.PRIORITIZED, 1), else_=2)
    rows = db.execute(
        select(QueueRecovery, ReleasedBooking.release_id).outerjoin(ReleasedBooking, ReleasedBooking.sample_id == QueueRecovery.sample_id)
        .order_by(order, (QueueRecovery.observed_wait_minutes - QueueRecovery.threshold_minutes).desc(), QueueRecovery.observed_at.desc())
    )
    return [describe_recovery(row, release_id) for row, release_id in rows]


def describe_recovery(row: QueueRecovery, release_id: int | None) -> RecoveryOut:
    return RecoveryOut.model_validate({
        **{name: getattr(row, name) for name in RecoveryOut.model_fields if name != 'release_id'},
        'release_id': release_id,
    })


def recovery_response(db: Session, row: QueueRecovery) -> RecoveryOut:
    booking = db.get(ReleasedBooking, row.sample_id)
    return describe_recovery(row, booking.release_id if booking else None)


def recovery_candidates(db: Session) -> list[RecoveryCandidate]:
    rows = db.execute(select(WaitSample, DepartmentSlot.threshold_minutes)
        .join(DepartmentSlot).outerjoin(QueueRecovery, QueueRecovery.sample_id == WaitSample.id)
        .where(WaitSample.status == SampleStatus.CHECKED_IN, WaitSample.checkin_time.is_not(None),
               WaitSample.called_time.is_(None), QueueRecovery.id.is_(None))
        .order_by(WaitSample.checkin_time))
    return [RecoveryCandidate(**SampleOut.model_validate(sample).model_dump(), threshold_minutes=threshold) for sample, threshold in rows]


def recovery_for_sample(db: Session, sample_id: int) -> QueueRecovery | None:
    return db.scalar(select(QueueRecovery).where(QueueRecovery.sample_id == sample_id))


def open_recovery(db: Session, payload: RecoveryCreate, user: User) -> QueueRecovery:
    sample = locked_sample(db, payload.sample_id)
    ensure_no_attendance_hold(db, sample.id)
    if sample.status != SampleStatus.CHECKED_IN or not sample.checkin_time or sample.called_time:
        raise HTTPException(409, '只有已签到且尚未叫号的候诊样本可以发起处置')
    if recovery_for_sample(db, sample.id):
        raise HTTPException(409, '该候诊样本已有处置记录')
    now = datetime.now(CLINIC_TIMEZONE).replace(tzinfo=None)
    if not sample.checkin_time <= payload.observed_at <= now:
        raise HTTPException(409, '观察时间须介于现场签到和当前诊区时间之间')
    waited = int((payload.observed_at - sample.checkin_time).total_seconds() // 60)
    if waited < sample.slot.threshold_minutes:
        raise HTTPException(409, f'候诊实测 {waited} 分钟，尚未达到 {sample.slot.threshold_minutes} 分钟处置阈值')
    row = QueueRecovery(**payload.model_dump(), observed_wait_minutes=waited, threshold_minutes=sample.slot.threshold_minutes,
                        status=RecoveryStatus.PENDING, opened_by=user.id)
    db.add(row)
    db.commit()
    return row


def decide_recovery(db: Session, recovery_id: int, payload: RecoveryDecision, user: User) -> QueueRecovery:
    sample_id = db.scalar(select(QueueRecovery.sample_id).where(QueueRecovery.id == recovery_id))
    if sample_id is None:
        raise HTTPException(404, '超时处置单不存在')
    # Sample events and recovery transitions always acquire the sample lock first.
    locked_sample(db, sample_id)
    row = db.get(QueueRecovery, recovery_id, populate_existing=True)
    if row.status != RecoveryStatus.PENDING or row.opened_by == user.id:
        raise HTTPException(409, '只有独立复核员可以处理待分流处置单')
    row.status = RecoveryStatus(payload.decision)
    row.decided_by = user.id
    row.decided_at = datetime.utcnow()
    row.decision_note = payload.note
    db.commit()
    return row


def capture_recovery_call(db: Session, sample_id: int, event_time: datetime, user: User) -> None:
    row = recovery_for_sample(db, sample_id)
    if row is None or row.status == RecoveryStatus.DISMISSED:
        return
    if row.status == RecoveryStatus.PENDING:
        raise HTTPException(409, '超时处置待科室确认，请先在候诊处置台分流')
    if row.status == RecoveryStatus.RECOVERED:
        raise HTTPException(409, '处置叫号已留存，请勿重复录入')
    now = datetime.now(CLINIC_TIMEZONE).replace(tzinfo=None)
    if event_time.tzinfo is not None or not row.observed_at <= event_time <= now:
        raise HTTPException(409, '处置叫号时间须介于观察和当前诊区时间之间')
    row.status = RecoveryStatus.RECOVERED
    row.called_at = event_time
    row.recorded_by = user.id
