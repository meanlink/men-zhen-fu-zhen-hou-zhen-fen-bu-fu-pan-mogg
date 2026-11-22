from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_roles
from ..database import get_db
from ..models import DepartmentSlot, User, UserRole, WaitSample
from ..schemas import SampleAction, SampleCreate, SampleOut
from ..services.attendance import locked_sample
from ..services.workflow import record_sample_event

router = APIRouter(prefix="/samples", tags=["候诊样本"])


@router.get("", response_model=list[SampleOut])
def list_samples(db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.ANALYST, UserRole.DEPARTMENT_REVIEWER, UserRole.OPERATIONS_ADMIN))):
    return list(db.scalars(select(WaitSample).order_by(WaitSample.appointment_time.desc())).all())


@router.post("", response_model=SampleOut)
def create_sample(payload: SampleCreate, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.ANALYST, UserRole.OPERATIONS_ADMIN))):
    if not db.get(DepartmentSlot, payload.department_slot_id):
        raise HTTPException(status_code=404, detail="科室时段不存在")
    sample = WaitSample(**payload.model_dump(), created_by=user.id)
    if payload.checkin_time:
        if payload.checkin_time < payload.appointment_time:
            raise HTTPException(status_code=409, detail="签到时间不能早于预约时间")
        from ..models import SampleStatus
        sample.status = SampleStatus.CHECKED_IN
    db.add(sample)
    db.commit()
    db.refresh(sample)
    return sample


@router.post("/{sample_id}/checkin", response_model=SampleOut)
def checkin(sample_id: int, payload: SampleAction, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.ANALYST, UserRole.OPERATIONS_ADMIN))):
    sample = locked_sample(db, sample_id)
    return record_sample_event(db, sample, "checkin", payload.event_time, user, payload.note)


@router.post("/{sample_id}/call", response_model=SampleOut)
def call(sample_id: int, payload: SampleAction, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.ANALYST, UserRole.OPERATIONS_ADMIN))):
    sample = locked_sample(db, sample_id)
    return record_sample_event(db, sample, "call", payload.event_time, user, payload.note)


@router.post("/{sample_id}/complete", response_model=SampleOut)
def complete(sample_id: int, payload: SampleAction, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.ANALYST, UserRole.OPERATIONS_ADMIN))):
    sample = locked_sample(db, sample_id)
    return record_sample_event(db, sample, "complete", payload.event_time, user, payload.note)
