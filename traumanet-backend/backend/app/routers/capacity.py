"""Router de capacidad hospitalaria y gestión de reservas (Jefe de Urgencias / CRUM)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.auth import ActorContext, require_roles
from app.core.dependencies import get_capacity_service
from app.schemas.capacity import (
    CapacityUpdateRequest,
    ExpireReservationsResponse,
    HospitalCapacityResponse,
    ReservaActionResponse,
    ReservaHospitalItem,
)
from app.schemas.network import RecursoResumen
from app.services.capacity_service import CapacityService

router = APIRouter(tags=["Capacidad Hospitalaria y Reservas"])


@router.get(
    "/hospitals/{hospital_id}/capacity",
    response_model=HospitalCapacityResponse,
    summary="Consulta inventario en vivo de un hospital (expirando reservas vencidas)",
)
def get_hospital_capacity(
    hospital_id: int,
    _actor: ActorContext = Depends(require_roles("CRUM", "JEFE_URGENCIAS", "PARAMEDICO")),
    service: CapacityService = Depends(get_capacity_service),
) -> HospitalCapacityResponse:
    return service.get_hospital_capacity(hospital_id)


@router.get(
    "/hospitals/{hospital_id}/reservas",
    response_model=list[ReservaHospitalItem],
    summary="Lista las reservas entrantes e históricas de un hospital",
)
def get_hospital_reservas(
    hospital_id: int,
    actor: ActorContext = Depends(require_roles("JEFE_URGENCIAS", "CRUM")),
    service: CapacityService = Depends(get_capacity_service),
) -> list[ReservaHospitalItem]:
    return service.get_hospital_reservas(hospital_id=hospital_id, actor=actor)


@router.put(
    "/hospitals/{hospital_id}/capacity",
    response_model=RecursoResumen,
    summary="Actualiza total y ocupados de un recurso (protegido por CHECK disponibles >= 0)",
)
def update_hospital_capacity(
    hospital_id: int,
    payload: CapacityUpdateRequest,
    actor: ActorContext = Depends(require_roles("JEFE_URGENCIAS", "CRUM")),
    service: CapacityService = Depends(get_capacity_service),
) -> RecursoResumen:
    return service.update_capacity(hospital_id=hospital_id, payload=payload, actor=actor)


@router.post(
    "/reservas/{reserva_id}/confirm",
    response_model=ReservaActionResponse,
    summary="Confirma una reserva activa (ya no expira por TTL)",
)
def confirm_reservation(
    reserva_id: str,
    _actor: ActorContext = Depends(require_roles("JEFE_URGENCIAS", "CRUM")),
    service: CapacityService = Depends(get_capacity_service),
) -> ReservaActionResponse:
    return service.confirm_reservation(reserva_id)


@router.post(
    "/reservas/expire-overdue",
    response_model=ExpireReservationsResponse,
    summary="Ejecuta el barrido idempotente de expiración de reservas vencidas (TTL)",
)
def expire_overdue_reservations(
    _actor: ActorContext = Depends(require_roles("CRUM", "JEFE_URGENCIAS")),
    service: CapacityService = Depends(get_capacity_service),
) -> ExpireReservationsResponse:
    return service.expire_overdue()
