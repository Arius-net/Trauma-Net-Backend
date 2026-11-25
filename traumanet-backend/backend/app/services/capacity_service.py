"""Servicio de gestión de capacidad hospitalaria y reservas (Jefe de Urgencias / CRUM)."""
from __future__ import annotations

from app.core.auth import ActorContext
from app.core.exceptions import CapacityConflictError
from app.repositories.relational.relational_repo import RelationalRepository
from app.schemas.capacity import (
    CapacityUpdateRequest,
    ExpireReservationsResponse,
    HospitalCapacityResponse,
    ReservaActionResponse,
    ReservaHospitalItem,
)
from app.schemas.network import RecursoResumen


class CapacityService:
    def __init__(self, relational_repo: RelationalRepository) -> None:
        self._relational = relational_repo

    def get_hospital_capacity(self, hospital_id: int) -> HospitalCapacityResponse:
        data = self._relational.get_hospital_capacity(hospital_id)
        return HospitalCapacityResponse(
            hospital_id=data["hospital_id"],
            nombre=data["nombre"],
            recursos=[RecursoResumen(**r) for r in data["recursos"]],
        )

    def get_hospital_reservas(self, hospital_id: int, actor: ActorContext) -> list[ReservaHospitalItem]:
        if (
            actor.role == "JEFE_URGENCIAS"
            and actor.hospital_id is not None
            and actor.hospital_id != hospital_id
        ):
            raise CapacityConflictError(
                f"El Jefe de Urgencias del hospital {actor.hospital_id} no puede consultar reservas del hospital {hospital_id}."
            )
        rows = self._relational.get_reservas_by_hospital(hospital_id)
        return [ReservaHospitalItem(**r) for r in rows]

    def update_capacity(
        self,
        *,
        hospital_id: int,
        payload: CapacityUpdateRequest,
        actor: ActorContext,
    ) -> RecursoResumen:
        if (
            actor.role == "JEFE_URGENCIAS"
            and actor.hospital_id is not None
            and actor.hospital_id != hospital_id
        ):
            raise CapacityConflictError(
                f"El Jefe de Urgencias del hospital {actor.hospital_id} no puede modificar el hospital {hospital_id}."
            )
        updated = self._relational.update_hospital_capacity(
            hospital_id=hospital_id,
            tipo_recurso=payload.tipo_recurso,
            total=payload.total,
            ocupados=payload.ocupados,
            actualizado_por=actor.usuario_id,
        )
        return RecursoResumen(**updated)

    def confirm_reservation(self, reserva_id: str) -> ReservaActionResponse:
        res = self._relational.confirm_reservation(reserva_id)
        return ReservaActionResponse(**res)

    def expire_overdue(self) -> ExpireReservationsResponse:
        count = self._relational.expire_overdue_reservations()
        return ExpireReservationsResponse(reservas_expiradas=count)
