from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import require_roles
from ..database import get_db
from ..models import User, UserRole
from ..operations_schemas import RecoveryCandidate, RecoveryCreate, RecoveryDecision, RecoveryOut
from ..services import recovery

router = APIRouter(prefix='/queue-recoveries', tags=['候诊超时处置'])
read_roles = require_roles(UserRole.ANALYST, UserRole.DEPARTMENT_REVIEWER, UserRole.OPERATIONS_ADMIN)
open_roles = require_roles(UserRole.ANALYST, UserRole.OPERATIONS_ADMIN)
reviewer_role = require_roles(UserRole.DEPARTMENT_REVIEWER)


@router.get('', response_model=list[RecoveryOut])
def list_recoveries(db: Session = Depends(get_db), user: User = Depends(read_roles)):
    return recovery.recovery_rows(db)


@router.get('/candidates', response_model=list[RecoveryCandidate])
def list_candidates(db: Session = Depends(get_db), user: User = Depends(open_roles)):
    return recovery.recovery_candidates(db)


@router.post('', response_model=RecoveryOut, status_code=201)
def open_ticket(payload: RecoveryCreate, db: Session = Depends(get_db), user: User = Depends(open_roles)):
    return recovery.recovery_response(db, recovery.open_recovery(db, payload, user))


@router.post('/{recovery_id}/decision', response_model=RecoveryOut)
def decide(recovery_id: int, payload: RecoveryDecision, db: Session = Depends(get_db), user: User = Depends(reviewer_role)):
    return recovery.recovery_response(db, recovery.decide_recovery(db, recovery_id, payload, user))
