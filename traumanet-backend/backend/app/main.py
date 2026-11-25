"""Aplicación principal FastAPI de TraumaNet (D05 — API JWT + CORS + Rebanada vertical)."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import Settings
from app.core.dependencies import ServiceContainer
from app.core.exceptions import (
    CapacityConflictError,
    DocumentUnavailableError,
    DocumentValidationError,
    GraphUnavailableError,
    NotFoundError,
    PartialWriteError,
    RelationalUnavailableError,
)
from app.routers import auth, capacity, dispatch, expedientes, health, network


def create_app(settings: Settings | None = None) -> FastAPI:
    container = ServiceContainer(settings=settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.container.startup()
        try:
            yield
        finally:
            app.state.container.shutdown()

    app = FastAPI(
        title="TraumaNet API",
        version="0.3.0",
        description=(
            "API modular de apoyo a la decisión (DSS) para despacho de emergencias prehospitalarias "
            "y derivación interhospitalaria en el corredor Tuxtla Gutiérrez – San Cristóbal – Comitán. "
            "Autenticación formal JWT Bearer (D-0005 / Q-05). TraumaNet apoya la decisión; no decide."
        ),
        lifespan=lifespan,
    )
    app.state.container = container

    app.add_middleware(
        CORSMiddleware,
        allow_origins=container.settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(PartialWriteError)
    async def _partial_write_handler(_request: Request, exc: PartialWriteError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.payload)

    @app.exception_handler(NotFoundError)
    async def _not_found_handler(_request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})

    @app.exception_handler(DocumentValidationError)
    async def _doc_validation_handler(_request: Request, exc: DocumentValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": str(exc)}
        )

    @app.exception_handler(CapacityConflictError)
    async def _capacity_conflict_handler(_request: Request, exc: CapacityConflictError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})

    @app.exception_handler(RelationalUnavailableError)
    @app.exception_handler(DocumentUnavailableError)
    @app.exception_handler(GraphUnavailableError)
    async def _db_unavailable_handler(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"detail": str(exc)}
        )

    prefix = "/api/v1"
    app.include_router(health.router, prefix=prefix)
    app.include_router(auth.router, prefix=prefix)
    app.include_router(dispatch.router, prefix=prefix)
    app.include_router(network.router, prefix=prefix)
    app.include_router(capacity.router, prefix=prefix)
    app.include_router(expedientes.router, prefix=prefix)

    return app


app = create_app()
