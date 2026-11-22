from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_roles
from ..database import get_db
from ..models import DepartmentSlot, User, UserRole
from ..schemas import SlotCreate, SlotOut

router = APIRouter(prefix="/slots", tags=["科室时段"])


@router.get("", response_model=list[SlotOut])
def list_slots(db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.ANALYST, UserRole.DEPARTMENT_REVIEWER, UserRole.OPERATIONS_ADMIN))):
    return list(db.scalars(select(DepartmentSlot).order_by(DepartmentSlot.slot_date.desc(), DepartmentSlot.start_time)).all())


@router.post("", response_model=SlotOut)
def create_slot(payload: SlotCreate, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OPERATIONS_ADMIN))):
    slot = DepartmentSlot(**payload.model_dump())
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return slot
