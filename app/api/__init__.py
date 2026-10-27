from fastapi import APIRouter

from app.api import appointments, doctors, patients

api_router = APIRouter()
api_router.include_router(appointments.router, tags=["appointments"])
api_router.include_router(doctors.router, tags=["doctors"])
api_router.include_router(patients.router, tags=["patients"])
