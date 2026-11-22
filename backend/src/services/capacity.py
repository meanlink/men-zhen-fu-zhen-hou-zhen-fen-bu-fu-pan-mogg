from collections import defaultdict
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..capacity_models import CapacityRelease, ReleasedBooking, ReleaseStatus
from ..models import DepartmentSlot, User, WaitSample
from ..operations_schemas import ReleaseCreate, ReleaseDecision, ReleaseBookingCreate, ReleaseBookingOut, ReleaseOut


def describe_releases(db: Session, releases: list[CapacityRelease]) -> list[ReleaseOut]:
    ids = [release.id for release in releases]
    by_release = defaultdict(list)
    rows = db.execute(
        select(ReleasedBooking, WaitSample).join(WaitSample).where(ReleasedBooking.release_id.in_(ids))
        .order_by(WaitSample.appointment_time, WaitSample.id)
    )
    for booking, sample in rows:
        by_release[booking.release_id].append(ReleaseBookingOut(
            sample_id=sample.id, sample_code=sample.sample_code, appointment_time=sample.appointment_time,
            booked_by=booking.booked_by, booked_at=booking.booked_at,
        ))
    return [ReleaseOut.model_validate({
        **{name: getattr(release, name) for name in ReleaseOut.model_fields if name not in ('bookings', 'available')},
        'bookings': by_release[release.id],
        'available': release.quantity - len(by_release[release.id]) if release.status == ReleaseStatus.APPROVED else 0,
    }) for release in releases]


def get_release(db: Session, release_id: int) -> CapacityRelease:
    release = db.get(CapacityRelease, release_id, with_for_update=True, populate_existing=True)
    if not release:
        raise HTTPException(404, '加号批次不存在')
    return release


def propose_release(db: Session, payload: ReleaseCreate, user: User) -> CapacityRelease:
    slot = db.get(DepartmentSlot, payload.slot_id)
    if not slot:
        raise HTTPException(404, '科室时段不存在')
    if any(value.tzinfo is not None for value in (payload.starts_at, payload.ends_at)):
        raise HTTPException(422, '临时加号时间须使用诊区本地时刻')
    if slot.status != 'open' or not slot.start_time <= payload.starts_at < payload.ends_at <= slot.end_time:
        raise HTTPException(409, '加号时间必须在开放的复诊时段内')
    if payload.quantity > slot.capacity:
        raise HTTPException(409, '单批加号上限为该时段基础容量')
    release = CapacityRelease(**payload.model_dump(), status=ReleaseStatus.PROPOSED, proposed_by=user.id)
    db.add(release)
    db.commit()
    return release


def decide_release(db: Session, release_id: int, payload: ReleaseDecision, user: User) -> CapacityRelease:
    release = get_release(db, release_id)
    if release.status != ReleaseStatus.PROPOSED or release.proposed_by == user.id:
        raise HTTPException(409, '只有独立复核员可以决定待审核批次')
    if payload.decision == 'approved':
        # Lock the parent slot so simultaneous decisions cannot approve overlapping windows.
        slot = db.get(DepartmentSlot, release.slot_id, with_for_update=True, populate_existing=True)
        if slot.status != 'open':
            raise HTTPException(409, '复诊时段已关闭')
        overlap = db.scalar(select(CapacityRelease.id).where(
            CapacityRelease.slot_id == slot.id,
            CapacityRelease.status.in_((ReleaseStatus.APPROVED, ReleaseStatus.CLOSED)),
            CapacityRelease.starts_at < release.ends_at,
            CapacityRelease.ends_at > release.starts_at,
        ).limit(1))
        if overlap is not None:
            raise HTTPException(409, '同一复诊时段已有重叠的已批加号批次')
    release.status = ReleaseStatus(payload.decision)
    release.decided_by = user.id
    release.decided_at = datetime.utcnow()
    release.decision_note = payload.note
    db.commit()
    return release


def issue_booking(db: Session, release_id: int, payload: ReleaseBookingCreate, user: User) -> WaitSample:
    release = get_release(db, release_id)
    if release.status != ReleaseStatus.APPROVED:
        raise HTTPException(409, '只有已批准且开放的批次可以发放加号')
    slot = db.get(DepartmentSlot, release.slot_id)
    if slot.status != 'open' or not (
        payload.appointment_time.date() == slot.slot_date
        and release.starts_at <= payload.appointment_time.time() < release.ends_at
    ):
        raise HTTPException(409, '预约必须落在已批准的加号时段内（含开始、不含结束）')
    booked = db.scalar(select(func.count()).select_from(ReleasedBooking).where(ReleasedBooking.release_id == release.id))
    if booked >= release.quantity:
        raise HTTPException(409, '该批次加号名额已用完')
    sample = WaitSample(**payload.model_dump(), department_slot_id=slot.id, source_channel='临时容量加号', created_by=user.id)
    db.add(sample)
    try:
        db.flush()
        db.add(ReleasedBooking(sample_id=sample.id, release_id=release.id, booked_by=user.id))
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if getattr(getattr(error.orig, 'diag', None), 'constraint_name', None) == 'ix_wait_samples_sample_code':
            raise HTTPException(409, '候诊样本编号已存在') from error
        raise
    return sample


def close_release(db: Session, release_id: int, note: str, user: User) -> CapacityRelease:
    release = get_release(db, release_id)
    if release.status != ReleaseStatus.APPROVED:
        raise HTTPException(409, '只有已批准批次可以收回剩余名额')
    release.status = ReleaseStatus.CLOSED
    release.closed_by = user.id
    release.closed_at = datetime.utcnow()
    release.close_note = note
    db.commit()
    return release
