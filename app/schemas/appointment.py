from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.appointment import AppointmentStatus


class AppointmentCreate(BaseModel):
    doctor_id: int
    patient_id: int
    start_at: datetime = Field(
        ...,
        description="Slot start datetime (timezone-aware preferred). Must align to a 30-minute boundary.",
    )


class AppointmentCancel(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class AppointmentReschedule(BaseModel):
    start_at: datetime = Field(
        ...,
        description="New slot start datetime. Must pass the same validation as a fresh booking.",
    )


class AppointmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    doctor_id: int
    patient_id: int
    start_at: datetime
    end_at: datetime
    status: AppointmentStatus
    cancel_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class Slot(BaseModel):
    start_at: datetime
    end_at: datetime


class AvailabilityResponse(BaseModel):
    doctor_id: int
    date: date
    timezone: str
    slots: list[Slot]
