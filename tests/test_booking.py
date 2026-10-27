from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Doctor, Patient
from app.services import booking as booking_service


def test_book_valid_slot(
    client: TestClient,
    doctor: Doctor,
    patient: Patient,
    bookable_start: datetime,
):
    response = client.post(
        "/appointments",
        json={
            "doctor_id": doctor.id,
            "patient_id": patient.id,
            "start_at": bookable_start.isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "booked"
    assert body["doctor_id"] == doctor.id
    assert body["patient_id"] == patient.id


def test_double_booking_rejected(
    client: TestClient,
    doctor: Doctor,
    patient: Patient,
    bookable_start: datetime,
    db: Session,
):
    booking_service.book_appointment(
        db,
        doctor_id=doctor.id,
        patient_id=patient.id,
        start_at=bookable_start,
    )
    db.flush()

    other = Patient(full_name="Other", email="other@example.com")
    db.add(other)
    db.flush()

    response = client.post(
        "/appointments",
        json={
            "doctor_id": doctor.id,
            "patient_id": other.id,
            "start_at": bookable_start.isoformat(),
        },
    )
    assert response.status_code == 409
    assert "already booked" in response.json()["detail"].lower()


def test_outside_working_hours_rejected(
    client: TestClient,
    doctor: Doctor,
    patient: Patient,
    bookable_start: datetime,
):
    # 08:00 is before 09:00 opening
    bad = bookable_start.replace(hour=8, minute=0)
    response = client.post(
        "/appointments",
        json={
            "doctor_id": doctor.id,
            "patient_id": patient.id,
            "start_at": bad.isoformat(),
        },
    )
    assert response.status_code == 400
    assert "working hours" in response.json()["detail"].lower()


def test_past_slot_rejected(
    client: TestClient,
    doctor: Doctor,
    patient: Patient,
    clinic_tz,
):
    past = datetime.now(clinic_tz) - timedelta(days=1)
    # Snap to a half-hour boundary
    past = past.replace(minute=0 if past.minute < 30 else 30, second=0, microsecond=0)
    response = client.post(
        "/appointments",
        json={
            "doctor_id": doctor.id,
            "patient_id": patient.id,
            "start_at": past.isoformat(),
        },
    )
    assert response.status_code == 400
    assert "minutes in advance" in response.json()["detail"].lower()


def test_cancel_frees_slot(
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

    cancel = client.patch(
        f"/appointments/{appt.id}/cancel",
        json={"reason": "Feeling better"},
    )
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"

    # Same slot bookable again
    rebook = client.post(
        "/appointments",
        json={
            "doctor_id": doctor.id,
            "patient_id": patient.id,
            "start_at": bookable_start.isoformat(),
        },
    )
    assert rebook.status_code == 201, rebook.text


def test_cancel_already_cancelled(
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
    booking_service.cancel_appointment(db, appt.id, "first cancel")
    db.flush()

    response = client.patch(
        f"/appointments/{appt.id}/cancel",
        json={"reason": "again"},
    )
    assert response.status_code == 409
