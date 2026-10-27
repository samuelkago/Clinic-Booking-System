from app.schemas.appointment import (
    AppointmentCancel,
    AppointmentCreate,
    AppointmentRead,
    AppointmentReschedule,
    AvailabilityResponse,
    Slot,
)
from app.schemas.doctor import DoctorRead
from app.schemas.patient import PatientAppointmentList, PatientRead

__all__ = [
    "AppointmentCancel",
    "AppointmentCreate",
    "AppointmentRead",
    "AppointmentReschedule",
    "AvailabilityResponse",
    "DoctorRead",
    "PatientAppointmentList",
    "PatientRead",
    "Slot",
]
