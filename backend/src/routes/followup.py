from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_roles
from ..database import get_db
from ..models import AttendanceException, User, UserRole, WaitImprovement
from ..schemas import (
    AttendanceCreate, AttendanceDecision, AttendanceOut, EvaluationAction,
    ImplementationAction, ImprovementCreate, ImprovementOut, ReportOut,
)
from ..services.attendance import decide_attendance, submit_attendance
from ..services.improvements import create_improvement, evaluate_improvement, implement_improvement, list_comparisons
from .reports import serialize

router = APIRouter(tags=["到诊核销与改善追踪"])
read_access = require_roles(*UserRole)
submit_access = require_roles(UserRole.ANALYST, UserRole.OPERATIONS_ADMIN)
review_access = require_roles(UserRole.DEPARTMENT_REVIEWER, UserRole.OPERATIONS_ADMIN)
operations_access = require_roles(UserRole.OPERATIONS_ADMIN)


@router.get("/attendance-exceptions", response_model=list[AttendanceOut])
def attendance_list(db: Session = Depends(get_db), user: User = Depends(read_access)):
    return list(db.scalars(select(AttendanceException).order_by(AttendanceException.id.desc())))


@router.post("/attendance-exceptions", response_model=AttendanceOut, status_code=201)
def attendance_submit(payload: AttendanceCreate, db: Session = Depends(get_db), user: User = Depends(submit_access)):
    return submit_attendance(db, payload, user)


@router.post("/attendance-exceptions/{attendance_id}/decision", response_model=AttendanceOut)
def attendance_decision(attendance_id: int, payload: AttendanceDecision, db: Session = Depends(get_db), user: User = Depends(review_access)):
    return decide_attendance(db, attendance_id, payload, user)


@router.get("/improvements", response_model=list[ImprovementOut])
def improvement_list(db: Session = Depends(get_db), user: User = Depends(read_access)):
    return list(db.scalars(select(WaitImprovement).order_by(WaitImprovement.id.desc())))


@router.post("/improvements", response_model=ImprovementOut, status_code=201)
def improvement_submit(payload: ImprovementCreate, db: Session = Depends(get_db), user: User = Depends(submit_access)):
    return create_improvement(db, payload, user)


@router.post("/improvements/{row_id}/implement", response_model=ImprovementOut)
def improvement_implementation(row_id: int, payload: ImplementationAction, db: Session = Depends(get_db), user: User = Depends(operations_access)):
    return implement_improvement(db, row_id, payload, user)


@router.get("/improvements/{row_id}/comparisons", response_model=list[ReportOut])
def improvement_comparisons(row_id: int, db: Session = Depends(get_db), user: User = Depends(read_access)):
    return [serialize(report) for report in list_comparisons(db, row_id)]


@router.post("/improvements/{row_id}/evaluate", response_model=ImprovementOut)
def improvement_evaluation(row_id: int, payload: EvaluationAction, db: Session = Depends(get_db), user: User = Depends(review_access)):
    return evaluate_improvement(db, row_id, payload, user)
