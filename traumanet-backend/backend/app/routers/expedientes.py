"""Router de consulta de expedientes FRAP unificados (MongoDB + PostgreSQL)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.auth import ActorContext, require_roles
from app.core.dependencies import get_expediente_service
from app.schemas.expediente import ExpedienteFRAPResponse
from app.schemas.frap import EstadoFrap, TipoIncidente
from app.services.expediente_service import ExpedienteService

router = APIRouter(prefix="/expedientes", tags=["Expedientes FRAP"])


@router.get(
    "",
    summary="Lista FRAPs registrados en MongoDB con filtros opcionales por estado y tipo de incidente",
)
def list_expedientes(
    estado_frap: EstadoFrap | None = Query(default=None),
    tipo_incidente: TipoIncidente | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    _actor: ActorContext = Depends(require_roles("CRUM", "PARAMEDICO", "JEFE_URGENCIAS")),
    service: ExpedienteService = Depends(get_expediente_service),
) -> list[dict]:
    return service.list_fraps(
        estado_frap=estado_frap,
        tipo_incidente=tipo_incidente,
        limit=limit,
    )


@router.get(
    "/{frap_id}",
    response_model=ExpedienteFRAPResponse,
    summary="Consulta el expediente FRAP completo (MongoDB) junto con su traslado y reservas (PostgreSQL)",
)
def get_expediente(
    frap_id: str,
    _actor: ActorContext = Depends(require_roles("CRUM", "PARAMEDICO", "JEFE_URGENCIAS")),
    service: ExpedienteService = Depends(get_expediente_service),
) -> ExpedienteFRAPResponse:
    return service.get_expediente(frap_id)
