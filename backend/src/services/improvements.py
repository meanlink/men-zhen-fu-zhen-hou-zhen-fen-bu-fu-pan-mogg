import json
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import DepartmentSlot, ImprovementStatus, ReportStatus, ReviewReport, User, WaitImprovement
from ..schemas import EvaluationAction, ImplementationAction, ImprovementCreate
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
    baseline = db.get(ReviewReport, row.baseline_report_id).slot
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
        raise HTTPException(409, "对照报告须为实施日之后同科室、同窗口的完整已复核报告，且至少有 3 条有效样本")
    row.status = ImprovementStatus.EVALUATED
    row.comparison_report_id = report.id
    row.comparison_p90 = report.p90_minutes
    row.evaluated_at = datetime.utcnow()
    row.evaluated_by = user.id
    row.evaluation_note = payload.evaluation_note
    db.commit()
    db.refresh(row)
    return row
