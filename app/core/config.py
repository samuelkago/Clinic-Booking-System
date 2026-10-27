from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Clinic Booking System"
    app_env: str = "development"
    debug: bool = False

    database_url: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/clinic_booking"
    )

    slot_minutes: int = 30
    min_booking_lead_minutes: int = 60
    timezone: str = "Africa/Nairobi"


@lru_cache
def get_settings() -> Settings:
    return Settings()
