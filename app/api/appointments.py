from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.appointment import (
    AppointmentCancel,
    AppointmentCreate,
    AppointmentRead,
    AppointmentReschedule,
)
from app.services import booking as booking_service

router = APIRouter()


def _raise(exc: booking_service.BookingError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.post(
    "/appointments",
    response_model=AppointmentRead,
    status_code=201,
    summary="Book an appointment slot",
)
def create_appointment(
    payload: AppointmentCreate,
    db: Session = Depends(get_db),
) -> AppointmentRead:
    try:
        appointment = booking_service.book_appointment(
            db,
            doctor_id=payload.doctor_id,
            patient_id=payload.patient_id,
            start_at=payload.start_at,
        )
    except booking_service.BookingError as exc:
        _raise(exc)
    db.commit()
    db.refresh(appointment)
    return appointment


@router.patch(
    "/appointments/{appointment_id}/cancel",
    response_model=AppointmentRead,
    summary="Cancel an appointment",
)
def cancel_appointment(
    appointment_id: int,
    payload: AppointmentCancel,
    db: Session = Depends(get_db),
) -> AppointmentRead:
    try:
        appointment = booking_service.cancel_appointment(
            db, appointment_id, payload.reason
        )
    except booking_service.BookingError as exc:
        _raise(exc)
    db.commit()
    db.refresh(appointment)
    return appointment


@router.patch(
    "/appointments/{appointment_id}/reschedule",
    response_model=AppointmentRead,
    summary="Reschedule an appointment to a new slot",
)
def reschedule_appointment(
    appointment_id: int,
    payload: AppointmentReschedule,
    db: Session = Depends(get_db),
) -> AppointmentRead:
    try:
        appointment = booking_service.reschedule_appointment(
            db, appointment_id, payload.start_at
        )
    except booking_service.BookingError as exc:
        _raise(exc)
    db.commit()
    db.refresh(appointment)
    return appointment
