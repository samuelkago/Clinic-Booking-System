from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.doctor import Doctor


class WorkingHours(Base):
    """Doctor availability for a weekday (0=Monday … 6=Sunday)."""

    __tablename__ = "working_hours"
    __table_args__ = (
        UniqueConstraint("doctor_id", "day_of_week", name="uq_doctor_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"), nullable=False, index=True)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)  # 0–6
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)

    doctor: Mapped[Doctor] = relationship(back_populates="working_hours")
