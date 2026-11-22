import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_roles
from ..database import get_db
from ..models import ReportStatus, ReviewReport, User, UserRole
from ..schemas import ReportCreate, ReportOut, ReviewAction
from ..services.workflow import archive_report, create_report, review_report

router = APIRouter(prefix="/reports", tags=["复盘报告"])


def serialize(report: ReviewReport):
    return {
        "id": report.id,
        "report_code": report.report_code,
        "title": report.title,
        "department_slot_id": report.department_slot_id,
        "status": report.status,
        "sample_count": report.sample_count,
        "missing_checkin_count": report.missing_checkin_count,
        "p50_minutes": report.p50_minutes,
        "p90_minutes": report.p90_minutes,
        "median_minutes": report.median_minutes,
        "mad_minutes": report.mad_minutes,
        "anomaly_count": report.anomaly_count,
        "distribution": json.loads(report.distribution_json or "[]"),
        "anomaly_codes": json.loads(report.anomaly_codes_json or "[]"),
        "exclusions": report.exclusions,
        "summary": report.summary,
        "review_note": report.review_note,
        "created_at": report.created_at,
        "reviewed_at": report.reviewed_at,
        "archived_at": report.archived_at,
    }


@router.get("", response_model=list[ReportOut])
def list_reports(db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.ANALYST, UserRole.DEPARTMENT_REVIEWER, UserRole.OPERATIONS_ADMIN))):
    reports = db.scalars(select(ReviewReport).order_by(ReviewReport.created_at.desc())).all()
    return [serialize(item) for item in reports]


@router.post("", response_model=ReportOut)
def generate(payload: ReportCreate, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.ANALYST, UserRole.OPERATIONS_ADMIN))):
    return serialize(create_report(db, payload.department_slot_id, payload.title, user))


@router.post("/{report_id}/review", response_model=ReportOut)
def review(report_id: int, payload: ReviewAction, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.DEPARTMENT_REVIEWER, UserRole.OPERATIONS_ADMIN))):
    report = db.get(ReviewReport, report_id, with_for_update=True)
    if not report:
        raise HTTPException(status_code=404, detail="复盘报告不存在")
    return serialize(review_report(db, report, user, payload.review_note))


@router.post("/{report_id}/archive", response_model=ReportOut)
def archive(report_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OPERATIONS_ADMIN))):
    report = db.get(ReviewReport, report_id, with_for_update=True)
    if not report:
        raise HTTPException(status_code=404, detail="复盘报告不存在")
    return serialize(archive_report(db, report, user))
