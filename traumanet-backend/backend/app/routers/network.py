"""Router de red hospitalaria y derivación en cascada (Grafo + Relacional)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.auth import ActorContext, require_roles
from app.core.dependencies import get_network_service
from app.schemas.frap import ProtocoloCodigo
from app.schemas.network import (
    CascadeDerivationResponse,
    NetworkOverviewResponse,
    TramoUpdateRequest,
    TramoUpdateResponse,
)
from app.services.network_service import NetworkService

router = APIRouter(prefix="/network", tags=["Red Hospitalaria y Cascada"])


@router.get(
    "/hospitals",
    response_model=NetworkOverviewResponse,
    summary="Consulta integrada de hospitales, especialidades, equipos, rutas y capacidad en vivo",
)
def get_network_hospitals(
    _actor: ActorContext = Depends(require_roles("CRUM", "PARAMEDICO", "JEFE_URGENCIAS")),
    service: NetworkService = Depends(get_network_service),
) -> NetworkOverviewResponse:
    return service.get_network_overview()


@router.get(
    "/cascade",
    response_model=CascadeDerivationResponse,
    summary="Propone hospitales vecinos compatibles para derivación en cascada (Decisión 2)",
)
def evaluate_cascade(
    hospital_saturado_id: int = Query(..., ge=1),
    protocolo_codigo: ProtocoloCodigo = Query(...),
    _actor: ActorContext = Depends(require_roles("CRUM", "JEFE_URGENCIAS")),
    service: NetworkService = Depends(get_network_service),
) -> CascadeDerivationResponse:
    return service.evaluate_cascade_derivation(
        hospital_saturado_id=hospital_saturado_id,
        protocolo_codigo=protocolo_codigo,
    )


@router.patch(
    "/tramos/{tramo_id}",
    response_model=TramoUpdateResponse,
    summary="Actualiza estado_via de un tramo carretero en el grafo (normal/demora/bloqueo)",
)
def update_tramo_estado(
    tramo_id: str,
    payload: TramoUpdateRequest,
    _actor: ActorContext = Depends(require_roles("CRUM")),
    service: NetworkService = Depends(get_network_service),
) -> TramoUpdateResponse:
    return service.update_tramo_estado(tramo_id=tramo_id, estado_via=payload.estado_via)
