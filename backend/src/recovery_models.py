from datetime import datetime
from enum import Enum

from sqlalchemy import CheckConstraint, DateTime, Enum as SqlEnum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class RecoveryStatus(str, Enum):
    PENDING = 'pending'
    PRIORITIZED = 'prioritized'
    DISMISSED = 'dismissed'
    RECOVERED = 'recovered'


class QueueRecovery(Base):
    __tablename__ = 'queue_recoveries'
    __table_args__ = (
        CheckConstraint('observed_wait_minutes >= threshold_minutes', name='ck_recovery_breach'),
        CheckConstraint(
            "(status = 'PENDING') = (decided_by IS NULL) AND "
            '(decided_by IS NULL) = (decided_at IS NULL) AND (decided_by IS NULL) = (decision_note IS NULL)',
            name='ck_recovery_decision',
        ),
        CheckConstraint(
            "(status = 'RECOVERED') = (called_at IS NOT NULL) AND "
            '(called_at IS NULL) = (recorded_by IS NULL) AND called_at >= observed_at',
            name='ck_recovery_call',
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    sample_id: Mapped[int] = mapped_column(ForeignKey('wait_samples.id'), unique=True)
    status: Mapped[RecoveryStatus] = mapped_column(SqlEnum(RecoveryStatus, name='recovery_status'))
    observed_at: Mapped[datetime] = mapped_column(DateTime)
    observed_wait_minutes: Mapped[int]
    threshold_minutes: Mapped[int]
    incident_note: Mapped[str] = mapped_column(String(500))
    opened_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    decision_note: Mapped[str | None] = mapped_column(String(500))
    called_at: Mapped[datetime | None] = mapped_column(DateTime)
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'))

    @property
    def recovery_minutes(self) -> int | None:
        if self.called_at is not None:
            return int((self.called_at - self.observed_at).total_seconds() // 60)
        return None
