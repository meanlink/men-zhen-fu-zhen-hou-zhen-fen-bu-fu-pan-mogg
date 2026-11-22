from datetime import date, datetime, time, timedelta

from sqlalchemy import select

from src.models import (
    AttendanceReason, AttendanceStatus, DepartmentSlot, ImprovementEvaluationHistory,
    ImprovementSlotClaim, ReviewReport, SampleStatus, User, WaitImprovement, WaitSample,
)
from src.schemas import AttendanceCreate, AttendanceDecision, EvaluationAction, ImprovementCreate, WithdrawalAction
from src.services.attendance import attendance_for_sample, decide_attendance, submit_attendance
from src.services.improvements import (
    create_improvement, evaluate_improvement, list_evaluation_history, withdraw_evaluation,
)
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
    admin = db.scalar(select(User).where(User.username == "admin"))
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
    seed_claim_demo(db, analyst, reviewer, admin)


def seed_claim_demo(db, analyst, reviewer, admin):
    """演示时段占用、撤回留档与同窗口多份报告的完整链路（幂等）。"""
    if db.scalar(select(ImprovementEvaluationHistory.id)):
        print("claim demo seed skipped: history already exists")
        return
    from src.schemas import ImplementationAction
    from src.services.improvements import implement_improvement

    base_slot = seed_window(db, analyst, 12, [22, 26, 32, 52])
    base_report = seed_report(db, analyst, reviewer, base_slot, "呼吸内科加开窗 · 占用演示基线")
    first = db.scalar(select(WaitImprovement).where(WaitImprovement.baseline_report_id == base_report.id))
    if not first:
        first = create_improvement(db, ImprovementCreate(
            baseline_report_id=base_report.id,
            anomaly_sample_code=db.scalars(select(WaitSample.sample_code)
                                           .where(WaitSample.department_slot_id == base_slot.id)
                                           .order_by(WaitSample.id.desc())).first(),
            target_p90=35, action_plan="占用演示事项 A：高峰时段增开分诊台。",
        ), analyst)

    second_slot = seed_window(db, analyst, 13, [24, 27, 33, 49])
    second_report = seed_report(db, analyst, reviewer, second_slot, "呼吸内科加开窗 · 占用演示基线二")
    second = db.scalar(select(WaitImprovement).where(WaitImprovement.baseline_report_id == second_report.id))
    if not second:
        second = create_improvement(db, ImprovementCreate(
            baseline_report_id=second_report.id,
            anomaly_sample_code=db.scalars(select(WaitSample.sample_code)
                                           .where(WaitSample.department_slot_id == second_slot.id)
                                           .order_by(WaitSample.id.desc())).first(),
            target_p90=34, action_plan="占用演示事项 B：复诊预约错峰 15 分钟。",
        ), analyst)

    target_slot = seed_window(db, analyst, 18, [12, 14, 18, 24])
    first_version = seed_report(db, analyst, reviewer, target_slot, "呼吸内科加开窗 · 复测首版")
    redo_version = seed_report(db, analyst, reviewer, target_slot, "呼吸内科加开窗 · 复测重做版")

    for row in (first, second):
        if row.status.value == "planned":
            implement_improvement(db, row.id, ImplementationAction(
                implemented_on=date(2026, 11, 14), implementation_note="按演示方案完成排班调整。",
            ), admin)

    evaluate_improvement(db, first.id, EvaluationAction(
        comparison_report_id=first_version.id, evaluation_note="首版复测 P90 达标，先予验收。",
    ), reviewer)
    withdraw_evaluation(db, first.id, WithdrawalAction(
        withdrawal_note="首版样本需要补录核对，撤回验收并保留原结论。",
    ), reviewer)
    evaluate_improvement(db, second.id, EvaluationAction(
        comparison_report_id=redo_version.id, evaluation_note="使用重做报告验收，占用同一门诊时段。",
    ), reviewer)
    print(
        "claim demo seed ok: history_rows=", len(list_evaluation_history(db)),
        "target_slot_claimed=", db.scalar(select(ImprovementSlotClaim.id).where(
            ImprovementSlotClaim.department_slot_id == target_slot.id)) is not None,
    )


def seed_report(db, analyst, reviewer, slot, title):
    report = db.scalar(select(ReviewReport).where(ReviewReport.department_slot_id == slot.id, ReviewReport.title == title))
    if report:
        return report
    report = create_report(db, slot.id, title, analyst)
    return review_report(db, report, reviewer, "已逐条核对候诊记录与时段分布。")
