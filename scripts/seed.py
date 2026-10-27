"""Seed 5 doctors with weekday working hours and a sample patient.

Usage (from project root, with DATABASE_URL set):
    python -m scripts.seed
"""

from __future__ import annotations

from datetime import time

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Doctor, Patient, WorkingHours

DOCTORS = [
    ("Dr. Amina Wanjiku", "General Practice"),
    ("Dr. Brian Otieno", "Pediatrics"),
    ("Dr. Carol Njeri", "Dermatology"),
    ("Dr. David Kimani", "Cardiology"),
    ("Dr. Esther Muthoni", "Orthopedics"),
]

# Mon–Fri 09:00–17:00 (clinic local time)
WEEKDAY_HOURS = (time(9, 0), time(17, 0))


def seed() -> None:
    db = SessionLocal()
    try:
        existing = db.scalar(select(Doctor).limit(1))
        if existing:
            print("Database already seeded; skipping.")
            return

        for name, specialty in DOCTORS:
            doctor = Doctor(full_name=name, specialty=specialty)
            db.add(doctor)
            db.flush()
            for day in range(5):  # Monday–Friday
                db.add(
                    WorkingHours(
                        doctor_id=doctor.id,
                        day_of_week=day,
                        start_time=WEEKDAY_HOURS[0],
                        end_time=WEEKDAY_HOURS[1],
                    )
                )

        db.add(
            Patient(
                full_name="Jane Doe",
                email="jane.doe@example.com",
                phone="+254700000001",
            )
        )
        db.commit()
        print("Seeded 5 doctors (Mon–Fri 09:00–17:00) and 1 sample patient.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
