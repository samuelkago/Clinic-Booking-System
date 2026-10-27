from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import AppointmentStatus, Doctor, Patient
from app.services import booking as booking_service


def test_reschedule_moves_slot(
    client: TestClient,
    doctor: Doctor,
    patient: Patient,
    bookable_start: datetime,
    db: Session,
):
    appt = booking_service.book_appointment(
        db,
        doctor_id=doctor.id,
        patient_id=patient.id,
        start_at=bookable_start,
    )
    db.flush()

    new_start = bookable_start + timedelta(hours=1)
    response = client.patch(
        f"/appointments/{appt.id}/reschedule",
        json={"start_at": new_start.isoformat()},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["start_at"] == new_start.isoformat()

    # Original slot free again
    rebook = client.post(
        "/appointments",
        json={
            "doctor_id": doctor.id,
            "patient_id": patient.id,
            "start_at": bookable_start.isoformat(),
        },
    )
    assert rebook.status_code == 201, rebook.text


def test_reschedule_cancelled_rejected(
    client: TestClient,
    doctor: Doctor,
    patient: Patient,
    bookable_start: datetime,
    db: Session,
):
    appt = booking_service.book_appointment(
        db,
        doctor_id=doctor.id,
        patient_id=patient.id,
        start_at=bookable_start,
    )
    db.flush()
    booking_service.cancel_appointment(db, appt.id, "no longer needed")
    db.flush()

    response = client.patch(
        f"/appointments/{appt.id}/reschedule",
        json={"start_at": (bookable_start + timedelta(hours=2)).isoformat()},
    )
    assert response.status_code == 409
    assert "cancelled" in response.json()["detail"].lower()


def test_reschedule_to_taken_slot(
    client: TestClient,
    doctor: Doctor,
    patient: Patient,
    bookable_start: datetime,
    db: Session,
):
    first = booking_service.book_appointment(
        db,
        doctor_id=doctor.id,
        patient_id=patient.id,
        start_at=bookable_start,
    )
    other = Patient(full_name="Other", email="other2@example.com")
    db.add(other)
    db.flush()

    taken = bookable_start + timedelta(hours=1)
    booking_service.book_appointment(
        db,
        doctor_id=doctor.id,
        patient_id=other.id,
        start_at=taken,
    )
    db.flush()

    response = client.patch(
        f"/appointments/{first.id}/reschedule",
        json={"start_at": taken.isoformat()},
    )
    assert response.status_code == 409

    # Original booking must remain intact when the new slot is invalid.
    db.refresh(first)
    assert first.start_at == bookable_start
    assert first.status == AppointmentStatus.BOOKED
