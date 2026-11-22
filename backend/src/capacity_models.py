from datetime import datetime, time
from enum import Enum

from sqlalchemy import CheckConstraint, DateTime, Enum as SqlEnum, ForeignKey, String, Time
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class ReleaseStatus(str, Enum):
    PROPOSED = 'proposed'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    CLOSED = 'closed'


class CapacityRelease(Base):
    __tablename__ = 'capacity_releases'
    __table_args__ = (
        CheckConstraint('starts_at < ends_at AND quantity BETWEEN 1 AND 100', name='ck_release_window'),
        CheckConstraint(
            "(status = 'PROPOSED') = (decided_by IS NULL) AND "
            '(decided_by IS NULL) = (decided_at IS NULL) AND (decided_by IS NULL) = (decision_note IS NULL)',
            name='ck_release_decision',
        ),
        CheckConstraint(
            "(status = 'CLOSED') = (closed_by IS NOT NULL) AND "
            '(closed_by IS NULL) = (closed_at IS NULL) AND (closed_by IS NULL) = (close_note IS NULL)',
            name='ck_release_close',
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    slot_id: Mapped[int] = mapped_column(ForeignKey('department_slots.id'), index=True)
    starts_at: Mapped[time] = mapped_column(Time)
    ends_at: Mapped[time] = mapped_column(Time)
    quantity: Mapped[int]
    staffing_note: Mapped[str] = mapped_column(String(500))
    status: Mapped[ReleaseStatus] = mapped_column(SqlEnum(ReleaseStatus, name='release_status'))
    proposed_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    proposed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    decision_note: Mapped[str | None] = mapped_column(String(500))
    closed_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    close_note: Mapped[str | None] = mapped_column(String(500))


class ReleasedBooking(Base):
    __tablename__ = 'released_bookings'

    sample_id: Mapped[int] = mapped_column(ForeignKey('wait_samples.id'), primary_key=True)
    release_id: Mapped[int] = mapped_column(ForeignKey('capacity_releases.id'), index=True)
    booked_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    booked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
