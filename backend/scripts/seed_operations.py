from datetime import date, time

from sqlalchemy import select

from src.capacity_models import CapacityRelease
from src.models import DepartmentSlot
from src.operations_schemas import ReleaseCreate
from src.services.capacity import propose_release


DEMO_DAY = date(2026, 11, 20)
DEMO_DEPARTMENT = '心内科'
DEMO_WINDOW = '周五午后复诊'


def seed_operations(db, admin):
    slot = db.scalar(select(DepartmentSlot).where(
        DepartmentSlot.department_name == DEMO_DEPARTMENT,
        DepartmentSlot.slot_date == DEMO_DAY,
        DepartmentSlot.slot_label == DEMO_WINDOW,
    ))
    if slot is None:
        slot = DepartmentSlot(department_name=DEMO_DEPARTMENT, slot_date=DEMO_DAY, slot_label=DEMO_WINDOW,
                              start_time=time(13, 30), end_time=time(17), threshold_minutes=25, capacity=18)
        db.add(slot)
        db.flush()
    starts_at, ends_at = time(15), time(16)
    existing = db.scalar(select(CapacityRelease.id).where(
        CapacityRelease.slot_id == slot.id, CapacityRelease.starts_at == starts_at, CapacityRelease.ends_at == ends_at,
    ).limit(1))
    if existing is None:
        propose_release(db, ReleaseCreate(slot_id=slot.id, starts_at=starts_at, ends_at=ends_at, quantity=2,
                                         staffing_note='3 号诊室 15:00 有支援医生，预约台可补发两个复诊号。'), admin)
    print('operations seed ok: 心内科 15:00–16:00 · 2 个待审批加号')
