from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import require_roles
from ..database import get_db
from ..models import (
    AttendanceException, ImprovementEvaluationHistory, ImprovementSlotClaim,
    User, UserRole, WaitImprovement,
)
from ..schemas import (
    AttendanceCreate, AttendanceDecision, AttendanceOut, EvaluationAction,
    EvaluationHistoryOut, ImplementationAction, ImprovementCreate, ImprovementOut,
    ReportOut, SlotClaimOut, AvailableSlotOut, WithdrawalAction,
)
from ..services.attendance import decide_attendance, submit_attendance
from ..services.improvements import (
    create_improvement, evaluate_improvement, implement_improvement,
    list_comparisons, list_evaluation_history, list_slot_claims, withdraw_evaluation,
)
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


def _claim_and_history_maps(db: Session):
    claim_map = {
        item.improvement_id: item.id
        for item in db.scalars(select(ImprovementSlotClaim)).all()
    }
    withdrawn_counts = dict(db.execute(
        select(ImprovementEvaluationHistory.improvement_id, func.count(ImprovementEvaluationHistory.id))
        .group_by(ImprovementEvaluationHistory.improvement_id)
    ).all())
    return claim_map, withdrawn_counts


def serialize_improvement(db: Session, row: WaitImprovement, claim_map: dict[int, int], withdrawn_counts: dict[int, int]) -> dict:
    return {
        "id": row.id,
        "baseline_report_id": row.baseline_report_id,
        "anomaly_sample_code": row.anomaly_sample_code,
        "action_plan": row.action_plan,
        "target_p90": row.target_p90,
        "status": row.status,
        "baseline_p90": row.baseline_p90,
        "created_by": row.created_by,
        "created_at": row.created_at,
        "implemented_by": row.implemented_by,
        "implemented_on": row.implemented_on,
        "implementation_note": row.implementation_note,
        "comparison_report_id": row.comparison_report_id,
        "comparison_p90": row.comparison_p90,
        "evaluated_by": row.evaluated_by,
        "evaluated_at": row.evaluated_at,
        "evaluation_note": row.evaluation_note,
        "outcome": row.outcome,
        "p90_change": row.p90_change,
        "active_claim_id": claim_map.get(row.id),
        "withdrawn_count": withdrawn_counts.get(row.id, 0),
    }


@router.get("/improvements", response_model=list[ImprovementOut])
def improvement_list(db: Session = Depends(get_db), user: User = Depends(read_access)):
    rows = list(db.scalars(select(WaitImprovement).order_by(WaitImprovement.id.desc())))
    claim_map, withdrawn_counts = _claim_and_history_maps(db)
    return [serialize_improvement(db, row, claim_map, withdrawn_counts) for row in rows]


@router.post("/improvements", response_model=ImprovementOut, status_code=201)
def improvement_submit(payload: ImprovementCreate, db: Session = Depends(get_db), user: User = Depends(submit_access)):
    row = create_improvement(db, payload, user)
    return serialize_improvement(db, row, *_claim_and_history_maps(db))


@router.post("/improvements/{row_id}/implement", response_model=ImprovementOut)
def improvement_implementation(row_id: int, payload: ImplementationAction, db: Session = Depends(get_db), user: User = Depends(operations_access)):
    row = implement_improvement(db, row_id, payload, user)
    return serialize_improvement(db, row, *_claim_and_history_maps(db))


@router.get("/improvements/{row_id}/comparisons", response_model=list[ReportOut])
def improvement_comparisons(row_id: int, db: Session = Depends(get_db), user: User = Depends(read_access)):
    return [serialize(report) for report in list_comparisons(db, row_id)]


@router.post("/improvements/{row_id}/evaluate", response_model=ImprovementOut)
def improvement_evaluation(row_id: int, payload: EvaluationAction, db: Session = Depends(get_db), user: User = Depends(review_access)):
    row = evaluate_improvement(db, row_id, payload, user)
    return serialize_improvement(db, row, *_claim_and_history_maps(db))


@router.post("/improvements/{row_id}/withdraw", response_model=ImprovementOut)
def improvement_withdrawal(row_id: int, payload: WithdrawalAction, db: Session = Depends(get_db), user: User = Depends(review_access)):
    row = withdraw_evaluation(db, row_id, payload, user)
    return serialize_improvement(db, row, *_claim_and_history_maps(db))


@router.get("/improvement-slot-claims")
def improvement_slot_claims(db: Session = Depends(get_db), user: User = Depends(read_access)):
    claims, available = list_slot_claims(db)
    user_names = {item.id: item.display_name for item in db.scalars(select(User)).all()}
    claim_payload = [
        SlotClaimOut(
            id=item.id,
            improvement_id=item.improvement_id,
            department_slot_id=item.department_slot_id,
            report_id=item.report_id,
            claimed_by=item.claimed_by,
            claimed_by_name=user_names.get(item.claimed_by, str(item.claimed_by)),
            claimed_at=item.claimed_at,
            department_name=item.slot.department_name,
            slot_date=item.slot.slot_date,
            slot_label=item.slot.slot_label,
            start_time=item.slot.start_time,
            end_time=item.slot.end_time,
            report_code=item.report.report_code,
            report_title=item.report.title,
            report_p90=item.report.p90_minutes,
            improvement_action_plan=item.improvement.action_plan,
            improvement_status=item.improvement.status,
        )
        for item in claims
    ]
    return {"claims": claim_payload, "available_slots": [AvailableSlotOut(**entry) for entry in available]}


@router.get("/improvement-evaluation-history", response_model=list[EvaluationHistoryOut])
def improvement_evaluation_history(db: Session = Depends(get_db), user: User = Depends(read_access)):
    user_names = {item.id: item.display_name for item in db.scalars(select(User)).all()}
    history = list_evaluation_history(db)
    payload = []
    for item in history:
        report = item.comparison_report
        improvement = item.improvement
        payload.append(EvaluationHistoryOut(
            id=item.id,
            improvement_id=item.improvement_id,
            comparison_report_id=item.comparison_report_id,
            comparison_p90=item.comparison_p90,
            evaluation_note=item.evaluation_note,
            evaluated_by=item.evaluated_by,
            evaluated_by_name=user_names.get(item.evaluated_by, str(item.evaluated_by)),
            evaluated_at=item.evaluated_at,
            withdrawal_note=item.withdrawal_note,
            withdrawn_by=item.withdrawn_by,
            withdrawn_by_name=user_names.get(item.withdrawn_by, str(item.withdrawn_by)),
            withdrawn_at=item.withdrawn_at,
            department_name=report.slot.department_name,
            slot_date=report.slot.slot_date,
            slot_label=report.slot.slot_label,
            report_code=report.report_code,
            report_title=report.title,
            outcome="met" if item.comparison_p90 <= improvement.target_p90 else "missed",
            baseline_p90=improvement.baseline_p90,
            target_p90=improvement.target_p90,
            improvement_action_plan=improvement.action_plan,
        ))
    return payload
