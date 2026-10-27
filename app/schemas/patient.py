from pydantic import BaseModel, ConfigDict, Field

from app.schemas.appointment import AppointmentRead


class PatientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    phone: str | None = None


class PatientCreate(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=120)
    email: str = Field(..., min_length=3, max_length=255)
    phone: str | None = None


class PatientAppointmentList(BaseModel):
    patient_id: int
    appointments: list[AppointmentRead]
