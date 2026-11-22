from datetime import datetime
import json
import secrets

from fastapi import HTTPException
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from ..models import (
    AttendanceException, AttendanceStatus, DepartmentSlot, ReportAttendanceExclusion,
    ReportStatus, ReviewReport, SampleStatus, User, WaitSample,
)
from .analytics import calculate_review
from .attendance import ensure_no_attendance_hold
from .recovery import capture_recovery_call


def record_sample_event(db: Session, sample: WaitSample, event: str, event_time: datetime, user: User, note: str | None = None):
    ensure_no_attendance_hold(db, sample.id)
    if event == "checkin":
        if sample.status not in (SampleStatus.BOOKED, SampleStatus.NEEDS_REVIEW):
            raise HTTPException(status_code=409, detail="当前样本不能重复签到")
        if event_time < sample.appointment_time.replace(tzinfo=None):
            raise HTTPException(status_code=409, detail="签到时间不能早于预约时间")
        sample.checkin_time = event_time
        sample.status = SampleStatus.CHECKED_IN
    elif event == "call":
        capture_recovery_call(db, sample.id, event_time, user)
        if not sample.checkin_time:
            raise HTTPException(status_code=409, detail="缺少签到时间，不能叫号")
        if event_time < sample.checkin_time:
            raise HTTPException(status_code=409, detail="叫号时间不能早于签到时间")
        sample.called_time = event_time
        sample.status = SampleStatus.CALLED
    elif event == "complete":
        if not sample.called_time:
            raise HTTPException(status_code=409, detail="缺少叫号时间，不能完成接诊")
        if event_time < sample.called_time:
            raise HTTPException(status_code=409, detail="完成时间不能早于叫号时间")
        sample.completed_time = event_time
        sample.status = SampleStatus.COMPLETED
    else:
        raise HTTPException(status_code=400, detail="未知样本事件")
    if note:
        sample.note = note
    db.commit()
    db.refresh(sample)
    return sample


def create_report(db: Session, slot_id: int, title: str, user: User):
    slot = db.get(DepartmentSlot, slot_id)
    if not slot:
        raise HTTPException(status_code=404, detail="科室时段不存在")
    # Read samples and approved exclusions in one SQL snapshot.
    rows = db.execute(select(WaitSample, AttendanceException).outerjoin(
        AttendanceException,
        and_(AttendanceException.sample_id == WaitSample.id, AttendanceException.status == AttendanceStatus.CONFIRMED),
    ).where(WaitSample.department_slot_id == slot_id).order_by(WaitSample.appointment_time)).all()
    result = calculate_review([sample for sample, attendance in rows if attendance is None], slot)
    report = ReviewReport(
        report_code=f"RPT-{slot.slot_date.strftime('%m%d')}-{secrets.token_hex(2).upper()}",
        title=title,
        department_slot_id=slot_id,
        status=ReportStatus.UNDER_REVIEW,
        sample_count=result["sample_count"],
        missing_checkin_count=result["missing_checkin_count"],
        p50_minutes=result["p50_minutes"],
        p90_minutes=result["p90_minutes"],
        median_minutes=result["median_minutes"],
        mad_minutes=result["mad_minutes"],
        anomaly_count=result["anomaly_count"],
        distribution_json=json.dumps(result["distribution"], ensure_ascii=False),
        anomaly_codes_json=json.dumps(result["anomaly_codes"], ensure_ascii=False),
        summary=result["summary"],
        created_by=user.id,
    )
    report.exclusions = [
        ReportAttendanceExclusion(attendance_id=attendance.id, sample_code=sample.sample_code, reason=attendance.reason)
        for sample, attendance in rows if attendance is not None
    ]
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def review_report(db: Session, report: ReviewReport, user: User, note: str):
    if report.status != ReportStatus.UNDER_REVIEW:
        raise HTTPException(status_code=409, detail="只有待科室复核的报告才能复核")
    if report.missing_checkin_count > 0:
        raise HTTPException(status_code=409, detail="存在缺失签到时间的样本，修正后才能发布")
    report.status = ReportStatus.REVIEWED
    report.reviewed_by = user.id
    report.reviewed_at = datetime.utcnow()
    report.review_note = note
    db.commit()
    db.refresh(report)
    return report


def archive_report(db: Session, report: ReviewReport, user: User):
    if report.status != ReportStatus.REVIEWED:
        raise HTTPException(status_code=409, detail="报告需完成科室复核后才能归档")
    if report.missing_checkin_count > 0:
        raise HTTPException(status_code=409, detail="存在缺失签到时间的样本，禁止发布")
    report.status = ReportStatus.ARCHIVED
    report.archived_at = datetime.utcnow()
    db.commit()
    db.refresh(report)
    return report
