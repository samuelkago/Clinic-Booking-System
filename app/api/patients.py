from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.patient import PatientAppointmentList
from app.services import booking as booking_service

router = APIRouter()


@router.get(
    "/patients/{patient_id}/appointments",
    response_model=PatientAppointmentList,
    summary="Upcoming appointments for a patient (sorted by date)",
)
def patient_appointments(
    patient_id: int,
    db: Session = Depends(get_db),
) -> PatientAppointmentList:
    try:
        appointments = booking_service.list_upcoming_patient_appointments(db, patient_id)
    except booking_service.BookingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    return PatientAppointmentList(patient_id=patient_id, appointments=appointments)
