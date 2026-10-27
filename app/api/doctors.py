from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models import Doctor
from app.schemas.appointment import AvailabilityResponse, Slot
from app.schemas.doctor import DoctorRead
from app.services import booking as booking_service

router = APIRouter()


@router.get("/doctors", response_model=list[DoctorRead], summary="List doctors")
def list_doctors(db: Session = Depends(get_db)) -> list[Doctor]:
    return list(db.scalars(select(Doctor).where(Doctor.is_active.is_(True)).order_by(Doctor.id)).all())


@router.get(
    "/doctors/{doctor_id}/availability",
    response_model=AvailabilityResponse,
    summary="Available 30-minute slots for a doctor on a given date",
)
def doctor_availability(
    doctor_id: int,
    date_: date = Query(..., alias="date", description="Calendar date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
) -> AvailabilityResponse:
    try:
        slots = booking_service.list_available_slots(db, doctor_id, date_)
    except booking_service.BookingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    return AvailabilityResponse(
        doctor_id=doctor_id,
        date=date_,
        timezone=get_settings().timezone,
        slots=[Slot(start_at=s, end_at=e) for s, e in slots],
    )
