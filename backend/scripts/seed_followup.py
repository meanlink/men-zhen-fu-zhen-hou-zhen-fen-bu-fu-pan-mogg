from datetime import date, datetime, time, timedelta

from sqlalchemy import select

from src.models import AttendanceReason, AttendanceStatus, DepartmentSlot, ReviewReport, SampleStatus, WaitImprovement, WaitSample
from src.schemas import AttendanceCreate, AttendanceDecision, ImprovementCreate
from src.services.attendance import attendance_for_sample, decide_attendance, submit_attendance
from src.services.improvements import create_improvement
from src.services.workflow import create_report, review_report


def seed_window(db, analyst, day, waits, extra_booking=False):
    slot_date = date(2026, 11, day)
    slot = db.scalar(select(DepartmentSlot).where(
        DepartmentSlot.department_name == "呼吸内科", DepartmentSlot.slot_date == slot_date,
        DepartmentSlot.slot_label == "随访加开窗",
    ))
    if not slot:
        slot = DepartmentSlot(department_name="呼吸内科", slot_date=slot_date, slot_label="随访加开窗",
                              start_time=time(9), end_time=time(11), threshold_minutes=30, capacity=12)
        db.add(slot)
        db.flush()
    bookings = [*waits, None] if extra_booking else waits
    for i, wait in enumerate(bookings, start=1):
        code = f"FU-11{day}-{i:02}"
        if db.scalar(select(WaitSample.id).where(WaitSample.sample_code == code)):
            continue
        appointment = datetime.combine(slot_date, time(9)) + timedelta(minutes=8 * (i - 1))
        checkin = appointment + timedelta(minutes=2) if wait is not None else None
        called = checkin + timedelta(minutes=wait) if checkin else None
        db.add(WaitSample(
            sample_code=code, department_slot_id=slot.id, patient_alias=f"随访代号 {i}",
            appointment_time=appointment, checkin_time=checkin, called_time=called,
            completed_time=called + timedelta(minutes=10) if called else None,
            status=SampleStatus.COMPLETED if called else SampleStatus.BOOKED,
            source_channel="电话预约", created_by=analyst.id,
        ))
    db.commit()
    return slot


def seed_followup(db, analyst, reviewer):
    baseline = seed_window(db, analyst, 16, [20, 24, 28, 58], extra_booking=True)
    comparison = seed_window(db, analyst, 19, [17, 18, 22, 30])
    no_show = db.scalar(select(WaitSample).where(WaitSample.sample_code == "FU-1116-05"))
    record = attendance_for_sample(db, no_show.id)
    if not record:
        record = submit_attendance(db, AttendanceCreate(
            sample_id=no_show.id, reason=AttendanceReason.NO_SHOW, evidence="闭诊后核对预约台与签到终端均无记录。",
        ), analyst)
        decide_attendance(db, record.id, AttendanceDecision(
            decision=AttendanceStatus.CONFIRMED, decision_note="科室核对电话回访，确认患者当日未到诊。",
        ), reviewer)
    baseline_report = seed_report(db, analyst, reviewer, baseline, "呼吸内科加开窗 · 长尾基线")
    seed_report(db, analyst, reviewer, comparison, "呼吸内科加开窗 · 改善复测")
    if not db.scalar(select(WaitImprovement.id).where(WaitImprovement.baseline_report_id == baseline_report.id)):
        create_improvement(db, ImprovementCreate(
            baseline_report_id=baseline_report.id, anomaly_sample_code="FU-1116-04", target_p90=35,
            action_plan="将加号集中到 10:30 后，由分诊护士每 15 分钟检查一次积压。",
        ), analyst)
    print("followup seed ok: confirmed=FU-1116-05, baseline_p90=49.0, comparison_p90=27.6, target_p90=35")


def seed_report(db, analyst, reviewer, slot, title):
    report = db.scalar(select(ReviewReport).where(ReviewReport.department_slot_id == slot.id, ReviewReport.title == title))
    if report:
        return report
    report = create_report(db, slot.id, title, analyst)
    return review_report(db, report, reviewer, "已逐条核对候诊记录与时段分布。")
