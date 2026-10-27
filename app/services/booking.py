"""Domain logic for availability, booking, cancel, and reschedule."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings, get_settings
from app.models import Appointment, AppointmentStatus, Doctor, Patient, WorkingHours


class BookingError(Exception):
    """Raised for domain validation failures; mapped to HTTP by the API layer."""

    def __init__(self, message: str, *, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _tz(settings: Settings) -> ZoneInfo:
    return ZoneInfo(settings.timezone)


def ensure_aware(dt: datetime, settings: Settings) -> datetime:
    """Normalize naive datetimes to the clinic timezone, then return aware."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_tz(settings))
    return dt


def now_clinic(settings: Settings | None = None) -> datetime:
    settings = settings or get_settings()
    return datetime.now(_tz(settings))


def align_to_slot(dt: datetime, slot_minutes: int) -> bool:
    """Return True if dt falls on a slot boundary (minutes divisible by slot length, seconds=0)."""
    return (
        dt.minute % slot_minutes == 0
        and dt.second == 0
        and dt.microsecond == 0
    )


def get_doctor_or_404(db: Session, doctor_id: int) -> Doctor:
    doctor = db.get(Doctor, doctor_id)
    if doctor is None or not doctor.is_active:
        raise BookingError(f"Doctor {doctor_id} not found.", status_code=404)
    return doctor


def get_patient_or_404(db: Session, patient_id: int) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise BookingError(f"Patient {patient_id} not found.", status_code=404)
    return patient


def get_appointment_or_404(db: Session, appointment_id: int) -> Appointment:
    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        raise BookingError(f"Appointment {appointment_id} not found.", status_code=404)
    return appointment


def _working_hours_for_day(
    db: Session, doctor_id: int, day: date
) -> WorkingHours | None:
    # Python: Monday=0 … Sunday=6 — matches our schema.
    return db.scalar(
        select(WorkingHours).where(
            WorkingHours.doctor_id == doctor_id,
            WorkingHours.day_of_week == day.weekday(),
        )
    )


def _booked_starts_on_day(
    db: Session, doctor_id: int, day: date, settings: Settings
) -> set[datetime]:
    tz = _tz(settings)
    day_start = datetime.combine(day, datetime.min.time(), tzinfo=tz)
    day_end = day_start + timedelta(days=1)

    rows = db.scalars(
        select(Appointment.start_at).where(
            Appointment.doctor_id == doctor_id,
            Appointment.status == AppointmentStatus.BOOKED,
            Appointment.start_at >= day_start,
            Appointment.start_at < day_end,
        )
    ).all()
    return {ensure_aware(r, settings) for r in rows}


def generate_day_slots(
    day: date,
    hours: WorkingHours,
    settings: Settings,
) -> list[tuple[datetime, datetime]]:
    """All possible 30-minute slots within working hours for a calendar day."""
    tz = _tz(settings)
    slot = timedelta(minutes=settings.slot_minutes)
    cursor = datetime.combine(day, hours.start_time, tzinfo=tz)
    end = datetime.combine(day, hours.end_time, tzinfo=tz)

    slots: list[tuple[datetime, datetime]] = []
    while cursor + slot <= end:
        slots.append((cursor, cursor + slot))
        cursor += slot
    return slots


def list_available_slots(
    db: Session,
    doctor_id: int,
    day: date,
    settings: Settings | None = None,
) -> list[tuple[datetime, datetime]]:
    settings = settings or get_settings()
    get_doctor_or_404(db, doctor_id)

    hours = _working_hours_for_day(db, doctor_id, day)
    if hours is None:
        return []

    booked = _booked_starts_on_day(db, doctor_id, day, settings)
    lead = timedelta(minutes=settings.min_booking_lead_minutes)
    earliest = now_clinic(settings) + lead

    available: list[tuple[datetime, datetime]] = []
    for start, end in generate_day_slots(day, hours, settings):
        if start in booked:
            continue
        if start < earliest:
            continue
        available.append((start, end))
    return available


def validate_slot(
    db: Session,
    doctor_id: int,
    start_at: datetime,
    settings: Settings | None = None,
    *,
    exclude_appointment_id: int | None = None,
) -> tuple[datetime, datetime]:
    """Validate a candidate booking slot. Returns (start_at, end_at) on success."""
    settings = settings or get_settings()
    get_doctor_or_404(db, doctor_id)

    start_at = ensure_aware(start_at, settings)
    if not align_to_slot(start_at, settings.slot_minutes):
        raise BookingError(
            f"start_at must align to a {settings.slot_minutes}-minute slot boundary "
            "(seconds and microseconds must be zero)."
        )

    end_at = start_at + timedelta(minutes=settings.slot_minutes)
    lead = timedelta(minutes=settings.min_booking_lead_minutes)
    if start_at < now_clinic(settings) + lead:
        raise BookingError(
            f"Appointments must be booked at least {settings.min_booking_lead_minutes} "
            "minutes in advance."
        )

    day = start_at.astimezone(_tz(settings)).date()
    hours = _working_hours_for_day(db, doctor_id, day)
    if hours is None:
        raise BookingError("Doctor has no working hours on this day.")

    valid = {(s, e) for s, e in generate_day_slots(day, hours, settings)}
    if (start_at, end_at) not in valid:
        raise BookingError("Requested slot falls outside the doctor's working hours.")

    conflict_q = select(Appointment).where(
        Appointment.doctor_id == doctor_id,
        Appointment.start_at == start_at,
        Appointment.status == AppointmentStatus.BOOKED,
    )
    if exclude_appointment_id is not None:
        conflict_q = conflict_q.where(Appointment.id != exclude_appointment_id)

    conflict = db.scalar(conflict_q)
    if conflict is not None:
        raise BookingError("This slot is already booked.", status_code=409)

    return start_at, end_at


def book_appointment(
    db: Session,
    *,
    doctor_id: int,
    patient_id: int,
    start_at: datetime,
    settings: Settings | None = None,
) -> Appointment:
    settings = settings or get_settings()
    get_patient_or_404(db, patient_id)
    start_at, end_at = validate_slot(db, doctor_id, start_at, settings)

    appointment = Appointment(
        doctor_id=doctor_id,
        patient_id=patient_id,
        start_at=start_at,
        end_at=end_at,
        status=AppointmentStatus.BOOKED,
    )
    db.add(appointment)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise BookingError("This slot is already booked.", status_code=409) from exc

    db.refresh(appointment)
    return appointment


def cancel_appointment(
    db: Session,
    appointment_id: int,
    reason: str,
) -> Appointment:
    appointment = get_appointment_or_404(db, appointment_id)
    if appointment.status == AppointmentStatus.CANCELLED:
        raise BookingError("Appointment is already cancelled.", status_code=409)

    appointment.status = AppointmentStatus.CANCELLED
    appointment.cancel_reason = reason
    db.flush()
    db.refresh(appointment)
    return appointment


def reschedule_appointment(
    db: Session,
    appointment_id: int,
    new_start_at: datetime,
    settings: Settings | None = None,
) -> Appointment:
    settings = settings or get_settings()
    appointment = get_appointment_or_404(db, appointment_id)

    if appointment.status == AppointmentStatus.CANCELLED:
        raise BookingError("Cannot reschedule a cancelled appointment.", status_code=409)

    new_start, new_end = validate_slot(
        db,
        appointment.doctor_id,
        new_start_at,
        settings,
        exclude_appointment_id=appointment.id,
    )

    appointment.start_at = new_start
    appointment.end_at = new_end
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise BookingError("This slot is already booked.", status_code=409) from exc

    db.refresh(appointment)
    return appointment


def list_upcoming_patient_appointments(
    db: Session,
    patient_id: int,
    settings: Settings | None = None,
) -> list[Appointment]:
    settings = settings or get_settings()
    get_patient_or_404(db, patient_id)
    now = now_clinic(settings)

    return list(
        db.scalars(
            select(Appointment)
            .where(
                Appointment.patient_id == patient_id,
                Appointment.status == AppointmentStatus.BOOKED,
                Appointment.start_at >= now,
            )
            .order_by(Appointment.start_at.asc())
            .options(selectinload(Appointment.doctor))
        ).all()
    )
