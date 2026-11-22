from datetime import date, datetime, time, timedelta
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select

from src.auth import hash_password
from src.database import SessionLocal, init_db
from src.models import DepartmentSlot, SampleStatus, User, UserRole, WaitSample


def get_or_create_user(db, username, display_name, role):
    user = db.scalar(select(User).where(User.username == username))
    if user:
        return user
    user = User(username=username, display_name=display_name, role=role, password_hash=hash_password("demo123"))
    db.add(user)
    db.flush()
    return user


def main():
    init_db()
    db = SessionLocal()
    try:
        analyst = get_or_create_user(db, "analyst", "林晓岚", UserRole.ANALYST)
        reviewer = get_or_create_user(db, "reviewer", "周医生", UserRole.DEPARTMENT_REVIEWER)
        admin = get_or_create_user(db, "admin", "顾运营", UserRole.OPERATIONS_ADMIN)
        db.flush()

        slot = db.scalar(select(DepartmentSlot).where(DepartmentSlot.department_name == "呼吸内科", DepartmentSlot.slot_date == date(2026, 11, 20), DepartmentSlot.slot_label == "午后复诊"))
        if not slot:
            slot = DepartmentSlot(department_name="呼吸内科", slot_date=date(2026, 11, 20), slot_label="午后复诊", start_time=time(13, 30), end_time=time(17, 30), threshold_minutes=30, capacity=24, status="open")
            db.add(slot)
            db.flush()
        slot2 = db.scalar(select(DepartmentSlot).where(DepartmentSlot.department_name == "皮肤科", DepartmentSlot.slot_date == date(2026, 11, 20), DepartmentSlot.slot_label == "上午复诊"))
        if not slot2:
            slot2 = DepartmentSlot(department_name="皮肤科", slot_date=date(2026, 11, 20), slot_label="上午复诊", start_time=time(8, 30), end_time=time(12, 0), threshold_minutes=25, capacity=20, status="open")
            db.add(slot2)
            db.flush()

        base = datetime(2026, 11, 20, 13, 30)
        samples = [
            ("OP-1120-01", "赵女士", 0, 8, 28, "线上预约"),
            ("OP-1120-02", "陈先生", 5, 11, 29, "电话预约"),
            ("OP-1120-03", "孙阿姨", 12, 10, 40, "线上预约"),
            ("OP-1120-04", "王先生", 18, 7, 31, "现场加号"),
            ("OP-1120-05", "吴女士", 24, 4, 34, "线上预约"),
            ("OP-1120-06", "李先生", 31, 6, 75, "电话预约"),
            ("OP-1120-07", "周女士", 39, 5, 36, "线上预约"),
            ("OP-1120-08", "郑先生", 46, 5, 29, "现场加号"),
            ("OP-1120-09", "梁阿姨", 55, 3, 45, "线上预约"),
            ("OP-1120-10", "蒋先生", 63, 2, 33, "电话预约"),
            ("OP-1120-11", "何女士", 70, None, None, "线上预约"),
        ]
        existing = {item.sample_code for item in db.scalars(select(WaitSample).where(WaitSample.department_slot_id == slot.id)).all()}
        for code, alias, offset, checkin_gap, wait, channel in samples:
            if code in existing:
                continue
            appointment = base + timedelta(minutes=offset)
            checkin = appointment + timedelta(minutes=checkin_gap) if checkin_gap is not None else None
            called = checkin + timedelta(minutes=wait) if wait is not None and checkin is not None else None
            completed = called + timedelta(minutes=12) if called else None
            status = SampleStatus.COMPLETED if completed else SampleStatus.BOOKED
            db.add(WaitSample(sample_code=code, patient_alias=alias, department_slot_id=slot.id, appointment_time=appointment, checkin_time=checkin if wait is not None else None, called_time=called, completed_time=completed, status=status, source_channel=channel, note="seed 演示样本", created_by=analyst.id))

        skin_base = datetime(2026, 11, 20, 8, 30)
        skin_samples = [("SK-1120-01", "杜女士", 0, 6, 12), ("SK-1120-02", "袁先生", 25, 4, 18), ("SK-1120-03", "沈女士", 50, 3, 22)]
        existing2 = {item.sample_code for item in db.scalars(select(WaitSample).where(WaitSample.department_slot_id == slot2.id)).all()}
        for code, alias, offset, checkin_gap, wait in skin_samples:
            if code in existing2:
                continue
            appointment = skin_base + timedelta(minutes=offset)
            checkin = appointment + timedelta(minutes=checkin_gap)
            called = checkin + timedelta(minutes=wait)
            db.add(WaitSample(sample_code=code, patient_alias=alias, department_slot_id=slot2.id, appointment_time=appointment, checkin_time=checkin, called_time=called, completed_time=called + timedelta(minutes=10), status=SampleStatus.COMPLETED, source_channel="线上预约", note="seed 演示样本", created_by=analyst.id))
        db.commit()
        print("seed ok: users=3, slots=2, samples=14")
        if "--with-expansion" in sys.argv[1:]:
            from seed_followup import seed_followup
            seed_followup(db, analyst, reviewer)
        if "--with-operations" in sys.argv[1:]:
            from seed_operations import seed_operations
            seed_operations(db, admin)
    finally:
        db.close()


if __name__ == "__main__":
    main()
