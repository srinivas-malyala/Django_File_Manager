"""FastAPI application factory and ASGI entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import Settings
from .database import Base, build_database
from .routers import auth, files


def create_app(settings: Settings | None = None) -> FastAPI:
    service_settings = settings or Settings()
    service_settings.validate()
    engine, session_factory = build_database(service_settings.database_url)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        service_settings.upload_dir.mkdir(parents=True, exist_ok=True)
        Base.metadata.create_all(engine)
        yield
        engine.dispose()

    application = FastAPI(
        title="Enterprise File Manager API",
        version="1.0.0",
        description="Standalone JWT-authenticated, owner-scoped private file service.",
        lifespan=lifespan,
    )
    application.state.settings = service_settings
    application.state.engine = engine
    application.state.session_factory = session_factory
    application.include_router(auth.router)
    application.include_router(files.router)

    @application.get("/api/health", tags=["operations"])
    def health():
        return {"status": "healthy", "service": "fastapi-file-manager"}

    @application.get("/", include_in_schema=False)
    def root():
        return {"service": "Enterprise File Manager API", "docs": "/docs"}

    return application


app = create_app()
