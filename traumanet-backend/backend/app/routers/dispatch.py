"""Router de la Decisión 1: evaluación de FRAP y reserva atómica de recurso crítico."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.core.auth import ActorContext, require_roles
from app.core.dependencies import get_dispatch_service
from app.schemas.dispatch import DispatchEvaluateRequest, DispatchEvaluateResponse
from app.services.dispatch_service import DispatchService

router = APIRouter(prefix="/dispatch", tags=["Despacho (Decisión 1)"])


@router.post(
    "/evaluate-and-assign",
    response_model=DispatchEvaluateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Persiste FRAP en MongoDB, evalúa red en Neo4j y reserva recurso atómico en PostgreSQL",
)
def evaluate_and_assign(
    payload: DispatchEvaluateRequest,
    actor: ActorContext = Depends(require_roles("PARAMEDICO", "CRUM")),
    service: DispatchService = Depends(get_dispatch_service),
) -> DispatchEvaluateResponse:
    return service.evaluate_and_assign(request=payload, actor=actor)
