from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import require_roles
from ..database import get_db
from ..models import DepartmentSlot, ReportStatus, ReviewReport, SampleStatus, User, UserRole, WaitSample

router = APIRouter(prefix="/dashboard", tags=["仪表盘"])


@router.get("/summary")
def summary(db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.ANALYST, UserRole.DEPARTMENT_REVIEWER, UserRole.OPERATIONS_ADMIN))):
    return {
        "slot_count": db.scalar(select(func.count(DepartmentSlot.id))) or 0,
        "sample_count": db.scalar(select(func.count(WaitSample.id))) or 0,
        "under_review_count": db.scalar(select(func.count(ReviewReport.id)).where(ReviewReport.status == ReportStatus.UNDER_REVIEW)) or 0,
        "archived_count": db.scalar(select(func.count(ReviewReport.id)).where(ReviewReport.status == ReportStatus.ARCHIVED)) or 0,
        "needs_review_samples": db.scalar(select(func.count(WaitSample.id)).where(WaitSample.status == SampleStatus.NEEDS_REVIEW)) or 0,
    }
