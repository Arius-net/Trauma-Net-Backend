"""Esquemas Pydantic para consulta unificada de expediente FRAP (MongoDB + PostgreSQL)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ReservaExpediente(BaseModel):
    reserva_id: str
    recurso_id: int
    tipo_recurso: str
    cantidad: int
    estado: str
    creada_en: datetime
    expira_en: datetime
    cerrada_en: datetime | None = None


class TrasladoExpediente(BaseModel):
    traslado_id: str
    hospital_destino_id: int
    hospital_destino_nombre: str
    ambulancia_id: int | None = None
    protocolo_codigo: str
    estado: str
    eta_min: float | None = None
    eta_margen_min: float | None = None
    estado_via: str | None = None
    data_vintage: datetime
    creado_en: datetime
    actualizado_en: datetime
    reservas: list[ReservaExpediente]


class ExpedienteFRAPResponse(BaseModel):
    frap_id: str
    frap: dict[str, Any]
    traslado: TrasladoExpediente | None = None
