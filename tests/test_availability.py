from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Doctor, Patient
from app.services import booking as booking_service


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_availability_excludes_booked_slot(
    client: TestClient,
    doctor: Doctor,
    patient: Patient,
    bookable_start: datetime,
    db: Session,
    next_weekday,
):
    booking_service.book_appointment(
        db,
        doctor_id=doctor.id,
        patient_id=patient.id,
        start_at=bookable_start,
    )
    db.flush()

    response = client.get(
        f"/doctors/{doctor.id}/availability",
        params={"date": next_weekday.isoformat()},
    )
    assert response.status_code == 200, response.text
    starts = {_parse_dt(s["start_at"]) for s in response.json()["slots"]}
    assert bookable_start not in starts


def test_availability_empty_on_weekend(
    client: TestClient,
    doctor: Doctor,
    clinic_tz,
):
    # Find next Saturday
    from datetime import timedelta

    day = datetime.now(clinic_tz).date()
    while day.weekday() != 5:
        day += timedelta(days=1)

    response = client.get(
        f"/doctors/{doctor.id}/availability",
        params={"date": day.isoformat()},
    )
    assert response.status_code == 200
    assert response.json()["slots"] == []


def test_availability_unknown_doctor(client: TestClient, next_weekday):
    response = client.get(
        "/doctors/99999/availability",
        params={"date": next_weekday.isoformat()},
    )
    assert response.status_code == 404
