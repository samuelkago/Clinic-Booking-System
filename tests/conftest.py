"""Shared fixtures. Uses PostgreSQL (same server as .env, database clinic_booking_test)."""

from __future__ import annotations

from collections.abc import Generator
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models import Doctor, Patient, WorkingHours

import app.models  # noqa: F401


def _test_database_url() -> str:
    base = get_settings().database_url
    prefix, _dbname = base.rsplit("/", 1)
    return f"{prefix}/clinic_booking_test"


@pytest.fixture(scope="session")
def engine():
    url = _test_database_url()
    admin_url = url.rsplit("/", 1)[0] + "/postgres"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    db_name = url.rsplit("/", 1)[-1]
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"),
            {"n": db_name},
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    admin.dispose()

    eng = create_engine(url, poolclass=NullPool)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def db(engine) -> Generator[Session, None, None]:
    """Session wrapped in an outer transaction; commits only release savepoints."""
    connection = engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(bind=connection, autocommit=False, autoflush=False)
    session = SessionLocal()
    session.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess: Session, trans) -> None:  # type: ignore[no-untyped-def]
        if trans.nested and not trans._parent.nested:  # noqa: SLF001
            sess.begin_nested()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    app = create_app()

    def _override() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def clinic_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


@pytest.fixture
def doctor(db: Session) -> Doctor:
    doc = Doctor(full_name="Dr. Test", specialty="General")
    db.add(doc)
    db.flush()
    for day in range(5):
        db.add(
            WorkingHours(
                doctor_id=doc.id,
                day_of_week=day,
                start_time=time(9, 0),
                end_time=time(17, 0),
            )
        )
    db.flush()
    return doc


@pytest.fixture
def patient(db: Session) -> Patient:
    p = Patient(full_name="Test Patient", email="patient@example.com")
    db.add(p)
    db.flush()
    return p


@pytest.fixture
def next_weekday(clinic_tz: ZoneInfo) -> date:
    """First weekday far enough ahead to clear the min-lead booking rule."""
    settings = get_settings()
    lead = timedelta(minutes=settings.min_booking_lead_minutes + 30)
    candidate = (datetime.now(clinic_tz) + lead + timedelta(days=1)).date()
    while candidate.weekday() > 4:
        candidate += timedelta(days=1)
    return candidate


@pytest.fixture
def bookable_start(next_weekday: date, clinic_tz: ZoneInfo) -> datetime:
    return datetime.combine(next_weekday, time(10, 0), tzinfo=clinic_tz)
