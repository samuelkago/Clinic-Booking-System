from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import api_router
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Place for startup hooks (e.g. warm caches). Schema is managed by Alembic.
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description="REST API for a small clinic appointment booking system.",
        lifespan=lifespan,
    )
    app.include_router(api_router)

    @app.get("/", tags=["health"])
    def root() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
