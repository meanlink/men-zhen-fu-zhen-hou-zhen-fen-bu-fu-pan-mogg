from fastapi import APIRouter, Depends
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from ..auth import require_roles
from ..capacity_models import CapacityRelease, ReleaseStatus
from ..database import get_db
from ..models import User, UserRole
from ..operations_schemas import ReleaseBookingCreate, ReleaseClose, ReleaseCreate, ReleaseDecision, ReleaseOut
from ..schemas import SampleOut
from ..services import capacity

router = APIRouter(prefix='/capacity-releases', tags=['临时容量'])
read_roles = require_roles(UserRole.ANALYST, UserRole.DEPARTMENT_REVIEWER, UserRole.OPERATIONS_ADMIN)
admin_role = require_roles(UserRole.OPERATIONS_ADMIN)
reviewer_role = require_roles(UserRole.DEPARTMENT_REVIEWER)
booking_roles = require_roles(UserRole.ANALYST, UserRole.OPERATIONS_ADMIN)


@router.get('', response_model=list[ReleaseOut])
def list_releases(db: Session = Depends(get_db), user: User = Depends(read_roles)):
    order = case((CapacityRelease.status == ReleaseStatus.PROPOSED, 0), (CapacityRelease.status == ReleaseStatus.APPROVED, 1), else_=2)
    releases = list(db.scalars(select(CapacityRelease).order_by(order, CapacityRelease.proposed_at.desc())))
    return capacity.describe_releases(db, releases)


@router.post('', response_model=ReleaseOut, status_code=201)
def propose(payload: ReleaseCreate, db: Session = Depends(get_db), user: User = Depends(admin_role)):
    row = capacity.propose_release(db, payload, user)
    return capacity.describe_releases(db, [row])[0]


@router.post('/{release_id}/decision', response_model=ReleaseOut)
def decide(release_id: int, payload: ReleaseDecision, db: Session = Depends(get_db), user: User = Depends(reviewer_role)):
    row = capacity.decide_release(db, release_id, payload, user)
    return capacity.describe_releases(db, [row])[0]


@router.post('/{release_id}/bookings', response_model=SampleOut, status_code=201)
def book(release_id: int, payload: ReleaseBookingCreate, db: Session = Depends(get_db), user: User = Depends(booking_roles)):
    return capacity.issue_booking(db, release_id, payload, user)


@router.post('/{release_id}/close', response_model=ReleaseOut)
def close(release_id: int, payload: ReleaseClose, db: Session = Depends(get_db), user: User = Depends(admin_role)):
    row = capacity.close_release(db, release_id, payload.note, user)
    return capacity.describe_releases(db, [row])[0]
