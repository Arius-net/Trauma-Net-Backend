"""Esquemas Pydantic para gestión de capacidad hospitalaria y reservas (Jefe de Urgencias)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.dispatch import TipoRecurso
from app.schemas.network import RecursoResumen


class CapacityUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo_recurso: TipoRecurso
    total: int = Field(..., ge=0)
    ocupados: int = Field(..., ge=0)


class HospitalCapacityResponse(BaseModel):
    hospital_id: int
    nombre: str
    recursos: list[RecursoResumen]


class ReservaHospitalItem(BaseModel):
    reserva_id: str
    traslado_id: str
    frap_id: str
    recurso_id: int
    tipo_recurso: str
    cantidad: int
    estado_reserva: str
    estado_traslado: str
    protocolo_codigo: str
    eta_min: float | None = None
    eta_margen_min: float | None = None
    creada_en: datetime
    expira_en: datetime
    cerrada_en: datetime | None = None


class ReservaActionResponse(BaseModel):
    reserva_id: str
    traslado_id: str
    estado_reserva: str
    estado_traslado: str
    cerrada_en: datetime | None = None


class ExpireReservationsResponse(BaseModel):
    reservas_expiradas: int
