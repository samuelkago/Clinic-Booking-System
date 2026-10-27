"""True concurrent inserts against PostgreSQL (bypasses nested-test savepoints)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models import Doctor, Patient, WorkingHours
from app.services import booking as booking_service
from app.services.booking import BookingError


def _next_weekday(clinic_tz: ZoneInfo) -> date:
    settings = get_settings()
    lead = timedelta(minutes=settings.min_booking_lead_minutes + 30)
    candidate = (datetime.now(clinic_tz) + lead + timedelta(days=1)).date()
    while candidate.weekday() > 4:
        candidate += timedelta(days=1)
    return candidate


def test_concurrent_bookings_only_one_succeeds(engine):
    """Two simultaneous commits for the same slot → exactly one wins (partial unique index)."""
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    clinic_tz = ZoneInfo(get_settings().timezone)
    start = datetime.combine(_next_weekday(clinic_tz), time(11, 0), tzinfo=clinic_tz)

    setup = SessionLocal()
    try:
        doctor = Doctor(full_name="Dr. Concurrent", specialty="General")
        setup.add(doctor)
        setup.flush()
        for day in range(5):
            setup.add(
                WorkingHours(
                    doctor_id=doctor.id,
                    day_of_week=day,
                    start_time=time(9, 0),
                    end_time=time(17, 0),
                )
            )
        p1 = Patient(full_name="Patient A", email="concurrent-a@example.com")
        p2 = Patient(full_name="Patient B", email="concurrent-b@example.com")
        setup.add_all([p1, p2])
        setup.commit()
        doctor_id, patient_a, patient_b = doctor.id, p1.id, p2.id
    finally:
        setup.close()

    def attempt(patient_id: int) -> str:
        db: Session = SessionLocal()
        try:
            booking_service.book_appointment(
                db,
                doctor_id=doctor_id,
                patient_id=patient_id,
                start_at=start,
            )
            db.commit()
            return "ok"
        except BookingError:
            db.rollback()
            return "conflict"
        except Exception:
            db.rollback()
            return "error"
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt, patient_a), pool.submit(attempt, patient_b)]
        results = [f.result() for f in as_completed(futures)]

    assert results.count("ok") == 1, results
    assert results.count("conflict") == 1, results
