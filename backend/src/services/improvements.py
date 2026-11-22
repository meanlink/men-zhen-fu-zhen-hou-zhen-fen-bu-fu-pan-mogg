import json
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import (
    DepartmentSlot, ImprovementEvaluationHistory, ImprovementSlotClaim, ImprovementStatus,
    ReportStatus, ReviewReport, User, WaitImprovement,
)
from ..schemas import EvaluationAction, ImplementationAction, ImprovementCreate, WithdrawalAction
from .attendance import CLINIC_TIMEZONE

MIN_SAMPLE_COUNT = 3
FINAL_REPORTS = (ReportStatus.REVIEWED, ReportStatus.ARCHIVED)


def usable_report(db: Session, report_id: int) -> ReviewReport:
    report = db.get(ReviewReport, report_id, with_for_update=True, populate_existing=True)
    if not report:
        raise HTTPException(404, "复盘报告不存在")
    if (report.status not in FINAL_REPORTS or report.missing_checkin_count
            or report.sample_count < MIN_SAMPLE_COUNT or report.p90_minutes is None):
        raise HTTPException(409, "报告须已复核或归档，且至少有 3 条有效样本和完整的候诊记录")
    return report


def create_improvement(db: Session, payload: ImprovementCreate, user: User) -> WaitImprovement:
    report = usable_report(db, payload.baseline_report_id)
    if db.scalar(select(WaitImprovement.id).where(WaitImprovement.baseline_report_id == report.id)):
        raise HTTPException(409, "该基线报告已立项")
    if payload.anomaly_sample_code not in json.loads(report.anomaly_codes_json):
        raise HTTPException(409, "请选择基线报告快照中的异常样本")
    if payload.target_p90 >= report.p90_minutes:
        raise HTTPException(409, "目标 P90 必须低于基线 P90")
    row = WaitImprovement(**payload.model_dump(), baseline_p90=report.p90_minutes,
                          status=ImprovementStatus.PLANNED, created_by=user.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def locked_improvement(db: Session, row_id: int, status: ImprovementStatus) -> WaitImprovement:
    row = db.get(WaitImprovement, row_id, with_for_update=True, populate_existing=True)
    if not row:
        raise HTTPException(404, "改善事项不存在")
    if row.status != status:
        raise HTTPException(409, "当前改善状态不允许执行该操作")
    return row


def implement_improvement(db: Session, row_id: int, payload: ImplementationAction, user: User) -> WaitImprovement:
    row = locked_improvement(db, row_id, ImprovementStatus.PLANNED)
    baseline = db.get(ReviewReport, row.baseline_report_id)
    if not baseline.slot.slot_date < payload.implemented_on <= datetime.now(CLINIC_TIMEZONE).date():
        raise HTTPException(409, "实施日期必须晚于基线时段且不得在未来")
    row.status = ImprovementStatus.IMPLEMENTED
    row.implemented_on = payload.implemented_on
    row.implemented_by = user.id
    row.implementation_note = payload.implementation_note
    db.commit()
    db.refresh(row)
    return row


def candidate_reports(db: Session, row: WaitImprovement):
    """候选对照报告：同科室同名同起止窗口、实施日之后的合格已复核报告。

    其所属门诊时段若已被其他改善事项占用，则不再可选——同一时段并发验收只能通过一项。
    """
    baseline = db.get(ReviewReport, row.baseline_report_id).slot
    other_claim = exists().where(
        ImprovementSlotClaim.department_slot_id == DepartmentSlot.id,
        ImprovementSlotClaim.improvement_id != row.id,
    )
    return select(ReviewReport).join(ReviewReport.slot).where(
        DepartmentSlot.department_name == baseline.department_name,
        DepartmentSlot.slot_label == baseline.slot_label,
        DepartmentSlot.start_time == baseline.start_time,
        DepartmentSlot.end_time == baseline.end_time,
        # Implementation is stored by day. A later day guarantees exposure.
        DepartmentSlot.slot_date > row.implemented_on,
        ReviewReport.status.in_(FINAL_REPORTS),
        ReviewReport.sample_count >= MIN_SAMPLE_COUNT,
        ReviewReport.missing_checkin_count == 0,
        ReviewReport.p90_minutes.is_not(None),
        ~other_claim,
    )


def list_comparisons(db: Session, row_id: int) -> list[ReviewReport]:
    row = db.get(WaitImprovement, row_id)
    if not row:
        raise HTTPException(404, "改善事项不存在")
    if row.status != ImprovementStatus.IMPLEMENTED:
        return []
    return list(db.scalars(candidate_reports(db, row).order_by(DepartmentSlot.slot_date.desc(), ReviewReport.id.desc())))


def evaluate_improvement(db: Session, row_id: int, payload: EvaluationAction, user: User) -> WaitImprovement:
    row = locked_improvement(db, row_id, ImprovementStatus.IMPLEMENTED)
    if row.implemented_by == user.id:
        raise HTTPException(409, "请由另一位人员验收改善措施")
    report = db.scalar(candidate_reports(db, row).where(ReviewReport.id == payload.comparison_report_id))
    if not report:
        raise HTTPException(409, "对照报告须为实施日之后同科室、同窗口的完整已复核报告，且其门诊时段未被其他改善事项占用")
    # 认领的是报告对应的门诊时段；唯一索引保证并发下同一时段只能有一个占用方。
    claim = ImprovementSlotClaim(
        improvement_id=row.id,
        department_slot_id=report.department_slot_id,
        report_id=report.id,
        claimed_by=user.id,
    )
    db.add(claim)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "该门诊时段已被其他改善事项占用，同一时段只能通过一项验收")
    row.status = ImprovementStatus.EVALUATED
    row.comparison_report_id = report.id
    row.comparison_p90 = report.p90_minutes
    row.evaluated_at = datetime.utcnow()
    row.evaluated_by = user.id
    row.evaluation_note = payload.evaluation_note
    db.commit()
    db.refresh(row)
    return row


def withdraw_evaluation(db: Session, row_id: int, payload: WithdrawalAction, user: User) -> WaitImprovement:
    """撤回验收：原结论快照留档，释放本事项的时段占用，事项回到待验收。

    占用按 improvement_id 条件删除，因此旧的重试请求不会重复释放已被其他事项认领的时段。
    """
    row = locked_improvement(db, row_id, ImprovementStatus.EVALUATED)
    snapshot = ImprovementEvaluationHistory(
        improvement_id=row.id,
        comparison_report_id=row.comparison_report_id,
        comparison_p90=row.comparison_p90,
        evaluation_note=row.evaluation_note,
        evaluated_by=row.evaluated_by,
        evaluated_at=row.evaluated_at,
        withdrawal_note=payload.withdrawal_note,
        withdrawn_by=user.id,
    )
    db.add(snapshot)
    # 只删除本事项自己的占用；若该时段已被其他事项重新认领，不会被这里误删。
    db.query(ImprovementSlotClaim).filter(
        ImprovementSlotClaim.improvement_id == row.id).delete(synchronize_session=False)
    row.status = ImprovementStatus.IMPLEMENTED
    row.comparison_report_id = None
    row.comparison_p90 = None
    row.evaluated_by = None
    row.evaluated_at = None
    row.evaluation_note = None
    db.commit()
    db.refresh(row)
    return row


def list_slot_claims(db: Session):
    """改善追踪页使用：返回活跃占用方与可选门诊时段。"""
    claims = list(db.scalars(select(ImprovementSlotClaim).order_by(ImprovementSlotClaim.id.desc())))
    claimed_slot_ids = {item.department_slot_id for item in claims}
    # 可选时段：同科室/窗口中，实施日之后存在合格报告、且当前没有活跃占用的时段。
    rows = db.execute(
        select(DepartmentSlot, ReviewReport)
        .join(ReviewReport, ReviewReport.department_slot_id == DepartmentSlot.id)
        .where(
            ReviewReport.status.in_(FINAL_REPORTS),
            ReviewReport.sample_count >= MIN_SAMPLE_COUNT,
            ReviewReport.missing_checkin_count == 0,
            ReviewReport.p90_minutes.is_not(None),
        )
        .order_by(DepartmentSlot.slot_date.desc(), ReviewReport.id.desc())
    ).all()
    available: dict[int, dict] = {}
    for slot, report in rows:
        if slot.id in claimed_slot_ids:
            continue
        entry = available.setdefault(slot.id, {
            "slot_id": slot.id,
            "department_name": slot.department_name,
            "slot_date": slot.slot_date,
            "slot_label": slot.slot_label,
            "start_time": slot.start_time,
            "end_time": slot.end_time,
            "reports": [],
        })
        entry["reports"].append({
            "id": report.id,
            "report_code": report.report_code,
            "title": report.title,
            "status": report.status,
            "p90_minutes": report.p90_minutes,
            "sample_count": report.sample_count,
            "created_at": report.created_at,
        })
    return claims, list(available.values())


def list_evaluation_history(db: Session) -> list[ImprovementEvaluationHistory]:
    return list(db.scalars(
        select(ImprovementEvaluationHistory).order_by(ImprovementEvaluationHistory.id.desc())))
